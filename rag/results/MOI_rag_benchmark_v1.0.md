# MOI RAG Benchmark：四个平台、五类数据集的证据链评测与复现研究

> 报告版本：v1.0  
> 评测快照：2026-08-14
> 评测对象：MOI、Dify、FastGPT、MaxKB  
> 复现状态：已落盘结果可在本地审计，并可在满足数据、平台与模型条件时复跑。

## TL;DR

本研究在 WikiEval、MMDocIR、DocBench、EnterpriseRAG-Bench 和 Lenovo-bench 上，对 MOI、Dify、FastGPT 与 MaxKB 的文本检索、长文档页面/布局检索、原始 PDF 问答、企业多源问答和自建证据链问答进行了分层评估。

1. **WikiEval 已接近检索天花板。** MOI、Dify、FastGPT 的 Source Recall@1 都是 100%，MaxKB 为 98%。MOI 的 reference keyword recall 最高（65.19%），Dify 的 Faithfulness 与 Context Precision 最高，FastGPT 的 Context Recall 最高。该数据集更适合做链路回归，不足以区分复杂企业 RAG。
2. **长文档中，“找对页面”和“覆盖正确布局区域”是两个问题。** MMDocIR 的记录显示，Dify 在 Page fraction@1 上最高，MaxKB 在高 K 页面覆盖上最高，FastGPT 的 Page MRR 最高；MOI 在四个平台的 Layout@1/5/10 上均最高，但仍低于论文中最强的 Col-Phi3→ColBERT 参考行。由于 MOI 与竞品的记录范围并非全部同分母，这些差异是描述性诊断，不是正式配对排名。
3. **DocBench 暴露了文本题与多模态/元数据题之间的断层。** Dify 的记录 Overall Correctness 最高（61.32%），MOI 为 58.26%；四个平台在 Multimodal 与 Metadata 上都明显弱于论文 GPT-4 参考行。MOI 在本地平台中 Metadata（24.53%）和 Unanswerable（85.96%）最高，但该表混合了 Native PDF、current-corpus adapted 与 controlled parsed-text 条件，不能直接宣布平台优胜。
4. **EnterpriseRAG-Bench 出现明显的召回与噪声权衡。** FastGPT 的 Doc Recall@10、Complete Evidence-set Recall@10 和 Correctness 最高；MOI 的 Invalid Extra Docs 最低（2.345），Completeness 最高（58.74%）。这表明 MOI 当前更保守、更少引入额外文档，但证据覆盖广度仍落后。该实验是 722 文档的 adapted slice，不是约 51 万文档的官方全库复现。
5. **Lenovo-bench 说明“说得对”不等于“说得全”。** FastGPT 的 Evidence Recall@10、Complete Evidence-set Recall@10 和 Reference-claim Recall 最高；MaxKB 的 Response-claim Correctness 最高，MOI 次之，但二者的 Reference-claim Recall 明显较低。高 claim correctness 与低 reference recall 可以同时出现，通常意味着回答较保守或覆盖不足。

对 MOI 而言，当前证据支持的定位是：**小规模文本链路稳定、布局级证据定位有竞争力、企业检索噪声控制较好；但页面/证据召回广度、答案覆盖率、原生多模态解析的同口径证明和引用闭环仍需加强。**

---

## 摘要

企业 RAG 平台的质量由文档接入、解析、切分、向量化、检索、上下文组装、生成、拒答和引用等多个阶段共同决定，仅使用单一 Recall 或 LLM Judge 分数难以解释系统差异。本文构建 MOI RAG Benchmark 的论文式实验报告，在统一结果表和复现协议基础上，分析 MOI、Dify、FastGPT 与 MaxKB 在五类数据集上的表现。评测覆盖 50 题小规模文本 RAG、1,658 题长文档 Page/Layout Retrieval、1,102 题原始 PDF 问答、500 题企业多源问答，以及 60 题自建正式证据链问答。结果显示：四个平台不存在跨任务的一致最优者；FastGPT 在 EnterpriseRAG-Bench 与 Lenovo-bench 的证据召回广度上占优，Dify 在多个生成质量指标和 DocBench 总体正确率上表现突出，MaxKB 在 MMDocIR 高 K 页面覆盖和 Lenovo-bench response-claim correctness 上有优势，MOI 则在 WikiEval 关键词覆盖、MMDocIR 布局召回、EnterpriseRAG-Bench 噪声控制和完整性上表现出较强的保守证据组织特征。与此同时，实验包含 official、adapted、native、controlled 和 pilot 等不同条件，部分平台缺少稳定 Direct Retrieval trace，LLM Judge 与托管模型也不能做到逐 bit 冻结。因此，本文不构造跨数据集总分，而以数据集内结果、协议标签和证据链诊断形成结论。研究表明，可信 RAG 评测必须同时报告可用性、证据召回、答案正确性、答案覆盖、拒答、引用与失败分母。


