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
from astra.runners.pi_terminal_bench.verifier_evidence import (
    VERIFIER_INFRA_EXCEPTION_TYPES,
    VerifierEvidenceError,
    validate_binary_reward,
    validate_ctrf_report,
)


EXPECTED_AGENT = (
    "astra.runners.pi_terminal_bench.agent:PiTerminalBenchC0Agent"
)
EXPECTED_MODEL = "zai/glm-5.2"
EXPECTED_VERSION = "0.73.1"
TASK_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def load_queue(path: Path) -> list[str]:
    tasks: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        task = line.split("\t", 1)[0]
        if not TASK_PATTERN.fullmatch(task):
            raise ValueError(f"invalid queue line {line_number}: {line!r}")
        if task in seen:
            raise ValueError(f"duplicate queued task: {task}")
        seen.add(task)
        tasks.append(task)
    if not tasks:
        raise ValueError(f"queue is empty: {path}")
    return tasks


def belongs_to_cohort(result: dict[str, Any]) -> bool:
    trial_config = result.get("config") or {}
    agent = trial_config.get("agent") or {}
    kwargs = agent.get("kwargs") or {}
    return (
        trial_config.get("install_only") is not True
        and agent.get("name") == EXPECTED_AGENT
        and agent.get("model_name") == EXPECTED_MODEL
        and kwargs.get("version") == EXPECTED_VERSION
        and kwargs.get("preinstalled") is True
    )


def latest_results(
    jobs_dir: Path,
    expected: set[str],
) -> tuple[dict[str, tuple[dict[str, Any], Path]], list[str]]:
    latest: dict[str, tuple[dict[str, Any], Path]] = {}
    ignored: list[str] = []
    if not jobs_dir.is_dir():
        return latest, ignored
    for path in sorted(jobs_dir.glob("*/*/result.json")):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            task = result["task_name"].rsplit("/", 1)[-1]
            finished_at = result.get("finished_at")
        except (json.JSONDecodeError, KeyError, OSError, TypeError):
            continue
        if task not in expected or not finished_at:
            continue
        if not belongs_to_cohort(result):
            ignored.append(str(path.resolve()))
            continue
        previous = latest.get(task)
        if previous is None or (str(finished_at), str(path)) > (
            str(previous[0].get("finished_at") or ""),
            str(previous[1]),
        ):
            latest[task] = (result, path)
    return latest, ignored


def reward_value(result: dict[str, Any]) -> float | None:
    value = ((result.get("verifier_result") or {}).get("rewards") or {}).get(
        "reward"
    )
    if value is None:
        return None
    return validate_binary_reward(value)


