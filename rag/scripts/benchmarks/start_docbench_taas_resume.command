#!/bin/zsh
set -Eeuo pipefail

ROOT="/Users/muuushroom/gitrepos/moi-benchmark/rag"
PARSED="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/docbench/moi-documents.jsonl"
SUMMARY="$ROOT/outputs/parsed-documents/moi-ready-v1/datasets/docbench/summary.json"
CONFIG="$ROOT/prototypes/local-matrixflow-rag/config.docbench.maas.json"
OLD_PROGRESS=$(find "$ROOT/runs/stage1/docbench-local-ingest" -mindepth 2 -maxdepth 2 -name ingest-progress.json -type f -print 2>/dev/null | sort | tail -1)
RUN_ROOT="$ROOT/runs/stage1/docbench-taas-ingest"
LOG_FILE="$RUN_ROOT/runner.log"
GO_BIN="$RUN_ROOT/local-matrixflow-rag"
BUILD_CACHE="$ROOT/tmp/go-build-cache-docbench-taas-ingest"

mkdir -p "$RUN_ROOT" "$BUILD_CACHE"
export GOCACHE="$BUILD_CACHE"

if [[ ! -f "$PARSED" || ! -f "$SUMMARY" ]]; then
  print -u2 "DocBench parsed corpus is missing: $PARSED"
  exit 1
fi
if [[ -z "$OLD_PROGRESS" || ! -f "$OLD_PROGRESS" ]]; then
  print -u2 "No local DocBench ingest checkpoint found; refusing to start a non-resumable Huawei MaaS run."
  exit 1
fi

python3 - "$SUMMARY" "$PARSED" "$OLD_PROGRESS" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
blocks = sum(1 for line in Path(sys.argv[2]).open(encoding="utf-8") if line.strip())
progress = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
if summary.get("planned_documents") != 229 or summary.get("successful_documents") != 229:
    raise SystemExit(f"DocBench parse is incomplete: {summary}")
if summary.get("failed_documents", 0) != 0 or blocks == 0:
    raise SystemExit(f"DocBench parsed corpus has failures or no blocks: {summary}")
if progress.get("stage") == "committed":
    raise SystemExit(f"DocBench ingest is already committed: {sys.argv[3]}")
if progress.get("embedded_entries") != progress.get("committed_entries"):
    raise SystemExit(f"Checkpoint is not at a committed boundary: {progress}")
print(
    f"DocBench resume ready: parsed_blocks={blocks} "
    f"resume_from={progress.get('committed_entries')} total={progress.get('total_entries')}"
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
  -d '{"model":"bge-m3","input":["DocBench Huawei MaaS embedding smoke"]}' \
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

print "Resuming DocBench ingestion with Huawei MaaS; log=$LOG_FILE"
print "Database: moi_stage1_docbench.embedding_results"
print "Resume checkpoint: $OLD_PROGRESS"
print "Embedding: Huawei MaaS bge-m3 (direct route, no system proxy)"
exec "$GO_BIN" ingest \
  --config "$CONFIG" \
  --documents "$PARSED" \
  --run "$RUN_ROOT" \
  --resume-progress "$OLD_PROGRESS" 2>&1 | tee "$LOG_FILE"
