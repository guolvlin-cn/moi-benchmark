#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run or resume all 89 Terminal-Bench 2.1 tasks with prebuilt Hermes C0.

Usage:
  hermes-terminal-bench-all-c0.sh [OPTIONS]

Options:
  --check          Validate the snapshot and prepare a pending queue only.
  --max-tasks N    Run at most N currently pending tasks in this invocation.
  --retry-errors   Schedule tasks whose latest recorded trial is an exception.
  --retry-audit-failures
                   Schedule tasks whose C0 audit is no_hit or infra_error.
  --rerun-all      Ignore recorded results and schedule the full 89-task queue.
  --state-dir DIR  Summary and pending-queue directory.
  -h, --help       Show this help.

The shared Hermes runtime is retained. Each task-derived image is built on
demand with --no-cache, used for one Harbor job, and then deleted. Completed
trial results are discovered from work/hermes-c0-all-jobs, so rerunning this
script resumes missing tasks.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "${script_dir}/../../.." && pwd)"
export MOI_BENCH_ROOT="${MOI_BENCH_ROOT:-${workspace_root}}"
runner_root="${workspace_root}/astra/runners/hermes_terminal_bench"
builder="${runner_root}/prebuilt/build-images.sh"
summarizer="${runner_root}/prebuilt/summarize_results.py"
config="${runner_root}/c0-all-prebuilt.yaml"
full_queue="${runner_root}/prebuilt/c0-all.queue.txt"
tasks_root="${workspace_root}/work/terminal-bench-2-1/tasks"
dataset_root="${workspace_root}/work/terminal-bench-2-1"
expected_dataset_commit="5c8eadf1f393183288fa08b8f73ca9a469cc5e00"
jobs_dir="${workspace_root}/work/hermes-c0-all-jobs"
state_dir="${workspace_root}/work/hermes-c0-all-state"
full_run_lock="${workspace_root}/work/.hermes-c0-all-run.lock"
cohort_fingerprint_path="${jobs_dir}/.moi-hermes-c0-cohort.sha256"
cohort_manifest_path="${jobs_dir}/.moi-hermes-c0-cohort.txt"
full_run_lock_acquired=false
check_only=false
retry_errors=false
retry_audit_failures=false
rerun_all=false
max_tasks=""

release_full_run_lock() {
  [[ "${full_run_lock_acquired}" == "true" ]] || return 0
  if ! rmdir "${full_run_lock}"; then
    echo "warning: unable to release full-run lock: ${full_run_lock}" >&2
    return 1
  fi
  full_run_lock_acquired=false
}

trap release_full_run_lock EXIT

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --check)
      check_only=true
      shift
      ;;
    --max-tasks)
      [[ "$#" -ge 2 ]] || {
        echo "--max-tasks requires a value" >&2
        exit 2
      }
      max_tasks="$2"
      shift 2
      ;;
    --retry-errors)
      retry_errors=true
      shift
      ;;
    --retry-audit-failures)
      retry_audit_failures=true
      shift
      ;;
    --rerun-all)
      rerun_all=true
      shift
      ;;
    --state-dir)
      [[ "$#" -ge 2 ]] || {
        echo "--state-dir requires a path" >&2
        exit 2
      }
      state_dir="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -n "${max_tasks}" && ! "${max_tasks}" =~ ^[1-9][0-9]*$ ]]; then
  echo "--max-tasks must be a positive integer" >&2
  exit 2
fi

for required in \
  "${builder}" \
  "${summarizer}" \
  "${config}" \
  "${full_queue}"; do
  [[ -f "${required}" ]] || {
    echo "missing required runner file: ${required}" >&2
    exit 2
  }
done
[[ -d "${tasks_root}" ]] || {
  echo "missing Terminal-Bench task directory: ${tasks_root}" >&2
  exit 2
}
actual_dataset_commit="$(git -C "${dataset_root}" rev-parse HEAD 2>/dev/null)" \
  || {
    echo "Terminal-Bench snapshot is not a readable Git checkout" >&2
    exit 2
  }
