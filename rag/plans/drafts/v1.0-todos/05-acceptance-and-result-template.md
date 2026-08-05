# 05 Gate 验收与结果模板

- [ ] **S-501** 依赖：M-117；预检 G0 evidence。DoD：identity、scope、license、egress 有证据；G1–G4 在对应阶段验收。
- [ ] **S-502** 依赖：S-511；确认 formal Judge/audit freeze。DoD：QWK≥0.60、120-question blind sample、同一 repeat 映射、10,000-replicate bootstrap、seed/CI 均已在 S-517/G2 前锁定。
- [ ] **S-503** 依赖：DP-401/402；解释边界。DoD：Native 对 shared Gold 仅 descriptive native-to-shared-oracle reference delta；同 envelope 才计算 retrieved-context-to-gold-context gap；trace unavailable=N/A。
- [ ] **S-504** 依赖：S-514、S-519；发布质量结果报告。DoD：范围/身份、分母账本、readiness、answer/citation、reliability、可用 replay、案例、限制和唯一结论完整；性能若完成则作为独立 addendum。

## 报告最小表

| 字段 | 内容 |
|---|---|
| `run/freeze` | freeze_id、schema_version、artifact_hash |
| `denominator` | 每个 condition 使用母计划第 6 节公式；initial/retry 分开，不做笼统笛卡尔积 |
| `gate` | G0–G5 状态与证据 |
| `metrics` | numerator、denominator、rate、CI/Bootstrap、N/A reason |
| `conclusion` | Pilot 或 Formal 的唯一状态；Formal 用 `FORMAL_COMPLETE/FORMAL_DIAGNOSTIC_ONLY/BLOCKED/INVALID`，不写总冠军 |

验收禁止：不得按 pilot 分数淘汰资格、不得把 shared oracle 复制为平台样本、不得将 retry 当初次、不得宣称生产就绪。

## Gate 验收表

| ID | Gate | 必须证据 | Owner | 失败动作 |
|---|---|---|---|---|
| S-505 | G0 identity/safety/scope | tenant、license、egress、候选清单 | Program | BLOCKED |
| S-506 | G1 journey/readiness | ready 状态、smoke raw、build log | Operator | DIAGNOSTIC_ONLY |
| S-507 | G2 freeze | gold/rubric/config/run-order hash | Data/Judge | 停止 scored |
| S-508 | G3 run completeness | ledger 对账、artifact、失败分母 | Operator | DIAGNOSTIC_ONLY/INVALID |
| S-509 | G4 scoring/report | judge audit、统计脚本、限制 | Judge | DIAGNOSTIC_ONLY |
| S-510 | G5 performance | env manifest、质量 gate、perf raw | Perf | 不发布性能榜 |

每个 gate 记录 `gate_id,status,checked_at,evidence_paths,owner,decision_id,next_action`；状态不得用空白代替。

## 六层结果表与对账

| 层 | 必报字段 |
|---|---|
| Validity/readiness | planned、terminal、ready、invalid、replacement、hash |
| Answer | correctness、critical recall、reference recall、unanswerable success |
| Citation/evidence | locator validity、entailment、claim coverage、gold support |
| Reliability | availability、timeout/error、pass/pass、翻转、retry recovery |
| Operability | build time、TTF searchable/trusted、human minutes、interventions |
| Trace/diagnostic | evidence recall/context precision/faithfulness（无 trace=N/A） |

对账公式：`planned_initial_units = score-bearing_initial_or_replacement_units + invalid_unreplaced_units + not_started_units`；`request_rows = initial_rows + retry_rows + replacement_rows`。Stage1 必须显示同窗新跑 `MOI 40 + competitors 160 = native 200` 与独立 shared Gold Context oracle 40；formal 显示各 condition 分母。

## 统计与审计

