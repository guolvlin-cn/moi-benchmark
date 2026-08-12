#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
RUNTIME_DIR="/Users/wangyaqi/Documents/cursor_project/agent评估/memoria_runtime"
VENV_DIR="/Users/wangyaqi/Documents/cursor_project/.venv"
API_URL="http://127.0.0.1:8100"
RUN_DIR="$REPO_ROOT/memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1-smoke-conv30"

source "$VENV_DIR/bin/activate"

MASTER_KEY="$(python -c 'import sys; sys.path.insert(0, sys.argv[1]); import ingest; print(ingest.read_env(ingest.Path(sys.argv[2])).get("MEMORIA_MASTER_KEY", ""))' "$SCRIPT_DIR" "$RUNTIME_DIR/.env")"
if [[ -z "$MASTER_KEY" ]]; then
  echo "MEMORIA_MASTER_KEY is missing from $RUNTIME_DIR/.env" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/locomo-smoke-ingest.XXXXXX)"
trap 'rm -rf -- "$TMP_DIR"' EXIT

curl --fail --silent --show-error "$API_URL/health/instance" > "$TMP_DIR/health.json"
curl --fail --silent --show-error "$API_URL/admin/config" \
  -H "Authorization: Bearer $MASTER_KEY" > "$TMP_DIR/config.json"

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

cd "$REPO_ROOT"
python memoria/scripts/locomo/ingest.py \
  --run-dir "$RUN_DIR" \
  --workers 1 \
  --sample-id conv-30 \
  --user-prefix locomo-qwen-v4-smoke- \
  --embedding-model text-embedding-v4 \
  --embedding-dimension 1024 \
  --memoria-commit 54c9114fd6888e11821edc2ee9acd570c17c5ee3 \
  --memoria-patch-sha256 a668ae33c3c5e4fd83f642c75003e1d299f81c039ca300bb4c89996bf7aca128

python - "$RUN_DIR/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "selected_samples": 1,
    "completed_samples": 1,
    "sessions": 19,
    "expected_memories": 369,
    "accepted_memories": 369,
    "failed_memories": 0,
    "missing_ingest_keys": 0,
    "extra_ingest_keys": 0,
}
bad = {
    key: (summary.get(key), value)
    for key, value in expected.items()
    if summary.get(key) != value
}
results = summary.get("results", [])
if len(results) != 1 or results[0].get("sample_id") != "conv-30":
    bad["sample_id"] = ([row.get("sample_id") for row in results], ["conv-30"])
if summary.get("sample_failures"):
    bad["sample_failures"] = (summary["sample_failures"], [])
if bad:
    raise SystemExit(f"smoke import acceptance failed: {bad}")
print("Smoke import accepted: conv-30, 369/369 memories")
PY

echo "LoCoMo smoke import completed."
echo "Next: ./memoria/scripts/locomo/run_full_ingest.sh"
