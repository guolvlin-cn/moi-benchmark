# Astra 评测计划总体进度与 Terminal-Bench 阶段性结果

> 日期：2026-07-31  
> 计划版本：[v0.5 草稿](../plans/drafts/v0.5.md)  
> 状态：评测方案与工程门禁建设中，尚无正式可发布的跨产品主结果  
> 当前结果范围：Astra 与 Hermes 的 Terminal-Bench 2.1 生命周期无故障条件工程预运行  
> Hermes 数据截止：2026-07-31 16:46:44 +08:00

Hermes 数字是固定的 64 项终态快照；截止时间之后新完成的任务不追写进该分母，应在增量复核后形成下一版快照。

## 1. 总体定位

Astra 的总体评测不等于一次 Terminal-Bench 批次。当前计划由三层组成：

1. 公共 Benchmark 上的任务完成、可靠性和资源效率；
2. 同任务无故障/单故障配对的生命周期韧性；
3. 后续 Astra 机制归因与权限、安全边界实验。

当前已经产生的 Astra 56 项、Hermes 64 项和 46 项同任务比较，只属于第一层中 **Terminal-Bench 2.1 全集生命周期无故障轨的工程预运行证据**。它们不表示以下里程碑已经完成：

- Astra 总体评测；
- Terminal-Bench 89 题正式有效运行；
- Terminal-Bench 单故障注入配对实验；
- SWE-bench-Live 泛化运行；
- Astra、Hermes、Goose 的公平、因果性产品比较。

当前预运行的主要价值是验证 Runner、日志、Token、工具、Verifier 和失败归因链路，并暴露正式运行前必须关闭的生命周期与连接可靠性问题。

## 2. 评测组合与总体进度

| 评测轨/工作流 | 计划范围 | 当前证据 | 状态 | 正式有效性 | 下一门禁 |
| --- | --- | --- | --- | --- | --- |
| 方案冻结 | 数据集、系统、模型、预算、条件、指标和结论边界 | v0.5 已按最新方向形成草稿 | 进行中 | 未冻结 | 审阅并批准 v0.5；冻结重复次数和故障目录 |
| Terminal-Bench 全集无故障轨 | 三产品完成 89 题生命周期无故障正式运行 | Astra 已尝试 89 题；56 个轨迹可分析、33 题需从头重跑。Hermes 冻结快照有 64 题终态 | 工程预运行已有证据 | 已分析结果均未通过 lifecycle gate | 修正真实产品进程 tracking，统一配置后执行正式全量运行 |
| Terminal-Bench 故障韧性轨 | 预注册 Base Task 的同题无故障/单故障配对；当前规划值为 12，尚未冻结 | 尚无冻结 Task/Fault Manifest 或正式配对运行 | 未开始 | 不适用 | 按元数据和故障兼容性选题；不得按当前 reward 选题 |
| 第二数据集方向 | 初步选择 SWE-bench-Live Python `verified`；任务数和条件尚未定义 | GDPval/SWE-bench 研究审计已完成 | 方向已记录，执行计划暂缓 | 不适用 | 后续另行冻结协议，不进入当前关键路径 |
| 跨产品公平比较 | Astra、Hermes、Goose 的等价配置对比 | 仅有 Astra/Hermes 46 题非等价配置交集 | 探索性 | 不具因果排名资格 | 冻结模型、轮次、deadline、重试、工具和权限 |
| Astra 机制归因 | Git4Data、Observation/Reflection、Privacy/Authority 受控实验 | 已有研究设计，未进入本轮公共 Benchmark 执行 | 后续阶段 | 不适用 | 在公共任务结果之后另立对照/消融计划 |
| 正式报告 | 当前先形成三个 Terminal-Bench 面板、区间、失败分类、数据卡和复现包 | 已有 Markdown、CSV、JSON 与分析脚本基础 | 未开始正式冻结 | 无正式主结果 | Terminal-Bench validity gate 通过后发布 |

因此，当前不能只用一个条件代码描述总体进度。应分别报告：

- 运行覆盖了多少任务；
- 多少任务产生可分析轨迹；
- 多少任务通过上游 Verifier；
- 多少任务达到严格端到端成功；
- 多少任务满足生命周期和实验有效性门禁；
- 每条 Benchmark 轨是否已开始、冻结或完成。

## 3. 第二数据集方向

当前初步选择 **SWE-bench-Live Python `verified`** 作为第二公共数据集方向，而不是 GDPval。本轮不进一步冻结 SWE-bench-Live 的任务数、条件、Adapter、重复次数或运行计划。

