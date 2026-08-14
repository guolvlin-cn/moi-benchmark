#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "${script_dir}/../../.." && pwd)"
cd "${workspace_root}"

if [[ -z "${GLM_API_KEY:-}" ]]; then
  echo "GLM_API_KEY is required; export it or use Harbor with --env-file." >&2
  exit 2
fi

harbor run \
  --config "astra/runners/hermes_terminal_bench/s0-four-cases.yaml" \
  --yes
