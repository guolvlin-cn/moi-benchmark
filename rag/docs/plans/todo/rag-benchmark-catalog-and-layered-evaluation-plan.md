# MOI RAG Benchmark 总目录与分层评测计划

> 更新日期：2026-08-03  
> 范围：本地已下载的 12 个 benchmark 候选，包括此前五个通用 RAG benchmark 和本次七个文档 RAG 候选。  
> 结论：不要把 12 个数据集混成一个总分。应把它们放到“解析 → 检索 → 回答与引用 → 原生 PDF 端到端 → 产品工程”各层，逐层诊断。

## 1. 范围和本地状态

本地数据分为两组：

- `rag/datasets/downloads/public/`：此前五个通用 RAG benchmark，约 1.4 GiB。
- `rag/datasets/downloads/document-rag/`：本次文档 RAG、解析和视觉检索候选。保留 ZIP 并解压后约 30 GiB。

本次文档组有 6 套 corpus 完整落盘；Double-Bench 因 corpus 约 21.9 GiB、运行成本过高，按要求只保留论文和官方代码。因此本文将 Double-Bench 作为未来扩展项，不把它计入当前可运行数据集数量。

公司内部产品研发和评测按本项目的保守口径视为商业使用。数据“公开可下载”不等于允许商业测试或再发布；下表的授权风险是工程隔离依据，不构成法律意见。

## 2. 十二个 benchmark 分别用来做什么

### 2.1 文档、PDF 与多模态组

| Benchmark | 输入 → 输出 | 主要用途 | 官方/论文规模 | 本地状态 | 在 MOI Bench 中的角色 | 授权风险 |
|---|---|---|---|---|---|---|
| **DocBench** | 原始 PDF + query → 文本回答 | 最直接的 PDF-to-answer 端到端测试；覆盖长文档、跨页信息和不同问法 | 229 份真实文档、1,102 个问题，5 个领域、4 类问题 | 完整；229 PDF + 229 QA JSONL，约 0.57 GiB | **P0 端到端 smoke 候选**；最接近 MOI 的上传、解析、建库、查询路径 | 高：数据许可证不清晰，默认隔离，公开/商业使用前审核 |
| **MMDocRAG** | 多页 PDF/页面/图片 + query → 多模态证据选择 + 回答 | 检验文本、表格、图像混合证据的检索、选择和生成；强调跨页、跨模态证据链 | 4,055 个专家标注 QA；论文比较 14 个 retriever 和 60 个语言/视觉模型 | 完整；3.22 GiB 原始发行版；另已解压 220 PDF 和 14,826 图片 | **P1 多模态端到端主集**；用于判断“解析没丢，但视觉证据是否仍召回并用于回答” | 高：作者说明数据按 CC BY-NC / research-only 处理 |
| **OmniDocBench** | PDF 页面图像 → 带版面、文本、公式、表格、阅读顺序的结构化结果 | 单独测试 PDF 解析/OCR/layout，不让检索和生成掩盖解析错误 | README 口径 1,651 页；10 种文档类型、5 种版式、5 种语言；28 类 block、4 类 span 标注 | 完整；1.44 GiB、1,662 个发行文件 | **P0 解析主集**；用于 OCR、表格、公式、阅读顺序和 block 定位回归 | 高：research-only / non-commercial |
| **READoc** | 原始 PDF → 语义丰富 Markdown | 测试真实文档结构化抽取，尤其是标题层级、段落、公式、表格和跨页阅读顺序 | 论文核心集 2,233 份：1,009 arXiv + 1,224 GitHub | 完整；3.06 GiB 压缩发行版；已解压 1,009 arXiv、1,224 GitHub、1,343 Zenodo PDF | **P1 解析补充集**；更贴近 MOI 入库前的 PDF-to-Markdown/结构块质量 | 中高：工具代码许可不自动覆盖 arXiv/GitHub/Zenodo 底层文档 |
| **MMDocIR Evaluation** | query + 长文档页面/layout → 相关页面或版面块排名 | 将 retrieval 从生成中独立出来，测试 page-level 与 layout-level 多模态召回 | 1,685 个专家问题；另有 173,843 个 bootstrapped 训练问题，本地未下载训练集 | 完整；仅 Evaluation Dataset，10.43 GiB、11 个发行文件 | **P0 文档检索主集**；判断 MOI 是否召回正确页、表格、图片或版面块 | 高：CC BY-NC / research-only；本地仅评测集 |
| **ViDoRe V2** | 文本 query + 页面图像 corpus → 页面图像排名 | 视觉文档检索，适合 OCR 不可靠、图表/版式决定语义的场景 | 本地为 ESG、人工标注 ESG、生物医学讲义、经济报告 4 个官方子集 | 完整；31 个发行文件，2.25 GiB | **P1 视觉 retrieval 补充集**；报告 nDCG@10、Recall@K 和索引/搜索耗时 | 高且混合：含 CC BY-NC-SA，其他子集仍有原文档权利 |
| **Double-Bench** | 多语言多模态文档 + 单跳/多跳 query → 分组件 retrieval 与回答结果 | 大规模、细粒度的文档 RAG 端到端诊断，并显式标注证据页和多跳步骤 | 3,276 文档、72,880 页、5,168 queries、6 种语言、4 类文档 | **corpus 未下载**；论文和官方代码已保留 | **P3 未来扩展**；机器和预算允许时替代小规模端到端集做压力/覆盖验证 | 未纳入当前运行；启用前重新做许可审查 |

