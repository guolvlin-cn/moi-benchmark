# Hermes C0 当前已完成任务与 Astra 56 项交叉统计（V1）

- Hermes 根目录：`/Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs`
- Hermes 快照截止：`2026-07-31T16:46:44+08:00`
- Hermes 已终态：64；另有 `regex-chess` 在快照时仍运行，未纳入
- Astra 对照：[Astra C0 56 项 V1](</Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/analysis/v1/astra-c0-56-tasks-statistics-v1.md>)
- 主比较样本：Hermes 64 与 Astra 56 的 46 个同任务交集
- 数据来源：trial `result.json`、Hermes session/run/events、controller、CTRF，以及 Astra V1 CSV/JSON

## 1. 执行摘要

- Hermes 当前 64 个终态任务中，`reward=1` 为 **35/64（54.69%）**；在 57 个已有 reward 的任务中为 **35/57（61.40%）**。
- Hermes 严格端到端成功为 **33/64（51.56%）**；Agent 正常终态为 **49/64（76.56%）**。
- Hermes 有 22 个零分和 7 个无 reward 异常。22 个零分中只有 **1 个**具有明确 LLM/provider 无响应证据；失败主因已从 Astra 的传输中断转为任务未完成、deadline、后台进程生命周期和评估基础设施问题。
- 在 46 个同任务交集上，Astra 通过 **26/46（56.52%）**，Hermes 通过 **31/46（67.39%）**，但 Hermes 有 6 项未评分。若只看双方都有 Hermes reward 的 40 项，Astra 为 **24/40（60.00%）**，Hermes 为 **31/40（77.50%）**。
- 同任务交集的严格 E2E 成功：Astra **20/46（43.48%）**，Hermes **30/46（65.22%）**。
- 同任务交集上，Hermes 累计 E2E 时间比 Astra 少 **31.72%**，但总 token 为 Astra 的 **2.97 倍**；fresh input 基本持平，增量主要来自 Hermes 的 cache-read（3.64 倍）。
- 两边所有纳入项均为 `formal_score_eligible=false`。本文只能解释探索性运行结果，不能作为正式 C0 主结果。

## 2. 范围与可比口径

### 2.1 三个样本集合

| 集合 | 任务数 | 用途 | 主要偏差 |
| --- | ---: | --- | --- |
| Hermes 当前终态快照 | 64 | 研究 Hermes 当前完成情况 | 进行中批次的时间截面，非随机样本 |
| Astra V1 非重跑样本 | 56 | 复用既有基线 | 从 89 项排除 33 个必须完整重跑任务后的条件样本 |
| 同任务交集 | 46 | 主交叉比较 | 控制任务组成，但模型、turn budget、timeout 和 runner 仍不同 |

Hermes 当前 64 项中，有 18 项属于 Astra V1 排除的“必须从头重跑”集合；Astra 56 项中还有 10 项在 Hermes 快照时尚未终态。因此 64 对 56 的全样本通过率只能描述各自快照，不能直接解释为 Agent 优劣。

- Hermes 已完成、但不在 Astra 56 中的 18 项：`adaptive-rejection-sampler`, `build-pov-ray`, `dna-assembly`, `dna-insert`, `feal-linear-cryptanalysis`, `fix-code-vulnerability`, `gpt2-codegolf`, `kv-store-grpc`, `large-scale-text-editing`, `make-doom-for-mips`, `make-mips-interpreter`, `model-extraction-relu-logits`, `polyglot-rust-c`, `prove-plus-comm`, `pytorch-model-recovery`, `qemu-alpine-ssh`, `qemu-startup`, `query-optimize`。
- Astra 56 中尚未进入 Hermes 终态的 10 项：`log-summary-date-ranges`, `regex-chess`, `reshard-c4-data`, `rstan-to-pystan`, `sam-cell-seg`, `schemelike-metacircular-eval`, `sqlite-db-truncate`, `sqlite-with-gcov`, `torch-pipeline-parallelism`, `vulnerable-secret`。

### 2.2 指标定义

| 指标 | 统一判定 |
| --- | --- |
| Verifier 功能通过 | `reward=1`，不要求 Agent 正常退出 |
| Agent 正常终态 | `product_terminal_status=completed && rc=0` |
| 严格端到端成功 | Agent 正常终态且 `reward=1` |
| Input token | `fresh_input + cache_read` |
| Total token | `input + output`；reasoning 是 output 的补充分拆，不重复相加 |
| 工具调用 | Astra 为完成/失败 step event；Hermes 为 `tool.completed` |
| 失败工具返回 | Astra `ToolCallFailed`；Hermes `tool.completed.error=true` |
| 时间 | 每任务阶段时间累计；不是并发批次 wall-clock |

轮次与工具失败是近似对齐而非同源埋点：Astra 使用 `StepStarted`/中断记录，Hermes 使用 session `api_call_count`；Astra 的 bash 非零返回可能不记 `ToolCallFailed`，Hermes 的 event error 也不等价于所有非零子进程状态。

## 3. Hermes 当前 64 项结果

### 3.1 完成与评分

| 口径 | 数量 | 比例 |
| --- | ---: | ---: |
| Reward=1 / 全部终态 | 35/64 | 54.69% |
| Reward=1 / 已评分 | 35/57 | 61.40% |
| Reward=0 | 22/64 | 34.38% |
| Reward 缺失 | 7/64 | 10.94% |
| Agent completed/rc0 | 49/64 | 76.56% |
| 严格 E2E 成功 | 33/64 | 51.56% |
| 异常终止但通过 | 2/64 | 3.12% |
| 正式 C0 合格 | 0/64 | 0.00% |

| Product 终态 | 总数 | Reward=1 | Reward=0 | 无 Reward |
| --- | ---: | ---: | ---: | ---: |
| `completed/rc0` | 49 | 33 | 16 | 0 |
| `timeout/rc124` | 7 | 2 | 5 | 0 |
| `failed/rc2` | 1 | 0 | 1 | 0 |
| `adapter_infra_error/rc null` | 7 | 0 | 0 | 7 |

两个“异常终止但通过”是 `model-extraction-relu-logits` 和 `path-tracing-reverse`：都达到 driver deadline，但 timeout 前留下的 artifact 通过了 Verifier。功能 reward 可以保留，严格 E2E 不计成功。

### 3.2 Verifier

- 56/64 生成 CTRF；合计 **193 tests，152 pass、41 fail**。
- Reward=1：130/130 tests。
- Reward=0 且有 CTRF：22/63 tests。
- 8 项无 CTRF：7 个无 reward 异常，以及 `pytorch-model-recovery`；后者在 Verifier 下载依赖时出现网络/SSL 故障。

### 3.3 时间

| 阶段 | 覆盖 | 累计小时 | 均值分钟 | 中位数分钟 | P90 分钟 | 最大分钟 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 端到端 | 64/64 | 21.842 | 20.48 | 13.19 | 54.62 | 93.04 |
| 环境初始化 | 64/64 | 0.030 | 0.03 | 0.02 | 0.04 | 0.13 |
| Agent 初始化 | 64/64 | 0.112 | 0.10 | 0.09 | 0.13 | 0.36 |
| Agent 执行 | 64/64 | 20.289 | 19.02 | 11.80 | 49.54 | 91.77 |
| Verifier | 57/64 | 1.180 | 1.24 | 0.45 | 1.00 | 22.90 |

端到端累计为 **21.842 task-hours**；Agent 执行累计 **20.289 agent-hours**。

E2E 时间最高的任务：

