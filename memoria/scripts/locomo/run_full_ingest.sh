#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
RUNTIME_DIR="/Users/wangyaqi/Documents/cursor_project/agent评估/memoria_runtime"
VENV_DIR="/Users/wangyaqi/Documents/cursor_project/.venv"
API_URL="http://127.0.0.1:8100"
RUN_DIR="$REPO_ROOT/memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1"
SMOKE_DIR="$REPO_ROOT/memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1-smoke-conv30"
SMOKE_USER="locomo-qwen-v4-smoke-conv-30"

source "$VENV_DIR/bin/activate"

MASTER_KEY="$(python -c 'import sys; sys.path.insert(0, sys.argv[1]); import ingest; print(ingest.read_env(ingest.Path(sys.argv[2])).get("MEMORIA_MASTER_KEY", ""))' "$SCRIPT_DIR" "$RUNTIME_DIR/.env")"
if [[ -z "$MASTER_KEY" ]]; then
  echo "MEMORIA_MASTER_KEY is missing from $RUNTIME_DIR/.env" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/locomo-full-ingest.XXXXXX)"
trap 'rm -rf -- "$TMP_DIR"' EXIT

python - "$SMOKE_DIR/summary.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f"accepted smoke summary is missing: {path}")
summary = json.loads(path.read_text(encoding="utf-8"))
expected = {
    "selected_samples": 1,
    "sessions": 19,
    "expected_memories": 369,
    "accepted_memories": 369,
    "failed_memories": 0,
    "missing_ingest_keys": 0,
    "extra_ingest_keys": 0,
}
bad = {key: (summary.get(key), value) for key, value in expected.items() if summary.get(key) != value}
if bad:
    raise SystemExit(f"smoke acceptance check failed: {bad}")
print("Smoke prerequisite accepted: 369/369 memories")
PY

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
bad = {key: (config.get(key), value) for key, value in expected.items() if config.get(key) != value}
if bad:
    raise SystemExit(f"Memoria embedding configuration mismatch: {bad}")
print("Memoria configuration accepted: text-embedding-v4 / 1024")
PY

if [[ "${1:-}" == "--preflight-only" ]]; then
  echo "Full import preflight completed; no memories were written or deleted."
  exit 0
fi

cd "$REPO_ROOT"
python memoria/scripts/locomo/ingest.py \
  --run-dir "$RUN_DIR" \
  --workers 1 \
  --user-prefix locomo-qwen-v4- \
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
    "selected_samples": 10,
    "completed_samples": 10,
    "sessions": 272,
    "expected_memories": 5882,
    "accepted_memories": 5882,
    "failed_memories": 0,
    "missing_ingest_keys": 0,
    "extra_ingest_keys": 0,
}
bad = {key: (summary.get(key), value) for key, value in expected.items() if summary.get(key) != value}
if summary.get("sample_failures"):
    bad["sample_failures"] = (summary["sample_failures"], [])
if bad:
    raise SystemExit(f"full import acceptance check failed; smoke user retained: {bad}")
print("Full import accepted: 5882/5882 memories")
PY

curl --fail --silent --show-error "$API_URL/admin/users/$SMOKE_USER/stats" \
  -H "Authorization: Bearer $MASTER_KEY" > "$TMP_DIR/smoke-before.json"

python - "$TMP_DIR/smoke-before.json" "$SMOKE_USER" <<'PY'
import json
import sys
from pathlib import Path

stats = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_user = sys.argv[2]
if stats.get("user_id") != expected_user or stats.get("memory_count") != 369:
    raise SystemExit(f"refusing smoke cleanup; unexpected user stats: {stats}")
print("Smoke cleanup target resolved exactly: 369 active memories")
PY

curl --fail --silent --show-error -X DELETE "$API_URL/admin/users/$SMOKE_USER" \
  -H "Authorization: Bearer $MASTER_KEY" > "$TMP_DIR/smoke-delete.json"
curl --fail --silent --show-error "$API_URL/admin/users/$SMOKE_USER/stats" \
  -H "Authorization: Bearer $MASTER_KEY" > "$TMP_DIR/smoke-after.json"

python - "$TMP_DIR/smoke-before.json" "$TMP_DIR/smoke-delete.json" "$TMP_DIR/smoke-after.json" "$RUN_DIR/smoke_cleanup.json" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
deleted = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
after = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
if deleted.get("status") != "ok" or after.get("memory_count") != 0:
    raise SystemExit(f"smoke cleanup verification failed: delete={deleted}, after={after}")
record = {
    "deleted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "operation": "DELETE /admin/users/:user_id (soft delete active memories)",
    "before": before,
    "response": deleted,
    "after": after,
}
Path(sys.argv[4]).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("Smoke user removed: active memories 369 -> 0")
PY

echo "Formal LoCoMo import and smoke cleanup completed."
