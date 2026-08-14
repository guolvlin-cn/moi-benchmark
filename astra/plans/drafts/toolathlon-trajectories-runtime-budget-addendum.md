# Toolathlon 轨迹驱动的模型请求与运行时预算补充说明

## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: validate
- Origin Date: 2026-08-05
- Verification Status: ANALYZED
- Version Label: toolathlon_budget_addendum_v1.1
- Source: `/Users/chenyuwei/Documents/dataset/Toolathlon-Trajectories`
- Overall Confidence: CAUTION

> 文档用途：同步给协作同事的新增预算结论。  
> 关系说明：本文不修改 [Astra 与 Hermes：Toolathlon-Verified 评测执行方案](toolathlon-verified-astra-hermes-evaluation-plan.md)；如结论获批准，再由负责人将预算字段合入正式 freeze manifest。  
> 适用对象：Astra、Hermes；8 vCPU、8 GiB RAM Linux VM；`workers=1`。

## 0. 同步结论

基于本地 66 份 JSONL、7,116 条公开轨迹，建议新增冻结值：

| 冻结项 | 建议值 | 说明 |
| --- | ---: | --- |
| 公共 Agent 模型请求上限 | **100 次/任务/产品** | 所有任务和产品相同；统计所有产品侧 Agent LLM 请求 |
| 工具调用/工具轮次上限 | **不设置** | 只采集终态工具调用和失败调用，不作为终止条件 |
| R1 Agent 时限 | **30 分钟** | 历史可解析最大值不超过 10 分钟，且无时长删失 |
| R2 Agent 时限 | **45 分钟** | 历史可解析最大值为 10–20 分钟，且无时长删失 |
| R3 Agent 时限 | **60 分钟** | 历史可解析最大值为 20–30 分钟，且无时长删失 |
| R4 Agent 时限 | **90 分钟** | 历史最大值超过 30 分钟，或存在缺失/timeout 的右删失记录 |

核心决策：

1. **模型请求使用单一公共上限 100，不按任务分档。**公开轨迹的正值请求均值为 20.39、P95 为 51、P99 为 74；100 与原始公开轨迹的 `max_steps_under_single_turn_mode=100` 一致，便于保持预算口径可比。自然需求上界仍被 100 硬截断，因此达到上限必须作为有效产品终态单列。
2. **运行时长按任务分档，采用最大值向上留量。**可解析全局最大值为 2,376 秒（39.6 分钟），最高档给 90 分钟；含 timeout/缺失时间的任务直接进入 R4，避免把删失记录误当成短任务。
3. **不限制工具轮次。**时间和模型请求是公共终止条件；工具调用数量仅作为效率与失败诊断指标。
4. **分档时限只用于 Agent execution window。**计时从 Adapter 将冻结 Prompt 交给产品开始，到产品终态、Agent deadline 或模型请求上限为止。Preprocess、Gateway readiness、evaluator 和 cleanup 使用独立基础设施时限，不挤占 Agent 预算。
5. **达到 100 次请求或任务时限均属于有效产品结果。**Orchestrator 仍必须调用 evaluator；不得按基础设施错误自动重跑。

## 1. 数据审计

### 1.1 本地实际规模

本地 [README.md](</Users/chenyuwei/Documents/dataset/Toolathlon-Trajectories/README.md>) 写的是 17 个模型、51 个轨迹文件，但当前目录实际为：

| 项目 | 本地复算结果 |
| --- | ---: |
| JSONL 文件 | 66 |
| 模型 | 22 |
| 每模型运行数 | 3 |
| 理论记录 | 7,128 = 22 × 3 × 108 |
| 实际记录 | 7,116 |
| JSON 解析错误 | 0 |
| 唯一任务 ID | 108 |
| 可解析时长 | 6,995 |
| 带 `agent_llm_requests` 数值 | 6,997 |
| 正值模型请求记录 | 6,862 |
| 请求为 0 | 135 |
| 请求缺失 | 119 |