| 任务 | Reward | Product | E2E 分钟 | Agent 分钟 | 类别 |
| --- | ---: | --- | ---: | ---: | --- |
| [adaptive-rejection-sampler](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__12-02-21/adaptive-rejection-sampler__RUDgwZK/result.json>) | 0 | `failed/rc2` | 93.04 | 91.77 | LLM/Provider 明确无响应 |
| [compile-compcert](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__19-01-52/compile-compcert__THECWzy/result.json>) | 0 | `timeout/rc124` | 80.92 | 80.23 | Driver deadline，任务未完成 |
| [fix-ocaml-gc](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-39-17/fix-ocaml-gc__KRpRZNt/result.json>) | 1 | `completed/rc0` | 76.63 | 53.41 | 正常完成且通过 |
| [caffe-cifar-10](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__17-41-21/caffe-cifar-10__MyMkUd9/result.json>) | 0 | `completed/rc0` | 67.87 | 67.17 | 任务交付或产物错误 |
| [path-tracing-reverse](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__11-44-49/path-tracing-reverse__bqaaCSt/result.json>) | 1 | `timeout/rc124` | 61.12 | 60.21 | 超时终止但通过 |
| [path-tracing](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-35-33/path-tracing__99PefA4/result.json>) | — | `adapter_infra_error/rcnull` | 60.56 | 60.23 | Deadline 后 adapter 异常，无 Verifier |
| [extract-moves-from-video](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__00-10-48/extract-moves-from-video__CTkXDwT/result.json>) | — | `adapter_infra_error/rcnull` | 60.52 | 60.21 | Deadline 后 adapter 异常，无 Verifier |
| [install-windows-3.11](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__05-42-50/install-windows-3.11__mjR9MNB/result.json>) | — | `adapter_infra_error/rcnull` | 40.84 | 40.52 | Cleanup/adapter 异常，无 Verifier |

### 3.4 Token、轮次与工具

| 指标 | 覆盖 | 累计 | 均值 | 中位数 | P90 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fresh input | 63/64 | 3,339,004 | 53,000 | 24,649 | 139,480.8 |
| Cache-read | 63/64 | 73,233,280 | 1,162,433 | 447,872 | 3,181,900.8 |
| Input（含 cache） | 63/64 | 76,572,284 | 1,215,433 | 498,724 | 3,315,004.8 |
| Output | 63/64 | 1,876,876 | 29,792 | 15,539 | 68,171.4 |
| 总 token | 63/64 | 78,449,160 | 1,245,225 | 517,349 | 3,388,652.0 |
| API/Agentic 轮次 | 63/64 | 2,040 | 32 | 22 | 75.4 |
| 工具完成返回 | 64/64 | 2,233 | 35 | 23 | 75.7 |
| 失败工具返回 | 64/64 | 219 | 3 | 2 | 8.7 |

- Cache-read 占 input 的 **95.64%**。
- Reasoning token 共 1,270,604；它已包含在 output 口径内，不再加入 total。
- 工具事件失败率为 **219/2,233（9.81%）**；工具累计执行时间约 **8.050 小时**。
- 63/64 有 session/token；`prove-plus-comm` 在 session 建立前失败。美元成本没有可靠记录，`estimated_cost_usd=0` 不能解释为实际成本为零。

| 工具 | 完成返回 | 失败返回 | 事件失败率 |
| --- | ---: | ---: | ---: |
| `terminal` | 1,617 | 171 | 10.58% |
| `write_file` | 156 | 3 | 1.92% |
| `read_file` | 143 | 3 | 2.10% |
| `patch` | 75 | 1 | 1.33% |
| `process` | 71 | 0 | 0.00% |
| `todo` | 56 | 0 | 0.00% |
| `search_files` | 44 | 1 | 2.27% |
| `execute_code` | 32 | 32 | 100.00% |
| `vision_analyze` | 28 | 4 | 14.29% |
| `browser_navigate` | 4 | 0 | 0.00% |

按 Reward 分组的资源投入：

| 分组 | 任务 | E2E 小时 | Agent 小时 | 总 token | API 轮次 | 工具 | 失败工具 | Tests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Reward=1 | 35 | 8.736 | 7.663 | 31,447,999 | 871 | 987 | 90 | 130/130 |
| Reward=0 | 22 | 10.056 | 9.616 | 35,846,517 | 874 | 939 | 79 | 22/63 |
| Reward 缺失 | 7 | 3.050 | 3.010 | 11,154,644 | 295 | 307 | 50 | 0/0 |
| 严格 E2E 成功 | 33 | 7.203 | 6.156 | 25,113,669 | 762 | 872 | 84 | 126/126 |

31 个非严格成功任务消耗约 **53.34M token，占可观测总 token 的 67.99%**。因此不能把零分或未评分任务当作“零资源失败”。

总 token 最高的任务：

| 任务 | Reward | 总 token | Fresh | Cache | Output | API 轮次 | 工具 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [make-doom-for-mips](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__07-29-59/make-doom-for-mips__Wjfu7d3/result.json>) | 0 | 6,821,341 | 175,599 | 6,602,496 | 43,246 | 90 | 99 |
| [make-mips-interpreter](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__07-48-27/make-mips-interpreter__MwMSXQK/result.json>) | 0 | 6,807,364 | 254,654 | 6,466,560 | 86,150 | 90 | 115 |
| [gcode-to-text](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__03-57-56/gcode-to-text__igrmbEY/result.json>) | 0 | 4,126,686 | 210,373 | 3,851,840 | 64,473 | 70 | 69 |
| [build-cython-ext](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-23-53/build-cython-ext__6BZKneV/result.json>) | 1 | 4,063,645 | 206,090 | 3,839,360 | 18,195 | 80 | 132 |
| [path-tracing-reverse](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__11-44-49/path-tracing-reverse__bqaaCSt/result.json>) | 1 | 3,866,585 | 310,569 | 3,495,424 | 60,592 | 54 | 61 |
| [db-wal-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-54-42/db-wal-recovery__33DeyG7/result.json>) | 1 | 3,411,792 | 132,564 | 3,214,656 | 64,572 | 76 | 75 |
| [fix-ocaml-gc](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-39-17/fix-ocaml-gc__KRpRZNt/result.json>) | 1 | 3,396,198 | 115,009 | 3,259,776 | 21,413 | 59 | 62 |
| [path-tracing](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-35-33/path-tracing__99PefA4/result.json>) | — | 3,358,468 | 212,275 | 2,915,328 | 230,865 | 58 | 58 |
| [mailman](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__07-13-36/mailman__WzGfTVF/result.json>) | — | 3,207,777 | 135,264 | 3,050,880 | 21,633 | 70 | 76 |
| [install-windows-3.11](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__05-42-50/install-windows-3.11__mjR9MNB/result.json>) | — | 2,941,557 | 68,862 | 2,853,312 | 19,383 | 90 | 90 |

## 4. Hermes 失败与异常根因

### 4.1 分类总表

