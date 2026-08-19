# v0.4 验收与结果模板

> 母计划：[`../v0.4.md`](../v0.4.md) ｜ MOI only ｜ sealed scored pilot set=20

统一状态：`[ ]` 未开始、`[>]` 进行中、`[x]` 完成、`[!]` 阻塞/失败、`[-]` 不适用。`[-]` 必须带 reason。

## 1. G0–G4 验收

| Gate | 与母计划一致的通过条件 | 状态 | 证据链接/hash | 失败或 N/A reason |
|---|---|---|---|---|
| G0 Identity/Safety/Scope | MOI 身份、版本、权限、Native proof、egress、6-file manifest 和 artifact 保存可验证 | `[ ]` |  |  |
| G1 Native Journey/Smoke | 6 files 有 ready/failure 证据；6 Smoke 可发出并保存 raw/status/citation | `[ ]` |  |  |
| G2 Dataset/Rubric Freeze | 20题、8 calibration、Gold/rubric、6-question audit、run order 与 hash 在 scored 前冻结 | `[ ]` |  |  |
| G3 Scored Run | 20题×2 repeats=40 initial units 均有可追溯去向；产品失败仍在分母 | `[ ]` |  |  |
| G4 Score/Audit/Report | 40次主判分、12-row self-audit、核心指标、failure taxonomy、限制和 artifacts 可重算 | `[ ]` |  |  |

## 2. 数据与运行账本

| 项目 | 计划 | 实际 | 状态 | 证据/备注 |
|---|---:|---:|---|---|
| existing PDFs | 4 |  | `[ ]` |  |
| fresh PDFs | 2 |  | `[ ]` |  |
| Smoke/dev questions | 6 |  | `[ ]` | 不进入 scored |
| calibration outputs | 8 |  | `[ ]` | scored 前完成 |
| sealed scored questions | 20 |  | `[ ]` | 配额 6/4/4/2/4 |
| fresh scored | 4 |  | `[ ]` |  |
| citation-required answerable | 10 |  | `[ ]` |  |
| repeat 1 initial units | 20 |  | `[ ]` |  |
| repeat 2 initial units | 20 |  | `[ ]` |  |
| total initial units | 40 |  | `[ ]` | product failure 不删除 |
| self-audit questions | 6 |  | `[ ]` | 每题两个 repeats |
| self-audit rows | 12 |  | `[ ]` | 非独立审计 |

完整性检查：

- [ ] 每个 `question_id × repeat_id` 有 run/status/raw/timestamp/artifact 去向。
- [ ] retry 未替换 initial；product failure 未被标成 invalid。
- [ ] 空 claim、Gold lineage、family leakage 和 citation-required 配额均通过 freeze validator。
- [ ] freeze 后未根据 MOI 输出修改 question、Gold、rubric、阈值或 run order。
- [ ] 所有 N/A 都有 reason；`TRACE_UNAVAILABLE` 未被解释为成功或失败。

## 3. Pilot-TDAS 与 question-level 结果

Wilson 只作 question-level 二元指标的描述区间；每个指标使用实际 eligible distinct-question 分母。Pilot-TDAS 每个 repeat 的 N=20。两 repeat question mean 不填 Wilson。

| metric | repeat 1 numerator / denominator | repeat 1 rate / Wilson 95% | repeat 2 numerator / denominator | repeat 2 rate / Wilson 95% | two-repeat question mean / summary | evidence |
|---|---|---|---|---|---|---|
| Pilot-TDAS | /20 |  | /20 |  |  |  |
| strict unanswerable success | /4 |  | /4 |  |  |  |
| false refusal | /16 |  | /16 |  |  |  |
| critical contradiction-free | /16 |  | /16 |  |  |  |
| citation-required gate pass | /10 |  | /10 |  |  |  |
| initial availability | /20 |  | /20 |  |  |  |

## 4. Component、readiness、reliability 与 operability

Claim/citation-level rate 不生成 CI；必须给实际 numerator/denominator，并按母计划 §5.1 先拆分、去重 canonical factual claims。无法观察时写 `N/A + reason`。

