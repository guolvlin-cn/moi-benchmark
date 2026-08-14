# Astra、Hermes 与 Pi：Toolathlon 108 题对比分析

生成日期：2026-08-14

## 口径

- Astra/Hermes 沿用既有 108 题正式投影；Pi 使用隔离与服务修复后的最终覆盖结果。
- Astra、Hermes 均有 108 个明确 evaluator 结果；Pi 有 104 个明确结果，另有 3 个 `unavailable` 和 1 个 `incomplete`。三方组合不会把这四题算作 Pi 失败。
- 通过与否只以 evaluator 为准。时间、工具调用、模型请求和 token 都是产品整体运行时口径，不是同构 agent loop，效率指标只能描述观测足迹。
- Pi 最终结果不是单一运行批次：Pi 的 effective result 按“基础批次 → 隔离重跑 → 最终服务/审计重跑”的顺序覆盖，同一题以后层完成且 artifact gate 通过的结果为准：

| 最终来源                                 | 采用题数 | 说明                                                               |
| ---------------------------------------- | -------: | ------------------------------------------------------------------ |
| `toolathlon-pi-108-v1`                 |       75 | 初始 108 题批次中未被后续有效结果替换的 slot                       |
| `toolathlon-pi-isolated-rerun-v1`      |       25 | 路径访问审计命中题及原基础设施未完成题的隔离重跑                   |
| `toolathlon-pi-service-and-audit-8-v3` |        8 | Canvas/WooCommerce 服务修复后的正式重跑，以及 NHL/VLM 扩展审计重跑 |

初始批次使用 `isolated_bind_mount` 映射任务 workspace，但不是空根文件系统容器。后两批使用 Docker sidecar：根文件系统只读，仅任务 workspace 可写，不暴露宿主机 home、宿主机 `/tmp` 或 Docker socket，并启用 `no-new-privileges`。因此，不能把 Pi 的全部 108 个 slot 描述为在完全相同的容器隔离模式下运行；准确口径是审计命中的任务已用增强隔离结果替换，其余初始结果继续保留。

四个没有明确 Pi evaluator 判定的 slot 仍保留原状态：第 38 题无完整 `run.json`；第 53、55、72 题 evaluator 返回 `pass: null`。它们不进入 104 题三方胜负配对，也不被补记为 `no_pass`。

## 实验产品与配置

| 项目               | Astra                                                                                                                                 | Hermes                                                                                                                          | Pi                                                           |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| 产品版本           | Linux/AMD64 release build；源码`v0.0.5-4-g844473c68`，commit `844473c68649d8ea43e10b616dc4fbf98e2321e8`；CLI 输出 `astra 0.1.0` | release descriptor`v2026.7.20-63-gf4df260f2`，commit `f4df260f26c93f15694698869f3ea8e965eea301`，project version `0.19.0` | `0.73.1` Linux x64 binary；                                |
| API 模型 ID        | `deepseek-v4-flash`                                                                                                                 | `deepseek-v4-flash`                                                                                                           | `deepseek-v4-flash`                                        |
| 模型版本口径       | DeepSeek-V4-Flash-0731                                                                                                                | DeepSeek-V4-Flash-0731                                                                                                          | DeepSeek-V4-Flash-0731                                       |
| 模型提供方         | DeepSeek 官方 API，经每次运行独立的本地代理                                                                                           | 同左                                                                                                                            | 同左                                                         |
| 推理配置           | Thinking enabled；`reasoning_effort=max`                                                                                            | 同左                                                                                                                            | 同左                                                         |
| Temperature        | 发送`temperature=0`；DeepSeek Thinking 模式下该参数不生效                                                                           | 同左                                                                                                                            | 同左                                                         |
| 产品原生 max turns | Astra 冻结默认值`300`                                                                                                               | Hermes 冻结默认值`90`                                                                                                         | 未显式设置                                                   |
| 外部统一请求预算   | 每题最多 100 次 product model request；允许第 100 次，拒绝第 101 次                                                                   | 同左                                                                                                                            | 同左                                                         |
| 实际最高模型请求数 | 100                                                                                                                                   | 100                                                                                                                             | 100                                                          |
| Agent deadline     | 按任务采用 R1/R2/R3/R4：1800/2700/3600/5400 秒                                                                                        | 同左                                                                                                                            | 同左                                                         |
| Prompt 口径        | 保留 Astra 原生 system prompt，并输入 Toolathlon 公共 system/task 指令                                                                | 保留 Hermes 原生 system prompt，并输入相同公共指令                                                                              | 保留 Pi 原生 system prompt，通过 append 方式输入相同公共指令 |
| 工具范围           | 保留产品内置工具；提供当前任务 的 MCP 工具                                                                                            | 保留产品内置工具；提供当前任务 的 MCP 工具                                                                                      | 保留产品内置工具；提供当前任务 的 MCP 工具                   |

