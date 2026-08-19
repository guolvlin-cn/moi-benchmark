# MOI RAG Bench 评估指标调研与记载建议

> 调研日期：2026-08-10  
> 文档性质：指标研究笔记，不覆盖当前规范  
> 当前规范权威：[`plans/drafts/v1.0.md`](../drafts/v1.0.md)；Golden/计分合同：[`plans/todo/golden-and-metrics-spec-v0.4.md`](../todo/golden-and-metrics-spec-v0.4.md)

## 1. 结论先行

MOI RAG Bench 应继续采用“**端到端二元门禁 + 分层诊断 scorecard + 独立性能报告**”，不要生成一个可相互补偿的加权总分。

建议把正式必报指标分成七组：

1. 数据有效性与 Native readiness；
2. 检索有效性；
3. 回答正确性、完整性与拒答；
4. 基于 Gold 和运行时 context 的忠实性；
5. 引用可定位性、覆盖率与蕴含精度；
6. 可靠性、时延、吞吐、资源和成本；
7. 鲁棒性及端到端可信任务成功率（TDAS）。

这里最重要的设计不是“再多加几个分数”，而是给每个指标固定：**评测对象、公式、计分单元、分母、适用条件、N/A 原因、聚合方法、证据来源和失败归因层**。否则同名的 recall、faithfulness、citation precision 很容易测到不同对象。

## 2. 与 MOI 当前计划的语境对齐

本仓库已经形成了合理的基本边界：

- v1.0 将 Native、retrieved-context replay、shared Gold Context、No-context/Noise 和 Performance 视为不同 condition，不允许混分；
- Golden 不是单一 reference answer，而是原子 `claims + alternative evidence sets + source/page/span/bbox/hash`；
- Pilot-TDAS/TDAS 是 attempt 级二元任务成功门禁，质量分不能补偿失败、超时或伪造引用；
- 没有真实 retrieval trace、rank 和匹配 qrels 时，检索与 runtime-context 指标必须为 `N/A/TRACE_UNAVAILABLE`，不能从最终答案或可见 citation 反推；
- initial failure 保留在主分母，retry 只测 recoverability；
- parser、retriever、reader、citation、Native end-to-end 和 performance 分层报告。

