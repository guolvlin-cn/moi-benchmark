# Astra 与 Hermes：Toolathlon 108 题正式结果对比

生成日期：2026-08-12
数据范围：Toolathlon 第 1–108 题，每题各包含 Astra、Hermes 一个正式有效结果。

## 口径

- `pass` 表示 evaluator 通过；`no-pass` 表示有效运行已有 evaluator 结果但未通过。最终投影中没有 `unavailable`、`infra_invalid` 或缺失 slot。
- “正常端到端成功”沿用 TerminalBench2.1 报告口径：`verify pass` 且无 timeout。
- 端到端时间由 `finished_at - started_at` 计算；Agent 和 evaluator 时间直接取 `run.json`。`orchestration` 是端到端减去 Agent 和 evaluator 的剩余时间，包含准备、adapter 收尾及 post-terminal model drain，不能单独解释为纯环境准备时间。
- 工具调用采用 `run.json.trajectory.tool_terminal_events`；失败工具采用 `tool_failed_events`。
- Token 只统计 `model_request.completed` 中 provider 明确上报的 input/output/total。若一个 effective run 存在缺失 usage 的 completed response，则该 run 不进入保守 token 汇总。Token 是产品整体架构足迹，不代表单次推理成本或单位任务效率。
- “可见 token 下界”则汇总全部任务中所有已经明确上报的 usage；缺 usage 的请求保持未知，不推算也不补零。因此它覆盖全部 108 题，但只是实际 token 总量的最低可确认值。
- “排除 Astra 内部非流式请求”采用可直接从代理日志复核的规则：Astra `model_request.started` 同时满足 `stream=false` 且 `request_tool_count=0`，再按 `model_request_id` 排除其对应 completed usage。Hermes 侧仍统计完整 provider usage。

## 实验产品与配置

| 项目 | Astra | Hermes |
| --- | --- | --- |
| 产品版本 | Linux/AMD64 release build；源码 `v0.0.5-4-g844473c68`，commit `844473c68649d8ea43e10b616dc4fbf98e2321e8`；CLI 输出 `astra 0.1.0` | release descriptor `v2026.7.20-63-gf4df260f2`，commit `f4df260f26c93f15694698869f3ea8e965eea301`，project version `0.19.0` |
| API 模型 ID | `deepseek-v4-flash` | `deepseek-v4-flash` |
| 模型版本口径 | DeepSeek-V4-Flash-0731 | DeepSeek-V4-Flash-0731 |
| 模型提供方 | DeepSeek 官方 API，经每次运行独立的本地代理 | 同左 |
| 推理配置 | Thinking enabled；`reasoning_effort=max` | 同左 |
| Temperature | 发送 `temperature=0`；DeepSeek Thinking 模式下该参数不生效 | 同左 |
| 产品原生 max turns | Astra 冻结默认值 `300` | Hermes 冻结默认值 `90` |
| 外部统一请求预算 | 每题最多 100 次 product model request；允许第 100 次，拒绝第 101 次 | 同左 |
| 实际最高模型请求数 | 100 | 100 |
| Agent deadline | 按任务采用 R1/R2/R3/R4：1800/2700/3600/5400 秒 | 同左 |
| Prompt 口径 | 保留 Astra 原生 system prompt，并输入 Toolathlon 公共 system/task 指令 | 保留 Hermes 原生 system prompt，并输入相同公共指令 |
| 工具范围 | 保留产品内置工具；提供当前任务的 MCP 工具 | 保留产品内置工具；提供当前任务的 MCP 工具 |

Astra 与 Hermes 的内部“turn”并非同构指标。本实验以运行代理观测到的 `model_request.started` 作为统一请求预算和 step 统计，不把产品原生 max turns 或模型请求数直接解释为用户可见对话回合。

## 基础运行环境

