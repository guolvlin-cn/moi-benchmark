# OmniDocBench Stage 1 adapter

This adapter implements the Stage 1 run contract for OmniDocBench: deterministic proportional sampling by `data_source`, conversion of each page image to a one-page PDF, MOI parsing, official Markdown naming, and MOI attempt/latency/error ledgers.

The official dataset card states that the dataset is research-only and not for commercial use. S1-G0 was cleared on 2026-08-03 only for the researcher's explicitly declared non-commercial graduation-thesis research, including confirmed third-party cloud processing. This clearance does not extend to commercial product evaluation or redistribution of source pages.

After written authorization is recorded, the intended commands are:

```bash
python3 benchmarks/omnidocbench/run_stage1.py prepare \
  --ground-truth datasets/downloads/document-rag/omnidocbench/data/OmniDocBench.json \
  --images datasets/downloads/document-rag/omnidocbench/data/images \
  --run-dir runs/stage1/omnidocbench/<run_id> \
  --sample-size 200 \
  --seed 20260803

python3 benchmarks/omnidocbench/run_stage1.py parse \
  --run-dir runs/stage1/omnidocbench/<run_id> \
  --parser-bin /absolute/path/to/local-matrixflow-parser \
  --pipeline precision \
  --env-file /Users/muuushroom/gitrepos/moi-benchmark/rag/.env \
  --workers 4
```

The official scorer must use OmniDocBench's pinned Docker environment and the metrics recorded in the run's `official/protocol.json`.

## Persist parsed documents by engine and pipeline

After a parse run completes, export its inputs, parsed Markdown, parser result/summary, metadata, and SHA-256 manifest into the engine-isolated local store:

```bash
python3 benchmarks/omnidocbench/export_parsed_documents.py \
  --run-dir runs/stage1/omnidocbench/<run_id> \
  --output-root outputs/parsed-documents/omnidocbench \
  --engine mineru \
  --pipeline precision
```

Use `--pipeline agent` for the MinerU agent pipeline. Genuine MOI Native outputs must use `--engine moi --pipeline native`; do not relabel MinerU service output as MOI Native. Other parsers use their own engine directory, for example `--engine docling`.

The resulting layout is `<engine>/<pipeline>/<run_id>/documents/<document_id>/`. The exporter is idempotent only when existing files match by SHA-256 and fails rather than overwriting different content.
