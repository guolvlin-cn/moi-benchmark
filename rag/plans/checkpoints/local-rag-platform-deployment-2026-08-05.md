# 本地 RAG 竞品部署初版断点

更新时间：2026-08-05（Asia/Shanghai）
状态：**已暂停，镜像准备已完成，等待恢复**

## 1. 任务范围

本次任务是在现有本地 MOI RAG 基础上，为 `dify_local`、`fastgpt_local`、`ragflow_local`、`maxkb_local` 建立本地部署初版，并核对其本地 API 流程与云端/官网流程。当前只完成了部署探测、服务级 smoke 和阻塞点归档，尚未进入完整 Stage 1。

模型与 Embedding 仍使用 MatrixOrigin TaaS 的 OpenAI-compatible endpoint；因此服务本体是本地运行，但 `model_egress=external`，不是 fully-offline 部署。

## 2. 主机与运行边界

- 主机：macOS / Apple Silicon，16 GiB。
- 容器运行时：Colima Linux/arm64（Docker Server platform 为 `linux/aarch64`）。
- Docker Compose：Docker Compose 5.4.0，已补齐 Compose v2。
- Colima Docker 数据盘已从约 60 GiB 扩容到 100 GiB；本次镜像拉取后约剩 13 GiB。
- 竞品服务按串行策略运行，避免内存和端口竞争。
- MOI 现有服务保持运行：
  - `moi-openxml-parser`：`127.0.0.1:8080`
  - `matrixone`：`6001`、`9876`
- 竞品计划端口：Dify `8000`（实际因端口被占用改为 `8010`）、FastGPT `3000`、RAGFlow `9380`、MaxKB `8090`。
- `.local-services/` 已加入 `.gitignore`，运行数据、密钥和 raw artifact 不提交 Git。

## 3. 当前状态

| 系统 | 当前结论 | 已完成 | 暂停时状态 |
|---|---|---|---|
| `dify_local` | `LOCAL_VARIANT`，初始服务可用但未初始化 | 官方 Dify 1.16.1 Compose；镜像已核对为 arm64；Nginx/API 在 `8010` 可达；服务级 smoke 通过 | 已停止；卷保留。尚未访问 `/install` 创建本地管理员、Dataset/App API key，也未配置 TaaS provider。后续保留卷重启观察曾遇到迁移/资源阻塞，事件已归档 |
| `fastgpt_local` | `LOCAL_VARIANT`，服务已启动但 pipeline 未配置 | 官方 FastGPT v4.15.6 源码；官方 Compose 使用 v4.15.4 应用镜像；运行时 Compose 增加了本地必需的 `FE_DOMAIN`、`FILE_DOMAIN`、`AGENT_ENGINE`；全栈 ARM64 容器曾成功启动并健康 | 已停止；卷保留。服务 smoke 为 ready，但缺少本地 `FASTGPT_API_KEY`/`appId`，尚未建库、上传、索引、Native QA 或 Direct Retrieval |
| `ragflow_local` | `IMAGE_READY`，服务仍待架构/资源验证 | 官方 v0.26.4 主镜像及配置的 CPU/Elasticsearch Compose 依赖已下载；主镜像为 `linux/amd64`，后续需 emulation | 未启动。没有改用远程主机；此前的拉取阻塞结果已被本次成功拉取事件更新 |
| `maxkb_local` | `IMAGE_READY`，服务尚未启动 | `1panel/maxkb:v2.10.4-lts` 已下载为 `linux/arm64`；API smoke adapter 已准备 | 未启动；后续可直接使用本地镜像启动 `8090` |

### 已保存的关键 smoke 结果

- Dify：`smoke-local-uninitialized-v2` 中 `service_status=ready`，`ingest/native/retrieval=unsupported`，原因是 `MISSING_DATASET_KEY`；同时记录了本地 Embedding provider 未认证和本地 App key 缺失。
- FastGPT：`smoke-local-unconfigured-v3` 中 `service_status=ready`，`ingest/native/retrieval=unsupported`，原因是 `MISSING_APP_ID`；没有把未认证的 400/403 误判为服务不可达。
- RAGFlow：`smoke-architecture-blocked` 是镜像完成前的历史 smoke；当前镜像已就绪，服务启动验证仍待做。
- MaxKB：`smoke-image-pull-blocked` 是镜像完成前的历史 smoke；当前 arm64 镜像已就绪，服务启动验证仍待做。

## 4. 已落地的实现材料