轨迹中的 108 个任务 ID 与冻结 Toolathlon commit `2aed2468858f15818acafa178518390cc4b0f5cb` 的正式任务清单完全一致，没有缺失或额外任务。任务实现与 evaluator 版本仍可能不同，因此这里只把旧轨迹用于预算先验，不把旧 evaluation 结果当作 Toolathlon-Verified 成绩。

### 1.2 时长字段与删失

本文使用：

```text
trajectory_duration
= completion_time - initial_run_time
```

它覆盖 Agent 轨迹中的模型推理、工具调用、网络等待和产品内重试。它不用于给 preprocess、Gateway 启动或 evaluator 分配时限。

运行状态为：

| `task_status.running` | 数量 | 时长可解析性 |
| --- | ---: | --- |
| `done` | 6,862 | 可解析 |
| `timeout` | 118 | 时长字段缺失，右删失 |
| `max_turn_exceeded` | 113 | 可解析，但请求计数写为 0 |
| `fail` | 20 | 可解析，但请求计数写为 0 |
| `running` | 1 | 异常/缺失 |
| `None` | 2 | 异常/缺失 |

因此，“133 条未完成记录的平均时长约 821 秒”实际只覆盖 113 条 `max_turn_exceeded` 和 20 条 `fail`；它不包含 118 条没有结束时间的 `timeout`。这些 timeout 是右删失数据，不能参与最大值计算，必须在分档时额外保护。

### 1.3 原始请求上限造成的删失

可解析配置中：

```text
max_turns = 50
max_steps_under_single_turn_mode = 100
single_turn_mode = true
```

以上组合出现 6,997 次。公开轨迹中 `agent_llm_requests` 的可见最大值恰好为 100，说明最大值受到原始配置上限约束。113 条 `max_turn_exceeded` 又把请求数保存为 0，所以不能把 100 解释为自然需求最大值。

## 2. 复算结果

### 2.1 总体时长

| 指标 | 秒 | 分钟 |
| --- | ---: | ---: |
| 平均值 | 300.7 | 5.01 |
| 中位数 | 184 | 3.07 |
| P75 | 374 | 6.23 |
| P90 | 692 | 11.53 |
| P95 | 992 | 16.53 |
| P99 | 1,846.1 | 30.77 |
| 最大值 | 2,376 | 39.60 |

Evaluator 通过记录平均 234.0 秒、P90 486 秒；evaluator 失败记录平均 308.3 秒、P90 719 秒。失败更慢是描述性关联，不能解释为“失败导致耗时增加”。

### 2.2 公共模型请求

原始总体均值 20.00 包含 135 个结构性零值，会低估请求需求。公共上限采用正值记录口径：

| 指标 | `agent_llm_requests` |
| --- | ---: |
| 有效正值记录 | 6,862 |
| 平均值 | 20.39 |
| 中位数 | 16 |
| P75 | 27 |
| P90 | 40 |
| P95 | 51 |
| P99 | 74 |
| 可见最大值 | 100（受到原始硬上限约束） |

100 的位置关系：

```text
100 / mean         = 4.90×
100 / P95          = 1.96×
100 / P99          = 1.35×
100 / observed max = 1.00×
```

因此冻结 100 可覆盖绝大多数公开轨迹，并与原始配置保持一致。它等于可见硬上限，不代表自然需求上界；达到 100 的运行应标记为 `max_model_requests`，不得推断任务本可在更多请求下完成或失败。

### 2.3 相关性

| 变量对 | Pearson r | 解释边界 |
| --- | ---: | --- |
| 时长 vs. Agent 模型请求 | 0.470 | 中等正相关；模型/API 延迟仍造成大量差异 |
| 时长 vs. 工具调用 | 0.393 | 较弱正相关，不支持设置统一工具上限 |
| 时长 vs. 总 Agent 轮数 | 0.520 | 中等正相关，不构成因果结论 |

不同公开模型的速度差距很大，而且当前轨迹没有 GLM-5.2。任务均值只用于排期先验；Astra/Hermes 的实际 ETA 必须由 14 题 smoke 更新。

