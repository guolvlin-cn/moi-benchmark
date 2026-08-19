# 本地 Dify、MaxKB 与 FastGPT 的 RAG 实现机制

## 架构、数据流、接口契约与可复现实验报告

**项目**：MOI RAG Benchmark  
**报告日期**：2026-08-11  
**研究对象**：`dify_local`、`maxkb_local`、`fastgpt_local`  
**部署模式**：本地服务 + 外部模型提供商（`model_egress=external`）  
**主机**：macOS / Apple Silicon，Colima `linux/arm64`，16 GiB RAM

> 本报告回答的是“这三个系统如何实现 RAG”，而不是在没有统一模型、语料、切分参数和评测条件时给出总排名。报告同时区分三类证据：`[OF]` 官方文档或官方仓库事实；`[LO]` 当前本地部署、适配器和运行产物观察；`[INF]` 基于前两者的工程推断。

## 摘要

检索增强生成（Retrieval-Augmented Generation，RAG）可以抽象为一条由文档摄取、解析与切分、向量化、索引、查询召回、可选重排、上下文组装和大模型生成组成的流水线。Dify、FastGPT 和 MaxKB 都实现了这条主链路，但它们把“知识库”和“应用”的边界放在了不同位置：

1. **Dify 是编排优先（orchestration-first）的实现**。知识库以 Dataset 为中心，文档经过异步索引后可通过 Dataset Retrieval API 单独检索；Native Chat 再将 Dataset 绑定到一个本地 Chat App，由应用编排模型调用和上下文注入。
2. **FastGPT 是数据集与搜索引擎优先（dataset/search-first）的实现**。知识库由 Dataset、Collection 和数据条目组成，向量通常存入 PostgreSQL/PGVector，MongoDB 负责其他元数据和文件对象；查询可经过语义、全文、混合、RRF 和可选重排，再由应用 API 完成回答。
3. **MaxKB 是智能体优先（agent-first）的实现**。知识库由文档和段落构成，应用绑定知识库后通过 OpenAI-compatible Chat API 对外提供 RAG 问答。当前 MaxKB 实例能够通过管理接口执行 `hit_test` 诊断，但没有在本项目中确认一个可供评测器稳定使用的公开 Direct Retrieval 合约，因此不能把管理命中测试冒充为公开检索能力。

三者的核心差异不在“是否使用向量数据库”，而在于：索引单元和状态机不同、搜索策略的默认边界不同、应用与知识库的绑定方式不同，以及检索结果和引用是否通过稳定公共 API 暴露。当前本地适配器已经把三个系统映射到统一的 `ingest → readiness → retrieval → native_qa` 抽象；其中 Dify 和 FastGPT 有公共 Direct Retrieval 合约，MaxKB 当前只保留管理侧诊断结果。

## 1. 研究问题与边界

### 1.1 研究问题

本报告围绕以下问题展开：

* **RQ1：** 三个平台如何把源文档转化为可检索的知识单元？
* **RQ2：** 三个平台如何执行查询召回、重排和上下文组装？
* **RQ3：** Native QA 如何调用模型，知识库如何绑定到应用？
* **RQ4：** 本地部署的 API、组件和数据流与厂商官网/云端公开流程在哪些地方相同或不同？
* **RQ5：** 哪些差异会影响竞品评估的可比性？

### 1.2 研究边界

本报告分析的是当前仓库中已经落地的本地部署和评测适配，不等同于对厂商全部内部实现的源码审计。具体边界如下：

* 服务本体运行在当前机器的 Docker/Colima 中；模型和 Embedding 可以访问外部 API，因此不是 fully-offline 实验。
* RAGFlow 因当前机器的资源与官方镜像条件被单独标记为 `BLOCKED_LOCAL`，不纳入本报告的三平台机制对比。
* 评测 adapter 的“控制文本（candidate Markdown）”是为了保证多平台输入一致的实验表示；它不能被误读为平台生产环境唯一的原生文档解析路径。
* 当前报告不比较不同模型、Embedding 或 Prompt 的优劣；更换 Embedding 必须创建新索引，不能在同一向量空间内混用。

## 2. 方法与证据

### 2.1 证据来源

本文使用四类证据：

1. 各厂商的官方仓库、部署文档、知识库和检索文档；
2. 本地固定版本和 Docker 镜像 manifest；
3. `local-rag-platforms/scripts/evaluation/competitor_eval_runner.py` 中的实际请求、状态轮询和回答提取逻辑；
4. 本地 smoke、readiness、provider probe 和评估运行产物。

