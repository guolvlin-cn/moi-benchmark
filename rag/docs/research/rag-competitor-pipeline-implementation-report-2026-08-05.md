# 本地 Dify / MaxKB / RAGFlow / FastGPT RAG Benchmark Pipeline 执行文档

> 调查日期：2026-08-05（Asia/Shanghai）
>
> 文档状态：执行设计，尚未开始写新增 adapter 代码
>
> 目标：在本地运行 benchmark runner，通过本地 Dify、MaxKB、RAGFlow、FastGPT 的 HTTP API 完成数据导入、索引就绪检查、原生问答与直接检索。

## 0. 执行结论

本项目接下来不应把竞品当成网页自动化目标，而应把它们当成本地部署的 RAG 服务。benchmark runner 在本地负责统一数据、问题、重复次数、会话隔离、重试、结果归档和评分；Dify、MaxKB、RAGFlow、FastGPT 负责各自的解析、切分、向量化、召回、重排和生成。

按当前官方 API 能力和仓库已有实现，建议接入顺序为：

1. **本地 Dify**：现有 ingest、Chat/Workflow、检索和结果归档代码已经可复用，只需要把 endpoint 从 Dify Cloud 切换到本地服务，并冻结 self-hosted 版本和模型配置。
2. **FastGPT**：知识库创建、文件上传、检索测试、应用对话都有公开 OpenAPI，适合作为第一套新增竞品 adapter。
3. **RAGFlow**：文档解析状态、块检索、OpenAI 兼容问答和引用参数都比较完整，但本地部署对 x86、Docker 资源和模型服务有更高要求。
4. **MaxKB**：应用问答 API 明确；知识库管理和命中测试依赖具体实例中的 API 文档、权限和版本，适配前必须做 contract discovery，不能把仓库内部路由直接当成长期稳定的公共 API。

Dify Cloud 只保留为已有远端 smoke/reference，不与本地 Dify 共享 `system_id`、知识库 ID、API key 或正式结果。正式本地矩阵使用 `dify_local`，并在 `system.json` 中记录 Dify 镜像 tag、compose commit、向量库和模型出网情况。

本执行文档将“本地的两个 pipeline”定义为以下两条可分别评测的 pipeline：

```text
Pipeline A: Native QA
本地 corpus → 产品知识库 API → 产品解析/切分/索引 → 产品原生问答 API → answer/citation/usage

Pipeline B: Direct Retrieval
本地 corpus → 产品知识库 API → 产品解析/切分/索引 → 产品检索 API → ranked chunks/contexts
```

两条 pipeline 共用同一份本地 corpus 和同一套 ingest manifest，但查询、结果格式和评分目的不同：

- Native QA 评价产品默认 RAG 体验，包括最终答案、原生引用、请求成功率和端到端延迟。
- Direct Retrieval 评价产品实际返回的上下文，包括命中、Recall@K、MRR、分数、来源和上下文顺序，不调用外部 LLM 生成答案。
- Direct Retrieval 的结果不能反推 Native QA 的内部检索结果；Native QA 中没有真实 context/reference 时必须标记 `N/A: TRACE_UNAVAILABLE`。

这一定义与当前 v1.0 plans 的 adapter、attempt ledger、trace audit 和“不要从答案/引用反推 trace”要求一致。

## 1. 与当前 plans 和仓库实现的对齐

### 1.1 当前 benchmark 约束

当前 `plans/drafts/v1.0.md` 是总计划，`plans/drafts/v1.0-todos/` 是执行拆解。本报告遵循以下约束：

- 正式比较对象是 MOI、Dify、FastGPT、RAGFlow、MaxKB 五个系统；S0 历史 MOI 结果不能混入新的同窗比较。
- Stage 1 是五个系统各 `20 questions × 2 repeats = 40 attempts`，共 200 个 native attempts，另有独立的 shared Gold Context oracle；竞品接入不能自行改变分母。
- Quick Native、Frozen Optimized、Direct Retrieval、Shared Gold Context、No-context、Noise、Performance 是不同条件，不能把检索 API 的结果冒充 native answer。
- attempt 必须保留首次失败；retry 作为带 `retry_of` 的独立 lineage，不替换首次结果。
- 若产品没有公开可验证的真实 trace，字段值应为 `N/A`，并保存不可用原因，不能从答案中的文件名或模型输出臆测 chunk/page/rank。
- benchmark 只评估固定版本、固定租户/知识库、固定模型和固定配置下的行为，不在本报告中宣称生产就绪、总冠军或整体产品优劣。

### 1.2 现有 MOI 与 Dify 管线

仓库目前有两类实现，但还没有最终统一到 v1.0 计划中的 adapter/ledger：

| 系统 | 当前实现 | 可复用部分 | 当前缺口 |
|---|---|---|---|
| 本地 MOI RAG | `prototypes/local-matrixflow-rag/` 以及 `prototypes/throwaway-ragbench-moi/ragbench_moi.py` | 产品 parser、切分、MatrixOne full-text/vector 检索、证据扩展；throwaway adapter 已有上传/轮询/检索流程 | 尚未统一 native answer、citation、attempt schema 和五系统 ledger |
| Dify API runner | `dify-rag-eval/` | dataset/doc upload、index 等待、Chat/Workflow API、contexts normalization、retry、metrics、raw response | 默认配置和已记录 smoke 指向 Dify Cloud；仓库没有 Dify 服务 compose，需要补充本地服务部署与 `dify_local` 配置 |

建议不要复制四份新的独立 runner。先把 `dify-rag-eval` 中的通用部分抽到共享层，再让 Dify、MOI、FastGPT、RAGFlow、MaxKB 都实现同一个 adapter contract。Dify 本地化优先复用现有 `DifyClient` 和 `KnowledgeClient`；旧 CLI 可以保留兼容入口，避免破坏已有 Cloud smoke 结果。

### 1.3 计划中的统一 contract

统一生命周期保持为：

```text
prepare_corpus()
  → wait_ready()
  → reset_session()
  → send(question)
  → capture()
  → normalize()
  → archive()
```

