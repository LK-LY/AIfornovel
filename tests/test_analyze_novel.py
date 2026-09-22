from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any

import pytest

from tools.analyze_novel import (
    AnalysisError,
    CODEX_SYNTHESIS_SCHEMA,
    CodexAdapter,
    MAP_SCHEMA,
    MAP_INSTRUCTIONS,
    ModelCall,
    PROMPT_VERSION,
    REDUCE_INSTRUCTIONS,
    SYNTHESIS_SCHEMA,
    ValidationError,
    load_source,
    parse_args,
    run_analysis,
    validate_synthesis,
)


def source_text(*, changed: bool = False) -> str:
    suffix = "（修订）" if changed else ""
    return (
        "《测试作品》\n"
        "作者：测试者\n"
        f"文案：她要重新选择自己的生活。{suffix}\n"
        "第一章 开始\n"
        "事件一：她拒绝把工作交给别人。\n"
        "事件二：她第一次说出自己的计划。\n"
        "事件三：两人曾在年少时表白与拒绝。\n"
        "事件四：多年后他们才开始重新认识。\n"
        "事件五：她也照顾家人与朋友的需要。\n"
        "事件六：🌱她最终完成了自己的选择。\n"
        "正文完\n"
        "第86章 番外\n"
        "番外事件一：后来生活仍然继续。\n"
        "第87章 哥哥\n"
        "番外事件二：家人的故事得到补充。\n"
        "番外完\n"
    )


def _payload(prompt: str, tag: str) -> dict[str, Any]:
    opening = f"<{tag}>\n"
    closing = f"\n</{tag}>"
    start = prompt.rindex(opening) + len(opening)
    end = prompt.index(closing, start)
    return json.loads(prompt[start:end])


class FakeAdapter:
    cli_version = "fake-codex 1.0"
    configured_model = "fake-configured-model"

    def __init__(self, *, invalid_map_calls: int = 0, bad_reduce_calls: int = 0) -> None:
        self.invalid_map_calls = invalid_map_calls
        self.bad_reduce_calls = bad_reduce_calls
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def complete(
        self,
        *,
        prompt: str,
        schema_path: Path,
        output_path: Path,
        stage: str,
        timeout_seconds: int,
    ) -> ModelCall:
        del schema_path, output_path, timeout_seconds
        with self._lock:
            self.calls.append(stage)
            call_number = len(self.calls)
            invalid_map = stage.startswith("map") and self.invalid_map_calls > 0
            if invalid_map:
                self.invalid_map_calls -= 1
            bad_reduce = stage.startswith("reduce") and self.bad_reduce_calls > 0
            if bad_reduce:
                self.bad_reduce_calls -= 1
        if stage.startswith("map"):
            payload = _payload(prompt, "UNTRUSTED_SOURCE_DATA")
            paragraphs = payload["paragraphs"]
            events = []
            for index, paragraph in enumerate(paragraphs[:5]):
                quote = "不存在于原文的引用" if invalid_map and index == 0 else paragraph["text"][:80]
                events.append(
                    {
                        "claim": f"文本事件 {index + 1}",
                        "interpretation": f"模型解读 {index + 1}",
                        "paragraph_id": paragraph["paragraph_id"],
                        "quote": quote,
                        "category": [
                            "metadata_promise",
                            "opening_hook",
                            "relationship",
                            "agency",
                            "counterevidence",
                        ][index],
                    }
                )
            return ModelCall(
                data={"summary": "本块模型摘要", "key_events": events},
                thread_id=f"thread-{call_number}",
                usage={"input_tokens": 10, "output_tokens": 5},
                model="fake-event-model",
                duration_ms=3,
            )
        payload = _payload(prompt, "UNTRUSTED_VALIDATED_MAPS")
        evidence_ids = [item["id"] for item in payload["evidence"]]
        if bad_reduce:
            evidence_ids = ["ev_00000000000000000000", *evidence_ids]
        section_ids = evidence_ids[:2]
        sections = [
            {
                "heading": heading,
                "paragraphs": ["模型综合结论。", "反例或替代解释：仍需人工复核语境。"],
                "evidence_ids": section_ids,
            }
            for heading in ["承诺", "开篇", "关系", "主体性", "结局", "策略"]
        ]
        return ModelCall(
            data={
                "title": "测试作品内容研究",
                "executive_summary": ["摘要一", "摘要二", "摘要三"],
                "sections": sections,
                "recommendations": ["待验证建议一", "待验证建议二", "待验证建议三"],
                "hypotheses": ["可证伪假设一", "可证伪假设二"],
                "limitations": [
                    "这是模型解读，不是人工 gold label。",
                    "单本作品不可直接外推到品类。",
                    "没有真实平台经营指标。",
                ],
            },
            thread_id=f"thread-{call_number}",
            usage={"input_tokens": 20, "output_tokens": 10},
            model="fake-event-model",
            duration_ms=4,
        )