| 类别 | 数量 | 是否计分 | 是否明确 LLM 连接问题 | 建议 |
| --- | ---: | --- | --- | --- |
| 正常完成且通过 | 33 | Reward=1 | 否 | 保留 |
| 超时终止但通过 | 2 | Reward=1 | 否 | 保留功能结果；严格 E2E 可重跑 |
| LLM/Provider 明确无响应 | 1 | Reward=0 | 是 | Provider 恢复后完整重跑 |
| Driver deadline，任务未完成 | 5 | Reward=0 | 无明确证据 | 若 deadline 是协议预算则保留；否则统一配置后重跑 |
| 任务交付或产物错误 | 10 | Reward=0 | 否 | 保留真实零分 |
| 性能门槛未满足 | 1 | Reward=0 | 否 | 保留真实零分 |
| 后台服务被 gateway cleanup 清理 | 4 | Reward=0 | 否 | 改为独立 daemon 后完整重跑 |
| Verifier 基础设施失败 | 1 | Reward=0 | 否 | 优先重跑 Verifier |
| Deadline 后 adapter 异常，无 Verifier | 2 | 无 Reward | 否 | 完整重跑并保留明确 timeout 终态 |
| Cleanup/adapter 异常，无 Verifier | 4 | 无 Reward | 否 | 完整重跑取得评分 |
| Launcher/环境异常，无 Verifier | 1 | 无 Reward | 否 | 修复 launcher 后完整重跑 |

### 4.2 明确的 LLM/provider 无响应只有 1 项

`adaptive-rejection-sampler` 的 driver 明确记录 `Provider has been unresponsive ... for 5 consecutive stale attempts`，这是当前唯一可以严格计为 LLM/provider 无返回的失败。它运行约 93 分钟后失败，未生成 `ars.R`。 [driver](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__12-02-21/adaptive-rejection-sampler__RUDgwZK/agent/hermes-driver.stdout.txt:1>)

`gpt2-codegolf` 在最后工具完成后出现长时间无事件，可能与等待下一次模型返回有关，但日志只记录 `ProductDeadlineExpired`，没有 transport/provider 错误，因此不计入“明确 LLM 连接失败”。`feal-linear-cryptanalysis` 是回复多次截断后以`run.completed/output=null` 结束，也不能归为连接失败。

### 4.3 四个后台服务被 gateway cleanup 清理

`configure-git-webserver`、`kv-store-grpc`、`pypi-server`、`qemu-startup`均在 Agent 内启动过服务，但使用 Hermes 工具托管的 background。`run.completed` 后 gateway 正常 shutdown 会清理这些进程，Verifier 随后连接失败。这类零分是可重复的生命周期集成问题，不是 LLM 无返回。

- [configure-git-webserver：run.completed → cleanup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-30-38/configure-git-webserver__VuHrDDN/agent/hermes-run-events.jsonl:419>)；[Verifier HTTP 000](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-30-38/configure-git-webserver__VuHrDDN/verifier/test-stdout.txt:30>)
- [kv-store-grpc：run.completed → cleanup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-25-39/kv-store-grpc__Ef67kGg/agent/hermes-run-events.jsonl:515>)；[Verifier 5328 connection refused](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-25-39/kv-store-grpc__Ef67kGg/verifier/test-stdout.txt:125>)
- [pypi-server：run.completed → cleanup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-05-34/pypi-server__SzFsDEH/agent/hermes-run-events.jsonl:1329>)；[Verifier 无法安装包](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-05-34/pypi-server__SzFsDEH/verifier/test-stdout.txt:67>)
- [qemu-startup：run.completed → cleanup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-09-06/qemu-startup__4pKPFNL/agent/hermes-run-events.jsonl:282>)；[Verifier telnet 失败](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-09-06/qemu-startup__4pKPFNL/verifier/test-stdout.txt:99>)

### 4.4 七个 Exception/no-reward

七项都表现为 `ExceptionGroup + adapter_infra_error`，表层共同错误为 `LifecycleControllerError: process cleanup report is unavailable`：

- Deadline 后再被 adapter 异常覆盖：`extract-moves-from-video`、`path-tracing`。
- Hermes 已 `run.completed`，但 cleanup report 缺失、Verifier 被跳过：`git-multibranch`、`install-windows-3.11`、`mailman`、`nginx-request-logging`。
- Agent/session 未成功建立：`prove-plus-comm`。

这些任务都不是明确 LLM 连接失败；因为原环境已经结束，现有 session 不能直接恢复成可验证的现场。共同异常示例见 [git-multibranch result](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-45-22/git-multibranch__annFNdb/result.json:197>)。

### 4.5 真实任务/产物失败

11 项属于任务交付、产物正确性或性能门槛失败，不应误归入 LLM/runner 可靠性：`winning-avg-corewars`、`build-pov-ray`、`caffe-cifar-10`、`dna-assembly`、`dna-insert`、`feal-linear-cryptanalysis`、`make-doom-for-mips`、`make-mips-interpreter`、`openssl-selfsigned-cert`、`protein-assembly`、`query-optimize`。

其中 `query-optimize` 的结果正确，但 solution median 1.269s，超过 golden 0.966s 的 1.05 倍性能门槛；这是有效的性能零分。 [Verifier](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-29-40/query-optimize__GxjCVic/verifier/test-stdout.txt:110>)

## 5. 与 Astra V1 的交叉对比

### 5.1 全样本快照：只能描述，不能直接排名

| 指标 | Astra V1 56 | Hermes 当前 64 |
| --- | ---: | ---: |
| Reward=1 | 31/56（55.36%） | 35/64（54.69%）；已评分口径 35/57（61.40%） |
| 严格 E2E 成功 | 25/56（44.64%） | 33/64（51.56%） |
| Agent completed/rc0 | 27/56（48.21%） | 49/64（76.56%） |
| 无 Reward | 0 | 7 |
| E2E 累计 task-hours | 25.483 | 21.842 |
| Agent 累计 hours | 21.956 | 20.289 |
| Fresh input | 2,609,838 | 3,339,004 |
| Cache-read | 14,853,952 | 73,233,280 |
| 总 token | 19,511,085 | 78,449,160 |
| 轮次/API 调用 | 970 | 2,040 |
| 工具返回 | 1,282 | 2,233 |
| 失败工具返回 | 101 | 219 |
| CTRF tests | 140/197 | 152/193 |
| 正式 C0 合格 | 0 | 0 |

### 5.2 46 个同任务的结果变化