[[ "${actual_dataset_commit}" == "${expected_dataset_commit}" ]] || {
  echo "unexpected Terminal-Bench commit: ${actual_dataset_commit}" >&2
  echo "expected: ${expected_dataset_commit}" >&2
  exit 2
}
dataset_changes="$(
  git -C "${dataset_root}" status --short --untracked-files=all -- tasks
)"
[[ -z "${dataset_changes}" ]] || {
  echo "Terminal-Bench task snapshot has local changes:" >&2
  printf '%s\n' "${dataset_changes}" >&2
  exit 2
}

if [[ -n "${HARBOR_BIN:-}" ]]; then
  harbor_bin="${HARBOR_BIN}"
elif command -v harbor >/dev/null 2>&1; then
  harbor_bin="$(command -v harbor)"
elif [[ -x "${HOME}/.local/bin/harbor" ]]; then
  harbor_bin="${HOME}/.local/bin/harbor"
else
  echo "Harbor was not found; set HARBOR_BIN to Harbor 0.20.0" >&2
  exit 2
fi
harbor_version="$("${harbor_bin}" --version 2>&1 | tail -n 1 | tr -d '[:space:]')"
[[ "${harbor_version}" == "0.20.0" ]] || {
  echo "this runner requires Harbor 0.20.0; found: ${harbor_version}" >&2
  exit 2
}
export HARBOR_BIN="${harbor_bin}"

if [[ -n "${HERMES_FULL_PYTHON_BIN:-}" ]]; then
  python_bin="${HERMES_FULL_PYTHON_BIN}"
elif [[ -x "${HOME}/.local/share/uv/tools/harbor/bin/python" ]]; then
  python_bin="${HOME}/.local/share/uv/tools/harbor/bin/python"
else
  python_bin="$(command -v python3)"
fi
export PYTHON_BIN="${python_bin}"
export PYTHONPATH="${workspace_root}${PYTHONPATH:+:${PYTHONPATH}}"
generated_tasks_root="${workspace_root}/work/terminal-bench-2-1-hermes-prebuilt/tasks"
export HERMES_TBENCH_GENERATED_TASKS_ROOT="${generated_tasks_root}"
export HERMES_PREBUILT_IMAGE_PREFIX="moi/hermes-tbench"
export HERMES_PREBUILT_IMAGE_TAG="v2026.7.20"
export HERMES_PREBUILT_RUNTIME_IMAGE="moi/hermes-tbench-runtime:v2026.7.20"
runtime_base_image="${HERMES_PREBUILT_RUNTIME_BASE_IMAGE:-alexgshaw/modernize-scientific-stack:20251031}"
export HERMES_PREBUILT_RUNTIME_BASE_IMAGE="${runtime_base_image}"
export HERMES_PREBUILT_LOCK_DIR="${workspace_root}/work/.hermes-prebuilt-image-queue.lock"

cohort_files=(
  "${runner_root}/agent.py"
  "${runner_root}/gateway_driver.py"
  "${runner_root}/managed/config.yaml"
  "${runner_root}/managed/.env"
  "${runner_root}/policy_guard/sitecustomize.py"
  "${runner_root}/c0-all-prebuilt.yaml"
  "${runner_root}/prebuilt/build-images.sh"
  "${runner_root}/prebuilt/Dockerfile"
  "${runner_root}/prebuilt/Dockerfile.task"
  "${runner_root}/prebuilt/configure_temperature.py"
  "${runner_root}/prebuilt/prepare_tasks.py"
  "${runner_root}/prebuilt/c0-all.queue.txt"
  "${workspace_root}/astra/runners/astra_smoke/core.py"
  "${workspace_root}/astra/runners/astra_smoke/probe.py"
  "${workspace_root}/astra/runners/lifecycle_c0/__init__.py"
  "${workspace_root}/astra/runners/lifecycle_c0/core.py"
  "${workspace_root}/astra/runners/lifecycle_c0/predicate_probe.py"
)

