#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "${script_dir}/../../.." && pwd)"
runner_root="${workspace_root}/astra/runners/pi_terminal_bench"
data_root="${MOI_BENCH_DATA_ROOT:-${workspace_root}}"
tasks_root="${data_root}/work/terminal-bench-2-1/tasks"
dataset_root="${data_root}/work/terminal-bench-2-1"
expected_commit="5c8eadf1f393183288fa08b8f73ca9a469cc5e00"
state_dir="${data_root}/work/pi-c0-all-state"
canonical_queue="${state_dir}/resource.queue.tsv"
queue="${canonical_queue}"
builder="${runner_root}/prebuilt/build-images.sh"
generated_root="${data_root}/work/terminal-bench-2-1-pi-prebuilt/tasks"
jobs_dir="${data_root}/work/pi-c0-all-jobs"
config="${runner_root}/c0-all-prebuilt.yaml"
schedule="${runner_root}/prebuilt/schedule.py"
summary="${runner_root}/prebuilt/summarize_results.py"
verifier_cache_builder="${runner_root}/prebuilt/prepare-verifier-cache.sh"
check_only=false
max_tasks=""
retry_queue=""
harbor_bin="${HARBOR_BIN:-harbor}"
python_bin="${PYTHON_BIN:-}"

if [[ -z "${python_bin}" ]]; then
  resolved_harbor="$(command -v "${harbor_bin}" 2>/dev/null || true)"
  if [[ -n "${resolved_harbor}" && -x "$(dirname "${resolved_harbor}")/python" ]]; then
    python_bin="$(dirname "${resolved_harbor}")/python"
  else
    python_bin="python3"
  fi
fi

remove_task_image() {
  local task="$1"
  local image="moi/pi-tbench-${task}:0.73.1"
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
Run Pi C0 Terminal-Bench with an 8GB-aware queue.

Usage: pi-terminal-bench-all-c0.sh [--check] [--max-tasks N]
                                     [--retry-queue FILE]

The runner uses three 2GB memory tokens. An 8GB task takes all tokens and is
isolated; a 4GB task may pair with one 2GB task; three 2GB tasks may overlap.
With --retry-queue, every task listed in FILE is run even if an earlier attempt
has valid verifier output.
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --check) check_only=true; shift ;;
    --max-tasks) max_tasks="$2"; shift 2 ;;
    --retry-queue) retry_queue="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -z "${max_tasks}" || "${max_tasks}" =~ ^[1-9][0-9]*$ ]] || {
  echo "--max-tasks must be positive" >&2
  exit 2
}
[[ -d "${tasks_root}" ]] || {
  echo "missing dataset tasks: ${tasks_root}" >&2
  exit 2
}
actual_commit="$(git -C "${dataset_root}" rev-parse HEAD)"
[[ "${actual_commit}" == "${expected_commit}" ]] || {
  echo "unexpected dataset commit: ${actual_commit}" >&2
  exit 2
}
mkdir -p "${state_dir}"
"${python_bin}" "${runner_root}/prebuilt/resource_queue.py" \
  --tasks-root "${tasks_root}" \
  --output "${canonical_queue}"
if [[ -n "${retry_queue}" ]]; then
  [[ -f "${retry_queue}" ]] || {
    echo "missing retry queue: ${retry_queue}" >&2
    exit 2
  }
  while IFS= read -r retry_row; do
    [[ -z "${retry_row}" ]] && continue
    grep -Fqx -- "${retry_row}" "${canonical_queue}" || {
      echo "retry queue row is not in the canonical queue: ${retry_row}" >&2
      exit 2
    }
  done < "${retry_queue}"
  queue="${retry_queue}"
fi
echo "Dataset commit: ${actual_commit}"
echo "Queue: ${queue}"
echo "Policy: 3 memory tokens, 8GB isolated, largest and longest first"
if [[ "${check_only}" == "true" ]]; then
  exit 0
fi
[[ -n "${ZAI_API_KEY:-}" || -n "${GLM_API_KEY:-}" ]] || {
  echo "ZAI_API_KEY or GLM_API_KEY is required" >&2
  exit 2
}
if [[ -z "${ZAI_API_KEY:-}" ]]; then
  export ZAI_API_KEY="${GLM_API_KEY}"
fi
export PI_TBENCH_JOBS_DIR="${jobs_dir}"
export PI_TBENCH_GENERATED_TASKS_ROOT="${generated_root}"
export PI_TBENCH_TASKS_ROOT="${tasks_root}"
export PI_TBENCH_VERIFIER_CACHE="${PI_TBENCH_VERIFIER_CACHE:-${data_root}/work/pi-verifier-cache}"
export PYTHON_BIN="${python_bin}"
schedule_args=(
  "${schedule}"
  --queue "${queue}"
  --jobs-dir "${jobs_dir}"
  --generated-root "${generated_root}"
  --config "${config}"
  --workspace-root "${workspace_root}"
  --harbor-bin "${harbor_bin}"
  --print-pending
)
[[ -z "${max_tasks}" ]] || schedule_args+=(--max-tasks "${max_tasks}")
[[ -z "${retry_queue}" ]] || schedule_args+=(--rerun-completed)
pending_queue="${state_dir}/pending.queue.tsv"
"${python_bin}" "${schedule_args[@]}" > "${pending_queue}"
pending_tasks=()
while IFS=$'\t' read -r task _rest; do
  [[ -n "${task}" ]] && pending_tasks+=("${task}")
done < "${pending_queue}"
if [[ "${#pending_tasks[@]}" -eq 0 ]]; then
  "${python_bin}" "${summary}" \
    --jobs-dir "${jobs_dir}" \
    --queue-file "${canonical_queue}" \
    --output-dir "${state_dir}/analysis" \
    --dataset-commit "${actual_commit}"
  echo "All cohort tasks already have terminal results."
  exit 0
fi

/bin/bash "${verifier_cache_builder}" \
  --cache-root "${PI_TBENCH_VERIFIER_CACHE}"

# Build all thin images before model execution so image construction and
# resource-heavy task containers do not contend for the 8GB Docker budget.
/bin/bash "${builder}" --build-only --keep-images "${pending_tasks[@]}"

set +e
"${python_bin}" "${schedule}" \
  --queue "${pending_queue}" \
  --jobs-dir "${jobs_dir}" \
  --generated-root "${generated_root}" \
  --config "${config}" \
  --workspace-root "${workspace_root}" \
  --harbor-bin "${harbor_bin}" \
  ${retry_queue:+--rerun-completed}
run_status="$?"
set -e

for task in "${pending_tasks[@]}"; do
  remove_task_image "${task}"
done

"${python_bin}" "${summary}" \
  --jobs-dir "${jobs_dir}" \
  --queue-file "${canonical_queue}" \
  --output-dir "${state_dir}/analysis" \
  --dataset-commit "${actual_commit}"
exit "${run_status}"
