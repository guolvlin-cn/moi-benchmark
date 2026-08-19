#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 RUN_DIR OUTPUT_DIR" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$(cd "$1" && pwd)"
OUTPUT_DIR="$2"
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

if [[ -f "$OUTPUT_DIR/predictions_quick_match_run_summary.json" ]]; then
  echo "official score already complete: $OUTPUT_DIR/predictions_quick_match_run_summary.json"
  exit 0
fi

PIPELINE="$(python3 - "$RUN_DIR/moi-unified/progress.json" <<'PY'
import json
import sys
from pathlib import Path

progress = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(progress["pipeline"])
PY
)"
python3 "$SCRIPT_DIR/run_stage1.py" verify \
  --run-dir "$RUN_DIR" \
  --pipeline "$PIPELINE" \
  --allow-empty-predictions

docker run --rm --platform linux/amd64 --entrypoint bash \
  -v "$RUN_DIR/official/ground-truth.json:/workspace/gt/ground-truth.json:ro" \
  -v "$RUN_DIR/official/predictions:/workspace/data_md/predictions:ro" \
  -v "$SCRIPT_DIR/official-config.yaml:/workspace/configs/moi-stage1.yaml:ro" \
  -v "$OUTPUT_DIR:/workspace/result" \
  ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204 \
  -c 'python pdf_validation.py --config configs/moi-stage1.yaml'

test -f "$OUTPUT_DIR/predictions_quick_match_run_summary.json"
echo "official score complete: $OUTPUT_DIR/predictions_quick_match_run_summary.json"
