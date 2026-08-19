#!/bin/zsh

# Read-only progress monitor for DocBench local parsing/ingestion.
# Usage: zsh scripts/benchmarks/watch_docbench_local_ingest.command [run-root]

setopt NO_NOMATCH
ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
RUN_ROOT="${1:-$ROOT/runs/stage1/docbench-local-ingest}"
DB="moi_stage1_docbench"
TABLE="embedding_results"

while true; do
  clear
  print "MOI DocBench local ingestion"
  print "root: $RUN_ROOT"
  print "time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  print ""

  PROGRESS=$(find "$RUN_ROOT" -mindepth 2 -maxdepth 2 -name ingest-progress.json -type f -print 2>/dev/null | sort | tail -1)
  CHILD_RUN="${PROGRESS:h}"
  print "active child: ${CHILD_RUN:-preparing}"
  print "progress file: ${PROGRESS:-not created}"
  if [[ -n "$PROGRESS" && -f "$PROGRESS" ]]; then
    jq -r '"stage=" + (.stage // "unknown") +
      "  embedded=" + ((.embedded_entries // 0) | tostring) + "/" + ((.total_entries // 0) | tostring) +
      "  committed=" + ((.committed_entries // 0) | tostring) +
      "  expanded=" + ((.expanded_entries // 0) | tostring) +
      "  batch=" + ((.batch_start // 0) | tostring) + "-" + ((.batch_end // 0) | tostring)' "$PROGRESS"
  else
    print "stage=preparing (progress file not created yet)"
  fi

  DB_COUNT=$(/opt/homebrew/opt/mysql-client/bin/mysql --protocol=tcp -h127.0.0.1 -P6001 -uroot -p111 -Nse \
    "SELECT COUNT(*) FROM ${DB}.${TABLE}" 2>/dev/null || print "unavailable")
  print "committed_rows=$DB_COUNT"
  print ""
  if [[ -f "$RUN_ROOT/runner.log" ]]; then
    print "last log lines:"
    tail -n 5 "$RUN_ROOT/runner.log"
  fi

  if [[ -n "$PROGRESS" ]] && jq -e '.stage == "committed"' "$PROGRESS" >/dev/null 2>&1; then
    print ""
    print "DocBench local MOI ingestion is complete."
    break
  fi
  sleep 5
done

read -k 1 '?Press any key to close this monitor...'
print
