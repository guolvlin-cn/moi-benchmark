# MOI RAG Benchmark 指标体系 v2：Evidence Chain

> 日期：2026-08-10
> 状态：基于 `refs/` 22 篇唯一论文重构的研究提案
> 关系：本文件重构并取代上一版指标建议，但**不会自动覆盖**当前规范权威 [`plans/drafts/v1.0.md`](../drafts/v1.0.md)；若采纳，应通过 decision log 修订母计划和 metric registry。

## 0. 这次重构改变了什么

上一版按通用 RAG 的 Readiness、Retrieval、Answer、Citation、Reliability、Operability 罗列指标，方向正确，但还不够贴近 MOI，也没有把 `refs/` 中全部论文的设计差异系统纳入。

这次重构后的判断是：

1. **MOI 不是“检索器 + LLM”的薄封装，而是证据生命周期平台**。它覆盖文件载入、解析/OCR/layout、chunk、embedding/index、文件范围控制、检索、生成、引用、workflow、job/retry、artifact/lineage 和更新运维。
2. **MOI Bench 的主对象应是 Evidence Chain，而不是答案文本**。核心问题是：原文件中的可信证据，能否完整、正确、稳定、可追溯地到达最终回答。
3. **TDAS 继续作为端到端北极星**，但不再承担所有解释工作。八层 Evidence Chain 负责解释掉点发生在哪里。
4. **公开论文提供的是不同层的“测量协议”，不是可以相加的分数**。OmniDocBench 的 TEDS、MMDocIR 的 Layout Recall、ALCE 的 citation precision、RAGAS 的 faithfulness 和 CRUD-RAG 的 ROUGE 不在同一测量空间。
5. **MOI 特有的 scope、版本、增量更新、删除、workflow、解析 artifact 和 source mapping 必须成为一等指标**。这些能力在多数通用 RAG benchmark 中缺失，却直接决定企业产品是否可信。
6. **当前项目最缺的不是第 23 个数据集，而是统一 ledger、Gold/evidence schema、引用判分和跨平台同口径运行**。新版优先解决“能否重算、能否归因、能否公平比较”。

新版框架命名为：

```text
MOI RAG Evidence Chain v2
```

## 1. 论文全集与采用决策

`refs/` 中共有 22 篇唯一的 RAG benchmark、文档/QA benchmark 或评测框架论文。这里不是简单综述，而是明确每篇论文在 MOI Bench 中的角色。

