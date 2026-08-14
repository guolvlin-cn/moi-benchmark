#!/usr/bin/env python3
"""Extract a Hermes-v2-compatible latest-attempt Pi Terminal-Bench snapshot."""

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
BATCH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2}$")
FIELDS = [
    "task_id", "attempt_count_for_task", "selected_run_dir", "selected_trial_name",
    "selected_trial_path", "selected_finished_at", "reward", "verify_status",
    "normal_e2e_pass", "outcome_bucket", "timeout", "product_terminal_status",
    "product_return_code", "product_completion_claim", "trajectory_capture_status",
    "trajectory_capture_error", "pi_final_stop_reason", "e2e_s",
    "environment_setup_s", "agent_setup_s", "agent_execution_s", "verifier_s",
    "tool_calls", "tool_calls_failed", "tool_call_failure_rate", "tool_breakdown",
    "failed_tool_breakdown", "assistant_messages", "model_activity_observed",
    "gateway_balance_error_line_count", "token_input", "token_cache", "token_output",
    "token_total", "token_source", "token_accounting_status", "cost_usd",
    "verifier_tests", "verifier_passed", "verifier_failed", "verifier_skipped",
    "failed_test_names",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--exclude-task", action="append", default=[])
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
        stream = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    with stream:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def number(value: Any) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    return None


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_between(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    start, finish = parse_time(value.get("started_at")), parse_time(value.get("finished_at"))
    return (finish - start).total_seconds() if start and finish else None


def percentile(values: Iterable[float | int | None], p: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    index = (len(clean) - 1) * p
    low, high = math.floor(index), math.ceil(index)
    return clean[low] if low == high else clean[low] + (clean[high] - clean[low]) * (index - low)


def metric_stats(values: Iterable[float | int | None]) -> dict[str, Any]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"n": 0, "sum": None, "mean": None, "median": None, "p90": None, "min": None, "max": None}
    return {
        "n": len(clean), "sum": sum(clean), "mean": sum(clean) / len(clean),
        "median": percentile(clean, 0.5), "p90": percentile(clean, 0.9),
        "min": min(clean), "max": max(clean),
    }


def verifier_summary(trial_dir: Path) -> dict[str, Any]:
    ctrf = read_json(trial_dir / "verifier" / "ctrf.json") or {}
    results = ctrf.get("results") if isinstance(ctrf.get("results"), dict) else {}
    summary = results.get("summary") if isinstance(results.get("summary"), dict) else {}
    tests = results.get("tests") if isinstance(results.get("tests"), list) else []
    failed = [str(test.get("name")) for test in tests if isinstance(test, dict) and test.get("status") == "failed"]
    return {
        "verifier_tests": number(summary.get("tests")),
        "verifier_passed": number(summary.get("passed")),
        "verifier_failed": number(summary.get("failed")),
        "verifier_skipped": number(summary.get("skipped")),
        "failed_test_names": "; ".join(failed),
    }


def pi_summary(trial_dir: Path) -> dict[str, Any]:
    events = read_jsonl(trial_dir / "agent" / "pi.txt")
    calls: Counter[str] = Counter()
    failed: Counter[str] = Counter()
    assistant_messages = 0
    for event in events:
        if event.get("type") == "message_end" and isinstance(event.get("message"), dict):
            message = event["message"]
            if message.get("role") == "assistant":
                assistant_messages += 1
            content = message.get("content") if isinstance(message.get("content"), list) else []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "toolCall":
                    calls[str(item.get("name") or "unknown")] += 1
        elif event.get("type") == "tool_execution_end":
            result = event.get("result") if isinstance(event.get("result"), dict) else {}
            if event.get("isError") is True or result.get("isError") is True:
                failed[str(event.get("toolName") or "unknown")] += 1
    stderr = ""
    try:
        stderr = (trial_dir / "agent" / "pi.stderr.txt").read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    return {
        "tool_calls": sum(calls.values()),
        "tool_calls_failed": sum(failed.values()),
        "tool_breakdown": json.dumps(dict(sorted(calls.items())), ensure_ascii=False),
        "failed_tool_breakdown": json.dumps(dict(sorted(failed.items())), ensure_ascii=False),
        "assistant_messages": assistant_messages,
        "model_activity_observed": assistant_messages > 0,
        "gateway_balance_error_line_count": len(re.findall(r"Insufficient balance or no resource package", stderr, re.I)),
    }


def extract_trial(run_dir: Path, trial_dir: Path) -> dict[str, Any] | None:
    result = read_json(trial_dir / "result.json")
    if not result or not result.get("task_name"):
        return None
    agent = result.get("agent_result") if isinstance(result.get("agent_result"), dict) else {}
    metadata = agent.get("metadata") if isinstance(agent.get("metadata"), dict) else {}
    task_id = metadata.get("task_id") or str(result["task_name"]).removeprefix("terminal-bench/")
    reward_value = (((result.get("verifier_result") or {}).get("rewards") or {}).get("reward"))
    reward = number(reward_value)
    reward = int(reward) if reward in (0, 0.0, 1, 1.0) else None
    pi = pi_summary(trial_dir)
    metadata_tool_calls = number(metadata.get("pi_tool_call_count"))
    if metadata_tool_calls is not None:
        pi["tool_calls"] = int(metadata_tool_calls)
    product_status = str(metadata.get("product_terminal_status") or "unknown")
    timeout = product_status == "timeout"
    normal_pass = reward == 1 and not timeout
    token_input = number(agent.get("n_input_tokens"))
    token_cache = number(agent.get("n_cache_tokens"))
    token_output = number(agent.get("n_output_tokens"))
    complete_tokens = token_input is not None and token_cache is not None and token_output is not None
    if not complete_tokens:
        token_status = "missing_after_model_activity" if pi["model_activity_observed"] else "missing_no_model_activity"
        token_total = None
    elif token_input == token_cache == token_output == 0 and pi["model_activity_observed"]:
        token_status, token_total = "suspect_zero_after_model_activity", None
    elif token_input == token_cache == token_output == 0:
        token_status, token_total = "reported_zero_no_activity", 0
    else:
        token_status, token_total = "reported", token_input + token_cache + token_output
    if reward == 1:
        outcome = "normal_e2e_pass" if normal_pass else "verifier_pass_after_timeout"
    elif timeout:
        outcome = "timeout_no_pass"
    elif product_status == "completed":
        outcome = "completed_no_pass"
    else:
        outcome = "failed_no_pass"
    row = {
        "task_id": task_id, "attempt_count_for_task": None,
        "selected_run_dir": run_dir.name, "selected_trial_name": result.get("trial_name") or trial_dir.name,
        "selected_trial_path": str(trial_dir.resolve()), "selected_finished_at": result.get("finished_at"),
        "reward": reward, "verify_status": "pass" if reward == 1 else "no_pass" if reward == 0 else "missing",
        "normal_e2e_pass": normal_pass, "outcome_bucket": outcome, "timeout": timeout,
        "product_terminal_status": product_status, "product_return_code": number(metadata.get("product_return_code")),
        "product_completion_claim": metadata.get("product_completion_claim"),
        "trajectory_capture_status": metadata.get("pi_trajectory_status") or "unknown",
        "trajectory_capture_error": metadata.get("pi_trajectory_error"),
        "pi_final_stop_reason": metadata.get("pi_final_stop_reason"),
        "e2e_s": seconds_between(result), "environment_setup_s": seconds_between(result.get("environment_setup")),
        "agent_setup_s": seconds_between(result.get("agent_setup")), "agent_execution_s": seconds_between(result.get("agent_execution")),
        "verifier_s": seconds_between(result.get("verifier")),
        "tool_call_failure_rate": pi["tool_calls_failed"] / pi["tool_calls"] if pi["tool_calls"] else 0.0,
        "token_input": token_input, "token_cache": token_cache, "token_output": token_output,
        "token_total": token_total, "token_source": "result.json.agent_result" if complete_tokens else "missing",
        "token_accounting_status": token_status, "cost_usd": number(agent.get("cost_usd")),
        **pi, **verifier_summary(trial_dir),
    }
    return row


def discover(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.glob("*/*/result.json")):
        row = extract_trial(path.parent.parent, path.parent)
        if row is None:
            continue
        run_name = path.parent.parent.name
        finished = parse_time(row["selected_finished_at"]) or datetime.min
        if BATCH_RE.fullmatch(run_name):
            sort_key = (2, datetime.strptime(run_name, "%Y-%m-%d__%H-%M-%S"), "")
        else:
            sort_key = (1, finished, run_name)
        row["_sort_key"] = sort_key
        rows.append(row)
    return rows


def select_latest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["task_id"]), []).append(row)
    selected = []
    for attempts in grouped.values():
        row = max(attempts, key=lambda item: item["_sort_key"])
        row["attempt_count_for_task"] = len(attempts)
        row.pop("_sort_key", None)
        selected.append(row)
    return sorted(selected, key=lambda row: str(row["task_id"]))