三种产品的“turn”不是同构指标：Astra 会产生内部规划、反思和非流式请求，Hermes 主要使用携带工具 schema 的流式主循环，Pi 还包含其原生压缩与生命周期行为。因此，本实验以运行代理观测到的 `model_request.started` 作为统一请求预算和 step 统计，不把产品原生 max turns 或模型请求数直接解释为用户可见对话回合。

## 基础运行环境

| 环境项          | 配置                                                                                                           |
| --------------- | -------------------------------------------------------------------------------------------------------------- |
| 数据集          | Toolathlon，固定 108 题；严格三方比较采用 Pi 也有明确 evaluator 判定的 104 题                                  |
| Host OS         | Ubuntu 22.04.5 LTS，Linux`5.15.0-186-generic`，UTC                                                           |
| CPU             | Intel Xeon Platinum 8255C @ 2.50 GHz，x86_64，8 vCPU                                                           |
| 内存与 Swap     | Linux MemTotal 7.75 GiB（名义配置 8 GiB）；8 GiB swap，swappiness 10，关闭 zram                                |
| 虚拟化          | Oracle/Vagrant 虚拟机                                                                                          |
| 容器运行时      | rootful Docker Engine 29.1.3，cgroup v2，systemd cgroup driver，overlayfs                                      |
| 任务镜像        | `lockon0927/toolathlon-task-image@sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f`   |
| 单任务资源上限  | 8 CPU、8 GiB RAM、8 GiB swap                                                                                   |
| Kubernetes 工具 | Kind v0.20.0；kubectl v1.34.1                                                                                  |
| 外部应用状态    | 由任务 preprocess 恢复；Canvas、WooCommerce、Poste、MatrixOne 和 Kind 等使用共享部署，并非每题重新部署整套服务 |
| 网络边界        | 未统一关闭公开互联网出口；任务级 MCP 限于当前任务，但终端、fetch、浏览器或产品内置工具仍可能访问公开网络       |
| Evaluator       | 使用 Toolathlon 每题原生 evaluator，在 Agent 终止后独立执行                                                    |

这里记录的是实验冻结时的环境；实验结束后宿主机内核或服务状态的变化不追溯修改历史运行口径。三种产品的内部 turn 定义不同，因此报告统一使用代理观测到的 `model_request.started`，不把它重述为可直接比较的 Agent 回合数

## 任务完成结果

| 产品      | pass | no-pass | 未完成 | 按 108 题通过率 | 已测评题通过率 |
| --------- | ---: | ------: | -----: | --------------: | -------------: |
| Astra     |   61 |      47 |      0 |          56.48% |         56.48% |
| Hermes    |   72 |      36 |      0 |          66.67% |         66.67% |
| Pi 0.73.1 |   77 |      27 |      4 |          71.30% |         74.04% |

### 三方逐题组合

`P/F` 顺序固定为 Astra/Hermes/Pi。

