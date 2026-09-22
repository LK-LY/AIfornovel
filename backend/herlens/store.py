"""SQLite persistence for the HerLens local service.

The store keeps complete, versioned work documents as JSON while maintaining
separate durable ledgers for runs, reports, and annotation history.  SQLite
transactions provide the global revision compare-and-swap used by the API.
"""

from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterator
from uuid import uuid4

from .extraction import ProviderConfig, load_seed_works, utc_now, validate_annotation
from .schemas import SCHEMA_VERSION


class StoreError(RuntimeError):
    pass


class ReadOnlyError(StoreError):
    pass


class NotFoundError(StoreError):
    pass


class RevisionConflict(StoreError):
    def __init__(self, expected: int, current: int):
        super().__init__(f"revision conflict: expected {expected}, current {current}")
        self.expected = expected
        self.current = current


class IdempotencyConflict(StoreError):
    pass


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: str) -> Any:
    return json.loads(value)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class Store:
    def __init__(self, path: str | Path | None = None, *, read_only: bool | None = None):
        if path is None:
            project_root = Path(__file__).resolve().parents[2]
            data_dir = Path(os.getenv("HERLENS_DATA_DIR", str(project_root / "private-data")))
            resolved = data_dir / "herlens.sqlite3"
        else:
            resolved = Path(path)
            if resolved.exists() and resolved.is_dir():
                resolved = resolved / "herlens.sqlite3"
        self.path = resolved.expanduser().resolve()
        self.read_only = _truthy(os.getenv("HERLENS_READ_ONLY")) if read_only is None else read_only
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._bootstrap_seed()
        if not self.read_only:
            self.mark_unfinished_interrupted()

    @property
    def mode(self) -> str:
        return "readonly" if self.read_only else "local"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 15000")
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS works (
                    id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL UNIQUE,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    fingerprint TEXT NOT NULL,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS history (
                    id TEXT PRIMARY KEY,
                    annotation_id TEXT,
                    revision INTEGER NOT NULL,
                    before_data TEXT,
                    after_data TEXT,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS history_revision_idx ON history(revision);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO metadata(key, value) VALUES ('revision', '0')"
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )

    def _bootstrap_seed(self) -> None:
        seed_works = load_seed_works()
        if not seed_works:
            return
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                count = connection.execute("SELECT COUNT(*) FROM works").fetchone()[0]
                if count:
                    connection.execute("COMMIT")
                    return
                for work in seed_works:
                    work = deepcopy(work)
                    work["revision"] = 1
                    for annotation in work.get("annotations", []):
                        annotation["revision"] = 1
                    connection.execute(
                        "INSERT INTO works(id, content_hash, data) VALUES (?, ?, ?)",
                        (work["id"], work["contentHash"], _encode(work)),
                    )
                connection.execute(
                    "UPDATE metadata SET value = '1' WHERE key = 'revision'"
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _ensure_writable(self) -> None:
        if self.read_only:
            raise ReadOnlyError("HerLens is running in read-only mode")

    @staticmethod
    def _revision(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'revision'"
        ).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _next_revision(connection: sqlite3.Connection) -> int:
        revision = Store._revision(connection) + 1
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'revision'", (str(revision),)
        )
        return revision

    def revision(self) -> int:
        with self._lock, self._connect() as connection:
            return self._revision(connection)

    def list_works(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            return [
                _decode(row["data"])
                for row in connection.execute("SELECT data FROM works ORDER BY rowid")
            ]

    def get_work(self, work_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM works WHERE id = ?", (work_id,)
            ).fetchone()
            return _decode(row["data"]) if row else None

    def add_work(self, work: dict[str, Any]) -> tuple[str, dict[str, Any], int]:
        """Insert one work or return its exact content duplicate."""

        self._ensure_writable()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                duplicate = connection.execute(
                    "SELECT data FROM works WHERE content_hash = ?", (work["contentHash"],)
                ).fetchone()
                if duplicate:
                    existing = _decode(duplicate["data"])
                    revision = self._revision(connection)
                    connection.execute("COMMIT")
                    return "duplicate", existing, revision
                revision = self._next_revision(connection)
                persisted = deepcopy(work)
                persisted["revision"] = revision
                for annotation in persisted.get("annotations", []):
                    annotation["revision"] = revision
                connection.execute(
                    "INSERT INTO works(id, content_hash, data) VALUES (?, ?, ?)",
                    (persisted["id"], persisted["contentHash"], _encode(persisted)),
                )
                connection.execute("COMMIT")
                return "imported", persisted, revision
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def find_annotation(self, annotation_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        for work in self.list_works():
            for annotation in work.get("annotations", []):
                if annotation.get("id") == annotation_id:
                    return work, annotation
        return None

    @staticmethod
    def _write_history(
        connection: sqlite3.Connection,
        *,
        annotation_id: str | None,
        revision: int,
        before: Any,
        after: Any,
        reason: str,
    ) -> None:
        connection.execute(
            """INSERT INTO history
               (id, annotation_id, revision, before_data, after_data, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                f"hist-{uuid4().hex}",
                annotation_id,
                revision,
                _encode(before) if before is not None else None,
                _encode(after) if after is not None else None,
                reason,
                utc_now(),
            ),
        )

    def patch_annotation(
        self,
        annotation_id: str,
        patch: dict[str, Any],
        *,
        expected_revision: int,
    ) -> tuple[dict[str, Any], int]:
        self._ensure_writable()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current_revision = self._revision(connection)
                if expected_revision != current_revision:
                    raise RevisionConflict(expected_revision, current_revision)
                rows = connection.execute("SELECT id, data FROM works ORDER BY rowid").fetchall()
                target_work: dict[str, Any] | None = None
                target_index = -1
                for row in rows:
                    candidate = _decode(row["data"])
                    for index, annotation in enumerate(candidate.get("annotations", [])):
                        if annotation.get("id") == annotation_id:
                            target_work = candidate
                            target_index = index
                            break
                    if target_work is not None:
                        break
                if target_work is None:
                    raise NotFoundError(f"annotation {annotation_id!r} was not found")

                before = deepcopy(target_work["annotations"][target_index])
                after = deepcopy(before)
                after.update(
                    {
                        "value": patch["value"],
                        "rationale": patch["rationale"],
                        "evidenceIds": list(patch.get("evidenceIds", [])),
                        "reviewStatus": patch["reviewStatus"],
                    }
                )
                validate_annotation(target_work, after)
                revision = self._next_revision(connection)
                after["revision"] = revision
                target_work["annotations"][target_index] = after
                target_work["revision"] = revision
                target_work["updatedAt"] = utc_now()
                if after["reviewStatus"] == "已审核":
                    selected = set(after["evidenceIds"])
                    for evidence in target_work.get("evidence", []):
                        if evidence.get("id") in selected:
                            evidence["reviewStatus"] = "已审核"
                self._write_history(
                    connection,
                    annotation_id=annotation_id,
                    revision=revision,
                    before=before,
                    after=after,
                    reason="manual annotation review",
                )
                connection.execute(
                    "UPDATE works SET data = ? WHERE id = ?",
                    (_encode(target_work), target_work["id"]),
                )
                connection.execute("COMMIT")
                return after, revision
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def apply_extraction(
        self,
        work_id: str,
        annotations: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        *,
        reason: str,
        preserve_reviewed: bool = True,
    ) -> tuple[dict[str, Any], int, bool]:
        """Atomically apply a complete eight-group proposal to one work."""

        self._ensure_writable()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT data FROM works WHERE id = ?", (work_id,)
                ).fetchone()
                if not row:
                    raise NotFoundError(f"work {work_id!r} was not found")
                work = _decode(row["data"])
                prior_by_group = {
                    item.get("group"): item for item in work.get("annotations", [])
                }
                proposal_by_group = {item.get("group"): deepcopy(item) for item in annotations}
                merged: list[dict[str, Any]] = []
                changes: list[tuple[dict[str, Any] | None, dict[str, Any]]] = []
                for group in proposal_by_group:
                    proposal = proposal_by_group[group]
                    before = prior_by_group.get(group)
                    if preserve_reviewed and before and before.get("reviewStatus") == "已审核":
                        merged.append(before)
                        continue
                    merged.append(proposal)
                    if before != proposal:
                        changes.append((before, proposal))
                # A structurally validated extractor always supplies all groups,
                # but preserve any future extension group rather than dropping it.
                merged.extend(
                    item for group, item in prior_by_group.items() if group not in proposal_by_group
                )

                evidence_by_id = {item.get("id"): item for item in work.get("evidence", [])}
                for item in evidence:
                    existing = evidence_by_id.get(item.get("id"))
                    if existing is not None and existing != item:
                        raise StoreError(f"evidence id {item.get('id')!r} already exists")
                    evidence_by_id[item.get("id")] = deepcopy(item)
                candidate_work = dict(work, annotations=merged, evidence=list(evidence_by_id.values()))
                for annotation in merged:
                    # Provider proposals are pending, but still require grounding
                    # for every non-unknown value.
                    validate_annotation(candidate_work, annotation, accepted_only=False)

                if not changes and candidate_work["evidence"] == work.get("evidence", []):
                    revision = self._revision(connection)
                    connection.execute("COMMIT")
                    return work, revision, False
                revision = self._next_revision(connection)
                for annotation in merged:
                    if annotation.get("reviewStatus") != "已审核" or annotation.get("revision") is None:
                        annotation["revision"] = revision
                candidate_work["revision"] = revision
                candidate_work["updatedAt"] = utc_now()
                for before, after in changes:
                    after["revision"] = revision
                    self._write_history(
                        connection,
                        annotation_id=after.get("id"),
                        revision=revision,
                        before=before,
                        after=after,
                        reason=reason,
                    )
                connection.execute(
                    "UPDATE works SET data = ? WHERE id = ?",
                    (_encode(candidate_work), work_id),
                )
                connection.execute("COMMIT")
                return candidate_work, revision, True
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def history(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM history ORDER BY revision DESC, created_at DESC"
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "annotationId": row["annotation_id"],
                    "revision": row["revision"],
                    "before": _decode(row["before_data"]) if row["before_data"] else None,
                    "after": _decode(row["after_data"]) if row["after_data"] else None,
                    "reason": row["reason"],
                    "createdAt": row["created_at"],
                }
                for row in rows
            ]

    def start_run(
        self,
        *,
        idempotency_key: str,
        fingerprint: str,
        mode: str,
        model: str,
        work_ids: list[str],
    ) -> tuple[dict[str, Any], bool]:
        self._ensure_writable()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT fingerprint, data FROM runs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    if existing["fingerprint"] != fingerprint:
                        raise IdempotencyConflict(
                            "idempotencyKey was already used for different content or configuration"
                        )
                    run = _decode(existing["data"])
                    run["cacheHit"] = run.get("status") == "completed"
                    connection.execute("COMMIT")
                    return run, True
                run = {
                    "id": f"run-{uuid4().hex}",
                    "status": "running",
                    "mode": mode,
                    "model": model,
                    "cacheHit": False,
                    "createdAt": utc_now(),
                    "durationMs": 0,
                    "steps": [],
                    "errors": [],
                    "workIds": list(work_ids),
                }
                connection.execute(
                    "INSERT INTO runs(id, idempotency_key, fingerprint, data) VALUES (?, ?, ?, ?)",
                    (run["id"], idempotency_key, fingerprint, _encode(run)),
                )
                connection.execute("COMMIT")
                return run, False
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def save_run(self, run: dict[str, Any]) -> None:
        self._ensure_writable()
        with self._lock, self._connect() as connection:
            result = connection.execute(
                "UPDATE runs SET data = ? WHERE id = ?", (_encode(run), run["id"])
            )
            if result.rowcount == 0:
                raise NotFoundError(f"run {run['id']!r} was not found")

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            return _decode(row["data"]) if row else None

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            return [
                _decode(row["data"])
                for row in connection.execute("SELECT data FROM runs ORDER BY rowid DESC")
            ]

    def mark_unfinished_interrupted(self) -> int:
        self._ensure_writable()
        changed = 0
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute("SELECT id, data FROM runs").fetchall()
                for row in rows:
                    run = _decode(row["data"])
                    if run.get("status") not in {"running", "queued"}:
                        continue
                    run["status"] = "interrupted"
                    run.setdefault("errors", []).append(
                        {
                            "code": "interrupted",
                            "message": "run was interrupted by a service restart",
                        }
                    )
                    connection.execute(
                        "UPDATE runs SET data = ? WHERE id = ?",
                        (_encode(run), row["id"]),
                    )
                    changed += 1
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return changed

    def save_report(self, report: dict[str, Any]) -> None:
        self._ensure_writable()
        persisted = deepcopy(report)
        persisted["stale"] = int(persisted.get("revision", -1)) != self.revision()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO reports(id, data) VALUES (?, ?)",
                (persisted["id"], _encode(persisted)),
            )

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM reports WHERE id = ?", (report_id,)
            ).fetchone()
            if not row:
                return None
            report = _decode(row["data"])
            report["stale"] = int(report.get("revision", -1)) != self._revision(connection)
            return report

    def list_reports(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            revision = self._revision(connection)
            reports = [
                _decode(row["data"])
                for row in connection.execute("SELECT data FROM reports ORDER BY rowid DESC")
            ]
            for report in reports:
                report["stale"] = int(report.get("revision", -1)) != revision
            return reports

    def state(self) -> dict[str, Any]:
        # Individual queries are protected by the process lock. SQLite remains
        # the source of truth across processes; the final revision lets clients
        # detect a concurrent state refresh.
        with self._lock:
            works = self.list_works()
            revision = self.revision()
            return {
                "works": works,
                "revision": revision,
                "runs": self.list_runs(),
                "reports": self.list_reports(),
                "history": self.history(),
                "provider": ProviderConfig.from_env().public(),
                "mode": self.mode,
            }
