#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "${script_dir}/../../../.." && pwd)"
tasks_root="${PI_TBENCH_TASKS_ROOT:-${workspace_root}/work/terminal-bench-2-1/tasks}"
generated_root="${PI_TBENCH_GENERATED_TASKS_ROOT:-${workspace_root}/work/terminal-bench-2-1-pi-prebuilt/tasks}"
config="${PI_TBENCH_CONFIG:-${script_dir}/../c0-all-prebuilt.yaml}"
image_prefix="${PI_PREBUILT_IMAGE_PREFIX:-moi/pi-tbench}"
image_tag="${PI_PREBUILT_IMAGE_TAG:-0.73.1}"
runtime_image="${PI_PREBUILT_RUNTIME_IMAGE:-moi/pi-tbench-runtime:0.73.1}"
runtime_base_image="${PI_PREBUILT_RUNTIME_BASE_IMAGE:-debian:12-slim}"
harbor_bin="${HARBOR_BIN:-harbor}"
python_bin="${PYTHON_BIN:-python3}"
rebuild_runtime=false
build_only=false
keep_images=false
tasks=()

remove_task_image() {
  local image="$1"
  local task="$2"
  local labels
  labels="$(docker image inspect --format '{{ index .Config.Labels "io.moi.pi-tbench.kind" }}|{{ index .Config.Labels "io.moi.pi-tbench.task" }}' "${image}")"
  [[ "${labels}" == "ephemeral-task|${task}" ]] || {
    echo "refusing to remove image with unexpected labels: ${image}" >&2
    return 1
  }
  docker image rm --force "${image}" >/dev/null
}

usage() {
  cat <<'EOF'
Build Pi 0.73.1 thin task images and optionally run their Harbor trials.

Usage: build-images.sh [--build-only] [--keep-images] [--rebuild-runtime] TASK [TASK ...]
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --build-only) build_only=true; shift ;;
    --keep-images) keep_images=true; shift ;;
    --rebuild-runtime) rebuild_runtime=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) tasks+=("$1"); shift ;;
  esac
done
[[ "${#tasks[@]}" -gt 0 ]] || { usage >&2; exit 2; }

if [[ "${rebuild_runtime}" == "true" ]] \
  || ! docker image inspect "${runtime_image}" >/dev/null 2>&1; then
  docker buildx build \
    --load \
    --platform linux/amd64 \
    --build-arg "RUNTIME_BASE_IMAGE=${runtime_base_image}" \
    --tag "${runtime_image}" \
    --file "${script_dir}/Dockerfile" \
    "${script_dir}"
fi

for task in "${tasks[@]}"; do
  [[ "${task}" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "invalid task: ${task}" >&2
    exit 2
  }
  task_toml="${tasks_root}/${task}/task.toml"
  [[ -f "${task_toml}" ]] || {
    echo "missing task: ${task}" >&2
    exit 2
  }
  base_image="$({
    sed -nE \
      's/^[[:space:]]*docker_image[[:space:]]*=[[:space:]]*"([^"]+)".*$/\1/p' \
      "${task_toml}"
  })"
  [[ "$(printf '%s\n' "${base_image}" | sed '/^$/d' | wc -l | tr -d ' ')" == "1" ]] || {
    echo "task must contain one docker_image: ${task}" >&2
    exit 2
  }
  image="${image_prefix}-${task}:${image_tag}"
  docker buildx build \
    --load \
    --platform linux/amd64 \
    --build-arg "BASE_IMAGE=${base_image}" \
    --build-arg "PI_RUNTIME_IMAGE=${runtime_image}" \
    --build-arg "TASK_NAME=${task}" \
    --tag "${image}" \
    --file "${script_dir}/Dockerfile.task" \
    "${script_dir}"
  docker run --rm --platform linux/amd64 --entrypoint /usr/local/bin/pi \
    "${image}" --version 2>&1 | grep -Fx '0.73.1'
  "${python_bin}" "${script_dir}/prepare_tasks.py" \
    --source "${tasks_root}" \
    --destination "${generated_root}" \
    --image-prefix "${image_prefix}" \
    --image-tag "${image_tag}" \
    --overwrite \
    "${task}"
  if [[ "${build_only}" == "false" ]]; then
    env "PYTHONPATH=${workspace_root}${PYTHONPATH:+:${PYTHONPATH}}" \
      "${harbor_bin}" run \
      --config "${config}" \
      --jobs-dir "${PI_TBENCH_JOBS_DIR:-${workspace_root}/work/pi-c0-all-jobs}" \
      --path "${generated_root}/${task}" \
      --no-force-build \
      --yes
  fi
  if [[ "${keep_images}" == "false" ]]; then
    remove_task_image "${image}" "${task}"
  fi
done
