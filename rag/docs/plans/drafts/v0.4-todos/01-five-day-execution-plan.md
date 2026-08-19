# v0.4 单人五日执行计划

> 母计划（权威）：[`../v0.4.md`](../v0.4.md) ｜ 预算：40h ｜ MOI only

## 1. 逐时任务

| ID | 时段 | hours | 依赖 | 任务与产物 | DoD / Gate |
|---|---|---:|---|---|---|
| D1-01 | D1 09:00–10:00 | 1 | — | 冻结目标、非目标、40h 上限、失败/invalid/retry 合同和 decision log | scope 不含 comparator/调优/通用 harness |
| D1-02 | D1 10:00–12:00 | 2 | D1-01 | 核验 MOI 身份、版本、权限、egress/retention；用 1 PDF 做 Native upload→ready→query→artifact proof | 身份、安全和 Native proof 可追溯，否则 `[!] BLOCKED` |
| D1-03 | D1 13:00–16:00 | 3 | D1-02 | 选择 4 existing，制作/选取 2 fresh；完成 6-file manifest、hash、family split 和授权 | 6 PDFs；dev=2、scored=4；无 family 泄漏 |
| D1-04 | D1 16:00–18:00 | 2 | D1-03 | 建立 question/Gold/run/citation ledger、artifact 路径、rubric 骨架和校验清单 | **G0：scope/identity/safety/manifest/storage 通过** |
| D2-01 | D2 09:00–11:00 | 2 | G0 | ingest/index 6 PDFs，记录 job、ready/failure、页面、人工动作与 search probe | 6 files 均有明确状态和证据 |
| D2-02 | D2 11:00–13:00 | 2 | D2-01 | 运行 6 Smoke/dev，保存 raw response、citation、status、latency | 6 outputs 可回放；不进入 scored 分母 |
| D2-03 | D2 14:00–15:00 | 1 | D2-02 | 只修复阻断 Pilot 的配置/捕获问题，冻结 MOI Quick-start | 不调优，不根据质量分数改配置 |
| D2-04 | D2 15:00–18:00 | 3 | D2-03 | 起草 20 scored questions、claims、evidence sets 和配额账本 | **G1：Native journey/Smoke 通过；20题 Gold 草案可复核** |
| D3-01 | D3 09:00–13:00 | 4 | G1 | 完成并逐题复核 Gold、critical/scored claims、source/page/span/hash、answerability | 20题配额 6/4/4/2/4；fresh=4；citation-required=10 |
| D3-02 | D3 14:00–16:00 | 2 | D3-01 | 用 6 Smoke 各一次 + 预选2题第二次形成8 outputs；打乱后标注，修订并冻结 rubric/N/A/阈值 | calibration=8；Judge/rubric hash 在 scored 前冻结 |
| D3-03 | D3 16:00–17:00 | 1 | D3-02 | 预抽 6-question self-audit sample；每题固定 repeat1+repeat2；覆盖关键 strata | audit manifest=6 questions/12 rows |
| D3-04 | D3 17:00–18:00 | 1 | D3-03 | 冻结 corpus/question/Gold/rubric/run order/retry 和 hashes | **G2：全部 freeze 完成；之后不得看结果改合同** |
| D4-01 | D4 09:00–11:30 | 2.5 | G2 | 执行 MOI repeat 1 的 20 initial attempts | 20 个 unit 均有 status/raw/artifact |
| D4-02 | D4 11:30–14:00 | 2.5 | D4-01 | fresh sessions + 冻结轮换顺序执行 repeat 2 | 累计 40 initial attempts |
| D4-03 | D4 15:00–16:00 | 1 | D4-02 | 对账 coverage、error、retry、invalid/replacement 和 hashes | 计划数=实际去向；产品失败未删除 |
| D4-04 | D4 16:00–18:00 | 2 | D4-03 | 规范化 response/claims/citations，并开始按冻结 rubric 主判分 | **G3：两 repeats 完整，主判分可继续** |
| D5-01 | D5 09:00–10:30 | 1.5 | G3 | 完成 40 attempts 的主判分与理由 | 每个 unit 有 TDAS/component/N/A reason |
| D5-02 | D5 10:30–11:30 | 1 | D5-01 | 重新检查预抽的 12 self-audit rows，记录 label change/reason | 不覆盖初判；保留前后标签 |
| D5-03 | D5 11:30–13:00 | 1.5 | D5-02 | 计算分母、每-repeat描述区间、question mean、flip counts、readiness/reliability/operability | 指标可从 ledger 重算 |
| D5-04 | D5 14:00–16:00 | 2 | D5-03 | 写成功/失败案例、限制、唯一结论等级和下一轮建议；互链 artifacts | **G4：报告和证据包完整** |
| D5-05 | D5 16:00–18:00 | 2 | D5-04 | contingency：仅补证据、复核、hash/格式/归档 | 不扩题、不接产品、不调优；超时即降级 |

**工时核对：D1 8h + D2 8h + D3 8h + D4 8h + D5 8h = 40h。**

## 2. 每日停线检查

- D1 结束：无身份、安全、Native proof 或合法 corpus，停止并 `BLOCKED`。
- D2 结束：Native journey/Smoke 不可回放，停止 scored，交付 `DIAGNOSTIC_ONLY`。
- D3 结束：20 题、Gold、rubric、calibration 或 hash 未冻结，禁止 scored。
- D4 结束：40 initial units 不可对账或缺第二 repeat，结论最高 `DIAGNOSTIC_ONLY`。
- D5 结束：不加班补齐，不缩分母；按实际证据选择唯一结论等级。

## 3. 资源不足时的降级顺序

1. 删除可选 trace 深诊断和额外案例；
2. 停止任何未冻结的新功能、新脚本和额外 retry；
3. 保留 20题×2 repeats、全量主判分、分母账本和失败证据；
4. 仍无法完成时停止，并把结果降为 `DIAGNOSTIC_ONLY`；不得减少题数后仍声称按 v0.4 完成。
