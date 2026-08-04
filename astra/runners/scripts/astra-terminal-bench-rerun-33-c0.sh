#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run one architecture queue from the frozen exact-33 Astra C0 rerun.

Usage:
  astra-terminal-bench-rerun-33-c0.sh --arch amd64|arm64
      --manifest PATH --manifest-sha256 SHA256
      [--task NAME] [--check] [--yes] [--jobs-dir PATH]

Options:
  --arch ARCH              Required. Run only the frozen amd64 or arm64 queue.
  --manifest PATH          Frozen JSON produced by freeze_rerun_33.py.
  --manifest-sha256 HASH   Required out-of-band SHA-256 printed by the freezer.
  --task NAME              Run one task; it must be in the selected frozen queue.
                           Use --arch amd64 --task tune-mjcf for its native-only
                           queue; it is excluded from the ordinary amd64 queue.
  --check                  Validate the freeze and print resolved Harbor config.
  --yes                    Pass --yes to Harbor for an actual run.
  --jobs-dir PATH          Result root (default:
                           work/astra-c0-rerun-from-scratch-33/jobs).
  -h, --help               Show this help.

Environment overrides:
  HARBOR_BIN
  HARBOR_PYTHON
  DOCKER_BIN
  ASTRA_API_URL
  ASTRA_ACCESS_TOKEN       Used only for fresh isolated identity registration.

This driver fixes concurrency=1, n_attempts=1, Harbor max_retries=0,
max_turns=50, stream retries=2, optional retry threshold=930 seconds,
the model ID, and read_memory=false. It never combines architectures.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "$script_dir/../../.." && pwd)"
config_path="$workspace_root/astra/runners/astra_terminal_bench/c0-four-cases.yaml"
task_list_path="$workspace_root/astra/runners/astra_terminal_bench/rerun-from-scratch-33.tasks.txt"
host_overlay_path="$workspace_root/astra/runners/astra_terminal_bench/host-docker-internal.compose.yaml"
model_freeze_path="$workspace_root/astra/runners/astra_terminal_bench/model-c5bde5de.freeze.json"
tasks_dir="$workspace_root/work/terminal-bench-2-1/tasks"
default_manifest="$workspace_root/work/astra-c0-rerun-from-scratch-33/frozen-inputs.json"
jobs_dir="$workspace_root/work/astra-c0-rerun-from-scratch-33/jobs"
legacy_jobs_dir="$workspace_root/work/astra-c0-all-jobs"

fixed_model="c5bde5de-9805-48d4-a016-1db6e6018fc4"
fixed_api_url="http://host.docker.internal:17001"
fixed_max_turns=50
fixed_stream_retries=2
fixed_optional_retry_min_remaining_sec=930
fixed_timeout_multiplier=2.0
fixed_harbor_agent_timeout_multiplier=2.5
fixed_harbor_verifier_timeout_multiplier=2.0
fixed_harbor_agent_setup_timeout_multiplier=2.0
fixed_harbor_environment_build_timeout_multiplier=2.0

architecture=""
manifest_path="$default_manifest"
expected_manifest_sha256="${ASTRA_TBENCH_EXPECTED_FREEZE_MANIFEST_SHA256:-}"
single_task=""
check_only=false
assume_yes=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch)
      [[ $# -ge 2 ]] || {
        echo "--arch requires a value" >&2
        exit 2
      }
      architecture="$2"
      shift 2
      ;;
    --manifest)
      [[ $# -ge 2 ]] || {
        echo "--manifest requires a value" >&2
        exit 2
      }
      manifest_path="$2"
      shift 2
      ;;
    --manifest-sha256)
      [[ $# -ge 2 ]] || {
        echo "--manifest-sha256 requires a value" >&2
        exit 2
      }
      expected_manifest_sha256="$2"
      shift 2
      ;;
    --task)
      [[ $# -ge 2 ]] || {
        echo "--task requires a value" >&2
        exit 2
      }
      single_task="$2"
      shift 2
      ;;
    --check)
      check_only=true
      shift
      ;;
    --yes)
      assume_yes=true
      shift
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

case "$architecture" in
  amd64|arm64)
    ;;
  "")
    echo "--arch amd64|arm64 is required" >&2
    exit 2
    ;;
  *)
    echo "--arch must be amd64 or arm64" >&2
    exit 2
    ;;
esac

