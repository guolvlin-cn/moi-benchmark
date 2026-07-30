# 系统与运行执行清单（v0.3）

> 日期：2026-07-29 ｜ 状态：Draft TODO ｜ parent plan：[`../v0.3.md`](../v0.3.md)

本清单把 v0.3 规范落实为可执行任务，不改变其阈值、赛道边界、无效运行规则或判分合同。估算统一为 1 人日=8 小时；完整 v0.3 为 65–85 人日、3–4 FTE、约 8–10 周。分项人日不能简单相加为日历时间：数据、adapter、环境、judge 和审批可并行，但设备/供应商等待、门禁和重跑会形成关键路径。Pilot 只发现问题，不能代替 formal run。

## 1. 角色、系统身份与冻结原则

### 1.1 角色

| 统一角色 | 本文件责任边界 |
|---|---|
| RAG Owner | 冻结协议、预算与发布门禁；不修改 hidden Gold。 |
| Benchmark Engineer | 实现 MOI/Dify/FastGPT adapters、contracts、artifact/observability、状态机与工程测试；不得替产品修改冻结配置。 |
| Data & Eval Engineer | 负责 corpus/question/evidence manifest、ready/Gold preservation、指标输入和统计交接；与 operator 分离。 |
| System Operator（每产品一名） | 只按固定 onboarding/runbook 操作原生路径，保存动作与人工时间；不得查看 hidden Gold。 |
| Reviewer | 盲审 Judge、claim/citation、scope、invalid 和发布证据；不得查看系统名后回改标签。 |
| Approver | 签署身份、freeze、invalid/replacement 与发布决定；须满足 v0.3 的独立和看分前审批要求。 |

### 1.2 原生身份与 manifest

为每个 `system_id ∈ {moi,dify,fastgpt}` 建立签名 `system_manifest.json`，至少记录：产品全名（MOI 必须确认是 MatrixOne Intelligence）、部署模式/endpoint、frontend/backend build、版本/日期、tenant/region、权限与 entitlement、资源/quota/pricing、启用的 parser/chunker/embedding/retriever/reranker/prompt/LLM、可观察性能力、隐含 defaults、operator、配置 hash。身份、部署或 Explore/API automation 未确认时停止，不以产品别名替代。MOI→Dify、MOI+DeerFlow/MCP 是 integration，不计入 MOI Native。

### 1.3 赛道与公平预算

- **Quick-start Native**：按预注册画像和固定 tie-break 选官方默认/模板，冻结 onboarding/support script、支持时窗与预算；模板选择和首次 ready 不能临场更改。
- **Optimized Native**：只在 dev split 调优；MOI、Dify、FastGPT 使用相同 dev trial 数、active person-hours、wall-clock、配置 action 数、允许 search space、stop rule、vendor-help 是否计时。每项预算在 manifest 签名后不可增加。
- **Controlled Generation（可选诊断）**：仅当能导出真实 `retrieved-context envelope` 才运行；统一排序/拼接/截断/context-token-budget、citation schema、model/version、system+user template、temperature、max output。不能导出者记 `unavailable`，不从答案反推，绝不替代/混入 Native。

## 2. 系统与运行工作清单

每一行必须勾选并链接产物；`人日`是执行量，不是日历承诺。

