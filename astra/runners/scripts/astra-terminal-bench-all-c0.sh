#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run all 89 tasks in the local Terminal-Bench 2.1 snapshot with Astra C0.

Usage:
  astra-terminal-bench-all-c0.sh [--check] [--yes]
                                      [--concurrency N]
                                      [--jobs-dir PATH]
                                      [--run-name NAME]

Options:
  --check          Validate inputs and print Harbor's resolved config; do not run.
  --yes            Pass --yes to Harbor.
  --concurrency N  Number of concurrent trials (default: 1).
  --jobs-dir PATH  Result root (default: work/astra-c0-all-jobs).
  --run-name NAME  Harbor job name (default: astra-c0-YYYYMMDD-HHMMSS).
  -h, --help       Show this help.

This command always starts all 89 tasks. It is not a resumable pending queue.
Use a new run name for each complete reproduction.

Environment overrides:
  HARBOR_BIN
  MOI_BENCH_DATA_ROOT               Dataset/result root (default: repository root).
  ASTRA_API_URL
  ASTRA_TBENCH_LINUX_BINARY
  ASTRA_TBENCH_MODEL
  ASTRA_TBENCH_READ_MEMORY
  ASTRA_ACCESS_TOKEN                 Required only when memory reads are enabled.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "$script_dir/../../.." && pwd)"
data_root="${MOI_BENCH_DATA_ROOT:-$workspace_root}"
config_path="$workspace_root/astra/runners/astra_terminal_bench/c0-four-cases.yaml"
dataset_root="$data_root/work/terminal-bench-2-1"
tasks_dir="$dataset_root/tasks"
jobs_dir="$data_root/work/astra-c0-all-jobs"
expected_dataset_commit="5c8eadf1f393183288fa08b8f73ca9a469cc5e00"
concurrency=1
check_only=false
assume_yes=false
run_name=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      check_only=true
      shift
      ;;
    --yes)
      assume_yes=true
      shift
      ;;
    --concurrency)
      [[ $# -ge 2 ]] || {
        echo "--concurrency requires a value" >&2
        exit 2
      }
      concurrency="$2"
      shift 2
      ;;
    --jobs-dir)
      [[ $# -ge 2 ]] || {
        echo "--jobs-dir requires a value" >&2
        exit 2
      }
      jobs_dir="$2"
      shift 2
      ;;
    --run-name)
      [[ $# -ge 2 ]] || {
        echo "--run-name requires a value" >&2
        exit 2
      }
      run_name="$2"
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

if ! [[ "$concurrency" =~ ^[1-9][0-9]*$ ]]; then
  echo "--concurrency must be a positive integer" >&2
  exit 2
fi
if [[ -z "$run_name" ]]; then
  run_name="astra-c0-$(date '+%Y%m%d-%H%M%S')"
fi
if ! [[ "$run_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "--run-name may contain only letters, digits, dot, underscore, and hyphen" >&2
  exit 2
fi

if [[ -n "${HARBOR_BIN:-}" ]]; then
  harbor_bin="$HARBOR_BIN"
elif command -v harbor >/dev/null 2>&1; then
  harbor_bin="$(command -v harbor)"
elif [[ -x "$HOME/.local/bin/harbor" ]]; then
  harbor_bin="$HOME/.local/bin/harbor"
else
  echo "harbor was not found; install Harbor 0.20.0 or set HARBOR_BIN" >&2
  exit 2
fi

harbor_version="$("$harbor_bin" --version 2>&1 | tail -n 1 | tr -d '[:space:]')"
if [[ "$harbor_version" != "0.20.0" ]]; then
  echo "this runner is pinned to Harbor 0.20.0; found: $harbor_version" >&2
  exit 2
fi

[[ -f "$config_path" ]] || {
  echo "missing Astra C0 config: $config_path" >&2
  exit 2
}
[[ -d "$tasks_dir" ]] || {
  echo "missing Terminal-Bench task directory: $tasks_dir" >&2
  exit 2
}

actual_dataset_commit="$(git -C "$dataset_root" rev-parse HEAD 2>/dev/null)" || {
  echo "Terminal-Bench snapshot is not a readable Git checkout: $dataset_root" >&2
  exit 2
}
if [[ "$actual_dataset_commit" != "$expected_dataset_commit" ]]; then
  echo "unexpected Terminal-Bench commit: $actual_dataset_commit" >&2
  echo "expected: $expected_dataset_commit" >&2
  exit 2
fi
dataset_changes="$(
  git -C "$dataset_root" status --short --untracked-files=all -- tasks
)"
if [[ -n "$dataset_changes" ]]; then
  echo "Terminal-Bench task snapshot has local changes:" >&2
  printf '%s\n' "$dataset_changes" >&2
  exit 2
fi

task_count="$(
  find "$tasks_dir" -mindepth 2 -maxdepth 2 -type f -name task.toml -print |
    wc -l |
    tr -d '[:space:]'
)"
if [[ "$task_count" != "89" ]]; then
  echo "expected the pinned Terminal-Bench 2.1 snapshot with 89 tasks; found $task_count" >&2
  exit 2
fi

export ASTRA_API_URL="${ASTRA_API_URL:-http://host.docker.internal:17001}"
export ASTRA_TBENCH_LINUX_BINARY="${ASTRA_TBENCH_LINUX_BINARY:-$workspace_root/work/astra-linux-build-amd64/target/release/astra}"
export ASTRA_TBENCH_MODEL="${ASTRA_TBENCH_MODEL:-c5bde5de-9805-48d4-a016-1db6e6018fc4}"
export ASTRA_TBENCH_READ_MEMORY="${ASTRA_TBENCH_READ_MEMORY:-false}"
export PYTHONPATH="$workspace_root${PYTHONPATH:+:$PYTHONPATH}"

case "$ASTRA_API_URL" in
  http://host.docker.internal|http://host.docker.internal:*|https://host.docker.internal|https://host.docker.internal:*)
    ;;
  *)
    echo "ASTRA_API_URL must use host.docker.internal from Docker tasks" >&2
    exit 2
    ;;
