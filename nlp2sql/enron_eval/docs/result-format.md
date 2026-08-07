# 产品运行结果格式

每次运行使用目录：

```text
runs/<product>/<run_id>/
├── run.json
├── predictions.jsonl
└── raw/
```

## run.json

记录可复现信息：

```json
{
  "run_id": "2026-08-06_baseline_01",
  "product": "moi",
  "product_version": "...",
  "model": "...",
  "benchmark_id": "enron_golden50_v1",
  "database_snapshot": "expected_counts_v1",
  "semantic_rules": "enron_golden50_rule_injection.json",
  "started_at": "2026-08-06T00:00:00+08:00",
  "notes": ""
}
```

## predictions.jsonl

每道题一行JSON，SQL中的换行按JSON字符串转义：

```json
{"question_id":"e01_sender_count","question":"这个邮件库里一共有多少个不同的发件邮箱？","generated_sql":"SELECT ...","status":"ok","latency_ms":1234,"error":null,"raw_answer":null}
```

必需字段：

- `question_id`
- `question`
- `generated_sql`
- `status`：`ok`、`generation_error`、`empty_sql`或`manual_capture`
- `latency_ms`：无法取得时为`null`
- `error`：没有错误时为`null`

可选字段：

- `raw_answer`：产品同时生成的自然语言答案
- `attempt`：重试次数，基准运行默认只允许1次
- `metadata`：产品特有的模型、token或追踪信息

不要把Golden SQL、执行评分或预期结果写进产品预测文件。

下一版 timing、Token、成本、模型调用、修复和稳定性字段见：[v0.4多维指标计划](../../plans/drafts/v0.4.md)。现有字段继续兼容，平台不可观测的指标必须写为 `null` 并记录原因，不能用0代替。