---

## 1. 研究背景

开源或可私有化的 RAG 平台通常都宣称支持 PDF、向量检索、知识库问答、中文和大模型编排，但用户真正面对的是一条连续产品链路：

~~~mermaid
flowchart LR
    A["原始文件"] --> B["解析、OCR 与结构保留"]
    B --> C["切分、Embedding 与索引"]
    C --> D["Searchable-ready"]
    D --> E["检索与排序"]
    E --> F["上下文组装"]
    F --> G["生成或拒答"]
    G --> H["Claim、证据与引用校验"]
    H --> I["可审计结果与运行账本"]
~~~

任一阶段失败，都可能让最终答案不可用。文档上传成功不等于可检索，命中正确文档不等于找到正确页面，找到相关页面不等于收齐完整证据，答案中的句子看似正确也不等于覆盖了全部参考 claim。正因如此，本研究不把平台简化为“Retriever + LLM”，而把评测对象定义为从原文件到可核验回答的 **Evidence Chain**。

本文回答五个研究问题：

- **RQ1：** 四个平台在小规模通用文本 RAG 上是否已经达到稳定可用状态？
- **RQ2：** 面对长文档时，页面级召回、布局级证据覆盖与下游问答之间有什么差异？
- **RQ3：** 从原始 PDF 到回答的链路中，text-only、multimodal、metadata 和 unanswerable 题分别暴露了什么瓶颈？
- **RQ4：** 在企业多源与冲突信息场景中，证据召回广度、额外噪声、答案正确性和完整性如何权衡？
- **RQ5：** MOI 的现有优势更接近解析、检索、证据组织，还是回答生成；哪些结论尚未被同口径实验支持？


## 2. 评测对象

MOI 指 MatrixOne Intelligence。四个平台的产品重心并不相同，因此同一分数不能代表完全相同的产品能力。

| 平台 | 固定版本或镜像 | 本研究中的主要产品边界 | 关键可观察性限制 |
|---|---|---|---|
| **MOI** | MatrixOne <code>4.1.4</code>；runtime <code>8.0.30-MatrixOne-v4.1.4</code> | 原始文件、MatrixFlow 解析、多级索引、MatrixOne 全文/向量检索、证据展开与生成 | 历史 build 为 dirty；部分轨使用 current corpus 或 LIKE full-text fallback；历史索引 operator 与查询距离曾不一致 |
| **Dify** | <code>1.16.1</code>；commit <code>6f8ed69ee15f9a2e7189ca066275e973d091d1e9</code> | Dataset API、Direct Retrieval、应用 Chat/Workflow | Dataset key 与 App key 分离；实际 parser、向量库与插件配置必须随 run 冻结 |
| **FastGPT** | source <code>v4.15.6</code> / commit <code>3db33e93b78e75b37c93f7a6e3d0fafeafbfd256</code>；部署镜像记录为 <code>v4.15.4</code> | Dataset/Collection、<code>searchTest</code>、OpenAI-compatible Chat | <code>searchTest.limit</code> 是 token budget；需扩大 budget 后再按唯一 source 截取 Top-K |
| **MaxKB** | <code>v2.10.4-lts</code> / commit <code>fd6141e662582e88a41edbb7f6f89f4539e3e5dd</code> | 知识库、应用 Chat、管理侧诊断 | 未验证稳定的 public Direct Retrieval API；admin hit-test 只作诊断，不能冒充正式排名 trace |


## 3. 实验设计

### 3.1 数据集与能力覆盖

