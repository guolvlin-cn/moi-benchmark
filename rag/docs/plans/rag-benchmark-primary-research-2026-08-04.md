# MatrixOne Intelligence RAG 平台 Benchmark：一手证据研究与可执行建议

> 截止日期：2026-08-04  
> 研究对象：MatrixOrigin **MatrixOne Intelligence（MOI）**。本文中的 MOI 绝非 moi-ai.com 的 MoiAI。  
> 证据规则：优先论文、官方文档、官方 GitHub/许可证和官方价格页；价格、版本和 Preview 状态均是截止日快照。  
> 标记：**[事实]** 可由所附一手来源直接核验；**[推断]** 是从事实得到的范围判断；**[建议]** 是面向本项目的实施选择；**[风险]** 是执行前必须关闭的不确定项。

## 1. 结论先行

1. **[推断] 不存在一个可以直接套用的“端到端企业 RAG 平台标准总分”。** RAGAS、ARES、RAGBench主要评估“已有 query/context/answer”；BEIR、MTEB、BRIGHT主要评估检索；KILT评估固定 Wikipedia 上的知识密集任务与 provenance；CRAG评估动态 Web/KG 问答。它们均不能覆盖企业平台的原始文件导入、解析、索引就绪、权限隔离、引用可解析性、更新删除、可靠性和全栈成本。
2. **[建议] 采用分层计分板，不发布一个掩盖故障位置的总分。** 至少拆成：语料与导入、解析与索引、检索、答案、引用、拒答/安全、性能可靠性、成本与运维。先设硬门槛，再比较各层指标；确需综合分时，只在同一赛道内使用预注册权重，并同时展示全部分项与置信区间。
3. **[建议] RAGFlow 应从“可选”升级为主竞品。** 它与 MOI 原生链路最贴近，官方 API 同时覆盖文档上传、解析/ingestion、状态、独立 retrieval、聊天与引用，且公开定位是企业级一体化 RAG/Agent 平台。主自部署赛道建议为 **MOI + RAGFlow + Dify + FastGPT**。
4. **[建议] MaxKB 作为 P1 条件竞品。** 产品边界吻合、文件与自部署能力合适，但官方公开的 OSS/应用聊天接口与“平台 Open API”权限边界、机器可读检索/引用 schema 不够透明；只有在小样本适配器试验确认可导入、轮询和导出引用后，才进入正式榜。
5. **[建议] 云托管平台单列“工程参照赛道”，不得与自部署平台混算总分。** 建议比较 Amazon Bedrock Knowledge Bases、Google Agent Search/Vertex AI Search（同时把 Vertex AI RAG Engine标为组件服务）、Azure AI Search/Foundry IQ。它们的部署责任、固定容量费、模型费、解析费和 Preview/GA 边界与自部署平台不同。
6. **[建议] AnythingLLM、Quivr、Open WebUI 仅列越界/轻量参照。** NotebookLM、ChatDOC 同样不进入主轨。它们可用于局部 UX、个人/本地部署或框架上限观察，但不能代替企业 Data+AI/RAG 平台竞品。

## 2. “标准分层”：评什么、为何不能混

### 2.1 推荐七层模型

| 层 | 平台输入/输出边界 | 核心问题 | 主指标 | 失败归因 |
|---|---|---|---|---|
| L0 语料与控制面 | 原始文件/连接器 → 接受、版本、权限 | 能否稳定接收、更新、删除、隔离？ | 导入接受率、最终成功率、重复导入幂等性、更新/删除新鲜度、越权泄漏率 | 连接器、配额、权限、控制面 |
| L1 解析与索引 | 文件 → 可检索单元 | 版面、表格、扫描件、图片是否正确解析并可搜索？ | 文本/表格/阅读顺序/图表覆盖；可检索文档率；time-to-searchable | parser/OCR/chunker/indexer |
| L2 检索 | query → ranked chunks/docs | 是否找全、排对、抗硬负例？ | Recall@k、MRR@k、nDCG@k、证据集完成率、Context Precision/Recall | embedding、BM25、融合、rerank、filter |
| L3 生成答案 | query + retrieved context → answer | 答案是否正确、完整且仅依赖证据？ | claim correctness、completeness、faithfulness、格式遵循 | prompt、LLM、context packing |
| L4 引用 | answer → cited evidence | 引用是否真支持相应 claim，且用户能定位原文？ | citation precision、coverage、resolvability、page/span accuracy | 引用生成、映射、UI/API schema |
| L5 行为与安全 | 可答/不可答/冲突/越权 query | 会不会编造、误拒答、引用旧版本或泄漏？ | 拒答 precision/recall、冲突/时效正确率、越权泄漏率 | policy、ACL、retrieval/generation |
| L6 系统与经济性 | 工作负载 → 延迟、吞吐、成本、运维 | 能否在目标并发与预算下复现？ | p50/p95/p99、首 token、吞吐、initial/final success、恢复时间、单位成本、操作工时 | 平台、基础设施、上游模型/服务 |

**[推断]** 层间错误会级联：解析漏表可能表现为检索 recall 低，检索漏证据又会表现为答案不完整。因此只看最终答案会把根因混在一起；只看检索又会漏掉平台最重要的导入、引用和运维价值。

### 2.2 组件 benchmark 与端到端平台 benchmark 的根本差异