其中 Direct Retrieval 使用同一个 ingest 和 ready 阶段，但查询阶段调用 `retrieve(question)`，不调用 `send(question)` 的生成路径。

## 2. 推荐的本地工程结构

建议在 Python runner 中新增共享包，逐步把现有 Dify 专用实现迁移进去：

```text
dify-rag-eval/
  src/dify_rag_eval/
    contract.py                 # Adapter、NativeResponse、RetrievalResponse
    ledger.py                   # attempt ledger、retry lineage、分母 reconciliation
    archive.py                  # raw/normalized/config/hash/artifact 写入
    normalize.py                # 通用 answer/context/citation/trace 规范化
    runner.py                   # native 与 retrieval 两种本地运行器
    adapters/
      dify.py                   # 由现有 DifyClient 演进，支持 Cloud/self-hosted
      moi.py                    # 包装现有 MOI HTTP/local runner
      fastgpt.py
      ragflow.py
      maxkb.py
    probes/
      fastgpt_contract.py
      ragflow_contract.py
      maxkb_contract.py
```

如果后续 Dify 专用命名造成维护成本，再将 package 重命名为 `ragbench`；第一阶段不需要为了重命名而阻塞新增竞品接入。

### 2.1 Adapter 接口

```python
class PlatformAdapter(Protocol):
    def identity(self) -> SystemIdentity: ...
    def capabilities(self) -> CapabilityManifest: ...
    def prepare_corpus(self, manifest: CorpusManifest) -> IngestResult: ...
    def wait_ready(self, ingest: IngestResult) -> ReadinessResult: ...
    def reset_session(self, question_id: str, repeat_id: int) -> Session: ...

    # Pipeline A: 产品原生问答
    def send(self, session: Session, question: str) -> RawPlatformResponse: ...
    def normalize_native(self, raw: RawPlatformResponse) -> NativeResponse: ...

    # Pipeline B: 产品直接检索
    def retrieve(self, question: str) -> RawPlatformResponse: ...
    def normalize_retrieval(self, raw: RawPlatformResponse) -> RetrievalResponse: ...

    def archive(self, attempt: AttemptRecord, raw: object) -> ArtifactManifest: ...
```

Native 与 Retrieval 应显式区分 `condition` 和 `pipeline`，例如：

```json
{
  "pipeline": "native_qa",
  "condition": "quick_native",
  "system_id": "fastgpt",
  "question_id": "q-001",
  "repeat_id": 1,
  "status": "terminal_success",
  "answer": "...",
  "citations": [],
  "context": [],
  "trace_status": "available|partial|N/A: TRACE_UNAVAILABLE",
  "latency_ms": 1820,
  "raw_response_sha256": "..."
}
```

Retrieval attempt 至少保留：

```json
{
  "pipeline": "direct_retrieval",
  "question_id": "q-001",
  "repeat_id": 1,
  "status": "terminal_success",
  "contexts": [
    {
      "rank": 1,
      "platform_chunk_id": "...",
      "platform_document_id": "...",
      "source_name": "...",
      "content": "...",
      "retrieval_score": 0.83,
      "rerank_score": null,
      "page": null,
      "raw_text_hash": "..."
    }
  ],
  "retrieval_config": {
    "top_k": 10,
    "similarity_threshold": null,
    "vector_similarity_weight": null,
    "rerank_id": null
  }
}
```

### 2.2 本地 artifact 目录

每个产品、版本、配置和 run 都必须自包含，推荐：

```text
runs/<run_id>/<system_id>/
  system.json                 # version、image tag、API base、capabilities
  config.json                 # model、embedding、chunk、top_k、rerank 等
  corpus-manifest.json        # local file hash → platform document/collection id
  ingest-state.json           # upload、parse、index readiness
  raw/                        # 原始 HTTP response、SSE、错误、请求元数据
  normalized/                 # attempt JSONL
  screenshots/                # 仅用于诊断，不作为数据主路径
  artifact-manifest.json      # sha256、时间戳、请求/响应关联
```

API key、密码和完整 Authorization header 不得写入 raw artifact；保存脱敏后的请求和 secret fingerprint 即可。

## 3. 四个服务的官方能力调查

### 3.1 能力总表

| 系统 | 本地部署 | 导入/索引 | Native QA API | Direct Retrieval API | trace/citation 预期 | 接入判断 |
|---|---|---|---|---|---|---|
| Dify（self-hosted） | 官方 Docker Compose；本地服务入口通常为 `http://localhost` | `/datasets`、`/document/create-by-file`、`/documents`；轮询 `indexing_status` | `/chat-messages` 或 `/workflows/run` | `/datasets/{id}/retrieve` | Chat blocking response 可从 `metadata.retriever_resources` 取 context；Workflow 只有显式声明的 outputs 可用 | 先完成本地化，作为参考 adapter |
| FastGPT | Docker Compose；官方文档给出 PgVector/Milvus 等部署方式 | `POST /api/core/dataset/create`；`POST /api/core/dataset/collection/create/localFile` | `POST /api/v1/chat/completions`，`appId`、独立 `chatId`、`detail` | `POST /api/core/dataset/searchTest` | `detail=true` 可拿到 `responseData`、node/model/token 等；检索结果有 source/score，但 native 引用字段必须运行时验证 | 最先实现 |
| RAGFlow | 官方 Docker 镜像；当前 README 标注镜像为 x86，ARM64 需构建 | 创建 dataset；上传 `/datasets/{id}/documents`；解析 `/datasets/{id}/chunks`；轮询文档 `run` 状态 | `POST /api/v1/openai/{chat_id}/chat/completions`，可传 `extra_body.reference=true` | `POST /api/v1/retrieval`，支持 dataset/document、top_k、threshold、vector weight、rerank | API 原生支持 reference/reference metadata；文档状态、parser config 和 retrieval chunks 可独立归档 | 第二个实现 |
| MaxKB | 官方仓库提供 Docker 单容器 quick start | 官方文档要求从应用概览进入实例 API 文档；仓库当前源码可见 `/dataset`、`/dataset/{id}/document`、`hit_test` 等内部路由 | 应用 OpenAI 兼容接口：`Base URL/chat/completions`；也可用系统 API 的 open/session/dialogue | 以实例 API 文档中的 dataset `hit_test` 为首选；若权限/版本不支持则标记 unsupported | OpenAI 标准响应不应默认假设有 citations；只有原始 response/system API 明确返回 evidence 才记录 | 最后实现，先做 contract discovery |