这些边界与一手研究一致。RAGChecker 明确把整体、retriever 和 generator 诊断拆开，并采用 claim-level entailment，而不是只做回答级相似度；RAGPerf 则把 embedding、indexing、retrieval、reranking、generation 拆开做系统剖析。[RAGChecker（NeurIPS 2024）](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)、[RAGPerf（2026）](https://arxiv.org/abs/2603.10765)

## 3. 指标总框架

| 层 | 必报核心指标 | 主要回答的问题 | 建议角色 |
|---|---|---|---|
| L0 Validity/Readiness | manifest/hash 完整率、accepted/searchable-ready 文件与页面率、Gold evidence preservation、build success/time | 数据和知识库是否真的可评 | Gate，不进质量加权 |
| L1 Retrieval | Evidence/claim Recall@K、Complete Evidence-set Recall@K、nDCG@K、Context Precision@K、MRR（次要） | 找到了什么、是否找齐、排序是否合理 | 有真实 trace 才报 |
| L2 Answer | Response-claim Correctness、Reference-claim Recall、Critical Claim Coverage、严格拒答成功率、False Refusal、Answer Relevance | 说得对不对、全不全、是否回应问题 | TDAS 核心组成 |
| L3 Grounding | Gold-evidence Support、Runtime-context Faithfulness、Hallucinated Claim/Span Rate、Context Utilization | 事实是否由冻结真值或实际上下文支持 | Gold 与 runtime 必须分列 |
| L4 Citation | Locator Validity、Citation Entailment Precision、Answer-claim Citation Coverage、fabricated/out-of-scope citation | 用户看到的引文能否核验且支持对应 claim | citation-required 题为 Gate |
| L5 Reliability/Performance/Cost | availability、error/timeout、repeat flip、TTFT/E2E P50/P95、steady-state QPS、资源、单位 attempt/可信答案成本 | 系统是否稳定、快且经济 | 独立性能报告 |
| L6 Robustness/E2E | 扰动前后 TDAS/组件分下降、worst-slice、TDAS rate | 在噪声、冲突、版本和规模变化下是否仍完成可信任务 | 端到端北极星与风险报告 |

## 4. 各层指标建议

### 4.1 L0：Validity 与 Native readiness

必须记载：

- `planned/observed` 文档、页面、问题、initial/retry/replacement 数；
- manifest、file hash、Gold hash、system/config/judge 版本完整率；
- accepted、processed、indexed、searchable-ready 文件率和页面率；
- **Gold Evidence Preservation**：冻结 evidence item 在解析产物中仍可定位的比例，critical evidence 单列；
- source/page/span/bbox/hash provenance 完整率；
- ingest、parse、embedding、index 和总 build 时间；
- readiness failure、question/run invalid、replacement、N/A reason counts。

为什么：如果 Gold 证据在解析阶段已经丢失，回答失败不能归因给 retriever 或 generator。UI 的“完成”也不等于 searchable-ready。L0 应作为资格和失败归因 Gate，不折入后续质量平均数。

### 4.2 L1：Retrieval effectiveness

#### P0：Evidence/Claim Recall@K

```text
Evidence Recall@K = K 内命中的 eligible Gold evidence items / eligible Gold evidence items
Claim Recall@K = 至少一套证据命中的 Gold claims / 全部 Gold claims
```

两者都要记。Evidence item recall 便于定位页/块遗漏；claim recall 更接近“生成答案所需信息是否到齐”。RAGChecker 把 claim recall 定义为 retriever 对 ground-truth claims 的覆盖，说明传统 chunk 指标和语义信息覆盖并不等价。[RAGChecker §3.3 与 Appendix B](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)

#### P0：Complete Evidence-set Recall@K

```text
Complete-set Recall@K =
  在 K 内至少完整命中一套替代 evidence set 的 claims
  / 全部 eligible claims
```

这是 MOI 多证据、多跳题最关键的检索指标。普通 any-hit Recall@K 会把“只找到半条证据链”误判为成功；Golden 的 set 间 OR、set 内 AND 正好可直接计算这一指标。critical claims 应另报 `Critical Complete-set Recall@K`，不能被非关键 claim 平均稀释。

#### P0：nDCG@K；P1：MRR

- `nDCG@K` 适合页面/块有 graded relevance 时，反映相关度和位置折损；建议文档视觉检索主报 `nDCG@10`，并同时报 recall。
- `MRR` 只看首个相关结果，适合 exact-identifier/single-evidence 查询；它不反映多证据是否找齐，因此不应作为 MOI 主检索指标。

TREC 强调 qrels 必须与被测 document collection 匹配；其 graded judgments 还要求二元指标与 nDCG 使用正确的 relevance 映射。因此，版本错位或 collection 不匹配时一律 N/A，不能“近似计算”。[TREC relevance judgments](https://trec.nist.gov/data/reljudge_eng.html)、[TREC 2023 Deep Learning qrels 说明](https://trec.nist.gov/data/deep2023.html)

#### P1：Context Precision@K

```text
Context Precision@K = top-K 中含至少一个 Gold claim/evidence 的 chunks / 返回 chunks 数
```

为什么：高 recall 可能通过塞入大量噪声换来。RAGChecker 的 context precision 是 relevant chunks / k，同时其结果指出增加 context 可能提高 recall/faithfulness，却也提高噪声敏感性；因此 recall 和 precision 必须成对看。[RAGChecker](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)

记录注意：必须保存 retrieval unit（page/chunk/span）、chunker 版本、K、rank、score/rerank score、raw text/hash、context order 和 truncation。否则跨系统的“chunk precision”不可比。

### 4.3 L2：Generation / answer quality

#### P0：Response-claim Correctness（实质是 claim precision）

```text
Correctness = Σ eligible response factual claim correctness / eligible response factual claims
标签：correct=1, partial=0.5, incorrect=0
```

为什么：它回答“系统说出的内容有多少正确”，不能回答遗漏。应在 schema 中把显示名写为 `Response-claim Correctness`，并在描述中明确其 precision 语义，避免与整体 QA accuracy 混淆。

#### P0：Reference-claim Recall 与 Critical Claim Coverage

```text
Reference-claim Recall = 完整覆盖的 scored Gold claims / 全部 scored Gold claims
Critical Claim Coverage = 覆盖的 critical claims / 全部 critical claims
```

为什么：correctness 很高的极短回答仍可能漏掉大部分要求。critical coverage 必须为 1 的 Gate；普通 reference recall 用于记录非关键要点的完整性。RAGChecker 的整体 precision/recall 同样通过响应 claims 与 ground-truth claims 的双向 entailment区分“多说错”和“少说漏”。[RAGChecker](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)

#### P0：不可回答与相关性

- `Strict Unanswerable Success`：明确证据不足，理由符合冻结 `negative_reason`，且无 unsupported fact/伪造引用；
- `False Refusal Rate`：answerable initial attempts 中错误拒答的比例；
- `Answer Relevance / Instruction Compliance`：回答是否直接回应问题、满足格式/范围约束；建议 0/1/2 rubric 并保留理由，首版只作诊断。

RGB 将 negative rejection、noise robustness、information integration 和 counterfactual robustness 分开，说明“拒答”和“回答准确”是不同能力，不能只看一个 QA 分数。[RGB 原始论文](https://arxiv.org/abs/2309.01431)

Exact Match、token F1、ROUGE/BLEU 只应在短、规范化、封闭答案上作为兼容指标；对于同义表述、多 claim、长答案、表格/视觉题，它们不能替代 claim correctness/recall。

### 4.4 L3：Faithfulness / groundedness

必须同时保留两个不同参照：

```text
Gold-evidence Support =
  被至少一套完整冻结 Gold evidence set 支持的 response claims
  / eligible response claims

Runtime-context Faithfulness =
  被本次实际送入 generator 的 retrieved context 完整支持的 response claims
  / eligible response claims
```

- Gold support 回答“相对于被测 corpus 的冻结真值，这个回答有无依据”；是 Native TDAS 的核心。
- Runtime-context faithfulness 回答“generator 是否忠于它实际看到的 context”；只在真实 context trace 可导出时计算。

一个回答可能忠于错误/过期 retrieved context，却不符合 Gold；也可能凭模型内知识答对，但没有被实际 context 支持。两者必须分列，不能用 RAGAS 式 faithfulness 或最终 citation 替代 Gold support。RAGAS 把 context relevance、answer faithfulness、answer relevance分开，并将其定位为无需人工 reference 的快速评估框架；它适合诊断或回归，不应覆盖 MOI 的冻结 Gold 判分。[RAGAS（EACL 2024）](https://aclanthology.org/2024.eacl-demo.16.pdf)

另建议记录：

- `Unsupported/Hallucinated Claim Rate = unsupported response claims / response claims`；
- `Hallucinated Span Rate`（字符/token 或人工 span 数，单位必须冻结）；
- `Context Utilization`：已召回 Gold claims 中实际进入回答的比例；
- critical contradiction count/率。

RAGTruth 使用自然生成响应的 response-level 与 word-level 人工幻觉标注，适合校准 hallucination evaluator；但它不是 Native retrieval 或 PDF 端到端分数。[RAGTruth（ACL 2024）](https://aclanthology.org/2024.acl-long.585.pdf)

RAGBench 的 TRACe 另分 Relevance、Utilization、Completeness、Adherence；其 completeness 衡量“已召回相关 context 被答案使用多少”，不是 MOI 的 Reference-claim Recall。实现时必须避免同名误接。[RAGBench 原始论文](https://arxiv.org/abs/2407.11005)

### 4.5 L4：Citation quality

建议固定四个互补指标：

1. `Citation Locator/Resolvability Validity`：引用能否解析到冻结 `document/page/span|bbox/hash`；
2. `Citation Entailment Precision`：提交的 citations 中，能完整支持其关联 claim 的比例；
3. `Answer-claim Citation Coverage`：citation-required response claims 中至少有一条 valid + entailing citation 的比例；
4. `Fabricated / Out-of-scope Citation Count`：伪造、不可解析、越 selected-file scope 的引用数量。

ALCE 明确把 citation recall（每个 statement 是否被其 citations 联合完整支持）与 citation precision（逐 citation 是否相关）分开；其附录也指出自动 NLI 对 partial support 的处理存在边界。因此 MOI 应保留 `full/partial/none` 原始标签，Gate 只认 full support，关键 claim/citation 做人工审计。[ALCE §3.3 与 Appendix E/F](https://aclanthology.org/2023.emnlp-main.398.pdf)、[ALCE 官方代码](https://github.com/princeton-nlp/ALCE)

零 citation 的语义要明确：locator/entailment precision 为 `N/A/NO_SUBMITTED_CITATION`；citation-required 题 coverage=0，TDAS=0。不要把空集 precision=1 单独展示，否则会奖励完全不引用的系统。

### 4.6 L5：Reliability、latency、throughput 与 cost

#### 可靠性

- Initial availability、terminal success、timeout/error rate（按 error taxonomy）；
- retry recovery rate，但 retry 不替换 initial；
- repeat contingency：`pass/pass/...` 或三次 formal 的 `3/3 pass`、flip rate；
- 每题 component dispersion，另报 worst-repeat；
- quality drift：同一冻结 probe 在性能批次前后是否下降。

为什么：只对成功请求算质量会产生幸存者偏差；只报平均成功率会隐藏同题随机翻转。

#### 时延与吞吐

- Online：TTFT、retrieval、rerank、generation、E2E latency 的 P50/P95；样本量足够再报 P99；
- Offline/build：ingest、parse、embedding、index、ready 总时长；
- Steady-state throughput：successful terminal requests/s 和 trusted answers/s；同时报告 offered load、completed load、timeout/error；
- 固定 low/medium/high concurrency、query/update mix、input/output/context tokens、warm/cold cache、warm-up 和 steady-state window；
- timeout 是 censored failure，不得从分位数数据中静默删除，必须与 terminal latency 分布并列。

MLPerf 的可复用原则是：由统一 load generator 负责请求调度、日志、latency 和质量校验，并在 latency/quality constraint 下测吞吐；这比单次手工 stopwatch 更可比。[MLPerf Inference 论文](https://arxiv.org/abs/1911.02549)、[MLCommons LoadGen/提交流程](https://docs.mlcommons.org/inference/submission/)

#### 资源与成本

- build/query 阶段 CPU/GPU 利用率、峰值与 P95 RAM/VRAM、disk/network I/O；
- index size、storage amplification、cache policy；
- `Cost per initial attempt = initial billable cost / all initial attempts`；
- `Cost per trusted answer = initial billable cost / TDAS-successful initial attempts`；
- retry、build、storage、egress、judge 和人工成本分列；
- token/embedding/vector DB/API usage 及价格表版本、币种、税费口径。

RAGPerf 同时采集端到端 throughput、CPU/GPU/内存/I/O 与 context recall、query accuracy、factual consistency，并支持 query/update ratio 等 workload；这支持 MOI 把“质量—性能—资源”同屏观察，但仍不合成一个总冠军分。[RAGPerf](https://arxiv.org/abs/2603.10765)

`cost per trusted answer` 尤其重要：便宜但低 TDAS 的系统不应因 `cost/request` 较低而被误判为经济。若成功数为 0，记 `N/A/NO_TRUSTED_ANSWER` 或 `+∞`，不能记 0。

### 4.7 L6：Robustness 与端到端

建议把鲁棒性设计成同源 paired variants，在相同 claim/evidence truth 下只改变一个因素：

| 轴 | 建议控制变量 | 必报结果 |
|---|---|---|
| irrelevant noise | 噪声 chunk 比例、相似度、位置、数量 | TDAS/claim recall/faithfulness 的绝对与相对下降 |
| misleading/contradictory evidence | 是否含近真错误、版本冲突、权威级别 | critical contradiction、正确拒答/消歧率 |
| missing evidence | 移除关键证据或只留半套 evidence set | strict unanswerable / unsupported claim |
| query variation | 中英文、同义改写、拼写/OCR、exact identifier | paired pass flip、retrieval rank shift |
| document variation | 扫描质量、表格/图片、跨页、多跳、长文档 | 分层 complete-set recall 与 TDAS |
| scope/version | selected-file、旧新版、近重复 family | scope violation、version disambiguation success |
| load/scale | corpus size、并发、query/update mix | quality drift + latency/error degradation |

RGB 的四个测试能力为 noise robustness、negative rejection、information integration、counterfactual robustness；RAGGED 进一步表明检索深度增加并不保证 RAG 改善，reader 对噪声的鲁棒性可能决定系统是否随 context 扩大而退化。[RGB](https://arxiv.org/abs/2309.01431)、[RAGGED（ICML 2025）](https://proceedings.mlr.press/v267/hsia25a.html)

鲁棒性不要只报扰动条件的绝对分。每组都应记录：

```text
absolute_drop = score_clean - score_perturbed
relative_drop = absolute_drop / max(score_clean, ε)
paired_flip   = clean_pass != perturbed_pass
worst_slice   = min(score over preregistered slices)
```

端到端主指标保留项目自定义 TDAS：每个 initial `(system, condition, question, repeat)` 只有在 readiness、terminal success、answer、critical claims、Gold support、scope 和 citation gates 全过时才为 1。必须同时展示各 component numerator/denominator；TDAS 是“可信任务是否完成”，不是隐藏诊断信息的万能总分。

## 5. 每条 metric record 必须记载的字段

建议建立统一 metric catalog 与长表结果，而不是只在报告里写百分比。

```yaml
metric_id: citation.claim_coverage.v1
display_name: Answer-claim Citation Coverage
layer: citation
definition_version: v1
direction: higher_is_better
unit: response_claim
formula: valid_entailing_cited_claims / citation_required_response_claims
numerator: 18
denominator: 20
value: 0.90
aggregation: micro_within_attempt_then_question_macro
applicability: citation_required_answerable
na_reason: null
gate_role: tdas_required_eq_1
source_contract: gold-v1
judge_version: judge-v3
```

每条结果还必须联接以下维度：

- `run_id, initial/retry/replacement, system_id/version, condition, config_hash`；
- `question_id, family_id, analysis_cluster_id, question_type, slice tags`；
- `corpus/freeze/gold/schema version, document/page/evidence IDs`；
- `repeat_id, timestamp, timeout/error/censoring`；
- metric 原始 numerator、denominator、value、N/A reason；
- 自动/人工判定、judge model/prompt/temperature、reviewer/adjudication；
- latency/usage/cost 的原始事件与价格版本。

为什么必须保存 numerator/denominator：`90%` 可能是 9/10、90/100，也可能是在剔除失败后的 9/10；只有原始分母和 eligibility/N/A 才能审计。

## 6. 聚合和统计口径

1. attempt 是事实记录单位；initial、retry、replacement 不混分母。
2. claim/citation 指标先在 attempt 内计算；整体同时报 micro 原始计数和按 question 的 macro，不能把相关 claims 当独立样本造窄 CI。
3. repeats 先在同一 question 内汇总，再按 question/analysis cluster 聚合，防止多次采样伪增样本量。
4. Pilot 只给 numerator/denominator、rate 和描述性 Wilson interval；正式同题系统比较采用冻结的 paired cluster bootstrap。
5. 题型、语言、表格/视觉、多跳、fresh、unanswerable、citation-required、长文档和版本冲突为预注册切片；小切片只报 counts/rates/cases。
6. 性能分位数仅基于有完整时间戳的 terminal attempts，但 timeout/error/censored 数必须并列；吞吐必须绑定 latency 与 quality Gate。
7. 不跨不同 freeze、condition、generator envelope、context budget 或 K 做无条件排名。

## 7. 推荐的最小落地优先级

### P0：首轮必须实现

- manifest/readiness/evidence preservation；
- Response-claim Correctness、Reference-claim Recall、Critical Coverage；
- Gold-evidence Support、strict unanswerable、false refusal；
- Citation locator、entailment precision、claim coverage、fabrication/scope；
- initial availability/error、repeat flip、E2E P50/P95；
- TDAS 与完整 attempt ledger；
- trace 可用时 Evidence Recall@K、Complete Evidence-set Recall@K、Context Precision@K。

### P1：formal/performance 轨补齐

- nDCG@K、MRR、runtime-context faithfulness、context utilization；
- TTFT 与分阶段 latency、steady-state QPS、资源利用、index/storage；
- cost per attempt、cost per trusted answer；
- paired robustness delta、worst-slice、quality-under-load；
- judge-human agreement 与分层 error analysis。

### P2：暂不作为主指标

- 单独的 embedding answer relevance；
- BLEU/ROUGE/BERTScore；
- 无 trace 的 retrieval/faithfulness 猜测值；
- 任意 F1/harmonic 或加权总分；
- 未经人类校准的 LLM-as-judge 分数；
- 把引用当 retrieval trace、把 vendor “满意度”当 benchmark 真值。

## 8. 关键风险与缓解

| 风险 | 后果 | 缓解 |
|---|---|---|
| Judge 漂移/自偏好 | 自动分数变化不代表系统变化 | 冻结 judge；双人盲审校准；记录 QWK/分标签 precision-recall；模型/prompt 变更重校准 |
| chunk 粒度不同 | Context Precision/Recall 跨系统失真 | 同时报 claim/evidence-set 语义指标；记录 unit/chunker；无法对齐时只做系统内诊断 |
| qrels/collection 不匹配 | nDCG/MRR/Recall 无意义 | freeze hash 对账；不匹配即 N/A |
| trace 不可用 | 无法归因 retrieval vs generator | `TRACE_UNAVAILABLE`；保留 Native TDAS；用统一 replay/oracle 作有限诊断，不反推 |
| citation 与 evidence 混淆 | 看似有引文但事实无支持 | locator、coverage、entailment 分开；Gold support 独立计算 |
| 成功样本幸存者偏差 | 超时系统看起来质量更高 | 所有 initial 进 TDAS/availability 分母；terminal latency 与失败并列 |
| cost/价格漂移 | 跨时段比较错误 | usage 原始量与 price snapshot 分离；币种/时间/折扣/税口径冻结 |
| 鲁棒性多因素同时变 | 无法解释下降原因 | paired single-factor variants、seed 和 perturbation manifest 预注册 |
| 许可与数据泄漏 | 结果不可用于产品决策/公开 | Product gate 与 research lane 物理隔离；family/hash/license/egress gate |

## 9. 一手来源索引

- [RAGChecker: A Fine-grained Framework for Diagnosing Retrieval-Augmented Generation（NeurIPS 2024）](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)：claim-level overall/retriever/generator 指标。
- [RAGAS: Automated Evaluation of Retrieval Augmented Generation（EACL 2024）](https://aclanthology.org/2024.eacl-demo.16.pdf)：context relevance、faithfulness、answer relevance 的 reference-free 框架。
- [ALCE: Enabling Large Language Models to Generate Text with Citations（EMNLP 2023）](https://aclanthology.org/2023.emnlp-main.398.pdf) 与 [官方代码](https://github.com/princeton-nlp/ALCE)：citation recall/precision、claim recall。
- [RAGBench / TRACe](https://arxiv.org/abs/2407.11005)：Relevance、Utilization、Completeness、Adherence 及 evaluator 回归。
- [RAGTruth（ACL 2024）](https://aclanthology.org/2024.acl-long.585.pdf)：自然 RAG 响应的 response/word-level hallucination 标注。
- [RGB](https://arxiv.org/abs/2309.01431)：noise、negative rejection、information integration、counterfactual robustness。
- [RAGGED（ICML 2025）](https://proceedings.mlr.press/v267/hsia25a.html)：retrieval depth、噪声鲁棒性和稳定/扩展性。
- [TREC relevance judgments](https://trec.nist.gov/data/reljudge_eng.html) 与 [TREC 2023 graded qrels](https://trec.nist.gov/data/deep2023.html)：qrels/collection 匹配与 graded/binary relevance 口径。
- [BEIR（NeurIPS 2021）](https://openreview.net/pdf?id=wCu6T5xFjeJ)：跨领域 retrieval 泛化和效率权衡。
- [RAGPerf](https://arxiv.org/abs/2603.10765)：端到端 RAG 组件性能、资源和 workload 设计。
- [MLPerf Inference](https://arxiv.org/abs/1911.02549) 与 [MLCommons LoadGen 文档](https://docs.mlcommons.org/inference/submission/)：可复现负载、latency/throughput/quality 约束。

## 10. 最终建议

MOI Bench 的最小可信公开结果不应是一行总分，而应至少同时给出：

```text
TDAS + initial availability
+ answer correctness/recall/critical coverage
+ Gold support + citation coverage/precision/locator validity
+ trace 可用时 complete evidence-set recall@K
+ repeat flip
+ E2E P50/P95 + timeout/error
+ cost per trusted answer
+ 预注册关键切片与鲁棒性下降
+ numerator/denominator/N/A reasons
```

这套组合能分别回答“能不能用、为什么失败、是否稳定、代价多少”，又不允许时延、成本或某个漂亮的自动分数掩盖核心质量失败。