class ExplodingAdapter(FakeAdapter):
    def complete(self, **kwargs: Any) -> ModelCall:
        raise AssertionError("prepare-only must not call the model")


def write_source(tmp_path: Path, *, changed: bool = False) -> Path:
    path = tmp_path / "authorized.txt"
    path.write_text(source_text(changed=changed), encoding="utf-8")
    return path


def test_prepare_only_writes_schemas_and_never_calls_adapter(tmp_path: Path) -> None:
    source = write_source(tmp_path)
    output = tmp_path / "prepared"
    result = run_analysis(source, output, prepare_only=True, adapter=ExplodingAdapter())

    assert result["status"] == "prepared"
    assert result["chunking"]["gap_free"] is True
    assert result["source"]["input_filename"] == source.name
    assert result["source"]["codepoints"] == len(source_text())
    assert (output / "schemas" / "map.schema.json").is_file()
    assert (output / "schemas" / "synthesis.schema.json").is_file()
    assert (output / "schemas" / "synthesis.codex.schema.json").is_file()
    assert not (output / "analysis.json").exists()


def test_model_use_requires_explicit_authorization(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="--allow-model"):
        run_analysis(write_source(tmp_path), tmp_path / "out", adapter=FakeAdapter())


def test_mock_map_reduce_produces_exact_unicode_evidence(tmp_path: Path) -> None:
    source = write_source(tmp_path)
    output = tmp_path / "out"
    adapter = FakeAdapter()
    result = run_analysis(source, output, allow_model=True, adapter=adapter)
    normalized = source_text()

    assert result["run"]["status"] == "completed"
    assert result["run"]["mode"] == "codex-live-map-reduce"
    assert result["run"]["model"] == "fake-event-model"
    assert result["run"]["configured_model"] == "fake-configured-model"
    assert result["run"]["model_call_count"] == 2
    assert result["source"]["title"] == "测试作品"
    assert result["evidence"]
    assert all(normalized[item["start_char"] : item["end_char"]] == item["quote"] for item in result["evidence"])
    assert all(item["id"].startswith("ev_") and len(item["id"]) == 23 for item in result["evidence"])
    assert (output / "analysis.json").is_file()


def test_map_quote_failure_gets_exactly_one_repair(tmp_path: Path) -> None:
    adapter = FakeAdapter(invalid_map_calls=1)
    result = run_analysis(
        write_source(tmp_path), tmp_path / "out", allow_model=True, adapter=adapter
    )

    assert adapter.calls[:2] == ["map-chunk_000001", "map-repair-chunk_000001"]
    assert sum(item["stage"] == "map_repair" for item in result["run"]["trace"]) == 1


def test_second_invalid_map_fails_without_fixture_fallback(tmp_path: Path) -> None:
    output = tmp_path / "out"
    adapter = FakeAdapter(invalid_map_calls=2)
    with pytest.raises(ValidationError, match="after one repair"):
        run_analysis(write_source(tmp_path), output, allow_model=True, adapter=adapter)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert not (output / "analysis.json").exists()
    assert len(adapter.calls) == 2


def test_resume_reuses_only_valid_maps_and_keeps_original_receipts(tmp_path: Path) -> None:
    source = write_source(tmp_path)
    output = tmp_path / "out"
    first = FakeAdapter()
    run_analysis(source, output, allow_model=True, adapter=first)

    second = FakeAdapter()
    result = run_analysis(source, output, allow_model=True, resume=True, adapter=second)

    assert second.calls == ["reduce"]
    assert result["run"]["cached_chunk_count"] == 1
    assert result["run"]["usage"] == {"input_tokens": 20, "output_tokens": 10}
    cache_trace = next(item for item in result["run"]["trace"] if item["cache_hit"])
    assert cache_trace["cached_call_receipts"][0]["thread_id"] == "thread-1"


def test_source_change_invalidates_resume_fingerprint(tmp_path: Path) -> None:
    source = write_source(tmp_path)
    output = tmp_path / "out"
    run_analysis(source, output, allow_model=True, adapter=FakeAdapter())
    source.write_text(source_text(changed=True), encoding="utf-8")
    second = FakeAdapter()

    result = run_analysis(source, output, allow_model=True, resume=True, adapter=second)

    assert second.calls[0].startswith("map-")
    assert result["run"]["cached_chunk_count"] == 0


