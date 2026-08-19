#!/bin/zsh
set -Eeuo pipefail

RAG_ROOT=/Users/muuushroom/gitrepos/moi-benchmark/rag
PARSER_BIN=/tmp/moi-local-matrixflow-parser-datasets
PDFCPU_BIN=/tmp/moi-pdfcpu
LOG_FILE="$RAG_ROOT/outputs/parsed-documents/moi-ready-v1/rescue-runner.log"
TASK_TMP=/tmp/moi-parser-rescue-tmp
GOCACHE_DIR="$RAG_ROOT/tmp/go-build-cache-parser-batch"

mkdir -p "$TASK_TMP" "$GOCACHE_DIR"
export TMPDIR="$TASK_TMP"
export GOCACHE="$GOCACHE_DIR"

cd "$RAG_ROOT"
exec /usr/bin/python3 benchmarks/retry_failed_samples.py \
  --parser-bin "$PARSER_BIN" \
  --pdfcpu-bin "$PDFCPU_BIN" \
  --env-file "$RAG_ROOT/.env" \
  --output-root "$RAG_ROOT/outputs/parsed-documents/moi-ready-v1" \
  --precision-workers 2 \
  --vlm-workers 1 \
  --precision-attempts 2 \
  --vlm-attempts 4 2>&1 | tee -a "$LOG_FILE"