| 数据集 | 冻结规模 | 主要输入 | 核心能力 | 协议边界 |
|---|---:|---|---|---|
| **WikiEval** | 50 sources / 50 QA | Wikipedia Markdown | 小规模文本 ingest、检索、生成和 RAGAS 回归 | 四平台使用同一 50 题冻结集；RAGAS 各指标的有效分母需独立记录 |
| **MMDocIR** | 313 docs / 20,395 pages / 170,338 layouts / 1,658 QA | 官方预提取 page/layout 与 bbox | document-local Page/Layout Retrieval；下游 QA | 官方任务只定义检索；QA 为项目适配。竞品主要记录为 20 docs / 681 pages / 103 QA exact-input 条件 |
| **DocBench** | 229 PDF / 1,102 QA | raw PDF 或 candidate Markdown | 原始 PDF、长文档、表格/图片、metadata、拒答 | Native PDF 与 controlled parsed-text 必须分开解释 |
| **EnterpriseRAG-Bench** | 本地 722 docs / 500 QA | 九类企业来源的合成文档 | 多源、冲突、完整性、info-not-found | 本地是 question-linked adapted slice；公开全库约 511,962 docs |
| **Lenovo-bench** | 46 PDF / 1,104 pages / 100 QA；formal=60 | 企业 PDF 与 evidence-chain Gold | 证据集合、claim、引用和严格拒答 | 项目自建数据集；尚无公开下载页；formal 主分母为 60 |

这五个数据集分别压测文本回归、长文档定位、复杂 PDF、企业多源检索和内部可信问答。它们的指标空间不同，因此本文不把 Page Recall、RAGAS Faithfulness、DocBench Correctness 与 claim recall 相加。

### 3.2 模型与检索配置

复现指南冻结的共同配置为：

- 文本生成与主要 Judge：<code>deepseek-v4-flash</code>；
- 涉及视觉输入的生成或 Judge：<code>qwen3.5-35b-a3b</code>；
- 纯文本 Embedding：<code>bge-m3</code>，1,024 维；
- 视觉相关 Embedding：<code>Qwen3-VL-Embedding</code>，1,024 维；
- Reranker：四平台均未启用；
- 检索 K：按数据集冻结为 1/3/5/10 或 Top-10；

### 3.3 公平性与失败分母

本研究采用以下规则：

1. **同一冻结优先。** 只有 dataset、split、questions、Gold、Top-K、模型和 scorer 一致时，才允许正式配对比较。
2. **首次请求决定主结果。** Retry 用于恢复诊断，不能覆盖 initial attempt 的 EMPTY、FAILED、TIMEOUT 或 BLOCKED。
3. **失败与不适用分开。** 平台错误或空答在适用质量指标中进入分母；Gold 缺失、协议不适用、Judge 无有效结果则记 N/A。
4. **不可观察的检索不反推。** 没有真实 rank、score、source lineage 或 bbox trace 时，使用 <code>N/A: TRACE_UNAVAILABLE</code>；没有受支持接口时使用 <code>N/A: UNSUPPORTED_API</code>。
5. **先题内、后题间。** 多次 repeat 先在问题内求均值，再做 question macro-average。
6. **Claim 指标同时保留 micro 与 macro。** 例如 109/123 是 response-claim 微观计数，不等于 53 个 answerable questions 的宏平均。

## 4. 指标

### 4.1 检索指标

对问题 q，设 Gold 单元集合为 $G_q$，系统 Top-K 返回为 $R_q@K$：

$$
Evidence\ Recall@K(q)=\max_{S\in GoldSets(q)}
\frac{|R_q@K\cap S|}{|S|}
$$

$$
Complete\ Evidence\text{-}set\ Recall@K(q)
=I(\exists S\in GoldSets(q), S\subseteq R_q@K)
$$

$$
MRR=\frac{1}{|Q|}\sum_{q\in Q}\frac{1}{rank_q}
$$

其中，WikiEval 的 Source Recall 是“至少命中一个 Gold source”；MMDocIR 的 Page fraction 是“找回 Gold pages 的比例”；Layout Recall 依据同页 bbox 与 Gold bbox 的交叠面积；Enterprise 和 Lenovo 则关注完整 evidence set。它们名称相近，但测量对象不同。

### 4.2 回答与证据指标

