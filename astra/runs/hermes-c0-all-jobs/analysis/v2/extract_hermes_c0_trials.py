#!/usr/bin/env python3
"""Extract a reusable latest-attempt Hermes C0 Terminal-Bench dataset.

The extractor deliberately separates functional verification from product
lifecycle status and telemetry quality.  It is intended to be rerun after new
trial directories are added beneath a Hermes C0 work root.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


DEFAULT_EXCLUDED_TASKS = {"tune-mjcf"}
BATCH_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2}$")

TRIAL_FIELDS = [
    "task_id",
    "attempt_count_for_task",
    "selected_run_dir",
    "selected_trial_name",
    "selected_trial_path",
    "selected_finished_at",
    "reward",
    "verify_status",
    "normal_e2e_pass",
    "outcome_bucket",
    "timeout",
    "product_terminal_status",
    "product_return_code",
    "product_completion_claim",
    "run_status",
    "run_error",
    "trajectory_capture_status",
    "trajectory_terminal_event",
    "trajectory_terminal_event_count",
    "trajectory_capture_error",
    "e2e_s",
    "environment_setup_s",
    "agent_setup_s",
    "agent_execution_s",
    "verifier_s",
    "run_duration_s",
    "tool_calls",
    "tool_calls_failed",
    "tool_call_failure_rate",
    "tool_duration_s",
    "tool_breakdown",
    "failed_tool_breakdown",
    "session_api_calls",
    "session_messages",
    "message_delta_count",
    "model_activity_observed",
    "gateway_response_truncated_count",
    "gateway_balance_error_line_count",
    "token_input",
    "token_output",
    "token_total",
    "token_source",
    "token_accounting_status",
    "token_sources_consistent",
    "cost_usd",
    "verifier_tests",
    "verifier_passed",
    "verifier_failed",
    "verifier_skipped",
    "failed_test_names",
]


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=script_dir.parents[1],
        help="Hermes C0 work root (default: the directory containing analysis/).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "output",
        help="Directory for regenerated CSV, JSON, and Markdown outputs.",
    )
    parser.add_argument(
        "--exclude-task",
        action="append",
        default=[],
        help="Additional task id to exclude; may be supplied more than once.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def batch_sort_key(run_dir: Path, result: dict[str, Any]) -> tuple[int, datetime, str]:
    """Use the batch directory timestamp as the primary latest-attempt key."""

    if BATCH_NAME_RE.fullmatch(run_dir.name):
        try:
            return (2, datetime.strptime(run_dir.name, "%Y-%m-%d__%H-%M-%S"), "")
        except ValueError:
            pass
    finished = parse_time(result.get("finished_at"))
    if finished is not None:
        return (1, finished, run_dir.name)
    return (0, datetime.min, run_dir.name)


def number(value: Any) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    return None


def seconds_between(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    start = parse_time(value.get("started_at"))
    finish = parse_time(value.get("finished_at"))
    if start is None or finish is None:
        return None
    return (finish - start).total_seconds()


def compact_counter(counter: Counter[str]) -> str:
    return json.dumps(dict(sorted(counter.items())), ensure_ascii=False)


def percentile(values: Iterable[float | int | None], p: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    index = (len(clean) - 1) * p
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return clean[low]
    return clean[low] + (clean[high] - clean[low]) * (index - low)


def metric_stats(values: Iterable[float | int | None]) -> dict[str, float | int | None]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {
            "n": 0,
            "sum": None,
            "mean": None,
            "median": None,
            "p90": None,
            "min": None,
            "max": None,
        }
    return {
        "n": len(clean),
        "sum": sum(clean),
        "mean": sum(clean) / len(clean),
        "median": percentile(clean, 0.5),
        "p90": percentile(clean, 0.9),
        "min": min(clean),
        "max": max(clean),
    }


def verifier_summary(trial_dir: Path) -> dict[str, Any]:
    ctrf = read_json(trial_dir / "verifier" / "ctrf.json")
    results = ctrf.get("results") if ctrf else None
    if not isinstance(results, dict):
        return {
            "verifier_tests": None,
            "verifier_passed": None,
            "verifier_failed": None,
            "verifier_skipped": None,
            "failed_test_names": "",
        }
    summary = results.get("summary")
    tests = results.get("tests")
    summary = summary if isinstance(summary, dict) else {}
    tests = tests if isinstance(tests, list) else []
    failed_names = [
        str(test.get("name"))
        for test in tests
        if isinstance(test, dict) and test.get("status") == "failed"
    ]
    return {
        "verifier_tests": number(summary.get("tests")),
        "verifier_passed": number(summary.get("passed")),
        "verifier_failed": number(summary.get("failed")),
        "verifier_skipped": number(summary.get("skipped")),
        "failed_test_names": "; ".join(failed_names),
    }


def session_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Find the exported session object without using its usage as trial usage.

    The session object's input token field is not consistently equal to the
    terminal runner aggregate.  It is therefore used only for API-call and
    activity evidence, never as a fallback total-token estimate.
    """

    for row in rows:
        if "api_call_count" in row or "tool_call_count" in row:
            return row
    return rows[0] if rows else {}


