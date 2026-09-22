"""Offline structural benchmark for an authorized local UTF-8 text.

The JSON result intentionally contains hashes, offsets, IDs, counts, timing,
and memory measurements only. It never serializes source text or excerpts.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
from statistics import median
import sys
import time
import tracemalloc
import unicodedata


HEADING_RE = re.compile(
    r"^(?:"
    r"第\s*[0-9０-９零〇一二三四五六七八九十百千万两]+\s*[章节回卷部篇话]"
    r"|[章节回卷部篇话]\s*[0-9０-９零〇一二三四五六七八九十百千万两]+(?=\s|[:：、.\-—]|$)"
    r"|序章|業子|终章|尾声|番外(?:\s*[0-9０-９零〇一二三四五六七八九十百千万两]+)?"
    r")"
    r"(?:\s*(?:[:：、.\-—]\s*)?.*)?$",
    re.IGNORECASE,
)
DECORATION_RE = re.compile(r"^[\s#>*_=~★☆◆◇●○【\[(（《〈「『]+|[\s#<*_=~★☆◆◇●○】\])）》〉」』]+$")
NON_CONTENT_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)


@dataclass(frozen=True)
class Heading:
    id: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class Paragraph:
    id: str
    chapter_id: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class Chunk:
    id: str
    start_char: int
    end_char: int
    codepoints: int
    first_chapter_id: str
    last_chapter_id: str
    first_paragraph_id: str | None
    last_paragraph_id: str | None


def decode_utf8(raw: bytes) -> tuple[str, bool]:
    """Decode UTF-8 strictly and remove an optional BOM."""

    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        return raw.decode("utf-8-sig"), has_bom
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"input is not valid UTF-8 at byte {exc.start}; convert it before benchmarking"
        ) from exc


def normalize_text(text: str) -> str:
    """Normalize line endings and canonical Unicode representation."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", normalized)


def normalize_heading(line: str) -> str:
    text = re.sub(r"\s+", " ", line.strip().replace("\u3000", " "))
    return DECORATION_RE.sub("", text).strip()


def is_chinese_chapter_heading(line: str) -> bool:
    candidate = normalize_heading(line)
    return bool(candidate and len(candidate) <= 120 and HEADING_RE.fullmatch(candidate))


def detect_headings(text: str) -> list[Heading]:
    headings: list[Heading] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\n")
        if is_chinese_chapter_heading(content):
            headings.append(
                Heading(
                    id=f"chapter_{len(headings) + 1:05d}",
                    start_char=offset,
                    end_char=offset + len(content),
                )
            )
        offset += len(line)
    return headings


def _chapter_id_at(offset: int, headings: list[Heading]) -> str:
    if not headings:
        return "chapter_00000"
    starts = [heading.start_char for heading in headings]
    index = bisect_right(starts, offset) - 1
    return headings[index].id if index >= 0 else "chapter_00000"


def detect_paragraphs(text: str, headings: list[Heading]) -> list[Paragraph]:
    """Return non-empty logical-line spans, excluding chapter headings.

    Many exported Chinese novels use a single newline, rather than a blank
    line, between narrative paragraphs. Treating each non-empty normalized
    line as a paragraph keeps the rule stable across those exports.
    """

    paragraphs: list[Paragraph] = []
    heading_spans = {(heading.start_char, heading.end_char) for heading in headings}
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\n")
        leading = len(content) - len(content.lstrip())
        trailing = len(content.rstrip())
        start = offset + leading
        end = offset + trailing
        offset += len(line)
        if start >= end or (start, end) in heading_spans:
            continue
        paragraphs.append(
            Paragraph(
                id=f"paragraph_{len(paragraphs) + 1:07d}",
                chapter_id=_chapter_id_at(start, headings),
                start_char=start,
                end_char=end,
            )
        )
    return paragraphs


def build_chunks(
    text: str,
    headings: list[Heading],
    paragraphs: list[Paragraph],
    max_codepoints: int,
) -> list[Chunk]:
    """Build gap-free, non-overlapping chunks, preferring structural boundaries."""

    if max_codepoints < 1:
        raise ValueError("max_codepoints must be positive")
    if not text:
        return []

    boundaries = {0, len(text)}
    boundaries.update(heading.start_char for heading in headings)
    boundaries.update(paragraph.end_char for paragraph in paragraphs)
    ordered = sorted(boundaries)
    chunks: list[Chunk] = []
    start = 0

    while start < len(text):
        hard_end = min(start + max_codepoints, len(text))
        boundary_index = bisect_right(ordered, hard_end) - 1
        preferred_end = ordered[boundary_index] if boundary_index >= 0 else hard_end
        end = preferred_end if preferred_end > start else hard_end

        intersecting = [
            paragraph
            for paragraph in paragraphs
            if paragraph.end_char > start and paragraph.start_char < end
        ]
        first_chapter = _chapter_id_at(start, headings)
        last_chapter = _chapter_id_at(max(start, end - 1), headings)
        chunks.append(
            Chunk(
                id=f"chunk_{len(chunks) + 1:06d}",
                start_char=start,
                end_char=end,
                codepoints=end - start,
                first_chapter_id=first_chapter,
                last_chapter_id=last_chapter,
                first_paragraph_id=intersecting[0].id if intersecting else None,
                last_paragraph_id=intersecting[-1].id if intersecting else None,
            )
        )
        start = end

    return chunks


