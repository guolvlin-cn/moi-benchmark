# 文档与研究资料索引

`docs/` 保存 MOI RAG Benchmark 的设计依据、执行计划、研究结论和论文资料。它是项目的决策与追溯层，不是运行时输入，也不承载最终实验分数；最终结果请看 [`results/`](../results/)。

## 目录总览

| 目录 | 作用 | 主要内容 |
|---|---|---|
| [`metrics/`](metrics/) | 指标与评测口径 | Benchmark 设计问题、指标框架、分母/有效性规则、原始字段和发布前检查 |
| [`plans/`](plans/) | 计划与执行拆解 | v0.1–v1.0 母计划、执行 TODO、阶段计划、运行计划和检查点 |
| [`refs/`](refs/) | 外部资料与证据缓存 | 论文 PDF、中文翻译、阅读笔记、数据集/许可/API 调研；当前默认不纳入 Git |
| [`research/`](research/) | 研究与实现分析 | 官方产品证据、数据集演进、竞品本地流程、MOI 方案和实现调研 |

## 各目录怎么用

### `metrics/`：指标和结果口径

这里回答“测什么、怎么算、什么情况下有效、结果如何解释”。适合在写 adapter、运行评测或核对报告前阅读。

- [`benchmark-design-questions.md`](metrics/benchmark-design-questions.md)：Benchmark 必须回答的范围、对象、Gold、可比性、Judge 和发布问题。
- [`moi-rag-benchmark-metrics-framework-v2-2026-08-10.md`](metrics/moi-rag-benchmark-metrics-framework-v2-2026-08-10.md)：指标框架和分层评测设计。
- [`moi-rag-benchmark-metrics-assessment-2026-08-10.md`](metrics/moi-rag-benchmark-metrics-assessment-2026-08-10.md)：当前指标的适用性、缺口和记录建议。
- `research-notes.md`：指标相关的补充研究笔记。

这里的文档是口径和设计依据；逐题结果、聚合数值和最终报告分别在 [`results/metrics/`](../results/metrics/) 和 [`results/reports/`](../results/reports/)。

### `plans/`：版本计划、TODO 和执行证据

这里记录“准备做什么、按什么 Gate 做、完成需要留下什么证据”。同一版本内，母计划优先于子 TODO；历史计划不应被当作当前运行状态。

- `plans/v1.0.md`：v1.0 母计划和当前版本的范围、阶段与验收边界。
- `plans/v1.0-todos/`：v1.0 的五个执行工作包，负责把母计划拆成数据/Gold、平台 adapter、诊断性能和验收任务；具体规则见其 [`README.md`](plans/v1.0-todos/README.md)。
- `plans/checkpoints/`：按日期保存的运行/评测检查点，记录当时已运行内容、失败、阻塞和证据入口；用于回溯，不覆盖新的 canonical 结果。
- `plans/drafts/`：v0.1–v0.4 等历史版本的草案及执行拆解。草案只有在被当前母计划引用后才具有执行效力；其中的 `v0.3-todos/`、`v0.4-todos/` 各自有导航 README。
- `plans/todo/`：跨版本待办和未来设计任务，例如 Gold/metrics 规范、benchmark catalog、竞品格局和阶段计划；它是 backlog，不等于已承诺的运行范围。
- `plans/TODO.md`：计划层的总入口和未归档事项索引。

### `refs/`：外部论文和调研原材料

这里保存研究时下载或整理的外部资料，方便核对数据集定义、论文指标、许可和官方 API。它不是程序依赖，也不是结果来源的唯一记录；结果仍需在 manifest 或 `sources.json` 中留下可追溯信息。

- `refs/` 根目录的 Markdown：数据集 shortlist、商业使用审查、MOI API/上传方式和其他外部调研记录。
- `refs/papers/original/`：数据集与 benchmark 的原始论文 PDF，以及 16 篇 MOI 数据集论文的 canonical 索引。
- `refs/papers/TRANS/`：对应论文的中文翻译版 PDF，便于内部阅读，不替代原文引用。
- `refs/papers/notes/`：逐篇阅读笔记、指标摘录、数据边界和对 MOI 的评估价值分析。
- `refs/papers/o1/`：早期通用 RAG benchmark、诊断框架和中文 RAG 扩展论文包，保留其独立的研究索引。

当前 `.gitignore` 包含 `docs/refs/`，所以这些 PDF 和本地资料默认只保留在工作机；需要对外归档时应单独打包，或先明确调整忽略策略。

### `research/`：研究结论和实现分析

这里放已经形成文档的调研与方案分析，连接外部证据和仓库实现，例如：

- 官方产品身份、能力、API、引用/trace 和本地部署证据；
- Dify、FastGPT、RAGFlow、MaxKB 的本地 RAG 流程与 benchmark adapter 设计；
- MOI 数据集演进、语料入库、评测范围和竞品比较边界；
- 具体数据集或评测框架的来源审查和实现建议。

研究文档用于支持计划和实现决策；如果结论改变了 schema、指标、分母、Gate 或发布口径，应同步更新对应母计划和结果说明，而不是只修改研究报告。

## 推荐阅读顺序

1. 先按当前版本阅读 [`plans/v1.0.md`](plans/v1.0.md) 和 [`plans/v1.0-todos/README.md`](plans/v1.0-todos/README.md)。
2. 再阅读 [`metrics/benchmark-design-questions.md`](metrics/benchmark-design-questions.md) 和指标框架，确认评测对象、指标与分母。
3. 需要外部依据时查 [`research/`](research/)；需要原论文时查 [`refs/papers/`](refs/papers/)。
4. 运行完成后，以 [`results/README.md`](../results/README.md) 和 [`results/metrics/README.md`](../results/metrics/README.md) 为结果归档入口。

## 更新规则

- 历史 checkpoint、研究结论和已发布结果不覆盖；新增内容使用日期或 run 标识。
- 新的指标、阈值、Gold、denominator、valid/invalid 或 Gate 规则先更新母计划/规范，再同步 TODO 和报告。
- 研究资料与运行产物分开保存：原始运行数据在 `runs/`/`outputs/`，canonical 结果在 `results/`，本目录只保存设计、证据和解释。
