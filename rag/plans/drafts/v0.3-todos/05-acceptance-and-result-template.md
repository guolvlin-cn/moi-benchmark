# RAG Benchmark v0.3 最终验收与结果模板

> 日期：2026-07-29 ｜ 状态：Draft TODO ｜ Parent plan：[`v0.3.md`](../v0.3.md)
>
> 规则：本文定义执行与交付格式；若与 Parent plan 冲突，以 Parent plan 为准。

## 1. 验收目标

最终验收回答四个问题：

1. 本次运行是否严格执行了冻结的 Native 条件、数据集、配置、重复次数和计分合同；
2. 结果能否支持 MOI、Dify、FastGPT 在产品级 Data-to-Answer 旅程上的分层比较；
3. 每项结论能否回溯到 manifest、原始运行、Judge、人审和统计工件；
4. 当前产物应标记为正式结果、带限制的正式结果、Pilot，还是不接受。

验收不产生加权总分、排行榜或“总体赢家”。Controlled Generation 是可选诊断，缺失时不阻塞 Native 正式验收；trace 依赖型检索指标只能在真实 trace 可导出时验收。

## 2. 验收角色与签字边界

| 角色 | 职责 | 不得兼任的最终决定 |
|---|---|---|
| RAG Owner | 确认范围、资源、发布口径和例外 | 不得单独批准本人提出的看分后例外 |
| Benchmark Engineer | 提供代码、配置、运行和重现证据 | 不得自行批准 `run_invalid` |
| Data & Eval Engineer | 提供 corpus、Gold、Judge 和统计证据 | 不得独自裁决本人生成的 Gold 争议 |
| System Operator | 签署产品版本、配置、支持预算和运行记录 | 不得修改 hidden dataset |
| 两名 Reviewer | 盲审回答、Gold 和 citation | 不接触系统名称后再回改原始标签 |
| Adjudicator | 处理 reviewer 分歧 | 不修改原始 response |
| Approver | 以盲化方式批准 invalid/replacement ledger 和最终状态 | 在签字前不得查看系统得分排名 |

## 3. 最终验收门禁

所有“阻塞”项必须通过，才可以发布正式结果。可诊断项缺失时必须报告 `N/A` 或 `observability_gap`，不能按零分或静默忽略。

| Gate | 验收证据 | 通过标准 | 阻塞 | Owner | 状态 |
|---|---|---|---:|---|---|
| AC-01 身份与部署 | 三个 signed system manifests | 产品、前后端版本、部署、租户、区域、entitlements、日期及 hidden defaults 已记录 | 是 | System Operator | ☐ |
| AC-02 Corpus 与安全 | corpus/fresh manifests、hash、授权与 egress 记录 | 文件数、页数、版本族、敏感性、许可证、保留期可追溯；8–12 份 fresh-control 合规 | 是 | Data & Eval Engineer | ☐ |
| AC-03 Native 路径 | Smoke run、界面/API 证据、runbook | 三个产品均从相同 raw files 完成其 Native journey；集成路径未混入 | 是 | Benchmark Engineer | ☐ |
| AC-04 Data Readiness | job/artifact 时间线、search probe、Gold preservation 结果 | `processed + embedded + searchable` 可验证；失败进入正式分母而非删题 | 是 | Benchmark Engineer | ☐ |
| AC-05 Dataset 与隐藏性 | dataset manifest、split/lineage validator | 180–240 个 hidden formal questions；配额、family split、fresh 30–40 题和访问控制通过 | 是 | Data & Eval Engineer | ☐ |
| AC-06 Judge 与 Gold | Judge config signature、calibration、kappa、audit、adjudication | primary Judge 的 model/version/prompts/temperature/max output 与 blinded-input mapping 已冻结；calibration ≥30；QWK ≥0.60；Gold validity ≥95%；critical error=0 | 是 | Reviewer（两名） | ☐ |
| AC-07 公平性冻结 | Quick-start/Optimized config manifests | Quick 的官方模板/tie-break/onboarding/support 已冻结且未按 dev 选优；Optimized 的 dev trials、人时、动作、搜索空间、停止规则已冻结；hidden 未用于调参 | 是 | RAG Owner | ☐ |
| AC-08 正式运行完整性 | run index、batch ledger、raw hashes | 每个 system × condition × hidden question 有 3 次 scored initial attempts 或合规 invalid/replacement | 是 | Benchmark Engineer | ☐ |
| AC-09 统计合同 | evaluator version、analysis notebook/report | repeat 先按 question 聚合；10,000 次 paired cluster bootstrap；分母和 95% CI 可复算 | 是 | Data & Eval Engineer | ☐ |
| AC-10 MOI 能力验证 | capability evidence matrix | MOI-specific 能力与 Common scorecard 隔离；缺失和限制如实披露 | 是 | System Operator（MOI） | ☐ |
| AC-11 诊断完整性 | trace/export 或 gap 声明 | 有 trace 才计算检索排序指标；无 trace 明确为 observability gap | 否 | Benchmark Engineer | ☐ |
| AC-12 发布包 | report、scorecard、ledger、approval | 所有表格有样本量、分母、版本、限制和证据链接；无 overall winner | 是 | Approver | ☐ |