- `local-rag-platforms/versions.json`：固定版本、源码 commit、Compose 定位、端口、平台策略和状态。
- `local-rag-platforms/prepare_local_services.py`：环境 preflight、源码准备、部署 manifest、镜像 manifest、事件记录。
- `local-rag-platforms/fixtures/smoke/`：3 个最小 fixture 文档、问题集和 retrieval probe。
- `dify-rag-eval/src/dify_rag_eval/local_smoke.py`：统一本地 smoke context、请求/响应脱敏、artifact hash、Dify/FastGPT/RAGFlow/MaxKB adapter。
- `dify-rag-eval/src/dify_rag_eval/cli.py`：`local-smoke` 命令和本地 key/blocked reason 参数。
- `dify-rag-eval/tests/test_local_smoke.py`：脱敏和 MaxKB API 探测测试。
- 各平台部署说明：`local-rag-platforms/{dify_local,fastgpt_local,ragflow_local,maxkb_local}/README.md`。
- 官方文档/流程证据备忘：`plans/research/local-rag-official-flow-evidence-2026-08-05.md`。

## 5. 运行 artifact 索引

以下路径均在本仓库根目录 `/Users/muuushroom/gitrepos/moi-benchmark/rag` 下：

- `.local-services/environment-manifest.json`
- `.local-services/dify_local/logs/deployment-manifest.json`
- `.local-services/dify_local/logs/deployment-events.jsonl`
- `.local-services/dify_local/logs/smoke-local-uninitialized-v2/smoke-result.json`
- `.local-services/fastgpt_local/compose/docker-compose.pg.yml`（本地运行时修正版）
- `.local-services/fastgpt_local/logs/deployment-manifest.json`
- `.local-services/fastgpt_local/logs/deployment-events.jsonl`
- `.local-services/fastgpt_local/logs/smoke-local-unconfigured-v3/smoke-result.json`
- `.local-services/fastgpt_local/logs/image-manifest-*`
- `.local-services/ragflow_local/logs/image-manifest-ragflow-v0.26.4.json`
- `.local-services/ragflow_local/logs/deployment-events.jsonl`
- `.local-services/ragflow_local/logs/smoke-architecture-blocked/smoke-result.json`
- `.local-services/maxkb_local/logs/image-manifest-maxkb-v2.10.4-lts.json`
- `.local-services/maxkb_local/logs/deployment-events.jsonl`
- `.local-services/maxkb_local/logs/smoke-image-pull-blocked/smoke-result.json`
- `.local-services/ragflow_local/logs/deployment-events.jsonl` 已追加成功的 `image-pull` 事件。
- `.local-services/maxkb_local/logs/deployment-events.jsonl` 已追加成功的 `image-pull` 事件。

## 6. 恢复顺序

恢复任务时按以下顺序继续：

1. 先确认 MOI parser/MatrixOne 仍可用，并保持竞品串行启动。
2. Dify：启动官方 Compose，访问 `http://127.0.0.1:8010/install` 完成本地管理员初始化；只设置 `DIFY_LOCAL_DATASET_API_KEY`、`DIFY_LOCAL_API_KEY` 和 TaaS provider，然后重新执行本地 smoke，确认 ingest 与 run 都没有回到 Dify Cloud。
3. FastGPT：使用 `.local-services/fastgpt_local/compose/docker-compose.pg.yml`，不要直接覆盖它；完成本地账户/app/API key 和 TaaS provider 配置，再执行 3 文档建库、上传、ready、`searchTest`、Native QA。
4. MaxKB：直接使用已下载的 arm64 镜像启动 `8090`；启动后通过实例 OpenAPI discovery 确认 native API，并把 Direct Retrieval 标为 `unsupported`，除非发现稳定的公开 API-key 合约。
5. RAGFlow：使用已下载的 amd64 镜像和 Compose 依赖，在当前 Colima 中尝试 emulation；不使用远程主机替代。若服务仍因架构或资源失败，保留 `BLOCKED_LOCAL_ARCH`/`BLOCKED_LOCAL_RESOURCES`。
6. 四个平台的最小 smoke 可重复后，再补齐 44 文档 readiness、统一 attempt ledger 和 Stage 1（20 questions × 2 repeats）。
7. 最后更新 `reports/local-rag-platform-comparison-2026-08-05.md`，将其中的 pending 行替换为实际结果，并完成测试与 diff 检查。

## 7. 尚未完成

- Dify 本地管理员、API key、模型/Embedding provider 初始化。
- FastGPT 本地 API key/app、模型 provider、3 文档索引与问答。
- MaxKB 实际容器启动和 API discovery（镜像已完成）。
- RAGFlow 在当前主机上的本地化 smoke（镜像已完成，服务架构/资源仍待验证）。
- 所有系统的完整 3 文档 ingest/index/native QA/direct retrieval 矩阵。
- 44 文档索引 readiness、Stage 1 正式运行和跨系统统一比较。
- `reports/local-rag-platform-comparison-2026-08-05.md` 的最终状态矩阵；该文件当前仍包含待更新项。

暂停时未删除任何 MOI 服务或竞品数据卷；FastGPT 容器已停止，Dify 容器也已停止，后续可从保留卷恢复。
