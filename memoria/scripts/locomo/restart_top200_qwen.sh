#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
RUNTIME_DIR="/Users/wangyaqi/Documents/cursor_project/agent评估/memoria_runtime"
VENV_DIR="/Users/wangyaqi/Documents/cursor_project/.venv"
API_URL="http://127.0.0.1:8100"
PREFLIGHT_RUN_DIR="$REPO_ROOT/memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/mem0-compatible-retrieval-top200-preflight1-v1"
MODE="${1:-preflight}"

if [[ "$MODE" != "preflight" && "$MODE" != "config-only" ]]; then
  echo "Usage: $0 [preflight|config-only]" >&2
  exit 2
fi

source "$VENV_DIR/bin/activate"
set -a
source "$RUNTIME_DIR/.env"
set +a

read -r -s -p "DashScope API key: " DASHSCOPE_API_KEY
echo
if [[ -z "$DASHSCOPE_API_KEY" ]]; then
  echo "DashScope API key cannot be empty." >&2
  exit 1
fi

export MEMORIA_EMBEDDING_PROVIDER="openai"
export MEMORIA_EMBEDDING_MODEL="text-embedding-v4"
export MEMORIA_EMBEDDING_DIM="1024"
export MEMORIA_EMBEDDING_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export MEMORIA_EMBEDDING_API_KEY="$DASHSCOPE_API_KEY"

TMP_DIR="$(mktemp -d /tmp/locomo-top200-qwen.XXXXXX)"
cleanup() {
  unset DASHSCOPE_API_KEY MEMORIA_EMBEDDING_API_KEY
  rm -rf -- "$TMP_DIR"
}
trap cleanup EXIT

cd "$RUNTIME_DIR"
docker compose up -d --no-deps --force-recreate api

ready=0
for _attempt in {1..30}; do
  if curl --fail --silent "$API_URL/health" > /dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "Memoria API did not become healthy within 60 seconds." >&2
  docker compose logs --tail=200 api >&2
  exit 1
fi

curl --fail --silent --show-error "$API_URL/admin/config" \
  -H "Authorization: Bearer $MEMORIA_MASTER_KEY" > "$TMP_DIR/config.json"

python - "$TMP_DIR/config.json" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "embedding_provider": "openai",
    "embedding_model": "text-embedding-v4",
    "embedding_dim": 1024,
    "embedding_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "has_embedding": True,
}
bad = {
    key: (config.get(key), value)
    for key, value in expected.items()
    if config.get(key) != value
}
if bad:
    raise SystemExit(f"Memoria embedding configuration mismatch: {bad}")
print("Memoria configuration accepted: text-embedding-v4 / 1024")
PY

if [[ "$MODE" == "config-only" ]]; then
  echo "Memoria API is ready for LoCoMo ingestion; retrieval preflight skipped."
  exit 0
fi

cd "$REPO_ROOT"
python memoria/scripts/locomo/retrieve.py \
  --limit 1 \
  --workers 1 \
  --run-dir "$PREFLIGHT_RUN_DIR"

python - "$PREFLIGHT_RUN_DIR/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "selected_questions": 1,
    "snapshot_records": 1,
    "valid_retrievals": 1,
    "failed_or_invalid_retrievals": 0,
    "complete": True,
}
bad = {
    key: (summary.get(key), value)
    for key, value in expected.items()
    if summary.get(key) != value
}
if bad:
    raise SystemExit(f"Top-200 preflight failed: {bad}")
print("Top-200 preflight accepted: 1/1 question returned 200 valid memories")
PY

echo "Memoria API is ready for the LoCoMo Top-200 smoke."