### 2.2 此前五个通用 RAG 组

| Benchmark | 输入 → 输出 | 主要用途 | 本地规模 | 在 MOI Bench 中的角色 | 授权风险 |
|---|---|---|---|---|---|
| **RGB** | query + 固定检索上下文 → 回答/拒答 | 分开测试噪声鲁棒性、无答案拒答、信息整合和反事实冲突 | refined 有效 1,000 rows；整个目录约 44 MiB | **鲁棒性题型与 rubric 参考**；适合近失配证据、冲突证据和不可回答题 | 红：CC BY-NC-SA；不得把整包用于公司商业产品测试或公开包 |
| **ALCE** | query + 检索结果 → 带引用长答案 | 将答案正确性、citation recall 和 citation precision 分开；适合长答案证据覆盖 | ASQA、QAMPARI、ELI5 各 1,000 eval；本地约 861 MiB，含缓存检索结果 | **引用评测协议参考**；MOI 若展示引用，应把其 claim-to-citation 思路升为核心 gate | 红：混合数据和网页内容无统一商业授权，不得整包使用/发布 |
| **RAGTruth** | source + 已生成 response → 幻觉标签/span | 校准 hallucination/faithfulness evaluator，并把无根据与冲突信息定位到 span | 2,965 sources、17,790 responses；本地约 43 MiB | **Judge 校准与错误归因集**；不是 retrieval 或 PDF 端到端分数 | 红：含 MS MARCO、Yelp、新闻等受限来源，整包不可用于商业测试/发布 |
| **RAGBench** | question + 已处理 documents + response → TRACe 标签/分数 | 统一 12 个数据集，用 Relevance、Utilization、Completeness、Adherence 做可解释 evaluator 回归 | 12 configs、95,381 rows、36 parquet；本地约 431 MiB | **P0 evaluator 回归集**；优先看 TechQA、EManual，TAT-QA/HotpotQA 仅作题型补充；不能冒充原生 PDF 评测 | 黄/红：必须逐 config 审计；`msmarco` 禁用，raw documents 不得整包发布 |
| **MultiHop-RAG** | query + 609 篇文档 → 多文档检索 + 组合回答 | 测试 2–4 篇证据的跨文档多跳检索、时间问题、比较问题和 null 问题 | 2,556 queries + 609 documents；本地约 15 MiB | **P1 多跳 retrieval/reader 诊断集**；必须补报 all-evidence success，不能只用官方 any-hit Hits@K | 黄/红：ODC-BY 不覆盖文章正文；正文和 evidence 摘录不得进入商业 corpus |

### 2.3 角色边界

这 12 个 benchmark 不是同一种任务：

- OmniDocBench、READoc 只回答“PDF 有没有被正确解析”。
- MMDocIR、ViDoRe V2 只回答“问题对应的页面/布局有没有被找回来”。
- RAGBench、RAGTruth、RGB、ALCE 主要回答“上下文给定后，回答、引用或自动 Judge 是否可靠”。
- DocBench、MMDocRAG 才能较自然地走原始文档到回答的端到端链路。
- MultiHop-RAG 横跨 retrieval 和 reader，但其原始 corpus 不是 PDF。
- Double-Bench 当前没有 corpus，不能纳入实跑分母。

因此，任何报告都必须注明输入起点。把“给定 processed context”的 RAGBench 分数和“从原始 PDF 上传”的 DocBench 分数放到同一排行榜，会混淆解析、检索和生成三类失败。

## 3. 推荐的分层评测体系

### 3.1 两条隔离运行轨

先按授权把评测拆成两条物理隔离的轨道：

