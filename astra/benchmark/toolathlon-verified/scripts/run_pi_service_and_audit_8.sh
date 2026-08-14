#!/usr/bin/env bash
set -uo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 ABSOLUTE_OUTPUT_ROOT" >&2
  exit 64
fi

repo_root="/home/vagrant/moi-benchmark"
runner="${repo_root}/astra/benchmark/toolathlon-verified/scripts/run_pi_findings_and_incomplete.sh"
output_root=$(readlink -m -- "$1")
manifest_path="${output_root}/pi-selected-rerun-manifest.json"
credential_manifest_path="${output_root}/credential-manifest.runtime.json"
experiment_id="toolathlon-pi-0.73.1-service-and-audit-8-v3"

case "$output_root" in
  /home/vagrant/moi-benchmark/*|/tmp/*) ;;
  *)
    echo "ERROR: output root must be below /home/vagrant/moi-benchmark or /tmp." >&2
    exit 64
    ;;
esac

mkdir -p -- "$output_root"
if [[ ! -f "$credential_manifest_path" ]] && [[ -d "${output_root}/runs" ]]; then
  echo "ERROR: this output root contains attempts created before the runtime credential snapshot fix." >&2
  echo "Use a new output root (recommended suffix: -v2); the preflight-only attempts are preserved." >&2
  exit 73
fi
if [[ ! -f "$manifest_path" ]]; then
  unexpected=$(find "$output_root" -mindepth 1 -maxdepth 1 -print -quit)
  if [[ -n "$unexpected" ]]; then
    echo "ERROR: a new output root must be empty; use the original root to resume or choose a new one." >&2
    exit 73
  fi

  batch_id=$(date -u +%Y%m%dT%H%M%SZ)
  python3 - "$manifest_path" "$batch_id" "$experiment_id" "$output_root" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

manifest_path, batch_id, experiment_id, output_root = sys.argv[1:]
tasks = [
    (21, "canvas-art-manager", "formal_required"),
    (24, "canvas-list-test", "formal_required"),
    (25, "canvas-new-students-notification", "formal_required"),
    (102, "woocommerce-customer-survey", "formal_required"),
    (104, "woocommerce-new-welcome", "formal_required"),
    (105, "woocommerce-product-recall", "formal_required"),
    (69, "nhl-b2b-analysis", "extended_audit"),
    (99, "vlm-history-completer", "extended_audit"),
]
record = {
    "schema_version": 1,
    "benchmark_status": "exploratory_pi_only",
    "batch_id": batch_id,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "experiment_id": experiment_id,
    "system_id": "pi",
    "pi_version": "0.73.1",
    "source_root": "/home/vagrant/dataset/Toolathlon",
    "output_root": str(Path(output_root).resolve()),
    "workers": 1,
    "selection": {
        "name": "service_and_audit_8",
        "formal_required_count": 6,
        "extended_audit_count": 2,
        "selected_task_count": len(tasks),
    },
    "tasks": [
        {
            "position": position,
            "task_id": task_id,
            "sources": [source],
            "v1_state": "selected_for_rerun",
        }
        for position, task_id, source in tasks
    ],
}
target = Path(manifest_path)
temporary = target.with_suffix(target.suffix + ".tmp")
temporary.write_text(
    json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
os.replace(temporary, target)
PY
  if [[ $? -ne 0 ]]; then
    exit 79
  fi
fi

if [[ ! -f "$credential_manifest_path" ]]; then
  python3 - \
    "${repo_root}/astra/benchmark/toolathlon-verified/freeze/credential-manifest.json" \
    "/home/vagrant/dataset/Toolathlon" \
    "$credential_manifest_path" <<'PY'
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

base_path, source_root, target_path = map(Path, sys.argv[1:])
record = json.loads(base_path.read_text(encoding="utf-8"))
files = record["toolathlon_application_credentials"]["files"]
for item in files:
    relative = Path(item["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise SystemExit(f"unsafe credential path: {relative}")
    source = source_root / relative
    if not source.is_file() or source.is_symlink():
        raise SystemExit(f"credential file is unavailable: {source}")
    item["mode"] = oct(stat.S_IMODE(source.stat().st_mode))
    item["size_bytes"] = source.stat().st_size
    item["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()

canonical = json.dumps(
    files,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
record["frozen_at"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
record["toolathlon_application_credentials"]["root_sha256"] = hashlib.sha256(
    canonical
).hexdigest()
record["runtime_rebaseline"] = {
    "base_manifest_sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
    "reason": "shared application services were redeployed before the selected rerun batch",
    "scope": "application credential file fingerprints only",
}
target = target_path
temporary = target.with_suffix(target.suffix + ".tmp")
temporary.write_text(
    json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
os.chmod(temporary, 0o600)
os.replace(temporary, target)
PY
  if [[ $? -ne 0 ]]; then
    exit 79
  fi
fi

TOOLATHLON_PI_CREDENTIAL_MANIFEST="$credential_manifest_path" \
TOOLATHLON_PI_EXPERIMENT_ID="$experiment_id" \
  exec "$runner" "$output_root"
