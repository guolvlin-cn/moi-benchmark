#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo -E so Docker and runtime credentials are available." >&2
  exit 77
fi
if [[ $# -ne 1 ]]; then
  echo "usage: $0 ABSOLUTE_OUTPUT_ROOT" >&2
  exit 64
fi

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_root}/../../.." && pwd)
output_root=$(readlink -m -- "$1")

export TOOLATHLON_REPO_ROOT="${TOOLATHLON_REPO_ROOT:-$repo_root}"

"${repo_root}/astra/runners/toolathlon_verified/scripts/run_astra_hermes_108.sh" \
  "${output_root}/astra-hermes"
"${repo_root}/astra/runners/toolathlon_pi/scripts/run_pi_108.sh" \
  "${output_root}/pi"

echo "Three-product Toolathlon results: $output_root"
