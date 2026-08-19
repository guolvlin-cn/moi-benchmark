# 本地 RAG 竞品部署初版断点

更新时间：2026-08-10（Asia/Shanghai）
状态：**Dify、FastGPT、MaxKB 本地完整最小链路已通过；RAGFlow 仍受资源阻塞；Stage 1 尚未开始**

## 1. 当前结论

本轮在既有本地 MOI 之外，完成了 Dify、FastGPT、MaxKB、RAGFlow 的本地化
部署初版验证。服务本体限定在当前 Apple Silicon + Colima 主机；LLM 与
Embedding 使用 MatrixOrigin TaaS，因此统一记录 `model_egress=external`，
不是 fully-offline。

| system_id | 本地结论 | ingest | Native QA | Direct Retrieval |
| --- | --- | --- | --- | --- |
| `dify_local` | 成功，原生 arm64 | 3/3 ready；另完成 44/44 readiness | success | success，5 contexts |
| `fastgpt_local` | 成功，原生 arm64 | PDF ready；独立千帆向量空间 | success，千帆生成式回答 | success，1 hit + 1 quote |
| `maxkb_local` | 成功，原生 arm64 | 解析文档 `nnn2`，embedding state 2/SUCCESS | success，千帆生成式回答 | `UNSUPPORTED_API`；admin hit-test 成功但仅作诊断 |
| `ragflow_local` | `BLOCKED_LOCAL_RESOURCES` | 未执行 | 未执行 | 未执行 |

没有使用远程 Linux/x86 主机替代失败结果，也没有把任何 Cloud 结果复制到
local system ID。完整对比见
[`plans/reports/local-rag-platform-comparison-2026-08-05.md`](/Users/muuushroom/gitrepos/moi-benchmark/rag/plans/reports/local-rag-platform-comparison-2026-08-05.md)。

2026-08-10 多 provider 实测：当前 TaaS key 对 chat/embedding 均返回 401；
百度千帆 V2 chat/embedding 可用；ModelArts MaaS 的 `bge-m3` embedding 可用，
但 `/models` 中 11 个文本候选和 `bge-reranker-v2-m3` 均因账号权限返回
`403 ModelArts.81004`。因此本轮没有把 MaaS model list 的可见性误记为可调用性。

## 2. 主机与串行运行边界

- macOS / Apple Silicon / 16 GiB；Colima `linux/aarch64`。
- Colima 实际配置：2 CPU、12 GiB、Docker 数据盘 100 GiB，执行时约剩
  12–13 GiB。
- Docker client 29.6.2、server 29.5.2、Docker Compose 5.4.0。
- 竞品服务始终串行运行；当前竞品容器均已停止，数据卷/数据目录保留。
- MOI 仍在运行：`moi-openxml-parser` 监听 `127.0.0.1:8080`；MatrixOne
  监听 `6001/9876`。
- 端口：Dify `8010`（8000 被已有 uvicorn 占用）、FastGPT `3000`、
  RAGFlow `9380`、MaxKB `8090`。
- `.local-services/` 被 Git 忽略；密钥、密码、vendor checkout、数据卷和 raw
  artifact 不提交。

## 3. 平台执行断点

### Dify 1.16.1

- 官方 Community Edition Compose 在原生 arm64 上启动成功。
- 本地管理员、独立 Dataset/App key 与 app-linked dataset 已初始化，未复用
  Dify Cloud key、ID 或结果。
- repository-owned `matrixorigin-taas` Dify plugin 已升级到 `0.0.3`，同时暴露
  `deepseek-v4-flash` LLM 与 `bge-m3` embedding。
- 三文档 smoke：service/ingest/native/retrieval 全部成功。
- 44 文档 readiness：44 个文件全部上传并进入 ready；该运行只验证 corpus
  readiness，不是 Stage 1。
- 当前 Compose 已 `down`，卷保留。重启后 API 可能因 migration 在约 1–2 分钟
  内暂时返回 502，应等待 `/console/api/setup` 返回 finished，不要重建卷。

