#!/usr/bin/env bash
set -u

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
BENCH="$ROOT/benchmarks/omnidocbench"
RUNS="$ROOT/runs/stage1/omnidocbench"
PID_FILE="$RUNS/results-watcher.pid"
READINESS="$RUNS/results-readiness.json"

cd "$ROOT"
echo $$ > "$PID_FILE"
cleanup() {
  rm -f "$PID_FILE"
}
trap cleanup EXIT

echo "Waiting for all OmniDocBench experiments and official scorers to complete."
echo "The XLSX and Markdown records will be updated only after all five runs are complete."
echo

while true; do
  if python3 "$BENCH/collect_experiment_results.py" --output "$READINESS" >/dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] All results are ready; recording outputs."
    if "$BENCH/finalize_experiment_results.sh"; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Result recording completed."
      exit 0
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Recording failed; retrying in 30 seconds."
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Experiments still running..."
  fi
  sleep 30
done
