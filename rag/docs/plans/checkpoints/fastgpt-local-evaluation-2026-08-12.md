# FastGPT 本地评估断点（2026-08-12）

## 状态

- 状态：`USER_PAUSED`
- 断点时间：`2026-08-12T09:34:35+08:00`
- 范围：FastGPT 本地 `mmdocir/layout` ingest；布局 QA 和后续串行竞品评估尚未开始。
- Docker 服务保持运行，未删除或重建任何 volume。
- Dify 的独立评估进程不属于本次暂停范围，未修改。

## 已停止的评估进程

以下进程已优雅停止，并已确认不再存在：

| 进程 | 作用 |
|---|---|
| `68182` | FastGPT layout ingest |
| `68278` | layout 安全 supervisor |
| `87426` | 后续 FastGPT 串行等待链 |

## 当前运行身份与断点位置

- `run_id`：`local-frozen-v14-20260811-008-mmdocrag-c15-fastgpt_local`
- package：`.local-services/competitor-eval-ready/v1/mmdocir/layout`
- output root：`runs/competitor-eval-campaign/local-frozen-v14-20260811/008-mmdocir-layout-fastgpt_local`
- run root：`runs/competitor-eval-campaign/local-frozen-v14-20260811/008-mmdocir-layout-fastgpt_local/local-frozen-v14-20260811-008-mmdocir-layout-fastgpt_local`
- 输入资源总数：`313`
- `resource-map.partial.json`：`ready=143`、`not_started=170`、`failed=0`
- 当前 QA ledger：`0` 行；布局预期为 `1,658` 个问题，尚未执行。
- `c15` 及之后的串行评估尚未启动。

最近一次 readiness raw artifact：

```text
http/004814-fastgpt-readiness-6a7bc1e10545d19108885262.json
```

该 collection 的最新服务状态为：

```text
dataset_id=6a7bc1e10545d19108885262
collection_id=6a7bc1e10545d19108885276
dataAmount=49
trainingAmount=1
activeTrainingAmount=1
finalErrorAmount=0
hasError=false
slowestTrainingStatus=running
updateTime=2026-08-12T01:32:22.317Z
```

由于进程是在 `_wait_ready` 期间暂停的，resource map 中该资源暂时仍为 `not_started`，但其 upload checkpoint 已保存为 `submitted`，并保留了 `dataset_id` / `collection_id`。恢复时应复用现有 collection，不删除后重新建库，也不覆盖现有 HTTP artifact。

## 当前服务状态

FastGPT 服务保持运行：

- `fastgpt-app`：running
- `fastgpt-mongo`：running/healthy
- `fastgpt-aiproxy`：running/healthy
- `fastgpt-pg`：running/healthy

暂停时没有重启服务。此前最近一次异常是本机 PG/Mongo IO 长尾造成的 `Query read timeout`；暂停前 resource map 没有新增失败项。

## 已完成的修复与验证

### Runner readiness

`local-rag-platforms/scripts/evaluation/competitor_eval_runner.py` 的 FastGPT `_wait_ready` 已改为 progress-aware：

- `training` 下降、`active_training` 下降或 `dataAmount` 上升时延长 inactivity deadline；
- 保留 `active_training > 0` 时不提前报告最终索引失败；
- 没有进展时仍按 `index_timeout=1800` 失败；
- 绝对上限为 `2 * index_timeout = 3600s`。

验证：

```text
py_compile：通过
FastGPT readiness focused tests：3 passed
test_competitor_eval_runner.py：39 passed
```

### FastGPT 本地吞吐配置

`.local-services/fastgpt_local/compose/docker-compose.pg.yml` 已将：

```text
VECTOR_MAX_PROCESS: 2 -> 1
```

并同步更新了 `local-rag-platforms/tests/fastgpt/test_provider_contract.py`。compose 配置检查已通过。

注意：当前正在运行的 `fastgpt-app` 仍是旧容器环境：

```text
VECTOR_MAX_PROCESS=2
DB_MAX_LINK=10
```

文件修改尚未作用到运行中的容器；恢复前应按下方步骤重建 `fastgpt-app`，不要重建数据库服务。

## 恢复步骤

恢复前先确认没有同 run-id 的其他 ingest/QA 进程：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
ps -axo pid,command | rg \
  'competitor_eval_runner.py (ingest|qa) --system fastgpt_local|safe-layout-supervisor|serial-chain'
```

如果当前 collection 仍显示 `activeTrainingAmount > 0`，先保持现有 FastGPT 服务运行，等待其进入 terminal state；不要在训练任务进行中贸然重建 app。确认没有 active training 后，仅重建 app 以加载单 worker 配置：

```bash
docker compose -p moi_fastgpt_local \
  -f .local-services/fastgpt_local/compose/docker-compose.pg.yml config -q

docker compose -p moi_fastgpt_local \
  -f .local-services/fastgpt_local/compose/docker-compose.pg.yml \
  up -d --no-deps --force-recreate fastgpt-app
```

不要执行 `down -v`，不要重建 `fastgpt-pg`、`fastgpt-mongo` 或 `fastgpt-aiproxy`，不要删除 dataset/collection。

然后使用同一个 `run_id` resume ingest：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
set -a
source .env
source .local-services/providers/qianfan.env
source .local-services/fastgpt_local/fastgpt.env
set +a
unset TAAS_BASE_URL TAAS_API_KEY TAAS_LLM_MODEL TAAS_EMBEDDING_MODEL TAAS_CHANNEL_NAME

python3 local-rag-platforms/scripts/evaluation/competitor_eval_runner.py ingest \
  --system fastgpt_local \
  --package .local-services/competitor-eval-ready/v1/mmdocir/layout \
  --output-root runs/competitor-eval-campaign/local-frozen-v14-20260811/008-mmdocir-layout-fastgpt_local \
  --run-id local-frozen-v14-20260811-008-mmdocir-layout-fastgpt_local \
  --repeats 1 --top-k 10 --poll-seconds 10 \
  --service-timeout 600 --provider-timeout 60 --upload-timeout 300 \
  --index-timeout 1800 --query-timeout 120 --qa-timeout 240 \
  --qa-concurrency 4
```

resume 应复用已有 `submitted + collection_id` checkpoint；新的 raw HTTP evidence 继续使用更高编号追加。

只有 ingest 结束且同时满足：

```text
failed=0
not_started=0
```

才启动 layout QA。layout QA 必须达到 `1,658` 个唯一 question ID 后，才允许启动 `mmdocrag/c15`。

## 注意事项

- 不要手工编辑 `resource-map` 或 `terminal-ledger` 来伪造完成状态。
- 不要把 `activeTrainingAmount > 0` 的 collection 视为 ready。
- 不要把 provider 的 401 fallback 当成 FastGPT runtime 根因。
- 本 checkpoint 不代表 layout 评估完成；当前只是安全暂停点。