关键 evidence：

- `.local-services/dify_local/logs/smoke-2026-08-06/smoke-result.json`
- `.local-services/dify_local/logs/readiness-44docs-2026-08-06/smoke-result.json`
- `.local-services/dify_local/credentials.env`（0600，ignored）

### FastGPT v4.15.6 / runtime image v4.15.4

- 官方 PgVector 全栈在原生 arm64 上启动成功。原 TaaS key 已被上游明确拒绝为
  `401 invalid_api_key`，因此 2026-08-10 使用独立百度千帆 V2 channel 重跑。
- 千帆 AIProxy channel 固定为 type `49`；`deepseek-v4-flash` chat 与
  `qwen3-embedding-8b` embedding 的 FastGPT 类型化 probe 均 HTTP/API 200。
  `qwen3-reranker-8b` 因上游负载饱和返回 500，仅记为可选能力不可用。
- 新建 dataset 在上传前校验实际 `vectorModel=qwen3-embedding-8b`，不复用或
  回退到 TaaS 向量空间。唯一 sentinel PDF 上传、解析、索引 ready；
  `searchTest` 返回 1 hit。
- 新建隔离 app 与 fresh `chatId` 调用 `/api/v1/chat/completions` 成功；
  `quoteList` 1 条，检索结果、引用与最终答案均包含唯一 sentinel。
- 恢复期间出现的 `bge-m3`/401 来自持久卷中的旧 TaaS 训练队列，不属于新
  千帆 dataset；runner 已增加上传前模型门禁，防止静默回退。
- 当前 Compose 已 `down`；5 个 `moi_fastgpt_local_*` named volumes 保留。

关键 evidence：

- `.local-services/fastgpt_local/logs/smoke-partial-20260806-114747/smoke-result.json`
- `.local-services/fastgpt_local/logs/acceptance-qianfan-20260810-165918/manifest.json`
- `.local-services/fastgpt_local/compose/docker-compose.pg.yml`
- `.local-services/fastgpt_local/fastgpt.env`（0600，ignored）

FastGPT 最小完整链路已通过；下一步才是 44 文档 readiness 或统一 Stage 1，
且必须继续使用同一个千帆 embedding 模型完成整个知识库，不能混入旧 TaaS 向量。

### MaxKB v2.10.4-lts

- 官方 `1panel/maxkb:v2.10.4-lts` 原生 arm64 image 在 8090 启动成功。
- 原 TaaS chat/embedding key 已被上游拒绝为 `401 invalid_api_key`。改用
  ModelArts MaaS `bge-m3` embedding（不传自定义 `dimensions`）后模型验证成功。
- 唯一 sentinel Markdown 通过实例 API split、batch create、异步 embedding；
  文档状态 `nnn2` 中末位 state `2` 已由任务状态与数据库证据确认是 SUCCESS。
- admin hit-test 命中唯一段落，证明解析、向量化与检索链路真实工作。
- 百度千帆 V2 `deepseek-v4-flash` 在 MaxKB OpenAI provider 中验证成功。
  普通 SIMPLE 应用关联知识库并发布，公开 OpenAI-compatible endpoint 返回
  正确 sentinel，`usage.total_tokens=267`。
- Native QA 的最终根因是自定义 `model_setting.prompt` 遗漏 MaxKB 必需的
  `{data}` 和 `{question}` 占位符：检索曾成功，但段落没有注入 LLM 消息。
  runner 与回归测试现已强制检查这两个占位符。
- 未找到 API-key 可访问的稳定公开 Direct Retrieval endpoint，记为
  `UNSUPPORTED_API`。
- 容器已停止；`.local-services/maxkb_local/data` 保留。

关键 evidence：

