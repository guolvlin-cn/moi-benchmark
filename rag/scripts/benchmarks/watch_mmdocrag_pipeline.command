#!/bin/zsh

# Live, read-only monitor for the DocBench -> MMDocRAG handoff.
# Usage: zsh scripts/benchmarks/watch_mmdocrag_pipeline.command

setopt NO_NOMATCH
ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
DOCBENCH_ROOT="$ROOT/runs/stage1/docbench-taas-ingest"
MMDOCRAG_ROOT="$ROOT/runs/stage1/mmdocrag-taas-ingest"

while true; do
  clear
  print "MOI Stage-1: DocBench -> MMDocRAG"
  print "time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  print ""

  DOC_PROGRESS=$(find "$DOCBENCH_ROOT" -mindepth 2 -maxdepth 2 -name ingest-progress.json -type f -print 2>/dev/null | sort | tail -1)
  print "[DocBench]"
  if [[ -f "$DOC_PROGRESS" ]]; then
    jq -r '"stage=" + (.stage // "unknown") +
      "  embedded=" + ((.embedded_entries // 0) | tostring) + "/" + ((.total_entries // 0) | tostring) +
      "  committed=" + ((.committed_entries // 0) | tostring)' "$DOC_PROGRESS"
  else
    print "stage=waiting"
  fi
  DOC_ROWS=$(/opt/homebrew/opt/mysql-client/bin/mysql --protocol=tcp -h127.0.0.1 -P6001 -uroot -p111 -Nse \
    'SELECT COUNT(*) FROM moi_stage1_docbench.embedding_results' 2>/dev/null || print unavailable)
  print "rows=$DOC_ROWS"
  print ""

  print "[MMDocRAG parser]"
  if [[ -f "$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/mmdocrag/summary.json" ]]; then
    jq -r '"documents=" + ((.successful_documents // 0) | tostring) + "/" + ((.planned_documents // 0) | tostring) +
      "  failed=" + ((.failed_documents // 0) | tostring) +
      "  blocks=" + ((.moi_document_blocks // 0) | tostring)' \
      "$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/mmdocrag/summary.json"
  else
    print "status=waiting"
  fi
  print ""

  print "[MMDocRAG MOI ingest]"
  MM_PROGRESS=$(find "$MMDOCRAG_ROOT" -mindepth 2 -maxdepth 2 -name ingest-progress.json -type f -print 2>/dev/null | sort | tail -1)
  if [[ -f "$MM_PROGRESS" ]]; then
    jq -r '"stage=" + (.stage // "unknown") +
      "  embedded=" + ((.embedded_entries // 0) | tostring) + "/" + ((.total_entries // 0) | tostring) +
      "  committed=" + ((.committed_entries // 0) | tostring)' "$MM_PROGRESS"
    MM_ROWS=$(/opt/homebrew/opt/mysql-client/bin/mysql --protocol=tcp -h127.0.0.1 -P6001 -uroot -p111 -Nse \
      'SELECT COUNT(*) FROM moi_stage1_mmdocrag.embedding_results' 2>/dev/null || print unavailable)
    print "rows=$MM_ROWS"
  else
    print "stage=waiting for DocBench completion"
  fi
  print ""

  if [[ -f "$MM_PROGRESS" ]] && jq -e '.stage == "committed"' "$MM_PROGRESS" >/dev/null 2>&1; then
    print "MMDocRAG local MOI ingestion is complete."
    break
  fi
  sleep 5
done

read -k 1 '?Press any key to close this monitor...'
print