| ID | checkbox | 依赖 | 角色 | 工作 | 产物 | DoD | 人日 |
|---|---|---|---|---|---|---|---:|
| SR-01 | [ ] | — | RAG Owner、Benchmark Engineer、Approver | 确认 MOI 身份、部署、版本、租户、区域、entitlement 与原生 Explore/API 路径；签 `system_manifest`。 | `rag/systems/*/system_manifest.json` | 三产品身份字段齐全且 Approver 签名；缺字段显式 unknown 并阻止 formal。 | 1.5 |
| SR-02 | [ ] | SR-01 | Benchmark Engineer | 冻结 adapter、run、storage contracts；定义 input/config/output/error/hash 字段与 schema version。 | `rag/benchmark/contracts/{adapter,run,storage}.schema.json` | schema 可校验；不支持字段为 `unavailable`/`N/A`，无伪造默认值。 | 2 |
| SR-03 | [ ] | SR-01 | RAG Owner、System Operator | 预注册 Quick-start 模板选择、画像、tie-break、onboarding 脚本、support/vendor-help 预算和停止时刻。 | `rag/systems/*/quickstart.json`、runbook | 三系统选择可复现；脚本与预算 hash 固定。 | 1 |
| SR-04 | [ ] | SR-01 | RAG Owner、System Operator | 预注册 Optimized dev trial、person-hour、wall-clock、action/search space、stop rule；vendor help 计时方式一致。 | `rag/systems/*/optimized-budget.json` | dev-only 配置签名；任何超预算自动停止并记录。 | 1 |
| SR-05 | [ ] | SR-02 | Benchmark Engineer、Data & Eval Engineer | 建立 selected-file scope、file/chunk eligibility、source/page/span/hash、citation 和 retrieved-context envelope。 | `rag/benchmark/contracts/evidence.schema.json` | 能验证选中文件隔离、disabled chunk exclusion；citation 与 trace 分开存储。 | 2 |
| SR-06 | [ ] | SR-02,SR-05 | Benchmark Engineer、Data & Eval Engineer | 定义 `ready = processed + embedded + searchable`，实现 ready probe、artifact hash、job 状态/重试/lineage 采集。 | `ready_report.json`、artifact manifest | UI 完成不被当 ready；逐 claim 记录是否至少一套 complete alternative evidence set 的全部 sources ready/searchable；其他 alternative 的失败只作诊断。 | 2 |
| SR-07 | [ ] | SR-03,SR-04 | System Operator、Benchmark Engineer | 分别执行冻结 Quick-start 的 onboarding rehearsal 与 Optimized 的 dev-only trials；记录起止、动作、错误、active minutes、wall-clock、support。 | `rag/runs/*/setup_timeline.json`、Optimized trial ledger/final config signature | Quick 只验证预注册官方默认/模板，不得按 dev 结果选优或调参；Optimized 只用 dev split并按停止规则签署最终配置；两者不混报。 | 4 |
| SR-08 | [ ] | SR-06 | Benchmark Engineer、System Operator | 设计并执行安全的 fault-injection/recovery scenarios（job/API/write/read/timeout 等）；冻结 severity、观察窗、终止与 censoring。 | `fault_matrix.json`、timeline/raw logs | 仅预注册且环境允许的注入；自然故障与注入故障分开。 | 3 |
| SR-09 | [ ] | SR-06,SR-08 | System Operator、Benchmark Engineer | 独立执行 reset/rebuild diagnostic：重置代表性子集、重建、hash 校验、ready 重验；不污染 formal。 | `reset_rebuild/*` | 前后 hash、耗时、差异和恢复级别完整；恢复后才可继续 query。 | 2 |
| SR-10 | [ ] | SR-05,SR-06 | Benchmark Engineer、Data & Eval Engineer、System Operator | 运行 30–50 题 Smoke（10–15 families），覆盖单/多文档、exact ID、版本/distractor、视觉/表格、unanswerable、scope。 | `smoke_report.json` | 三产品 native journey、artifact、错误和必要 trace 可保存；失败停止扩展。 | 3 |
| SR-11 | [ ] | SR-10 | Benchmark Engineer、Data & Eval Engineer、Reviewer、Approver | 修复并冻结 adapter、Gold/dataset defect 判定合同、Gold lineage、Judge calibration；重跑受影响 Smoke。 | `freeze_record.json` | calibration ≥30 answers、kappa ≥0.60、Gold validity ≥95% 且 critical error=0。 | 3 |
| SR-12 | [ ] | SR-03,SR-06,SR-07,SR-11,DE-12 | Benchmark Engineer、System Operator | 建立运行命名与字段；使用签名 Quick config 和 frozen hidden set 执行 formal Quick-start，每题三次隔离 initial repeats。 | Quick `rag/runs/{run_id}/` | run manifest 引用 DE-12 签名 task-set version/hash/ACL；Quick 配置未按 dev 选优；每题恰一个 scored initial；raw response/claims/citations/context/status/timestamps/cost/error/hash 齐全。 | 4 |
| SR-13 | [ ] | SR-04,SR-06,SR-07,SR-11,DE-12 | Benchmark Engineer、System Operator、Approver | 在 Optimized trial ledger、预算和最终配置签名后执行 formal Optimized，每题三次隔离 initial repeats。 | Optimized `rag/runs/{run_id}/` | run manifest 引用 DE-12 签名 task-set version/hash/ACL；Optimized 已在 dev-only 等额预算内冻结；与 Quick 分批；所有 initial/product failures 进入分母。 | 4 |
| SR-14 | [ ] | SR-12,SR-13 | Benchmark Engineer、Reviewer、Approver | 只对 initial failure 做最多两次 retry 诊断；分类 `question_invalid`、`run_invalid`、`batch replacement`，不替换主分数。 | `retry_diagnostics.json`、`invalid_ledger.json` | 产品/API failure 有效零分；单 batch 超一次 benchmark fault 则整体标 execution failure 并按规则重跑。 | 2 |
| SR-15 | [ ] | SR-12,SR-13 | Data & Eval Engineer、Reviewer | 审计 selected-file scope、Gold-evidence support、citation precision/coverage、question/run invalid；保存 claim-level rationale。 | `audit/*` | 伪造/越 scope/错误 page-span-hash 可追责；无 trace 标 observability gap。 | 5 |
| SR-16 | [ ] | SR-10,SR-12,SR-13 | Benchmark Engineer、System Operator、Reviewer | 独立执行 MOI capability validation：workflow topology/config export、parser artifacts/previews、page mapping、embedded eligibility/disabled chunks、selected-file scope、job status/retry/lineage/export。 | `moi_capability_matrix.json`、evidence refs | 每项为 pass/fail/unavailable/gap；Common 等价能力与 MOI-specific 项分栏，不折入横向共同分数。 | 2–3 |
| SR-17 | [ ] | SR-14,SR-15,SR-16 | Benchmark Engineer、Data & Eval Engineer、Reviewer | 汇总 build/query latency、TTFT/E2E、cost/currency/date、ready time、failure taxonomy 与 operator journey；按 condition/fresh-control 分层。 | `stage_diagnostics/`、`scorecard_input.json` | raw artifacts 与成本时延可复算；不生成 weighted total/winner。 | 4 |
| SR-18 | [ ] | SR-15,SR-17 | RAG Owner、Data & Eval Engineer、Reviewer、Approver | 盲审、cluster bootstrap 10,000 次 paired 95% CI、缺失能力/限制/审批；发布系统运行验收。 | `rag/reports/system-run-acceptance.md` | 所有 Gate 通过，目录与 hash 可追溯，未解决 defect 有明确 disposition。 | 3 |