## 3. 公共模型请求计数规则

### 3.1 计数定义

以下产品侧请求均计入公共 100 次上限：

- 为生成下一步 Agent 动作发起的主模型请求；
- 产品原生 planning、reflection、summary 或 recovery 使用的模型请求；
- 已发送但以 provider error、stream error 或 timeout 结束的请求；
- 产品内部自动重试产生的新请求。

以下不计入：

- Toolathlon preprocess、evaluator 或离线分析调用；
- MCP tool call；
- 不调用模型的本地规则、解析和日志逻辑。

Adapter 至少记录：

```text
model_request_id
request_started_at
request_finished_at
request_status
provider_request_id
retry_of
usage
```

当第 100 次请求结束后，或第 101 次请求准备发起时，Adapter 必须阻止新请求，终态记为 `max_model_requests`，随后进入 evaluator。不得通过隐式子进程或旁路 provider 绕开公共计数。

### 3.2 工具调用策略

- `tool_call_limit = null`；
- 不按任务难度设置工具轮次；
- 不因工具调用数量较高自动停止任务；
- 仍记录终态工具调用总数、失败调用数、中位数、P90 和 canonical tool 类型；
- 工具调用最终只受 Agent deadline、模型请求上限、产品权限和任务环境约束。

## 4. 分档时间预算

### 4.1 分类规则

先对每个任务汇总 22 个模型 × 3 次运行的可解析时长，再按该任务的历史最大值分档。任何缺失时长或 `timeout` 都视为右删失，直接进入 R4。

| 档位 | 数据规则 | Agent 时限 | 相对可见档位上界的余量 |
| --- | --- | ---: | ---: |
| R1 | 最大值 ≤ 10 分钟，且无时长缺失 | 30 分钟 | ≥3.0× |
| R2 | 10 < 最大值 ≤ 20 分钟，且无时长缺失 | 45 分钟 | ≥2.25× |
| R3 | 20 < 最大值 ≤ 30 分钟，且无时长缺失 | 60 分钟 | ≥2.0× |
| R4 | 最大值 > 30 分钟，或存在时长缺失/timeout | 90 分钟 | 全局可见最大值的 2.27×；同时覆盖删失不确定性 |

最终分布：

| 档位 | 任务数 | 每任务每产品时限 |
| --- | ---: | ---: |
| R1 | 8 | 30 分钟 |
| R2 | 15 | 45 分钟 |
| R3 | 11 | 60 分钟 |
| R4 | 74 | 90 分钟 |
| **合计** | **108** | — |

R4 数量较多并非 74 个任务的均值都很高，而是 56 个任务至少存在一条无法解析时长的记录，且部分任务的可见最大值已经超过 30 分钟。该规则有意偏宽松。

### 4.2 时钟与终态

```text
agent_started_at
= Adapter 把冻结 Prompt 交给产品、产品可开始模型或工具动作的时刻

agent_finished_at
= 产品完成、失败、崩溃、达到 100 次请求或达到分档 deadline 的时刻

agent_duration
= monotonic(agent_finished_at - agent_started_at)
```

- Agent deadline 是产品预算，产品/model/tool 卡住都消耗该预算；
- preprocess、Gateway readiness、evaluator 和 cleanup 使用独立 `infra_*_timeout`；
- Agent deadline 到期记为有效 `agent_timeout`，不是 `infra_invalid`；
- 无论何种 Agent 终态都必须运行 evaluator；
- 产品 timeout、模型 timeout 或达到请求上限不重跑；只有独立证据确认的公共基础设施无效才允许替代运行。

## 5. 14 题 smoke 的新增预算

