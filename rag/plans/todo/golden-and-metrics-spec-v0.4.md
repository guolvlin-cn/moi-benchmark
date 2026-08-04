# MOI RAG Pilot：Golden 与指标规范

> 日期：2026-07-30  
> 状态：Draft derived specification  
> 当前权威计划：[v0.4](drafts/v0.4.md)  
> 适用范围：MOI only、Quick-start Native、20 个 sealed scored questions、每题 2 次 initial repeat

## 1. 文档目的与权威关系

本文汇总 `plans/` 下各版计划中关于单个样本 Golden、运行判分和最终指标的约定，并将其整理为可直接实现的数据合同。

- `v0.4.md` 已明确取代 `v0.3.md`，因此范围、阈值、分母、聚合和结论等级以 v0.4 为准。
- `v0.3` 及其 TODO 仅用于补足 lineage、验证记录等审计字段，不改变 v0.4 的评分合同。
- 若本文与 v0.4 冲突，以 v0.4 为准。

核心原则：

> 一个 Golden 不是单独一段 `reference_answer`，而是“题目 + 可回答性 + 原子真值 claims + 每个 claim 的替代证据集合 + 精确来源定位 + 引用要求”的结构化对象。

## 2. Golden 与运行判分的边界

需要区分两类数据：

1. **Golden**：在看到 scored output 之前冻结，定义题目、正确事实、证据和验收要求。
2. **Response judgement**：运行后产生，描述某次回答中的 claims 与 Golden 的关系。

Response judgement 不得回写 Golden。看到 MOI 回答失败后，不得修改问题、claim、证据、引用要求或阈值来适应输出。

## 3. 每个 sample 的 Golden 真值标记

### 3.1 样本身份与分组

| 字段 | 要求 | 含义 |
|---|---|---|
| `question_id` | 必需 | 样本唯一 ID |
| `question_family_id` | 必需 | 同源改写和 paired variants 的分组 ID |
| `analysis_cluster_id` | 必需 | 相关样本的分析聚类 ID |
| `question` | 必需 | 实际发送给 MOI 的问题 |
| `question_type` | 必需 | 五种互斥主类型之一 |
| `split` | 必需 | `smoke` 或 `scored`；本文 Golden 主体为 `scored` |
| `fresh_control` | 必需 | 是否来自 fresh fictional/private 文档 |

`question_type` 的允许值：

```text
single_doc_single_evidence
single_doc_multi_evidence
cross_document
table_visual
unanswerable
```

虽然 v0.4 的最小字段短表没有单列 `question_type`，但数据集存在固定的 `6/4/4/2/4` 题型配额，验收和自审也需要按题型覆盖，因此实现 schema 必须保存该字段。

### 3.2 可回答性真值

| 字段 | 要求 | 含义 |
|---|---|---|
| `answerability` | 必需 | `answerable` 或 `unanswerable` |
| `negative_type` | 不可回答题必需 | 不可回答原因类别 |
| `negative_reason` | 不可回答题必需 | 可复核的具体原因及正确拒答应表达的内容 |
| `citation_required` | 必需 | 是否要求回答中的事实 claim 提供有效引用 |

推荐的 `negative_type`：

```text
missing_information
attribute_missing
false_premise
version_confusion
insufficient_evidence
```

`negative_reason` 不能只写 `not answerable`。例如：

```json
{
  "negative_type": "attribute_missing",
  "negative_reason": "文档提到了 AX-200 型号，但没有提供该型号的待机功耗。"
}
```

### 3.3 Scored reference claims

每个可回答题必须至少有一个非空 `scored_reference_claims`。每个 claim 至少包含：

| 字段 | 要求 | 含义 |
|---|---|---|
| `claim_id` | 必需 | 原子 claim 唯一 ID |
| `text` | 必需 | 单一、可独立判定的事实 |
| `critical` | 必需 | 漏答或答错是否直接导致 Pilot-TDAS 失败 |
| `evidence_set_ids` | 必需 | 能完整支持该 claim 的替代证据集合 |

同时在题目层保存 `critical_required_claims`，列出所有 critical claim ID。

Claim 必须保持原子性。例如：

