#!/usr/bin/env bash
set -euo pipefail

prototype_dir=$(cd "$(dirname "$0")" && pwd)
rag_root=$(cd "$prototype_dir/../.." && pwd)
run_id=$(date '+%Y%m%d-%H%M%S')
run_root="$rag_root/runs/stage1/mmdocir/$run_id-full-1658"
prepared="$run_root/artifacts/prepared"
mkdir -p "$run_root/logs" "$run_root/page" "$run_root/layout"
trap 'touch "$run_root/FAILED"' ERR

set -a
source "$rag_root/.env"
set +a

python3 "$prototype_dir/prepare_mmdocir_official.py" \
  --data "$rag_root/datasets/downloads/document-rag/mmdocir/data" \
  --output "$prepared" \
  --sample-queries 0 \
  --seed 20260806 | tee "$run_root/logs/prepare.log"

(cd "$prototype_dir" && go build -o "$run_root/local-matrixflow-rag" .)

watch_command="'$prototype_dir/watch_mmdocir_official.sh' '$run_root'"
osascript -e 'tell application "Terminal" to activate' \
  -e "tell application \"Terminal\" to do script \"$watch_command\""

"$run_root/local-matrixflow-rag" mmdocir-ingest \
  --config "$prototype_dir/config.mmdocir-official-pages.maas.json" \
  --candidates "$prepared/pages.jsonl" --force \
  --run "$run_root/page/ingest" >"$run_root/logs/page.log" 2>&1

"$run_root/local-matrixflow-rag" mmdocir-ingest \
  --config "$prototype_dir/config.mmdocir-official-layouts.maas.json" \
  --candidates "$prepared/layouts.jsonl" --force \
  --run "$run_root/layout/ingest" >"$run_root/logs/layout.log" 2>&1

"$run_root/local-matrixflow-rag" mmdocir-run \
  --config "$prototype_dir/config.mmdocir-official-pages.maas.json" \
  --questions "$prepared/questions.jsonl" --granularity page \
  --run "$run_root/page/eval" >>"$run_root/logs/page.log" 2>&1

"$run_root/local-matrixflow-rag" mmdocir-run \
  --config "$prototype_dir/config.mmdocir-official-layouts.maas.json" \
  --questions "$prepared/questions.jsonl" --granularity layout \
  --run "$run_root/layout/eval" >>"$run_root/logs/layout.log" 2>&1

touch "$run_root/DONE"
echo "run_root=$run_root"
