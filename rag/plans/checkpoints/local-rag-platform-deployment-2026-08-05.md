# 本地 RAG 竞品部署初版断点

更新时间：2026-08-06（Asia/Shanghai）
状态：**初版本地部署与 smoke 已收口；Stage 1 尚未开始**

## 1. 当前结论

本轮在既有本地 MOI 之外，完成了 Dify、FastGPT、MaxKB、RAGFlow 的本地化
部署初版验证。服务本体限定在当前 Apple Silicon + Colima 主机；LLM 与
Embedding 使用 MatrixOrigin TaaS，因此统一记录 `model_egress=external`，
不是 fully-offline。

| system_id | 本地结论 | ingest | Native QA | Direct Retrieval |
| --- | --- | --- | --- | --- |
| `dify_local` | 成功，原生 arm64 | 3/3 ready；另完成 44/44 readiness | success | success，5 contexts |
| `fastgpt_local` | 部分成功，原生 arm64 | 3/3 ready | error，工作流请求 timeout | success，3 hits |
| `maxkb_local` | 部分成功，原生 arm64 | 3/3 已上传，落盘状态 `nnn2` 语义未确认 | partial，HTTP 200 但未正确消费问题 | `UNSUPPORTED_API`；admin hit-test 仅作诊断 |
| `ragflow_local` | `BLOCKED_LOCAL_RESOURCES` | 未执行 | 未执行 | 未执行 |

没有使用远程 Linux/x86 主机替代失败结果，也没有把任何 Cloud 结果复制到
local system ID。完整对比见
[`reports/local-rag-platform-comparison-2026-08-05.md`](/Users/muuushroom/gitrepos/moi-benchmark/rag/reports/local-rag-platform-comparison-2026-08-05.md)。

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

- 官方 PgVector 全栈在原生 arm64 上启动成功，TaaS AIProxy channel 创建成功。
- `qwen3.6-flash` 与 `bge-m3` provider/model probe 成功。
- 3/3 collection ready；`POST /api/core/dataset/searchTest` 返回 3 hits。
- `POST /api/v1/chat/completions` 于 `2026-08-06T03:44:03Z` 启动工作流后
  持续没有 HTTP response，因此 Native QA 明确记为
  `NATIVE_QA_TIMEOUT_NO_RESPONSE_SINCE_2026-08-06T03:44:03Z`。
- 当前 Compose 已 `down`；5 个 `moi_fastgpt_local_*` named volumes 保留。

关键 evidence：

- `.local-services/fastgpt_local/logs/smoke-partial-20260806-114747/smoke-result.json`
- `.local-services/fastgpt_local/compose/docker-compose.pg.yml`
- `.local-services/fastgpt_local/fastgpt.env`（0600，ignored）

下一步不是重复 ingest；应集中诊断 Native workflow 的模型节点/超时，再复用
现有 dataset/app 做一次隔离的新 `chatId` 调用。只有最小 smoke 全部通过后才做
44 文档 readiness。

### MaxKB v2.10.4-lts

- 官方 `1panel/maxkb:v2.10.4-lts` 原生 arm64 image 在 8090 启动成功。
- 本地管理员 API、TaaS `deepseek-v4-flash`/`bge-m3`、知识库、应用和应用 key
  初始化成功。
- 三份 fixture 均上传，落盘 evidence 中状态为 `nnn2`；因该码不是已确认的稳定公共状态
  contract，ingest 保守记为 partial。
- admin hit-test 返回 3 条真实来源/内容/相似度，仅证明内部检索可工作。
- 应用 OpenAI-compatible endpoint 返回 HTTP 200/OpenAI schema，但回答未正确
  消费用户问题，Native QA 为 partial。
- 未找到 API-key 可访问的稳定公开 Direct Retrieval endpoint，记为
  `UNSUPPORTED_API`。
- 容器已停止；`.local-services/maxkb_local/data` 保留。

关键 evidence：

- `.local-services/maxkb_local/discovery/hit-test-summary.json`
- `.local-services/maxkb_local/discovery/`
- `.local-services/maxkb_local/logs/smoke-partial-2026-08-06/smoke-result.json`
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
- `local-rag-platforms/prepare_local_services.py`：preflight、source/image manifest、
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
- FastGPT provider contract：1 个 unittest 通过。
- Python compile、JSON parse、MaxKB/RAGFlow shell syntax、`git diff --check` 通过。
- Dify 44 文档：44 个 upload artifact，最终 `ingest_status=ready`。
- 当前仅 MOI parser/MatrixOne 容器运行，竞品服务均已释放。

## 6. 下一次恢复顺序

1. 先确认 MOI 两个容器与端口仍健康，继续坚持竞品串行运行。
2. 优先修复 FastGPT Native QA timeout；成功后再跑 44 文档 readiness。
3. 修复 MaxKB Native 请求消费问题，并确认 `nnn2` 的实例版本状态语义；公共
   Direct Retrieval 若仍不存在，继续保持 `UNSUPPORTED_API`。
4. 只有本机 Colima 资源达到官方门槛后再启动 RAGFlow。
5. 各平台最小 smoke 通过后，才接统一 attempt ledger 与 Stage 1
   `20 questions × 2 repeats`；不要对 partial/blocked 平台做效果总排名。

本断点不包含任何明文 key/password。暂停或恢复时都不要删除
`.local-services/`、Dify/FastGPT volumes 或 MaxKB data。