- **Correctness：** 判断答案是否正确；量表可能是 0/1、0–1 连续值或 1–5 分，不能混算。
- **Faithfulness：** 答案中的事实 claim 是否得到实际运行上下文支持。
- **Completeness / Reference-claim Recall：** Gold 中应回答的事实被覆盖了多少。
- **Response-claim Correctness：** 系统实际说出的 factual claims 中，有多少正确或部分正确。
- **Strict Unanswerable Success：** 正确拒答、理由符合 Gold，且不产生无依据事实或伪造引用。
- **Contains-gold 与 Token F1：** 词面诊断指标，不替代语义正确性。



## 5. 实验结果

### 5.1 WikiEval：文本 RAG 链路接近饱和

| 方法 | Source R@1 | Source R@3 | Source R@5 | MRR | Reference keyword recall | Faithfulness | Answer Relevance | Context Precision | Context Recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **MOI** | 100.0% | 100.0% | 100.0% | 1.000 | **65.19%** | 0.9637 | **0.9309** | 0.7406 | 0.9927 |
| **Dify** | 100.0% | 100.0% | 100.0% | 1.000 | 59.46% | **0.9938** | 0.9123 | **0.8015** | 0.9871 |
| **FastGPT** | 100.0% | 100.0% | 100.0% | 1.000 | 41.39% | 0.9682 | 0.9135 | 0.7916 | **0.9971** |
| **MaxKB** | 98.0% | 98.0% | 98.0% | 0.980 | 62.37% | 0.9711 | 0.8802 | 0.7805 | 0.9792 |
| 论文：RAGAS | N/A | N/A | N/A | N/A | N/A | 0.95 | 0.78 | 0.70 | N/A |
| 论文：ChatGPT | N/A | N/A | N/A | N/A | N/A | 0.72 | 0.52 | 0.63 | N/A |

三个系统在 Source Recall@1 就达到 100%，说明 50-source 规模下，源文档级命中已经很难区分系统。MOI 的 reference keyword recall 比 Dify 高 5.73 个百分点、比 FastGPT 高 23.80 个百分点，说明其检索上下文保留了更多冻结关键词；但 MOI 的 Context Precision 低于 Dify 6.09 个百分点。结合 MOI 的证据展开机制，一个合理但尚未由消融实验证实的解释是：扩展邻域有利于覆盖关键词和 Context Recall，也可能引入额外上下文。

Dify 的 Faithfulness 和 Context Precision 最高，FastGPT 的 Context Recall 最高，MOI 的 Answer Relevance 最高。四个 RAGAS 维度没有由同一平台全部领先，因此 WikiEval 的合理用途是验证 ingest→retrieval→generation→judge 链路，而不是生成企业场景总榜。

### 5.2 MMDocIR：页面覆盖、布局覆盖与 QA 的分化

#### 5.2.1 Page 与 Layout Retrieval

| 方法 | Page fraction @1 | @3 | @5 | @10 | Page MRR | Layout @1 | @5 | @10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **MOI** | 43.49% | 65.85% | 73.93% | 84.02% | 0.6208 | **28.02%** | **52.70%** | **61.87%** |
| **Dify** | **53.51%** | 67.00% | 72.59% | 78.00% | 0.6959 | 21.03% | 50.77% | 59.98% |
| **FastGPT** | 51.46% | 69.53% | 75.95% | 87.72% | **0.7271** | 22.09% | 51.70% | 57.39% |
| **MaxKB** | 48.95% | **70.83%** | **80.32%** | **92.56%** | 0.7242 | 26.01% | 49.75% | 59.01% |
| 论文：Col-Phi3→ColBERT | 57.1% | 76.8% | 83.0% | N/A | N/A | 35.3% | 58.8% | 65.4% |
| 论文：DPR-Phi3→ColBERT | 53.7% | 74.3% | 81.8% | N/A | N/A | 30.6% | 56.6% | 64.5% |
| 论文：BGE VLM-text | 39.6% | 59.7% | 68.4% | N/A | N/A | 28.3% | 51.8% | 60.3% |

在记录值中，Dify 更容易把首个 Gold page 排到第 1，FastGPT 的首个相关页面平均排名最好，MaxKB 的高 K 页面覆盖最高；MOI 则在四个平台的 Layout@1/5/10 上全部领先。与论文最强参考行相比，MOI 的 Layout@1/5/10 仍分别低 7.28、6.10 和 3.53 个百分点，说明布局检索虽是相对优势，但尚未达到外部最强参考量级。


