# MOI 平台 RAG 能力三阶段 Benchmark 计划 v1

> 日期：2026-08-03  
> 状态：Draft for execution  
> 目标：先用公开 benchmark 建立外部可比基线，再构建有完整权利和 Gold lineage 的 MOI 新数据集，最后用该数据集对 MOI、Dify、FastGPT 做公平的 Native 产品横评。

## 0. 执行摘要

整个项目分为三个 Stage：

| Stage | 要回答的问题 | 主数据 | 被测系统 | 主要产出 |
|---|---|---|---|---|
| **1. Public Benchmark Baseline** | MOI 在社区公开 benchmark 上处于什么水平？不同组件的主要短板在哪里？ | 已下载的公开解析、检索、端到端、回答/引用数据集 | MOI | 每个数据集的论文同口径结果 + MOI 统一指标结果 + adapter/限制报告 |
| **2. MOI Benchmark Dataset v1** | 在符合真实产品场景、可商用、fresh 且有严谨 Gold 的新数据上，MOI 整体能力如何？ | 新建的 200 文档 / 1,000 问题数据集；Stage 2 只使用 dev 和 pilot split | MOI | 数据集 v1、Gold、rubric、MOI-only pilot、错误地图和产品改进清单 |
| **3. Competitive Formal Evaluation** | 在相同原始文件、问题、预算和运行协议下，MOI 与竞品差异有多大？ | Stage 2 数据集的 sealed formal split | MOI、Dify、FastGPT；RAGFlow 作为可选后续 | 盲判横评、paired difference/CI、产品能力 scorecard、可审计报告 |

三个 Stage 使用同一套内部数据 schema 和运行 ledger，但指标分为两个独立命名空间：

1. **Dataset-native metrics**：严格使用论文/官方代码的输入、split、metric、prompt、Judge 和聚合方式，目的是与论文及社区结果可比。
2. **MOI unified metrics**：使用现有 v0.3/v0.4 计划定义的 readiness、retrieval、answer、citation、reliability、operability 和 TDAS，目的是跨数据集、跨产品保持一致。

两套指标不得平均、改名或合成一个 overall score。公开论文分数回答“是否复现了该 benchmark 协议”，MOI 统一分数回答“产品链路是否满足我们的验收标准”。

## 1. 全局评测合同

### 1.1 系统边界

- MOI Native 结果只能来自 MOI 原生 `upload → parse/index → searchable → query → answer/citation` 路径。
- MOI 预处理后导出到 Dify、外接统一 retriever 或外部 agent 的结果不得记为 MOI Native。
- Stage 1 只测 MOI；Stage 3 的 comparator 固定为 Dify、FastGPT，RAGFlow 等候选只能在主实验冻结前加入。
- Stage 3 主轨为 **Quick-start Native**：每个产品使用官方推荐默认路径。
- 可选第二轨为 **Frozen Optimized Native**：只在 dev split 调优，并给所有产品相同的试验次数、人工时间、wall-clock、vendor help 和允许搜索空间。
- Controlled Generation 只能作为诊断轨；不能替代 Native 结果，也不能和 Native 混报。

### 1.2 数据和许可边界

- 公司内部商业产品研发和评测按保守口径视为商业使用。
- 公开 benchmark 必须先经过 dataset/config/field 级 allowlist；NC、research-only 或来源权利不清晰的数据保存在隔离 research lane，不进入商业 CI、产品制品或公开样例。
- Stage 2 新数据集只能使用公司自有、取得明确授权或完全合成的文档。公开 benchmark 只用于学习任务设计和 schema，不复制受限原文、问题、答案或 evidence。
- 每份文档保存 `source_owner, license, allowed_use, redistribution, training_allowed, acquired_at, reviewer`；任何一项不明均不得进入 formal split。

### 1.3 冻结、运行和失败合同

- 每个 Stage 保存 dataset revision、文件 SHA-256、代码 commit、产品版本、tenant/region、模型、prompt、chunking、embedding、top-k、reranker、时间和费用。
- 每次 query 使用 fresh session；planned request 第一次发出即为 initial attempt。
- timeout、空响应、解析失败、产品错误和 citation 缺失全部保留在 initial 分母中；retry 只评估 recoverability，不能覆盖 initial 结果。
- 只有预注册的 dataset/Gold defect 才能对所有系统统一标 `question_invalid`。不能根据某个系统答得不好而删题。
- retrieved chunks/rank/qrels 无法导出时，对应指标写 `N/A: TRACE_UNAVAILABLE`；不得从最终答案或引用反推 retrieval trace。