| # | 论文/Benchmark | 最有价值的设计 | 在 MOI v2 中的角色 | 不直接采用的部分 |
|---:|---|---|---|---|
| 1 | RGB | Noise、Negative Rejection、Information Integration、Counterfactual 四类受控测试 | 鲁棒性 paired variants；中英文噪声/冲突/拒答 | 固定拒答字符串和 EM 不作为主判分 |
| 2 | ALCE | 长答案 correctness + citation recall/precision | claim→citation 覆盖和蕴含判分 | NLI 自动判分不能替代 locator 与人工审计 |
| 3 | RAGTruth | response/span-level hallucination 标注 | Judge 校准与 unsupported span 错误 taxonomy | 不作为 Native retrieval/PDF 总分 |
| 4 | RAGBench | TRACe Relevance、Utilization、Completeness、Adherence | runtime context 使用诊断 | Completeness 不改名为 reference-claim recall |
| 5 | MultiHop-RAG | 多跳类型、retrieval vs Gold evidence answer gap | complete evidence-set recall、跨页/跨文档证据链 | Hit@K/短答案 EM 不代表完整可信答案 |
| 6 | OmniDocBench | text/table/formula/order 的解析分解 | parser official track、evidence survival 诊断 | 不进入 Native 端到端总分；当前 MinerU 结果不标 MOI Native parser |
| 7 | READoc | 完整 PDF→结构化 Markdown、标题树和阅读序 | 多页结构与 provenance 回归 | 自动 Gold 和格式敏感分数仅作 parser 专项 |
| 8 | MMDocIR | Page/Layout Recall 与页→区域级联 | 长文档多模态 retrieval 主协议 | Layout Recall 混入检测误差，必须同时报 candidate coverage |
| 9 | ViDoRe V2 | blind query、多语、视觉页面 nDCG@5 | 视觉检索压力集 | 单一 nDCG 无法说明证据是否足够回答 |
| 10 | DocBench | 原始 PDF→答案、多领域/多模态/不可回答 | Native PDF E2E 主公开轨 | 单一 GPT-4 correctness 必须补齐中间 trace 与 claim 判分 |
| 11 | MMDocRAG | 文本/图片 quote selection 与图文回答 | 多模态最小充分证据链、quote P/R/F1 | BLEU/ROUGE 和五维 Judge 只保留为 dataset-native |
| 12 | EnterpriseRAG-Bench | 多源企业 corpus、atomic facts、冲突、无答案、invalid extras、可修订 Gold | 自建企业 Gold 的首要设计来源 | 合成扁平企业数据不代表权限、真实格式与时效 |
| 13 | FAB-Bench | 垂直领域 rubric、needle/multi-hop、context scaling | 领域切片和 context operating-point 曲线 | 六维 LLM 总分不进入通用主榜 |
| 14 | MIRAGE | Base/Oracle/Mixed 三条件与四类互斥失败 | controlled diagnostic matrix | 单跳 Wikipedia + EM 需扩展为多证据 claim 判分 |
| 15 | CMRC2018 | 中文字符 LCS-F1、跨句 challenge | 中文 answer boundary 和 challenge 回归 | 单段抽取不能代表企业 RAG |
| 16 | Natural Questions | long/short/NULL、多标注与 answerability threshold | answerability、多可接受答案、evidence range | 英文 Wikipedia 与旧快照仅作方法参考 |
| 17 | RAGAS | Faithfulness、Answer/Context Relevance 的 reference-free 回归 | 低成本 regression/judge 辅助轨 | 不替代 Gold correctness、evidence recall 或 citation |
| 18 | CRAG | 动态/长尾事实、Web/KG、错误负分、missing 优于 hallucination | freshness、long-tail、false-premise 与严重错误 taxonomy | 动态 Web/KG 不能混入静态 Native 文档主榜 |
| 19 | FRAMES | Fact/Fetch/Reason、多步检索、数值/表格/时序 | agentic/multi-step 专项 | Wikipedia 污染和多次调用成本，不作首轮主轨 |
| 20 | RAGChecker | claim-level overall/retriever/generator 细粒度归因 | MOI unified evaluator 的主要计算骨架 | overall F1 不作为北极星；LLM entailment 需校准 |
| 21 | ARES | 约 150+ 人工标签、专用 Judge、PPI 区间 | formal 后期的 evaluator scaling 方案 | 当前小 Pilot 不满足默认输入合同 |
| 22 | CRUD-RAG | 中文 Create/Read/Update/Delete、多文档摘要与纠幻 | MOI 知识生命周期专项 | BLEU/ROUGE/BERTScore 仅保留为任务原生指标 |

本表的本地证据入口见文末“论文索引”。核心取舍是：**吸收设计，不复制总分；保留官方指标，不把异构指标混榜。**

## 2. MOI 的评估对象与当前项目约束

### 2.1 MOI 的原生证据链

根据 [MOI 产品 benchmark scope](../research/moi-rag-platform-benchmark-scope.md)，原生产品路径应建模为：

```text
source file / volume
  → upload / workflow job
  → parse / OCR / layout / table / image artifact
  → chunk / embedding / index
  → selected-file and disabled-chunk scope
  → retrieval / rerank / context assembly
  → answer / abstention
  → citation / page / span / bbox / source mapping
```

MOI 还具备 workflow topology、配置、job status/retry、artifact preview/download、lineage 和多源数据处理能力。这意味着 MOI Bench 至少要同时评价：

- 用户能否完成 Native journey；
- 原始证据是否在 parser/index 中存活；
- 检索是否找全且没有越 scope；
- 回答是否正确、完整、有证据；
- 引用是否可核验；
- workflow 是否稳定、可恢复、可复现；
- 知识更新/删除后旧证据是否仍泄漏。

### 2.2 当前 API 与可观测性边界

[MOI API 核查](../../refs/moi-api-access-and-upload-2026-07.md) 确认，公开 Atomic API 可以提交 parse/chunk/embed job、查询 file/job status 并下载解析 artifact；但旧原型使用的 `/datasets`、`/retrieval` 路径不是已确认的公开稳定契约。

因此：

- file/job/artifact/readiness 指标可以立即建立稳定合同；
- retrieval rank/score/context/citation 是否可稳定导出，需要针对目标 tenant 验证；
- 无真实 trace 时，Native TDAS 仍可计算，但 retrieval/runtime-context 指标必须为 `N/A: TRACE_UNAVAILABLE`；
- 不能为了“表格完整”从答案或 citation 反推 retrieval trace。

### 2.3 当前运行状态决定了短期优先级

