# LoCoMo Controlled Track ingestion

`ingest.py` imports LoCoMo conversation history into Memoria with this fixed
mapping:

```text
sample_id -> X-Impersonate-User
session_n -> session_id
dialogue turn -> one memory
dia_id -> subject_id and extra_metadata.dia_id
```

The importer writes conversation turns only. It does not ingest `qa`,
`observation`, `session_summary`, or `event_summary`.

## Offline validation

Always use the shared project Python environment:

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark/memoria/scripts/locomo
source /Users/wangyaqi/Documents/cursor_project/.venv/bin/activate

pytest -q test_ingest.py

python ingest.py \
  --dry-run \
  --run-dir /tmp/locomo-ingest-dry-run
```

Expected full-dataset dry-run totals:

```text
selected_samples: 10
sessions: 272
expected_memories: 5882
failed_memories: 0
missing_ingest_keys: 0
extra_ingest_keys: 0
```

## Smoke import

Start the API with the pinned Qwen embedding configuration, then import the
fixed `conv-30` smoke sample. The runner is resumable and validates exactly 19
sessions and 369 active memories:

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark
./memoria/scripts/locomo/restart_top200_qwen.sh config-only
./memoria/scripts/locomo/run_smoke_ingest.sh
```

The smoke run directory is fixed at
`memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1-smoke-conv30`.
The accepted historical smoke may be stored under `memoria/runs/archive/`;
running this command for a fresh full import recreates the fixed active path.

## Full import

The accepted smoke is a prerequisite but is isolated from the formal corpus.
The full runner imports all 10 samples under the production
`locomo-qwen-v4-` user prefix. It validates the final 5,882 active memories
before soft-deleting the 369 memories owned by the smoke user.

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark
./memoria/scripts/locomo/run_full_ingest.sh
```

To run only the read-only prerequisite and live-configuration checks:

```bash
./memoria/scripts/locomo/run_full_ingest.sh --preflight-only
```

The Memoria API must already be running with `text-embedding-v4`, 1024
dimensions, and the DashScope OpenAI-compatible base URL. The runner refuses
to proceed if the live configuration differs. It is idempotent and may be
rerun with the same formal run directory after an interruption.

The run directory contains:

- `manifest.json`: frozen dataset, tokenizer, Memoria, mapping, and time config;
- `logs/checkpoint.jsonl`: append-only successful-write receipts;
- `logs/errors.jsonl`: per-turn and per-sample failures;
- `summary.json`: database-reconciled expected, accepted, missing, and extra keys.

The checkpoint is recovery state, not acceptance truth. A successful import
requires the final active-memory reconciliation in `summary.json` to report
5,882 accepted memories, zero missing keys, and zero extra keys.

## Top-200 retrieval evaluation

`retrieve.py` sends each Category 1–4 question once with `top_k=200`, stores an
append-only retrieval snapshot, and computes Top-10/20/50/200 metrics from the
same ranked list. It reports evidence Hit accuracy, mean evidence recall,
complete evidence recall, MRR, category breakdowns, latency, failures, and
cross-user/provenance validation.

The current Memoria API commit used by this experiment clamps both retrieve and
search requests to at most 100 results in
`memoria/crates/memoria-api/src/routes/memory.rs`. A valid Top-200 experiment
therefore requires that server limit to be raised to 200 and the API service to
be rebuilt/restarted first. The runner deliberately treats a 100-result
response as invalid instead of silently presenting it as Top-200.

The exact benchmark patches are retained under `patches/`. Apply them to the
pinned base commit before building the API image:

```bash
git checkout 54c9114fd6888e11821edc2ee9acd570c17c5ee3
git apply /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark/memoria/scripts/locomo/patches/memoria-sensitivity-filter-toggle.patch
git apply /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark/memoria/scripts/locomo/patches/memoria-top200-limit.patch
```

The first patch SHA-256 is
`a668ae33c3c5e4fd83f642c75003e1d299f81c039ca300bb4c89996bf7aca128`.
After both patches, `memory.rs` SHA-256 must be
`51eeb10a76158b93e9cfb463ac5b5bf07c7a56e6d59ff84e36c697c3bbeaeaa9`.

After the local image containing the Top-200 patch has been built, restart the
API with the same Qwen embedding configuration used for ingestion. The helper
prompts for the DashScope key without echoing or saving it, recreates only the
API container, verifies the live configuration, and runs one real Top-200
query:

```bash
./memoria/scripts/locomo/restart_top200_qwen.sh
```

Use `config-only` only while bootstrapping an empty database; it performs the
same restart and configuration checks but skips the retrieval preflight that
requires already imported memories.

Run the deterministic 10-question smoke first:

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark
source /Users/wangyaqi/Documents/cursor_project/.venv/bin/activate

python memoria/scripts/locomo/retrieve.py \
  --smoke \
  --run-dir memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/mem0-compatible-retrieval-smoke10-v1
```

The smoke selects one evidence-annotated question per sample and covers all
four evaluated categories. It must finish with 10/10 valid retrievals and 200
results per question.

After the smoke is accepted, run all 1,540 questions:

```bash
python memoria/scripts/locomo/retrieve.py \
  --run-dir memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/mem0-compatible-retrieval-top200-full1540-v1
```

