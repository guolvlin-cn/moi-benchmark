# MultiHop-RAG Benchmark：原始结果、后续工作与评测口径梳理

> 调研日期：2026-07-31
> 研究对象：Tang & Yang, *MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries*（COLM 2024）及后续明确使用 MultiHop-RAG 数据集并报告定量结果的工作。

## 1. 结论先行

MultiHop-RAG 的公开结果不能简单排成一张“谁最高”的榜单。后续论文至少使用了三类彼此不等价的评测协议：

1. **接近原论文的检索评测**：256-token chunk、top-k 检索，以 MRR@10、MAP@10、Hits@10、Hits@4 为主。原论文最佳结果是 Voyage-02 + reranker 的 **MRR@10 0.5860、MAP@10 0.4795、Hits@10 0.7467、Hits@4 0.6625**；后续元数据过滤和问题分解方法把 Hits@10 推到约 **0.87–0.90**，但数据预处理、候选生成和指标实现并不完全相同。
2. **端到端问答评测**：不同论文使用 Accuracy、EM、F1、Recall 或 LLM judge，生成模型从 GPT-4、GPT-4o 到 Qwen2.5-72B、7B/8B 开源模型不等，测试集又可能只抽取 100、500 或 1000 条。因此报告的 **60%–82%** 不能视为同一标尺下的进步。
3. **辅助任务评测**：例如预测来源和日期过滤条件，其 90% 左右的准确率不是问答准确率，也不是证据检索成功率。

如果目的是给自己的系统定基线，一个实用判断是：

- 在接近原始检索协议时，**Hits@4 0.60–0.70、Hits@10 0.72–0.80** 属于成熟基线；加入问题分解、元数据或更强重排后，**Hits@4 0.75 左右、Hits@10 0.87–0.90** 是较强水平。
- 在端到端问答上，原论文时代的“检索上下文 + 闭卷式生成”约为 **44%–56%**；现代图式、记忆式或 agentic 系统常报告 **60%–82%**，但多数不是原协议上的严格可比提升。
- MultiHop-RAG 官方 Hits@K 是“top-k 内命中任意一条 gold evidence”即可，并不要求找齐多跳证据。它会高估真正完成多跳检索的概率；内部评测应额外报告 evidence recall、all-evidence success 和分问题类型结果。

## 2. 数据集与原始评测

### 2.1 数据集构成