#### 5.2.2 下游 QA

| 方法 | Answer Correctness | Token F1 | Faithfulness | Contains Gold | Answer non-empty |
|---|---:|---:|---:|---:|---:|
| **MOI** | 3.91/5 | 0.1147 | 0.7398 | 47.23% | 96.20% |
| **Dify** | **4.02/5** | **0.1651** | **0.7921** | **58.11%** | 98.01% |
| **FastGPT** | 3.95/5 | 0.1219 | 0.7458 | 54.07% | 97.86% |
| **MaxKB** | 3.87/5 | 0.1160 | 0.6811 | 51.46% | **98.06%** |
| Shared Gold-page oracle | 4.59/5 | 0.1593 | 0.8577 | 54.37% | 100.00% |
| 论文参考：GPT-4.1 Perfect Retriever；Multi-retriever/Clauses | 4.14/5；3.79/5 | N/A | N/A | N/A | N/A |

Dify 在当前记录的 QA correctness、Token F1、Faithfulness 和 Contains Gold 上最高，MaxKB 的非空回答率最高。Gold-page oracle 的 correctness 为 4.59/5，高于所有平台，表明页面检索仍限制下游回答；但 Dify 的 Token F1 与 Contains Gold 高于 oracle，说明词面指标不是单调的“oracle 上界”，不能把它们独立解释为语义质量。

MMDocIR 原论文只定义检索，本报告中的 QA 是基于 Gold answer/evidence 的项目扩展。其结论必须标记为 adapted QA，不能写成 MMDocIR 官方 QA 排名。

### 5.3 DocBench：复杂 PDF 的主要瓶颈仍在多模态与元数据

| 方法与条件 | Overall Correctness | Text-only | Multimodal | Metadata | Unanswerable | Contains-gold | Token F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **MOI（current-corpus adapted）** | 58.26% | 77.37% | 43.23% | **24.53%** | **85.96%** | 15.23% | 13.96% |
| **Dify（Native PDF）** | **61.32%** | **80.19%** | **45.12%** | 20.85% | 79.21% | **18.80%** | **16.19%** |
| **FastGPT（controlled parsed-text）** | 54.23% | 79.25% | 40.92% | 22.98% | 84.97% | 18.62% | 10.04% |
| **MaxKB（controlled parsed-text）** | 59.91% | 76.53% | 42.72% | 22.98% | 80.82% | 11.05% | 14.69% |
| 论文：GPT-4 | 67.9% | 79.1% | 63.3% | 54.3% | 70.2% | N/A | N/A |

Dify 的记录总体正确率为 61.32%，比 MOI 高 3.06 个百分点；MOI 在本地平台的 Metadata 和 Unanswerable 上分别领先 1.55 和 0.99 个百分点。四个平台的 Text-only 均在 76.53%–80.19%，但 Multimodal 只有 40.92%–45.12%，Metadata 只有 20.85%–24.53%。相较论文 GPT-4 参考行，多模态和元数据仍是最明显的缺口。

Unanswerable 得分普遍高于论文参考行并不自动意味着总体更强：严格拒答是必要能力，但也需要与 answerable questions 的 completeness 和 false refusal 一起检查。仅看拒答切片可能奖励过度保守。

更重要的是，四行使用的输入协议不同。Dify 使用 raw PDF/native parser，FastGPT 与 MaxKB 的完整结果主要是 controlled parsed-text，MOI 是 current-corpus adapted 路径。上表可用于识别题型难点，不可作为严格的 parser 或端到端平台排名。

### 5.4 EnterpriseRAG-Bench：广召回与低噪声之间的权衡