| 转移 | 数量 | 含义 | 任务 |
| --- | ---: | --- | --- |
| 1→1 | 19 | 两边都通过 | [bn-fit-modify](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/result.json>)、[break-filter-js-from-html](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__13-38-01/break-filter-js-from-html__MhrC9uW/result.json>)、[build-cython-ext](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-23-53/build-cython-ext__6BZKneV/result.json>)、[cobol-modernization](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-21-33/cobol-modernization__WBMseXk/result.json>)、[constraints-scheduling](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-41-17/constraints-scheduling__cX4gLS6/result.json>)、[count-dataset-tokens](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-48-04/count-dataset-tokens__hSzRjmb/result.json>)、[custom-memory-heap-crash](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-37-12/custom-memory-heap-crash__bzdH3jy/result.json>)、[db-wal-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-54-42/db-wal-recovery__33DeyG7/result.json>)、[feal-differential-cryptanalysis](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__01-13-23/feal-differential-cryptanalysis__cdkHeUK/result.json>)、[financial-document-processor](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-15-56/financial-document-processor__xaV7aav/result.json>)、[fix-git](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-29-59/fix-git__v5ytDph/result.json>)、[fix-ocaml-gc](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-39-17/fix-ocaml-gc__KRpRZNt/result.json>)、[git-leak-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-35-51/git-leak-recovery__FSFqxjL/result.json>)、[headless-terminal](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__05-29-30/headless-terminal__w4fJEGp/result.json>)、[merge-diff-arc-agi-task](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__08-50-54/merge-diff-arc-agi-task__vhnhmaK/result.json>)、[modernize-scientific-stack](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-32-29/modernize-scientific-stack__BA2S2GU/result.json>)、[multi-source-data-merger](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-40-03/multi-source-data-merger__mm3EWMs/result.json>)、[password-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-22-47/password-recovery__7Y4d5e9/result.json>)、[polyglot-c-py](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__12-52-58/polyglot-c-py__TW2ShP7/result.json>) |
| 0→1 | 12 | Hermes 改善 | [build-pmars](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__13-52-02/build-pmars__d5SRCdf/result.json>)、[chess-best-move](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-02-59/chess-best-move__oL3Bfm6/result.json>)、[code-from-image](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-42-47/code-from-image__FSsBtAW/result.json>)、[crack-7z-hash](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-08-33/crack-7z-hash__hexw2DN/result.json>)、[distribution-search](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__22-24-38/distribution-search__vcpnUUq/result.json>)、[extract-elf](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__23-48-32/extract-elf__L78scP6/result.json>)、[filter-js-from-html](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__01-42-23/filter-js-from-html__RdhDxsm/result.json>)、[llm-inference-batching-scheduler](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-44-32/llm-inference-batching-scheduler__fKWoNdN/result.json>)、[mcmc-sampling-stan](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__08-18-19/mcmc-sampling-stan__tJaMa3U/result.json>)、[overfull-hbox](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-00-15/overfull-hbox__8TTwMxE/result.json>)、[path-tracing-reverse](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__11-44-49/path-tracing-reverse__bqaaCSt/result.json>)、[portfolio-optimization](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__13-12-48/portfolio-optimization__LWrHTUo/result.json>) |
| 1→0 | 5 | Hermes 回退 | [caffe-cifar-10](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__17-41-21/caffe-cifar-10__MyMkUd9/result.json>)、[compile-compcert](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__19-01-52/compile-compcert__THECWzy/result.json>)、[configure-git-webserver](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-30-38/configure-git-webserver__VuHrDDN/result.json>)、[openssl-selfsigned-cert](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-50-26/openssl-selfsigned-cert__sXE9ZoE/result.json>)、[pypi-server](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-05-34/pypi-server__SzFsDEH/result.json>) |
| 0→0 | 4 | 两边都零分 | [gcode-to-text](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__03-57-56/gcode-to-text__igrmbEY/result.json>)、[protein-assembly](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__13-27-47/protein-assembly__mDbiyVc/result.json>)、[raman-fitting](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-53-54/raman-fitting__NhucZkQ/result.json>)、[winning-avg-corewars](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__16-10-28/winning-avg-corewars__8cG97ch/result.json>) |
| 0→NA | 4 | Astra 零分，Hermes 未评分 | [extract-moves-from-video](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__00-10-48/extract-moves-from-video__CTkXDwT/result.json>)、[install-windows-3.11](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__05-42-50/install-windows-3.11__mjR9MNB/result.json>)、[mailman](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__07-13-36/mailman__WzGfTVF/result.json>)、[path-tracing](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-35-33/path-tracing__99PefA4/result.json>) |
| 1→NA | 2 | Astra 通过，Hermes 未评分 | [git-multibranch](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-45-22/git-multibranch__annFNdb/result.json>)、[nginx-request-logging](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-45-39/nginx-request-logging__kHJx38i/result.json>) |

Astra 在这 46 项中的 17 个 `stream_transport` 零分，在 Hermes 中变为：**10 个通过、4 个零分、3 个未评分**。这表明 Hermes 当前显著减少了Astra 批次中的 stream/fallback 回传故障表现，但并没有把所有原 stream 零分都转化为成功。

5 个 1→0 回退分别是：`caffe-cifar-10`（训练未完成）、`compile-compcert`（deadline）、`configure-git-webserver` 和 `pypi-server`（后台服务被 cleanup）、`openssl-selfsigned-cert`（交付脚本依赖未随任务环境提供）。

### 5.3 同任务时间与资源

| 指标 | Astra 46 | Hermes 46 | Hermes/Astra 累计比 | 配对中位比 |
| --- | ---: | ---: | ---: | ---: |
| E2E 累计小时 | 22.159 | 15.131 | 0.683× | 0.767× |
| Agent 累计小时 | 18.907 | 13.978 | 0.739× | 0.844× |
| Fresh input | 2,367,786 | 2,389,438 | 1.009× | 1.020× |
| Cache-read | 13,272,128 | 48,312,320 | 3.640× | 3.211× |
| Input（含 cache） | 15,639,914 | 50,701,758 | 3.242× | 2.707× |
| Output | 1,854,598 | 1,238,955 | 0.668× | 0.549× |
| 总 token | 17,494,512 | 51,940,713 | 2.969× | 2.443× |
| 轮次/API 调用 | 865 | 1,465 | 1.694× | 1.646× |
| 工具返回 | 1,162 | 1,605 | 1.381× | 1.550× |
| 失败工具返回 | 97 | 174 | 1.794× | 1.750× |

- E2E：Astra **22.159h**，Hermes **15.131h**；Hermes 累计少 31.72%，典型任务的配对中位比为 0.767。
- 总 token：Astra **17,494,512**，Hermes **51,940,713**，Hermes 为 2.97 倍。
- Fresh input 几乎持平（1.009 倍），但 cache-read 为 3.64 倍；cache 占 input 从 Astra 的 **84.86%** 升至 Hermes 的 **95.29%**。
- Hermes output 只有 Astra 的 0.668 倍，但 API 轮次为 1.694 倍、工具返回为 1.381 倍：表现为更多轮、更短输出、更高上下文复用。
- 工具事件失败率：Astra 约 **8.35%**，Hermes 约 **10.84%**；两者事件定义不同，只能作为诊断指标。

### 5.4 失败模式发生了什么变化

| 维度 | Astra V1 56 | Hermes 当前 64 |
| --- | --- | --- |
| 明确 LLM/传输失败 | 22 个 `stream_transport` 零分，占零分 88.00% | 1 个 provider 明确无响应，占零分 4.55% |
| 异常但 reward 可得 | 6 个异常通过，Verifier 仍运行 | 2 个 timeout 通过；另有 7 个 adapter 异常完全无 reward |
| 后台服务生命周期 | 未形成主要零分类别 | 4 个服务在 gateway cleanup 后消失 |
| Deadline | 1 个预算耗尽异常通过，另有个别 verifier timeout | 7 个 product timeout：2 pass、5 zero；另有 2 个 timeout 被 adapter 异常覆盖 |
| 真实任务/性能失败 | 1 个明确任务失败 | 11 个任务交付、产物或性能失败 |
| Verifier infra | 1 个无 CTRF，1 个固定超时 | 1 个网络/uvx 故障无 CTRF |

本次观测的主要差异是 Hermes 批次很少出现 Astra 最突出的 stream/fallback 连接问题；同时暴露出新的系统边界：gateway 对工具后台进程的清理语义、cleanup report 缺失导致 Verifier 被跳过、以及更短或不同的 product deadline。

## 6. 重跑与处置建议

### 6.1 若目标是得到可信的探索性 reward