## 2. Stage 1：公开数据集能力基线

### 2.1 Stage 目标

1. 验证 MOI 能否接入社区常用的 PDF、页面图像、query/qrels 和 processed-context benchmark。
2. 用官方脚本生成论文同口径结果，确保可以和论文表格或社区 leaderboard 对照。
3. 对同一批 MOI 输出再计算内部统一指标，建立后续 Stage 2/3 可复用的 evaluator 和错误分类。
4. 区分解析、检索、reader、引用和端到端失败，避免把所有问题归结为“回答不准”。

### 2.2 数据集和评测方式

#### A. 解析层

| 数据集 | 使用数据 | 论文/官方同口径指标 | 同时保存的 MOI 指标 | 执行优先级 |
|---|---|---|---|---|
| **OmniDocBench** | 完整公开页面；先跑 200 页分层 smoke，通过后跑完整集 | text Edit Distance；table TEDS/Edit Distance；formula CDM/Edit Distance；reading-order Edit Distance；官方 Overall | accepted-page rate、关键 block preservation、表格/公式/标题定位、parse latency、失败类型 | **P0**，PDF parser 主基线 |
| **READoc** | 先跑 arXiv/GitHub 各 50 PDF；资源允许再跑论文核心 2,233 文档 | text EDS/F1、heading EDS/TEDS、inline/outline formula EDS、table EDS/TEDS、order Kendall tau/Spearman | Gold evidence preservation、Markdown 结构完整性、页/章节 provenance、build time | **P1**，真实 PDF-to-Markdown 补充 |

只有 MOI 能导出可对应官方 schema 的解析结果时，才计算论文同口径 parser metric。若产品只暴露最终回答，Stage 1 解析轨应标记 unavailable，而不是使用 OCR 文本或回答倒推解析质量。

#### B. 检索层

| 数据集 | 使用数据 | 论文/官方同口径指标 | 同时保存的 MOI 指标 | 执行优先级 |
|---|---|---|---|---|
| **MMDocIR Evaluation** | 本地 evaluation set；不使用未下载的训练集和模型权重 | page-level Recall@K、layout-level Recall@K，K 与固定官方脚本一致 | Recall@1/5/10、nDCG@10、complete evidence-set recall、index/search latency、trace completeness | **P0**，长文档 page/layout retrieval 主集 |
| **ViDoRe V2** | ESG、human-labeled ESG、biomedical、economics 四子集 | nDCG@5/10、Recall@5/10，按子集和 macro 报告 | 索引耗时、query latency、页面召回、语言/领域切片 | **P0**，视觉页面 retrieval |
| **MultiHop-RAG** | 2,556 queries + 609 documents；仅在字段级许可获批后运行 | 官方 Hits@K 与 QA Accuracy，保留官方代码版本 | evidence Recall@K、**all-evidence success**、complete evidence-set recall、answer correctness、null success | **P1**，跨文档多跳检索 |

MultiHop-RAG 官方 Hits@K 是 any-hit 口径，不能代表多跳证据已经找齐。因此官方 Hits@K 必须保留，但产品结论优先看 all-evidence success。

#### C. 原始文档到回答的端到端层

| 数据集 | 使用数据 | 论文/官方同口径指标 | 同时保存的 MOI 指标 | 执行优先级 |
|---|---|---|---|---|
| **DocBench** | 229 PDF、1,102 QA；先跑 20 PDF / 50 QA smoke | 官方 LLM Judge 二元 Correctness（0/1），冻结原 prompt、Judge 模型和版本 | TDAS、claim correctness、Reference-claim Recall、Gold-evidence Support、citation coverage、端到端 latency | **P0**，最小可跑的 PDF-to-answer 主集 |
| **MMDocRAG** | 4,055 专家 QA；先跑 200 QA 的 text/table/image/cross-modal 分层样本 | quote selection Precision/Recall/F1（text/image/overall）、BLEU、ROUGE-L，以及官方 LLM Judge 的 Fluency、Citation Quality、Text-Image Coherence、Reasoning Logic、Factuality | multimodal evidence recall、critical-claim coverage、citation locator/support、TDAS、按模态失败归因 | **P1**，多模态端到端主集 |
| **Double-Bench** | 当前 corpus 未下载 | 不运行、不进入分母 | 无 | **P3 暂缓**；机器、预算、许可通过后另立项目 |