### 3.2 本地 Dify

#### 目标与部署边界

Dify 可以作为本地 self-hosted 服务运行，不需要使用 Dify Cloud。官方仓库的 Docker Compose quick start 是：

```bash
git clone https://github.com/langgenius/dify.git
cd dify
git checkout <固定的-release-tag>
cd docker
cp .env.example .env
# 按 benchmark 要求冻结 SECRET_KEY、存储、向量库和模型 provider
docker compose up -d
```

启动后在 `http://localhost/install` 完成初始化；默认反向代理入口通常是 `http://localhost`，Service API 基址通常为 `http://localhost/v1`。如果修改了 Nginx/宿主机端口，所有 runner 配置以实际入口为准。官方仓库当前要求 Docker Compose v2.24.0 或更高版本，并给出约 2 CPU/4 GiB RAM 的最低启动参考；正式 benchmark 仍需额外核算模型和向量库资源。

本地 Dify 的身份必须与 Dify Cloud 分开记录：

```text
system_id       = dify_local
deployment_mode = self_hosted
base_url        = http://127.0.0.1/v1
tenant/app      = local Dify tenant/app
dataset        = local Dify dataset
api keys        = local App API Key + local Dataset API Key
```

Dify 本身不等于本地模型。要做到“不调用 Dify 官网服务”，只需使用本地 Dify API；要做到“不调用任何外部 AI 服务”，还必须把 generation、embedding 和可选 reranker 配成同机/内网的 Ollama、vLLM 或其他 OpenAI-compatible endpoint，并在 `system.json` 中记录 `model_egress=local|internal|external`。更新检查、网页抓取、插件和其他可选外联功能也要单独审计，不能仅凭 API 地址是 localhost 就宣称完全离线。

#### 与当前仓库代码的对应关系

现有 [DifyClient](../../dify-rag-eval/src/dify_rag_eval/dify.py) 已经把 Service API 调用封装好：

- `app_type=chat` 调用 `POST /chat-messages`，使用 `response_mode=blocking`、空 `conversation_id` 和按题目/重复次数组合的 `user`。
- `app_type=workflow` 调用 `POST /workflows/run`；`answer_path` 和 `contexts_path` 从配置读取。
- Chat response 从 `metadata.retriever_resources` 规范化 context；Workflow 只读取应用显式输出的 JSON path。

现有 [KnowledgeClient](../../dify-rag-eval/src/dify_rag_eval/knowledge.py) 已经覆盖本地 Dify 所需的 Dataset API：

- `GET /workspaces/current/models/model-types/text-embedding`：选择 active embedding model；
- `GET/POST /datasets`：查找或创建知识库；
- `POST /datasets/{dataset_id}/document/create-by-file`：上传文档；
- `GET /datasets/{dataset_id}/documents`：轮询 `indexing_status`；
- `POST /datasets/{dataset_id}/retrieve`：直接检索。

因此，Dify 本地化的第一阶段不应重写 API adapter，而应先把服务部署出来并让现有 runner 通过本地 `base_url` 跑通。

#### 本地配置与启动顺序

1. 固定 Dify release tag、compose 文件 hash、镜像 digest 和 vector store。
2. 启动 Docker Compose，访问 `/install` 完成本地管理员初始化。
3. 在本地 Dify 中配置 generation/embedding/rerank provider；如果使用外部 provider，将 endpoint、模型和出网类型写入 manifest。
4. 创建本地 Chatflow 或 Workflow，绑定本地知识库；关闭不需要的对话记忆。
5. 在本地应用中分别创建 App API Key 和 Dataset API Key。
6. 把 runner 的 `base_url` 指向 `http://localhost/v1` 或实际反向代理地址。
7. 先执行一条 question 的 ingest、retrieve probe 和 native query，再扩展到 Stage 1。

runner 的本地配置至少为：

```dotenv
# dify-rag-eval/.env
DIFY_API_BASE_URL=http://localhost/v1
DIFY_DATASET_API_KEY=<local-dataset-api-key>
DIFY_API_KEY=<local-app-api-key>
```

```json
{
  "base_url": "http://localhost/v1",
  "app_type": "chat",
  "api_key_env": "DIFY_API_KEY",
  "user_prefix": "dify-local-benchmark"
}
```

注意：当前 CLI 的 `ingest --base-url` 默认读取 `DIFY_API_BASE_URL`，但 `run` 使用 `config.json` 中的 `base_url`。只修改 `.env` 而不修改 `config.local.json`，可能导致导入已经指向本地、问答仍然请求 Dify Cloud；这项检查应加入 preflight。

#### 两条 pipeline 的实现

**Pipeline A：Native QA**

1. 使用本地 Dataset API 创建/复用知识库并上传 corpus。
2. 轮询所有文档直到 `indexing_status=completed`；`error`、pending 和缺失文档分别归档。
3. 对 Chatflow 调用 `/chat-messages`；对 Workflow 调用 `/workflows/run`。
4. 每个 question/repeat 使用独立 `user`，并保持 `conversation_id=""` 或使用明确的新 session，避免上下文污染。
5. 保存 answer、usage、task/message/conversation/workflow id、retriever resources 或显式 workflow contexts，以及完整 raw response。

**Pipeline B：Direct Retrieval**

1. 使用同一 local dataset 和同一索引快照，不重新上传或重新切分。
2. 调用 `/datasets/{dataset_id}/retrieve`，固定 query、search method、top_k、threshold 和 reranker 配置。
3. 直接把返回的 segment、document、score、content 和 metadata 规范化为 `ContextRecord`。
4. 该路径是 Dify 的 retrieval-only 条件，不把它当作 Chatflow 内部 trace；Chatflow 没有真实 retriever resources 时仍标记 `N/A: TRACE_UNAVAILABLE`。

