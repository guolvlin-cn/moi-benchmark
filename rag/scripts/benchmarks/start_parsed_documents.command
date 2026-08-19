#!/bin/zsh
set -Eeuo pipefail

RAG_ROOT=/Users/muuushroom/gitrepos/moi-benchmark/rag
PYTHON_BIN="$RAG_ROOT/tmp/parser-batch-venv/bin/python"
PARSER_BIN=/tmp/moi-local-matrixflow-parser-datasets
LOG_FILE="$RAG_ROOT/outputs/parsed-documents/moi-ready-v1/runner.log"
TASK_TMP=/tmp/moi-parser-batch-tmp
GOCACHE_DIR="$RAG_ROOT/tmp/go-build-cache-parser-batch"

mkdir -p "$TASK_TMP" "$GOCACHE_DIR"
export TMPDIR="$TASK_TMP"
export GOCACHE="$GOCACHE_DIR"

cd "$RAG_ROOT/prototypes/local-matrixflow-parser"
go build -o "$PARSER_BIN" ./cmd/local-matrixflow-parser
mkdir -p "$(dirname "$LOG_FILE")"
cd "$RAG_ROOT"
exec "$PYTHON_BIN" benchmarks/parse_downloaded_datasets.py \
  --parser-bin "$PARSER_BIN" \
  --env-file "$RAG_ROOT/.env" \
  --output-root "$RAG_ROOT/outputs/parsed-documents/moi-ready-v1" \
  --precision-workers 4 \
  --vlm-workers 4 \
  --local-workers 8 2>&1 | tee -a "$LOG_FILE"