#### D. Reader、引用、鲁棒性和 Judge 校准层

| 数据集 | 使用方式 | 论文/官方同口径指标 | MOI 中的正确角色 | 许可状态 |
|---|---|---|---|---|
| **RAGBench** | 优先 TechQA、EManual；其他 config 逐项审计 | TRACe Relevance、Utilization、Completeness、Adherence | evaluator 回归、rubric 校准、processed-context reader 诊断；不能作为原始 PDF 主榜 | 黄/红；`msmarco` 禁用 |
| **RGB** | 若获得商业授权，仅在隔离轨运行 refined split | noise accuracy/rejection rate、negative rejection、information integration、counterfactual robustness 的官方口径 | 近失配、冲突证据、不可回答题设计参考 | 红；未获授权前不运行产品测试 |
| **ALCE** | 若获得授权，复现 ASQA/QAMPARI/ELI5 citation protocol | correctness、citation recall、citation precision | claim-to-citation evaluator 参考；不作为 MOI PDF 解析分数 | 红；混合来源整包默认禁用 |
| **RAGTruth** | 只用于候选 Judge 的离线校准，不作为 MOI RAG 端到端能力 | response/span-level hallucination detection 指标 | 检查自动 Judge 能否识别 baseless/contradictory span | 红；未获授权前不进入商业测试 |

### 2.3 双指标输出合同

每个公开 benchmark 产生两份不可混淆的结果：

```text
runs/stage1/<benchmark>/<run_id>/
├── official/
│   ├── predictions.<official-format>
│   ├── metrics.json
│   └── protocol.json
├── moi-unified/
│   ├── attempts.jsonl
│   ├── claims.jsonl
│   ├── citations.jsonl
│   ├── metrics.json
│   └── error-taxonomy.json
└── artifacts/
    ├── manifest.json
    ├── logs/
    └── hashes.txt
```

`official/protocol.json` 至少记录论文、数据 revision、官方代码 commit、split、prompt、Judge、指标单位和聚合方式。若任一关键项不同，结果必须标 `ADAPTED_PROTOCOL`，不能声称严格复现论文。

### 2.4 Stage 1 运行顺序与 Gate

1. **S1-G0 Legal/Data Gate**：逐数据集完成 allowlist；红色数据未获授权不得上传 MOI。
2. **S1-G1 Adapter Smoke**：每个 P0 数据集跑 10–50 样本，验证上传、ID 映射、输出 schema 和官方 evaluator。
3. **S1-G2 Core Run**：完整跑 OmniDocBench、MMDocIR、ViDoRe V2、DocBench；MMDocRAG 先跑 200 QA，再按成本决定全量。
4. **S1-G3 Diagnostic Run**：运行获批的 RAGBench configs 和 MultiHop-RAG；ALCE/RGB/RAGTruth 只在授权通过后运行。
5. **S1-G4 Reproducibility**：随机抽 5% 样本重跑；官方指标可从 raw artifact 重算；任何不可复现结果不进入报告。

### 2.5 Stage 1 交付物

- `public-benchmark-manifest.json`：数据版本、许可状态、任务、样本量、本地路径。
- 每个 benchmark 的 adapter、runbook 和 official scorer wrapper。
- 论文同口径 scorecard；与论文数字并列时明确 model/system/protocol 差异，不做虚假 SOTA 声明。
- MOI unified scorecard：Readiness、Retrieval、Answer、Citation、Reliability、Operability。
- top failure taxonomy 和 Stage 2 新数据集 coverage gap。

预计周期：**3–5 周**，其中许可审核与 MOI 可观测性/API 是关键路径。

## 3. Stage 2：构造 MOI Benchmark Dataset v1，并评估 MOI 整体能力

### 3.1 为什么不能直接拿 Stage 1 数据做正式主榜

