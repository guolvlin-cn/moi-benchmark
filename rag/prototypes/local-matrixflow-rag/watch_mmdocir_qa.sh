#!/usr/bin/env bash
set -euo pipefail

run_root=${1:?usage: watch_mmdocir_qa.sh RUN_ROOT}
results="$run_root/results.jsonl"
log="$run_root/run.log"
total=$(wc -l < "$run_root/questions.jsonl" | tr -d ' ')

while true; do
  done_count=0
  result_file="$results"
  if [[ ! -f "$result_file" ]]; then
    result_file=$(find "$run_root" -maxdepth 2 -name results.jsonl -type f -print -quit 2>/dev/null || true)
  fi
  if [[ -n "$result_file" && -f "$result_file" ]]; then
    done_count=$(wc -l < "$result_file" | tr -d ' ')
  fi
  failed=0
  if [[ -n "$result_file" && -f "$result_file" ]]; then
    failed=$(rg -c '"status":"failed"' "$result_file" || true)
  fi
  if [[ -f "$run_root/DONE" ]]; then state=DONE;
  elif [[ -f "$run_root/FAILED" ]]; then state=FAILED;
  elif [[ -f "$run_root/PAUSED" ]]; then state=PAUSED;
  else state=RUNNING; fi
  printf '\033[2J\033[H'
  echo "MMDocIR MOI QA"
  echo "run_root: $run_root"
  echo "status: $state"
  echo "progress: $done_count/$total"
  echo "failed: $failed"
  if [[ -f "$run_root/qa-summary.json" ]]; then
    echo
    sed -n '1,80p' "$run_root/qa-summary.json"
  fi
  echo
  echo "last log lines:"
  if [[ -f "$log" ]]; then tail -n 5 "$log"; else echo "waiting for log"; fi
  if [[ "$state" != RUNNING ]]; then break; fi
  sleep 5
done