1. **Product / release gate**：只用公司自有、明确获授权或全合成数据。沿用 v0.4 的 6 PDF、20 sealed questions 主合同，可形成产品发布判断。
2. **Research diagnostic lane**：运行公共 benchmark，用于组件比较、错误定位和方法研究。黄色/红色数据不进入商业 CI、产品制品、公开样例、日志截图或可下载报告。

公共 benchmark 的结果可以帮助发现问题，但在许可证未获批准前，不能反向成为产品 release gate 的数据来源。

### 3.2 层级、指标和门禁

| 层级 | 核心问题 | 主数据集 | 必报指标 | 进入下一层的建议门禁 |
|---|---|---|---|---|
| **L0 数据治理与有效性** | 文件、版本、hash、许可、split 和 Gold lineage 是否可信？ | 全部；产品轨以自有/合成数据为主 | planned/actual 文件数、hash mismatch、invalid/replacement、许可 allowlist、字段缺失、泄漏检查 | 数据版本冻结；必填字段完整；hash 异常为 0；未批准数据无法进入产品轨 |
| **L1 上传、解析与结构保持** | PDF 是否 accepted、能解析、页数正确；文本、表格、公式、图片和阅读顺序是否保留？ | OmniDocBench、READoc；v0.4 自有 PDF | accepted-file/page rate、OCR/edit distance、TEDS、公式 CDM、reading-order、block F1、Gold evidence preservation、parse/build time | 所有 scored PDF searchable-ready；关键 Gold 证据 100% 可定位；解析失败不得用回答分数掩盖 |
| **L2 索引与检索** | 正确页面、布局和完整多跳证据是否进入 top-k？ | MMDocIR、ViDoRe V2、MultiHop-RAG | Recall@K、nDCG@10、MRR、complete evidence-set recall、all-evidence success、trace completeness、index/search latency | 关键证据 recall 达预注册阈值；多跳题必须报告“找齐证据”，不能只报 any-hit |
| **L3 Reader 与证据利用** | 给定召回上下文后，系统是否正确组合事实，并在证据不足时拒答？ | RAGBench、RGB、MultiHop-RAG；v0.4 Gold | claim correctness、Reference-claim Recall、Gold-evidence Support、unanswerable success、false refusal、critical contradiction | answerable 题 correctness/claim recall 达阈值；Gold-evidence Support=1；不可回答题无编造 |
| **L4 引用与忠实性** | 每个回答 claim 是否被具体、可打开的引用完整支持？自动 Judge 是否可信？ | ALCE 协议、RAGTruth、RAGBench；v0.4 citation-required 题 | citation locator validity、citation entailment precision、answer-claim citation coverage、hallucination span rate、Judge-human agreement | citation-required 题 coverage=1；提交引用均可解析且支持对应 claim；Judge 先经人工校准 |
| **L5 原生 PDF 端到端** | 从 upload 到 answer/citation 的用户路径整体是否成功？ | 产品轨 v0.4；研究轨 DocBench、MMDocRAG | Pilot-TDAS、端到端成功率、按 text/table/image/multi-page 切片、失败归因到 L1–L4 | 只在 L1–L4 trace 足够时给端到端结论；任何总分必须同时展示分层诊断 |
| **L6 产品可靠性与可运营性** | 重复运行是否稳定，失败能否恢复，成本和人工操作是否可接受？ | v0.4 两次 repeat；必要时公共集小样本复跑 | initial availability、timeout/error、pass/pass 等翻转、P50/P95、retry recovery、TTF searchable、TTF trusted answer、人工分钟、干预次数、成本 | 冻结 SLO 后判定；失败和 retry 保留在 initial 分母，禁止用重试覆盖首轮失败 |

鲁棒性不是独立替代层，而是横切 L2–L5：在每层加入 OCR 噪声、近失配文档、无答案、冲突证据、表格/图片、跨文档和 fresh/private 样本切片。

## 4. 建议执行顺序

### Phase A：一周可行性 Pilot，不改变 v0.4 合同

- 继续使用 6 份自有/获批 PDF、6 道 smoke、20 道 sealed scored questions、每题 2 次 repeat。
- 先完成 L0/L1，再跑 L5/L6；所有失败回溯标到 parsing、retrieval、reader、citation 或 product/API。
- RAGBench 只用于 Judge/rubric 离线校准；其合成 PDF 不进入 v0.4 主 corpus，也不保留原始版面能力结论。
- 输出 `PILOT_COMPLETE / DIAGNOSTIC_ONLY / BLOCKED / INVALID`，不声称产品优于外部系统。

### Phase B：组件级回归基线

在独立 research lane 先跑小而分层的固定样本：

