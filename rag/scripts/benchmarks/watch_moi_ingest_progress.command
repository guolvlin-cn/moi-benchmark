#!/bin/zsh

# Usage:
#   zsh scripts/benchmarks/watch_moi_ingest_progress.command [run_dir] [go_pid]
#
# This is a read-only monitor. It does not start, stop, or modify ingestion.

setopt NO_NOMATCH

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
RUN_DIR="${1:-}"
CHILD_PID="${2:-}"

if [[ -z "$RUN_DIR" ]]; then
  RUN_DIR=$(find "$ROOT/runs/stage1/moi-rag-native" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort | tail -1)
fi
if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  print "No benchmark run directory found."
  exit 1
fi

INDEX_ROOT="$RUN_DIR/datasets/mmdocir/index-run"
DB="moi_stage1_mmdocir"
TABLE="embedding_results"

if [[ -z "$CHILD_PID" ]]; then
  CHILD_PID=$(pgrep -f "local-matrixflow-rag ingest.*$RUN_DIR" | tail -1)
fi

while true; do
  clear
  print "MOI MMDocIR ingestion monitor"
  print "run: $RUN_DIR"
  print "time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  print ""

  PROGRESS=$(find "$INDEX_ROOT" -mindepth 2 -maxdepth 2 -name ingest-progress.json -type f -print 2>/dev/null | sort | tail -1)
  CHILD_RUN="${PROGRESS:h}"
  print "active child: $CHILD_RUN"
  print "progress file: $PROGRESS"
  print ""
  if [[ -f "$PROGRESS" ]]; then
    jq -r '"stage=" + (.stage // "unknown") +
      "  embedded=" + ((.embedded_entries // 0) | tostring) + "/" + ((.total_entries // 0) | tostring) +
      "  committed=" + ((.committed_entries // 0) | tostring) +
      "  expanded=" + ((.expanded_entries // 0) | tostring) +
      "  batch=" + ((.batch_start // 0) | tostring) + "-" + ((.batch_end // 0) | tostring)' "$PROGRESS"
  else
    print "stage=preparing (progress file not created yet)"
  fi

  DB_COUNT=$(mysql --protocol=tcp -h127.0.0.1 -P6001 -uroot -p111 -Nse \
    "SELECT COUNT(*) FROM ${DB}.${TABLE}" 2>/dev/null || print "unavailable")
  print "committed_rows=$DB_COUNT"
  if [[ -n "$CHILD_PID" ]]; then
    ps -o pid,state,etime,%cpu,%mem,command -p "$CHILD_PID" 2>/dev/null | tail -n +2 || print "child process finished"
  fi

  if [[ -n "$CHILD_PID" ]] && ! kill -0 "$CHILD_PID" 2>/dev/null; then
    print ""
    print "MMDocIR child process finished. The terminal will remain open."
    break
  fi
  sleep 5
done

read -k 1 '?Press any key to close this monitor...'
print