| 维度 | 普通组件级 benchmark | 端到端 RAG 平台 benchmark |
|---|---|---|
| 起点 | 已清洗 corpus/query/qrels 或已给定 context | 原始 PDF、Office、图片、网页/连接器及 ACL |
| 被测对象 | embedding、retriever、reranker、reader、judge 之一 | 导入→解析→切分→索引→检索→生成→引用→运维全链 |
| 可控性 | 模型、chunk、top-k 通常完全可控 | 很多平台隐藏模型、chunk、重试、缓存或升级 |
| 标准输出 | ranked doc IDs、score 或 answer | 状态、chunks、answer、citations、trace、usage、错误与日志 |
| 公平性 | 同 corpus、同 qrels、同 metric 即可 | 还需同原始文件、硬件/套餐、模型、默认/调优轨、并发、冷暖缓存、重试规则 |
| 归因 | 组件相对清楚 | 必须有 trace；无 trace 时只报告 E2E，不反推检索质量 |
| 成本 | 常是单模型推理/索引成本 | 许可证、基础设施、OCR/parser、embedding、向量库、rerank、LLM、出网和人力 |
| 可比结果 | 可形成同一 leaderboard | 自部署、SaaS、云托管应分轨；不宜一个总榜 |

**[建议] 两个同时存在但互不混分的实验轨：**

- **平台原生轨（主轨）**：每个平台用官方支持的原始文件入口和原生回答/引用入口，测试用户真正得到的结果。再分“出厂默认”和“受限调优”两条，不把隐藏人工修复混入默认成绩。
- **组件诊断轨（辅轨）**：只有当平台公开独立 ranked retrieval API 时，才用选定 BEIR/MTEB/BRIGHT 数据或自建 qrels 测 retrieval。若没有接口，标 `N/A / observability unavailable`，不可从答案猜测 chunk 排名。

## 3. 指标定义与计算合同

### 3.1 确定性优先

设问题集合为 `Q`，问题 `q` 的相关证据单元集合为 `Gq`，前 `k` 个返回单元为 `Rq,k`。

- `Recall@k(q) = |Gq ∩ Rq,k| / |Gq|`。对多个同样有效的证据集合，保留 `Gq = {Gq,1 ... Gq,m}`，取最佳合法集合，而不是强迫唯一 page/chunk。
- `MRR@k = mean(1 / rank(first relevant))`，前 `k` 无相关证据为 0；适合“找到第一条就够”的问题。
- `nDCG@k = DCG@k / IDCG@k`，用于有 0/1/2 等级相关性并关注排序的检索；BEIR、MTEB retrieval 和 BRIGHT 均常以 nDCG@10 为核心。
- `Evidence-set completion@k(q) = 1` 当且仅当存在一个合法完整证据集 `S ∈ Gq` 且 `S ⊆ Rq,k`。它比普通 recall 更能检测多证据/多跳问题是否“找齐”。
- `Citation precision = 被引用且确实支持其相邻 claim 的引用数 / 全部引用数`。
- `Citation coverage = 有有效支持引用的、应引用 claim 数 / 全部应引用 claim 数`。
- `Citation resolvability = 可通过返回 ID/URI 定位到正确 document + page/span 的引用数 / 全部引用数`。页面跳转但找不到原句不算通过。
- `Faithfulness = 被检索上下文支持的生成 claim 数 / 可验证生成 claim 数`。这与“答案是否符合外部真值”不同：一个答案可 faithful 但 context 本身错或过期。
- `Answer claim correctness = 与 gold claims 一致的加权 claim / gold claim 总权重`；同时报 `completeness`，避免只答一小部分却看似正确。
- `Unanswerable recall = 正确拒答的不可答问题 / 全部不可答问题`；`false-refusal rate = 被错误拒答的可答问题 / 全部可答问题`。两者必须成对报告。

### 3.2 平台与运行指标

- 导入接受率：API/UI 接受文件数 / 尝试文件数。
- 最终可检索率：规定超时内，能由探针 query 检索到预埋标记的文档数 / 计划文档数。
- `time-to-searchable`：从平台确认接收至探针首次稳定检索成功；同时报告 p50/p95，不能只使用“上传完成”时间。
- initial success：第一次请求在预算内成功，不允许透明重试；eventual success：按预注册重试策略最终成功。两者分别报告，避免重试掩盖稳定性。
- p50/p95/p99 end-to-end latency；流式平台另报 TTFT。冷启动、暖缓存和并发档位分别测。
- 更新/删除新鲜度：从提交变更至新内容可检索、旧内容不再检索的时间。
- 越权泄漏率：无权限用户的回答、引用或 trace 中出现受限 evidence 的比例；**任何非零正式样本应视为安全门槛失败**。
- 成本：`ingest_cost / 1000 pages`、`query_cost / 1000 answered requests`、`monthly fixed cost`、`operator hours / run` 分开；评测 judge 成本单列，不能算进产品服务成本。

### 3.3 Judge 使用规则