def token_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row["token_accounting_status"]) for row in rows)
    usable = [row for row in rows if row["token_accounting_status"] == "reported"]
    return {
        "accounting_status": dict(sorted(statuses.items())), "usable_reported_trials": len(usable),
        "input_tokens": metric_stats(row["token_input"] for row in usable),
        "cache_tokens": metric_stats(row["token_cache"] for row in usable),
        "output_tokens": metric_stats(row["token_output"] for row in usable),
        "total_tokens": metric_stats(row["token_total"] for row in usable),
    }


def group_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(rows),
        "time": {field: metric_stats(row[field] for row in rows) for field in ("e2e_s", "environment_setup_s", "agent_setup_s", "agent_execution_s", "verifier_s")},
        "tools": {field: metric_stats(row[field] for row in rows) for field in ("tool_calls", "tool_calls_failed")},
        "token": token_summary(rows),
    }


def summarize(discovered: list[dict[str, Any]], latest: list[dict[str, Any]], included: list[dict[str, Any]], excluded: set[str]) -> dict[str, Any]:
    missing = [row for row in latest if row["task_id"] not in excluded and row["reward"] is None]
    groups = {
        "all_included": included,
        "verify_pass": [row for row in included if row["reward"] == 1],
        "verify_no_pass": [row for row in included if row["reward"] == 0],
        "timeout": [row for row in included if row["timeout"]],
        "non_timeout": [row for row in included if not row["timeout"]],
    }
    tools, failed_tools = Counter(), Counter()
    for row in included:
        tools.update(json.loads(row["tool_breakdown"]))
        failed_tools.update(json.loads(row["failed_tool_breakdown"]))
    passes = sum(row["reward"] == 1 for row in included)
    return {
        "schema_version": 2,
        "selection_policy": {
            "latest_attempt": "Maximum batch directory timestamp per task_id.",
            "excluded_tasks": sorted(excluded),
            "included_trials": "Latest trials with numeric verifier reward 0 or 1; lifecycle audit fields are not gates.",
        },
        "scope": {
            "discovered_valid_attempts": len(discovered), "unique_tasks_before_exclusion": len(latest),
            "repeated_task_count": sum(row["attempt_count_for_task"] > 1 for row in latest),
            "excluded_tasks_present": sorted(excluded & {str(row["task_id"]) for row in latest}),
            "latest_tasks_without_verifier_reward_after_exclusion": sorted(str(row["task_id"]) for row in missing),
            "included_latest_verified_tasks": len(included),
        },
        "completion": {
            "verify_pass": passes, "verify_no_pass": len(included) - passes,
            "pass_rate_valid_verifier": passes / len(included) if included else None,
            "timeout": sum(bool(row["timeout"]) for row in included),
            "non_timeout": sum(not row["timeout"] for row in included),
            "normal_e2e_pass": sum(bool(row["normal_e2e_pass"]) for row in included),
            "outcome_bucket": dict(sorted(Counter(str(row["outcome_bucket"]) for row in included).items())),
            "product_terminal_status": dict(sorted(Counter(str(row["product_terminal_status"]) for row in included).items())),
            "trajectory_capture_status": dict(sorted(Counter(str(row["trajectory_capture_status"]) for row in included).items())),
        },
        "metrics_by_group": {name: group_metrics(rows) for name, rows in groups.items()},
        "tool_breakdown": dict(tools.most_common()), "failed_tool_breakdown": dict(failed_tools.most_common()),
        "token_definition": {
            "canonical_source": "result.json agent_result n_input_tokens/n_cache_tokens/n_output_tokens",
            "total_formula": "input + cache + output", "cost_usd": "Reported only; no price-based estimate.",
        },
        "limitations": [
            "C0 audit pass, no_hit, audit infrastructure error, and lifecycle_gate_passed are intentionally not validity gates in this report.",
            "Latest trials without a numeric verifier reward are reported as verifier infrastructure cases and excluded from the valid-verifier pass-rate denominator.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: Any) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}" if float(value).is_integer() else f"{float(value):,.2f}"


def mins(value: Any) -> str:
    return "—" if value is None else f"{float(value) / 60:.2f} min"


def write_report(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    scope, completion = summary["scope"], summary["completion"]
    metrics = summary["metrics_by_group"]["all_included"]
    lines = [
        "# Pi C0 latest verified trials", "",
        "Generated from the latest attempt per task. Lifecycle-audit fields are intentionally not used as validity gates.", "",
        "## Scope", "", "| Item | Value |", "| --- | ---: |",
        f"| Valid discovered attempts | {scope['discovered_valid_attempts']} |",
        f"| Unique tasks before exclusion | {scope['unique_tasks_before_exclusion']} |",
        f"| Repeated tasks | {scope['repeated_task_count']} |",
        f"| Included latest verified tasks | {scope['included_latest_verified_tasks']} |",
        f"| Latest tasks without verifier reward | {', '.join(scope['latest_tasks_without_verifier_reward_after_exclusion']) or '—'} |", "",
        "## Completion", "", "| Metric | Count |", "| --- | ---: |",
        f"| Verify pass | {completion['verify_pass']} |", f"| Verify no pass | {completion['verify_no_pass']} |",
        f"| Valid-verifier pass rate | {completion['pass_rate_valid_verifier']:.2%} |",
        f"| Timeout | {completion['timeout']} |", f"| Non-timeout | {completion['non_timeout']} |", "",
        "## Time, tools, and tokens", "", "| Metric | Coverage | Sum | Median | P90 |", "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, field in (("End-to-end time", "e2e_s"), ("Agent execution time", "agent_execution_s"), ("Verifier time", "verifier_s")):
        stat = metrics["time"][field]
        lines.append(f"| {label} | {stat['n']}/{len(rows)} | {mins(stat['sum'])} | {mins(stat['median'])} | {mins(stat['p90'])} |")
    for label, field in (("Tool calls", "tool_calls"), ("Failed tool calls", "tool_calls_failed")):
        stat = metrics["tools"][field]
        lines.append(f"| {label} | {stat['n']}/{len(rows)} | {fmt(stat['sum'])} | {fmt(stat['median'])} | {fmt(stat['p90'])} |")
    token = metrics["token"]["total_tokens"]
    lines.append(f"| Usable reported total tokens | {token['n']}/{len(rows)} | {fmt(token['sum'])} | {fmt(token['median'])} | {fmt(token['p90'])} |")
    lines += ["", "## Token accounting", "", "Total tokens are Pi-reported input + cache-read + output tokens.", "", "| Status | Tasks |", "| --- | ---: |"]
    for status, count in metrics["token"]["accounting_status"].items():
        lines.append(f"| {status} | {count} |")
    lines += ["", "## Latest verified task rows with no pass", "", "| Task | Timeout | Product status | Stop reason | Tool calls | Path |", "| --- | --- | --- | --- | ---: | --- |"]
    for row in rows:
        if row["reward"] == 0:
            lines.append(f"| {row['task_id']} | {'yes' if row['timeout'] else 'no'} | {row['product_terminal_status']} | {row['pi_final_stop_reason'] or '—'} | {row['tool_calls']} | `{row['selected_trial_path']}` |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root, output = args.root.expanduser().resolve(), args.output_dir.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Pi root does not exist: {root}")
    excluded = DEFAULT_EXCLUDED_TASKS | set(args.exclude_task)
    discovered = discover(root)
    latest = select_latest(discovered)
    included = [row for row in latest if row["task_id"] not in excluded and row["reward"] is not None]
    summary = summarize(discovered, latest, included, excluded)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "pi-c0-latest-verified-trials.csv", included)
    write_csv(output / "pi-c0-latest-verified-no-pass.csv", [row for row in included if row["reward"] == 0])
    (output / "pi-c0-latest-verified-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(output / "pi-c0-latest-verified-report.md", summary, included)
    print(f"Extracted {len(included)} latest verified tasks from {len(discovered)} attempts.")


if __name__ == "__main__":
    main()
