# 本地 RAG 竞品部署与云端流程对比

> 研究日期：2026-08-05；初版执行完成：2026-08-06
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
| `dify_local` | Dify `1.16.1` | 8010 | Compose、Knowledge API、App API、retrieve |
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
| Native Workflow | `POST /workflows/run` | 本轮未创建/发布 Workflow，未做本地调用验证 | `LOCAL_VARIANT` |
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
| Native QA | `POST /api/v1/chat/completions` | 同一路径，`detail=true`、新 `chatId`；本轮自 2026-08-06T03:44:03Z 起无 HTTP 响应 | `BLOCKED_LOCAL` |
| Direct Retrieval | `POST /api/core/dataset/searchTest` | 同一路径，保存 `sourceName/sourceId/score` | `SAME_CONTRACT` |
| Citation/trace | detail response 的 `responseData.quoteList` 依版本而定 | 只保存原始 response 中实际出现的 quote | `VERSION_DIVERGENCE` |
| 模型出网 | Cloud/provider | TaaS external | `LOCAL_VARIANT` |
| 版本/资源 | Cloud 托管 | tag `v4.15.6`，优先 PgVector，16 GiB 串行运行 | `VERSION_DIVERGENCE` |

FastGPT 的 API contract 在版本相同时可直接复用，但官方 API 文档强调
实例自动生成的 Dev/System OpenAPI 可能随版本变化。完整 GHCR Compose 的
ARM64 需要逐镜像检查；组件级 Mongo/CPU 说明不等价于完整栈 ARM64 保证。
本轮 provider 与两个模型测试成功，三文档 collection 全部 ready，`searchTest`
返回 3 hits；native QA 超时，精确阻塞为
`NATIVE_QA_TIMEOUT_NO_RESPONSE_SINCE_2026-08-06T03:44:03Z`。脱敏证据位于
`.local-services/fastgpt_local/logs/smoke-partial-20260806-114747/smoke-result.json`。

### 3.3 RAGFlow

官方材料：

