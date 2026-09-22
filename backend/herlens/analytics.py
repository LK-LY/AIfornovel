"""Reproducible, read-only SQL aggregates over a validated snapshot.

The temporary database never contains credentials or executes user-provided SQL.
Metric observations are validated before being loaded; rejection reasons are part
of the result, not silently discarded rows.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from time import perf_counter


FREQUENCY_SQL = """WITH selected AS (
  SELECT DISTINCT a.work_id, a.version_id, a.value
  FROM annotations AS a
  JOIN annotation_evidence AS ae ON ae.annotation_id = a.id AND ae.work_id = a.work_id
  WHERE a.group_name = :group
    AND (:reviewed_only = 0 OR a.review_status = :reviewed_status)
    AND a.value NOT IN (:unknown, :not_applicable)
)
SELECT value, COUNT(*) AS work_count
FROM selected GROUP BY value ORDER BY work_count DESC, value;"""

SUPPORT_SQL = """SELECT DISTINCT a.value, a.work_id, ae.evidence_id
FROM annotations AS a
JOIN annotation_evidence AS ae ON ae.annotation_id = a.id AND ae.work_id = a.work_id
WHERE a.group_name = :group
  AND (:reviewed_only = 0 OR a.review_status = :reviewed_status)
  AND a.value NOT IN (:unknown, :not_applicable)
ORDER BY a.value, a.work_id, ae.evidence_id;"""

METRIC_SQL = """SELECT synthetic, definition, channel, window_spec, counting_unit,
       COUNT(DISTINCT work_id) AS work_count, COUNT(*) AS observation_count,
       SUM(impressions) AS impressions, SUM(clicks) AS clicks,
       1.0 * SUM(clicks) / NULLIF(SUM(impressions), :zero) AS ctr