| 顺序 | 任务 | 有效时长 n | 均值 | P95 | 可见最大值 | 缺失 | 档位 | Agent 时限 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | `find-alita-paper` | 66 | 1.1 min | 3.9 min | 6.6 min | 0 | R1 | 30 min |
| 2 | `set-conf-cr-ddl` | 66 | 0.9 min | 2.6 min | 4.2 min | 0 | R1 | 30 min |
| 3 | `course-schedule` | 66 | 4.1 min | 11.8 min | 13.9 min | 0 | R2 | 45 min |
| 4 | `canvas-homework-grader-python` | 66 | 5.2 min | 11.8 min | 35.1 min | 0 | R4 | 90 min |
| 5 | `arrange-workspace` | 66 | 3.7 min | 8.1 min | 38.1 min | 0 | R4 | 90 min |
| 6 | `notion-movies` | 65 | 3.9 min | 9.7 min | 34.9 min | 1 | R4 | 90 min |
| 7 | `price-comparison` | 66 | 2.7 min | 5.6 min | 32.1 min | 0 | R4 | 90 min |
| 8 | `quantitative-financial-analysis` | 62 | 10.4 min | 34.5 min | 37.6 min | 4 | R4 | 90 min |
| 9 | `excel-data-transformation` | 65 | 9.1 min | 18.7 min | 34.2 min | 1 | R4 | 90 min |
| 10 | `notion-hr` | 65 | 6.6 min | 17.1 min | 35.2 min | 1 | R4 | 90 min |
| 11 | `shopping-helper` | 65 | 4.5 min | 9.6 min | 29.1 min | 1 | R4 | 90 min |
| 12 | `woocommerce-stock-alert` | 66 | 5.0 min | 13.3 min | 30.8 min | 0 | R4 | 90 min |
| 13 | `git-bug-hunt` | 66 | 2.1 min | 6.6 min | 31.0 min | 0 | R4 | 90 min |
| 14 | `k8s-safety-audit` | 66 | 6.4 min | 21.7 min | 36.4 min | 0 | R4 | 90 min |

两个产品的 14 题 smoke：

- 按公开任务均值估算：约 **2.19 小时** Agent 时间；
- 按硬时限上界估算：约 **36.5 小时** Agent 时间；
- 两者差异来自宽松 timeout 和右删失保护，不应把 36.5 小时当作预计实际耗时。

## 6. 正式 108 题的运行量影响

| 口径 | 单个产品 | Astra + Hermes |
| --- | ---: | ---: |
| 按 108 个任务公开均值求和 | 9.09 h | 18.19 h |
| 按分档硬时限求和 | 137.25 h | 274.50 h |

以上只包含 Agent execution window。由于 `workers=1`，正式阶段的最坏 Agent 日历时间为 274.5 小时，约 11.44 天；preprocess、环境 reset、evaluator、cleanup 和人工排查另计。实际排期以 14 题 smoke 的 Astra/Hermes 端到端中位数和 P90 更新。

## 7. 全部任务分档

`缺失`表示 66 个模型-运行槽位中无法计算 `completion_time - initial_run_time` 的数量；只要大于 0，该任务进入 R4。

