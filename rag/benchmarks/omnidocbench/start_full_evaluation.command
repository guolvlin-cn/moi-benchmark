#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
BENCH="$ROOT/benchmarks/omnidocbench"
RUNS="$ROOT/runs/stage1/omnidocbench"
PID_FILE="$RUNS/full-evaluation.pid"

mkdir -p "$RUNS"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Evaluation is already running with PID $(cat "$PID_FILE")."
else
  nohup "$BENCH/run_full_evaluation.sh" >/dev/null 2>&1 &
  echo $! > "$PID_FILE"
  echo "Started OmniDocBench full evaluation with PID $!."
fi

exec "$BENCH/monitor_progress.command"
