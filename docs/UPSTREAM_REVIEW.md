# 上游快照核验与复用决策

**核验日期：**2026-09-22

**核验方式：**通过 GitHub 公开 API 和 pinned raw source 读取 commit、LICENSE 与相关源文件。本记录只证明该快照存在且查看到的源文件具有所述结构，不等于对上游做了完整安装、安全或生产验收。

## 已验证快照

| 项目 | 锁定提交 | GitHub 返回提交日期 | 许可证 |
| --- | --- | --- | --- |
| [`elecfish-yxf/novel-deconstructor`](https://github.com/elecfish-yxf/novel-deconstructor) | [`a91931691af905fda04282988f3dd86e46e86646`](https://github.com/elecfish-yxf/novel-deconstructor/commit/a91931691af905fda04282988f3dd86e46e86646) | 2026-07-11 UTC | [MIT，Copyright (c) 2026 elecfish-yxf](https://github.com/elecfish-yxf/novel-deconstructor/blob/a91931691af905fda04282988f3dd86e46e86646/LICENSE) |
| [`Ce-Legend/novel-analysis-agent`](https://github.com/Ce-Legend/novel-analysis-agent) | [`93e45864937cb3bc0794a5bdcfaaebe94e154c02`](https://github.com/Ce-Legend/novel-analysis-agent/commit/93e45864937cb3bc0794a5bdcfaaebe94e154c02) | 2026-05-17 UTC | [MIT，Copyright (c) 2026 Ce-Legend](https://github.com/Ce-Legend/novel-analysis-agent/blob/93e45864937cb3bc0794a5bdcfaaebe94e154c02/LICENSE) |

## 读取范围与结论

### novel-deconstructor

- README、`frontend/package.json`、`backend/requirements.txt`：确认 React / Vite / TypeScript + FastAPI / SQLAlchemy 工程方向以及文本上传、切分、任务和导出范围。
- `services/pipeline.py`：设计核验时的主流程保存 Markdown 结果，并有原始提示／响应落盘路径。因此它不自动提供 HerLens 所需的严格标签表、数值分析与证据语义审核，且公开快照不能继承其原始请求日志。
- `services/file_parser.py`：读取了 UTF-8/GB 系列编码检测、换行规范化、DOCX/PDF 抽取和有界上传的实现。
- `services/chapter_splitter.py`：读取了中文章节标题、稳定分块 ID、偏移和有界长文本分块的实现。
- `services/path_safety.py`：读取了输出根路径约束和相对路径校验。

### novel-analysis-agent

- README：确认其文档描述了结构化分析、mock、导出和质量检查思路。
- `src/novel_agent/analysis/chapter.py`：核对到结构化响应、分片合并和 evidence 字段。这些用于影响 HerLens 契约设计，但未导入其完整长篇聚合与报告系统。

## 复用决策

评估过的最小候选是 `file_parser.py` 的编码检测／纯文本规范化和 `chapter_splitter.py` 的标题判定。最终决定是**不复制上游函数**：

1. HerLens P0 的公开导入范围与上游 DOCX/PDF 管线不同，整段复用会过度引入依赖与攻击面。
2. HerLens 需要将规范化后 Unicode 码点偏移、段落 ID、内容哈希与证据失效做成同一契约。
3. 本仓库的 `tools/benchmark_text.py` 使用面向该契约的独立实现；没有复制上游正则、函数体或注释。

因此，当前 [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) 将两个项目列为“设计研究，未纳入源码”。未来如果复制或改编任何文件，必须在合并前改为文件级来源、保留上游 MIT 版权与许可文本，并补回归测试。

## 边界

- 上游根 LICENSE 不自动覆盖仓库外数据、第三方素材、模型输出或依赖。
- 锁定 commit 是可复核的核验点，不声称代表未来 `main` 的行为。
- 上游仅作工程与方法参考；HerLens 的女频八类规范、承诺—兑现证据链、同口径分析和受限研究工具是本项目自己的产品范围。
