#!/usr/bin/env bash
set -uo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo -E so Docker and task application credentials remain available." >&2
  exit 77
fi

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 TASK_ID ABSOLUTE_OUTPUT_DIR [RUN_ID]" >&2
  exit 64
fi

repo_root="/home/vagrant/moi-benchmark"
source_root="/home/vagrant/dataset/Toolathlon"
task_id=$1
output_dir=$(readlink -m -- "$2")
run_id=${3:-"$(date -u +%Y%m%dT%H%M%SZ)-${task_id}-pi-a1"}

case "$output_dir" in
  /home/vagrant/moi-benchmark/*|/tmp/*) ;;
  *)
    echo "ERROR: output directory must be below /home/vagrant/moi-benchmark or /tmp." >&2
    exit 64
    ;;
esac

if [[ -z ${TOOLATHLON_DEEPSEEK_PI_API_KEY:-} ]]; then
  echo "ERROR: TOOLATHLON_DEEPSEEK_PI_API_KEY is required." >&2
  exit 78
fi
if [[ -z ${TOOLATHLON_PI_EXECUTABLE:-} ]]; then
  echo "ERROR: TOOLATHLON_PI_EXECUTABLE must point to the Pi 0.73.1 executable." >&2
  exit 78
fi
if [[ ! -x $TOOLATHLON_PI_EXECUTABLE ]]; then
  echo "ERROR: TOOLATHLON_PI_EXECUTABLE is not executable: $TOOLATHLON_PI_EXECUTABLE" >&2
  exit 78
fi
if [[ -e $output_dir ]] && [[ -n $(find "$output_dir" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
  echo "ERROR: output directory must be absent or empty." >&2
  exit 73
fi

cd -- "$repo_root"
python3 -m astra.runners.toolathlon_pi.lifecycle \
  --task-id "$task_id" \
  --experiment-id toolathlon-pi-0.73.1-v1 \
  --run-id "$run_id" \
  --output-dir "$output_dir" \
  --toolathlon-source "$source_root"

