from copy import deepcopy
from hashlib import sha256

import pytest

from tools.build_novel_report import build_artifact, evidence_distribution, validate_analysis, verify_original_source


def example():
    return {
        "run": {"status": "completed", "mode": "codex-live-map-reduce", "chunk_count": 2,
                "completed_at": "2026-09-22T00:00:00Z"},
        "source": {"title": "测试作品", "codepoints": 100, "raw_sha256": "abc", "normalized_sha256": "def"},
        "evidence": [
            {"id": "a", "start_char": 0, "end_char": 2, "quote": "甲乙", "paragraph_id": "p1",
             "claim": "判断甲", "interpretation": "需复核", "chapter_label": "第一章", "section_kind": "main_text"},
            {"id": "b", "start_char": 99, "end_char": 100, "quote": "终", "paragraph_id": "p2",
             "claim": "判断乙", "interpretation": "需复核", "chapter_label": "终章", "section_kind": "main_text"},
        ],
        "maps": [{}, {}],
        "synthesis": {"title": "研究测试", "executive_summary": ["结论一", "结论二", "结论三"],
                      "sections": [{"heading": "正文发现", "paragraphs": ["证据解读", "替代解释"], "evidence_ids": ["a", "b"]}],
                      "recommendations": ["补充比较样本"], "hypotheses": ["是否存在另一种解释？"], "limitations": ["单作品"]},
    }


def test_report_preserves_all_findings_citations_and_role_order():
    data = example()
    artifact, notes = build_artifact(data)
    blocks = artifact["manifest"]["blocks"]
    assert blocks[0]["body"] == "# HerLens · 《测试作品》内容研究报告"
    assert blocks[1]["body"].startswith("## Executive Summary")
    assert "甲乙" in blocks[3]["body"] and "终" in blocks[3]["body"]
    assert notes["cited_evidence_count"] == 2
    assert artifact["snapshot"]["status"] == "ready"
    assert "model accuracy" not in str(artifact)
    assert "引文的支持范围" in blocks[2]["body"]
    assert "不是盲测" in blocks[2]["body"]
    assert "关联事件概括（模型）" in blocks[3]["body"]


@pytest.mark.parametrize("state", ["prepared", "failed", "running", "fixture"])
def test_incomplete_or_fixture_run_cannot_become_live_report(state):
    data = example()
    data["run"]["status"] = state
    with pytest.raises(ValueError, match="completed live"):
        validate_analysis(data)


def test_invalid_reference_and_spans_fail_closed():
    data = example()
    data["synthesis"]["sections"][0]["evidence_ids"] = ["a", "missing"]
    with pytest.raises(ValueError, match="valid evidence"):
        validate_analysis(data)
    data = example()
    data["evidence"][0]["end_char"] = 3
    with pytest.raises(ValueError, match="codepoint"):
        validate_analysis(data)


def test_distribution_preserves_empty_bins_and_count_not_semantics():
    data = example()
    rows = evidence_distribution(data["evidence"], data["source"]["codepoints"])
    assert len(rows) == 10
    assert rows[0]["count"] == 1 and rows[-1]["count"] == 1
    assert sum(row["count"] for row in rows) == 2
    assert rows[5]["count"] == 0
    assert "非情节密度" in rows[0]["definition"]


def test_no_raw_html_is_introduced_by_model_prose():
    data = deepcopy(example())
    data["synthesis"]["executive_summary"][0] = "<script>alert(1)</script>"
    artifact, _ = build_artifact(data)
    assert "<script>" not in artifact["manifest"]["blocks"][1]["body"]


@pytest.mark.parametrize("field,value", [("chunk_count", 3), ("completed_chunks", 1)])
def test_partial_or_mismatched_maps_cannot_claim_full_coverage(field, value):
    data = example()
    data["run"][field] = value
    with pytest.raises(ValueError):
        validate_analysis(data)


def test_title_and_link_like_source_text_are_literal():
    data = example()
    data["source"]["title"] = "<script>[click](javascript:alert)</script>"
    artifact, _ = build_artifact(data)
    assert "<script>" not in artifact["manifest"]["title"]
    assert "\\[click\\]" in artifact["manifest"]["title"]


def test_evidence_identifier_cannot_inject_markup():
    data = example()
    data["evidence"][0]["id"] = "<script>"
    with pytest.raises(ValueError, match="identifier"):
        validate_analysis(data)


def test_report_revalidates_original_hash_and_exact_quotes(tmp_path):
    path = tmp_path / "original.txt"
    text = "甲乙" + " " * 97 + "终"
    path.write_bytes(text.encode("utf-8"))
    data = example()
    data["source"]["raw_sha256"] = sha256(path.read_bytes()).hexdigest()
    data["source"]["normalized_sha256"] = sha256(text.encode("utf-8")).hexdigest()
    verify_original_source(data, path)
    data["evidence"][0]["quote"] = "丙丁"
    with pytest.raises(ValueError, match="no longer matches"):
        verify_original_source(data, path)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        verify_original_source(data, path)
