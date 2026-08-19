#!/bin/zsh
set -Eeuo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
PARSED="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/mmdocrag/moi-documents.jsonl"
CONFIG="$ROOT/prototypes/local-matrixflow-rag/config.mmdocrag.maas.json"
RUN_ROOT="$ROOT/runs/stage1/mmdocrag-taas-ingest"
PROGRESS="$RUN_ROOT/recovery/resume-progress-20260810-151459.json"
GO_BIN="$RUN_ROOT/local-matrixflow-rag-maas"
LOG_FILE="$RUN_ROOT/resume-maas-runner.log"
BUILD_CACHE="$ROOT/tmp/go-build-cache-mmdocrag-taas-ingest"

mkdir -p "$RUN_ROOT" "$BUILD_CACHE"
export GOCACHE="$BUILD_CACHE"

if [[ -z "$PROGRESS" || ! -f "$PROGRESS" ]]; then
  print -u2 "MMDocRAG checkpoint not found under $RUN_ROOT"
  exit 1
fi
if [[ ! -f "$PARSED" ]]; then
  print -u2 "MMDocRAG parsed corpus is missing: $PARSED"
  exit 1
fi

EXPECTED=$(jq -r '.committed_entries' "$PROGRESS")
STAGE=$(jq -r '.stage' "$PROGRESS")
if [[ "$STAGE" == "committed" ]]; then
  print "MMDocRAG is already committed."
  exit 0
fi
ACTUAL=$(/opt/homebrew/opt/mysql-client/bin/mysql --protocol=tcp -h127.0.0.1 -P6001 -uroot -p111 -Nse \
  'SELECT COUNT(*) FROM moi_stage1_mmdocrag.embedding_results')
if [[ "$ACTUAL" -ne "$EXPECTED" ]]; then
  print -u2 "Refusing resume: MatrixOne rows=$ACTUAL but checkpoint=$EXPECTED"
  exit 1
fi

set -a
source "$ROOT/.env"
set +a
if [[ -z "${MAAS_API_KEY:-}" ]]; then
  print -u2 "MAAS_API_KEY is not set in $ROOT/.env"
  exit 1
fi

print "MMDocRAG resume checkpoint: $EXPECTED"
print "Testing direct Huawei MaaS embedding route (proxy disabled)..."
SMOKE=$(curl --noproxy '*' -fsS --max-time 60 \
  -H "Authorization: Bearer $MAAS_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","input":["MMDocRAG resume smoke"]}' \
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

if [[ ! -x "$GO_BIN" ]]; then
  cd "$ROOT/prototypes/local-matrixflow-rag"
  go build -o "$GO_BIN" .
  cd "$ROOT"
fi

print "Resuming MMDocRAG Huawei MaaS ingestion; log=$LOG_FILE"
exec "$GO_BIN" ingest \
  --config "$CONFIG" \
  --documents "$PARSED" \
  --run "$RUN_ROOT" \
  --resume-progress "$PROGRESS" 2>&1 | tee "$LOG_FILE"