| layer | metric | numerator | denominator | rate/value | N/A/gap | evidence/notes |
|---|---|---:|---:|---:|---|---|
| Readiness | accepted files |  | 6 |  |  |  |
| Readiness | searchable-ready files |  | 6 |  |  |  |
| Readiness | accepted/ready pages |  |  |  |  |  |
| Readiness | Gold evidence preservation probe |  |  |  |  |  |
| Answer | Correctness |  |  |  |  |  |
| Answer | critical-required claim coverage |  |  |  |  |  |
| Answer | Reference-claim Recall |  |  |  |  |  |
| Answer | Gold-evidence Support |  |  |  |  |  |
| Citation | locator/resolvability validity |  |  |  |  | zero submitted=`NO_SUBMITTED_CITATION` |
| Citation | entailment precision |  |  |  |  | zero submitted=`NO_SUBMITTED_CITATION` |
| Citation | answer-claim coverage |  |  |  |  | required but zero submitted=0 |
| Reliability | timeout/error |  | 40 |  |  |  |
| Reliability | retry recovery（diagnostic） |  |  |  |  | 不回写 initial |
| Reliability | P50/P95 latency |  |  |  |  | terminal+timestamp only |
| Operability | Time-to-First-Searchable-Corpus |  |  |  |  |  |
| Operability | Time-to-First-Trusted-Answer |  |  |  |  |  |
| Operability | active human minutes / interventions |  |  |  |  |  |
| Trace-only | trace metrics |  |  |  |  | 真实 trace+rank+qrels 才计算 |

两次 repeat 翻转：

| pass/pass | pass/fail | fail/pass | fail/fail | total distinct questions | representative cases |
|---:|---:|---:|---:|---:|---|
|  |  |  |  | 20 |  |

## 5. Self-audit（6 questions × 2 repeats）

抽样在 scored run 前冻结。主判分完成后再复核；保留初判与复核，不静默覆盖。

| question_id | repeat_id | type/fresh/citation-required | initial TDAS/components | recheck TDAS/components | label changed | reason | artifact |
|---|---:|---|---|---|---|---|---|
| Q- | 1 |  |  |  |  |  |  |
| Q- | 2 |  |  |  |  |  |  |
| Q- | 1 |  |  |  |  |  |  |
| Q- | 2 |  |  |  |  |  |  |
| Q- | 1 |  |  |  |  |  |  |
| Q- | 2 |  |  |  |  |  |  |
| Q- | 1 |  |  |  |  |  |  |
| Q- | 2 |  |  |  |  |  |  |
| Q- | 1 |  |  |  |  |  |  |
| Q- | 2 |  |  |  |  |  |  |
| Q- | 1 |  |  |  |  |  |  |
| Q- | 2 |  |  |  |  |  |  |

Self-audit label changes：`___ / 12`。

主要原因：`___`。

限制：同一人复核，不计算 QWK，不声明 reviewer independence。

## 6. 失败与案例

| stage | count | affected files/questions/runs | product / benchmark / unknown | evidence | next action |
|---|---:|---|---|---|---|
| ingest/parse |  |  |  |  |  |
| embed/index/ready |  |  |  |  |  |
| scope/retrieval |  |  |  |  |  |
| answer/citation |  |  |  |  |  |
| platform/API |  |  |  |  |  |

至少保留 2 个成功案例和 4 个不同阶段的失败/边界案例；若无对应失败，写 0 和证据，不为凑案例制造故障。

## 7. 唯一最终结论

- [ ] `PILOT_COMPLETE`：G0–G4 全通过，40 initial attempts、判分、自审、指标和 artifacts 可重算。
- [ ] `DIAGNOSTIC_ONLY`：Native journey 有证据，但 G1–G4 任一核心项不完整；不得发布 benchmark 质量结论。
- [ ] `BLOCKED`：身份、权限、Native path、授权或安全条件不满足。
- [ ] `INVALID`：freeze/Gold/schema/run lineage 不可修复，结果不能解释。

选择：`__________`

一句话结论：`__________`

下一轮只做的三件事：`1. ______  2. ______  3. ______`

## 8. 发布限制

- [ ] 不比较其他产品/模型，不发布赢家、排名或加权总分。
- [ ] 不把 n=20 的描述结果解释为统计证明或生产级泛化。
- [ ] 不做显著性检验、McNemar、bootstrap、双审或 QWK。
- [ ] 不把 Smoke、retry、trace gap、N/A 或删题当作 scored 成功。
- [ ] 明确披露单人同时建 Gold、运行、判分和复核的偏差风险。
