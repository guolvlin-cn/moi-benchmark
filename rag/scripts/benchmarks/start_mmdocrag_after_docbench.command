#!/bin/zsh
set -Eeuo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
DOCBENCH_ROOT="$ROOT/runs/stage1/docbench-taas-ingest"
DOCBENCH_PROGRESS=$(find "$DOCBENCH_ROOT" -mindepth 2 -maxdepth 2 -name ingest-progress.json -type f -print 2>/dev/null | sort | tail -1)
MMDOCRAG_PARSED="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/mmdocrag/moi-documents.jsonl"
MMDOCRAG_SUMMARY="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/mmdocrag/summary.json"
CONFIG="$ROOT/prototypes/local-matrixflow-rag/config.mmdocrag.maas.json"
RUN_ROOT="$ROOT/runs/stage1/mmdocrag-taas-ingest"
LOG_FILE="$RUN_ROOT/runner.log"
GO_BIN="$RUN_ROOT/local-matrixflow-rag"
BUILD_CACHE="$ROOT/tmp/go-build-cache-mmdocrag-taas-ingest"

mkdir -p "$RUN_ROOT" "$BUILD_CACHE"
export GOCACHE="$BUILD_CACHE"

print "Waiting for DocBench Huawei MaaS ingestion to commit before starting MMDocRAG..."
while true; do
  DOCBENCH_PROGRESS=$(find "$DOCBENCH_ROOT" -mindepth 2 -maxdepth 2 -name ingest-progress.json -type f -print 2>/dev/null | sort | tail -1)
  if [[ -z "$DOCBENCH_PROGRESS" ]]; then
    print "DocBench progress file is not available yet; retrying..."
    sleep 20
    continue
  fi
  STAGE=$(jq -r '.stage // "unknown"' "$DOCBENCH_PROGRESS")
  EMBEDDED=$(jq -r '.embedded_entries // 0' "$DOCBENCH_PROGRESS")
  TOTAL=$(jq -r '.total_entries // 0' "$DOCBENCH_PROGRESS")
  print "DocBench stage=$STAGE committed=$EMBEDDED/$TOTAL"
  if [[ "$STAGE" == "committed" && "$EMBEDDED" -eq "$TOTAL" ]]; then
    break
  fi
  sleep 20
done

if [[ ! -f "$MMDOCRAG_PARSED" || ! -f "$MMDOCRAG_SUMMARY" ]]; then
  print -u2 "MMDocRAG parsed corpus is missing: $MMDOCRAG_PARSED"
  exit 1
fi

python3 - "$MMDOCRAG_SUMMARY" "$MMDOCRAG_PARSED" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
blocks = sum(1 for line in Path(sys.argv[2]).open(encoding="utf-8") if line.strip())
if summary.get("planned_documents") != 220 or summary.get("successful_documents") != 220:
    raise SystemExit(f"MMDocRAG parse is incomplete: {summary}")
if summary.get("failed_documents", 0) != 0 or blocks == 0:
    raise SystemExit(f"MMDocRAG parsed corpus has failures or no blocks: {summary}")
print(
    f"MMDocRAG parse ready and will be reused: documents=220 "
    f"blocks={blocks} images={summary.get('images_validated', 0)}"
)
PY

set -a
source "$ROOT/.env"
set +a
if [[ -z "${MAAS_API_KEY:-}" ]]; then
  print -u2 "MAAS_API_KEY is not set in $ROOT/.env"
  exit 1
fi

print "Testing direct Huawei MaaS embedding route (proxy disabled)..."
SMOKE=$(curl --noproxy '*' -fsS --max-time 60 \
  -H "Authorization: Bearer $MAAS_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","input":["MMDocRAG Huawei MaaS embedding smoke"]}' \
  https://api.modelarts-maas.com/v1/embeddings)
python3 - "$SMOKE" <<'PY'
import json
import sys
value = json.loads(sys.argv[1])
data = value.get("data") or []
if len(data) != 1 or len(data[0].get("embedding") or []) != 1024:
    raise SystemExit(f"unexpected Huawei MaaS embedding response: {value}")
print("Huawei MaaS embedding smoke passed: 1 vector x 1024 dimensions")
PY

cd "$ROOT/prototypes/local-matrixflow-rag"
go build -o "$GO_BIN" .
cd "$ROOT"

print "Starting MMDocRAG Huawei MaaS ingestion; log=$LOG_FILE"
print "Database: moi_stage1_mmdocrag.embedding_results"
print "Embedding: Huawei MaaS bge-m3 (direct route, no system proxy)"
exec "$GO_BIN" ingest \
  --config "$CONFIG" \
  --documents "$MMDOCRAG_PARSED" \
  --run "$RUN_ROOT" \
  --force 2>&1 | tee "$LOG_FILE"
