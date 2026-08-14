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

每道题的每轮独立运行占一行JSON，SQL中的换行按JSON字符串转义：

```json
{"question_id":"e01_sender_count","question":"这个邮件库里一共有多少个不同的发件邮箱？","repeat_index":1,"generated_sql":"SELECT ...","status":"ok","latency_ms":9927,"sql_execution_ms":97,"prompt_tokens":14600,"completion_tokens":351,"total_tokens":14951,"error":null,"raw_answer":"一共有836个不同的发件邮箱。","metadata":{"model":"qwen3.7-plus-2026-05-26","session_id":"...","history_size":0,"database":"enron_eval"}}
```

必需字段：

- `question_id`
- `question`
- `repeat_index`：同一问题第几轮独立运行，从1开始
- `generated_sql`
- `status`：`ok`、`generation_error`、`execution_error`、`empty_sql`、`context_error`、`collector_error`或`manual_capture`
- `latency_ms`：无法取得时为`null`
- `prompt_tokens`：该轮完整产品流程中所有模型调用的输入Token总和，无法取得时为`null`
- `completion_tokens`：该轮所有模型调用的输出Token总和，无法取得时为`null`
- `total_tokens`：输入与输出Token之和，无法取得时为`null`
- `error`：没有错误时为`null`

可选字段：

- `raw_answer`：产品同时生成的自然语言答案
- `sql_execution_ms`：产品内部可观测到的数据库执行耗时
- `metadata`：产品特有的模型、token或追踪信息

## 统一口径

- 三轮稳定性测试必须是三个新会话，不能在同一对话里连续提问；
- `latency_ms` 从产品接收到问题开始，到完整最终回答生成结束；
- 产品一次回答可能调用模型多次，Token必须把本轮所有模型调用相加；
- `repeat_index` 表示独立测量轮次，不是失败后的自动重试；
- 预测文件只保存产品实际输出和观测数据，不保存 Golden SQL 或正确答案；
- 平台无法提供的字段写 `null`，不能写0。

不要把Golden SQL、执行评分或预期结果写进产品预测文件。

`evaluate_repeated_mysql.py` 直接读取这一格式。旧记录中的 `attempt`、`sql` 和 `latency_seconds` 仍可兼容，但新运行统一使用上述字段。