| 环境项 | 配置 |
| --- | --- |
| 数据集 | Toolathlon，固定 108 题；Astra/Hermes 每题各有一个正式有效结果 |
| Host OS | Ubuntu 22.04.5 LTS，Linux `5.15.0-186-generic`，UTC |
| CPU | Intel Xeon Platinum 8255C @ 2.50 GHz，x86_64，8 vCPU |
| 内存与 Swap | Linux MemTotal 7.75 GiB（名义配置 8 GiB）；8 GiB swap，swappiness 10，关闭 zram |
| 虚拟化 | Oracle/Vagrant 虚拟机 |
| 容器运行时 | rootful Docker Engine 29.1.3，cgroup v2，systemd cgroup driver，overlayfs |
| 任务镜像 | `lockon0927/toolathlon-task-image@sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f` |
| 单任务资源上限 | 8 CPU、8 GiB RAM、8 GiB swap |
| Kubernetes 工具 | Kind v0.20.0；kubectl v1.34.1 |
| 外部应用状态 | 由任务 preprocess 恢复；Canvas、WooCommerce、Poste、MatrixOne 和 Kind 等使用共享部署，并非每题重新部署整套服务 |
| 网络边界 | 未统一关闭公开互联网出口；任务级 MCP 限于当前任务，但终端、fetch、浏览器或产品内置工具仍可能访问公开网络 |
| Evaluator | 使用 Toolathlon 每题原生 evaluator，在 Agent 终止后独立执行 |

这里记录的是实验冻结时的环境；实验结束后宿主机内核或服务状态的变化不追溯修改历史运行口径。

## 任务完成结果

| 指标                                |            Astra |           Hermes |
| ----------------------------------- | ---------------: | ---------------: |
| 正式任务数                          |              108 |              108 |
| verify pass                         |               61 |               72 |
| no-pass                             |               47 |               36 |
| unavailable / invalid               |                0 |                0 |
| verify pass rate                    | **56.48%** | **66.67%** |
| 正常端到端成功（pass 且无 timeout） |               61 |               72 |
| timeout                             |                0 |                0 |

Hermes 的绝对通过数比 Astra 多 11 题，通过率高 **10.19 个百分点**。配对结果为：

| 配对结果       | 题数 |
| -------------- | ---: |
| 双方均通过     |   51 |
| 仅 Astra 通过  |   10 |
| 仅 Hermes 通过 |   21 |
| 双方均未通过   |   26 |

仅看 31 个结果不一致的配对，Hermes 独过 21 题、Astra 独过 10 题。作为补充描述，精确双侧 McNemar/binomial 检验 `p=0.0708`；在常用 0.05 阈值下不能据此宣称差异具有统计显著性。这里的 108 题是固定 benchmark 全集，不是从更大任务总体随机抽样，因此通过率和逐题差异仍是主要结论。

### 仅一方通过的任务

仅 Astra 通过（10）：

`course-schedule`、`k8s-safety-audit`、`add-bibtex`、`email-paper-homepage`、`imagenet`、`k8s-deployment-cleanup`、`search-ca-school`、`upenn-campus-route`、`verl-dataset`、`yahoo-analysis`。

仅 Hermes 通过（21）：

`notion-movies`、`woocommerce-stock-alert`、`canvas-art-manager`、`canvas-do-quiz`、`canvas-list-test`、`cooking-guidance`、`cvpr-research`、`dataset-license-issue`、`fillout-online-forms`、`filter-low-selling-products`、`identify-all-songs`、`inter-final-performance-analysis`、`ipad-edu-price`、`k8s-mysql`、`k8s-pr-preview-testing`、`profile-update-online`、`reimbursement-form-filler`、`stock-build-position`、`wandb-best-score`、`woocommerce-new-product`、`woocommerce-new-welcome`。

## No-pass 原因

| 主要原因                     | Astra | 占 Astra no-pass | Hermes | 占 Hermes no-pass |
| ---------------------------- | ----: | ---------------: | -----: | ----------------: |
| 任务完成但 evaluator 未通过  |    27 |           57.45% |     33 |            91.67% |
| 达到模型请求预算，未完成任务 |    20 |           42.55% |      3 |             8.33% |
| 合计                         |    47 |             100% |     36 |              100% |

最终正式结果已不再包含 adapter/infra invalid 或 evaluator unavailable。Astra 的 no-pass 中有 20 题由 100 次模型请求预算终止，是其失败的显著组成；Hermes 对应只有 3 题。其余失败均是有效端到端运行结束后 evaluator 未通过，更接近最终产物或任务执行能力问题。

## 时间消耗