def validate_evidence_span(
    text: str,
    paragraph: Paragraph,
    start_char: int,
    end_char: int,
    quote: str,
) -> bool:
    """Validate a document-absolute, paragraph-bounded evidence span."""

    if not (paragraph.start_char <= start_char < end_char <= paragraph.end_char):
        return False
    return text[start_char:end_char] == quote


def offset_round_trip_smoke(text: str, paragraphs: list[Paragraph], limit: int = 7) -> dict:
    """Exercise paragraph-relative to absolute offsets without emitting text.

    Samples are deterministically derived from the input, so this is a
    mechanical smoke test, not an independent annotation-accuracy measure.
    """

    eligible = [p for p in paragraphs if p.end_char - p.start_char >= 8]
    if not eligible:
        return {
            "kind": "mechanical_smoke_not_semantic_accuracy",
            "sample_count": 0,
            "exact_match_count": 0,
            "all_exact": True,
        }
    if len(eligible) <= limit:
        sample = eligible
    else:
        sample = [eligible[round(index * (len(eligible) - 1) / (limit - 1))] for index in range(limit)]

    exact = 0
    for paragraph in sample:
        paragraph_length = paragraph.end_char - paragraph.start_char
        relative_start = min(paragraph_length // 3, max(paragraph_length - 1, 0))
        relative_end = min(relative_start + 64, paragraph_length)
        absolute_start = paragraph.start_char + relative_start
        absolute_end = paragraph.start_char + relative_end
        quote = text[absolute_start:absolute_end]
        exact += int(
            validate_evidence_span(
                text,
                paragraph,
                absolute_start,
                absolute_end,
                quote,
            )
        )
    return {
        "kind": "mechanical_smoke_not_semantic_accuracy",
        "sample_count": len(sample),
        "exact_match_count": exact,
        "all_exact": exact == len(sample),
    }


def repeated_quote_check(text: str, width: int = 10) -> dict:
    """Find two exact occurrences and verify offsets disambiguate the same quote."""

    seen: dict[str, int] = {}
    upper = max(len(text) - width + 1, 0)
    # Natural-language duplicates usually appear quickly. Scanning every
    # code-point (rather than a stride) also exercises duplicates whose
    # occurrences are not aligned to the same modulus.
    for start in range(0, min(upper, 250_000)):
        quote = text[start : start + width]
        if "\n" in quote or NON_CONTENT_RE.fullmatch(quote):
            continue
        previous = seen.get(quote)
        if previous is not None and previous != start:
            return {
                "available": True,
                "codepoint_length": width,
                "first_start_char": previous,
                "second_start_char": start,
                "positions_distinct": previous != start,
                "both_exact": text[previous : previous + width] == quote
                and text[start : start + width] == quote,
            }
        seen[quote] = start
    return {
        "available": False,
        "codepoint_length": width,
        "positions_distinct": False,
        "both_exact": False,
    }


def astral_codepoint_check() -> dict:
    """Regression check that offsets use Unicode code points, not UTF-16 units."""

    source = "A\U0001f642B\U0001f642C"
    quote = "\U0001f642B"
    start = source.index(quote)
    end = start + len(quote)
    return {
        "exact": source[start:end] == quote,
        "start_char": start,
        "end_char": end,
        "quote_codepoints": len(quote),
        "source_codepoints": len(source),
    }


def _benchmark_once(input_path: Path, *, label: str, max_codepoints: int) -> dict:
    started = time.perf_counter()
    tracemalloc.start()
    raw = input_path.read_bytes()
    text, has_bom = decode_utf8(raw)
    normalized = normalize_text(text)
    headings = detect_headings(normalized)
    paragraphs = detect_paragraphs(normalized, headings)
    chunks = build_chunks(normalized, headings, paragraphs, max_codepoints)
    evidence = offset_round_trip_smoke(normalized, paragraphs)
    repeated = repeated_quote_check(normalized)
    astral = astral_codepoint_check()

    coverage_exact = (
        (not chunks and not normalized)
        or (
            bool(chunks)
            and chunks[0].start_char == 0
            and chunks[-1].end_char == len(normalized)
            and all(left.end_char == right.start_char for left, right in zip(chunks, chunks[1:]))
            and sum(chunk.codepoints for chunk in chunks) == len(normalized)
        )
    )
    manifest = [asdict(chunk) for chunk in chunks]
    manifest_bytes = json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "schema_version": "1.0",
        "benchmark": "offline_long_text_structure",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "label": label,
            "bytes": len(raw),
            "raw_sha256": sha256(raw).hexdigest(),
            "valid_utf8": True,
            "utf8_bom": has_bom,
        },
        "normalization": {
            "form": "NFC",
            "line_endings": "LF",
            "codepoints": len(normalized),
            "lines": normalized.count("\n") + (1 if normalized else 0),
            "normalized_sha256": sha256(normalized.encode("utf-8")).hexdigest(),
        },
        "structure": {
            "chapter_heading_count": len(headings),
            "paragraph_count": len(paragraphs),
            "paragraph_rule": "each_nonempty_normalized_line_excluding_detected_chapter_headings",
            "chunk_count": len(chunks),
            "configured_max_chunk_codepoints": max_codepoints,
            "largest_chunk_codepoints": max((chunk.codepoints for chunk in chunks), default=0),
            "oversized_chunk_count": sum(chunk.codepoints > max_codepoints for chunk in chunks),
            "gap_free_exact_coverage": coverage_exact,
            "chunk_manifest_sha256": sha256(manifest_bytes).hexdigest(),
            "chunks": manifest,
        },
        "evidence_checks": {
            "offset_round_trip_smoke": evidence,
            "repeated_quote": repeated,
            "astral_unicode": astral,
        },
        "runtime": {
            "repeat_count": 1,
            "elapsed_ms_runs": [round(elapsed_ms, 3)],
            "elapsed_ms_median": round(elapsed_ms, 3),
            "peak_traced_memory_bytes_runs": [peak_bytes],
            "peak_traced_memory_bytes_median": peak_bytes,
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "deterministic_structure_across_runs": True,
        },
        "privacy": {
            "offline_only": True,
            "model_called": False,
            "network_called": False,
            "source_path_emitted": False,
            "text_excerpt_emitted": False,
        },
        "interpretation": {
            "supports": "local UTF-8 normalization, structural heading detection, bounded code-point chunking, and exact-offset mechanics",
            "does_not_support": "female short-story generalization, semantic label quality, model accuracy, or causal performance claims",
        },
    }