| 结果组                        | 题数 | 任务                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ----------------------------- | ---: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 三者均通过                    |   49 | `find-alita-paper`（1）、`set-conf-cr-ddl`（2）、`canvas-homework-grader-python`（4）、`price-comparison`（7）、`excel-data-transformation`（9）、`notion-hr`（10）、`git-bug-hunt`（13）、`ab-testing`（15）、`academic-pdf-report`（16）、`academic-warning`（17）、`apply-phd-email`（19）、`canvas-arrange-exam`（20）、`canvas-art-quiz`（22）、`canvas-new-students-notification`（25）、`canvas-submit-late-work`（26）、`courses-ta-hws`（29）、`dietary-health`（33）、`excel-market-research`（35）、`flagged-transactions`（39）、`game-statistics`（40）、`gdp-cr5-analysis`（41）、`git-milestone`（42）、`git-repo`（43）、`huggingface-upload`（45）、`inventory-sync`（50）、`invoice-org`（52）、`k8s-redis-helm-upgrade`（57）、`landing-task-reminder`（58）、`latex-prompt-box`（60）、`live-transactions`（61）、`llm-training-dataset`（62）、`machine-operating`（64）、`meeting-assign`（65）、`notion-find-job`（70）、`notion-personal-website`（71）、`nvidia-stock-analysis`（73）、`payable-invoice-checker`（76）、`ppt-analysis`（78）、`sales-accounting`（82）、`sla-timeout-monitor`（84）、`student-interview`（86）、`sync-todo-to-readme`（88）、`train-ticket-plan`（90）、`trip-adviser`（93）、`trip-itinerary-generator`（94）、`update-material-inventory`（96）、`wandb-shortest-length`（101）、`woocommerce-customer-survey`（102）、`woocommerce-update-cover`（106） |
| Astra、Hermes 通过，Pi 未通过 |    2 | `nhl-b2b-analysis`（69）、`personal-website-construct`（77）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Astra、Pi 通过                |    8 | `course-schedule`（3）、`k8s-safety-audit`（14）、`email-paper-homepage`（34）、`imagenet`（47）、`k8s-deployment-cleanup`（54）、`search-ca-school`（83）、`upenn-campus-route`（97）、`yahoo-analysis`（107）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 仅 Astra 通过                 |    2 | `add-bibtex`（18）、`verl-dataset`（98）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Hermes、Pi 通过               |   11 | `notion-movies`（6）、`woocommerce-stock-alert`（12）、`canvas-art-manager`（21）、`canvas-do-quiz`（23）、`cooking-guidance`（27）、`dataset-license-issue`（31）、`fillout-online-forms`（37）、`inter-final-performance-analysis`（48）、`profile-update-online`（80）、`reimbursement-form-filler`（81）、`wandb-best-score`（100）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 仅 Hermes 通过                |    7 | `canvas-list-test`（24）、`cvpr-research`（30）、`identify-all-songs`（46）、`k8s-pr-preview-testing`（56）、`stock-build-position`（85）、`woocommerce-new-product`（103）、`woocommerce-new-welcome`（104）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| 仅 Pi 通过                    |    9 | `quantitative-financial-analysis`（8）、`interview-report`（49）、`logical-datasets-collection`（63）、`mrbeast-analysis`（67）、`music-analysis`（68）、`oil-price`（74）、`travel-expense-reimbursement`（92）、`woocommerce-product-recall`（105）、`youtube-repo`（108）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 三者均未通过                  |   16 | `arrange-workspace`（5）、`shopping-helper`（11）、`course-assistant`（28）、`detect-revised-terms`（32）、`experiments-recordings`（36）、`hk-top-conf`（44）、`investment-decision-analysis`（51）、`language-school`（59）、`merge-hf-datasets`（66）、`paper-checker`（75）、`privacy-desensitization`（79）、`subway-planning`（87）、`task-tracker`（89）、`travel-exchange`（91）、`university-course-selection`（95）、`vlm-history-completer`（99）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Pi 无明确 evaluator 判定      |    4 | `filter-low-selling-products`（38）、`ipad-edu-price`（53）、`k8s-mysql`（55）、`nvidia-market`（72）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |

最有区分度的是仅单一产品通过的任务。Pi 在 Astra 和 Hermes 都失败时通过 9 题：`quantitative-financial-analysis`（8）、`interview-report`（49）、`logical-datasets-collection`（63）、`mrbeast-analysis`（67）、`music-analysis`（68）、`oil-price`（74）、`travel-expense-reimbursement`（92）、`woocommerce-product-recall`（105）、`youtube-repo`（108）。反向地，Astra 和 Hermes 都通过但 Pi 未通过 2 题：`nhl-b2b-analysis`（69）、`personal-website-construct`（77）。

### 两两配对