选择依据：

- FAIL_TO_PASS 与 PASS_TO_PASS 提供执行式、可复核的最终 Oracle；
- base commit、test patch、Harness 和 Docker image 可以冻结；
- 更容易把任务失败、生命周期故障、Runner 失败和评分失败分开归因；
- 后续可以补充真实仓库修复证据，但如何与 Terminal-Bench 对照尚未定义。

放弃的边际收益和保留边界：

- SWE-bench-Live 与 Terminal-Bench 都偏软件工程，不能把结果外推到通用知识工作；
- GDPval 覆盖 44 个职业和多模态专业产物，领域更宽，但当前 canonical 本地评分缺失、托管 grader 已停止、35 题没有公开 deliverable，且许可仍不清晰；
- GDPval 保留为后续专业产物质量专项，待评分器、人工校准、附件和许可问题关闭后再接入。

相关依据：

- [SWE-bench-Live `verified` 数据集分析](../research/swe-bench-live-verified-dataset-analysis.md)
- [GDPval 数据集分析](../research/gdpval-dataset-analysis.md)

## 4. 统一结果口径

### 4.1 四个任务结果层级

| 层级 | 判定 | 含义 |
| --- | --- | --- |
| Verifier 功能性通过 | `reward=1` 或等价执行式 Oracle 通过 | 最终环境或工件正确，不要求 Agent 正常退出 |
| 产品正常终态 | `product_terminal_status=completed && rc=0` | Agent 正常退出，不保证任务要求已满足 |
| 严格端到端成功 | 产品正常终态且 Verifier 通过 | 当前公共任务的主要端到端指标 |
| 正式有效任务 | lifecycle、配置、Runner、环境和 Verifier 门禁全部通过 | 可以进入正式发布结果 |

异常终止仍可能通过，是因为 Verifier 检查最终环境和工件；Agent 可能在 timeout、连接故障或 cleanup 异常前已经完成任务。反过来，Agent 正常退出也可能未满足任务要求。

### 4.2 正式 89 题分母

正式全量运行将同时报告：

- `outcome_coverage = 有效结果任务数 / 89`；
- `full_frame_lower_bound = 严格成功任务数 / 89`，作为包含未解决无效项的保守下界；
- `valid_run_success = 严格成功任务数 / 有效结果任务数`，必须与 coverage 和无效根因并列。

产品、模型、deadline 和任务失败属于有效结果中的失败；只有实验故障域外且有独立证据的 Runner、环境或 Verifier 无效才退出有效结果分母。当前 56/64 快照不满足正式门禁，因此不计算上述正式估计。

### 4.3 条件命名

- **Source-clean（S0）**：完整上游 Harness，不经过生命周期包装；当前用于 Terminal-Bench Wrapper parity，第二数据集如何使用尚未冻结；
- **生命周期无故障条件（C0）**：Lifecycle Wrapper、触发检测和采集全部开启，但故障动作是 no-op；
- **单故障注入条件（F1）**：同一 Base Task、相同配置，只开启一个预注册故障；
- 代码标识可以保留在目录和 Schema 中，但结果标题必须同时给出数据集、样本范围和完整条件名称；
- 当前结果应称为“Terminal-Bench 2.1 生命周期无故障条件工程预运行”。

### 4.4 Token、时间与工具

- `input_tokens = fresh_input_tokens + cache_read_tokens`；
- `total_tokens = input_tokens + output_tokens`；
- reasoning token 是 output 的补充分拆，不重复计入 total；
- 时间按任务阶段累计，不等于并发批次真实 wall-clock；
- Astra 的轮次主要来自 `StepStarted` 或中断记录，Hermes 使用 session `api_call_count`；
- Astra 工具失败来自 `ToolCallFailed`，Hermes 来自 `tool.completed.error=true`，只能近似比较；
- CPU、RAM、GPU、磁盘 I/O、网络字节和实际美元成本目前没有可靠可比数据。

## 5. Terminal-Bench 全集无故障轨：当前工程预运行

### 5.1 结果快照

| 快照 | 当前样本 | Verifier 通过 | 严格端到端成功 | 正式有效任务 |
| --- | ---: | ---: | ---: | ---: |
| Astra 工程运行 | 56 个可分析轨迹 | 31/56 | 25/56 | 0/56 |
| Hermes 工程快照 | 64 个终态任务 | 35/64；在 57 个已评分任务中为 35/57 | 33/64 | 0/64 |
| 同任务交集 | 46 个任务 | Astra 26；Hermes 31 | Astra 20；Hermes 30 | 两边均不具正式资格 |