公开集存在训练污染、领域偏移、第三方版权和输入起点不一致问题。Stage 2 要构造一个从原始文件开始、能覆盖真实企业知识库、带页码/bbox/span/hash 证据链、可合法用于内部商业测试和后续发布聚合结果的新数据集。

Stage 2 会对 MOI 做一次 pilot，但只使用 `dev + pilot`。`formal` split 始终 sealed，留给 Stage 3。否则根据 Stage 2 结果修复 MOI 后再在同一批题上与竞品比较，会产生数据泄漏和不公平优势。

### 3.2 数据集 v1 固定规模

**文档：200 份原始 PDF**

| 文档主类型 | 数量 | 主要能力 |
|---|---:|---|
| 产品手册、技术文档 | 50 | 操作步骤、故障诊断、条件与例外 |
| SOP、政策、制度 | 35 | 条款定位、版本与适用范围 |
| 报告、财务/运营表格 | 35 | 表格解析、计算、多页证据 |
| 合同、规格书、招投标材料 | 25 | 长文档、精确引用、否定与例外 |
| 扫描件、表单、低质量 OCR | 25 | OCR、键值、印章/手写干扰 |
| Slides、宣传册、图文混排 | 20 | 图片、图表、版式语义 |
| Changelog、版本化文档 | 10 | 新旧版本冲突、freshness |
| **合计** | **200** | |

语言配额：中文 90、英文 70、中英混合 40。至少 60 份文档为新创作或此前不公开的 fresh/private 文档；所有 split 按 document family/near-duplicate component 隔离。

**问题：1,000 道**

| 互斥主类型 | 数量 |
|---|---:|
| 单文档、单证据 | 250 |
| 单文档、多证据 | 170 |
| 跨文档综合/多跳 | 180 |
| 表格与数值计算 | 120 |
| 图片、图表、版面定位 | 80 |
| 时间、版本、冲突处理 | 80 |
| 不可回答/证据不足 | 120 |
| **合计** | **1,000** |

正交标签包括：`language, domain, layout, scan_quality, answerability, citation_required, fresh_control, evidence_modality, hop_count, numerical_reasoning, version_conflict, distractor_type, sensitivity`。

### 3.3 Split 合同

| Split | 文档 | 问题 | 用途 | 可见性 |
|---|---:|---:|---|---|
| **dev** | 40 | 200 | adapter、prompt/rubric、产品调优 | 工程和评测团队可见 |
| **pilot** | 40 | 200 | Stage 2 MOI-only 整体能力评估 | 运行前对操作员隐藏问题/Gold；运行后可用于修复 |
| **formal** | 120 | 600 | Stage 3 MOI vs comparator 正式横评 | Stage 3 freeze 前始终 sealed |

三个 split 不共享 document family、模板、近重复内容或由同一基础事实改写的问题。Stage 2 不能访问 formal 的问题、答案和证据位置。

### 3.4 Gold schema

每道题至少保存：

```text
question_id
question_family_id
analysis_cluster_id
split
question
answerability
negative_reason
scored_reference_claims[]
critical_required_claims[]
evidence_sets[][]
  └── document_id, page, bbox/span, section, exact_hash
citation_required
accepted_answer_variants[]
forbidden_claims[]
coverage_tags[]
author_id, reviewer_ids[], adjudication
gold_version, freeze_hash
```

- answerable 题必须有非空 reference claims，每个 claim 至少有一套完整 evidence set。
- unanswerable 题必须有明确 `negative_reason`，并记录最接近但仍不足的 hard-negative 文档。
- 表格/图片题保存 bbox 或稳定的区域 locator；文本题至少保存 page + span/hash。
- Gold 不能根据 MOI 或竞品输出回写。任何修订都创建新版本并保留 lineage。

### 3.5 标注与质量控制

1. 文档先通过权利、敏感信息和外发审核，再进入 authoring pool。
2. Annotator A 编题、参考 claims 和 evidence；Annotator B 独立核验 answerability、证据完整性和可判分性。
3. formal split 的所有题双审；dev/pilot 至少 30% 双审，高风险类型全量双审。
4. 分歧由第三人 adjudication；formal Gold 有效率目标 ≥95%，critical error=0。
5. 运行前做 near-duplicate、答案泄漏、空证据、跨 split family 和 prompt injection 扫描。
6. 保存 reviewer agreement；claim-level correctness/support ordinal labels 的 QWK 目标 ≥0.60。

