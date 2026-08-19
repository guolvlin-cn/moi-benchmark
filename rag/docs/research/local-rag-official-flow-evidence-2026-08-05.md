# 本地 RAG 竞品官方流程证据

> 研究日期：2026-08-05
> 研究范围：Dify、FastGPT、RAGFlow、MaxKB 的官方 self-hosted/cloud 流程、公开 API、认证方式、引用/检索能力、官方镜像与 ARM64 支持。
> 来源约束：只使用厂商官方文档、官方代码仓库、官方发布页，以及官方镜像仓库的 manifest 元数据。页面访问/检索日期均为 2026-08-05。本文只做证据整理，不代表本机部署已经成功，也不把云端结果替代为本地结果。

## 结论摘要

| 平台 | 官方本地入口 | 公开 ingest / QA / retrieval contract | 认证 | 引用/来源能力 | ARM64 证据 | 当前判断 |
|---|---|---|---|---|---|---|
| Dify | Community Edition Docker Compose；/install 初始化 | Knowledge API：建库、文件导入、索引状态、retrieve；App API：/chat-messages；Workflow API：/workflows/run | App key 与 Knowledge/Dataset key 分离，均为 Bearer | Chat response 可在 metadata.retriever_resources 返回检索来源；Workflow 取决于工作流输出 | 官方 dify-api:latest、dify-web:latest 的 registry metadata 含 linux/arm64，但完整 Compose 依赖仍须逐镜像检查 | SAME_CONTRACT + LOCAL_VARIANT |
| FastGPT | 官方 Docker Compose；MongoDB + PostgreSQL/PgVector/Milvus + AIProxy | /api/core/dataset/*；/api/core/dataset/searchTest；OpenAI-compatible /api/v1/chat/completions | Authorization: Bearer API key；账号/团队或应用范围 | searchTest 返回来源与分数；Chat detail=true 的 responseData.quoteList 可提供引用，但结构受版本影响 | 官方 Compose 使用 GHCR；官方文档有 ARM/Mongo 运行注意事项，但没有确认完整 Compose 的 ARM64 manifest | API 可按版本复用，部署属于 LOCAL_VARIANT；ARM64 待验证 |
| RAGFlow | 官方 self-host Docker Compose；默认 Elasticsearch；外部 LLM/Embedding | /api/v1/datasets、documents、chunks、run status、/api/v1/retrieval；OpenAI-compatible /api/v1/openai/{chat_id}/chat/completions | Bearer API key | extra_body.reference=true 返回 reference；retrieval API 返回 chunks | 官方仓库明确预构建镜像为 x86、当前无 ARM64 镜像；官方 latest registry metadata 仅见 linux/amd64 | 当前机器是 Apple Silicon/Colima arm64，原生本地化为 BLOCKED_LOCAL 风险；只能尝试本机 amd64 emulation/build |
| MaxKB | 官方 Docker 镜像/在线安装；PostgreSQL + pgvector；Web/API 默认 8080 | 官方公开材料明确标准 App OpenAI-compatible chat；open → dialogue 会话流程；direct retrieval 公共 API 未形成稳定文档 | 应用 API key，Bearer；实例内 Open API/Swagger 需从应用页面发现 | 工作流/界面可显示知识来源；标准 OpenAI API 文档未承诺固定 evidence/citation JSON 字段 | 官方 1panel/maxkb:latest registry metadata 同时含 linux/amd64、linux/arm64；仍需运行时 smoke | 本地流程为 LOCAL_VARIANT；direct retrieval 暂记 UNSUPPORTED_API，直到实例 OpenAPI 证明可用 |

核心结论：

- 四个平台都把“创建知识库/数据集 → 导入文档 → 解析/切分 → Embedding/索引 → 应用问答”作为主流程，但公开的 direct retrieval contract 并不等价。
- Dify、FastGPT、RAGFlow 的官方资料提供了可用于 benchmark 的结构化 retrieval/search API；MaxKB 的公开资料主要覆盖应用问答和 UI/工作流中的知识来源，暂未找到稳定、可由 API key 调用的公共 direct retrieval 与 citation schema。
- RAGFlow 的本地化风险不是普通配置差异：官方文档直接说明预构建镜像面向 x86、没有 ARM64 镜像。当前机器不允许借助远程 x86 主机，因此若本机 emulation/build 无法完成 smoke，应记录 BLOCKED_LOCAL。
- “云端与本地同 contract”只表示 API 路径、认证和字段语义在相同版本下可映射；租户初始化、数据卷、模型 provider、版本、资源与网络出口仍属于 LOCAL_VARIANT。

## 1. 判定口径与本机约束

### 1.1 contract 判定

本文使用以下状态，且只把这些状态作为流程对比结论：

- SAME_CONTRACT：官方资料对云端/本地给出相同或可直接映射的 API 路径、认证方式和请求/响应语义。域名、API key 和资源 ID 可以不同。
- LOCAL_VARIANT：功能流程相同，但服务初始化、模型配置、存储、版本、端口或管理方式由本地部署负责。
- CLOUD_ONLY：本次官方资料显示只在云端入口或托管控制面提供，未发现本地等价 contract。
- LOCAL_ONLY：本次官方资料只发现 self-host/API 入口，未发现可核对的官方托管 contract。此状态不等同于断言厂商永远没有云产品。
- VERSION_DIVERGENCE：云端或文档页面的版本与本地固定版本可能不同，不能直接假定字段完全一致。
- BLOCKED_LOCAL：当前主机架构、资源或官方镜像/构建条件使本地 smoke 无法完成。
- UNSUPPORTED_API：官方公开材料没有证明存在稳定、可由当前认证方式调用的目标 API；不得用内部源码 route 或 UI 行为替代。

SAME_CONTRACT 不覆盖“模型是否相同”“默认 prompt 是否相同”“索引参数是否相同”。这些条件必须在 benchmark manifest 中单独记录。

### 1.2 引用判定

只有在原始 response 中出现结构化的 reference、retriever_resources、quoteList、source、document、chunk 或 context 字段时，才记录为可用引用/来源。答案中提到“来自某文档”不算引用。

“UI 能显示知识来源”与“公开 Chat API 返回 citation 字段”是两个不同能力。MaxKB 尤其需要按此规则区分。

### 1.3 当前机器

- 主机：macOS / Apple Silicon。
- Docker 运行时：Colima，目标平台为 Linux/arm64。
- 内存：16 GiB。
- 允许模型和 Embedding 访问现有 MatrixOrigin TaaS OpenAI-compatible endpoint；因此本项目不是 fully offline。服务本体仍必须运行在当前机器。
- 本报告没有执行部署或修改配置；本机 Docker Compose 插件、端口和数据卷是后续部署阶段的 preflight 项。

## 2. Dify

### 2.1 官方 self-hosted/cloud 流程

官方 Dify 仓库将产品区分为 Cloud 与开源的 Self-hosted Community Edition。Self-hosted 官方 Docker Compose 流程是：获取 release 代码 → 进入 docker 目录 → 复制 .env.example → docker compose up -d → 检查 Compose 服务 → 访问 /install 完成初始化 → 访问 Web 控制台。

官方 Docker 快速开始文档给出的本地入口是 http://localhost/install 和随后使用的 http://localhost。文档还列出 macOS 需要 Docker Desktop、Compose 2.24.0+，以及至少 2 vCPU/8 GiB 的 Docker VM；Linux 也要求 Compose 2.24.0+。这说明本地部署的控制面和 API 都由 Compose 负责，不需要把请求转发到 Dify Cloud。

云端和本地的主要差异在于：

- Cloud 使用官方托管域名、Cloud 账号、Cloud app/dataset ID 与 key。
- Self-hosted 使用本地 /install 创建的管理员、自己实例的 API base URL、自己创建的 app/dataset/key。
- Dify 文档公开的 API 路径可以保持相同，但 release tag、插件/provider、默认配置、数据卷和服务资源由本地承担。

### 2.2 公开 API 与认证

| 流程 | 官方 API | 认证/关键字段 | 可用于本项目的证据 |
|---|---|---|---|
| 创建知识库 | POST /datasets | Knowledge API key，Bearer；name、permission、indexing_technique 等 | 返回 dataset/knowledge base 标识；无 embedding model 时可能失败 |
| 文件导入 | POST /datasets/{dataset_id}/document/create-by-file | Knowledge API key；multipart 文件与导入参数 | 异步建立 batch；不应把上传成功当成索引完成 |
| 索引状态 | GET /datasets/{dataset_id}/documents/{batch}/indexing-status | Knowledge API key | 状态从等待、解析、清理、切分、索引到完成或错误；可单独归档 |
| Direct Retrieval | POST /datasets/{dataset_id}/retrieve | Knowledge API key；query、top_k、score threshold 等 | 官方称其用于知识库检索/测试，返回 chunks/segments |
| Native Chat | POST /chat-messages | App API key；query、inputs、response_mode、user、可选 conversation_id | blocking 或 SSE；response 可有 answer、usage、retriever resources |
| Native Workflow | POST /workflows/run | App API key；发布后的 workflow；inputs、response_mode、user | 独立 workflow run；输出由工作流 graph/最后输出节点决定 |

Dify 明确区分 app API key 与 Knowledge API key：前者按 app 访问，后者按创建者可见范围访问知识库。因而本地 runner 必须分别保存 DIFY_API_KEY 与 DIFY_DATASET_API_KEY，不能用一个 Cloud key 代替本地 key。

Self-hosted API base URL 由本地实例决定；官方文档以 Cloud 的 https://api.dify.ai/v1 作为示例，不能把它硬编码为本地地址。实际本地流程应使用类似 http://127.0.0.1:8000/v1 的实例 URL，并从本地控制台获取 app/dataset key。

### 2.3 引用与 trace

官方 send-chat-message response 示例在 metadata 中包含 usage 与 retriever_resources。其中资源记录可包含 dataset、document、segment、content、score 等检索信息。因此：

- Dify Native Chat：引用能力为“response 中有结构化 retriever resources 时可用”。
- Dify Direct Retrieval：/datasets/{dataset_id}/retrieve 直接返回检索 chunks，适合作为独立 retrieval probe。
- Dify Workflow：/workflows/run 的结果取决于工作流是否把检索节点结果映射到输出；不能只因工作流回答了问题，就推断它返回了 citation。

本项目应保存原始 response，并分别记录“回答成功”和“结构化来源是否存在”。

### 2.4 镜像与 ARM64

官方 Dify Compose/镜像来源：

- 官方仓库的 Docker 配置引用 langgenius/dify-* 镜像。
- 2026-08-05 查询官方 Docker Hub registry metadata 时，langgenius/dify-api:latest 与 langgenius/dify-web:latest 均出现 linux/amd64 与 linux/arm64 manifest。
- latest 是可变 tag；该结果不能证明所有 worker、sandbox、插件和依赖镜像都支持 ARM64。部署时必须对实际 release tag 的每个镜像记录 digest 与 platform。

因此 Dify 的本地判断是：

- 服务流程：LOCAL_VARIANT。
- Knowledge/App API contract：在版本相同且 app/dataset 自己创建的前提下，可判 SAME_CONTRACT。
- 当前 ARM64：主 API/Web 镜像有正向证据，但完整 Compose 仍需 smoke；暂不宣称“完整栈原生 ARM64 已确认”。

## 3. FastGPT

### 3.1 官方 self-hosted/cloud 流程

FastGPT 官方 self-host 文档描述的 Docker 架构包含：

1. MongoDB，存储非向量数据；
2. PostgreSQL + PgVector，或 Milvus/OceanBase/SeekDB 等向量/检索存储；
3. AIProxy；
4. FastGPT Web/API。

启动 Compose 后进入本地 Web，配置 Language Model 与 Index Model，创建 Knowledge Base，上传文档，等待集合/索引完成，再通过 App Chat API 或 Search Test API 使用。

官方文档给出的端口示例包括 Web/API 3000，S3/MinIO 9000，MCP 3003。本机已有其他服务占用部分端口时，应在独立 Compose project 中映射，不应复用云端 app 或知识库 ID。

FastGPT 的模型配置允许 OpenAI-compatible provider：文档要求请求 URL、Bearer key 和模型 API 遵循 OpenAI 格式，并区分聊天模型与索引/Embedding 模型。使用 MatrixOrigin TaaS 时，模型出网属于外部 provider，不能描述为 FastGPT fully local。

FastGPT 官方同时提供 Cloud 入口与社区 self-host 方案。Cloud 的控制面、账号和资源由 FastGPT 托管；self-host 的数据服务、API 网关、模型 provider 和版本由本机负责。

### 3.2 公开 API 与认证

| 流程 | 官方 API | 认证/关键字段 | 适合的 benchmark 用法 |
|---|---|---|---|
| 创建知识库 | POST /api/core/dataset/create | Authorization: Bearer API key；parentId、type、name、intro；模型字段可选 | 创建独立 dataset，保存返回 ID |
| 上传本地文件 | POST /api/core/dataset/collection/create/localFile | Bearer；multipart 文件与序列化导入参数 | 上传 PDF/DOCX/MD/TXT/HTML/CSV 等，等待处理结果 |
| Direct Retrieval / Search Test | POST /api/core/dataset/searchTest | Bearer；datasetId、text、limit、similarity、searchMode 等 | 直接保存 data[] 中的 q/a、sourceName/sourceId、score |
| Native QA | POST /api/v1/chat/completions | Bearer；appId、chatId、messages、stream、detail | OpenAI-compatible chat；detail=true 保存中间结果 |

FastGPT 官方 API 文档说明，从 4.15.0 起 API 文档自动生成，并区分 Dev API 与 System OpenAPI；不是每一个 Dev API 都能用 API key 调用。每个实例可从 endpoint/apidoc/devapi 和 endpoint/apidoc/systemopenapi 查看与当前版本对应的接口。因此 benchmark 必须把实例版本和实际 API 文档一起归档，不能只依据一个跨版本网页。

官方文档还说明 API key 可从账号/API Keys 或应用发布渠道获得，通常通过 Authorization: Bearer 发送。API key 的账号/团队范围与 app scope 必须在 smoke 中记录。

### 3.3 引用与 trace

FastGPT 的 direct retrieval contract 比标准 Chat response 更明确：

- searchTest 返回搜索结果中的来源名、来源 ID、相关分数以及片段问答字段，适合做独立的 retrieval probe。
- Chat API 的 detail=true 会把中间过程放入 responseData；官方示例中出现 Dataset Search、AI Chat 和 quoteList，quote 中可包含 dataset、collection、source 等信息。
- 官方文档提醒 responseData 可能随版本变化。因此 quoteList 只能以“当前 pinned version 的原始 response 中实际出现”为准，不能把它当成永远稳定的 OpenAI 标准字段。
- chatId 会影响会话上下文；隔离 benchmark question 时使用新的 chatId，或明确使用无会话模式，避免跨题污染。

结论：

- Direct Retrieval：可判 SAME_CONTRACT（本地实例版本与官方文档一致时）。
- Native QA citation：LOCAL_VARIANT 的实现级差异，能力为“detail=true 且当前 workflow 返回 quoteList 时可用”。
- 不应从最终 answer 文本反推出 citation。

### 3.4 镜像与 ARM64

官方 FastGPT Compose 使用 GHCR 镜像，官方版本快照示例包含：

- ghcr.io/labring/fastgpt
- ghcr.io/labring/fastgpt-code-sandbox
- ghcr.io/labring/fastgpt-mcp_server
- ghcr.io/labring/fastgpt-plugin
- ghcr.io/labring/aiproxy
- MongoDB、PostgreSQL/PgVector、Redis、MinIO 等依赖。

官方部署文档给出 PgVector 的资源建议约为测试 2c4g、推荐 2c8g；Milvus 测试约 2c8g、推荐 4c16g。当前机器 16 GiB，使用 Milvus 方案会与其他本地服务竞争资源，初版应优先使用轻量 PgVector 并串行启动。

官方文档有 ARM/CPU 运行注意事项，尤其提到 MongoDB 5 的 AVX/CPU 兼容问题，并提供官方 Mongo 镜像或 Mongo 4.4 作为兼容性方向。这是组件级指导，不等于 FastGPT 完整 Compose 已获得 ARM64 矩阵保证。

截至本次检索，公开官方文档明确了 GHCR 镜像和 ARM/Mongo 注意事项，但没有给出完整 Compose 所有镜像的 ARM64 manifest 结论。GHCR 需要逐镜像、逐 tag 检查 manifest；本次没有把未认证的 registry 响应当作 ARM64 证据。

因此 FastGPT 的本地判断是：

- API 流程：SAME_CONTRACT，前提是使用实例自动生成的 API 文档和固定版本。
- 数据库、模型 provider、端口、密钥和 Compose：LOCAL_VARIANT。
- 完整 ARM64 支持：证据不足，部署阶段需做 manifest preflight；若某个官方镜像无法在本机运行，再记录 BLOCKED_LOCAL，不能改用远程机器。

## 4. RAGFlow

### 4.1 官方 self-hosted/cloud 流程

RAGFlow 官方仓库同时提供 Cloud 入口 https://cloud.ragflow.io 与 self-host 代码/Compose。官方 self-host 流程是：

1. 准备 Docker、Docker Compose、CPU/内存/磁盘和 vm.max_map_count；
2. 使用稳定 release/tag 对应的 Docker Compose 和预构建镜像；
3. 启动 Elasticsearch、MySQL/Redis/MinIO 等依赖与 RAGFlow 服务；
4. 创建 Dataset；
5. 上传文档；
6. 选择 parser/DeepDoc/OCR 等解析方式；
7. 触发 chunks/解析与 Embedding/index；
8. 等待 document run 状态完成；
9. 创建 Chat assistant，使用检索或 OpenAI-compatible Chat API。

官方 Docker README 说明默认文档引擎为 Elasticsearch，镜像不内置 Embedding 模型，需要配置外部 LLM/Embedding 服务。使用现有 TaaS endpoint 可以满足 provider 方向，但不能把 RAGFlow 服务和模型 endpoint 都称为本地。

RAGFlow 官方 README 给出的 self-host 资源门槛包括至少 4 CPU、16 GB RAM、50 GB 磁盘，并要求 Docker 24+、Compose 2.26.1+；还要求提高 Linux vm.max_map_count。在当前 16 GiB 主机上，这已经是下限，amd64 emulation 可能进一步放大资源压力。

### 4.2 公开 API 与认证

| 流程 | 官方 API | 认证/关键字段 | 关键状态或输出 |
|---|---|---|---|
| 创建 Dataset | POST /api/v1/datasets | Bearer API key；parser/chunk/embedding 配置 | 返回 dataset 标识 |
| 上传文档 | POST /api/v1/datasets/{dataset_id}/documents | Bearer；local/web/empty 类型，multipart 或 JSON | 返回 document 标识 |
| 触发解析/切分 | POST /api/v1/datasets/{dataset_id}/chunks | Bearer；document_ids | 触发 parser/chunk/index 流程 |
| 查看文档状态 | GET /api/v1/datasets/{dataset_id}/documents | Bearer；可按 run 过滤 | UNSTART/RUNNING/CANCEL/DONE/FAIL 等状态 |
| Direct Retrieval | POST /api/v1/retrieval | Bearer；question、dataset/document IDs、top_k、similarity、keyword、rerank 等 | 返回检索 chunks/context |
| Native QA | POST /api/v1/openai/{chat_id}/chat/completions | Bearer；OpenAI-compatible messages；extra_body.reference=true | 可在响应中要求 reference/reference metadata |

官方 API 参考中还标注了旧的 OpenAI route 已弃用，初版应使用当前 /api/v1/openai/{chat_id}/chat/completions，而不是把旧 route 当成稳定 contract。

### 4.3 解析状态、检索与引用

RAGFlow 的官方 API 将 parser/index 状态和 retrieval 结果分开，适合 benchmark 做独立归因：

- run 状态为失败时，应记作 parser/embedding/index 失败，而不是 retrieval miss。
- /api/v1/retrieval 返回真实 chunks，直接作为 direct retrieval 证据。
- Chat API 通过 extra_body.reference=true 以及可选的 reference metadata 请求引用。只有原始响应实际返回 reference 时，才把该题标为 citation available。
- reference_metadata.include/fields 可用于控制返回的引用元数据；字段以当前版本的 API response 为准。

因此 RAGFlow 在 API contract 上具有清晰的本地/云端映射，但 parser、OCR、Embedding provider、文档引擎和默认模型配置会造成 LOCAL_VARIANT 或 VERSION_DIVERGENCE。

### 4.4 镜像与 ARM64

这是本项目最明确的本地化阻塞点：

- RAGFlow 官方仓库的 Docker 说明明确写明预构建 Docker image 面向 x86，当前没有 ARM64 images；ARM64 需要按 build guide 自行构建。
- 官方说明还提示 Linux/arm64 下的 Infinity 文档引擎并非官方支持路径，默认 Elasticsearch 更稳妥。
- 2026-08-05 查询官方 Docker Hub infiniflow/ragflow:latest registry metadata 时，仅看到 linux/amd64 manifest。
- 官方仓库不建议把未维护的 macOS Compose 文件当作常规路径；当前主机应优先尝试官方 Linux Compose + 本机 amd64 emulation/build。

执行判定：

- 先检查实际 release tag 的所有镜像和 platform。
- 若 Colima 的 amd64 emulation 能启动并完成 3 文档 smoke，结果标记为 emulated_amd64，不能称为原生 ARM64。
- 若镜像启动、解析、Embedding、Elasticsearch 或资源要求无法在本机完成，标记 BLOCKED_LOCAL；不得用远程 x86 结果替代。

当前研究结论为：RAGFlow 的官方预构建镜像对本机原生 arm64 是 BLOCKED_LOCAL 风险，而不是已经证明的本地成功。

## 5. MaxKB

### 5.1 官方 self-hosted/cloud 流程

MaxKB 官方仓库和 v2 文档提供 Docker/在线安装流程。官方快速启动示例将容器 8080 映射到 Web，数据卷挂载到 /opt/maxkb；本项目已有 MOI parser 使用 8080，因此本地应映射为 8090。

官方 MaxKB 流程是：

1. 启动官方 MaxKB 镜像并完成管理员初始化；
2. 配置 LLM 与 Embedding/model provider；
3. 创建应用/Agent 与知识库；
4. 上传文档；
5. 等待后台分段、存储、向量化完成；
6. 将知识库关联到 Agent；
7. 发布应用；
8. 通过应用 OpenAI-compatible API 或 UI 对话。

官方文档的 self-host server 说明以 Linux、Ubuntu 22.04/CentOS 7、4C/8G 和 100 GB 磁盘为参考，默认端口为 8080。当前 Colima 是本机 Linux/arm64 容器环境，属于本地运行变体，不能把官方 Linux server 说明理解为对 macOS/Colima 的完整认证。

本次审阅到的 MaxKB 官方资料主要是开源/self-hosted/在线安装与本地应用 API；没有找到可以逐字段核对的独立 MaxKB managed-cloud API/tenant contract。因此云端比较只使用“本次官方资料范围内未发现”的表述，不据此断言 MaxKB 不提供任何云服务。

### 5.2 公开 API 与认证

| 流程 | 官方公开材料 | 认证/稳定性 | 当前可用结论 |
|---|---|---|---|
| 应用问答 | App 的 OpenAI-compatible Base URL/chat/completions | Authorization: Bearer API Key；标准 messages | 可作为 Native QA；实际 URL/base path 从当前实例 API 文档获取 |
| 会话初始化 | 官方文档描述 open 创建 session ID | 应用 API key；随后 dialogue 使用 session | 适合每个问题建立隔离 session |
| 会话对话 | 官方文档描述 dialogue 发送问题并使用 session ID | Bearer；session 属于应用 | 保存 session、answer、usage 与原始响应 |
| 知识库/文档导入 | 官方 UI/知识库文档描述创建、上传、分段、存储、向量化 | 公开页面主要是 UI 流程；稳定 API path 需当前实例 OpenAPI/Swagger | 初版可用 UI 或实例 API 文档，但不能凭内部 route 编写公共 adapter |
| Direct Retrieval | 官方文档/导航提到 hit test 或检索测试概念，但本次未找到稳定的 API-key 公共 endpoint 与 response schema | 需实例 API 文档确认 | 暂记 UNSUPPORTED_API |

MaxKB 官方应用页面提供 Open API 文档入口；因此部署阶段应从当前实例的应用页面或 Swagger discovery 获取真实 path、请求体和认证要求。不得把源码内部 route、浏览器网络请求或 UI handler 当作跨版本公共 API。

### 5.3 引用与知识来源

官方 MaxKB 工作流/Agent 文档展示了知识检索节点、知识来源显示和段落列表等能力；这些材料证明 UI/工作流可以展示知识来源，但不等价于标准 OpenAI-compatible Chat API 一定返回固定引用字段。

本项目应按以下规则处理：

- 如果当前实例 Chat response 真实返回 source、document、paragraph、reference 等结构化字段，保存 raw response 并记录 citation available。
- 如果只在 UI 上看到知识来源，而 API response 只有 answer，则记为 API citation unavailable/undocumented。
- Direct Retrieval 在实例 Swagger 显式提供、且 API key 可访问前，保持 UNSUPPORTED_API。

### 5.4 镜像与 ARM64

官方 Docker Hub registry metadata 在 2026-08-05 对 1panel/maxkb:latest 同时返回 linux/amd64 与 linux/arm64 manifest。这是 MaxKB 主镜像支持 ARM64 的正向证据，但不是对所有依赖、存储驱动、模型 provider 和当前版本配置的端到端保证。

latest 是可变 tag，正式部署仍需固定 release/tag 并保存实际 image digest。主镜像能拉取不代表模型 endpoint 或本地数据卷迁移已经通过 smoke。

因此 MaxKB 的本地判断为：

- 主服务镜像：有 ARM64 证据，优先尝试原生 Colima arm64。
- 知识库/应用流程：LOCAL_VARIANT。
- Native QA：标准 App Chat API 可按版本核验，属于 SAME_CONTRACT 的候选，但本次官方材料未提供独立 cloud/local 对照 contract。
- Direct Retrieval：UNSUPPORTED_API，直到当前实例 OpenAPI 证明有公开、可认证、稳定的 retrieval endpoint。

## 6. 云端/官网流程与本地流程对照

以下“官网流程”指官方 Cloud 或官方公开 API/部署文档中的流程。没有找到厂商托管 cloud contract 的地方，明确标注证据边界。

| 流程步骤 | Dify | FastGPT | RAGFlow | MaxKB |
|---|---|---|---|---|
| 服务/租户初始化 | Cloud 账号/app vs 本地 /install；LOCAL_VARIANT | Cloud 账号/团队 vs 本地 Compose/账号；LOCAL_VARIANT | Cloud 入口 vs 本地 Compose/依赖服务；LOCAL_VARIANT | 本次材料主要是 self-host/online install；LOCAL_ONLY（限本次资料范围） |
| 创建知识库 | Cloud 与本地均有 Knowledge API /datasets；SAME_CONTRACT | /api/core/dataset/create 可用于本地与官方 API 文档；SAME_CONTRACT | /api/v1/datasets；SAME_CONTRACT，版本需对齐 | 官方明确 UI 流程，公共 API 需实例 discovery；LOCAL_VARIANT |
| 上传文档 | /document/create-by-file；SAME_CONTRACT | /collection/create/localFile；SAME_CONTRACT | /datasets/{id}/documents；SAME_CONTRACT | UI/实例 OpenAPI；LOCAL_VARIANT |
| 解析/切分 | 文档状态接口明确展示解析、清理、切分、索引；SAME_CONTRACT | 集合导入后等待处理；具体状态字段随版本；VERSION_DIVERGENCE 风险 | parser/chunks/run status 明确；SAME_CONTRACT | 官方 UI 描述 split/store/vectorize；API 字段需 discovery；LOCAL_VARIANT |
| Embedding/index | provider 与索引策略在本地自行配置；LOCAL_VARIANT | Language Model/Index Model 与存储在本地配置；LOCAL_VARIANT | 外部 Embedding + Elasticsearch/配置在本地承担；LOCAL_VARIANT | LLM/Embedding provider 与本地向量库配置；LOCAL_VARIANT |
| Native QA | /chat-messages；Cloud/local 路径语义可映射；SAME_CONTRACT | OpenAI-compatible /api/v1/chat/completions；SAME_CONTRACT，需 pin version | OpenAI-compatible /api/v1/openai/{chat_id}/chat/completions；SAME_CONTRACT | App OpenAI-compatible chat；本次未找到 cloud 对照；LOCAL_VARIANT |
| Direct Retrieval | /datasets/{id}/retrieve；SAME_CONTRACT | /api/core/dataset/searchTest；SAME_CONTRACT | /api/v1/retrieval；SAME_CONTRACT | 稳定 public API 未证实；UNSUPPORTED_API |
| Citation/trace | Chat metadata.retriever_resources；Workflow 取决于输出映射；SAME_CONTRACT/LOCAL_VARIANT | SearchTest source/score；Chat detail=true 的 quoteList 受版本影响；VERSION_DIVERGENCE | reference=true 与 retrieval chunks；SAME_CONTRACT | UI/workflow 有知识来源，但标准 Chat JSON 未承诺固定字段；UNSUPPORTED_API（citation schema） |
| 模型出网 | Cloud 托管 provider vs 本地 TaaS external endpoint；LOCAL_VARIANT | 同上；LOCAL_VARIANT | 官方支持外部 LLM/Embedding；LOCAL_VARIANT | provider 由本地配置，TaaS external；LOCAL_VARIANT |
| 版本/资源 | Cloud 托管版本 vs 本地 release/Compose/digest；VERSION_DIVERGENCE | 同上，且 API 文档按实例生成；VERSION_DIVERGENCE | Cloud 托管 vs 本地 tag、ES、CPU/RAM；VERSION_DIVERGENCE | 官方文档/镜像版本需固定；VERSION_DIVERGENCE |

### 6.1 同一 contract 的边界

可视为同一 contract 的部分：

- Dify 的 dataset/document/retrieve 与 app chat 路径；
- FastGPT 的 dataset、localFile、searchTest 与 OpenAI-compatible chat 路径；
- RAGFlow 的 dataset/document/chunks/retrieval 与 OpenAI-compatible chat 路径。

仅是 local variant 的部分：

- 管理员初始化、租户/团队、API key 创建；
- Docker Compose、数据卷、依赖数据库、端口；
- LLM/Embedding provider 与网络出口；
- 默认 parser、chunk、rerank、top-k、索引策略；
- 版本、镜像 digest 和资源限制。

当前无法当作同一 contract 的部分：

- MaxKB 的 direct retrieval：公开资料未提供稳定 API-key contract。
- MaxKB 的 citation JSON：UI/workflow knowledge source 不等于标准 Chat API 字段。
- RAGFlow 在当前 ARM64 主机上的“本地服务可用性”：API contract 清楚，但官方预构建镜像/架构条件阻塞本地运行。

## 7. API、认证、引用能力汇总

| 平台 | API key/认证 | Ingest | Native QA | Direct Retrieval | 结构化 citation |
|---|---|---|---|---|---|
| Dify | Knowledge key 与 App key 分离，Bearer | datasets + document upload + indexing status | /chat-messages；blocking/SSE | /datasets/{id}/retrieve | Chat metadata.retriever_resources；Workflow 取决于 graph 输出 |
| FastGPT | Bearer；账号/团队或 App API key | /api/core/dataset/* | /api/v1/chat/completions | /api/core/dataset/searchTest | searchTest source/score；Chat detail=true 可有 responseData.quoteList |
| RAGFlow | Bearer API key | datasets/documents/chunks + run status | /api/v1/openai/{chat_id}/chat/completions | /api/v1/retrieval | extra_body.reference=true；reference metadata |
| MaxKB | App API key，Bearer；从实例 Open API 文档获取细节 | 官方 UI/实例 API 文档 | App OpenAI-compatible chat；open → dialogue | UNSUPPORTED_API，待 Swagger 证明 | UI/workflow 可见；标准 Chat API schema 未证实 |

### 7.1 API 仅云端或可能 unsupported

- 本次未发现 Dify、FastGPT、RAGFlow 的核心 Knowledge/Chat/Retrieval API 明确限定为 Cloud-only；相反，官方 self-host 文档和 API 文档允许本地实例使用对应路径。它们的差异主要是 host、key、资源 ID、版本与 provider，结论是 SAME_CONTRACT + LOCAL_VARIANT。
- Dify Workflow 的具体输出字段不是平台统一的 citation contract；没有把 retrieval node 的内部结果映射到输出时，不能假定 citation 存在。
- FastGPT 官方明确提示并非所有 Dev API 都支持 API key 调用；未在当前实例 OpenAPI 和认证方式中验证的 Dev API 应记为 UNSUPPORTED_API。
- RAGFlow 旧的 OpenAI route 已被官方标为 deprecated；实现时使用当前 route，旧 route 视为 VERSION_DIVERGENCE/不兼容风险。
- MaxKB 的标准 App Chat API 是公开可用方向，但本次官方材料没有给出稳定 public direct retrieval endpoint 或固定 citation response schema，故这两项先标 UNSUPPORTED_API，不使用内部 route 代替。
- “云端提供某 UI 功能”不能推出“本地 API 一定提供该功能”；同理，“本地 UI 显示来源”不能推出“云端/本地 Chat response 有 source 字段”。

## 8. 官方镜像与 ARM64 证据

| 平台/镜像 | 官方来源 | 2026-08-05 观察 | 解读 |
|---|---|---|---|
| Dify API/Web | [Dify Docker Hub API image metadata](https://hub.docker.com/v2/repositories/langgenius/dify-api/tags/latest)、[Dify Web metadata](https://hub.docker.com/v2/repositories/langgenius/dify-web/tags/latest) | latest 的 API/Web manifest 均出现 amd64 与 arm64 | 主镜像有 ARM64 证据；完整 Compose 依赖仍需逐镜像检查 |
| FastGPT | 官方 Compose 使用 [GHCR 镜像](https://doc.fastgpt.cn/deploy/docker/v4.15/global/docker-compose.pg.yml) | 官方公开文档给出镜像 tag 和 ARM/Mongo 注意事项；本次未完成 GHCR 所有镜像 manifest 核验 | 不把完整栈 ARM64 视为已确认；部署阶段逐镜像核验 |
| RAGFlow | [RAGFlow Docker Hub API image metadata](https://hub.docker.com/v2/repositories/infiniflow/ragflow/tags/latest)；[官方仓库 Docker 说明](https://github.com/infiniflow/ragflow/blob/main/docker/README.md) | latest 只观察到 linux/amd64；官方 README 明确预构建镜像 x86、当前无 ARM64 | 当前主机原生 arm64 为 BLOCKED_LOCAL 风险；只允许本机 emulation/build |
| MaxKB | [MaxKB Docker Hub API image metadata](https://hub.docker.com/v2/repositories/1panel/maxkb/tags/latest) | latest 观察到 amd64 与 arm64 | 主镜像有 ARM64 证据；依赖和运行时仍需 smoke |

这些 registry URL 返回的是可变 latest 的 registry metadata，不是版本锁定证明。正式部署必须：

1. 固定厂商 release/tag；
2. 记录 Compose commit 与所有实际镜像 digest；
3. 保存 platform manifest；
4. 在本机实际启动并运行 health/ingest/QA/retrieval smoke。

## 9. 后续本地化 gate 与关键阻塞点

### 9.1 Dify

- 先补齐 Docker Compose v2，并使用官方 release 的 Compose 文件。
- 用本地 /install 初始化，不复用 Dify Cloud app key、dataset ID 或结果。
- 分别验证本地 Knowledge API 与 App/Workflow API 的 base URL，避免 ingest 已本地化但 QA 仍调用 Cloud。
- 检查完整 Compose 依赖镜像，而不是只依据 API/Web 的 ARM64 manifest。

### 9.2 FastGPT

- 优先使用 PgVector，避免在 16 GiB 主机上先启用更重的 Milvus。
- 在当前 Colima 逐镜像核验 GHCR platform；Mongo 的 AVX/ARM 兼容性是首个运行时检查点。
- 使用实例 /apidoc/devapi 与 /apidoc/systemopenapi 对照实际版本，未被 API key 允许的 Dev API 标 UNSUPPORTED_API。
- searchTest 作为 direct retrieval 主路径；Chat citation 仅按 detail=true 原始 response 中实际出现的 quoteList 记录。

### 9.3 RAGFlow

- 这是最可能无法本地化的平台：官方预构建镜像无 ARM64，且官方最低资源约为 16 GB RAM。
- 允许的尝试只有当前机器的 amd64 emulation 或官方 build guide；不得把远程 x86 主机结果写成 local。
- 如果启动、解析、Embedding、Elasticsearch 或资源条件任一无法完成最小 smoke，记录 BLOCKED_LOCAL，并保留 architecture、tag、digest、logs 和失败阶段。
- 即使 emulation 成功，也标记 emulated_amd64，不能宣称原生 ARM64。

### 9.4 MaxKB

- 主镜像具备 ARM64 manifest，优先尝试原生 Colima。
- 将 8090 映射给 MaxKB，避免占用现有 MOI parser 的 8080。
- 从当前实例应用页面发现 Open API/Swagger；只有发现公开、可认证的 hit-test/retrieval endpoint 后，才能把 direct retrieval 从 UNSUPPORTED_API 改为可用。
- 分离记录“UI/工作流知识来源显示”和“Chat API 结构化 citation”；没有字段就不推断。

## 10. 官方来源索引

### Dify

1. [Dify 官方仓库](https://github.com/langgenius/dify) —— Cloud 与 Self-hosted Community Edition 定位、代码和发布信息；访问/检索：2026-08-05。
2. [Dify Docker Compose 快速开始](https://docs.dify.ai/en/self-host/deploy/quick-start/docker-compose) —— 本地 Compose、环境文件、启动、/install 和资源要求；访问/检索：2026-08-05。
3. [Dify Docker README](https://github.com/langgenius/dify/blob/main/docker/README.md) —— 官方 Docker 目录与配置说明；访问/检索：2026-08-05。
4. [Dify API Get Started](https://docs.dify.ai/en/api-reference/guides/get-started) —— Cloud/self-host API base、API key 范围和 REST API 总览；访问/检索：2026-08-05。
5. [Dify Knowledge API guide](https://docs.dify.ai/en/api-reference/guides/knowledge) —— Knowledge API、文档导入、索引状态、retrieve；访问/检索：2026-08-05。
6. [Dify 创建空知识库](https://docs.dify.ai/en/api-reference/knowledge-bases/create-an-empty-knowledge-base) —— POST /datasets；访问/检索：2026-08-05。
7. [Dify 文件导入](https://docs.dify.ai/en/api-reference/documents/create-document-by-file) —— POST /datasets/{dataset_id}/document/create-by-file；访问/检索：2026-08-05。
8. [Dify 索引状态](https://docs.dify.ai/en/api-reference/documents/get-document-indexing-status) —— 批次状态查询；访问/检索：2026-08-05。
9. [Dify Retrieve](https://docs.dify.ai/en/api-reference/knowledge-bases/retrieve-chunks-from-a-knowledge-base-test-retrieval) —— POST /datasets/{dataset_id}/retrieve；访问/检索：2026-08-05。
10. [Dify Chatflow API guide](https://docs.dify.ai/en/api-reference/guides/chatflow) —— Chatflow 与对话 API；访问/检索：2026-08-05。
11. [Dify Send Chat Message](https://docs.dify.ai/en/api-reference/chat-messages/send-chat-message) —— /chat-messages、usage 与 retriever_resources；访问/检索：2026-08-05。
12. [Dify Workflow guide](https://docs.dify.ai/en/api-reference/guides/workflow) 与 [Run Workflow](https://docs.dify.ai/en/api-reference/workflow-runs/run-workflow) —— /workflows/run 与发布要求；访问/检索：2026-08-05。
13. [Dify API image registry metadata](https://hub.docker.com/v2/repositories/langgenius/dify-api/tags/latest) 与 [Web image registry metadata](https://hub.docker.com/v2/repositories/langgenius/dify-web/tags/latest) —— platform manifest；访问/检索：2026-08-05。

### FastGPT

1. [FastGPT 官方仓库](https://github.com/labring/FastGPT) —— Cloud、社区 self-host 和代码仓库；访问/检索：2026-08-05。
2. [FastGPT Docker self-host 文档](https://doc.fastgpt.io/en/self-host/deploy/docker) —— Compose 架构、资源、端口、模型配置和 ARM/Mongo 注意事项；访问/检索：2026-08-05。
3. [FastGPT 官方 Compose 版本快照](https://doc.fastgpt.cn/deploy/docker/v4.15/global/docker-compose.pg.yml) —— 官方 GHCR 镜像、依赖和端口；访问/检索：2026-08-05。
4. [FastGPT OpenAPI 总览](https://doc.fastgpt.io/en/openapi/intro) —— API 文档、API key、Bearer、实例文档入口；访问/检索：2026-08-05。
5. [FastGPT Dataset API](https://doc.fastgpt.io/en/openapi/dataset) —— 创建 dataset、文件导入、searchTest 和来源字段；访问/检索：2026-08-05。
6. [FastGPT Chat API](https://doc.fastgpt.io/en/openapi/chat) —— OpenAI-compatible chat、detail、chatId、responseData/quoteList；访问/检索：2026-08-05。
7. [FastGPT 模型配置](https://doc.fastgpt.io/en/self-host/config/model/intro) —— OpenAI-compatible model/index provider 配置；访问/检索：2026-08-05。

### RAGFlow

1. [RAGFlow 官方仓库](https://github.com/infiniflow/ragflow) —— Cloud 入口、self-host、资源、x86/ARM64 说明；访问/检索：2026-08-05。
2. [RAGFlow Docker README](https://github.com/infiniflow/ragflow/blob/main/docker/README.md) —— Compose、Elasticsearch、外部 Embedding 和配置；访问/检索：2026-08-05。
3. [RAGFlow HTTP API reference](https://ragflow.com.cn/docs/http_api_reference) —— Dataset、文档、chunks、run status、retrieval、OpenAI endpoint、reference；访问/检索：2026-08-05。
4. [RAGFlow 官方 Cloud 入口](https://cloud.ragflow.io) —— 官方托管入口；访问/检索：2026-08-05。
5. [RAGFlow image registry metadata](https://hub.docker.com/v2/repositories/infiniflow/ragflow/tags/latest) —— latest platform manifest；访问/检索：2026-08-05。

### MaxKB

1. [MaxKB 官方仓库](https://github.com/1Panel-dev/MaxKB) —— 开源产品、自托管 Docker 入口、技术栈；访问/检索：2026-08-05。
2. [MaxKB v2 在线安装](https://maxkb.cn/docs/v2/installation/online_installtion/) —— Linux 资源、Docker、8080、官方镜像与卷；访问/检索：2026-08-05。
3. [MaxKB v2 快速开始](https://maxkb.cn/docs/v2/quick_start/) —— 模型、知识库、文档处理、Agent/应用流程；访问/检索：2026-08-05。
4. [MaxKB Dataset 文档](https://maxkb.cn/docs/v2/user_manual/dataset/dataset/) —— 知识库类型、分段、存储、向量化和完成状态；访问/检索：2026-08-05。
5. [MaxKB App Chat API](https://maxkb.cn/docs/v2/user_manual/chat_to_API/) —— OpenAI-compatible endpoint、Bearer、open → dialogue；访问/检索：2026-08-05。
6. [MaxKB 应用总览](https://maxkb.cn/docs/v2/user_manual/app/app-view/) —— App API key 与 Open API 文档入口；访问/检索：2026-08-05。
7. [MaxKB Workflow App](https://maxkb.cn/docs/v2/user_manual/app/workflow_app/) —— 知识检索节点和 knowledge source 显示行为；访问/检索：2026-08-05。
8. [MaxKB changelog](https://maxkb.cn/docs/v2/changelog/) —— 版本和知识来源显示相关变更；访问/检索：2026-08-05。
9. [MaxKB image registry metadata](https://hub.docker.com/v2/repositories/1panel/maxkb/tags/latest) —— latest platform manifest；访问/检索：2026-08-05。

## 11. 研究结论

在相同 release/version、相同模型 provider、相同 corpus、相同 parser/index 参数和相同 question condition 下：

- Dify、FastGPT、RAGFlow 的核心 ingest、Native QA、Direct Retrieval 都有官方公开路径，可以继续实现本地 API smoke adapter；本地与云端应分别生成 system identity 和资源 ID。
- MaxKB 可以先实现本地服务、应用创建/配置和 Native QA；Direct Retrieval 与稳定 citation schema 必须在本地实例 OpenAPI discovery 后再决定，当前不能假设可实现。
- RAGFlow 的 API 流程最完整，但当前机器架构与官方预构建镜像方向冲突，先做本机 emulation/build gate；失败即 BLOCKED_LOCAL。
- 任何平台都不能因为“官方云端有功能”就把本地功能标为已验证；最终 smoke 必须保留脱敏 raw request/response、版本、镜像 digest、parser/index 状态和失败阶段。
