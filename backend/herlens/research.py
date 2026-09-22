"""A bounded deterministic research workflow with real, inspectable tool calls."""
from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from .analytics import compare, snapshot, unique_works, valid_evidence


def inspect_dataset(works):
    return {"sampleCount": len(works), "syntheticIds": [w["id"] for w in works if w.get("isSynthetic") is True],
            "realIds": [w["id"] for w in works if w.get("isSynthetic") is not True],
            "sourceSnapshot": snapshot(works), "hasMetricObservations": any(w.get("observations") or w.get("metric") for w in works)}


def select_cohort(works, inspection):
    if inspection["syntheticIds"] and inspection["realIds"]:
        return {"workIds": [], "refusal": "真实作品与合成演示样本不能混为一个研究队列；请单独选择一种来源后重新运行。"}
    if not works:
        return {"workIds": [], "refusal": "未选择作品，无法研究。"}
    return {"workIds": [w["id"] for w in works], "isSynthetic": bool(inspection["syntheticIds"]),
            "selection": "用户选定样本；非随机抽样，不推断市场总体"}


def aggregate_features(works, revision, group, reviewed_only):
    return compare(works, revision, group, reviewed_only)


def compare_metrics(comparison):
    groups = comparison["metricGroups"]
    available = [g for g in groups if g["ctr"] is not None]
    if not available:
        return {"groups": [], "refusal": "没有具备可比曝光和点击分母的指标；拒绝生成表现优劣或 CTR 结论。",
                "excluded": comparison["excluded"]}
    return {"groups": available, "excluded": comparison["excluded"],
            "boundary": "只按同口径分层汇总；不跨渠道/窗口/计数单位比较，也不推断内容特征导致表现。"}


def get_evidence(works, evidence_ids):
    wanted = set(evidence_ids)
    return {"evidence": [dict(e, title=w.get("title", "")) for w in works for eid, e in valid_evidence(w).items() if eid in wanted],
            "requestedIds": sorted(wanted)}


def draft_memo(comparison, metric_result, evidence_result, cohort):
    """All numbers/claims are derived from completed tools; never a live-model claim."""
    if cohort.get("refusal"):
        return {"findings": [], "refusal": cohort["refusal"]}
    findings = []
    n, missing = comparison["sampleCount"], comparison["missingCount"]
    supported = {e["id"] for e in evidence_result["evidence"]}
    source = "合成演示样本" if cohort["isSynthetic"] else "用户导入作品"
    scope = f"{source}，选定 {n} 篇；{comparison['group']} 有有效标签 {n - missing} 篇，缺失/不符合纳入条件 {missing} 篇；数据修订 {comparison['revision']}。"
    for frequency in comparison["frequencies"][:2]:
        ids = [eid for eid in frequency["evidenceIds"] if eid in supported]
        if not ids:
            continue
        findings.append({"id": f"finding-{len(findings) + 1}", "title": f"{comparison['group']}：{frequency['value']}",
                         "observation": f"在当前选定的 {n} 篇作品中，{frequency['count']} 篇包含“{frequency['value']}”标签；每个作品版本按标签值去重计数。",
                         "evidenceIds": ids, "queryIds": [comparison["queryId"]], "scope": scope,
                         "limitation": "标签频次仅描述当前样本，不能代表读者偏好或市场热度；合成样本不能作为真实业务效果。" if cohort["isSynthetic"] else "样本由用户选定；标签频次不能代表市场占比，也不构成内容质量或因果证据。",
                         "nextStep": f"补充同题材、同文本覆盖范围的本人作品；独立复核“{frequency['value']}”及相反案例，记录分歧。",
                         "criterion": "每个纳入标签均有当前版本的精确原文引用；补充样本后重新运行并报告样本数与分歧数。"})
    if metric_result.get("groups") and len(findings) < 3:
        group = metric_result["groups"][0]
        findings.append({"id": f"finding-{len(findings) + 1}", "title": "同口径曝光与点击的描述性汇总",
                         "observation": f"{group['channel']} / {group['windowSpec']} / {group['countingUnit']}：{len(group['workIds'])} 篇、{group['observationCount']} 个互不重叠的有效观测；曝光 {group['impressions']}、点击 {group['clicks']}，加权 CTR = 点击总和 ÷ 曝光总和 = {group['ctr']:.2%}。",
                         "evidenceIds": [], "queryIds": [comparison["queryId"]], "scope": scope + f" 指标定义：{group['definition']}。",
                         "limitation": "该数值来自合成演示指标，仅用于验证计算流程；不能作为真实业务改善。" if cohort["isSynthetic"] else "汇总没有控制流量、作者基础和发布时间；不能据此判断标签导致 CTR 变化。",
                         "nextStep": "对本人作品收集相同渠道、窗口、版本与计数单位的真实区间观测；包装实验需预先记录分流方式与主要指标。",
                         "criterion": "真实曝光与点击可追溯到原始观测；窗口不重叠；预先约定最小样本量与停止规则后再评估差异。"})
    if not findings:
        return {"findings": [], "refusal": "当前队列没有可引用的已审核标签或可比指标；先补齐证据与审核，再生成发现。"}
    return {"findings": findings}


def research(works, revision, question, group="包装钩子", reviewed_only=True):
    works = unique_works(works)
    trace = []

    def run(tool, inputs, operation):
        started = perf_counter()
        output = operation()
        trace.append({"index": len(trace) + 1, "tool": tool, "status": "refused" if output.get("refusal") else "completed",
                      "input": inputs, "output": output, "durationMs": round((perf_counter() - started) * 1000, 3)})
        return output

    inspection = run("inspect_dataset", {"workIds": [w["id"] for w in works]}, lambda: inspect_dataset(works))
    cohort = run("select_cohort", {"question": question, "syntheticIds": inspection["syntheticIds"], "realIds": inspection["realIds"]},
                 lambda: select_cohort(works, inspection))
    selected = [w for w in works if w["id"] in cohort["workIds"]]
    comparison = run("aggregate_features", {"workIds": cohort["workIds"], "revision": revision, "group": group, "reviewedOnly": reviewed_only},
                     lambda: aggregate_features(selected, revision, group, reviewed_only))
    metrics = run("compare_metrics", {"queryId": comparison["queryId"]}, lambda: compare_metrics(comparison))
    evidence_ids = sorted({eid for f in comparison["frequencies"][:2] for eid in f["evidenceIds"]})
    evidence = run("get_evidence", {"workIds": cohort["workIds"], "evidenceIds": evidence_ids}, lambda: get_evidence(selected, evidence_ids))
    memo = run("draft_memo", {"queryId": comparison["queryId"], "question": question, "evidenceIds": evidence_ids},
               lambda: draft_memo(comparison, metrics, evidence, cohort))
    report = {"id": "report-" + uuid4().hex, "question": question, "revision": revision,
              "createdAt": datetime.now(timezone.utc).isoformat(), "stale": False, "mode": "deterministic-research",
              "sampleCount": comparison["sampleCount"], "findings": memo["findings"], "trace": trace, "comparison": comparison}
    if memo.get("refusal"):
        report["refusal"] = memo["refusal"]
    return report