esac

[[ -f "$ASTRA_TBENCH_LINUX_BINARY" ]] || {
  echo "missing Linux Astra binary: $ASTRA_TBENCH_LINUX_BINARY" >&2
  exit 2
}
binary_description="$(file "$ASTRA_TBENCH_LINUX_BINARY")"
if [[ "$binary_description" != *"ELF 64-bit"* || "$binary_description" != *"x86-64"* ]]; then
  echo "the pinned Terminal-Bench images require an x86-64 Linux Astra ELF" >&2
  echo "$binary_description" >&2
  exit 2
fi

case "$ASTRA_TBENCH_READ_MEMORY" in
  true|TRUE|True|1|yes|YES|Yes|on|ON|On)
    if [[ -z "${ASTRA_ACCESS_TOKEN:-}" ]]; then
      echo "ASTRA_ACCESS_TOKEN is required when ASTRA_TBENCH_READ_MEMORY=true" >&2
      exit 2
    fi
    ;;
  false|FALSE|False|0|no|NO|No|off|OFF|Off)
    ;;
  *)
    echo "ASTRA_TBENCH_READ_MEMORY must be a boolean value" >&2
    exit 2
    ;;
esac

# The snapshot's largest upstream [agent].timeout_sec is 12000 seconds.
# The product applies the 2.25-times limit per task. This inner Astra cap is raised
# to the largest resulting budget so it cannot truncate the other 88 tasks.
astra_inner_timeout_sec=27000

harbor_args=(
  run
  --config "$config_path"
  --path "$tasks_dir"
  --jobs-dir "$jobs_dir"
  --job-name "$run_name"
  --n-concurrent "$concurrency"
  --agent-timeout-multiplier 2.5
  --agent-kwarg "turn_timeout_sec=$astra_inner_timeout_sec"
  --agent-kwarg "trigger_timeout_sec=$astra_inner_timeout_sec"
  --agent-kwarg "stream_transport_retries=2"
)