def classify_token_accounting(
    run_usage: dict[str, Any],
    agent_result: dict[str, Any],
    model_activity_observed: bool,
    truncated_count: int,
) -> dict[str, Any]:
    run_input = number(run_usage.get("input_tokens"))
    run_output = number(run_usage.get("output_tokens"))
    agent_input = number(agent_result.get("n_input_tokens"))
    agent_output = number(agent_result.get("n_output_tokens"))

    sources_consistent: bool | None = None
    if all(value is not None for value in (run_input, run_output, agent_input, agent_output)):
        sources_consistent = run_input == agent_input and run_output == agent_output

    if run_input is not None or run_output is not None:
        token_input, token_output, source = run_input, run_output, "hermes-run.json.usage"
    elif agent_input is not None or agent_output is not None:
        token_input, token_output, source = (
            agent_input,
            agent_output,
            "result.json.agent_result",
        )
    else:
        token_input, token_output, source = None, None, "missing"

    if token_input is None or token_output is None:
        status = (
            "missing_after_model_activity"
            if model_activity_observed
            else "missing_no_model_activity"
        )
        return {
            "token_input": token_input,
            "token_output": token_output,
            "token_total": None,
            "token_source": source,
            "token_accounting_status": status,
            "token_sources_consistent": sources_consistent,
        }

    if token_input == 0 and token_output == 0 and (
        model_activity_observed or truncated_count > 0
    ):
        status = "suspect_zero_after_model_activity"
    elif token_input == 0 and token_output == 0:
        status = "reported_zero_no_activity"
    else:
        status = "reported"
    return {
        "token_input": token_input,
        "token_output": token_output,
        "token_total": token_input + token_output,
        "token_source": source,
        "token_accounting_status": status,
        "token_sources_consistent": sources_consistent,
    }


def derive_outcome_bucket(row: dict[str, Any]) -> str:
    if row["verify_status"] == "pass":
        if row["normal_e2e_pass"]:
            return "normal_e2e_pass"
        if row["timeout"]:
            return "verifier_pass_after_timeout"
        return "verifier_pass_with_abnormal_lifecycle"
    if row["timeout"]:
        return "timeout_no_pass"
    if row["product_terminal_status"] == "completed":
        return "completed_no_pass"
    return "failed_no_pass"


