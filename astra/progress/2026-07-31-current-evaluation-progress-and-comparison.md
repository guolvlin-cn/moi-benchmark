# 当前评测整体进度与 Astra / Hermes 阶段性对比

> 日期：2026-07-31  
> 状态：工程预运行结果；不是正式发布结果或产品能力排名  
> 数据快照：Astra 完成首轮 89 题尝试；Hermes 截止 2026-07-31 16:46:44 +08:00 的 64 题终态快照

## 1. 整体评测计划

本计划考察 Astra、Hermes、Goose 三个 Agent 产品在公共任务中的任务完成、运行可靠性与资源效率，并在后续通过受控故障和机制实验定位能力边界。评测分为三个层次：

1. **公共 Benchmark 无故障运行**：在相同任务上观察任务完成、正常退出、时间、Token、轮次、工具调用和失败类型；
2. **Terminal-Bench 单故障配对**：对预先选定任务，在同一配置下比较生命周期无故障条件与单一故障注入条件，衡量触发、恢复、重复副作用和误完成；
3. **Astra 机制归因**：在公共结果之后，通过受控对照或消融验证 Git4Data、Observation/Reflection、Privacy/Authority 等机制的贡献。

### 1.1 系统范围

| 系统 | 当前角色 | 当前状态 |
| --- | --- | --- |
| Astra | 主要受测对象 | Terminal-Bench 首轮 89 题已运行，工程恢复与正式重跑待进行 |
| Hermes | 竞品对照 | 仍在运行；本文件使用固定的 64 题终态快照 |
| Goose | 竞品对照 | 尚无可分析运行数据 |

### 1.2 数据集与工作流

| 数据集/轨道 | 目的 | 当前状态 |
| --- | --- | --- |
| Terminal-Bench 2.1 全集无故障轨 | 三产品全量 89 题的端到端、可靠性和效率基线 | 当前 Astra/Hermes 仅为工程预运行；正式等价运行尚未开始 |
| Terminal-Bench 2.1 单故障注入轨 | 同任务无故障/单故障配对，评估生命周期韧性 | 未开始；Task/Fault Manifest、兼容矩阵和样本数尚未冻结 |
| SWE-bench-Live Python `verified` | 第二公共数据集方向，用于可复核软件修复任务 | 已完成方向选择；任务数、条件、Adapter、重复次数和时间表尚未定义 |
| Astra 机制归因轨 | 验证 Astra 内部机制，不与公共 Benchmark 结果混用 | 有研究设计，尚未执行 |

Terminal-Bench 的正式无故障运行采用生命周期包装，但故障动作必须为 no-op；故障注入仅适用于预注册的配对样本。任何含故障注入的结果均是 MOI 派生评测结果，不应称为上游官方排行榜成绩。

## 2. 当前进度

当前进度属于 **Terminal-Bench 2.1 全集生命周期无故障条件的工程预运行**，而不是整个 Astra 评测计划的完成状态。

| 项目 | 当前进度 | 结果资格 |
| --- | --- | --- |
| Astra | 已完成第一轮 89 题尝试；56 个轨迹可分析，33 题需从头重跑 | 仅工程诊断；56 项均未通过 lifecycle gate |
| Hermes | 仍在运行；冻结快照中有 64 个终态任务 | 仅工程诊断；64 项均未通过 lifecycle gate |
| Astra vs Hermes | 46 个同任务交集可做观察性描述 | 非等价配置，不能作因果性排名 |
| Goose | 尚未启动可比运行 | 无 |
| Terminal-Bench 故障轨 | 未开始 | 无 |
| 第二数据集 | 仅完成 SWE-bench-Live 方向选择 | 无 |

当前生命周期门禁未通过的原因是产品真实进程的 tracking/trigger 记录无效。因此当前 reward、时间和 Token 可以用于定位工程问题和描述运行行为，但不能在事后升级为正式生命周期无故障实验结果；正式样本需在门禁修复和配置冻结后重新执行。

## 3. 指标口径

| 指标层级 | 判定 | 说明 |
| --- | --- | --- |
| Verifier 功能性通过 | `reward=1` 或等价 Oracle 通过 | 最终环境/工件正确，Agent 不一定正常退出 |
| 产品正常终态 | `completed` 且 `rc=0` | Agent 正常结束，任务不一定完成 |
| 严格端到端成功 | 正常终态且 Verifier 通过 | 当前最接近端到端完成的工程指标 |
| 正式有效任务 | lifecycle、配置、Runner、环境和 Verifier 门禁均通过 | 才可进入正式发布结果；当前为 0 |

异常终止后仍可能通过，是因为 Verifier 检查的是最终环境或工件；反之，正常退出也可能没有完成任务。时间为逐任务阶段累计，不等于并发批次的真实墙钟时间。Astra 的轮次取自 `StepStarted`/中断记录，Hermes 取自 session `api_call_count`；工具失败的采集方式也不同，因此这些效率指标只能近似对照。

## 4. 当前结果

### 4.1 Astra：第一轮 89 题中的可分析部分

