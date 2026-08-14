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

repo_root="/home/vagrant/moi-benchmark"
source_root="/home/vagrant/dataset/Toolathlon"
findings_path="${repo_root}/astra/reports/pi-tool-path-audit/findings.jsonl"
v1_summary_path="${repo_root}/astra/results/toolathlon-pi-108-v1/pi-108-summary.json"
output_root=$(readlink -m -- "$1")
manifest_path="${output_root}/pi-selected-rerun-manifest.json"
summary_path="${output_root}/pi-selected-rerun-summary.json"
experiment_id="${TOOLATHLON_PI_EXPERIMENT_ID:-toolathlon-pi-0.73.1-isolated-rerun-v1}"

case "$output_root" in
  /home/vagrant/moi-benchmark/*|/tmp/*) ;;
  *)
    echo "ERROR: output root must be below /home/vagrant/moi-benchmark or /tmp." >&2
    exit 64
    ;;
esac

mkdir -p -- "$output_root"
exec 9>"${output_root}/.pi-selected-rerun.lock"
if ! flock -n 9; then
  echo "ERROR: another selected Pi rerun holds ${output_root}/.pi-selected-rerun.lock." >&2
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

if [[ ! -f "$manifest_path" ]]; then
  unexpected=$(find "$output_root" -mindepth 1 -maxdepth 1 ! -name '.pi-selected-rerun.lock' -print -quit)
  if [[ -n "$unexpected" ]]; then
    echo "ERROR: a new output root must be empty; use the original root to resume or choose a new one." >&2
    exit 73
  fi
  batch_id=$(date -u +%Y%m%dT%H%M%SZ)
  python3 - "$findings_path" "$v1_summary_path" "$manifest_path" "$batch_id" "$experiment_id" "$source_root" "$output_root" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

findings_path, summary_path, target_path, batch_id, experiment_id, source_root, output_root = sys.argv[1:]
findings_path = Path(findings_path).resolve()
summary_path = Path(summary_path).resolve()
target_path = Path(target_path)


def task_from_run_directory(value: object) -> str:
    parts = Path(str(value)).parts
    for index in range(len(parts) - 2):
        if parts[index : index + 2] == ("runs", "pi"):
            task_id = parts[index + 2]
            if task_id:
                return task_id
    raise ValueError(f"could not derive task ID from findings run_dir: {value!r}")


findings_tasks: set[str] = set()
with findings_path.open(encoding="utf-8") as stream:
    for number, line in enumerate(stream, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            findings_tasks.add(task_from_run_directory(row["run_dir"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid findings row {number}: {exc}") from exc

v1 = json.loads(summary_path.read_text(encoding="utf-8"))
schedule = v1.get("tasks")
if not isinstance(schedule, list) or len(schedule) != 108:
    raise SystemExit("v1 summary does not contain the expected 108-task schedule")
schedule_ids = [row.get("task_id") for row in schedule if isinstance(row, dict)]
if len(schedule_ids) != 108 or any(not isinstance(task, str) or not task for task in schedule_ids):
    raise SystemExit("v1 summary has invalid task IDs")
if len(set(schedule_ids)) != 108:
    raise SystemExit("v1 summary has duplicate task IDs")
unknown = sorted(findings_tasks - set(schedule_ids))
if unknown:
    raise SystemExit(f"findings contain tasks outside the v1 schedule: {unknown}")

incomplete_tasks = {
    row["task_id"]
    for row in schedule
    if row.get("state") != "complete"
}
entries = []
for row in schedule:
    task_id = row["task_id"]
    sources = []
    if task_id in findings_tasks:
        sources.append("findings")
    if task_id in incomplete_tasks:
        sources.append("v1_incomplete")
    if sources:
        entries.append(
            {
                "position": row["position"],
                "task_id": task_id,
                "sources": sources,
                "v1_state": row.get("state"),
            }
        )
if not entries:
    raise SystemExit("selected Pi rerun task set is empty")

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
    "selection": {
        "findings_path": str(findings_path),
        "v1_summary_path": str(summary_path),
        "findings_task_count": len(findings_tasks),
        "v1_incomplete_task_count": len(incomplete_tasks),
        "overlap_count": len(findings_tasks & incomplete_tasks),
        "selected_task_count": len(entries),
    },
    "tasks": entries,
}
temporary = target_path.with_suffix(target_path.suffix + ".tmp")
temporary.write_text(
    json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
os.replace(temporary, target_path)
PY
  if [[ $? -ne 0 ]]; then
    exit 79
  fi
else
  python3 - "$manifest_path" "$experiment_id" "$source_root" "$output_root" <<'PY'
import json
import sys
from pathlib import Path

path, experiment_id, source_root, output_root = sys.argv[1:]
record = json.loads(Path(path).read_text(encoding="utf-8"))
expected = {
    "experiment_id": experiment_id,
    "system_id": "pi",
    "pi_version": "0.73.1",
    "source_root": str(Path(source_root).resolve()),
    "output_root": str(Path(output_root).resolve()),
    "workers": 1,
}
for key, value in expected.items():
    if record.get(key) != value:
        raise SystemExit(f"selected rerun manifest mismatch for {key}")
tasks = record.get("tasks")
if not isinstance(tasks, list) or not tasks:
    raise SystemExit("selected rerun manifest has no tasks")
if len({row.get("task_id") for row in tasks if isinstance(row, dict)}) != len(tasks):
    raise SystemExit("selected rerun manifest has invalid or duplicate tasks")
if not isinstance(record.get("batch_id"), str) or not record["batch_id"]:
    raise SystemExit("selected rerun manifest has no batch_id")
PY
  if [[ $? -ne 0 ]]; then
    exit 79
  fi
fi

batch_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["batch_id"])' "$manifest_path")
mapfile -t task_rows < <(
  python3 - "$manifest_path" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
for row in record["tasks"]:
    print(f"{row['position']}\t{row['task_id']}")
PY
)
task_count=${#task_rows[@]}
if [[ $task_count -eq 0 ]]; then
  echo "ERROR: selected rerun manifest produced no task rows." >&2
  exit 79
fi

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


def jsonl(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError, json.JSONDecodeError):
        return []


rows = []
totals = Counter()
required = ("artifacts.sha256", "model-usage.jsonl", "tool-calls.jsonl", "resource-usage.jsonl")
for entry in manifest["tasks"]:
    task_id = entry["task_id"]
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
            and all((candidate / name).is_file() for name in required)
        ):
            selected, run = candidate, value
            break
    base = {
        "position": entry["position"],
        "task_id": task_id,
        "sources": entry["sources"],
        "v1_state": entry["v1_state"],
    }
    if selected is None or run is None:
        rows.append({**base, "state": "pending" if not candidates else "incomplete"})
        continue

    model_events = [event for event in jsonl(selected / "model-usage.jsonl") if event.get("event") == "model_request.completed"]
    tool_events = [event for event in jsonl(selected / "tool-calls.jsonl") if event.get("state") == "started"]
    usage = Counter()
    for event in model_events:
        for source, destination in (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("total_tokens", "total_tokens"),
            ("cache_read_tokens", "cache_read_tokens"),
        ):
            value = event.get("token_usage", {}).get(source, {}).get("value")
            if isinstance(value, int):
                usage[destination] += value
    rows.append(
        {
            **base,
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
    )
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

task_count = len(manifest["tasks"])
summary = {
    "schema_version": 1,
    "benchmark_status": "exploratory_pi_only",
    "batch_id": manifest["batch_id"],
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "selection": manifest["selection"],
    "task_count": task_count,
    "complete_count": totals["complete"],
    "pending_or_incomplete_count": task_count - totals["complete"],
    "aggregate": dict(totals),
    "tasks": rows,
}
temporary = summary_path.with_suffix(summary_path.suffix + ".tmp")
temporary.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
os.replace(temporary, summary_path)
PY
}

echo "Selected Pi rerun: ${task_count} tasks"
for index in "${!task_rows[@]}"; do
  ordinal_position=$((index + 1))
  IFS=$'\t' read -r original_position task_id <<<"${task_rows[$index]}"
  task_root="${runs_root}/${task_id}"
  run_prefix="${batch_id}-$(printf '%03d' "$original_position")-${task_id}-pi"
  a1_dir="${task_root}/${run_prefix}-a1"
  a2_dir="${task_root}/${run_prefix}-a2"

  mkdir -p -- "$task_root"
  while true; do
    if attempt_complete "$a1_dir" || attempt_complete "$a2_dir"; then
      echo "[$ordinal_position/$task_count][$original_position/108] SKIP complete: $task_id"
      break
    fi

    if [[ ! -e "$a1_dir" ]]; then
      attempt_ordinal=1
      run_id="${run_prefix}-a1"
      run_dir="$a1_dir"
      replacement_args=()
    elif [[ ! -e "$a2_dir" ]]; then
      attempt_ordinal=2
      run_id="${run_prefix}-a2"
      run_dir="$a2_dir"
      replacement_args=(--replacement-for-run-id "${run_prefix}-a1")
      echo "[$ordinal_position/$task_count][$original_position/108] preserving a1 and using the one infrastructure replacement." >&2
    else
      echo "[$ordinal_position/$task_count][$original_position/108] INCOMPLETE after two preserved attempts: $task_id" >&2
      break
    fi

    echo "[$ordinal_position/$task_count][$original_position/108] START $task_id (a$attempt_ordinal)"
    python3 -m astra.runners.toolathlon_pi.lifecycle \
      --task-id "$task_id" \
      --experiment-id "$experiment_id" \
      --run-id "$run_id" \
      --output-dir "$run_dir" \
      --toolathlon-source "$source_root" \
      "${replacement_args[@]}"
    status=$?
    if attempt_complete "$run_dir"; then
      echo "[$ordinal_position/$task_count][$original_position/108] RECORDED $task_id (process exit $status)"
      break
    fi
    if [[ $attempt_ordinal -eq 1 ]] && attempt_requires_replacement "$run_dir"; then
      echo "[$ordinal_position/$task_count][$original_position/108] a1 is infra_invalid; starting the one allowed a2 replacement." >&2
      continue
    fi
    echo "[$ordinal_position/$task_count][$original_position/108] INTERRUPTED/INFRA-INCOMPLETE $task_id (process exit $status); rerun this script to resume." >&2
    break
  done
  if ! write_summary; then
    echo "ERROR: failed to update selected rerun summary." >&2
    exit 79
  fi
done

if ! write_summary; then
  echo "ERROR: failed to finalize selected rerun summary." >&2
  exit 79
fi
complete_count=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["complete_count"])' "$summary_path")
echo "Pi selected rerun summary: ${summary_path}"
echo "Completed artifacts: ${complete_count}/${task_count}"
if [[ "$complete_count" -ne "$task_count" ]]; then
  exit 1
fi
