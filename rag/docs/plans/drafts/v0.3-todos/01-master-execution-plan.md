# v0.3 总执行计划

> 日期：2026-07-29 ｜ 状态：Draft TODO ｜ Parent plan：[v0.3](../v0.3.md)

本文件只分解 v0.3 的执行顺序、责任、产物和完成定义（DoD）。指标、阈值、schema 语义、无效运行规则或范围若与 v0.3 冲突，以 v0.3 为准。

## 1. 目标与非目标

### 目标

- 把身份治理、研究、数据、工程、Smoke、配置、Formal runs、MOI 诊断、盲审统计和发布串成有依赖、有主责、有证据的执行链。
- 在各 Gate 前得到可复核的 manifest、contract、run record、hash、审查与审批记录。
- 用同一 raw corpus、冻结条件和运行合同，分别交付 Quick-start Native 与 Frozen Optimized Native 结果。
- 在完整执行基线 **65–85 人日**内给出排期，并显式管理风险容量和 re-freeze/re-run。

### 非目标

- 不重定义 TDAS、component metrics、数据配额、Judge 阈值、统计方法或报告结构。
- 不生成加权总分、排行榜或“总体赢家”，不把 MOI 专属能力伪装成共同指标。
- 不把 MOI→Dify、DeerFlow/MCP、NL2SQL、多轮、GraphRAG、安全攻击或其他 v0.3 延后项并入核心执行。
- 不把 Pilot、Smoke、retry 或 Controlled Generation 结果替代 Formal Native 结果。
- 不把尚未验证的产品能力、运行时默认值、部署等价性或商业条件写成已确认事实。

## 2. 角色与责任边界

| 角色 | 主责 | 必须交接 |
|---|---|---|
| **RAG Owner** | 范围、资源、依赖、Gate readiness、变更与跨文档一致性 | 向 Approver 提交完整证据包；向全体同步 freeze/hash |
| **Benchmark Engineer** | contracts、adapters、harness、observability、工程测试与可复现执行 | 向 Operator 交付版本化 runbook；向 Data & Eval 交付规范化 artifacts |
| **Data & Eval Engineer** | corpus、fresh-control、问题/Gold、Judge、抽样、统计和 lineage | 向工程侧交付冻结 schema；向 Reviewer 交付盲化审计包 |
| **System Operator** | 系统配置、建库、查询、观察、恢复和动作/耗时记录 | 不修改 Gold/Judge；按冻结 runbook 输出 run_id、状态和证据 |
| **Reviewer** | 独立/盲化复核 Gold、Judge、运行异常、统计和报告 | 提交争议与 adjudication 记录，不静默修正 raw records |
| **Approver** | 身份/安全、freeze、invalid/replacement、Gate、发布签字 | 在看分前处理排除；外部等待不计人日 |

具体任务的“角色”列先列主责，再列必要协作/复核者。Reviewer/Approver 的独立性要求沿用 v0.3。

## 3. 完整逐步计划

### A. 治理、身份与研究（9–12 人日）

| ID | Checkbox | 工作 | 依赖 | 角色 | 产物 | DoD | 人日 | 日历窗 |
|---|---|---|---|---|---|---|---:|---|
| M01 | - [ ] | 建立执行登记、角色、decision/Gate/change log 与 parent plan 版本基线 | 无 | RAG Owner | 执行登记、责任表、plan commit/hash | 01–05 ID 可追踪；母计划版本、当前 Gate、升级路径已记录 | 1 | W1 |
| M02 | - [ ] | 核实 MOI 身份、部署、前后端版本、租户、区域和 Entitlement | M01 | RAG Owner、System Operator、Approver | 签名 system manifest、身份证据索引 | 字段齐全；来源/日期/构建可复核；未知项显式阻塞而非推断 | 2 | W1 |
| M03 | - [ ] | 建立账户/权限、数据访问、egress/retention 审批与密钥操作边界 | M01–M02 | RAG Owner、System Operator、Approver | 访问矩阵、安全审批索引、密钥 runbook | 最小权限可用；baseline/fresh 数据处理路径获准；秘密不入库 | 1–2 | W1–W2 |
| M04 | - [ ] | 研究 MOI Native Explore/API 自动化、trace/citation/source-map 导出与身份边界 | M01–M02 | RAG Owner、Benchmark Engineer、Reviewer | [研究计划](02-research-plan.md)对应证据包 | P0 问题均为 confirmed/confirmed unavailable/blocked；Smoke 路径有决定 | 2–3 | W1–W2 |
| M05 | - [ ] | 研究运行时组件/defaults、运维语义、部署 parity、安全、quota/pricing | M02–M03 | Benchmark Engineer、System Operator、Reviewer | runtime/ops/commercial capability matrix | 每项有目标部署证据或明确 gap；正式配置可冻结字段已识别 | 2–3 | W1–W2 |
| M06 | - [ ] | 研究 Dify/FastGPT 等价能力及 Judge/metric 实现证据 | M01 | Data & Eval Engineer、Benchmark Engineer、Reviewer | 跨产品能力矩阵、Judge 证据矩阵 | “等价/缺失/不可观察”有逐项依据；实现选择不改写 v0.3 公式 | 1 | W1–W2 |

