#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
BENCH="$ROOT/benchmarks/omnidocbench"
RUNS="$ROOT/runs/stage1/omnidocbench"
OUTPUT="$ROOT/outputs/experiment-record-20260804"
WORK="$RUNS/artifact-recording-runtime"
LOCK="$RUNS/results-recording.lock"
NODE="/Users/muuushroom/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
NODE_PACKAGES="/Users/muuushroom/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
RESULTS="$OUTPUT/omnidocbench-results.json"
WORKBOOK="$OUTPUT/MOI-RAG-实验记录表.xlsx"
MARKDOWN="$OUTPUT/MOI-RAG-实验记录表.md"
SUMMARY="$OUTPUT/omnidocbench-recording-summary.json"
PREVIEWS="$RUNS/results-recording-previews"

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "Another OmniDocBench result recorder is already running; skipping duplicate invocation."
  exit 0
fi
cleanup() {
  rmdir "$LOCK" 2>/dev/null || true
}
trap cleanup EXIT

mkdir -p "$WORK" "$OUTPUT"
ln -sfn "$NODE_PACKAGES" "$WORK/node_modules"
cp "$BENCH/record_experiment_results.mjs" "$WORK/record_experiment_results.mjs"

python3 "$BENCH/collect_experiment_results.py" --output "$RESULTS"
cd "$WORK"
"$NODE" record_experiment_results.mjs \
  --results "$RESULTS" \
  --workbook "$WORKBOOK" \
  --markdown "$MARKDOWN" \
  --preview-dir "$PREVIEWS" \
  --summary "$SUMMARY"

echo "Recorded OmniDocBench results in $WORKBOOK and $MARKDOWN"
