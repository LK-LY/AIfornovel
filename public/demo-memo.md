# HerLens 研究备忘录

标题与导语的情绪承诺，是否在开篇与结尾获得支持？

生成时间：2026\-09\-22T03:01:21\.294511\+00:00 · 数据修订：1 · 样本数：4

运行模式：deterministic-research（固定边界研究流程；发现依据当前 SQL 结果和原文证据生成）。

## 包装钩子：结果前置

在当前选定的 4 篇作品中，2 篇包含“结果前置”标签；每个作品版本按标签值去重计数。

适用范围：合成演示样本，选定 4 篇；包装钩子 有有效标签 2 篇，缺失/不符合纳入条件 2 篇；数据修订 1。

局限：标签频次仅描述当前样本，不能代表读者偏好或市场热度；合成样本不能作为真实业务效果。

下一步：补充同题材、同文本覆盖范围的本人作品；独立复核“结果前置”及相反案例，记录分歧。

验收判据：每个纳入标签均有当前版本的精确原文引用；补充样本后重新运行并报告样本数与分歧数。

证据 ID：\["ev\-019\-01", "ev\-019\-02", "ev\-024\-01", "ev\-024\-02"\]

查询 ID：\["qry\-bba96bde1fa39a1924ae"\]

## 同口径曝光与点击的描述性汇总

站内推荐 / post\_publish\_d7 / 次：2 篇、2 个互不重叠的有效观测；曝光 40600、点击 7680，加权 CTR = 点击总和 ÷ 曝光总和 = 18\.92%。

适用范围：合成演示样本，选定 4 篇；包装钩子 有有效标签 2 篇，缺失/不符合纳入条件 2 篇；数据修订 1。 指标定义：impressions\_clicks\_v1。

局限：该数值来自合成演示指标，仅用于验证计算流程；不能作为真实业务改善。

下一步：对本人作品收集相同渠道、窗口、版本与计数单位的真实区间观测；包装实验需预先记录分流方式与主要指标。

验收判据：真实曝光与点击可追溯到原始观测；窗口不重叠；预先约定最小样本量与停止规则后再评估差异。

证据 ID：\[\]

查询 ID：\["qry\-bba96bde1fa39a1924ae"\]

## 原文证据

- ev\-024\-01 · 离婚后，我把春天留给自己 · v3 · title [5, 12)

  把春天留给自己

- ev\-024\-02 · 离婚后，我把春天留给自己 · v3 · intro [16, 34)

  签完字的那天，我在旧城开了一间花店。

- ev\-019\-01 · 前夫求复合时，我在给别人办婚礼 · v2 · title [0, 5)

  前夫求复合

- ev\-019\-02 · 前夫求复合时，我在给别人办婚礼 · v2 · p01 [0, 25)

  他在婚礼现场叫住我时，新娘正挽着别人的手走向花门。

## 查询与来源

以下为实际执行的只读 SQLite 查询；纳入前校验记录见排除项。

    WITH selected AS (
      SELECT DISTINCT a.work_id, a.version_id, a.value
      FROM annotations AS a
      JOIN annotation_evidence AS ae ON ae.annotation_id = a.id AND ae.work_id = a.work_id
      WHERE a.group_name = :group
        AND (:reviewed_only = 0 OR a.review_status = :reviewed_status)
        AND a.value NOT IN (:unknown, :not_applicable)
    )
    SELECT value, COUNT(*) AS work_count
    FROM selected GROUP BY value ORDER BY work_count DESC, value;

    SELECT DISTINCT a.value, a.work_id, ae.evidence_id
    FROM annotations AS a
    JOIN annotation_evidence AS ae ON ae.annotation_id = a.id AND ae.work_id = a.work_id
    WHERE a.group_name = :group
      AND (:reviewed_only = 0 OR a.review_status = :reviewed_status)
      AND a.value NOT IN (:unknown, :not_applicable)
    ORDER BY a.value, a.work_id, ae.evidence_id;

    SELECT synthetic, definition, channel, window_spec, counting_unit,
           COUNT(DISTINCT work_id) AS work_count, COUNT(*) AS observation_count,
           SUM(impressions) AS impressions, SUM(clicks) AS clicks,
           1.0 * SUM(clicks) / NULLIF(SUM(impressions), :zero) AS ctr
    FROM observations
    GROUP BY synthetic, definition, channel, window_spec, counting_unit
    ORDER BY synthetic, definition, channel, window_spec, counting_unit;

