#!/usr/bin/env bash
set -euo pipefail

prototype_dir=$(cd "$(dirname "$0")" && pwd)
rag_root=$(cd "$prototype_dir/../.." && pwd)
run_root="$rag_root/runs/stage1/mmdocir/20260806-161153-full-1658"
prepared="$run_root/artifacts/prepared"
checkpoint=$(find "$run_root/layout" -name progress.json -type f | sort | tail -1)
resume_id=$(date '+%Y%m%d-%H%M%S')
mkdir -p "$run_root/layout/resume-$resume_id" "$run_root/logs"
if [[ -z "$checkpoint" ]]; then
  echo "no MMDocIR layout progress checkpoint found under $run_root/layout" >&2
  exit 1
fi
rm -f "$run_root/PAUSED" "$run_root/FAILED" "$run_root/DONE"
trap 'touch "$run_root/FAILED"' ERR

set -a
source "$rag_root/.env"
set +a

(cd "$prototype_dir" && go build -o "$run_root/local-matrixflow-rag" .)

watch_command="'$prototype_dir/watch_mmdocir_official.sh' '$run_root'"
osascript -e 'tell application "Terminal" to activate' \
  -e "tell application \"Terminal\" to do script \"$watch_command\""

"$run_root/local-matrixflow-rag" mmdocir-ingest \
  --config "$prototype_dir/config.mmdocir-official-layouts.maas.json" \
  --candidates "$prepared/layouts.jsonl" \
  --resume-progress "$checkpoint" \
  --run "$run_root/layout/resume-$resume_id" >>"$run_root/logs/layout.log" 2>&1

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
