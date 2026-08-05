# 03 adapters、schema 与 run ledger

- [ ] **A-301** 依赖：D-201；为 MOI、Dify、FastGPT、RAGFlow、MaxKB 记录 identity/capability/version/access。DoD：MOI 永久保留候选行但须过 G0，失败标 BLOCKED/NOT_ELIGIBLE。
- [ ] **A-302** 依赖：A-301；实现统一 attempt schema：`run_id,system_id,condition,question_id,repeat_id,status,error,latency,response,citations,context,hash,retry_of`。DoD：产品失败留初次分母。
- [ ] **A-303** 依赖：A-302；Stage 0/1 运行矩阵。DoD：Stage 1 竞品各 20×2=40、四家=160，MOI 40，native 总计 200；shared oracle 40。
- [ ] **A-304** 依赖：A-303；retry 与 invalid lineage。DoD：retry 不替代初次；仅 benchmark-side 缺陷可 replacement，原记录保留。
- [ ] **A-305** 依赖：D-229、A-315；formal 资格、condition 与预算冻结。DoD：Quick `600×N×3` 可展开，N=5 时为 9,000；其他 condition 使用各自分母，blocked 系统保留行。

Gate G3：每个计划 attempt 有 terminal 去向、raw artifact、时间戳、hash 和 N/A reason；trace 缺失只能 `TRACE_UNAVAILABLE`。

## Capability/identity manifest

| ID | 系统 | 必填能力 | 身份字段 | 资格风险 |
|---|---|---|---|---|
| A-306 | MOI | upload/parse/index/query/citation | tenant/version/model | 不得删除 |
| A-307 | Dify | dataset/retrieval/workflow | workspace/version/provider | 默认路径漂移 |
| A-308 | FastGPT | knowledge base/query | tenant/version/model | quota/插件 |
| A-309 | RAGFlow | parser/retrieval/answer | deployment/version | OCR/trace差异 |
| A-310 | MaxKB | ingest/query/citation | deployment/version | citation schema |

统一 manifest：`system_id,vendor,version,tenant,model,embedding,parser,config_hash,identity,capability,license,egress,quota,budget_hash,freeze_id`。

## Adapter 与 attempt schema

接口：`prepare_corpus() → wait_ready() → reset_session() → send(question) → capture() → normalize() → archive()`。统一输入包括 question、question_id、condition、session_id；输出包括 response、citations、context（若真实可得）、status、error、start/end、artifact_hash。

运行状态允许值：`planned,started,succeeded,timeout,service_error,parse_error,empty_answer,invalid,replaced`。`retry_of` 只指向初次 run；replacement 必须记录 benchmark-side defect。

## 条件与预算

- **A-311** 依赖 A-306–310；Quick 配置冻结。DoD：平台默认/Quick-start 参数、模型、prompt、context budget 均有 config hash。
- **A-312** 依赖 A-311；Optimized 预算登记。DoD：所有候选系统使用同一 `T/H/W/A`、API/compute/vendor-support budget、参数白名单、搜索空间与停止规则；任一候选无法满足则整个 Optimized condition 不开榜。
- Optimized 公平合同冻结：最大 dev trials `T`、active person-hours `H`、wall-clock `W`、configuration actions `A`、API/compute/vendor-support budget；参数白名单、搜索空间、停止规则、日志均必填。任一系统不能满足则整个 Optimized condition 不开榜。
- **A-313** 依赖 A-311；session/reset/run order。DoD：每题 fresh session、预注册顺序、warm-up 不混入质量分母。
- **A-314** 依赖 A-313；artifact/hash。DoD：raw request/response、截图或 API payload、引用、context、时间戳和 sha256 可回放。

## Stage1 与 formal 算式

Stage1 同窗新跑：MOI `20×2=40`；四竞品各 `20×2=40`，竞品 `160`；native 新总计 `20×5×2=200`（不是复用 S0）；shared Gold Context oracle `20×1×2=40`，无平台维度。No-context/Noise 各自另行 `Q×R`/`Q×C×R`。

| Formal condition | 计分单位与分母 | 平台维度 |
|---|---|---:|
| Quick Native | `600×N×3`；N=5 时 9,000 | 有 |
| Frozen Optimized Native | 全体公平启用时 `600×N×3`，否则不开榜 | 有 |
| Retrieved-context replay | `600×N_trace×R_replay`；默认建议 R=3，G2 冻结 | 仅上游 context 来源 |
| Shared Gold Context | `600×3=1,800` | 无 |
| No-context | `Q_nc×R_nc`，Q/R 预注册 | 无 |
| Noise | `Q_noise×C_noise×R_noise`，Q/C/R 预注册 | 无 |

每个 condition 建独立 ledger；retry 另列，不能把这些公式笼统相乘。

## Eligibility 与 trace

