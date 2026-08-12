#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-preflight}"
if [[ "$MODE" != "preflight" && "$MODE" != "full" ]]; then
  echo "Usage: $0 [preflight|full] [extra evaluate_zep_model_top200.py args...]" >&2
  exit 2
fi
if [[ $# -gt 0 ]]; then
  shift
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source /Users/wangyaqi/Documents/cursor_project/.venv/bin/activate
cd "$PROJECT_ROOT"

OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://aihubmix.com/v1}"
export OPENAI_BASE_URL
if [[ -z "${AIHUBMIX_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
  read -r -s -p "AiHubMix API key: " AIHUBMIX_API_KEY
  echo
  export AIHUBMIX_API_KEY
fi
OPENAI_API_KEY="${AIHUBMIX_API_KEY:-${OPENAI_API_KEY:-}}"
export OPENAI_API_KEY

BASE_RUN_DIR="memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation"
if [[ "$MODE" == "preflight" ]]; then
  RUN_DIR="$BASE_RUN_DIR/zep-model-aligned-gpt54-medium-mem0-prompt-top200-aihubmix-preflight1-v1"
else
  RUN_DIR="$BASE_RUN_DIR/zep-model-aligned-gpt54-medium-mem0-prompt-top200-aihubmix-full1540-v1"
fi

COMMAND=(python memoria/scripts/locomo/evaluate_zep_model_top200.py
  --base-url "$OPENAI_BASE_URL"
  --answerer-model gpt-5.4
  --judge-model gpt-5.4
  --run-dir "$RUN_DIR")
if [[ "$MODE" == "preflight" ]]; then
  COMMAND+=(--limit 1)
fi
COMMAND+=("$@")

"${COMMAND[@]}"