if ! [[ "$expected_manifest_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "--manifest-sha256 must be the lowercase SHA-256 printed by the freezer" >&2
  exit 2
fi

[[ -f "$manifest_path" ]] || {
  echo "missing frozen manifest: $manifest_path" >&2
  exit 2
}
[[ -f "$config_path" ]] || {
  echo "missing Astra C0 config: $config_path" >&2
  exit 2
}
[[ -f "$task_list_path" ]] || {
  echo "missing exact-33 task list: $task_list_path" >&2
  exit 2
}
[[ -f "$host_overlay_path" ]] || {
  echo "missing frozen host gateway overlay: $host_overlay_path" >&2
  exit 2
}
[[ -f "$model_freeze_path" ]] || {
  echo "missing frozen model metadata: $model_freeze_path" >&2
  exit 2
}
[[ -d "$tasks_dir" ]] || {
  echo "missing Terminal-Bench task directory: $tasks_dir" >&2
  exit 2
}

jobs_dir="$(
  cd "$(dirname "$jobs_dir")" 2>/dev/null &&
    printf '%s/%s\n' "$PWD" "$(basename "$jobs_dir")"
)" || {
  echo "the parent of --jobs-dir must already exist: $(dirname "$jobs_dir")" >&2
  exit 2
}
if [[ "$jobs_dir" == "$legacy_jobs_dir" ]]; then
  echo "refusing to write this rerun into the original all-jobs directory" >&2
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

if [[ -n "${HARBOR_PYTHON:-}" ]]; then
  harbor_python="$HARBOR_PYTHON"
else
  harbor_shebang="$(head -n 1 "$harbor_bin" 2>/dev/null || true)"
  harbor_python="${harbor_shebang#\#!}"
fi
if [[ ! -x "$harbor_python" ]]; then
  echo "could not resolve Harbor's Python; set HARBOR_PYTHON" >&2
  exit 2
fi

docker_bin="${DOCKER_BIN:-docker}"
if ! command -v "$docker_bin" >/dev/null 2>&1; then
  echo "docker was not found; set DOCKER_BIN" >&2
  exit 2
fi

export ASTRA_API_URL="${ASTRA_API_URL:-$fixed_api_url}"
if [[ "$ASTRA_API_URL" != "$fixed_api_url" ]]; then
  echo "ASTRA_API_URL is frozen to $fixed_api_url" >&2
  exit 2
fi
export ASTRA_TBENCH_MODEL="$fixed_model"
export ASTRA_TBENCH_READ_MEMORY=false
export PYTHONPATH="$workspace_root${PYTHONPATH:+:$PYTHONPATH}"

command -v curl >/dev/null 2>&1 || {
  echo "curl is required for the Astra API health preflight" >&2
  exit 2
}
api_health="$(
  curl --silent --show-error --fail --max-time 5 \
    http://127.0.0.1:17001/health
)" || {
  echo "Astra API health preflight failed on http://127.0.0.1:17001/health" >&2
  exit 2
}
printf '%s' "$api_health" |
  "$harbor_python" -c '
import json
import sys

try:
    health = json.load(sys.stdin)
except (json.JSONDecodeError, TypeError) as exc:
    raise SystemExit(f"invalid Astra API health response: {exc}")
if health.get("status") != "healthy" or health.get("database") != "connected":
    raise SystemExit(f"Astra API is not healthy: {health}")
'

validation_output="$(
  "$harbor_python" - \
    "$manifest_path" \
    "$expected_manifest_sha256" \
    "$task_list_path" \
    "$tasks_dir" \
    "$architecture" \
    "$single_task" \
    "$docker_bin" \
    "$workspace_root" \
    "$fixed_model" <<'PY'
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

(
    manifest_arg,
    expected_manifest_sha256,
    task_list_arg,
    tasks_dir_arg,
    selected_arch,
    single_task,
    docker_bin,
    workspace_root_arg,
    fixed_model,
) = sys.argv[1:]

manifest_path = Path(manifest_arg).resolve()
task_list_path = Path(task_list_arg).resolve()
tasks_dir = Path(tasks_dir_arg).resolve()
workspace_root = Path(workspace_root_arg).resolve()


