#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
BENCH="$ROOT/benchmarks/omnidocbench"
RUNS="$ROOT/runs/stage1/omnidocbench"
RUN_DIR="$RUNS/20260804-precision-full-1651"
OUTPUT_DIR="$RUN_DIR/official/scorer-output"
STATUS="$RUNS/LIVE-STATUS.txt"
LOG="$RUNS/precision-full-official-score.log"
PID_FILE="$RUNS/precision-full-score.pid"

cd "$ROOT"
echo $$ > "$PID_FILE"
exec > >(tee -a "$LOG") 2>&1

phase() {
  printf '%s\n' "$1" > "$STATUS"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

cleanup() {
  code=$?
  rm -f "$PID_FILE"
  if [[ $code -ne 0 ]]; then
    phase "FAILED Precision 1651 official score exit_code=$code; inspect $LOG"
  fi
}
trap cleanup EXIT

phase "OFFICIAL SCORE Precision 1651 pages"
"$BENCH/score_official.sh" "$RUN_DIR" "$OUTPUT_DIR"
phase "COMPLETED Precision 1651 official score"

echo
echo "Precision 1651 official scoring completed. Press Enter to close this terminal."
read -r
