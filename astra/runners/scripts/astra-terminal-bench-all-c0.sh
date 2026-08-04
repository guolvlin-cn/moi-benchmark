#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run all 89 tasks in the local Terminal-Bench 2.1 snapshot with Astra C0.

Usage:
  astra-terminal-bench-all-c0.sh [--check] [--yes]
                                      [--concurrency N]
                                      [--jobs-dir PATH]

Options:
  --check          Validate inputs and print Harbor's resolved config; do not run.
  --yes            Pass --yes to Harbor.
  --concurrency N  Number of concurrent trials (default: 1).
  --jobs-dir PATH  Result root (default: work/astra-c0-all-jobs).
  -h, --help       Show this help.

Environment overrides:
  HARBOR_BIN
  ASTRA_API_URL
  ASTRA_TBENCH_LINUX_BINARY
  ASTRA_TBENCH_MODEL
  ASTRA_TBENCH_READ_MEMORY
  ASTRA_ACCESS_TOKEN                 Required only when memory reads are enabled.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "$script_dir/../../.." && pwd)"
config_path="$workspace_root/astra/runners/astra_terminal_bench/c0-four-cases.yaml"
tasks_dir="$workspace_root/work/terminal-bench-2-1/tasks"
jobs_dir="$workspace_root/work/astra-c0-all-jobs"
concurrency=1
check_only=false
assume_yes=false

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
  --n-concurrent "$concurrency"
  --agent-timeout-multiplier 2.5
  --agent-kwarg "turn_timeout_sec=$astra_inner_timeout_sec"
  --agent-kwarg "trigger_timeout_sec=$astra_inner_timeout_sec"
  --agent-kwarg "stream_transport_retries=2"
)

echo "Harbor: $harbor_version"
echo "Condition: C0 (task-specific trigger when registered; generic product-live otherwise)"
echo "Tasks: $task_count"
echo "Concurrency: $concurrency"
echo "Product timeout: each task's upstream [agent].timeout_sec x 2.25"
echo "Harbor agent phase timeout: upstream timeout x 2.5 (includes cleanup and trajectory)"
echo "LLM fallback timeout: 600 seconds"
echo "Stream transport retries: 2 (same Astra session)"
echo "Jobs directory: $jobs_dir"
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

"$harbor_bin" "${harbor_args[@]}"