echo "Harbor: $harbor_version"
echo "Workspace commit: $(git -C "$workspace_root" rev-parse HEAD)"
echo "Dataset commit: $actual_dataset_commit"
echo "Condition: C0 (task-specific trigger when registered; generic product-live otherwise)"
echo "Tasks: $task_count"
echo "Concurrency: $concurrency"
echo "Product timeout: each task's upstream [agent].timeout_sec x 2.25"
echo "Harbor agent phase timeout: upstream timeout x 2.5 (includes cleanup and trajectory)"
echo "LLM fallback timeout: 600 seconds"
echo "Stream transport retries: 2 (same Astra session)"
echo "Jobs directory: $jobs_dir"
echo "Run name: $run_name"
echo "Astra binary: $ASTRA_TBENCH_LINUX_BINARY"
echo "Astra model: $ASTRA_TBENCH_MODEL"
echo "Read existing user memory: $ASTRA_TBENCH_READ_MEMORY"

if [[ "$check_only" == true ]]; then
  if [[ -n "${ASTRA_ACCESS_TOKEN:-}" ]]; then
    ASTRA_ACCESS_TOKEN=redacted-for-config-check \
      "$harbor_bin" "${harbor_args[@]}" --print-config
  else
    "$harbor_bin" "${harbor_args[@]}" --print-config
  fi
  exit 0
fi

if [[ "$assume_yes" == true ]]; then
  harbor_args+=(--yes)
fi

manifest_dir="$jobs_dir/.reproduction"
manifest_path="$manifest_dir/$run_name.tsv"
mkdir -p "$manifest_dir"
if [[ -e "$manifest_path" ]]; then
  echo "reproduction manifest already exists for run name: $run_name" >&2
  echo "choose a new --run-name" >&2
  exit 2
fi
workspace_commit="$(git -C "$workspace_root" rev-parse HEAD)"
workspace_tracked_state="clean"
git -C "$workspace_root" diff --quiet -- . || workspace_tracked_state="dirty"
git -C "$workspace_root" diff --cached --quiet -- . || workspace_tracked_state="dirty"
{
  printf 'schema_version\t1\n'
  printf 'run_name\t%s\n' "$run_name"
  printf 'workspace_commit\t%s\n' "$workspace_commit"
  printf 'workspace_tracked_state\t%s\n' "$workspace_tracked_state"
  printf 'dataset_commit\t%s\n' "$actual_dataset_commit"
  printf 'harbor_version\t%s\n' "$harbor_version"
  printf 'condition\tC0\n'
  printf 'lifecycle_audit_is_score_gate\tfalse\n'
  printf 'task_count\t%s\n' "$task_count"
  printf 'concurrency\t%s\n' "$concurrency"
  printf 'jobs_dir\t%s\n' "$jobs_dir"
  printf 'astra_api_url\t%s\n' "$ASTRA_API_URL"
  printf 'astra_binary\t%s\n' "$ASTRA_TBENCH_LINUX_BINARY"
  printf 'astra_binary_description\t%s\n' "$binary_description"
  printf 'astra_model\t%s\n' "$ASTRA_TBENCH_MODEL"
  printf 'astra_read_memory\t%s\n' "$ASTRA_TBENCH_READ_MEMORY"
  printf 'product_timeout_policy\tupstream_agent_timeout_x_2.25\n'
  printf 'harbor_agent_timeout_policy\tupstream_agent_timeout_x_2.5\n'
  printf 'stream_transport_retries\t2\n'
} > "$manifest_path"

set +e
"$harbor_bin" "${harbor_args[@]}"
run_status="$?"
set -e
printf 'harbor_exit_code\t%s\n' "$run_status" >> "$manifest_path"
echo "Reproduction manifest: $manifest_path"
exit "$run_status"
