#!/bin/zsh
set -u

RAG_ROOT=/Users/muuushroom/gitrepos/moi-benchmark/rag
PROGRESS_FILE="$RAG_ROOT/outputs/parsed-documents/moi-ready-v1/progress.json"
REPORT_FILE="$RAG_ROOT/outputs/parsed-documents/moi-ready-v1/REPORT.md"
PYTHON_BIN=/usr/bin/python3

while true; do
  clear
  echo "MOI benchmark document parsing progress"
  date '+%Y-%m-%d %H:%M:%S %Z'
  echo
  if [ ! -f "$PROGRESS_FILE" ]; then
    echo "Waiting for $PROGRESS_FILE"
    sleep 3
    continue
  fi
  "$PYTHON_BIN" - "$PROGRESS_FILE" <<'PY'
import datetime
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
planned = data.get("planned", 0)
succeeded = data.get("succeeded", 0)
failed = data.get("failed", 0)
running = data.get("running", 0)
completed = succeeded + failed
percent = completed * 100 / planned if planned else 0
updated = datetime.datetime.fromtimestamp(data.get("updated_at_epoch", 0)).astimezone()
print(f"Status:    {data.get('status')}")
print(f"Overall:   {completed}/{planned} ({percent:.2f}%)")
print(f"Succeeded: {succeeded}    Failed: {failed}    Running: {running}")
print(f"Updated:   {updated:%Y-%m-%d %H:%M:%S %Z}")
print("\nDatasets")
print(f"{'dataset':22} {'done/planned':>16} {'running':>8} {'failed':>8} {'reused':>8}")
for name, row in sorted(data.get("datasets", {}).items()):
    done = row.get("succeeded", 0) + row.get("failed", 0)
    print(f"{name:22} {done:7}/{row.get('planned', 0):<7} {row.get('running', 0):8} {row.get('failed', 0):8} {row.get('reused', 0):8}")
print("\nTool invocations (retries count separately)")
for name, count in sorted(data.get("tool_invocations", {}).items()):
    print(f"  {name:38} {count:8}")
PY
  echo
  echo "Output: $RAG_ROOT/outputs/parsed-documents/moi-ready-v1"
  if [ -f "$REPORT_FILE" ]; then
    echo "Final report: $REPORT_FILE"
  fi
  sleep 5
done