### 3.6 Stage 2 的 MOI-only 评测

Stage 2 先在 dev 完成适配和有限调优，再冻结 MOI 配置，在 pilot 的 200 题上每题运行 2 次 initial repeat。

主指标沿用 v0.4：

- **Readiness**：accepted file/page、processed/indexed/searchable-ready、Gold evidence preservation、build time。
- **Retrieval**：Evidence Recall@K、complete evidence-set recall、context precision；仅在真实 trace/rank/qrels 可用时计算。
- **Answer**：Correctness、critical-claim coverage、Reference-claim Recall、Gold-evidence Support、unanswerable success、false refusal、critical contradiction。
- **Citation**：locator/resolvability、citation entailment precision、answer-claim citation coverage、伪造/越界引用。
- **Reliability**：initial availability、timeout/error、retry recovery、repeat pass/fail 翻转、P50/P95 latency。
- **Operability**：Time-to-First-Searchable-Corpus、Time-to-First-Trusted-Answer、人工分钟、干预次数、配置错误、诊断质量。

每个 answerable attempt 的 TDAS gate 沿用现有计划：Correctness ≥0.8、critical claims 全覆盖、Reference-claim Recall ≥0.8、Gold-evidence Support=1；citation-required 题 coverage=1 且所有引用可解析并完整支持关联 claim。unanswerable attempt 必须正确拒答且无编造事实/引用。

Stage 2 不使用一个加权总分表示“整体能力”。整体结论由 TDAS 宏平均和六层 scorecard 共同组成；每个失败必须归因到 ingest、parse、retrieval、reader、citation 或 product/API。

### 3.7 Stage 2 Gate 和交付物

| Gate | 通过条件 |
|---|---|
| **S2-G0 Rights** | 200 文档全部有明确权利和允许用途；formal 可用于计划中的内部横评和聚合发布 |
| **S2-G1 Coverage** | 文档、语言、问题类型和 fresh 配额满足；split 无 family 泄漏 |
| **S2-G2 Gold** | formal 全量双审；Gold validity ≥95%；critical error=0；freeze hash 完成 |
| **S2-G3 Pilot** | MOI pilot 400 initial attempts 完整；raw artifacts、判分和 N/A reason 可重算 |
| **S2-G4 Readiness for Comparison** | formal 保持 sealed；竞品 adapter、统一 ledger 和盲判流程在 dev 上通过 smoke |

交付物：`dataset-v1/`、datasheet、许可 manifest、dev/pilot/formal freeze、Gold/rubric、MOI pilot report、错误地图、Stage 3 preregistration。

预计周期：**6–8 周**。数据权利、formal 双审和证据定位是主要成本，不能用自动生成后不复核的方式压缩。

## 4. Stage 3：在新数据集上重新评估并与竞品对比

### 4.1 被测产品和条件

主比较系统：

- MOI
- Dify
- FastGPT

RAGFlow 或其他产品只有在 formal freeze 前满足身份、部署、授权、自动化和 evidence capture 要求时才能加入。正式运行后不得新增系统再重复查看 formal Gold。

每个产品至少有 **Quick-start Native** 条件。若资源允许，再增加 **Frozen Optimized Native**，但两种条件分表报告，不把 optimized 结果当默认用户体验。

### 4.2 公平性合同

- 所有产品从完全相同的 120 份 formal 原始 PDF 开始，不共享某一产品的解析结果、chunks 或 embedding。
- 使用语义等价 instruction、同一 formal question、同一时间窗口、相同最大 context/输出预算和 fresh session。
- Quick-start 使用官方推荐默认；无法对齐的隐藏默认参数必须记录，不强行声称组件完全受控。
- Optimized 条件给每个产品相同的 dev trials、active person-hours、wall-clock、配置动作数和 vendor support budget。
- 操作员不可能对产品身份盲，但 Judge/reviewer 看到的输出必须去除 system ID、随机排序。
- formal 每题每系统每条件运行 **3 次 initial repeat**；顺序按预注册 rotation/Latin-square 分散时间和服务波动。

若只有 Quick-start 三系统，主分母为：

```text
600 formal questions × 3 systems × 3 repeats = 5,400 initial attempts
```

任何 retry 都不替换这 5,400 次 initial attempt。