def fail(message):
    raise SystemExit(f"frozen rerun validation failed: {message}")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def task_file_manifest(task_dir):
    records = []
    for path in sorted(task_dir.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(task_dir).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            records.append(
                {
                    "path": relative,
                    "type": "symlink",
                    "target": target,
                    "sha256": sha256_text(target),
                }
            )
        elif path.is_file():
            records.append(
                {
                    "path": relative,
                    "type": "file",
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return records, sha256_text(canonical)


def normalize_arch(value):
    aliases = {
        "amd64": "amd64",
        "x86_64": "amd64",
        "x86-64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    normalized = str(value).strip().lower()
    if normalized not in aliases:
        fail(f"unsupported architecture: {value!r}")
    return aliases[normalized]


def elf_arch(path):
    with path.open("rb") as handle:
        header = handle.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF":
        fail(f"Astra artifact is not ELF: {path}")
    byte_order = {1: "<", 2: ">"}.get(header[5])
    if byte_order is None:
        fail(f"invalid ELF byte order: {path}")
    machine = struct.unpack(f"{byte_order}H", header[18:20])[0]
    architectures = {62: "amd64", 183: "arm64"}
    if machine not in architectures:
        fail(f"unsupported ELF machine {machine}: {path}")
    return architectures[machine]


manifest_sha256 = sha256_file(manifest_path)
if manifest_sha256 != expected_manifest_sha256:
    fail(
        "manifest SHA-256 mismatch: "
        f"expected {expected_manifest_sha256}, found {manifest_sha256}"
    )
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"cannot read frozen manifest: {exc}")

if manifest.get("schema_version") != 1:
    fail("manifest schema_version must be 1")
if manifest.get("purpose") != "exact-33-from-scratch-c0-rerun-input-freeze":
    fail("unexpected manifest purpose")
if manifest.get("harbor_tasks_started") is not False:
    fail("manifest must state harbor_tasks_started=false")
if manifest.get("write_once") is not True:
    fail("manifest must be write-once")

task_names = [
    line.strip()
    for line in task_list_path.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]
if len(task_names) != 33 or len(set(task_names)) != 33:
    fail("the canonical rerun task list must contain 33 unique names")
if any(not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) for name in task_names):
    fail("canonical task names must not contain Harbor glob characters")

task_selection = manifest.get("task_selection", {})
if task_selection.get("expected_count") != 33:
    fail("manifest expected_count must be 33")
if task_selection.get("actual_count") != 33:
    fail("manifest actual_count must be 33")
if task_selection.get("unique") is not True:
    fail("manifest task selection must be unique")
if task_selection.get("names") != task_names:
    fail("manifest task order differs from the canonical exact-33 list")
if task_selection.get("manifest_sha256") != sha256_file(task_list_path):
    fail("the exact-33 task-list hash differs from the frozen value")

execution = manifest.get("execution", {})
if execution.get("condition") != "C0":
    fail("condition must be C0")
if execution.get("astra_api_url") != "http://host.docker.internal:17001":
    fail("Astra API URL differs from the frozen endpoint")
if execution.get("model") != fixed_model:
    fail("model differs from the fixed rerun model")
expected_model_freeze_path = str(
    (
        workspace_root
        / "astra"
        / "runners"
        / "astra_terminal_bench"
        / "model-c5bde5de.freeze.json"
    ).resolve()
)
try:
    model_snapshot = json.loads(
        Path(expected_model_freeze_path).read_text(encoding="utf-8")
    )
except (OSError, json.JSONDecodeError) as exc:
    fail(f"cannot parse frozen model metadata: {exc}")
if not isinstance(model_snapshot.get("model"), dict):
    fail("frozen model metadata has no model object")
if model_snapshot["model"].get("model_id") != fixed_model:
    fail("frozen model metadata has the wrong model ID")
if model_snapshot.get("secrets_included") is not False:
    fail("frozen model metadata must declare secrets_included=false")
expected_model_freeze = {
    "path": expected_model_freeze_path,
    "sha256": sha256_file(Path(expected_model_freeze_path)),
    "size_bytes": Path(expected_model_freeze_path).stat().st_size,
    "model_id": fixed_model,
    "secrets_included": False,
}
if execution.get("model_freeze") != expected_model_freeze:
    fail("model metadata differs from the frozen snapshot")
if execution.get("max_turns") != 50:
    fail("max_turns must be 50")
if execution.get("concurrency") != 1:
    fail("concurrency must be 1")
expected_overlay_path = str(
    (
        workspace_root
        / "astra"
        / "runners"
        / "astra_terminal_bench"
        / "host-docker-internal.compose.yaml"
    ).resolve()
)
if execution.get("environment") != {
    "type": "docker",
    "force_build": False,
    "delete": True,
    "extra_allowed_hosts": ["host.docker.internal"],
    "extra_docker_compose": [expected_overlay_path],
}:
    fail("environment policy differs from the frozen Docker policy")
permissions = execution.get("permissions", {})
if permissions.get("permission_mode") != "auto":
    fail("permission_mode must be auto")
if permissions.get("read_memory") is not False:
    fail("read_memory must be false")
budgets = execution.get("budgets", {})
if budgets.get("llm_fallback_timeout_sec") != 600:
    fail("LLM fallback timeout must be 600 seconds")
if budgets.get("llm_total_budget_sec") != 900:
    fail("LLM total budget must be 900 seconds")
if budgets.get("stream_transport_retries") != 2:
    fail("stream transport retry limit must be 2")
if budgets.get("product_timeout_multiplier") != 2.25:
    fail("product timeout multiplier must be 2.25")
retry_policy = budgets.get("retry_policy", {})
if retry_policy.get("first_retry_guaranteed") is not True:
    fail("the first stream retry must be guaranteed")
if retry_policy.get("additional_retries_require_remaining_budget") is not True:
    fail("the optional second retry must require remaining budget")
if retry_policy.get("optional_retry_min_remaining_seconds") != 930:
    fail("the optional retry threshold must be 930 seconds")
harbor_multipliers = budgets.get("harbor_timeout_multipliers", {})
expected_harbor_multipliers = {
    "timeout_multiplier": 2.0,
    "agent_timeout_multiplier": 2.5,
    "verifier_timeout_multiplier": 2.0,
    "agent_setup_timeout_multiplier": 2.0,
    "environment_build_timeout_multiplier": 2.0,
}
if harbor_multipliers != expected_harbor_multipliers:
    fail("Harbor timeout multipliers differ from the frozen policy")

from astra.runners.astra_terminal_bench import agent as live_agent

live_constants = {
    "C0_PRODUCT_TIMEOUT_MULTIPLIER": 2.25,
    "LLM_FALLBACK_TIMEOUT_SEC": 600,
    "LLM_TOTAL_BUDGET_SEC": 900,
    "STREAM_OPTIONAL_RETRY_MIN_REMAINING_SEC": 930,
}
for name, expected in live_constants.items():
    if getattr(live_agent, name, None) != expected:
        fail(f"live agent constant {name} does not match frozen policy")
c0_signature = inspect.signature(live_agent.AstraTerminalBenchC0Agent.__init__)
base_signature = inspect.signature(live_agent.AstraTerminalBenchAgent.__init__)
if c0_signature.parameters["stream_transport_retries"].default != 2:
    fail("live agent stream_transport_retries default must be 2")
if base_signature.parameters["max_turns"].default != 50:
    fail("live agent max_turns default must be 50")

runner_files = manifest.get("runner_files")
if not isinstance(runner_files, list) or not runner_files:
    fail("manifest contains no frozen runner files")
for record in runner_files:
    path = Path(record.get("path", ""))
    if not path.is_file():
        fail(f"frozen runner file is missing: {path}")
    if sha256_file(path) != record.get("sha256"):
        fail(f"frozen runner file changed: {path}")
if expected_overlay_path not in {
    str(Path(record.get("path", "")).resolve()) for record in runner_files
}:
    fail("host gateway overlay is absent from the frozen runner files")
if expected_model_freeze_path not in {
    str(Path(record.get("path", "")).resolve()) for record in runner_files
}:
    fail("model metadata snapshot is absent from the frozen runner files")

server_binary = manifest.get("astra_server_binary", {})
server_binary_path = Path(server_binary.get("path", ""))
if not server_binary_path.is_file():
    fail(f"frozen Astra server binary is missing: {server_binary_path}")
if sha256_file(server_binary_path) != server_binary.get("sha256"):
    fail(f"frozen Astra server binary changed: {server_binary_path}")
if server_binary_path.stat().st_size != server_binary.get("size_bytes"):
    fail(f"frozen Astra server binary size changed: {server_binary_path}")

artifacts = manifest.get("astra_artifacts", {})
for arch in ("amd64", "arm64"):
    record = artifacts.get(arch, {})
    artifact_path = Path(record.get("path", ""))
    if not artifact_path.is_file():
        fail(f"missing frozen {arch} Astra artifact: {artifact_path}")
    if record.get("architecture") != arch or record.get("os") != "linux":
        fail(f"invalid frozen {arch} Astra artifact metadata")
    if elf_arch(artifact_path) != arch:
        fail(f"frozen Astra artifact has wrong architecture: {artifact_path}")
    if sha256_file(artifact_path) != record.get("sha256"):
        fail(f"frozen Astra artifact changed: {artifact_path}")

images = manifest.get("images")
if not isinstance(images, dict) or not images:
    fail("manifest contains no frozen Docker images")
for configured_ref, frozen in images.items():
    result = subprocess.run(
        [docker_bin, "image", "inspect", configured_ref],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-1000:]
        fail(f"frozen image is unavailable: {configured_ref}: {detail}")
    try:
        current = json.loads(result.stdout)[0]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError):
        fail(f"invalid docker inspect output for {configured_ref}")
    current_config = current.get("Config") or {}
    current_workdir = current_config.get("WorkingDir") or ""
    if current.get("Id") != frozen.get("image_id"):
        fail(f"Docker tag moved after freeze: {configured_ref}")
    if normalize_arch(current.get("Architecture")) != frozen.get("architecture"):
        fail(f"Docker image architecture changed: {configured_ref}")
    if str(current.get("Os", "")).lower() != frozen.get("os"):
        fail(f"Docker image OS changed: {configured_ref}")
    if current_workdir != frozen.get("working_dir"):
        fail(f"Docker image working directory changed: {configured_ref}")
    frozen_ref = frozen.get("frozen_ref")
    if frozen_ref not in (current.get("RepoDigests") or []):
        fail(f"frozen repository digest is unavailable: {configured_ref}")

task_records = manifest.get("tasks")
if not isinstance(task_records, list) or len(task_records) != 33:
    fail("manifest must contain 33 task records")
if [record.get("name") for record in task_records] != task_names:
    fail("manifest task records differ from the exact-33 list")
tasks_by_name = {record["name"]: record for record in task_records}
for name in task_names:
    record = tasks_by_name[name]
    task_dir = (tasks_dir / name).resolve()
    if task_dir.parent != tasks_dir or not task_dir.is_dir():
        fail(f"task is missing from the pinned snapshot: {name}")
    current_files, current_tree_sha256 = task_file_manifest(task_dir)
    if current_tree_sha256 != record.get("task_tree_sha256"):
        fail(f"task files changed after freeze: {name}")
    if current_files != record.get("task_files"):
        fail(f"task file inventory changed after freeze: {name}")
    task_permissions = record.get("permissions", {})
    if task_permissions.get("permission_mode") != "auto":
        fail(f"{name}: permission_mode must be auto")
    if task_permissions.get("read_memory") is not False:
        fail(f"{name}: read_memory must be false")
    timeouts = record.get("timeouts", {})
    upstream = timeouts.get("upstream_agent_timeout_sec")
    if not isinstance(upstream, (int, float)) or upstream <= 0:
        fail(f"{name}: invalid frozen upstream timeout")
    if timeouts.get("product_timeout_multiplier") != 2.25:
        fail(f"{name}: product timeout multiplier must be 2.25")
    expected_product = upstream * 2.25
    if timeouts.get("product_timeout_sec") != expected_product:
        fail(f"{name}: frozen product timeout is inconsistent")
    if timeouts.get("harbor_agent_timeout_multiplier") != 2.5:
        fail(f"{name}: Harbor agent timeout multiplier must be 2.5")
    if timeouts.get("harbor_agent_timeout_sec") != upstream * 2.5:
        fail(f"{name}: frozen Harbor agent timeout is inconsistent")
    upstream_verifier = timeouts.get("upstream_verifier_timeout_sec")
    if not isinstance(upstream_verifier, (int, float)) or upstream_verifier <= 0:
        fail(f"{name}: invalid frozen verifier timeout")
    if timeouts.get("harbor_verifier_timeout_multiplier") != 2.0:
        fail(f"{name}: Harbor verifier timeout multiplier must be 2.0")
    if timeouts.get("harbor_verifier_timeout_sec") != upstream_verifier * 2.0:
        fail(f"{name}: frozen Harbor verifier timeout is inconsistent")
    upstream_build = timeouts.get("upstream_environment_build_timeout_sec")
    if not isinstance(upstream_build, (int, float)) or upstream_build <= 0:
        fail(f"{name}: invalid frozen environment build timeout")
    if timeouts.get("harbor_environment_build_timeout_multiplier") != 2.0:
        fail(f"{name}: Harbor environment build multiplier must be 2.0")
    if (
        timeouts.get("harbor_environment_build_timeout_sec")
        != upstream_build * 2.0
    ):
        fail(f"{name}: frozen Harbor environment build timeout is inconsistent")
    if timeouts.get("harbor_agent_setup_base_timeout_sec") != 360:
        fail(f"{name}: Harbor agent setup base timeout must be 360 seconds")
    if timeouts.get("harbor_agent_setup_timeout_multiplier") != 2.0:
        fail(f"{name}: Harbor agent setup multiplier must be 2.0")
    if timeouts.get("harbor_agent_setup_timeout_sec") != 720:
        fail(f"{name}: frozen Harbor agent setup timeout must be 720 seconds")
    configured_ref = record.get("configured_image")
    if configured_ref not in images:
        fail(f"{name}: configured image is absent from the image freeze")
    task_image = record.get("image", {})
    if task_image.get("image_id") != images[configured_ref].get("image_id"):
        fail(f"{name}: task image differs from the image freeze")

queues = manifest.get("queues_by_architecture", {})
amd64_queue = queues.get("amd64")
arm64_queue = queues.get("arm64")
native_amd64_queue = queues.get("native_amd64_required")
if (
    not isinstance(amd64_queue, list)
    or not isinstance(arm64_queue, list)
    or not isinstance(native_amd64_queue, list)
):
    fail("manifest architecture queues are missing")
if len(amd64_queue) + len(arm64_queue) + len(native_amd64_queue) != 33:
    fail("architecture queues must cover exactly 33 tasks")
queue_sets = [set(amd64_queue), set(arm64_queue), set(native_amd64_queue)]
if any(
    queue_sets[left].intersection(queue_sets[right])
    for left in range(3)
    for right in range(left + 1, 3)
):
    fail("architecture queues overlap")
if set().union(*queue_sets) != set(task_names):
    fail("architecture queues do not cover the exact-33 task list")
for arch, queue in (("amd64", amd64_queue), ("arm64", arm64_queue)):
    for name in queue:
        configured_ref = tasks_by_name[name]["configured_image"]
        if images[configured_ref].get("architecture") != arch:
            fail(f"{name}: queue architecture differs from its frozen image")
if native_amd64_queue != ["tune-mjcf"]:
    fail("the native-amd64-only queue must contain exactly tune-mjcf")
tune_ref = tasks_by_name["tune-mjcf"]["configured_image"]
if images[tune_ref].get("architecture") != "amd64":
    fail("tune-mjcf frozen image must be amd64")

selected_tasks = list(queues[selected_arch])
if single_task:
    if single_task not in task_names:
        fail(f"--task is not in the exact-33 manifest: {single_task}")
    if single_task == "tune-mjcf" and selected_arch == "amd64":
        selected_tasks = [single_task]
    elif single_task not in selected_tasks:
        fail(f"--task {single_task} is not in the {selected_arch} queue")
    else:
        selected_tasks = [single_task]
if not selected_tasks:
    fail(f"the frozen {selected_arch} queue is empty")

artifact = artifacts[selected_arch]
artifact_path = artifact["path"]
if "\n" in artifact_path or "\t" in artifact_path:
    fail("frozen artifact path contains unsupported control characters")
max_product_timeout = max(
    tasks_by_name[name]["timeouts"]["product_timeout_sec"]
    for name in selected_tasks
)
inner_timeout_sec = math.ceil(max_product_timeout)

print(f"MANIFEST_SHA256\t{manifest_sha256}")
print(f"ARTIFACT_PATH\t{artifact_path}")
print(f"ARTIFACT_SHA256\t{artifact['sha256']}")
print(f"INNER_TIMEOUT_SEC\t{inner_timeout_sec}")
health_ref = tasks_by_name[selected_tasks[0]]["configured_image"]
print(f"HEALTH_IMAGE_ID\t{images[health_ref]['image_id']}")
if "tune-mjcf" in selected_tasks:
    print(f"TUNE_IMAGE_ID\t{images[tune_ref]['image_id']}")
for name in selected_tasks:
    print(f"TASK\t{name}")
PY
)"

