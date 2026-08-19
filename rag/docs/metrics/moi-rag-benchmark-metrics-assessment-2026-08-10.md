# MOI RAG Benchmark 评估指标调研与记载建议

> **版本提示：本文已由 [MOI RAG Benchmark 指标体系 v2：Evidence Chain](moi-rag-benchmark-metrics-framework-v2-2026-08-10.md) 重构取代；本文仅保留为第一版研究记录。**
>
> 日期：2026-08-10
> 范围：MOI Native RAG 产品链路、公开 benchmark 诊断轨、自建 Gold 正式横评、独立性能轨
> 结论性质：指标设计建议，不是本轮产品排名

## 1. 结论

MOI RAG Bench 评估的对象不是单个检索器或生成模型，而是完整产品链路：

```text
原始文件 → ingest → parse/OCR/layout → chunk/index → retrieval
        → context assembly → generation → citation/evidence binding
```

因此，建议采用“一个严格的端到端北极星 + 六层可诊断 scorecard + 独立性能/可运维报告”，而不是把所有指标加权成一个总分：

1. **端到端北极星：TDAS**。每个问题、每次 initial attempt 判断是否同时满足就绪、请求成功、回答正确完整、有 Gold 支持、无关键矛盾，以及题目要求的引用门禁。
2. **六层 scorecard**：Validity/Readiness、Retrieval、Answer、Citation、Reliability、Operability/Trace。它解释 TDAS 为什么成功或失败。
3. **指标分轨**：Native、retrieved-context replay、shared Gold Context/oracle、公开 benchmark official、performance 必须分开，不能混在同一排行榜。
4. **先记原始事实，再算指标**：每个聚合数都必须能回溯到 frozen manifest、逐题 ledger、原始回答、retrieved context/citation、判分记录和 hash。
5. **不发布 overall winner**：正确率、缺失能力、延迟、成本和人工操作量是不同构念，任意权重会掩盖真实取舍。

这与当前母计划对 MOI 产品边界、TDAS 六层 scorecard、attempt 合同和报告约束的定义一致，参见 [v1.0 执行路线图](../drafts/v1.0.md)、[三阶段计划](../todo/moi-rag-benchmark-three-stage-plan-v1.md) 和 [Golden 与指标规范](../todo/golden-and-metrics-spec-v0.4.md)。

## 2. 我对当前 MOI RAG Bench 的理解

### 2.1 它要回答的不是一个问题，而是五个问题

| 研究问题 | 对应输出 |
|---|---|
| 文件能否可靠变成可搜索证据 | Readiness、解析/证据保存、build time |
| 系统能否找全并排好正确证据 | Recall@K、complete evidence-set recall、nDCG/MRR、context precision |
| 系统能否基于证据给出正确且完整的答案 | claim correctness、reference-claim recall、Gold support、拒答/矛盾 |
| 引用是否真实、可定位且支持对应陈述 | locator validity、citation entailment precision、claim coverage |
| 这条链路是否稳定、快、便宜且容易运维 | availability、repeat flip、latency、throughput、cost、人工时间、恢复性 |

MOI 还暴露 workflow、解析 artifact、page/source mapping、selected-file scope、job/retry/lineage 等产品能力，所以只看最终答案会把解析、索引或 scope 失败错误归因给生成模型。[MOI benchmark scope](../research/moi-rag-platform-benchmark-scope.md) 已经明确把被测对象定义为组合产品链路。

### 2.2 不同阶段的指标角色不同

- **公开 benchmark / Stage 1**：保留 dataset-native official metrics，用来复现论文口径和定位组件能力；同时产出 MOI unified metrics。两者必须分表。
- **自建 Gold / Stage 2**：验证 Gold、rubric、evidence lineage 和 MOI-only pilot，核心是 TDAS 与六层 scorecard 是否可重算。
- **正式横评 / Stage 3–4**：在同一 freeze、同一题集、同一 condition、同一时间窗下比较 MOI 与竞品，使用 question-level paired difference 和区间。
- **性能 / Stage 5**：固定硬件、负载和并发阶梯，独立报告 latency、throughput、error/censoring 和成本，不让高吞吐抵消低质量。

