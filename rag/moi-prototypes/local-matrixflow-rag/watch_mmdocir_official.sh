#!/usr/bin/env bash
set -u

run_root="${1:?usage: watch_mmdocir_official.sh RUN_ROOT}"

while true; do
  clear
  date '+MMDocIR watcher  %Y-%m-%d %H:%M:%S'
  echo "run_root=$run_root"
  echo
  for lane in page layout; do
    echo "[$lane]"
    progress=$(find "$run_root/$lane" -name progress.json -type f 2>/dev/null | sort | tail -1)
    metrics=$(find "$run_root/$lane" -name metrics.json -type f 2>/dev/null | sort | tail -1)
    log="$run_root/logs/$lane.log"
    if [[ -n "$progress" ]]; then
      python3 - "$progress" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]))
print("index stage={stage} embedded={embedded}/{total} committed={committed} elapsed={elapsed_seconds:.1f}s".format(**p))
PY
    fi
    if [[ -n "$metrics" ]]; then
      python3 - "$metrics" <<'PY'
import json, sys
m=json.load(open(sys.argv[1]))
print(f"queries={m['attempts']} ok={m['successful_attempts']} failed={m['failed_attempts']} recall={m['recall_at_k']} p95={m['latency_p95_ms']:.2f}ms")
PY
    fi
    if [[ -f "$log" ]]; then
      tail -2 "$log"
    else
      echo "waiting"
    fi
    echo
  done
  if [[ -f "$run_root/DONE" || -f "$run_root/FAILED" ]]; then
    echo "status=$(basename "$(find "$run_root" -maxdepth 1 -name DONE -o -name FAILED | head -1)")"
    break
  fi
  sleep 2
done

echo
echo "Watcher stopped. This terminal can be closed."
