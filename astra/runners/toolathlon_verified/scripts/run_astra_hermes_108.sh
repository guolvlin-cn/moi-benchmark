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
repo_root=$(cd -- "${script_root}/../../../.." && pwd)
output_root=$(readlink -m -- "$1")
m1_root="${output_root}/qualification-pair"
m2_root="${output_root}/m2-first-14"
m3_root="${output_root}/m3-remaining-94"

export TOOLATHLON_REPO_ROOT="${TOOLATHLON_REPO_ROOT:-$repo_root}"
mkdir -p -- "$output_root"

if [[ ! -d "$m1_root" ]]; then
  "${repo_root}/astra/benchmark/toolathlon-verified/scripts/run_minimal_e2e_pair.sh" \
    "$m1_root"
fi
"${repo_root}/astra/benchmark/toolathlon-verified/scripts/run_m2_first_batch.sh" \
  "$m2_root" "$m1_root"
"${repo_root}/astra/benchmark/toolathlon-verified/scripts/run_m3_remaining_batch.sh" \
  "$m3_root" "$m2_root"

echo "Astra/Hermes 108-task results: $output_root"