这些分母不同且均未通过生命周期门禁，只能用于工程诊断和观察性比较。

### 5.2 Astra：89 题尝试中的 56 个可分析轨迹

| 项目 | 数量 |
| --- | ---: |
| 初始尝试任务 | 89 |
| 必须从头重跑 | 33 |
| 当前可分析轨迹 | 56 |
| Verifier 通过 | 31 |
| `reward=0`（Verifier 未通过） | 25 |
| 产品正常终态 | 27 |
| 严格端到端成功 | 25 |
| 正式有效任务 | 0 |

56 项是排除 33 个必须完整重启任务后的条件样本，不是完整或随机的 89 题样本。

失败与处置：

| 类别 | 数量 | 当前处理 |
| --- | ---: | --- |
| 正常完成且通过 | 25 | 保留工程功能结果 |
| 异常终止但通过 | 6 | 保留功能结果，单列异常终态 |
| LLM `stream_transport` 中断且可恢复 | 22 | 恢复原 session 后重新执行后续步骤与 Verifier |
| 任务要求未满足 | 1 | 保留真实任务失败 |
| Verifier 固定超时 | 1 | 调整统一 Verifier 策略后重评 |
| 预算耗尽并叠加 Verifier infra | 1 | 优先在现有 artifact 上重跑 Verifier |

25 个 Verifier 未通过任务中，22 个带 checkpoint、可恢复原 session 的 LLM stream/fallback 失败，占 88.00%。它们说明当前产品栈/连接可靠性失败，但不能简单解释为模型任务能力失败，也不应丢弃已经完成的工具操作后从头重复执行。

### 5.3 Astra 资源

| 指标 | 56 项合计 |
| --- | ---: |
| 累计 E2E | 25.483 task-hours |
| 累计 Agent 执行 | 21.956 agent-hours |
| Fresh input | 2,609,838 |
| Cache-read | 14,853,952 |
| Output | 2,047,295 |
| 总 Token | 19,511,085 |
| Agentic 轮次 | 970 |
| 工具调用 | 1,282 |
| 失败工具返回 | 101 |

22 个可恢复 stream failure 已经消耗：

- 10.347 agent-hours；
- 4,352,597 input token；
- 693,534 output token；
- 265 轮；
- 373 次工具调用。

这部分已投入资源是“恢复原 session”优于“从头重启任务”的直接工程依据。

### 5.4 Hermes：64 项终态快照

| 指标 | 数量 | 比例 |
| --- | ---: | ---: |
| 终态任务 | 64 | — |
| Verifier 通过 / 全部终态 | 35/64 | 54.69% |
| Verifier 通过 / 已评分 | 35/57 | 61.40% |
| `reward=0`（Verifier 未通过） | 22/64 | 34.38% |
| 未产生可评分结果 | 7/64 | 10.94% |
| 产品正常终态 | 49/64 | 76.56% |
| 严格端到端成功 | 33/64 | 51.56% |
| 异常终止但通过 | 2/64 | 3.13% |
| 正式有效任务 | 0/64 | 0.00% |

产品终态为：

- `completed/rc0`：49，其中 33 个通过、16 个 Verifier 未通过；
- `timeout/rc124`：7，其中 2 个通过、5 个 Verifier 未通过；
- `failed/rc2`：1，Verifier 未通过；
- `adapter_infra_error`：7，全部未产生 reward。

Hermes 失败根因：

| 类别 | 数量 | 处置 |
| --- | ---: | --- |
| 正常完成且通过 | 33 | 保留 |
| Timeout 但通过 | 2 | 保留功能结果；严格终态单列 |
| LLM/provider 明确无响应 | 1 | Provider 恢复后从头重跑 |
| Driver deadline，任务未完成 | 5 | 若 deadline 是冻结预算则保留，否则统一配置后重跑 |
| 任务工件或交付错误 | 10 | 保留真实任务失败 |
| 性能门槛失败 | 1 | 保留真实任务失败 |
| 后台服务被 gateway cleanup 清理 | 4 | 冻结可跨 cleanup 存活的服务语义后重跑 |
| Verifier 基础设施失败 | 1 | 优先重跑 Verifier |
| Deadline 后 adapter 异常 | 2 | 完整重跑并保留明确 timeout 终态 |
| Cleanup/adapter 异常 | 4 | 完整重跑取得评分 |
| Launcher/环境异常 | 1 | 修复启动问题后重跑 |

