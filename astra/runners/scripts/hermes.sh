#!/usr/bin/env bash
set -euo pipefail

cd "/Users/chenyuwei/Documents/MOI benchmark"

if [[ -z "${GLM_API_KEY:-}" ]]; then
  echo "GLM_API_KEY is required; export it or use Harbor with --env-file." >&2
  exit 2
fi

harbor run \
  --config "/Users/chenyuwei/Documents/MOI benchmark/astra/runners/hermes_terminal_bench/s0-four-cases.yaml" \
  --yes