| 方法 | Doc Recall@10 | Complete Evidence-set Recall@10 | Invalid Extra Docs ↓ | Semantic Recall | Conflict Recall | 检索 Info-not-found Success | Correctness | Completeness | Dataset Aggregate | 问答 Info-not-found Success（adapted） |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **MOI** | 80.59% | 74.68% | **2.345** | 70.40% | 77.50% | 85.00% | 49.20% | **58.74%** | 47.30% | 85.00% |
| **Dify** | 88.51% | 78.30% | 5.991 | 73.60% | **100.00%** | **100.00%** | 55.40% | 57.50% | **56.40%** | **100.00%** |
| **FastGPT** | **89.61%** | **85.53%** | 8.685 | **80.80%** | 85.00% | **100.00%** | **60.27%** | 57.95% | 55.94% | **100.00%** |
| 论文：BM25 | 68.4% | N/A | 9.0 | 43.2% | N/A | N/A | 68.8% | 56.0% | N/A | N/A |
| 论文：OpenAI text-embedding-3-large | 46.0% | N/A | 9.3 | 24.8% | N/A | N/A | 51.4% | 42.9% | N/A | N/A |

> 原始结果表最后一列命名为 Strict Unanswerable Success。复现指南指出：当前 500 题若仍全部标记为 <code>answerable=true</code>，其中 20 个 <code>info_not_found</code> 题不能静默重标为 unanswerable。本文因此使用 **Info-not-found Success（adapted）**，避免制造不存在的 strict-unanswerable Gold。
>
> 原始表同时保留了检索侧 Info-not-found 字段与问答侧字段，且当前三平台的两列值相同。二者是否来自同一 scorer 仍需回溯逐题 artifact；本文不将重复列视为两项独立证据。

FastGPT 的 Doc Recall@10 比 MOI 高 9.02 个百分点，Complete Evidence-set Recall@10 高 10.85 个百分点，Correctness 高 11.07 个百分点。MOI 的平均 Invalid Extra Docs 只有 2.345，较 Dify 低约 60.9%，较 FastGPT 低约 73.0%；MOI 的 Completeness 也分别比 FastGPT 和 Dify高 0.79、1.24 个百分点。

这是一组典型的 breadth–noise trade-off：FastGPT 找回更多 Gold 文档和完整证据集，但同时返回更多无效额外文档；MOI 的上下文更克制，覆盖面却较窄。Dify 在 Conflict Recall 和 info-not-found 上表现突出。若企业任务对漏证据和噪声的代价不同，应分别冻结阈值，而不是只看一个 aggregate。



### 5.5 Lenovo-bench：回答正确率与参考覆盖率并不一致

| 方法 | Evidence Recall @1 | @3 | @5 | @10 | Complete Set @1 | @3 | @5 | @10 | Response-claim Correctness | Reference-claim Recall | Strict Unanswerable Success |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **MOI** | 19.50% | 28.30% | 35.69% | 50.00% | 13.21% | 20.75% | 28.30% | 41.51% | 88.62%（109/123） | 18.71%（26/139） | 71.43%（5/7） |
| **Dify** | 24.68% | 31.09% | 38.62% | 45.35% | 21.15% | 26.92% | 32.69% | 36.54% | 68.52%（37/54） | 8.63%（12/139） | **100.00%（7/7）** |
| **FastGPT** | **30.82%** | **58.02%** | **63.36%** | **75.16%** | **24.53%** | **49.06%** | **50.94%** | **62.26%** | 86.11%（124/144） | **45.32%（63/139）** | 85.71%（6/7） |
| **MaxKB（controlled chunked-text）** | 17.55% | 30.19% | 37.17% | 60.35% | 13.79% | 20.51% | 37.74% | 58.11% | **91.07%（51/56）** | 3.60%（5/139） | **100.00%（7/7）** |

FastGPT 在全部 Evidence Recall K、全部 Complete Evidence-set Recall K 和 Reference-claim Recall 上领先。与 MOI 相比，其 Evidence Recall@10 高 25.16 个百分点，Complete Evidence-set Recall@10 高 20.75 个百分点，Reference-claim Recall 高 26.61 个百分点。

MaxKB 的 response-claim correctness 为 91.07%，MOI 为 88.62%，FastGPT 为 86.11%；但 MaxKB 的 reference-claim recall 只有 3.60%，MOI 也只有 18.71%。这表明“系统说出的内容大多正确”与“系统覆盖了 Gold 要求的内容”并不冲突：一个简短、保守的回答可以有高 claim precision，同时严重漏答。FastGPT 的 response claims 更多，覆盖率也显著更高，表现出更积极的证据利用。

