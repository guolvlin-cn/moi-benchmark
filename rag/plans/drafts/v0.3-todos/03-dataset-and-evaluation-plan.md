# v0.3 数据集与评测执行计划

> 日期：2026-07-29 ｜ 状态：Draft TODO ｜ Parent plan：[v0.3](../v0.3.md)

本文件把 v0.3 的 corpus、fresh-control、问题、Gold、Judge、人工审计和统计合同拆成执行项，不重新定义指标或阈值。若本文与 Parent plan 冲突，以 Parent plan 为准。

## 1. 范围、角色与估时

本计划覆盖：

- 复核当前观测的 46 份 PDF（约 58 MiB、约 1,104 页）；
- 建设 8–12 份 egress-safe、带版本的 fresh-control PDF；
- 建设 30–50 题 Smoke 和 180–240 题 hidden formal set，其中 fresh-control 30–40 题；
- 生成 evidence-first Gold、Judge、人工审计和统计发布输入。

统一角色使用 [执行 TODO 导航](README.md)中的六类角色。Data & Eval Engineer 主责数据、Gold、Judge 和统计；Benchmark Engineer 主责 schema/validator 集成；System Operator 不得访问 hidden Gold；Reviewer 与 Approver 承担独立复核和签字。

1 人日按 8 小时计算。本文件涉及约 **29–40 人日**，已经分散计入总执行计划的 **65–85 人日**，不能作为额外预算相加；实际工时按 [Crosswalk](README.md#8-子计划与总人日-crosswalk)记入对应 M ID。数据制作、validator/Judge 开发和产品 adapter 可并行；family split、Smoke Gate、Judge Gate 与 formal freeze 位于关键路径。

## 2. 输入与输出

### 输入

- Parent plan 及冻结 commit/hash；
- public baseline 原始 PDF；
- identity/security/egress 研究结论；
- `document-parsing` Track 可提供的解析缺陷校准信息；
- 三产品 artifact、citation 和 trace 能力合同。

`document-parsing` 只提供校准和 failure attribution；本 Track 不重复 OCR、layout、TEDS、formula 全量评分。表格只作为 RAG 视觉/检索证据，不执行 SQL，也不进入 NLP2SQL。

### 输出目录

```text
rag/datasets/
├── manifests/          # corpus、fresh、split、question/task-set manifests
├── schemas/            # file/question/claim/evidence/lineage schemas
├── dev/                # 允许调参与 Judge 开发的数据
├── smoke/              # Smoke task set 与验证记录
└── hidden/             # 只保存允许入 Git 的索引/hash，不暴露 Gold payload

rag/benchmark/
├── evaluators/         # metric、Judge I/O、TDAS 与统计实现
├── validators/         # deterministic schema/lineage/leakage checks
└── tests/              # golden cases、边界条件和回归测试

rag/reports/
└── <release_id>/       # audit、统计、scorecard 与验收发布包
```

私有文档、hidden Gold、大型中间产物和敏感 Judge payload 放受控外部存储；Git 只保存版本化 manifest、hash、访问级别、保留期和可公开摘要。

## 3. 逐步工作表

| ID | Checkbox | 依赖 | 角色 | 工作 | 产物 | DoD | 人日 |
|---|---|---|---|---|---|---|---:|
| DE-01 | - [ ] | Parent plan | Data & Eval Engineer、Benchmark Engineer | 冻结 file/question/claim/evidence/lineage schema 和 reason codes | versioned schemas、示例、validator contract | v0.3 必填字段、替代 evidence sets、answerability、citation、family/cluster 和生成 lineage 均可校验 | 1.5–2 |
| DE-02 | - [ ] | identity/security 研究 | Data & Eval Engineer、Reviewer | 重验 public baseline 的文件数、bytes、pages、hash、语言、域、版本和 parseability | `public_baseline` manifest、差异报告 | 不把 46/58 MiB/1,104 页旧观测当最终事实；每项差异有 disposition | 2–3 |
| DE-03 | - [ ] | DE-02 | Data & Eval Engineer、Approver | 核对 license、sensitivity、egress、访问级别和 retention | data approval matrix | 每个文件允许进入目标部署；不合规文件在 freeze 前全局移除并留痕 | 0.5–1 |
| DE-04 | - [ ] | DE-02 | Data & Eval Engineer、Reviewer | 识别 document family、版本链、近重复和 connected components | family/version graph、duplicate report | component 整体进入 dev 或 hidden；paired variants 和 analysis cluster 不跨 split | 1–2 |
| DE-05 | - [ ] | DE-03 | Data & Eval Engineer、Reviewer、Approver | 创作 8–12 份 private-or-fictional、真实感、带版本 fresh-control PDF | fresh PDFs、source/authoring lineage、manifest | egress-safe；版本冲突/干扰材料可用；无产品输出参与创作或修订 Gold | 3–4 |
| DE-06 | - [ ] | DE-01、DE-02、DE-05 | Data & Eval Engineer、Reviewer | 建立 evidence inventory 和可出题单元 | evidence catalog | 每项含 file/hash/page/span/bbox、版本和 claim 候选；表格/视觉项标注可判定性 | 2–3 |
| DE-07 | - [ ] | DE-04、DE-06 | Data & Eval Engineer | 构建 30–50 题 Smoke，覆盖 10–15 families | Smoke task set、配额表 | 覆盖单/多文档、exact ID、版本/干扰、视觉/表格、unanswerable、scope；不进入正式分数 | 1–1.5 |
| DE-08 | - [ ] | DE-04、DE-06 | Data & Eval Engineer、Reviewer | 生成 hidden formal 候选题、reference claims 和 alternative evidence sets | 180–240 题候选、lineage | 包含 fresh 30–40 题；互斥主类型配额和正交标签满足；产品输出未参与 | 3–4 |
| DE-09 | - [ ] | DE-07、DE-08 | Reviewer、Data & Eval Engineer | 独立验证 answerability、claim/evidence entailment、source/page/span/hash 和版本范围 | Gold validation records | required claims 均有完整有效 evidence set；不可回答题 reason 可验证；critical defect=0 | 2–3 |
| DE-10 | - [ ] | DE-01、DE-08、DE-09 | Benchmark Engineer、Data & Eval Engineer | 实现 schema、配额、leakage、hash、evidence 和 lineage validators | validators、正反例 tests | 对缺字段、跨 split、重复、失效 hash、空证据集和非法 N/A 确定性失败 | 1.5–2 |
| DE-11 | - [ ] | DE-07、系统 Smoke | Data & Eval Engineer、Benchmark Engineer、Reviewer | 分析 Smoke 中的 dataset、benchmark 和 product-stage failure | Smoke defect ledger | 缺陷分类有证据；产品解析/ready/retrieval 失败不用于删除 hard cases | 1–2 |
| DE-12 | - [ ] | DE-09–DE-11、Smoke Gate | Data & Eval Engineer、Approver | 在 Smoke 通过后冻结 dev/hidden、task-set version、hash 和访问 ACL | signed dataset freeze | formal hidden 明确为 180–240 题；Smoke 默认不晋升；任何例外均需重新 lineage 和独立批准 | 1 |
| DE-13 | - [ ] | DE-01、DE-09 | Data & Eval Engineer、Benchmark Engineer | 实现 claim canonicalization、规范 metrics、TDAS、refusal/citation 和 Judge I/O | evaluator、盲化 Judge config/signature、golden tests | 冻结 primary Judge 的 model、model version、system/user prompt、temperature、max output 和 system-identity blinded-input mapping；指标边界与 v0.3 一致 | 3–4 |
| DE-14 | - [ ] | DE-13、Smoke responses | Reviewer、Data & Eval Engineer | 完成至少 30-answer 分层 calibration、双审和 adjudication | calibration pack、QWK report | 覆盖 answerability、题型、三系统和 score strata；claim-level QWK ≥0.60 | 1.5–2 |
| DE-15 | - [ ] | DE-12–DE-14、Formal runs | Reviewer、Data & Eval Engineer | 执行固定人工 audit 和争议扩审 | blind audit/adjudication records | 抽取 `max(40, 20% distinct hidden questions)`；每题覆盖所有 system × Native condition 的同一预注册 repeat；Gold validity ≥95%、critical=0 | 3–4 |
| DE-16 | - [ ] | DE-12、DE-15、run reconciliation | Data & Eval Engineer、Reviewer | 计算 question-level 聚合、macro metrics、切片和 paired cluster bootstrap | analysis outputs、10,000 bootstrap records | 先固定平均三次 repeat，再按 `analysis_cluster_id` paired resample；报告 95% CI、分母和 run variance | 2 |
| DE-17 | - [ ] | DE-16 | Data & Eval Engineer、Reviewer | 形成数据/Judge/统计验收包 | manifests、audit summary、scorecard inputs、limitations | public/fresh、Quick/Optimized 分开；所有 N/A/gap、invalid 和限制可追溯 | 1 |

## 4. 数据集配额与切分

### 4.1 Hidden formal 主类型

主类型互斥，按最终题数冻结整数配额；因取整产生的差异不得超过 1 题，并在 manifest 中记录取整规则。

| 主类型 | 目标比例 | 关键 Gold 要求 |
|---|---:|---|
| 单文档、单证据 | 35% | 一个 required claim 可由一个明确 evidence item 完整支持 |
| 单文档、多证据 | 20% | 至少一个 claim 需要同一 complete evidence set 内多个 evidence items |
| 跨文档证据链 | 15% | complete evidence set 跨多个允许文件；selected-file scope 可验证 |
| 表格/视觉条件 | 10% | 人工确认页面区域与语义；不要求 SQL 执行 |
| 不可回答 | 20% | answerability reason、negative category 和相关干扰源明确 |

正交标签至少包括 `exact_identifier`、`semantic_paraphrase`、`distractor`、`version_disambiguation`、`long_document`、`query_language`、`fresh_control`。不可回答题覆盖信息缺失、实体存在但属性缺失、错误前提、版本/近邻混淆和证据不足；可回答 cohort 同时测 false refusal。

### 4.2 Split 和访问规则

1. 先按 document family、版本链和 near-duplicate connected component 分组，再做约 20/80 dev/hidden 切分。
2. `question_family_id`、paired variants、`base_question_id` 和 `analysis_cluster_id` 不跨 split。
3. dev corpus/questions 可供调参与 Judge 开发；180–240 只指 hidden formal scored questions。
4. fresh-control 的 30–40 个问题全部属于 hidden formal，并单独报告。
5. System Operator、adapter 运行账户和厂商支持人员不得访问 hidden question、reference answer 或 Gold。
6. hidden 解封只面向冻结 harness；记录访问人、时间、目的、文件 hash 和导出行为。

## 5. Gold 与评测合同

### 5.1 最小题目记录

```yaml
question_id:
base_question_id:
question_family_id:
analysis_cluster_id:
split:
question:
answerability:
negative_type:
negative_reason:
citation_required:
required_reference_claims:
  - claim_id:
    text:
    alternative_evidence_sets:
      - [evidence_id]
evidence:
  - evidence_id:
    file_id:
    file_sha256:
    page:
    span:
    bbox:
lineage:
  document_family_ids: []
  versions: []
generator:
extractor:
validator:
validation:
```

每项 generator/extractor/validator 记录 model、model version、prompt version 和 code version。Gold 必须先于产品正式输出产生；后续看到产品失败不得修改问题使产品“可答”。

### 5.2 Gold Evidence Preservation

RAG 只判定 Gold evidence 是否在产品的 parsed/indexed/retrievable representation 中存活，以及来源/页映射、missing/duplicate evidence 和 searchable coverage。它用于 Data Readiness 与 failure attribution，不重复 document-parsing 的 OCR/layout/TEDS/formula 分数。

## 6. 数据验收矩阵

| 检查 | 方法 | 通过标准 | 失败处置 |
|---|---|---|---|
| Corpus 完整性 | file/page/hash validator | manifest 与冻结 payload 一致 | freeze 前修 manifest 或替换文件并重跑下游 lineage |
| 授权与 egress | approval matrix | 每个文件有明确允许路径 | 全局移除不合规文件并重建受影响题目 |
| Family leakage | connected-component validator | component、paired/cluster IDs 不跨 split | 重新切分并废弃受影响候选题 |
| 题型配额 | deterministic counter | 整数配额符合冻结取整规则 | freeze 前增删候选题；不得看分后调配额 |
| Answerability | 双人 evidence review | 可回答题有完整 evidence；不可回答 reason 可复核 | 修复或删除候选题；formal 后按 `question_invalid` 全系统处理 |
| Citation/provenance | source/page/span/hash check | 引用位置存在且支持对应 claim | 重建 Gold；critical 错误阻止 Gate |
| Fresh-control | lineage/security review | 8–12 PDFs、30–40 hidden 题、egress-safe | 修复 authoring/授权并重新 hash |
| Validator | golden positive/negative cases | 所有预注册边界测试通过 | 修代码、版本升级并重验全部数据 |
| Judge calibration | 双 Reviewer + adjudication | ≥30 answers；QWK ≥0.60 | 修 rubric/prompt，重新校准，不进入 Formal |
| Formal Gold audit | 固定抽样 | validity ≥95%；critical=0 | 受影响 strata 全审或重建，并评估全局 `question_invalid` |

## 7. 返工与变更控制

| 事件 | 允许动作 | 禁止动作 |
|---|---|---|
| pre-freeze manifest/Gold 缺陷 | 修复、提升版本、重跑 validators，保留旧记录 | 覆盖旧 hash 或隐去缺陷 |
| Smoke 暴露 benchmark-side 缺陷 | 修 schema/evaluator/harness，重跑受影响 Smoke 后再 freeze | 把产品能力失败改称 benchmark fault |
| Formal 后确认 Gold/dataset defect | 对所有系统/conditions/repeats执行 `question_invalid`，保留原运行与批准记录 | 仅删除某系统失败题或看分后改答案 |
| 产品未 ready、证据丢失或 citation 缺失 | 记录 stage failure/TDAS=0 并做 failure attribution | 通过修改 Gold、移除 hard case 或 retry 替换 initial |
| Judge kappa 或 Gold audit 不达标 | 停止发布，修 rubric/Gold，扩审或重建 strata | 降低阈值、缩小分母或只审争议系统 |
| family/hidden 泄漏 | 停止运行，重建 split、task-set version 和受影响配置 | 继续使用已泄漏 hidden 结果 |
| 题型配额无法实现 | freeze 前提交书面变更并修改 Parent plan/批准记录 | Formal 后按结果调整配额 |

## 8. 里程碑与并行建议

| 日历阶段 | 数据/Gold 流 | 评测/Judge 流 | 会合 Gate |
|---|---|---|---|
| W1–W2 | baseline/security/family 复核、fresh 设计 | schema/validator contract | identity、security |
| W2–W4 | fresh 制作、evidence inventory、Smoke/formal candidates | metric golden tests、Judge I/O | artifact contract |
| W5 | Smoke 缺陷分析 | Judge calibration 准备 | Smoke Gate |
| W5–W6 | 修复、独立 Gold 复核、hidden freeze | calibration、QWK、Judge freeze | Dataset/Judge Gate |
| W7–W9 | formal lineage 与访问审计 | blind audit、adjudication | run completeness |
| W9–W10 | slice/limitations | macro、CI、发布输入 | final acceptance |

主要不确定性是 fresh-control 创作质量、表格/视觉 Gold、一手页面定位、hidden 泄漏、Judge 校准返工和正式运行后发现系统性 Gold 缺陷。总计划已额外预留 20%–30% 风险容量与一次 re-freeze/re-run 周；不得通过降低数据规模、人工 audit 或 Gold Gate 吸收延期。

## 9. 完成清单

- [ ] public baseline 数量、页数、hash、family、license、egress 已重新核验。
- [ ] 8–12 份 fresh-control PDF 与 30–40 个 hidden questions 完成独立验证。
- [ ] dev、Smoke、hidden formal 三类数据的用途、ACL、lineage 和 hash 分离。
- [ ] 180–240 hidden formal questions 满足主类型配额和正交标签。
- [ ] 所有 required claims 有至少一套 complete alternative evidence set。
- [ ] unanswerable reason、paired variants、版本/近重复与 `analysis_cluster_id` 可校验。
- [ ] schema/validator golden tests 通过；产品输出未参与 Gold 创建或修订。
- [ ] Primary Judge 的盲化输入映射及 model/version/prompts/temperature/max output 已签名；calibration、双审/adjudication、QWK ≥0.60。
- [ ] 固定人工 audit、Gold validity ≥95%、critical error=0。
- [ ] repeat 聚合、macro average 与 10,000 次 paired cluster bootstrap 可复算。
- [ ] 数据/Judge/统计产物均有版本、hash、访问级别、保留期和审批记录。
