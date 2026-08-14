#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCUMENT_PARSING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCORER_REPO="${MOI_PARSE_BENCH_DIR:-/Users/wangyaqi/Documents/cursor_project/moi-parse-bench}"
SCORER_COMMIT="06faf76112c998835f0f9ca174a5f2d311d559f2"
OUTPUT="${1:-$DOCUMENT_PARSING_DIR/evaluate/semiconductor-private-final/reproduced-score.json}"
VENV="/Users/wangyaqi/Documents/cursor_project/.venv"

if [[ ! -d "$SCORER_REPO/.git" ]]; then
  echo "moi-parse-bench checkout not found: $SCORER_REPO" >&2
  echo "Set MOI_PARSE_BENCH_DIR to a checkout of git@github.com:matrixorigin/moi-parse-bench.git" >&2
  exit 2
fi
if ! git -C "$SCORER_REPO" cat-file -e "$SCORER_COMMIT^{commit}"; then
  echo "scorer commit is unavailable in $SCORER_REPO: $SCORER_COMMIT" >&2
  exit 2
fi
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "required Python environment is missing: $VENV" >&2
  exit 2
fi

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/semiconductor-private-score.XXXXXX")"
trap 'rm -rf "$TEMP_DIR"' EXIT
mkdir -p "$TEMP_DIR/source"
git -C "$SCORER_REPO" archive "$SCORER_COMMIT" tools/parsing_benchmark \
  | tar -x -C "$TEMP_DIR/source"

source "$VENV/bin/activate"
python "$SCRIPT_DIR/score_semiconductor_private.py" \
  --scorer-src "$TEMP_DIR/source/tools/parsing_benchmark/src" \
  --document-parsing-dir "$DOCUMENT_PARSING_DIR" \
  --output "$OUTPUT"

echo "Reproduced private-dataset score: $OUTPUT"