参数：\{"group": "包装钩子", "not\_applicable": "not\_applicable", "reviewed\_only": 1, "reviewed\_status": "已审核", "unknown": "unknown", "zero": 0\}

来源快照：\[\{"annotationHash": "5864dbc215555cd10c5b39f26f694eeee12d8d5e652550856d713610501c9ac5", "contentHash": "18c87ca559544ed5caf03cd33aab6f32590d1742bdac10c04c4933a1d6b1f13f", "isSynthetic": true, "observationHash": "8ce62219f82edaf400625521aaea5cb59837765c76a1963a0abd9fd0dcb67368", "revision": 1, "scope": "full\_text", "versionId": "v3", "workId": "HL\-024"\}, \{"annotationHash": "7dc933a785342d3ae906254cfcfe07578cbfbad7c61f00a581da16217dfab021", "contentHash": "9a8855c5fcdf7daa5910f92b7fc7026c6638daddd72e9ed464d95171d3a44770", "isSynthetic": true, "observationHash": "e430f669d574b07cbf5c3aca7d08720c4eb4638a756e18c59117542fa5d93b2d", "revision": 1, "scope": "full\_text", "versionId": "v2", "workId": "HL\-019"\}, \{"annotationHash": "3b028ecbfa9cd171547d29c6676b13d75b8011c47d8b09347673b3040eb95a8e", "contentHash": "15deabaa553592ce8a4dc4ae41aae080cdea4aa6e720aeb473d55e04f54f473c", "isSynthetic": true, "observationHash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "revision": 1, "scope": "opening\_only", "versionId": "v1", "workId": "HL\-011"\}, \{"annotationHash": "b53763499311fa374c381ea996d84ec20281489cd969bd53a24567eac65eb3ba", "contentHash": "02077d40d11087120f6414e72a48325b5a8a78b8216c9d21ae034f39d59d518f", "isSynthetic": true, "observationHash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "revision": 1, "scope": "metadata\_only", "versionId": "v1", "workId": "HL\-006"\}\]

排除项：\[\{"annotationId": "an\-99b1826ce201ba10", "reason": "标签未经人工审核", "workId": "HL\-011"\}, \{"annotationId": "an\-e900cddd692b76c4", "reason": "标签未经人工审核", "workId": "HL\-006"\}, \{"reason": "无指标观测；不以 0 填补缺失值", "workId": "HL\-011"\}, \{"reason": "无指标观测；不以 0 填补缺失值", "workId": "HL\-006"\}\]

## 执行轨迹