**[事实]** RAGAS 的 faithfulness、response relevancy、context precision/recall 等多个指标依赖 LLM/embedding；其 API 支持指定 evaluator、embedding、run config 与 token parser。LLM judge 输出会随模型与提示改变（[RAGAS 指标](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)、[evaluate API](https://docs.ragas.io/en/latest/references/evaluate/)、[EACL 论文](https://aclanthology.org/2024.eacl-demo.16/)）。

**[建议]** 所有可确定计算的指标先算；LLM judge 只补充 claim entailment、faithfulness、helpfulness 等。冻结 judge 名称/版本、temperature、prompt hash、RAGAS 版本；在正式集之前，由两名标注员独立标 100–150 条分层样本，报告 judge 与人工的一致性以及分类型偏差。judge 不达预注册门槛时，回退人工或报告为探索性指标。

## 4. 指定评测框架与公开 benchmark 的适用性核验

| 项目 | 一手证据事实 | 对 MOI 的适用结论 |
|---|---|---|
| RAGAS | [事实] 官方列出 Context Precision/Recall、Context Entity Recall、Noise Sensitivity、Response Relevancy、Faithfulness 等 RAG 指标；论文定位是 reference-free evaluation 框架，不是原始企业文件产品榜。[Docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) · [论文](https://aclanthology.org/2024.eacl-demo.16/) | **保留为评测工具，不作测试语料或最终真值。** 在统一 adapter 输出后运行；冻结 judge 并人工校准。它不能测导入、parser、ACL、引用跳转和运维。
| ARES | [事实] 使用合成训练数据、微调 judge 与 prediction-powered inference，评 Context Relevance、Answer Faithfulness、Answer Relevance；官方建议至少约 50 条、最好数百条人工验证样本，并输出置信区间。[论文](https://aclanthology.org/2024.naacl-long.20/) · [官方仓库](https://github.com/stanford-futuredata/ARES) | **条件保留。** 适合有标注预算时做校准后的系统级估计与 CI；不是开箱即用平台 benchmark，也不能单独评价 ingestion/parser。
| RAGBench | [事实] 约 10 万 examples、5 个行业域；围绕 TRACe 的 relevance、utilization、completeness、adherence 标签，数据形态已包含 query/context/response。[论文](https://arxiv.org/abs/2407.11005) · [官方仓库](https://github.com/rungalileo/ragbench) · [数据卡](https://huggingface.co/datasets/galileo-ai/ragbench) | **仅用于 evaluator/reader 回归与 judge 校准。** 不是 raw document→index→retrieve→answer 主榜。数据卡标 CC-BY-4.0，但正式商业使用仍应逐字段和原始子数据审计来源权利。
| CRAG | [事实] 4,409 个 factual QA，5 个域、8 类问题，带 mock Web/KG API并强调时效；评分把正确记 +1、缺答 0、错误 -1。官方仓库许可证为 **CC BY-NC 4.0**。[论文](https://arxiv.org/abs/2406.04744) · [官方仓库](https://github.com/facebookresearch/CRAG) | **不进入商业正式集。** 可借鉴动态、冲突和“宁缺勿错”任务设计；除非取得许可，不把数据用于商业产品排名。它也不测企业 PDF ingestion。
| KILT | [事实] 将 11 个数据集统一到固定 Wikipedia 快照，并用 provenance-aware 指标把任务答案与证据联系起来；官方仓库现为归档状态，语料基于较老 Wikipedia 快照。[论文](https://arxiv.org/abs/2009.02252) · [Meta 介绍](https://ai.meta.com/blog/introducing-kilt-a-new-unified-benchmark-for-knowledge-intensive-nlp-tasks/) · [仓库](https://github.com/facebookresearch/KILT) | **研究/回归辅轨，非主轨。** provenance 思路值得复用，但语料年代、百科域、体量与企业文档格式均不匹配。
| BEIR | [事实] 18 个异质 IR 数据集，关注 zero-shot retrieval；官方实现常用 nDCG@10，并明确只是分发/接入各数据集、使用者需自行遵守每个原始许可证。[论文](https://arxiv.org/abs/2104.08663) · [官方仓库](https://github.com/beir-cellar/beir) | **保留为可观测 retrieval 组件辅轨。** 只能在平台能返回 ranked results 时使用；逐数据集做许可白名单，不能把分数与平台 E2E 分混算。
| MTEB | [事实] 当前官方目录覆盖大量 embedding tasks，retrieval task 元数据包含语言、域和 license，常以 nDCG@10 为 main score。[官方文档](https://docs.mteb.org/) · [Retrieval tasks](https://docs.mteb.org/overview/available_tasks/retrieval/) · [两阶段示例](https://docs.mteb.org/get_started/advanced_usage/two_stage_reranking/) | **只选少量任务用于 embedding/retrieval 控制实验。** 必须记录精确 task revision、language、license 与数据 hash；不能宣称“跑完整 MTEB”就是平台评测。
| BRIGHT | [事实] reasoning-intensive retrieval，12 个域/数据集，官网使用 mean nDCG@10；当前官网写 1,385 queries，而原始论文摘要写 1,384，说明版本已变化。[官网](https://brightbenchmark.github.io/) · [论文](https://arxiv.org/abs/2407.12883) | **P1 可选的推理型检索压力集。** 仅用于暴露 ranked chunks 的平台，冻结确切 revision/hash；不作为原始 PDF 或 E2E 主榜。

**[推断] 公开集组合结论：** 上述项目中，没有一个可直接替代自建企业原始文档集。合理组合是：RAGAS（必要时 ARES）做评测器；RAGBench做 evaluator 回归；许可通过的 BEIR/MTEB/BRIGHT 子集做组件检索辅轨；CRAG只借鉴设计；KILT只作历史 provenance 研究。

## 5. 竞品与可测接口：自部署主轨

### 5.1 RAGFlow —— 升为 P0 主竞品

**[事实]** 官方将 RAGFlow 描述为面向企业的 RAG/context layer 与 Agent 平台，支持复杂文档理解、模板化 chunk、可追踪引用、Word/Slides/Excel/TXT/图片/扫描件/结构化数据/网页，支持 Docker 自部署；官方 README 截止日示例固定 stable tag，而非要求使用 nightly（[README](https://github.com/infiniflow/ragflow/blob/main/README.md)）。许可证为 [Apache-2.0](https://github.com/infiniflow/ragflow/blob/main/LICENSE)。

**[事实] 可自动化面：** 官方 [HTTP API reference](https://github.com/infiniflow/ragflow/blob/main/docs/references/http_api_reference.md) 包含：

- `POST /api/v1/datasets/{dataset_id}/documents`：multipart 上传多个文件；
- `POST /api/v1/datasets/{dataset_id}/chunks`：内置切分/解析；使用 ingestion pipeline 时改用 `POST /api/v1/documents/ingest`；
- `GET /api/v1/datasets/{dataset_id}/documents?...`：返回 `UNSTART/RUNNING/CANCEL/DONE/FAIL`、progress、progress message、chunk/token counts 等，可计算 time-to-searchable；
- `POST /api/v1/retrieval`：返回 chunk、document/dataset IDs、position、content、similarity/term/vector score，并支持阈值、top-k、rerank、metadata 等；
- `POST /api/v1/openai/{chat_id}/chat/completions` 及原生 chat API：回答可附 reference chunks；应显式开启 reference 并保存原始 response。

**[事实] 成本快照：** 官方 [价格页](https://ragflow.io/) 的 Free 无 API key；Starter/Pro 有 API key，页面当前主显示约 `$29/月` 与 `$129/月`，另有不同显示价/促销价，正式报价须以结算页为准；Enterprise 支持 BYOC/on-prem、定制 SLA。自部署成本另含基础设施、模型、embedding、reranker/OCR 与运维。

**[建议]** RAGFlow 是最应优先实现 adapter 的同类产品：接口能把 L1/L2/L3/L4 分开测。固定 release tag、镜像 digest 和 parser pipeline；不得用 `main` 或 nightly。官方 release notes 的检索/API bug 修复频繁，版本漂移是主要风险。

### 5.2 Dify —— P0 主竞品，观测性强

**[事实]** Dify 是可自部署的 LLM app/agent/workflow/RAG 平台；许可证是带多租户与前端 logo 限制的 **modified Apache-2.0**，不是无附加条件 Apache-2.0（[仓库](https://github.com/langgenius/dify)、[LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE)）。官方当前文件列表含 PDF、Office、Excel/CSV、Markdown、HTML/XML、EPUB、EML/MSG 等，页面提示单文件通常 15MB、受套餐影响（[官方教程](https://dify.ai/blog/create-knowledge-in-dify-for-beginners)）。

**[事实] 可自动化面：**

- [Create Document by File](https://docs.dify.ai/en/api-reference/documents/create-document-by-file)；
- [Get Document Indexing Status](https://docs.dify.ai/en/api-reference/documents/get-document-indexing-status)，能区分 waiting/parsing/cleaning/splitting/indexing/completed/error；
- [Test Retrieval](https://docs.dify.ai/en/api-reference/knowledge-bases/retrieve-chunks-from-a-knowledge-base-test-retrieval)；
- [Send Chat Message](https://docs.dify.ai/en/api-reference/chat-messages/send-chat-message) 的 blocking response 包含 `metadata.usage`（token、单价、总价、币种、latency）及 `metadata.retriever_resources[]`（dataset/document/segment IDs、score、content）。

**[风险]** Agent/New Agent 与 Chatbot/Chatflow 的 blocking/streaming 与 retriever event 形态不同。正式评测应选择能稳定返回 `retriever_resources` 的 Chatbot/Chatflow 路径，并把应用类型写入配置，不能把不同 app type 混跑。

**[事实] 成本快照：** [Dify Cloud](https://dify.ai/pricing/dify-cloud) 当前 Sandbox 免费（50 documents/50MB、10 knowledge requests/min、5,000 API calls/月），Professional `$59/workspace/月`（500 docs/5GB、100 knowledge requests/min），Team `$159/workspace/月`（1,000 docs/20GB、1,000 knowledge requests/min）；credits 按模型消耗并可 BYOK。自部署仍需把 license/基础设施/模型等分项核算。

### 5.3 FastGPT —— P0 主竞品，需钉死版本化 schema

**[事实]** FastGPT 支持 Docker 自部署、知识库 search test、聊天引用、调用链日志、应用评估、混合检索/重排；其开源许可证同样是 Apache-2.0 加多租户 SaaS 与 logo 附加条件（[仓库](https://github.com/labring/FastGPT)、[许可证说明](https://doc.fastgpt.io/en/guide/version/opensource/license)）。

**[事实] 可自动化面：**

- [Dataset API](https://doc.fastgpt.io/en/openapi/dataset) 提供知识库创建、`POST /api/core/dataset/collection/create/localFile` 文件导入（该端点文档列 PDF/DOCX/MD/TXT/HTML/CSV）、collection/chunk 列表与 `searchTest`；
- [Chat API](https://doc.fastgpt.io/en/openapi/chat) 为 `POST /api/v1/chat/completions`，但 `model`、`temperature` 由 workflow 决定而忽略请求值；设置 `detail=true` 后 `responseData` 可含 dataset search、score/limit、`quoteList`、node running time、points/tokens；标准 `usage` 示例只是占位值，官方明确“不返回实际 Token”，须从 `responseData` 或上游账单另算；
- [API intro](https://doc.fastgpt.io/en/openapi/intro) 明确从 4.15.0 起以部署实例的 `/apidoc/devapi`、`/apidoc/systemopenapi` 自动生成文档，手写侧栏不再持续更新。

**[建议]** 安装后先快照生成的 OpenAPI schema，固定版本、app/workflow export、模型和 `detail=true`。引用/检索可测，但 token/货币成本必须独立计量，不可直接相信 OpenAI `usage` 占位值。

**[事实] 成本快照：** 官方 [云价格页](https://fastgpt.io/en/price) 当前 Free `¥0`（600 KB indexes、30 QPM）、Basic `¥99/月`（6,000 indexes、300 QPM）、Advanced `¥599/月`（36,000 indexes、1,500 QPM）；credits 是平台计量，不等同于统一货币 token 成本。官方 [商业版](https://doc.fastgpt.io/en/guide/version/commercial) 的托管与自部署另行定价。

### 5.4 MaxKB —— P1 条件竞品

**[事实]** MaxKB 是 GPLv3 的自部署企业 Agent/RAG 平台（[仓库](https://github.com/1Panel-dev/MaxKB)）。[文档导入](https://maxkb.cn/docs/v2/user_manual/dataset/doclist/) 支持 TXT/Markdown/PDF/DOCX/HTML/XLS/XLSX/CSV/ZIP、文件夹上传，每批默认最多 50、单文件 100MB，并支持同步、重新向量化、导出、替换；[APIKey chat](https://maxkb.cn/docs/v2/dev_manual/APIKey_chat/) 兼容 OpenAI Chat API；[对话日志](https://maxkb.cn/docs/v2/user_manual/app/log/) 在 UI/导出中能看到引用分段。

**[事实] 成本/权限：** [官方价格页](https://maxkb.pro/pricing) OSS 免费自部署（最多 2 users/5 apps/50 KB），Pro 年付询价；对比表把完整 Open API 列为 Pro 能力。没有 SaaS 月订阅。

**[风险/建议]** 公开 Chat API 页面没有稳定展示机器可读 citations/retrieval response schema，平台管理 API 又可能需要 Pro。先用 10 documents/30 QA 做 adapter gate：自动导入、就绪状态、独立 retrieval、answer citations 四项都能取到才入正式榜；否则只做 UI E2E/人工引用检查，不进入可观测 retrieval 榜。

## 6. 云托管工程参照（独立赛道）

### 6.1 Amazon Bedrock Knowledge Bases

**[事实]** Bedrock KB 可连接 S3、Confluence、custom、Google Drive、OneDrive、SharePoint、Web Crawler；非结构化资料包含 text、Markdown、HTML、PDF 及图像/多模态，处理链为 parse→chunk→embedding→vector store（[数据源与 ingestion](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-how-data.html)）。`IngestKnowledgeBaseDocuments` 可直接写入 custom/S3 data source，API 每次上限 25 documents（[direct ingestion](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-direct-ingestion-add.html)）。

**[事实] 可测输出：** `Retrieve` 返回 ranked source chunks/images；`RetrieveAndGenerate` 返回 answer 与 `citations[].retrievedReferences`，并提供输出 span；新 Managed Knowledge Base 另有 `AgenticRetrieveStream` trace，不能把两种 KB/SKU 的 API 和价格混用（[retrieval overview](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-how-retrieval.html)、[RetrieveAndGenerate API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html)）。Bedrock 自带 RAG evaluation，区分 retrieve-only 与 retrieve-and-generate，指标含 context relevance/coverage、correctness、completeness、faithfulness、citation precision/coverage、refusal 等，但 judge token 会计费（[评测概览](https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-kb.html)、[指标](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-eval-retrieve.html)）。

**[事实] 成本快照：** [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) 当前 Managed KB 列 `$5/GB raw data/月`、standard Retrieve `$1/1000 calls`、agentic retrieval `$4/1000 agentic calls` 加 `$1/1000 underlying Retrieve calls`；内置 parser/embedding/reranker在该 SKU 中列为包含。选择自有模型或 self-managed KB 时另计 parser、embedding、reranker、vector store、LLM 与数据服务；RAG judge token 也另计。

**[建议]** 云轨先固定“self-managed KB + Retrieve + RetrieveAndGenerate”或“Managed KB + AgenticRetrieveStream”中的一种。前者更适合 L2/L3/L4 分层，后者更适合当前托管 agentic 形态；不得混成一个 Bedrock 条目。

### 6.2 Google Agent Search / Vertex AI Search 与 Vertex AI RAG Engine

**[事实] 产品边界不同：** Agent Search（原 Vertex AI Search/AI Applications）是完整企业搜索与 grounded answers 服务；Vertex AI RAG Engine 是 corpus、import、RetrieveContexts 与模型 grounding 的 RAG 组件服务。主云平台参照应选前者，后者只作工程组件参照。

**[事实] Agent Search 可测面：** unstructured search 可接 PDF、HTML、TXT、JPEG/PNG 等 Cloud Storage/BigQuery 数据，也支持 `ImportDocuments` 或 streaming CRUD（[custom search](https://docs.cloud.google.com/generative-ai-app-builder/docs/about-generic-search)、[准备导入](https://docs.cloud.google.com/generative-ai-app-builder/docs/prepare-data)）。`search` 返回结果，`:answer` 能通过 `answerGenerationSpec.includeCitations=true` 返回按句 citation metadata（[Answer API](https://cloud.google.com/generative-ai-app-builder/docs/answer)）。

**[事实] RAG Engine 可测面：** `ImportRagFiles` 可从 GCS、Drive，并在当前 API 中扩展到 Slack/Jira/SharePoint；response 直接给 imported/failed/skipped counts；`RetrieveContexts` 支持 top-k 和 hybrid alpha；`GenerateContentResponse` 的 retrieved context 包含 URI/title/text/documentName（[RPC/API](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rpc/google.cloud.aiplatform.v1)、[RAG release status](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/release-notes)）。RAG Engine 的 managed DB 使用 Spanner，基础/扩展 tier 会形成固定计算与存储成本（[RagEngineConfig](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/RagEngineConfig)、[Spanner pricing](https://cloud.google.com/spanner/pricing)）。

**[事实] Agent Search 成本快照：** [官方价格](https://cloud.google.com/generative-ai-app-builder/pricing) 的 General 模式当前 Standard Search `$1.50/1000 queries`、Enterprise `$4/1000`、Advanced Generative Answers 另加 `$4/1000`；index storage 约 `$5/GiB/月`（前 10GiB 免费）。Layout Parser、OCR、ranking 和所选生成模型有各自计费项。

**[建议]** 正式报告将 Agent Search 的 search、answer/citations、storage/parser/model 成本逐项记录；RAG Engine 不与 Agent Search 同名合并，也不与 MOI 自部署成本直接排名。

### 6.3 Azure AI Search / Foundry IQ

**[事实]** Azure AI Search 的 classic `Search Documents` API 可返回 `@search.score`、semantic `@search.rerankerScore`、captions 与 extractive answers；其 indexer/skillset 支持导入、OCR、layout-aware chunk、integrated vectorization（[Search REST](https://learn.microsoft.com/en-us/rest/api/searchservice/documents/search-post?view=rest-searchservice-2026-04-01)、[RAG overview](https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview)、[Document Layout skill](https://learn.microsoft.com/en-us/azure/search/search-how-to-semantic-chunking)）。

**[事实] Agentic retrieval：** 2026-04-01 GA API 支持最小 extractive retrieval；`2026-05-01-preview` 才提供完整 messages、answer synthesis、reasoning effort 与部分多模态能力。`retrieve` response 包含 extracted/synthesized answer、activity 与 references；activity 给 subqueries、elapsed、模型 token 等，references 提供可用于 citation linking 的 ID/docKey/sourceData（[retrieve API](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve)、[概念](https://learn.microsoft.com/en-us/azure/search/search-agentic-retrieval-concept)）。Preview 无 SLA，不可在一半产品用 GA、另一半用 Preview 后仍宣称公平。

**[事实] 成本：** [官方价格页](https://azure.microsoft.com/en-us/pricing/details/search/) 是地区/协议动态价，Dedicated 按 Search Unit 容量，Serverless preview 按 CU-hour 与 indexed storage；semantic ranker、agentic retrieval token、document image extraction及 Azure OpenAI 另计。页面当前列 agentic retrieval 每月前 50M tokens 免费、semantic ranker 前 1,000 requests 免费，但实际单价必须在同地区、同协议的 calculator/账单中快照。

**[建议]** 第一轮优先 classic GA retrieval 做可重复 L2；如评估 agentic answer synthesis，则所有云产品另开 `agentic-preview` 赛道，固定 API version，并把模型 token 与 search 费用分别入账。

## 7. 越界/轻量参照，不进入主榜

| 产品 | 官方可测事实 | 成本/许可证 | 本项目位置 |
|---|---|---|---|
| AnythingLLM | 官方仓库支持本地/Docker、文档工作区、source citations 与 developer API；常用入口为 document upload 与 workspace chat，近期 release 提到 API sources 返回。[仓库](https://github.com/Mintplex-Labs/anything-llm) · [releases](https://github.com/Mintplex-Labs/anything-llm/releases) | MIT；自部署基础设施和模型成本，无同类企业平台固定 TCO | 仅本地/私有轻量 UX sanity check；不与 MOI 主榜排名 |
| Quivr | 当前官方主线是可嵌入的 `quivr-core`，以 `Brain.from_files(...)`、`brain.ask(...)` 形式提供 PDF/TXT/MD 等 RAG workflow，可配置 LLM/reranker/vector store。[仓库](https://github.com/QuivrHQ/quivr) · [Core docs](https://core.quivr.com/en/latest/brain/) | Apache-2.0；基础设施与模型成本 | 框架/组件控制，不是匹配的一体化企业平台 |
| Open WebUI | API 文档有 `POST /api/v1/files/`、process status、knowledge file add、`POST /api/chat/completions`；支持多种 vector DB/extractor 与知识库 citations。[API](https://docs.openwebui.com/reference/api-endpoints/) · [Knowledge](https://docs.openwebui.com/features/workspace/knowledge/) · [仓库](https://github.com/open-webui/open-webui) | 0.6.6+ 为带 branding 限制的 Open WebUI License，不应称 OSI 开源；自部署成本 | 通用 LLM UI 的可自动化边界参照，非企业 Data+AI/RAG 主竞品 |

**[建议]** NotebookLM、ChatDOC、MoiAI 不建 adapter、不进入主轨；如正文提及，只用于解释为何“个人文档问答 UX”不能代表 MatrixOne Intelligence 的企业平台边界。

## 8. 自建数据设计：200 documents / 1,000 QA

### 8.1 文档层

**[建议]** 使用企业自有、明确授权或新合成的 200 个原始文档；公开 benchmark 只在独立辅轨使用。按主要困难分层，标签允许交叉：

| 主层 | 数量 | 必含难点 |
|---|---:|---|
| 简单 TXT/Markdown/HTML | 30 | 基线、标题、列表、代码、中文/英文 |
| born-digital 复杂 PDF | 35 | 双栏、页眉页脚、脚注、跨页段落、目录 |
| 扫描 PDF/OCR | 30 | 倾斜、噪声、印章、混合字体、中英混排 |
| 表格/财务/Excel | 30 | 合并单元格、单位、负数、跨页表、公式结果 |
| Slides/图片/图表 | 25 | 图例、坐标、流程图、图片文字、讲者备注 |
| 长手册/规章 | 25 | 100+ 页、层级章节、定义与例外、跨章证据 |
| 版本/冲突/跨文档 | 25 | 新旧政策、撤销条款、相似文件名、时间有效性 |
| 合计 | 200 | 对每个文档记录 SHA-256、license、语言、页数、敏感级别、版本时间 |

另为全部文档打语言（中文/英文/混合）、布局、是否扫描、是否含表格/图片、版本族、权限分区标签。不要按随机页面切分 dev/test；按 **document family** 切分，防止同一模板或版本泄漏。

### 8.2 QA 与 gold schema

| 问题类型 | 数量 | 评分重点 |
|---|---:|---|
| 单证据直接问答 | 220 | 第一证据 rank、答案正确、引用定位 |
| 同文档多证据/条件与例外 | 180 | evidence-set completion、完整性 |
| 跨文档多跳 | 160 | 找齐证据、推理、每个 claim 的引用 |
| 表格/数值/单位 | 120 | cell provenance、运算、单位与舍入 |
| 布局/图片/图表 | 100 | parser coverage、视觉证据引用 |
| 版本/冲突/最新有效 | 80 | 新鲜度、冲突说明、旧版不误引 |
| 不可回答/范围外 | 100 | 拒答 recall 与假拒答率 |
| ACL/租户隔离 | 40 | 零泄漏硬门槛 |
| 合计 | 1,000 | 中英与混合问法、短/长问法、真实噪声 |

每条 gold 至少包含：`question_id`、question、answerable、required claims（权重）、一个或多个合法 evidence sets、document/version ID、page、bounding box 或 normalized text span、evidence content hash、ACL principal、question type/difficulty/language、允许的数值 tolerance、合法拒答规则。chunk ID 由平台决定，**不能作为 gold 主键**；通过页面/span/hash 将平台 chunk 映射回 gold。

**[建议]** 40 documents/200 QA 作开发集，20 documents/100 QA 作 adapter pilot，140 documents/700 QA 密封为正式集。正式集在冻结适配器、模型和阈值后才解封。每个可答问题至少有一条硬负例；10% 问题做等义改写，检测表达稳定性。

## 9. 可执行流程与 adapter 合同

### 9.1 预注册与环境冻结

1. 记录产品版本/tag、镜像 digest、部署拓扑/套餐/地区、CPU/GPU/RAM、模型 provider 与精确 model ID、embedding/reranker、parser/OCR、chunk/top-k/threshold、API version、系统 prompt hash。
2. 每产品建两轨：`native-default` 与 `bounded-tuned`。调优轨只允许统一预算（例如最多 20 次 dev 实验/4 人时），所有改动留审计日志。
3. 清空或新建隔离 workspace/index；导入前记录 corpus manifest 和 SHA-256。禁用无法统一的外部 Web search、memory 和非语料工具。

### 9.2 统一 adapter 最小输出

```json
{
  "run_id": "...",
  "system": "ragflow|dify|fastgpt|moi|...",
  "system_version": "...",
  "track": "native-default",
  "question_id": "...",
  "request_started_at": "...",
  "answer": "...",
  "status": "ok|timeout|throttled|error",
  "latency_ms": 0,
  "ttft_ms": null,
  "retrieved": [
    {"rank": 1, "document_id": "...", "document_name": "...", "chunk_id": "...", "page": null, "content": "...", "score": null, "raw": {}}
  ],
  "citations": [
    {"answer_start": null, "answer_end": null, "document_id": "...", "page": null, "span": null, "uri": null, "raw": {}}
  ],
  "usage": {"input_tokens": null, "output_tokens": null, "currency": null, "amount": null},
  "retry_count": 0,
  "raw_response_path": "..."
}
```

`null` 表示平台未提供，不能以 0 替代；所有 raw request/response、headers 中的 request ID、stream events、状态轮询结果和账单导出要留存。涉及密钥/个人数据时先脱敏。

### 9.3 运行顺序

1. 导入 corpus，记录每个文件的 accepted/error；轮询官方状态，再用唯一探针测首次可检索时刻。
2. 对可观察平台先跑独立 retrieval，保存完整 top-k；再用**新 session** 跑 answer，避免历史污染。平台只有 E2E API 时，retrieval 指标标 N/A。
3. 问题顺序按系统×问题的配对随机化；统一并发档（1、5、20 或按目标 SLO），记录冷/暖缓存。
4. 第一次结果始终入账；允许的重试另存 eventual result，不覆盖 initial failure。
5. 至少对 10% 正式问题重复 3 次，估计非确定性；关键差异使用 paired bootstrap 95% CI。按问题类型、文档类型、语言和可答性分层报告，不只给 macro average。
6. 先跑 deterministic metrics，再跑冻结的 RAGAS/ARES/judge；从正式结果中抽分层样本做盲人工复核。裁判看不到产品名称。
7. 最后跑更新、删除、ACL、故障恢复和并发；这些测试需要独立 workspace，避免污染质量主集。

## 10. 评分、门槛与报告方式

### 10.1 硬门槛

**[建议]** 以下任一项失败即标红，不用高答案分抵消：

- ACL/租户越权泄漏 > 0；
- 正式语料可检索率低于预注册阈值（建议 99%）；
- 无法导出答案或引用，导致核心任务不可审计；
- 未经披露的人工修复、手工重传或隐式外部搜索；
- 版本、模型或套餐在正式运行中发生变化；
- license/数据使用权未通过审计。

### 10.2 分层面板，而非单一总分

建议发布 8 张 scorecard：ingestion/readiness、parser、retrieval、answer、citation、abstention/security、performance/reliability、cost/operability。每张给总体、分层、95% CI、样本数与 N/A 原因。

若管理层要求综合分：只在“自部署主轨”内部、通过硬门槛后计算；在解封正式集之前固定权重，例如质量 60%（retrieval 20、answer 20、citation 20）、可靠性 20%、性能 10%、成本/运维 10%。**[风险]** 此权重是业务选择，不是学术标准；必须同时展示原始分项，且云托管、组件和越界参照不纳入该排名。

### 10.3 全栈成本合同

每个系统统一记录：

`TCO = license/subscription + amortized infrastructure + parser/OCR + embedding + vector store + reranker + generation model + network/egress + operator labor`。

同时发布：固定月成本、一次全量 ingest 成本、增量更新成本、1,000 次 query 边际成本、每次成功且正确回答的成本。Dify response price、FastGPT points、AWS/Google/Azure账单等只是某些分项；不同单位未经账单映射不能直接比较。

## 11. 最终竞品组合与实施优先级

| 优先级 | 系统 | 赛道 | 决策 |
|---|---|---|---|
| P0 | MOI、RAGFlow、Dify、FastGPT | 自部署/一体化企业 RAG 主轨 | 全量 200 docs/1,000 QA；RAGFlow 明确由可选升级为主竞品 |
| P1 gate | MaxKB Pro/OSS 可测配置 | 自部署条件竞品 | 10 docs/30 QA adapter pilot 通过导入/就绪/retrieval/citation gate 后再全量 |
| P1 | Bedrock KB、Agent Search/Vertex AI Search、Azure AI Search | 云托管工程参照 | 同数据、同问题，独立榜；冻结 region/SKU/API GA/Preview 与账单 |
| P2 | 许可通过的 BEIR/MTEB/BRIGHT 子集 | 组件检索辅轨 | 只测暴露 ranked retrieval 的系统，不混 E2E 分 |
| 边界 | AnythingLLM、Quivr、Open WebUI；NotebookLM/ChatDOC | 轻量/框架/UX | 不进入主榜；仅解释产品边界或做小样本 sanity check |

**[建议] 最短落地路径：** 先为 MOI、RAGFlow、Dify、FastGPT 实现四个 adapter，用 20 docs/100 QA（其中至少 10 个复杂 PDF/扫描/表格）关闭 schema 与引用映射问题；然后扩到 200/1,000。云轨优先 Bedrock self-managed KB（Retrieve/RetrieveAndGenerate 边界最清楚），第二批加入 Azure GA classic retrieval 与 Google Agent Search；agentic Preview 统一另开赛道。

## 12. 未决风险清单

1. **MOI 本身的可测接口尚需冻结：** Explore/chat API、独立 retrieval/trace、引用 page/span、索引状态、usage 与 request ID；若只有 UI，应预先定义可重复的浏览器自动化与人工引用协议。
2. **生成模型公平性：** 平台未必支持同一 provider/model，且 FastGPT会忽略 request model/temperature。主结果应分“同模型可控子集”与“各平台最佳原生体验”，不可混称同条件。
3. **文档解析差异：** 文件被平台拒收必须留在分母；禁止把失败文件预先转 Markdown 只为某一产品补救。可另开“预处理统一输入”组件轨，但与原生轨分开。
4. **引用可观察性：** UI 展示引用不等于 API 可导出、也不等于引用支持 claim。MaxKB、Open WebUI、AnythingLLM 需 pilot 验证 response schema；无证据时标 N/A。
5. **版本漂移：** RAGFlow/FastGPT/Dify/Azure 等接口变化快；保存镜像 digest、OpenAPI snapshot、完整 raw responses。正式运行期间不升级。
6. **许可：** CRAG 为非商业；BEIR/MTEB/RAGBench 所接子数据需逐项审计；自建企业文档也需记录授权、脱敏和保留期限。
7. **动态价格/免费额度：** 免费额度、促销价和区域价不能当长期 TCO。以同一日期、地区、币种的报价与账单为准，并提供成本敏感性分析。
8. **Judge 偏差：** 同一 judge 可能偏好某种答案风格或语言；人工校准、分语言误差和 judge 版本 hash 是发布前门槛。

---

### 证据强度说明

本文对“接口存在、字段、格式、许可证、官方价格与 Preview/GA”使用官方页面或论文；对“应进入哪条赛道、采用何种数据配比、硬门槛、权重和统计流程”明确标为项目建议。后者是为 MatrixOne Intelligence 企业 Data+AI/RAG 边界设计的可执行方案，不应误写成行业已统一标准。