当前只有 `adaptive-rejection-sampler` 有明确的 provider 无响应日志。`gpt2-codegolf` 只记录 `ProductDeadlineExpired`，因此不能在缺乏 transport 证据时计为明确 LLM 连接失败。

四个后台生命周期失败任务是：

- `configure-git-webserver`；
- `kv-store-grpc`；
- `pypi-server`；
- `qemu-startup`。

它们在 Agent 会话内启动过服务，但服务由 Hermes gateway 管理；`run.completed` 后 gateway shutdown 清理进程，Verifier 随后无法连接。

### 5.5 Hermes 资源与 Verifier

- 56/64 生成 CTRF；
- 合计 193 tests：152 pass、41 fail；
- `reward=1` 的任务对应 130/130 tests 通过；
- `reward=0` 且有 CTRF 的任务对应 22/63 tests 通过；
- 8 项没有 CTRF，其中 7 项未产生 reward，另 1 项为 `pytorch-model-recovery` 的 Verifier 网络/依赖失败。

| 指标 | 64 项合计 |
| --- | ---: |
| 累计 E2E | 21.842 task-hours |
| 累计 Agent 执行 | 20.289 agent-hours |
| Fresh input | 3,339,004 |
| Cache-read | 73,233,280 |
| Output | 1,876,876 |
| 总 Token | 78,449,160 |
| API/Agentic 轮次 | 2,040 |
| 工具完成返回 | 2,233 |
| 失败工具返回 | 219 |
| 工具累计执行 | 8.050 小时 |

Cache-read 占 Hermes input 的 95.64%。31 个非严格成功任务消耗约 53.34M token，占可观测总 Token 的 67.99%。

## 6. Astra 与 Hermes 的同任务观察性比较

Hermes 64 项与 Astra 56 项共有 46 个相同任务。只有该交集可以做同任务描述；由于模型、轮次、deadline、工具和生命周期门禁尚未等价，它仍不是因果性产品排名。

### 6.1 任务结果

| 指标 | Astra 46 | Hermes 46 |
| --- | ---: | ---: |
| Verifier 通过 | 26/46（56.52%） | 31/46（67.39%） |
| 严格端到端成功 | 20/46（43.48%） | 30/46（65.22%） |
| Hermes 有 reward 的 40 项 | Astra 24/40（60.00%） | Hermes 31/40（77.50%） |
| 未产生 reward | 0 | 6 |

任务结果转移：

| 转移 | 数量 |
| --- | ---: |
| Astra 通过 → Hermes 通过 | 19 |
| Astra 未通过 → Hermes 通过 | 12 |
| Astra 通过 → Hermes 未通过 | 5 |
| Astra 未通过 → Hermes 未通过 | 4 |
| Astra 未通过 → Hermes 未产生 reward | 4 |
| Astra 通过 → Hermes 未产生 reward | 2 |

Astra 在这 46 项中有 17 个 `stream_transport` 导致的 Verifier 未通过；对应 Hermes 有 10 个通过、4 个未通过、3 个未产生 reward。Hermes 当前较少复现 Astra 的 stream/fallback 连接故障，但并未把全部相关任务转化为成功。

### 6.2 同任务时间与资源

| 指标 | Astra 46 | Hermes 46 | Hermes/Astra |
| --- | ---: | ---: | ---: |
| 累计 E2E | 22.159 小时 | 15.131 小时 | 0.683× |
| 累计 Agent 执行 | 18.907 小时 | 13.978 小时 | 0.739× |
| Fresh input | 2,367,786 | 2,389,438 | 1.009× |
| Cache-read | 13,272,128 | 48,312,320 | 3.640× |
| Input | 15,639,914 | 50,701,758 | 3.242× |
| Output | 1,854,598 | 1,238,955 | 0.668× |
| 总 Token | 17,494,512 | 51,940,713 | 2.969× |
| 轮次/API 调用 | 865 | 1,465 | 1.694× |
| 工具调用 | 1,162 | 1,605 | 1.381× |
| 失败工具返回 | 97 | 174 | 1.794× |

阶段性观察：

- Hermes 累计 E2E 时间少 31.72%；
- Hermes 总 Token 约为 Astra 的 2.97 倍；
- 两边 fresh input 基本持平，Token 增量主要来自 Hermes cache-read；
- Hermes 使用更多 API 轮次和工具调用，但总 output 更少；
- 当前现象更接近两套原生产品栈的执行风格差异，不能单独归因于 Agent 架构。