#### 本地 Dify 的主要风险

- Dify Cloud 的 app key、dataset id 和本地 Dify 的对应物完全不可复用。
- Workflow blocking API 只返回应用声明为输出的值；如果要评估 context，Workflow 必须显式输出检索结果，或者另跑 retrieval-only API。
- Dify self-hosted 的版本、插件、模型 provider 和向量库由本地 compose 决定；每次正式 run 都要写入 system identity。
- 本地服务启动成功不代表 embedding/generation 可用；必须把模型 provider probe 纳入 readiness gate。

### 3.3 FastGPT

#### 官方确认的能力

FastGPT 的官方 OpenAPI 入口说明了本地 Base URL 的形式，例如 `http://localhost:3000/api`，统一使用 `Authorization: Bearer <apikey>`。官方文档说明 API 可以调用应用、上传知识库数据和运行搜索测试，但不是所有系统接口都允许 API Key 访问；这意味着 runner 必须在启动时做 capability probe，而不是只凭版本号判断能力。

官方 Dataset API 提供：

- 创建知识库：`POST /api/core/dataset/create`。
- 上传本地文件并创建 collection：`POST /api/core/dataset/collection/create/localFile`，multipart 中包含 `file` 和序列化的 `data`，返回 `collectionId`。
- 检索测试：`POST /api/core/dataset/searchTest`，支持 `embedding`、`fullTextRecall`、`mixedRecall` 和 rerank 开关；其 `limit` 是最大 token 数，不应直接当成 top-k。

官方 Chat API 提供：

- `POST /api/v1/chat/completions`。
- 请求需要 `appId`、`messages`、`stream`，并可使用 `chatId`；官方示例使用 `detail=true` 获取 `responseData`。
- 直接在 Chat API 上传本地文件不支持；本 benchmark 应先走知识库导入，而不是把文件作为 query 附件。
- 产品应用的 workflow 决定实际模型和温度，runner 不应假设请求体中的通用 `model`/`temperature` 一定生效。

#### 本地部署建议

使用 FastGPT 官方 Docker Compose 方案，并固定 compose 文件、镜像 tag、向量数据库类型和模型配置。第一版建议使用 PgVector 方案以降低依赖，记录实际的 MongoDB、PostgreSQL/向量库、AIProxy 和 FastGPT 镜像版本。官方部署文档给出的 PgVector 测试最低配置是约 2c4g，建议 2c8g；这只作为启动参考，不作为 benchmark 性能结论。

部署后必须先配置 Language Model 和 Index Model，再创建用于 benchmark 的 app。app 的知识库绑定、chunk 设置、rerank、system prompt 和工作流都写入 `config.json`。

#### 两条 pipeline 的实现

**Pipeline A：Native QA**

1. `create_dataset` 创建或复用一个带版本/hash 后缀的 dataset。
2. 按 corpus manifest 上传文件，记录 local sha256 → `collectionId`。
3. 轮询 collection/数据状态；如果当前版本没有可用的稳定状态 API，以 `collectionId` + `searchTest` 的固定探针命中作为 readiness probe，并保存 probe raw response。
4. 对每个 question/repeat 使用新的 `chatId`，调用 `POST /api/v1/chat/completions`，默认 `stream=false`、`detail=true`。
5. 从 `choices` 提取 answer；从 `responseData` 只提取实际存在的 node、retrieval、source、token、running time 字段。字段不存在就保持 `null`，不把文件名字符串解析成 citation。

**Pipeline B：Direct Retrieval**

1. 使用同一 dataset，不重新切分、不重新上传。
2. 调用 `POST /api/core/dataset/searchTest`。
3. 将返回的 `id`、`sourceName`、`sourceId`、`collectionId`、score 和原文映射到统一 `ContextRecord`。
4. 因为接口的 `limit` 是 token 上限，adapter 应同时记录服务器返回数量、实际截取的 K 和请求 token limit。
5. 将此路径标记为 `retrieval_mode=fastgpt_search_test`，不要把它写成 FastGPT Native QA 的内部 trace。

#### 主要风险

- searchTest 是知识库搜索测试接口，可能与 app workflow 的最终检索参数不完全相同，必须在报告中独立命名。
- API 文档以版本为基础自动生成；官方说明从 4.15.0 开始生成 Dev API/System OpenAPI。启动时应保存 `/apidoc/devapi` 或 `/apidoc/systemopenapi` 的 spec hash。
- `detail=true` 的 responseData 结构应以运行时 probe 为准，不能只按文档示例硬编码字段。

### 3.4 RAGFlow

#### 官方确认的能力

RAGFlow 官方仓库的当前 Docker quick start 文档示例使用 `v0.26.4`，并明确说明预构建镜像为 x86；ARM64 没有官方预构建镜像，需要走兼容构建。官方文档还要求调整 `vm.max_map_count` 至至少 `262144`。RAGFlow 镜像依赖外部 LLM/embedding 服务，不能把“容器启动成功”误认为 benchmark 已可用。

HTTP API 文档提供完整的服务路径：

- 上传文档：`POST /api/v1/datasets/{dataset_id}/documents`，支持 local/web/empty 三种模式。
- 触发解析：`POST /api/v1/datasets/{dataset_id}/chunks`，请求体提交 `document_ids`。
- 查询文档状态：`GET /api/v1/datasets/{dataset_id}/documents`，可以按 `run` 状态过滤。
- 直接检索：`POST /api/v1/retrieval`，支持 `dataset_ids`、`document_ids`、`top_k`、`similarity_threshold`、`vector_similarity_weight`、`rerank_id`、keyword 和 metadata condition。
- 创建聊天助手：`POST /api/v1/chats`，绑定 dataset 和 LLM/prompt 配置。
- 原生问答：使用当前路径 `POST /api/v1/openai/{chat_id}/chat/completions`；旧的 `/chats_openai/...` 已弃用。
- 原生引用：在问答请求 `extra_body` 中设置 `reference=true`，并按需设置 `reference_metadata`。