```text
c1: 设备工作温度范围为 -10°C 至 45°C。
c2: 双传感器模式要求固件版本不低于 3.4。
```

不要把这两个可分别对错的事实合并成一个 claim。

### 3.4 Gold evidence 与替代证据集合

每个可回答 claim 至少有一套完整、可复核的 Gold evidence set。

证据集合的逻辑为：

- 不同集合之间是 **OR**；
- 同一集合中的 evidence items 是 **AND**。

例如：

```text
claim c1 可由：
  evidence set es1 = [e1]
或
  evidence set es2 = [e2, e3]
完整支持
```

命中 `e1` 即足够；若使用 `es2`，则必须同时具备 `e2` 和 `e3`，只得到其中一个不算完整支持。

每条 evidence 至少保存：

| 字段 | 要求 | 含义 |
|---|---|---|
| `evidence_id` | 必需 | 证据唯一 ID |
| `document_id` | 必需 | 来源文件 |
| `file_sha256` | 必需 | 冻结文件版本 |
| `page` | 必需 | PDF 页码 |
| `span` | 必需 | 支持事实的原文 |
| `bbox` | 条件必需 | 表格/视觉题需要；普通文本可为 `null` |
| `evidence_sha256` | 推荐 | 规范化证据片段 hash |
| `section` | 推荐 | 章节、标题或表格名称 |

页码口径必须在冻结前统一，例如明确使用 PDF 物理页还是文档印刷页。

### 3.5 Scope、lineage 与冻结信息

建议保存：

| 字段 | 用途 |
|---|---|
| `allowed_document_ids` | 判定 selected-file scope violation |
| `document_family_ids` | 防止 family/近重复泄漏 |
| `versions` | 版本消歧和 lineage |
| `generator` | 生成模型、prompt、代码版本 |
| `extractor` | 证据抽取方法及版本 |
| `validator` | 独立验证方法及版本 |
| `validation` | schema、answerability、entailment、provenance 等状态 |
| `schema_version` | 数据合同版本 |
| `freeze_id` | 本轮冻结 ID |
| `gold_hash` | 规范化 Golden 记录的 hash |

这些审计字段继承自 v0.3 的完整 schema 思路，不改变 v0.4 的评分公式。

### 3.6 `reference_answer` 的地位

`reference_answer` 可以作为人类可读的可选字段，但不是计分权威。

真正的计分真值是：

```text
scored_reference_claims
+ critical_required_claims
+ evidence_sets
+ evidence provenance
```

这可以稳定处理同义改写、多要点回答、部分覆盖和额外幻觉，而不依赖字符串相似度。

## 4. 推荐 Golden JSON

