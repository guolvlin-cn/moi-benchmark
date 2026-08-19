#!/bin/zsh
set -Eeuo pipefail

RAG_ROOT=/Users/muuushroom/gitrepos/moi-benchmark/rag
PYTHON_BIN=/usr/bin/python3
PARSER_BIN=/tmp/moi-local-matrixflow-parser-mmdoc
OUTPUT_ROOT="$RAG_ROOT/outputs/parsed-documents/moi-ready-v1"
LOG_FILE="$OUTPUT_ROOT/reparse-mmdoc-runner.log"
TASK_TMP=/tmp/moi-reparse-mmdoc-tmp
GOCACHE_DIR="$RAG_ROOT/tmp/go-build-cache-reparse-mmdoc"

mkdir -p "$TASK_TMP" "$GOCACHE_DIR" "$OUTPUT_ROOT"
export TMPDIR="$TASK_TMP"
export GOCACHE="$GOCACHE_DIR"

cd "$RAG_ROOT/prototypes/local-matrixflow-parser"
echo "[setup] validating local parser image-asset support"
go test ./...
echo "[setup] building parser: $PARSER_BIN"
go build -o "$PARSER_BIN" ./cmd/local-matrixflow-parser

cd "$RAG_ROOT"
echo "[start] MMDocIR + DocBench + MMDocRAG force reparse"
echo "[start] progress: $OUTPUT_ROOT/reparse-mmdoc-progress.json"
echo "[start] log: $LOG_FILE"
exec "$PYTHON_BIN" benchmarks/reparse_mmdoc_datasets.py \
  --parser-bin "$PARSER_BIN" \
  --env-file "$RAG_ROOT/.env" \
  --output-root "$OUTPUT_ROOT" \
  --workers 4 \
  --attempts 2 \
  --max-upload-pages 200 \
  --chunk-pages 180 \
  --timeout 1800 2>&1 | tee -a "$LOG_FILE"