- 1. inspect\_dataset · completed · 0.137 ms

  输入：\{"workIds": \["HL\-024", "HL\-019", "HL\-011", "HL\-006"\]\}

  输出：\{"hasMetricObservations": true, "realIds": \[\], "sampleCount": 4, "sourceSnapshot": \[\{"annotationHash": "5864dbc215555cd10c5b39f26f694eeee12d8d5e652550856d713610501c9ac5", "contentHash": "18c87ca559544ed5caf03cd33aab6f32590d1742bdac10c04c4933a1d6b1f13f", "isSynthetic": true, "observationHash": "8ce62219f82edaf400625521aaea5cb59837765c76a1963a0abd9fd0dcb67368", "revision": 1, "scope": "full\_text", "versionId": "v3", "workId": "HL\-024"\}, \{"annotationHash": "7dc933a785342d3ae906254cfcfe07578cbfbad7c61f00a581da16217dfab021", "contentHash": "9a8855c5fcdf7daa5910f92b7fc7026c6638daddd72e9ed464d95171d3a44770", "isSynthetic": true, "observationHash": "e430f669d574b07cbf5c3aca7d08720c4eb4638a756e18c59117542fa5d93b2d", "revision": 1, "scope": "full\_text", "versionId": "v2", "workId": "HL\-019"\}, \{"annotationHash": "3b028ecbfa9cd171547d29c6676b13d75b8011c47d8b09347673b3040eb95a8e", "contentHash": "15deabaa553592ce8a4dc4ae41aae080cdea4aa6e720aeb473d55e04f54f473c", "isSynthetic": true, "observationHash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "revision": 1, "scope": "opening\_only", "versionId": "v1", "workId": "HL\-011"\}, \{"annotationHash": "b53763499311fa374c381ea996d84ec20281489cd969bd53a24567eac65eb3ba", "contentHash": "02077d40d11087120f6414e72a48325b5a8a78b8216c9d21ae034f39d59d518f", "isSynthetic": true, "observationHash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "revision": 1, "scope": "metadata\_only", "versionId": "v1", "workId": "HL\-006"\}\], "syntheticIds": \["HL\-024", "HL\-019", "HL\-011", "HL\-006"\]\}

- 2. select\_cohort · completed · 0.003 ms

  输入：\{"question": "标题与导语的情绪承诺，是否在开篇与结尾获得支持？", "realIds": \[\], "syntheticIds": \["HL\-024", "HL\-019", "HL\-011", "HL\-006"\]\}

  输出：\{"isSynthetic": true, "selection": "用户选定样本；非随机抽样，不推断市场总体", "workIds": \["HL\-024", "HL\-019", "HL\-011", "HL\-006"\]\}

