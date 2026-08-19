#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
BENCH="$ROOT/benchmarks/omnidocbench"
RUNS="$ROOT/runs/stage1/omnidocbench"
DATASET="$ROOT/datasets/downloads/document-rag/omnidocbench/data/OmniDocBench.json"
IMAGES="$ROOT/datasets/downloads/document-rag/omnidocbench/data/images"
ENV_FILE="$ROOT/.env"
PARSER_BIN="/tmp/moi-local-matrixflow-parser"
STATUS="$RUNS/LIVE-STATUS.txt"
LOG="$RUNS/full-evaluation.log"
TASK_TMP_DIR="$RUNS/runtime-tmp"
GO_CACHE_DIR="$RUNS/go-build-cache"

mkdir -p "$RUNS" "$TASK_TMP_DIR" "$GO_CACHE_DIR"
export TMPDIR="$TASK_TMP_DIR"
export GOCACHE="$GO_CACHE_DIR"
exec > >(tee -a "$LOG") 2>&1

phase() {
  printf '%s\n' "$1" > "$STATUS"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

on_exit() {
  code=$?
  if [[ $code -ne 0 ]]; then
    phase "FAILED_OR_INTERRUPTED exit_code=$code; inspect $LOG and rerun this script to resume"
  fi
}
trap on_exit EXIT

prepare_run() {
  local run_dir="$1"
  local sample_size="$2"
  if [[ ! -f "$run_dir/artifacts/sample-manifest.jsonl" ]]; then
    python3 "$BENCH/run_stage1.py" prepare \
      --ground-truth "$DATASET" \
      --images "$IMAGES" \
      --run-dir "$run_dir" \
      --sample-size "$sample_size" \
      --seed 20260803
  fi
}

parse_run() {
  local run_dir="$1"
  local pipeline="$2"
  python3 "$BENCH/run_stage1.py" parse \
    --run-dir "$run_dir" \
    --parser-bin "$PARSER_BIN" \
    --pipeline "$pipeline" \
    --env-file "$ENV_FILE" \
    --workers 4
}

score_run() {
  local run_dir="$1"
  local output_name="$2"
  if [[ -f "$run_dir/official/$output_name/predictions_quick_match_run_summary.json" ]]; then
    echo "Official score already complete, reusing $run_dir/official/$output_name"
    return 0
  fi
  "$BENCH/score_official.sh" "$run_dir" "$run_dir/official/$output_name"
}

phase "BUILD parser and validate adapter"
cd "$ROOT/prototypes/local-matrixflow-parser"
go test ./...
go build -o "$PARSER_BIN" ./cmd/local-matrixflow-parser
cd "$ROOT"
python3 -m unittest -v benchmarks.omnidocbench.test_run_stage1

phase "SMOKE agent official scoring 20 pages"
score_run "$RUNS/20260803-agent-smoke-20" "scorer-output-resume-01"

for pipeline in precision agent; do
  run_dir="$RUNS/20260804-${pipeline}-stratified-200"
  phase "CORE-200 prepare $pipeline 200 pages"
  prepare_run "$run_dir" 200
  phase "CORE-200 parse $pipeline 200 pages"
  parse_run "$run_dir" "$pipeline"
  phase "CORE-200 official score $pipeline 200 pages"
  score_run "$run_dir" "scorer-output"
done

run_dir="$RUNS/20260804-precision-full-1651"
phase "FULL prepare precision 1651 pages"
prepare_run "$run_dir" 1651
phase "FULL reuse overlapping precision predictions from 20/200-page runs"
python3 "$BENCH/run_stage1.py" reuse \
  --run-dir "$run_dir" \
  --source-run "$RUNS/20260804-precision-stratified-200" \
  --source-run "$RUNS/20260803-precision-smoke-20"
phase "FULL verify externally completed precision 1651 parse; do not parse again"
python3 "$BENCH/run_stage1.py" verify \
  --run-dir "$run_dir" \
  --pipeline precision
phase "FULL official score precision 1651 pages"
score_run "$run_dir" "scorer-output"

phase "RECORD OmniDocBench results to XLSX and Markdown"
"$BENCH/finalize_experiment_results.sh"

phase "COMPLETED OmniDocBench precision 1651 + precision/agent 200 evaluation"
trap - EXIT
