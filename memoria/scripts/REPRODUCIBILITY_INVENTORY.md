# Memoria public benchmark reproducibility inventory

Updated: 2026-08-12

This inventory covers only the four final experiments summarized in
`memoria/evaluate/memoria-longmemeval-locomo-final-summary.md`. It does not
authorize deleting or rewriting historical runs. Files under `memoria/runs/`
remain immutable experimental evidence.

## Final experiments

| Dataset | Comparison | Reader / Judge | Final run |
|---|---|---|---|
| LongMemEval-S | Mem0-aligned | GPT-5 / GPT-5 | `longmemeval-s-mem0-protocol-gpt5-top20-full500-v1` |
| LongMemEval-S | Zep model-aligned proxy | GPT-5.4 medium / GPT-5.4 medium | `longmemeval-s-zep-aligned-gpt54-top20-full500-v1` |
| LoCoMo | Mem0-aligned | GPT-5 / GPT-5 | `mem0-compatible-gpt5-reader-judge-top200-aihubmix-full1540-v1` |
| LoCoMo | Zep model-aligned proxy | GPT-5.4 medium / GPT-5.4 medium | `zep-model-aligned-gpt54-medium-mem0-prompt-top200-aihubmix-full1540-v1` |

## Retain: final QA reproduction

### LongMemEval-S

- `longmemeval/evaluate_mem0_protocol.py`
- `longmemeval/mem0_prompts.py`
- `longmemeval/snapshot_common.py`
- `longmemeval/run_mem0_protocol_top20.sh`
- `longmemeval/run_zep_aligned_top20.sh`
- `longmemeval/smoke10-question-ids.json`
- `longmemeval/test_evaluate_mem0_protocol.py`

### LoCoMo

- `locomo/evaluate_top200.py`
- `locomo/evaluate_zep_model_top200.py`
- `locomo/mem0_prompts.py`
- `locomo/run_top200_qa_judge.sh`
- `locomo/run_zep_model_top200_qa_judge.sh`
- `locomo/test_evaluate_top200.py`
- `locomo/test_evaluate_zep_model_top200.py`
- `locomo/README.md`

## Retain: ingestion and retrieval lineage

### LongMemEval-S

- `longmemeval/ingest.py`
- `longmemeval/retrieve.py`
- `longmemeval/evaluate_retrieval.py`
- `longmemeval/run_retrieval_500.sh`
- `longmemeval/test_ingest.py`
- `longmemeval/test_retrieval.py`
- `longmemeval/RETRIEVAL_RUNBOOK.md`

### LoCoMo

- `locomo/ingest.py`
- `locomo/retrieve.py`
- `locomo/restart_top200_qwen.sh`
- `locomo/run_smoke_ingest.sh`
- `locomo/run_full_ingest.sh`
- `locomo/patches/memoria-sensitivity-filter-toggle.patch`
- `locomo/patches/memoria-top200-limit.patch`
- `locomo/test_ingest.py`
- `locomo/test_retrieve.py`
- `locomo/README.md`

The LoCoMo smoke runner pins `conv-30`, the original user prefix, Qwen
embedding configuration, Memoria commit label, patch hash, run directory, and
the 369-memory acceptance gate. Historical ingest manifests did not record the
sample-selection arguments; the runner is therefore the missing executable
provenance for that selection.

## Retain: immutable inputs and evidence

- `memoria/datasets/downloads/public-benchmarks/longmemeval/longmemeval_oracle.json`
- `memoria/datasets/downloads/public-benchmarks/locomo/locomo10.json`
- `memoria/runs/longmemeval-s-bge-m3-relative-shift-v1/`
- `memoria/runs/longmemeval-s-mem0-protocol-gpt5-top20-full500-v1/`
- `memoria/runs/longmemeval-s-zep-aligned-gpt54-top20-full500-v1/`
- `memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/`
- the four final reports and the consolidated report under `memoria/evaluate/`
- the isolated runtime configuration and tokenizer under `../memoria_runtime/`