### B. Corpus、fresh-control 与数据集（10–13 人日）

| ID | Checkbox | 工作 | 依赖 | 角色 | 产物 | DoD | 人日 | 日历窗 |
|---|---|---|---|---|---|---|---:|---|
| M07 | - [ ] | 重验 public_baseline 文件、页数、hash、license、sensitivity、egress 与 family | M03、M05 | Data & Eval Engineer、Reviewer | dataset manifest、校验报告 | 观测的 46 PDF 基线被重新核验；差异留痕；禁止把旧观测当最终事实 | 2–3 | W2–W3 |
| M08 | - [ ] | 创作并验证 8–12 份带版本标识的 egress-safe fresh-control PDF | M03、M05 | Data & Eval Engineer、Reviewer、Approver | fresh corpus、manifest、生成 lineage | private-or-fictional、真实感、版本/授权/访问/保留期完整；hash 冻结 | 3–4 | W2–W4 |
| M09 | - [ ] | 落地文件、问题、claim/evidence、citation、split 与 analysis cluster schema | M06 | Data & Eval Engineer、Benchmark Engineer | 版本化 schema、validators、rubric | 覆盖 v0.3 必填字段、替代 evidence sets、空集/边界；验证器有测试 | 2 | W2–W3 |
| M10 | - [ ] | 构建 dev、Smoke 与 180–240 hidden formal 候选问题/Gold，建立 lineage | M07–M09 | Data & Eval Engineer、Reviewer | [数据集与评测计划](03-dataset-and-evaluation-plan.md)产物、split manifest | 题型互斥配额、正交标签、document family/near-duplicate component 20/80 隔离通过；fresh hidden 30–40；Gold 不来自产品输出；Formal 保持 pre-freeze | 3–4 | W3–W5 |

### C. Contracts、adapters、harness 与 observability（12–15 人日）

| ID | Checkbox | 工作 | 依赖 | 角色 | 产物 | DoD | 人日 | 日历窗 |
|---|---|---|---|---|---|---|---:|---|
| M11 | - [ ] | 实现 task/system/config/run/artifact/judge contracts 与 validators | M04、M06、M09 | Benchmark Engineer、Data & Eval Engineer | `rag/benchmark/` contracts/tests | 字段、枚举、hash、run/replacement lineage 与 v0.3 一致；正反例测试通过 | 2–3 | W2–W3 |
| M12 | - [ ] | 实现 MOI Native adapter 与批准的 UI/API 自动化路径 | M04、M11 | Benchmark Engineer、System Operator | MOI adapter、fixture、runbook | 从 raw file 到 Native answer 可复跑；raw response/status/error/artifact 保存；不混入集成路径 | 2–3 | W3–W4 |
| M13 | - [ ] | 实现 Dify、FastGPT 原生 adapter 与语义等价 instruction | M06、M11 | Benchmark Engineer、System Operator | 两个 adapter、fixture、runbook | 各自从相同 raw file 开始；能力缺口显式编码；同一请求合同可校验 | 3 | W3–W4 |
| M14 | - [ ] | 实现三次隔离 repeat、initial-first、retry 诊断、batch/invalid/replacement 控制 | M11–M13 | Benchmark Engineer | harness、状态机、故障测试 | 产品/API failure 计有效零分；retry 不替换 initial；batch failure 与 replacement 规则测试通过 | 2–3 | W3–W4 |
| M15 | - [ ] | 实现 artifact/hash/source-map/trace/citation/timing/cost 采集与 failure taxonomy | M11–M14 | Benchmark Engineer、Data & Eval Engineer | artifact store contract、observability matrix | 可观察字段原样保存；不可观察标 gap；citation 与 retrieval trace 分离；失败可归层 | 2 | W3–W4 |
| M16 | - [ ] | 实现规范 metric、Judge I/O 与 paired cluster bootstrap 骨架 | M09、M11、M15 | Data & Eval Engineer、Benchmark Engineer | evaluator/analysis tests | 公式、eligible set、rounding、N/A、三次均值和 10,000 次 cluster bootstrap 有 golden tests | 1 | W3–W4 |

