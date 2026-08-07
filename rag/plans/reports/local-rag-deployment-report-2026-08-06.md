# 本地 RAG 竞品部署报告

> 执行日期：2026-08-05—2026-08-06  
> 执行主机：macOS / Apple Silicon / 16 GiB，Colima Linux/arm64  
> 范围：Dify、FastGPT、RAGFlow、MaxKB 本地部署初版；不包含 Stage 1 效果排名

## 1. 执行摘要

本轮在不影响既有 MOI 本地 pipeline 的前提下，对四套 RAG 竞品进行了服务
启动、模型配置、三文档 ingest、索引状态、Native QA 和 Direct Retrieval 验证。
服务本体、数据库、parser/index 均要求在当前 Colima 主机运行；LLM 与
Embedding 允许使用 MatrixOrigin TaaS，因此统一记录
`model_egress=external`，不称为 fully offline。

最终结果如下：

| system_id | 部署结论 | 服务 | Ingest | Native QA | Direct Retrieval |
| --- | --- | --- | --- | --- | --- |
| `dify_local` | `LOCAL_VARIANT`，部署成功 | ready | 3/3 ready；另完成 44/44 readiness | success | success，5 contexts |
| `fastgpt_local` | `BLOCKED_LOCAL`，部署部分成功 | ready | 3/3 ready | error，工作流请求 timeout | success，3 hits |
| `maxkb_local` | `LOCAL_VARIANT`，部署部分成功 | ready | 3/3 已上传；状态 `nnn2` 语义未确认 | error；HTTP 200 但未正确消费问题 | `UNSUPPORTED_API` |
| `ragflow_local` | `BLOCKED_LOCAL` | blocked | 未执行 | 未执行 | 未执行 |

Dify 是本轮唯一通过完整最小 smoke 并进入 44 文档 readiness 的竞品。FastGPT
与 MaxKB 的服务和部分 RAG 链路已经可用，但尚不能作为完整 pipeline pass。
RAGFlow 因当前主机低于官方资源门槛未强行启动，也未使用远程 x86 主机替代。

## 2. 主机和隔离策略

| 项目 | 实际值 |
| --- | --- |
| Host | macOS 15.7 / Apple Silicon / arm64 |
| Docker runtime | Colima，server platform `linux/aarch64` |
| Colima resource | 2 CPU、约 12 GiB 可用内存、无 swap |
| Docker disk | 100 GiB 数据盘；执行时约剩 12–13 GiB |
| Docker | client 29.6.2 / server 29.5.2 |
| Docker Compose | 5.4.0 |
| 外部模型 | MatrixOrigin TaaS OpenAI-compatible endpoint |

竞品服务始终串行启动，避免 16 GiB 主机出现内存竞争。既有 MOI 服务在整个
执行过程中保持运行：

- `moi-openxml-parser`：`127.0.0.1:8080`
- MatrixOne：`6001`、`9876`

竞品端口分别为 Dify `8010`、FastGPT `3000`、RAGFlow `9380`、MaxKB
`8090`。Dify 原计划使用 8000，但该端口已有无关 uvicorn 服务，因此调整为
8010。所有运行数据、凭据、vendor checkout 和 raw response 均保存在被 Git
忽略的 `.local-services/<system_id>/`；可提交文件只包含 launcher、脱敏模板、
版本信息、测试和报告。

## 3. 验证方法

每个可启动平台按相同阶段验证：

1. 检查 source tag、commit、image digest 和 architecture manifest；
2. 启动本地 Web/API、数据库和索引依赖；
3. 创建本地管理员、知识库和应用，配置 TaaS LLM/Embedding；
4. 上传统一三文档 fixture 并等待索引状态；
5. 调用产品自身 Native QA API；
6. 调用公开 Direct Retrieval API；若不存在则记为 `UNSUPPORTED_API`；
7. 保存脱敏结果、SHA-256、版本和阻塞原因；
8. 停止竞品服务但保留 volume/data，再切换下一个平台。

统一 fixture 位于 `local-rag-platforms/fixtures/smoke/`。只有完整最小 smoke
成功后才执行 44 文档 readiness；本轮没有启动正式的
`20 questions × 2 repeats`。