根据 [2026-08-10 进度证据](../../reports/rag-benchmark-progress-2026-08-10/source-notes.md) 和 [当前结果](<../../results/MOI RAG 0807.md>)：

- OmniDocBench 已有完整/分层解析结果，但属于外部 MinerU 适配，不是 MOI Native parser；
- MMDocIR 已有 MOI Page/Layout 全量与 Dify 50 题 page pilot，但本地协议是 document-local adapted；
- WikiEval 50 题已跑 MOI/Dify，Source Recall 出现 ceiling，适合回归而非正式区分；
- DocBench 1,102 题只完成 38 题后中断；
- MMDocRAG 已有 ingest/准备产物，但没有形成完整统一 E2E 主表；
- 本地竞品只有 Dify 完成真实 benchmark；FastGPT、MaxKB、RAGFlow 仍未通过完整门禁；
- latency、trace、citation、cost 和 attempt disposition 跨平台不齐。

所以新版的第一优先级是“统一账本并重算现有结果”，不是立刻全量接入 22 套论文数据。

## 3. 新框架：八层 Evidence Chain

### 3.1 总体结构

```text
北极星：TDAS / Trusted Answer Delivery Rate

L0  Protocol, Validity & Eligibility
L1  Corpus Journey & Searchable Readiness
L2  Evidence Survival & Provenance
L3  Retrieval, Scope & Context Assembly
L4  Answer Correctness, Completeness & Grounding
L5  Citation & User-verifiable Evidence
L6  Reliability, Performance & Cost
L7  Lifecycle, Workflow & Operability

横切：Robustness、Slices、Judge Quality、Rights/Egress
```

相对上一版，最重要的结构变化是：

- 将“是否 ready”和“证据是否在解析中存活”拆成 L1/L2；
- 将 selected-file/disabled-chunk/版本范围放入 L3 硬门禁；
- 将引用独立为用户可验证证据层；
- 将知识更新、删除、workflow 和运维独立为 L7；
- 性能必须绑定质量和失败分母，不单报成功请求 latency。

### 3.2 Evidence Chain 漏斗

每个 answerable initial attempt 应在同一主分母上报告以下无条件通过率：

```text
F0 eligible question
F1 required evidence searchable-ready
F2 required evidence survived parser/index with provenance
F3 at least one complete evidence set retrieved within K     [trace-only]
F4 answer correct + complete + Gold-supported
F5 required citations valid + entailing + complete
F6 TDAS pass
F7 SLO-TDAS pass                                              [optional]
```

必须同时报告：

- `pass(Fi) / all eligible initial attempts`：用户最终看到的真实损失；
- `pass(Fi) / pass(Fi-1)`：阶段转换率，用于工程归因；
- 每一层的失败 count 和 error taxonomy。

不能只在上一层成功样本中展示漂亮指标。例如只对成功回答算 faithfulness，会隐藏 timeout/空答的幸存者偏差。

## 4. 北极星与核心判分

### 4.1 TDAS 保持为唯一端到端质量北极星

对 answerable 问题，每个 `(system, condition, question, repeat)` 的 initial attempt：

```text
TDAS =
  1{required evidence ready}
× 1{initial terminal success}
× 1{Response-claim Correctness ≥ 0.8}
× 1{all critical claims covered}
× 1{Reference-claim Recall ≥ 0.8}
× 1{Gold-evidence Support = 1}
× 1{no critical contradiction}
× 1{no verified scope/version violation}
× citation_gate
```

`citation_gate`：

- citation-required 题要求 Required-claim Citation Coverage=1，且所有提交引用 locator valid、可解析、完整支持关联 claim；
- 非 citation-required 题无需主动引用，但伪造、错绑或越 scope 引用仍使 TDAS=0。

不可回答题独立判定：正确拒答/说明证据不足，理由符合 Gold，且不输出 unsupported fact 或伪造引用。

聚合：

```text
question_TDAS(q) = mean_r TDAS(q,r)
system_TDAS      = mean_q question_TDAS(q)
```

TDAS 是“可信任务是否完成”，不是任意多指标加权总分。

### 4.2 为什么不改用 supported-claim F1 或论文 aggregate

RAGChecker 的 overall F1、EnterpriseRAG 的 correctness×completeness、CRAG 的 truthfulness、FAB 的六维 Judge 和 CRUD-RAG 的 RAGQuestEval 都有各自用途，但不适合作为 MOI 的共同北极星：

- precision/recall 的调和平均允许关键遗漏被其他内容补偿；
- 不同任务对 hallucination、missing、citation 和 scope 的失败成本不同；
- 产品 timeout、解析失败和 citation 缺失很容易被条件分母排除；
- 加权分数会让高延迟/低成本与答案质量发生没有业务依据的补偿。