| 集合 | 数量 | 处置 |
| --- | ---: | --- |
| 已正常通过 | 33 | 保留 |
| Timeout 但通过 | 2 | 功能 reward 保留；严格 E2E 需要重跑 |
| 真实任务/性能失败 | 11 | 保留零分，不进入可靠性重跑队列 |
| Deadline 零分 | 5 | 若 deadline 是预先定义预算则保留；若配置不一致，统一后重跑 |
| 明确 provider 无响应 | 1 | 完整重跑；现有环境已结束，不能只恢复 LLM session |
| 后台服务被 cleanup | 4 | 修正 daemon 化方式后完整重跑 |
| Verifier infra | 1 | 优先重跑 Verifier；环境不可恢复时完整重跑 |
| 无 reward adapter/launcher 异常 | 7 | 完整重跑取得评分 |

因此，按与 Astra V1 相同的“只重跑可靠性或评估无效项”口径，**最低优先队列为 13 项**：1 个 provider 无响应、4 个后台生命周期失败、1 个 Verifier infra、7 个无 reward。5 个 deadline 零分是否重跑取决于deadline 是否属于预先冻结的实验预算。

如果采用更保守的“所有零分和无 reward 都重跑”策略，则为 **29 项**；若还要求两个 timeout-pass 具有干净终态，则为 **31 项**。

### 6.2 若目标是正式 C0

64/64 都是 `trigger_hit=false`、`lifecycle_gate_passed=false`、`formal_score_eligible=false`。Hermes controller 登记的是短生命周期的 `/run/rosetta/rosetta` wrapper；no-hit 分布为：`product_exited_before_noop=55`、`product_exited=2`、`controller_incomplete=7`。

如果目标是正式有效 C0，必须先修正 lifecycle process tracking，再重跑全部 64 项；当前 reward 只能保留为探索性诊断结果。典型证据：[controller 注册 wrapper](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/agent/controller.jsonl:6>)、[trigger no-hit](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/agent/controller.jsonl:7>)、[gate false](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/agent/controller.jsonl:10>)。

## 7. 解释限制

1. Astra 56 与 Hermes 64 都不是随机、完整的 89 项样本；Agent 能力比较必须以 46 项交集为主。
2. Hermes 明确使用 `zai/glm-5.2`、`max_turns=90`；Astra 的模型只保存为不透明 UUID，`max_turns=50`。更高的 Hermes 成功数不能单独归因于 runner。
3. 两边 product deadline 配置不同；Hermes 的部分回退直接来自 1,800/3,600/4,800 秒 deadline。
4. Astra 23 个 journal token 项是已落盘 usage 的可观测下界；Hermes 有 1 项没有 session/token。
5. API 轮次、工具失败是近似映射；不能做精确埋点级显著性结论。
6. CPU、RAM、GPU、磁盘 I/O、网络字节和实际美元成本均不可比较。
7. 46 项中 Hermes 有 6 项未评分；将它们算零分、排除或重跑会产生不同通过率，报告已分别列出。
8. 所有结果均不具正式 C0 资格，不能用于正式主榜或最终模型结论。

## 附录 A：Hermes 64 项明细

时间单位为分钟；Token 为 `fresh + cache + output`。