manifest_sha256=""
astra_binary=""
astra_binary_sha256=""
astra_inner_timeout_sec=""
health_image_id=""
tune_image_id=""
selected_tasks=()
while IFS=$'\t' read -r record_type record_value; do
  case "$record_type" in
    MANIFEST_SHA256)
      manifest_sha256="$record_value"
      ;;
    ARTIFACT_PATH)
      astra_binary="$record_value"
      ;;
    ARTIFACT_SHA256)
      astra_binary_sha256="$record_value"
      ;;
    INNER_TIMEOUT_SEC)
      astra_inner_timeout_sec="$record_value"
      ;;
    HEALTH_IMAGE_ID)
      health_image_id="$record_value"
      ;;
    TUNE_IMAGE_ID)
      tune_image_id="$record_value"
      ;;
    TASK)
      selected_tasks+=("$record_value")
      ;;
    *)
      echo "unexpected frozen validation record: $record_type" >&2
      exit 2
      ;;
  esac
done < <(printf '%s\n' "$validation_output")

if [[ -z "$manifest_sha256" || -z "$astra_binary" || -z "$astra_inner_timeout_sec" || -z "$health_image_id" ]]; then
  echo "frozen validation did not return required execution metadata" >&2
  exit 2
fi
if [[ "${#selected_tasks[@]}" -eq 0 ]]; then
  echo "frozen validation selected no tasks" >&2
  exit 2