## 4. 分平台部署结果

### 4.1 Dify Community Edition 1.16.1

部署形态：官方 Community Edition Docker Compose，原生 `linux/arm64`，本地
端口 8010。source commit 为
`6f8ed69ee15f9a2e7189ca066275e973d091d1e9`。

本轮完成：

- 初始化独立本地管理员、Dataset key、App key 和 app-linked dataset；
- 未复用 Dify Cloud 的 key、app ID、dataset ID 或执行结果；
- 将仓库内 MatrixOrigin TaaS provider 升级为 `0.0.3`；
- provider 同时暴露 `deepseek-v4-flash` LLM 与 `bge-m3` embedding；
- 3/3 fixture ready；`/datasets/{id}/retrieve` 返回 5 个 context；
- `/chat-messages` 返回非空答案；
- 另创建独立 44 文档 dataset，44/44 上传并进入 ready。

本轮只实测了 Chat App API，没有创建并执行 `/workflows/run`，因此不宣称
Workflow 已验证。Compose 重启时 API 会在 migration 阶段短暂返回 502，等待
`/console/api/setup` 返回 `finished` 后即可恢复，无需重建数据卷。

关键 evidence：

- `.local-services/dify_local/logs/smoke-2026-08-06/smoke-result.json`
- `.local-services/dify_local/logs/readiness-44docs-2026-08-06/smoke-result.json`
- `.local-services/dify_local/logs/deployment-manifest.json`

部署说明见
[`local-rag-platforms/dify_local/README.md`](/Users/muuushroom/gitrepos/moi-benchmark/rag/local-rag-platforms/dify_local/README.md)。

### 4.2 FastGPT v4.15.6

部署形态：官方 PgVector Compose，source 固定为 v4.15.6，运行 Compose 中应用
image 为 v4.15.4。全栈镜像均提供 `linux/arm64` manifest；FastGPT 应用 image
digest 为
`sha256:5af59670b73cbc3aa8510e68f58861b8be8c7670fc3b9704452dc71e9364a143`。

本轮完成：

- MongoDB、PostgreSQL/PgVector、AIProxy、Redis、MinIO、plugin、sandbox 和
  FastGPT Web/API 全部启动；
- 创建 MatrixOrigin TaaS AIProxy channel；
- `qwen3.6-flash` 与 `bge-m3` provider/model probe 成功；
- 创建 dataset/app/API key，3/3 collection ready；
- `POST /api/core/dataset/searchTest` 返回 3 条真实命中；
- Native `POST /api/v1/chat/completions` 启动工作流后持续没有 HTTP response。

最终阻塞原因固定为
`NATIVE_QA_TIMEOUT_NO_RESPONSE_SINCE_2026-08-06T03:44:03Z`。该问题没有被
检索成功掩盖，FastGPT 因此仍是 partial。runner 已补充 timeout/error 自动写
统一 artifact 的失败路径，避免后续再次出现失败但没有汇总 JSON。

关键 evidence：

- `.local-services/fastgpt_local/logs/smoke-partial-20260806-114747/smoke-result.json`
- `.local-services/fastgpt_local/logs/deployment-manifest.json`
- `.local-services/fastgpt_local/compose/docker-compose.pg.yml`

部署和恢复说明见
[`local-rag-platforms/fastgpt_local/README.md`](/Users/muuushroom/gitrepos/moi-benchmark/rag/local-rag-platforms/fastgpt_local/README.md)。

### 4.3 MaxKB v2.10.4-lts

部署形态：官方 `1panel/maxkb:v2.10.4-lts` image，原生 `linux/arm64`，映射
`127.0.0.1:8090:8080`。OCI digest 为
`sha256:20205df1ba6eef4e4276e48c892038de72cf8618d1e1c1d50eb1f535d45dfedc`。

本轮完成：

- 本地管理员 API 初始化；
- 创建 TaaS `deepseek-v4-flash` 与 `bge-m3` 模型，两者连通性成功；
- 创建知识库、简易应用并发布，生成本地 application key；
- 三份 fixture 均上传，落盘 evidence 中状态为 `nnn2`；
- admin hit-test 返回 3 条真实来源、内容和相似度；
- 应用 OpenAI-compatible endpoint 返回 HTTP 200 和 OpenAI schema。