主要混杂：Hermes 使用 `zai/glm-5.2`、`max_turns=90`；Astra 保存的是不透明模型 UUID、`max_turns=50`；两边 product deadline、工具 Schema、上下文管理和 Runner 均未完成等价冻结。

## 7. Terminal-Bench 无故障轨的正式有效性阻塞

当前 Astra 56 项和 Hermes 64 项均没有满足正式有效性门禁的结果：

- `trigger_hit=false`；
- `lifecycle_gate_passed=false`；
- `formal_score_eligible=false`。

Hermes 64 项的 controller 登记的是短生命周期 `/run/rosetta/rosetta` wrapper，而不是持续运行的真实产品进程。Trigger no-hit 分布为：

- `product_exited_before_noop`：55；
- `product_exited`：2；
- `controller_incomplete`：7。

因此：

- 当前 reward 只能用于探索性任务效果、效率和可靠性诊断；
- 正式运行前必须修正真实产品进程识别和 lifecycle tracking；
- 修正后需要重新执行正式样本，不能把当前探索性结果事后升级为正式结果。

## 8. 其他评测轨的当前状态

### 8.1 Terminal-Bench 单故障注入轨

当前尚未完成：

- 故障 Base Task、Reserve 和 Smoke 的最终数量冻结；当前规划值为 12/4/2；
- task × fault 兼容矩阵；
- Fault Manifest、触发谓词和独立 Ground Truth；
- 无故障/单故障配对的 replay；
- fault-hit、恢复、重复副作用和 false-complete 统计。

选题必须根据任务类别、复杂度、操作链、稳定触发点和故障兼容性完成。当前 Astra/Hermes 的 reward 和失败任务列表不得参与抽样。

### 8.2 第二数据集方向

已完成 GDPval 与 SWE-bench-Live 的研究审计，并初步选择 SWE-bench-Live Python `verified` 作为第二数据集方向。

当前没有冻结：任务数、任务 ID、实验条件、重复次数、Adapter、镜像、有效分母、运行预算和时间表。因此该轨道只记为“方向已确认、执行计划待定”，不计入当前完成度或 Terminal-Bench 关键路径。

### 8.3 Astra 机制归因轨

Git4Data、Observation/Reflection、Privacy/Authority 已有研究设计，但不是当前 Terminal-Bench 运行的一部分。公共 Benchmark 结果完成后，仍需通过相同模型/工具/预算的受控对照或 Astra 内部消融验证机制增益。

## 9. 重跑与恢复队列

### 9.1 Astra 工程恢复

| 集合 | 数量 | 处理 |
| --- | ---: | --- |
| 初始必须从头重跑 | 33 | 修复环境、launcher、无 checkpoint 等问题后完整重跑 |
| 可恢复 stream failure | 22 | 恢复原 session，不从头丢弃现场 |
| 正常或异常但已通过 | 31 | 保留工程功能结果 |
| 真实任务失败 | 1 | 保留 |
| Verifier 超时 | 1 | 优先只重跑 Verifier |
| 预算耗尽 + Verifier infra | 1 | 先重跑 Verifier，必要时同预算完整重跑 |

### 9.2 Hermes 工程恢复

最低可靠性无效队列为 13 项：

- 1 个明确 provider 无响应；
- 4 个后台服务生命周期失败；
- 1 个 Verifier infra；
- 7 个未产生 reward 的 adapter/launcher 异常。

若全部 22 个 Verifier 未通过和 7 个未产生 reward 都重跑，则为 29 项；若还要求两个 timeout-pass 取得正常终态，则为 31 项。5 个 deadline 失败是否允许重跑，取决于 deadline 是否属于预先冻结的实验预算，不能看到结果后只为失败任务延长。

### 9.3 正式运行与工程恢复的区别

上述恢复用于理解和修复工程问题。由于当前所有已审计结果都没有通过 lifecycle gate，正式 Terminal-Bench 全集无故障轨仍需要在版本和配置冻结后重新执行，不能把“工程恢复完成”等同于“正式结果完成”。

## 10. 关键路径与下一里程碑

按依赖顺序：