- [RAGFlow repository](https://github.com/infiniflow/ragflow)
- [official HTTP API reference](https://ragflow.com.cn/docs/http_api_reference)
- [official Docker guide](https://github.com/infiniflow/ragflow/blob/main/docker/README.md)

| 流程步骤 | 云端/官网流程 | 本地实际流程 | 结论 |
| --- | --- | --- | --- |
| 服务/租户初始化 | Cloud assistant/workspace | 因资源 gate 未启动完整本地服务 | `BLOCKED_LOCAL` |
| 创建 Dataset | `POST /api/v1/datasets` | 仅按官方文档准备 contract，未在本地实例调用 | `BLOCKED_LOCAL` |
| 上传文档 | `POST /api/v1/datasets/{id}/documents` | 仅按官方文档准备 contract，未在本地实例调用 | `BLOCKED_LOCAL` |
| 解析/切分 | DeepDoc/parser/OCR pipeline | 本地 parser/DeepDoc/OCR 未启动 | `BLOCKED_LOCAL` |
| Embedding/index | Cloud/provider | 计划使用 TaaS + 本地 Elasticsearch，未执行 | `BLOCKED_LOCAL` |
| Native QA | `POST /api/v1/openai/{chat_id}/chat/completions` | 官方 contract 已记录，本地未调用 | `BLOCKED_LOCAL` |
| Direct Retrieval | `POST /api/v1/retrieval` | 官方 contract 已记录，本地未调用 | `BLOCKED_LOCAL` |
| Citation/trace | `reference` / `reference_metadata` | 本地无 response，不宣称 citation 可用 | `BLOCKED_LOCAL` |
| 模型出网 | Cloud/provider | 计划使用 TaaS external，未执行 | `BLOCKED_LOCAL` |
| 版本/资源 | Cloud 托管 | tag `v0.26.4`；官方镜像偏 x86；16 GiB 已接近资源下限 | `BLOCKED_LOCAL` |

RAGFlow 是本轮唯一未启动服务的系统。v0.26.4 主镜像只有 `linux/amd64`，
本机具备 qemu-x86_64 emulation；但当前 Colima 只有 2 CPU、12 GiB 可用内存和
约 12 GiB Docker 剩余空间，低于该版本官方 4 CPU、16 GB、50 GB 的启动门槛。
因此静态 preflight 结论为 `BLOCKED_LOCAL_RESOURCES`，统一映射为
`BLOCKED_LOCAL`。为避免破坏仍在运行的 MOI 服务，本轮没有强行启动完整栈，
也没有用远程 x86 主机替代。证据位于
`.local-services/ragflow_local/logs/preflight-20260806T031839Z/` 和
`.local-services/ragflow_local/logs/smoke-resources-blocked-2026-08-06-v2/`。

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
| Native QA | 应用 OpenAI-compatible endpoint | 本地 endpoint 返回 OpenAI schema/HTTP 200，但本轮未正确消费问题 | `VERSION_DIVERGENCE` |
| Direct Retrieval | 本次官方公开材料未形成稳定 API | 先探测实例 OpenAPI/Swagger；没有认证 endpoint 就 unsupported | `UNSUPPORTED_API` |
| Citation/trace | UI/工作流可显示来源，但标准 Chat schema 未承诺 evidence 字段 | 只认 raw response 的结构化来源 | `UNSUPPORTED_API` |
| 模型出网 | Cloud/provider | TaaS external | `LOCAL_VARIANT` |
| 版本/资源 | 云端托管 | tag `v2.10.4-lts`，本地 volume/端口由本机承担 | `VERSION_DIVERGENCE` |

MaxKB 已在原生 arm64 image 上启动并完成管理员、TaaS LLM/Embedding、知识库
与应用初始化。三份文档均上传，但落盘 evidence 中的 `nnn2` 状态语义未在稳定公共
contract 中确认，因此 ingest 保守记为 partial。管理员 hit-test 返回三条真实
命中，只作为诊断证据；当前版本没有验证到 API-key 可访问的稳定公开 retrieval
API，故 Direct Retrieval 为 `UNSUPPORTED_API`。不能用源码内部 URL、UI 行为
或答案文本推断公共 contract/citation。

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
- Dify `1.16.1` 已完成本地管理员、独立 Dataset/App key、TaaS provider、
  三文档索引、Direct Retrieval 与 Native QA；未复用 Dify Cloud key 或 ID。
- Dify 使用本地安装的 MatrixOrigin TaaS provider `0.0.3`：
  `deepseek-v4-flash` 提供 chat，`bge-m3` 提供 embedding；服务本体与向量库
  都在 Colima，本轮仅模型调用出网。
- Dify 另完成 44 文档 readiness：44/44 上传并进入 ready，artifact 位于
  `.local-services/dify_local/logs/readiness-44docs-2026-08-06/`；这不是
  Stage 1 正式执行。
- FastGPT 本地 ARM64 全栈、TaaS provider、3/3 ingest 与 Direct Retrieval
  已完成；Native QA 记为本机 timeout，未提升为完整 pipeline pass。
- MaxKB 本地 ARM64 服务与 provider 已完成，pipeline 因文档状态语义、Native
  回答和公共 retrieval API 三项限制记为 partial。
- RAGFlow 因当前 Colima 资源低于官方门槛记为 `BLOCKED_LOCAL`；镜像与
  emulation 证据已保存，未启动完整服务。

### 初版实际运行结果

| system_id | service | ingest | native | retrieval | local result |
| --- | --- | --- | --- | --- | --- |
| `dify_local` | ready | ready（3/3；另完成 44/44 readiness） | success | success（5 contexts） | `.local-services/dify_local/logs/smoke-2026-08-06/`；`.local-services/dify_local/logs/readiness-44docs-2026-08-06/` |
| `fastgpt_local` | ready | ready（3/3） | error（timeout） | success（3 hits） | `.local-services/fastgpt_local/logs/smoke-partial-20260806-114747/smoke-result.json` |
| `ragflow_local` | blocked | unsupported | unsupported | unsupported | `BLOCKED_LOCAL_RESOURCES`；2 CPU/12 GiB/12 GiB free，低于官方 4 CPU/16 GB/50 GB gate |
| `maxkb_local` | ready | partial（3/3 状态 `nnn2`；统一 schema 为 error） | partial（HTTP 200，但未消费问题；统一 schema 为 error） | unsupported（admin hit-test 仅作诊断） | `.local-services/maxkb_local/logs/smoke-partial-2026-08-06/smoke-result.json` |

该矩阵是部署初版验收结果，不是效果排名。只有 Dify 通过完整最小 smoke，因而
只有 Dify 执行了 44 文档 readiness。FastGPT、MaxKB 仍是 partial，RAGFlow 是
`BLOCKED_LOCAL`；它们不会被云端结果替换或伪装为本地 pass。

## 6. 与既有 MOI / Dify Cloud 的关系

- MOI 继续是已完成的本地 pipeline，parser `8080` 和 MatrixOne `6001/9876`
  保留，不与竞品共用数据目录或结果 ID。
- 既有 Dify Cloud 结果继续作为远端参考；本地 Dify 使用独立的
  `system_id=dify_local`、local app key、local dataset key、local IDs。
- 本轮 smoke 通过后再接 Stage 1 attempt ledger；当前不启动正式的
  `20 questions × 2 repeats`，也不把不同版本、不同模型/provider 或不同
  corpus 的结果合并为总排名。
