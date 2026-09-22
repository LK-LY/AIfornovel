from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.benchmark_text import (
    astral_codepoint_check,
    benchmark,
    build_chunks,
    decode_utf8,
    detect_headings,
    detect_paragraphs,
    is_chinese_chapter_heading,
    normalize_text,
    repeated_quote_check,
)


def test_utf8_is_strict_and_bom_is_removed() -> None:
    text, has_bom = decode_utf8(b"\xef\xbb\xbf\xe7\xac\xac\xe4\xb8\x80\xe7\xab\xa0")
    assert text == "第一章"
    assert has_bom is True
    with pytest.raises(ValueError, match="not valid UTF-8"):
        decode_utf8(b"\xff\xfe\x00")


def test_normalization_uses_lf_and_nfc() -> None:
    assert normalize_text("e\u0301\r\n甲\r乙") == "é\n甲\n乙"


def test_natural_dialogue_is_not_a_chapter_heading():
    assert not is_chinese_chapter_heading("话一出来，她便后悔了。")
    assert not is_chinese_chapter_heading("话一脱口，她又停了下来。")
    assert is_chinese_chapter_heading("章一 开始")
    assert is_chinese_chapter_heading("第一章开始")


@pytest.mark.parametrize(
    "line",
    ["第一章 相遇", "第12回：旧事", "番外 2", "尾声", "【终章】"],
)
def test_detects_supported_chinese_headings(line: str) -> None:
    assert is_chinese_chapter_heading(line)


@pytest.mark.parametrize("line", ["这是普通段落。", "第一次相遇", "", "A" * 121])
def test_rejects_non_headings(line: str) -> None:
    assert not is_chinese_chapter_heading(line)


def test_chunks_are_bounded_gap_free_and_have_structural_ids() -> None:
    text = normalize_text(
        "第一章 起点\n"
        + "甲" * 37
        + "\n\n"
        + "乙" * 41
        + "\n\n第二章 转折\n"
        + "丙" * 47
    )
    headings = detect_headings(text)
    paragraphs = detect_paragraphs(text, headings)
    chunks = build_chunks(text, headings, paragraphs, max_codepoints=32)

    assert len(headings) == 2
    assert all(chunk.codepoints <= 32 for chunk in chunks)
    assert chunks[0].start_char == 0
    assert chunks[-1].end_char == len(text)
    assert all(left.end_char == right.start_char for left, right in zip(chunks, chunks[1:]))
    assert all(chunk.id.startswith("chunk_") for chunk in chunks)
    assert all(chunk.first_chapter_id.startswith("chapter_") for chunk in chunks)
    assert "".join(text[chunk.start_char : chunk.end_char] for chunk in chunks) == text


def test_each_nonempty_single_newline_is_a_paragraph_and_heading_is_excluded() -> None:
    text = "第一章 起点\n第一行叙事\n第二行叙事\n\n第三行叙事\n"
    headings = detect_headings(text)
    paragraphs = detect_paragraphs(text, headings)

    assert len(headings) == 1
    assert len(paragraphs) == 3
    assert [text[item.start_char : item.end_char] for item in paragraphs] == [
        "第一行叙事",
        "第二行叙事",
        "第三行叙事",
    ]
    assert all(item.chapter_id == "chapter_00001" for item in paragraphs)


def test_exact_offsets_disambiguate_repeated_quote() -> None:
    text = "第一章\n重复语句甲乙丙丁戊己。\n\n第二章\n重复语句甲乙丙丁戊己。"
    result = repeated_quote_check(text, width=8)
    assert result["available"] is True
    assert result["positions_distinct"] is True
    assert result["both_exact"] is True
    assert result["first_start_char"] != result["second_start_char"]


def test_astral_offsets_are_unicode_codepoints() -> None:
    result = astral_codepoint_check()
    assert result == {
        "exact": True,
        "start_char": 1,
        "end_char": 3,
        "quote_codepoints": 2,
        "source_codepoints": 5,
    }


def test_benchmark_output_contains_no_source_text_or_path(tmp_path: Path) -> None:
    secret_marker = "PRIVATE_SOURCE_MARKER_9274"
    source = tmp_path / "private-title.txt"
    source.write_text(
        f"第一章\n{secret_marker}\n\n内容内容内容内容\n\n"
        "第二章\n内容内容内容内容\n",
        encoding="utf-8",
    )
    result = benchmark(source, label="synthetic-test", max_codepoints=24)
    serialized = json.dumps(result, ensure_ascii=False)

    assert secret_marker not in serialized
    assert str(source) not in serialized
    assert source.name not in serialized
    assert result["input"]["valid_utf8"] is True
    assert result["structure"]["oversized_chunk_count"] == 0
    assert result["structure"]["gap_free_exact_coverage"] is True
    assert result["structure"]["paragraph_rule"] == "each_nonempty_normalized_line_excluding_detected_chapter_headings"
    assert result["evidence_checks"]["offset_round_trip_smoke"]["all_exact"] is True
    assert result["evidence_checks"]["offset_round_trip_smoke"]["kind"] == "mechanical_smoke_not_semantic_accuracy"
    assert result["evidence_checks"]["astral_unicode"]["exact"] is True
    assert result["privacy"]["text_excerpt_emitted"] is False