def extract_trial(run_dir: Path, trial_dir: Path) -> dict[str, Any] | None:
    result = read_json(trial_dir / "result.json")
    if not result or not result.get("task_name"):
        return None
    agent_result = result.get("agent_result")
    agent_result = agent_result if isinstance(agent_result, dict) else {}
    metadata = agent_result.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    task_id = metadata.get("task_id") or str(result["task_name"]).removeprefix("terminal-bench/")
    if not isinstance(task_id, str) or not task_id:
        return None

    reward_value = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    reward = number(reward_value)
    if reward not in (0, 0.0, 1, 1.0):
        reward = None

    run = read_json(trial_dir / "agent" / "hermes-run.json") or {}
    events = read_jsonl(trial_dir / "agent" / "hermes-run-events.jsonl")
    session = session_summary(read_jsonl(trial_dir / "agent" / "hermes-session.jsonl"))
    gateway_log = ""
    try:
        gateway_log = (trial_dir / "agent" / "hermes-gateway.txt").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        pass

    tool_events = [event for event in events if event.get("event") == "tool.completed"]
    tool_counts: Counter[str] = Counter(
        str(event["tool"]) for event in tool_events if isinstance(event.get("tool"), str)
    )
    failed_tool_counts: Counter[str] = Counter(
        str(event["tool"])
        for event in tool_events
        if isinstance(event.get("tool"), str) and event.get("error") is True
    )
    message_delta_count = sum(event.get("event") == "message.delta" for event in events)
    session_api_calls = number(session.get("api_call_count"))
    model_activity_observed = bool(message_delta_count or (session_api_calls or 0) > 0)
    truncated_count = gateway_log.count("Response truncated (finish_reason='length')")
    balance_line_count = len(
        re.findall(r"Insufficient balance or no resource package", gateway_log, flags=re.I)
    )
    token = classify_token_accounting(
        run.get("usage") if isinstance(run.get("usage"), dict) else {},
        agent_result,
        model_activity_observed,
        truncated_count,
    )

    product_status = str(metadata.get("product_terminal_status") or "unknown")
    run_status = str(run.get("status") or "unknown")
    timeout = product_status == "timeout" or run_status == "timed_out"
    trajectory_status = str(metadata.get("trajectory_capture_status") or "unknown")
    terminal_event = metadata.get("trajectory_terminal_event")
    terminal_event_count = number(metadata.get("trajectory_terminal_event_count"))
    normal_e2e_pass = bool(
        reward == 1
        and product_status == "completed"
        and run_status == "completed"
        and trajectory_status == "saved"
        and terminal_event == "run.completed"
        and terminal_event_count == 1
    )
    row: dict[str, Any] = {
        "task_id": task_id,
        "attempt_count_for_task": None,
        "selected_run_dir": run_dir.name,
        "selected_trial_name": result.get("trial_name") or trial_dir.name,
        "selected_trial_path": str(trial_dir.resolve()),
        "selected_finished_at": result.get("finished_at"),
        "reward": int(reward) if reward is not None else None,
        "verify_status": "pass" if reward == 1 else "no_pass" if reward == 0 else "missing",
        "normal_e2e_pass": normal_e2e_pass,
        "outcome_bucket": "",
        "timeout": timeout,
        "product_terminal_status": product_status,
        "product_return_code": number(metadata.get("product_return_code")),
        "product_completion_claim": metadata.get("product_completion_claim"),
        "run_status": run_status,
        "run_error": run.get("error"),
        "trajectory_capture_status": trajectory_status,
        "trajectory_terminal_event": terminal_event,
        "trajectory_terminal_event_count": terminal_event_count,
        "trajectory_capture_error": metadata.get("trajectory_capture_error"),
        "e2e_s": seconds_between(result),
        "environment_setup_s": seconds_between(result.get("environment_setup")),
        "agent_setup_s": seconds_between(result.get("agent_setup")),
        "agent_execution_s": seconds_between(result.get("agent_execution")),
        "verifier_s": seconds_between(result.get("verifier")),
        "run_duration_s": number(run.get("duration_sec")),
        "tool_calls": len(tool_events),
        "tool_calls_failed": sum(failed_tool_counts.values()),
        "tool_call_failure_rate": (
            sum(failed_tool_counts.values()) / len(tool_events) if tool_events else 0.0
        ),
        "tool_duration_s": sum(float(event.get("duration") or 0) for event in tool_events),
        "tool_breakdown": compact_counter(tool_counts),
        "failed_tool_breakdown": compact_counter(failed_tool_counts),
        "session_api_calls": session_api_calls,
        "session_messages": number(metadata.get("trajectory_session_message_count")),
        "message_delta_count": message_delta_count,
        "model_activity_observed": model_activity_observed,
        "gateway_response_truncated_count": truncated_count,
        "gateway_balance_error_line_count": balance_line_count,
        "cost_usd": number(agent_result.get("cost_usd")),
        **token,
        **verifier_summary(trial_dir),
    }
    row["outcome_bucket"] = derive_outcome_bucket(row)
    return row