### 2.3 当前已产出的指标与主要缺口

[2026-08-07 结果](../../results/MOI%20RAG%200807.md) 已经覆盖：

- WikiEval：Source Recall@1/3/5、MRR、RAGAS Faithfulness/Answer Relevance/Context Precision/Recall、MOI retrieval P50/P95；
- MMDocIR retrieval：Page Recall、Layout Recall、MOI retrieval P50/P95；
- MMDocIR QA：LLM-judge correctness、Token F1、Faithfulness、contains-gold、normalized EM、MOI QA P50/P95。

这些结果能支持工程诊断，但还不足以支撑正式产品结论：WikiEval 已出现明显 ceiling；Dify 延迟缺失；FastGPT/MaxKB 未形成可比完整运行；MMDocIR QA 是 adapted protocol；统一 TDAS、claim/citation 判分、readiness、failure denominator、repeat stability、成本和可运维数据尚未在发布主表中闭环。DocBench 全量 1,102 题仅完成 38 题且已暂停，必须保留为 interrupted/censored run，不能把 38 题当成全量分母，参见 [DocBench checkpoint](../checkpoints/docbench-full-evaluation-2026-08-07.md)。

## 3. 指标设计原则

### 3.1 官方指标与 MOI 统一指标并存，但不改名

每个公开 benchmark 应输出两套结果：

- `official/*`：严格记录论文/官方代码版本、原始指标名、单位、聚合方式和 protocol；
- `moi-unified/*`：用统一 Gold、attempt、claim、citation、latency 和错误口径计算。

如果数据、候选范围、模型、prompt、Judge 或 scorer 任一关键条件不同，必须标 `ADAPTED_PROTOCOL`。不能把 RAGAS Context Precision/Recall 改名为论文中的 Context Relevance，也不能把 any-hit Recall 当作多跳证据“全部找齐”。

### 3.2 指标必须绑定明确的计分单元和分母

至少区分四种计分单元：

- file/page：ingest、parse、ready；
- query/question：retrieval、端到端 TDAS、拒答；
- claim/citation：正确性、完整性、支持度和引用；
- attempt/journey：availability、latency、cost、repeat、人工操作。

每个结果字段必须同时保存 `numerator`、`denominator`、`value`、`unit`、`eligible_count`、`missing_count` 和 `na_reason`。只写 `score=0.83` 不足以审计。

### 3.3 Gold support、runtime faithfulness 和 correctness 不能互相替代

- **Correctness**：回答说出来的事实是否正确；
- **Reference-claim Recall**：应该回答的要点覆盖了多少；
- **Gold-evidence Support**：回答事实是否被冻结 Gold evidence 完整支持；
- **Runtime-context Faithfulness**：回答是否被这一次实际 retrieved context 支持。