Strict Unanswerable Success 的分母只有 7。Dify 与 MaxKB 的 7/7 是积极信号，但样本太小，不能据此推断所有拒答场景。MaxKB 还是 controlled chunked-text 条件，且 Lenovo-bench 尚无公开下载页，外部独立复现受到限制。

## 6. 跨数据集综合分析

### 6.1 条件化结果摘要

| 能力面 | 当前记录中的突出者 | MOI 的相对位置 | 解释边界 |
|---|---|---|---|
| 小规模 source 命中 | MOI / Dify / FastGPT 并列 100% | 达到天花板；关键词覆盖最高 | 只有 50 sources，不能外推大库 |
| 长文档 Page Retrieval | Dify@1、FastGPT MRR、MaxKB 高 K | 页面覆盖居中偏后 | MOI full 与竞品 subset 不同分母 |
| 长文档 Layout Retrieval | MOI | 四平台最高 | 仍低于最强论文参考 |
| DocBench 端到端正确性 | Dify 当前记录最高 | 总体中游；metadata/unanswerable 本地最高 | 输入协议混合，不能作严格排名 |
| 企业证据召回 | FastGPT | 召回较低 | 722-doc adapted slice |
| 企业上下文降噪 | MOI | Invalid Extra Docs 最低 | 更低噪声伴随更低召回 |
| 内部证据覆盖 | FastGPT | claim correctness 高、reference recall 低 | Lenovo Gold 未公开；claim 分母系统相关 |
| 严格拒答 | Dify / MaxKB 在 Lenovo 7/7 | MOI 5/7 | 小样本参考意义偏低 |

### 6.2 没有全局冠军

若按数据集逐项看“最高值”，平台优势会随测量对象改变：

- Dify 更常在生成质量、DocBench 总体正确性和冲突/信息缺失处理上出现高值；
- FastGPT 更常在大证据集召回、完整证据集覆盖和 reference-claim recall 上领先；
- MaxKB 在高 K 页面覆盖和已输出 claim 的正确率上表现突出；
- MOI 在关键词覆盖、布局区域召回、低无效文档数和答案完整性上表现出优势。

这些结果说明，平台差异不是一条从弱到强的直线，而是解析、召回、噪声、生成、覆盖和可观察性之间的多维权衡。

### 6.3 研究问题回答

| 研究问题 | 基于当前证据的回答 |
|---|---|
| **RQ1：小规模文本 RAG 是否稳定？** | 是。三个系统 Source Recall@1=100%，第四个为 98%；但该数据集已经出现明显 ceiling effect。 |
| **RQ2：页面、布局和 QA 是否一致？** | 不一致。Page@1、高 K page coverage、Page MRR 和 Layout Recall 分别由不同平台领先，Gold-page oracle 也显示检索仍限制 QA。 |
| **RQ3：复杂 PDF 的主要瓶颈是什么？** | Text-only 已接近论文参考量级，多模态与 metadata 仍明显偏低；当前协议混合，尚不能把差距单独归因于 parser。 |
| **RQ4：企业场景如何权衡？** | 更广的 evidence recall 往往伴随更多 invalid extras。FastGPT 偏广召回，MOI 偏低噪声，二者需要按业务错误成本选择。 |
| **RQ5：MOI 的优势在哪里？** | 当前证据更支持布局定位、低噪声与可追溯证据组织；不支持全面 parser 或多模态领先的结论。 |

## 7. MOI 的证据链诊断

### 7.1 已被当前数据支持的优势

1. **文本回归链路稳定。** WikiEval Source Recall@1=100%、MRR=1.000，说明 ingest、混合检索、生成和 Judge 链路可以闭环运行。
2. **布局级定位有竞争力。** MMDocIR Layout@1/5/10 在四个平台记录行中最高，证明当前 page/layout candidate 到 MatrixOne 检索的路径具有有效区域覆盖能力。
3. **企业检索更克制。** EnterpriseRAG-Bench 的 Invalid Extra Docs 显著低于 Dify 和 FastGPT，说明当前结果更少引入非 Gold/非合法 alternative set 文档。
4. **已输出 claim 的正确率较高。** Lenovo-bench response-claim correctness 为 88.62%，仅低于 MaxKB；DocBench 的 strict rejection 也较强。
5. **证据 lineage 适合诊断。** MOI 本地链路可保存 route、score、source、page、bbox 和 evidence group，有利于区分 parser miss、candidate miss、ranking miss 与 generation miss。

