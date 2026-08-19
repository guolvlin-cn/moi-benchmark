#!/bin/zsh

# Read-only DocBench evaluation monitor.
# Usage: zsh scripts/benchmarks/watch_docbench_eval_progress.command <run_dir>

setopt NO_NOMATCH

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
RUN_DIR="${1:-}"

if [[ -z "$RUN_DIR" ]]; then
  RUN_DIR=$(find "$ROOT/runs/stage1/moi-rag-native" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort | tail -1)
fi
if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  print "No MOI evaluation run directory found."
  exit 1
fi

MANIFEST="$RUN_DIR/manifest.json"
STATE="$RUN_DIR/state.json"
EVENTS="$RUN_DIR/events.jsonl"

while true; do
  clear
  print "MOI DocBench full evaluation monitor"
  print "run: $RUN_DIR"
  print "time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  print ""

  if [[ -f "$MANIFEST" ]]; then
    jq -r '"run_status=" + (.status // "unknown") +
      "  split=" + ((.datasets.docbench.preparation.split // "unknown")|tostring) +
      "  planned=" + ((.datasets.docbench.preparation.questions // 0)|tostring)' "$MANIFEST"
  fi
  if [[ -f "$STATE" ]]; then
    jq -r '"stage=" + (.stage // "unknown") + "  state=" + (.status // "unknown")' "$STATE"
  fi
  print ""

  RESULT=$(find "$RUN_DIR/datasets/docbench/query-run" -name results.jsonl -type f -print 2>/dev/null | sort | tail -1)
  if [[ -n "$RESULT" && -f "$RESULT" ]]; then
    jq -s -r '"query_completed=" + (length|tostring) +
      "  ok=" + (map(select(.status == "ok"))|length|tostring) +
      "  failed=" + (map(select(.status != "ok"))|length|tostring)' "$RESULT"
  else
    print "query_completed=0  ok=0  failed=0"
  fi

  JUDGE="$RUN_DIR/datasets/docbench/judgements.jsonl"
  if [[ -f "$JUDGE" ]]; then
    jq -s -r '"judge_completed=" + (length|tostring) +
      "  ok=" + (map(select(.status != "fail" and (.score == 0 or .score == 1)))|length|tostring) +
      "  fail=" + (map(select(.status == "fail"))|length|tostring) +
      "  score1=" + (map(select(.score == 1))|length|tostring) +
      "  score0=" + (map(select(.score == 0))|length|tostring)' "$JUDGE"
  else
    print "judge_completed=0  ok=0  fail=0  score1=0  score0=0"
  fi

  DB_COUNT=$(/opt/homebrew/opt/mysql-client/bin/mysql --protocol=tcp -h127.0.0.1 -P6001 -uroot -p111 -Nse \
    'SELECT COUNT(*) FROM moi_stage1_docbench.embedding_results' 2>/dev/null || print unavailable)
  print "docbench_index_rows=$DB_COUNT"
  QIANFAN_ENV="$ROOT/.local-services/providers/qianfan.env"
  if [[ -n "${QIANFAN_API_KEY:-}" ]]; then
    print "qianfan_key=available_in_monitor_env"
  elif [[ -f "$QIANFAN_ENV" ]]; then
    print "qianfan_key=configured_in=$QIANFAN_ENV"
  else
    print "qianfan_key=not_configured"
  fi
  print ""

  if [[ -f "$EVENTS" ]]; then
    print "last_event:"
    tail -1 "$EVENTS" | jq -r '.message' 2>/dev/null || tail -1 "$EVENTS"
  fi
  print ""
  ps -axo pid,etime,state,%cpu,command | rg -i 'moi_rag_benchmark.py|local_matrixflow_rag.py run' | rg -v 'rg -i' | head -8 || print "no active evaluation worker"

  STATUS=$(jq -r '.status // "running"' "$MANIFEST" 2>/dev/null)
  if [[ "$STATUS" == "succeeded" || "$STATUS" == "paused_api_error" || "$STATUS" == "failed" || "$STATUS" == "interrupted" ]]; then
    print ""
    print "terminal state: $STATUS; monitor will remain open."
    break
  fi
  sleep 5
done

read -k 1 '?Press any key to close this monitor...'
print
