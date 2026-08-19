#!/bin/zsh

setopt NO_NOMATCH

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
RUN_ROOT="$ROOT/runs/stage1/mmdocrag-taas-ingest"
LOG_FILE="$RUN_ROOT/resume-maas-runner.log"
MYSQL="/opt/homebrew/opt/mysql-client/bin/mysql"

while true; do
  clear
  print "MMDocRAG -> MOI vector database (Huawei Cloud MaaS bge-m3)"
  print "time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  print "refresh: every 5 seconds"
  print ""

  PROGRESS=$(find "$RUN_ROOT" -mindepth 2 -maxdepth 2 -name ingest-progress.json -type f -print 2>/dev/null | sort | tail -1)
  if [[ -f "$PROGRESS" ]]; then
    jq -r '
      (.total_entries // 0) as $total |
      (.committed_entries // 0) as $done |
      "stage=" + (.stage // "unknown") +
      "\nembedded=" + ((.embedded_entries // 0) | tostring) + "/" + ($total | tostring) +
      "\ncommitted=" + ($done | tostring) + "/" + ($total | tostring) +
      "\nremaining=" + (($total - $done) | tostring) +
      "\npercent=" + (if $total > 0 then (($done * 10000 / $total | floor) / 100 | tostring) else "0" end) + "%"' \
      "$PROGRESS"
    print "progress_file=$PROGRESS"
  else
    print "stage=waiting_for_progress_file"
  fi

  ROWS=$($MYSQL --protocol=tcp -h127.0.0.1 -P6001 -uroot -p111 -Nse \
    'SELECT COUNT(*) FROM moi_stage1_mmdocrag.embedding_results' 2>/dev/null || print unavailable)
  print "database_rows=$ROWS"

  if pgrep -f 'local-matrixflow-rag-maas ingest.*config.mmdocrag.maas.json' >/dev/null 2>&1; then
    print "worker=running"
  else
    print "worker=not_running"
  fi

  print ""
  print "latest log:"
  tail -8 "$LOG_FILE" 2>/dev/null || print "log not available yet"

  if [[ -f "$PROGRESS" ]] && jq -e '.stage == "committed"' "$PROGRESS" >/dev/null 2>&1; then
    print ""
    print "MMDocRAG ingestion completed."
    break
  fi
  sleep 5
done

read -k 1 '?Press any key to close this monitor...'
print
