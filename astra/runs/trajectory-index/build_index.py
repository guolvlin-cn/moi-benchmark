"""Build metadata indexes for the three copied benchmark run roots."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
SOURCES = {
    "astra-c0-all-jobs": ROOT / "astra/runs/astra-c0-all-jobs",
    "astra-c0-rerun-from-scratch-33": ROOT / "astra/runs/astra-c0-rerun-from-scratch-33",
    "hermes-c0-all-jobs": ROOT / "astra/runs/hermes-c0-all-jobs",
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def first_number(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return None


def task_id(result: dict[str, Any]) -> str:
    value = result.get("task_id")
    if isinstance(value, dict):
        value = value.get("path") or value.get("id") or ""
    if isinstance(value, str):
        return Path(value).name if "/" in value else value
    return ""


def trial_dirs(root: Path) -> Iterable[Path]:
    for result_path in sorted(root.rglob("result.json")):
        parent = result_path.parent
        if (parent / "agent").is_dir() and (parent / "config.json").is_file():
            yield parent


def record(source_name: str, root: Path, trial: Path) -> dict[str, Any]:
    result = read_json(trial / "result.json")
    agent = trial / "agent"
    is_hermes = source_name == "hermes-c0-all-jobs"
    if is_hermes:
        runtime = read_json(agent / "hermes-run.json")
        trajectory_kind = "hermes-driver-session"
        trajectory_path = agent / "hermes-run.json"
        status = runtime.get("status", "")
        session_id = runtime.get("session_id", "")
        run_id = runtime.get("run_id", "")
        event_count = runtime.get("stream_event_count")
        file_count = ""
        capture_status = "driver-recorded"
        manifest_path = trial / "artifacts/manifest.json"
    else:
        runtime = read_json(agent / "trajectory-status.json")
        manifest_path = agent / "astra-trajectory/manifest.json"
        manifest = read_json(manifest_path)
        trajectory_kind = "astra-session-trajectory"
        trajectory_path = agent / "astra-trajectory"
        status = runtime.get("product_terminal_status", "")
        session_id = runtime.get("astra_session_id") or manifest.get("session_id", "")
        run_id = runtime.get("controller_run_id", "")
        event_count = first_number(
            runtime.get("server_event_count"),
            manifest.get("server_event_count"),
            manifest.get("local_journal_event_count"),
        )
        file_count = first_number(runtime.get("trajectory_file_count"), manifest.get("local_file_count"))
        capture_status = runtime.get("capture_status", manifest.get("capture_status", ""))
    verifier = result.get("verifier_result") or {}
    rewards = verifier.get("rewards") or {}
    reward = rewards.get("reward")
    if isinstance(reward, float) and reward.is_integer():
        reward = int(reward)
    manifest_rel = manifest_path.relative_to(ROOT)
    trajectory_rel = trajectory_path.relative_to(ROOT)
    return {
        "source_root": source_name,
        "task_id": task_id(result),
        "task_name": result.get("task_name", ""),
        "trial_name": result.get("trial_name", trial.name),
        "batch_path": str(trial.parent.relative_to(ROOT)),
        "raw_relative_path": str(trial.relative_to(ROOT)),
        "trajectory_kind": trajectory_kind,
        "trajectory_relative_path": str(trajectory_rel),
        "manifest_relative_path": str(manifest_rel),
        "manifest_sha256": sha256(manifest_path) if manifest_path.is_file() else "",
        "session_id": session_id,
        "run_id": run_id,
        "trajectory_status": capture_status,
        "product_terminal_status": status,
        "trajectory_event_count": event_count if event_count is not None else "",
        "trajectory_file_count": file_count if file_count is not None else "",
        "verifier_reward": reward if reward is not None else "",
        "started_at": result.get("started_at", ""),
        "finished_at": result.get("finished_at", ""),
    }


def main() -> None:
    records: list[dict[str, Any]] = []
    for source_name, root in SOURCES.items():
        if root.is_dir():
            records.extend(record(source_name, root, trial) for trial in trial_dirs(root))
    records.sort(key=lambda item: (item["source_root"], item["raw_relative_path"]))
    fields = list(records[0]) if records else []
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for source_name in SOURCES:
        rows = [item for item in records if item["source_root"] == source_name]
        with (OUTPUT / f"{source_name}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    (OUTPUT / "trajectory-index.json").write_text(
        json.dumps({"sources": list(SOURCES), "records": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"indexed {len(records)} task attempts")


if __name__ == "__main__":
    main()
