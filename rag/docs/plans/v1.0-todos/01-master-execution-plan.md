# 01 总执行与关键路径

母计划：[`../v1.0.md`](../v1.0.md)。

- [ ] **M-101** 依赖：v1.0 母计划权威声明；建立 decision log、freeze registry、责任人和停止条件。DoD：每次冲突先记录 decision id，再更新母计划。

Gate：G0 范围与身份；G1 数据/adapter 可运行；G2 freeze；G3 ledger 完整；G4 验收报告；G5 性能环境。质量关键路径为 `02 freeze → 03 Native run → 05 quality acceptance`；04 的 replay 是并行诊断支线，performance 只在 S-519 后启动。

## 稳定任务表

| ID | 阶段/Owner | 依赖 | 产物 | DoD | 估时/触发 |
|---|---|---|---|---|---|
| M-106 | S0/Program | v0.4 | S0 checklist | 原样复现 6/6/20/40 与 G0-G4 | 8h；启动即触发 |
| M-107 | S0/Operator | M-106 | MOI ledger | MOI-only、失败留分母 | 16h；G0通过 |
| M-108 | S0/Judge | M-107 | pilot report | 四种结论之一 | 16h；G4 |
| M-109 | S1/Program | M-108 | 5-system scope | 共同时间窗、MOI+四竞品、S0 结果不复用 | 4h；S0 complete |
| M-110 | S1/Operator | M-109 | Stage1 ledger | 同窗新跑 20×5×2=200，四竞品160、MOI40 | 24h；adapter readiness gate |
| M-111 | S1/Gold | D-205 | oracle ledger | 独立 shared oracle 40 | 8h；freeze ready |
| M-112 | S2/Research | source gates | source matrix | 条件、license、用途齐全 | 16h；并行 |
| M-113 | S3/Data | D-242 | Chinese gold | 200/1000、两次 rights Gate 与双审门槛 | 30–50 人日；预算冻结 |
| M-114 | S4/Program | D-229,A-332,S-517 | eligibility freeze | N 与预算批准 | 8h；formal前 |
| M-115 | S4/Operator | M-114,S-517,A-334 | formal ledger | 600×N×3 重算一致 | 按 N；预算冻结 |
| M-116 | S5/Perf | S-519 | perf manifest/report | 50/200 docs 必测；1,000 docs 仅在 D-243 通过时启用；G5 与质量榜分离 | 1–2 周；G4通过 |

## 入口、出口与并行

| 阶段 | 入口 | 出口 |
|---|---|---|
| S0 | MOI identity/license/egress 可用 | 40 attempts 或明确降级 |
| S1 | v0.4 freeze 完整、五系统 capability smoke、共同时间窗已冻结 | 新跑 200 native + shared Gold Context 40 对账；S0 MOI 40 单列历史基线 |
| S2 | source matrix 与启用 gate | 独立诊断 memo |
| S3 | pilot source rights Gate 与审查人 | 50/250 pilot 后，经 expansion rights Gate 完成 200/1000 gold_version |
| S4 | N、预算、环境、judge 冻结 | formal raw 与统计结果 |
| S5 | G4 pass、性能环境冻结 | 独立性能报告 |

可并行：S2 source review 与 S1 adapter smoke；S3 文档生产与 S1 结果审计。不可并行：freeze 前正式运行、G4 前性能、跨版本合并。

## 资源与降级顺序

资源短缺时依次删可选 trace→删额外案例→保住冻结题与 first attempts→停止并交诊断。不得减少失败分母、把 retry 代替初次或只补 MOI/竞品一侧。

## 逐阶段检查清单

