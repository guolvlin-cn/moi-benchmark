# Common one-round contract

## Required invariants

- SOP root contains the frozen 50-question file and all runner scripts.
- Model is exactly `qwen3.7-plus-2026-05-26`.
- One round contains 50 unique question IDs and only `repeat_index=1`.
- Each question uses a new conversation, thread, or fixed-knowledge session.
- Output goes to `runs/<product>/<run-id>/`.
- Product failures remain in `predictions.jsonl`; collector or context errors must be repaired and recollected.

## Common checks

Run from the SOP root with its virtual environment:

```bash
.venv/bin/python scripts/verify_csv_files.py
```

For Chat2DB and Wren, load the private database environment and verify the live MySQL snapshot:

```bash
source .env
.venv/bin/python scripts/verify_mysql_snapshot.py
```

Do not show `.env` contents. If `.venv` is absent, create it and install `requirements.txt`. If the database is absent, stop and ask whether to run the separately authorized database setup; do not use `--rebuild` without explicit permission because it deletes the existing database.

## Run identifiers

Prefer lowercase IDs containing product, model family, date or round, for example:

```text
chat2db_qwen37_round1
wren_qwen37_round1
moi_qwen37_no_semantic_round1
moi_qwen37_semantic_v2_round1
```

Do not reuse an ID for a different product, model, semantic condition, or question set.

## Completion evidence

Require these files:

```text
run.json
predictions.jsonl
validation.json
```

Wren and MOI also normally produce `run_summary.json`. MOI additionally produces `raw/`, which stays local and is Git-ignored.

Validation must establish 50/50 coverage, unique keys, frozen question text, the required model, no collector/context errors, and MOI-native fields where applicable. SQL correctness is deliberately excluded.