这些指标保留在对应诊断层或 dataset-native 表中，不进入 Native 总榜。

### 4.3 可选 SLO-TDAS

只有在运行前冻结阈值时，才可报告：

```text
SLO-TDAS = TDAS=1
           ∧ E2E latency ≤ frozen SLO
           ∧ billable cost ≤ frozen ceiling
```

不得看完结果后选择阈值。

## 5. 八层指标合同

### 5.1 L0：Protocol、Validity 与 Eligibility

| 必记项 | 输出 |
|---|---|
| System identity | vendor/product/version/deployment/tenant/region/license/egress |
| Condition | Quick Native / Frozen Optimized / replay / oracle / robustness / performance |
| Frozen config | parser、chunk、embedding、top-k、reranker、generator、prompt、budget、hash |
| Data identity | source/dataset/split/file/question/gold/freeze hash |
| Attempt ledger | planned/initial/retry/replacement/invalid/interrupted/not-started |
| Capability ledger | trace/rank/score/citation/token/cost/workflow export 是否可用 |
| Artifact integrity | raw/config/context/answer/judgement 路径与 SHA-256 |

主表必须先显示分母和资格，再显示质量分数。

### 5.2 L1：Corpus Journey 与 Searchable Readiness

| 指标 | 定义 |
|---|---|
| Accepted-file/page rate | accepted eligible files/pages ÷ manifest files/pages |
| Job terminal success | completed files/jobs ÷ submitted files/jobs；failed/timeout 单列 |
| Searchable-ready success | `processed ∧ indexed/embedded ∧ search-probe-pass` |
| Required-evidence ready | 每题至少一套完整 alternative evidence set 的所有 source 均 ready |
| Build latency | upload→parsed、parsed→indexed、upload→searchable 的 P50/P95 与 censored failures |
| Idempotent ingest | 同一 hash 重复提交不产生错误重复证据的 case pass rate |

UI/job 显示 completed 不是充分条件，必须通过 search probe。

### 5.3 L2：Evidence Survival 与 Provenance

这是 MOI v2 的关键新增层。

| 指标 | 定义/作用 |
|---|---|
| Gold Evidence Survival | Gold span/table/image/formula/bbox 在解析 artifact 中仍完整可识别的比例 |
| Critical Evidence Survival | critical claims 所需 evidence 的 survival，必须单列 |
| Provenance completeness | artifact/chunk→file/page/span/bbox/hash 映射完整率 |
| Candidate coverage | Gold region 是否进入检索候选池；防止把 detector miss 算成 ranker miss |
| Structure preservation | heading tree、reading order、table cell、formula/image linkage 的专项指标 |
| Duplicate/omission rate | 重复 block、空 chunk、缺页/缺块比例 |

Dataset-native parser 表保留：

- OmniDocBench：Text/Formula Edit、TEDS、CDM、reading-order error；
- READoc：text/heading/formula edit、vocabulary F1、tree similarity、TEDS、Kendall Tau。

这些分数只在 parser track 中比较；Native 主榜使用 evidence survival/provenance，因为它们与下游可信回答直接相关。

### 5.4 L3：Retrieval、Scope 与 Context Assembly

| 指标 | 定义/规则 |
|---|---|
| Evidence Recall@K | K 内命中的 Gold evidence items ÷ eligible items |
| Claim Recall@K | K 内至少命中一套支持证据的 Gold claims ÷ Gold claims |
| Complete Evidence-set Recall@K | K 内至少完整命中一个 alternative evidence set 的 required claims ÷ required claims |
| Critical Complete-set Recall@K | critical claims 的完整证据召回 |
| Page/Layout Recall@K | 严格按 MMDocIR official/adapted protocol 分表 |
| nDCG@K / MRR | 仅在真实 rank 和匹配 collection 的 graded/binary qrels 可用时计算 |
| Context Precision@K | returned chunks 中含 Gold claim/evidence 的 chunks ÷ returned chunks |
| Invalid Extra Rate | returned context 中非 gold、非 valid-alternative 的额外证据比例 |
| Scope violation | 使用 disabled/out-of-selected-file/version evidence 的 attempt rate/count |
| Context budget | returned/deduped tokens、order、truncation、K、candidate count |
| Trace completeness | trace-capable attempts 的 chunk→source lineage 必填字段完整率 |

对多跳题，普通 Hit@K 只说明“找到任意证据”，不能替代 complete evidence-set recall。

