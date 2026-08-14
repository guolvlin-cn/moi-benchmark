# Chat2DB round

## Preconditions

- Run on macOS with Chat2DB Pro open and signed in.
- Connect the conversation to MySQL database `enron_eval` and schema `enron_eval`.
- Select the custom model `qwen3.7-plus-2026-05-26`.
- Configure DashScope OpenAI-compatible Base URL as `https://dashscope.aliyuncs.com/compatible-mode/v1`.
- Use Temperature `0` and Max Tokens `4096`.
- Grant Accessibility permission to the terminal or Codex process controlling the UI.
- Keep the Chat2DB window position and size unchanged and do not interact with it during the round.

If local IPv4 port 3306 is occupied by SSH forwarding while MySQL listens on IPv6, use `::1:3306` in Chat2DB.

## Preflight

From the SOP root:

```bash
.venv/bin/python .agents/skills/run-enron-nl2sql-round/scripts/preflight.py \
  --product chat2db
```

Treat missing application logs, non-macOS execution, or an absent Chat2DB process as blocking.

## Run

```bash
.venv/bin/python scripts/run_one_round.py \
  --product chat2db \
  --run-id <run-id>
```

The runner creates a new UI conversation per question and validates `historySize=0`, database `enron_eval`, and the actual model captured from the application log. It records SQL, product execution status, end-to-end latency, SQL execution latency, exact log usage, and answer text.

## Recovery

For UI movement, timeout, log parsing, model mismatch, history contamination, or wrong database context, stop. Correct the cause and rerun the same command with the same ID. Invalid collector/context records are archived to `collection_errors.jsonl` and must not occupy a formal attempt.

Do not manually use Chat2DB while the runner is active.
