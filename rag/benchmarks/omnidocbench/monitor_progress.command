#!/usr/bin/env bash
set -u

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
RUNS="$ROOT/runs/stage1/omnidocbench"
STATUS="$RUNS/LIVE-STATUS.txt"
LOG="$RUNS/full-evaluation.log"

while true; do
  clear
  echo "OmniDocBench Stage 1 — live progress"
  echo "Updated: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  echo "Current phase:"
  if [[ -f "$STATUS" ]]; then
    cat "$STATUS"
  else
    echo "Waiting for evaluation process to initialize..."
  fi
  echo
  python3 - "$RUNS" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
names = [
    "20260803-precision-smoke-20",
    "20260803-agent-smoke-20",
    "20260804-precision-stratified-200",
    "20260804-agent-stratified-200",
    "20260804-precision-full-1651",
]
print(f"{'Run':42} {'Parse':>16} {'Official score':>18}")
print("-" * 80)
for name in names:
    run = root / name
    progress_path = run / "moi-unified" / "progress.json"
    metrics_path = run / "moi-unified" / "metrics.json"
    progress = None
    for path in (progress_path, metrics_path):
        if path.is_file():
            try:
                progress = json.loads(path.read_text())
                break
            except Exception:
                pass
    if progress:
        planned = progress.get("planned_pages", 0)
        done = progress.get("completed_pages", progress.get("accepted_pages", 0))
        accepted = progress.get("accepted_pages", 0)
        failed = progress.get("failed_pages", planned - accepted if done == planned else 0)
        parse_state = f"{done}/{planned} ok={accepted} err={failed}"
    else:
        parse_state = "not started"
    summaries = list((run / "official").glob("scorer-output*/predictions_quick_match_run_summary.json")) if run.exists() else []
    score_state = "complete" if summaries else "pending"
    print(f"{name:42} {parse_state:>16} {score_state:>18}")
PY
  echo
  echo "Latest log lines:"
  echo "--------------------------------------------------------------------------------"
  if [[ -f "$LOG" ]]; then
    tail -n 18 "$LOG"
  fi

  if [[ -f "$STATUS" ]] && grep -q '^COMPLETED\|^FAILED_OR_INTERRUPTED' "$STATUS"; then
    echo
    echo "Evaluation stopped at the status shown above. Press Enter to close this terminal."
    read -r
    exit 0
  fi
  sleep 5
done