RAGAS 将 faithfulness、answer relevance 和 context relevance 分开，说明“受 context 支持”与“切题/检索相关”不是同一概念；RAGChecker 进一步把 response claim、ground-truth claim 和 retrieved chunks 分开诊断。[RAGAS](https://aclanthology.org/2024.eacl-demo.16.pdf)；[RAGChecker](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)。MOI Bench 应保留这四个维度，不用一个 LLM 总分替代。

### 3.4 trace 不可见要写 N/A，但必需能力缺失不能获益

- 没有真实 retrieved chunks/rank/qrels：Retrieval、runtime faithfulness 和 utilization 为 `N/A: TRACE_UNAVAILABLE`，不得从回答或引用反推。
- citation-required 题没有提交引用：locator/precision 因无提交对象可为 N/A，但 required-claim citation coverage 必须为 0，TDAS 失败。
- timeout、空答、产品/API 错误：保留在 initial 分母，质量和 TDAS 记 0，不是 N/A。
- 只有 benchmark-side 数据、schema、脚本或 lineage 缺陷才能标 invalid；replacement 不能覆盖原始失败记录。

## 4. 建议记载的指标

### 4.1 P0：运行身份、有效性与分母账本

这是所有分数的前置条件，建议每次运行强制记录。

| 指标/字段 | 定义或输出 | 为什么必须记 |
|---|---|---|
| System/condition identity | system、版本、部署、tenant/region、Native/Optimized/replay/oracle/performance | 防止跨版本、跨路径混排 |
| Frozen configuration | parser、embedding、chunking、top-k、reranker、generator、prompt、context/output budget、config hash | 让差异可归因、可复现 |
| Dataset/Gold identity | dataset revision、split、file/question/gold hash、gold_version、freeze_id | 防止题集或 Gold 漂移 |
| Planned/observed ledger | files、pages、questions、initial/retry/replacement attempts | 发现删题、漏跑和分母漂移 |
| Attempt disposition | success、empty、timeout、product error、invalid、interrupted/censored、not started | 区分产品失败与评测失败 |
| Capability/trace ledger | citation capability、trace/rank/score/source map/token usage/cost 可用性 | 防止能力缺失被当成高分或静默缺失 |
| Artifact integrity | raw/config/gold/answer/context/judgement 路径与 SHA-256 | 保证主表能由 artifact 重算 |

最终报告第一张表应是 validity/capability 表，而不是准确率表。

### 4.2 P0：Readiness 与解析/证据保存

| 指标 | 推荐定义 | 原因 |
|---|---|---|
| Accepted-file/page rate | 被产品接受的 eligible file/page ÷ manifest file/page | 直接捕获格式或规模兼容性 |
| Searchable-ready success | `processed ∧ indexed/embedded ∧ search-probe-pass` 的文件比例 | UI 显示“完成”不等于真的可检索 |
| Required-evidence ready rate | 每题至少一套完整 Gold evidence set 已 ready 的比例 | 连接 corpus readiness 与端到端失败 |
| Gold evidence preservation | Gold span/bbox/table/image 是否在解析 artifact 中保留且可定位 | 识别 parser 导致的不可恢复信息损失 |
| Provenance preservation | artifact/chunk/citation 到 file/page/span/bbox/hash 的映射正确率 | 是可解释检索和可信引用的基础 |
| Build time/status | ingest 开始到 searchable-ready；失败保留 terminal/censored 状态 | 衡量 time-to-value，避免只对成功建库计时 |
| Dataset-native parser metrics | text edit distance、TEDS、formula/reading-order 等，按官方任务单列 | 可诊断 parser，但不能与回答质量合成总分 |

### 4.3 P0/P1：Retrieval 与 context assembly

只有真实 trace、rank 和与候选集合匹配的 qrels 可用时才计算排序指标。TREC 也强调 relevance judgments/qrels 必须与对应 test collection 一起解释。[NIST TREC qrels](https://trec.nist.gov/data/reljudge_eng.html)。

| 指标 | 推荐定义 | 优先级与原因 |
|---|---|---|
| Evidence Recall@K | 被 Top-K 命中的 required Gold evidence item ÷ required items | P0；回答失败最常见的上游解释 |
| Complete Evidence-set Recall@K | 至少一套 alternative evidence set 在 K 内完整召回的 required claims ÷ required claims | P0；多跳/多证据题比 any-hit Recall 更有意义 |
| Page/Layout Recall@K | 严格沿用 MMDocIR 官方 page/layout 匹配和 K | P0 official；保留当前长 PDF、多模态可比性 |
| Context Precision@K | Top-K 中含 required Gold claim 的 chunks ÷ returned chunks | P1；衡量噪声和 context budget 浪费 |
| MRR | 首个 relevant item 的 reciprocal rank，未命中为 0 | P1；适合关注首个正确结果，但不能衡量证据是否找全 |
| nDCG@K | 使用冻结 graded qrels 的 normalized discounted gain | P1；同时反映等级相关性和排序位置 |
| Candidate/context budget | candidate 数、返回数、去重数、token 数、截断量、context order | P0 原始字段；解释同 recall 下的噪声与成本 |
| Trace/lineage completeness | trace-capable attempts 中必填 lineage 字段完整比例 | P0；衡量产品可观察性，不能与 retrieval quality 混为一谈 |
| Scope violation | 使用 disabled/out-of-scope file/chunk 的 attempt 数和率 | P0 gate；高 recall 不能补偿越权取证 |

RAGBench 的 TRACe Relevance、Utilization、Completeness、Adherence 可以作为 processed-context reader 诊断，但它的 Completeness 是“已召回的相关 context 有多少被回答使用”，不是 Reference-claim Recall，指标名必须保持边界。[RAGBench](https://arxiv.org/pdf/2407.11005)。

### 4.4 P0：Answer quality 与不可回答题

| 指标 | 推荐定义 | 为什么需要 |
|---|---|---|
| Claim Correctness | response factual claims 的 `1/0.5/0` 正确性均值 | 避免一个整体 Judge 分掩盖局部错误 |
| Reference-claim Recall | 完整覆盖的 scored reference claims ÷ 全部 reference claims | 衡量答案完整性 |
| Critical-required claim coverage | 覆盖的 critical claims ÷ 全部 critical claims | 关键字段遗漏不能被一般正确内容抵消 |
| Gold-evidence Support | 被至少一套完整 Gold evidence set 支持的 response claims ÷ eligible response claims | 衡量基于冻结证据的 groundedness |
| Critical contradiction-free | 是否没有与 Gold/critical claim 冲突的陈述 | 将高危错误设为硬门禁 |
| Strict unanswerable success | 正确拒答、理由匹配且无编造事实/引用的问题比例 | 防止系统靠“总回答”获得表面高覆盖 |
| False refusal | answerable 问题中错误拒答比例 | 与 unanswerable success 配对，防止过度保守 |
| Runtime-context Faithfulness | 被实际 retrieved context 完整支持的 response claims ÷ response claims | P1/trace-only；区分 retriever 与 generator 责任 |

Token F1、ROUGE、BLEU、embedding answer relevance 可作为 dataset-native 或回归诊断，不应成为 MOI 的主结论：词面相似不能可靠判断事实真值、关键点完整性或证据支持。

### 4.5 P0：Citation 与 evidence binding

| 指标 | 推荐定义 | 为什么需要 |
|---|---|---|
| Citation locator/resolvability validity | 提交引用中能解析到冻结 file/page/span/bbox/hash 的比例 | 检测“看起来像引用但无法核验” |
| Citation entailment precision | 提交引用中完整支持其关联 claim 的比例 | 检测引用与陈述错绑 |
| Required-claim citation coverage | citation-required claims 中有至少一个有效支持引用的比例 | 检测漏引，和 precision 互补 |
| Fabricated citation count | 不存在或无法解析的引用数量 | 高风险错误应给原始 count |
| Out-of-scope citation count | 指向 selected scope 外证据的引用数量 | 验证 scope/权限边界 |

ALCE 将 citation correctness 拆成 citation recall 与 precision，说明“有没有覆盖该引的陈述”和“引用是否真正支持陈述”必须分别报告。[ALCE](https://aclanthology.org/2023.emnlp-main.398.pdf)。MOI 还应额外报告 locator validity，因为产品引用必须能回到实际文件和页面。

### 4.6 P0：端到端 TDAS

建议继续采用现有规范的 strict binary TDAS。对 answerable 问题，每个 `(system, condition, question, repeat)` 的 initial attempt 必须同时满足：

```text
required evidence ready
∧ initial terminal success
∧ Correctness ≥ 0.8
∧ critical claims 全覆盖
∧ Reference-claim Recall ≥ 0.8
∧ Gold-evidence Support = 1
∧ 无 critical contradiction / scope violation
∧ citation-required gate
```

不可回答题使用独立 strict-success 规则。产品 timeout、空答、错误均为 TDAS=0。

TDAS 的价值不是“概括所有产品维度”，而是回答一个清晰问题：**用户这一次是否得到可用且可信的完整答案**。它不吸收 latency、cost、operability；如果业务需要把服务约束纳入，可在运行前冻结阈值后另报 `SLO-TDAS`，不得事后挑阈值。

### 4.7 P0/P1：Reliability、latency、throughput 与 cost

| 指标 | 推荐口径 | 注意事项 |
|---|---|---|
| First-pass availability | 合规 terminal response 的 initial attempts ÷ 全部 scored initial attempts | 不得 N/A，retry 不替换初次 |
| Final availability / retry recovery | initial 或预注册 retry 内恢复的 request units 比例 | 只作 recoverability 诊断 |
| Timeout/error rate | timeout/product/API error initial attempts ÷ 全部 initial attempts，按 error code 分层 | 失败必须留在分母 |
| Repeat stability | 3/3 TDAS pass、mixed flip、0/3 pass 的 question 数和率 | 比平均分更能揭示不稳定 |
| Latency | ingest/build、retrieval、TTFT、generation/completion、end-to-end 的 P50/P95；正式性能轨加 P99 | 必须冻结计时边界、冷/热状态、成功分母和 censoring |
| Throughput | 固定并发下 pages/docs/bytes per minute、queries per second、tokens per second | 只能在同 workload/hardware/quality gate 下比较 |
| Query/build cost | initial billable cost/unit；retry 单列；同时保存 token/调用/资源 usage | 价格不可见时 N/A + commercial gap |
| Cost per trusted answer | initial 总成本 ÷ TDAS-successful initial attempts | 成功数为 0 时为 N/A/∞，不能报 0 |

质量主轨只需稳定记录 P50/P95 和失败；并发、P99、耐久和资源饱和应放在独立 performance track。否则不同系统的限流、超时和不完整请求会污染质量比较。

### 4.8 P1：Operability 与可观察性

| 指标 | 推荐输出 | 原因 |
|---|---|---|
| Time-to-First-Searchable-Corpus | 首个管理动作到冻结 corpus ready 的 elapsed time/status | 衡量部署后的实际 time-to-value |
| Time-to-First-Trusted-Answer | 首个管理动作到首个 TDAS=1 的回答 | 把搭建、建库、调试和回答连起来 |
| Active human minutes / wall time | 按预注册角色累计，二者同时报告 | 区分机器等待与人工成本 |
| Actions/interventions | 配置、恢复、重建、人工修复的 taxonomy count | 识别“高分但难操作”的系统 |
| Configuration error rate | 阻断或改变预期流程的配置错误 ÷ journeys | 评价默认体验和可理解性 |
| Diagnostic quality | incident 的准确、及时、可操作等级及 count | 衡量能否快速定位失败 |
| Recoverability | 自动恢复、runbook 一步、需重建、不可恢复的事件分布 | 与 retry success 区分，反映工程韧性 |

这些指标给出原始 count、时间和案例，不建议做显著性排名或折入 TDAS。

### 4.9 P1/P2：切片、鲁棒性与错误归因

至少按以下切片报告 count、denominator、rate 和代表案例：

- 文档类型、领域、语言、PDF 版式、页数/长度、扫描质量；
- text/table/formula/image/cross-modal；
- single-hop/multi-hop、单文档/跨文档；
- answerable/unanswerable、citation-required；
- fresh/public、版本冲突、近失配噪声、counterfactual；
- cold/warm、并发档、产品版本和 condition。

根因 taxonomy 建议固定为：`ingest / parse / index / retrieval / context assembly / reader / citation / scope / product-api / judge-benchmark`。L1 解析失败必须在端到端 TDAS 中保留失败，同时根因归到 parse；已经完整召回证据但答错，才归到 reader/citation。

小切片只做描述性诊断，不宣布 winner。鲁棒性/noise/counterfactual 只有在 condition 和扰动规则预注册后进入 P2 专项。

## 5. 不只是“记指标”：还要记计算指标所需的原始字段

### 5.1 Run-level manifest

```text
run_id, benchmark, protocol_label, dataset_revision, split,
freeze_id, gold_version, code_commit, system_id/version/deployment,
condition, parser, embedding, chunking, top_k, reranker,
generator, prompt_hash, context/output_budget, judge_version,
hardware, run_window, order/reset/warmup, timeout/retry policy,
config_hash, artifact_root
```

### 5.2 Per-attempt ledger

```text
question_id, analysis_cluster_id, repeat_id, attempt_type,
planned_at, started_at, first_token_at, completed_at,
status, error_code, retry_of, replacement_of, invalid_reason,
session_id, answer_raw, citation_raw, retrieved_context_ref,
trace_available, input/output tokens, billable cost,
raw_response_hash, config_hash, gold_hash
```

### 5.3 Retrieval/context trace（可导出时）

```text
query_rewrite, rank, retrieval_score, rerank_score,
chunk_id, document_id, page, span/bbox, raw_text_hash,
context_order, token_count, truncation, qrel/evidence_set_id,
scope_eligible, lineage_complete
```

### 5.4 Per-response judgement

```text
canonical response claims and correctness labels,
covered reference_claim_ids, critical coverage,
Gold support and supporting evidence_set_id,
submitted citation IDs, locator/entailment/scope labels,
false refusal, critical contradiction, TDAS,
judge/reviewer/adjudication reason and version
```

### 5.5 Aggregate metric record

建议所有聚合指标统一为机器可读结构：

```json
{
  "metric_id": "reference_claim_recall",
  "metric_version": "1.0",
  "scope": {"system": "moi", "condition": "quick-native", "slice": "all"},
  "numerator": 410,
  "denominator": 500,
  "value": 0.82,
  "unit": "rate",
  "aggregation": "repeat-mean-then-question-macro",
  "ci": null,
  "eligible_count": 500,
  "missing_count": 0,
  "na_reason": null,
  "protocol_label": "MOI_UNIFIED_V1"
}
```

这比宽表更适合作为真实 source of truth；最终 Markdown/HTML 表格可由它生成。

## 6. 汇总与统计规则

1. **initial attempt 是主分母**。retry 产生附加记录，不覆盖初次。
2. **先 repeat、后 question 宏平均**。避免重复次数多的题获得更高权重。
3. **正式横评只做同 freeze、同题集、同 condition 的 paired comparison**。
4. pilot 报 numerator/denominator/rate 和描述性区间；formal 按 `analysis_cluster_id` 做同步 paired cluster bootstrap，固定 seed、10,000 replicates 和 CI 方法。
5. claim/citation 报原始 numerator、denominator 和 rate；同一问题内 claims 相关，不能把它们当独立样本制造过窄 CI。
6. 自动 Judge 必须保存 model/version/prompt/temperature/rubric，并在冻结前完成人工校准；正式输出盲化 system label，报告 QWK、分歧和 adjudication。
7. 缺失值不静默排除。每个 N/A、not-started、interrupted、censored、invalid 都需要 reason code 和计数。
8. 多切片结果默认探索性；若要做正式推断，应预注册主比较和多重比较处理。

## 7. 推荐的最终报告表格

每次正式报告至少应有以下表，而不是一张“准确率榜”：

1. Run identity、freeze、capability、protocol 和公平预算表；
2. Planned/initial/retry/replacement/invalid/interrupted 分母账本；
3. Readiness 与解析/证据保存表；
4. Retrieval 与 trace coverage 表；
5. Answer、Citation 和 TDAS 表；
6. Reliability、latency、cost 表；
7. Operability 与 observability 表；
8. Slice 与 error taxonomy 表；
9. question-level paired difference + CI 表；
10. 独立 performance/concurrency/censoring 表。

所有表必须明确 `Native / official / adapted / replay / oracle / performance`，不得横向混排。

## 8. 实施优先级

### 第一批：没有这些就不应发布正式质量结论

- run/system/config/dataset/gold freeze 与逐 attempt ledger；
- initial failure、invalid、retry、replacement、interrupted 的统一分母合同；
- readiness、claim-level answer、citation、TDAS；
- availability、timeout/error、E2E latency P50/P95；
- raw artifact、judgement 与 hash 可重算；
- Judge calibration、盲审和 protocol label。

### 第二批：有 trace/usage 才启用

- Evidence/complete-set Recall@K、Context Precision、MRR/nDCG；
- runtime faithfulness、utilization、scope/lineage completeness；
- query/build cost、cost per trusted answer；
- retrieved-context replay 与 shared Gold Context gap。

### 第三批：独立专项

- 全量 parser official metrics；
- noise、contradiction、counterfactual、freshness；
- 高并发、P99、耐久、资源饱和、弹性；
- 安全、权限隔离、poisoning、动态更新和 HA。

## 9. 对下一轮 MOI RAG Bench 的具体建议

1. 先定义一个版本化的 `metric registry`，为每个指标冻结公式、单位、计分单元、分母、方向、依赖字段、N/A/zero 规则和适用 track。
2. 把现有 WikiEval/MMDocIR runner 的输出统一映射到 per-attempt ledger 和 aggregate metric schema；不要先追求新增更多 Judge 分数。
3. 下一轮横评优先补齐 Dify 的相同计时边界、FastGPT/MaxKB terminal disposition 和全系统 capability/trace 表，否则不要发布性能或完整产品排名。
4. 在自建 Gold 中优先保证 claims、critical claims、alternative evidence sets、page/span/bbox/hash 和 answerability；没有这些，TDAS、complete-set recall 和 citation entailment 都不可审计。
5. 把当前的 RAGAS/Token F1/contains-gold 保留为诊断列，但将主结论迁移到 claim correctness、reference recall、Gold support、citation 和 TDAS。
6. 将 DocBench interrupted run 作为 ledger/censoring 的验收样例：报告 `planned=1102, completed=38, interrupted=1064`，不生成伪“全量均值”。
7. 每次发布前做一个硬验收：主表中的任意 numerator/denominator 能否从 immutable ledger 在干净环境重算；不能则结果只能标 diagnostic。

## 10. 主要参考

### 仓库内计划与现状

- [MOI RAG Benchmark v1.0 执行路线图](../drafts/v1.0.md)
- [MOI 平台 RAG 能力三阶段 Benchmark 计划](../todo/moi-rag-benchmark-three-stage-plan-v1.md)
- [Golden 与指标规范](../todo/golden-and-metrics-spec-v0.4.md)
- [分层评测计划](../todo/rag-benchmark-catalog-and-layered-evaluation-plan.md)
- [v0.3 数据量与指标建议](../research/v0.3-data-volume-and-metrics-recommendation.md)
- [MOI 产品 benchmark scope](../research/moi-rag-platform-benchmark-scope.md)
- [当前结果](../../results/MOI%20RAG%200807.md)
- [本报告配套的一手资料调研笔记](research-notes.md)

### 一手论文/官方资料

- [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://aclanthology.org/2024.eacl-demo.16.pdf)
- [RAGChecker: A Fine-grained Framework for Diagnosing RAG](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)
- [RAGBench: Explainable Benchmark for RAG Systems](https://arxiv.org/pdf/2407.11005)
- [ALCE: Enabling LLMs to Generate Text with Citations](https://aclanthology.org/2023.emnlp-main.398.pdf)
- [ARES: An Automated Evaluation Framework for RAG Systems](https://aclanthology.org/2024.naacl-long.20.pdf)
- [NIST TREC relevance judgments/qrels](https://trec.nist.gov/data/reljudge_eng.html)