#### 本地部署建议

优先在 x86 Linux Docker 主机上固定一个 release tag。若开发机是 Apple Silicon，不建议直接把 ARM64 本地运行结果与 x86 运行结果混为同一性能条件；可以使用 x86 虚拟机/远程 Docker 主机，或按官方 build-from-source 路径构建，但必须把 `platform`、镜像 digest 和宿主机资源写入 system identity。

正式跑 benchmark 前，至少验证：

1. Web/API 服务已真正 ready。
2. LLM、embedding、必要时 rerank provider 均可调用。
3. dataset 的 embedding model 与 parser/chunk 配置已冻结；解析开始后不再变更。
4. 所有文档的 `run` 状态达到可检索状态，失败、取消、解析错误、embedding 错误分开记录。

#### 两条 pipeline 的实现

**Pipeline A：Native QA**

1. 创建 dataset，设定 chunk method、embedding model 和 parser config。
2. 逐文件调用 `/documents` 上传，记录 document id、文件名、hash、parser config。
3. 调用 `/chunks` 触发解析，轮询 `/documents` 的 `run` 状态和进度信息；保存 `run`、`progress`、`progress_msg`、`parser_config`。
4. 创建 chat assistant，绑定 dataset。
5. 对每个 question/repeat 调用 `/openai/{chat_id}/chat/completions`，优先 `stream=false`；请求包含 `extra_body.reference=true`，若需要来源元数据则增加 `reference_metadata`。
6. 将 answer、usage、references、reference metadata 和完整 raw response 归档。若某版本只在 SSE final chunk 返回 reference，就切换为稳定 SSE parser，并在 `trace_status` 中注明来源是 stream final chunk。

**Pipeline B：Direct Retrieval**

1. 使用已 ready 的 dataset/document ids。
2. 调用 `/api/v1/retrieval`，固定 `top_k`、similarity threshold、vector weight、rerank id、keyword 等参数。
3. 保存服务器返回的 chunk id、document id、content、page/position、score、rerank score 和 metadata。
4. 将 parser/OCR/DeepDoc 处理状态与 retrieval score 分开。解析失败的文档不应作为“低召回”计入，应该先在 readiness 层失败或标记 invalid。

#### 主要风险

- RAGFlow 的 parser/OCR/embedding 是产品特性的一部分，处理时间和资源占用明显高于轻量 API 产品；必须先过 readiness gate 再进入 quality/performance。
- 官方 API 同时存在旧路径和新路径；adapter 只使用当前路径，并在 smoke 阶段对 endpoint/spec 做 contract check。
- `reference=true` 是真实 citation 的可用入口，但必须保留 raw response，不能只保留最终文本，因为引用可能只在 stream final event 或 metadata 中出现。

### 3.5 MaxKB

#### 官方确认的能力

MaxKB 官方仓库提供 Docker quick start，默认暴露 8080；benchmark 环境应使用固定镜像 tag、持久化目录和明确的密码/secret 配置，不应依赖 README 中的默认登录凭据。

MaxKB 官方文档明确支持两类接入：

- **标准 OpenAI API**：将 Base URL 替换为应用实际地址，使用 `Base URL/chat/completions` 和 `Authorization: Bearer API Key`。
- **系统 API**：在应用概览中打开该实例的 API 文档，在其中创建/授权 API Key；文档提供 open 获取会话 id 和对话接口。

与 FastGPT/RAGFlow 的差异在于：MaxKB 的公开文档没有给出一套跨版本、固定的知识库导入 REST contract。当前开源仓库源码能看到 `/dataset`、`/dataset/{dataset_id}/document`、批量 document、document split、refresh、`hit_test` 等路由，但这些是版本绑定的系统内部实现；不能直接将源码路由当成永远稳定的公共 API。

#### 本地部署建议

使用官方 Docker 镜像在 benchmark 专用目录持久化 PostgreSQL/data 与 sandbox package 目录，固定 `MAXKB_IMAGE` tag。启动后记录：MaxKB 版本、镜像 digest、应用 id、知识库 id、模型/embedding 配置、API 文档地址和 API spec hash。

MaxKB adapter 的第一步不是上传文件，而是 `discover_contract()`：

1. 访问应用概览暴露的 API 文档地址。
2. 保存脱敏后的 OpenAPI/Swagger spec hash。
3. 探测 dataset create/list/document create/list/refresh/split/hit_test 是否存在。
4. 探测当前 API key 对每个 endpoint 的权限。
5. 根据真实 spec 生成 request body，不从另一版本的源码或网上示例复制字段。

#### 两条 pipeline 的实现

**Pipeline A：Native QA**

1. 通过实例系统 API 创建或复用 dataset；如果当前版本的 API key 无权创建，提前失败，不转为 UI 自动化。
2. 通过当前 spec 中的 document endpoint 上传文件，并轮询 document/task/vector 状态；若没有状态 endpoint，用固定 hit-test probe 验证目标文档可检索，同时保存该 readiness 的证据。
3. 每个 question/repeat 使用新的 session。优先使用系统 API 的 `open → dialogue` 方式，以便明确控制 session；也可以使用应用 OpenAI endpoint，但必须验证单请求是否会复用上下文。
4. 解析标准 OpenAI response 的 answer、usage 和 id。只有 response 或系统 API 明确返回 source/evidence/answer_list 等结构时才写入 citations；普通回答中的文件名、数字或模型自述都不能作为 citation。

**Pipeline B：Direct Retrieval**

1. 在实例 API 文档中优先使用 dataset `hit_test` 或同等检索接口。
2. 固定 top_n、similarity、search mode、rerank 等字段，并把请求/响应完整归档。
3. 若本版本没有 API-key 可访问的检索 endpoint，`CapabilityManifest.direct_retrieval=false`，Pipeline B 结果为 `UNSUPPORTED`，不能从 Native QA 的 citation 或回答反构 contexts。
4. 如果后续确实需要使用内部源码路由，必须把 adapter 与 MaxKB commit/tag 绑定，并加入版本化 contract test；该路径在最终报告中标记为 `internal_api`，不能与公开 API 能力混称。

