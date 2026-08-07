# RAG 平台竞品调研报告：Dify、FastGPT、RAGFlow、MaxKB

> 调研日期：2026-08-06（Asia/Shanghai）  
> 调研对象：Dify、FastGPT、RAGFlow、MaxKB  
> Benchmark 环境：macOS / Apple Silicon / 16 GiB，Colima `linux/arm64`；模型与 Embedding 使用 MatrixOrigin TaaS OpenAI-compatible endpoint，服务本体要求在本机运行。  
> 本文是产品与接入调研，不是效果排名。未经同一 corpus、模型、Embedding、切分策略、检索参数和重复次数约束，不比较答案质量高低。

## 1. 执行摘要

四个平台都覆盖“知识库 + RAG + 应用/智能体”，但产品中心不同：

- **Dify** 是通用 LLM 应用开发与 LLMOps 平台。知识库只是应用、Chatflow、Workflow、Agent 的一个基础能力；模型插件、工具插件、数据源插件和公开 Service API 较完整。它最适合作为本 benchmark 的“标准 API 型、应用编排型 RAG”代表。[官方仓库](https://github.com/langgenius/dify)将其定位为包含 AI Workflow、RAG Pipeline、Agent、模型管理与可观测能力的应用平台。
- **FastGPT** 更聚焦“知识库问答 + 可视化 AI 工作流”。其 Dataset API 明确公开建库和 `searchTest`，Chat API 提供 OpenAI-compatible 入口，并能用 `detail=true` 返回工作流中间数据，适合同时测 Direct Retrieval 与 Native QA。[官方产品仓库](https://github.com/labring/FastGPT)、[Dataset API](https://doc.fastgpt.io/en/openapi/dataset)、[Chat API](https://doc.fastgpt.io/en/openapi/chat)。
- **RAGFlow** 的差异点是复杂文档理解、模板化切分、混合检索、重排和可追溯引用，产品主轴最接近“文档 ETL/Context Engine + RAG/Agent”。公开 HTTP API 同时覆盖 Dataset、Document、Chunk、Retrieval 和 OpenAI-compatible Chat；但官方预构建镜像只面向 x86，且资源门槛最高。[官方仓库与部署要求](https://github.com/infiniflow/ragflow)、[v0.26.4 HTTP API contract](https://github.com/infiniflow/ragflow/blob/v0.26.4/docs/references/http_api_reference.md)。
- **MaxKB** 强调企业知识库、智能体、工作流和低门槛交付。知识库侧支持通用文档、Web、飞书和工作流知识库；应用侧提供 OpenAI-compatible 对话。其 UI 功能完整，但社区版公开材料对“API-key 可调用的独立检索 API”承诺弱于前三者，因此 benchmark 接入需要把 UI/admin route 与稳定公共 API 严格分开。[产品介绍](https://maxkb.cn/docs/v2/)、[知识库文档](https://maxkb.cn/docs/v2/user_manual/dataset/dataset/)、[通过 API Key 对话](https://maxkb.cn/docs/v2/user_manual/chat_to_API/)。

对当前 benchmark 的优先级建议是：

1. 以 Dify 作为第一条完整竞品基线，保留 Knowledge API、Native QA 和原始 `retriever_resources`。
2. FastGPT 保留已经跑通的 ingest/retrieval，单独修复 Native QA 超时，不重复建库。
3. MaxKB 先完成实例版本的公开 OpenAPI discovery；没有公开 Direct Retrieval contract 时继续使用 `UNSUPPORTED_API`，不能用内部 `hit_test` 替代正式结果。
4. RAGFlow 只有在本机资源达到官方门槛后再启动；在此之前只保存官方 contract，所有本地能力均为 `BLOCKED_LOCAL`。

## 2. 研究口径与状态词

### 2.1 三层证据

本文把证据分成三层：

1. **官方声明**：官方官网、官方文档和官方仓库对定位、功能、部署要求的描述。
2. **源码/API contract**：固定版本的公开路由、请求字段、响应字段与许可证。存在 contract 不代表本项目已经成功调用。
3. **本项目实测**：仅指当前 Apple Silicon + Colima 主机、固定版本、MatrixOrigin TaaS provider 和三文档 fixture 的实际结果。本地偶发故障、版本差异或单机资源限制，不外推为产品普遍事实。

### 2.2 唯一允许的结论状态

| 状态 | 本文含义 |
| --- | --- |
| `SAME_CONTRACT` | 同版本下，本地与官方/云端公开合同的路径、认证及核心字段可直接映射，并已获得足够证据。 |
| `LOCAL_VARIANT` | 核心业务流程相同，但初始化、provider、存储、端口、资源或运维责任由本地承担。 |
| `CLOUD_ONLY` | 官方只在托管服务承诺该能力，当前 self-hosted 形态没有同等公开承诺。 |
| `LOCAL_ONLY` | 本项目或本地扩展提供、云端默认流程没有的能力。 |
| `VERSION_DIVERGENCE` | 文档、源码、运行镜像或响应字段因版本不一致而不能视为同一合同。 |
| `BLOCKED_LOCAL` | 当前主机架构、资源或本地执行条件阻止了该能力的验证。 |
| `UNSUPPORTED_API` | 未找到可由目标认证方式调用的稳定公开 API；UI 或内部 route 不构成公共合同。 |

## 3. 产品形态与开源边界

| 平台 | 核心定位 | 开放源码与许可证 | Self-hosted | 官方托管/商业形态 |
| --- | --- | --- | --- | --- |
| Dify | 通用 LLM 应用平台：Workflow、RAG、Agent、模型管理、LLMOps | Dify Open Source License，基于 Apache 2.0 并附加多租户与前端标识条件；应以[仓库 LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE)为准 | Community Edition Docker Compose；官方最低 2 CPU / 4 GiB，[部署入口](https://github.com/langgenius/dify#quick-start) | Dify Cloud、企业/VPC 形态；[官方仓库版本说明](https://github.com/langgenius/dify#using-dify) |
| FastGPT | 知识库问答、RAG 与可视化 AI 工作流 | FastGPT Open Source License，基于 Apache 2.0 并附加多租户 SaaS、Logo 等条件；[仓库 LICENSE](https://github.com/labring/FastGPT/blob/main/LICENSE) | Community Edition Docker Compose，可选 PgVector、Milvus、OceanBase、SeekDB 等；[部署文档](https://doc.fastgpt.io/en/self-host/deploy/docker) | 中国与国际 Cloud、商业版和托管部署；[Cloud 说明](https://doc.fastgpt.io/en/guide/version/cloud/intro)、[版本对比](https://doc.fastgpt.io/en/guide/version/commercial) |
| RAGFlow | 复杂文档 ETL、Context Engine、混合检索、RAG 与 Agent | Apache License 2.0；[仓库 LICENSE](https://github.com/infiniflow/ragflow/blob/main/LICENSE) | 官方 Docker Compose 与源码部署；[官方仓库](https://github.com/infiniflow/ragflow#self-hosting) | 官方 Cloud；[Cloud 入口](https://cloud.ragflow.io/)、[官网套餐](https://ragflow.io/) |
| MaxKB | 企业知识库、智能体与工作流平台 | GPLv3；以[仓库 LICENSE](https://github.com/1Panel-dev/MaxKB/blob/main/LICENSE)为准；部分共享资源、认证和完整 SDK 属于 X-Pack/专业版 | 社区版在线 Docker、生产推荐离线包；[在线安装](https://maxkb.cn/docs/v2/installation/online_installtion/)、[离线安装](https://maxkb.cn/docs/v2/installation/offline_installtion/) | 官方资料重点是社区版、X-Pack/专业版和云主机安装；不把“部署在云服务器”视为与 SaaS 等价 |

许可证结论仅用于技术选型提示，不构成法律意见。Dify 与 FastGPT 虽公开源码，但不是无附加条件的标准 Apache 2.0；若计划把平台本身作为多租户 SaaS，应先做许可证审查。

## 4. Dify

### 4.1 定位与核心架构

**官方声明。** Dify 把 Workflow、模型接入、RAG Pipeline、Agent、LLMOps 和 Backend-as-a-Service 放在同一 workspace 中；公开 API 用于把 prompt、工作流和知识库从业务代码中分离。[官方仓库功能说明](https://github.com/langgenius/dify#key-features)、[官方介绍](https://docs.dify.ai/guides/knowledge-base/retrieval)。

**架构理解。** Self-hosted Compose 不是单容器应用，通常包括 Web/API、异步 worker、scheduler、plugin daemon、PostgreSQL、Redis、向量存储和 sandbox/SSR 防护组件。平台控制面负责应用、知识库和 provider 配置，worker 执行文档索引和工作流，模型能力通过 provider/plugin 接入。[官方 Docker Compose](https://github.com/langgenius/dify/tree/main/docker)。

### 4.2 知识库流程

典型流程为：创建 Dataset/Knowledge Base → 文件或外部数据源导入 → 文本抽取与切分 → Embedding/索引 → Dataset Retrieval 或应用中的 Knowledge Retrieval 节点 → LLM 生成 → 日志与引用。Dify 1.9.0 以后还支持 datasource plugin 作为 Knowledge Pipeline 的起点，覆盖网站、在线文档和在线网盘类型。[Datasource Plugin 官方说明](https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/datasource-plugin)。

Knowledge API 的文档列表会暴露 `indexing_status`、`error`、token、word count 等字段，因此 benchmark 应显式等待索引完成，不能把解析/索引失败归类为 retrieval miss。[获取知识库文档列表](https://docs.dify.ai/api-reference/%E6%96%87%E6%A1%A3/%E8%8E%B7%E5%8F%96%E7%9F%A5%E8%AF%86%E5%BA%93%E7%9A%84%E6%96%87%E6%A1%A3%E5%88%97%E8%A1%A8)。

### 4.3 模型与 Embedding 接入

Dify 的 Model Plugin contract 明确定义 LLM、Text Embedding、Rerank、Speech-to-Text、TTS 和 Moderation 等模型类型，并支持 predefined、customizable、remote-fetch 等配置模式。[Model API Interface](https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/model-schema)、[Model Specs](https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/model-designing-rules)。这使 OpenAI-compatible 私有 endpoint 可以通过官方插件或自定义 provider 接入；是否完全离线取决于模型、Embedding、Rerank 和数据源是否出网，而不是取决于 Dify 服务是否 self-hosted。

### 4.4 API、citation 与 trace

| 能力 | 公开合同 | 对 benchmark 的含义 | 合同结论 |
| --- | --- | --- | --- |
| Ingest | `POST /datasets`、`POST /datasets/{dataset_id}/document/create-by-file`、文档状态查询；统一入口见[API Reference](https://docs.dify.ai/api-reference) | Dataset key 与 App key 分离；等待 `indexing_status` 完成 | `SAME_CONTRACT` |
| Direct Retrieval | `POST /datasets/{dataset_id}/retrieve`；固定版本合同也可见[service OpenAPI](https://github.com/langgenius/dify/blob/1.16.1/api/openapi/markdown/service-openapi.md) | 可直接保存 chunk、score、document metadata | `SAME_CONTRACT` |
| Native QA | `POST /chat-messages` | 每题使用独立 `user`/`conversation_id`，避免上下文污染 | `SAME_CONTRACT` |
| Workflow | `POST /workflows/run` | 本项目本轮没有创建并调用本地 Workflow，不能把路由存在写成实测通过 | `LOCAL_VARIANT` |
| Citation/trace | Chat response 的 `metadata.retriever_resources`，Workflow 另有运行日志 API；[Workflow logs](https://docs.dify.ai/api-reference/workflows/list-workflow-logs) | 只认原始结构化字段，不从答案文本推断来源 | `SAME_CONTRACT` |

### 4.5 扩展性、运维、适用场景与局限

- 扩展性强：模型、工具、Agent Strategy、Datasource、Trigger 和 Endpoint 均有插件类型；[插件类型说明](https://docs.dify.ai/en/develop-plugin/getting-started/choose-plugin-type)。
- 工作流与应用形态丰富，适合需要 RAG 与业务工具、条件分支、Agent 共同编排的团队。
- 运维面较宽：多容器、worker、plugin daemon、数据库、向量库与版本迁移都需要持续维护；Cloud 与 self-hosted 的业务合同接近，但资源、扩缩容和升级责任不同，属于 `LOCAL_VARIANT`。
- 主要局限：版本更新快，插件签名、provider 模型枚举、Community/Cloud 行为可能发生变化；固定 tag、compose commit、image digest 与 OpenAPI snapshot 是 benchmark 可复现性的必要条件。

### 4.6 本项目实测边界

本项目固定 Dify 1.16.1，在本地 ARM64 Compose 中完成三文档 ingest、Native QA、Direct Retrieval，并另外完成 44/44 文档 readiness；模型调用仍出网到 MatrixOrigin TaaS。该结果证明本项目配置为 `LOCAL_VARIANT`，不证明其他主机、版本或 provider 都会得到相同结果。Workflow 路由未做本地调用验证，仍为 `LOCAL_VARIANT`。

## 5. FastGPT

### 5.1 定位与核心架构

**官方声明。** FastGPT 是以 LLM 为基础的知识库平台，核心能力包括数据处理、RAG 检索、可视化 AI 工作流和应用发布。[官方仓库](https://github.com/labring/FastGPT)。

**架构理解。** 官方 Compose 以 FastGPT 主服务、MongoDB、向量数据库和 AIProxy 为核心；MongoDB 保存除向量以外的数据及 GridFS 文件，PgVector/Milvus/OceanBase/SeekDB 等保存向量，AIProxy 聚合模型 API。[Docker 部署架构](https://doc.fastgpt.io/en/self-host/deploy/docker)。官方 Dataset Design 描述的导入路径是：文件进入 MongoDB GridFS → 浏览器解析文本与 chunk → training queue → worker 生成向量 → 写入 PostgreSQL。[Dataset Design](https://doc.fastgpt.io/en/self-host/design/dataset)。

### 5.2 知识库与检索流程

Dataset 支持知识库、collection 和 data group。公开 API 可建库、推送结构化数据、执行 Search Test；检索模式包括 embedding、full-text 和 mixed recall，并可配置 query extension 与 rerank。[Dataset API](https://doc.fastgpt.io/en/openapi/dataset)。

这里有一个重要 benchmark 差异：官方设计中部分文件解析发生在浏览器，而 API 上传或结构化 `pushData` 的路径可能不同。正式评测必须固定使用同一种 ingest contract，不能把 UI 导入和 API 导入混合成同一 condition。

### 5.3 模型与 Embedding 接入

首次 self-hosted 登录至少要配置 Language Model 与 Index Model；AIProxy 负责对接和聚合模型服务。[模型配置步骤](https://doc.fastgpt.io/en/self-host/deploy/docker#6-configure-models)。Dataset 可以显式指定 `vectorModel`、`agentModel`、`vlmModel`，官方建议未特别需要时采用系统默认。[Dataset API](https://doc.fastgpt.io/en/openapi/dataset)。

对 benchmark 而言，Language Model 与 Index Model 必须分别 probe；一个 provider channel 创建成功不等于聊天与 Embedding 两条模型调用都通过。还应记录向量维度，已有 corpus 更换 Embedding 后需重新索引。

### 5.4 API、citation 与 trace

| 能力 | 公开合同 | 对 benchmark 的含义 | 合同结论 |
| --- | --- | --- | --- |
| Ingest | `POST /api/core/dataset/create`；collection/file 与 `pushData` 接口由实例 OpenAPI/官方 Dataset API 给出 | 从 4.15.0 起官方建议以实例 `/apidoc/devapi`、`/apidoc/systemopenapi` 为准 | `VERSION_DIVERGENCE` |
| Direct Retrieval | `POST /api/core/dataset/searchTest` | 返回 `sourceName`、`sourceId`、`score` 等真实命中信息 | `SAME_CONTRACT` |
| Native QA | `POST /api/v1/chat/completions`，OpenAI-compatible；`model`、`temperature` 由工作流控制 | 每个 attempt 使用新 `chatId`；`detail=true` 保存 `responseData` | `SAME_CONTRACT` |
| Citation/trace | `detail=true` 返回工作流中间值，引用通常位于版本相关的 `responseData`/`quoteList` | 字段随工作流和版本变化，必须保存 raw response | `VERSION_DIVERGENCE` |
| API discovery | Dev API 与 System OpenAPI 分离，并非所有 Dev endpoint 都能用 API key 调用；[官方说明](https://doc.fastgpt.io/en/openapi/intro) | 只使用当前实例声明且已验证认证范围的 endpoint | `LOCAL_VARIANT` |

### 5.5 扩展性、工作流、运维、适用场景与局限

- 可视化工作流与 Dataset Search 节点紧密，Native Chat API 可以直接运行已发布应用；适合企业问答、客服、内部助手和需要可视化编排的 RAG 应用。
- 向量后端选择多。PgVector 测试规格最低 2C4G，百万级向量官方建议 4C8G/50GB；Milvus 适合更大规模，但增加运维复杂度。[官方资源建议](https://doc.fastgpt.io/en/self-host/deploy/docker#recommended-specs)。
- Community、Commercial 与 Cloud 功能存在明确差异，例如运行日志看板、应用评估、第三方知识库定时同步和部分企业能力；[官方版本对比](https://doc.fastgpt.io/en/guide/version/commercial)。比较 Cloud 与本地时不能默认所有能力都是 `SAME_CONTRACT`。
- 主要局限：公开 API 正迁移到自动生成 OpenAPI，旧手工文档不再持续更新；源码 tag 与官方 compose 中镜像版本也可能错位，需按实例保存 contract snapshot。

### 5.6 本项目实测边界

本项目在原生 ARM64 上启动 FastGPT 全栈，完成 TaaS provider、三文档索引和 `searchTest` 三条命中；Native QA 在当前工作流调用中长期无 HTTP response，因此该能力在本机记为 `BLOCKED_LOCAL`。这不代表 FastGPT Chat API 普遍不可用，也不推翻其公开 `SAME_CONTRACT`；它只说明当前 app/workflow/provider 组合仍需诊断。源码固定 v4.15.6，而 compose runtime image 为 v4.15.4，整体还存在 `VERSION_DIVERGENCE`。

## 6. RAGFlow

### 6.1 定位与核心架构

**官方声明。** RAGFlow 是融合 RAG 与 Agent 的开源 Context Engine，突出复杂文档理解、模板切分、混合检索、重排和可追溯引用。[官方仓库](https://github.com/infiniflow/ragflow)、[官网](https://ragflow.io/)。

**架构理解。** 默认 self-hosted 栈包含 RAGFlow 服务、MySQL、MinIO、Redis 和 Elasticsearch；Elasticsearch 同时承载全文与向量，官方也提供 Infinity 切换路径。DeepDoc/parser/OCR 负责复杂文档处理，Agent/Chat 层消费检索结果。[官方架构与配置](https://github.com/infiniflow/ragflow#configurations)。

### 6.2 知识库流程

流程为 Dataset → Document upload → parser/chunker → Embedding/index → Retrieval → Chat/Agent。官方强调 Word、Slides、Excel、TXT、图片、扫描件、结构化数据和网页等异构来源，并提供可视化 chunk 人工干预。[官方 Key Features](https://github.com/infiniflow/ragflow#key-features)。

固定 v0.26.4 的 HTTP API contract 覆盖 Dataset 创建、文档上传、文档解析、Chunk 管理和 `POST /api/v1/retrieval`；Native QA 则有 `POST /api/v1/openai/{chat_id}/chat/completions`。[v0.26.4 HTTP API reference](https://github.com/infiniflow/ragflow/blob/v0.26.4/docs/references/http_api_reference.md)。

### 6.3 模型与 Embedding 接入

官方支持配置 LLM、Embedding 和 Rerank，并在自托管配置中通过 `service_conf.yaml.template`、环境变量或 UI 设置模型 provider；官方镜像从 v0.22.0 起仅提供不内置 Embedding 模型的 slim 形态，依赖外部模型/Embedding 服务。[Self-hosting 与镜像说明](https://github.com/infiniflow/ragflow#self-hosting)。

这与本 benchmark 的 TaaS 方案匹配，但只能说明合同可配置。由于本地服务未启动，不能声称 MatrixOrigin TaaS 在 RAGFlow 中已经通过 provider probe。

### 6.4 API、citation 与 trace

| 能力 | 公开合同 | 对 benchmark 的含义 | 本地结论 |
| --- | --- | --- | --- |
| Ingest | Dataset、Document upload、Parse documents 和状态查询均在固定版本 HTTP API 中 | parser/OCR/Embedding/index 状态分别归档 | `BLOCKED_LOCAL` |
| Direct Retrieval | `POST /api/v1/retrieval`，支持 dataset/document 范围、阈值、top-k、rerank 等参数 | 可保存 chunk、score 与 document metadata | `BLOCKED_LOCAL` |
| Native QA | `POST /api/v1/openai/{chat_id}/chat/completions` | OpenAI-compatible 入口不等于所有 extra body 字段跨版本稳定 | `BLOCKED_LOCAL` |
| Citation/trace | `extra_body` 可请求 reference/reference metadata，产品也声明 traceable citation | 本地没有 response，不能宣称引用已可用 | `BLOCKED_LOCAL` |
| Cloud API | Cloud 套餐中免费层不提供 API key，付费层提供；[官网套餐](https://ragflow.io/) | Cloud 能力受套餐限制 | `CLOUD_ONLY` |

### 6.5 扩展性、工作流、运维、适用场景与局限

- 最适合版式复杂、扫描/OCR、多表格、多格式和要求引用可追溯的文档型场景；也适合研究 parser、chunking、hybrid retrieval 与 rerank 对效果的影响。
- Agent、MCP、数据同步和可编排 ingestion pipeline 扩展了平台边界，但也增加了实验变量；benchmark 应先禁用不必要的 Agent/tool 行为，只保留可控 RAG 路径。
- 官方最低要求为 4 CPU、16 GB RAM、50 GB disk，Docker ≥24、Compose ≥2.26.1；预构建镜像只支持 x86，ARM64 需自行构建。[官方 prerequisites](https://github.com/infiniflow/ragflow#self-hosting)。
- 运维负担在四者中最高：文档引擎、对象存储、关系数据库、缓存、解析任务和模型服务都要监控。复杂解析带来的收益必须与 ingest 延迟、资源和可复现性一起评估。
- 主要局限：ARM64 官方镜像缺失；Elasticsearch/Infinity 选择会改变检索底层；版本迭代较快，旧接口会弃用，必须固定 tag。

### 6.6 本项目实测边界

当前 Colima 只有 2 CPU、12 GiB 可用内存和约 12 GiB Docker 可用空间，低于官方 4 CPU、16 GB、50 GB；v0.26.4 主镜像还是 `linux/amd64`。因此本项目只完成静态 preflight，没有启动 RAGFlow 服务，所有本地 ingest、retrieval、Native QA 和 citation 都是 `BLOCKED_LOCAL`。这只是当前主机部署结论，不是对 RAGFlow 产品能力的否定。

## 7. MaxKB

### 7.1 定位与核心架构

**官方声明。** MaxKB 是企业级智能体平台，提供 RAG、Workflow、Agent、MCP、第三方嵌入和多模型接入，目标是降低企业 AI 应用交付门槛。[产品介绍](https://maxkb.cn/docs/v2/)。

**架构理解。** 社区版提供单镜像在线部署，也有官方推荐的生产离线安装包；持久化目录位于 `/opt/maxkb`，应用内部包含 Web/API、任务处理、PostgreSQL/向量相关数据和文档处理能力。[在线安装](https://maxkb.cn/docs/v2/installation/online_installtion/)、[备份还原](https://maxkb.cn/docs/v2/installation/backup/)。相较多容器平台，初始安装简单，但单镜像并不消除数据库备份、升级与容量管理责任。

### 7.2 知识库流程

MaxKB 支持通用型、Web 站点、飞书和工作流知识库。通用文档流程为上传 → 智能/高级分段与预览 → 自动分段 → 存储 → 向量化；工作流知识库允许数据源 → 文档解析 → 文档分段 → 知识库写入，并可接入 OCR、MinerU 或第三方分段工具。[知识库官方说明](https://maxkb.cn/docs/v2/user_manual/dataset/dataset/)。

文档支持 TXT、Markdown、PDF、DOCX、HTML、XLS/XLSX、CSV、ZIP；智能分段按 Markdown 标题层级处理，高级分段支持自定义 delimiter、长度、清洗和正则。文档完成后还可编辑分段、添加关联问题、重新向量化和执行 UI 命中测试。[文档管理](https://maxkb.cn/docs/v2/user_manual/dataset/doclist/)、[命中测试](https://maxkb.cn/docs/v2/user_manual/dataset/hit-testing/)。

### 7.3 模型与 Embedding 接入

模型管理覆盖 LLM、向量、重排、语音、视觉与图片生成，并支持 OpenAI、Azure OpenAI、DeepSeek、Ollama、vLLM、Docker AI 等 provider；部分共享模型和资源授权属于 X-Pack。[模型概述](https://maxkb.cn/docs/v2/user_manual/model/model_summary/)。Docker AI 文档明确要求 API 域名、API Key、基础模型与模型类型，可用于 OpenAI-compatible 私有服务的类比配置。[Docker AI 模型接入](https://maxkb.cn/docs/v2/user_manual/model/dockerai_model/)。

对 benchmark 必须锁定知识库向量模型、应用 LLM 与可选 rerank；更换向量模型后按官方流程重新向量化，不能复用旧 index。

### 7.4 API、citation 与 trace

| 能力 | 公开合同 | 对 benchmark 的含义 | 合同结论 |
| --- | --- | --- | --- |
| Ingest | 官方用户文档完整描述 UI/工作流导入；专业版提供平台级完整 SDK，实例可暴露 System API | 社区版应先从当前实例 Swagger/OpenAPI 验证 API-key 权限，不把内部 route 当公共 API | `UNSUPPORTED_API` |
| Direct Retrieval | 官方文档有 UI“命中测试”，但本轮未确认社区版稳定、API-key 可访问的独立 retrieval endpoint | admin `hit_test` 只能作诊断证据 | `UNSUPPORTED_API` |
| Native QA | 应用支持 OpenAI-compatible `Base URL/chat/completions`，也支持 System API 的 open → dialogue；[官方文档](https://maxkb.cn/docs/v2/user_manual/chat_to_API/) | 每题先建独立会话，保存 application key 对应的 raw response | `SAME_CONTRACT` |
| Citation/trace | UI 可显示知识来源，OpenAI 标准 schema 未在该文档中承诺结构化 evidence 字段 | 只有 response 明确返回 source/document/chunk 才计 citation | `UNSUPPORTED_API` |
| 完整系统 API | 官方说明专业版在社区版上提供平台级完整 SDK；[System API](https://maxkb.cn/docs/v2/user_manual/X-Pack/system_API/) | Community 与 X-Pack 不能混作同一 contract | `VERSION_DIVERGENCE` |

上表中的 `VERSION_DIVERGENCE` 还包括 edition divergence：Community 与 X-Pack/专业版可能都能 self-hosted，但不能被当成同一 API contract。

### 7.5 扩展性、工作流、运维、适用场景与局限

- 工作流覆盖 AI 对话、知识库检索、问题优化、判断、指定回复、文档总结、多模态和 MCP；知识库本身也可以工作流化，适合企业内部知识助手、客服与办公场景。[高级智能体](https://maxkb.cn/docs/v2/user_manual/app/workflow_app/)、[工作流知识库](https://maxkb.cn/docs/v2/user_manual/dataset/workflow/)。
- 单镜像初始部署简单；官方生产要求 4C8GB、100GB disk，并推荐离线安装包。[部署要求](https://maxkb.cn/docs/v2/installation/offline_installtion/)。
- 社区版与 X-Pack 的共享资源、认证、完整 SDK、部分数据源能力不同，采购/部署决策前必须按版本逐项核对。
- 主要局限：公开用户文档偏 UI 操作，API contract 依赖实例 Swagger discovery；状态码和内部 route 不应被 benchmark 直接当作跨版本稳定接口。

### 7.6 本项目实测边界

本项目在原生 ARM64 镜像上完成管理员、TaaS LLM/Embedding、知识库与应用初始化。三份文档已上传，但落盘状态码 `nnn2` 未在稳定公共 contract 中确认；应用 OpenAI-compatible endpoint 返回 HTTP 200 schema，但没有正确消费本轮问题；admin hit-test 返回三条真实命中，但不是公开 Direct Retrieval API。因此整体为 `LOCAL_VARIANT`，Direct Retrieval 与结构化 citation 继续为 `UNSUPPORTED_API`。这些现象只适用于 v2.10.4-lts 本地实例和本轮调用方式。

## 8. 统一能力对比矩阵

### 8.1 产品与架构

| 维度 | Dify | FastGPT | RAGFlow | MaxKB |
| --- | --- | --- | --- | --- |
| 产品中心 | 通用 LLM App/LLMOps | 知识库问答与 AI Workflow | 文档 ETL/Context Engine/RAG | 企业知识库与智能体 |
| RAG 深度 | 完整、易编排 | Dataset/Search Test 清晰 | 复杂解析、混合检索、引用最突出 | UI/工作流友好 |
| 主要持久化 | PostgreSQL + Redis + 可选向量库 | MongoDB/GridFS + 向量 DB | MySQL + MinIO + Redis + Elasticsearch/Infinity | 单镜像内持久化栈 |
| 模型扩展 | Model Plugin，类型完整 | AIProxy + Language/Index Model | 多 provider，LLM/Embedding/Rerank | 多 provider 与多模型类型 |
| 工作流 | Workflow/Chatflow/Agent | 可视化 AI Workflow | Agent + ingestion pipeline | 智能体 + 工作流知识库 |
| API 可测性 | Knowledge 与 App API 成熟 | Dataset/SearchTest/Chat 明确，但版本 API 正迁移 | HTTP API 覆盖最完整 | Native Chat 清晰，独立 retrieval 较弱 |
| 初始运维复杂度 | 中高 | 中高 | 高 | 中低 |
| ARM64 适配 | 本项目已原生运行 | 本项目已原生运行 | 官方镜像不支持 ARM64 | 本项目已原生运行 |

### 8.2 Benchmark 接口合同

| 能力 | Dify | FastGPT | RAGFlow | MaxKB |
| --- | --- | --- | --- | --- |
| 建库 | `SAME_CONTRACT` | `SAME_CONTRACT` | `BLOCKED_LOCAL` | `UNSUPPORTED_API` |
| API 文件导入 | `SAME_CONTRACT` | `VERSION_DIVERGENCE` | `BLOCKED_LOCAL` | `UNSUPPORTED_API` |
| 索引状态 | `SAME_CONTRACT` | `VERSION_DIVERGENCE` | `BLOCKED_LOCAL` | `VERSION_DIVERGENCE` |
| Direct Retrieval | `SAME_CONTRACT` | `SAME_CONTRACT` | `BLOCKED_LOCAL` | `UNSUPPORTED_API` |
| Native QA | `SAME_CONTRACT` | `BLOCKED_LOCAL` | `BLOCKED_LOCAL` | `VERSION_DIVERGENCE` |
| 结构化 citation | `SAME_CONTRACT` | `VERSION_DIVERGENCE` | `BLOCKED_LOCAL` | `UNSUPPORTED_API` |
| 工作流 trace | `LOCAL_VARIANT` | `VERSION_DIVERGENCE` | `BLOCKED_LOCAL` | `VERSION_DIVERGENCE` |
| 本地模型/provider | `LOCAL_VARIANT` | `LOCAL_VARIANT` | `BLOCKED_LOCAL` | `LOCAL_VARIANT` |
| 当前本机整体 | `LOCAL_VARIANT` | `BLOCKED_LOCAL` | `BLOCKED_LOCAL` | `LOCAL_VARIANT` |

矩阵中的 RAGFlow `BLOCKED_LOCAL` 是“本地未执行”的结论，不否认其官方 API contract。FastGPT Native QA 的 `BLOCKED_LOCAL` 是本项目当前 workflow timeout。MaxKB 建库/导入的 `UNSUPPORTED_API` 指社区版稳定公开 API 证据不足，不表示 UI 不能完成这些操作。

### 8.3 适用场景

| 场景 | 优先考察 | 原因 | 需要重点验证 |
| --- | --- | --- | --- |
| 快速构建带工具/Agent 的业务应用 | Dify | 应用形态、插件与 Service API 完整 | provider、插件版本、工作流 trace |
| 企业知识库问答与可视化编排 | FastGPT | Dataset/SearchTest 与应用工作流结合紧 | 实例 OpenAPI、Native workflow 稳定性 |
| 扫描件、表格、复杂版式与高要求引用 | RAGFlow | Deep document understanding、hybrid search、rerank | 资源成本、解析准确性、ARM64/x86 |
| 私有化企业助手、低门槛交付 | MaxKB | 单镜像、知识库与智能体 UI 完整 | Community/X-Pack 边界、公共 retrieval API |

## 9. 对本 benchmark 的接入建议

### 9.1 统一 adapter 不应抹平产品差异

建议统一暴露以下逻辑操作，而不是强迫所有平台使用相同 URL：

```text
create_knowledge_base
upload_document
wait_index_ready
retrieve
create_isolated_session
native_qa
extract_citations
collect_trace
```

每个操作都返回统一 envelope，同时保存 vendor raw request/response。统一字段至少包括：`system_id`、固定版本、source commit、image digest、platform、model egress、dataset/document/session IDs 的 hash、请求时间、耗时、错误分类、artifact SHA-256。

### 9.2 分离三条评测通道

1. **Ingest/readiness**：只判断文档是否解析、切分、Embedding 并进入可检索状态；parser failure 与 retrieval miss 分开。
2. **Direct Retrieval**：仅接收真实 chunk/context、score、source metadata；没有公开 endpoint 就记 `UNSUPPORTED_API`，不从 Native QA 文本反推。
3. **Native QA**：调用厂商应用/工作流入口，保留其 prompt、检索、rerank、引用和生成逻辑；每题和 repeat 使用独立会话。

这样既能横向比较 retrieval，又不会把平台的 Native Workflow 优势错误地压缩成同一个简化 RAG chain。

### 9.3 固定 condition

- Corpus：相同 44 文档与相同文件 hash；若平台对格式支持不同，另建“共同格式子集” condition。
- LLM：优先统一 `deepseek-v4-flash`；若某平台只能稳定使用其他模型，单列 condition，不合并排名。
- Embedding：统一 `bge-m3`、维度、batch 和 normalization；变更模型必须重建索引。
- Retrieval：记录 search mode、top-k/token limit、score threshold、rerank、query rewrite、parent-child 等参数；不能只记录“默认”。
- Chunking：至少保留 vendor-native 与 controlled 两类 condition。RAGFlow/MaxKB 的复杂解析优势应在 vendor-native 中体现，controlled condition 用于隔离 retrieval 差异。
- Session：Dify `conversation_id/user`、FastGPT `chatId`、RAGFlow chat ID、MaxKB dialogue ID 均按 question × repeat 隔离。

### 9.4 平台具体下一步

**Dify**

- 复用已完成的本地 dataset/app，不再重复 44 文档 readiness。
- 给正式 Stage 1 增加 `retriever_resources`、workflow/app log ID 与 provider version 归档。
- 如果加入 Workflow condition，先单独创建、发布并验证 `/workflows/run`，该项由 `LOCAL_VARIANT` 达到 `SAME_CONTRACT` 后再入正式结果。

**FastGPT**

- 复用已有 dataset/app，定位 Native QA timeout：检查应用工作流入口、模型节点、AIProxy 日志、stream/non-stream 与 response timeout。
- 从当前实例保存 `/apidoc/devapi` 和 `/apidoc/systemopenapi` snapshot，解决 v4.15.6 source 与 v4.15.4 runtime 的 `VERSION_DIVERGENCE`。
- Native QA 解除 `BLOCKED_LOCAL` 后再跑 44 文档 readiness；保留 `detail=true` 原始 `responseData`。

**RAGFlow**

- 先把 Colima 提升到至少 4 CPU、16 GiB 与 50 GiB 可用磁盘；若主机物理内存无法安全满足，不强行启动。
- 选择明确的 ARM64 自构建或 amd64 emulation condition，并记录为不同 platform；不要把 emulation 写成原生 ARM64。
- 启动后按 Dataset → Upload → Parse → Status → Retrieval → OpenAI Chat 顺序做三文档 smoke，解析/OCR/index 单独归因。

**MaxKB**

- 固定 v2.10.4-lts 实例 Swagger/OpenAPI，确认 System API 与 Community/X-Pack 权限。
- 重新验证 OpenAI-compatible 消息角色和 System API `open → dialogue`，确保问题被正确消费。
- 在公共 Direct Retrieval endpoint 得到证据前保持 `UNSUPPORTED_API`；admin `hit_test` 只用于诊断，不进入正式 Direct Retrieval ledger。
- 对文档状态 `nnn2` 只保存原始值，不擅自映射为索引完成；以公开状态 contract 或可复现检索结果补证。

## 10. 结论

Dify、FastGPT、RAGFlow、MaxKB 不是四个同质的“向量检索封装”。Dify 的竞争力是完整应用平台与扩展生态，FastGPT 是 Dataset API 与可视化问答工作流，RAGFlow 是复杂文档 ETL 和高精度检索，MaxKB 是企业知识库/智能体的低门槛私有化交付。

对本 benchmark，最重要的不是尽快把四者放进同一排行榜，而是保留三类差异：解析/切分能力、Direct Retrieval contract、Native Application/Workflow 行为。当前只有 Dify 具备进入统一 Stage 1 的完整本地证据；FastGPT 需要解除 Native QA 的 `BLOCKED_LOCAL`，MaxKB 需要收口公开 API 与消息合同，RAGFlow 需要先解除资源层面的 `BLOCKED_LOCAL`。在这些条件满足前，保持版本化、可审计的差异状态比补齐一个不可复现的总分更可靠。

## 11. 官方一手资料索引

### Dify

- [官方仓库](https://github.com/langgenius/dify)
- [Dify Open Source License](https://github.com/langgenius/dify/blob/main/LICENSE)
- [官方 Docker/self-hosted 目录](https://github.com/langgenius/dify/tree/main/docker)
- [API Reference](https://docs.dify.ai/api-reference)
- [固定 1.16.1 Service OpenAPI](https://github.com/langgenius/dify/blob/1.16.1/api/openapi/markdown/service-openapi.md)
- [Model API Interface](https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/model-schema)
- [Datasource Plugin](https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/datasource-plugin)

### FastGPT

- [官方仓库](https://github.com/labring/FastGPT)
- [FastGPT Open Source License](https://github.com/labring/FastGPT/blob/main/LICENSE)
- [Docker Compose 部署](https://doc.fastgpt.io/en/self-host/deploy/docker)
- [Dataset Design](https://doc.fastgpt.io/en/self-host/design/dataset)
- [OpenAPI Introduction](https://doc.fastgpt.io/en/openapi/intro)
- [Dataset API](https://doc.fastgpt.io/en/openapi/dataset)
- [Chat API](https://doc.fastgpt.io/en/openapi/chat)
- [Community/Commercial/Cloud 对比](https://doc.fastgpt.io/en/guide/version/commercial)

### RAGFlow

- [官方仓库](https://github.com/infiniflow/ragflow)
- [Apache 2.0 License](https://github.com/infiniflow/ragflow/blob/main/LICENSE)
- [固定 v0.26.4 README](https://github.com/infiniflow/ragflow/blob/v0.26.4/README.md)
- [固定 v0.26.4 HTTP API Reference](https://github.com/infiniflow/ragflow/blob/v0.26.4/docs/references/http_api_reference.md)
- [官方 Cloud](https://cloud.ragflow.io/)
- [官网与套餐](https://ragflow.io/)

### MaxKB

- [官方仓库](https://github.com/1Panel-dev/MaxKB)
- [GPLv3 License](https://github.com/1Panel-dev/MaxKB/blob/main/LICENSE)
- [产品介绍](https://maxkb.cn/docs/v2/)
- [知识库](https://maxkb.cn/docs/v2/user_manual/dataset/dataset/)
- [文档管理](https://maxkb.cn/docs/v2/user_manual/dataset/doclist/)
- [模型概述](https://maxkb.cn/docs/v2/user_manual/model/model_summary/)
- [通过 API Key 对话](https://maxkb.cn/docs/v2/user_manual/chat_to_API/)
- [System API](https://maxkb.cn/docs/v2/user_manual/X-Pack/system_API/)
- [在线安装](https://maxkb.cn/docs/v2/installation/online_installtion/)
- [生产环境离线安装](https://maxkb.cn/docs/v2/installation/offline_installtion/)
