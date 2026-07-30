# v0.3 决策型研究计划

> 日期：2026-07-29 ｜ 状态：Draft TODO ｜ Parent plan：[v0.3](../v0.3.md)

本研究只为执行 v0.3 收集可审计证据并作出 Gate 决策，不做泛读、产品宣传汇编或新规范设计。已有范围证据见 [MOI benchmark-scope evidence note](../../../research/moi-rag-platform-benchmark-scope.md) 与 [v0.2 一手证据复核](../../../research/v0.2-primary-evidence-review.md)；它们是研究起点，v0.3 仍是规范权威。

## 1. 目标与边界

研究必须回答三类问题：

1. **能否执行**：目标系统身份、部署、Entitlement、Native 路径、自动化、作业和 reset/rebuild 是否可复现。
2. **能测到什么**：response、trace、rank、context、citation、source map、状态、耗时和成本哪些可真实导出，哪些只能标 observability gap。
3. **如何公平冻结**：运行时组件/defaults、cloud/private 差异、权限/egress/retention、quota/pricing、跨产品等价能力和 Judge 实现如何形成可签名输入。

研究不证明产品“更好”，不从最终答案倒推检索链路，不通过逆向未支持接口填补 observability，也不使用任何产品输出生成 Gold。

## 2. 证据等级与结论状态

### 证据等级

| 等级 | 定义 | 可支持的决定 |
|---|---|---|
| **A：目标部署可复现实证** | 在待测 tenant/region/build 上按记录步骤执行，保存原始 UI/API/job/artifact、时间、版本和 hash | 运行合同、能力可用/不可用、实际默认值、操作语义 |
| **B：当前一手规范证据** | 与目标版本相关的官方文档、公开 API/schema、release note、合同/价格/安全条款，保留日期与快照/hash | 预期能力、支持边界、字段定义；不能单独证明目标部署已启用 |
| **C：可归属书面确认** | 厂商/管理员的带日期书面答复，可识别回答者权限与适用部署 | 解释缺口或限制；关键运行事实仍尽量用 A 复核 |
| **D：二手或行为推断** | 社区文章、搜索摘要、营销比较、从输出行为猜测 | 仅作为后续线索，不得关闭 Gate |

表中“最低证据”是关闭问题所需门槛。关键能力常要求 `A+B`；若能力确认不可用，仍须保存 A/B/C 中足以证明测试范围与影响的证据。

### 结论状态

- `confirmed`：证据达到最低等级，结论适用于明确的部署/版本/日期。
- `confirmed_unavailable`：已证实目标部署不可用或不可导出，并已记录报告影响。
- `blocked`：证据不足且会阻止 Gate；不得改写成 N/A。
- `open_non_blocking`：v0.3 允许以 gap/限制报告，且 RAG Owner、Reviewer 已记录不影响当前 Gate 的理由。
- `contradicted`：证据冲突；按停止条件升级，不自行挑选有利来源。

## 3. 研究问题与执行表

