# Toolathlon-Verified 13 Cases 阶段性结果分析

- 报告日期：2026-08-07
- 数据截止：2026-08-07 09:40:47 UTC（M2 位置 13 `git-bug-hunt` 配对门禁通过）
- 分析范围：M1 的 1 题正式复用结果 + M2 冻结顺序前 12 题，共 13 题、26 个有效系统槽
- 对比系统：Astra、Hermes
- 当前性质：运行中快照；不能替代完整 M2 或 Toolathlon-Verified 全集结论

## 1. 结论摘要

本批 13 题全部取得 Astra/Hermes 可配对的有效结果，26 个有效槽的 artifact gate 均通过。Astra `verify pass` 为 8/13（61.54%），Hermes 为 9/13（69.23%），Hermes 在当前样本上高 7.69 个百分点。13 个配对任务中，7 题双方均通过，1 题仅 Astra 通过，2 题仅 Hermes 通过，3 题双方均未通过。

Hermes 当前平均端到端任务时长为 4.23 分钟，Astra 为 9.13 分钟；Hermes 平均 Agent 执行时长为 2.78 分钟，Astra 为 8.26 分钟。Astra 的 1 个任务因达到 100 次模型请求上限而以 `max_steps` 结束，其余 25 个有效槽均正常到达 `completed`；两侧均无超时。上述差异仅描述当前按冻结顺序取得的单次运行，不应直接解释为系统总体能力或因果效率差异。

## 2. 样本与实验口径

### 2.1 13 题组成

| 来源 | 任务数 | 纳入范围 |
| --- | ---: | --- |
| M1 正式复用 | 1 | `find-alita-paper`；M1 qualification 为 GO，Astra/Hermes 均为有效 pass |
| M2 当前结果 | 12 | M2 冻结顺序位置 2—13，即前 12 个新增任务 |
| 合计 | 13 | 每题 Astra/Hermes 各 1 个有效槽，共 26 个有效槽 |

### 2.2 主要配置

| 配置项 | 当前口径 |
| --- | --- |
| Benchmark | Toolathlon-Verified |
| 系统 | Astra、Hermes，各使用自身原生产品栈 |
| 模型 | 运行别名 `deepseek-v4-flash`；冻结文档标识 `DeepSeek-V4-Flash-0731` |
| 配对控制 | 同一任务对使用相同冻结任务、容器与工具 schema；任务级 MCP Gateway |
| 并发与重复 | `workers=1`；每系统每任务保留 1 个正式有效结果 |
| 模型请求上限 | 每个任务 100 次 |
| 评测结果 | 任务专用 evaluator 输出二元 `pass` / `no_pass` |
| 时间 | 端到端时长为 `finished_at - started_at`；Agent 时长取 `agent_duration_seconds` |
| 工具调用 | 从 `run.json` trajectory 统计 started、terminal 与 failed 调用 |
| Token | 汇总 `model-usage.jsonl` 中 `model_request.completed` 事件 |

Hermes 的 `shopping-helper` 首次候选 A1 中断且不完整，调度器按预设规则生成 A2 替代运行；本报告只把有效 A2 纳入统计，CSV 同时保留 `attempt_ordinal=2`、`candidate_count=2` 和 `replacement_for_run_id`，以便审计。

## 3. 精度与配对结果

### 3.1 总体精度

| 指标 | Astra | Hermes |
| --- | ---: | ---: |
| 当前配对任务 | 13 | 13 |
| 有效结果 | 13 | 13 |
| Artifact gate 通过 | 13 | 13 |
| `verify pass` | 8 | 9 |
| Verifier 通过率 | 8/13（61.54%） | 9/13（69.23%） |
| 正常到达 `completed` | 12/13（92.31%） | 13/13（100.00%） |
| 超时 | 0 | 0 |

当前点估计中 Hermes 高 1 题，即 7.69 个百分点。样本只有 13 题、每个系统每题仅一次正式有效运行，且任务来自冻结顺序的前段而非随机抽样，因此本结果只用于阶段性方向判断，不给出显著性或总体优劣结论。

### 3.2 配对胜负矩阵

| 配对结果 | 任务数 | 占比 | 任务 |
| --- | ---: | ---: | --- |
| 双方均通过 | 7 | 53.85% | `find-alita-paper`、`set-conf-cr-ddl`、`canvas-homework-grader-python`、`price-comparison`、`excel-data-transformation`、`notion-hr`、`git-bug-hunt` |
| 仅 Astra 通过 | 1 | 7.69% | `course-schedule` |
| 仅 Hermes 通过 | 2 | 15.38% | `notion-movies`、`woocommerce-stock-alert` |
| 双方均未通过 | 3 | 23.08% | `arrange-workspace`、`quantitative-financial-analysis`、`shopping-helper` |