### 7.2 当前最明显的缺口

1. **高 K 证据召回广度不足。** 在 Enterprise 与 Lenovo 上，MOI 的 complete evidence-set recall 均落后 FastGPT。
2. **正确但不完整。** Lenovo 中 88.62% response-claim correctness 与 18.71% reference-claim recall 的组合，说明答案覆盖不足是主问题之一。
3. **页面级与布局级能力不一致。** MOI 在 MMDocIR Layout 上较强，但 Page fraction 和 Page MRR 没有同步领先，需要拆解 query representation、candidate pool 与排序策略。
4. **多模态与 metadata 仍有较大绝对缺口。** DocBench 的 Multimodal 43.23%、Metadata 24.53%，距离论文参考行仍远。
5. **原生 parser 优势尚未被公平证明。** WikiEval 输入是 Markdown，MMDocIR 使用官方预提取 page/layout，DocBench 又存在 current-corpus adapted 条件；因此不能从现有结果推出“MOI Native parser 全面优于竞品”。
6. **没有独立 reranker 消融。** 当前融合策略可解释且成本低，但是否限制复杂语义排序尚无 paired ablation。

### 7.3 优先优化假设

下一轮应优先验证以下假设，而不是直接增加新的综合分：

- <code>full-text only / vector only / hybrid / hybrid + reranker</code> 四组配对消融；
- <code>no expansion / adjacent expansion / table-aware expansion</code> 对 Recall、Context Precision、Completeness 和 token budget 的影响；
- 对 MMDocIR 分离 page candidate coverage、page ranking 与 layout ranking；
- 对 DocBench 固定 raw PDF、parser、embedding、generator 后只替换单个组件；
- 对 Lenovo 的漏答题检查：Gold evidence 未检出、已检出但未进入 context、已进入 context 但 reader 未利用，还是 claim/citation Judge 失败；
- 将引用 locator validity 与 reference-claim recall 绑定，验证“正确答案是否可被用户核验”。

## 8. 场景化选型含义

本节不是采购结论，而是根据当前数据形成的 POC 方向。

1. **小规模文本知识库：** 四个平台都已形成高 source hit，选型应更多考虑应用编排、部署、公开 API、可观察性和维护成本。
2. **长文档页面检索：** 在相同文档子集上，应重点复测 FastGPT/MaxKB 的高 K 覆盖与 MOI 的 layout 优势，并统一 candidate representation 后再决定。
3. **原始复杂 PDF：** 必须坚持 raw PDF Native 主轨与 controlled parsed-text 诊断轨双报。只上传解析后的 Markdown，无法评价平台 parser。
4. **企业多源问答：** 若漏证据代价更高，应关注 FastGPT 的 evidence breadth；若噪声和错引代价更高，MOI 的低 invalid extras 值得进一步 POC。两者都必须结合最终 claim/citation 判分。
5. **严格合规问答：** 不能只追求 response-claim correctness。应同时设 reference-claim recall、strict unanswerable、citation coverage 和 scope/version violation 门禁。


## 9. 结论

MOI RAG Benchmark 的核心发现不是“四个平台谁第一”，而是不同平台在证据链上的损失位置不同。WikiEval 表明小规模文本 source retrieval 已经接近饱和；MMDocIR 表明页面排序和布局覆盖并不一致；DocBench 表明复杂 PDF 的多模态与元数据理解仍是共同短板；EnterpriseRAG-Bench 揭示召回广度与上下文噪声之间的权衡；Lenovo-bench 则证明 response-claim correctness 不能替代 reference-claim recall。

对 MOI，现有证据支持“稳定文本链路、较强布局检索、较低企业检索噪声和可追溯证据组织”的判断，但不支持“全面最佳 parser、多模态 RAG 最优或端到端总冠军”的宣传。下一阶段最有价值的工作是补齐同口径 Native PDF 对比、提高完整证据集召回和答案覆盖、加入 reranker/证据展开消融，并把 citation 与生命周期测试纳入正式门禁。

因此，可信的 RAG 评测应回答的不是一个总分，而是六个连续问题：**文档能否入库、证据是否存活、检索是否找全、上下文是否干净、答案是否正确完整、引用是否可核验。**
