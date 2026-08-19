#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
RUNS="$ROOT/runs/stage1/omnidocbench"
RUN_DIR="$RUNS/20260804-precision-full-1651"
PID_FILE="$RUNS/precision-full-parse.pid"

cd "$ROOT"
echo $$ > "$PID_FILE"
cleanup() {
  rm -f "$PID_FILE"
}
trap cleanup EXIT

echo "Starting MinerU Precision full parsing."
echo "Run: $RUN_DIR"
echo "Existing successful/reused pages will be skipped."
echo

python3 "$ROOT/benchmarks/omnidocbench/run_stage1.py" parse \
  --run-dir "$RUN_DIR" \
  --parser-bin /tmp/moi-local-matrixflow-parser \
  --pipeline precision \
  --env-file "$ROOT/.env" \
  --workers 4

echo
echo "Precision full parsing completed. Press Enter to close this terminal."
read -r