| # | 任务 | R | Product | 类别 | E2E | Agent | 总 token | API | 工具/失败 | Verifier | 建议 |
| ---: | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [adaptive-rejection-sampler](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__12-02-21/adaptive-rejection-sampler__RUDgwZK/result.json>) | 0 | `failed/rc2` | LLM/Provider 明确无响应 | 93.04 | 91.77 | 0 | 0 | 0/0 | 0/9 | LLM/provider 恢复后完整重跑 |
| 2 | [break-filter-js-from-html](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__13-38-01/break-filter-js-from-html__MhrC9uW/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 11.48 | 10.65 | 335,411 | 15 | 17/4 | 1/1 | 保留结果 |
| 3 | [build-pmars](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__13-52-02/build-pmars__d5SRCdf/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 5.48 | 4.92 | 1,017,745 | 41 | 38/2 | 4/4 | 保留结果 |
| 4 | [bn-fit-modify](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 5.86 | 4.87 | 260,796 | 13 | 12/3 | 9/9 | 保留结果 |
| 5 | [build-cython-ext](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-23-53/build-cython-ext__6BZKneV/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 23.11 | 22.60 | 4,063,645 | 80 | 132/10 | 11/11 | 保留结果 |
| 6 | [chess-best-move](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-02-59/chess-best-move__oL3Bfm6/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 15.22 | 14.26 | 320,837 | 15 | 14/1 | 1/1 | 保留结果 |
| 7 | [cobol-modernization](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-21-33/cobol-modernization__WBMseXk/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 17.93 | 17.32 | 1,573,510 | 54 | 58/6 | 3/3 | 保留结果 |
| 8 | [code-from-image](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-42-47/code-from-image__FSsBtAW/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 2.95 | 2.37 | 83,081 | 5 | 4/1 | 2/2 | 保留结果 |
| 9 | [winning-avg-corewars](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__16-10-28/winning-avg-corewars__8cG97ch/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 11.44 | 10.83 | 2,169,448 | 90 | 107/0 | 1/3 | 保留任务零分 |
| 10 | [build-pov-ray](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__16-55-07/build-pov-ray__XX7Q3Gy/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 39.30 | 38.21 | 2,202,644 | 55 | 58/6 | 2/3 | 保留任务零分 |
| 11 | [caffe-cifar-10](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__17-41-21/caffe-cifar-10__MyMkUd9/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 67.87 | 67.17 | 2,433,237 | 90 | 90/6 | 3/6 | 保留任务零分 |
| 12 | [compile-compcert](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__19-01-52/compile-compcert__THECWzy/result.json>) | 0 | `timeout/rc124` | Driver deadline，任务未完成 | 80.92 | 80.23 | 565,000 | 31 | 31/5 | 0/3 | 若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑 |
| 13 | [configure-git-webserver](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-30-38/configure-git-webserver__VuHrDDN/result.json>) | 0 | `completed/rc0` | 后台服务被 gateway cleanup 清理 | 3.33 | 2.50 | 333,538 | 19 | 18/1 | 0/1 | 使用独立 daemon 后完整重跑 |
| 14 | [constraints-scheduling](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-41-17/constraints-scheduling__cX4gLS6/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 4.80 | 3.87 | 135,244 | 6 | 8/1 | 3/3 | 保留结果 |
| 15 | [count-dataset-tokens](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-48-04/count-dataset-tokens__hSzRjmb/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 13.52 | 13.06 | 613,371 | 25 | 24/2 | 1/1 | 保留结果 |
| 16 | [crack-7z-hash](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-08-33/crack-7z-hash__hexw2DN/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 21.51 | 20.98 | 747,316 | 38 | 37/7 | 2/2 | 保留结果 |
| 17 | [custom-memory-heap-crash](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-37-12/custom-memory-heap-crash__bzdH3jy/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 10.08 | 9.09 | 700,781 | 28 | 39/0 | 6/6 | 保留结果 |
| 18 | [db-wal-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-54-42/db-wal-recovery__33DeyG7/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 27.55 | 26.63 | 3,411,792 | 76 | 75/8 | 7/7 | 保留结果 |
| 19 | [distribution-search](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__22-24-38/distribution-search__vcpnUUq/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 12.42 | 11.75 | 129,347 | 4 | 3/0 | 4/4 | 保留结果 |
| 20 | [dna-assembly](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__22-45-12/dna-assembly__uska5na/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 35.19 | 34.25 | 1,913,261 | 41 | 43/12 | 0/1 | 保留任务零分 |
| 21 | [dna-insert](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__23-29-41/dna-insert__3jGZkjs/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 12.41 | 11.85 | 961,823 | 35 | 34/4 | 0/1 | 保留任务零分 |
| 22 | [extract-elf](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__23-48-32/extract-elf__L78scP6/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 14.61 | 13.75 | 417,880 | 13 | 18/1 | 2/2 | 保留结果 |
| 23 | [extract-moves-from-video](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__00-10-48/extract-moves-from-video__CTkXDwT/result.json>) | — | `adapter_infra_error/rcnull` | Deadline 后 adapter 异常，无 Verifier | 60.52 | 60.21 | 992,878 | 42 | 42/9 | 无 CTRF | 完整重跑；若保留原 deadline，应将超时作为明确终态 |
| 24 | [feal-differential-cryptanalysis](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__01-13-23/feal-differential-cryptanalysis__cdkHeUK/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 6.43 | 5.67 | 278,879 | 13 | 12/2 | 1/1 | 保留结果 |
| 25 | [feal-linear-cryptanalysis](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__01-21-50/feal-linear-cryptanalysis__my336PY/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 19.08 | 18.62 | 15,792 | 1 | 3/0 | 0/1 | 保留任务零分 |
| 26 | [filter-js-from-html](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__01-42-23/filter-js-from-html__RdhDxsm/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 25.13 | 13.47 | 127,274 | 7 | 6/0 | 2/2 | 保留结果 |
| 27 | [financial-document-processor](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-15-56/financial-document-processor__xaV7aav/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 6.37 | 5.81 | 455,651 | 20 | 28/2 | 7/7 | 保留结果 |
| 28 | [fix-code-vulnerability](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-24-20/fix-code-vulnerability__Uo3XDpv/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 3.77 | 3.39 | 1,011,849 | 28 | 29/0 | 6/6 | 保留结果 |
| 29 | [fix-git](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-29-59/fix-git__v5ytDph/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 2.47 | 2.01 | 225,525 | 12 | 17/4 | 2/2 | 保留结果 |
| 30 | [fix-ocaml-gc](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-39-17/fix-ocaml-gc__KRpRZNt/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 76.63 | 53.41 | 3,396,198 | 59 | 62/9 | 1/1 | 保留结果 |
| 31 | [gcode-to-text](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__03-57-56/gcode-to-text__igrmbEY/result.json>) | 0 | `timeout/rc124` | Driver deadline，任务未完成 | 30.69 | 30.22 | 4,126,686 | 70 | 69/12 | 0/2 | 若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑 |
| 32 | [git-leak-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-35-51/git-leak-recovery__FSFqxjL/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 1.93 | 1.09 | 137,239 | 8 | 11/0 | 5/5 | 保留结果 |
| 33 | [git-multibranch](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-45-22/git-multibranch__annFNdb/result.json>) | — | `adapter_infra_error/rcnull` | Cleanup/adapter 异常，无 Verifier | 3.40 | 3.09 | 413,829 | 22 | 23/4 | 无 CTRF | 完整重跑以获得可评分结果 |
| 34 | [gpt2-codegolf](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-56-32/gpt2-codegolf__D7dv6Qz/result.json>) | 0 | `timeout/rc124` | Driver deadline，任务未完成 | 31.01 | 30.21 | 399,602 | 14 | 21/4 | 0/1 | 若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑 |
| 35 | [headless-terminal](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__05-29-30/headless-terminal__w4fJEGp/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 7.64 | 7.03 | 309,498 | 15 | 16/4 | 7/7 | 保留结果 |
| 36 | [install-windows-3.11](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__05-42-50/install-windows-3.11__mjR9MNB/result.json>) | — | `adapter_infra_error/rcnull` | Cleanup/adapter 异常，无 Verifier | 40.84 | 40.52 | 2,941,557 | 90 | 90/11 | 无 CTRF | 完整重跑以获得可评分结果 |
| 37 | [kv-store-grpc](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-25-39/kv-store-grpc__Ef67kGg/result.json>) | 0 | `completed/rc0` | 后台服务被 gateway cleanup 清理 | 3.64 | 3.22 | 286,172 | 15 | 15/1 | 5/7 | 使用独立 daemon 后完整重跑 |
| 38 | [large-scale-text-editing](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-31-20/large-scale-text-editing__RXziCtM/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 10.09 | 8.94 | 246,200 | 12 | 16/2 | 5/5 | 保留结果 |
| 39 | [llm-inference-batching-scheduler](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-44-32/llm-inference-batching-scheduler__fKWoNdN/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 21.61 | 21.15 | 1,798,643 | 37 | 38/4 | 6/6 | 保留结果 |
| 40 | [mailman](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__07-13-36/mailman__WzGfTVF/result.json>) | — | `adapter_infra_error/rcnull` | Cleanup/adapter 异常，无 Verifier | 14.36 | 14.05 | 3,207,777 | 70 | 76/16 | 无 CTRF | 完整重跑以获得可评分结果 |
| 41 | [make-doom-for-mips](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__07-29-59/make-doom-for-mips__Wjfu7d3/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 16.39 | 15.37 | 6,821,341 | 90 | 99/3 | 0/3 | 保留任务零分 |
| 42 | [make-mips-interpreter](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__07-48-27/make-mips-interpreter__MwMSXQK/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 23.95 | 22.91 | 6,807,364 | 90 | 115/2 | 0/3 | 保留任务零分 |
| 43 | [mcmc-sampling-stan](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__08-18-19/mcmc-sampling-stan__tJaMa3U/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 24.78 | 19.73 | 956,532 | 38 | 42/0 | 6/6 | 保留结果 |
| 44 | [merge-diff-arc-agi-task](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__08-50-54/merge-diff-arc-agi-task__vhnhmaK/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 6.94 | 6.11 | 517,349 | 22 | 21/1 | 5/5 | 保留结果 |
| 45 | [model-extraction-relu-logits](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__08-59-53/model-extraction-relu-logits__Y2jbEX7/result.json>) | 1 | `timeout/rc124` | 超时终止但通过 | 30.84 | 30.21 | 2,467,745 | 55 | 54/0 | 1/1 | 保留功能结果；严格 E2E 统计记为未成功 |
| 46 | [modernize-scientific-stack](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-32-29/modernize-scientific-stack__BA2S2GU/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 2.88 | 2.34 | 262,870 | 13 | 15/1 | 2/2 | 保留结果 |
| 47 | [multi-source-data-merger](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-40-03/multi-source-data-merger__mm3EWMs/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 3.58 | 3.03 | 193,071 | 10 | 11/3 | 3/3 | 保留结果 |
| 48 | [nginx-request-logging](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-45-39/nginx-request-logging__kHJx38i/result.json>) | — | `adapter_infra_error/rcnull` | Cleanup/adapter 异常，无 Verifier | 2.75 | 2.45 | 240,135 | 13 | 18/2 | 无 CTRF | 完整重跑以获得可评分结果 |
| 49 | [openssl-selfsigned-cert](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-50-26/openssl-selfsigned-cert__sXE9ZoE/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 2.04 | 1.59 | 73,145 | 4 | 4/0 | 5/6 | 保留任务零分 |
| 50 | [overfull-hbox](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-00-15/overfull-hbox__8TTwMxE/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 13.50 | 12.10 | 476,142 | 18 | 20/3 | 4/4 | 保留结果 |
| 51 | [password-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-22-47/password-recovery__7Y4d5e9/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 9.29 | 8.48 | 363,077 | 13 | 20/2 | 2/2 | 保留结果 |
| 52 | [path-tracing](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-35-33/path-tracing__99PefA4/result.json>) | — | `adapter_infra_error/rcnull` | Deadline 后 adapter 异常，无 Verifier | 60.56 | 60.23 | 3,358,468 | 58 | 58/8 | 无 CTRF | 完整重跑；若保留原 deadline，应将超时作为明确终态 |
| 53 | [path-tracing-reverse](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__11-44-49/path-tracing-reverse__bqaaCSt/result.json>) | 1 | `timeout/rc124` | 超时终止但通过 | 61.12 | 60.21 | 3,866,585 | 54 | 61/6 | 3/3 | 保留功能结果；严格 E2E 统计记为未成功 |
| 54 | [polyglot-c-py](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__12-52-58/polyglot-c-py__TW2ShP7/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 2.77 | 1.90 | 87,070 | 5 | 6/0 | 1/1 | 保留结果 |
| 55 | [polyglot-rust-c](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__13-03-48/polyglot-rust-c__h2GeXmG/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 6.99 | 6.07 | 104,470 | 5 | 4/0 | 1/1 | 保留结果 |
| 56 | [portfolio-optimization](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__13-12-48/portfolio-optimization__LWrHTUo/result.json>) | 1 | `completed/rc0` | 正常完成且通过 | 12.87 | 11.48 | 355,376 | 14 | 19/1 | 4/4 | 保留结果 |
| 57 | [protein-assembly](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__13-27-47/protein-assembly__mDbiyVc/result.json>) | 0 | `completed/rc0` | 任务交付或产物错误 | 20.33 | 19.85 | 1,941,838 | 40 | 44/6 | 0/1 | 保留任务零分 |
| 58 | [prove-plus-comm](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__13-59-51/prove-plus-comm__weWUbNV/result.json>) | — | `adapter_infra_error/rcnull` | Launcher/环境异常，无 Verifier | 0.59 | 0.06 | — | — | 0/0 | 无 CTRF | 修复 launcher/架构问题后完整重跑 |
| 59 | [pypi-server](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-05-34/pypi-server__SzFsDEH/result.json>) | 0 | `completed/rc0` | 后台服务被 gateway cleanup 清理 | 5.64 | 4.33 | 527,205 | 26 | 23/2 | 0/1 | 使用独立 daemon 后完整重跑 |
| 60 | [pytorch-model-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-20-57/pytorch-model-recovery__Nf3p9xm/result.json>) | 0 | `completed/rc0` | Verifier 基础设施失败 | 11.87 | 10.71 | 347,134 | 16 | 15/1 | 无 CTRF | 优先重跑 Verifier；若原环境不可恢复则完整重跑 |
| 61 | [qemu-alpine-ssh](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-36-17/qemu-alpine-ssh__7Aa9Evb/result.json>) | 0 | `timeout/rc124` | Driver deadline，任务未完成 | 30.99 | 30.24 | 2,019,865 | 73 | 74/7 | 0/1 | 若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑 |
| 62 | [qemu-startup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-09-06/qemu-startup__4pKPFNL/result.json>) | 0 | `completed/rc0` | 后台服务被 gateway cleanup 清理 | 12.70 | 11.71 | 693,106 | 34 | 33/2 | 0/1 | 使用 QEMU -daemonize 后完整重跑 |
| 63 | [query-optimize](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-29-40/query-optimize__GxjCVic/result.json>) | 0 | `completed/rc0` | 性能门槛未满足 | 20.79 | 10.92 | 210,079 | 11 | 15/1 | 5/6 | 保留任务零分 |
| 64 | [raman-fitting](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-53-54/raman-fitting__NhucZkQ/result.json>) | 0 | `timeout/rc124` | Driver deadline，任务未完成 | 30.72 | 30.22 | 998,237 | 29 | 28/4 | 1/3 | 若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑 |

## 附录 B：46 个同任务配对明细

| # | 任务 | Astra R | Hermes R | 转移 | Astra E2E | Hermes E2E | Astra token | Hermes token | Astra 工具 | Hermes 工具 |
| ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | [bn-fit-modify](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/result.json>) | 1 | 1 | `1->1` | 10.13 | 5.86 | 153,378 | 260,796 | 10 | 12 |
| 2 | [break-filter-js-from-html](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__13-38-01/break-filter-js-from-html__MhrC9uW/result.json>) | 1 | 1 | `1->1` | 6.80 | 11.48 | 145,127 | 335,411 | 10 | 17 |
| 3 | [build-cython-ext](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-23-53/build-cython-ext__6BZKneV/result.json>) | 1 | 1 | `1->1` | 18.98 | 23.11 | 1,289,818 | 4,063,645 | 62 | 132 |
| 4 | [build-pmars](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__13-52-02/build-pmars__d5SRCdf/result.json>) | 0 | 1 | `0->1` | 25.28 | 5.48 | 1,336,737 | 1,017,745 | 85 | 38 |
| 5 | [caffe-cifar-10](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__17-41-21/caffe-cifar-10__MyMkUd9/result.json>) | 1 | 0 | `1->0` | 70.06 | 67.87 | 1,166,021 | 2,433,237 | 74 | 90 |
| 6 | [chess-best-move](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-02-59/chess-best-move__oL3Bfm6/result.json>) | 0 | 1 | `0->1` | 15.06 | 15.22 | 80,036 | 320,837 | 8 | 14 |
| 7 | [cobol-modernization](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-21-33/cobol-modernization__WBMseXk/result.json>) | 1 | 1 | `1->1` | 12.18 | 17.93 | 244,012 | 1,573,510 | 15 | 58 |
| 8 | [code-from-image](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__15-42-47/code-from-image__FSsBtAW/result.json>) | 0 | 1 | `0->1` | 75.52 | 2.95 | 483,676 | 83,081 | 34 | 4 |
| 9 | [compile-compcert](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__19-01-52/compile-compcert__THECWzy/result.json>) | 1 | 0 | `1->0` | 46.26 | 80.92 | 658,930 | 565,000 | 54 | 31 |
| 10 | [configure-git-webserver](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-30-38/configure-git-webserver__VuHrDDN/result.json>) | 1 | 0 | `1->0` | 18.60 | 3.33 | 309,058 | 333,538 | 28 | 18 |
| 11 | [constraints-scheduling](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-41-17/constraints-scheduling__cX4gLS6/result.json>) | 1 | 1 | `1->1` | 4.88 | 4.80 | 63,309 | 135,244 | 5 | 8 |
| 12 | [count-dataset-tokens](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-48-04/count-dataset-tokens__hSzRjmb/result.json>) | 1 | 1 | `1->1` | 11.75 | 13.52 | 238,214 | 613,371 | 16 | 24 |
| 13 | [crack-7z-hash](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-08-33/crack-7z-hash__hexw2DN/result.json>) | 0 | 1 | `0->1` | 62.33 | 21.51 | 524,424 | 747,316 | 42 | 37 |
| 14 | [custom-memory-heap-crash](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-37-12/custom-memory-heap-crash__bzdH3jy/result.json>) | 1 | 1 | `1->1` | 197.55 | 10.08 | 951,592 | 700,781 | 65 | 39 |
| 15 | [db-wal-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__21-54-42/db-wal-recovery__33DeyG7/result.json>) | 1 | 1 | `1->1` | 3.05 | 27.55 | 101,529 | 3,411,792 | 8 | 75 |
| 16 | [distribution-search](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__22-24-38/distribution-search__vcpnUUq/result.json>) | 0 | 1 | `0->1` | 31.89 | 12.42 | 17,383 | 129,347 | 1 | 3 |
| 17 | [extract-elf](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__23-48-32/extract-elf__L78scP6/result.json>) | 0 | 1 | `0->1` | 17.23 | 14.61 | 116,160 | 417,880 | 11 | 18 |
| 18 | [extract-moves-from-video](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__00-10-48/extract-moves-from-video__CTkXDwT/result.json>) | 0 | — | `0->NA` | 49.61 | 60.52 | 830,937 | 992,878 | 58 | 42 |
| 19 | [feal-differential-cryptanalysis](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__01-13-23/feal-differential-cryptanalysis__cdkHeUK/result.json>) | 1 | 1 | `1->1` | 10.53 | 6.43 | 177,491 | 278,879 | 7 | 12 |
| 20 | [filter-js-from-html](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__01-42-23/filter-js-from-html__RdhDxsm/result.json>) | 0 | 1 | `0->1` | 9.71 | 25.13 | 14,226 | 127,274 | 1 | 6 |
| 21 | [financial-document-processor](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-15-56/financial-document-processor__xaV7aav/result.json>) | 1 | 1 | `1->1` | 16.48 | 6.37 | 259,140 | 455,651 | 15 | 28 |
| 22 | [fix-git](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-29-59/fix-git__v5ytDph/result.json>) | 1 | 1 | `1->1` | 3.96 | 2.47 | 170,955 | 225,525 | 16 | 17 |
| 23 | [fix-ocaml-gc](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__02-39-17/fix-ocaml-gc__KRpRZNt/result.json>) | 1 | 1 | `1->1` | 98.54 | 76.63 | 1,253,735 | 3,396,198 | 53 | 62 |
| 24 | [gcode-to-text](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__03-57-56/gcode-to-text__igrmbEY/result.json>) | 0 | 0 | `0->0` | 29.62 | 30.69 | 608,999 | 4,126,686 | 29 | 69 |
| 25 | [git-leak-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-35-51/git-leak-recovery__FSFqxjL/result.json>) | 1 | 1 | `1->1` | 4.22 | 1.93 | 126,084 | 137,239 | 10 | 11 |
| 26 | [git-multibranch](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-45-22/git-multibranch__annFNdb/result.json>) | 1 | — | `1->NA` | 16.36 | 3.40 | 928,991 | 413,829 | 60 | 23 |
| 27 | [headless-terminal](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__05-29-30/headless-terminal__w4fJEGp/result.json>) | 1 | 1 | `1->1` | 10.10 | 7.64 | 95,739 | 309,498 | 6 | 16 |
| 28 | [install-windows-3.11](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__05-42-50/install-windows-3.11__mjR9MNB/result.json>) | 0 | — | `0->NA` | 81.46 | 40.84 | 1,086,731 | 2,941,557 | 61 | 90 |
| 29 | [llm-inference-batching-scheduler](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-44-32/llm-inference-batching-scheduler__fKWoNdN/result.json>) | 0 | 1 | `0->1` | 13.82 | 21.61 | 37,387 | 1,798,643 | 4 | 38 |
| 30 | [mailman](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__07-13-36/mailman__WzGfTVF/result.json>) | 0 | — | `0->NA` | 20.14 | 14.36 | 336,160 | 3,207,777 | 38 | 76 |
| 31 | [mcmc-sampling-stan](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__08-18-19/mcmc-sampling-stan__tJaMa3U/result.json>) | 0 | 1 | `0->1` | 58.21 | 24.78 | 861,836 | 956,532 | 47 | 42 |
| 32 | [merge-diff-arc-agi-task](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__08-50-54/merge-diff-arc-agi-task__vhnhmaK/result.json>) | 1 | 1 | `1->1` | 49.37 | 6.94 | 307,878 | 517,349 | 23 | 21 |
| 33 | [modernize-scientific-stack](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-32-29/modernize-scientific-stack__BA2S2GU/result.json>) | 1 | 1 | `1->1` | 1.48 | 2.88 | 58,501 | 262,870 | 7 | 15 |
| 34 | [multi-source-data-merger](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-40-03/multi-source-data-merger__mm3EWMs/result.json>) | 1 | 1 | `1->1` | 5.18 | 3.58 | 112,730 | 193,071 | 8 | 11 |
| 35 | [nginx-request-logging](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-45-39/nginx-request-logging__kHJx38i/result.json>) | 1 | — | `1->NA` | 7.23 | 2.75 | 222,296 | 240,135 | 18 | 18 |
| 36 | [openssl-selfsigned-cert](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__09-50-26/openssl-selfsigned-cert__sXE9ZoE/result.json>) | 1 | 0 | `1->0` | 4.50 | 2.04 | 154,184 | 73,145 | 14 | 4 |
| 37 | [overfull-hbox](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-00-15/overfull-hbox__8TTwMxE/result.json>) | 0 | 1 | `0->1` | 12.58 | 13.50 | 61,042 | 476,142 | 7 | 20 |
| 38 | [password-recovery](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-22-47/password-recovery__7Y4d5e9/result.json>) | 1 | 1 | `1->1` | 14.96 | 9.29 | 343,777 | 363,077 | 25 | 20 |
| 39 | [path-tracing](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__10-35-33/path-tracing__99PefA4/result.json>) | 0 | — | `0->NA` | 85.78 | 60.56 | 220,798 | 3,358,468 | 15 | 58 |
| 40 | [path-tracing-reverse](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__11-44-49/path-tracing-reverse__bqaaCSt/result.json>) | 0 | 1 | `0->1` | 30.89 | 61.12 | 557,156 | 3,866,585 | 29 | 61 |
| 41 | [polyglot-c-py](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__12-52-58/polyglot-c-py__TW2ShP7/result.json>) | 1 | 1 | `1->1` | 4.57 | 2.77 | 47,660 | 87,070 | 4 | 6 |
| 42 | [portfolio-optimization](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__13-12-48/portfolio-optimization__LWrHTUo/result.json>) | 0 | 1 | `0->1` | 8.39 | 12.87 | 19,114 | 355,376 | 6 | 19 |
| 43 | [protein-assembly](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__13-27-47/protein-assembly__mDbiyVc/result.json>) | 0 | 0 | `0->0` | 17.14 | 20.33 | 349,848 | 1,941,838 | 39 | 44 |
| 44 | [pypi-server](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-05-34/pypi-server__SzFsDEH/result.json>) | 1 | 0 | `1->0` | 2.59 | 5.64 | 129,022 | 527,205 | 14 | 23 |
| 45 | [raman-fitting](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-53-54/raman-fitting__NhucZkQ/result.json>) | 0 | 0 | `0->0` | 24.71 | 30.72 | 212,479 | 998,237 | 12 | 28 |
| 46 | [winning-avg-corewars](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__16-10-28/winning-avg-corewars__8cG97ch/result.json>) | 0 | 0 | `0->0` | 9.89 | 11.44 | 30,212 | 2,169,448 | 8 | 107 |

## 附录 C：机器可读数据

- Hermes 64 项 CSV：[hermes-c0-current-64-tasks-v1.csv](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/analysis/v1/hermes-c0-current-64-tasks-v1.csv>)
- 46 项配对 CSV：[hermes-vs-astra-matched-46-tasks-v1.csv](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/analysis/v1/hermes-vs-astra-matched-46-tasks-v1.csv>)
- 聚合 JSON：[hermes-vs-astra-current-summary-v1.json](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/analysis/v1/hermes-vs-astra-current-summary-v1.json>)
- 可复现分析脚本：[analyze_hermes_astra_current.py](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/analysis/v1/analyze_hermes_astra_current.py>)