### 5.5 L4：Answer Correctness、Completeness 与 Grounding

| 指标 | 定义 |
|---|---|
| Response-claim Correctness | response factual claims 的 `correct=1 / partial=.5 / incorrect=0` 均值 |
| Reference-claim Recall | 完整覆盖的 scored Gold claims ÷ all scored Gold claims |
| Critical Claim Coverage | covered critical claims ÷ critical claims |
| Gold-evidence Support | 被至少一套完整冻结 evidence set 支持的 response claims ÷ response claims |
| Runtime-context Faithfulness | 被本次实际送入 generator 的 context 支持的 response claims ÷ response claims；trace-only |
| Context Utilization | 已召回的 Gold claims/evidence 中实际进入回答的比例 |
| Critical contradiction | 与 critical Gold/active version 冲突的 claim count/rate |
| Strict Unanswerable Success | 正确拒答 + 理由正确 + 无 unsupported fact/citation |
| False Refusal | answerable attempt 中错误拒答比例 |
| Invalid Extra Claims | 正确答案之外不必要、错误或越范围的 factual claims |

Gold support 与 runtime faithfulness 必须分列：系统可能忠实复述错误/过期 context，也可能凭模型内知识答对却没有使用 corpus evidence。

RAGAS/ARES 的 relevance/faithfulness 只作为 regression；RAGTruth 的 span labels 用于 Judge 校准；RAGChecker 的 claim decomposition 用作实现骨架。

### 5.6 L5：Citation 与 User-verifiable Evidence

| 指标 | 定义 |
|---|---|
| Locator/Resolvability Validity | citation 可解析到冻结 file/page/span/bbox/hash 的比例 |
| Citation Entailment Precision | submitted citations 中完整支持关联 claim 的比例 |
| Required-claim Citation Coverage | citation-required claims 中有 valid+entailing citation 的比例 |
| Minimal Evidence Precision | 引用是否包含支持 claim 所需的最小充分区域，避免整页泛引 |
| Fabricated Citation Count | 不存在、不可解析或伪造 locator |
| Out-of-scope/Version Citation | 指向禁用文件、错误版本、过期或删除证据的 count/rate |

零 citation 时：locator/precision=`N/A/NO_SUBMITTED_CITATION`；citation-required coverage=0，TDAS=0。不能把空集 precision=1 展示为优势。

### 5.7 L6：Reliability、Performance 与 Cost

| 指标 | 口径 |
|---|---|
| First-pass availability | 合规 terminal initial responses ÷ all initial units |
| Final availability | initial 或冻结 retry 内成功的 units ÷ all initial units |
| Retry recovery | 仅诊断，不替换 initial failure |
| Repeat stability | 3/3 TDAS pass、mixed flip、0/3 pass；component dispersion |
| Latency | upload/build、retrieval、TTFT、completion、E2E 的 P50/P95；性能轨加 P99 |
| Throughput | fixed offered load 下 completed requests/s 与 **trusted answers/s** |
| Quality under load | 每档并发的 TDAS、complete-set recall、error、latency 联合输出 |
| Resource | CPU/GPU、RAM/VRAM、I/O、index size/storage amplification |
| Cost/attempt | initial billable cost ÷ all initial attempts；retry/build/judge 单列 |
| Cost/trusted answer | initial total cost ÷ TDAS-successful initial attempts |

terminal latency 分位数必须与 timeout/error/censored count 并列；不能只统计成功样本。

### 5.8 L7：Lifecycle、Workflow 与 Operability

这是 MOI 相比大多数论文 benchmark 的第二个关键新增层，设计主要吸收 CRUD-RAG、CRAG 和 MOI 产品能力。

| 指标 | 定义/场景 |
|---|---|
| Update propagation delay | 新版本提交到旧答案不再出现、新答案可检索的 elapsed time |
| Stale-answer rate | 更新后仍回答 superseded fact 的 question rate |
| Delete leakage | 删除/禁用后，旧 evidence 仍出现在 retrieval/answer/citation 的 rate |
| Version disambiguation | 面对 active/archived/conflicting versions 时选择正确版本的 rate |
| Incremental-index correctness | 更新后未误伤未修改 evidence 的 regression pass rate |
| Workflow reproducibility | export/reimport 后 topology/config/hash 等价的 case rate |
| Job/status accuracy | UI/API 状态与实际 artifact/searchability 一致率 |
| Recoverability | 自动恢复/runbook 一步/需重建/不可恢复的 incident 分布 |
| Active human minutes | 预注册角色实际操作时间；与 wall-clock 分列 |
| Interventions/config errors | 配置、恢复、重建和人为修复 count/taxonomy |
| Time-to-First-Trusted-Answer | 首个管理动作到首个 TDAS=1 的 journey 时间 |