| 指标 | 数值 |
| --- | ---: |
| 初始尝试任务 | 89 |
| 可分析轨迹 | 56 |
| 必须从头重跑 | 33 |
| Verifier 通过 | 31/56 |
| Verifier 未通过（`reward=0`） | 25/56 |
| 产品正常终态 | 27/56 |
| 严格端到端成功 | 25/56 |
| 正式有效任务 | 0/56 |
| 累计 E2E 时间 | 25.483 task-hours |
| 累计 Agent 执行时间 | 21.956 agent-hours |
| 总 Token | 19,511,085 |
| Agentic 轮次 | 970 |
| 工具调用 | 1,282 |
| 失败工具返回 | 101 |

25 个 Verifier 未通过任务中，22 个具有 `stream_transport` / fallback 中断及可恢复原 session 的证据。这是当前 Astra 的主要工程可靠性问题：不应把它们直接解释为模型能力失败，也不应在已有副作用工具操作的情况下机械地从头执行。其余可分析失败包括 1 个真实任务未满足、1 个 Verifier 固定超时和 1 个预算耗尽并叠加 Verifier 基础设施问题。

### 4.2 Hermes：64 题冻结快照

| 指标 | 数值 |
| --- | ---: |
| 终态任务 | 64 |
| Verifier 通过 / 全部终态 | 35/64 |
| Verifier 通过 / 已评分任务 | 35/57 |
| Verifier 未通过（`reward=0`） | 22/64 |
| 未产生可评分结果 | 7/64 |
| 产品正常终态 | 49/64 |
| 严格端到端成功 | 33/64 |
| 正式有效任务 | 0/64 |
| 累计 E2E 时间 | 21.842 task-hours |
| 累计 Agent 执行时间 | 20.289 agent-hours |
| 总 Token | 78,449,160 |
| API/Agentic 轮次 | 2,040 |
| 工具完成返回 | 2,233 |
| 失败工具返回 | 219 |

Hermes 的主要工程失败模式与 Astra 不同：后台服务在 `run.completed` 后被 gateway cleanup 清理（4 题）、deadline、cleanup/adapter 异常、Verifier 基础设施问题和 launcher/环境异常。当前只有 1 题具有明确 provider 无响应日志；不能把只记录 deadline 的任务归为 LLM 连接失败。

## 5. Astra 与 Hermes：46 个同任务的观察性对比

两侧样本的模型、最大轮次、deadline、工具 Schema、上下文管理和 Runner 尚未等价冻结。下表只描述现有轨迹，不支持“哪一个产品能力更强”的因果结论。

| 指标 | Astra（46） | Hermes（46） | 观察 |
| --- | ---: | ---: | --- |
| Verifier 通过 | 26/46（56.52%） | 31/46（67.39%） | Hermes 当前更多 |
| 严格端到端成功 | 20/46（43.48%） | 30/46（65.22%） | Hermes 当前更多 |
| 未产生 reward | 0 | 6 | Hermes 存在未评分终态 |
| 累计 E2E | 22.159 小时 | 15.131 小时 | Hermes 为 Astra 的 0.683× |
| 累计 Agent 执行 | 18.907 小时 | 13.978 小时 | Hermes 为 Astra 的 0.739× |
| Fresh input | 2,367,786 | 2,389,438 | 基本持平 |
| Cache-read | 13,272,128 | 48,312,320 | Hermes 为 Astra 的 3.640× |
| 总 Token | 17,494,512 | 51,940,713 | Hermes 为 Astra 的 2.969× |
| 轮次/API 调用 | 865 | 1,465 | Hermes 为 Astra 的 1.694× |
| 工具调用 | 1,162 | 1,605 | Hermes 为 Astra 的 1.381× |
| 失败工具返回 | 97 | 174 | Hermes 为 Astra 的 1.794× |

阶段性可观察到：在该非等价交集中，Hermes 的 Verifier 通过和严格端到端成功更多，累计时间也更少；与此同时，其 Token 消耗接近 Astra 的三倍，主要来自 cache-read，且 API 轮次、工具调用和失败工具返回更多。这更像两套原生产品栈的执行风格差异，而不是可独立归因于 Agent 架构的结论。

## 6. 下一阶段

1. 修正真实产品进程 tracking 和 lifecycle gate，冻结三产品的模型、轮次、deadline、工具权限、重试和后台服务语义；
2. 对 Astra 完成 33 题从头重跑，并针对 22 个可恢复 stream 失败恢复原 session；
3. 对 Hermes 后续完成任务做增量分类，另行形成新的冻结快照；
4. 在正式运行前冻结 Terminal-Bench 故障子集、Task/Fault Manifest 与配对协议；
5. 三产品完成等价 Smoke 后，执行 Terminal-Bench 全集 89 题的正式无故障运行，再进行单故障配对；
6. Goose 的对照运行和 SWE-bench-Live 的具体执行计划随后另行冻结。

## 7. 证据与详细报告

- [总体进度与完整工程诊断](2026-07-31-benchmark-progress.md)
- [Astra 56 项统计报告](../../work/astra-c0-all-jobs/2026-07-29__19-36-33/analysis/v1/astra-c0-56-tasks-statistics-v1.md)
- [Hermes 当前结果与 Astra 交叉报告](../../work/hermes-c0-all-jobs/analysis/v1/hermes-current-vs-astra56-comparison-v1.md)
- [Astra/Hermes 46 项配对数据](../../work/hermes-c0-all-jobs/analysis/v1/hermes-vs-astra-matched-46-tasks-v1.csv)

原始工作目录中的 `c0` 是历史路径命名；本文一律使用“Terminal-Bench 全集生命周期无故障条件工程预运行”来说明具体实验上下文。