fi

if [[ -n "$tune_image_id" ]]; then
  docker_os="$("$docker_bin" info --format '{{.OSType}}' 2>/dev/null)"
  docker_arch="$("$docker_bin" info --format '{{.Architecture}}' 2>/dev/null)"
  case "$docker_arch" in
    amd64|x86_64|x86-64)
      ;;
    *)
      echo "tune-mjcf requires a native amd64 Docker daemon; found: $docker_os/$docker_arch" >&2
      exit 2
      ;;
  esac
  if [[ "$docker_os" != "linux" ]]; then
    echo "tune-mjcf requires a native Linux amd64 Docker daemon; found: $docker_os/$docker_arch" >&2
    exit 2
  fi
  "$docker_bin" run \
    --rm \
    --network none \
    --platform linux/amd64 \
    --entrypoint python3 \
    "$tune_image_id" \
    -X faulthandler \
    -c 'import platform, mujoco; assert platform.machine().lower() in {"x86_64", "amd64"}; model = mujoco.MjModel.from_xml_path("/app/model_ref.xml"); print(mujoco.__version__, model.nq)' \
    >/dev/null
  echo "Native tune-mjcf MuJoCo preflight: passed"
fi

"$docker_bin" run \
  --rm \
  --platform "linux/$architecture" \
  --add-host host.docker.internal:host-gateway \
  --env "ASTRA_API_URL=$fixed_api_url" \
  --entrypoint /tmp/astra-health-probe \
  --volume "$astra_binary:/tmp/astra-health-probe:ro" \
  "$health_image_id" \
  health \
  >/dev/null
