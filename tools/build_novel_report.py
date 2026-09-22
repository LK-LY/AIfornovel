"""Package verified live novel analysis as a portable report and readable source.

No model calls or novel-specific findings live in this renderer. HTML uses the
canonical Data Analytics portable renderer supplied with --renderer.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import unicodedata
from uuid import uuid4


def verify_original_source(data: dict, original: Path) -> None:
    raw = original.read_bytes()
    source = data["source"]
    if sha256(raw).hexdigest() != source["raw_sha256"]:
        raise ValueError("Source file changed since the model run")
    normalized = unicodedata.normalize("NFC", raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n"))
    if sha256(normalized.encode("utf-8")).hexdigest() != source["normalized_sha256"]:
        raise ValueError("Normalized source hash does not match")
    for item in data["evidence"]:
        if normalized[item["start_char"]:item["end_char"]] != item["quote"]:
            raise ValueError(f"Evidence no longer matches source: {item['id']}")


def safe_text(value: object) -> str:
    return str(value).replace("<", "&lt;").replace(">", "&gt;").replace("[", "\\[").replace("]", "\\]")


def validate_analysis(data: dict) -> None:
    if data.get("run", {}).get("status") != "completed":
        raise ValueError("Only a completed live analysis can become an interview report")
    if data["run"].get("mode") != "codex-live-map-reduce":
        raise ValueError("Only a completed live analysis can become an interview report")
    count = data["run"].get("chunk_count")
    if not isinstance(count, int) or count < 1 or len(data.get("maps", [])) != count:
        raise ValueError("Map count does not match completed chunk count")
    if data["run"].get("completed_chunks", count) != count:
        raise ValueError("Partial coverage cannot be reported as complete")
    evidence = data.get("evidence", [])
    ids = [item["id"] for item in evidence]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Evidence IDs must be nonempty and unique")
    if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in ids):
        raise ValueError("Invalid evidence identifier")
    source_length = data["source"]["codepoints"]
    for item in evidence:
        start, end = item["start_char"], item["end_char"]
        if not 0 <= start < end <= source_length or end - start != len(item["quote"]):
            raise ValueError("Invalid codepoint evidence span")
    for section in data["synthesis"]["sections"]:
        if len(set(section["evidence_ids"])) < 2 or not set(section["evidence_ids"]) <= set(ids):
            raise ValueError("Each section needs at least two valid evidence references")


def execute_snapshot_query(query: str) -> list[dict]:
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(query).fetchall()]


def distribution_query(evidence: list[dict], length: int) -> str:
    if not evidence or length <= 0:
        raise ValueError("Distribution needs nonempty validated evidence")
    values = ",".join(f"({int(item['start_char'])})" for item in evidence)
    return f"""WITH RECURSIVE
evidence(start_char) AS (VALUES {values}),
bins(n) AS (SELECT 0 UNION ALL SELECT n+1 FROM bins WHERE n<9)
SELECT printf('%d–%d%%',n*10,(n+1)*10) AS range,
       (SELECT COUNT(*) FROM evidence WHERE MIN(start_char*10/{int(length)},9)=n) AS count,
       n/10.0 AS start_fraction, (n+1)/10.0 AS end_fraction,
       {len(evidence)} AS total_verified_quotes, {int(length)} AS normalized_codepoints,
       '按唯一证据ID计数，依引文起点落入原文码点位置十分位；非情节密度' AS definition