- 3. aggregate\_features · completed · 1.103 ms

  输入：\{"group": "包装钩子", "reviewedOnly": true, "revision": 1, "workIds": \["HL\-024", "HL\-019", "HL\-011", "HL\-006"\]\}

  输出：\{"durationMs": 1\.086, "excluded": \[\{"annotationId": "an\-99b1826ce201ba10", "reason": "标签未经人工审核", "workId": "HL\-011"\}, \{"annotationId": "an\-e900cddd692b76c4", "reason": "标签未经人工审核", "workId": "HL\-006"\}, \{"reason": "无指标观测；不以 0 填补缺失值", "workId": "HL\-011"\}, \{"reason": "无指标观测；不以 0 填补缺失值", "workId": "HL\-006"\}\], "frequencies": \[\{"count": 2, "evidenceIds": \["ev\-019\-01", "ev\-019\-02", "ev\-024\-01", "ev\-024\-02"\], "value": "结果前置", "workIds": \["HL\-019", "HL\-024"\]\}\], "group": "包装钩子", "metricGroups": \[\{"channel": "站内推荐", "clicks": 7680, "countingUnit": "次", "ctr": 0\.1891625615763547, "definition": "impressions\_clicks\_v1", "impressions": 40600, "isSynthetic": true, "key": "metric\-1f36c6894afe3154", "observationCount": 2, "observations": \[\{"channel": "站内推荐", "clicks": 3720, "countingUnit": "次", "ctrReported": 20, "definition": "impressions\_clicks\_v1", "id": "metric\-024", "impressions": 18600, "isSynthetic": true, "observationType": "interval", "status": "可比", "unit": "次", "versionId": "v3", "window": "发布后 7 日", "windowEnd": "2026\-09\-08T00:00:00Z", "windowSpec": "post\_publish\_d7", "windowStart": "2026\-09\-01T00:00:00Z", "workId": "HL\-024"\}, \{"channel": "站内推荐", "clicks": 3960, "countingUnit": "次", "ctrReported": 18, "definition": "impressions\_clicks\_v1", "id": "metric\-019", "impressions": 22000, "isSynthetic": true, "observationType": "interval", "status": "可比", "unit": "次", "versionId": "v2", "window": "发布后 7 日", "windowEnd": "2026\-09\-08T00:00:00Z", "windowSpec": "post\_publish\_d7", "windowStart": "2026\-09\-01T00:00:00Z", "workId": "HL\-019"\}\], "sampleCount": 2, "windowSpec": "post\_publish\_d7", "workIds": \["HL\-019", "HL\-024"\]\}\], "missingCount": 2, "params": \{"group": "包装钩子", "not\_applicable": "not\_applicable", "reviewed\_only": 1, "reviewed\_status": "已审核", "unknown": "unknown", "zero": 0\}, "queryId": "qry\-bba96bde1fa39a1924ae", "reviewedOnly": true, "revision": 1, "sampleCount": 4, "sourceSnapshot": \[\{"annotationHash": "5864dbc215555cd10c5b39f26f694eeee12d8d5e652550856d713610501c9ac5", "contentHash": "18c87ca559544ed5caf03cd33aab6f32590d1742bdac10c04c4933a1d6b1f13f", "isSynthetic": true, "observationHash": "8ce62219f82edaf400625521aaea5cb59837765c76a1963a0abd9fd0dcb67368", "revision": 1, "scope": "full\_text", "versionId": "v3", "workId": "HL\-024"\}, \{"annotationHash": "7dc933a785342d3ae906254cfcfe07578cbfbad7c61f00a581da16217dfab021", "contentHash": "9a8855c5fcdf7daa5910f92b7fc7026c6638daddd72e9ed464d95171d3a44770", "isSynthetic": true, "observationHash": "e430f669d574b07cbf5c3aca7d08720c4eb4638a756e18c59117542fa5d93b2d", "revision": 1, "scope": "full\_text", "versionId": "v2", "workId": "HL\-019"\}, \{"annotationHash": "3b028ecbfa9cd171547d29c6676b13d75b8011c47d8b09347673b3040eb95a8e", "contentHash": "15deabaa553592ce8a4dc4ae41aae080cdea4aa6e720aeb473d55e04f54f473c", "isSynthetic": true, "observationHash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "revision": 1, "scope": "opening\_only", "versionId": "v1", "workId": "HL\-011"\}, \{"annotationHash": "b53763499311fa374c381ea996d84ec20281489cd969bd53a24567eac65eb3ba", "contentHash": "02077d40d11087120f6414e72a48325b5a8a78b8216c9d21ae034f39d59d518f", "isSynthetic": true, "observationHash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "revision": 1, "scope": "metadata\_only", "versionId": "v1", "workId": "HL\-006"\}\], "sql": "WITH selected AS \(\\n  SELECT DISTINCT a\.work\_id, a\.version\_id, a\.value\\n  FROM annotations AS a\\n  JOIN annotation\_evidence AS ae ON ae\.annotation\_id = a\.id AND ae\.work\_id = a\.work\_id\\n  WHERE a\.group\_name = :group\\n    AND \(:reviewed\_only = 0 OR a\.review\_status = :reviewed\_status\)\\n    AND a\.value NOT IN \(:unknown, :not\_applicable\)\\n\)\\nSELECT value, COUNT\(\*\) AS work\_count\\nFROM selected GROUP BY value ORDER BY work\_count DESC, value;\\n\\nSELECT DISTINCT a\.value, a\.work\_id, ae\.evidence\_id\\nFROM annotations AS a\\nJOIN annotation\_evidence AS ae ON ae\.annotation\_id = a\.id AND ae\.work\_id = a\.work\_id\\nWHERE a\.group\_name = :group\\n  AND \(:reviewed\_only = 0 OR a\.review\_status = :reviewed\_status\)\\n  AND a\.value NOT IN \(:unknown, :not\_applicable\)\\nORDER BY a\.value, a\.work\_id, ae\.evidence\_id;\\n\\nSELECT synthetic, definition, channel, window\_spec, counting\_unit,\\n       COUNT\(DISTINCT work\_id\) AS work\_count, COUNT\(\*\) AS observation\_count,\\n       SUM\(impressions\) AS impressions, SUM\(clicks\) AS clicks,\\n       1\.0 \* SUM\(clicks\) / NULLIF\(SUM\(impressions\), :zero\) AS ctr\\nFROM observations\\nGROUP BY synthetic, definition, channel, window\_spec, counting\_unit\\nORDER BY synthetic, definition, channel, window\_spec, counting\_unit;"\}

