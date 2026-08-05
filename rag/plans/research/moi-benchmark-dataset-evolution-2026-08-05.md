# MOI RAG Benchmark 数据集构建四次变动与来源目录

> 日期：2026-08-05
> 范围：梳理 MOI RAG Benchmark 数据集从初版到当前版本的四次调整，并记录每个数据集的论文、官方数据/代码入口、本地位置、基本介绍和计划用途。
> 术语：本文中的 MOI 特指 MatrixOrigin 的 MatrixOne Intelligence，不是 MoiAI。

## 1. 结论先行

这四次变化不是简单地“不断增加数据集”，而是评测对象发生了变化：

```text
通用 RAG 能力基线
    → 文档/PDF/多模态能力扩展
    → 从主评测中剥离过重的组件型数据
    → 面向企业、专业领域、噪声和中文场景的产品诊断
```

当前的最终分层口径是：

| 分层 | 数据集 | 当前定位 |
|---|---|---|
| 初版保留 | RGB、ALCE、RAGTruth、RAGBench、MultiHop-RAG | 通用 RAG、引用、幻觉、噪声和多跳能力的公开基线 |
| 第二版中保留 | MMDocIR、DocBench、MMDocRAG | 多模态检索、PDF 到回答、多模态端到端研究诊断 |
| 第三版退出主评测 | OmniDocBench、READoc、ViDoRe V2 | 仍保存在本地，但不再作为当前 MOI 主数据集；必要时只做解析/视觉检索专项回归 |
| 第四版新增 | EnterpriseRAG-Bench、FAB-Bench、MIRAGE、CMRC2018 | 企业文本、半导体领域、上下文噪声和中文基础能力诊断 |

“不用”在本文中指**退出当前主评测或正式产品结论的分母**，不等于删除本地文件。

## 2. 四次数据集构建变动

### 第一次：采用五个通用 RAG benchmark

**数据集：** RGB、ALCE、RAGTruth、RAGBench、MultiHop-RAG。

**为什么这样选：**

- 它们分别覆盖噪声与拒答、引用、幻觉、解释性 RAG、多跳检索等通用能力。
- 论文、官方代码和数据相对容易找到，社区已有一定复现基础。
- 可以先建立一个不依赖 MOI 特定产品界面的外部基线。

**暴露的问题：**

- 这五个数据集大多以 JSON/JSONL/Parquet 形式发布，问题、上下文或文章正文已经结构化。
- 它们通常不提供与原始 PDF 版式对应的完整 PDF corpus。
- 因此无法充分评估 MOI 的文件上传、解析、OCR、表格/公式恢复、页码定位和视觉证据能力。

这也是第二次扩展到文档和多模态 benchmark 的直接原因。

### 第二次：引入文档/PDF/多模态 benchmark

**新增数据集：** OmniDocBench、READoc、MMDocIR、ViDoRe V2、DocBench、MMDocRAG。

**为什么扩展：**

| 评测缺口 | 对应数据集 |
|---|---|
| PDF 解析、OCR、表格、公式、阅读顺序 | OmniDocBench、READoc |
| 页面级和布局级多模态检索 | MMDocIR |
| 视觉页面检索 | ViDoRe V2 |
| 原始 PDF 到文本回答 | DocBench |
| 跨页、跨模态证据和多模态回答 | MMDocRAG |

这一步把评测从“给定结构化上下文后能否回答”推进到更接近 MOI 产品链路的：

```text
原始 PDF/图像 → 解析 → 建索引 → 检索页面/布局 → 回答与引用
```

**这次扩展带来的代价：**

- 数据规模和磁盘占用明显增加，解压后的 `document-rag` 目录约 30 GiB。
- 各数据集任务定义不同，不能直接合并为一个总分。
- 需要分别适配 parser、retriever、reader 和 multimodal evidence evaluator。
- 部分数据集是 research-only、NC 或底层来源权利不清晰，不能直接作为商业发布主集。
- 长 PDF 的解析、图像处理和多模态检索成本显著高于第一版五个结构化数据集。

### 第三次：决定不用 OmniDocBench、ViDoRe V2、READoc

这里的“原因”是根据相关对话、旧三阶段计划、实验记录和后续 v1.0/source-readiness 计划综合还原；仓库中没有一份单独的决策日志逐字记录这次决定。