| 阶段               | 产品   |      总计 |      平均 |    中位数 |       P90 |
| ------------------ | ------ | --------: | --------: | --------: | --------: |
| 端到端             | Astra  |   34.18 h | 18.99 min | 10.16 min | 50.01 min |
| 端到端             | Hermes |   17.58 h |  9.77 min |  7.10 min | 19.63 min |
| Agent 执行         | Astra  |   32.69 h | 18.16 min |  9.10 min | 49.26 min |
| Agent 执行         | Hermes |   14.21 h |  7.89 min |  5.21 min | 16.93 min |
| Evaluator          | Astra  | 36.26 min |   20.15 s |   12.68 s |   38.53 s |
| Evaluator          | Hermes | 36.21 min |   20.12 s |   11.40 s |   32.76 s |
| Orchestration/收尾 | Astra  | 52.94 min |   29.41 s |   27.96 s |   40.95 s |
| Orchestration/收尾 | Hermes |    2.77 h |   92.36 s |  101.83 s |  142.75 s |

同一任务配对计算，Astra 相对 Hermes：

- 端到端时间中位差：**+2.99 分钟**。
- Agent 执行时间中位差：**+3.71 分钟**。

Astra 总端到端时间比 Hermes 多 16.60 小时，主要来自 Agent 执行时间。

## 工具调用

| 指标             | Astra | Hermes |
| ---------------- | ----: | -----: |
| 有工具计数的任务 |   108 |    108 |
| 工具调用总数     | 4,345 |  4,848 |
| 单任务平均       | 40.23 |  44.89 |
| 单任务中位数     |  31.5 |   32.5 |
| 单任务 P90       |  75.6 |   78.6 |
| 失败工具事件总数 |    56 |      0 |

同任务配对的工具调用数中位差（Astra − Hermes）为 **−2**。总体工具调用工作负担接近，Hermes 总量多 503 次。失败工具事件不能直接横向解释：Hermes adapter 在本批 effective run 中没有把工具终态归类为 failed，而这不等于其所有工具在语义上都成功。

常见终态工具：

- Astra：`local-python-execute` 464、`terminal-run_command` 234、`woocommerce-woo_products_list` 172、`wandb-query_wandb_tool` 153、`word-add_paragraph` 151。
- Hermes：`terminal` 754、`word-add_paragraph` 392、`local-python-execute` 288、`terminal-run_command` 232、`emails-send_email` 129。

由于 Hermes 的本地 `terminal` 与 task MCP `terminal-run_command` 是两种封装，而 Astra 又有自己的内置工具和内部 loop，按工具名称逐项比较不代表完全相同的能力边界。

## 模型请求

| 指标                     |           Astra |          Hermes |
| ------------------------ | --------------: | --------------: |
| 模型请求 started         |           5,229 |           3,287 |
| 模型请求 completed event |           5,229 |           3,284 |
| 单任务 started 平均      |           48.42 |           30.44 |
| 单任务 started 中位数    |            33.5 |              20 |
| 单任务 started P90       |             100 |            66.5 |
| 达到 100 请求上限的任务  |              23 |               3 |
| 因请求预算 no-pass       |              20 |               3 |
| 流式请求                 | 2,226（42.57%） | 3,081（93.73%） |
| 非流式请求               | 3,003（57.43%） |    206（6.27%） |

Astra 比 Hermes 多发出 1,942 个模型请求，总量高 59.08%；单任务中位数高 13.5 次。Astra 23 题触及 100 次请求上限，其中 20 题最终因模型请求预算 no-pass；另外 3 题在第 100 次附近完成并通过。

请求分布也反映两种架构差异：Astra 大量内部无工具、非流式请求与对外 agent response 请求共同出现；Hermes 以携带工具 schema 的流式主循环请求为主。因此请求数不能等同于用户可见轮数，也不能单凭请求数判断模型效率。

## Token 数据

### 保守覆盖与总体足迹

| 指标                |              Astra |             Hermes |
| ------------------- | -----------------: | -----------------: |
| 保守可靠 token 记录 | 95 / 108（87.96%） | 82 / 108（75.93%） |
| 输入 token 总量     |        114,783,243 |        142,142,325 |
| 输出 token 总量     |          8,791,196 |          1,964,613 |
| total token 总量    |        123,574,439 |        144,106,938 |
| 单任务输入中位数    |            617,205 |          1,147,115 |
| 单任务输出中位数    |             40,868 |             19,696 |
| 单任务 total 中位数 |            649,739 |          1,174,439 |

总量只覆盖各自可靠记录，覆盖数不同，不能将总量差直接解释为产品差异。两边又有明显不同的请求形态：Hermes 主请求通常携带较大的工具 schema 和累积上下文；Astra 许多内部请求不携带 provider tool schema，但请求次数更多、输出 token 更多。因此：