def discover_trials(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result_path in sorted(root.glob("*/*/result.json")):
        trial_dir = result_path.parent
        run_dir = trial_dir.parent
        if run_dir.name == "analysis":
            continue
        row = extract_trial(run_dir, trial_dir)
        if row is not None:
            row["_sort_key"] = batch_sort_key(run_dir, read_json(result_path) or {})
            rows.append(row)
    return rows


def select_latest(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["task_id"]), []).append(row)
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for task_id, attempts in grouped.items():
        latest = max(attempts, key=lambda row: row["_sort_key"])
        latest["attempt_count_for_task"] = len(attempts)
        latest.pop("_sort_key", None)
        selected.append(latest)
        counts[task_id] = len(attempts)
    return sorted(selected, key=lambda row: str(row["task_id"])), counts


def group_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(rows),
        "time": {
            field: metric_stats(row.get(field) for row in rows)
            for field in (
                "e2e_s",
                "environment_setup_s",
                "agent_setup_s",
                "agent_execution_s",
                "verifier_s",
                "run_duration_s",
            )
        },
        "tools": {
            "tool_calls": metric_stats(row.get("tool_calls") for row in rows),
            "tool_calls_failed": metric_stats(
                row.get("tool_calls_failed") for row in rows
            ),
            "tool_duration_s": metric_stats(row.get("tool_duration_s") for row in rows),
        },
        "token": token_summary(rows),
    }


def token_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row["token_accounting_status"]) for row in rows)
    usable = [row for row in rows if row["token_accounting_status"] == "reported"]
    return {
        "accounting_status": dict(sorted(statuses.items())),
        "usable_reported_trials": len(usable),
        "input_tokens": metric_stats(row.get("token_input") for row in usable),
        "output_tokens": metric_stats(row.get("token_output") for row in usable),
        "total_tokens": metric_stats(row.get("token_total") for row in usable),
        "source_mismatch_count": sum(
            row["token_sources_consistent"] is False for row in rows
        ),
    }


