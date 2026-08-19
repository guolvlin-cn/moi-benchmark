#!/bin/zsh
set -Eeuo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
SOURCE_DIR="$ROOT/prototypes/local-matrixflow-rag"
PARSED="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/mmdocrag/moi-documents.jsonl"
CONFIG="$SOURCE_DIR/config.mmdocrag.maas.json"
RUN_ROOT="$ROOT/runs/stage1/mmdocrag-taas-ingest"
RECOVERY_DIR="$RUN_ROOT/recovery"
GO_BIN="$RUN_ROOT/local-matrixflow-rag-maas-parallel"
LOG_FILE="$RUN_ROOT/resume-maas-parallel.log"
BUILD_CACHE="$ROOT/tmp/go-build-cache-mmdocrag-maas-parallel"

mkdir -p "$RUN_ROOT" "$RECOVERY_DIR" "$BUILD_CACHE"
export GOCACHE="$BUILD_CACHE"

if pgrep -f "local-matrixflow-rag.* ingest .*config.mmdocrag.maas.json" >/dev/null 2>&1; then
  print -u2 "An MMDocRAG ingest worker is already running; refusing concurrent database writers."
  exit 1
fi

PROGRESS="${1:-}"
if [[ -z "$PROGRESS" ]]; then
  PROGRESS=$(find "$RECOVERY_DIR" -maxdepth 1 -name 'resume-progress-parallel-*.json' -type f -print 2>/dev/null | sort | tail -1)
fi
if [[ -z "$PROGRESS" || ! -f "$PROGRESS" ]]; then
  print -u2 "No parallel MMDocRAG recovery checkpoint found under $RECOVERY_DIR"
  exit 1
fi
if [[ ! -f "$PARSED" ]]; then
  print -u2 "MMDocRAG parsed corpus is missing: $PARSED"
  exit 1
fi

EXPECTED=$(jq -r '.committed_entries' "$PROGRESS")
TOTAL=$(jq -r '.total_entries' "$PROGRESS")
CONCURRENCY=$(jq -r '.embedding_concurrency // 1' "$CONFIG")
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

print "Building concurrent MMDocRAG ingester..."
cd "$SOURCE_DIR"
go build -o "$GO_BIN" .
cd "$ROOT"

print "Starting MMDocRAG from $EXPECTED/$TOTAL with embedding_concurrency=$CONCURRENCY"
print "Log: $LOG_FILE"
exec "$GO_BIN" ingest \
  --config "$CONFIG" \
  --documents "$PARSED" \
  --run "$RUN_ROOT" \
  --resume-progress "$PROGRESS" 2>&1 | tee "$LOG_FILE"