- **S-511** 依赖 D-229、A-332 与 dev/pilot calibration outputs；formal Judge/blind/statistics pre-run freeze。DoD：Judge model/version/prompt/temperature/rubric 已校准且 QWK≥0.60；预抽 120 个不同问题，每题固定所有系统的同一 repeat；`analysis_cluster_id`、10,000 replicates、seed、CI 与缺失处理写入 freeze。未通过不得签 S-517 或运行 M-132。
- **S-512** 依赖 M-132、S-511；运行后盲审/adjudication。DoD：两名 reviewer 独立、system label 隐藏、critical disagreement 有 adjudication；不得在看到 formal 输出后重做 calibration。
- **S-513** 依赖 S-512；paired bootstrap 与 slice audit。DoD：paired CI 可重算；family/type/fresh 小切片只报 counts/rates。
- **S-514** 依赖 S-513；quality release checklist。DoD：hash、链接、版本、各 condition 分母、N/A reason、decision log 均齐全。

## 结论用语

Pilot 允许：`PILOT_COMPLETE`、`DIAGNOSTIC_ONLY`、`BLOCKED`、`INVALID`。Formal 允许：`FORMAL_COMPLETE`、`FORMAL_DIAGNOSTIC_ONLY`、`BLOCKED`、`INVALID`；只说指定 condition/freeze/budget 下的描述或区间。性能是可选 addendum，不是质量报告前置。禁止“生产就绪”“冠军”等。

## 验收任务表

- [ ] **S-515** Owner Program；依赖 M-117；产物 G0 evidence bundle；DoD identity、license、egress、scope 完整；触发运行前。
- [ ] **S-516** Owner Operator；依赖 A-325；产物 G1 readiness bundle；DoD ready/indexed/searchable 与 smoke raw；估时 4h。
- [ ] **S-517** Owner Data/Judge；依赖 D-229、A-332、S-511；产物 G2 freeze bundle；DoD gold/question、Judge calibration、rubric、config、audit sample、统计与 run-order hash 全部签署；估时 3h。
- [ ] **S-518** Owner Operator；依赖 M-132、A-317；产物 G3 reconciliation；DoD 每个 formal condition 的 planned/initial/retry/replacement 独立对账；估时 4h+。
- [ ] **S-519** Owner Judge；依赖 S-513、S-518；产物 G4 scoring bundle；DoD 六层 scorecard、120-question blind audit 与统计脚本可重算；估时 12h+。
- [ ] **S-520** Owner Perf；依赖 DP-436；产物 G5 perf bundle；DoD 环境、censoring、独立报告；估时 6h。
- [ ] **S-521** Owner Program；依赖 S-514、S-519；产物 formal quality decision memo；DoD 唯一 Formal 状态、风险和后续动作；不依赖性能完成；估时 3h。
- [ ] **S-522** Owner Release；依赖 S-504、S-521；产物 quality release checklist；DoD 链接、hash、版本、来源均可访问；估时 2h。
- [ ] **S-523** Owner Release；依赖 S-520；产物 optional performance addendum；DoD G5 环境、分母和 censoring 齐全，并与质量报告分开；估时 2h。

## 结果模板扩展

### 系统/条件行

`system_id | vendor | version | condition | model | config_hash | eligibility | freeze_id | budget_hash`

### 分母账本行

`question_id | repeat_id | system_id | condition | attempt_kind(initial/retry/replacement) | status | error_code | run_id | artifact_hash`

### paired difference 行

`cluster_id | pair | metric | left_condition | right_condition | delta | bootstrap_ci | seed | exclusions_reason`

### Replay gap 行

`question_id | native_score | retrieved_replay_score | gold_oracle_score | no_context_score | noise_score | trace_status | attribution_allowed`

### Performance 行

`hardware_hash | dataset_size | concurrency | read_write_mix | warmup | duration | p50 | p95 | throughput | errors | censored | autoscaling_events`

发布前审计：确认同窗新跑 40/160/200 与独立 Gold Context 40（Stage1）；确认 Quick/Optimized 各自 `600×N×3`、replay=`600×N_trace×R_replay`、Gold=1,800、No-context/Noise 使用冻结 Q/C/R（formal）；N=5 Quick=9,000。确认 retry 不替代 first attempt、shared conditions 无 platform 维度、所有 N/A 有 reason、没有“总冠军”措辞。

Formal bootstrap 固定 10,000 replicates，cluster=`analysis_cluster_id`；`family_id` 只用于泄漏隔离，不与 cluster 混称。seed、CI 方法在 G2 冻结。盲审样本为 `max(40,20%×600)=120` 个不同 formal questions，每题覆盖所有系统与同一预注册 repeat，双审并 adjudication；Judge calibration QWK≥0.60。
