---
name: run-enron-nl2sql-round
description: Run and validate one reproducible 50-question Enron NL2SQL collection round for Chat2DB, Wren, or MOI. Use when the user asks to run, resume, monitor, or verify an Enron evaluation round; collect SQL, latency, token, session, error, and MOI MatrixOne-native result artifacts; or prepare one product run for later scoring. Do not use this skill to calculate Golden accuracy or perform human SQL review.
---

# Run Enron NL2SQL Round

Run exactly one 50-question collection round through the repository's tested SOP. Preserve product failures, reject collection contamination, and never overwrite frozen reference results.

## Locate the SOP

Resolve the SOP root as the directory three levels above this Skill directory:

```text
<sop-root>/.agents/skills/run-enron-nl2sql-round/SKILL.md
```

Required entry points:

- `<sop-root>/scripts/run_one_round.py`
- `<sop-root>/scripts/validate_one_round.py`
- `<sop-root>/benchmark/questions/user/questions_enron_50_user_mix.txt`

Stop if these files are absent. Do not reconstruct or silently substitute another question set.

## Select the product path

Require exactly one product: `chat2db`, `wren`, or `moi`. Require a new, descriptive `run-id`; reuse the same ID only when resuming an interrupted collection.

Read [references/common.md](references/common.md) completely. Then read only the selected product reference:

- Chat2DB: [references/chat2db.md](references/chat2db.md)
- Wren: [references/wren.md](references/wren.md)
- MOI: [references/moi.md](references/moi.md)

For MOI, also require the intended condition: no semantic configuration or semantic configuration v2. Never infer the condition from a vague knowledge-base name.

## Execute the workflow

1. Tell the user that this Skill is starting read-only preflight checks. Do not expose secret values.
2. Run `scripts/preflight.py` with the selected product and required product arguments.
3. Run the CSV integrity verifier. For Chat2DB and Wren, also run the MySQL snapshot verifier described in the common reference.
4. If a required service, credential variable, model, database snapshot, knowledge base, or Wren private configuration is missing, pause and report the exact failed check. Do not weaken the check.
5. First run the unified entry point with `--dry-run`. Inspect the expanded command and output directory.
6. Tell the user when this Skill is about to control Chat2DB, call Wren, or create MOI sessions. This action starts real model requests and may consume API quota.
7. Run the unified entry point without `--dry-run`. Do not add automatic retries that replace product failures.
8. During a long run, report progress at useful milestones and at least once per 60 seconds. Read the live process output; do not estimate progress from elapsed time.
9. If collection infrastructure fails, fix only the collection issue and resume with the same `run-id`. Preserve audit files. If the product returns empty SQL or an execution error normally, keep it as the product's result.
10. Let the unified entry point run `validate_one_round.py`. If necessary, rerun validation explicitly using the product reference.
11. Report the run ID, coverage, generated-SQL count, product failure count, collection-error status, Token availability, output path, and whether the run is ready for scoring.

## Integrity rules

- Fix the model to `qwen3.7-plus-2026-05-26`.
- Treat one round as 50 distinct questions with `repeat_index=1` and an isolated conversation for each question.
- Write only below `<sop-root>/runs/<product>/<run-id>/`.
- Never write into `<sop-root>/reference_results/`.
- Never inject Golden SQL, Golden results, another product's output, or prior question context.
- Never print or persist API keys, passwords, cookies, CSRF tokens, or database credentials.
- Do not estimate missing Token values. Preserve `null` when exact usage is unavailable.
- For MOI, require MatrixOne-native query results and selected result artifacts; generated SQL alone is insufficient.
- A round is ready for scoring only when `validation.json` says `validation: passed`.

## Scope boundary

This Skill collects and validates raw product outputs. Do not calculate Execution Accuracy, Repeat Correct Rate, human-adjusted accuracy, or final product rankings. Hand those artifacts to the separate scoring workflow.
