# 五个目标 API 性能基准

规范入口是 `local-rag-platforms/api/control.py`。它把 MOI、Dify、FastGPT、MaxKB、
RAGFlow 的请求适配成同一套压测窗口，并输出 `summary.json`、`samples.jsonl`、
`resolved-targets.json` 和 `report.md`。旧的
`local-rag-platforms/api/api_load_benchmark.py` 仍然转发到同一个总控。

## 先验证配置，不需要 API key

```bash
python3 local-rag-platforms/api/control.py dry-run \
  --platforms all \
  --scenario both \
  --connections 1,4,8
```

旧命令也可以运行：

```bash
python3 local-rag-platforms/api/api_load_benchmark.py \
  --dry-run --platforms all --scenario both --connections 1,4,8
```

## 指标口径

- `Event Throughput (events/s)`：测量窗口内收到的完整 SSE 事件数除以窗口秒数；报告同时给出按所有请求流时长计算的 `stream_event_rate_events_per_s`。
- `TTFE (ms)`：从请求开始到收到第一个完整 SSE 事件的时间，输出 `p50/p95/avg/min/max`。非流式 JSON 请求把第一个非空响应体视为一个 `response` 事件。
- `Connections`：并发请求数，同时输出 `peak_in_flight`。当前实现采用 `fresh-per-request`，每次请求新建 HTTP 连接，避免把连接复用策略混入第一版结果。
- `Empty Workflow QPS`：成功完成的空工作流请求数除以测量窗口秒数。Dify、FastGPT、MaxKB 默认使用各自无输入/无状态应用的 blocking 调用；必须把 key/app ID 指向真正的 no-op 工作流或应用，结果才可称为 empty workflow。
- RAGFlow 的 `events` 使用 `/api/v1/openai/{chat_id}/chat/completions` SSE，`empty_workflow` 使用同一路径的非流式 JSON；请求体保留 `extra_body.reference=true`，以便同时记录回答和引用。

MOI 的 `/byoa/api/v1/data_asking/analyze` 是官方 SDK 暴露的 SSE Data Asking/RAG 分析接口，因此默认参与事件吞吐和 TTFE；它不是一个跨部署统一的 empty-workflow API，所以默认把 MOI 的 Empty Workflow 标为 `unsupported`。如果当前部署有 no-op workflow，使用 `--config local-rag-platforms/api/api_benchmark.example.json` 或设置 `MOI_BENCHMARK_EMPTY_PATH`。

## 真实运行前的环境变量

先设置服务地址和凭据名称对应的值：

```bash
export MOI_API_URL='http://127.0.0.1:8000'
export MOI_API_KEY='...'

export DIFY_BENCHMARK_BASE_URL='http://127.0.0.1:8010/v1'
export DIFY_API_KEY='app-...'
export DIFY_BENCHMARK_INPUTS_JSON='{}'

export FASTGPT_BASE_URL='http://127.0.0.1:3000'
export FASTGPT_API_KEY='fastgpt-...'
export FASTGPT_APP_ID='...'

export MAXKB_BASE_URL='http://127.0.0.1:8090'
export MAXKB_API_KEY='agent-...'
export MAXKB_APPLICATION_ID='...'

export RAGFLOW_BASE_URL='http://127.0.0.1:9380'
export RAGFLOW_API_KEY='ragflow-...'
export RAGFLOW_CHAT_ID='...'
```

然后先做短窗口 smoke：

```bash
python3 local-rag-platforms/api/control.py benchmark \
  --platforms moi,dify,fastgpt,maxkb \
  --scenario both \
  --connections 1,4 \
  --warmup 1 \
  --duration 10 \
  --timeout 60 \
  --max-requests 100 \
  --output runs/api-benchmark-smoke
```

没有配置的目标会在结果里显示为 `skipped`，不会导致其他目标的结果丢失。`--max-requests` 是第一阶段的安全上限；正式比较时应在目标之间使用相同的 duration、warmup、connections、问题文本和应用状态。

## 自定义请求

`local-rag-platforms/api/api_benchmark.example.json` 展示了如何覆盖 base URL、鉴权、事件路径和 MOI 的 empty-workflow 请求。请求体支持以下占位符：

- `{{uuid}}`：每次请求生成唯一 ID；
- `{{timestamp}}`：每次请求生成纳秒时间戳；
- `{{env:NAME}}` 或 `${NAME}`：读取环境变量。

API key 只从环境变量读取，不写入 JSON 或输出 artifact。