FROM bins ORDER BY n"""


def evidence_distribution(evidence: list[dict], length: int) -> list[dict]:
    return execute_snapshot_query(distribution_query(evidence, length))


def literal(value: object) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build_artifact(data: dict) -> tuple[dict, dict]:
    validate_analysis(data)
    source, run, synthesis = data["source"], data["run"], data["synthesis"]
    evidence = {item["id"]: item for item in data["evidence"]}
    completed_at = run.get("completed_at", run.get("finished_at", ""))
    book_title = source.get("title", "小说")
    title = f"HerLens · 《{safe_text(book_title)}》内容研究报告"
    blocks = [{"id": "title", "type": "markdown", "body": f"# {title}"}]

    def section(identity: str, heading: str, paragraphs: list[str], source_id: str | None = None) -> None:
        block = {"id": identity, "type": "markdown", "body": f"## {safe_text(heading)}\n\n" + "\n\n".join(paragraphs)}
        if source_id:
            block["sourceId"] = source_id
        blocks.append(block)

    section("summary", "Executive Summary · 核心发现", [
        "\n".join(f"- {safe_text(item)}" for item in synthesis["executive_summary"]),
        "**阅读方式**：本报告是 Agent 对所提供文本的内容解读，面向内容策略与产品研究面试。下文引文已由程序逐字回查；解读仍需人工复核，不代表平台用户偏好或商业效果。",
    ], "analysis")
    section("scope", "研究对象与判断边界", [
        f"**分析主线**：{safe_text(synthesis['title'])}",
        "分析对象是用户提供的单个本地文本版本；区分包装文案、正文与番外，不以篇幅给作品设置产品边界。全文覆盖是对本文件的处理覆盖，不等于与正式出版版本逐章核对。",
        "**研究设定**：这是研究问题引导的单作品案例，不是盲测；提示词预先要求检查关系阶段、正文与番外等边界。报告用于展示抽取、核验和综合流程，不能把提示中已设定的检查点声称为模型独立发现。",
        "**证据分级**：原文直接陈述 → 基于上下文的模型解释 → 待实验验证的内容策略。三者不能互相替代；尤其不将拒绝、误会、关系建立和恋爱复合混为一谈。",
        "**引文的支持范围**：下列短引文是回到上下文的定位锚点。关联事件概括可能合并多个场景，不能将一条短引文视为整条复合判断已经得到充分证明；需要按子命题继续核对相邻原文。",
    ], "analysis")
    cited_ids: set[str] = set()
    for index, item in enumerate(synthesis["sections"], 1):
        paragraphs = [safe_text(p) for p in item["paragraphs"]]
        paragraphs.append("### 原文证据与解释")
        for identity in item["evidence_ids"]:
            ev = evidence[identity]
            cited_ids.add(identity)
            kind = {"metadata": "包装/前置材料", "main_text": "正文", "extra": "番外"}.get(ev.get("section_kind"), "文本")
            chapter = safe_text(ev.get("chapter_label") or ev.get("chapter_id") or kind)
            paragraphs.extend([
                f"> {safe_text(ev['quote'])}",
                f"**{chapter} · {kind}**  \n关联事件概括（模型）：{safe_text(ev['claim'])}  \n解释（待复核）：{safe_text(ev['interpretation'])}  \n{identity} · {safe_text(ev['paragraph_id'])} · 码点 [{ev['start_char']}, {ev['end_char']})",
            ])
        section(f"finding-{index}", item["heading"], paragraphs, "analysis")

    section("recommendations", "下一步：把文本机制转化为可验证的内容方案", [
        "以下是从本案例提炼的候选方法，不是已经产生增长的运营结论。",
        "\n".join(f"{i}. {safe_text(value)}" for i, value in enumerate(synthesis["recommendations"], 1)),
    ], "analysis")
    section("questions", "进一步需要验证的问题", [
        "\n".join(f"- {safe_text(value)}" for value in synthesis["hypotheses"]),
        "**补数方向**：如需讨论点击、留存或付费效果，应另取同版本、同渠道、同时间窗的可比观测，并明确分母；本报告没有这些数据。",
    ], "analysis")
    section("caveats", "局限与解读风险", [
        "\n".join(f"- {safe_text(value)}" for value in synthesis["limitations"]),
        "- 本报告仅供本地研究和面试展示准备；原作著作权归权利人所有。原文、节选及报告未加入公开 Demo，也未发布到 GitHub。",
        "- 没有人工金标集，不能将引用匹配通过率称为标签准确率、F1、文学判断正确率或跨作品泛化能力。",
        "- 事件类别和复合概括仍是模型候选；误会被呈现不等于已经修复，短引文存在不等于概括中的全部子命题均有充分证据。本报告不按这些候选类别生成语义频次或准确率统计。",
    ], "analysis")

    chunks = run.get("chunk_count", len(data.get("maps", [])))
    section("coverage", "运行证据：引文并非只来自文件开头", [
        f"本次运行处理 **{source['codepoints']:,} 个规范化 Unicode 码点**，完成 **{chunks} 个分析片段**，保留 **{len(evidence)} 条**逐字匹配的原文证据。采用分块抽取、原文回查与作品级综合流程。",
        "下图按引文起点在整份文件中的位置分组，展示抽取证据的分布。横轴不是阅读时长，纵轴不是情绪强度、情节数量或模型准确率；每块的有限抽取预算也会影响数量。",
    ], "analysis")
    blocks.append({"id": "evidence-chart", "type": "chart", "chartId": "evidence-positions", "layout": "full"})
    section("audit", "面试时可以复查什么", [
        "任选一个结论，核对其引文、章节与码点位置，再回到本地原文查看上下文；随后查看分块结果和运行记录，区分模型生成、确定性校验与人工评价。",
        "本报告保留完整证据索引和实际调用摘要。重新运行可复现处理流程与校验规则，但模型文本不承诺逐字相同。",
        "恢复运行时，完成的分块会重新执行原文校验后复用；本轮开始时间和调用量只代表此次恢复，历史分块的实际调用时间与用量保存在 cached_call_receipts 中，不重复计入本轮消耗。",
    ], "analysis")
    blocks.append({"id": "run-table", "type": "table", "tableId": "run-facts", "layout": "full"})

    facts = [
        {"order": 1, "item": "调用方式", "value": run.get("mode", "codex-live-map-reduce")},
        {"order": 2, "item": "模型标识", "value": run.get("model") or "调用结果未回传模型标识"},
        {"order": 3, "item": "CLI 版本", "value": run.get("cli_version", "未记录")},
        {"order": 4, "item": "本轮开始（含时区；可能复用缓存）", "value": run.get("started_at", "未记录")},
        {"order": 5, "item": "运行完成（含时区）", "value": completed_at or "未记录"},
        {"order": 6, "item": "覆盖与校验", "value": f"{chunks} 个分析片段；{len(evidence)} 条引用逐字核验；不代表语义准确率"},
        {"order": 7, "item": "经营数据", "value": "未提供；未计算CTR、留存、付费转化或爆款分数"},
        {"order": 8, "item": "人工审核", "value": "非人工金标评测；面试使用前由作品熟悉者复核"},
    ]
    if "model_call_count" in run:
        facts.extend([
            {"order": 9, "item": "本轮成功模型调用（含修复）", "value": str(run["model_call_count"])},
            {"order": 10, "item": "复用的已校验分块", "value": str(run.get("cached_chunk_count", 0))},
        ])
    if run.get("prompt_version"):
        facts.append({"order": 11, "item": "本次实际提示词版本", "value": run["prompt_version"]})
    if run.get("configured_model"):
        facts.insert(2, {"order": 2.5, "item": "调用时配置模型（非服务回传）", "value": run["configured_model"]})
    for index, row in enumerate(facts, 1):
        row["order"] = index
    canonical_source = {
        "id": "analysis", "label": "本地小说文本与 HerLens 实际运行结果", "path": "analysis.json",
        "query": {"engine": "HerLens verified file analysis", "language": "python",
                  "description": f"用户提供的 {source.get('input_filename', book_title)}；NFC/LF；原文SHA256={source.get('raw_sha256', '未记录')}；规范化SHA256={source.get('normalized_sha256', '未记录')}。模型分块抽取与综合，引用在指定段落内唯一匹配后计算全局码点偏移。",
                  "executed_at": completed_at,
                  "filters": ["单一作品、单一本地文本版本", "包含前置包装、正文、番外并保留类别", "仅程序核验通过的证据；无人工金标和真实经营数据"],
                  "metric_definitions": ["evidence_count：按唯一证据ID计数，不是情节/主题频次", "position_bin：floor(start_char / normalized_codepoints * 10)，右端100%并入末组"]},
    }
    quote_query = distribution_query(list(evidence.values()), source["codepoints"])
    facts_values = ",".join("(" + ",".join(literal(row[key]) for key in ("order", "item", "value")) + ")" for row in facts)
    facts_query = f'WITH run_snapshot("order",item,value) AS (VALUES {facts_values}) SELECT * FROM run_snapshot ORDER BY "order"'
    quote_source = {
        "id": "quote-distribution", "label": "analysis.json / evidence 引文位置统计", "path": "analysis.json",
        "query": {"engine": "SQLite", "language": "sql", "sql": quote_query, "executed_at": completed_at,
                  "description": "实际执行的自包含 SQLite 查询；VALUES 来自本次 analysis.json 已校验证据起点，而非平台经营数据。",
                  "metric_definitions": canonical_source["query"]["metric_definitions"]},
    }
    facts_source = {
        "id": "run-snapshot", "label": "analysis.json / run 实际运行摘要", "path": "analysis.json",
        "query": {"engine": "SQLite", "language": "sql", "sql": facts_query, "executed_at": completed_at,
                  "description": "实际执行的自包含 SQLite 查询；VALUES 是本次运行元数据及明确的使用边界，不是远程数据库结果。"},
    }
    sources = [canonical_source, quote_source, facts_source]
    artifact = {"surface": "report", "manifest": {
        "version": 1, "surface": "report", "title": title,
        "description": "全文分块分析 · 原文可核查 · 内容策略候选 · 本地私有案例",
        "generatedAt": completed_at, "blocks": blocks, "sources": sources,
        "cards": [], "charts": [{
            "id": "evidence-positions", "title": "已校验引文的位置分布", "type": "bar",
            "subtitle": "按文件码点进度分为十段；计数对象是抽取引文，而非情节或情绪", "showDescription": True,
            "dataset": "evidence-positions", "sourceId": "quote-distribution", "layout": "full",
            "encodings": {"x": {"field": "range", "type": "ordinal", "label": "文件进度"},
                          "y": {"field": "count", "type": "quantitative", "label": "已校验引文数", "format": "number"}},
            "valueFormat": "number", "palette": {"kind": "sequential", "name": "blue"},
            "labels": {"values": "all"}, "settings": {"sort": "none", "groupMode": "single"},
        }], "tables": [{
            "id": "run-facts", "title": "实际运行与使用边界", "dataset": "run-facts", "sourceId": "run-snapshot",
            "defaultSort": {"field": "order", "direction": "asc"},
            "columns": [{"field": "order", "label": "序", "format": "number"},
                        {"field": "item", "label": "项目", "type": "text"},
                        {"field": "value", "label": "记录", "type": "text"}],
        }]}, "snapshot": {"version": 1, "status": "ready", "generatedAt": completed_at,
                               "datasets": {"evidence-positions": execute_snapshot_query(quote_query), "run-facts": execute_snapshot_query(facts_query)}},
        "sources": sources}
    notes = {"audience": "product stakeholders", "delivery": "html", "required_structure": {
        "Title": "title", "Executive summary": "summary", "Key findings with visual evidence": "finding-1..N with exact quotes; coverage chart", "Recommended next steps": "recommendations", "Further questions": "questions", "Caveats and assumptions": "scope+caveats"},
        "chart_contract": {"question": "引用是否只抽取文件开头？", "family": "distribution, ordered bar", "grain": "evidence start-position decile", "rows": 10, "palette": "single-root blue; labels provide non-color reading", "omitted": "无经营数据、无可靠情绪金标；不绘制用户漏斗或情绪曲线"},
        "analysis_sha256": sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "cited_evidence_count": len(cited_ids), "all_evidence_count": len(evidence),
        "editorial_boundary": "Narrative from synthesis; deterministic packaging adds scope, audit, rights and metric caveats. No invented findings."}
    return artifact, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--source", type=Path, required=True, help="Original authorized text; hash and quotes are rechecked")
    parser.add_argument("--renderer", type=Path, help="Data Analytics deliver_portable_artifact.mjs")
    args = parser.parse_args(argv)
    data = json.loads(args.analysis.read_text(encoding="utf-8"))
    verify_original_source(data, args.source)
    artifact, notes = build_artifact(data)
    directory = args.analysis.parent.resolve()
    private_root = Path(__file__).resolve().parents[1] / "private-reports"
    if not directory.is_relative_to(private_root.resolve()):
        raise ValueError("Novel reports must remain under private-reports")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed" or manifest.get("fingerprint") != data["run"].get("fingerprint"):
        raise ValueError("Completed manifest fingerprint must match the analysis")
    if manifest.get("run_id") != data["run"].get("id") or manifest.get("source") != data["source"]:
        raise ValueError("Manifest source identity and run ID must match the analysis")
    chunking = manifest["chunking"]
    chunks = chunking["chunks"]
    if (not chunking.get("gap_free") or not chunks or chunks[0]["start_char"] != 0
            or chunks[-1]["end_char"] != data["source"]["codepoints"]
            or any(a["end_char"] != b["start_char"] for a, b in zip(chunks, chunks[1:]))
            or [item["id"] for item in chunks] != [item["chunk_id"] for item in data["maps"]]):
        raise ValueError("Manifest must prove gap-free file coverage by the completed maps")
    (directory / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "report-source-notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = "\n\n---\n\n".join(block["body"] for block in artifact["manifest"]["blocks"] if block["type"] == "markdown")
    (directory / "报告正文.md").write_text(markdown + "\n", encoding="utf-8")
    (directory / "evidence-index.json").write_text(json.dumps(data["evidence"], ensure_ascii=False, indent=2), encoding="utf-8")
    if args.renderer:
        candidate = directory / f".report-{uuid4().hex}.html"
        command = ["node", str(Path(__file__).with_name("deliver_novel_report.mjs")),
                   "--renderer", str(args.renderer.resolve()), "--input", str(directory / "artifact.json"),
                   "--output", str(candidate)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
        try:
            receipt = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("Renderer did not return a parseable verification receipt") from exc
        if not result.returncode and (not receipt.get("ok") or not candidate.is_file()):
            raise ValueError("Renderer reported success without the expected HTML artifact")
        if receipt.get("ok"):
            receipt["html_sha256"] = sha256(candidate.read_bytes()).hexdigest()
            candidate.replace(directory / "HerLens_分析报告.html")
            receipt["html"] = str(directory / "HerLens_分析报告.html")
        (directory / "render-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(result.stdout)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            return result.returncode
    print(json.dumps({"status": "packaged", "sections": len(data["synthesis"]["sections"]), "evidence": len(data["evidence"]), "directory": str(directory)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
