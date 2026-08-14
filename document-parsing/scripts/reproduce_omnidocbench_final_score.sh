#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

GOLDEN="$TRACK_DIR/datasets/omnidocbench/OmniDocBench.json"
PREDICTION_DIR="$TRACK_DIR/runs/omnidocbench-idc-4.1.14-vlm-final-1651-official-md"
ADAPTER_REPORT="$PREDICTION_DIR/adapter-report.json"
CONFIG="$TRACK_DIR/evaluate/moi-omnidocbench-final/end2end.docker.yaml"
OUTPUT_DIR="$TRACK_DIR/evaluate/moi-omnidocbench-final/reproduced-result"
VERIFY_ONLY=false

IMAGE_TAG="ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204"
IMAGE_DIGEST="sha256:6116ad72172e763b5c43e963d5efebf2093f2362b975f58156ce4f6c9142e617"
IMAGE="$IMAGE_TAG@$IMAGE_DIGEST"
PYTHON_ENTRYPOINT="/opt/miniconda310/envs/omnidocbench_v16_smoke_20260408_py310/bin/python"

usage() {
  printf '%s\n' \
    "Usage: $0 [--golden PATH] [--output-dir PATH] [--verify-only]" \
    "" \
    "Validates the pinned final inputs and reproduces the official 90.23 score." \
    "The Docker image is pinned by digest and is pulled automatically if absent."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --golden)
      GOLDEN="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --verify-only)
      VERIFY_ONLY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

VERIFY_ARGS=(
  --golden "$GOLDEN"
  --prediction-dir "$PREDICTION_DIR"
  --adapter-report "$ADAPTER_REPORT"
)

python3 "$SCRIPT_DIR/verify_omnidocbench_final_score.py" "${VERIFY_ARGS[@]}"

if [[ "$VERIFY_ONLY" == true ]]; then
  printf 'Input verification complete; Docker scoring was skipped.\n'
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  printf 'Docker is required to run the official evaluator.\n' >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"

printf 'Evaluator image tag: %s\n' "$IMAGE_TAG"
printf 'Pinned image digest: %s\n' "$IMAGE_DIGEST"

docker run --rm \
  --entrypoint "$PYTHON_ENTRYPOINT" \
  -v "$GOLDEN:/workspace/gt/OmniDocBench.json:ro" \
  -v "$PREDICTION_DIR:/workspace/data_md/omnidocbench-idc-4.1.14-vlm-final-1651-official-md:ro" \
  -v "$CONFIG:/workspace/configs/moi-omnidocbench-final.yaml:ro" \
  -v "$OUTPUT_DIR:/workspace/result" \
  "$IMAGE" \
  pdf_validation.py --config configs/moi-omnidocbench-final.yaml

python3 "$SCRIPT_DIR/verify_omnidocbench_final_score.py" \
  "${VERIFY_ARGS[@]}" \
  --result-dir "$OUTPUT_DIR"
