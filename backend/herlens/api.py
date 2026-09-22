"""FastAPI surface for the local HerLens strategy service."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import ipaddress
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .analytics import compare
from .exporting import export_report
from .extraction import (
    EvidenceValidationError,
    ExtractionError,
    ProviderConfig,
    ProviderRequest,
    extract_live,
    load_seed_works,
    prepare_import_work,
)
from .research import research
from .schemas import (
    AnnotationPatch,
    ComparisonRequest,
    GROUPS,
    ImportItem,
    ImportRequest,
    ResearchRunRequest,
    RunRequest,
    SCHEMA_VERSION,
)
from .store import (
    IdempotencyConflict,
    NotFoundError,
    ReadOnlyError,
    RevisionConflict,
    Store,
    StoreError,
)


LOOPBACK_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
)


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validation_message(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors(include_input=False)[:10]
    )


def _fingerprint(
    work_ids: list[str], works: dict[str, dict[str, Any]], mode: str, provider: ProviderConfig
) -> str:
    content = [
        {
            "id": work_id,
            "versionId": works.get(work_id, {}).get("versionId"),
            "contentHash": works.get(work_id, {}).get("contentHash"),
            "missing": work_id not in works,
        }
        for work_id in sorted(work_ids)
    ]
    config = {
        "mode": mode,
        "model": provider.model if mode == "live" else "precomputed-fixture",
        "baseUrl": provider.base_url if mode == "live" else "local-fixture",
        "extractor": "structured-v1",
        "works": content,
    }
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _public_run_error(exc: Exception) -> dict[str, str]:
    if isinstance(
        exc,
        (
            ExtractionError,
            EvidenceValidationError,
            NotFoundError,
            StoreError,
            ValueError,
        ),
    ):
        message = str(exc)[:1_000]
    else:
        message = "internal processing error"
    return {"code": type(exc).__name__, "message": message}


def _selected_works(store: Store, work_ids: list[str]) -> tuple[list[dict[str, Any]], int]:
    state = store.state()
    by_id = {work["id"]: work for work in state["works"]}
    missing = [work_id for work_id in work_ids if work_id not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail={"message": "work not found", "workIds": missing})
    return [by_id[work_id] for work_id in work_ids], state["revision"]


def create_app(
    *,
    data_path: str | Path | None = None,
    store: Store | None = None,
    read_only: bool | None = None,
    provider_request: ProviderRequest | None = None,
    testing: bool = False,
) -> FastAPI:
    strategy_store = store or Store(data_path, read_only=read_only)
    app = FastAPI(title="HerLens local strategy API", version="0.2.0")
    app.state.strategy_store = strategy_store
    app.state.provider_request = provider_request
    app.state.testing = testing

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOOPBACK_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @app.middleware("http")
    async def local_write_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            host = request.client.host if request.client else None
            if not app.state.testing and not _is_loopback(host):
                return Response(
                    content=json.dumps({"detail": "writes are restricted to loopback clients"}),
                    status_code=403,
                    media_type="application/json",
                )
            origin = request.headers.get("origin")
            if origin and origin not in LOOPBACK_ORIGINS:
                return Response(
                    content=json.dumps({"detail": "write origin is not allowed"}),
                    status_code=403,
                    media_type="application/json",
                )
        return await call_next(request)

    def require_writable() -> None:
        if strategy_store.read_only:
            raise HTTPException(status_code=403, detail="HerLens is running in read-only mode")

    @app.get("/api/strategy/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "mode": strategy_store.mode,
            "schemaVersion": SCHEMA_VERSION,
        }

    @app.get("/api/strategy/state")
    def state() -> dict[str, Any]:
        return strategy_store.state()

    @app.post("/api/strategy/datasets/import")
    def import_datasets(payload: ImportRequest) -> dict[str, Any]:
        require_writable()
        results: list[dict[str, Any]] = []
        for row_number, raw in enumerate(payload.items, start=1):
            try:
                item = ImportItem.model_validate(raw)
                work = prepare_import_work(item)
                status, persisted, _revision = strategy_store.add_work(work)
                results.append(
                    {
                        "row": row_number,
                        "status": status,
                        "workId": persisted["id"],
                        "message": (
                            "imported with exact unreviewed evidence candidates"
                            if status == "imported"
                            else "exact content duplicate; existing work returned"
                        ),
                    }
                )
            except ValidationError as exc:
                results.append(
                    {
                        "row": row_number,
                        "status": "error",
                        "message": _validation_message(exc),
                    }
                )
            except (ValueError, StoreError) as exc:
                results.append(
                    {
                        "row": row_number,
                        "status": "error",
                        "message": str(exc)[:1_000],
                    }
                )
        return {"results": results, "revision": strategy_store.revision()}

    @app.post("/api/strategy/runs")
    def create_run(payload: RunRequest) -> dict[str, Any]:
        require_writable()
        provider = ProviderConfig.from_env()
        current = {work["id"]: work for work in strategy_store.list_works()}
        fingerprint = _fingerprint(payload.workIds, current, payload.mode, provider)
        model = provider.model if payload.mode == "live" else "precomputed-fixture"
        try:
            run, reused = strategy_store.start_run(
                idempotency_key=payload.idempotencyKey,
                fingerprint=fingerprint,
                mode=payload.mode,
                model=model,
                work_ids=payload.workIds,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        if reused:
            return run

        started = perf_counter()
        completed_count = 0
        seeds: dict[tuple[str, str, str], dict[str, Any]] = {}
        if payload.mode == "fixture":
            seeds = {
                (work["id"], work["versionId"], work["contentHash"]): work
                for work in load_seed_works()
            }
        for work_id in payload.workIds:
            step_started = perf_counter()
            tool_name = (
                "replay_precomputed_fixture"
                if payload.mode == "fixture"
                else "structured_chat_completion"
            )
            try:
                if work_id not in current:
                    raise NotFoundError(f"work {work_id!r} was not found")
                if payload.mode == "fixture":
                    work = current[work_id]
                    seed = seeds.get((work["id"], work["versionId"], work["contentHash"]))
                    if seed is None:
                        raise ExtractionError(
                            f"fixture mode refuses non-seed content for work {work_id}"
                        )
                    strategy_store.apply_extraction(
                        work_id,
                        deepcopy(seed["annotations"]),
                        deepcopy(seed["evidence"]),
                        reason="precomputed fixture replay",
                        # A fixture is a deterministic candidate source, not an
                        # authority allowed to undo a later human decision.
                        preserve_reviewed=True,
                    )
                    summary = (
                        f"{work_id}: precomputed synthetic demo fixture; "
                        "not a model or human-accuracy result"
                    )
                else:
                    if not provider.configured:
                        raise ExtractionError("live provider is not configured on the server")
                    work = strategy_store.get_work(work_id)
                    if work is None:
                        raise NotFoundError(f"work {work_id!r} was not found")
                    if not work.get("modelConsent"):
                        raise ExtractionError(f"work {work_id} does not grant modelConsent")
                    annotations, evidence, attempts = extract_live(
                        work,
                        config=provider,
                        request_json=app.state.provider_request,
                    )
                    strategy_store.apply_extraction(
                        work_id,
                        annotations,
                        evidence,
                        reason="live structured extraction proposal",
                        preserve_reviewed=True,
                    )
                    summary = f"{work_id}: validated structured proposal in {attempts} attempt(s)"
                run["steps"].append(
                    {
                        "tool": tool_name,
                        "status": "completed",
                        "summary": summary,
                        "durationMs": round((perf_counter() - step_started) * 1_000),
                    }
                )
                completed_count += 1
            except Exception as exc:  # isolate failures so later works still run
                error = _public_run_error(exc)
                error["workId"] = work_id
                run["errors"].append(error)
                run["steps"].append(
                    {
                        "tool": tool_name,
                        "status": "failed",
                        "summary": f"{work_id}: {error['message']}",
                        "durationMs": round((perf_counter() - step_started) * 1_000),
                    }
                )
        if completed_count == len(payload.workIds):
            run["status"] = "completed"
        elif completed_count:
            run["status"] = "partial_failed"
        else:
            run["status"] = "failed"
        run["durationMs"] = round((perf_counter() - started) * 1_000)
        strategy_store.save_run(run)
        return run

    @app.get("/api/strategy/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = strategy_store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.patch("/api/strategy/annotations/{annotation_id}")
    def patch_annotation(annotation_id: str, payload: AnnotationPatch) -> dict[str, Any]:
        require_writable()
        try:
            annotation, revision = strategy_store.patch_annotation(
                annotation_id,
                payload.model_dump(exclude={"expectedRevision"}),
                expected_revision=payload.expectedRevision,
            )
        except RevisionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "revision conflict",
                    "expectedRevision": exc.expected,
                    "currentRevision": exc.current,
                },
            ) from None
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except EvidenceValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return {"annotation": annotation, "revision": revision}

    @app.post("/api/strategy/comparisons")
    def create_comparison(payload: ComparisonRequest) -> dict[str, Any]:
        if payload.group not in GROUPS:
            raise HTTPException(status_code=422, detail="group is not configured")
        works, revision = _selected_works(strategy_store, payload.workIds)
        try:
            return compare(
                works, revision, group=payload.group, reviewed_only=payload.reviewedOnly
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.post("/api/strategy/research-runs")
    def create_research_run(payload: ResearchRunRequest) -> dict[str, Any]:
        require_writable()
        if payload.group not in GROUPS:
            raise HTTPException(status_code=422, detail="group is not configured")
        works, revision = _selected_works(strategy_store, payload.workIds)
        try:
            report = research(
                works,
                revision,
                payload.question,
                group=payload.group,
                reviewed_only=payload.reviewedOnly,
            )
            strategy_store.save_report(report)
            return strategy_store.get_report(report["id"]) or report
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/api/strategy/reports/{report_id}")
    def get_report(report_id: str) -> dict[str, Any]:
        report = strategy_store.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        return report

    @app.get("/api/strategy/reports/{report_id}/export")
    def export_saved_report(
        report_id: str,
        format: Literal["md", "html", "xlsx"] = Query(...),
    ) -> Response:
        report = strategy_store.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        if report.get("stale"):
            raise HTTPException(
                status_code=409,
                detail="report is stale after a data revision; run research again",
            )
        snapshot = report.get("comparison", {}).get("sourceSnapshot", [])
        ids = [item.get("workId") for item in snapshot if isinstance(item, dict)]
        works_by_id = {work["id"]: work for work in strategy_store.list_works()}
        works = [works_by_id[work_id] for work_id in ids if work_id in works_by_id]
        try:
            data, media_type, filename = export_report(report, works, format)
        except ValueError as exc:
            # Snapshot mismatch is equivalent to staleness, even if the global
            # revision was restored externally.
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return Response(
            content=data,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


app = create_app()