| 任务 | 有效时长 n | 均值 | P95 | 可见最大值 | 缺失 | 档位 | Agent 时限 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `ab-testing` | 66 | 6.3 min | 15.6 min | 29.3 min | 0 | R3 | 60 min |
| `academic-pdf-report` | 65 | 4.7 min | 10.9 min | 29.5 min | 1 | R4 | 90 min |
| `academic-warning` | 65 | 8.0 min | 20.4 min | 32.1 min | 1 | R4 | 90 min |
| `add-bibtex` | 66 | 5.1 min | 13.4 min | 22.6 min | 0 | R3 | 60 min |
| `apply-phd-email` | 66 | 3.8 min | 7.3 min | 36.9 min | 0 | R4 | 90 min |
| `arrange-workspace` | 66 | 3.7 min | 8.1 min | 38.1 min | 0 | R4 | 90 min |
| `canvas-arrange-exam` | 66 | 4.4 min | 9.0 min | 38.7 min | 0 | R4 | 90 min |
| `canvas-art-manager` | 62 | 8.5 min | 26.6 min | 32.1 min | 4 | R4 | 90 min |
| `canvas-art-quiz` | 66 | 1.6 min | 4.1 min | 10.4 min | 0 | R2 | 45 min |
| `canvas-do-quiz` | 66 | 5.1 min | 12.7 min | 29.9 min | 0 | R3 | 60 min |
| `canvas-homework-grader-python` | 66 | 5.2 min | 11.8 min | 35.1 min | 0 | R4 | 90 min |
| `canvas-list-test` | 64 | 5.1 min | 13.7 min | 22.1 min | 2 | R4 | 90 min |
| `canvas-new-students-notification` | 65 | 6.0 min | 13.2 min | 36.4 min | 1 | R4 | 90 min |
| `canvas-submit-late-work` | 66 | 4.4 min | 13.1 min | 33.9 min | 0 | R4 | 90 min |
| `cooking-guidance` | 65 | 4.6 min | 10.5 min | 32.0 min | 1 | R4 | 90 min |
| `course-assistant` | 66 | 1.6 min | 4.4 min | 10.7 min | 0 | R2 | 45 min |
| `course-schedule` | 66 | 4.1 min | 11.8 min | 13.9 min | 0 | R2 | 45 min |
| `courses-ta-hws` | 65 | 5.7 min | 16.8 min | 35.4 min | 1 | R4 | 90 min |
| `cvpr-research` | 65 | 4.1 min | 8.9 min | 29.1 min | 1 | R4 | 90 min |
| `dataset-license-issue` | 64 | 5.1 min | 13.7 min | 34.2 min | 2 | R4 | 90 min |
| `detect-revised-terms` | 65 | 5.8 min | 16.3 min | 20.4 min | 1 | R4 | 90 min |
| `dietary-health` | 66 | 3.7 min | 11.1 min | 19.6 min | 0 | R2 | 45 min |
| `email-paper-homepage` | 66 | 4.1 min | 11.7 min | 14.2 min | 0 | R2 | 45 min |
| `excel-data-transformation` | 65 | 9.1 min | 18.7 min | 34.2 min | 1 | R4 | 90 min |
| `excel-market-research` | 66 | 4.1 min | 13.7 min | 18.9 min | 0 | R2 | 45 min |
| `experiments-recordings` | 63 | 7.8 min | 23.4 min | 28.4 min | 3 | R4 | 90 min |
| `fillout-online-forms` | 64 | 5.0 min | 11.9 min | 34.9 min | 2 | R4 | 90 min |
| `filter-low-selling-products` | 64 | 8.3 min | 25.6 min | 30.4 min | 2 | R4 | 90 min |
| `find-alita-paper` | 66 | 1.1 min | 3.9 min | 6.6 min | 0 | R1 | 30 min |
| `flagged-transactions` | 66 | 7.5 min | 17.0 min | 35.0 min | 0 | R4 | 90 min |
| `game-statistics` | 66 | 2.5 min | 7.0 min | 17.7 min | 0 | R2 | 45 min |
| `gdp-cr5-analysis` | 65 | 5.7 min | 16.1 min | 24.5 min | 1 | R4 | 90 min |
| `git-bug-hunt` | 66 | 2.1 min | 6.6 min | 31.0 min | 0 | R4 | 90 min |
| `git-milestone` | 66 | 0.9 min | 2.1 min | 7.5 min | 0 | R1 | 30 min |
| `git-repo` | 66 | 1.2 min | 2.7 min | 4.7 min | 0 | R1 | 30 min |
| `hk-top-conf` | 62 | 7.6 min | 20.3 min | 36.9 min | 4 | R4 | 90 min |
| `huggingface-upload` | 62 | 9.0 min | 26.3 min | 32.0 min | 4 | R4 | 90 min |
| `identify-all-songs` | 65 | 3.5 min | 14.0 min | 19.6 min | 1 | R4 | 90 min |
| `imagenet` | 66 | 3.3 min | 8.3 min | 31.4 min | 0 | R4 | 90 min |
| `inter-final-performance-analysis` | 58 | 9.9 min | 27.9 min | 33.1 min | 8 | R4 | 90 min |
| `interview-report` | 65 | 7.6 min | 18.2 min | 36.8 min | 1 | R4 | 90 min |
| `inventory-sync` | 65 | 7.6 min | 22.6 min | 36.0 min | 1 | R4 | 90 min |
| `investment-decision-analysis` | 66 | 6.7 min | 17.8 min | 37.0 min | 0 | R4 | 90 min |
| `invoice-org` | 66 | 2.6 min | 6.2 min | 7.1 min | 0 | R1 | 30 min |
| `ipad-edu-price` | 65 | 4.2 min | 11.1 min | 31.5 min | 1 | R4 | 90 min |
| `k8s-deployment-cleanup` | 66 | 2.3 min | 5.4 min | 13.9 min | 0 | R2 | 45 min |
| `k8s-mysql` | 64 | 4.6 min | 11.9 min | 16.9 min | 2 | R4 | 90 min |
| `k8s-pr-preview-testing` | 63 | 7.5 min | 18.3 min | 29.4 min | 3 | R4 | 90 min |
| `k8s-redis-helm-upgrade` | 57 | 7.5 min | 20.6 min | 27.4 min | 9 | R4 | 90 min |
| `k8s-safety-audit` | 66 | 6.4 min | 21.7 min | 36.4 min | 0 | R4 | 90 min |
| `landing-task-reminder` | 60 | 6.9 min | 19.3 min | 23.7 min | 0 | R3 | 60 min |
| `language-school` | 64 | 9.3 min | 24.9 min | 37.4 min | 2 | R4 | 90 min |
| `latex-prompt-box` | 64 | 5.7 min | 18.2 min | 19.4 min | 2 | R4 | 90 min |
| `live-transactions` | 66 | 5.8 min | 19.2 min | 31.1 min | 0 | R4 | 90 min |
| `llm-training-dataset` | 66 | 3.8 min | 11.3 min | 23.6 min | 0 | R3 | 60 min |
| `logical-datasets-collection` | 66 | 2.6 min | 6.3 min | 32.1 min | 0 | R4 | 90 min |
| `machine-operating` | 65 | 6.0 min | 15.0 min | 38.9 min | 1 | R4 | 90 min |
| `meeting-assign` | 63 | 4.0 min | 15.8 min | 22.6 min | 3 | R4 | 90 min |
| `merge-hf-datasets` | 66 | 5.1 min | 16.1 min | 24.6 min | 0 | R3 | 60 min |
| `mrbeast-analysis` | 60 | 7.1 min | 17.4 min | 23.7 min | 6 | R4 | 90 min |
| `music-analysis` | 62 | 12.7 min | 26.2 min | 34.8 min | 4 | R4 | 90 min |
| `nhl-b2b-analysis` | 65 | 5.3 min | 10.7 min | 37.9 min | 1 | R4 | 90 min |
| `notion-find-job` | 65 | 3.0 min | 8.9 min | 17.6 min | 1 | R4 | 90 min |
| `notion-hr` | 65 | 6.6 min | 17.1 min | 35.2 min | 1 | R4 | 90 min |
| `notion-movies` | 65 | 3.9 min | 9.7 min | 34.9 min | 1 | R4 | 90 min |
| `notion-personal-website` | 66 | 3.5 min | 8.7 min | 13.2 min | 0 | R2 | 45 min |
| `nvidia-market` | 64 | 9.1 min | 22.7 min | 29.2 min | 2 | R4 | 90 min |
| `nvidia-stock-analysis` | 65 | 3.8 min | 9.0 min | 19.1 min | 1 | R4 | 90 min |
| `oil-price` | 64 | 8.5 min | 26.0 min | 37.8 min | 2 | R4 | 90 min |
| `paper-checker` | 65 | 6.3 min | 18.9 min | 34.3 min | 1 | R4 | 90 min |
| `payable-invoice-checker` | 65 | 4.2 min | 11.0 min | 21.0 min | 1 | R4 | 90 min |
| `personal-website-construct` | 66 | 6.5 min | 18.5 min | 26.2 min | 0 | R3 | 60 min |
| `ppt-analysis` | 66 | 2.6 min | 5.8 min | 17.2 min | 0 | R2 | 45 min |
| `price-comparison` | 66 | 2.7 min | 5.6 min | 32.1 min | 0 | R4 | 90 min |
| `privacy-desensitization` | 66 | 2.9 min | 7.4 min | 12.0 min | 0 | R2 | 45 min |
| `profile-update-online` | 65 | 4.2 min | 10.1 min | 14.2 min | 1 | R4 | 90 min |
| `quantitative-financial-analysis` | 62 | 10.4 min | 34.5 min | 37.6 min | 4 | R4 | 90 min |
| `reimbursement-form-filler` | 66 | 5.6 min | 16.1 min | 31.0 min | 0 | R4 | 90 min |
| `sales-accounting` | 66 | 1.2 min | 3.8 min | 6.5 min | 0 | R1 | 30 min |
| `search-ca-school` | 64 | 5.8 min | 18.4 min | 26.9 min | 2 | R4 | 90 min |
| `set-conf-cr-ddl` | 66 | 0.9 min | 2.6 min | 4.2 min | 0 | R1 | 30 min |
| `shopping-helper` | 65 | 4.5 min | 9.6 min | 29.1 min | 1 | R4 | 90 min |
| `sla-timeout-monitor` | 66 | 3.9 min | 9.5 min | 34.5 min | 0 | R4 | 90 min |
| `stock-build-position` | 66 | 3.6 min | 8.6 min | 12.3 min | 0 | R2 | 45 min |
| `student-interview` | 66 | 1.7 min | 4.5 min | 8.3 min | 0 | R1 | 30 min |
| `subway-planning` | 66 | 2.5 min | 6.3 min | 13.0 min | 0 | R2 | 45 min |
| `sync-todo-to-readme` | 65 | 3.7 min | 8.3 min | 33.2 min | 1 | R4 | 90 min |
| `task-tracker` | 62 | 9.3 min | 21.1 min | 29.6 min | 4 | R4 | 90 min |
| `train-ticket-plan` | 66 | 2.0 min | 4.1 min | 6.0 min | 0 | R1 | 30 min |
| `travel-exchange` | 66 | 3.9 min | 9.3 min | 15.8 min | 0 | R2 | 45 min |
| `travel-expense-reimbursement` | 62 | 10.5 min | 21.0 min | 39.2 min | 4 | R4 | 90 min |
| `trip-adviser` | 65 | 2.0 min | 5.6 min | 11.7 min | 1 | R4 | 90 min |
| `trip-itinerary-generator` | 59 | 4.2 min | 13.9 min | 27.4 min | 1 | R4 | 90 min |
| `university-course-selection` | 66 | 5.7 min | 14.7 min | 27.8 min | 0 | R3 | 60 min |
| `update-material-inventory` | 66 | 5.3 min | 18.2 min | 25.5 min | 0 | R3 | 60 min |
| `upenn-campus-route` | 65 | 3.4 min | 6.9 min | 35.0 min | 1 | R4 | 90 min |
| `verl-dataset` | 65 | 2.7 min | 7.9 min | 31.4 min | 1 | R4 | 90 min |
| `vlm-history-completer` | 64 | 7.2 min | 21.1 min | 32.1 min | 2 | R4 | 90 min |
| `wandb-best-score` | 66 | 2.8 min | 8.0 min | 12.2 min | 0 | R2 | 45 min |
| `wandb-shortest-length` | 65 | 4.1 min | 11.6 min | 25.8 min | 1 | R4 | 90 min |
| `woocommerce-customer-survey` | 66 | 4.6 min | 13.1 min | 33.3 min | 0 | R4 | 90 min |
| `woocommerce-new-product` | 65 | 5.2 min | 24.6 min | 39.6 min | 1 | R4 | 90 min |
| `woocommerce-new-welcome` | 65 | 5.6 min | 14.2 min | 32.3 min | 1 | R4 | 90 min |
| `woocommerce-product-recall` | 66 | 4.6 min | 11.8 min | 35.3 min | 0 | R4 | 90 min |
| `woocommerce-stock-alert` | 66 | 5.0 min | 13.3 min | 30.8 min | 0 | R4 | 90 min |
| `woocommerce-update-cover` | 66 | 3.0 min | 8.2 min | 28.7 min | 0 | R3 | 60 min |
| `yahoo-analysis` | 58 | 8.0 min | 20.8 min | 28.6 min | 8 | R4 | 90 min |
| `youtube-repo` | 66 | 3.9 min | 15.7 min | 27.9 min | 0 | R3 | 60 min |

