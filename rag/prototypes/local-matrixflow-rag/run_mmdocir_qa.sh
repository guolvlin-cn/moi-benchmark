#!/usr/bin/env bash
set -euo pipefail

prototype_dir=$(cd "$(dirname "$0")" && pwd)
rag_root=$(cd "$prototype_dir/../.." && pwd)
source_run_root="$rag_root/runs/stage1/mmdocir/20260806-161153-full-1658"
run_id=$(date '+%Y%m%d-%H%M%S')
limit="${MMDocIR_QA_LIMIT:-0}"
if [[ "$limit" =~ ^[0-9]+$ && "$limit" -gt 0 ]]; then
  run_suffix="pilot-$limit"
else
  limit=0
  run_suffix="full-1658"
fi
run_root="$rag_root/runs/stage1/mmdocir-qa/$run_id-$run_suffix"
mkdir -p "$run_root"
trap 'touch "$run_root/FAILED"' ERR

set -a
source "$rag_root/.env"
set +a

python3 "$prototype_dir/prepare_mmdocir_qa.py" \
  --input "$source_run_root/artifacts/prepared/questions.jsonl" \
  --output "$run_root/questions.jsonl" \
  --limit "$limit" | tee "$run_root/prepare.json"
cp "$prototype_dir/config.mmdocir-qa.taas.json" "$run_root/config.json"
cp "$source_run_root/artifacts/prepared/manifest.json" "$run_root/source-manifest.json"
cp "$source_run_root/artifacts/prepared/questions.jsonl" "$run_root/official-questions.jsonl"

(cd "$prototype_dir" && go build -o "$run_root/local-matrixflow-rag" .)

watch_command="'$prototype_dir/watch_mmdocir_qa.sh' '$run_root'"
if command -v osascript >/dev/null 2>&1; then
  osascript -e 'tell application "Terminal" to activate' \
    -e "tell application \"Terminal\" to do script \"$watch_command\"" || true
fi

"$run_root/local-matrixflow-rag" mmdocir-qa \
  --config "$run_root/config.json" \
  --questions "$run_root/official-questions.jsonl" \
  --limit "$limit" \
  --max-hits 10 \
  --run "$run_root" >"$run_root/run.log" 2>&1

results=$(find "$run_root" -maxdepth 2 -name results.jsonl -type f | sort | tail -1)
if [[ -z "$results" ]]; then
  echo "results.jsonl not found under $run_root" >&2
  exit 1
fi
ln -sf "$results" "$run_root/results.jsonl"
python3 "$prototype_dir/export_mmdocir_qa_ledger.py" \
  --results "$results" \
  --ledger "$run_root/qa-ledger.jsonl" \
  --summary "$run_root/qa-summary.json" | tee "$run_root/export.json"
touch "$run_root/DONE"
echo "run_root=$run_root"