#### 主要风险

- 知识库 API、权限模型、serializer 字段和返回结构随 MaxKB 版本变化，需要实例级 spec discovery。
- 标准 OpenAI 响应不等于可审计的 RAG trace；MaxKB native pipeline 可能能完成 answer，但 citation/contexts 仍然是 `N/A`。
- 如果只能通过 UI 完成知识库导入，不能把 UI 结果冒充 API pipeline；该版本应先排除在“API 可复现 native/retrieval”条件之外，或单独标记 `ingest_mode=ui_fallback`。

## 4. 统一实现方案

### 4.1 两种 runner 模式

建议在 CLI 上明确分开：

```bash
# 先做一次导入和 ready，生成 corpus-manifest / ingest-state
python -m dify_rag_eval.cli prepare \
  --system fastgpt --config configs/fastgpt.local.json \
  --corpus data/formal --run-id smoke-fastgpt

# 产品原生问答
python -m dify_rag_eval.cli run-native \
  --system fastgpt --questions data/questions/pilot.jsonl \
  --run-id smoke-fastgpt

# 产品直接检索
python -m dify_rag_eval.cli run-retrieval \
  --system fastgpt --questions data/questions/pilot.jsonl \
  --top-k 10 --run-id smoke-fastgpt
```

命令名可以按现有 CLI 调整；关键是让 pipeline、condition、run_id 在数据层显式存在，而不是依赖不同脚本名来隐式区分。

### 4.2 Corpus 与平台 ID 映射

平台通常会重新生成 dataset/document/collection/chunk id，不能把本地文件名当作唯一键。统一映射表至少包含：

```json
{
  "local_document_id": "doc-local-001",
  "relative_path": "source/a.pdf",
  "sha256": "...",
  "mime_type": "application/pdf",
  "platform": "ragflow",
  "platform_dataset_id": "...",
  "platform_document_id": "...",
  "platform_collection_id": null,
  "ingest_config_hash": "...",
  "parse_status": "DONE",
  "index_status": "READY"
}
```

source 映射优先级为 platform id → platform metadata/name → local manifest hash。若只能通过文件名映射，必须把 `source_mapping_confidence=weak` 写入结果，不能在质量指标中隐藏这一事实。

### 4.3 Readiness gate

每个系统进入 question run 之前必须通过同一组最小 gate：

| 层级 | 检查 |
|---|---|
| 服务 | health/API 认证成功；版本和 image digest 可读取 |
| 模型 | generation、embedding、可选 rerank 均可调用 |
| 导入 | 目标文件数、文件 hash、平台 document/collection id 一致 |
| 解析 | 所有文档不是 pending/failed/cancelled；失败文档有明确错误 |
| 索引 | 固定 query 能检索到至少一条预期文档；probe raw response 已保存 |
| API contract | endpoint、鉴权、响应关键字段通过 smoke；spec hash 已记录 |
| 会话 | Native QA 可以创建新 session/chat id，并验证不会复用历史消息 |

readiness 失败属于产品/环境失败，不应计成回答错误；但它仍保留在 attempt/operability ledger，并在最终报告中单列。

### 4.4 Trace 规范

统一 trace 字段沿用当前计划：

```text
query_rewrite
chunk_id / document_id
page / span
rank
retrieval_score / rerank_score
raw_text / raw_text_hash
context_order
token_count / truncation
qrels
```

四个产品不一定全部提供这些字段。normalize 层只做字段映射，不做推断：

- API 给了 chunk text 和 rank：记录。
- API 给了 source name 但没有 chunk text：记录 source，context text 为 unavailable。
- API 只给了 answer：answer 保留，trace 为 `N/A: TRACE_UNAVAILABLE`。
- API 的 score 是混合召回分数：记录原字段名和 `score_semantics=platform_defined`，不要擅自当作 cosine similarity。

### 4.5 Retry 与会话隔离

每个 question/repeat 都创建新的 session/chat id，尤其是 FastGPT `chatId`、RAGFlow `chat_id` 和 MaxKB system API session。重试必须：

- 有新的 `attempt_id`；
- 保存 `retry_of`；
- 使用新的 request id 和新会话；
- 不覆盖首次失败的 raw response；
- 在分母和结果表中保留首次尝试的失败性质。

这样才能区分 API 不稳定、索引未 ready、产品拒答、模型错误和真正的答案质量错误。

## 5. 配置文件建议

每个系统使用一个本地配置，但公共字段保持一致：

```json
{
  "system_id": "ragflow",
  "deployment_mode": "self_hosted",
  "base_url": "http://127.0.0.1:9380",
  "api_key_env": "RAGFLOW_API_KEY",
  "dataset_id": null,
  "app_id": null,
  "chat_id_prefix": "bench-ragflow",
  "pipeline_defaults": {
    "native": {"stream": false, "reference": true},
    "retrieval": {"top_k": 10}
  },
  "timeout_seconds": 120,
  "retries": 2,
  "version_pin": "v0.26.4",
  "embedding_model": "freeze-at-runtime",
  "generation_model": "freeze-at-runtime",
  "model_egress": "local|internal|external",
  "compose_commit": "freeze-at-runtime",
  "image_digest": "freeze-at-runtime"
}
```

需要特别记录的产品差异：

- Dify：self-hosted API 基址通常为 `http://localhost/v1`；ingest 使用 Dataset API Key，native chat/workflow 使用 App API Key；`DIFY_API_BASE_URL` 不替代 run 配置中的 `base_url`。
- FastGPT：`base_url` 通常包含 `/api`；app chat 使用 `/api/v1/chat/completions`，dataset API 使用 `/api/core/...`。
- RAGFlow：API root 通常是实例地址，路径含 `/api/v1/...`；chat assistant id 与 dataset id 分离。
- MaxKB：应用的 OpenAI Base URL 由应用概览生成，不能简单假设是实例 root；系统 API base 也以实例 API 文档显示为准。