估算合计约 48.5–49.5 人日（本文件 slice）；与完整 v0.3 的 65–85 人日有重叠，不可解释为额外日历工期，实际工时按 [Crosswalk](README.md#8-子计划与总人日-crosswalk)记入对应 M ID。

## 3. 运行前检查（formal 前逐项签字）

- [ ] 三个 `system_manifest` 身份、部署、frontend/backend build、tenant/region/entitlements、资源和日期已签名；MOI 明确为 MatrixOne Intelligence。
- [ ] raw corpus/question/evidence manifest 的 sha256、版本、授权、egress、split、访问级别和 retention 已冻结；fresh-control 题已纳入 hidden formal。
- [ ] Native path、Quick-start 模板与固定 onboarding 已演练；Optimized 各预算、search space、stop rule、vendor-help 口径一致。
- [ ] adapter/run/storage contracts、selected-file scope、citation、trace、ready probe、artifact/hash 写入通过 schema check。
- [ ] `ready` 不是 UI 完成：每个 required reference claim 均检查是否至少一套 complete alternative evidence set 的全部 sources processed、embedded、searchable；其他 alternative 失败保留为诊断。若某 claim 无有效 ready set，相关 initial TDAS=0 并记录 stage failure，不删题或阻止其进入正式分母。
- [ ] Smoke 门禁、judge calibration/kappa、Gold audit、question_invalid 清单通过；hidden formal 不可被 operator 访问。
- [ ] formal batch、run order、fresh session、三次 initial、最多两次 diagnostic retry、replacement approver 已预注册。
- [ ] Controlled Generation 的 capability 已确认；不可导出 context/trace 的系统标 unavailable，且不阻塞 Native。

## 4. 单题状态机与运行命名

### 4.1 状态机

```text
PLANNED → INPUT_CHECKED → REQUEST_SENT → INITIAL_RECORDED
                         ├→ question_invalid（全局排除，保留记录）
                         ├→ run_invalid（benchmark-side fault，按 replacement）
                         └→ product_failure（有效零分）
INITIAL_RECORDED → RETRY_DIAGNOSTIC(0..2) → JUDGED → AUDITED → CLOSED
```

`REQUEST_SENT` 前发生的 harness fault 不能伪装成产品失败；产品/API unavailable 从 `REQUEST_SENT` 起是有效 initial failure。单题 retry 只影响 availability/诊断，不改变 initial score。`question_invalid` 只用于预注册 Gold/dataset defect，对所有 system/condition/repeat 全局排除；`run_invalid` 只用于请求未发出、adapter 崩溃、基准网络/写入故障。产品结果按系统删题、看分后重跑均禁止。

### 4.2 命名和必填字段

`run_id = v03-{track}-{system_id}-{condition}-{batch_id}-q{question_id}-r{repeat_id}-{attempt}`；不可变且新 replacement 必须另建 run_id，并写 `replaces_run_id`。必填字段包括 `plan_version`、`system_id`、`native_condition`、`track`、`batch_id`、`question_id`、`repeat_id`、`attempt_type`、`status`、`state_timestamps`、`config_hash`、`input_hash`、`output_hash`、`response_raw`、`response_claims[]`、`citations[]`、`retrieved_contexts/ranks`（无则 `unavailable`）、`source_map`、`ready_snapshot`、`ttft_ms`、`e2e_ms`、`tokens`、`cost`、`error_code`、`operator`、`artifact_refs`。

`batch_id` 固定为 `system_id × native_condition × frozen question set × repeat round/time window`。同 batch 超过一次 benchmark-side fault，整 batch 标 `benchmark_execution_failure`，停止、修复、重冻结后整体重跑；不得选择性逐题 replacement。

## 5. 异常处置决策表

| 事件 | 主分数 | 是否 retry | 处置/产物 |
|---|---|---|---|
| Gold/dataset defect（预注册） | 所有系统/condition/repeat 全局排除 | 否 | `question_invalid`，保留 evidence、审批和原 run。 |
| 请求未发出、adapter 崩溃、benchmark 网络/写入故障 | 不计入该 replacement；其余有效 | 最多按 batch replacement 一次 | 新 run_id/`replaces_run_id`，盲 approver 看分前签字。 |
| 产品/API/模型不可用、超时、解析失败 | initial=0，进入 failure taxonomy | 最多两次诊断 retry | 不得 invalid；retry 不替换 initial。 |
| selected-file scope 越界、citation source/page/hash 错 | TDAS/citation 按规范失败 | 否（可记录诊断） | 保存上下文、截图/响应和审计判定。 |
| ready 未满足或 artifact 缺失 | 相关题有效失败/零分 | 修复后仅按预注册 batch 规则处理 | 不删除 hard case；记录 `readiness_failure`。 |
| 同 batch 第二次 benchmark fault | 暂停整 batch | 整体重冻结重跑 | 标 `benchmark_execution_failure`，不得把产品结果置零。 |

## 6. 产出目录与保留

```text
rag/systems/{moi,dify,fastgpt}/                 # manifests/config hashes
rag/benchmark/contracts/                         # adapter/run/storage/evidence schemas
rag/runs/{run_id}/                               # manifest, raw, normalized, artifacts, logs
rag/runs/{run_id}/diagnostics/                   # retry, fault, reset/rebuild, timelines
rag/reports/system-run-acceptance.md             # acceptance and limitations
rag/progress/                                    # smoke/gate/freeze ledgers
```

raw response、claims、citations、retrieved context/rank/source map、状态时间线、artifact、错误、成本和 hash 必须保留；敏感 raw/log/trace 置于受控外部存储，仅提交 manifest、summary、hash 和 access pointer。所有 replacement、invalid、审计签名和配置冻结记录不可静默删除。

## 7. 耗时、并行与 Pilot 边界

可并行：SR-01/03/04 的产品确认与预算起草；SR-02/05 的 contract/schema；Data & Eval Engineer 的 dataset/Gold 与 Benchmark Engineer 的 adapter；三产品 onboarding 演练。关键等待：身份/权限、供应商帮助时窗、ready/build、fresh-control、judge 校准、盲审审批；任何等待要记录 wall-clock，不折算为 active person-hours。Operator journey 同时记录两者。

Pilot 仅包括 Smoke、代表性 fault/reset 和少量 contract 贯通，用于发现缺字段、observability gap、scope 或状态机问题；Pilot 输出不得进入 hidden formal 分母、不得替代三次 initial repeats、不得证明 Quick/Optimized 正式结论。修复需重新冻结受影响 contract/config/question lineage。

## 8. 系统运行验收（Release Gate）

RAG Owner 仅在下列全部满足并取得 Reviewer 与 Approver 签字后提交发布：

1. 三产品 identity/deployment/manifest 与 native boundary 明确；Quick-start、Optimized、可选 Controlled 的分离和预算证据齐全。
2. ready 验证、adapter/run/storage contracts、artifact/hash、selected-file scope、citation 与 trace observability gap 均可审计；不可观察项显式缺失，不以答案反推。
3. Smoke、formal Quick/Optimized、三次 initial、最多两次诊断 retry、question_invalid/run_invalid/batch replacement 均遵守 v0.3；没有看分后删题或静默重跑。
4. raw artifacts、成本、时延、failure taxonomy、operator journey、fault injection、reset/rebuild 和 MOI-specific validation 目录完整，缺失能力与限制单独报告。
5. TDAS/component metrics、fresh-control、CI、audit、Gold validity 和 approval ledger 可复算；不发布 weighted total、单一 winner 或把 Pilot 当 formal。

未满足项必须列为 blocker 并停止发布；修复后只重冻结并重跑受影响范围。