- [ ] **M-117** S0 入口：owner Program；依赖 v0.4；产物 identity checklist；DoD 租户、版本、egress、6 PDF 授权均签字；触发 D1。
- [ ] **M-118** S0 corpus：owner Data；依赖 M-117；产物 6-file manifest；DoD 4 existing+2 fresh、family split、hash 完整；估时 3h。
- [ ] **M-119** S0 smoke：owner Operator；依赖 M-118；产物 6 smoke raw；DoD 每题 terminal status 与 artifact；估时 3h。
- [ ] **M-120** S0 scored freeze：owner Judge；依赖 M-119；产物 20 sealed questions；DoD calibration 8 outputs、rubric hash、audit sample；估时 4h。
- [ ] **M-121** S0 repeat：owner Operator；依赖 M-120；产物 40 initial；DoD repeat 1/2 均有 fresh session；估时 5h。
- [ ] **M-122** S0 report：owner Judge；依赖 M-121；产物 pilot report；DoD 唯一结论和限制；估时 5h。
- [ ] **M-123** S1 scope：owner Program；依赖 M-122；产物 system matrix；DoD MOI、四竞品和条件明确；估时 2h。
- [ ] **M-124** S1 smoke：owner Operator；依赖 M-123；产物 adapter smoke log；DoD 失败分类不替换初次；估时 8h。
- [ ] **M-125** S1 native：owner Operator；依赖 A-333；产物 200 native ledger；DoD 同窗新跑 40+160，对账时排除 S0 历史 MOI 40；估时按平台吞吐另计。
- [ ] **M-126** S1 oracle：owner Data；依赖 D-205；产物 shared oracle 40；DoD 无 platform_id；估时 4h。
- [ ] **M-127** S1 closeout：owner Program；依赖 M-125/126；产物 pilot memo；DoD 明确不排名；估时 4h。
- [ ] **M-128** S2 source：owner Research；依赖 D-206–211；产物 source matrix；DoD 每来源用途与禁用条件；估时 3–6 人日。
- [ ] **M-129** S3 pilot：owner Data；依赖预算、D-240、D-202；产物 50/250 report；DoD pilot family/license/egress gate；估时 8–15 人日。
- [ ] **M-130** S3 formal gold：owner Data/Judge；依赖 M-129、D-241、D-242；产物 200/1000 gold；DoD expansion rights、formal 全双审、validity/QWK 门槛；新增工作约 30–50 人日、6–8 周。
- [ ] **M-131** S4 eligibility：owner Program；依赖 D-229、A-332、S-517；产物 frozen eligibility；DoD N、每个 blocked row 与预算批准；估时 8h。
- [ ] **M-132** S4 formal Native run：owner Operator；依赖 M-131、A-334、S-511、S-517；产物 Quick 与可选 Optimized Native ledger/context artifacts；DoD Quick `600×N×3` first-attempt 完整，Optimized 若启用则单独同量；不在此任务运行 replay/shared oracle；按 N/Native condition 计时。
- [ ] **M-133** S4 stats：owner Judge；依赖 M-132、S-512；产物 bootstrap report；DoD `analysis_cluster_id`、10,000 replicates、seed/CI 可重算；估时 24h+。
- [ ] **M-134** S5 perf：owner Perf；依赖 S-519；产物 environment/perf report；DoD 质量榜分离；估时 1–2 周。

停止触发：任何 freeze hash 不一致、关键 schema 缺失、未授权 egress、预算不等价或 planned/initial 无法对账。每次停止必须关联 decision_id 与下一步解锁条件。

## 关键路径记录字段

每阶段账本至少记录 `stage_id,entry_gate,exit_gate,owner,start_at,end_at,planned_hours,actual_hours,wall_clock_hours,blocker,decision_id,next_action`。Program owner 每日核对；小时超预算时先降级，不静默延长。

## 里程碑审查问题

- [ ] **M-135** S0：是否仍仅 MOI、无 comparator、无调优？
- [ ] **M-136** S1：是否同窗新跑 40+160=200、排除 S0 历史 40，并把 shared Gold Context 40 独立对账？
- [ ] **M-137** S2：是否把公共数据与 native 结果完全分开？
- [ ] **M-138** S3：是否达到 gold validity、critical error、QWK 三门槛？
- [ ] **M-139** S4：是否在 formal 前冻结 N、预算和 eligibility？
- [ ] **M-140** S5：是否质量 Gate 后才运行、性能榜独立，且 1,000-doc 档已有 D-243 的额外 800-doc 许可/hash manifest？