compute_cohort_manifest() {
  local cohort_file
  local cohort_file_sha256

  printf 'dataset_commit %s\n' "${actual_dataset_commit}"
  printf 'runtime_base_image %s\n' "${HERMES_PREBUILT_RUNTIME_BASE_IMAGE}"
  printf 'runtime_image %s\n' "${HERMES_PREBUILT_RUNTIME_IMAGE}"
  printf 'task_image_prefix %s\n' "${HERMES_PREBUILT_IMAGE_PREFIX}"
  printf 'task_image_tag %s\n' "${HERMES_PREBUILT_IMAGE_TAG}"
  for cohort_file in "${cohort_files[@]}"; do
    [[ -f "${cohort_file}" ]] || {
      echo "missing cohort file: ${cohort_file}" >&2
      exit 2
    }
    cohort_file_sha256="$(shasum -a 256 "${cohort_file}" | awk '{print $1}')"
    printf '%s %s\n' \
      "${cohort_file#"${workspace_root}/"}" \
      "${cohort_file_sha256}"
  done
}

compute_cohort_fingerprint() {
  printf '%s\n' "$1" |
    shasum -a 256 |
    awk '{print $1}'
}

verify_current_cohort() {
  local current_dataset_changes
  local current_dataset_commit
  local current_fingerprint
  local current_manifest

  current_dataset_commit="$(
    git -C "${dataset_root}" rev-parse HEAD 2>/dev/null
  )" || return 1
  [[ "${current_dataset_commit}" == "${expected_dataset_commit}" ]] \
    || return 1
  current_dataset_changes="$(
    git -C "${dataset_root}" status --short --untracked-files=all -- tasks
  )" || return 1
  [[ -z "${current_dataset_changes}" ]] || return 1
  current_manifest="$(compute_cohort_manifest)" || return 1
  current_fingerprint="$(
    compute_cohort_fingerprint "${current_manifest}"
  )" || return 1
  [[ "${current_fingerprint}" == "${cohort_fingerprint}" ]]
}

cohort_manifest="$(compute_cohort_manifest)"
cohort_fingerprint="$(
  compute_cohort_fingerprint "${cohort_manifest}"
)"

resolved_queue="$(
  /bin/bash "${builder}" \
    --tasks-root "${tasks_root}" \
    --print-queue \
    --queue-file "${full_queue}"
)"
task_count="$(
  find "${tasks_root}" -mindepth 2 -maxdepth 2 -type f \
    -name task.toml -print |
    wc -l |
    tr -d '[:space:]'
)"
queue_count="$(printf '%s\n' "${resolved_queue}" | wc -l | tr -d '[:space:]')"
[[ "${task_count}" == "89" && "${queue_count}" == "89" ]] || {
  echo "expected 89 snapshot tasks and 89 queued tasks; found ${task_count}/${queue_count}" >&2
  exit 2
}
queue_difference="$(
  comm -3 \
    <(
      find "${tasks_root}" -mindepth 2 -maxdepth 2 -type f \
        -name task.toml -print |
        awk -F/ '{print $(NF-1)}' |
        LC_ALL=C sort
    ) \
    <(printf '%s\n' "${resolved_queue}" | LC_ALL=C sort)
)"
[[ -z "${queue_difference}" ]] || {
  echo "the pinned full queue does not match the 89-task snapshot:" >&2
  printf '%s\n' "${queue_difference}" >&2
  exit 2
}

mkdir -p "$(dirname "${full_run_lock}")"
if ! mkdir "${full_run_lock}" 2>/dev/null; then
  echo "another Hermes full-run wrapper may be active: ${full_run_lock}" >&2
  exit 2
fi
full_run_lock_acquired=true

mkdir -p "${jobs_dir}"
shopt -s nullglob
existing_results=("${jobs_dir}"/*/*/result.json)
shopt -u nullglob
if [[ -f "${cohort_fingerprint_path}" ]]; then
  recorded_cohort_fingerprint="$(
    tr -d '[:space:]' < "${cohort_fingerprint_path}"
  )"
  if [[ "${recorded_cohort_fingerprint}" != "${cohort_fingerprint}" ]]; then
    [[ "${#existing_results[@]}" -eq 0 ]] || {
      echo "full-run cohort changed; refusing to mix result generations" >&2
      echo "recorded: ${recorded_cohort_fingerprint}" >&2
      echo "current:  ${cohort_fingerprint}" >&2
      exit 2
    }
    printf '%s\n' "${cohort_fingerprint}" > "${cohort_fingerprint_path}"
    printf '%s\n' "${cohort_manifest}" > "${cohort_manifest_path}"
  elif [[ ! -f "${cohort_manifest_path}" ]]; then
    [[ "${#existing_results[@]}" -eq 0 ]] || {
      echo "cohort manifest is missing for recorded results: ${jobs_dir}" >&2
      exit 2
    }
    printf '%s\n' "${cohort_manifest}" > "${cohort_manifest_path}"
  fi