### 4.3 Stage 3 指标

所有系统统一报告 Stage 2 的六层指标和 TDAS，不使用产品自带“满意度”作为主指标：

1. **Native readiness/parsing**：文件/页成功率、evidence preservation、建库时间。
2. **Retrieval**：真实 trace 可用时报告 Recall@K、complete evidence-set recall、context precision；不可用系统明确 N/A。
3. **Answer**：Correctness、Reference-claim Recall、Gold-evidence Support、unanswerable success、false refusal。
4. **Citation**：locator validity、entailment precision、claim coverage、伪造引用数。
5. **End-to-end TDAS**：每个 `(system, condition, question, repeat)` 的二元任务成功。
6. **Reliability/operability**：availability、timeout、repeat flip、P50/P95、人工分钟、干预、恢复和成本。

切片至少包括：文档类型、语言、PDF 版式、扫描质量、表格、图片、多跳、版本冲突、fresh、不可回答和 citation-required。

### 4.4 判分、复核和统计

- Judge 在 Stage 2 dev/pilot 输出上校准，正式运行前冻结 model/version/prompt/temperature/max output。
- 至少抽 `max(40, 20% × 600)=120` 个不同 formal questions 做双人盲审；每个抽中问题覆盖所有系统同一预注册 repeat。
- 先对同一 `system × condition × question` 的 3 次 repeat 取平均，再在 600 个 question 上做宏平均。
- paired comparison 以 `analysis_cluster_id` 为 bootstrap 单位，所有系统同步重采样 10,000 次，报告 paired difference 和 95% CI。
- 同时报 `pass/pass/pass`、混合翻转和 `fail/fail/fail` 数量，避免平均值掩盖不稳定。
- 如果 paired CI 跨 0，结论写“未观察到稳定差异”；不依据单个小切片宣布 winner。
- claims/citations 报分子、分母和 rate，不把同一题内相关 claims 当独立样本生成置信区间。

### 4.5 Stage 3 Gate 和最终结论

| Gate | 通过条件 |
|---|---|
| **S3-G0 Identity/Parity** | 三系统身份、版本、Native path、权限、预算和配置 manifest 完整 |
| **S3-G1 Corpus Readiness** | 120 formal 文档对每个系统均有 terminal ready/failure 状态；失败保留在分母 |
| **S3-G2 Run Completeness** | 5,400 个 initial attempts 全部对账；raw response、citation、时间和错误完整 |
| **S3-G3 Judge/Audit** | Judge freeze 有效；120-question 双审完成；一致性和 adjudication 达标 |
| **S3-G4 Reproducibility** | 所有主表可从 immutable artifacts 重算；question exclusions 对所有系统共同生效 |

最终报告不给一个加权“总冠军”，而给出：

- Quick-start Native 的分层主表；
- 可选 Optimized Native 的独立主表；
- MOI 相对 Dify/FastGPT 的 paired TDAS difference 和 CI；
- 各层能力差异及根因；
- time-to-value、稳定性、人工成本和可观察性差异；
- 明确区分“准确率差异”“能力缺失”“trace 不可见”和“运行失败”。

预计周期：**3–4 周**，前提是 Stage 2 formal 已冻结、三个产品的自动化和权限可用。

## 5. 三阶段数据使用总表

| 数据/Benchmark | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|
| OmniDocBench | 解析论文同口径 + MOI 统一指标 | 只借 coverage/schema，不复制数据 | 不使用 |
| READoc | PDF-to-Markdown 诊断 | 只借结构化 Gold 思路 | 不使用 |
| MMDocIR | page/layout retrieval 基线 | 只借 qrels 与 evidence-set 设计 | 不使用 |
| ViDoRe V2 | 视觉 retrieval 基线 | 只借视觉/领域切片设计 | 不使用 |
| DocBench | PDF-to-answer 端到端基线 | 只借题型设计 | 不使用 |
| MMDocRAG | 多模态端到端基线 | 只借跨模态 evidence schema | 不使用 |
| RAGBench | evaluator/reader 回归 | 只借 TechQA/EManual/TAT-QA/HotpotQA 题型 | 不使用 |
| MultiHop-RAG | 多跳 retrieval/reader 诊断 | 只借 2–4 evidence-set 设计 | 不使用 |
| RGB | 授权通过后做鲁棒性；否则只参考论文 | 借噪声/拒答/冲突设计 | 不使用 |
| ALCE | 授权通过后复现 citation；否则只参考协议 | 借 claim-to-citation schema | 不使用 |
| RAGTruth | 授权通过后做 Judge 校准 | 借 span-level hallucination label | 不使用 |
| Double-Bench | corpus 未下载，暂缓 | 只借多语言、多模态和动态更新设计 | 不使用 |
| 新建 MOI Dataset v1 dev | 不使用 | adapter、调优、Judge calibration | 只用于预先允许的配置和 scorer smoke |
| 新建 MOI Dataset v1 pilot | 不使用 | MOI-only 评测 | 不进入正式比较 |
| 新建 MOI Dataset v1 formal | 不使用 | 始终 sealed | MOI、Dify、FastGPT 正式横评 |