## 6. 分阶段实施计划

### Phase 0：共享层和 smoke fixture

- 从 `dify-rag-eval` 抽出 `AttemptRecord`、`ArtifactManifest`、`PlatformResponse`、`ContextRecord`。
- 把现有 Dify pipeline 适配到共享接口，确保 Dify Cloud 旧 smoke 仍能跑，并新增 `dify_local` identity。
- 包含 2–3 个小文档和 3 个问题的本地 smoke fixture：一个可回答问题、一个多文档问题、一个应拒答问题。
- 写统一 readiness、raw redaction、trace unavailable、retry lineage 测试。

### Phase 1：Dify self-hosted reference pipeline

- 固定 Dify release tag、compose commit、镜像 digest、vector store 和持久化目录。
- 在本地 Dify 完成 `/install`、模型 provider、embedding、Chatflow/Workflow、知识库和两个 API key 配置。
- 使用现有 `dify-rag-eval ingest` 跑本地 Dataset API，验证 `indexing_status=completed` 和 retrieval probe。
- 使用现有 `dify-rag-eval run` 跑本地 `/chat-messages` 或 `/workflows/run`，验证一题 native answer、contexts 和 session isolation。
- 记录 `model_egress`；外部模型可作为单独条件，但不能与 fully-local model 条件合并。
- 通过后再把 `dify_local` 纳入计划中的 20 questions × 2 repeats；Dify Cloud 结果不混入该分母。

### Phase 2：FastGPT adapter

- 固定 FastGPT compose、镜像 tag、PgVector/模型配置。
- 实现 dataset create/reuse、localFile upload、ready probe、searchTest、chat completions。
- 完成 `detail=true` responseData 的运行时 schema snapshot。
- 先跑 native 3 questions × 2 repeats，再跑 retrieval 3 questions。
- 通过后再进入计划中的 20 questions × 2 repeats。

### Phase 3：RAGFlow adapter

- 固定 x86 Docker 环境、release tag、embedding/LLM/rerank provider。
- 实现 dataset、documents upload、chunks parse、run status polling。
- 实现 `/retrieval` 和 `/openai/{chat_id}/chat/completions`。
- 加入 `reference=true` / reference metadata 的 native trace 解析和 SSE fallback。
- 独立记录 parser/OCR/readiness 错误，不并入 retrieval recall。

### Phase 4：MaxKB contract discovery 与 adapter

- 部署固定 MaxKB image，创建 benchmark app/dataset/API key。
- 拉取并 hash 实例 API 文档，探测 dataset/document/hit_test/session endpoints。
- 根据真实 spec 实现 ingest、ready、session、native、retrieval。
- 若 direct retrieval 或 document ingest 权限不可用，清晰标注 unsupported，并决定该版本是否进入正式矩阵。
- 不以 UI 操作为 API pipeline 的替代实现；如需 UI 仅作为诊断/人工确认 artifact。

### Phase 5：统一 Stage 1 smoke 与正式运行

- 五个系统在同一时间窗口完成版本、配置、模型和 corpus manifest 冻结。
- 每个系统先完成 native 40 attempts，再完成独立 retrieval 条件；不交叉复用结果。
- 进行 denominator reconciliation、trace audit、citation audit、invalid/retry lineage audit。
- 之后才运行正式规模；性能测试仍放在 quality/function gate 之后，独立报告。

## 7. 评测口径

### Native QA

复用当前 Dify metrics 的基础能力，并补充平台无关字段；Dify Cloud 与 `dify_local` 作为不同 deployment variant 统计：

- request success / terminal status；
- exact match、token F1、required keywords、refusal match；
- citation presence、citation source correctness、evidence entailment（只有真实 citation/context 可用时计分）；
- latency mean/p50/p95、usage；
- parse/index readiness、session isolation、API error 分类。

### Direct Retrieval

使用 platform API 返回的真实 contexts 计算：

- Recall@K、Precision@K、MRR；
- gold document/chunk hit；
- source mapping completeness；
- score/rerank 分布仅作诊断，不跨平台直接比较分数绝对值；
- context length、truncation、duplicate rate、empty retrieval rate。

### 不允许的做法

- 用平台返回的文件名拼接“引用”字段；
- 用 Native answer 文本猜测平台召回了哪个 chunk；
- 用 FastGPT searchTest 的结果声称它就是 app chat 的内部 trace；
- 将 MaxKB OpenAI 标准 response 自动标记为有 citation；
- 将 RAGFlow parser 失败的文档记成 retrieval miss；
- 用一次重试成功覆盖首次失败；
- 以不同产品的默认模型、embedding、chunk size 差异直接下结论而不记录配置。

## 8. 验收标准

### 共享层

- [ ] Dify 和 MOI 的已有路径能写入统一 ledger。
- [ ] Native 与 Direct Retrieval 使用不同的 pipeline/condition。
- [ ] 所有 raw request/response 脱敏并有 hash。
- [ ] 失败、重试、超时、unsupported、trace unavailable 都有明确 status/reason。
- [ ] run 结束可以自动 reconcile 计划分母与实际 attempts。

### 本地 Dify

- [ ] Dify release tag、compose commit、镜像 digest 和 vector store 已固定。
- [ ] `http://localhost/install` 初始化成功，`<base_url>/v1` API 认证成功。
- [ ] 本地 App API Key 与 Dataset API Key 已创建，Cloud key/ID 未被复用。
- [ ] 本地 generation、embedding、可选 reranker provider probe 通过，并记录 `model_egress`。
- [ ] 44 文档 smoke 能达到 `indexing_status=completed`，retrieval probe 有 raw artifact。
- [ ] Chat/Workflow native path 能返回 answer；Chat 的 retriever resources 或 Workflow 显式 contexts 能被规范化，否则记录 trace unavailable。
- [ ] 直接 `/datasets/{dataset_id}/retrieve` 的结果可归档，并与 native 条件分开统计。

### FastGPT