echo "Task-container Astra API health preflight: passed"

export ASTRA_TBENCH_LINUX_BINARY="$astra_binary"
export ASTRA_TBENCH_FREEZE_MANIFEST_SHA256="$manifest_sha256"

harbor_args=(
  run
  --config "$config_path"
  --path "$tasks_dir"
  --jobs-dir "$jobs_dir"
  --n-concurrent 1
  --n-concurrent-agents 1
  --n-attempts 1
  --max-retries 0
  --timeout-multiplier "$fixed_timeout_multiplier"
  --agent-timeout-multiplier "$fixed_harbor_agent_timeout_multiplier"
  --verifier-timeout-multiplier "$fixed_harbor_verifier_timeout_multiplier"
  --agent-setup-timeout-multiplier "$fixed_harbor_agent_setup_timeout_multiplier"
  --environment-build-timeout-multiplier "$fixed_harbor_environment_build_timeout_multiplier"
  --extra-docker-compose "$host_overlay_path"
  --allow-environment-host host.docker.internal
  --agent-kwarg "max_turns=$fixed_max_turns"
  --agent-kwarg "turn_timeout_sec=$astra_inner_timeout_sec"
  --agent-kwarg "trigger_timeout_sec=$astra_inner_timeout_sec"
  --agent-kwarg "stream_transport_retries=$fixed_stream_retries"
  --agent-kwarg "stream_optional_retry_min_remaining_sec=$fixed_optional_retry_min_remaining_sec"
  --agent-env "ASTRA_TBENCH_LINUX_BINARY=$ASTRA_TBENCH_LINUX_BINARY"
  --agent-env "ASTRA_TBENCH_MODEL=$fixed_model"
  --agent-env "ASTRA_TBENCH_READ_MEMORY=false"
  --agent-env "ASTRA_TBENCH_FREEZE_MANIFEST_SHA256=$manifest_sha256"
)
for task_name in "${selected_tasks[@]}"; do
  harbor_args+=(--include-task-name "$task_name")