**核心原因不是这三个数据集质量差，而是它们不再适合当前主评测范围：**

1. **任务层级过于底层或单一。**
   - OmniDocBench 主要是 PDF 解析与结构识别。
   - READoc 主要是 PDF → Markdown 的文档结构化抽取。
   - ViDoRe V2 主要是视觉页面检索。
   它们不能直接代表一个 RAG 产品从入库到回答的整体能力。

2. **与当前主问题不完全匹配。**
   当前更关心 MOI 的企业知识库问答、证据、拒答、稳定性和产品可运营性，而不是单独建立一个完整的文档解析排行榜。

3. **成本和工程复杂度过高。**
   三者分别需要官方 parser scorer、Markdown 结构适配或视觉检索模型/索引，运行成本和适配成本会把主评测拖成多个独立项目。

4. **指标不可直接和 RAG 问答指标合并。**
   Edit Distance、TEDS、CDM、结构化抽取分数、nDCG/Recall 与答案正确率、引用覆盖率属于不同 estimand。把它们放进同一主榜容易制造一个没有解释性的综合分数。

5. **许可与发布边界更复杂。**
   这些数据适合作为研究诊断集，但不适合作为当前产品主榜或商业发布数据的唯一来源。

**因此当前处理方式是：**

- 不再把三者列入当前 MOI 主数据集构建和正式产品结论分母；
- 保留本地下载内容、论文和解析产物；
- 如果需要定位 parser 或视觉检索问题，仍可作为独立的 layered benchmark 使用。

### 第四次：引入 EnterpriseRAG-Bench、FAB-Bench、MIRAGE、CMRC2018

这次调整把重点从“覆盖更多文档技术组件”转向“更贴近产品使用场景的诊断问题”：

| 新数据集 | 引入的能力 |
|---|---|
| EnterpriseRAG-Bench | 大规模企业文本、问题类型、Gold 文档、Atomic Facts、无答案/冲突场景 |
| FAB-Bench | 半导体专业领域、Gold Context 与 Native/with-kb 对照诊断 |
| MIRAGE | Base/Oracle/Mixed 上下文敏感性和噪声鲁棒性 |
| CMRC2018 | 中文阅读理解、中文分词/Embedding/回答基础能力 |

**为什么更适合当前产品导向计划：**

- 能直接映射到企业知识库问答、专业领域问答、噪声干扰和中文用户问题。
- EnterpriseRAG 的 Gold Documents 与 Atomic Facts 适合分析“答对了多少”和“证据是否找对”。
- FAB 的双模式思想可以区分检索瓶颈和生成瓶颈。
- MIRAGE 可以把“没有上下文、只有 Gold、Gold + 噪声”拆开，避免把检索和生成问题混为一谈。
- CMRC2018 能作为中文基础诊断，但不冒充企业 PDF RAG benchmark。

**必须保留的限制：**

- EnterpriseRAG 是扁平化 JSON/Parquet 企业文本，不是 PDF/OCR benchmark。
- FAB 当前公开的是 200 道 QA 和证据摘录，没有论文描述的完整语料；目前只能把 Gold Context 作为可运行条件，Native 条件受 corpus/code/license gate 限制。
- MIRAGE 原论文正式只有 Base、Oracle、Mixed 三种条件；Hard Negative 和 Contradictory 是本项目扩展，不能写成 MIRAGE 原生模式。
- CMRC2018 是中文抽取式阅读理解数据集，不能替代后续自建中文企业数据。

## 3. 数据集来源、简介与用途

### 3.1 第一次：五个通用 RAG benchmark

