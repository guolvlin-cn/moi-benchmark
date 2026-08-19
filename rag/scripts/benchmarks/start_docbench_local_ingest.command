#!/bin/zsh
set -Eeuo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
PARSED="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/docbench/moi-documents.jsonl"
SUMMARY="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/docbench/summary.json"
CONFIG="$ROOT/prototypes/local-matrixflow-rag/config.docbench.local-bge-m3.json"
RUN_ROOT="$ROOT/runs/stage1/docbench-local-ingest"
GO_BIN="$RUN_ROOT/local-matrixflow-rag"
LOG_FILE="$RUN_ROOT/runner.log"
BUILD_CACHE="$ROOT/tmp/go-build-cache-docbench-ingest"
BGE_ROOT="$ROOT/prototypes/local-bge-m3-embedding"

mkdir -p "$RUN_ROOT" "$BUILD_CACHE"
export GOCACHE="$BUILD_CACHE"

if [[ ! -f "$PARSED" || ! -f "$SUMMARY" ]]; then
  print -u2 "DocBench parsed corpus is missing: $PARSED"
  exit 1
fi

python3 - "$SUMMARY" "$PARSED" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
records = [
    json.loads(line)
    for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()
    if line.strip()
]
if summary.get("planned_documents") != 229 or summary.get("successful_documents") != 229:
    raise SystemExit(f"DocBench parse is incomplete: {summary}")
if summary.get("failed_documents", 0) != 0 or len(records) == 0:
    raise SystemExit(f"DocBench parsed corpus has failures or no blocks: {summary}")
print(
    f"DocBench parse ready: documents={summary['successful_documents']} "
    f"blocks={summary['moi_document_blocks']} images={summary.get('images_validated', 0)}"
)
PY

if ! curl -fsS --max-time 5 http://127.0.0.1:8081/readyz >/dev/null 2>&1; then
  print "Local BGE-M3 is not ready; starting it in the background."
  nohup zsh "$BGE_ROOT/start_local_bge_m3.command" >"$RUN_ROOT/local-bge-m3.log" 2>&1 &
  BGE_PID=$!
  for _ in {1..180}; do
    if curl -fsS --max-time 5 http://127.0.0.1:8081/readyz >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$BGE_PID" 2>/dev/null; then
      print -u2 "Local BGE-M3 exited before becoming ready; see $RUN_ROOT/local-bge-m3.log"
      exit 1
    fi
    sleep 2
  done
fi
curl -fsS --max-time 5 http://127.0.0.1:8081/readyz >/dev/null
print "Local BGE-M3 is ready at http://127.0.0.1:8081"

cd "$ROOT/prototypes/local-matrixflow-rag"
go build -o "$GO_BIN" .
cd "$ROOT"

print "Starting DocBench local MOI ingestion; log=$LOG_FILE"
print "Database: moi_stage1_docbench.embedding_results"
print "Embedding: local BGE-M3 (no TaaS embedding request)"
exec "$GO_BIN" ingest \
  --config "$CONFIG" \
  --documents "$PARSED" \
  --run "$RUN_ROOT" \
  --force 2>&1 | tee "$LOG_FILE"