L7 不折入 Native TDAS；其中 scope/version/delete violation 影响具体 attempt 的 TDAS gate。

## 6. Controlled Diagnostic Matrix

单一 Native 分数无法区分 parser、retriever 和 generator。新版吸收 MIRAGE、MultiHop-RAG、FAB、RAGChecker 的设计，为同一 Gold 构造以下条件：

| Condition | 平台参与 | Context | 回答什么问题 |
|---|---|---|---|
| Quick Native | 是 | 平台真实 | 默认产品体验 |
| Frozen Optimized Native | 是 | 平台真实 | 等预算调优上限 |
| Retrieved-context replay | 上游平台 | 各平台真实 context + 统一 generator | 上游 context 差异影响多少 |
| Shared Gold Context | 否 | Gold evidence + 统一 generator | reader/oracle ceiling |
| Base / No-context | 否 | 空 | 模型内知识和污染基线 |
| Oracle | 否 | 最小充分 Gold set | 正确 context 是否被接受 |
| Mixed | 否 | Gold + 相似噪声 | 是否被噪声干扰 |
| Contradictory/Versioned | 否或 Native | Gold + 过期/冲突证据 | 是否正确消歧、引用 active version |
| Missing-evidence | 否或 Native | 移除关键证据 | 是否安全拒答 |

MIRAGE 四类指标可改造成 claim/TDAS 版本：

- `Noise Vulnerability`：Oracle TDAS=1、Mixed TDAS=0；
- `Context Acceptability`：Oracle=1、Mixed=1；
- `Context Insensitivity`：Base=0、Oracle=0；
- `Context Misinterpretation`：Base=1、Oracle=0。

对多证据题，Oracle 必须提供一套完整 alternative evidence set，而不是单一 chunk。

## 7. Gold v2：围绕 evidence chain 建模

### 7.1 核心结构

每题至少保存：

```text
question_id / family_id / analysis_cluster_id
answerability / negative_type / negative_reason
scored claims / critical claims / acceptable answer variants
alternative evidence sets
source_id / source_type / document_version
page / span / bbox / table-cell / image-region / hashes
selected-file scope / active version / valid_from / valid_to
conflict set / supersedes / deleted_at
slice tags / rights / egress / gold_version / freeze_id
```

### 7.2 Evidence-set 逻辑

```text
同一 claim 的多个 alternative evidence sets：OR
一个 evidence set 内的多个 evidence items：AND
question 的 critical claims：全部必须覆盖
```

这同时支持：

- ALCE 的逐 claim 引用；
- MultiHop-RAG 的多证据链；
- EnterpriseRAG 的 atomic facts/valid alternatives；
- MMDocIR/MMDocRAG 的 page/layout/text/image evidence；
- NQ 的多个可接受答案和 NULL；
- CRUD-RAG/CRAG 的时间与版本状态。

### 7.3 Correction-aware 但不可静默修 Gold

吸收 EnterpriseRAG 的 correction-aware gold：运行中发现新的有效证据时，可以提交 Gold 修订候选，但必须：

1. 保留原 Gold；
2. 双审或预注册 Judge 多数决；
3. 新建 `gold_version`；
4. 记录受影响题目和系统；
5. 对正式比较统一重跑/重判。

不能因为某个系统给出意外答案就直接把它加入 Gold。

## 8. Dataset-native、MOI-unified 与 Product-native 三套输出

每次公开 benchmark 运行必须区分：

### A. Dataset-native official/adapted

保留原论文指标、单位、K、Judge、数据版本和 scorer commit，例如：

- OmniDocBench TextEdit/TEDS/CDM；
- MMDocIR Page/Layout Recall；
- ViDoRe nDCG@5；
- DocBench binary correctness；
- MMDocRAG quote P/R/F1 与官方 Judge；
- RGB/CRAG/CRUD-RAG 的任务原生分数。

协议变化则标 `ADAPTED_PROTOCOL`。

### B. MOI-unified

所有数据集尽量映射到共同 schema：

```text
attempt ledger + readiness + claims + evidence sets + citations
+ TDAS + reliability + latency + errors + hashes
```

### C. Product-native capability

仅报告真实产品能力：

- workflow/job/retry/artifact；
- selected-file/disabled chunk；
- source/page mapping；
- update/delete/version；
- operability/cost/observability。

