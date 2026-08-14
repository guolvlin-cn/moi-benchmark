#!/usr/bin/env bash
set -uo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo -E so frozen credentials and Docker are available without copying secrets." >&2
  exit 77
fi

if [[ $# -ne 2 ]]; then
  echo "usage: $0 ABSOLUTE_M3_OUTPUT_ROOT ABSOLUTE_M2_GO_ROOT" >&2
  exit 64
fi

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root="${TOOLATHLON_REPO_ROOT:-$(cd -- "${script_root}/../../../.." && pwd)}"
source_root="${TOOLATHLON_SOURCE_ROOT:-/home/vagrant/dataset/Toolathlon}"
freeze_root="${repo_root}/astra/benchmark/toolathlon-verified/freeze"
output_root=$(readlink -m -- "$1")
m2_root=$(readlink -m -- "$2")

if [[ "$output_root" != "$repo_root"/* && "$output_root" != /tmp/* ]]; then
  echo "ERROR: M3 output root must be below the repository or /tmp." >&2
  exit 64
fi
if [[ "$m2_root" != "$repo_root"/* && "$m2_root" != /tmp/* ]]; then
  echo "ERROR: M2 root must be below the repository or /tmp." >&2
  exit 64
fi

mkdir -p -- "$output_root"
cd -- "$repo_root"

(
  cd -- "$freeze_root"
  sha256sum -c m0.sha256
) || {
  echo "ERROR: M0 checksum root is not valid." >&2
  exit 79
}

if [[ ! -f "${output_root}/m3-batch-manifest.json" ]]; then
  unexpected=$(find "$output_root" -mindepth 1 -maxdepth 1 ! -name '.m3.lock' -print -quit)
  if [[ -n "$unexpected" ]]; then
    echo "ERROR: a new M3 output root must be empty; preserve existing evidence and choose another directory." >&2
    exit 73
  fi
fi

python3 -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")); raise SystemExit(0 if value.get("state") == "GO" else 1)' \
  "${freeze_root}/credential-manifest.json" || {
    echo "ERROR: runtime credential fingerprint manifest is not GO." >&2
    exit 78
  }

python3 astra/benchmark/toolathlon-verified/scripts/check_astra_model_precondition.py || exit $?

python3 -m astra.runners.toolathlon_verified.m3_batch run \
  --repo-root "$repo_root" \
  --source-root "$source_root" \
  --output-root "$output_root" \
  --m2-root "$m2_root"