- Hermes 的可靠记录中 input token 中位数更高。
- Astra 的可靠记录中 output token 中位数更高。
- 这描述的是完整 agent 架构在代理层可见的 token 足迹，而非相同 prompt 下的模型效率。

### 全部任务的可见 token 下界

保守完整口径会整题排除 token 不完整的 case；下界口径保留这些 case 中已经可见的 usage。108 题均至少有一个请求明确上报 token，因此两侧覆盖都是 108/108：

| 统计边界                 | 任务数 | 已上报 / 缺 usage 的 completed 请求 | 输入 token 下界 | 输出 token 下界 | total token 下界 |
| ------------------------ | -----: | ----------------------------------: | --------------: | --------------: | ---------------: |
| Astra 完整架构           |    108 |                          5,210 / 19 |     149,741,746 |      11,654,317 |      161,396,063 |
| Astra 排除内部非流式请求 |    108 |                           2,219 / 8 |     140,643,034 |       5,226,429 |      145,869,463 |
| Hermes 完整架构          |    108 |                          3,256 / 28 |     244,960,861 |       3,124,778 |      248,085,639 |

按可见下界，Astra 完整架构的 total 比 Hermes 完整架构低 34.94%；排除 Astra 内部非流式请求后低 41.20%。但这两个百分比不能作为精确 token 差异：Astra 仍有 19 次、Hermes 仍有 28 次 completed 请求没有 usage，未知 token 可能使真实差距发生变化。

作为附加数据，所有 pass 任务的可见 total 下界为 Astra 54,953,969（61 题）、过滤后 Astra 50,294,805（61 题）、Hermes 142,497,968（72 题）。由于 pass 题数量和题目集合不同，不直接用这些总量计算产品效率差。

### Pass 任务 token

| 指标                         |                      Astra |                         Hermes |
| ---------------------------- | -------------------------: | -----------------------------: |
| pass 任务                    |                         61 |                             72 |
| 有可靠 token 的 pass 任务    |                         56 |                             54 |
| pass token 覆盖率            |                     91.80% |                         75.00% |
| pass 输入 token 总量         |                 41,163,279 |                     87,554,219 |
| pass 输出 token 总量         |                  2,841,207 |                      1,139,527 |
| pass total token 总量        |                 44,004,486 |                     88,693,746 |
| pass 平均输入 / 输出 / total | 735,059 / 50,736 / 785,794 | 1,621,374 / 21,102 / 1,642,477 |
| pass total 中位数            |                    518,071 |                      1,045,431 |

双方均 pass 且两侧 token 都可靠的重叠任务有 36 个。在这 36 个相同任务上：

| 产品   |    平均输入 / 输出 / total | total 中位数 |
| ------ | -------------------------: | -----------: |
| Astra  | 615,564 / 43,379 / 658,943 |      437,022 |
| Hermes | 857,039 / 14,597 / 871,636 |      645,930 |

配对后 Astra 的可见 total token 仍较低，但上述工具 schema、内部请求结构、上下文组织和 cache 计量差异仍然存在，所以不应将该差值直接表述为 token 效率提升比例。

### 排除 Astra 内部非流式请求后

Astra 的 5,229 个 started 请求中，3,002 个满足 `stream=false && request_tool_count=0`，过滤后保留 2,227 个。这里没有直接排除全部非流式请求：第 77 题 `personal-website-construct` 有 1 个 `stream=false` 但携带 117 个工具的请求，按规则保留。

先在原先 95 个 Astra 完整 token 均可靠的相同记录上观察过滤本身的影响，避免样本覆盖变化干扰：

| Astra（同一批 95 题） |      过滤前 |     排除量 | 排除比例 |
| --------------------- | ----------: | ---------: | -------: |
| 输入 token            | 114,783,243 |  6,981,242 |    6.08% |
| 输出 token            |   8,791,196 |  4,882,441 |   55.54% |
| total token           | 123,574,439 | 11,863,683 |    9.60% |

内部非流式请求对 Astra 输出 token 的影响明显大于输入 token。过滤还使 5 个原本因内部请求 usage 缺失而不满足完整口径的任务可进入过滤口径，因此下面 Astra 覆盖为 100 题，而 Hermes 完整口径覆盖仍为 82 题：