The command is resumable with the identical arguments and run directory. The
main outputs are:

- `retrieval.jsonl`: immutable per-question ranked results;
- `evidence_normalization.json`: evidence cleanup and anomaly audit;
- `metrics.json`: machine-readable strict metrics;
- `report.md`: Top-10/20/50/200 summary;
- `summary.json`: completion and validation status;
- `errors.jsonl`: failed or invalid attempts.

The strict metric denominator includes every selected question with usable
evidence; request failures and invalid Top-200 responses score zero. The four
Category 3 questions without evidence remain outside retrieval metrics and will
still be included in the later 1,540-question end-to-end QA evaluation.

## Top-200 GPT-5 Reader + Judge

`evaluate_top200.py` consumes the frozen 1,540-question retrieval snapshot; it
does not query Memoria again. It uses the Reader and evidence-free unified Judge
prompts pinned from Mem0 `memory-benchmarks` commit
`4b61c5d31b9c668a12b4f5e78064248a02c82d2b`, with `gpt-5` for both calls.
The three prompt hashes are checked before any paid request.

For Reader input, the script takes exactly the ranked Top-200 memories and then
sorts those memories chronologically, as Mem0 does. Memoria's `observed_at` is
the shifted import timeline, so the displayed dates are reconstructed from the
official dataset using each result's `dia_id`. The per-sample reference date is
the latest original LoCoMo session date. Judge evidence and user profiles are
both disabled to match the selected Mem0 protocol.

Run one paid Reader + Judge preflight first. The `openai` mode uses the
OpenAI-compatible AiHubMix endpoint `https://aihubmix.com/v1` by default. The
helper reads the AiHubMix API key without echoing it or writing it to disk:

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark
./memoria/scripts/locomo/run_top200_qa_judge.sh preflight openai
```

After the preflight reports one successful answer and judgment, run all 1,540
questions:

```bash
./memoria/scripts/locomo/run_top200_qa_judge.sh full openai
```

To use a different OpenAI-compatible endpoint, set `OPENAI_BASE_URL` before the
command. The selected non-secret base URL is recorded in `manifest.json`.

The public Mem0 artifact records Azure as its provider. If strict provider
alignment is required and the Azure deployment is also named `gpt-5`, use:

```bash
./memoria/scripts/locomo/run_top200_qa_judge.sh preflight azure
./memoria/scripts/locomo/run_top200_qa_judge.sh full azure
```

For an Azure deployment with a different name, append matching overrides, for
example `--answerer-model DEPLOYMENT --judge-model DEPLOYMENT`. Both stages use
Chat Completions, omit temperature for GPT-5, set `max_completion_tokens=4096`,
retry up to five calls, use a 120-second timeout, and rate-limit each client to
200 requests/minute.

The run is resumable. `answers.jsonl` and `judgments.jsonl` are separate
append-only checkpoints, so a completed Reader call is not repeated if its Judge
call fails or the process is interrupted. Main outputs are:

- `manifest.json`: frozen snapshot, models, providers, prompt hashes, and input policy;
- `answers.jsonl`: raw Reader response, extracted answer, usage, latency, and input hashes;
- `judgments.jsonl`: raw Judge JSON, label, reasoning, usage, and latency;
- `errors.jsonl`: failed Reader/Judge attempts;
- `metrics.json` and `report.md`: strict overall/category accuracy and evidence-state diagnostics;
- `summary.json`: completion acceptance state.

An accepted full run requires 1,540 successful answers, 1,540 successful
judgments, and `complete: true`. Missing or failed judgments remain in the
strict denominator as wrong.

## Zep model-aligned GPT-5.4 under the Mem0 prompt protocol

Zep's Research page discloses `gpt-5.4` with `reasoning=medium` for the Reader
and `gpt-5.4` with chain-of-thought grading for the Judge, but it does not
publish the complete prompts or detailed scoring rules used for the 94.7%
LoCoMo run. `evaluate_zep_model_top200.py` therefore aligns the published model
configuration while using the pinned, fully public Mem0 Reader and no-evidence
Judge prompts for a reproducible Raw-Turn evaluation. Memory formatting,
chronological ordering, reference dates, Category 3 gold preprocessing, and
Judge rules are identical to the Mem0-compatible experiment.

This is named a **Zep model-aligned proxy under the Mem0 prompt protocol**. It
does not claim to reproduce Zep's undisclosed prompts, scoring implementation,
or multi-scope retrieval pipeline. The prior Zep-repository-prompt-derived v2
run remains a separate prompt ablation and is never overwritten. Its scripts
are preserved under `../archive/locomo/` and are not a current final-experiment
entrypoint.

Run one paid Reader + Judge preflight:

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark
./memoria/scripts/locomo/run_zep_model_top200_qa_judge.sh preflight
```

After it reports one successful answer and judgment, run all 1,540 questions:

```bash
./memoria/scripts/locomo/run_zep_model_top200_qa_judge.sh full
```

Both modes use the Responses API through `https://aihubmix.com/v1`, request
`gpt-5.4` with `reasoning.effort=medium` for Reader and Judge, and resume from
the latest successful per-question JSONL records. Outputs are isolated under
`zep-model-aligned-gpt54-medium-mem0-prompt-top200-aihubmix-*-v1`.
