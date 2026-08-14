#!/usr/bin/env bash
set -uo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo -E so credential fingerprints can be verified without copying secrets." >&2
  exit 77
fi

if [[ $# -ne 1 ]]; then
  echo "usage: $0 ABSOLUTE_OUTPUT_ROOT" >&2
  exit 64
fi

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root="${TOOLATHLON_REPO_ROOT:-$(cd -- "${script_root}/../../../.." && pwd)}"
output_root=$(readlink -m -- "$1")
source_root="${TOOLATHLON_SOURCE_ROOT:-/home/vagrant/dataset/Toolathlon}"
experiment_id="toolathlon-verified-v0.5"
task_id="find-alita-paper"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)

if [[ "$output_root" != "$repo_root"/* && "$output_root" != /tmp/* ]]; then
  echo "output root must be below the repository or /tmp" >&2
  exit 64
fi

mkdir -p -- "$output_root"
if [[ -n "$(find "$output_root" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "ERROR: output root must be empty; preserve failed batches and choose a new directory." >&2
  exit 73
fi
cd -- "$repo_root"

python3 astra/benchmark/toolathlon-verified/scripts/freeze_m1_credentials.py \
  --source "$source_root" \
  --output astra/benchmark/toolathlon-verified/freeze/credential-manifest.json \
  --frozen-at "$timestamp" || exit $?
python3 -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")); raise SystemExit(0 if value.get("state") == "GO" else 1)' \
  astra/benchmark/toolathlon-verified/freeze/credential-manifest.json || {
    echo "ERROR: runtime credential freeze is not GO; verify sudo -E preserved the two DeepSeek keys and Astra admin token." >&2
    exit 78
  }
python3 astra/benchmark/toolathlon-verified/scripts/check_astra_model_precondition.py || exit $?

docker_args=()

run_system() {
  local system=$1
  local original_run_id="${timestamp}-${task_id}-${system}-a1"
  local original_dir="${output_root}/${system}/${task_id}/${original_run_id}"

  python3 -m astra.runners.toolathlon_verified.lifecycle \
    --system "$system" \
    --task-id "$task_id" \
    --experiment-id "$experiment_id" \
    --run-id "$original_run_id" \
    --output-dir "$original_dir" \
    --toolathlon-source "$source_root" \
    "${docker_args[@]}"
  local status=$?
  if [[ $status -eq 0 ]]; then
    return 0
  fi

  echo "${system}: original run exited ${status}; starting the one allowed replacement" >&2
  local replacement_run_id="${timestamp}-${task_id}-${system}-a2"
  local replacement_dir="${output_root}/${system}/${task_id}/${replacement_run_id}"
  python3 -m astra.runners.toolathlon_verified.lifecycle \
    --system "$system" \
    --task-id "$task_id" \
    --experiment-id "$experiment_id" \
    --run-id "$replacement_run_id" \
    --replacement-for-run-id "$original_run_id" \
    --output-dir "$replacement_dir" \
    --toolathlon-source "$source_root" \
    "${docker_args[@]}"
}

run_system astra || exit $?
run_system hermes || exit $?
python3 astra/benchmark/toolathlon-verified/scripts/validate_minimal_e2e_pair.py "$output_root"
