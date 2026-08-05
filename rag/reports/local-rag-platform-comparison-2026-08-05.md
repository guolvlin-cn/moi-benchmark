# 本地 RAG 竞品部署与云端流程对比

> 研究与初版执行日期：2026-08-05
>
> 本文只比较本地服务与官方 self-hosted/cloud 流程的合同和部署差异，不给出未经同一模型、同一 corpus、同一 condition 约束的总排名。

## 1. 范围与判定口径

本轮目标是把现有本地 MOI pipeline 之外的 Dify、FastGPT、RAGFlow、MaxKB
部署到当前唯一允许的主机，并先完成服务级和最小 API smoke。服务本体必须
在当前 macOS/Apple Silicon + Colima Linux/arm64 主机运行；MatrixOrigin TaaS
OpenAI-compatible LLM/Embedding endpoint 可以出网，因此本轮不是 fully offline。
所有结果写 `model_egress=external`。

当前 host facts：

| 项目 | 值 |
| --- | --- |
| host | macOS 15.7 / Apple Silicon / arm64 |
| container runtime | Colima |
| container platform | `linux/aarch64`（等价记录为 `linux/arm64`） |
| memory | 16 GiB |
| Docker | client 29.6.2 / server 29.5.2 |
| Compose | Docker Compose 5.4.0 |
| existing MOI | parser `8080`，MatrixOne `6001/9876`，未替换 |

允许的结果状态只有：

`SAME_CONTRACT`、`LOCAL_VARIANT`、`CLOUD_ONLY`、`LOCAL_ONLY`、
`VERSION_DIVERGENCE`、`BLOCKED_LOCAL`、`UNSUPPORTED_API`。

- `SAME_CONTRACT`：路径、认证和字段语义可在相同版本下直接映射。
- `LOCAL_VARIANT`：主要业务流程相同，但初始化、数据卷、provider、端口、版本或资源由本地承担。
- `BLOCKED_LOCAL`：当前主机架构、资源或本地启动条件无法完成 smoke。
- `UNSUPPORTED_API`：官方公开材料没有证明存在稳定、可由当前认证方式调用的目标 API。

答案中提到某个文档不算 citation。只有原始 response 中出现结构化
`reference`、`retriever_resources`、`quoteList`、`source`、`document`、
`chunk` 或 `context` 字段时，才记录 citation/source available。

## 2. 固定版本与本地运行材料

版本和 source URL 固定在
[`local-rag-platforms/versions.json`](/Users/muuushroom/gitrepos/moi-benchmark/rag/local-rag-platforms/versions.json)：

| system_id | pinned source | local port | 本轮目标 |
| --- | --- | ---: | --- |
| `dify_local` | Dify `1.16.1` | 8000 | Compose、Knowledge API、App API、retrieve |
| `fastgpt_local` | FastGPT `v4.15.6` | 3000 | PgVector Compose、dataset、searchTest、Chat |
| `ragflow_local` | RAGFlow `v0.26.4` | 9380 | Compose、parser/index、retrieval、OpenAI Chat |
| `maxkb_local` | MaxKB `v2.10.4-lts` | 8090 | Docker、应用 OpenAI Chat、API discovery |

运行目录统一为：

```text
.local-services/<system_id>/
  source/   # pinned vendor checkout, ignored
  compose/  # runtime-only compose/env references, ignored
  data/     # volumes, ignored
  logs/     # health, manifest and smoke artifacts, ignored
```

仓库中只提交部署 launcher、脱敏配置模板、版本 manifest、fixture 和本报告；
真实 key、密码、dataset/app ID、vendor checkout 和 raw response 不提交。

## 3. 官方流程与本地流程映射

### 3.1 Dify

官方材料：