Do not commit runtime secrets. Preserve `.env.example`, Compose configuration,
tokenizer hash, image identity, and the exact Top-200 patch separately from API
keys.

## Archived run outputs

Historical run directories not required by the four final experiments have
been moved intact to `memoria/runs/archive/`:

- `memoria/runs/archive/longmemeval/`: earlier Luna, Opus, Oracle, smoke,
  stability, and Memoria-version investigations;
- `memoria/runs/archive/locomo/`: early BGE-M3 smoke, paid/retrieval preflights,
  the accepted Qwen `conv-30` ingest smoke, and the superseded
  Zep-repository-prompt adapter run.

The Qwen smoke is reproducible rather than an active final result:
`run_smoke_ingest.sh` recreates it at its fixed original path whenever a fresh
full ingestion is required, after which it may be archived again.

See `memoria/runs/archive/README.md` for the original nested-path mapping and
storage policy. Formal run contents were not rewritten during archival.

## Archived: not used by the four final experiments

The following files have been moved under `memoria/scripts/archive/`. They are
retained as historical evidence but are not current reproduction entrypoints.

### LongMemEval-S earlier Reader, Opus, and Oracle experiments

- `archive/longmemeval/end_to_end_eval.py`
- `archive/longmemeval/oracle_reader_eval.py`
- `archive/longmemeval/legacy_opus_reproduction.py`
- `archive/longmemeval/run_e2e_full500.sh`
- `archive/longmemeval/run_e2e_smoke10.sh`
- `archive/longmemeval/run_e2e_top20_calibrated_idk51.sh`
- `archive/longmemeval/run_e2e_top20_full500.sh`
- `archive/longmemeval/run_legacy_opus_reproduction.sh`
- `archive/longmemeval/run_oracle_reader_50.sh`
- `archive/longmemeval/run_oracle_reader_gpt55.sh`
- `archive/longmemeval/top20-opus-prompt-idk51-question-ids.json`
- `archive/longmemeval/test_end_to_end_eval.py`
- `archive/longmemeval/test_legacy_opus_reproduction.py`
- `archive/longmemeval/test_oracle_reader_eval.py`
- `archive/longmemeval/E2E_RUNBOOK.md`
- `archive/longmemeval/LEGACY_OPUS_REPRODUCTION_RUNBOOK.md`
- `archive/longmemeval/ORACLE_READER_RUNBOOK.md`
- `archive/longmemeval/TOP20_LUNA_RUNBOOK.md`

### LongMemEval-S historical Memoria-version investigation

- `archive/longmemeval/embedding_escape_proxy.py`
- `archive/longmemeval/prepare_v022_reuse_store.py`
- `archive/longmemeval/run_memoria_apr02_retrieval.sh`
- `archive/longmemeval/run_memoria_v022_prebug_retrieval.sh`
- `archive/longmemeval/run_memoria_v022_reuse_store_retrieval.sh`
- `archive/longmemeval/run_retrieval_100.sh`
- `archive/longmemeval/MEMORIA_APR02_VERSION_RUNBOOK.md`
- `archive/longmemeval/MEMORIA_RETRIEVAL_VERSION_AUDIT.md`

### LoCoMo superseded Zep-prompt adapter experiment

- `archive/locomo/evaluate_zep_top200.py`
- `archive/locomo/zep_prompts.py`
- `archive/locomo/run_zep_top200_qa_judge.sh`
- `archive/locomo/test_evaluate_zep_top200.py`

### Generated caches

- `archive/generated-cache/`

## Remaining full-reproduction risk

The frozen retrieval and QA results are locally reproducible from retained
artifacts. The two local Memoria changes required to rebuild LoCoMo retrieval
from an empty service are now preserved as patches above and must be applied to
base commit `54c9114fd6888e11821edc2ee9acd570c17c5ee3` before building the API
image. The resulting `memory.rs` must have SHA-256
`51eeb10a76158b93e9cfb463ac5b5bf07c7a56e6d59ff84e36c697c3bbeaeaa9`.