所有 API 路径的“本地实现事实”以本项目冻结的 platform contract 和实际请求为准；厂商文档用于判断这些路径是否属于官方产品流程。对于没有公开稳定契约的能力，报告明确写为 `UNSUPPORTED_API` 或“管理诊断”，不从答案文本反推引用或检索上下文。

### 2.2 统一 RAG 抽象

设原始文档集合为 \(D=\{d_1,\ldots,d_n\}\)，解析器将文档切分为知识单元集合 \(C=\{c_1,\ldots,c_m\}\)。每个知识单元被编码为向量：

\[
z_i = f_{\theta}(c_i),
\]

查询 \(q\) 经过同一 Embedding 空间编码后，以相似度函数 \(s(q,z_i)\) 取得前 \(k\) 个候选：

\[
R_k(q)=\operatorname{TopK}_{c_i\in C}s(f_{\theta}(q),z_i).
\]

若平台启用关键词检索、混合召回或重排，则先得到候选集合，再使用融合或重排函数 \(g\)：

\[
R'_k(q)=\operatorname{TopK}_{c_i\in R(q)}g(q,c_i).
\]

最后，应用将查询、候选文本、来源元数据和系统 Prompt 组装为生成请求：

\[
\hat{a}=\arg\max_a P_{\phi}(a\mid q,R'_k(q),I),
\]

其中 \(I\) 是应用的编排配置。三个平台都实现了这个抽象，但对 (C)、(R(q))、(g) 和 (I) 的具体定义不同。

### 2.3 当前本地实验控制条件

机制研究与模型选择分离，但本项目的后续评估采用如下 provider policy：

| 组件 | 计划冻结配置 | 说明 |
| --- | --- | --- |
| 文本 LLM | 百度千帆 `deepseek-v4-flash`（项目别名 `dsv4f`） | 外部 API；实际可用 ID 以 `/v2/models` 为准 |
| 多模态 LLM | 百度千帆 `qwen3.5-35b-a3b`（按实际 model list 解析） | 仅在题目含图像输入时使用 |
| Embedding | 华为 MaaS `bge-m3` | 外部 API；使用独立向量空间 |
| Reranker | 初版关闭 | 避免平台默认策略造成不可控差异 |
| 服务 | 本地 Docker/Colima | 记录 `deployment_mode=self_hosted` |

历史 smoke 中曾出现 Qianfan `qwen3-embedding-8b` 4096 维配置；它与 MaaS `bge-m3` 不属于同一索引条件，切换时必须重建知识库/索引。FastGPT 的运行时还存在 1536 维向量存储约束，详见第 5 节。

## 3. 本地部署与组件拓扑

### 3.1 环境

本地环境记录于 [`environment-manifest.json`](../.local-services/environment-manifest.json)：Docker Engine `29.5.2`、Compose `5.4.0`，Docker context 为 `colima`，运行平台为 `linux/aarch64`。三个服务串行运行，以避免 16 GiB 主机上的数据库、索引和模型请求互相争抢资源。

| 系统 | 固定源版本 | 本地入口 | 本地运行形态 | 主要数据组件 |
| --- | --- | --- | --- | --- |
| Dify | Community Edition `1.16.1`，commit `6f8ed69e…` | `http://127.0.0.1:8010` | 官方 Docker Compose | PostgreSQL、Weaviate、Redis、Dify API/Worker、Plugin Daemon |
| FastGPT | 源码 `v4.15.6`，commit `3db33e9…`；运行镜像 `v4.15.4` | `http://127.0.0.1:3000` | 官方 PgVector Compose 变体 | PostgreSQL/PGVector、MongoDB、Redis、MinIO、AIProxy、FastGPT App |
| MaxKB | `v2.10.4-lts`，commit `fd6141e…` | `http://127.0.0.1:8090` | 固定 arm64 Docker image | MaxKB 单容器持久化卷，PostgreSQL/pgvector 与 LangChain 应用层 |

版本和镜像证据保存在各平台的 `deployment-manifest.json` 与 `image-manifest-*.json`。FastGPT 的源码 tag 与 compose 实际引用镜像存在 `v4.15.6`/`v4.15.4` 版本差异，故后续结果应标记 `VERSION_DIVERGENCE`。

### 3.2 从部署到 RAG 的共同数据流

```text
本地 Web/API
    │
    ├── 创建 Dataset / Knowledge Base
    │       └── 选择 Embedding provider
    │
    ├── 上传或提交文档
    │       └── 解析 → 清洗 → 切分 → Embedding → 向量/倒排索引
    │
    ├── 等待异步索引状态 ready
    │
    ├── Direct Retrieval（若有公开合约）
    │       └── query → candidates → optional rerank → contexts
    │
    └── Native QA
            └── app + knowledge base → prompt/context assembly → external LLM
```

这里“本地”只描述上图的 Web/API、数据库、索引和编排服务位置；Embedding 与生成模型仍可以出网。因而本项目的安全/性能结论应表述为“self-hosted RAG service with external model egress”。

## 4. Dify：Dataset 检索与 App 编排

### 4.1 官方产品模型

**[OF]** Dify 官方 [Docker 自托管文档](https://github.com/langgenius/dify/blob/main/docker/README.md) 采用 Docker Compose 部署 Community Edition；官方[知识库检索文档](https://docs.dify.ai/guides/knowledge-base/retrieval)将文档上传、切分、Embedding、检索和应用编排分为相互连接的能力。当前本地 Compose 使用 Dify API/Worker、Web、Plugin Daemon、PostgreSQL、Weaviate、Redis、Sandbox 和反向代理等组件。

**[INF]** 因此 Dify 的 RAG 抽象可以写为：

```text
Dataset
  ├── Document
  │     └── segments/chunks + metadata + vector
  └── Retrieval API

Chat App / Workflow
  └── Dataset binding → retrieve → prompt assembly → LLM
```

Dataset 是知识资产边界，App/Workflow 是回答行为边界。两者分离使得同一知识库可以被多个应用引用，但也要求评估器显式确认 Native App 的 Dataset binding。

### 4.2 本地摄取与索引

当前本地 adapter 的实际流程为：

1. `POST /datasets` 创建隔离 Dataset，并声明 `indexing_technique=high_quality`、`permission=only_me`、`embedding_model` 与 `embedding_model_provider`；
2. `POST /datasets/{dataset_id}/document/create-by-file` 以 multipart 上传文档；
3. 使用自定义处理规则：换行分隔，`max_tokens=512`、`overlap=64`，启用多余空格清理，关闭 URL/Email 清理；
4. 通过 `GET /datasets/{dataset_id}/documents` 轮询文档状态，只有达到 `completed/indexed/ready/available` 才进入检索；
5. 对大规模 document-local 条件，adapter 将每个 scope 独立管理并限制同时 indexing 的 scope 数量，以减少 Dify Worker、Weaviate 和外部 Embedding API 的并发压力。

Dify 的索引是异步过程。上传 HTTP 200 仅表示请求被接受，不能当作“知识库已经可检索”。本地资源图（`resource-map.json`）和 scope 状态持久化后，可以在中断后恢复，而不是重新创建所有 Dataset。

### 4.3 Direct Retrieval

当前本地 Direct Retrieval 使用公开 Dataset API：

```http
POST /v1/datasets/{dataset_id}/retrieve
Authorization: Bearer <local-dataset-key>
Content-Type: application/json

{
  "query": "...",
  "retrieval_model": {
    "search_method": "semantic_search",
    "reranking_enable": false,
    "top_k": 10,
    "score_threshold_enabled": false
  }
}
```

返回值被保存为 `public_direct_retrieval` 合约。评测器从结构化的 result/context 字段提取 `document_id`、segment、score 和位置元数据；不会从最终答案中猜测召回来源。当前初版关闭 Dify rerank，使得该路径主要观察 Embedding + semantic search。

### 4.4 Native QA

每个评估资源都创建或绑定一个本地 Chat App：

1. 通过本地 Console API 创建 Chat App；
2. 将当前新建 Dataset 写入 App 的 model configuration；
3. 创建该 App 的本地 API key；
4. 使用 `POST /v1/chat-messages`，发送 `query`、`inputs`、`response_mode=blocking`、空 `conversation_id` 和独立 `user`；
5. 从结构化 response 中读取 answer、usage 和可用引用字段。

每轮评估使用新绑定的 App 或恢复同一 run 的资源图，不复用 Dify Cloud 的 app key、dataset ID，也不把历史本地 App 当作隐式 fallback。该设计保证 Native QA 确实回答当前 Dataset，而不是一个看似成功但实际指向旧语料的应用。

### 4.5 与云端流程的关系

| 步骤 | Dify Cloud/官方流程 | Dify local 实际流程 | 结论 |
| --- | --- | --- | --- |
| 知识库 | Dataset | Dataset | `SAME_CONTRACT` |
| 上传 | Dataset document API/UI | 同一 API 路径，host 改为 `127.0.0.1:8010` | `LOCAL_VARIANT` |
| 索引 | Dify 托管 Worker/向量库 | 本地 Worker/Weaviate/PostgreSQL/Redis | `LOCAL_VARIANT` |
| Native QA | App API/Workflow API | 本地 App API/Workflow API | `SAME_CONTRACT` |
| 模型 | Cloud provider 或用户 provider | Qianfan/MaaS 外部 provider | `LOCAL_VARIANT` |
| 认证 | Cloud tenant key | 本地 tenant/admin/dataset/app key | `LOCAL_VARIANT` |
| Direct Retrieval | 公开 Dataset Retrieval | 公开 Dataset Retrieval | `SAME_CONTRACT` |

## 5. FastGPT：Dataset、Collection 与搜索引擎

### 5.1 官方产品模型

**[OF]** FastGPT 的[数据集设计文档](https://doc.fastgpt.io/en/self-host/design/dataset)把知识库描述为由知识库、集合（Collection）和数据条目组成；其[数据集引擎文档](https://doc.fastgpt.io/en/guide/dataset/dataset_engine)说明：MongoDB 保存其他业务数据/文件对象，PostgreSQL + PGVector 承担向量检索，并可使用 HNSW；搜索过程可包含查询优化、语义检索、全文检索、混合检索、RRF 和 rerank。

这使 FastGPT 的数据模型更接近一个可配置搜索引擎：

```text
Dataset / Knowledge Base
  └── Collection
        └── data entries / chunks
              ├── text + source metadata
              └── vector in PGVector

App / Workflow
  └── Dataset Search node or Chat API → context → LLM
```

与 Dify 的主要差异是，FastGPT 把“搜索方法”作为 Dataset Engine 的显式配置维度；而 Dify 当前适配器只固定了 semantic search 这一条公开路径。

### 5.2 本地摄取与索引

当前统一 runner 的控制流程为：

1. `POST /api/core/dataset/create` 创建隔离 Dataset，指定 `vectorModel` 和 `agentModel`；
2. `POST /api/core/dataset/collection/create` 创建 Collection；
3. `POST /api/core/dataset/data/pushData` 将规范化文本和元数据写入数据条目；
4. 轮询 `POST /api/core/dataset/collection/listV2`，要求对应 Collection 的 `trainingAmount=0`、`activeTrainingAmount=0`、`finalErrorAmount=0` 且没有 `hasError`；
5. 创建只绑定当前 Dataset 的本地 App，并通过 `POST /api/support/openapi/create` 生成应用 API key。

在官方 Web 流程中，用户可上传文件，文件进入 MongoDB GridFS，浏览器/服务端执行解析和切分，训练线程再生成向量并写入 PGVector。当前 benchmark adapter 对 `candidate_markdown` 使用 `pushData`，这样可以锁定输入文本和文档边界；它不是把所有 PDF 都当作 FastGPT 原生文件解析结果。

### 5.3 Direct Retrieval 与搜索组合

当前本地 Direct Retrieval 使用：

```http
POST /api/core/dataset/searchTest

{
  "datasetId": "...",
  "text": "...",
  "limit": 10,
  "similarity": 0,
  "searchMode": "embedding",
  "usingReRank": false,
  "datasetSearchUsingExtensionQuery": false
}
```

这条路径是 `public_direct_retrieval`，返回 `data.list` 中的命中条目。需要注意：FastGPT 官方引擎具备混合检索、RRF 和 rerank 等更丰富能力，但当前评估为了跨产品可比，明确使用 embedding search 且关闭 rerank。若未来开启这些功能，必须把 `searchMode`、候选数、融合权重、rerank 模型和成本作为新的实验条件记录，不能与当前结果直接合并。

### 5.4 Native QA

FastGPT 的 Native QA 通过 OpenAI-compatible App API：

```http
POST /api/v1/chat/completions

{
  "appId": "...",
  "chatId": "<new-uuid-per-question>",
  "stream": false,
  "detail": true,
  "messages": [{"role": "user", "content": "..."}]
}
```

`detail=true` 使返回值保留 `responseData`、choices、usage 和可能的检索/引用结构。评测器对每个问题和 repeat 使用新的 `chatId`，避免上一道题的会话状态污染当前题目。若响应只有 answer 字符串而没有结构化 source，结果只能记为“回答成功、引用不可用”。

### 5.5 向量维度和版本差异

当前本地配置中曾使用 Qianfan `qwen3-embedding-8b` 的 4096 维返回，而 FastGPT v4.15.x 运行时的 PGVector schema 为 1536 维。现有适配器把 `source_dimension`、`effective_dimension` 和 `dimension_action` 写入 artifact，并对超宽向量执行兼容性截断。

这不是一个可以忽略的实现细节：

* 它意味着“上游 Embedding 模型名相同”不等价于“下游索引保留了完整向量”；
* FastGPT 结果必须标记有效维度和动作，不能和原生 4096 维索引无条件比较；
* 更稳妥的生产/评测做法是使用与 PGVector schema 一致的 Embedding 维度，或者显式迁移 schema 后重建整个 Dataset。

### 5.6 与云端流程的关系

| 步骤 | FastGPT Cloud/官方流程 | FastGPT local 实际流程 | 结论 |
| --- | --- | --- | --- |
| 知识库 | Dataset → Collection → entries | 同一数据模型和 API 层次 | `SAME_CONTRACT` |
| 文件处理 | 上传/解析/训练线程 | 本地服务处理；benchmark 可用 controlled text | `LOCAL_VARIANT` |
| 向量索引 | 托管 PGVector/Mongo | 本地 PostgreSQL/PGVector/Mongo | `LOCAL_VARIANT` |
| 搜索 | Dataset Search，支持多种 search method | `searchTest`，当前固定 embedding | `LOCAL_VARIANT` |
| Native QA | App Chat API | 本地 App Chat API | `SAME_CONTRACT` |
| 引用 | `detail`/responseData 等结构化字段 | 原始 response 保存并按字段提取 | `SAME_CONTRACT` |
| 模型 | Cloud 或配置的 provider | Qianfan/MaaS 外部 provider | `LOCAL_VARIANT` |
| 版本 | 云端托管 | 源码 `v4.15.6` + 镜像 `v4.15.4` | `VERSION_DIVERGENCE` |

## 6. MaxKB：Knowledge Base、Paragraph 与 Agent API

### 6.1 官方产品模型

**[OF]** [MaxKB 官方仓库](https://github.com/1Panel-dev/MaxKB)将其定位为企业级开源智能体平台，提供知识库/RAG 流程、文件或网页输入、文本切分、向量化和多模型接入；[官方知识库文档](https://docs.maxkb.pro/user_manual/dataset/dataset/)描述了知识库的创建、配置和向量化流程。官方资料说明其技术栈包含 Django、LangChain、PostgreSQL/pgvector；知识库和应用是用户可见的主要产品对象。

从评测角度，可以把 MaxKB 抽象为：

```text
Knowledge Base
  └── Document
        └── Paragraphs/chunks + vector + metadata

Application / Agent
  └── bound knowledge base → retrieval → prompt → OpenAI-compatible LLM
```

与 Dify、FastGPT 相比，MaxKB 的公开产品边界更偏向“创建一个可对话的应用”。知识库内部的命中测试接口存在，但不一定是对外稳定的检索服务契约。

### 6.2 本地摄取与索引

当前 MaxKB adapter 使用本地管理 API 完成：

1. 通过 `POST /admin/api/workspace/default/knowledge/base` 创建隔离 Knowledge Base，并绑定 `embedding_model_id`；
2. 通过 `PUT /admin/api/workspace/default/knowledge/{knowledge_id}/document/batch_create` 写入文档名和段落列表；
3. 轮询 `GET /admin/api/workspace/default/knowledge/{knowledge_id}/document/{document_id}`，以当前版本状态后缀 `2` 作为 ready，后缀 `3` 作为 failed；
4. 创建 Application，设置 `knowledge_id_list` 为当前知识库，发布应用，并生成 application key；
5. 通过应用的 OpenAI-compatible endpoint 执行 Native QA。

这里的 `batch_create` 是控制文本评估的实现路径：它把已经确定的文本段落提交给 MaxKB，使三个平台尽量接收相同的解析后内容。对于原生 PDF 上传，当前冻结 contract 没有把 PDF bytes 直接送入这一批处理接口，因此 source-PDF 条件必须在评测 ledger 中记为 `UNSUPPORTED` 或使用明确声明的 controlled-text 适配，不能把两者混称。

### 6.3 Provider 与 Embedding 注册

MaxKB 的通用 OpenAI Embedding 表单对维度选项有限制。Qianfan 4096 维模型的历史注册脚本因此先直连 `/v2/embeddings` 校验向量长度，再以 provider、model type 和 model name 幂等发现/注册模型。当前正式评估建议改用 MaaS `bge-m3`，并把返回维度记录到 provider probe；无论哪一个 provider，切换都需要新建知识库并重新向量化。

该过程说明 MaxKB 的模型“配置成功”至少包含两个条件：

* 管理端保存了模型 credential 和 API base；
* 实际 Embedding 请求成功且返回长度与索引 schema 一致。

只修改环境变量或只在 provider 表中保存名称，不能证明 ingest 和 QA 两条路径都在使用同一模型。

### 6.4 Direct Retrieval 的限制

当前实例可以调用：

```http
POST /admin/api/workspace/default/knowledge/{knowledge_id}/hit_test

{
  "query_text": "...",
  "top_number": 10,
  "similarity": 0.0,
  "search_mode": "embedding"
}
```

但这是带管理员凭证的 `diagnostic_admin_contract`，不是本项目已经确认的公开 Direct Retrieval API。因此统一评测输出遵循以下规则：

* 保存 `hit_test` 的原始脱敏响应，作为 MaxKB 内部检索诊断；
* 可以计算诊断命中结果，但指标名称必须带 `admin_diagnostic`；
* 公共 Direct Retrieval 指标记为 `unsupported`，不与 Dify/FastGPT 的 `public_direct_retrieval` 混合排名；
* 不把 Native QA 的回答、引用文本或 UI 页面中的命中结果反推成公共检索 API。

这是当前三平台比较中最重要的契约差异。

### 6.5 Native QA

MaxKB 发布 Application 后，当前本地路径解析为：

```text
http://127.0.0.1:8090/chat/api/{application_id}/chat/completions
```

请求使用 OpenAI-compatible 的 `model`、`stream=false` 和 `messages`。应用内部负责选择关联知识库、执行检索、组装上下文并调用外部 LLM。评测器记录 answer、usage、session/application 标识和完整脱敏 response；只有 response 明确携带 evidence/source 字段时才记录 citation。

### 6.6 与云端流程的关系

| 步骤 | MaxKB Cloud/官方流程 | MaxKB local 实际流程 | 结论 |
| --- | --- | --- | --- |
| 知识库 | Knowledge Base | Knowledge Base | `SAME_CONTRACT` |
| 文档 | 上传/网页同步/自动切分 | 本地管理 API；评测可用 paragraph batch | `LOCAL_VARIANT` |
| Embedding | provider 配置与云端资源 | 本地 MaxKB 管理面 + 外部 MaaS/Qianfan | `LOCAL_VARIANT` |
| Native QA | 发布应用后调用应用 API | 本地应用 API | `SAME_CONTRACT` |
| Direct Retrieval | 产品 UI/内部命中测试能力 | 当前仅确认 admin `hit_test` | `UNSUPPORTED_API` |
| 引用 | 由应用配置和 response 字段决定 | 仅读取结构化 evidence/source | `LOCAL_VARIANT` |
| 服务/数据 | 平台托管 | 单机 Docker + 持久化卷 | `LOCAL_VARIANT` |

## 7. 三个平台的统一比较

### 7.1 数据模型与存储

| 维度 | Dify | FastGPT | MaxKB |
| --- | --- | --- | --- |
| 知识资产根对象 | Dataset | Dataset/Knowledge Base | Knowledge Base |
| 文档下一级 | Document → segments | Collection → data entries | Document → paragraphs |
| 本地向量后端 | 当前 Compose 使用 Weaviate | PGVector；HNSW 可用 | PostgreSQL/pgvector（官方架构） |
| 业务/文件元数据 | PostgreSQL 等 | MongoDB/GridFS 等 | MaxKB 持久化卷内的关系数据/文件数据 |
| 索引状态 | Dataset document indexing status | Collection training counters | Document status code/task state |
| 绑定应用 | App/Workflow model config | App/Workflow Dataset binding | Published Application knowledge list |

### 7.2 接口与评测能力

| 能力 | Dify | FastGPT | MaxKB |
| --- | --- | --- | --- |
| 创建知识资源 | `POST /datasets` | `POST /api/core/dataset/create` | `POST /workspace/default/knowledge/base` |
| 写入文档 | multipart `create-by-file` | Collection + `pushData` | `batch_create` paragraphs |
| 等待 ready | `GET /datasets/{id}/documents` | `collection/listV2` counters | document status endpoint |
| 公共检索 | `/datasets/{id}/retrieve` | `/api/core/dataset/searchTest` | 当前未确认 |
| Native QA | `/chat-messages` | `/api/v1/chat/completions` | `/chat/api/{app}/chat/completions` |
| 引用/上下文 | Retrieval response / app response | `detail=true` 的 responseData | 仅 response 明确返回时可用 |
| 当前 runner 的默认检索 | semantic | embedding | admin diagnostic embedding |
| 当前 runner 的 rerank | 关闭 | 关闭 | 公共路径未启用 |
| Direct Retrieval 统一状态 | `success` | `success` | `unsupported`（公共），诊断另存 |

### 7.3 机制上的本质差异

1. **边界差异。** Dify 把 Dataset Retrieval 做成独立公共 API；FastGPT 把搜索引擎能力做成 Dataset Engine 和 Workflow/Search 节点；MaxKB 把检索更多地隐藏在 Application/Agent 内。
2. **异步状态差异。** Dify 使用文档 indexing 状态，FastGPT 使用 training counters，MaxKB 使用文档任务状态。统一评估不能用“上传响应成功”作为 ready 判据，必须对每个平台定义自己的终止状态。
3. **搜索策略差异。** FastGPT 官方搜索链路的可配置项最丰富，支持混合检索、RRF 和 rerank；本轮为公平性关闭高级组合。Dify 和 MaxKB 的当前统一路径均是 embedding/semantic 基线。
4. **可观测性差异。** Dify/FastGPT 能在公共 API 层取得 contexts 或 responseData；MaxKB 当前只能取得 admin hit-test 诊断，导致“检索质量”和“应用 QA 质量”不能在同一 public contract 上完全对齐。
5. **输入表示差异。** 厂商原生文件解析可能包括 PDF/Office 解析、表格、图片或 OCR；为了比较检索机制，benchmark 还提供 controlled Markdown/paragraph 表示。必须在结果中记录输入表示，否则会把解析器能力差异误算为检索能力差异。

## 8. 本地 smoke 与实现验证

### 8.1 验证项目

统一 runner 输出以下阶段：

```text
service readiness
  → provider probe
  → knowledge resource creation
  → document ingest
  → index readiness
  → native QA
  → direct retrieval or explicit unsupported
```

所有请求和响应以脱敏 JSON 保存，并为每个 artifact 保存 SHA-256 sidecar；密钥只保存为 secret path 引用，不进入 `resource-map.json` 和报告。

### 8.2 已记录的本地观察

| 系统 | 本地观察 | 解释 |
| --- | --- | --- |
| Dify | 三文档 smoke 完成索引，Direct Retrieval 返回结构化 contexts；44 文档 readiness run 达到 indexed/ready | 说明 Dataset、异步索引、公共检索和本地 App API 这条链路已经贯通 |
| FastGPT | provider 初始化、Dataset/Collection 创建、三 Collection ready、`searchTest` 返回命中 | 搜索路径已贯通；早期部署 manifest 记录过 Native QA 超时，故正式评估仍需以当前 run artifact 的 terminal ledger 为准 |
| MaxKB | 本地 `/admin/` 可访问，知识库/模型/应用管理路径可用；`hit_test` 可做 admin 诊断 | Native QA 和文档状态必须按当前版本重新核对；公共 Direct Retrieval 仍记 `unsupported` |

这些观察是“实现与部署验证”，不是三平台同条件的最终排行榜。正式评估时应使用同一数据包、同一问题顺序、同一 repeat 规则，并把每个平台的 `public_direct_retrieval` 和 `diagnostic_admin_contract` 分开统计。

### 8.3 评估可比性的必要记录

每次评估启动前至少保存：

* 平台版本、源码 commit、镜像 digest、Docker platform；
* provider、model ID、Embedding 维度、API base 的非敏感部分；
* 文档表示（native source 或 controlled candidate text）、切分参数、chunk overlap；
* Dataset/Collection/Knowledge Base 的新建策略；
* top-k、similarity threshold、search mode、rerank 开关；
* ingest ready 的判定规则；
* QA timeout、stream/detail、chat/session 隔离方式；
* raw request/response 的 hash 和 terminal ledger。

## 9. 讨论

### 9.1 “本地部署”不等于“本地模型”

三套服务的数据库、索引、Web/API 和应用编排均在本机运行，但当前模型请求访问 Qianfan 或 MaaS。该模式适合研究平台工程能力、API 契约和索引流程，不适合宣称断网可用、完全隐私或端到端本地推理。若要研究 fully-offline，需要另行部署 LLM、Embedding、reranker、OCR/parser，并重新记录硬件和模型版本。

### 9.2 Provider 变化会改变实验对象

Embedding 不是普通配置项，而是索引函数 \(f_\theta\) 的一部分。切换 TaaS、Qianfan 或 MaaS 后，向量空间和相似度分布可能改变；正确流程是新建 Dataset/Knowledge Base、重新 ingest 和重新等待 ready。FastGPT 还可能发生向量维度适配或截断，因此 provider probe 和有效维度必须进入实验记录。

### 9.3 Native QA 与 Direct Retrieval 不是同一个指标

Direct Retrieval 测的是召回上下文是否命中 Gold；Native QA 测的是应用在上下文基础上生成答案的能力。MaxKB 当前只能把 admin `hit_test` 作为检索诊断，而不能把它和 Dify/FastGPT 的 public retrieval recall 直接放在同一主表。答案文本里出现了正确实体，也不能证明该实体来自知识库。

### 9.4 资源隔离是本地评测的必要条件

Dify 的 App binding、FastGPT 的 appId/datasetId、MaxKB 的 application/knowledge_id 都可能持久化在平台数据库中。如果复用历史应用或只修改全局 provider，评估会出现“请求成功但回答来自旧索引”的隐性污染。当前 runner 每个 run 创建隔离资源，并在 resume 时只恢复同一 run 的 resource map。

## 10. 威胁与限制

* **版本限制：** FastGPT 源码版本与运行镜像版本不完全一致；Dify/MaxKB 的官方文档和当前运行版本也可能随 release 变化。
* **解析限制：** controlled Markdown/paragraph 能控制文本一致性，但不能代表平台 native PDF、OCR、表格或图像解析器的全部能力。
* **模型限制：** 外部 provider 存在网络、限流、余额和服务稳定性风险；失败时切换 provider 会破坏与前一轮的严格可比性，必须新建实验条件。
* **检索 API 限制：** MaxKB 公共 Direct Retrieval 尚未确认，admin `hit_test` 只作为诊断，不作为公共指标。
* **资源限制：** 16 GiB Apple Silicon 主机要求竞品串行运行，冷启动、索引和模型请求延迟不能代表云端托管资源。
* **引用限制：** 报告只接受 response 的结构化 citation/source/evidence 字段；不从 answer 文本、UI 文字或推理过程推断 citation。
* **统计限制：** 当前 smoke 和部分 readiness 结果用于验证链路，不足以支持论文意义上的显著性检验或总排名。

## 11. 结论

本地 Dify、FastGPT 和 MaxKB 都把 RAG 落地为“知识资源管理 + 异步索引 + 应用问答”的系统，但三者的公共边界不同：

* Dify 的强项是 Dataset 与 App/Workflow 解耦，能够较自然地把公共检索和 Native Chat 分成两条可测路径；
* FastGPT 的强项是显式的数据集搜索引擎，搜索模式、混合召回、RRF 和 rerank 具有更强的可配置性，但需要严格处理向量维度与运行镜像版本；
* MaxKB 的强项是把知识库快速绑定到可发布的 Agent/Application，Native QA 路径清晰；当前评测的主要限制是公共 Direct Retrieval 契约未确认，必须把管理命中测试和公开检索能力分开。

因此，本项目后续正确的比较单位不是“哪个产品看起来回答得更好”，而是：在同一 corpus、同一解析表示、同一 Embedding/LLM、同一 top-k 和同一隔离策略下，分别比较 `public retrieval`、`native QA`、延迟、错误率和结构化 citation 能力，并对 MaxKB 的公共检索缺失单独标记 `UNSUPPORTED_API`。

## 参考资料

### 官方资料

1. [Dify GitHub repository](https://github.com/langgenius/dify)
2. [Dify official Docker deployment README](https://github.com/langgenius/dify/blob/main/docker/README.md)
3. [Dify official knowledge retrieval guide](https://docs.dify.ai/guides/knowledge-base/retrieval)
4. [Dify official API reference](https://docs.dify.ai/api-reference)
5. [FastGPT GitHub repository](https://github.com/labring/FastGPT)
6. [FastGPT self-hosted Docker deployment](https://doc.fastgpt.io/en/self-host/deploy/docker)
7. [FastGPT dataset design](https://doc.fastgpt.io/en/self-host/design/dataset)
8. [FastGPT dataset engine and search methods](https://doc.fastgpt.io/en/guide/dataset/dataset_engine)
9. [FastGPT Dataset Search workflow node](https://doc.fastgpt.io/en/guide/build/workflow/nodes/dataset_search)
10. [FastGPT quick start](https://doc.fastgpt.io/en/guide/getting-started/quick-start)
11. [MaxKB GitHub repository](https://github.com/1Panel-dev/MaxKB)
12. [MaxKB official knowledge-base documentation](https://docs.maxkb.pro/user_manual/dataset/dataset/)
13. [MaxKB official application/API documentation](https://docs.maxkb.pro/user_manual/app/app-view/)
14. [MaxKB official releases](https://github.com/1Panel-dev/MaxKB/releases)

### 本地实现与运行证据

1. [统一竞品评测 runner](../local-rag-platforms/scripts/evaluation/competitor_eval_runner.py)
2. [平台 API contract](../local-rag-platforms/scripts/evaluation/competitor_eval_platform_contracts.json)
3. [本地部署总说明](../local-rag-platforms/README.md)
4. [Dify 本地部署说明](../local-rag-platforms/dify_local/README.md)
5. [FastGPT 本地部署说明](../local-rag-platforms/fastgpt_local/README.md)
6. [MaxKB 本地部署说明](../local-rag-platforms/maxkb_local/README.md)
7. [Dify deployment manifest](../.local-services/dify_local/logs/deployment-manifest.json)
8. [FastGPT deployment manifest](../.local-services/fastgpt_local/logs/deployment-manifest.json)
9. [MaxKB deployment manifest](../.local-services/maxkb_local/logs/deployment-manifest.json)
10. [本地环境 manifest](../.local-services/environment-manifest.json)