def result_row(
    task: str,
    result: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    agent_result = result.get("agent_result") or {}
    metadata = agent_result.get("metadata") or {}
    exception = result.get("exception_info")
    verifier_reward_error = ""
    try:
        reward = reward_value(result)
    except VerifierEvidenceError as exc:
        reward = None
        verifier_reward_error = str(exc)
    verifier_evidence_error = ""
    verifier_test_count = 0
    try:
        verifier_evidence = validate_ctrf_report(
            path.parent / "verifier" / "ctrf.json"
        )
        verifier_test_count = verifier_evidence["test_count"]
    except VerifierEvidenceError as exc:
        verifier_evidence_error = str(exc)
    try:
        audit = audit_trial(path)
        audit_status = audit["audit_status"]
        audit_failure = ""
    except AuditError as exc:
        audit_status = "infra_error"
        audit_failure = str(exc)
    exception_type = (
        exception.get("exception_type") if isinstance(exception, dict) else None
    )
    if exception_type in VERIFIER_INFRA_EXCEPTION_TYPES:
        verifier_status = "verifier_infra_failure"
    elif verifier_evidence_error:
        verifier_status = "verifier_infra_failure"
    elif verifier_reward_error:
        verifier_status = "verifier_infra_failure"
    elif reward is None:
        verifier_status = "no_verifier_reward"
    elif reward == 1.0:
        verifier_status = "passed"
    else:
        verifier_status = "failed"
    scored_reward = (
        reward if verifier_status in {"passed", "failed"} else None
    )
    return {
        "task": task,
        "reward": reward,
        "scored_reward": scored_reward,
        "verifier_status": verifier_status,
        "verifier_test_count": verifier_test_count,
        "verifier_evidence_error": verifier_evidence_error,
        "verifier_reward_error": verifier_reward_error,
        "trial_exception_type": exception_type,
        "trial_exception_message": (
            exception.get("exception_message")
            if isinstance(exception, dict)
            else None
        ),
        "c0_audit_status": audit_status,
        "c0_audit_failure": audit_failure,
        "product_terminal_status": metadata.get("product_terminal_status"),
        "trajectory_status": metadata.get("pi_trajectory_status"),
        "final_stop_reason": metadata.get("pi_final_stop_reason"),
        "trigger_scope": metadata.get("trigger_scope"),
        "trigger_hit": metadata.get("trigger_hit"),
        "lifecycle_gate_passed": metadata.get("lifecycle_gate_passed"),
        "cleanup_zero_live_proven": metadata.get(
            "product_cleanup_zero_live_proven"
        ),
        "input_tokens": agent_result.get("n_input_tokens"),
        "output_tokens": agent_result.get("n_output_tokens"),
        "cache_tokens": agent_result.get("n_cache_tokens"),
        "cost_usd": agent_result.get("cost_usd"),
        "finished_at": result.get("finished_at"),
        "result_path": str(path.resolve()),
    }


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Pi C0 results")
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--queue-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-commit", required=True)
    args = parser.parse_args()

    tasks = load_queue(args.queue_file)
    latest, ignored = latest_results(args.jobs_dir, set(tasks))
    rows = [result_row(task, *latest[task]) for task in tasks if task in latest]
    completed = {
        row["task"]
        for row in rows
        if row["verifier_status"] in {"passed", "failed"}
    }
    pending = [
        task
        for task in tasks
        if task not in completed
    ]
    audit_counts = {
        status: sum(row["c0_audit_status"] == status for row in rows)
        for status in ("pass", "no_hit", "infra_error")
    }
    verifier_counts = {
        status: sum(row["verifier_status"] == status for row in rows)
        for status in (
            "passed",
            "failed",
            "verifier_infra_failure",
            "no_verifier_reward",
        )
    }
    summary = {
        "schema_version": 1,
        "condition": "C0",
        "agent": "pi-terminal-bench-c0",
        "model": EXPECTED_MODEL,
        "pi_version": EXPECTED_VERSION,
        "dataset_commit": args.dataset_commit,
        "expected_tasks": len(tasks),
        "recorded_tasks": len(rows),
        "valid_c0_tasks": audit_counts["pass"],
        "pending_tasks": len(pending),
        "valid_verifier_tasks": sum(
            row["verifier_status"] in {"passed", "failed"} for row in rows
        ),
        "mean_reward": (
            sum(
                float(row["scored_reward"])
                for row in rows
                if row["scored_reward"] is not None
            )
            / sum(row["scored_reward"] is not None for row in rows)
            if any(row["scored_reward"] is not None for row in rows)
            else None
        ),
        "mean_reward_policy": (
            "latest finished cohort attempt with valid non-empty CTRF evidence; "
            "verifier infrastructure failures are excluded and remain pending"
        ),
        "verifier_status_counts": verifier_counts,
        "c0_audit_status_counts": audit_counts,
        "ignored_noncohort_results": ignored,
        "pending": pending,
        "results": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(
        args.output_dir / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    csv_path = args.output_dir / "summary.csv"
    temporary_csv = csv_path.with_suffix(".csv.tmp")
    with temporary_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result_row_fields()))
        writer.writeheader()
        writer.writerows(rows)
    temporary_csv.replace(csv_path)
    atomic_write(
        args.output_dir / "pending.queue.txt",
        "".join(f"{task}\n" for task in pending),
    )
    print(
        f"Pi C0 state: {len(rows)}/{len(tasks)} recorded, "
        f"{len(pending)} pending"
    )
    return 0


def result_row_fields() -> tuple[str, ...]:
    return (
        "task",
        "reward",
        "scored_reward",
        "verifier_status",
        "verifier_test_count",
        "verifier_evidence_error",
        "verifier_reward_error",
        "trial_exception_type",
        "trial_exception_message",
        "c0_audit_status",
        "c0_audit_failure",
        "product_terminal_status",
        "trajectory_status",
        "final_stop_reason",
        "trigger_scope",
        "trigger_hit",
        "lifecycle_gate_passed",
        "cleanup_zero_live_proven",
        "input_tokens",
        "output_tokens",
        "cache_tokens",
        "cost_usd",
        "finished_at",
        "result_path",
    )


if __name__ == "__main__":
    raise SystemExit(main())