| 配对            | 可比较题数 | 双方通过 | 仅左侧通过 | 仅右侧通过 | 双方未通过 |
| --------------- | ---------: | -------: | ---------: | ---------: | ---------: |
| astra vs hermes |        108 |       51 |         10 |         21 |         26 |
| astra vs pi     |        104 |       57 |          4 |         20 |         23 |
| hermes vs pi    |        104 |       60 |          9 |         17 |         18 |

Pi 与另外两者的配对只覆盖 104 个有明确 Pi evaluator 判定的题；因此不能把第 38、53、55、72 题加入任何单方胜负。

在共同可比较的 104 题上，Pi 相对 Astra 是 20 个 Pi-only 对 4 个 Astra-only，净胜 16 题；相对 Hermes 是 17 个 Pi-only 对 9 个 Hermes-only，净胜 8 题。这是固定 benchmark 上的逐题描述，不是从更大总体抽样得到的显著性结论。

## No-pass 原因

| 产品   | 完成但 evaluator 未通过 | 模型请求预算 | 产品执行错误 |
| ------ | ----------------------: | -----------: | -----------: |
| astra  |                      27 |           20 |            0 |
| hermes |                      33 |            3 |            0 |
| pi     |                      23 |            2 |            1 |

Astra 的预算终止占失败的重要部分；Hermes 的失败主要发生在正常结束后未满足 evaluator。Pi 同时存在完成后精确性/完整性失败与预算耗尽，另有最终审计重跑记录到的产品执行错误。这里是直接终态分类，不推断模型内部原因。

## 时间消耗

Astra、Hermes 均统计 108 个正式结果；Pi 统计 107 个有完整 `run.json` 的 effective run，其中包括 3 个 evaluator `unavailable` 的运行，但不包括第 38 题的基础设施未完成 attempt。

| 阶段               | 产品   | 样本数 |      总计 |      平均 |    中位数 |       P90 |
| ------------------ | ------ | -----: | --------: | --------: | --------: | --------: |
| 端到端             | Astra  |    108 |   34.18 h | 18.99 min | 10.16 min | 50.01 min |
| 端到端             | Hermes |    108 |   17.58 h |  9.77 min |  7.10 min | 19.63 min |
| 端到端             | Pi     |    107 |   17.73 h |  9.94 min |  4.83 min | 22.39 min |
| Agent 执行         | Astra  |    108 |   32.69 h | 18.16 min |  9.10 min | 49.26 min |
| Agent 执行         | Hermes |    108 |   14.21 h |  7.89 min |  5.21 min | 16.93 min |
| Agent 执行         | Pi     |    107 |   15.90 h |  8.91 min |  4.07 min | 21.62 min |
| Evaluator          | Astra  |    108 | 36.26 min |   20.15 s |   12.68 s |   38.53 s |
| Evaluator          | Hermes |    108 | 36.21 min |   20.12 s |   11.40 s |   32.76 s |
| Evaluator          | Pi     |    107 | 43.34 min |   24.30 s |   10.75 s |   34.52 s |
| Orchestration/收尾 | Astra  |    108 | 52.94 min |   29.41 s |   27.96 s |   40.95 s |
| Orchestration/收尾 | Hermes |    108 |    2.77 h |   92.36 s |  101.83 s |  142.75 s |
| Orchestration/收尾 | Pi     |    107 |    1.12 h |   37.53 s |   21.93 s |   45.92 s |

Pi 的端到端和 Agent 时间中位数最低，分别为 4.83 和 4.07 分钟；Hermes 分别为 7.10 和 5.21 分钟，Astra 为 10.16 和 9.10 分钟。但 Pi 的 P90 端到端时间高于 Hermes，说明 Pi 的长尾任务仍然明显。上述时间包含通过与未通过任务，不能解释为“完成同样成功结果所需时间”。`orchestration` 是端到端减去 Agent 和 evaluator 后的剩余时间，包含准备、adapter 收尾及 post-terminal model drain，并非纯环境准备时间。

## 工具调用

| 指标             | Astra | Hermes |    Pi |
| ---------------- | ----: | -----: | ----: |
| 有工具计数的运行 |   108 |    108 |   107 |
| 工具调用总数     | 4,345 |  4,848 | 4,265 |
| 单运行平均       | 40.23 |  44.89 | 39.86 |
| 单运行中位数     |  31.5 |   32.5 |    29 |
| 单运行 P90       |  75.6 |   78.6 |  76.0 |
| 失败工具事件总数 |    56 |      0 |   247 |