### D. Smoke 与 Judge Gate（8–10 人日）

| ID | Checkbox | 工作 | 依赖 | 角色 | 产物 | DoD | 人日 | 日历窗 |
|---|---|---|---|---|---|---|---:|---|
| M17 | - [ ] | 对 10–15 个 document families、30–50 题执行三产品 Native Smoke | M07、M10、M12–M16 | System Operator、Benchmark Engineer、Data & Eval Engineer | Smoke runs、artifact completeness/defect report | 原生 journey 可运行；ready/失败可判；关键 raw/artifact/error 可保存；Smoke 不混入正式分数 | 3–4 | W5 |
| M18 | - [ ] | 修复 benchmark-side 缺陷并重跑受影响 Smoke；冻结 artifact contract | M17 | Benchmark Engineer、Data & Eval Engineer、Reviewer | defect closure、合同签名、重跑 lineage | 基准缺陷有复现/修复测试；旧 run 保留；产品失败未被改写为 benchmark fault | 2 | W5–W6 |
| M19 | - [ ] | 完成至少 30-answer Judge calibration、双 Reviewer/adjudication 与 Gold audit；通过 Smoke 后冻结 hidden formal dataset/Judge | M10、M16–M18 | Data & Eval Engineer、Reviewer、Approver | calibration pack、kappa/Gold validity 记录、dataset/Judge 签名 | 覆盖三系统与规定 strata；claim-level quadratic weighted kappa ≥0.60；Gold validity ≥95%、critical error=0；Formal lineage 只在 Smoke Gate 后锁定 | 3–4 | W5–W6 |

### E. Quick 与 Optimized freeze（8–11 人日）

| ID | Checkbox | 工作 | 依赖 | 角色 | 产物 | DoD | 人日 | 日历窗 |
|---|---|---|---|---|---|---|---:|---|
| M20 | - [ ] | 选择并冻结 Quick-start 官方默认/模板、用户画像、tie-break 与 support budget | M04、M06、M17–M18 | RAG Owner、System Operator、Approver | Quick config manifests、onboarding/support 脚本 | 三系统选择规则一致且可复核；版本、动作、时间窗和 vendor help 预算签名 | 2–3 | W5–W6 |
| M21 | - [ ] | 预注册 Optimized allowed search space、trial/人时/墙钟/动作/支持预算和 stop rule | M10、M19–M20 | RAG Owner、Data & Eval Engineer、Approver | tuning protocol、预算 ledger | 只允许 dev split；三系统上限等额；hidden 不可访问；停止条件可机械执行 | 1–2 | W6 |
| M22 | - [ ] | 在 dev split 内执行等额调优并冻结最终 Optimized manifests | M21 | System Operator、Benchmark Engineer、Data & Eval Engineer | trial ledger、dev artifacts、配置签名 | 每次 trial/动作/人时可追溯；未越预算；最终配置按预注册规则选出并签名 | 5–6 | W6–W7 |

### F. Formal runs 与批次完整性（7–9 人日）