- [ ] 固定版本和 OpenAPI spec hash 可复现。
- [ ] 文件 hash 到 collection id 映射完整。
- [ ] native chat 使用独立 chatId，detail response 可归档。
- [ ] searchTest 结果可归档为 direct retrieval contexts。

### RAGFlow

- [ ] x86/镜像/模型依赖和 `vm.max_map_count` 已记录。
- [ ] 每个文档的 parse/index run 状态可审计。
- [ ] `/retrieval` 返回的 chunk/source/score 可归档。
- [ ] native response 的 reference/reference metadata 可以被稳定解析，或明确记录不可用。

### MaxKB

- [ ] 实例 API 文档和版本已固定，spec hash 已归档。
- [ ] dataset/document/ready endpoint 权限 probe 通过。
- [ ] native session 隔离已通过重复问题测试。
- [ ] direct retrieval 的 hit_test 或等价 endpoint 有真实结构；否则结果标记 unsupported，不伪造 contexts。

## 9. 风险与决策门

| 风险 | 影响 | 决策门 |
|---|---|---|
| Dify Cloud 与本地 Dify 混用 | app key、dataset id、模型/版本和网络条件不可比 | 使用 `dify_cloud`/`dify_local` 两个 system identity；正式本地矩阵只统计 `dify_local` |
| Dify 服务本地启动但模型 provider 不可用 | ingest 或 native query 失败 | 服务 health、embedding probe、generation probe 都通过后才进入 question run |
| Dify runner 只改了 `.env` | ingest 与 run 可能指向不同 endpoint | preflight 同时打印并 hash `DIFY_API_BASE_URL` 与 config `base_url`，两者不一致时阻止运行 |
| 本地机器为 ARM64 | RAGFlow 官方镜像不可直接运行 | 使用 x86 Docker 主机/VM，或另建 ARM 构建条件；不得混合性能结果 |
| 产品版本漂移 | endpoint/response schema 变化 | 每个 run 固定 image tag，启动时保存 version/spec hash |
| 外部 LLM/embedding 不稳定 | readiness 和 latency 失真 | 记录模型 endpoint、超时、provider；失败归 operability，不当质量结论 |
| MaxKB API 不稳定或无权限 | 无法完成可复现 ingest/retrieval | 先 contract discovery；没有稳定 API 就暂停该版本，不用 UI 伪装 API |
| Citation 只在部分 response/event 中存在 | 证据指标不可比 | 保存完整 raw/SSE；按 `available/partial/unavailable` 分层统计 |
| chunk/embedding/rerank 默认不同 | 结果解释混淆 | Quick Native 保留默认条件；Optimized 另设条件且冻结预算和参数 |
| 大 corpus 导入耗时 | 运行窗口和资源不足 | 先用小 fixture，ready 后再扩容；解析失败与检索失败分开 |

## 10. 官方资料与仓库依据

以下链接均为本报告调查时使用的官方文档或官方源代码；版本、路径和响应格式仍以实际部署实例的 contract probe 为准。

### Dify

- [Dify 官方 GitHub Quick start](https://github.com/langgenius/dify#quick-start)：Community Edition、Docker Compose、`http://localhost/install` 和 self-hosted 入口。
- [Dify Docker 部署 README](https://github.com/langgenius/dify/blob/main/docker/README.md)：`.env`、compose、vector store 和服务启动说明。
- [Dify Docker 环境变量示例](https://github.com/langgenius/dify/blob/main/docker/.env.example)：self-hosted 服务配置、存储、向量库和可选外联项。
- [当前 Dify RAG evaluation pipeline](./dify-rag-evaluation-pipeline.md)：本地 runner 已实现的 Dataset、Chat/Workflow、retrieve 和结果归档路径。

### FastGPT

- [API Documentation Introduction](https://doc.fastgpt.io/en/openapi/intro)：Base URL、Dev API/System OpenAPI、API Key 权限说明。
- [Dataset API](https://doc.fastgpt.io/en/openapi/dataset)：知识库、localFile 上传、collection 和 searchTest。
- [Chat API](https://doc.fastgpt.io/en/openapi/chat)：应用对话、chatId、detail、responseData 和限制。
- [Deploy with Docker Compose](https://doc.fastgpt.io/en/self-host/deploy/docker)：本地 compose、向量数据库、资源和模型配置。

### RAGFlow

- [RAGFlow 官方 GitHub](https://github.com/infiniflow/ragflow)：Docker、release tag、x86/ARM64、`vm.max_map_count` 和本地运行说明。
- [RAGFlow HTTP API Reference](https://ragflow.com.cn/docs/http_api_reference)：当前 OpenAI endpoint、dataset/document/chunk、retrieval、reference 参数。

### MaxKB

- [MaxKB 官方 GitHub](https://github.com/1Panel-dev/maxkb)：开源仓库、Docker quick start 和版本入口。
- [通过 API KEY 进行对话](https://maxkb.cn/docs/v2/user_manual/chat_to_API/)：OpenAI 兼容应用 API、系统 API 文档、session/open/dialogue 说明。
- [MaxKB 知识库文档](https://maxkb.cn/docs/v2/user_manual/dataset/dataset/)：知识库和文档导入能力。
- [MaxKB dataset routes（当前源码）](https://raw.githubusercontent.com/1Panel-dev/MaxKB/refs/heads/main/apps/dataset/urls.py)：用于说明版本绑定的内部 route，不能替代实例 API 文档。
- [MaxKB application routes（当前源码）](https://raw.githubusercontent.com/1Panel-dev/MaxKB/refs/heads/main/apps/application/urls.py)：用于说明应用 chat/open/completions route 的版本绑定性质。

### 本仓库

- [v1.0 总计划](../drafts/v1.0.md)
- [平台 adapter 与运行计划](../drafts/v1.0-todos/03-platform-adapter-and-run-plan.md)
- [当前 Dify RAG evaluation pipeline](./dify-rag-evaluation-pipeline.md)
- [当前 MOI 本地 RAG pipeline](./moi-local-rag-pipeline-2026-08-05.md)
