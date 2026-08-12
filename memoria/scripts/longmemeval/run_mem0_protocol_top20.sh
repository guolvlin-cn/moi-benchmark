#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark"
VENV="/Users/wangyaqi/Documents/cursor_project/.venv"
MODE="${1:-full}"
STAGE="${2:-all}"

case "${MODE}" in
  smoke)
    RUN_DIR="${PROJECT_ROOT}/memoria/runs/longmemeval-s-mem0-protocol-gpt5-top20-smoke10-v1"
    SELECTION_ARGS=(
      --question-ids-file
      "${PROJECT_ROOT}/memoria/scripts/longmemeval/smoke10-question-ids.json"
    )
    ;;
  full)
    RUN_DIR="${PROJECT_ROOT}/memoria/runs/longmemeval-s-mem0-protocol-gpt5-top20-full500-v1"
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

COMMON_ARGS=(
  --run-dir "${RUN_DIR}"
  --answerer-model gpt-5
  --judge-model gpt-5
  --base-url "${OPENAI_BASE_URL:-https://aihubmix.com/v1}"
  --api-key-env "${OPENAI_API_KEY_ENV:-AIHUBMIX_API_KEY}"
)

if [[ "${MODE}" == "smoke" ]]; then
  python memoria/scripts/longmemeval/evaluate_mem0_protocol.py \
    "${STAGE}" "${COMMON_ARGS[@]}" "${SELECTION_ARGS[@]}"
else
  python memoria/scripts/longmemeval/evaluate_mem0_protocol.py \
    "${STAGE}" "${COMMON_ARGS[@]}"
fi
