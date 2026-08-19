# MOI RAG BENCHMARK RESULTS

> date: 2026-08-07

## 摘要

本轮围绕 WikiEval 和 MMDocIR，对 MOI 与本地 Dify 的 RAG 能力进行了三组评估，分别覆盖通用文本 RAG、长文档多模态证据检索和检索增强问答质量。WikiEval 50 题中，两套系统的 Source Recall@1/3/5 均为 100%，MRR 均为 1.000；RAGAS 诊断显示，Dify 的 Faithfulness 和 Context Precision 较高，MOI 的 Answer Relevance 和 Context Recall 较高。MMDocIR 检索实验中，MOI 在全部 Page Recall 和 Layout Recall 截点上优于 Dify，其中差距主要集中在 Page R@3 和 Layout R@1；但与论文中的最佳级联检索方法相比，在高截点覆盖和细粒度布局定位上仍有提升空间。

MMDocIR QA 实验中，Dify 的 Answer Correctness、Token F1 和 Faithfulness 小幅高于 MOI，两者的 LLM judge 得分均位于表中两个 MMDocRAG 论文参考结果之间。由于 WikiEval 数据和原论文模型年代较早，MMDocIR 与论文参考行的协议并不完全一致，同时部分平台延迟仍未记录，因此本文结果主要用于当前冻结配置下的工程诊断和能力对比，不作为跨版本、跨模型或跨协议的最终平台排名。FastGPT 和 MaxKB 的本地完整评测尚未完成，暂不纳入结果表。

## 数据集使用

### WikiEval（from RAGAS，ACL 2024）

RAGAS 的研究动机是解决 RAG 系统难以低成本、自动化评估的问题：端到端回答质量同时受到检索器、上下文和生成模型影响，而依赖人工参考答案或人工逐项打分的评测方式成本较高，也难以持续回归。论文将 RAGAS 定位为第一个面向 RAG 系统的自动化评估框架，希望在不依赖人工参考答案的条件下，把系统质量拆成可独立诊断的指标。

WikiEval 是 RAGAS 论文为验证自动指标与人工判断的一致性而构建的小型英文评测集。作者从近期编辑过的 50 个 Wikipedia 页面构造中等难度问题、上下文和回答，并进一步生成受控的低质量答案或带噪上下文；两位人工标注者分别判断 faithfulness、answer relevance 和 context relevance。 WikiEval 适合快速跑通 MOI 和竞品的统一 ingest、retrieval、generation、judge 与 artifact 链路。它可以评估 MOI 的基础文档召回、证据覆盖、回答切题性、上下文忠实度和查询延迟，也适合作为配置变更后的回归集。