总研究基线为 **5–7 人日**，纳入完整计划的 65–85 人日，不另加；实际工时按 [Crosswalk](README.md#8-子计划与总人日-crosswalk)记入对应 M ID。产品/供应商回复等待只计日历，不计人日。

| ID | 问题 | 方法 | 优先级 | 最低证据 | 输出 | 决策/门禁 | 角色 | 人日 |
|---|---|---|---|---|---|---|---|---:|
| R01 | “MOI”是否为目标 MatrixOne Intelligence；确切 deployment/build/tenant/region/Entitlement 是什么 | 核对采购/账户/控制台/版本页与官方身份材料；由 Owner、Approver 双签 | P0 | A+B | identity evidence index、签名 system manifest | 不明确即阻塞 identity Gate；不得用别名替代 | RAG Owner、System Operator、Approver | 0.5 |
| R02 | Native Explore 的 UI/API contract 能否稳定自动化；何种 API 可被正式批准为等价 Native | 盘点官方 API/schema；在目标部署完成最小 raw-file→Explore journey；记录 auth、请求、响应、session 与失败 | P0 | A+B | native journey、automation decision、runbook skeleton | Smoke 前选定受支持路径；无稳定 API 时决定可复现 UI 路径或阻塞 | Benchmark Engineer、System Operator、Reviewer | 0.5–0.75 |
| R03 | 能否导出真实 retrieved trace、rank/score、context、citation、source/page/span/bbox/hash map、token/timing | 用已知证据问题对 UI/API/artifact export 做逐字段探针；将 retrieval trace 与用户引用分开核对 | P0 | A+B | observability/export matrix、样例 artifact/hash | 决定哪些 retrieval metrics 可算；不可导出则明确 gap，禁止答案反推 | Benchmark Engineer、Data & Eval Engineer、Reviewer | 0.5–0.75 |
| R04 | 实际 parser/chunker/embedding/retriever/reranker/prompt/LLM 及 hidden defaults/版本是什么 | 核对可导出 workflow/config、管理页、API、release/build 信息；对不可见项索取书面确认 | P0 | A+B；hidden 可 A+C | runtime component/default matrix | 决定 system/config manifest 可冻结字段；未知项标 hidden，不猜测 | Benchmark Engineer、System Operator | 0.5–0.75 |
| R05 | selected-file scope 与 disabled-chunk exclusion 是否真实生效，怎样验证 | 设计包含同名冲突、排除文件和唯一 marker 的确定性 fixture；检查 response、citation 与真实 trace | P0 | A | scope/disabled-chunk test evidence | selected-file 是共同核心 Gate；disabled chunk 仅作 MOI capability validation | Benchmark Engineer、Data & Eval Engineer、Reviewer | 0.25–0.5 |
| R06 | job 状态、retry、reset/rebuild、duplicate/idempotency 的真实语义是什么 | 对代表性子集执行 create/run/fail/retry/reset/rebuild/duplicate；记录状态机、ID、时间线、前后 hash 与恢复动作 | P0 | A+B | operations state matrix、recovery/runbook evidence | 决定 ready、invalid/retry 与恢复自动化；产品失败不得改写为基准故障 | System Operator、Benchmark Engineer | 0.5 |
| R07 | cloud/private 在 Native、models、export、observability、quota 上是否等价 | 分部署核对官方 capability/version matrix；只对可访问目标做实测，未测项明确范围 | P1 | B；声称等价须 A+B | deployment parity matrix | 决定报告适用范围；不得把 cloud 结论外推 private 或反向外推 | RAG Owner、System Operator、Reviewer | 0.25–0.5 |
| R08 | corpus/fresh 数据的安全、egress、retention、日志/模型处理与删除路径是否允许 | 审查官方/合同条款和组织政策；做 data-flow/threat review；由 Approver 签数据类别与目的地 | P0 | B+审批记录；可验证项用 A | data-flow、egress/retention matrix、审批索引 | 未批准不得上传/运行；私有 raw/log/trace 不进入 Git | RAG Owner、Approver、System Operator | 0.5 |
| R09 | quota、限流、并发、计费单位和实际 pricing 如何约束运行 | 核对目标账户 quota/usage/billing、官方价目与合同；估算正式请求/存储/模型量并做小流量验证 | P1 | A+B | capacity/cost assumption ledger | 确认 formal capacity、成本字段与 SLO 可否冻结；价格未知须披露 | RAG Owner、System Operator | 0.25–0.5 |
| R10 | Dify 对 ingestion→Native answer、配置、trace/citation、job/reset 的等价能力是什么 | 以同一能力探针和原始文件做官方文档核对与目标部署实测 | P0 | A+B | Dify capability/equivalence row、artifact samples | 决定 common contract 与 Dify gap；不以 MOI 术语强套实现 | Benchmark Engineer、System Operator、Reviewer | 0.5 |
| R11 | FastGPT 对同一能力集合的等价能力是什么 | 复用 R10 的问题集合、证据字段和判定方法，在目标部署单独实测 | P0 | A+B | FastGPT capability/equivalence row、artifact samples | 决定 common contract 与 FastGPT gap；不可观察项不获 N/A 优势 | Benchmark Engineer、System Operator、Reviewer | 0.5 |
| R12 | Correctness/support/citation/unanswerable、claim canonicalization、kappa、bootstrap 将由何种实现产生可复核证据 | 将 v0.3 公式逐项映射到代码接口/golden cases；核对候选 Judge/metric 一手来源；设计 30-answer calibration、双审与 10,000 次 cluster bootstrap 验证 | P0 | A（本地测试）+B（实现来源） | metric-to-code matrix、golden test plan、Judge freeze/calibration plan | 实现不得改公式；未通过测试/calibration 不能关闭 dataset/Judge Gate | Data & Eval Engineer、Benchmark Engineer、Reviewer | 0.25–0.75 |

## 4. 方法与停止条件

### 单个问题的最短闭环

1. 写明待作决定、适用系统/部署/版本、最低证据和会阻塞的 Gate。
2. 先查已有一手材料，再做一个能区分结论的最小目标部署实验；不做无决策产出的漫游式阅读。
3. 保存原始证据、步骤、时间、hash 和限制；把“观察”与“解释”分开。
4. 由 Reviewer 检查证据等级、可复现性和反例；RAG Owner 记录 `confirmed`、`confirmed_unavailable`、`blocked` 或 `open_non_blocking`。
5. 达到决定所需证据即停止；新线索进入 backlog，不扩大当前研究范围。

### 必须停止并升级

- MOI 身份、部署、版本、tenant/region 或 Entitlement 无法确认。
- security/egress/retention 未批准；此时停止数据上传和外部模型调用。
- 找不到可复现且获批准的 Native journey；不得用 MOI→Dify、DeerFlow/MCP 或外部 generator 代替。
- 目标部署证据与官方规范/书面确认矛盾，且矛盾会改变配置、数据安全、可比性或 Gate。
- 自动化会依赖未支持私有接口、绕过权限或无法保存 initial attempt；停止实现并交由 RAG Owner/Approver 决策。
- P0 研究达到 5–7 人日预算仍未关闭：停止继续泛搜，将问题标 `blocked`，说明最小解阻证据和外部等待。

trace/rank/context export 确认不可用不自动取消整个产品；按 v0.3 标 `observability gap`，不计算依赖真实 trace 的指标。反之，identity/security/Native path 等硬 Gate 不得以“限制披露”绕过。

## 5. 证据记录模板

每项证据至少记录：

```yaml
research_id:
decision_question:
system_id:
deployment_build_tenant_region:
observed_at:
researcher:
method_and_reproduction_steps:
official_source_and_version:
source_snapshot_or_hash:
observed_result:
raw_artifact_uri:
raw_artifact_sha256:
access_level_and_retention:
evidence_grade:
conclusion_status:
scope_and_limitations:
conflicting_evidence:
decision_and_affected_gate:
reviewer_and_reviewed_at:
```

`raw_artifact_uri` 可指向受控外部存储；仓库只保存允许公开的摘要、索引、hash、访问级别和保留期。凭证、私有数据、完整 trace/log 不进入 Git。

## 6. 研究输出文件建议

建议在 `rag/research/` 形成以下版本化结论，并链接目标部署原始证据；名称可按仓库约定调整，但内容边界应保留：

| 建议文件 | 内容 |
|---|---|
| `2026-07-29-matrixone-intelligence-identity-and-entitlement.md` | R01 身份、部署、版本、Entitlement 与适用日期 |
| `2026-07-29-native-automation-and-observability-matrix.md` | R02–R03 三产品 Native 自动化与 export 字段矩阵 |
| `2026-07-29-runtime-defaults-and-scope-evidence.md` | R04–R05 组件/defaults、selected-file 与 disabled-chunk 证据 |
| `2026-07-29-operations-security-and-commercial-evidence.md` | R06–R09 job/retry/reset/idempotency、parity、安全、quota/pricing |
| `2026-07-29-product-equivalence-matrix.md` | R10–R11 Dify/FastGPT 共同能力、差异、gap 和适用版本 |
| `2026-07-29-judge-and-metric-implementation-evidence.md` | R12 公式到代码映射、候选实现依据、golden/calibration 计划 |

部署签名写入 `rag/systems/`，运行探针写入 `rag/runs/`，实现和测试写入 `rag/benchmark/`；研究文档只汇总结论并互链，不复制敏感 payload。

## 7. 不可推断事项

- 官方文档描述某能力，不等于目标 tenant/build 已启用、已授权或与文档行为一致。
- UI/job 显示完成，不等于 `processed + embedded + searchable`。
- 最终答案、答案中的引用或 source label，不等于真实 retrieved context、rank、score 或 utilization。
- 看不到配置项，不等于组件不存在；也不能从回答风格猜 LLM、prompt、reranker 或 hidden default。
- selected-file/disabled-chunk 的产品说明，不等于 scope enforcement 已通过确定性验证。
- cloud 的 feature、quota、安全或价格，不得外推 private；不同版本/region 也不得默认 parity。
- 标价页不等于目标账户实际单位成本；账单/usage 也不得在单位和归因未核对时直接比较。
- MOI 的术语、workflow topology 或 export 能力，不证明 Dify/FastGPT 有等价能力；反之亦然。
- API 未公开不等于能力绝对不存在，但在获批准和可复现前不得用于 Formal。
- 论文/框架报告的 Judge 表现，不证明冻结 Judge 在本数据、语言和 label strata 上有效；必须做本地 golden tests 与人工 calibration。
- 产品输出不得用于生成或修订 Gold；无 trace 时不得从答案反推检索失败。
- pre-freeze、Pilot 或 Smoke 观察不得写成 Formal 结论。

## 8. Research Acceptance Checklist

- [ ] R01–R12 均有负责人、适用版本/部署、原始证据索引、证据等级和 Reviewer。
- [ ] 所有 P0 项均为 `confirmed`、`confirmed_unavailable` 或显式 `blocked`；没有用 D 级推断关闭 Gate。
- [ ] MOI identity/deployment/build/tenant/region/Entitlement 已签名，产品边界未混入集成路径。
- [ ] MOI、Dify、FastGPT 各有可复现 Native journey；正式采用的 UI/API 路径已批准。
- [ ] trace、rank/score、context、citation、source map、timing、token/cost 逐字段确认可用性与保存方式。
- [ ] parser/chunker/embedding/retriever/reranker/prompt/LLM 可见字段已记录；hidden defaults 明确标记。
- [ ] selected-file scope fixture 已定义；MOI disabled-chunk 验证保持为独立 capability diagnostic。
- [ ] job/retry/reset/rebuild/duplicate/idempotency 状态与 initial/retry 语义可映射到 run contract。
- [ ] cloud/private parity 的已测、未测和不可外推边界清楚。
- [ ] security/egress/retention/data-flow 获批准；敏感证据存储和删除路径明确。
- [ ] quota、限流、formal capacity、计费单位/pricing 的已知与未知项进入 ledger。
- [ ] Dify/FastGPT 等价能力逐项有证据，缺失/不可观察不会被解释为优势。
- [ ] Judge/metric 选择逐项映射 v0.3 公式、golden cases、30-answer calibration、双审/kappa 与 bootstrap 测试。
- [ ] 所有矛盾、未知、限制和 open_non_blocking 决定均链接受影响 Gate；硬阻塞未被豁免。
- [ ] 研究总投入在 5–7 人日内；外部等待与实际研究工时分开记录。