- **A-315** 依赖 A-306–314、D-229；formal eligibility candidate freeze。DoD：identity/capability/budget 通过且在 formal 前锁定；未通过者保留 `BLOCKED/NOT_ELIGIBLE` 行。
- **A-316** 依赖 A-314；trace audit。DoD：核验 `query_rewrite,chunk_id,document_id,page,span,rank,retrieval_score,rerank_score,raw_text_hash,context_order,token_count,truncation`，qrels 来自 Gold；任一真实 trace 合同不成立时写 `N/A/TRACE_UNAVAILABLE`，禁止从答案或引用反推。
- **A-317** 依赖 A-302、A-304；denominator reconciliation contract。DoD：`planned_initial_units = score-bearing_initial_or_replacement_units + invalid_unreplaced_units + not_started_units`；`request_rows = initial_rows + retry_rows + replacement_rows`，产品失败属于 score-bearing initial。

## Adapter 任务表

- [ ] **A-318** Owner Operator；依赖 A-306；产物 MOI adapter；DoD upload→parse→index→query→citation 全路径可记录；估时 8h。
- [ ] **A-319** Owner Operator；依赖 A-307；产物 Dify adapter；DoD dataset/run config hash；估时 8h。
- [ ] **A-320** Owner Operator；依赖 A-308；产物 FastGPT adapter；DoD API/UI fallback 明示；估时 8h。
- [ ] **A-321** Owner Operator；依赖 A-309；产物 RAGFlow adapter；DoD OCR/parser 状态分离；估时 8h。
- [ ] **A-322** Owner Operator；依赖 A-310；产物 MaxKB adapter；DoD citation payload 可归档；估时 8h。
- [ ] **A-323** Owner Schema；依赖 A-318–322；产物 adapter contract；DoD 五系统 normalization 一致；估时 6h。
- [ ] **A-324** Owner Security；依赖 A-323；产物 egress report；DoD raw/citation/context 存储位置授权；估时 3h。
- [ ] **A-325** Owner Operator；依赖 A-324；产物 readiness matrix；DoD ready/indexed/searchable 状态可追溯；估时 4h。
- [ ] **A-326** Owner Operator；依赖 A-325；产物 run-order file；DoD order、session reset、warm-up 预注册；估时 2h。
- [ ] **A-327** Owner Operator；依赖 A-326；产物 attempt ledger；DoD planned/started/terminal 对账；估时 8h。
- [ ] **A-328** Owner Operator；依赖 A-327；产物 retry ledger；DoD retry_of、reason、恢复状态；估时 3h。
- [ ] **A-329** Owner QA；依赖 A-328；产物 invalid/replacement log；DoD 仅 benchmark-side 缺陷可 replacement；估时 3h。
- [ ] **A-330** Owner Storage；依赖 A-329；产物 artifact index；DoD 每 raw/config/citation/context 有 sha256；估时 4h。
- [ ] **A-331** Owner Research；依赖 A-330；产物 trace availability report；DoD N/A reason 逐 attempt；估时 3h。
- [ ] **A-332** Owner Program；依赖 A-315、A-331、D-229；产物 formal eligibility freeze；DoD identity/capability/budget 与 blocked rows 签署；估时 4h。
- [ ] **A-333** Owner Operator；依赖 A-323、A-325、A-326、D-205；产物 Stage1 matrix/ledger；DoD 同窗新跑 40+160=200 Native、独立 Gold Context 40，S0 结果不复用；总阶段预算纳入 10–15 人日。
- [ ] **A-334** Owner Operator；依赖 A-312、A-330、A-332、S-511；产物 formal condition matrix；DoD Quick、可选 Optimized、replay 与 shared conditions 按各自公式展开且 retries 分离；按 N/condition 计时。

恢复规则：API/UI 录入错误可标 run_invalid 并 replacement；平台 timeout、空答、quota error 不是 invalid。任何 adapter 升级都生成新 adapter_version 与全局影响清单。

## Ledger 字段审计

- [ ] **A-335** 每个 run 有唯一 run_id、batch_id、system_id、condition、question_id、repeat_id。
- [ ] **A-336** 每个 terminal row 有 start/end、status、error_code、response/citations artifact。
- [ ] **A-337** 每个 retry 有 retry_of、触发原因和是否恢复，绝不覆盖 initial。
- [ ] **A-338** 每个 invalid/replacement 有 schema defect、原始 hash、替代 lineage。
- [ ] **A-339** 每个 trace N/A 有 `TRACE_UNAVAILABLE` 和探测证据。
- [ ] **A-340** 每个 batch 有 config_hash、run-order hash、adapter_version、freeze_id。

对账前禁止打分；对账后仍须分别计算 first-attempt 与 retry recovery。任何平台少于计划 attempts 时，报告缺失而非缩小 denominator。
