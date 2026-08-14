#!/usr/bin/env bash
set -uo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo -E so the Pi credential and isolated Docker sidecar are available." >&2
  exit 77
fi

if [[ $# -ne 1 ]]; then
  echo "usage: $0 ABSOLUTE_OUTPUT_ROOT" >&2
  exit 64
fi

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root="${TOOLATHLON_REPO_ROOT:-$(cd -- "${script_root}/../../../.." && pwd)}"
source_root="${TOOLATHLON_SOURCE_ROOT:-/home/vagrant/dataset/Toolathlon}"
freeze_root="${repo_root}/astra/benchmark/toolathlon-verified/freeze"
protocol_path="${freeze_root}/execution-protocol.freeze.json"
requirements_path="${freeze_root}/task-requirements.json"
output_root=$(readlink -m -- "$1")
manifest_path="${output_root}/pi-108-batch-manifest.json"
summary_path="${output_root}/pi-108-summary.json"
experiment_id="toolathlon-pi-0.73.1-108-v1"

if [[ "$output_root" != "$repo_root"/* && "$output_root" != /tmp/* ]]; then
  echo "ERROR: output root must be below the repository or /tmp." >&2
  exit 64
fi

mkdir -p -- "$output_root"
exec 9>"${output_root}/.pi-108.lock"
if ! flock -n 9; then
  echo "ERROR: another Pi 108-task scheduler holds ${output_root}/.pi-108.lock." >&2
  exit 75
fi
cd -- "$repo_root"

if [[ -z ${TOOLATHLON_DEEPSEEK_PI_API_KEY:-} ]]; then
  echo "ERROR: TOOLATHLON_DEEPSEEK_PI_API_KEY is not available under sudo -E." >&2
  exit 78
fi
if [[ -z ${TOOLATHLON_PI_EXECUTABLE:-} ]]; then
  echo "ERROR: TOOLATHLON_PI_EXECUTABLE is not available under sudo -E." >&2
  exit 78
fi

python3 - <<'PY'
from astra.runners.toolathlon_pi.pi_adapter import PiRuntime
runtime = PiRuntime.load_from_environment()
print(f"Pi runtime: {runtime.executable} (0.73.1)")
PY
if [[ $? -ne 0 ]]; then
  exit 78
fi

mapfile -t tasks < <(
  python3 - "$protocol_path" "$requirements_path" <<'PY'
import json
import sys
from pathlib import Path

protocol = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
requirements = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
phases = protocol.get("formal_phases", {})
tasks = list(phases.get("first_batch", {}).get("tasks", []))
tasks.extend(phases.get("remaining_batch", {}).get("tasks", []))
required = requirements.get("tasks", {})
if len(tasks) != 108 or len(set(tasks)) != 108 or set(tasks) != set(required):
    raise SystemExit("frozen protocol does not define exactly the required 108 tasks")
print("\n".join(tasks))
PY
)
if [[ ${#tasks[@]} -ne 108 ]]; then
  echo "ERROR: failed to load the exact frozen 108-task schedule." >&2
  exit 79
fi

if [[ ! -f "$manifest_path" ]]; then
  unexpected=$(find "$output_root" -mindepth 1 -maxdepth 1 \
    ! -name '.pi-108.lock' \
    ! -name 'credential-manifest.runtime.json' \
    -print -quit)
  if [[ -n "$unexpected" ]]; then
    echo "ERROR: a new output root must be empty; use the original root to resume or choose a new one." >&2
    exit 73
  fi
  batch_id=$(date -u +%Y%m%dT%H%M%SZ)
  python3 - "$manifest_path" "$batch_id" "$experiment_id" "$source_root" "$output_root" "${tasks[@]}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path, batch_id, experiment_id, source_root, output_root, *tasks = sys.argv[1:]
record = {
    "schema_version": 1,
    "benchmark_status": "exploratory_pi_only",
    "batch_id": batch_id,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "experiment_id": experiment_id,
    "system_id": "pi",
    "pi_version": "0.73.1",
    "source_root": str(Path(source_root).resolve()),
    "output_root": str(Path(output_root).resolve()),
    "workers": 1,
    "task_count": len(tasks),
    "tasks": tasks,
}
target = Path(path)
temporary = target.with_suffix(target.suffix + ".tmp")
temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, target)
PY
else
  python3 - "$manifest_path" "$experiment_id" "$source_root" "$output_root" "${tasks[@]}" <<'PY'
import json
import sys
from pathlib import Path

path, experiment_id, source_root, output_root, *tasks = sys.argv[1:]
record = json.loads(Path(path).read_text(encoding="utf-8"))
expected = {
    "experiment_id": experiment_id,
    "system_id": "pi",
    "pi_version": "0.73.1",
    "source_root": str(Path(source_root).resolve()),
    "output_root": str(Path(output_root).resolve()),
    "workers": 1,
    "task_count": 108,
    "tasks": tasks,
}
for key, value in expected.items():
    if record.get(key) != value:
        raise SystemExit(f"batch manifest mismatch for {key}")
if not isinstance(record.get("batch_id"), str) or not record["batch_id"]:
    raise SystemExit("batch manifest has no batch_id")
PY
  if [[ $? -ne 0 ]]; then
    exit 79
  fi
fi

batch_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["batch_id"])' "$manifest_path")
runs_root="${output_root}/runs/pi"
mkdir -p -- "$runs_root"

attempt_complete() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
try:
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
required = ("artifacts.sha256", "model-usage.jsonl", "tool-calls.jsonl", "resource-usage.jsonl")
ok = (
    run.get("artifact_gate", {}).get("status") == "passed"
    and run.get("run_validity") != "infra_invalid"
    and all((root / name).is_file() for name in required)
)
raise SystemExit(0 if ok else 1)
PY
}

attempt_requires_replacement() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
try:
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
required = ("artifacts.sha256", "model-usage.jsonl", "tool-calls.jsonl", "resource-usage.jsonl")
ok = (
    run.get("artifact_gate", {}).get("status") == "passed"
    and run.get("run_validity") == "infra_invalid"
    and all((root / name).is_file() for name in required)
)
raise SystemExit(0 if ok else 1)
PY
}

write_summary() {
  python3 - "$manifest_path" "$runs_root" "$summary_path" <<'PY'
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

manifest_path, runs_root, summary_path = map(Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

def jsonl(path):
    try:
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError, json.JSONDecodeError):
        return []

rows = []
totals = Counter()
for position, task_id in enumerate(manifest["tasks"], start=1):
    task_root = runs_root / task_id
    candidates = sorted(path for path in task_root.glob("*") if path.is_dir()) if task_root.is_dir() else []
    selected = None
    run = None
    for candidate in reversed(candidates):
        try:
            value = json.loads((candidate / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            value.get("artifact_gate", {}).get("status") == "passed"
            and value.get("run_validity") != "infra_invalid"
        ):
            selected, run = candidate, value
            break
    if selected is None:
        rows.append({"position": position, "task_id": task_id, "state": "pending" if not candidates else "incomplete"})
        continue

    model_events = [event for event in jsonl(selected / "model-usage.jsonl") if event.get("event") == "model_request.completed"]
    tool_events = [event for event in jsonl(selected / "tool-calls.jsonl") if event.get("state") == "started"]
    usage = Counter()
    for event in model_events:
        for source, destination in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"), ("total_tokens", "total_tokens"), ("cache_read_tokens", "cache_read_tokens")):
            value = event.get("token_usage", {}).get(source, {}).get("value")
            if isinstance(value, int):
                usage[destination] += value
    row = {
        "position": position,
        "task_id": task_id,
        "state": "complete",
        "run_id": run.get("run_id"),
        "run_directory": str(selected),
        "terminal_status": run.get("terminal_status"),
        "verify_status": run.get("verify_status"),
        "run_validity": run.get("run_validity"),
        "primary_failure_category": run.get("primary_failure_category"),
        "model_requests": len(model_events),
        "tool_calls": len(tool_events),
        "agent_duration_seconds": run.get("agent_duration_seconds"),
        "evaluator_duration_seconds": run.get("evaluator_duration_seconds"),
        **usage,
    }
    rows.append(row)
    totals["complete"] += 1
    totals[f"verify_{run.get('verify_status', 'missing')}"] += 1
    totals[f"validity_{run.get('run_validity', 'missing')}"] += 1
    totals["model_requests"] += len(model_events)
    totals["tool_calls"] += len(tool_events)
    for key, value in usage.items():
        totals[key] += value
    for key in ("agent_duration_seconds", "evaluator_duration_seconds"):
        value = run.get(key)
        if isinstance(value, (int, float)):
            totals[key] += value

summary = {
    "schema_version": 1,
    "benchmark_status": "exploratory_pi_only",
    "batch_id": manifest["batch_id"],
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "task_count": 108,
    "complete_count": totals["complete"],
    "pending_or_incomplete_count": 108 - totals["complete"],
    "aggregate": dict(totals),
    "tasks": rows,
}
target = summary_path
temporary = target.with_suffix(target.suffix + ".tmp")
temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, target)
PY
}

for index in "${!tasks[@]}"; do
  position=$((index + 1))
  task_id=${tasks[$index]}
  task_root="${runs_root}/${task_id}"
  run_prefix="${batch_id}-$(printf '%03d' "$position")-${task_id}-pi"
  a1_dir="${task_root}/${run_prefix}-a1"
  a2_dir="${task_root}/${run_prefix}-a2"

  mkdir -p -- "$task_root"
  while true; do
    if attempt_complete "$a1_dir" || attempt_complete "$a2_dir"; then
      echo "[$position/108] SKIP complete: $task_id"
      break
    fi

    if [[ ! -e "$a1_dir" ]]; then
      ordinal=1
      run_id="${run_prefix}-a1"
      run_dir="$a1_dir"
      replacement_args=()
    elif [[ ! -e "$a2_dir" ]]; then
      ordinal=2
      run_id="${run_prefix}-a2"
      run_dir="$a2_dir"
      replacement_args=(--replacement-for-run-id "${run_prefix}-a1")
      echo "[$position/108] preserving a1 and using the one infrastructure replacement." >&2
    else
      echo "[$position/108] INCOMPLETE after two preserved attempts: $task_id" >&2
      break
    fi

    echo "[$position/108] START $task_id (a$ordinal)"
    python3 -m astra.runners.toolathlon_pi.lifecycle \
      --task-id "$task_id" \
      --experiment-id "$experiment_id" \
      --run-id "$run_id" \
      --output-dir "$run_dir" \
      --toolathlon-source "$source_root" \
      "${replacement_args[@]}"
    status=$?
    if attempt_complete "$run_dir"; then
      echo "[$position/108] RECORDED $task_id (process exit $status)"
      break
    fi
    if [[ $ordinal -eq 1 ]] && attempt_requires_replacement "$run_dir"; then
      echo "[$position/108] a1 is infra_invalid; starting the one allowed a2 replacement." >&2
      continue
    fi
    echo "[$position/108] INTERRUPTED/INFRA-INCOMPLETE $task_id (process exit $status); rerun this script to resume." >&2
    break
  done
  write_summary
done

write_summary
complete_count=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["complete_count"])' "$summary_path")
echo "Pi batch summary: ${summary_path}"
echo "Completed artifacts: ${complete_count}/108"
if [[ "$complete_count" -ne 108 ]]; then
  exit 1
fi