## 4. 验收执行工作与预计耗时

以下人日已包含在完整 v0.3 的 65–85 人日估算内，不能再次累加；实际工时按 [Crosswalk](README.md#8-子计划与总人日-crosswalk)记入对应 M ID。1 人日按 8 小时计算。

| ID | 工作 | 依赖 | 主要产物 | 人日 | 预计日历时间 |
|---|---|---|---|---:|---:|
| A-01 | 冻结验收样本、分母和证据索引 | 正式运行完成 | acceptance index | 0.5–1 | 0.5–1 天 |
| A-02 | 校验运行覆盖、hash、invalid/replacement | A-01 | completeness report、ledger | 1–1.5 | 1–2 天 |
| A-03 | 生成 component metrics、TDAS 和 Stage Diagnostics | A-02 | scorecards、diagnostics | 1.5–2.5 | 2–3 天 |
| A-04 | 执行 paired cluster bootstrap 与切片分析 | A-03 | 95% CI、paired differences | 1–1.5 | 1–2 天 |
| A-05 | 完成人工 audit、分歧扩审与 adjudication | A-01 | audit/adjudication records | 3–4 | 3–5 天 |
| A-06 | 汇总失败分类、MOI 能力矩阵和限制 | A-03、A-05 | failure/capability matrices | 1–1.5 | 1–2 天 |
| A-07 | 生成最终报告与机器可读发布包 | A-04、A-06 | report、CSV/JSON、release manifest | 1.5–2 | 2 天 |
| A-08 | 独立复算、Blind approval 和发布判定 | A-07 | reproducibility note、approval | 1–1.5 | 1–2 天 |
|  | **合计** |  |  | **10.5–15.5** | **约 2–3 周，可部分并行** |

若 A-02 发现同一 batch 超过一次 benchmark-side fault，必须按 Parent plan 停止、修复、重冻结并整体重跑；额外预留的一周 re-freeze/re-run 缓冲由此触发。

## 5. 发布目录格式

推荐为每次候选发布创建不可变的 `release_id`，例如 `rag-v0.3-2026q3-rc1`：

```text
rag/reports/<release_id>/
├── release-manifest.yaml
├── final-report.md
├── common-product-scorecard.csv
├── stage-diagnostics.csv
├── operability-scorecard.csv
├── moi-capability-validation.md
├── slice-results.csv
├── failure-taxonomy.csv
├── invalid-replacement-ledger.csv
├── judge-audit-summary.md
├── limitations.md
└── approval.md
```

原始 response、trace、日志和大型 artifacts 仍保存在受控外部存储；Git 中的 release manifest 必须记录 URI、SHA-256、访问级别和保留期。`rag/runs/` 保存不可变 run index、摘要与 hashes。

## 6. `release-manifest.yaml` 最小字段

```yaml
release_id: rag-v0.3-2026q3-rc1
status: candidate
parent_plan: rag/plans/drafts/v0.3.md
plan_sha256: ""
code_commit: ""
dataset_id: ""
dataset_sha256: ""
task_set_version: ""
judge_version: ""
judge_config_sha256: ""
evaluator_version: ""
systems:
  - system_id: ""
    deployment_manifest_sha256: ""
conditions:
  - quick_start_native
  - frozen_optimized_native
formal_question_count: 0
expected_initial_attempts: 0
observed_initial_attempts: 0
question_invalid_count: 0
run_invalid_count: 0
replacement_count: 0
raw_artifact_uri: ""
raw_artifact_sha256: ""
approvals:
  data_eval: pending
  systems: pending
  approver_blinded: pending
```

空字符串仅表示模板尚未实例化；候选发布进入验收时不得保留必填空值。

## 7. 最终报告格式

### 7.1 发布摘要

| 字段 | 结果 |
|---|---|
| Release ID |  |
| Parent plan / commit |  |
| Dataset / task set |  |
| 系统与精确版本 |  |
| Native conditions |  |
| 正式运行窗口 |  |
| Formal questions |  |
| Expected / observed initial attempts |  |
| 最终验收状态 |  |
| 主要限制 |  |

摘要只陈述是否完成协议、最重要的能力差异和限制，不宣称总体冠军。

### 7.2 Common Product Scorecard

每个系统必须按 Native condition 和 slice 分行，至少包含：

| System | Condition | Slice | Questions | Initial attempts | TDAS % | TDAS 95% CI | Correctness | Ref-claim Recall | Gold Support | Citation Precision | Citation Coverage | Unanswerable success | False refusal | First-pass success |
|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
|  |  | all / public / fresh |  |  |  |  |  |  |  |  |  |  |  |  |

所有比例同时报告 numerator/denominator。`N/A` 必须附 reason code，不能留空。

### 7.3 Reliability、性能与成本

| System | Condition | P50 E2E | P95 E2E | First-pass availability | Final availability | Query cost | Build time | Build cost | Currency/date |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
|  |  |  |  |  |  |  |  |  |  |

重试只进入 final availability、额外时延和额外成本，不替换 initial score。

### 7.4 Stage Diagnostics

| System | Condition | Accepted files/pages | Searchable coverage | Gold Evidence Preservation | Trace availability | Evidence Recall@K | Scope violations | Observability gap |
|---|---|---|---:|---:|---:|---:|---:|---|
|  |  |  |  |  |  |  |  |  |

检索列只有在真实 retrieved context、rank 和 qrels 可用时填写数值。

### 7.5 Product Operability

| System | Condition | TT First Searchable Corpus | TT First Trusted Answer | Active human min | Actions | Config errors | Diagnostic quality | Recoverability |
|---|---|---:|---:|---:|---:|---:|---|---|
|  |  |  |  |  |  |  |  |  |

这些指标只作描述性证据，不折入 TDAS。

### 7.6 MOI Capability Validation

| Capability | Deployment/version | Test case | Evidence | Result | Common or MOI-specific | Limitation |
|---|---|---|---|---|---|---|
| Workflow topology/config export |  |  |  | pass/fail/gap | MOI-specific |  |
| Parser artifact/page mapping |  |  |  | pass/fail/gap | MOI-specific |  |
| Embedded eligibility/disabled chunk |  |  |  | pass/fail/gap | MOI-specific |  |
| Selected-file scope |  |  |  | pass/fail/gap | Common |  |
| Job status/retry/lineage/export |  |  |  | pass/fail/gap | MOI-specific |  |

### 7.7 失败与例外

| Stage | Failure code | System/condition | Count | Denominator | Rate | Representative run IDs | Disposition |
|---|---|---|---:|---:|---:|---|---|
| ingest / parse / embed / retrieval / generation / citation / platform |  |  |  |  |  |  |  |

另附完整 `question_invalid`、`run_invalid`、replacement 和 `benchmark_execution_failure` ledger，包括发现时间、原因、原始 hash、批准人和替代 run。

### 7.8 Judge 与人工审计

| 检查项 | 结果 | 通过标准 | 状态 |
|---|---:|---:|---|
| Calibration answers |  | ≥30 |  |
| Quadratic weighted kappa |  | ≥0.60 |  |
| Distinct audited hidden questions |  | max(40, 20%) |  |
| Gold validity |  | ≥95% |  |
| Critical Gold errors |  | 0 |  |
| Expanded disagreement reviews |  | 报告实际数量 |  |

### 7.9 限制与适用范围

至少披露：

- 当前 corpus 主要是英文技术/硬件 PDF，不能外推到所有领域和模态；
- public_baseline 与 fresh-control 的差异；
- 不可观察的 hidden defaults、trace gap 和部署差异；
- Citation、Controlled Generation 或其他条件的不可用情况；
- Judge、人审、成本、时间窗和版本变化风险；
- 延后的 integrations、Agent、NL2SQL、GraphRAG、安全、动态更新和并发能力。

## 8. 验收状态

| 状态 | 使用条件 | 对外口径 |
|---|---|---|
| `ACCEPTED_FORMAL` | 所有阻塞 Gate 通过，无未披露偏差 | 可发布为 v0.3 正式结果 |
| `ACCEPTED_WITH_LIMITATIONS` | 阻塞 Gate 通过，仅非阻塞诊断缺失或存在已披露适用范围限制 | 可发布，但结论必须绑定限制 |
| `PILOT_ONLY` | Smoke/Pilot 完成，但 hidden formal、重复、审计或统计合同未完成 | 只能作为可行性和工程进展 |
| `REJECTED` | 任一阻塞 Gate 失败、存在看分后选择、不可追溯改写或无法复算 | 不得作为产品比较结论 |

`ACCEPTED_WITH_LIMITATIONS` 不能用来豁免 citation-required TDAS、hidden 隔离、三次 initial repeats、Gold/Judge 门禁或 invalid-run 合同。

## 9. 最终签字模板

```text
Release ID:
Decision:
Blocking gates passed:
Non-blocking gaps:
Invalid/replacement ledger reviewed:
Scorecard independently reproduced:
Known limitations:
Required follow-up:

Data & Eval Engineer / date:
System Operators / date:
Reviewers / date:
RAG Owner / date:
Approver（盲化签字）/ date:
```

## 10. 完成清单

- [ ] 发布包目录和 `release-manifest.yaml` 字段完整。
- [ ] 所有表格包含样本量、numerator/denominator、版本和证据链接。
- [ ] public/fresh、Quick-start/Optimized 分开报告。
- [ ] TDAS 与 component metrics 可从冻结原始记录复算。
- [ ] trace-dependent metrics 未从答案反推。
- [ ] audit、kappa、Gold validity 和 critical error 门禁通过。
- [ ] invalid/replacement ledger 经 Approver 盲化并在看分前批准。
- [ ] MOI-specific 能力未混入 Common Product Scorecard。
- [ ] Pilot、正式结果和外部公开证据没有混报。
- [ ] 报告没有加权总分、排行榜或总体赢家。