本轮使用的本地冻结快照包含 50 行、50 个 unique source；parquet SHA-256 为 `6846376fbdb40ee5b9903f84d002fabf8194c92f2a32f2d8bfb1112b091bbf80`。上游数据页为 [vibrantlabsai/wiki-eval](https://huggingface.co/datasets/vibrantlabsai/wiki-eval)，本地 manifest 位于 `runs/stage1/ragas-wikieval-moi/20260807-160000-wikieval/artifacts/dataset_manifest.json`。

### MMDocIR（Huawei，NeurIPS 2026）

MMDocIR 面向长文档多模态检索。论文指出，既有文档检索数据常来自单页 VQA、文档较短，且通常只标“相关页面”，无法判断系统是否定位到页面中的表格、图片、图表、公式或段落。因此它把任务拆成 page-level retrieval 和 layout-level retrieval：前者在长文档中找出包含答案证据的页面，后者进一步找出页内的具体证据区域。MMDocIR 的评测语料来自 MMLongBench-Doc 和 DocBench。作者先从两个数据集中整理出 364 篇文档和 2,193 个问题，再过滤不适合信息检索的问题、修订答案与页面标签，并补充页面级和布局级证据标注，形成最终评测集。训练集则汇集 MP-DocVQA、SlideVQA、TAT-DQA、arXivQA、SciQAG、DUDE 和 CUAD 七个数据集，并通过原文档追溯及半自动流程补全页面或布局标签。

官方评测集包含 313 篇长文档、1,658 个问题、2,107 个页面标签和 2,638 个布局标签，覆盖 10 个领域，并包含跨页、跨布局和跨模态问题。本项目选择它，是为了评估 MOI 对长 PDF 的索引能力、文档内候选约束、页级召回、bbox/layout 级证据定位，以及不同表示方式带来的效果—延迟权衡。当前使用 `bge-m3 + VLM-text` 的 adapted protocol.

## 实验配置与指标说明

### 通用记录原则

- 评测系统固定为 MOI、Dify、FastGPT 和 MaxKB；每一行同时记录系统版本、部署方式、模型 provider、embedding/LLM、切分参数、Top-K、数据哈希和配置哈希。
- 同一可比表内使用相同问题集、候选范围和计分函数。平台原生切分或接口限制无法统一时，单独标记为 `vendor-native` 或 `adapted`，不与受控协议混排。
- `attempted`、`valid`、`failed`、`empty` 和 `not started` 分别计数。重试保留为额外 attempt，不覆盖初次失败；无法评分的单元写明原因。
- 质量指标与性能指标分开解读。延迟至少记录 P50/P95，并说明计时边界；成功率或低延迟不能补偿低召回，反之亦然。
- 结果必须能够回溯到逐题 ledger、原始检索 chunk/marker、回答、引用字段及 SHA-256 sidecar。引用只读取平台返回的结构化字段，不从答案文本中猜测。

### 实验一：WikiEval RAG 评估

**评估目标**：衡量各系统在通用文本问答中的端到端 RAG 能力，包括是否召回正确来源、回答是否得到检索上下文支持、是否切合问题、上下文是否聚焦，以及检索链路的稳定性和延迟。

该实验将 WikiEval 的检索和 RAGAS 评估拆成确定性主指标与 judge 诊断两层。适配器从冻结的 WikiEval parquet 中选取 50 行，将 `source` 映射为文档、`question` 映射为查询、`grounded_answer` 映射为参考答案与 evidence。MOI 使用 512-token chunk、50-token overlap、TaaS `bge-m3` embedding 和 `qwen3.6-flash` generation；Dify 使用本地 app 的 vendor-native knowledge-base pipeline，固定同一批 50 个文档/问题并将 top-k 设为 10，但不假设其切分和计时边界与 MOI 相同。FastGPT 和 MaxKB 本轮未通过可比运行门禁，因此跳过。MOI 的 RAGAS judge 使用 TaaS `deepseek-v4-flash`，judge embedding 使用 `bge-m3`，temperature 为 0；本轮只对 MOI 运行 Ragas judge，Dify 记录同集确定性适配器指标。

沿用原论文记号：问题为 $q$，检索上下文为 $c(q)$，系统回答为 $a_s(q)$。回答被拆成的陈述集合记为 $S(a_s(q))$，其中可由上下文支持的陈述集合记为 $V$。Faithfulness 定义为：

\[
F=\frac{|V|}{|S(a_s(q))|}.
\]

Answer Relevance 根据回答生成 $n$ 个可能的问题 $q_i$，用 $e(\cdot)$ 表示 embedding，$\operatorname{sim}(\cdot,\cdot)$ 表示余弦相似度，其得分为：

\[
AR=\frac{1}{n}\sum_{i=1}^{n}\operatorname{sim}\bigl(e(q),e(q_i)\bigr).
\]

Context Relevance 先从上下文中抽取能够帮助回答问题的相关句子。设相关句子数为 $N_{\mathrm{rel}}$，上下文总句子数为 $N_{\mathrm{all}}$，则：

\[
CR=\frac{N_{\mathrm{rel}}}{N_{\mathrm{all}}}.
\]

三个指标均在 $[0,1]$ 区间，数值越高分别表示回答越受上下文支持、越切合问题、检索上下文越集中。本轮 Ragas 0.2.15 直接记录 Faithfulness、Answer Relevancy、Context Precision 和 Context Recall；原论文的 Context Relevance 未在当前 judge 结果中单独实现，因此结果表中单列标记为 `N/A`，不把 Precision/Recall 改名为 Context Relevance。Source Recall@K 表示前 K 个结果中是否出现 gold source 的问题比例；MRR 为每题第一个 gold source 排名倒数的平均值，未命中记 0。judge 失败保留为空值，并单独报告有效分母。

### 实验二：MMDocIR 检索效果

**评估目标**：衡量各系统在长文档、多模态和复杂版面场景中的证据定位能力，分别观察能否召回正确页面、能否进一步定位页内布局区域，以及页面轨和布局轨的检索效率。

该实验同时比较 MOI、Dify、FastGPT 和 MaxKB 的证据检索能力，并严格遵循 MMDocIR“每个 query 只在其所属长文档内检索”的候选范围。页面轨使用 VLM-text page candidate，布局轨使用带 page、layout type 和 bbox 的 layout candidate；统一采用 TaaS `bge-m3` embedding，不启用 rerank，页面返回 Top-5，布局返回 Top-10。MOI 当前页面轨包含 20,395 个候选，布局轨包含 170,338 个候选。竞品若暂不支持 layout candidate 或文档内候选约束，对应指标记为 `N/A`，不得改用不同协议的结果补位。

设问题集合为 $Q$，问题 $q$ 的 gold page 集合为 $G_q^{p}$，Top-K 检索页面集合为 $R_{q,K}^{p}$。原论文的 Page Recall@K 为：

\[
R_{\mathrm{page}}@K=\frac{1}{|Q|}\sum_{q\in Q}\frac{|R_{q,K}^{p}\cap G_q^{p}|}{|G_q^{p}|},\qquad K\in\{1,3,5\}.
\]

对于布局检索，设问题 $q$ 的 gold bbox 集合为 $G_q^{l}$，Top-K 预测 bbox 集合为 $R_{q,K}^{l}$，$A(b)$ 表示框 $b$ 的面积。只有预测框与 gold 框位于同一页时才计算交集，原论文的 overlap-area Layout Recall@K 为：

\[
R_{\mathrm{layout}}@K=\frac{1}{|Q|}\sum_{q\in Q}
\frac{\sum_{r\in R_{q,K}^{l}}\sum_{g\in G_q^{l}}\mathbf{1}[\operatorname{page}(r)=\operatorname{page}(g)]A(r\cap g)}
{\sum_{g\in G_q^{l}}A(g)},\qquad K\in\{1,5,10\}.
\]

此外分别记录 10 个领域等权平均的 Macro-domain Recall、有效 query 数以及检索延迟 P50/P95。空文本候选在 embedding 输入端使用不可见占位符，但数据库保留原始空内容，该预处理随结果披露。

### 实验三：MMDocIR QA 质量

**评估目标**：衡量检索结果进入生成阶段后的端到端问答能力，区分答案是否正确、是否覆盖参考答案、是否忠实使用检索证据，以及完整 QA 链路的成功率和延迟。

MMDocIR 原论文只定义检索任务；本实验是在其 gold answer 和证据标注之上增加的下游 QA 扩展，不作为论文官方指标。四个系统均取各自检索到的 Top-10 页面上下文，使用相同的 TaaS `deepseek-v4-flash`、prompt、上下文预算和输出限制生成回答；每题保留检索页、page marker 和生成答案。若平台无法导出检索上下文，则该系统不进入 controlled QA 对比，相关字段记为 `N/A`。

设生成答案为 $a_q$，参考答案为 $y_q$，规范化 token 集合为 $T(a_q)$ 和 $T(y_q)$。Token Precision、Token Recall 与 Token F1 定义为：

\[
P_q=\frac{|T(a_q)\cap T(y_q)|}{|T(a_q)|},\qquad
R_q=\frac{|T(a_q)\cap T(y_q)|}{|T(y_q)|},\qquad
F1_q=\frac{2P_qR_q}{P_q+R_q}.
\]

最终 Token F1 对全部有效问题取平均。Answer Correctness 由冻结的 judge 根据问题、参考答案和生成答案给出二元判断 $J_q\in\{0,1\}$，总体得分为 $\frac{1}{|Q|}\sum_{q\in Q}J_q$。Faithfulness 沿用实验一的陈述支持比例。另记录回答成功率和端到端 QA 延迟 P50/P95。

## 竞品说明

- [Dify](https://dify.ai/) 是一个用于构建生成式 AI 应用的开源平台。根据官网介绍，它把模型接入、Prompt 编排、RAG Pipeline、Agent、低代码 Workflow、应用发布和可观测性整合在同一工作空间中，既可以通过知识库为回答补充外部信息，也可以在可视化流程中组合模型调用、知识检索、工具、代码和条件分支。

- [FastGPT](https://fastgpt.io/en) 是一个基于大语言模型的知识库问答和 AI Agent 构建平台。官网重点介绍了企业知识库、RAG 检索、可视化低代码工作流和 API 集成能力：知识库为回答提供依据，Workflow 用于编排固定业务流程，Agent 则面向需要自主规划和执行的开放任务。

- [MaxKB](https://maxkb.cn/docs/v2/) 是一个用于构建企业级智能体的开源平台。官网将其核心能力概括为 RAG 知识库、工作流和 MCP 工具调用，并支持把企业文档组织为可检索知识，使智能体能够基于内部资料完成问答和业务任务。

结果表中的“论文参考”行不是可部署的竞品平台，而是用于帮助判断 MOI 与三个竞品结果所处位置的研究基线。WikiEval 引用 RAGAS 论文的 pairwise accuracy；MMDocIR 检索引用论文的 micro Recall；MMDocIR QA 则引用下游 MMDocRAG 的端到端结果。由于数据、协议和指标定义并不完全相同，这些行只作参考，不参与平台排名。

FastGPT 既有 smoke 为 service/ingest/retrieval 成功但 native QA 持续超时；MaxKB 既有 smoke 的 ingest 状态语义未验证、native 回答未消费问题，且没有稳定的 public direct-retrieval contract。两者后续只有在 ingest、direct retrieval、native QA 三段式门禁都通过后，才补入同一结果。

## 结果

### 实验一：WikiEval RAG 评估

| RAG 对象 | Source R@1 | Source R@3 | Source R@5 | MRR | Faithfulness | Answer Relevance | Context Relevance | Context Precision | Context Recall | Retrieval P50/P95 | 状态 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| MOI | 100.0% | 100.0% | 100.0% | 1.000 | 0.9637 | 0.9309 | N/A | 0.7406 | 0.9927 | 1553.5/4458.3 ms（retrieval） | deterministic + Ragas 完成 |
| Dify | 100.0% | 100.0% | 100.0% | 1.000 | 0.9938 | 0.9123 | N/A | 0.8015 | 0.8817 | N/A|deterministic + Ragas 完成 |
| 论文参考：RAGAS | N/A | N/A | N/A | N/A | 0.95 | 0.78 | 0.70 | N/A | N/A | N/A | Table 4 pairwise accuracy |
| 论文参考：GPT Score | N/A | N/A | N/A | N/A | 0.72 | 0.52 | 0.63 | N/A | N/A | N/A | Table 4 pairwise accuracy |

> 参考性说明：RAGAS 原论文使用 `gpt-3.5-turbo-16k` 作为评估模型、`text-embedding-ada-002` 计算 Answer Relevance，而本实验调用的是更新的 `deepseek-v4-flash` 和 `bge-m3`，模型能力及评分行为已经发生明显变化。WikiEval 又主要基于较早期的 Wikipedia 页面和问题构建，相关内容可能已经进入新模型的预训练语料，页面本身也可能在后续持续更新。因此论文结果更适合作为历史方法参考，不能直接视为当前模型条件下的严格基线。


### 实验二：MMDocIR 检索效果

| RAG 对象 | Page R@1 | Page R@3 | Page R@5 | Layout R@1 | Layout R@5 | Layout R@10 | Retrieval P50/P95 | 状态 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| MOI | 56.17 | 71.83 | 75.83 | 28.02 | 52.70 | 61.87 | page 430.38/2194.90 ms；layout 284.88/407.21 ms | Page R@10=84.50 |
| Dify | 53.51 | 67.00 | 72.59 | 21.03 | 50.77 | 59.98 | N/A | Page R@10=78.00 |
| 论文参考：Col-Phi3 → ColBERT | 57.1 | 76.8 | 83.0 | 35.3 | 58.8 | 65.4 | N/A | cascade；micro Recall |
| 论文参考：DPR-Phi3 → ColBERT | 53.7 | 74.3 | 81.8 | 30.6 | 56.6 | 64.5 | N/A | cascade；micro Recall |

> MOI 在 Page Recall 和 Layout Recall 的全部报告截点上均高于 Dify。页级差距为 2.66、4.83 和 3.24 个百分点，布局级差距为 6.99、1.93 和 1.89 个百分点；差距主要集中在 Page R@3 和 Layout R@1。与论文参考方法相比，MOI 的 Page R@1 已接近 Col-Phi3 → ColBERT，但 Page R@3/R@5 和布局召回仍有差距，说明高排名候选的覆盖与细粒度区域定位仍有提升空间。Dify 未记录检索延迟，因此当前只能比较召回效果，不能据此比较两个系统的检索效率。


### 实验三：MMDocIR QA 质量

| RAG 对象 | Answer Correctness | Token F1 | Faithfulness | QA P50/P95 | 状态 |
|---|---:|---:|---:|---:|---|
| MOI | 3.98/5（LLM judge） | 0.1231 | 0.75 | 15541.10/25871.89 ms | contains gold=0.34，normalized EM=0.02 |
| Dify | 4.02/5（LLM judge） | 0.1651 | 0.79 | N/A | contains gold=0.58，normalized EM=0.04 |
| 论文参考：GPT-4.1 + Perfect Retriever | 4.14/5（LLM judge） | N/A | N/A | N/A | MMDocRAG upper bound；BLEU 0.157，ROUGE-L 0.313 |
| 论文参考：GPT-4.1 + Multi-retriever / Clauses | 3.79/5（LLM judge） | N/A | N/A | N/A | MMDocRAG；BLEU 0.141，ROUGE-L 0.303 |

> Dify 的 Answer Correctness、Token F1 和 Faithfulness 分别比 MOI 高 0.04 分、0.0420 和 0.04，当前结果表现为小幅领先；两者的 Answer Correctness 均处于表中两个论文参考值之间。但论文行来自 MMDocRAG，数据、检索条件和评审协议与本实验并不完全一致，只能用于观察大致区间，不能直接据此判断是否达到或超过论文方法。同时 Dify 缺少 QA 延迟，性能侧也不能进行公平对比。


## 计划

1. 引入 EnterpriseRAG-Bench、FAB-Bench 等更面向企业知识和垂直领域的数据集，继续评估多文档检索、专业问题、多跳推理、冲突信息处理和完整性回答等能力。
2. 持续搜集真实企业与垂直领域语料，建立统一、可迭代且有针对性的自建 benchmark；固定数据版本、题型、gold evidence、评分规则和回归集，并根据线上失败案例持续补充测试样本。
3. 完善FastGPT, MaxKB的本地评估流程。
