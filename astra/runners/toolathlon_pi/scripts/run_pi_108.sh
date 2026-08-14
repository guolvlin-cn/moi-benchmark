#!/usr/bin/env bash
set -Eeuo pipefail

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_root}/../../../.." && pwd)
if [[ $# -ne 1 ]]; then
  echo "usage: $0 ABSOLUTE_OUTPUT_ROOT" >&2
  exit 64
fi

output_root=$(readlink -m -- "$1")
credential_manifest="${output_root}/credential-manifest.runtime.json"
source_root="${TOOLATHLON_SOURCE_ROOT:-/home/vagrant/dataset/Toolathlon}"

export TOOLATHLON_REPO_ROOT="${TOOLATHLON_REPO_ROOT:-$repo_root}"
mkdir -p -- "$output_root"
if [[ ! -f "$credential_manifest" ]]; then
  if [[ -d "${output_root}/runs" ]]; then
    echo "ERROR: existing Pi runs have no batch credential manifest; preserve them and choose a new output root." >&2
    exit 73
  fi
  python3 "${script_root}/snapshot_application_credentials.py" \
    --base "${repo_root}/astra/benchmark/toolathlon-verified/freeze/credential-manifest.json" \
    --source "$source_root" \
    --output "$credential_manifest"
fi

export TOOLATHLON_PI_CREDENTIAL_MANIFEST="$credential_manifest"
exec "${repo_root}/astra/benchmark/toolathlon-verified/scripts/run_pi_108.sh" "$output_root"