- 4. compare\_metrics · completed · 0.003 ms

  输入：\{"queryId": "qry\-bba96bde1fa39a1924ae"\}

  输出：\{"boundary": "只按同口径分层汇总；不跨渠道/窗口/计数单位比较，也不推断内容特征导致表现。", "excluded": \[\{"annotationId": "an\-99b1826ce201ba10", "reason": "标签未经人工审核", "workId": "HL\-011"\}, \{"annotationId": "an\-e900cddd692b76c4", "reason": "标签未经人工审核", "workId": "HL\-006"\}, \{"reason": "无指标观测；不以 0 填补缺失值", "workId": "HL\-011"\}, \{"reason": "无指标观测；不以 0 填补缺失值", "workId": "HL\-006"\}\], "groups": \[\{"channel": "站内推荐", "clicks": 7680, "countingUnit": "次", "ctr": 0\.1891625615763547, "definition": "impressions\_clicks\_v1", "impressions": 40600, "isSynthetic": true, "key": "metric\-1f36c6894afe3154", "observationCount": 2, "observations": \[\{"channel": "站内推荐", "clicks": 3720, "countingUnit": "次", "ctrReported": 20, "definition": "impressions\_clicks\_v1", "id": "metric\-024", "impressions": 18600, "isSynthetic": true, "observationType": "interval", "status": "可比", "unit": "次", "versionId": "v3", "window": "发布后 7 日", "windowEnd": "2026\-09\-08T00:00:00Z", "windowSpec": "post\_publish\_d7", "windowStart": "2026\-09\-01T00:00:00Z", "workId": "HL\-024"\}, \{"channel": "站内推荐", "clicks": 3960, "countingUnit": "次", "ctrReported": 18, "definition": "impressions\_clicks\_v1", "id": "metric\-019", "impressions": 22000, "isSynthetic": true, "observationType": "interval", "status": "可比", "unit": "次", "versionId": "v2", "window": "发布后 7 日", "windowEnd": "2026\-09\-08T00:00:00Z", "windowSpec": "post\_publish\_d7", "windowStart": "2026\-09\-01T00:00:00Z", "workId": "HL\-019"\}\], "sampleCount": 2, "windowSpec": "post\_publish\_d7", "workIds": \["HL\-019", "HL\-024"\]\}\]\}