常见终态工具：

- Astra：`local-python-execute` 464、`terminal-run_command` 234、`woocommerce-woo_products_list` 172、`wandb-query_wandb_tool` 153、`word-add_paragraph` 151。
- Hermes：`terminal` 754、`word-add_paragraph` 392、`local-python-execute` 288、`terminal-run_command` 232、`emails-send_email` 129。
- Pi：`bash` 751、`local-python-execute` 371、`terminal-run_command` 142、`canvas-canvas_list_folders` 132、`google-cloud-bigquery_run_query` 104。

三者的工具工作负担中位数接近，但工具名称和封装并不等价。Hermes 的 `terminal`、Pi 的 `bash`、任务 MCP 的 `terminal-run_command` 是不同传输层；Hermes adapter 没有把本批 effective run 的工具终态归类为 `failed`，因此失败事件 0 不表示所有工具在语义上成功。Pi 的 247 个失败事件也可能包含重试后恢复的调用，不能直接等同于任务失败。

## 模型请求

| 指标                     |           Astra |          Hermes |            Pi |
| ------------------------ | --------------: | --------------: | ------------: |
| 统计运行数               |             108 |             108 |           107 |
| 模型请求 started         |           5,229 |           3,287 |         2,595 |
| 模型请求 completed event |           5,229 |           3,284 |         2,595 |
| provider 失败请求        |              19 |              26 |            15 |
| 单运行 started 平均      |           48.42 |           30.44 |         24.25 |
| 单运行 started 中位数    |            33.5 |              20 |            16 |
| 单运行 started P90       |             100 |            66.5 |          48.8 |
| 触及 100 请求上限        |              23 |               3 |             4 |
| 因请求预算 no-pass       |              20 |               3 |             2 |
| 流式请求                 | 2,226（42.57%） | 3,081（93.73%） | 2,595（100%） |
| 非流式请求               | 3,003（57.43%） |    206（6.27%） |       0（0%） |

Pi 的模型请求总量和中位数最低；Astra 总请求数分别比 Hermes 和 Pi 高 59.08% 和 101.50%。但请求数不是用户可见 turn：Astra 的统计包含大量内部无工具非流式请求，Hermes 和 Pi 更接近携带工具 schema 的流式主循环。Pi 触及上限的 4 个运行中，2 个形成 `no_pass`，另有第 55、72 题的 evaluator 返回 `pass: null`；因此“触及上限”和“因预算 no-pass”不是同一计数。

## Token 数据

### 保守可靠记录

若一个 effective run 的 completed response 存在缺失 usage，该运行不进入本表：

| 指标                         |       Astra |      Hermes |          Pi |
| ---------------------------- | ----------: | ----------: | ----------: |
| 有完整 provider usage 的运行 |    95 / 108 |    82 / 108 |   103 / 107 |
| 输入 token 总量              | 114,783,243 | 142,142,325 | 230,864,137 |
| 输出 token 总量              |   8,791,196 |   1,964,613 |   2,268,979 |
| total token 总量             | 123,574,439 | 144,106,938 | 233,133,116 |
| 单运行 total 中位数          |     649,739 |   1,174,439 |     653,387 |

总量覆盖的运行数不同，不能把总量差直接解释为成本或效率差异。Pi 的可靠覆盖率最高，但其 input 中包含 provider 单独报告的 cache-read token；Astra 和 Hermes 的产品请求结构及缓存计量边界也不同。

### 全部可见 token 下界

下界口径保留每个完整运行中已经明确上报的 usage；缺失 usage 的 completed request 保持未知，不补零：

| 产品   | 运行数 | 已上报 / 缺 usage 的 completed 请求 | 输入 token 下界 | 输出 token 下界 | total token 下界 | 单运行 total 中位数 |
| ------ | -----: | ----------------------------------: | --------------: | --------------: | ---------------: | ------------------: |
| Astra  |    108 |                          5,210 / 19 |     149,741,746 |      11,654,317 |      161,396,063 |             756,014 |
| Hermes |    108 |                          3,256 / 28 |     244,960,861 |       3,124,778 |      248,085,639 |           1,364,392 |
| Pi     |    107 |                          2,580 / 15 |     237,628,246 |       2,360,566 |      239,988,812 |             653,387 |