三套表互相链接，但不能混排行。

## 9. 统计、Judge 与缺失值

### 9.1 聚合

1. initial attempt 是事实主分母；retry 不覆盖初次。
2. repeats 先在 question 内取均值，再 question macro-average。
3. claim/citation 同时报 attempt 内 rate、micro raw counts 和 question macro；不把同题 claims 当独立样本生成 CI。
4. formal paired comparison 只在同 freeze、同 condition、同题集上进行，以 `analysis_cluster_id` 同步 cluster bootstrap 10,000 次。
5. 切片必须报 count/denominator；小切片只作探索性诊断。

### 9.2 Judge quality

每个 Judge 保存：

```text
model/version/prompt/temperature/max output/rubric
calibration set/human labels/QWK or per-label P/R/F1
blind mapping/disagreement/adjudication
```

- RAGTruth 用于 unsupported/hallucination span 校准；
- ALCE 用于 citation entailment 校准；
- RAGBench/RAGChecker 用于 claim/context 归因回归；
- ARES/PPI 只有在具备足量领域人工标签后启用。

Judge 或 rubric 改版必须新建 metric version，不可与旧分数直接拼接。

### 9.3 Zero、N/A、invalid

| 情况 | 处理 |
|---|---|
| timeout/空答/product error | initial 分母内，TDAS/适用质量=0 |
| 无 citation 且题目要求 citation | coverage=0；locator/precision=N/A |
| 无真实 retrieval trace | retrieval/runtime faithfulness=N/A/TRACE_UNAVAILABLE |
| 产品不支持必需 Native capability | capability gap；相关 Gate 失败，不获益 |
| benchmark-side schema/Gold/脚本缺陷 | invalid；保留原 row 和 replacement |
| interrupted run | planned/completed/interrupted 全量披露，不从已完成子集伪造全量分数 |

## 10. 当前项目的落地顺序

### Phase M0：先把已有结果装进统一账本

不新增大规模运行，先完成：

1. 版本化 `metric-registry.yaml`；
2. `run-manifest.json`、`attempts.jsonl`、`claims.jsonl`、`citations.jsonl`、`metrics.json` 统一 schema；
3. 为 WikiEval、MMDocIR、DocBench、OmniDocBench、竞品 runner 写只读 converter；
4. 把现有 interrupted、missing latency、trace unavailable 和 adapted protocol 明确入账；
5. 用现有 artifact 重算能算的 numerator/denominator。

完成标准：任何主表单元格都能追到 raw row 和 hash。

### Phase M1：最小可比闭环

在同一 50 题/文档 freeze 上先完成 MOI + Dify：

- 相同 planned initial 分母；
- Native readiness 和 terminal disposition；
- Page/Evidence Recall@K（可观察时）；
- claim correctness/recall/Gold support；
- citation locator/coverage/entailment；
- E2E latency P50/P95 + timeout/error；
- 两次或三次 repeat stability；
- Base/Oracle/Mixed 诊断子集。

FastGPT/MaxKB/RAGFlow 未通过相同门禁前，只保留 capability/blocker 行，不进入完整对比表。

### Phase M2：自建中文企业 Gold

公共论文主要贡献 schema，不承担正式主榜。自建集优先覆盖：

- PDF/Word/Markdown/表格/图片混合；
- 中文、内部缩写、中英混合实体；
- single/multi-document、cross-page、table/image、multi-hop；
- completeness、conflict、version、info-not-found；
- selected-file/disabled chunk；
- update/delete/freshness；
- citation-required 与不可回答。

先做 200-document/1,000-question 设计中的 pilot，Gold 必须有 claims、evidence sets、page/span/bbox/hash、版本和 rights/egress。

### Phase M3：Formal 与独立性能轨

- Quick Native 作为默认体验主轨；
- Frozen Optimized 只有等预算时启用；
- question-level paired TDAS difference + CI；
- performance 在质量 Gate 通过后独立运行；
- 输出 trusted answers/s 和 cost/trusted answer，而不只 QPS/cost/request。

## 11. 当前可实现性清单

| 状态 | 当前可做 |
|---|---|
| 立即可做 | run/config hash、file/job/readiness、OmniDocBench official parser、MMDocIR page/layout、WikiEval/RAGAS、部分 MOI latency、Dify page/native disposition |
| 需要 schema/converter | 统一 attempt denominator、TDAS、claim judgement、citation judgement、repeat contingency、aggregate long-table |
| 需要 tenant/API 验证 | MOI 真实 rank/score/context trace、稳定 citation/source mapping、token usage |
| 需要商业/环境补齐 | 跨平台 cost、相同 latency boundary、FastGPT/MaxKB/RAGFlow 完整 Native run |
| 暂缓 | ARES/PPI、全量 22 数据集、动态 Web/KG、FRAMES agentic、多租户安全/HA |