当前精度差主要来自两题 Hermes-only pass 与一题 Astra-only pass 的净差，而不是大量单边胜出。后续应优先复盘这 3 个不一致任务；双方共同 no-pass 的 3 题则适合检查任务难点、工具可用性和 evaluator 约束是否形成共同瓶颈。

### 3.3 逐题结果

| 位置 | 来源 | 任务 | Astra | Hermes | 配对判断 |
| ---: | --- | --- | --- | --- | --- |
| 1 | M1 复用 | `find-alita-paper` | pass | pass | 双方均通过 |
| 2 | M2 | `set-conf-cr-ddl` | pass | pass | 双方均通过 |
| 3 | M2 | `course-schedule` | pass | no_pass | 仅 Astra 通过 |
| 4 | M2 | `canvas-homework-grader-python` | pass | pass | 双方均通过 |
| 5 | M2 | `arrange-workspace` | no_pass | no_pass | 双方均未通过 |
| 6 | M2 | `notion-movies` | no_pass | pass | 仅 Hermes 通过 |
| 7 | M2 | `price-comparison` | pass | pass | 双方均通过 |
| 8 | M2 | `quantitative-financial-analysis` | no_pass | no_pass | 双方均未通过 |
| 9 | M2 | `excel-data-transformation` | pass | pass | 双方均通过 |
| 10 | M2 | `notion-hr` | pass | pass | 双方均通过 |
| 11 | M2 | `shopping-helper` | no_pass / max_steps | no_pass | 双方均未通过 |
| 12 | M2 | `woocommerce-stock-alert` | no_pass | pass | 仅 Hermes 通过 |
| 13 | M2 | `git-bug-hunt` | pass | pass | 双方均通过 |

## 4. 失败与终止状态

| 主要类别 | Astra | Hermes | 说明 |
| --- | ---: | ---: | --- |
| `none` | 8 | 9 | Verifier 通过 |
| `completed_but_no_pass` | 4 | 4 | 产品运行正常结束，但 evaluator 为 no_pass |
| `model_request_budget` | 1 | 0 | Astra `shopping-helper` 达到 100 次模型请求上限，终止原因为 `max_model_requests` |
| timeout | 0 | 0 | 当前样本无超时 |

Astra 的 4 个 `completed_but_no_pass` 为 `arrange-workspace`、`notion-movies`、`quantitative-financial-analysis`、`woocommerce-stock-alert`；Hermes 的 4 个为 `course-schedule`、`arrange-workspace`、`quantitative-financial-analysis`、`shopping-helper`。多数 `eval_res.json` 只给出二元 no_pass，没有足够的结构化失败细节，因此此处不进一步臆测任务级根因；根因分析需要结合 trajectory、工具返回和任务专用 evaluator 条件逐题复盘。

## 5. 时间效率

| 指标 | Astra | Hermes |
| --- | ---: | ---: |
| 端到端总时长 | 118.66 分钟 | 54.99 分钟 |
| 平均任务时长 | 9.13 分钟 | 4.23 分钟 |
| 任务时长中位数 | 7.16 分钟 | 3.80 分钟 |
| Agent 执行总时长 | 107.44 分钟 | 36.09 分钟 |
| 平均 Agent 执行时长 | 8.26 分钟 | 2.78 分钟 |
| Verify-pass 任务平均时长 | 9.21 分钟 | 3.71 分钟 |
| Verify-pass 任务平均 Agent 时长 | 8.62 分钟 | 2.59 分钟 |

Astra 的均值受到 `notion-hr`（端到端约 30.57 分钟）和达到请求上限的 `shopping-helper`（约 21.83 分钟）明显影响，因此同时报告中位数。为减弱通过任务构成不同的影响，在双方共同通过的 7 题上，Astra 平均端到端时长为 9.99 分钟、Hermes 为 3.77 分钟；平均 Agent 时长分别为 9.37 和 2.74 分钟。由于两者使用不同原生产品栈，该比较仍是观测性结果。

## 6. 模型请求与工具调用