[原论文](https://openreview.net/pdf?id=t4eB3zYWBK)收集了 2023-09-26 至 2023-12-26 的 609 篇英文新闻，文章平均长度约 2,046.5 tokens，共构造 2,556 个问题：

| 类型 | 数量 |
|---|---:|
| Inference | 816 |
| Comparison | 856 |
| Temporal | 583 |
| Null / 无答案 | 301 |
| 合计 | 2,556 |

非空问题所需证据数量分布为：2 条证据 1,078 题、3 条证据 779 题、4 条证据 398 题。论文与数据代码见[官方仓库](https://github.com/yixuantt/MultiHop-RAG)。

### 2.2 原论文检索设置

原论文把文档切成 256-token chunks，先取 top-20，再可选用 `bge-reranker-large` 重排并保留 top-10。检索评测排除 301 个 null 问题，指标为 MRR@10、MAP@10、Hits@10 和 Hits@4。

一个很重要的实现细节是：官方 [retrieval_evaluate.py](https://github.com/yixuantt/MultiHop-RAG/blob/main/retrieval_evaluate.py) 中的 Hits@K 是**问题级 any-hit**——只要 top-k 检索结果包含任意一条 gold evidence，该题就记为命中。它不是“找齐全部证据”的成功率，也不是标准意义上的 evidence recall@k。

### 2.3 原论文检索结果

下表均来自[原论文 Table 3](https://openreview.net/pdf?id=t4eB3zYWBK)；“+RR”表示加入 `bge-reranker-large`。

| Embedding | 重排 | MRR@10 | MAP@10 | Hits@10 | Hits@4 |
|---|:---:|---:|---:|---:|---:|
| text-embedding-ada-002 | 否 | 0.4203 | 0.3431 | 0.6381 | 0.5040 |
| text-embedding-ada-002 | 是 | 0.5477 | 0.4625 | 0.7059 | 0.6169 |
| text-search-ada-query-001 | 否 | 0.4203 | 0.3431 | 0.6399 | 0.5031 |
| text-search-ada-query-001 | 是 | 0.5483 | 0.4625 | 0.7064 | 0.6174 |
| llm-embedder | 否 | 0.2558 | 0.1725 | 0.4499 | 0.3189 |
| llm-embedder | 是 | 0.4250 | 0.3059 | 0.5478 | 0.4756 |
| bge-large-en-v1.5 | 否 | 0.4298 | 0.3423 | 0.6718 | 0.5221 |
| bge-large-en-v1.5 | 是 | 0.5630 | 0.4759 | 0.7183 | 0.6364 |
| jina-embeddings-v2-base-en | 否 | 0.0621 | 0.0310 | 0.1479 | 0.0802 |
| jina-embeddings-v2-base-en | 是 | 0.1412 | 0.0772 | 0.1909 | 0.1639 |
| e5-base-v2 | 否 | 0.1843 | 0.1161 | 0.3556 | 0.2334 |
| e5-base-v2 | 是 | 0.3237 | 0.2165 | 0.4176 | 0.3716 |
| voyage-02 | 否 | 0.3934 | 0.3143 | 0.6506 | 0.4619 |
| **voyage-02** | **是** | **0.5860** | **0.4795** | **0.7467** | **0.6625** |
| instructor-large | 否 | 0.3458 | 0.2650 | 0.5717 | 0.4229 |
| instructor-large | 是 | 0.5115 | 0.4118 | 0.6590 | 0.5775 |

### 2.4 原论文端到端问答结果

原论文分别让模型读取检索到的 chunks 和人工标注的 gold evidence。下表是论文报告的 Accuracy：

| 生成模型 | 检索上下文 | Gold evidence |
|---|---:|---:|
| GPT-4 | **0.56** | **0.89** |
| ChatGPT | 0.44 | 0.57 |
| Llama2-70B | 0.28 | 0.32 |
| Mixtral 8×7B | 0.32 | 0.36 |
| Claude 2.1 | 0.52 | 0.56 |
| PaLM | 0.47 | 0.74 |

这组结果说明当时主要瓶颈仍是检索：GPT-4 从检索上下文的 0.56 上升到 gold evidence 的 0.89。但它也不是今天常说的严格 normalized exact match。当前仓库的 [qa_evaluate.py](https://github.com/yixuantt/MultiHop-RAG/blob/main/qa_evaluate.py) 采用预测与答案 token 存在交集即判对的宽松逻辑；复现实验必须明确使用的是论文当时的判分、当前仓库脚本，还是另行实现的 EM/LLM judge。

## 3. 后续论文结果总览

“可比性”是相对于原论文协议而言：

- **A**：指标和数据范围接近，但仍需核查 chunk、检索器和重排器；
- **B**：使用同一数据集，但任务、模型、切分或判分方式明显变化，只能横向参考；
- **C**：子集、聚合结果或辅助任务，不应进入主排行榜。

| 年份 | 工作 | 主要任务与协议 | 论文最佳/代表性结果 | 可比性 |
|---|---|---|---|:---:|
| 2024 | [Multi-Meta-RAG](https://arxiv.org/abs/2406.13213) | 元数据过滤 + dense retrieval + reranker | Voyage：MRR 0.6748，MAP 0.3388，H@10 0.9042，H@4 0.7920 | A- |
| 2024 | [Writing in the Margins](https://arxiv.org/abs/2408.14906) | 最长的 100 题，13k–32k 长上下文 | 在 HotpotQA 与 MultiHop-RAG 聚合的 reasoning 结果中平均 +7.5%，约比 RAG +9% | C |
| 2025 | [ToQD](https://aclanthology.org/2025.coling-main.191.pdf) | 问题拓扑分解，gte-base，256-token chunks | H@10 0.614，MAP@10 0.168，MRR@10 0.329 | B |
| 2025 | [Question Decomposition for RAG](https://aclanthology.org/2025.acl-srw.32.pdf) | 问题分解 + reranker | H@4 0.763，H@10 0.872，MAP 0.322，MRR 0.635 | A- |
| 2025 | [KG-CQR](https://aclanthology.org/anthology-files/pdf/emnlp/2025.emnlp-main.824.pdf) | 知识图谱约束查询重写 | KG-CQR+BM25：mAP 0.250，R@5/10/25 0.267/0.372/0.532 | B |
| 2025 | [MemTree](https://proceedings.iclr.cc/paper_files/paper/2025/file/0382cb76309820f71c6eacd47b36ce71-Paper-Conference.pdf) | 树式长期记忆；只报告三种非空问题 | Accuracy 80.5%；RAPTOR 81.0% | B |
| 2025 | [RAP-RAG](https://www.mdpi.com/2079-9292/14/21/4269) | 关系感知路径增强，小模型 RAG | 论文称总体较 MiniRAG 高约 3–5 个百分点；MultiHop-RAG 权重消融下降 5.7/6.1 点 | C |
| 2025 | [QCG-RAG](https://arxiv.org/html/2509.21237) | 查询中心图，1,200-token chunks，Qwen2.5-72B judge | 总体 Accuracy 79.60% | B |
| 2026 | [ArchRAG](https://ojs.aaai.org/index.php/AAAI/article/download/38619/42581) | 层次化图 RAG，自定义 Accuracy/Recall | 68.8 / 37.2 | B |
| 2026 | [TopoRAG](https://aclanthology.org/2026.findings-acl.1703.pdf) | 拓扑图 RAG，GPT-3.5-turbo | 61.2 / 28.3；加 chunk 后 Accuracy 64.1 | B |
| 2026 | [ToR-Lite](https://www.mdpi.com/2076-3417/16/8/3966) | 2,255 个非空问题，严格 normalized EM | 相对 baseline：H@10 +6.03 点，EM +0.89 点 | B |
| 2026 | [Interact-RAG](https://openreview.net/pdf?id=yHUjWb6eMe) | 每个数据集抽 500 题，交互式 corpus reasoning | 8B：EM 81.4，F1 82.3；7B：79.4/80.4 | C |
| 2026 | [eGoT](https://pmc.ncbi.nlm.nih.gov/articles/PMC13341121/) | 随机抽 1,000 题，GPT-4o，自定义 P/R/F1/Acc | P 75.5，R 79.2，F1 76.3，Acc 79.1 | C |
| 2026 | [AutoAgent](https://aclanthology.org/2026.findings-acl.2129.pdf) | gpt-4o-mini，top-6，语义一致性判分 | Accuracy 73.51，Error 14.20 | B |
| 2026 | [Probe, Don’t Prompt](https://arxiv.org/abs/2607.03929) | 预测 source/date 过滤条件；非问答任务 | 过滤集合 exact accuracy 90.9% | C |

## 4. 后续检索结果明细

### 4.1 Multi-Meta-RAG

[Multi-Meta-RAG](https://arxiv.org/abs/2406.13213)从问题中抽取新闻来源和日期等元数据，先过滤语料，再执行向量检索和重排。其 chunk size 为 256、overlap 为 32，先取 top-20，再由 BGE reranker 保留 top-10。

| 方法 | MRR@10 | MAP@10 | Hits@10 | Hits@4 |
|---|---:|---:|---:|---:|
| BGE baseline | 0.6029 | 0.2687 | 0.7490 | 0.6661 |
| Voyage baseline | 0.6016 | 0.2619 | 0.7419 | 0.6630 |
| Multi-Meta-RAG + BGE | 0.6574 | 0.3293 | 0.8909 | 0.7672 |
| **Multi-Meta-RAG + Voyage** | **0.6748** | **0.3388** | **0.9042** | **0.7920** |

其生成结果为：GPT-4 的 gold / baseline / Multi-Meta-RAG Accuracy 为 0.89 / 0.56 / **0.606**，PaLM 为 0.74 / 0.47 / **0.608**。论文正文另有一处将 GPT-4 写成 0.63，与表格 0.606 不一致；本文以表格为准并保留这一勘误提醒。

### 4.2 Question Decomposition for RAG

[ACL SRW 2025 的问题分解工作](https://aclanthology.org/2025.acl-srw.32.pdf)同时报告了原论文中的两条重排基线和自己的实现：

| 方法 | Hits@4 | Hits@10 | MAP@10 | MRR@10 |
|---|---:|---:|---:|---:|
| text-ada + RR（引用原论文） | 0.616 | 0.706 | 0.463 | 0.548 |
| voyage + RR（引用原论文） | 0.663 | 0.747 | 0.480 | 0.586 |
| Naive | 0.611 | 0.781 | 0.217 | 0.464 |
| + Question Decomposition | 0.655 | 0.810 | 0.238 | 0.498 |
| + Reranker | 0.687 | 0.781 | 0.274 | 0.574 |
| **+ QD + Reranker** | **0.763** | **0.872** | **0.322** | **0.635** |

论文还在 250 题上报告延迟：Naive 约 0.03 秒/题、reranker 0.88 秒、QD 16.7 秒、QD+reranker 18.9 秒。也就是说，检索增益伴随明显的查询时推理成本。

### 4.3 ToQD

[ToQD](https://aclanthology.org/2025.coling-main.191.pdf)使用 gte-base、ChromaDB 和 256-token chunks，但其绝对分数与原论文基线差异较大，因此不宜直接拼榜：

| 方法 | Hits@10 | MAP@10 | MRR@10 |
|---|---:|---:|---:|
| Native | 0.586 | 0.160 | 0.353 |
| HyDE | 0.611 | 0.164 | **0.362** |
| SubQuestion | 0.334 | 0.040 | 0.085 |
| MultiQuery | 0.426 | 0.092 | 0.217 |
| **ToQD** | **0.614** | **0.168** | 0.329 |
| ToQD w/o critique | 0.573 | 0.142 | 0.357 |
| ToQD w/o rewrite | 0.597 | 0.151 | 0.334 |

ToQD 在 Hits@10 和 MAP@10 最优，但 MRR@10 低于 HyDE；这说明“覆盖更多相关证据”和“第一条相关证据排得更靠前”并不总是同步改善。

### 4.4 KG-CQR

[KG-CQR](https://aclanthology.org/anthology-files/pdf/emnlp/2025.emnlp-main.824.pdf)使用 mAP 与 Recall@5/10/25，和官方 any-hit Hits@K 不是同一指标：

| 方法 | mAP | R@5 | R@10 | R@25 |
|---|---:|---:|---:|---:|
| BM25 | 0.241 | 0.261 | 0.353 | 0.486 |
| DPR | 0.099 | 0.125 | 0.183 | 0.284 |
| BGE | 0.227 | 0.251 | 0.357 | 0.520 |
| QE + BM25 | 0.124 | 0.135 | 0.187 | 0.256 |
| QE + DPR | 0.058 | 0.069 | 0.101 | 0.169 |
| QE + BGE | 0.139 | 0.147 | 0.211 | 0.313 |
| HyDE + DPR | 0.106 | 0.127 | 0.188 | 0.297 |
| HyDE + BGE | 0.232 | 0.256 | 0.363 | 0.524 |
| **KG-CQR + BM25** | **0.250** | **0.267** | **0.372** | **0.532** |
| KG-CQR + DPR | 0.129 | 0.157 | 0.224 | 0.340 |
| KG-CQR + BGE | 0.240 | 0.261 | 0.371 | 0.525 |

### 4.5 ToR-Lite

[ToR-Lite](https://www.mdpi.com/2076-3417/16/8/3966)明确排除 301 个 null 问题，在 2,255 题上采用语义切块、BGE-base-en-v1.5、Cohere reranker 和 Qwen3-30B-A3B。其主判分是严格 normalized EM，Hits@10 则表示 top-10 内至少出现一条 gold evidence。

论文公开文本主要报告相对增益：相对 baseline，ToR-Lite 的 Hits@10 提升 **6.03 个百分点**、EM 提升 **0.89 个百分点**；三子问题版本提升 **7.00 / 1.55 个百分点**。Comparison 类型的 Hits@10 与 EM 分别提升 **8.39 / 1.40 个百分点**。它比 LLM-based Adaptive ToR 快约 **3.18 倍**，但后者的效果增益更大。

## 5. 后续端到端问答结果明细

### 5.1 MemTree：记忆式系统

[MemTree](https://proceedings.iclr.cc/paper_files/paper/2025/file/0382cb76309820f71c6eacd47b36ce71-Paper-Conference.pdf)只列出 inference、comparison、temporal 三类，因而可推断其总体分数未包含 null 类：

| 方法 | Accuracy | 构建/插入 LLM calls |
|---|---:|---:|
| RAPTOR | **81.0%** | 3,753 |
| GraphRAG | 78.3% | 3,858 |
| MemoryStream | 74.7% | 1 / insertion |
| MemTree | 80.5% | 3.27 ± 2.38 / insertion |

MemTree 的模型消融如下：

| 构建模型与 embedding | Inference | Comparison | Temporal | Overall |
|---|---:|---:|---:|---:|
| GPT-4o + text-embedding-3-large | 96.0 | 73.9 | 68.4 | **80.5** |
| GPT-4o-mini + text-embedding-3-small | 94.6 | 71.3 | 66.0 | 78.4 |
| Llama-3.1-8B + text-embedding-3-small | 94.9 | 71.0 | 65.0 | 78.1 |

### 5.2 图 RAG：ArchRAG、TopoRAG、QCG-RAG

[ArchRAG](https://ojs.aaai.org/index.php/AAAI/article/download/38619/42581)使用“生成中是否包含 gold answer”风格的 Accuracy / Recall：

| 方法 | Accuracy | Recall |
|---|---:|---:|
| Zero-shot | 47.7 | 23.6 |
| CoT | 54.5 | 28.7 |
| BM25 | 37.6 | 19.4 |
| Vanilla RAG | 58.6 | 31.4 |
| RAPTOR | 59.1 | 34.1 |
| HippoRAG | 38.9 | 19.1 |
| LightRAG（local） | 44.1 | 25.1 |
| LightRAG（hybrid） | 50.3 | 30.3 |
| GraphRAG（global） | 45.9 | 28.4 |
| **ArchRAG** | **68.8** | **37.2** |

[TopoRAG](https://aclanthology.org/2026.findings-acl.1703.pdf)在自己的 GPT-3.5-turbo / text-embedding-small 环境中复现 ArchRAG 时仅得到 58.2 / 27.1，和 ArchRAG 原论文的 68.8 / 37.2 相差很大。这是“同名方法结果也依赖实现与模型配置”的典型例子：

| 方法 | Accuracy | Recall | 时间/题 | Tokens/题 |
|---|---:|---:|---:|---:|
| Vanilla RAG | 54.7 | 19.5 | 2.40s | 3.6k |
| RAPTOR | 59.9 | 27.6 | 3.20s | 3.2k |
| HippoRAG | 39.4 | 19.6 | 3.50s | 3.3k |
| LightRAG | 46.1 | 25.5 | 19.3s | 5.8k |
| GraphRAG（local） | 40.6 | 23.3 | 3.00s | 6.1k |
| GraphRAG（global） | 46.4 | 27.9 | 36.9s | 9.3k |
| ArchRAG（复现） | 58.2 | 27.1 | 2.58s | 6.0k |
| **TopoRAG** | **61.2** | **28.3** | **1.88s** | 4.8k |

TopoRAG 的 chunk 增强消融可达到 64.1 Accuracy，但这不是其基础配置的主结果。

[QCG-RAG](https://arxiv.org/html/2509.21237)采用 1,200-token chunk、100-token overlap、top-5、约 6,000-token 上下文和 all-MiniLM embedding，并由 Qwen2.5-72B 参与查询图构建及语义判分：

| 方法 | Overall | Inference | Comparison | Temporal | Null |
|---|---:|---:|---:|---:|---:|
| Naive RAG | 75.80 | 93.46 | 66.85 | 68.00 | 71.21 |
| D2QRAG | 76.20 | 92.81 | 69.61 | 66.00 | 71.21 |
| D2Q-RAG | 76.80 | 92.16 | 67.96 | 70.00 | 75.76 |
| GraphRAG | 67.20 | 81.05 | 64.09 | 66.00 | 45.45 |
| LightRAG | 72.20 | 94.12 | 71.82 | 59.00 | 42.42 |
| MiniRAG | 60.40 | 75.16 | 54.70 | 54.00 | 51.52 |
| KG-Retriever | 47.60 | 79.08 | 19.89 | 33.00 | 72.73 |
| **QCG-RAG** | **79.60** | 93.46 | **74.59** | 69.00 | **77.27** |

该表的高分部分来自更长 chunks、更小 top-k、强模型和 LLM judge 的组合，不能直接与原论文 GPT-4 的 0.56 对比。

### 5.3 Agentic / 交互式系统：Interact-RAG 与 AutoAgent

[Interact-RAG](https://openreview.net/pdf?id=yHUjWb6eMe)每个数据集抽取 500 个问题，并使用经过 SFT/RL 训练的 7B/8B 模型：

| 方法 | EM | F1 |
|---|---:|---:|
| Standard RAG 7B | 57.5 | 59.4 |
| MA-RAG 7B | 50.2 | 52.3 |
| Search-R1 7B | 73.0 | 74.1 |
| **Interact-RAG 7B** | **79.4** | **80.4** |
| Standard RAG 8B | 63.4 | 65.1 |
| MA-RAG 8B | 66.3 | 68.7 |
| **Interact-RAG 8B** | **81.4** | **82.3** |

[AutoAgent](https://aclanthology.org/2026.findings-acl.2129.pdf)使用 gpt-4o-mini、text-embedding-3-small、256-token chunks 和 top-6。其 Accuracy 是回答与期望答案的语义一致性，“Error”统计自信但错误的回答：

| 方法 | Accuracy | Error |
|---|---:|---:|
| NaiveRAG | 53.36 | 12.28 |
| HyDE | 56.59 | 16.55 |
| MiniRAG | 57.81 | 34.78 |
| LightRAG | 58.18 | 35.40 |
| LangChain agent | 62.83 | 20.50 |
| **AutoAgent** | **73.51** | **14.20** |

### 5.4 eGoT

[eGoT](https://pmc.ncbi.nlm.nih.gov/articles/PMC13341121/)对每个任务随机抽取 1,000 个问题/段落，图构建使用 LLaMA-4 Scout，问答和检索使用 GPT-4o：

| 方法 | Precision | Recall | F1 | Accuracy |
|---|---:|---:|---:|---:|
| Naive RAG | 47.5 | 59.9 | 50.1 | 60.4 |
| GraphRAG | 50.1 | 61.8 | 52.6 | 65.3 |
| LightRAG | 44.8 | 52.7 | 46.4 | 52.6 |
| PathRAG | 45.3 | 52.3 | 46.8 | 52.5 |
| HyperGraphRAG | 50.3 | 61.9 | 52.6 | 62.1 |
| TH-RAG | 71.1 | 72.0 | 71.2 | 72.2 |
| **eGoT** | **75.5** | **79.2** | **76.3** | **79.1** |

这同样是抽样且自定义判分的结果，适合比较该论文同一表内的方法，不适合加入官方排行榜。

## 6. 其他采用数据集的工作

### 6.1 Writing in the Margins

[Writing in the Margins](https://arxiv.org/abs/2408.14906)从 MultiHop-RAG 中选取最长的 100 个样本，构造 13k–32k 长上下文实验。论文报告在 HotpotQA 与 MultiHop-RAG 的 reasoning skills 聚合结果上平均提升约 7.5%，相对普通 RAG 约提升 9%。由于公开摘要和主表没有给出可独立抽取的完整 MultiHop-RAG 全集成绩，本文不把它列入数值排名。

### 6.2 RAP-RAG

[RAP-RAG](https://www.mdpi.com/2079-9292/14/21/4269)研究关系感知路径增强，使用 gpt-4o-mini / text-embedding-3-small 以及小模型配置。论文总结其总体上较 MiniRAG 高约 3–5 个百分点；在 MultiHop-RAG 上移除关系权重后，Llama-3.2-3B 和 Qwen2.5-1.5B 分别下降 5.7 和 6.1 个百分点。由于网页可访问文本中的 57.52% 等绝对值没有足够清晰地隔离出数据集、模型和表格列，本文仅保留能够确定语境的消融结论。

### 6.3 Probe, Don’t Prompt

[Probe, Don’t Prompt](https://arxiv.org/abs/2607.03929)使用全部 2,556 个问题，但任务是预测 source/date 元数据过滤集合，不是回答问题。其 set-exact accuracy 为：

| 方法 | 过滤集合 exact accuracy |
|---|---:|
| GPT-3.5 prompting | 80.9% |
| substring baseline | 88.0% |
| **probe** | **90.9%** |

论文指出主要增益来自 null 问题，非 null 问题上各方法相差约 1 个百分点。这项结果支持“元数据路由可以低成本实现”，但不能解读为 90.9% 的 RAG 问答准确率。

## 7. 为什么这些数字不能直接横比

### 7.1 测试集不同

- 原始检索评测使用 2,255 个非空问题；完整数据集有 2,556 题。
- WiM 只取最长的 100 题；Interact-RAG 每个数据集取 500 题；eGoT 随机取 1,000 题。
- 部分论文不报告是否包含 301 个 null 问题。null 类通常更依赖拒答和检索校准，纳入与否会显著改变总体准确率。

### 7.2 检索空间和上下文预算不同

- 原论文是 256-token chunks、top-20 候选、重排后 top-10。
- QCG-RAG 使用 1,200-token chunks、100-token overlap、top-5 和最多约 6,000 tokens。
- AutoAgent 使用 top-6；KG-CQR 报到 Recall@25。
- 元数据过滤、图构建和离线摘要都会改变实际候选空间，不能只看最后的 top-k。

### 7.3 “Accuracy”并不是一个统一指标

文献中至少出现了以下判分方式：

- 原论文人工/脚本式 accuracy；
- 当前官方仓库的“预测与答案存在 token 交集”；
- strict normalized exact match；
- 回答字符串是否包含 gold answer；
- 模型生成的语义一致性分；
- Qwen2.5-72B 等 LLM judge；
- EM/F1 的 token overlap；
- 辅助元数据集合的 set-exact match。

同样写作 “Accuracy 80%”，可能分别意味着严格全串匹配、宽松包含、语义裁判或不同样本子集。

### 7.4 Hits@K 不能代表完成多跳证据链

原始 Hits@K 只要求命中任意一条 gold evidence。一个需要 4 条证据的问题，只检索到其中 1 条仍会得到 hit。因此建议把它称为 **Any-evidence Hits@K**，并同时报告：

- `Evidence Recall@K = 命中的 gold evidence 数 / gold evidence 总数`；
- `All-evidence Success@K = 是否找齐全部 gold evidence`；
- 每题平均 evidence recall；
- 按 2-hop、3-hop、4-hop 分层的成功率。

### 7.5 生成模型和系统成本不同

GPT-4、GPT-4o、GPT-3.5、Qwen2.5-72B 与 7B/8B 训练后模型的能力不可视为常量；有些方法还在索引期调用数千次 LLM。只报告准确率会掩盖延迟、token、索引成本和训练数据投入。

## 8. 对“当前测试水平”的建议理解

### 8.1 检索

以原论文协议附近的工作为参照：

| 水平 | Any-evidence Hits@4 | Any-evidence Hits@10 | 说明 |
|---|---:|---:|---|
| 基础 dense retrieval | 约 0.46–0.52 | 约 0.64–0.67 | 原论文强 embedding、无重排 |
| 成熟 embedding + reranker | 约 0.62–0.66 | 约 0.71–0.75 | 原论文最强基线 |
| 强问题分解/元数据增强 | 约 0.75–0.79 | 约 0.87–0.90 | 后续论文自报；协议需逐项复核 |

由于 Hits 是 any-hit，**0.90 的 Hits@10 不代表 90% 的问题已经收齐全部多跳证据**。如果改成 all-evidence success，合理预期会明显下降，但现有论文很少统一报告这个数字。

### 8.2 端到端问答

| 评测族 | 常见报告区间 | 如何解读 |
|---|---:|---|
| 原论文检索上下文生成 | 28%–56% | 2024 年模型与原始检索协议 |
| 原论文 gold evidence | 32%–89% | 主要反映生成器上限 |
| 现代图/记忆 RAG | 约 58%–81% | 模型、索引和判分协议差异很大 |
| agentic / 训练后系统子集 | 约 73%–82% | 常是 500–1000 题或自定义 judge |

因此，若一个新系统报告 MultiHop-RAG Accuracy 75%，仅凭这个数字无法判断是否超过已有方法。至少还需要知道：测试题数、是否包含 null、生成模型、chunk/top-k、检索器、是否重排、判分代码、是否使用 LLM judge，以及是否有训练或索引期 LLM 调用。

## 9. 建议采用的统一复现协议

为了同时兼容历史结果和真正的多跳能力，建议把评测拆成四层。

### 9.1 数据与切分

- 固定官方 2,556 题，并分别报告 2,255 个非空问题和 301 个 null 问题。
- 报告 inference / comparison / temporal / null 四类结果。
- 固定语料版本，公开 chunk size、overlap、chunk 数量及文档到 chunk 的映射。

### 9.2 检索指标

- 为兼容历史：MRR@10、MAP@10、官方 Any-evidence Hits@4/10。
- 为衡量多跳：Evidence Recall@4/10、All-evidence Success@4/10。
- 为分析链路：按 gold evidence 数量 2/3/4 分层报告。
- 对 null 问题：报告无检索/拒答的 precision、recall、F1，而不是直接剔除。

### 9.3 生成指标

- strict normalized EM；
- token-level F1；
- 含义等价的 LLM judge，但必须公开 judge 模型、prompt、温度和重复判分一致率；
- 同时报告 gold-evidence oracle，以分离检索错误和生成错误。

### 9.4 效率指标

- 在线延迟 p50/p95；
- 每题输入/输出 tokens；
- 检索、重排、问题分解和生成分别计时；
- 索引构建时间、存储量和索引期 LLM calls；
- 使用商业 API 时给出按题成本。

建议主表只比较在**同一语料、同一问题集合、同一生成器、同一 evaluator**下复现的方法；论文原始自报结果单独放在“文献参考”表中。

## 10. 文献清单

### 原始论文

- Yixuan Tang, Yi Yang. [MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries](https://openreview.net/pdf?id=t4eB3zYWBK). COLM 2024. [arXiv](https://arxiv.org/abs/2401.15391)；[代码与数据](https://github.com/yixuantt/MultiHop-RAG)。

### 后续明确使用该数据集并报告结果的工作

- Poliakov, Shvai. [Multi-Meta-RAG](https://arxiv.org/abs/2406.13213). 2024.
- [Writing in the Margins: Better Inference Pattern for Long Context Retrieval](https://arxiv.org/abs/2408.14906). 2024.
- [Topology-of-Question-Decomposition: Enhancing Large Language Models with Information Retrieval for Knowledge-Intensive Tasks](https://aclanthology.org/2025.coling-main.191.pdf). COLING 2025.
- [Question Decomposition for Retrieval-Augmented Generation](https://aclanthology.org/2025.acl-srw.32.pdf). ACL SRW 2025.
- [KG-CQR: Knowledge Graph-Enhanced Contextual Query Reformulation for Retrieval-Augmented Generation](https://aclanthology.org/anthology-files/pdf/emnlp/2025.emnlp-main.824.pdf). EMNLP 2025.
- [MemTree: A Tree-Based Long-Term Memory Framework for Large Language Models](https://proceedings.iclr.cc/paper_files/paper/2025/file/0382cb76309820f71c6eacd47b36ce71-Paper-Conference.pdf). ICLR 2025.
- [RAP-RAG](https://www.mdpi.com/2079-9292/14/21/4269). *Electronics*, 2025.
- [QCG-RAG](https://arxiv.org/html/2509.21237). 2025 preprint.
- [ArchRAG](https://ojs.aaai.org/index.php/AAAI/article/download/38619/42581). AAAI 2026.
- [TopoRAG](https://aclanthology.org/2026.findings-acl.1703.pdf). Findings of ACL 2026.
- [ToR-Lite](https://www.mdpi.com/2076-3417/16/8/3966). *Applied Sciences*, 2026.
- [Interact-RAG](https://openreview.net/pdf?id=yHUjWb6eMe). ICLR 2026.
- [eGoT](https://pmc.ncbi.nlm.nih.gov/articles/PMC13341121/). *Bioinformatics*, 2026.
- [AutoAgent](https://aclanthology.org/2026.findings-acl.2129.pdf). Findings of ACL 2026.
- [Probe, Don’t Prompt](https://arxiv.org/abs/2607.03929). 2026 preprint.

## 11. 调研范围与限制

本次检索以论文标题、全文中的 “MultiHop-RAG” 精确匹配及论文引用链为主，优先使用 OpenReview、ACL Anthology、AAAI、ICLR Proceedings、期刊官网、arXiv 和作者代码仓库。纳入标准是论文正文明确使用该数据集进行实验，并能抽取至少一项定量结果；只在 related work 中引用数据集的论文未进入主表。

这不是一个保证零遗漏的系统综述：2026 年的新预印本、仅在代码仓库或附录中出现的数据、以及搜索引擎尚未完整索引的论文可能缺失。另有少数论文只公开相对增益或聚合结果，本文已明确标为不可直接比较，而没有反推不存在的绝对值。

> AI 使用说明：本文由 AI 辅助完成文献检索、表格抽取、指标归一和初稿撰写；关键数字均回指论文或官方代码，但在用于正式发表、采购决策或对外宣称 SOTA 前，仍建议由人工逐页复核原表、脚注与评测代码。