| 数据集 | 论文/文档位置 | 官方数据/代码 | 简介与用途 | 本地位置 |
|---|---|---|---|---|
| **RGB** | [Benchmarking Large Language Models in Retrieval-Augmented Generation](https://ojs.aaai.org/index.php/AAAI/article/view/29728)，[本地 PDF](../../refs/papers/01-RGB-AAAI-2024.pdf) | [GitHub](https://github.com/chen700564/RGB) | 覆盖噪声鲁棒、拒答、信息整合和反事实鲁棒，含中英文场景。用于检查 RAG 在干扰和不可回答问题上的行为。 | [`datasets/downloads/public/rgb`](../../datasets/downloads/public/rgb) |
| **ALCE** | [Enabling Large Language Models to Generate Text with Citations](https://aclanthology.org/2023.emnlp-main.398/)，[本地 PDF](../../refs/papers/02-ALCE-EMNLP-2023.pdf) | [GitHub](https://github.com/princeton-nlp/ALCE)，[HF](https://huggingface.co/datasets/princeton-nlp/ALCE-data) | 面向长答案生成和引用，关注 citation correctness、citation recall 等。用于验证 MOI 是否能给出可核验的证据引用。 | [`datasets/downloads/public/alce`](../../datasets/downloads/public/alce) |
| **RAGTruth** | [A Hallucination Corpus for Developing Trustworthy Retrieval-Augmented Language Models](https://aclanthology.org/2024.acl-long.585/)，[本地 PDF](../../refs/papers/03-RAGTruth-ACL-2024.pdf) | [GitHub](https://github.com/ParticleMedia/RAGTruth) | 提供回答级和 span 级 hallucination 标注。主要用于 Judge 离线校准、faithfulness 和无依据回答诊断，不适合作为唯一端到端产品分数。 | [`datasets/downloads/public/ragtruth`](../../datasets/downloads/public/ragtruth) |
| **RAGBench** | [Explainable Benchmark for Retrieval-Augmented Generation Systems](https://arxiv.org/abs/2407.11005)，[本地 PDF](../../refs/papers/04-RAGBench-arXiv-2024.pdf) | [GitHub](https://github.com/rungalileo/ragbench)，[HF](https://huggingface.co/datasets/galileo-ai/ragbench) | 大规模、多领域、带 context relevance、utilization、completeness、adherence 等标签。用于 reader/evaluator 回归和结构化上下文诊断；不能当作原始 PDF 解析主集。 | [`datasets/downloads/public/ragbench`](../../datasets/downloads/public/ragbench) |
| **MultiHop-RAG** | [Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries](https://openreview.net/forum?id=t4eB3zYWBK)，[本地 PDF](../../refs/papers/05-MultiHop-RAG-COLM-2024.pdf) | [GitHub](https://github.com/yixuantt/MultiHop-RAG)，[HF](https://huggingface.co/datasets/yixuantt/MultiHopRAG) | 2,556 道多跳问题和 609 篇文章，要求组合跨段/跨文档证据，并涉及时间过滤。用于多跳检索、完整 evidence-set 和回答整合诊断。 | [`datasets/downloads/public/multihop-rag`](../../datasets/downloads/public/multihop-rag) |

### 3.2 第二次：文档/PDF/多模态 benchmark

| 数据集 | 论文/文档位置 | 官方数据/代码 | 简介与用途 | 当前主评测定位 |
|---|---|---|---|---|
| **OmniDocBench** | [CVPR 2025 论文](https://openaccess.thecvf.com/content/CVPR2025/papers/Ouyang_OmniDocBench_Benchmarking_Diverse_PDF_Document_Parsing_with_Comprehensive_Annotations_CVPR2025_paper.pdf)，[本地 PDF](../../refs/papers/06-OmniDocBench-CVPR-2025.pdf) | [GitHub](https://github.com/opendatalab/OmniDocBench)，[HF](https://huggingface.co/datasets/opendatalab/OmniDocBench) | 1,651 页、10 类文档、丰富的 block/span、表格、公式、OCR 和阅读顺序标注。适合 PDF parser、OCR、表格/公式识别和结构恢复。 | 第三次退出主评测；保留为解析专项回归。 |
| **READoc** | [READoc 论文](https://arxiv.org/abs/2409.05137)，[本地 PDF](../../refs/papers/07-READoc-Findings-ACL-2025.pdf) | [GitHub](https://github.com/icip-cas/READoc)，[HF](https://huggingface.co/datasets/lazyc/READoc) | 2,233 个 arXiv/GitHub 文档，定义 PDF → 语义丰富 Markdown 的统一文档结构抽取任务。适合评估结构化解析和 Markdown 质量。 | 第三次退出主评测；保留为 PDF-to-Markdown 专项回归。 |
| **MMDocIR** | [MMDocIR 论文/EMNLP 2025](https://aclanthology.org/2025.emnlp-main.1576/)，[本地 PDF](../../refs/papers/08-MMDocIR-EMNLP-2025.pdf) | [GitHub](https://github.com/MMDocRAG/MMDocIR)，[HF Evaluation Dataset](https://huggingface.co/datasets/MMDocIR/MMDocIR_Evaluation_Dataset) | 313 篇长文档，包含页面级和 layout-level 的多模态检索问题，覆盖文字、图像、表格和布局证据。用于页面召回、布局召回和多模态 evidence-set 诊断。 | 第二次引入后保留为检索专项。 |
| **ViDoRe V2** | [ViDoRe Benchmark V2](https://arxiv.org/abs/2505.17166)，[本地 PDF](../../refs/papers/09-ViDoRe-V2-arXiv-2025.pdf) | [ViDoRe benchmark](https://github.com/illuin-tech/vidore-benchmark)，[HF collection](https://huggingface.co/collections/vidore/vidore-benchmark-v2) | 面向视觉文档检索，提供页面图像、查询和 qrels，覆盖 ESG、经济、医学讲义等领域。适合 ColPali/视觉检索和页面级 Recall/nDCG。 | 第三次退出主评测；保留为视觉检索专项。 |
| **DocBench** | [DocBench 论文](https://aclanthology.org/2025.knowledgenlp-1.29/)，[本地 PDF](../../refs/papers/10-DocBench-KnowledgeNLP-2025.pdf) | [GitHub](https://github.com/Anni-Zou/DocBench)，[数据下载](https://drive.google.com/drive/folders/1yxhF1lFF2gKeTNc8Wh0EyBdMT3M4pDYr) | 229 个真实 PDF、1,102 道问题，输入原始文档和问题，输出文本答案，覆盖多个领域和问题类型。用于最小可运行的 PDF-to-answer 端到端评测。 | 第二次引入后保留为端到端主研究集之一。 |
| **MMDocRAG** | [NeurIPS 2025 论文](https://proceedings.neurips.cc/paper_files/paper/2025/file/1a93178950e92fd2e7b7448f7d68fd7d-Paper-Datasets_and_Benchmarks_Track.pdf)，[本地 PDF](../../refs/papers/11-MMDocRAG-NeurIPS-2025.pdf) | [Homepage](https://mmdocrag.github.io/MMDocRAG/)，[GitHub](https://github.com/MMDocRAG/MMDocRAG)，[HF](https://huggingface.co/datasets/MMDocIR/MMDocRAG) | 4,055 个专家标注 QA、220 个长文档和文字/图像 quote，强调跨页、跨模态证据链和多模态回答。用于 quote selection、视觉证据整合和多模态端到端 RAG。 | 第二次引入后保留为多模态端到端研究集。 |

### 3.3 第四次：企业、专业领域、噪声和中文数据集

| 数据集 | 论文/文档位置 | 官方数据/代码 | 简介与用途 | 当前限制 |
|---|---|---|---|---|
| **EnterpriseRAG-Bench** | [本地论文 PDF](../../refs/papers/12-EnterpriseRAG-Bench-arXiv-2026.pdf) | [GitHub](https://github.com/onyx-dot-app/EnterpriseRAG-Bench)，[HF](https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench)，[v1.0.0 release](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/releases/tag/v1.0.0) | 约 511,962 条扁平化企业文本、500 道核心题、10 类问题，并提供 Gold 文档、Gold answer 和 Atomic Facts。用于企业文本检索、文档召回、回答正确性、完整性和无答案诊断。 | 不是 PDF/OCR/layout benchmark；不能替代文档解析集。 |
| **FAB-Bench** | [本地论文 PDF](../../refs/papers/13-FAB-Bench-arXiv-2026.pdf) | [GitHub](https://github.com/FuturefabAI/FAB-Bench) | 面向半导体制造知识，公开 200 道 QA，包含 ROB、MULTI、GEN 等问题类型；论文提出 `with_kb` 与 `without_kb` 双模式，可分析检索和生成瓶颈。 | 当前只有 QA 和 Gold Context 摘录，没有完整 347M-token source corpus；先做 Gold Context，Native 条件暂 blocked。 |
| **MIRAGE** | [论文 HTML](https://arxiv.org/html/2504.17137)，[本地 PDF](../../refs/papers/14-MIRAGE-arXiv-2025.pdf) | [GitHub](https://github.com/nlpai-lab/MIRAGE)，[HF](https://huggingface.co/datasets/nlpai-lab/mirage) | 7,560 道 QA、37,800 个 context pool，正式设置为 Base、Oracle、Mixed。用于测试回答模型对 Gold context、噪声和错误上下文的敏感性。 | Hard Negative、Contradictory 是本项目扩展，不属于论文原生三种设置；也不是企业多跳集。 |
| **CMRC2018** | [EMNLP-IJCNLP 2019 论文](https://aclanthology.org/D19-1600/)，[本地 PDF](../../refs/papers/15-CMRC2018-EMNLP-IJCNLP-2019.pdf) | [官方页面](https://ymcui.com/cmrc2018/)，[GitHub](https://github.com/ymcui/cmrc2018) | 中文 span-extraction machine reading comprehension 数据集，适合测中文阅读理解、中文分词、实体和答案抽取基础能力。 | 不是企业 RAG 或 PDF benchmark；官方 test/challenge 不公开，只做中文基础诊断。 |

## 4. 当前最终构建建议

### 4.1 不建议把所有数据集压成一个总榜

最终应分为四条研究线：

1. **通用 RAG 线：** RGB、ALCE、RAGTruth、RAGBench、MultiHop-RAG。
2. **文档/多模态研究线：** MMDocIR、DocBench、MMDocRAG，以及必要时的 OmniDocBench、READoc、ViDoRe V2 专项回归。
3. **产品诊断线：** EnterpriseRAG-Bench、FAB-Bench、MIRAGE、CMRC2018。
4. **正式产品主线：** 后续自建、获得授权或完全合成的中文企业 corpus 和 Gold，不直接把公共 benchmark 当作商业主榜。

### 4.2 当前最合理的使用顺序

1. 用 EnterpriseRAG-Bench 小切片验证企业文本 adapter、Gold 文档映射和 Atomic Facts 计算。
2. 用 FAB-Bench Gold Context 验证专业领域 reader 和六维 rubric；取得完整 corpus/code/license 后再考虑 Native。
3. 用 MIRAGE Base/Oracle/Mixed 验证上下文敏感性和噪声诊断。
4. 用 MMDocIR、DocBench、MMDocRAG 做独立的检索、PDF-to-answer 和多模态研究诊断。
5. 将 RGB、ALCE、RAGTruth、RAGBench、MultiHop-RAG 作为通用能力回归和 evaluator 校准集。
6. CMRC2018 只作为中文基础线；真正用于产品结论的中文数据仍应按 v1.0 计划构建 `50 docs/250 questions → 200 docs/1000 questions` 的自有 Gold 数据。

## 5. 关键本地证据索引

- [公开数据下载清单](../../datasets/downloads/public/DOWNLOAD_MANIFEST.md)：第一版五个 benchmark 的版本、规模和校验信息。
- [文档 RAG 下载清单](../../datasets/downloads/document-rag/README.md)：第二版文档/多模态数据的下载、论文、代码和许可边界。
- [统一数据集论文目录](../../refs/papers/README.md)：按四次构建变动顺序编号的 canonical PDF；Natural Questions 作为后续补充列为 16。
- [RAG benchmark 论文包](../../refs/papers/rag-benchmarks/README.md)：第一版五篇论文以及扩展论文的本地位置和官方链接。
- [三阶段 Benchmark 历史计划](../todo/moi-rag-benchmark-three-stage-plan-v1.md)：第二版文档型数据被纳入公开基线时的原始分层方案。
- [TODO 来源核验](./todo-benchmark-source-review-2026-08-05.md)：第四版四个新数据集的证据、限制和可运行边界。
- [v1.0 当前母计划](../drafts/v1.0.md)：当前 authority，以及“公共诊断线”和“正式产品主线”的分离规则。

## 6. 需要特别区分的两个候选

- **RAGPerf** 是性能 workload/运行框架，不是质量数据集；只用于性能测试结构和读写/更新负载设计。
- **Double-Bench** 曾是候选，但 21.9 GiB corpus 因资源和范围原因取消下载；本地保留论文和代码，不进入当前数据集分母。

最后，论文文件、评测代码、数据集使用权、商业上传权和公开再发布权是五个不同层级。即使论文和数据已下载到本地，也必须在正式运行或发布前按数据集、配置和底层文档逐项完成 license/egress 审查。