FROM observations
GROUP BY synthetic, definition, channel, window_spec, counting_unit
ORDER BY synthetic, definition, channel, window_spec, counting_unit;"""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def unique_works(works):
    """Identical repeated work rows are harmless; conflicting snapshots are not."""
    result = {}
    for work in works:
        work_id = work.get("id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError("作品缺少 id")
        if work_id in result and _canonical(result[work_id]) != _canonical(work):
            raise ValueError(f"作品 {work_id} 包含互相冲突的重复快照")
        result[work_id] = work
    return list(result.values())


def snapshot(works):
    return [{"workId": w["id"], "versionId": w.get("versionId"),
             "contentHash": w.get("contentHash") or _hash({"title": w.get("title"), "intro": w.get("intro"), "paragraphs": w.get("paragraphs", [])}),
             "annotationHash": _hash(w.get("annotations", [])),
             "observationHash": _hash(w.get("observations", [w["metric"]] if w.get("metric") else [])),
             "revision": w.get("revision", 0),
             "isSynthetic": w.get("isSynthetic") is True, "scope": w.get("scope")}
            for w in works]


def valid_evidence(work):
    """Only exact current-version Unicode character ranges can support a claim."""
    sources = {"title": work.get("title", ""), "intro": work.get("intro", "")}
    paragraphs = {p["id"]: p for p in work.get("paragraphs", []) if isinstance(p.get("id"), str)}
    sources.update({pid: paragraph.get("text", "") for pid, paragraph in paragraphs.items()})
    result = {}
    for evidence in work.get("evidence", []):
        if evidence.get("workId") != work["id"] or evidence.get("versionId") != work.get("versionId"):
            continue
        if evidence.get("contentHash") and work.get("contentHash") and evidence["contentHash"] != work["contentHash"]:
            continue
        field = evidence.get("field")
        paragraph_id = evidence.get("paragraphId")
        if field in ("标题", "导语"):
            if paragraph_id != {"标题": "title", "导语": "intro"}[field]:
                continue
        elif field in ("开篇", "正文", "结尾"):
            if work.get("scope") == "metadata_only" or paragraph_id in ("title", "intro"):
                continue
            paragraph = paragraphs.get(paragraph_id)
            if paragraph is None:
                continue
            label = str(paragraph.get("label", ""))
            if field == "开篇" and not label.startswith("开篇"):
                continue
            if field == "正文" and (work.get("scope") != "full_text" or not label.startswith("正文")):
                continue
            if field == "结尾" and (
                work.get("scope") != "full_text"
                or not work.get("endingConfirmed")
                or not (label.startswith("结尾") or label.startswith("开篇/结尾"))
            ):
                continue
        else:
            continue
        start, end = evidence.get("startChar"), evidence.get("endChar")
        source = sources.get(evidence.get("paragraphId"))
        if (not isinstance(source, str) or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(source) or source[start:end] != evidence.get("quote")):
            continue
        evidence_id = evidence.get("id")
        if isinstance(evidence_id, str) and evidence_id:
            result[evidence_id] = evidence
    return result


def _instant(value):
    if not isinstance(value, str):
        raise ValueError("缺少明确的观测起止时间")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Date-only/naive values have an explicit, stable UTC interpretation.
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _count(value):
    # Bound to the interoperable integer range used by JSON/JavaScript clients.
    return type(value) in (int, float) and 0 <= value <= 2**53 - 1 and math.isfinite(value) and int(value) == value


def _metric_rows(works, excluded):
    accepted = []
    for work in works:
        observations = work.get("observations")
        if observations is None:
            observations = [work["metric"]] if work.get("metric") else []
        if not observations:
            excluded.append({"workId": work["id"], "reason": "无指标观测；不以 0 填补缺失值"})
        candidates, seen = [], {}
        for observation in observations:
            oid = observation.get("id")
            reason = None
            if not isinstance(oid, str) or not oid:
                reason = "指标缺少观测 id"
            elif oid in seen:
                reason = "重复的指标观测 id；已去重" if seen[oid] == _canonical(observation) else "观测 id 冲突；不能合并"
                if seen[oid] != _canonical(observation):
                    candidates = [c for c in candidates if c["id"] != oid]
            elif observation.get("versionId") != work.get("versionId"):
                reason = "指标版本与当前文本版本不一致"
            elif observation.get("observationType") != "interval":
                reason = "累计快照或未注明区间的指标不能求和"
            elif observation.get("status") not in (None, "可比"):
                reason = "指标标记为不可比或缺失"
            elif any(not isinstance(observation.get(k), str) or not observation[k].strip()
                     for k in ("definition", "channel", "windowSpec", "countingUnit")):
                reason = "指标口径、渠道、窗口或计数单位缺失"
            elif observation.get("unit") and observation["unit"] != observation["countingUnit"]:
                reason = "展示单位与计数单位不一致"
            elif observation.get("impressions") is None or observation.get("clicks") is None:
                reason = "曝光或点击分母/分子缺失；仅上报 CTR 不参与汇总、不反推"
            elif not _count(observation["impressions"]) or not _count(observation["clicks"]):
                reason = "曝光与点击须为有限的非负整数"
            elif observation["impressions"] == 0 and observation["clicks"] > 0:
                reason = "零曝光却有点击，无法计算 CTR"
            elif observation["clicks"] > observation["impressions"]:
                reason = "点击超过曝光，当前曝光点击定义下不可比"
            if reason is None:
                try:
                    start, end = _instant(observation.get("windowStart")), _instant(observation.get("windowEnd"))
                    if start >= end:
                        raise ValueError("观测区间起点须早于终点")
                except (ValueError, TypeError, OverflowError):
                    reason = "观测起止时间缺失、无效或顺序错误"
            if oid not in seen:
                seen[oid] = _canonical(observation)
            if reason:
                excluded.append({"workId": work["id"], "observationId": oid, "reason": reason})
                continue
            candidate = dict(observation, workId=work["id"], isSynthetic=work.get("isSynthetic") is True)
            candidate["_start"], candidate["_end"] = start, end
            candidates.append(candidate)
        overlapping = set()
        for i, left in enumerate(candidates):
            for right in candidates[i + 1:]:
                if (all(left[k] == right[k] for k in ("definition", "channel", "windowSpec", "countingUnit"))
                        and left["_start"] < right["_end"] and right["_start"] < left["_end"]):
                    overlapping.update((left["id"], right["id"]))
        for candidate in candidates:
            if candidate["id"] in overlapping:
                excluded.append({"workId": work["id"], "observationId": candidate["id"], "reason": "同作品同口径观测区间重叠；全部冲突区间排除，避免重复累计"})
            else:
                candidate.pop("_start")
                candidate.pop("_end")
                accepted.append(candidate)
    totals = {}
    for observation in accepted:
        key = tuple(observation[k] for k in ("isSynthetic", "definition", "channel", "windowSpec", "countingUnit"))
        totals[key] = totals.get(key, 0) + observation["impressions"]
    safe = []
    for observation in accepted:
        key = tuple(observation[k] for k in ("isSynthetic", "definition", "channel", "windowSpec", "countingUnit"))
        if totals[key] > 2**53 - 1:
            excluded.append({"workId": observation["workId"], "observationId": observation["id"], "reason": "同口径总量超过安全整数范围，拒绝返回可能失真的汇总"})
        else:
            safe.append(observation)
    return safe


def compare(works: list[dict], revision: int, group: str = "包装钩子", reviewed_only: bool = True) -> dict:
    started = perf_counter()
    works = unique_works(works)
    excluded, annotation_rows, evidence_rows = [], [], []
    for work in works:
        evidence = valid_evidence(work)
        for index, annotation in enumerate(work.get("annotations", [])):
            if annotation.get("group") != group:
                continue
            if reviewed_only and annotation.get("reviewStatus") != "已审核":
                excluded.append({"workId": work["id"], "annotationId": annotation.get("id"), "reason": "标签未经人工审核"})
                continue
            if annotation.get("value") in (None, "", "unknown", "not_applicable"):
                continue
            ids = list(dict.fromkeys(annotation.get("evidenceIds", [])))
            if not ids or any(eid not in evidence for eid in ids):
                excluded.append({"workId": work["id"], "annotationId": annotation.get("id"), "reason": "标签缺少完整、精确且属于当前版本的原文证据"})
                continue
            if group in ("包装钩子", "情绪承诺", "承诺兑现") and not any(
                    evidence[eid].get("field") in ("标题", "导语") for eid in ids):
                excluded.append({"workId": work["id"], "annotationId": annotation.get("id"), "reason": "包装或情绪承诺缺少标题／导语原文证据"})
                continue
            if group == "承诺兑现" and (work.get("scope") != "full_text" or not work.get("endingConfirmed")
                                           or not any(evidence[eid].get("field") == "结尾" for eid in ids)):
                excluded.append({"workId": work["id"], "annotationId": annotation.get("id"), "reason": "未确认完整结尾，不判断承诺兑现"})
                continue
            # A local row identity prevents duplicate caller ids from multiplying joins.
            local_id = f"{work['id']}:{index}"
            annotation_rows.append((local_id, work["id"], work.get("versionId"), group,
                                    annotation.get("label", ""), annotation["value"], annotation.get("reviewStatus", "待审核")))
            evidence_rows.extend((local_id, work["id"], eid) for eid in ids)
    metric_rows = _metric_rows(works, excluded)
    params = {"group": group, "reviewed_only": int(reviewed_only), "reviewed_status": "已审核",
              "unknown": "unknown", "not_applicable": "not_applicable", "zero": 0}
    with sqlite3.connect(":memory:") as connection:
        connection.executescript("""
          CREATE TABLE annotations(id TEXT, work_id TEXT, version_id TEXT, group_name TEXT, label TEXT, value TEXT, review_status TEXT);
          CREATE TABLE annotation_evidence(annotation_id TEXT, work_id TEXT, evidence_id TEXT);
          CREATE TABLE observations(id TEXT, work_id TEXT, synthetic INTEGER, definition TEXT, channel TEXT, window_spec TEXT,
                                    counting_unit TEXT, impressions INTEGER, clicks INTEGER);
        """)
        connection.executemany("INSERT INTO annotations VALUES (?, ?, ?, ?, ?, ?, ?)", annotation_rows)
        connection.executemany("INSERT INTO annotation_evidence VALUES (?, ?, ?)", evidence_rows)
        connection.executemany("INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               [(o["id"], o["workId"], int(o["isSynthetic"]), o["definition"], o["channel"], o["windowSpec"],
                                 o["countingUnit"], int(o["impressions"]), int(o["clicks"])) for o in metric_rows])
        connection.execute("PRAGMA query_only = ON")
        frequency_results = connection.execute(FREQUENCY_SQL, params).fetchall()
        support = connection.execute(SUPPORT_SQL, params).fetchall()
        metric_results = connection.execute(METRIC_SQL, params).fetchall()
    frequencies = [{"value": value, "count": count,
                    "workIds": sorted({row[1] for row in support if row[0] == value}),
                    "evidenceIds": sorted({row[2] for row in support if row[0] == value})}
                   for value, count in frequency_results]
    metric_groups = []
    for synthetic, definition, channel, window, unit, n, observations, impressions, clicks, ctr in metric_results:
        matching = [o for o in metric_rows if (o["isSynthetic"], o["definition"], o["channel"], o["windowSpec"], o["countingUnit"])
                    == (bool(synthetic), definition, channel, window, unit)]
        key_parts = [bool(synthetic), definition, channel, window, unit]
        metric_groups.append({"key": "metric-" + _hash(key_parts)[:16], "isSynthetic": bool(synthetic),
                              "definition": definition, "channel": channel, "windowSpec": window, "countingUnit": unit,
                              "workIds": sorted({o["workId"] for o in matching}), "sampleCount": n,
                              "observationCount": observations, "observations": matching,
                              "impressions": impressions, "clicks": clicks, "ctr": ctr})
    return {"queryId": "qry-" + _hash([works, revision, group, reviewed_only])[:20], "revision": revision,
            "sampleCount": len(works), "missingCount": len(works) - len({row[1] for row in support}),
            "sourceSnapshot": snapshot(works), "group": group, "reviewedOnly": reviewed_only,
            "frequencies": frequencies, "metricGroups": metric_groups, "excluded": excluded,
            "sql": FREQUENCY_SQL + "\n\n" + SUPPORT_SQL + "\n\n" + METRIC_SQL, "params": params,
            "durationMs": round((perf_counter() - started) * 1000, 3)}