| 组件 | 建议首轮样本 | 目的 |
|---|---:|---|
| Parser | OmniDocBench 200 页，按文档类型/语言/表格/公式分层；READoc 100 PDF | 快速定位 OCR、表格、公式和阅读顺序短板 |
| Retriever | MMDocIR 200 queries；ViDoRe V2 每子集 50；MultiHop-RAG 200 | 建立 page/layout/visual/multi-hop retrieval 基线 |
| Reader/Judge | RAGBench TechQA、EManual 各 100；经许可后再加 TAT-QA、HotpotQA；RAGTruth 200 responses 仅做 evaluator 校准 | 冻结 claim、support、拒答和自动 Judge 的行为 |
| Citation | 使用自有 Gold 100 answers；ALCE 仅在授权允许的研究环境复现协议 | 校验 citation coverage、precision 和 locator，而不是照搬 ALCE 总分 |

首轮样本只用于调通 adapter、schema、指标和失败分类。样本 ID 必须在看到结果前冻结；任何调参后使用独立 holdout 或新 freeze id。

### Phase C：文档 RAG 端到端专项

1. **DocBench smoke**：先选 20 PDF / 50 QA 验证 `PDF → MOI ingest → query → answer → judge`。
2. **DocBench 扩展**：链路稳定后扩到全部 229 PDF / 1,102 QA，报告领域和题型切片。
3. **MMDocRAG 多模态专项**：先跑 200 QA，按 text/table/image/cross-modal evidence 分层；若 MOI 无法导出图片/页面级 trace，相关 retrieval 指标记 `N/A: TRACE_UNAVAILABLE`，不能从最终回答反推。
4. **Double-Bench 暂缓**：只有在机器、存储、运行预算和许可都通过新 gate 后再下载 corpus。

### Phase D：正式 decision-grade 评测

- 冻结产品版本、embedding、chunking、top-k、reranker、生成模型、prompt 和所有阈值。
- 使用公司自有/授权的 fresh hidden corpus 做主榜；公共集只做命名清楚的 supplemental tracks。
- 两名 reviewer + adjudication；Judge 在独立人工集上校准并报告一致性。
- 对 question-level 结果报告分子、分母和区间；claim/citation 指标报告原始计数，不把相关 claims 当独立样本生成虚假的窄置信区间。
- 公布分层 scorecard 和失败案例类型，不做不可解释的加权 overall score。

## 5. 建议的最终报告结构

每次 MOI RAG 评测至少输出以下七张表，而不是只有一个“准确率”：

1. **Run validity**：版本、配置、数据 hash、planned/actual、invalid/replacement。
2. **Readiness/parsing**：上传、处理、页数、证据保存、解析组件指标。
3. **Retrieval**：Recall@K、nDCG、完整证据集召回、trace 覆盖率。
4. **Answer**：correctness、claim recall、evidence support、拒答和 contradiction。
5. **Citation**：locator、precision、coverage、伪造/越界引用。
6. **Reliability/operability**：可用率、重复翻转、延迟、恢复、人工时间和成本。
7. **Slice/error taxonomy**：文档类型、语言、表格/公式/图片、多跳、fresh、不可回答及根因分布。

如果 L1 解析失败，应在 L5 端到端结果中保留失败，但根因归到 L1；如果 L2 已召回完整证据而答案错误，则归到 L3/L4。这个归因规则能让 MOI Bench 回答“系统为什么失败”，而不只是“最后得了多少分”。

## 6. 本地依据

- 文档组下载与解压清单：[`../../datasets/downloads/document-rag/README.md`](../../datasets/downloads/document-rag/README.md)
- 此前五个公开集下载清单：[`../../datasets/downloads/public/DOWNLOAD_MANIFEST.md`](../../datasets/downloads/public/DOWNLOAD_MANIFEST.md)
- 此前五个 benchmark 调研：[`../../refs/rag-public-datasets-shortlist-2026-07.md`](../../refs/rag-public-datasets-shortlist-2026-07.md)
- 商业使用风险筛查：[`../../refs/rag-public-datasets-commercial-use-review-2026-07.md`](../../refs/rag-public-datasets-commercial-use-review-2026-07.md)
- 当前一周 Pilot 合同：[`../drafts/v0.4.md`](../drafts/v0.4.md)
- Gold 与指标规范：[`../golden-and-metrics-spec-v0.4.md`](../golden-and-metrics-spec-v0.4.md)
- RAGBench → PDF → MOI 可行性：[`../drafts/v0.4-todos/03-ragbench-moi-integration-feasibility.md`](../drafts/v0.4-todos/03-ragbench-moi-integration-feasibility.md)
