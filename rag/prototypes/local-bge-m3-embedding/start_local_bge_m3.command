#!/bin/zsh

set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$SERVICE_ROOT"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x /Users/muuushroom/.local/bin/uv ]]; then
  UV_BIN="/Users/muuushroom/.local/bin/uv"
else
  echo "uv is required; install it from https://docs.astral.sh/uv/" >&2
  exit 1
fi

echo "Local BGE-M3 embedding service: http://${BGE_HOST:-127.0.0.1}:${BGE_PORT:-8081}"
echo "Model weights load on the first request when BGE_LAZY_LOAD=true."
exec "$UV_BIN" run uvicorn app:app \
  --host "${BGE_HOST:-127.0.0.1}" \
  --port "${BGE_PORT:-8081}"