def summarize(
    discovered_rows: list[dict[str, Any]],
    latest_rows: list[dict[str, Any]],
    included_rows: list[dict[str, Any]],
    excluded_tasks: set[str],
) -> dict[str, Any]:
    tool_counts: Counter[str] = Counter()
    failed_tool_counts: Counter[str] = Counter()
    for row in included_rows:
        tool_counts.update(json.loads(str(row["tool_breakdown"])))
        failed_tool_counts.update(json.loads(str(row["failed_tool_breakdown"])))

    latest_by_task = {str(row["task_id"]): row for row in latest_rows}
    excluded_present = sorted(excluded_tasks & latest_by_task.keys())
    excluded_scored = [
        task_id for task_id in excluded_present if latest_by_task[task_id]["reward"] is not None
    ]
    unverified_after_exclusion = [
        row for row in latest_rows if row["task_id"] not in excluded_tasks and row["reward"] is None
    ]
    groups = {
        "all_included": included_rows,
        "verify_pass": [row for row in included_rows if row["verify_status"] == "pass"],
        "verify_no_pass": [row for row in included_rows if row["verify_status"] == "no_pass"],
        "timeout": [row for row in included_rows if row["timeout"]],
        "non_timeout": [row for row in included_rows if not row["timeout"]],
        "normal_e2e_pass": [row for row in included_rows if row["normal_e2e_pass"]],
    }
    return {
        "schema_version": 2,
        "selection_policy": {
            "latest_attempt": "Maximum batch directory timestamp YYYY-MM-DD__HH-MM-SS per task_id; result finished_at and path are fallbacks only for malformed batch names.",
            "excluded_tasks": sorted(excluded_tasks),
            "included_trials": "Only latest trials with a numeric verifier reward of 0 or 1.",
        },
        "scope": {
            "discovered_valid_attempts": len(discovered_rows),
            "unique_tasks_before_exclusion": len(latest_rows),
            "repeated_task_count": sum(row["attempt_count_for_task"] > 1 for row in latest_rows),
            "excluded_tasks_present": excluded_present,
            "excluded_tasks_with_verifier_reward": excluded_scored,
            "latest_tasks_without_verifier_reward_after_exclusion": sorted(
                str(row["task_id"]) for row in unverified_after_exclusion
            ),
            "included_latest_verified_tasks": len(included_rows),
        },
        "completion": {
            "verify_pass": sum(row["verify_status"] == "pass" for row in included_rows),
            "verify_no_pass": sum(row["verify_status"] == "no_pass" for row in included_rows),
            "timeout": sum(bool(row["timeout"]) for row in included_rows),
            "non_timeout": sum(not row["timeout"] for row in included_rows),
            "normal_e2e_pass": sum(bool(row["normal_e2e_pass"]) for row in included_rows),
            "outcome_bucket": dict(
                sorted(Counter(str(row["outcome_bucket"]) for row in included_rows).items())
            ),
            "product_terminal_status": dict(
                sorted(Counter(str(row["product_terminal_status"]) for row in included_rows).items())
            ),
            "trajectory_capture_status": dict(
                sorted(Counter(str(row["trajectory_capture_status"]) for row in included_rows).items())
            ),
        },
        "metrics_by_group": {name: group_metrics(group) for name, group in groups.items()},
        "tool_breakdown": dict(tool_counts.most_common()),
        "failed_tool_breakdown": dict(failed_tool_counts.most_common()),
        "token_definition": {
            "canonical_source": "hermes-run.json.usage, cross-checked against result.json agent_result n_input_tokens/n_output_tokens when both are present",
            "total_formula": "token_total = token_input + token_output only when both terminal usage fields are present",
            "not_used_as_total": "hermes-session.jsonl input_tokens/cache fields are retained only as activity evidence because their values do not consistently match terminal runner aggregates",
            "excluded_from_token_totals": "missing usage and 0/0 records with observed model activity are not interpreted as zero-cost calls",
            "cost_usd": "No aggregate USD cost is produced when cost_usd is unavailable; token counts are not converted to cost",
        },
        "limitations": [
            "This is an exploratory C0 snapshot: formal_score_eligible and lifecycle trigger fields are not a validity gate for ordinary verifier-based baseline reporting.",
            "Timeout is reported separately from verifier outcome. It is retained as an observed task outcome and is not automatically recategorized as infrastructure failure.",
            "CPU, RAM, GPU, disk, network bytes, and provider billing are not present in the source artifacts and are intentionally not estimated.",
            "Gateway balance-error line counts are diagnostics from logs, not a count of provider requests or a causal label for the final task outcome.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TRIAL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def format_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        return f"{int(value):,}"
    return f"{float(value):,.{digits}f}"


def format_duration(seconds: Any) -> str:
    if seconds is None:
        return "—"
    return f"{float(seconds) / 60:.2f} min"


def write_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    completion = summary["completion"]
    all_metrics = summary["metrics_by_group"]["all_included"]
    token = all_metrics["token"]
    scope = summary["scope"]
    lines = [
        "# Hermes C0 latest verified trials",
        "",
        "This report is generated by `extract_hermes_c0_trials.py`. Re-run the script after adding or replacing trials; do not edit this file manually.",
        "",
        "## Scope",
        "",
        "| Item | Value |",
        "| --- | ---: |",
        f"| Valid discovered attempts | {scope['discovered_valid_attempts']} |",
        f"| Unique tasks before exclusion | {scope['unique_tasks_before_exclusion']} |",
        f"| Repeated tasks | {scope['repeated_task_count']} |",
        f"| Included latest verified tasks | {scope['included_latest_verified_tasks']} |",
        f"| Excluded task ids | {', '.join(scope['excluded_tasks_present']) or '—'} |",
        f"| Latest tasks without verifier reward | {', '.join(scope['latest_tasks_without_verifier_reward_after_exclusion']) or '—'} |",
        "",
        "## Completion",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Verify pass | {completion['verify_pass']} |",
        f"| Verify no pass | {completion['verify_no_pass']} |",
        f"| Timeout | {completion['timeout']} |",
        f"| Non-timeout | {completion['non_timeout']} |",
        f"| Normal E2E pass | {completion['normal_e2e_pass']} |",
        "",
        "`normal_e2e_pass` requires verifier pass, product/run completed, saved trajectory, and exactly one `run.completed` terminal event. A verifier pass after timeout remains a functional pass but not a normal E2E pass.",
        "",
        "## Time, tools, and tokens",
        "",
        "| Metric | Coverage | Sum | Median | P90 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, field in (
        ("End-to-end time", "e2e_s"),
        ("Agent execution time", "agent_execution_s"),
        ("Runner duration", "run_duration_s"),
    ):
        stats = all_metrics["time"][field]
        lines.append(
            f"| {label} | {stats['n']}/{len(rows)} | {format_duration(stats['sum'])} | {format_duration(stats['median'])} | {format_duration(stats['p90'])} |"
        )
    for label, field in (("Tool calls", "tool_calls"), ("Failed tool calls", "tool_calls_failed")):
        stats = all_metrics["tools"][field]
        lines.append(
            f"| {label} | {stats['n']}/{len(rows)} | {format_number(stats['sum'])} | {format_number(stats['median'])} | {format_number(stats['p90'])} |"
        )
    token_stats = token["total_tokens"]
    lines.append(
        f"| Usable reported total tokens | {token_stats['n']}/{len(rows)} | {format_number(token_stats['sum'])} | {format_number(token_stats['median'])} | {format_number(token_stats['p90'])} |"
    )
    lines.extend(
        [
            "",
            "## Token definition",
            "",
            "- Canonical usage is `agent/hermes-run.json` → `usage`, cross-checked with `result.json` token fields when both exist.",
            "- Input/output are terminal runner-reported aggregates. Cache accounting is not separately available in this source and is not inferred from session export fields.",
            "- `hermes-session.jsonl` token fields are not used to fill missing totals because they do not consistently match the terminal aggregate; they only provide model-activity evidence.",
            "- Missing usage remains missing. `0/0` with model activity or output truncation is `suspect_zero_after_model_activity`, not zero cost, and is excluded from token totals.",
            "- USD cost is not estimated from tokens because no verified per-model pricing and no reliable cost telemetry are available in these artifacts.",
            "",
            "| Token accounting status | Tasks |",
            "| --- | ---: |",
        ]
    )
    for status, count in token["accounting_status"].items():
        lines.append(f"| {status} | {count} |")
    lines.extend(
        [
            "",
            "## Latest verified task rows with no pass",
            "",
            "| Task | Timeout | Product status | Runner status | Token status | Tool calls | Path |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in rows:
        if row["verify_status"] != "no_pass":
            continue
        lines.append(
            "| {task} | {timeout} | {product} | {run} | {token} | {tools} | `{path}` |".format(
                task=row["task_id"],
                timeout="yes" if row["timeout"] else "no",
                product=row["product_terminal_status"],
                run=row["run_status"],
                token=row["token_accounting_status"],
                tools=row["tool_calls"],
                path=row["selected_trial_path"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = args.root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    excluded_tasks = DEFAULT_EXCLUDED_TASKS | set(args.exclude_task)
    if not root.is_dir():
        raise SystemExit(f"Hermes root does not exist: {root}")

    discovered = discover_trials(root)
    latest, _ = select_latest(discovered)
    included = [
        row
        for row in latest
        if row["task_id"] not in excluded_tasks and row["reward"] is not None
    ]
    summary = summarize(discovered, latest, included, excluded_tasks)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "hermes-c0-latest-verified-trials.csv"
    failed_csv_path = output_dir / "hermes-c0-latest-verified-no-pass.csv"
    json_path = output_dir / "hermes-c0-latest-verified-summary.json"
    markdown_path = output_dir / "hermes-c0-latest-verified-report.md"
    write_csv(csv_path, included)
    write_csv(
        failed_csv_path,
        [row for row in included if row["verify_status"] == "no_pass"],
    )
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(markdown_path, summary, included)

    print(
        "Extracted {included} latest verified tasks from {attempts} attempts "
        "({unique} unique tasks before exclusion).".format(
            included=len(included),
            attempts=summary["scope"]["discovered_valid_attempts"],
            unique=summary["scope"]["unique_tasks_before_exclusion"],
        )
    )
    print(f"CSV: {csv_path}")
    print(f"Summary: {json_path}")
    print(f"Report: {markdown_path}")


if __name__ == "__main__":
    main()