## 12. 最终报告应回答的五句话

任何一轮 MOI RAG Bench 的执行摘要都应能用有分母的证据回答：

1. **能不能用**：TDAS、initial availability、3/3 pass 是多少？
2. **哪里掉了**：readiness、evidence survival、complete-set retrieval、answer、citation 哪层损失最大？
3. **为什么掉**：解析遗漏、scope/version、retrieval、context noise、reader、citation 还是 product/API？
4. **是否稳定且值得运行**：P50/P95、timeout、trusted answers/s、cost/trusted answer、人工分钟是多少？
5. **MOI 的产品特色是否真的有效**：多模态 artifact、source mapping、workflow、文件范围和增删改是否通过独立 capability/lifecycle tests？

如果只能回答“LLM Judge 是 3.98/5”或“Recall@5 是 75.83%”，这仍然只是一个组件结果，不是 MOI 产品 benchmark。

## 13. 论文索引（本地）

### Canonical 论文与阅读笔记

- [RGB reading note](../../refs/papers/notes/01-RGB-AAAI-2024-reading-notes.md)
- [ALCE reading note](../../refs/papers/notes/02-ALCE-EMNLP-2023-reading-notes.md)
- [RAGTruth reading note](../../refs/papers/notes/03-RAGTruth-ACL-2024-reading-notes.md)
- [RAGBench reading note](../../refs/papers/notes/04-RAGBench-arXiv-2024-reading-notes.md)
- [MultiHop-RAG reading note](../../refs/papers/notes/05-MultiHop-RAG-COLM-2024-reading-notes.md)
- [OmniDocBench reading note](../../refs/papers/notes/06-OmniDocBench-CVPR-2025-reading-notes.md)
- [READoc reading note](../../refs/papers/notes/07-READoc-Findings-ACL-2025-reading-notes.md)
- [MMDocIR reading note](../../refs/papers/notes/08-MMDocIR-EMNLP-2025-reading-notes.md)
- [ViDoRe V2 reading note](../../refs/papers/notes/09-ViDoRe-V2-arXiv-2025-reading-notes.md)
- [DocBench reading note](../../refs/papers/notes/10-DocBench-KnowledgeNLP-2025-reading-notes.md)
- [MMDocRAG reading note](../../refs/papers/notes/11-MMDocRAG-NeurIPS-2025-reading-notes.md)
- [EnterpriseRAG-Bench reading note](../../refs/papers/notes/12-EnterpriseRAG-Bench-arXiv-2026-reading-notes.md)
- [FAB-Bench reading note](../../refs/papers/notes/13-FAB-Bench-arXiv-2026-reading-notes.md)
- [MIRAGE reading note](../../refs/papers/notes/14-MIRAGE-arXiv-2025-reading-notes.md)
- [CMRC2018 reading note](../../refs/papers/notes/15-CMRC2018-EMNLP-IJCNLP-2019-reading-notes.md)
- [Natural Questions reading note](../../refs/papers/notes/16-Natural-Questions-TACL-2019-reading-notes.md)
- [RAGAS reading note](../../refs/papers/notes/2024.eacl-demo.16-reading-notes.md)

### 扩展包中无独立 reading note 的论文

- [CRAG PDF](../../refs/papers/o1/06-crag-neurips-2024.pdf)
- [FRAMES PDF](../../refs/papers/o1/07-frames-naacl-2025.pdf)
- [RAGChecker PDF](../../refs/papers/o1/08-ragchecker-neurips-2024.pdf)
- [ARES PDF](../../refs/papers/o1/09-ares-naacl-2024.pdf)
- [CRUD-RAG PDF](../../refs/papers/o1/10-crud-rag-tois-2024.pdf)

### 项目证据

- [MOI RAG Benchmark v1.0](../drafts/v1.0.md)
- [Golden 与指标规范](../todo/golden-and-metrics-spec-v0.4.md)
- [MOI 三阶段计划](../todo/moi-rag-benchmark-three-stage-plan-v1.md)
- [MOI 产品 benchmark scope](../research/moi-rag-platform-benchmark-scope.md)
- [当前进度证据](../../reports/rag-benchmark-progress-2026-08-10/source-notes.md)
- [当前结果](<../../results/MOI RAG 0807.md>)