Pi 可见 cache-read token 为 226,238,208，占其可见 input 的 95.20%，且已经包含在 input/total 中，不能再次相加。Astra 完整架构包含内部非流式请求；双产品报告另提供“排除 Astra `stream=false && request_tool_count=0` 请求”的辅助口径。本三产品表保留各产品完整代理可见足迹，不使用不对称过滤结果给产品排序。

### Pass 任务的可靠 Token

| 产品   | 有可靠 token 的 pass 任务 | total token 总量 | 单任务平均 | 单任务中位数 |
| ------ | ------------------------: | ---------------: | ---------: | -----------: |
| Astra  |                   56 / 61 |       44,004,486 |    785,794 |      518,071 |
| Hermes |                   54 / 72 |       88,693,746 |  1,642,477 |    1,045,431 |
| Pi     |                   77 / 77 |       98,717,289 |  1,282,043 |      586,542 |

该表中三者通过的任务集合不同，不能据此计算单位成功成本。严格 token 对比还需要限制到三者共同 pass、三侧 usage 都完整的同一任务集合，并同时处理工具 schema、缓存和内部请求边界差异。

## 综合结论

1. **结果质量：Pi 当前已确认通过数最高，但覆盖尚不完整。** Pi 已确认 77 pass，高于 Hermes 的 72 和 Astra 的 61；按全部 108 题是 71.30%，按 104 个明确结果是 74.04%。第 38、53、55、72 题没有明确 Pi evaluator 判定，不能把当前结果表述为完整的 108 题最终排名。
2. **逐题结果不是包含关系。** 在104个三方可比较任务中，Pi 相对 Astra 净胜16题、相对 Hermes 净胜8题；Pi 独过9题，但也有2题由 Astra/Hermes 共同通过而 Pi 未通过。产品主循环、自检和工具执行策略都会改变结果。
3. **Astra 的请求预算消耗最突出。** Astra 有23题触及100请求上限，其中20题因预算 no-pass；Hermes分别为3和3，Pi为4和2。Astra模型请求中位数33.5，也高于Hermes的20和Pi的16。
4. **Pi 的典型运行更短，但存在长尾。** Pi Agent 时间中位数4.07分钟，为三者最低；其端到端 P90 为22.39分钟，高于Hermes的19.63分钟。不能仅用中位数概括所有任务。
5. **工具调用总量接近。** 三者单运行工具调用中位数为31.5、32.5和29。失败工具事件的采集和分类方式不同，不能直接作为产品可靠性排名。
6. **Token 只能描述架构足迹。** Pi和Astra的可靠记录 total 中位数接近，Hermes更高；但三者的工具 schema、缓存计量、上下文组织和内部请求不同，不能将差异直接表述为模型 token 效率或成本优势。
7. **Pi 的 effective result 混合了三个批次。** 路径审计命中题已由增强隔离重跑替换，服务异常题采用最终服务重跑；其余初始结果继续保留。环境修复和权限边界必须作为解释结果的一部分。
8. **能力归因必须以可观察证据为限。** Pi 的优势案例可归因到 evaluator 验证的产物完整性、步骤执行和终态自检，但不能从轨迹结果直接推断未观测的“推理能力”。

## 附件

- Pi 独立汇总：[`pi-toolathlon-108-task-comparison.md`](pi-toolathlon-108-task-comparison.md)
- 三产品逐 slot 数据：[`astra-hermes-pi-toolathlon-108-task-results.csv`](astra-hermes-pi-toolathlon-108-task-results.csv)
- 三产品机器可读汇总：[`astra-hermes-pi-toolathlon-108-task-summary.json`](astra-hermes-pi-toolathlon-108-task-summary.json)
- 原 Astra/Hermes 逐题原因：[`astra-hermes-paired-outcome-cause-analysis.md`](astra-hermes-paired-outcome-cause-analysis.md)
- 生成脚本：[`generate_astra_pi_hermes_comparison.py`](generate_astra_pi_hermes_comparison.py)