1. 审阅并批准 v0.5 的总体范围；
2. 修正真实产品进程 tracking 和生命周期门禁；
3. 冻结三产品模型、轮次、deadline、工具权限、重试和后台服务语义；
4. 完成 Astra 的 33 项从头重跑和 22 项原 session 恢复，用于验证工程修复；
5. 对 Hermes 新完成任务做增量分类并冻结最终工程快照；
6. 在任何正式产品结果产生前冻结 Terminal-Bench 故障子集最终数量及 Task/Fault Manifest；
7. 三产品通过等价 Smoke 后，执行 Terminal-Bench 89 题正式生命周期无故障运行；
8. 执行 Terminal-Bench 同任务单故障配对；
9. 生成三个 Terminal-Bench 结果面板、区间、失败 taxonomy、数据卡和复现包；
10. SWE-bench-Live 的执行计划在本轮进度确认之后另行制定。

已识别但未实施的工程要求：

- 将 LLM non-stream fallback timeout 从 120 秒提高到 600 秒；
- 外层 Runner 对 `stream_transport` 自动恢复原 session，统一允许 1–2 次重试；
- 恢复不得重复执行已完成且可能有副作用的工具调用；
- 修正 Rosetta wrapper 下真实产品进程的 lifecycle tracking；
- 冻结后台服务跨 gateway cleanup 的存活语义；
- 让 cleanup report 缺失保留原始产品终态；
- 为 Verifier 下载、`uvx` 和固定超时建立预检与独立重评流程。

本轮仅更新评测计划和进度文档，**没有修改 Astra 源码**。

## 11. 当前已形成资产

### 总体计划与数据研究

- [Astra 评测计划 v0.5](../plans/drafts/v0.5.md)
- [Terminal-Bench 2.1 任务调查](../research/terminal-bench-2.1-task-survey.md)
- [SWE-bench-Live `verified` 数据集分析](../research/swe-bench-live-verified-dataset-analysis.md)
- [GDPval 数据集分析](../research/gdpval-dataset-analysis.md)

### Astra 工程运行

- [Astra 56 项 V1 主报告](../../work/astra-c0-all-jobs/2026-07-29__19-36-33/analysis/v1/astra-c0-56-tasks-statistics-v1.md)
- [Astra 56 项 CSV](../../work/astra-c0-all-jobs/2026-07-29__19-36-33/analysis/v1/astra-c0-56-tasks-statistics-v1.csv)
- [Astra 56 项聚合 JSON](../../work/astra-c0-all-jobs/2026-07-29__19-36-33/analysis/v1/astra-c0-56-tasks-statistics-v1-summary.json)

### Hermes 与同任务比较

- [Hermes 当前结果与 Astra 交叉报告](../../work/hermes-c0-all-jobs/analysis/v1/hermes-current-vs-astra56-comparison-v1.md)
- [Hermes 64 项 CSV](../../work/hermes-c0-all-jobs/analysis/v1/hermes-c0-current-64-tasks-v1.csv)
- [Astra/Hermes 46 项配对 CSV](../../work/hermes-c0-all-jobs/analysis/v1/hermes-vs-astra-matched-46-tasks-v1.csv)
- [交叉统计聚合 JSON](../../work/hermes-c0-all-jobs/analysis/v1/hermes-vs-astra-current-summary-v1.json)
- [可复现分析脚本](../../work/hermes-c0-all-jobs/analysis/v1/analyze_hermes_astra_current.py)

原始工作目录沿用历史 `*-c0-*` 命名，这是既有文件路径，不代表本文继续使用缺少上下文的结果称呼。

## 12. 当前可得结论与禁止结论

当前证据支持：

1. Astra 的当前主要工程可靠性问题是 LLM stream/fallback 回传中断；22 个未通过任务具有可恢复原 session 的证据；
2. Hermes 当前明确 provider 无响应较少，但出现后台服务被 gateway cleanup、cleanup report 缺失、deadline 和高 cache-read 消耗等不同失败模式；
3. 在 46 个同任务的非等价配置观察中，Hermes 的 Verifier 通过和严格成功更多、累计时间更少，但总 Token 约为 Astra 的三倍；
4. 当前两边的生命周期采集都无效，因此这些现象只能帮助修复工程和设计正式实验。

当前禁止：

- 把 Astra 31/56、Hermes 35/64 写成完整 Terminal-Bench 或 Astra 总体表现；
- 把 46 项交集写成产品能力的因果排名；
- 把 lifecycle gate 未通过的 reward 升级为正式生命周期无故障结果；
- 用当前成功、失败或连接异常任务选择后续故障注入样本；
- 把 Terminal-Bench 结果推广为通用知识工作或企业 Agent 结论；
- 把未来 MOI-derived 故障结果写成上游官方排行榜成绩。
