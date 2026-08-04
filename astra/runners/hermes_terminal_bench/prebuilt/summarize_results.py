#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from astra.runners.lifecycle_c0.audit import AuditError, audit_trial


TASK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_AGENT = (
    "astra.runners.hermes_terminal_bench.agent:"
    "HermesTerminalBenchC0Agent"
)
EXPECTED_MODEL = "zai/glm-5.2"
EXPECTED_VERSION = "v2026.7.20"


def load_queue(path: Path) -> list[str]:
    tasks: list[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        task = raw_line.split("#", 1)[0].strip()
        if not task:
            continue
        if not TASK_NAME_PATTERN.fullmatch(task):
            raise ValueError(f"invalid task name in queue: {task!r}")
        if task in seen:
            raise ValueError(f"duplicate task name in queue: {task}")
        seen.add(task)
        tasks.append(task)
    if not tasks:
        raise ValueError(f"queue is empty: {path}")
    return tasks


def reward_value(result: dict[str, Any]) -> float | None:
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    value = rewards.get("reward")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def strict_c0_audit(
    result: dict[str, Any],
    path: Path,
) -> tuple[str, str]:
    metadata = (result.get("agent_result") or {}).get("metadata") or {}
    marker_sha256 = metadata.get("hermes_prebuilt_marker_sha256")
    if metadata.get("hermes_prebuilt_marker_verified") is not True:
        return "infra_error", "prebuilt_marker_not_verified"
    if (
        not isinstance(marker_sha256, str)
        or SHA256_PATTERN.fullmatch(marker_sha256) is None
    ):
        return "infra_error", "invalid_prebuilt_marker_sha256"
    try:
        report = audit_trial(path)
    except AuditError as exc:
        return "infra_error", str(exc)
    audit_status = report.get("audit_status")
    if audit_status == "pass":
        return "passed", ""
    if audit_status == "no_hit":
        return "no_hit", ""
    return "infra_error", f"unexpected audit status: {audit_status!r}"


def result_row(
    task: str,
    result: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    metadata = (result.get("agent_result") or {}).get("metadata") or {}
    exception = result.get("exception_info")
    reward = reward_value(result)
    if exception:
        verifier_status = "exception"
    elif reward is None:
        verifier_status = "no_verifier_reward"
    elif reward == 1.0:
        verifier_status = "passed"
    else:
        verifier_status = "failed"
    scored_reward = (
        reward
        if verifier_status in {"passed", "failed"}
        and isinstance(reward, (int, float))
        else 0.0
    )
    audit_status, audit_failure = strict_c0_audit(result, path)
    return {
        "task": task,
        "verifier_status": verifier_status,
        "c0_audit_status": audit_status,
        "c0_audit_failures": audit_failure,
        "reward": reward,
        "scored_reward": scored_reward,
        "exception_type": (
            exception.get("exception_type")
            or exception.get("type")
            or exception.get("name")
            if isinstance(exception, dict)
            else type(exception).__name__ if exception else None
        ),
        "finished_at": result.get("finished_at"),
        "input_tokens": (result.get("agent_result") or {}).get(
            "n_input_tokens"
        ),
        "output_tokens": (result.get("agent_result") or {}).get(
            "n_output_tokens"
        ),
        "trajectory_status": metadata.get("trajectory_capture_status"),
        "trajectory_sha256": metadata.get("trajectory_capture_sha256"),
        "session_export_status": metadata.get(
            "trajectory_session_export_status"
        ),
        "trigger_registration_status": metadata.get(
            "trigger_registration_status"
        ),
        "trigger_scope": metadata.get("trigger_scope"),
        "trigger_id": metadata.get("trigger_id"),
        "trigger_hit": metadata.get("trigger_hit"),
        "lifecycle_gate_passed": metadata.get("lifecycle_gate_passed"),
        "cleanup_zero_live_proven": metadata.get(
            "product_cleanup_zero_live_proven"
        ),
        "temperature_marker_sha256": metadata.get(
            "hermes_prebuilt_marker_sha256"
        ),
        "result_path": str(path.resolve()),
    }


def belongs_to_full_c0_cohort(result: dict[str, Any]) -> bool:
    agent = (result.get("config") or {}).get("agent") or {}
    kwargs = agent.get("kwargs") or {}
    return (
        agent.get("name") == EXPECTED_AGENT
        and agent.get("model_name") == EXPECTED_MODEL
        and kwargs.get("version") == EXPECTED_VERSION
        and kwargs.get("preinstalled") is True
    )


def latest_results(
    jobs_dir: Path,
    expected: set[str],
) -> tuple[
    dict[str, tuple[dict[str, Any], Path]],
    list[str],
]:
    latest: dict[str, tuple[dict[str, Any], Path]] = {}
    ignored: list[str] = []
    if not jobs_dir.is_dir():
        return latest, ignored
    for path in sorted(jobs_dir.glob("*/*/result.json")):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            config = result.get("config") or {}
            if config.get("install_only"):
                continue
            task_name = result["task_name"].rsplit("/", 1)[-1]
            finished_at = result.get("finished_at")
        except (json.JSONDecodeError, KeyError, OSError, TypeError):
            continue
        if task_name not in expected or not finished_at:
            continue
        if not belongs_to_full_c0_cohort(result):
            ignored.append(str(path.resolve()))
            continue
        previous = latest.get(task_name)
        candidate_key = (str(finished_at), str(path))
        if previous is None:
            latest[task_name] = (result, path)
            continue
        previous_key = (
            str(previous[0].get("finished_at") or ""),
            str(previous[1]),
        )
        if candidate_key > previous_key:
            latest[task_name] = (result, path)
    return latest, ignored


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize and resume a queued Hermes C0 full run"
    )
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--queue-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-commit", required=True)
    parser.add_argument("--cohort-fingerprint", required=True)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--retry-audit-failures", action="store_true")
    parser.add_argument("--rerun-all", action="store_true")
    parser.add_argument("--max-tasks", type=int)
    args = parser.parse_args()

    if args.max_tasks is not None and args.max_tasks <= 0:
        parser.error("--max-tasks must be positive")
    if SHA256_PATTERN.fullmatch(args.cohort_fingerprint) is None:
        parser.error("--cohort-fingerprint must be a lowercase SHA-256")

    tasks = load_queue(args.queue_file)
    expected = set(tasks)
    latest, ignored_results = latest_results(args.jobs_dir, expected)
    rows = [
        result_row(task, *latest[task])
        for task in tasks
        if task in latest
    ]
    rows_by_task = {row["task"]: row for row in rows}

    if args.rerun_all:
        pending = list(tasks)
    else:
        pending = [
            task
            for task in tasks
            if task not in rows_by_task
            or (
                args.retry_errors
                and rows_by_task[task]["verifier_status"] == "exception"
            )
            or (
                args.retry_audit_failures
                and rows_by_task[task]["c0_audit_status"] != "passed"
            )
        ]
    scheduled = (
        pending[: args.max_tasks]
        if args.max_tasks is not None
        else list(pending)
    )

    scored_rewards = [float(row["scored_reward"]) for row in rows]
    verifier_status_counts = {
        status: sum(row["verifier_status"] == status for row in rows)
        for status in ("passed", "failed", "exception", "no_verifier_reward")
    }
    audit_status_counts = {
        status: sum(row["c0_audit_status"] == status for row in rows)
        for status in ("passed", "no_hit", "infra_error")
    }
    trigger_scope_counts = {
        status: sum(
            (row["trigger_scope"] or "unknown") == status for row in rows
        )
        for status in (
            "task_specific_progress",
            "generic_product_live",
            "unknown",
        )
    }
    marker_sha256_values = sorted(
        {
            row["temperature_marker_sha256"]
            for row in rows
            if row["temperature_marker_sha256"]
        }
    )
    summary = {
        "schema_version": 1,
        "condition": "C0",
        "evaluation_status": "exploratory_unfrozen",
        "formal_score_eligible": False,
        "selected_attempts_per_task": 1,
        "aggregation_mode": "latest_finished_attempt_per_task",
        "agent": "hermes-terminal-bench-c0",
        "model": "zai/glm-5.2",
        "temperature": 0.0,
        "dataset_commit": args.dataset_commit,
        "cohort_fingerprint": args.cohort_fingerprint,
        "cohort": {
            "agent": EXPECTED_AGENT,
            "model": EXPECTED_MODEL,
            "version": EXPECTED_VERSION,
            "preinstalled": True,
            "marker_sha256_values": marker_sha256_values,
            "marker_consistent": len(marker_sha256_values) <= 1,
        },
        "expected_tasks": len(tasks),
        "recorded_tasks": len(rows),
        "valid_c0_tasks": audit_status_counts["passed"],
        "pending_tasks": len(pending),
        "scheduled_tasks": len(scheduled),
        "mean_reward": (
            sum(scored_rewards) / len(scored_rewards)
            if scored_rewards
            else None
        ),
        "mean_reward_policy": (
            "recorded tasks; exception or missing verifier reward counts as 0"
        ),
        "verifier_status_counts": verifier_status_counts,
        "c0_audit_status_counts": audit_status_counts,
        "trigger_scope_counts": trigger_scope_counts,
        "ignored_noncohort_results": ignored_results,
        "input_tokens": sum(
            row["input_tokens"] or 0
            for row in rows
            if isinstance(row["input_tokens"], (int, float))
        ),
        "output_tokens": sum(
            row["output_tokens"] or 0
            for row in rows
            if isinstance(row["output_tokens"], (int, float))
        ),
        "jobs_dir": str(args.jobs_dir.resolve()),
        "results": rows,
        "pending": pending,
        "scheduled": scheduled,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(
        args.output_dir / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    csv_path = args.output_dir / "summary.csv"
    temporary_csv = csv_path.with_suffix(".csv.tmp")
    fieldnames = [
        "task",
        "verifier_status",
        "c0_audit_status",
        "c0_audit_failures",
        "reward",
        "scored_reward",
        "exception_type",
        "finished_at",
        "input_tokens",
        "output_tokens",
        "trajectory_status",
        "trajectory_sha256",
        "session_export_status",
        "trigger_registration_status",
        "trigger_scope",
        "trigger_id",
        "trigger_hit",
        "lifecycle_gate_passed",
        "cleanup_zero_live_proven",
        "temperature_marker_sha256",
        "result_path",
    ]
    with temporary_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary_csv.replace(csv_path)
    atomic_write(
        args.output_dir / "pending.queue.txt",
        "".join(f"{task}\n" for task in scheduled),
    )

    print(
        "Hermes C0 full-run state: "
        f"{len(rows)}/{len(tasks)} recorded, "
        f"{len(pending)} pending, "
        f"{len(scheduled)} scheduled"
    )
    print(f"Summary JSON: {args.output_dir / 'summary.json'}")
    print(f"Summary CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