```json
{
  "schema_version": "rag-golden-v0.4",
  "freeze_id": "moi-rag-v04-20260730",
  "question_id": "q-001",
  "question_family_id": "qfam-001",
  "analysis_cluster_id": "cluster-family-aurora-x2",
  "split": "scored",
  "question_type": "single_doc_multi_evidence",
  "question": "Aurora Edge X2 的安全工作温度范围是什么？启用双传感器模式至少需要哪个固件版本？",

  "answerability": "answerable",
  "negative_type": null,
  "negative_reason": null,
  "citation_required": true,
  "fresh_control": true,
  "allowed_document_ids": ["doc-aurora-x2-v2"],

  "scored_reference_claims": [
    {
      "claim_id": "c1",
      "text": "Aurora Edge X2 的安全工作温度范围为 -10°C 至 45°C。",
      "critical": true,
      "evidence_set_ids": ["es-c1-1"]
    },
    {
      "claim_id": "c2",
      "text": "双传感器模式要求固件版本不低于 3.4。",
      "critical": true,
      "evidence_set_ids": ["es-c2-1", "es-c2-2"]
    }
  ],

  "critical_required_claims": ["c1", "c2"],

  "evidence_sets": [
    {
      "evidence_set_id": "es-c1-1",
      "claim_id": "c1",
      "all_of": ["e1"]
    },
    {
      "evidence_set_id": "es-c2-1",
      "claim_id": "c2",
      "all_of": ["e2"]
    },
    {
      "evidence_set_id": "es-c2-2",
      "claim_id": "c2",
      "all_of": ["e3", "e4"]
    }
  ],

  "evidence": [
    {
      "evidence_id": "e1",
      "document_id": "doc-aurora-x2-v2",
      "file_sha256": "f9d2...",
      "page": 7,
      "section": "2.3 Environmental Limits",
      "span": "Safe operating temperature: -10°C to 45°C.",
      "bbox": [84, 212, 468, 239],
      "evidence_sha256": "18aa..."
    },
    {
      "evidence_id": "e2",
      "document_id": "doc-aurora-x2-v2",
      "file_sha256": "f9d2...",
      "page": 12,
      "section": "4.2 Dual Sensor Mode",
      "span": "Dual Sensor Mode requires firmware 3.4 or later.",
      "bbox": [90, 318, 501, 344],
      "evidence_sha256": "29bc..."
    },
    {
      "evidence_id": "e3",
      "document_id": "doc-aurora-x2-v2",
      "file_sha256": "f9d2...",
      "page": 11,
      "section": "4.1 Feature Matrix",
      "span": "Dual Sensor Mode: available beginning with the 3.4 release.",
      "bbox": [75, 402, 514, 431],
      "evidence_sha256": "8b31..."
    },
    {
      "evidence_id": "e4",
      "document_id": "doc-aurora-x2-v2",
      "file_sha256": "f9d2...",
      "page": 18,
      "section": "Release History",
      "span": "Version 3.4 introduced Dual Sensor Mode.",
      "bbox": [86, 277, 492, 302],
      "evidence_sha256": "60d4..."
    }
  ],

  "reference_answer": "Aurora Edge X2 的安全工作温度为 -10°C 至 45°C；双传感器模式要求固件 3.4 或更高版本。",

  "lineage": {
    "document_family_ids": ["family-aurora-x2"],
    "versions": ["2.0"],
    "generator": {
      "model": "manual-plus-llm",
      "prompt_version": "gold-gen-v1",
      "code_version": "commit-sha"
    },
    "validator": {
      "method": "manual-evidence-review",
      "version": "gold-validator-v1"
    }
  },

  "validation": {
    "schema": "passed",
    "answerability": "passed",
    "claim_evidence_entailment": "passed",
    "provenance": "passed",
    "family_leakage": "passed"
  },

  "gold_hash": "sha256-of-canonical-record"
}
```

## 5. 不可回答题 Golden

不可回答题没有正确答案 claims，但必须有明确、可验证的拒答原因：

```json
{
  "schema_version": "rag-golden-v0.4",
  "question_id": "q-017",
  "question_family_id": "qfam-017",
  "analysis_cluster_id": "cluster-ax200",
  "split": "scored",
  "question_type": "unanswerable",
  "question": "AX-200 的待机功耗是多少？",

  "answerability": "unanswerable",
  "negative_type": "attribute_missing",
  "negative_reason": "选定语料提到 AX-200，但没有给出其待机功耗。",
  "citation_required": false,
  "fresh_control": false,

  "scored_reference_claims": [],
  "critical_required_claims": [],
  "evidence_sets": [],

  "evidence": [
    {
      "evidence_id": "distractor-1",
      "role": "negative_reason_support",
      "document_id": "doc-ax200",
      "file_sha256": "71ce...",
      "page": 3,
      "span": "AX-200 is listed as a supported controller, but no standby-power specification is provided.",
      "bbox": null
    }
  ]
}
```

不可回答题可保留用于验证 `negative_reason` 的相关干扰证据，但这些 evidence 不表示存在一个正向答案。

## 6. 每次回答的判分记录

每个 `(question_id, repeat_id)` 应单独生成 response judgement，例如：

```json
{
  "question_id": "q-001",
  "repeat_id": 1,
  "run_id": "v04-moi-q001-r1-initial",

  "eligible_response_claims": [
    {
      "response_claim_id": "rc1",
      "text": "Aurora Edge X2 的工作温度为 -10°C 至 45°C。",
      "correctness_label": "correct",
      "correctness_score": 1,
      "reference_claim_ids_covered": ["c1"],
      "gold_support": "fully_supported",
      "supporting_evidence_set_id": "es-c1-1",
      "submitted_citation_ids": ["cit1"],
      "citation_locator_valid": true,
      "citation_entails_claim": true,
      "scope_violation": false
    }
  ],

  "critical_claims_all_covered": false,
  "critical_contradiction": false,
  "false_refusal": false,
  "pilot_tdas": 0,
  "judgement_reason": "回答正确覆盖 c1，但遗漏 critical claim c2。"
}
```

