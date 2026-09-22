"""Build the public demo exclusively from the checked-in synthetic fixture.

No arguments select another dataset or destination, and no .env/provider config
or existing local database is read. Timings and report identity come from the
actual run; stable fixture content and queries are reproducible across builds.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.herlens.analytics import compare  # noqa: E402
from backend.herlens.exporting import export_report  # noqa: E402
from backend.herlens.research import research  # noqa: E402
from backend.herlens.schemas import GROUPS, SCHEMA_VERSION  # noqa: E402
from backend.herlens.store import Store  # noqa: E402


def build_snapshot() -> dict:
    fixture_path = PROJECT_ROOT / "fixtures" / "demo.json"
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Public demo requires a nonempty synthetic Work array")
    if any(not isinstance(work, dict) or work.get("isSynthetic") is not True for work in raw):
        raise ValueError("Public snapshot refused: every fixture work must explicitly be synthetic")
    fixture_ids = [work.get("id") for work in raw]
    if len(set(fixture_ids)) != len(fixture_ids):
        raise ValueError("Public snapshot refused: duplicate fixture work ids")

    # Explicit fresh path means HERLENS_DATA_DIR and the private SQLite file are
    # irrelevant. list_works/revision avoid Store.state's provider configuration.
    with TemporaryDirectory(prefix="herlens-public-snapshot-") as temporary:
        store = Store(Path(temporary) / "demo.sqlite3", read_only=True)
        works, revision = store.list_works(), store.revision()
    if [work["id"] for work in works] != fixture_ids or any(work.get("isSynthetic") is not True for work in works):
        raise ValueError("Public snapshot refused: normalized works differ from the synthetic fixture cohort")
    comparisons = {group: compare(works, revision, group, reviewed_only=True) for group in GROUPS}
    report = research(works, revision, "标题与导语的情绪承诺，是否在开篇与结尾获得支持？", group="包装钩子", reviewed_only=True)
    return {"schemaVersion": SCHEMA_VERSION, "mode": "readonly", "source": "fixtures/demo.json",
            "generatedAt": datetime.now(timezone.utc).isoformat(), "works": works,
            "comparison": comparisons["包装钩子"], "comparisons": comparisons, "report": report}


def main() -> int:
    if len(sys.argv) != 1:
        raise ValueError("build_snapshot.py takes no dataset or output arguments; public source is fixed")
    result = build_snapshot()
    output = PROJECT_ROOT / "public" / "demo-snapshot.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for format in ("md", "html", "xlsx"):
        content, _, _ = export_report(result["report"], result["works"], format)
        (output.parent / f"demo-memo.{format}").write_bytes(content)
    # Counts only: no story text, evidence quotes, raw benchmark, or credentials.
    print(f"Built public/demo-snapshot.json and demo-memo.md/html/xlsx: {len(result['works'])} synthetic works, {len(result['comparisons'])} SQL comparisons, {len(result['report']['trace'])} executed research actions.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(f"Public snapshot generation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