else
  [[ "${#existing_results[@]}" -eq 0 ]] || {
    echo "jobs directory has results but no cohort fingerprint" >&2
    echo "refusing to adopt legacy results: ${jobs_dir}" >&2
    exit 2
  }
  printf '%s\n' "${cohort_fingerprint}" > "${cohort_fingerprint_path}"
  printf '%s\n' "${cohort_manifest}" > "${cohort_manifest_path}"
fi

summary_args=(
  "${python_bin}"
  "${summarizer}"
  --jobs-dir "${jobs_dir}"
  --queue-file "${full_queue}"
  --output-dir "${state_dir}"
  --dataset-commit "${actual_dataset_commit}"
  --cohort-fingerprint "${cohort_fingerprint}"
)
[[ "${retry_errors}" == "false" ]] \
  || summary_args+=(--retry-errors)
[[ "${retry_audit_failures}" == "false" ]] \
  || summary_args+=(--retry-audit-failures)
[[ "${rerun_all}" == "false" ]] \
  || summary_args+=(--rerun-all)
[[ -z "${max_tasks}" ]] \
  || summary_args+=(--max-tasks "${max_tasks}")
"${summary_args[@]}"

pending_queue="${state_dir}/pending.queue.txt"
scheduled_count="$(
  sed '/^[[:space:]]*$/d' "${pending_queue}" | wc -l | tr -d '[:space:]'
)"

echo "Harbor: ${harbor_version}"
echo "Condition: C0 (4 task-specific triggers; generic product-live for 85 tasks)"
echo "Temperature: 0.0 (prebuilt ZAI provider profile)"
echo "Dataset commit: ${actual_dataset_commit}"
echo "Tasks scheduled now: ${scheduled_count}"
echo "Jobs directory: ${jobs_dir}"
echo "State directory: ${state_dir}"
echo "Execution: sequential on-demand image build, run, and deletion"
echo "Worst-case product budgets total about 84.4 hours before build/verifier overhead"

if [[ "${check_only}" == "true" ]]; then
  echo "Check complete; no Docker build, model call, or trial was started."
  exit 0
fi
[[ -n "${GLM_API_KEY:-}" ]] || {
  echo "GLM_API_KEY is required to start the full run" >&2
  exit 2
}
if [[ "${scheduled_count}" == "0" ]]; then
  echo "All expected tasks already have recorded terminal results."
  exit 0
fi

run_status=0
active_queue="${state_dir}/active.queue.txt"
cp "${pending_queue}" "${active_queue}"
while IFS= read -r task_name || [[ -n "${task_name}" ]]; do
  [[ -n "${task_name}" ]] || continue
  if ! verify_current_cohort; then
    echo "cohort changed before ${task_name}; refusing to continue" >&2
    run_status=1
    break
  fi
  if ! /bin/bash "${builder}" \
    --config "${config}" \
    --tasks-root "${tasks_root}" \
    "${task_name}"; then
    echo "full-run task failed: ${task_name}" >&2
    run_status=1
  fi
  if ! verify_current_cohort; then
    echo "cohort changed while ${task_name} was running; refusing to continue" >&2
    run_status=1
    break
  fi
  "${python_bin}" "${summarizer}" \
    --jobs-dir "${jobs_dir}" \
    --queue-file "${full_queue}" \
    --output-dir "${state_dir}" \
    --dataset-commit "${actual_dataset_commit}" \
    --cohort-fingerprint "${cohort_fingerprint}" \
    || {
      echo "warning: result summary failed after ${task_name}" >&2
      run_status=1
    }
done < "${active_queue}"

exit "${run_status}"