限制：当前版本没有验证到 application API key 可访问的稳定公共 Direct
Retrieval endpoint，admin hit-test 只能作为内部诊断，统一结论保持
`UNSUPPORTED_API`。Native API 本轮返回的回答没有正确消费问题，故记为
error/partial。`nnn2` 的公开状态语义也未确认，因此不能宣称索引 ready。

关键 evidence：

- `.local-services/maxkb_local/logs/smoke-partial-2026-08-06/smoke-result.json`
- `.local-services/maxkb_local/discovery/hit-test-summary.json`
- `.local-services/maxkb_local/logs/deployment-manifest.json`

部署说明见
[`local-rag-platforms/maxkb_local/README.md`](/Users/muuushroom/gitrepos/moi-benchmark/rag/local-rag-platforms/maxkb_local/README.md)。

### 4.4 RAGFlow v0.26.4

RAGFlow 主镜像只有 `linux/amd64`，本机已具备 qemu-x86_64 emulation，因此
阻塞类型不是 `BLOCKED_LOCAL_ARCH`。但该版本官方部署门槛为至少 4 CPU、
16 GB RAM、50 GB 可用磁盘；当前 Colima 为 2 CPU、约 12 GiB 内存和约
12 GiB Docker 可用空间，三项均不满足。

preflight 返回 `BLOCKED_LOCAL_RESOURCES`。为避免 Elasticsearch/RAGFlow
完整栈引发 OOM、磁盘 watermark 或破坏仍在运行的 MOI，本轮未执行服务启动、
parser/index、Native QA 或 Retrieval。报告中涉及的 RAGFlow API path 只来自
官方 contract，不是本机实测。

关键 evidence：

- `.local-services/ragflow_local/logs/preflight-20260806T031839Z/preflight.json`
- `.local-services/ragflow_local/logs/smoke-resources-blocked-2026-08-06-v2/smoke-result.json`
- `.local-services/ragflow_local/logs/deployment-manifest.json`

资源门禁和受控 Compose 见
[`local-rag-platforms/ragflow_local/README.md`](/Users/muuushroom/gitrepos/moi-benchmark/rag/local-rag-platforms/ragflow_local/README.md)。

## 5. 验收和测试结果

| 验证项 | 结果 |
| --- | --- |
| `dify-rag-eval` unittest | 16 passed |
| MatrixOrigin Dify plugin pytest | 6 passed；2 个第三方 warning |
| FastGPT contract/failure-path unittest | 2 passed |
| Python compile / JSON parse | passed |
| MaxKB/RAGFlow shell syntax | passed |
| RAGFlow Compose config | passed |
| `git diff --check` | passed |
| 可提交文件 credential value scan | 29 files / 8 credential values；0 match |

最终检查时只有 MOI parser 与 MatrixOne 容器运行。Dify、FastGPT、MaxKB 均已
停止但保留数据；RAGFlow 没有启动。

## 6. 风险和后续工作

1. 优先诊断 FastGPT app workflow 的 Native QA timeout；成功后再执行其 44
   文档 readiness。
2. 核对 MaxKB `nnn2` 的版本状态语义，修复 Native 请求消费问题；若公开
   Direct Retrieval API 仍不存在，继续保持 `UNSUPPORTED_API`。
3. 只有当前允许主机的 Colima 达到至少 4 CPU、16 GiB 和 50 GiB 可用空间后，
   才恢复 RAGFlow 完整 smoke。
4. 各平台最小 smoke 全部通过后，再接统一 attempt ledger 和 Stage 1
   `20 questions × 2 repeats`。
5. 在同模型、同 corpus、同 condition 约束满足之前，不输出跨平台效果总排名。

版本和当前状态的机器可读入口为
[`local-rag-platforms/versions.json`](/Users/muuushroom/gitrepos/moi-benchmark/rag/local-rag-platforms/versions.json)，
详细 local/cloud 合同映射见
[`local-rag-platform-comparison-2026-08-05.md`](/Users/muuushroom/gitrepos/moi-benchmark/rag/reports/local-rag-platform-comparison-2026-08-05.md)。