| 指标                         |    Astra（排除内部非流式） |           Hermes（完整 usage） |
| ---------------------------- | -------------------------: | -----------------------------: |
| 可靠 token 记录              |        100 / 108（92.59%） |             82 / 108（75.93%） |
| 输入 token 总量              |                120,029,959 |                    142,142,325 |
| 输出 token 总量              |                  4,532,527 |                      1,964,613 |
| total token 总量             |                124,562,486 |                    144,106,938 |
| 单任务输入中位数             |                    621,049 |                      1,147,115 |
| 单任务输出中位数             |                     21,921 |                         19,696 |
| 单任务 total 中位数          |                    639,356 |                      1,174,439 |
| 有可靠 token 的 pass 任务    |          58 / 61（95.08%） |              54 / 72（75.00%） |
| pass 平均输入 / 输出 / total | 719,866 / 21,982 / 741,848 | 1,621,374 / 21,102 / 1,642,477 |
| pass total 中位数            |                    516,294 |                      1,045,431 |

上述总量和 pass 均值的覆盖集合不同，只能用于描述各自可观测足迹。更可比的是双方都 pass、且两侧在新口径下 token 均可靠的 38 个相同任务：

| 产品与口径              |        平均输入 / 输出 / total | total 中位数 |
| ----------------------- | -----------------------------: | -----------: |
| Astra（排除内部非流式） |     626,379 / 20,457 / 646,836 |      424,425 |
| Hermes（完整 usage）    | 1,028,766 / 16,506 / 1,045,272 |      667,907 |

在这 38 个同题 pass 样本中，过滤后的 Astra 平均 input 低 39.11%、平均 total 低 38.12%，但平均 output 高 23.93%；total 中位数低 36.45%。这仍不是严格的模型 token 效率比较，因为 Hermes 完整请求包含工具 schema，而 Astra 内部请求被主动排除，两侧计量边界并不对称。该表回答的是“去掉 Astra 内部非流式架构开销后，代理层剩余 token 与 Hermes 完整足迹相比如何”。

## 综合结论

1. **结果质量：Hermes 领先。** Hermes 72 pass，Astra 61 pass，领先 11 题和 10.19 个百分点；配对上 Hermes 独过 21 题，Astra 独过 10 题。
2. **Astra 的模型请求预算是主要短板。** Astra 有 20/47 个 no-pass 由 100 请求预算耗尽导致；Hermes仅 3/36。Astra 请求总量和单题中位数也显著高于 Hermes。
3. **Hermes 的有效失败更偏任务能力问题。** Hermes 33/36 个 no-pass 是完整运行结束后 evaluator 未通过；Astra对应 27/47。
4. **Astra 更慢。** Astra 端到端中位数 10.16 分钟，Hermes 7.10 分钟；配对 Agent 时间中位差为 Astra慢 3.71 分钟。
5. **工具调用总量接近。** Astra 单题中位数 31.5，Hermes 32.5；高请求数并没有同比转化为更多终态工具调用，说明 Astra 的额外负担主要发生在内部模型交互而非外部工具动作。
6. **Token 只能作架构足迹。** 在 38 个同题 pass 且 token 可靠的任务上，排除 Astra 内部非流式请求后，其平均 total token 比 Hermes 完整 usage 低 38.12%。

## 附件与数据来源

- 逐题配对结果与失败原因：[`astra-hermes-paired-outcome-cause-analysis.md`](astra-hermes-paired-outcome-cause-analysis.md)
- 逐 slot 数据：[`astra-hermes-toolathlon-108-task-results.csv`](astra-hermes-toolathlon-108-task-results.csv)
- 机器可读汇总：[`astra-hermes-toolathlon-108-task-summary.json`](astra-hermes-toolathlon-108-task-summary.json)
- 可复现脚本：[`generate_toolathlon_comparison.py`](generate_toolathlon_comparison.py)
- M1/M2 qualification：`astra/results/toolathlon-m2-first-batch-v4/m2-first-batch-qualification.json`
- M3 manifest/projection：`astra/results/toolathlon-m3-remaining-batch-v1/m3-batch-manifest.json`、`artifact-gate-v2-projection.json`
- Posthoc qualification：`astra/results/toolathlon-posthoc-unavailable-infra-rerun-v1/posthoc-rerun-qualification.json`

CSV 中 `token_reliable=false` 表示该题只有部分可见 token；相应 token 数值可用于下界汇总，但不能当作该题的完整 token。空值才表示没有任何可汇总的已上报 usage，不表示 token 为 0。