def benchmark(
    input_path: Path,
    *,
    label: str,
    max_codepoints: int = 6000,
    repeat_count: int = 1,
) -> dict:
    if repeat_count < 1:
        raise ValueError("repeat_count must be at least 1")
    runs = [
        _benchmark_once(input_path, label=label, max_codepoints=max_codepoints)
        for _ in range(repeat_count)
    ]
    result = runs[0]
    elapsed_runs = [run["runtime"]["elapsed_ms_median"] for run in runs]
    memory_runs = [run["runtime"]["peak_traced_memory_bytes_median"] for run in runs]
    fingerprints = [
        (
            run["input"]["raw_sha256"],
            run["normalization"]["normalized_sha256"],
            run["structure"]["chunk_manifest_sha256"],
            run["structure"]["chapter_heading_count"],
            run["structure"]["paragraph_count"],
            run["structure"]["chunk_count"],
        )
        for run in runs
    ]
    result["runtime"] = {
        "repeat_count": repeat_count,
        "elapsed_ms_runs": elapsed_runs,
        "elapsed_ms_median": round(float(median(elapsed_runs)), 3),
        "peak_traced_memory_bytes_runs": memory_runs,
        "peak_traced_memory_bytes_median": int(median(memory_runs)),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "deterministic_structure_across_runs": len(set(fingerprints)) == 1,
    }
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="authorized local UTF-8 text")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("private-benchmarks") / "novel-benchmark.json",
        help="private JSON output path (default: private-benchmarks/novel-benchmark.json)",
    )
    parser.add_argument("--label", default="authorized-local-long-form", help="non-sensitive input label")
    parser.add_argument("--max-codepoints", type=int, default=6000)
    parser.add_argument("--repeat", type=int, default=3, help="measurement repetitions (default: 3)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print("benchmark input does not exist or is not a file", file=sys.stderr)
        return 2
    try:
        result = benchmark(
            args.input,
            label=args.label,
            max_codepoints=args.max_codepoints,
            repeat_count=args.repeat,
        )
    except (OSError, ValueError) as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "output": str(args.output),
        "bytes": result["input"]["bytes"],
        "codepoints": result["normalization"]["codepoints"],
        "chapters": result["structure"]["chapter_heading_count"],
        "paragraphs": result["structure"]["paragraph_count"],
        "chunks": result["structure"]["chunk_count"],
        "largest_chunk": result["structure"]["largest_chunk_codepoints"],
        "repeat_count": result["runtime"]["repeat_count"],
        "elapsed_ms_median": result["runtime"]["elapsed_ms_median"],
        "peak_memory_bytes_median": result["runtime"]["peak_traced_memory_bytes_median"],
        "privacy_safe": not result["privacy"]["text_excerpt_emitted"],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