done
harbor_args+=(--n-tasks "${#selected_tasks[@]}")

if [[ -n "${ASTRA_ACCESS_TOKEN:-}" ]]; then
  resolved_config="$(
    ASTRA_ACCESS_TOKEN=redacted-for-config-check \
      "$harbor_bin" "${harbor_args[@]}" --print-config
  )"
else
  resolved_config="$("$harbor_bin" "${harbor_args[@]}" --print-config)"
fi

printf '%s\n' "$resolved_config" |
  "$harbor_python" -c '
import json
import sys

(
    selected_arch,
    manifest_sha256,
    artifact_path,
    jobs_dir,
    inner_timeout,
    host_overlay_path,
    *task_names,
) = sys.argv[1:]
config = json.load(sys.stdin)

def require(condition, message):
    if not condition:
        raise SystemExit(f"resolved Harbor config validation failed: {message}")

require(config.get("jobs_dir") == jobs_dir, "unexpected jobs_dir")
require(config.get("n_concurrent_trials") == 1, "concurrency must be 1")
require(config.get("timeout_multiplier") == 2.0, "timeout multiplier must be 2.0")
require(
    config.get("agent_timeout_multiplier") == 2.5,
    "agent timeout multiplier must be 2.5",
)
require(
    config.get("verifier_timeout_multiplier") == 2.0,
    "verifier timeout multiplier must be 2.0",
)
require(
    config.get("agent_setup_timeout_multiplier") == 2.0,
    "agent setup timeout multiplier must be 2.0",
)
require(
    config.get("environment_build_timeout_multiplier") == 2.0,
    "environment build timeout multiplier must be 2.0",
)
environment = config.get("environment", {})
require(environment.get("type") == "docker", "environment must be Docker")
require(
    environment.get("extra_docker_compose") == [host_overlay_path],
    "host gateway compose overlay mismatch",
)
require(
    environment.get("extra_allowed_hosts") == ["host.docker.internal"],
    "host gateway permission mismatch",
)
agents = config.get("agents", [])
require(len(agents) == 1, "exactly one agent is required")
agent = agents[0]
require(
    agent.get("name")
    == "astra.runners.astra_terminal_bench.agent:AstraTerminalBenchC0Agent",
    "unexpected agent class",
)
kwargs = agent.get("kwargs", {})
expected_kwargs = {
    "max_turns": 50,
    "turn_timeout_sec": int(inner_timeout),
    "trigger_timeout_sec": int(inner_timeout),
    "stream_transport_retries": 2,
    "stream_optional_retry_min_remaining_sec": 930,
}
for key, expected in expected_kwargs.items():
    require(kwargs.get(key) == expected, f"{key} must be {expected}")