| 指标 | Astra | Hermes |
| --- | ---: | ---: |
| 模型请求总数 | 399 | 187 |
| 平均每任务模型请求 | 30.69 | 14.38 |
| 模型请求失败数 | 1 | 2 |
| 模型请求失败率 | 1/399（0.25%） | 2/187（1.07%） |
| 工具调用总数（terminal） | 281 | 271 |
| 平均每任务工具调用 | 21.62 | 20.85 |
| 工具调用失败数 | 3 | 0 |
| 工具调用失败率 | 3/281（1.07%） | 0/271（0.00%） |

Astra 的 3 次失败工具调用均出现在 M1 `find-alita-paper`，但该任务最终 verifier 通过。模型请求失败率和工具失败率均按“失败数 / 对应调用总数”计算；调用失败并不等于任务失败，系统可能在后续步骤恢复。

## 7. Token 资源消耗

### 7.1 全部 13 题

| 指标 | Astra | Hermes |
| --- | ---: | ---: |
| 输入 token 总量 | 9,419,882 | 10,074,709 |
| 输出 token 总量 | 595,582 | 146,461 |
| 缓存命中 token 总量 | 7,766,656 | 8,732,800 |
| 总 token（输入 + 输出） | 10,015,464 | 10,221,170 |
| 平均每任务输入 token | 724,606 | 774,978 |
| 平均每任务输出 token | 45,814 | 11,266 |
| 平均每任务缓存命中 token | 597,435 | 671,754 |
| 平均每任务总 token | 770,420 | 786,244 |

### 7.2 Verify-pass 任务

| 指标 | Astra（8 题） | Hermes（9 题） |
| --- | ---: | ---: |
| 输入 token 总量 | 5,390,154 | 5,707,667 |
| 输出 token 总量 | 375,232 | 94,369 |
| 缓存命中 token 总量 | 4,473,728 | 4,774,016 |
| 总 token（输入 + 输出） | 5,765,386 | 5,802,036 |
| 平均每个 pass 任务输入 token | 673,769 | 634,185 |
| 平均每个 pass 任务输出 token | 46,904 | 10,485 |
| 平均每个 pass 任务缓存命中 token | 559,216 | 530,446 |
| 平均每个 pass 任务总 token | 720,673 | 644,671 |

输入 token 已包含缓存命中部分，因此总 token 按“输入 + 输出”计算，不能再把缓存命中 token 重复相加。当前两侧全部任务的总 token 接近，但构成明显不同：Astra 输出 token 更多，Hermes 输入与缓存命中 token 更多。由于 pass 任务集合并不完全相同，Verify-pass 子集适合描述各自成功任务的资源消耗，不是严格同题比较。

在双方共同通过的 7 题上，Astra/Hermes 的总 token 分别为 5,444,744 和 4,194,092，平均每题约 777,821 和 599,156；这组同题数据可作为后续效率复盘入口，但仍需结合不同系统栈和上下文组织方式解释。

## 8. 数据质量、限制与后续分析

1. 当前 13 题为冻结顺序前段的阶段性样本，不是随机抽样，也不是完整 Toolathlon-Verified 全集。
2. 每个系统每题只有一次正式有效运行，当前无法估计运行方差或稳定性。
3. M2 批次在本报告截止时仍继续运行；本报告只冻结到位置 13 的配对门禁结果，不纳入位置 14 及之后数据。
4. 任务通过率应以 task-specific verifier 为准；正常完成、调用无失败或输出看似完整都不能替代 verifier pass。
5. 下一步优先逐题复盘 3 个配对分歧任务与 3 个双方 no-pass 任务，并在 M2 全部预定任务完成后重新生成同口径汇总、置信区间和失败类型分布。

## 9. 明细与证据索引

- [26 个有效槽明细 CSV](toolathlon-verified-13cases-current-results.csv)
- [M1 qualification](../../results/toolathlon-minimal-e2e-tool-events-v10/m1-live-qualification.json)
- [M2 batch manifest](../../results/toolathlon-m2-first-batch-v4/m2-batch-manifest.json)
- [M2 checkpoint](../../results/toolathlon-m2-first-batch-v4/checkpoint.json)
- [M2 scheduler events](../../results/toolathlon-m2-first-batch-v4/scheduler-events.jsonl)
- [模型冻结配置](../../benchmark/toolathlon-verified/freeze/model.freeze.json)
- [执行协议冻结配置](../../benchmark/toolathlon-verified/freeze/execution-protocol.freeze.json)

CSV 是本报告表格的可审计明细层：每行对应一个系统在一个任务上的有效槽，保留 run ID、候选替换关系、门禁状态、终止状态、verifier、时长、模型请求、工具调用、token 和 run directory。
