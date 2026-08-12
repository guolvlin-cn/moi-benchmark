#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-preflight}"
PROVIDER="${2:-openai}"
if [[ "$MODE" != "preflight" && "$MODE" != "full" ]]; then
  echo "Usage: $0 [preflight|full] [openai|azure] [extra evaluate_top200.py args...]" >&2
  exit 2
fi
if [[ "$PROVIDER" != "openai" && "$PROVIDER" != "azure" ]]; then
  echo "Provider must be openai or azure." >&2
  exit 2
fi
shift $(( $# > 0 ? 1 : 0 ))
shift $(( $# > 0 ? 1 : 0 ))

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source /Users/wangyaqi/Documents/cursor_project/.venv/bin/activate
cd "$PROJECT_ROOT"

if [[ "$PROVIDER" == "openai" ]]; then
  OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://aihubmix.com/v1}"
  export OPENAI_BASE_URL
  if [[ -z "${AIHUBMIX_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
    read -r -s -p "AiHubMix API key: " AIHUBMIX_API_KEY
    echo
    export AIHUBMIX_API_KEY
  fi
  OPENAI_API_KEY="${AIHUBMIX_API_KEY:-${OPENAI_API_KEY:-}}"
  export OPENAI_API_KEY
else
  if [[ -z "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
    read -r -p "Azure OpenAI endpoint: " AZURE_OPENAI_ENDPOINT
    export AZURE_OPENAI_ENDPOINT
  fi
  if [[ -z "${AZURE_OPENAI_API_KEY:-}" ]]; then
    read -r -s -p "Azure OpenAI API key: " AZURE_OPENAI_API_KEY
    echo
    export AZURE_OPENAI_API_KEY
  fi
fi

BASE_RUN_DIR="memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation"
if [[ "$MODE" == "preflight" ]]; then
  if [[ "$PROVIDER" == "openai" ]]; then
    RUN_DIR="$BASE_RUN_DIR/mem0-compatible-gpt5-reader-judge-top200-aihubmix-preflight1-v1"
  else
    RUN_DIR="$BASE_RUN_DIR/mem0-compatible-gpt5-reader-judge-top200-azure-preflight1-v1"
  fi
else
  if [[ "$PROVIDER" == "openai" ]]; then
    RUN_DIR="$BASE_RUN_DIR/mem0-compatible-gpt5-reader-judge-top200-aihubmix-full1540-v1"
  else
    RUN_DIR="$BASE_RUN_DIR/mem0-compatible-gpt5-reader-judge-top200-azure-full1540-v1"
  fi
fi

COMMAND=(python memoria/scripts/locomo/evaluate_top200.py --provider "$PROVIDER")
if [[ "$PROVIDER" == "openai" ]]; then
  COMMAND+=(--base-url "$OPENAI_BASE_URL")
fi
COMMAND+=( \
  --answerer-model gpt-5 \
  --judge-model gpt-5 \
  --run-dir "$RUN_DIR")
if [[ "$MODE" == "preflight" ]]; then
  COMMAND+=(--limit 1)
fi
COMMAND+=("$@")

"${COMMAND[@]}"