## 8. Freeze manifest 新增字段

建议协作同事将以下结构写入后续机器可读 freeze 文件：

```json
{
  "budget_policy_version": "trajectory-budget-v1",
  "source_trajectory_dir": "/Users/chenyuwei/Documents/dataset/Toolathlon-Trajectories",
  "source_jsonl_files": 66,
  "source_records": 7116,
  "source_duration_records": 6995,
  "max_agent_model_requests": 100,
  "tool_call_limit": null,
  "timeout_scope": "agent_execution",
  "runtime_tiers_seconds": {
    "R1": 1800,
    "R2": 2700,
    "R3": 3600,
    "R4": 5400
  },
  "right_censored_task_policy": "R4",
  "task_runtime_tier_manifest": "task-runtime-tiers.json"
}
```

实际 freeze 还应补充 66 个 JSONL 的文件名、大小和 SHA-256 Manifest，避免 README 或 Hugging Face 目录后续更新造成预算来源漂移。

## 9. 统计风险扫描

- Coverage: **11/11 fallacy types checked**

| 风险 | 严重度 | 本次情况与处理 |
| --- | --- | --- |
| Simpson's Paradox | CAUTION | 模型速度差异很大；聚合均值可能掩盖模型内分布，因此 timeout 采用逐任务最大值与删失规则 |
| Ecological Fallacy | NOTE | 任务均值不能推出某次 Astra/Hermes 运行一定耗时相同 |
| Berkson's Paradox | CAUTION | 样本仅包含公开模型和已发布轨迹，不代表全部 Agent 产品 |
| Collider Bias | NOTE | 未通过加入控制变量建立回归结论，本次不适用 |
| Base Rate Neglect | NOTE | 未报告诊断灵敏度/特异度，本次不适用 |
| Regression to the Mean | NOTE | 无按极值选择后的前后测推断，本次不适用 |
| Survivorship Bias | CAUTION | 118 条 timeout 无时长，135 条请求为结构性零；已使用正值请求口径和 R4 删失保护 |
| Look-Elsewhere Effect | NOTE | 使用全部 108 个共享任务，没有按结果挑选任务 |
| Garden of Forking Paths | CAUTION | 30/45/60/90 档位是设计决策，必须在正式结果产生前预注册冻结 |
| Correlation ≠ Causation | CAUTION | 相关系数只描述共同变化，不声称更多请求或工具调用导致更长时延 |
| Reverse Causality | CAUTION | 更复杂/更慢的任务可能诱发更多请求，方向不能由观察轨迹确定 |

## 10. 可复现性与限制

- Method: 对当前目录全部 JSONL 独立逐行解析，反序列化 `task_status`、`config` 和 `key_stats`，使用 `completion_time - initial_run_time`；
- Result: 用户提供的 66 文件、22 模型、7,116 记录、6,995 个时长以及总体分位数均已复现；
- Verdict: **PARTIALLY_REPRODUCIBLE**；当前目录可复算，但尚未生成不可变文件哈希 Manifest；
- Version limitation: 这些轨迹来自原始 Toolathlon，不能验证 Toolathlon-Verified 的 evaluator 或任务修改；
- Model limitation: 轨迹中没有正式计划候选 GLM-5.2，Astra/Hermes 实际速度仍需 14 题 smoke 校准；
- Censoring limitation: 100 次请求硬上限和 118 条无结束时间 timeout 使自然上界不可观察；100 次是保持公开口径的预算决定，R4=90 分钟是保守时长预算，二者都不是自然需求上界的统计估计。