## 6. 项目里程碑和建议排期

| 周期 | 里程碑 |
|---|---|
| Week 1 | 冻结 Stage 1 数据 allowlist、MOI API/Native boundary、统一 ledger schema |
| Week 2–3 | P0 adapter smoke；OmniDocBench、MMDocIR、ViDoRe、DocBench 首轮运行 |
| Week 4–5 | Stage 1 扩展运行、双指标报告、Stage 2 coverage gap 冻结 |
| Week 6–8 | 新文档取得/创作、权利和敏感信息审核、manifest 建立 |
| Week 9–11 | 1,000 问题和 Gold authoring、双审、adjudication、split 泄漏检查 |
| Week 12–13 | Stage 2 MOI dev/pilot、Judge 校准、错误地图、formal freeze |
| Week 14 | 三系统 dev smoke、Quick-start/Optimized 配置和预算冻结 |
| Week 15–16 | Stage 3 formal 运行、重试诊断、运行完整性审计 |
| Week 17 | 盲判、人工 audit、paired statistics、最终报告 |

理想排期约 **17 周**。若只有一名执行者，应先完成 Stage 1 P0 和 Stage 2 的 50 文档 / 250 问题 v0.5，再扩展到正式规模；不能通过减少 formal 双审、开放 sealed split 或复用同一题调优来压缩周期。

## 7. 与现有计划的关系

- [`drafts/v0.4.md`](drafts/v0.4.md) 仍是 MOI 单系统一周可行性 Pilot，可作为本计划 Stage 2 的最小技术预演。
- [`drafts/v0.3.md`](drafts/v0.3.md) 的 Native/Optimized 条件、三系统比较、paired bootstrap 和运行公平性规则进入 Stage 3。
- [`golden-and-metrics-spec-v0.4.md`](golden-and-metrics-spec-v0.4.md) 的 claim/evidence/citation/TDAS 定义是 Stage 2/3 的内部统一指标基线。
- [`research/rag-benchmark-catalog-and-layered-evaluation-plan.md`](research/rag-benchmark-catalog-and-layered-evaluation-plan.md) 负责解释各公开 benchmark 的层级角色；本文件负责三阶段执行顺序和数据流。
- [`../refs/rag-public-datasets-commercial-use-review-2026-07.md`](../refs/rag-public-datasets-commercial-use-review-2026-07.md) 是 Stage 1 的默认许可 gate。

## 8. 立即执行的前置任务

1. 为 12 个公开 benchmark 建 `ALLOW / RESEARCH_ISOLATED / BLOCK` 精确清单，并确认能否上传目标 MOI 租户。
2. 冻结 Stage 1 P0：OmniDocBench、MMDocIR、ViDoRe V2、DocBench；MMDocRAG 先做 200 QA。
3. 定义统一 adapter 输出：documents/pages、queries、qrels、responses、citations、trace、timing、errors。
4. 在 MOI 上验证 parser artifact、retrieved chunks/rank 和 citation locator 是否可导出；这决定哪些论文指标能真实计算。
5. 确认 Stage 2 文档来源和发布目标：只发布聚合分数，还是未来要发布题目/文档；后者需要更严格的取得授权。
6. 指定 Stage 2 的 Data Owner、Gold Owner、Reviewer、Product Operator 和 Legal/Security Reviewer。
7. 在任何 formal 数据生成前冻结 Stage 3 的 comparator shortlist、Native 边界和公平预算原则。