| ID | Checkbox | 工作 | 依赖 | 角色 | 产物 | DoD | 人日 | 日历窗 |
|---|---|---|---|---|---|---|---:|---|
| M23 | - [ ] | 用冻结 corpus/config 建库，确认 processed+embedded+searchable 与 Gold preservation | M08、M10、M18–M19 | System Operator、Data & Eval Engineer、Reviewer | formal readiness records、manifest/hash | required evidence source 全部按产品记录 ready/失败；UI“完成”不替代 searchable 验证；失败不删题 | 2–3 | W6–W7 |
| M24 | - [ ] | 执行 Quick-start hidden formal 三次 initial repeat 与诊断 retry | M20、M23 | System Operator、Benchmark Engineer | immutable Quick run batches | 180–240 题、三系统、三次隔离 repeat 完整；顺序轮换/fresh session；raw/hash/cost/error 齐全 | 2 | W7–W8 |
| M25 | - [ ] | 执行 Optimized hidden formal 三次 initial repeat 与诊断 retry | M22–M23 | System Operator、Benchmark Engineer | immutable Optimized run batches | 与 Quick 分开；同一 formal set/运行合同；所有 initial/product failure 入分母 | 2–3 | W8–W9 |
| M26 | - [ ] | 盲检 batch 完整性，处理 benchmark fault、invalid/replacement 或整批重跑决定 | M24–M25 | Reviewer、Approver、RAG Owner | completeness ledger、审批与 replacement lineage | 看分前签字；同 batch >1 benchmark fault 按 v0.3 停止/重冻结/整批重跑；无静默删除 | 1 | W8–W9 |

### G. MOI diagnostics、审计统计与发布（11–15 人日）

| ID | Checkbox | 工作 | 依赖 | 角色 | 产物 | DoD | 人日 | 日历窗 |
|---|---|---|---|---|---|---|---:|---|
| M27 | - [ ] | 独立验证 MOI topology/config export、artifact/preview/page map、eligible/disabled chunk、selected-file、job/retry/lineage/export | M12、M17–M18 | Benchmark Engineer、System Operator、Reviewer | MOI Capability Validation evidence | 每项为 pass/fail/unavailable/gap 且有证据；不折入横向共同分数 | 2–3 | W6–W8 |
| M28 | - [ ] | 执行预注册 reset/rebuild 与安全允许的 recovery diagnostics | M14–M15、M23 | System Operator、Reviewer | 前后 hash、状态时间线、动作/耗时、恢复结果 | 代表子集恢复到签名状态；诊断 run 与 Formal 分离；fault 场景有终止/censoring 规则 | 1 | W7–W8 |
| M29 | - [ ] | 执行固定盲化人工 audit、双 Reviewer 与争议 adjudication | M19、M24–M26 | Reviewer、Data & Eval Engineer | audit sample/labels、争议记录 | distinct hidden question 配额为 `max(40, 20%)`；覆盖所有 system×condition 的指定 repeat；争议扩展不挤配额 | 3–4 | W8–W9 |
| M30 | - [ ] | 计算规范指标、TDAS 分层、run variance、paired cluster bootstrap 与 95% CI | M26、M29 | Data & Eval Engineer、Reviewer | analysis outputs、reproducibility log | 先 repeat 均值再 question 宏平均；cluster paired resample 10,000 次；无 weighted total | 1 | W9 |
| M31 | - [ ] | 对账问题/运行分母、缺失能力、stage failure、cost/latency 与 audit 结果 | M26、M30 | Data & Eval Engineer、Reviewer | reconciliation checklist | 所有 frozen question×system×condition×repeat 有去向；N/A/gap/invalid/replacement 可追溯 | 1 | W9 |
| M32 | - [ ] | 编写 Common scorecard、Stage diagnostics、条件/语料分层、MOI 诊断、限制与失败报告 | M27–M31 | RAG Owner、Data & Eval Engineer、Reviewer | `rag/reports/` 发布候选、[结果模板](05-acceptance-and-result-template.md) | Quick/Optimized、baseline/fresh 分开；只报可观察 diagnostics；不发布 winner | 2–3 | W9–W10 |
| M33 | - [ ] | 完成 Gate/发布审批、版本化归档、README/current-plan 更新与复现交接 | M32 | RAG Owner、Approver、Reviewer | 签名验收、release index、commit/hash | 批准清单齐全；私有 payload 未入 Git；计划/数据/系统/运行/报告版本互链 | 1–2 | W10 |

