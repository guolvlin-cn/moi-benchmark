# MOI round

## Preconditions

- Run the local Matrixflow/MOI deployment and its UC service.
- Set `MOI_EMAIL`, `MOI_PASSWORD`, and `MOI_WORKSPACE_ID` in the private environment.
- Require one exact knowledge-base name and one explicit condition:
  - no semantic configuration; or
  - semantic configuration v2 imported from `semantic/moi_email_qa_semantic_config_v2.json`.
- Ensure MOI exposes model `qwen3.7-plus-2026-05-26`.
- Do not confuse MySQL scoring data with MOI's MatrixOne-backed knowledge data. MOI must answer and execute through its native knowledge-base flow.

## Preflight

```bash
.venv/bin/python .agents/skills/run-enron-nl2sql-round/scripts/preflight.py \
  --product moi \
  --knowledge-name '<exact knowledge name>'
```

Preflight checks local ports and secret-variable presence without printing values. The runner then authenticates, resolves the exact knowledge base, and resolves the exact model; ambiguity is blocking.

## Run without semantic configuration

```bash
.venv/bin/python scripts/run_one_round.py \
  --product moi \
  --run-id <run-id> \
  --knowledge-name '<no-semantic knowledge name>'
```

## Run with semantic configuration v2

```bash
.venv/bin/python scripts/run_one_round.py \
  --product moi \
  --run-id <run-id> \
  --knowledge-name '<semantic-v2 knowledge name>' \
  --semantic-rules moi_email_qa_semantic_config_v2
```

MOI creates an isolated fixed-knowledge session per question and records generated SQL, all MatrixOne-native query results, selected results used by the final answer, execution status and time, answer text, LLM calls, and exact Token events.

If MOI infrastructure stops repeatedly, restore the service and rerun with the same command plus `--resume`. Never use `--resume` to replace a normal product failure.