- `.local-services/maxkb_local/discovery/hit-test-summary.json`
- `.local-services/maxkb_local/discovery/`
- `.local-services/maxkb_local/logs/smoke-partial-2026-08-06/smoke-result.json`
- `.local-services/maxkb_local/logs/maxkb-full-chain-live/manifest.json`
- `.local-services/maxkb_local/logs/maxkb-full-chain-live/generative-public-qa-response-2.json`
- `.local-services/maxkb_local/secrets/`（0600，ignored）

### RAGFlow v0.26.4

- 主镜像为 `linux/amd64`，本机 qemu-x86_64 emulation 可用；依赖可使用
  arm64 manifest，因此最终阻塞不是 `BLOCKED_LOCAL_ARCH`。
- 官方该版本门槛为 4 CPU、16 GB RAM、50 GB disk；当前 Colima 只有 2 CPU、
  12 GiB、约 12 GiB Docker free space。
- 静态 preflight 因三项资源均不达标返回 `BLOCKED_LOCAL_RESOURCES`。为避免
  destabilize MOI，本轮没有强行启动完整 Elasticsearch/RAGFlow 栈。

关键 evidence：

- `.local-services/ragflow_local/logs/preflight-20260806T031839Z/preflight.json`
- `.local-services/ragflow_local/logs/smoke-resources-blocked-2026-08-06-v2/smoke-result.json`

只有在同一允许主机把 Colima 提升到至少 4 CPU/16 GiB 且提供 50 GiB 可用空间
后，才恢复完整服务 smoke；不使用远程主机绕过。

## 4. 已落地的可提交材料

- `local-rag-platforms/versions.json`：固定 tag、source commit、端口、平台与状态。
- `local-rag-platforms/scripts/deployment/prepare_local_services.py`：preflight、source/image manifest、
  0600 runtime credential helper。
- `local-rag-platforms/{dify_local,fastgpt_local,ragflow_local,maxkb_local}/`：各平台
  launcher、配置模板、contract 与部署说明。
- `local-rag-platforms/fixtures/smoke/`：统一三文档 fixture 和 probe。
- `dify-rag-eval/src/dify_rag_eval/local_smoke.py` 与 `cli.py`：统一 smoke、脱敏
  raw artifact、hash、Dify existing-dataset reuse。
- `dify-plugins/matrixorigin-taas/`：Dify 本地 TaaS LLM/Embedding provider 0.0.3。
- `reports/local-rag-platform-comparison-2026-08-05.md`：local/cloud 流程和实际矩阵。

## 5. 已完成验证

- `dify-rag-eval`：16 个 unittest 通过。
- MatrixOrigin Dify plugin：6 个 pytest 通过（2 个第三方 deprecation/monkey-patch warning）。
- FastGPT provider/full-chain contract：16 个 unittest 通过（含多文件 readiness 门禁）。
- MaxKB runner 静态 contract test 通过；真实行为验收由落盘 API/数据库 artifact 证明。
- Python compile、JSON parse、MaxKB/RAGFlow shell syntax、`git diff --check` 通过。
- Dify 44 文档：44 个 upload artifact，最终 `ingest_status=ready`。
- 当前仅 MOI parser/MatrixOne 容器运行，竞品服务均已释放。

## 6. 下一次恢复顺序

1. 先确认 MOI 两个容器与端口仍健康，继续坚持竞品串行运行。
2. FastGPT 已通过 PDF 最小链路；可继续做 44 文档 readiness，再进入统一评估。
3. MaxKB 已通过解析文档生成式 RAG；公共 Direct Retrieval 仍保持
   `UNSUPPORTED_API`，正式评估只将 admin hit-test 当诊断证据。
4. 只有本机 Colima 资源达到官方门槛后再启动 RAGFlow。
5. 各平台最小 smoke 通过后，才接统一 attempt ledger 与 Stage 1
   `20 questions × 2 repeats`；不要对 partial/blocked 平台做效果总排名。

本断点不包含任何明文 key/password。暂停或恢复时都不要删除
`.local-services/`、Dify/FastGPT volumes 或 MaxKB data。