**基线合计：65–85 人日。** 其中治理/研究 9–12、corpus/数据 10–13、工程 12–15、Smoke/Judge 8–10、配置/调优 8–11、Formal 7–9、MOI/审计/统计/发布 11–15。外部等待不计人日。

## 4. 阶段门禁

| Gate | 进入条件 | 退出证据 | 失败动作 |
|---|---|---|---|
| G0 执行治理 | M01 启动 | 角色、plan/hash、日志和升级路径可用 | 停止新增执行分支，先补治理 |
| G1 身份/部署/权限 | G0 | MOI 身份、版本/租户/区域/Entitlement 签名；访问与安全路径获准 | 身份不明或数据路径未批准则停止 |
| G2 研究与 corpus/security | G1 | P0 决策证据；automation/trace 能力已确认；baseline/fresh manifest、hash、授权、egress 通过 | 标 BLOCKED；不可用能力按 v0.3 披露，不用推断替代 |
| G3 Native path 与 artifact contract | G2 | 三产品 Native journey、adapters/harness、ready/artifact/failure contract 可验证 | 不进入扩展 Smoke；修复后保留旧证据并重验 |
| G4 Smoke | G3 | 30–50 题/10–15 families 完成；关键 artifact 可保存；benchmark 缺陷关闭 | 修复、重冻结受影响合同并重跑 Smoke |
| G5 Dataset/Judge | G4 | schema/配额/split/lineage、calibration/kappa、Gold audit 全通过 | 失败 strata 全审或重建；不得开始 Formal |
| G6 Quick freeze/run | G5 | 默认选择/support budget 签名；完整三次 initial records | 批次按 invalid/replacement 合同处理 |
| G7 Optimized freeze/run | G5、G6 可并行尾段 | bounded dev tuning 签名；完整三次 initial records | 越预算或触碰 hidden 则配置无效并重冻结 |
| G8 Blind audit/report/release | G6–G7 | CI、审计、分母、缺失能力、失败归因、限制、审批齐全 | 不发布；补证据或触发 re-freeze/re-run |

Gate 只判“能否进入下一阶段”，不创造 v0.3 之外的验收标准。

## 5. 并行流与关键路径

| 流 | W1–W2 | W2–W4 | W5–W6 | W6–W8 | W8–W10 |
|---|---|---|---|---|---|
| 治理/研究 | 身份、权限、P0 研究 | 决策收口、变更控制 | Gate/预算签字 | invalid/freeze 监督 | 发布审批 |
| 数据/评测 | corpus 盘点 | fresh、schema、问题/Gold | Smoke 分析、Judge calibration | formal freeze、审计准备 | 人工 audit、统计、报告 |
| 工程 | contract 设计 | adapters、harness、observability | Smoke 修复 | Formal 执行支持 | 完整性与复现交接 |
| 系统运行 | 账户/原生路径探查 | fixture 与 runbook | Smoke、Quick 配置 | dev tuning、建库、Quick run | Optimized run、MOI diagnostics |
| 独立保证 | 证据方法复核 | schema/合同复核 | Gold/Judge/Gate | batch 盲检 | audit、CI、发布复核 |

关键路径为：

`M01 → M02/M03 → M04–M06 → M07–M16 → M17/M18 → M19 → M20–M23 → M24/M25 → M26/M29 → M30–M33`

fresh-control 与工程可在研究决定稳定后并行；03 与 04 的工作必须在 M09/M11、M17/M18、M19/M20 和 M23 等会合点同步签名。

## 6. 8–10 周日历建议

| 周 | 主要结果 |
|---|---|
| W1 | 治理基线、MOI 身份/部署、账户权限、P0 研究启动 |
| W2 | 研究结论第一版、baseline 重验、fresh 设计、schema/contracts |
| W3 | fresh 制作、数据集生成、三产品 adapters 与 harness |
| W4 | hidden/Smoke 数据、observability、evaluator/analysis 工程就绪 |
| W5 | 30–50 题 Smoke、问题归因、Quick 候选配置 |
| W6 | Smoke 修复闭环、Judge/Gold Gate、Quick freeze、Optimized 协议 |
| W7 | dev tuning、formal readiness/build、Quick Formal 启动 |
| W8 | Quick 完成、Optimized Formal、MOI capability/recovery diagnostics |
| W9 | Formal 完成与批次对账、人工 audit、统计/CI |
| W10 | 报告、限制披露、审批、归档与交接 |