必须保留 claim 拆分、canonicalization、重复 claim 去除和每项判定理由，不能只保存最终总分。

## 7. Pilot-TDAS

Pilot-TDAS 是每个 `(question_id, repeat_id)` 的二元北极星指标。

### 7.1 可回答题通过条件

以下条件必须全部满足：

1. 所需 Gold evidence 已处于 searchable-ready；
2. initial request terminal success；
3. `Correctness >= 0.8`；
4. 所有 `critical_required_claims` 被覆盖；
5. `Reference-claim Recall >= 0.8`；
6. `Gold-evidence Support = 1`；
7. 无 critical contradiction；
8. 无已验证 scope violation；
9. citation-required 题的 `Answer-claim Citation Coverage = 1`；
10. 所有提交引用均 locator/resolvable，并完整支持关联 claim；
11. 非 citation-required 题如果主动提交伪造、不可解析、越 scope 或不支持关联 claim 的引用，同样失败。

### 7.2 不可回答题通过条件

以下条件必须全部满足：

- 明确拒答或说明证据不足；
- 理由与冻结的 `negative_reason` 一致；
- 不输出无支持事实；
- 不提供伪造引用。

### 7.3 产品失败

产品/API timeout、解析错误、空响应和服务错误：

- 保留在 initial 主分母；
- Pilot-TDAS 为 0；
- 适用的 answer-quality scores 为 0；
- 不得记成 N/A；
- retry 只用于 recoverability 诊断，不能替换 initial。

## 8. 最终必须计算的指标

### 8.1 Validity

- 计划与实际文件数、页数、题数和 attempt 数；
- 20 个 scored questions 是否完整；
- 40 个 initial attempts 是否全部有可追溯去向；
- hash 校验；
- missing fields；
- `question_invalid`、`run_invalid` 和 replacement 数；
- 所有 N/A 的 reason code；
- self-audit label change：`changed / 12`。

### 8.2 Readiness

- accepted files：`x / 6`；
- accepted pages；
- processed/indexed/searchable-ready files：`x / 6`；
- searchable-ready pages；
- Gold Evidence Preservation probe；
- source/page provenance preservation；
- build time；
- readiness failure 数量和原因。

`ready` 必须表示：

```text
processed + embedded/indexed + searchable
```

UI 显示“完成”本身不构成 ready。

### 8.3 Answer

#### Correctness

```text
sum(response factual claim correctness label)
------------------------------------------------
eligible canonical response factual claims
```

标签取值：

```text
correct = 1
partially_correct = 0.5
incorrect = 0
```

Answerable 空回答、直接拒答或零 eligible factual claims 时为 0。

#### Reference-claim Recall

```text
完整语义覆盖的 scored_reference_claims
---------------------------------------
全部 scored_reference_claims
```

Partial coverage 不计命中。Critical claims 另设 100% gate。

#### Critical-required claim coverage

```text
覆盖的 critical claims
----------------------
全部 critical claims
```

Pilot-TDAS 要求为 1。

#### Gold-evidence Support

```text
被至少一套完整 Gold evidence set 支持的 response factual claims
--------------------------------------------------------------
全部 eligible canonical response factual claims
```

Answerable 空回答、直接拒答或零 eligible factual claims 时为 0。

#### 其他 Answer 指标

- critical contradiction-free；
- strict unanswerable success；
- false refusal。

三个核心 component 分别回答：

- Correctness：说出来的话有多少是对的；
- Reference-claim Recall：应该回答的关键点覆盖了多少；
- Gold-evidence Support：说出来的话有多少能被 Golden 证据完整支持。

三者不可互相替代。

### 8.4 Citation

| 指标 | 定义 |
|---|---|
| Citation locator/resolvability validity | 引用能否解析到冻结文件、页码和 span/bbox/hash |
| Citation entailment precision | 提交引用中真正完整支持所关联 claim 的比例 |
| Answer-claim Citation Coverage | 需要引用的回答 claims 中，有至少一个有效支持引用的比例 |
| Fabricated citation count | 伪造引用数量 |
| Out-of-scope citation count | 引用 selected-file scope 外证据的数量 |

