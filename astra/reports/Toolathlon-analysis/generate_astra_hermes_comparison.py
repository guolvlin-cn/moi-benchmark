#!/usr/bin/env python3
"""Build the effective 108-task Toolathlon Astra/Hermes comparison dataset."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path("/home/vagrant/moi-benchmark")
RESULTS = ROOT / "astra/results"
M2 = RESULTS / "toolathlon-m2-first-batch-v4"
M3 = RESULTS / "toolathlon-m3-remaining-batch-v1"
POSTHOC = RESULTS / "toolathlon-posthoc-unavailable-infra-rerun-v1"
OUT_DIR = ROOT / "astra/reports/Toolathlon-analysis"
SYSTEMS = ("astra", "hermes")
ATTEMPT_RE = re.compile(r"-a(\d+)$")


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected object: {path}:{number}")
            rows.append(value)
    return rows


def scalar(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def attempt(run_id: str) -> int:
    match = ATTEMPT_RE.search(run_id)
    return int(match.group(1)) if match else 0


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def status_from_run(run: dict[str, Any]) -> dict[str, str]:
    return {
        "run_validity": str(run.get("run_validity") or "missing"),
        "verify_status": str(run.get("verify_status") or "missing"),
        "terminal_status": str(run.get("terminal_status") or "missing"),
        "failure_category": str(run.get("primary_failure_category") or "missing"),
    }


def reported_usage(row: dict[str, Any]) -> tuple[int, int, int] | None:
    usage = row.get("token_usage") or {}
    values = []
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        field = usage.get(key)
        if not isinstance(field, dict) or field.get("reliability") != "reported":
            return None
        value = field.get("value")
        if not isinstance(value, (int, float)):
            return None
        values.append(int(value))
    return values[0], values[1], values[2]


def extract_usage(run_dir: Path, run: dict[str, Any]) -> dict[str, Any]:
    rows = load_jsonl(run_dir / "model-usage.jsonl")
    completed = [row for row in rows if row.get("event") == "model_request.completed"]
    started = [row for row in rows if row.get("event") == "model_request.started"]
    started_by_id = {
        str(row["model_request_id"]): row
        for row in started
        if row.get("model_request_id") is not None
    }
    totals = [0, 0, 0]
    retained_totals = [0, 0, 0]
    excluded_totals = [0, 0, 0]
    usage_rows = 0
    retained_usage_rows = 0
    excluded_usage_rows = 0
    all_reported = True
    retained_all_reported = True
    retained_completion_count = 0
    excluded_completion_count = 0
    unmapped_completion_count = 0
    stream_counts: Counter[str] = Counter()
    request_classes: Counter[str] = Counter()
    for row in started:
        is_stream = row.get("stream") is True
        stream_counts["stream" if is_stream else "non_stream"] += 1
        tool_count = row.get("request_tool_count")
        if row.get("stream") is False and tool_count == 0:
            request_classes["internal_nonstream"] += 1
        else:
            request_classes["retained"] += 1
    for row in completed:
        started_row = started_by_id.get(str(row.get("model_request_id")))
        excluded = bool(
            started_row
            and started_row.get("stream") is False
            and started_row.get("request_tool_count") == 0
        )
        if started_row is None:
            unmapped_completion_count += 1
        if excluded:
            excluded_completion_count += 1
        else:
            retained_completion_count += 1

        values = reported_usage(row)
        if values is None:
            all_reported = False
            if not excluded:
                retained_all_reported = False
            continue

        usage_rows += 1
        for index, value in enumerate(values):
            totals[index] += value
        if excluded:
            excluded_usage_rows += 1
            for index, value in enumerate(values):
                excluded_totals[index] += value
        else:
            retained_usage_rows += 1
            for index, value in enumerate(values):
                retained_totals[index] += value

    budget = run.get("model_budget") or {}
    expected_completed = budget.get("provider_requests_completed")
    failed_requests = budget.get("provider_requests_failed")
    reliable = bool(completed) and all_reported and (
        expected_completed is None or expected_completed == len(completed)
    )
    retained_reliable = (
        bool(retained_completion_count)
        and retained_all_reported
        and unmapped_completion_count == 0
    )
    return {
        "model_requests_started": len(started),
        "model_requests_completed": len(completed),
        "model_requests_failed": int(failed_requests or 0),
        "token_usage_reported_completed": usage_rows,
        "token_usage_missing_completed": len(completed) - usage_rows,
        "stream_requests": stream_counts["stream"],
        "non_stream_requests": stream_counts["non_stream"],
        "internal_nonstream_requests": request_classes["internal_nonstream"],
        "retained_requests_excluding_internal_nonstream": request_classes["retained"],
        "internal_nonstream_requests_completed": excluded_completion_count,
        "internal_nonstream_usage_reported_completed": excluded_usage_rows,
        "retained_requests_completed_excluding_internal_nonstream": retained_completion_count,
        "retained_usage_reported_completed_excluding_internal_nonstream": retained_usage_rows,
        "retained_usage_missing_completed_excluding_internal_nonstream": (
            retained_completion_count - retained_usage_rows
        ),
        "token_input": totals[0] if usage_rows else None,
        "token_output": totals[1] if usage_rows else None,
        "token_total": totals[2] if usage_rows else None,
        "token_reliable": reliable,
        "token_note": (
            "all_completed_responses_reported"
            if reliable
            else "partial_or_missing_provider_usage"
        ),
        "internal_nonstream_token_input": excluded_totals[0] if excluded_usage_rows else None,
        "internal_nonstream_token_output": excluded_totals[1] if excluded_usage_rows else None,
        "internal_nonstream_token_total": excluded_totals[2] if excluded_usage_rows else None,
        "token_excluding_internal_nonstream_input": (
            retained_totals[0] if retained_usage_rows else None
        ),
        "token_excluding_internal_nonstream_output": (
            retained_totals[1] if retained_usage_rows else None
        ),
        "token_excluding_internal_nonstream_total": (
            retained_totals[2] if retained_usage_rows else None
        ),
        "token_excluding_internal_nonstream_reliable": retained_reliable,
        "token_excluding_internal_nonstream_note": (
            "all_retained_completed_responses_reported"
            if retained_reliable
            else "partial_or_missing_retained_provider_usage"
        ),
    }


def build_row(
    position: int,
    task_id: str,
    system: str,
    run_dir: Path,
    source: str,
    projected: dict[str, str] | None = None,
) -> dict[str, Any]:
    run = load_json(run_dir / "run.json")
    status = projected or status_from_run(run)
    started_at = str(run["started_at"])
    finished_at = str(run["finished_at"])
    e2e = (parse_time(finished_at) - parse_time(started_at)).total_seconds()
    agent = run.get("agent_duration_seconds")
    evaluator = run.get("evaluator_duration_seconds")
    trajectory = run.get("trajectory") or {}
    model_budget = run.get("model_budget") or {}
    return {
        "position": position,
        "task_id": task_id,
        "system": system,
        "run_id": run.get("run_id"),
        "source": source,
        "run_directory": str(run_dir),
        **status,
        "timeout": bool(run.get("timeout")),
        "timeout_scope": str(run.get("timeout_scope") or "none"),
        "normal_e2e_success": status["verify_status"] == "pass" and not run.get("timeout"),
        "started_at": started_at,
        "finished_at": finished_at,
        "e2e_seconds": e2e,
        "agent_seconds": float(agent) if isinstance(agent, (int, float)) else None,
        "evaluator_seconds": float(evaluator) if isinstance(evaluator, (int, float)) else None,
        "orchestration_seconds": (
            e2e - float(agent or 0) - float(evaluator or 0)
            if isinstance(agent, (int, float)) and isinstance(evaluator, (int, float))
            else None
        ),
        "tool_calls": trajectory.get("tool_terminal_events"),
        "tool_failures": trajectory.get("tool_failed_events"),
        "started_only_tool_calls": trajectory.get("started_only_tool_calls"),
        "claim_done_seen": bool(run.get("claim_done_seen")),
        "model_request_limit": model_budget.get("max_requests"),
        "model_request_limit_exceeded": bool(model_budget.get("limit_exceeded")),
        **extract_usage(run_dir, run),
    }


def m2_rows() -> dict[tuple[int, str], dict[str, Any]]:
    qualification = load_json(M2 / "m2-first-batch-qualification.json")
    result = {}
    for task in qualification["tasks"]:
        position = int(task["position"])
        task_id = str(task["task_id"])
        for system in SYSTEMS:
            item = task["systems"][system]
            run_dir = Path(item["effective_run_directory"])
            row = build_row(position, task_id, system, run_dir, "m2_qualification")
            # Qualification is authoritative for the effective evaluation result.
            row["verify_status"] = str(item.get("verify_status") or row["verify_status"])
            row["terminal_status"] = str(item.get("terminal_status") or row["terminal_status"])
            row["normal_e2e_success"] = row["verify_status"] == "pass" and not row["timeout"]
            result[(position, system)] = row
    return result


def m3_rows() -> dict[tuple[int, str], dict[str, Any]]:
    manifest = load_json(M3 / "m3-batch-manifest.json")
    projection = load_json(M3 / "artifact-gate-v2-projection.json")
    decisions = {
        (str(item["task_id"]), str(item["system_id"])): item
        for item in projection.get("slot_decisions", [])
    }
    incidents = {
        str(item["run_id"]): item
        for item in projection.get("incidents", [])
        if item.get("run_id")
    }
    result = {}
    for task in manifest["tasks"]:
        position = int(task["formal_position"])
        task_id = str(task["task_id"])
        for system in SYSTEMS:
            task_dir = M3 / "runs" / system / task_id
            candidates = []
            for path in task_dir.glob("*/run.json"):
                run = load_json(path)
                candidates.append((run, path.parent))
            decision = decisions.get((task_id, system))
            if decision:
                run_id = str(decision["effective_run_id"])
                selected = next(item for item in candidates if item[0].get("run_id") == run_id)
                incident = incidents.get(run_id)
                projected = None
                if incident:
                    projected = {
                        "run_validity": str(incident.get("projected_run_validity") or "missing"),
                        "verify_status": str(incident.get("projected_verify_status") or "missing"),
                        "terminal_status": str(selected[0].get("terminal_status") or "missing"),
                        "failure_category": str(
                            incident.get("projected_primary_failure_category") or "missing"
                        ),
                    }
                row = build_row(
                    position,
                    task_id,
                    system,
                    selected[1],
                    "m3_artifact_gate_v2_projection",
                    projected,
                )
            else:
                valid = [item for item in candidates if item[0].get("run_validity") == "valid"]
                pool = valid or candidates
                selected = max(
                    pool,
                    key=lambda item: (
                        attempt(str(item[0].get("run_id") or "")),
                        str(item[0].get("finished_at") or ""),
                    ),
                )
                row = build_row(
                    position,
                    task_id,
                    system,
                    selected[1],
                    "m3_latest_valid_run" if valid else "m3_latest_run",
                )
            result[(position, system)] = row
    return result


def apply_posthoc(rows: dict[tuple[int, str], dict[str, Any]]) -> list[dict[str, Any]]:
    qualification = load_json(POSTHOC / "posthoc-rerun-qualification.json")
    for item in qualification["cases"]:
        position = int(item["position"])
        system = str(item["system_id"])
        task_id = str(item["task_id"])
        run_dir = Path(item["effective_run_directory"])
        row = build_row(position, task_id, system, run_dir, "posthoc_formal_supplement")
        for key in ("run_validity", "verify_status", "terminal_status"):
            row[key] = str(item.get(key) or row[key])
        row["failure_category"] = str(
            item.get("primary_failure_category") or row["failure_category"]
        )
        row["normal_e2e_success"] = row["verify_status"] == "pass" and not row["timeout"]
        row["supplements_run_id"] = item.get("source_formal_run_id")
        rows[(position, system)] = row
    ordered = [rows[(position, system)] for position in range(1, 109) for system in SYSTEMS]
    if len(ordered) != 216:
        raise AssertionError(len(ordered))
    return ordered


def numeric(
    rows: list[dict[str, Any]],
    key: str,
    reliable: bool = False,
    reliability_key: str = "token_reliable",
) -> list[float]:
    values = []
    for row in rows:
        if reliable and not row[reliability_key]:
            continue
        value = row.get(key)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def stats(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "sum": sum(values),
        "mean": mean(values) if values else None,
        "median": median(values) if values else None,
        "p90": percentile(values, 0.9),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    systems = {}
    for system in SYSTEMS:
        selected = [row for row in rows if row["system"] == system]
        passes = [row for row in selected if row["verify_status"] == "pass"]
        no_passes = [row for row in selected if row["verify_status"] == "no_pass"]
        reliable = [row for row in selected if row["token_reliable"]]
        reliable_pass = [row for row in passes if row["token_reliable"]]
        systems[system] = {
            "tasks": len(selected),
            "verify": dict(Counter(row["verify_status"] for row in selected)),
            "validity": dict(Counter(row["run_validity"] for row in selected)),
            "pass_rate_all": len(passes) / len(selected),
            "normal_e2e_success": sum(row["normal_e2e_success"] for row in selected),
            "timeouts": sum(row["timeout"] for row in selected),
            "failure_categories": dict(Counter(row["failure_category"] for row in no_passes)),
            "time": {
                key: stats(numeric(selected, key))
                for key in ("e2e_seconds", "agent_seconds", "evaluator_seconds", "orchestration_seconds")
            },
            "tools": {
                "calls": stats(numeric(selected, "tool_calls")),
                "failures": stats(numeric(selected, "tool_failures")),
                "started_only": stats(numeric(selected, "started_only_tool_calls")),
            },
            "requests": {
                key: stats(numeric(selected, key))
                for key in (
                    "model_requests_started",
                    "model_requests_completed",
                    "model_requests_failed",
                    "stream_requests",
                    "non_stream_requests",
                )
            },
            "tokens": {
                "reliable_records": len(reliable),
                "input": stats(numeric(selected, "token_input", reliable=True)),
                "output": stats(numeric(selected, "token_output", reliable=True)),
                "total": stats(numeric(selected, "token_total", reliable=True)),
                "visible_lower_bound_records": sum(
                    isinstance(row.get("token_total"), (int, float)) for row in selected
                ),
                "visible_lower_bound_input": stats(numeric(selected, "token_input")),
                "visible_lower_bound_output": stats(numeric(selected, "token_output")),
                "visible_lower_bound_total": stats(numeric(selected, "token_total")),
                "pass_reliable_records": len(reliable_pass),
                "pass_input": stats(numeric(reliable_pass, "token_input", reliable=True)),
                "pass_output": stats(numeric(reliable_pass, "token_output", reliable=True)),
                "pass_total": stats(numeric(reliable_pass, "token_total", reliable=True)),
                "pass_visible_lower_bound_records": sum(
                    isinstance(row.get("token_total"), (int, float)) for row in passes
                ),
                "pass_visible_lower_bound_input": stats(numeric(passes, "token_input")),
                "pass_visible_lower_bound_output": stats(numeric(passes, "token_output")),
                "pass_visible_lower_bound_total": stats(numeric(passes, "token_total")),
            },
            "posthoc_slots": sum(row["source"] == "posthoc_formal_supplement" for row in selected),
            "request_limit_reached": sum(
                isinstance(row.get("model_request_limit"), (int, float))
                and row["model_requests_started"] >= row["model_request_limit"]
                for row in selected
            ),
        }

        tool_names: Counter[str] = Counter()
        for row in selected:
            for event in load_jsonl(Path(row["run_directory"]) / "tool-calls.jsonl"):
                if event.get("state") in {"succeeded", "failed"}:
                    tool_names[str(event.get("canonical_tool_name") or "unknown")] += 1
        systems[system]["tools"]["top_terminal_tools"] = tool_names.most_common(10)

    pairs = Counter()
    pair_tasks: dict[str, list[dict[str, Any]]] = {
        "both_pass": [],
        "astra_only": [],
        "hermes_only": [],
        "neither": [],
    }
    paired_differences = {key: [] for key in ("e2e_seconds", "agent_seconds", "tool_calls", "tool_failures")}
    overlapping_pass_token_rows = []
    for position in range(1, 109):
        astra = next(row for row in rows if row["position"] == position and row["system"] == "astra")
        hermes = next(row for row in rows if row["position"] == position and row["system"] == "hermes")
        ap = astra["verify_status"] == "pass"
        hp = hermes["verify_status"] == "pass"
        group = "both_pass" if ap and hp else "astra_only" if ap else "hermes_only" if hp else "neither"
        pairs[group] += 1
        pair_tasks[group].append({"position": position, "task_id": astra["task_id"]})
        for key in paired_differences:
            av, hv = astra.get(key), hermes.get(key)
            if isinstance(av, (int, float)) and isinstance(hv, (int, float)):
                paired_differences[key].append(float(av) - float(hv))
        if ap and hp and astra["token_reliable"] and hermes["token_reliable"]:
            overlapping_pass_token_rows.append((astra, hermes))

    overlap = {}
    for system, index in (("astra", 0), ("hermes", 1)):
        selected = [pair[index] for pair in overlapping_pass_token_rows]
        overlap[system] = {"n": len(selected)}
        overlap[system].update(
            {
                key: stats(numeric(selected, key, reliable=True))
                for key in ("token_input", "token_output", "token_total")
            }
        )

    # The filtered comparison uses Astra's provider usage after removing only
    # requests directly identified as stream=false and request_tool_count=0.
    # Hermes remains on its complete provider usage baseline.
    filtered_tokens = {}
    for system in SYSTEMS:
        selected = [row for row in rows if row["system"] == system]
        passes = [row for row in selected if row["verify_status"] == "pass"]
        if system == "astra":
            reliability_key = "token_excluding_internal_nonstream_reliable"
            keys = {
                "input": "token_excluding_internal_nonstream_input",
                "output": "token_excluding_internal_nonstream_output",
                "total": "token_excluding_internal_nonstream_total",
            }
        else:
            reliability_key = "token_reliable"
            keys = {"input": "token_input", "output": "token_output", "total": "token_total"}
        reliable = [row for row in selected if row[reliability_key]]
        reliable_pass = [row for row in passes if row[reliability_key]]
        filtered_tokens[system] = {
            "usage_basis": (
                "excluding_stream_false_and_zero_tools"
                if system == "astra"
                else "complete_provider_usage"
            ),
            "reliable_records": len(reliable),
            "pass_reliable_records": len(reliable_pass),
        }
        for label, key in keys.items():
            filtered_tokens[system][label] = stats(
                numeric(selected, key, reliable=True, reliability_key=reliability_key)
            )
            filtered_tokens[system][f"pass_{label}"] = stats(
                numeric(reliable_pass, key, reliable=True, reliability_key=reliability_key)
            )
            filtered_tokens[system][f"visible_lower_bound_{label}"] = stats(
                numeric(selected, key)
            )
            filtered_tokens[system][f"pass_visible_lower_bound_{label}"] = stats(
                numeric(passes, key)
            )
        filtered_tokens[system]["visible_lower_bound_records"] = sum(
            isinstance(row.get(keys["total"]), (int, float)) for row in selected
        )
        filtered_tokens[system]["pass_visible_lower_bound_records"] = sum(
            isinstance(row.get(keys["total"]), (int, float)) for row in passes
        )
        if system == "astra":
            filtered_tokens[system]["visible_lower_bound_reported_completed_requests"] = sum(
                row["retained_usage_reported_completed_excluding_internal_nonstream"]
                for row in selected
            )
            filtered_tokens[system]["visible_lower_bound_missing_usage_completed_requests"] = sum(
                row["retained_usage_missing_completed_excluding_internal_nonstream"]
                for row in selected
            )
        else:
            filtered_tokens[system]["visible_lower_bound_reported_completed_requests"] = sum(
                row["token_usage_reported_completed"] for row in selected
            )
            filtered_tokens[system]["visible_lower_bound_missing_usage_completed_requests"] = sum(
                row["token_usage_missing_completed"] for row in selected
            )

    filtered_overlap_rows = []
    for position in range(1, 109):
        astra = next(row for row in rows if row["position"] == position and row["system"] == "astra")
        hermes = next(row for row in rows if row["position"] == position and row["system"] == "hermes")
        if (
            astra["verify_status"] == "pass"
            and hermes["verify_status"] == "pass"
            and astra["token_excluding_internal_nonstream_reliable"]
            and hermes["token_reliable"]
        ):
            filtered_overlap_rows.append((astra, hermes))
    filtered_overlap = {}
    for system, index in (("astra", 0), ("hermes", 1)):
        selected = [pair[index] for pair in filtered_overlap_rows]
        keys = (
            {
                "input": "token_excluding_internal_nonstream_input",
                "output": "token_excluding_internal_nonstream_output",
                "total": "token_excluding_internal_nonstream_total",
            }
            if system == "astra"
            else {"input": "token_input", "output": "token_output", "total": "token_total"}
        )
        reliability_key = (
            "token_excluding_internal_nonstream_reliable"
            if system == "astra"
            else "token_reliable"
        )
        filtered_overlap[system] = {"n": len(selected)}
        for label, key in keys.items():
            filtered_overlap[system][label] = stats(
                numeric(selected, key, reliable=True, reliability_key=reliability_key)
            )

    astra_rows = [row for row in rows if row["system"] == "astra"]
    astra_full_reliable = [row for row in astra_rows if row["token_reliable"]]
    exclusion_effect = {
        "internal_nonstream_started": sum(
            row["internal_nonstream_requests"] for row in astra_rows
        ),
        "retained_started": sum(
            row["retained_requests_excluding_internal_nonstream"] for row in astra_rows
        ),
        "same_record_basis": len(astra_full_reliable),
    }
    for label, full_key, filtered_key in (
        ("input", "token_input", "token_excluding_internal_nonstream_input"),
        ("output", "token_output", "token_excluding_internal_nonstream_output"),
        ("total", "token_total", "token_excluding_internal_nonstream_total"),
    ):
        full_sum = sum(float(row[full_key]) for row in astra_full_reliable)
        filtered_sum = sum(float(row[filtered_key]) for row in astra_full_reliable)
        exclusion_effect[label] = {
            "full": full_sum,
            "filtered": filtered_sum,
            "excluded": full_sum - filtered_sum,
            "excluded_fraction": (full_sum - filtered_sum) / full_sum if full_sum else None,
        }

    return {
        "scope": {"tasks": 108, "slots": 216, "posthoc_supplement_slots": 11},
        "systems": systems,
        "pairs": dict(pairs),
        "pair_tasks": pair_tasks,
        "paired_differences_astra_minus_hermes": {
            key: stats(values) for key, values in paired_differences.items()
        },
        "overlapping_pass_tokens": overlap,
        "visible_token_lower_bound": {
            "definition": (
                "sum of all reported provider usage across every effective task; "
                "requests with missing usage remain unknown and contribute no inferred tokens"
            ),
            "systems": {
                system: {
                    "records": systems[system]["tokens"]["visible_lower_bound_records"],
                    "reported_completed_requests": sum(
                        row["token_usage_reported_completed"]
                        for row in rows
                        if row["system"] == system
                    ),
                    "missing_usage_completed_requests": sum(
                        row["token_usage_missing_completed"]
                        for row in rows
                        if row["system"] == system
                    ),
                    "input": systems[system]["tokens"]["visible_lower_bound_input"],
                    "output": systems[system]["tokens"]["visible_lower_bound_output"],
                    "total": systems[system]["tokens"]["visible_lower_bound_total"],
                    "pass_records": systems[system]["tokens"]["pass_visible_lower_bound_records"],
                    "pass_input": systems[system]["tokens"]["pass_visible_lower_bound_input"],
                    "pass_output": systems[system]["tokens"]["pass_visible_lower_bound_output"],
                    "pass_total": systems[system]["tokens"]["pass_visible_lower_bound_total"],
                }
                for system in SYSTEMS
            },
        },
        "tokens_excluding_astra_internal_nonstream": {
            "criterion": "Astra stream=false and request_tool_count=0; Hermes complete usage",
            "systems": filtered_tokens,
            "overlapping_pass_tokens": filtered_overlap,
            "astra_exclusion_effect_on_full_reliable_records": exclusion_effect,
        },
    }


def main() -> None:
    rows_by_key = m2_rows()
    rows_by_key.update(m3_rows())
    rows = apply_posthoc(rows_by_key)
    summary = summarize(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = OUT_DIR / "astra-hermes-toolathlon-108-task-results.csv"
    fields = sorted({key for row in rows for key in row})
    preferred = ["position", "task_id", "system", "verify_status", "run_validity", "terminal_status", "failure_category", "run_id", "source"]
    fields = preferred + [field for field in fields if field not in preferred]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with (OUT_DIR / "astra-hermes-toolathlon-108-task-summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