另预留一个 **R 周**用于一次受控 re-freeze/re-run；它不包含在 W1–W10 基线中。触发时冻结受影响范围、保留旧 run_id/hash，按 v0.3 整体替换规则执行，并相应顺延审计/发布。若未触发，R 周不转化为扩题或选择性重跑。

3–4 FTE 的建议不是把所有任务同时启动；Gate、产品运行等待和独立复核决定了 8–10 周日历。单 FTE 按相同依赖顺序约 13–17 周。账户开通、供应商回复和外部审批可能额外延长日历，但不计入人日。

## 7. Pilot 与 Formal

| 项目 | Pilot | Formal |
|---|---|---|
| 目的 | 证明 Native journey、adapter、artifact、Judge 和运行合同可行 | 产生可发布、可审计的 v0.3 正式结果 |
| 规模/工期 | 20–28 人日，3–4 周；以 30–50 题、10–15 families 的 Smoke 为核心 | 65–85 人日，3–4 FTE 8–10 周；180–240 hidden formal 题，含 30–40 fresh-control |
| 配置 | 可用候选默认和 dev fixture 探路，所有结果标 pre-freeze | Quick 与 Optimized 分别签名并严格隔离 |
| 重复/审计 | 可验证三次机制和抽样流程，但不构成正式分母/配额 | 每题三次 scored initial attempt；固定人工 audit 与 10,000 次 paired cluster bootstrap |
| 可发布结论 | 仅 feasibility、gap、风险、估时修订 | 按 v0.3 分层报告 component metrics/TDAS、CI、失败与限制 |
| 验收效力 | **不可通过正式验收，不可替代 Formal** | 只有 G0–G8 与批准清单完整才可验收 |

Pilot 发现的产品失败不自动代表 Formal 结论；Pilot 产物只有在重新验证、冻结并建立 lineage 后才能作为 Formal 工程输入。

## 8. 风险与缓冲

- 基线之外预留 **13–26 人日（20%–30%）**，只在触发器出现时使用：benchmark 缺陷、产品版本漂移、Gold/lineage 返工、Judge Gate 失败、批次级 benchmark fault 或安全/egress 变更。
- 日历另留一次 R 周。重跑范围由 v0.3 的 batch/replacement 规则和 Approver 决定，禁止按分数选择性重跑。
- 每次使用缓冲记录触发器、批准人、消耗人日、受影响 ID/签名、旧新 run lineage 和剩余额度。
- 外部审批等待、供应商回复、配额开通和产品队列不消耗人日，但在周状态中单列 elapsed delay。
- 若风险容量不足，RAG Owner 必须提交范围/日期变更；不得静默降低 hidden 规模、重复数、人工 audit 或 Judge Gate。

## 9. 每周状态模板

```markdown
# RAG v0.3 周状态：W__

- 周期：
- Parent plan / commit / dataset / system / evaluator 签名：
- 当前 Gate：进入条件__；已满足__；未满足__
- 本周完成：M__（产物链接、hash/run_id、DoD 证据）
- 进行中：M__（负责人、预计完成日、依赖）
- 下周计划：M__（主责、会合点）
- BLOCKED：事项、首次发生时间、影响 Gate、决策人、下一检查时间
- 运行完整性：有效/无效/replacement/batch failure 数及审批链接
- 数据与安全：manifest/egress/retention/访问变化
- 人力：本周实际__人日；累计__ / 65–85；风险容量消耗__ / 13–26
- 日历：产品运行等待__；外部审批等待__（均不计人日）
- 风险：触发器、概率/影响、缓解、是否申请 R 周
- Reviewer/Approver：待复核项、决定、日期
- 变更控制：受影响合同/配置/Judge/data，是否 re-freeze/re-run
```
