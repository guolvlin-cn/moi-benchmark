#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark"
VENV="/Users/wangyaqi/Documents/cursor_project/.venv"
MODE="${1:-smoke}"
STAGE="${2:-all}"

case "${MODE}" in
  smoke)
    RUN_DIR="${PROJECT_ROOT}/memoria/runs/longmemeval-s-zep-aligned-gpt54-top20-smoke10-v1"
    SELECTION_ARGS=(
      --question-ids-file
      "${PROJECT_ROOT}/memoria/scripts/longmemeval/smoke10-question-ids.json"
    )
    ;;
  full)
    RUN_DIR="${PROJECT_ROOT}/memoria/runs/longmemeval-s-zep-aligned-gpt54-top20-full500-v1"
    SELECTION_ARGS=()
    ;;
  *)
    echo "Usage: $0 [smoke|full] [prepare|readers|judge|report|all]" >&2
    exit 2
    ;;
esac

case "${STAGE}" in
  prepare|readers|judge|report|all) ;;
  *)
    echo "Usage: $0 [smoke|full] [prepare|readers|judge|report|all]" >&2
    exit 2
    ;;
esac

source "${VENV}/bin/activate"
cd "${PROJECT_ROOT}"

OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://aihubmix.com/v1}"
export OPENAI_BASE_URL

if [[ -z "${AIHUBMIX_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
  read -r -s -p "AiHubMix API key: " AIHUBMIX_API_KEY
  echo
  export AIHUBMIX_API_KEY
fi

if [[ -n "${AIHUBMIX_API_KEY:-}" ]]; then
  API_KEY_ENV="AIHUBMIX_API_KEY"
else
  API_KEY_ENV="OPENAI_API_KEY"
fi

COMMON_ARGS=(
  --run-dir "${RUN_DIR}"
  --answerer-model gpt-5.4
  --judge-model gpt-5.4
  --api-style responses
  --reasoning-effort medium
  --base-url "${OPENAI_BASE_URL}"
  --api-key-env "${API_KEY_ENV}"
  --experiment-name "LongMemEval-S Memoria Top-20 对标 Zep 实验"
  --protocol-name "zep-model-aligned-mem0-prompts-v1"
  --scope-note "Zep-aligned GPT-5.4 Reader/Judge models with reasoning=medium; Zep prompts are undisclosed, so pinned Mem0 LongMemEval Reader/Judge prompts are used as the proxy."
)

if [[ "${MODE}" == "smoke" ]]; then
  python memoria/scripts/longmemeval/evaluate_mem0_protocol.py \
    "${STAGE}" "${COMMON_ARGS[@]}" "${SELECTION_ARGS[@]}"
else
  python memoria/scripts/longmemeval/evaluate_mem0_protocol.py \
    "${STAGE}" "${COMMON_ARGS[@]}"
fi