零 submitted citations 时：

- locator validity：`N/A`，reason=`NO_SUBMITTED_CITATION`；
- entailment precision：`N/A`，reason=`NO_SUBMITTED_CITATION`；
- citation-required 题的 coverage=0，因此 Pilot-TDAS=0；
- 非 citation-required 题的 coverage=N/A。

### 8.5 Reliability

- initial availability；
- timeout/error count；
- retry recovery rate，仅用于诊断；
- terminal attempts 的 P50/P95 latency；
- 两次 repeat 的 `pass/pass`、`pass/fail`、`fail/pass`、`fail/fail`；
- 代表性的输出差异和翻转案例。

### 8.6 Operability

- Time-to-First-Searchable-Corpus；
- Time-to-First-Trusted-Answer；
- active human minutes；
- intervention count；
- configuration error count；
- diagnostic quality；
- recoverability。

这些指标只作描述性证据，不折入 Pilot-TDAS。

### 8.7 Trace-only

只有在能真实导出 retrieved trace、rank 和 qrels 时才计算：

- Evidence Recall@K；
- Complete Evidence-set Recall@K；
- Context Precision；
- Runtime-context Faithfulness；
- Context Utilization；
- Trace Completeness。

无法导出时统一记录：

```json
{
  "value": null,
  "reason": "TRACE_UNAVAILABLE"
}
```

不得从最终回答或产品 citation 反推 retrieval trace。

## 9. 分母与汇总口径

v0.4 主分母为：

```text
20 questions × 2 initial repeats = 40 initial attempts
```

Smoke、calibration、自审和 retry 不增加主分母。

Question-level 二元指标按每个 repeat 报告：

| 指标 | 每个 repeat 的分母 |
|---|---:|
| Pilot-TDAS | 20 |
| Strict unanswerable success | 4 |
| False refusal | 16 |
| Critical contradiction-free | 16 |
| Citation-required gate pass | 10 |
| Initial availability | 20 |

汇总规则：

1. 每个 repeat 的 question-level 二元指标给 numerator、denominator、rate 和 Wilson 95% 描述区间。
2. 两个 repeat 先对同一 question 取均值，再对 20 个 questions 做宏平均。
3. Two-repeat question mean 不计算 Wilson 区间。
4. Claim/citation-level 指标只给原始 numerator、denominator 和 rate，不把相关 claims 当独立样本生成 CI。
5. Fresh、题型、family 等小切片只报告 counts、rates 和案例，不下切片级结论。
6. Latency 仅对具有完整时间戳的 terminal attempts 计算 P50/P95，同时保留 timeout/error 数。

## 10. v0.4 明确不计算的内容

本 Pilot 不计算或不发布：

- comparator 或 paired product difference；
- 显著性检验；
- McNemar；
- bootstrap；
- 排行榜；
- 加权总分；
- overall winner；
- production-grade 泛化结论；
- v0.3 decision-grade 的成本规模化和推断统计。

## 11. Freeze 前最小校验清单

- [ ] 20 个 scored questions 满足 `6/4/4/2/4` 配额。
- [ ] Answerable=16、unanswerable=4。
- [ ] Fresh scored=4。
- [ ] Citation-required answerable=10。
- [ ] 每个 answerable question 的 `scored_reference_claims` 非空。
- [ ] 每个 scored claim 至少有一套非空、完整的 evidence set。
- [ ] 每条 evidence 的 source/page/span/hash 可解析。
- [ ] 表格/视觉题的 bbox 和页面语义已人工确认。
- [ ] 所有 critical claims 已明确标记。
- [ ] 每个不可回答题都有可验证的 `negative_type` 和 `negative_reason`。
- [ ] `question_family_id` 和 document family 不跨 Smoke/scored split。
- [ ] Corpus、Golden、rubric、threshold、run order 和 self-audit sample 均在 scored run 前冻结。
- [ ] Golden canonical serialization 和 hash 已生成。
- [ ] 产品输出没有参与 Golden 创建或修订。