- [Dify repository](https://github.com/langgenius/dify)
- [official Docker deployment](https://github.com/langgenius/dify/blob/main/docker/README.md)
- [Dify API reference](https://docs.dify.ai/api-reference)

| 流程步骤 | 云端/官网流程 | 本地实际流程 | 结论 |
| --- | --- | --- | --- |
| 服务/租户初始化 | Cloud 账号与托管 workspace | Community Edition Compose → `/install` → 本地 admin | `LOCAL_VARIANT` |
| 创建知识库 | `POST /datasets`，Knowledge/Dataset key | 同一路径，本地 key、本地 dataset ID | `SAME_CONTRACT` |
| 上传文档 | `POST /datasets/{id}/document/create-by-file` | 同一路径，文件进入本地 volume | `SAME_CONTRACT` |
| 解析/切分/索引 | Dify 托管 worker/provider | 本地 worker + 本地数据库/vector store | `LOCAL_VARIANT` |
| Embedding/index | Cloud/provider configuration | MatrixOrigin TaaS external provider | `LOCAL_VARIANT` |
| Native QA | `POST /chat-messages` | 本地 app key、同一路径 | `SAME_CONTRACT` |
| Native Workflow | `POST /workflows/run` | 本地发布的 Chatflow/Workflow | `SAME_CONTRACT` |
| Direct Retrieval | `POST /datasets/{id}/retrieve` | 本地 dataset API | `SAME_CONTRACT` |
| Citation/trace | `metadata.retriever_resources` 可用时记录 | 保存本地 response；没有字段则 N/A | `SAME_CONTRACT` |
| 模型出网 | Cloud-managed 或 provider | TaaS external，服务本体 local | `LOCAL_VARIANT` |
| 版本/资源 | 云端托管、不可由本项目固定 | tag `1.16.1`，Compose/volume 由本机承担 | `VERSION_DIVERGENCE` |

本地 runner 必须分别使用 `DIFY_DATASET_API_KEY` 与 `DIFY_API_KEY`，不能复用
Dify Cloud 的 key、app ID 或 dataset ID。只修改 `.env` 不是证据；需要同时
验证本地 ingest 和本地 `/chat-messages` 或 `/workflows/run`。

### 3.2 FastGPT

官方材料：

- [FastGPT repository](https://github.com/labring/FastGPT)
- [self-host Docker deployment](https://doc.fastgpt.io/en/self-host/deploy/docker)
- [dataset API](https://doc.fastgpt.io/en/openapi/dataset)
- [chat API](https://doc.fastgpt.io/en/openapi/chat)
- [model configuration](https://doc.fastgpt.io/en/self-host/config/model/intro)

| 流程步骤 | 云端/官网流程 | 本地实际流程 | 结论 |
| --- | --- | --- | --- |
| 服务/租户初始化 | Cloud account/team/app | MongoDB + PostgreSQL/PgVector + AIProxy + FastGPT Compose | `LOCAL_VARIANT` |
| 创建知识库 | `POST /api/core/dataset/create` | 同一路径，本地 dataset 与 key | `SAME_CONTRACT` |
| 上传文档 | `POST /api/core/dataset/collection/create/localFile` | 同一路径，等待 collection/index 状态 | `SAME_CONTRACT` |
| 解析/切分 | Cloud collection worker | 本地 worker/provider | `LOCAL_VARIANT` |
| Embedding/index | Index Model / managed provider | TaaS external Index Model | `LOCAL_VARIANT` |
| Native QA | `POST /api/v1/chat/completions` | 同一路径，`detail=true`、新 `chatId` | `SAME_CONTRACT` |
| Direct Retrieval | `POST /api/core/dataset/searchTest` | 同一路径，保存 `sourceName/sourceId/score` | `SAME_CONTRACT` |
| Citation/trace | detail response 的 `responseData.quoteList` 依版本而定 | 只保存原始 response 中实际出现的 quote | `VERSION_DIVERGENCE` |
| 模型出网 | Cloud/provider | TaaS external | `LOCAL_VARIANT` |
| 版本/资源 | Cloud 托管 | tag `v4.15.6`，优先 PgVector，16 GiB 串行运行 | `VERSION_DIVERGENCE` |

FastGPT 的 API contract 在版本相同时可直接复用，但官方 API 文档强调
实例自动生成的 Dev/System OpenAPI 可能随版本变化。完整 GHCR Compose 的
ARM64 需要逐镜像检查；组件级 Mongo/CPU 说明不等价于完整栈 ARM64 保证。

### 3.3 RAGFlow

官方材料：

- [RAGFlow repository](https://github.com/infiniflow/ragflow)
- [official HTTP API reference](https://ragflow.com.cn/docs/http_api_reference)
- [official Docker guide](https://github.com/infiniflow/ragflow/blob/main/docker/README.md)

| 流程步骤 | 云端/官网流程 | 本地实际流程 | 结论 |
| --- | --- | --- | --- |
| 服务/租户初始化 | Cloud assistant/workspace | 官方 Compose + Elasticsearch/依赖 + 本地 Web | `LOCAL_VARIANT` |
| 创建 Dataset | `POST /api/v1/datasets` | 同一路径，本地 dataset | `SAME_CONTRACT` |
| 上传文档 | `POST /api/v1/datasets/{id}/documents` | 同一路径，文件在本机 | `SAME_CONTRACT` |
| 解析/切分 | DeepDoc/parser/OCR pipeline | 本地 parser/DeepDoc/OCR，单独记录状态 | `LOCAL_VARIANT` |
| Embedding/index | Cloud/provider | TaaS external + 本地 Elasticsearch/index | `LOCAL_VARIANT` |
| Native QA | `POST /api/v1/openai/{chat_id}/chat/completions` | 同一路径，`extra_body.reference=true` | `SAME_CONTRACT` |
| Direct Retrieval | `POST /api/v1/retrieval` | 同一路径，保存真实 chunks | `SAME_CONTRACT` |
| Citation/trace | `reference` / `reference_metadata` | 只认原始 response 字段 | `SAME_CONTRACT` |
| 模型出网 | Cloud/provider | TaaS external | `LOCAL_VARIANT` |
| 版本/资源 | Cloud 托管 | tag `v0.26.4`；官方镜像偏 x86；16 GiB 已接近资源下限 | `BLOCKED_LOCAL` |

RAGFlow 是本轮最大本地化风险。官方仓库说明预构建镜像主要面向 x86、
没有可直接使用的 ARM64 镜像；本机只能尝试 Colima amd64 emulation 或本机
构建。若无法启动或 parser/Elasticsearch/Embedding 在 16 GiB 下无法完成
三文档 smoke，必须保留镜像 manifest、启动日志和 `BLOCKED_LOCAL`，不能用
远程 x86 结果替代。

RAGFlow parser/OCR/index 状态与 retrieval miss 必须分开归因：文档 `run`
失败是 ingest/index error，不是 retrieval recall=0。

### 3.4 MaxKB

官方材料：

- [MaxKB repository](https://github.com/1Panel-dev/maxkb)
- [dataset documentation](https://maxkb.cn/docs/v2/user_manual/dataset/dataset/)
- [Chat-to-API / OpenAI-compatible API](https://maxkb.cn/docs/v2/user_manual/chat_to_API/)

| 流程步骤 | 云端/官网流程 | 本地实际流程 | 结论 |
| --- | --- | --- | --- |
| 服务/租户初始化 | 官方入口/应用控制面 | 官方 image，`8090:8080`，本地 admin 初始化 | `LOCAL_VARIANT` |
| 创建知识库/应用 | UI/应用知识库关联 | UI 完成；实例 API 文档需 discovery | `LOCAL_VARIANT` |
| 上传文档 | UI/版本相关 API | 当前初版不把内部 route 当公共 contract | `UNSUPPORTED_API` |
| 解析/切分/Embedding | 应用后台配置 | 本地后台 + TaaS external | `LOCAL_VARIANT` |
| Native QA | 应用 OpenAI-compatible endpoint | 显式传入 local app base/path/key | `SAME_CONTRACT` |
| Direct Retrieval | 本次官方公开材料未形成稳定 API | 先探测实例 OpenAPI/Swagger；没有认证 endpoint 就 unsupported | `UNSUPPORTED_API` |
| Citation/trace | UI/工作流可显示来源，但标准 Chat schema 未承诺 evidence 字段 | 只认 raw response 的结构化来源 | `UNSUPPORTED_API` |
| 模型出网 | Cloud/provider | TaaS external | `LOCAL_VARIANT` |
| 版本/资源 | 云端托管 | tag `v2.10.4-lts`，本地 volume/端口由本机承担 | `VERSION_DIVERGENCE` |

MaxKB 的初版 adapter 会记录 API discovery 和 Native QA；只有运行实例的
OpenAPI/Swagger 证明有 API-key 可访问的 dataset ingest/retrieval contract，
才把相应状态改为 success。不能用源码内部 URL 或 UI 行为代替公开 API，也不
能从答案文本推断 citation。

## 4. 统一 smoke 实现与 artifact

统一入口是现有 `dify-rag-eval` package 的：

```bash
python3 -m dify_rag_eval local-smoke \
  --system <dify_local|fastgpt_local|ragflow_local|maxkb_local> \
  --base-url <local-url> \
  --output .local-services/<system_id>/logs/smoke \
  --source local-rag-platforms/fixtures/smoke
```

实现位置：

- `dify-rag-eval/src/dify_rag_eval/local_smoke.py`：HTTP、multipart、四个 adapter、状态归因、脱敏 artifact。
- `dify-rag-eval/src/dify_rag_eval/cli.py`：`local-smoke` 命令。
- `local-rag-platforms/prepare_local_services.py`：preflight、pinned source preparation、compose/image manifest。
- `local-rag-platforms/fixtures/smoke/`：相同三文档、answerable/multi-document/refusal question 与固定 retrieval probe。

每个 smoke JSON 至少包含：

```json
{
  "system_id": "fastgpt_local",
  "deployment_mode": "self_hosted",
  "platform": "linux/arm64",
  "version": "...",
  "image_digest": null,
  "model_egress": "external",
  "service_status": "ready",
  "ingest_status": "ready|error|unsupported",
  "native_status": "success|error|unsupported",
  "retrieval_status": "success|error|unsupported",
  "blocked_reason": null,
  "artifacts": []
}
```

请求和响应按操作拆分保存，headers/body 中的 key、Bearer、password、cookie
会脱敏；文件只保存 filename/size/SHA-256。每个 artifact 有 SHA-256 sidecar。
`chatId`、`conversation_id`、Dify user 等会话标识按题隔离，避免跨题污染。

## 5. 当前部署结论

### 已完成

- Docker Compose plugin 已通过 Homebrew 安装并接入 Docker CLI，版本 5.4.0。
- 本机 preflight、Colima platform、16 GiB、MOI 端口和运行目录已记录。
- 版本 tag、官方 source URL、端口和 provider egress manifest 已固定。
- Dify `1.16.1` source 已准备到 `.local-services/dify_local/source/dify`，commit 为 `6f8ed69ee15f9a2e7189ca066275e973d091d1e9`。
- 统一 local smoke adapter、脱敏 raw artifact、三文档 fixture 和单元测试已实现。
- 官方流程证据单独归档在 [`local-rag-official-flow-evidence-2026-08-05.md`](/Users/muuushroom/gitrepos/moi-benchmark/rag/plans/research/local-rag-official-flow-evidence-2026-08-05.md)。

### 运行结果记录规则

下表只在对应本地运行结束后填入 `ready/error/unsupported` 与 artifact 路径；
不要把 Cloud runner 的成功结果复制到 local system_id：

| system_id | service | ingest | native | retrieval | local result |
| --- | --- | --- | --- | --- | --- |
| `dify_local` | pending local Compose smoke | pending | pending | pending | use `.local-services/dify_local/logs/` |
| `fastgpt_local` | pending local Compose smoke | pending | pending | pending | use `.local-services/fastgpt_local/logs/` |
| `ragflow_local` | pending architecture/emulation gate | pending | pending | pending | use `.local-services/ragflow_local/logs/` |
| `maxkb_local` | pending local image smoke | unsupported until API discovery | pending | unsupported until API discovery | use `.local-services/maxkb_local/logs/` |

这里的 `pending` 只表示本报告生成时的执行中间态，不是允许用于最终 benchmark
排名的状态。最终交付前必须用真实 `smoke-result.json` 替换它；无法部署的平台
必须写出 `BLOCKED_LOCAL`、`BLOCKED_LOCAL_ARCH` 或 `BLOCKED_LOCAL_RESOURCES`
的具体日志证据。

## 6. 与既有 MOI / Dify Cloud 的关系

- MOI 继续是已完成的本地 pipeline，parser `8080` 和 MatrixOne `6001/9876`
  保留，不与竞品共用数据目录或结果 ID。
- 既有 Dify Cloud 结果继续作为远端参考；本地 Dify 使用独立的
  `system_id=dify_local`、local app key、local dataset key、local IDs。
- 本轮 smoke 通过后再接 Stage 1 attempt ledger；当前不启动正式的
  `20 questions × 2 repeats`，也不把不同版本、不同模型/provider 或不同
  corpus 的结果合并为总排名。