- 5. get\_evidence · completed · 0.048 ms

  输入：\{"evidenceIds": \["ev\-019\-01", "ev\-019\-02", "ev\-024\-01", "ev\-024\-02"\], "workIds": \["HL\-024", "HL\-019", "HL\-011", "HL\-006"\]\}

  输出：\{"evidence": \[\{"contentHash": "18c87ca559544ed5caf03cd33aab6f32590d1742bdac10c04c4933a1d6b1f13f", "endChar": 12, "field": "标题", "id": "ev\-024\-01", "note": "标题中的自我回收与脱离关系承诺", "paragraphId": "title", "quote": "把春天留给自己", "reviewStatus": "已审核", "startChar": 5, "title": "离婚后，我把春天留给自己", "versionId": "v3", "workId": "HL\-024"\}, \{"contentHash": "18c87ca559544ed5caf03cd33aab6f32590d1742bdac10c04c4933a1d6b1f13f", "endChar": 34, "field": "导语", "id": "ev\-024\-02", "note": "明确给出关系断裂后的新目标", "paragraphId": "intro", "quote": "签完字的那天，我在旧城开了一间花店。", "reviewStatus": "已审核", "startChar": 16, "title": "离婚后，我把春天留给自己", "versionId": "v3", "workId": "HL\-024"\}, \{"contentHash": "9a8855c5fcdf7daa5910f92b7fc7026c6638daddd72e9ed464d95171d3a44770", "endChar": 5, "field": "标题", "id": "ev\-019\-01", "paragraphId": "title", "quote": "前夫求复合", "reviewStatus": "已审核", "startChar": 0, "title": "前夫求复合时，我在给别人办婚礼", "versionId": "v2", "workId": "HL\-019"\}, \{"contentHash": "9a8855c5fcdf7daa5910f92b7fc7026c6638daddd72e9ed464d95171d3a44770", "endChar": 25, "field": "开篇", "id": "ev\-019\-02", "paragraphId": "p01", "quote": "他在婚礼现场叫住我时，新娘正挽着别人的手走向花门。", "reviewStatus": "已审核", "startChar": 0, "title": "前夫求复合时，我在给别人办婚礼", "versionId": "v2", "workId": "HL\-019"\}\], "requestedIds": \["ev\-019\-01", "ev\-019\-02", "ev\-024\-01", "ev\-024\-02"\]\}

- 6. draft\_memo · completed · 0.028 ms

  输入：\{"evidenceIds": \["ev\-019\-01", "ev\-019\-02", "ev\-024\-01", "ev\-024\-02"\], "queryId": "qry\-bba96bde1fa39a1924ae", "question": "标题与导语的情绪承诺，是否在开篇与结尾获得支持？"\}

  输出：\{"findings": \[\{"criterion": "每个纳入标签均有当前版本的精确原文引用；补充样本后重新运行并报告样本数与分歧数。", "evidenceIds": \["ev\-019\-01", "ev\-019\-02", "ev\-024\-01", "ev\-024\-02"\], "id": "finding\-1", "limitation": "标签频次仅描述当前样本，不能代表读者偏好或市场热度；合成样本不能作为真实业务效果。", "nextStep": "补充同题材、同文本覆盖范围的本人作品；独立复核“结果前置”及相反案例，记录分歧。", "observation": "在当前选定的 4 篇作品中，2 篇包含“结果前置”标签；每个作品版本按标签值去重计数。", "queryIds": \["qry\-bba96bde1fa39a1924ae"\], "scope": "合成演示样本，选定 4 篇；包装钩子 有有效标签 2 篇，缺失/不符合纳入条件 2 篇；数据修订 1。", "title": "包装钩子：结果前置"\}, \{"criterion": "真实曝光与点击可追溯到原始观测；窗口不重叠；预先约定最小样本量与停止规则后再评估差异。", "evidenceIds": \[\], "id": "finding\-2", "limitation": "该数值来自合成演示指标，仅用于验证计算流程；不能作为真实业务改善。", "nextStep": "对本人作品收集相同渠道、窗口、版本与计数单位的真实区间观测；包装实验需预先记录分流方式与主要指标。", "observation": "站内推荐 / post\_publish\_d7 / 次：2 篇、2 个互不重叠的有效观测；曝光 40600、点击 7680，加权 CTR = 点击总和 ÷ 曝光总和 = 18\.92%。", "queryIds": \["qry\-bba96bde1fa39a1924ae"\], "scope": "合成演示样本，选定 4 篇；包装钩子 有有效标签 2 篇，缺失/不符合纳入条件 2 篇；数据修订 1。 指标定义：impressions\_clicks\_v1。", "title": "同口径曝光与点击的描述性汇总"\}\]\}