env = agent.get("env", {})
require(env.get("ASTRA_TBENCH_LINUX_BINARY") == artifact_path, "artifact mismatch")
require(
    env.get("ASTRA_TBENCH_MODEL")
    == "c5bde5de-9805-48d4-a016-1db6e6018fc4",
    "model mismatch",
)
require(env.get("ASTRA_TBENCH_READ_MEMORY") == "false", "read_memory must be false")
require(
    env.get("ASTRA_TBENCH_FREEZE_MANIFEST_SHA256") == manifest_sha256,
    "freeze hash mismatch",
)
datasets = config.get("datasets", [])
require(len(datasets) == 1, "exactly one local dataset is required")
require(datasets[0].get("task_names") == task_names, "task filters changed")
' \
    "$architecture" \
    "$manifest_sha256" \
    "$astra_binary" \
    "$jobs_dir" \
    "$astra_inner_timeout_sec" \
    "$host_overlay_path" \
    "${selected_tasks[@]}"

echo "Harbor: $harbor_version"
echo "Condition: C0"
echo "Frozen manifest: $manifest_path"
echo "Frozen manifest SHA-256: $manifest_sha256"
echo "Architecture: $architecture"
echo "Tasks: ${#selected_tasks[@]}"
printf '  %s\n' "${selected_tasks[@]}"
echo "Concurrency: 1"
echo "Harbor attempts/retries: 1/0"
echo "Product timeout policy: upstream agent timeout x 2.25"
echo "Harbor agent phase timeout: upstream agent timeout x 2.5"
echo "LLM fallback/total budget: 600/900 seconds"
echo "Stream retry policy: first retry guaranteed; optional second requires 930 seconds remaining"
echo "Astra binary: $astra_binary"
echo "Astra binary SHA-256: $astra_binary_sha256"
echo "Astra model: $fixed_model"
echo "Read existing user memory: false"
echo "Jobs directory: $jobs_dir"

if [[ "$check_only" == true ]]; then
  printf '%s\n' "$resolved_config"
  exit 0
fi

if [[ "$assume_yes" == true ]]; then
  harbor_args+=(--yes)
fi

"$harbor_bin" "${harbor_args[@]}"