def test_extra_classification_starts_at_embedded_marker_and_is_inherited(tmp_path: Path) -> None:
    bundle = load_source(
        write_source(tmp_path), title=None, chunk_codepoints=24_000, max_chunks=64
    )
    by_label = {bundle.chapter_labels[item.id]: bundle.chapter_kinds[item.id] for item in bundle.headings}

    assert by_label["第86章 番外"] == "extra"
    assert by_label["第87章 哥哥"] == "extra"
    assert by_label["第一章 开始"] == "main_text"


def test_max_chunk_guard_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="above --max-chunks"):
        run_analysis(
            write_source(tmp_path),
            tmp_path / "out",
            prepare_only=True,
            chunk_codepoints=20,
            max_chunks=1,
        )


def test_codex_command_uses_https_read_only_no_tools_and_stdin(tmp_path: Path) -> None:
    adapter = CodexAdapter(executable="missing-codex-for-command-test")
    command = adapter.build_command(tmp_path / "schema.json", tmp_path / "out.json")
    joined = " ".join(command)

    assert command[-1] == "-"
    assert "--ephemeral" in command
    assert "--sandbox read-only" in joined
    assert "supports_websockets=false" in joined
    assert "features.shell_tool=false" in command
    assert 'web_search="disabled"' in command
    assert "--ignore-user-config" not in command


def test_synthesis_rejects_unknown_evidence_ids() -> None:
    candidate = {
        "title": "报告",
        "executive_summary": ["一", "二", "三"],
        "sections": [
            {
                "heading": str(index),
                "paragraphs": ["结论", "反例或替代解释：待核验"],
                "evidence_ids": ["ev_00000000000000000000", "ev_11111111111111111111"],
            }
            for index in range(6)
        ],
        "recommendations": ["一", "二", "三"],
        "hypotheses": ["一", "二"],
        "limitations": ["不是人工 gold label", "单本不可外推", "无指标"],
    }
    with pytest.raises(ValidationError, match="unknown evidence"):
        validate_synthesis(candidate, [])


def test_map_schema_is_closed_and_bounded() -> None:
    assert MAP_SCHEMA["additionalProperties"] is False
    events = MAP_SCHEMA["properties"]["key_events"]
    assert (events["minItems"], events["maxItems"]) == (5, 8)
    assert events["items"]["properties"]["quote"]["maxLength"] == 100


def test_codex_transport_schema_defers_unsupported_uniqueness_to_python() -> None:
    evidence_ids = CODEX_SYNTHESIS_SCHEMA["properties"]["sections"]["items"]["properties"]["evidence_ids"]
    assert "uniqueItems" not in evidence_ids
    logical_ids = SYNTHESIS_SCHEMA["properties"]["sections"]["items"]["properties"]["evidence_ids"]
    assert logical_ids["uniqueItems"] is True


def test_generic_prompt_never_forces_a_male_lead_or_cp() -> None:
    assert PROMPT_VERSION == "herlens-fullbook-map-reduce-1.1"
    assert "核心关系可能是亲情、\n友情、同事、恋爱或无 CP" in MAP_INSTRUCTIONS
    assert "不得强填男主、CP 或恋爱进展" in MAP_INSTRUCTIONS
    assert "若材料确实出现\n年少单向拒绝" in MAP_INSTRUCTIONS
    assert "不存在则明确不适用，绝不强填男主或 CP" in REDUCE_INSTRUCTIONS
    assert "关系是复合发展的" not in MAP_INSTRUCTIONS


def test_resume_keeps_bounded_sanitized_failure_history(tmp_path: Path) -> None:
    source = write_source(tmp_path)
    output = tmp_path / "out"
    with pytest.raises(ValidationError):
        run_analysis(
            source,
            output,
            allow_model=True,
            adapter=FakeAdapter(invalid_map_calls=2),
        )
    failed = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert failed["attempt_history"][-1]["error"] == {
        "code": "STRUCTURED_OUTPUT_INVALID",
        "stage": "map",
        "message": "Structured model output failed deterministic validation.",
    }

    run_analysis(source, output, allow_model=True, resume=True, adapter=FakeAdapter())
    recovered = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert [item["status"] for item in recovered["attempt_history"]] == ["failed", "completed"]
    serialized = json.dumps(recovered["attempt_history"], ensure_ascii=False)
    assert "不存在于原文的引用" not in serialized
    assert len(recovered["attempt_history"]) <= 20


def test_cli_refuses_output_outside_private_reports() -> None:
    with pytest.raises(SystemExit):
        parse_args(["authorized.txt", "--output", "public/not-private", "--prepare-only"])
