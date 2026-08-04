#!/usr/bin/env python3
"""Build a reusable latest-attempt Astra C0 benchmark dataset.

The extractor intentionally keeps verifier outcome, timeout evidence, product
lifecycle, and telemetry completeness as separate dimensions.  It can scan
multiple work roots, globally selects the latest attempt for each task, then
excludes configured tasks and attempts without a numeric 0/1 verifier reward.

Only the Python standard library is required.  The code is compatible with the
system Python 3.9 shipped on the machine that produced the current artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


SCHEMA_VERSION = 4
DEFAULT_EXCLUDED_TASKS = {"tune-mjcf"}
BATCH_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2}$")
FALLBACK_TIMEOUT_RE = re.compile(
    r"LLM fallback request failed \(timeout\s+([0-9]+(?:\.[0-9]+)?)s\)",
    flags=re.IGNORECASE,
)
SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,128}$")
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

TRIAL_FIELDS = [
    # Selection and identity.
    "task_id",
    "attempt_count_for_task",
    "selected_source_root",
    "selected_run_dir",
    "selected_trial_name",
    "selected_trial_path",
    "selected_started_at",
    "selected_finished_at",
    # Verifier result and independent CTRF detail.
    "reward",
    "verify_status",
    "verify_reward_present",
    "ctrf_present",
    "verifier_tests",
    "verifier_passed",
    "verifier_failed",
    "verifier_skipped",
    "failed_test_names",
    "reward_ctrf_consistent",
    # Completion and lifecycle.
    "normal_e2e_pass",
    "clean_e2e_pass",
    "outcome_bucket",
    "harbor_exception",
    "harbor_exception_type",
    "harbor_exception_message",
    "product_terminal_status",
    "product_return_code",
    "product_completion_claim",
    "product_error_type",
    "astra_final_state",
    "astra_exit_code",
    "interruption_kind",
    "trajectory_capture_status",
    "trajectory_capture_failed",
    "trajectory_terminal_event",
    "formal_score_eligible",
    "evaluation_status",
    "lifecycle_gate_passed",
    "trigger_hit",
    # Timeout: observed signals and the separately-labelled deadline inference.
    "timeout",
    "timeout_or_deadline_suspected",
    "timeout_observed",
    "timeout_inferred",
    "timeout_types",
    "timeout_evidence",
    "llm_request_timeout",
    "llm_timeout_event_count",
    "stream_transport_interruption_count",
    "controller_deadline_suspected",
    "product_timeout",
    "verifier_timeout",
    "adapter_timeout",
    "configured_product_timeout_s",
    "configured_llm_fallback_timeout_s",
    "observed_llm_fallback_timeout_s",
    "observed_llm_fallback_timeout_values",
    # Outer retry state.
    "product_attempt_count",
    "stream_transport_retry_count",
    "stream_transport_recovered",
    "stream_transport_retry_exhausted",
    "stream_transport_retry_status",
    "stream_transport_failure_classification",
    "stream_transport_retry_skip_reason",
    # Time and cost-like resources.
    "e2e_s",
    "environment_setup_s",
    "agent_setup_s",
    "agent_execution_s",
    "verifier_s",
    "product_attempt_duration_sum_s",
    "llm_call_duration_sum_s",
    "cost_usd",
    # Tool telemetry.
    "agentic_steps",
    "tool_calls_started",
    "tool_calls_completed",
    "tool_calls_failed",
    "tool_calls_skipped",
    "tool_calls_terminal",
    "tool_calls_unpaired",
    "tool_terminal_orphan_count",
    "tool_terminal_coverage",
    "tool_call_failure_rate",
    "tool_call_duration_sum_s",
    "tool_duration_observed_calls",
    "tool_duration_coverage",
    "tool_breakdown",
    "failed_tool_breakdown",
    "tool_telemetry_status",
    "tool_telemetry_source",
    # Model activity and token accounting.
    "model_activity_observed",
    "llm_calls_with_input_usage",
    "journal_pipeline_feedback_count",
    "background_agent_result_count",
    "token_input",
    "token_fresh_input",
    "token_cache_read",
    "token_cache_creation",
    "token_output",
    "token_total",
    "token_known_minimum",
    "token_cache_share",
    "token_source",
    "token_detail_source",
    "token_accounting_scope",
    "token_accounting_status",
    "token_sources_consistent",
    "token_is_lower_bound",
    "token_retry_attempts_included",
    "token_reconciliation_delta",
    # Server-side MatrixOne usage lookup.  These are kept next to the local
    # artifacts so a future re-extraction remains auditable after retention.
    "token_server_status",
    "token_server_request_count",
    "token_server_input",
    "token_server_fresh_input",
    "token_server_cache_read",
    "token_server_cache_creation",
    "token_server_output",
    "token_server_total",
    "token_server_components_consistent",
    "token_server_local_trace_delta",
    # Raw token cross-checks.  These prevent a convenient derived value from
    # hiding disagreement among source artifacts.
    "token_trace_input",
    "token_stdout_input",
    "token_stdout_fresh_input",
    "token_stdout_cache_read",
    "token_stdout_cache_creation",
    "token_stdout_output",
    "token_journal_input",
    "token_journal_output",
    "token_pre_final_retry_input",
    "token_pre_final_retry_output",
    "token_reconstructed_input",
    "token_reconstructed_output",
    "token_harbor_input",
    "token_harbor_cache_read",
    "token_harbor_output",
]

ATTEMPT_FIELDS = [
    "task_id",
    "attempt_index_for_task",
    "attempt_count_for_task",
    "source_root",
    "run_dir",
    "trial_name",
    "trial_path",
    "started_at",
    "finished_at",
    "batch_timestamp",
    "latest_sort_key",
    "reward",
    "verify_status",
    "selected_latest",
    "selection_status",
    "selected_trial_path_for_task",
]

QUALITY_FIELDS = ["task_id", "severity", "issue_code", "detail", "trial_path"]


class ParseDiagnostics:
    """Accumulate parsing quality without turning missing optional files into 0."""

    def __init__(self) -> None:
        self.result_files_seen = 0
        self.non_trial_result_files = 0
        self.json_files_read = 0
        self.json_parse_errors: List[Tuple[str, str]] = []
        self.jsonl_files_read = 0
        self.jsonl_lines_read = 0
        self.jsonl_bad_lines = 0
        self.jsonl_parse_errors: List[Tuple[str, int]] = []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "result_files_seen": self.result_files_seen,
            "non_trial_result_files": self.non_trial_result_files,
            "json_files_read": self.json_files_read,
            "json_parse_error_count": len(self.json_parse_errors),
            "jsonl_files_read": self.jsonl_files_read,
            "jsonl_lines_read": self.jsonl_lines_read,
            "jsonl_bad_line_count": self.jsonl_bad_lines,
        }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    astra_all_root = script_dir.parents[1]
    rerun_root = astra_all_root.parent / "astra-c0-rerun-from-scratch-33" / "jobs"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=None,
        help=(
            "Work root to scan recursively; may be supplied more than once. "
            "If omitted, the Astra all-jobs and rerun jobs roots are used."
        ),
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
    parser.add_argument(
        "--matrixone-token-source",
        choices=("off", "auto", "required"),
        default="off",
        help=(
            "Query server-side session usage from MatrixOne through a temporary "
            "MySQL Docker client. off keeps local artifacts only; auto falls back "
            "to local data if MatrixOne is unavailable; required fails instead."
        ),
    )
    parser.add_argument(
        "--matrixone-container",
        default="all-in-one-matrixone-1",
        help="Running MatrixOne container whose network namespace is used by the temporary client.",
    )
    parser.add_argument(
        "--matrixone-mysql-image",
        default="mysql:8.4",
        help="MySQL client image used only for --matrixone-token-source.",
    )
    parser.add_argument("--matrixone-host", default="127.0.0.1")
    parser.add_argument("--matrixone-port", type=int, default=6001)
    parser.add_argument("--matrixone-user", default="root")
    parser.add_argument("--matrixone-database", default="astra_runtime")
    parser.add_argument(
        "--matrixone-password-env",
        default="MATRIXONE_PASSWORD",
        help="Environment variable holding the MatrixOne password; its value is never written to outputs.",
    )
    parser.add_argument(
        "--matrixone-query-timeout-s",
        type=int,
        default=60,
        help="Maximum wall-clock time for the temporary MySQL client query.",
    )
    args = parser.parse_args(argv)
    args.root = args.root if args.root is not None else [astra_all_root, rerun_root]
    return args


def number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def integer(value: Any) -> Optional[int]:
    value_number = number(value)
    if value_number is None or not value_number.is_integer():
        return None
    return int(value_number)


def numeric_reward(value: Any) -> Optional[int]:
    value_number = number(value)
    if value_number == 0.0:
        return 0
    if value_number == 1.0:
        return 1
    return None


def read_json(
    path: Path,
    diagnostics: ParseDiagnostics,
    warn: bool = False,
    empty_is_missing: bool = False,
) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    diagnostics.json_files_read += 1
    try:
        text = path.read_text(encoding="utf-8")
        if empty_is_missing and not text.strip():
            return None
        value = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        diagnostics.json_parse_errors.append((str(path.resolve()), str(exc)))
        if warn:
            print("warning: cannot parse JSON {}: {}".format(path, exc), file=sys.stderr)
        return None
    if not isinstance(value, dict):
        diagnostics.json_parse_errors.append(
            (str(path.resolve()), "top-level JSON value is not an object")
        )
        if warn:
            print("warning: JSON object expected: {}".format(path), file=sys.stderr)
        return None
    return value


def read_jsonl(
    path: Path, diagnostics: ParseDiagnostics
) -> Tuple[List[Dict[str, Any]], int]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows, 0
    diagnostics.jsonl_files_read += 1
    bad_lines = 0
    try:
        stream = path.open("r", encoding="utf-8", errors="replace")
    except OSError as exc:
        diagnostics.json_parse_errors.append((str(path.resolve()), str(exc)))
        return rows, 0
    with stream:
        for line in stream:
            diagnostics.jsonl_lines_read += 1
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            if isinstance(value, dict):
                rows.append(value)
            else:
                bad_lines += 1
    if bad_lines:
        diagnostics.jsonl_bad_lines += bad_lines
        diagnostics.jsonl_parse_errors.append((str(path.resolve()), bad_lines))
    return rows, bad_lines


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    # Python 3.9 rejects nanosecond fractions.  Truncate to microseconds while
    # preserving the timezone suffix.
    normalized = re.sub(
        r"(\.\d{6})\d+(?=Z$|[+-]\d{2}:\d{2}$)", r"\1", value.strip()
    ).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def seconds_between(value: Any) -> Optional[float]:
    if not isinstance(value, dict):
        return None
    start = parse_time(value.get("started_at"))
    finish = parse_time(value.get("finished_at"))
    if start is None or finish is None:
        return None
    try:
        return (finish - start).total_seconds()
    except TypeError:
        return None


def batch_ancestor(trial_dir: Path) -> Optional[Path]:
    for ancestor in trial_dir.parents:
        if BATCH_NAME_RE.fullmatch(ancestor.name):
            return ancestor
    return None


def latest_sort_key(
    batch_dir: Optional[Path], result: Dict[str, Any], result_path: Path
) -> Tuple[float, float, float, str]:
    primary = float("-inf")
    if batch_dir is not None:
        try:
            primary = (
                datetime.strptime(batch_dir.name, "%Y-%m-%d__%H-%M-%S")
                - datetime(1970, 1, 1)
            ).total_seconds()
        except ValueError:
            pass
    if primary == float("-inf"):
        fallback = parse_time(result.get("started_at")) or parse_time(
            result.get("finished_at")
        )
        if fallback is not None:
            try:
                primary = fallback.timestamp()
            except (OSError, ValueError):
                pass
    started = parse_time(result.get("started_at"))
    finished = parse_time(result.get("finished_at"))

    def timestamp(value: Optional[datetime]) -> float:
        if value is None:
            return float("-inf")
        try:
            return value.timestamp()
        except (OSError, ValueError):
            return float("-inf")

    return (primary, timestamp(started), timestamp(finished), str(result_path.resolve()))


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def discover_attempts(
    roots: Sequence[Path], diagnostics: ParseDiagnostics
) -> List[Dict[str, Any]]:
    attempts: List[Dict[str, Any]] = []
    seen_paths: Set[str] = set()
    for root in roots:
        for result_path in sorted(root.rglob("result.json")):
            resolved = str(result_path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            diagnostics.result_files_seen += 1
            result = read_json(result_path, diagnostics, warn=True)
            if result is None:
                continue
            task_name = result.get("task_name")
            if not isinstance(task_name, str) or not task_name:
                diagnostics.non_trial_result_files += 1
                continue
            agent_result = result.get("agent_result")
            agent_result = agent_result if isinstance(agent_result, dict) else {}
            metadata = agent_result.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            task_id = metadata.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                task_id = task_name.removeprefix("terminal-bench/")
            if not task_id:
                diagnostics.non_trial_result_files += 1
                continue
            trial_dir = result_path.parent
            batch_dir = batch_ancestor(trial_dir)
            verifier_result = result.get("verifier_result")
            verifier_result = (
                verifier_result if isinstance(verifier_result, dict) else {}
            )
            rewards = verifier_result.get("rewards")
            rewards = rewards if isinstance(rewards, dict) else {}
            reward_value = rewards.get("reward")
            reward = numeric_reward(reward_value)
            sort_key = latest_sort_key(batch_dir, result, result_path)
            attempts.append(
                {
                    "task_id": task_id,
                    "source_root": str(root.resolve()),
                    "run_dir": batch_dir.name if batch_dir is not None else trial_dir.parent.name,
                    "trial_name": result.get("trial_name") or trial_dir.name,
                    "trial_path": str(trial_dir.resolve()),
                    "result_path": str(result_path.resolve()),
                    "started_at": result.get("started_at"),
                    "finished_at": result.get("finished_at"),
                    "batch_timestamp": batch_dir.name if batch_dir is not None else None,
                    "reward": reward,
                    "verify_status": (
                        "pass" if reward == 1 else "no_pass" if reward == 0 else "missing"
                    ),
                    "_sort_key": sort_key,
                    "_result": result,
                    "_trial_dir": trial_dir,
                }
            )
    return attempts


def select_latest(
    attempts: List[Dict[str, Any]], excluded_tasks: Set[str]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for attempt in attempts:
        grouped.setdefault(str(attempt["task_id"]), []).append(attempt)

    latest: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []
    for task_id, task_attempts in grouped.items():
        ordered = sorted(task_attempts, key=lambda row: row["_sort_key"])
        selected = ordered[-1]
        selected["attempt_count_for_task"] = len(ordered)
        latest.append(selected)
        for index, attempt in enumerate(ordered, start=1):
            is_selected = attempt is selected
            if not is_selected:
                selection_status = "superseded_by_later_attempt"
            elif task_id in excluded_tasks:
                selection_status = "selected_excluded_task"
            elif attempt["reward"] is None:
                selection_status = "selected_without_numeric_verifier"
            else:
                selection_status = "selected_included"
            audit.append(
                {
                    "task_id": task_id,
                    "attempt_index_for_task": index,
                    "attempt_count_for_task": len(ordered),
                    "source_root": attempt["source_root"],
                    "run_dir": attempt["run_dir"],
                    "trial_name": attempt["trial_name"],
                    "trial_path": attempt["trial_path"],
                    "started_at": attempt["started_at"],
                    "finished_at": attempt["finished_at"],
                    "batch_timestamp": attempt["batch_timestamp"],
                    "latest_sort_key": compact_json(list(attempt["_sort_key"])),
                    "reward": attempt["reward"],
                    "verify_status": attempt["verify_status"],
                    "selected_latest": is_selected,
                    "selection_status": selection_status,
                    "selected_trial_path_for_task": selected["trial_path"],
                }
            )
    return (
        sorted(latest, key=lambda row: str(row["task_id"])),
        sorted(audit, key=lambda row: (str(row["task_id"]), int(row["attempt_index_for_task"]))),
    )


def verifier_summary(
    trial_dir: Path,
    reward: int,
    diagnostics: ParseDiagnostics,
) -> Dict[str, Any]:
    ctrf_path = trial_dir / "verifier" / "ctrf.json"
    ctrf = read_json(ctrf_path, diagnostics)
    results = ctrf.get("results") if ctrf else None
    results = results if isinstance(results, dict) else None
    summary = results.get("summary") if results else None
    tests = results.get("tests") if results else None
    summary = summary if isinstance(summary, dict) else None
    tests = tests if isinstance(tests, list) else []
    failed_names = [
        str(test.get("name"))
        for test in tests
        if isinstance(test, dict) and str(test.get("status") or "").lower() == "failed"
    ]
    total = integer(summary.get("tests")) if summary else None
    passed = integer(summary.get("passed")) if summary else None
    failed = integer(summary.get("failed")) if summary else None
    skipped = integer(summary.get("skipped")) if summary else None
    consistent: Optional[bool] = None
    if failed is not None:
        consistent = (reward == 1 and failed == 0) or (reward == 0 and failed > 0)
    return {
        "ctrf_present": ctrf is not None,
        "verifier_tests": total,
        "verifier_passed": passed,
        "verifier_failed": failed,
        "verifier_skipped": skipped,
        "failed_test_names": "; ".join(failed_names),
        "reward_ctrf_consistent": consistent,
    }


def session_artifact_paths(
    trial_dir: Path, session_id: Optional[str]
) -> Tuple[List[Path], List[Path]]:
    root = trial_dir / "agent" / "astra-trajectory" / "local-sessions"
    if not root.is_dir():
        return [], []
    journals = sorted(
        path
        for path in root.glob("**/sessions/*.jsonl")
        if path.name != "step_events.jsonl"
    )
    step_paths = sorted(root.glob("**/sessions/*/step_events.jsonl"))
    if session_id:
        exact_journals = [path for path in journals if path.stem == session_id]
        exact_steps = [path for path in step_paths if path.parent.name == session_id]
        if exact_journals:
            journals = exact_journals
        if exact_steps:
            step_paths = exact_steps
    # A trial should have one Astra session.  If no exact session match is
    # available, combining all exported session files is safer than silently
    # discarding activity, and the telemetry status will remain auditable.
    return journals, step_paths


def dedupe_rows(rows: Iterable[Dict[str, Any]], key_field: str) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    result: List[Dict[str, Any]] = []
    for row in rows:
        value = row.get(key_field)
        key = str(value) if value else compact_json(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def load_local_session(
    trial_dir: Path,
    session_id: Optional[str],
    diagnostics: ParseDiagnostics,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int, List[Path], List[Path]]:
    journal_paths, step_paths = session_artifact_paths(trial_dir, session_id)
    journal_rows: List[Dict[str, Any]] = []
    step_rows: List[Dict[str, Any]] = []
    journal_bad = 0
    step_bad = 0
    for path in journal_paths:
        rows, bad = read_jsonl(path, diagnostics)
        journal_rows.extend(rows)
        journal_bad += bad
    for path in step_paths:
        rows, bad = read_jsonl(path, diagnostics)
        step_rows.extend(rows)
        step_bad += bad
    journal_rows = dedupe_rows(journal_rows, "event_id")
    # Step ids live in the nested payload envelope.
    seen_step_ids: Set[str] = set()
    deduped_steps: List[Dict[str, Any]] = []
    for row in step_rows:
        envelope = row.get("payload")
        envelope = envelope if isinstance(envelope, dict) else {}
        event_id = envelope.get("event_id")
        key = str(event_id) if event_id else compact_json(row)
        if key in seen_step_ids:
            continue
        seen_step_ids.add(key)
        deduped_steps.append(row)
    return journal_rows, deduped_steps, journal_bad, step_bad, journal_paths, step_paths


def extract_tools(
    step_rows: List[Dict[str, Any]], step_paths: List[Path], step_bad_lines: int
) -> Dict[str, Any]:
    started: Dict[str, Dict[str, Any]] = {}
    terminal: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    agentic_steps = 0
    anonymous_counter = 0
    for row in step_rows:
        envelope = row.get("payload")
        if not isinstance(envelope, dict):
            continue
        event_type = envelope.get("event_type")
        payload = envelope.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if event_type == "StepStarted":
            agentic_steps += 1
            continue
        if event_type not in {
            "ToolCallStarted",
            "ToolCallCompleted",
            "ToolCallFailed",
            "ToolCallSkipped",
        }:
            continue
        call_id = payload.get("call_id") or payload.get("tool_call_id")
        if not call_id:
            anonymous_counter += 1
            call_id = "anonymous:{}:{}".format(event_type, anonymous_counter)
        call_key = str(call_id)
        if event_type == "ToolCallStarted":
            started[call_key] = payload
        else:
            terminal[call_key] = (str(event_type), payload)

    terminal_counts = Counter(event_type for event_type, _ in terminal.values())
    tool_counts: Counter[str] = Counter()
    failed_counts: Counter[str] = Counter()
    duration_sum = 0.0
    duration_count = 0
    for call_key, payload in started.items():
        name = payload.get("tool_name")
        if isinstance(name, str) and name:
            tool_counts[name] += 1
    for event_type, payload in terminal.values():
        name = payload.get("tool_name")
        if event_type == "ToolCallFailed" and isinstance(name, str) and name:
            failed_counts[name] += 1
        elapsed_ms = number(payload.get("elapsed_ms"))
        if elapsed_ms is not None:
            duration_sum += elapsed_ms / 1000.0
            duration_count += 1

    started_count = len(started)
    terminal_count = len(terminal)
    completed_count = terminal_counts["ToolCallCompleted"]
    failed_count = terminal_counts["ToolCallFailed"]
    skipped_count = terminal_counts["ToolCallSkipped"]
    started_keys = set(started)
    terminal_keys = set(terminal)
    unpaired_count = len(started_keys - terminal_keys)
    orphan_count = len(terminal_keys - started_keys)
    terminal_coverage = (
        terminal_count / started_count if started_count else (1.0 if step_paths else None)
    )
    failure_denominator = completed_count + failed_count
    failure_rate = (
        failed_count / failure_denominator
        if failure_denominator
        else (0.0 if step_paths else None)
    )
    duration_coverage = (
        duration_count / terminal_count if terminal_count else (1.0 if step_paths else None)
    )
    if not step_paths:
        telemetry_status = "missing"
    elif step_bad_lines or unpaired_count or orphan_count:
        telemetry_status = "ledger_partial"
    else:
        telemetry_status = "ledger_internally_complete"
    return {
        "agentic_steps": agentic_steps if step_paths else None,
        "tool_calls_started": started_count if step_paths else None,
        "tool_calls_completed": completed_count if step_paths else None,
        "tool_calls_failed": failed_count if step_paths else None,
        "tool_calls_skipped": skipped_count if step_paths else None,
        "tool_calls_terminal": terminal_count if step_paths else None,
        "tool_calls_unpaired": unpaired_count if step_paths else None,
        "tool_terminal_orphan_count": orphan_count if step_paths else None,
        "tool_terminal_coverage": terminal_coverage,
        "tool_call_failure_rate": failure_rate,
        "tool_call_duration_sum_s": duration_sum if step_paths else None,
        "tool_duration_observed_calls": duration_count if step_paths else None,
        "tool_duration_coverage": duration_coverage,
        "tool_breakdown": compact_json(dict(sorted(tool_counts.items()))),
        "failed_tool_breakdown": compact_json(dict(sorted(failed_counts.items()))),
        "tool_telemetry_status": telemetry_status,
        "tool_telemetry_source": (
            ";".join(str(path.resolve()) for path in step_paths) if step_paths else "missing"
        ),
    }


def feedback_rows(journal_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    feedback: List[Dict[str, Any]] = []
    for row in journal_rows:
        if row.get("type") != "pipeline_feedback":
            continue
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            continue
        key = compact_json(
            {
                "ts": row.get("ts"),
                "turn": row.get("turn"),
                "metadata": metadata,
            }
        )
        if key in seen:
            continue
        seen.add(key)
        feedback.append(row)
    return feedback


def sum_feedback(
    rows: List[Dict[str, Any]], before: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    for row in rows:
        if before is not None:
            timestamp = parse_time(row.get("ts"))
            if timestamp is None:
                continue
            try:
                if timestamp >= before:
                    continue
            except TypeError:
                continue
        selected.append(row)
    if not selected:
        return None
    fresh = cache_read = cache_creation = output = 0
    complete = True
    for row in selected:
        metadata = row.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        values = [
            integer(metadata.get("prompt_tokens")),
            integer(metadata.get("cache_read_tokens")),
            integer(metadata.get("cache_creation_tokens")),
            integer(metadata.get("completion_tokens")),
        ]
        if any(value is None for value in values):
            complete = False
            continue
        fresh += int(values[0])
        cache_read += int(values[1])
        cache_creation += int(values[2])
        output += int(values[3])
    return {
        "count": len(selected),
        "complete": complete,
        "fresh": fresh if complete else None,
        "cache_read": cache_read if complete else None,
        "cache_creation": cache_creation if complete else None,
        "input": fresh + cache_read + cache_creation if complete else None,
        "output": output if complete else None,
    }


def stdout_usage(stdout: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not stdout:
        return None
    cache = stdout.get("cache")
    cache = cache if isinstance(cache, dict) else {}
    input_tokens = integer(stdout.get("prompt_tokens"))
    fresh = integer(stdout.get("fresh_prompt_tokens"))
    cache_read = integer(cache.get("read_tokens"))
    cache_creation = integer(cache.get("creation_tokens"))
    output = integer(stdout.get("completion_tokens"))
    if all(
        value is None
        for value in (input_tokens, fresh, cache_read, cache_creation, output)
    ):
        return None
    components_consistent: Optional[bool] = None
    if None not in (input_tokens, fresh, cache_read, cache_creation):
        components_consistent = input_tokens == fresh + cache_read + cache_creation
    return {
        "input": input_tokens,
        "fresh": fresh,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "output": output,
        "components_consistent": components_consistent,
    }


def context_trace_usage(
    trial_dir: Path,
    session_id: Optional[str],
    diagnostics: ParseDiagnostics,
) -> Dict[str, Any]:
    path = trial_dir / "agent" / "astra-trajectory" / "server-events.jsonl"
    rows, bad_lines = read_jsonl(path, diagnostics)
    seen: Set[str] = set()
    input_total = 0
    input_count = 0
    llm_duration_sum = 0.0
    llm_duration_count = 0
    foreign_session_events_ignored = 0
    for row in rows:
        if row.get("event_type") != "context_trace_signal":
            continue
        row_session_id = row.get("session_id")
        if session_id and row_session_id and row_session_id != session_id:
            foreign_session_events_ignored += 1
            continue
        event_id = row.get("event_id")
        key = str(event_id) if event_id else compact_json(row)
        if key in seen:
            continue
        seen.add(key)
        metadata = row.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        budget = metadata.get("budget")
        budget = budget if isinstance(budget, dict) else {}
        value = integer(budget.get("total_used"))
        if value is not None:
            input_total += value
            input_count += 1
        timing = metadata.get("timing")
        timing = timing if isinstance(timing, dict) else {}
        duration_ms = number(timing.get("llm_total_ms"))
        if duration_ms is not None:
            llm_duration_sum += duration_ms / 1000.0
            llm_duration_count += 1
    return {
        "input": input_total if input_count else None,
        "call_count": input_count,
        "llm_duration_sum_s": llm_duration_sum if llm_duration_count else None,
        "llm_duration_count": llm_duration_count,
        "path_present": path.is_file(),
        "bad_lines": bad_lines,
        "foreign_session_events_ignored": foreign_session_events_ignored,
    }


def retry_summary(
    trial_dir: Path,
    metadata: Dict[str, Any],
    agent_execution_s: Optional[float],
    stdout: Dict[str, Any],
    diagnostics: ParseDiagnostics,
) -> Dict[str, Any]:
    report = read_json(trial_dir / "agent" / "stream-transport-retry.json", diagnostics) or {}
    attempts = report.get("attempts")
    attempts = attempts if isinstance(attempts, list) else []
    durations = [
        number(attempt.get("duration_seconds"))
        for attempt in attempts
        if isinstance(attempt, dict)
    ]
    clean_durations = [value for value in durations if value is not None]
    final_start: Optional[datetime] = None
    final_attempt_index: Optional[int] = None
    if stdout:
        for index, attempt in reversed(list(enumerate(attempts))):
            if not isinstance(attempt, dict):
                continue
            if attempt.get("return_code") == 0 or (number(attempt.get("stdout_bytes")) or 0) > 0:
                final_start = parse_time(attempt.get("started_at_utc"))
                final_attempt_index = index
                break

    running_attempt = any(
        isinstance(attempt, dict) and attempt.get("status") == "running"
        for attempt in attempts
    )
    report_incomplete = bool(
        report
        and (
            report.get("complete") is False
            or report.get("status") == "attempt_running"
            or report.get("failure_classification") == "attempt_in_progress"
        )
    )
    configured_deadline = number(
        metadata.get("configured_product_timeout_sec")
        or metadata.get("product_timeout_sec")
        or report.get("overall_deadline_seconds")
    )
    near_deadline = bool(
        configured_deadline is not None
        and agent_execution_s is not None
        and agent_execution_s >= 0.95 * configured_deadline
    )
    controller_deadline_suspected = bool(
        report_incomplete and running_attempt and near_deadline
    )
    return {
        "report": report,
        "attempts": attempts,
        "attempt_count": integer(report.get("attempt_count")) if report else None,
        "retry_count": integer(report.get("retry_count")) if report else None,
        "duration_sum_s": sum(clean_durations) if clean_durations else None,
        "recovered": report.get("recovered") if report else None,
        "exhausted": report.get("exhausted") if report else None,
        "status": report.get("status") if report else None,
        "failure_classification": (
            report.get("failure_classification")
            if report
            else metadata.get("stream_transport_failure_classification")
        ),
        "skip_reason": report.get("retry_skip_reason") if report else None,
        "final_start": final_start,
        "final_attempt_index": final_attempt_index,
        "report_incomplete": report_incomplete,
        "controller_deadline_suspected": controller_deadline_suspected,
        "configured_deadline": configured_deadline,
    }


def attempt_session_id(attempt: Dict[str, Any]) -> Optional[str]:
    """Return a safe Astra session id from a discovered attempt."""
    result = attempt.get("_result")
    result = result if isinstance(result, dict) else {}
    agent_result = result.get("agent_result")
    agent_result = agent_result if isinstance(agent_result, dict) else {}
    metadata = agent_result.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    session_id = metadata.get("astra_session_id")
    if isinstance(session_id, str) and SAFE_SESSION_ID_RE.fullmatch(session_id):
        return session_id
    return None


def mysql_integer(value: str) -> Optional[int]:
    """Parse a nullable integer returned by mysql --batch --raw."""
    if value in ("", "NULL", "\\N"):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def matrixone_session_usage(
    session_ids: Iterable[Optional[str]], args: argparse.Namespace
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Aggregate persisted LLM responses per Astra session, without writes.

    The invocation intentionally uses a short-lived mysql container in the
    MatrixOne container's network namespace.  The password is passed only via
    MYSQL_PWD in the child environment, never in SQL, command arguments, or
    generated artifacts.
    """
    mode = args.matrixone_token_source
    requested = sorted(
        {
            session_id
            for session_id in session_ids
            if isinstance(session_id, str) and SAFE_SESSION_ID_RE.fullmatch(session_id)
        }
    )
    metadata: Dict[str, Any] = {
        "mode": mode,
        "status": "not_queried",
        "requested_session_count": len(requested),
        "found_session_count": 0,
        "database": args.matrixone_database,
        "table": "agent_events",
        "event_type": "llm_response",
    }
    if mode == "off":
        return {}, metadata
    if not requested:
        metadata["status"] = "no_valid_session_ids"
        return {}, metadata
    password = os.environ.get(args.matrixone_password_env)
    if not password:
        metadata["status"] = "password_not_configured"
        if mode == "required":
            raise SystemExit(
                "MatrixOne token lookup requires environment variable {}".format(
                    args.matrixone_password_env
                )
            )
        return {}, metadata
    if not SAFE_IDENTIFIER_RE.fullmatch(args.matrixone_database):
        raise SystemExit("Invalid MatrixOne database identifier")
    if args.matrixone_port <= 0 or args.matrixone_query_timeout_s <= 0:
        raise SystemExit("MatrixOne port and query timeout must be positive")

    quoted_ids = ", ".join("'{}'".format(session_id) for session_id in requested)
    sql = """
SELECT session_id,
       COUNT(*) AS response_count,
       SUM(token_input) AS input_tokens,
       SUM(token_output) AS output_tokens,
       SUM(token_total) AS total_tokens,
       SUM(JSON_EXTRACT(token_usage, '$.input_tokens') IS NOT NULL) AS fresh_count,
       SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(token_usage, '$.input_tokens')) AS SIGNED)) AS fresh_input_tokens,
       SUM(JSON_EXTRACT(token_usage, '$.cache_read') IS NOT NULL) AS cache_read_count,
       SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(token_usage, '$.cache_read')) AS SIGNED)) AS cache_read_tokens,
       SUM(JSON_EXTRACT(token_usage, '$.cache_creation_tokens') IS NOT NULL) AS cache_creation_count,
       SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(token_usage, '$.cache_creation_tokens')) AS SIGNED)) AS cache_creation_tokens
FROM `{database}`.agent_events
WHERE event_type = 'llm_response'
  AND token_input IS NOT NULL
  AND session_id IN ({session_ids})
GROUP BY session_id
ORDER BY session_id
""".format(database=args.matrixone_database, session_ids=quoted_ids)
    command = [
        "docker",
        "run",
        "--rm",
        "--network=container:{}".format(args.matrixone_container),
        "-e",
        "MYSQL_PWD",
        args.matrixone_mysql_image,
        "mysql",
        "-h",
        args.matrixone_host,
        "-P",
        str(args.matrixone_port),
        "-u",
        args.matrixone_user,
        "--batch",
        "--raw",
        "--skip-column-names",
        "-D",
        args.matrixone_database,
        "-e",
        sql,
    ]
    environment = dict(os.environ)
    environment["MYSQL_PWD"] = password
    try:
        result = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.matrixone_query_timeout_s,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        metadata["status"] = "query_failed"
        metadata["error_kind"] = type(exc).__name__
        if mode == "required":
            raise SystemExit("MatrixOne token lookup failed: {}".format(type(exc).__name__))
        return {}, metadata
    if result.returncode != 0:
        metadata["status"] = "query_failed"
        metadata["return_code"] = result.returncode
        if mode == "required":
            raise SystemExit("MatrixOne token lookup failed (mysql client exit {})".format(result.returncode))
        return {}, metadata

    usage: Dict[str, Dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 11 or not SAFE_SESSION_ID_RE.fullmatch(fields[0]):
            continue
        numbers = [mysql_integer(value) for value in fields[1:]]
        request_count, input_tokens, output_tokens, total_tokens = numbers[:4]
        fresh_count, fresh_tokens, cache_read_count, cache_read_tokens = numbers[4:8]
        cache_creation_count, cache_creation_tokens = numbers[8:]
        if request_count is None or input_tokens is None:
            continue
        detail_complete = all(
            count == request_count
            for count in (fresh_count, cache_read_count, cache_creation_count)
        )
        components_consistent = bool(
            detail_complete
            and None not in (fresh_tokens, cache_read_tokens, cache_creation_tokens)
            and input_tokens == fresh_tokens + cache_read_tokens + cache_creation_tokens
        )
        total_consistent = bool(
            output_tokens is not None
            and total_tokens is not None
            and total_tokens == input_tokens + output_tokens
        )
        usage[fields[0]] = {
            "request_count": request_count,
            "input": input_tokens,
            "fresh": fresh_tokens,
            "cache_read": cache_read_tokens,
            "cache_creation": cache_creation_tokens,
            "output": output_tokens,
            "total": total_tokens,
            "detail_complete": detail_complete,
            "components_consistent": components_consistent,
            "total_consistent": total_consistent,
        }
    metadata["status"] = "queried"
    metadata["found_session_count"] = len(usage)
    return usage, metadata


def token_accounting(
    trace: Dict[str, Any],
    stdout: Dict[str, Any],
    journal_rows: List[Dict[str, Any]],
    retry: Dict[str, Any],
    agent_result: Dict[str, Any],
    llm_request_timeout: bool,
    model_activity_observed: bool,
    journal_telemetry_present: bool = True,
    matrixone_usage: Optional[Dict[str, Any]] = None,
    matrixone_query_status: str = "not_queried",
) -> Dict[str, Any]:
    feedback = feedback_rows(journal_rows)
    journal_all = sum_feedback(feedback)
    journal_pre_final = (
        sum_feedback(feedback, before=retry.get("final_start"))
        if retry.get("final_start") is not None
        else None
    )
    stdout_values = stdout_usage(stdout)
    trace_input = trace.get("input")

    reconstructed: Optional[Dict[str, Any]] = None
    detail_source = "missing"
    retry_attempts_included = 0
    if stdout_values is not None:
        reconstructed = dict(stdout_values)
        detail_source = "astra.stdout.json"
        if retry.get("final_start") is not None and journal_pre_final is not None:
            if all(
                reconstructed.get(field) is not None
                for field in ("input", "fresh", "cache_read", "cache_creation", "output")
            ) and reconstructed.get("components_consistent") is not False and journal_pre_final.get("complete"):
                reconstructed = {
                    "input": int(reconstructed["input"]) + int(journal_pre_final["input"]),
                    "fresh": int(reconstructed["fresh"]) + int(journal_pre_final["fresh"]),
                    "cache_read": int(reconstructed["cache_read"])
                    + int(journal_pre_final["cache_read"]),
                    "cache_creation": int(reconstructed["cache_creation"])
                    + int(journal_pre_final["cache_creation"]),
                    "output": int(reconstructed["output"]) + int(journal_pre_final["output"]),
                    "components_consistent": True,
                }
                detail_source = "astra.stdout.json+pre-final-retry-pipeline_feedback"
                retry_attempts_included = int(retry.get("final_attempt_index") or 0)
    elif journal_all is not None and journal_all.get("complete"):
        reconstructed = {
            "input": journal_all["input"],
            "fresh": journal_all["fresh"],
            "cache_read": journal_all["cache_read"],
            "cache_creation": journal_all["cache_creation"],
            "output": journal_all["output"],
            "components_consistent": True,
        }
        detail_source = "local-session.pipeline_feedback"
        retry_attempts_included = int(retry.get("retry_count") or 0)

    reconstructed_input = reconstructed.get("input") if reconstructed else None
    reconstructed_output = reconstructed.get("output") if reconstructed else None
    sources_consistent: Optional[bool] = None
    reconciliation_delta: Optional[int] = None
    if trace_input is not None and reconstructed_input is not None:
        sources_consistent = trace_input == reconstructed_input
        reconciliation_delta = int(reconstructed_input) - int(trace_input)
    elif trace_input is None and stdout_values is not None and journal_all is not None:
        if stdout_values.get("input") is not None and journal_all.get("input") is not None:
            sources_consistent = stdout_values["input"] == journal_all["input"]

    canonical_input: Optional[int]
    fresh: Optional[int] = None
    cache_read: Optional[int] = None
    cache_creation: Optional[int] = None
    output: Optional[int] = None
    total: Optional[int] = None
    if trace_input is not None:
        canonical_input = int(trace_input)
        if reconstructed is None:
            status = "session_input_only"
            source = "server-context-trace"
            scope = "session_input_only"
        elif sources_consistent and reconstructed.get("components_consistent") is not False:
            fresh = integer(reconstructed.get("fresh"))
            cache_read = integer(reconstructed.get("cache_read"))
            cache_creation = integer(reconstructed.get("cache_creation"))
            output = integer(reconstructed.get("output"))
            if None not in (fresh, cache_read, cache_creation, output):
                total = canonical_input + int(output)
                status = "session_reconciled"
            else:
                status = "session_input_only"
            source = "server-context-trace+reconciled-details"
            scope = "session_wide_observed"
        elif sources_consistent:
            status = "session_component_mismatch"
            source = "server-context-trace"
            scope = "session_input_only"
        else:
            status = "session_source_mismatch"
            source = "server-context-trace"
            scope = "session_input_only"
    elif reconstructed is not None and reconstructed_input is not None:
        canonical_input = int(reconstructed_input)
        if reconstructed.get("components_consistent") is False:
            status = "component_mismatch_no_trace"
        else:
            fresh = integer(reconstructed.get("fresh"))
            cache_read = integer(reconstructed.get("cache_read"))
            cache_creation = integer(reconstructed.get("cache_creation"))
            output = integer(reconstructed.get("output"))
            if None not in (fresh, cache_read, cache_creation, output):
                total = canonical_input + int(output)
            if stdout_values is not None and journal_all is not None and sources_consistent:
                status = "complete_no_trace_crosscheck"
            elif stdout_values is not None:
                status = "complete_terminal_no_trace"
            else:
                status = "journal_observed_no_trace"
        source = detail_source
        scope = "session_observed_no_context_trace"
    else:
        canonical_input = None
        status = (
            "missing_after_model_activity" if model_activity_observed else "missing_no_activity"
        )
        source = "missing"
        scope = "missing"

    # MatrixOne persists one row for every returned provider response.  When a
    # session is still retained there, it is more complete than artifacts
    # written by the final CLI invocation and so becomes the canonical source.
    server_status = (
        "queried_found" if matrixone_usage is not None
        else ("queried_not_found" if matrixone_query_status == "queried" else matrixone_query_status)
    )
    server_input: Optional[int] = None
    server_fresh: Optional[int] = None
    server_cache_read: Optional[int] = None
    server_cache_creation: Optional[int] = None
    server_output: Optional[int] = None
    server_total: Optional[int] = None
    server_request_count: Optional[int] = None
    server_components_consistent: Optional[bool] = None
    server_local_trace_delta: Optional[int] = None
    if matrixone_usage is not None:
        server_input = integer(matrixone_usage.get("input"))
        server_fresh = integer(matrixone_usage.get("fresh"))
        server_cache_read = integer(matrixone_usage.get("cache_read"))
        server_cache_creation = integer(matrixone_usage.get("cache_creation"))
        server_output = integer(matrixone_usage.get("output"))
        server_total = integer(matrixone_usage.get("total"))
        server_request_count = integer(matrixone_usage.get("request_count"))
        server_components_consistent = bool(matrixone_usage.get("components_consistent"))
        if server_input is not None and trace_input is not None:
            server_local_trace_delta = server_input - int(trace_input)
        if server_input is not None:
            canonical_input = server_input
            source = "matrixone.agent_events.llm_response"
            scope = "server_session_observed"
            retry_attempts_included = int(retry.get("retry_count") or 0)
            if server_components_consistent and matrixone_usage.get("total_consistent"):
                fresh = server_fresh
                cache_read = server_cache_read
                cache_creation = server_cache_creation
                output = server_output
                total = server_total
                status = "server_reconciled"
            elif matrixone_usage.get("total_consistent"):
                output = server_output
                total = server_total
                status = "server_input_output_only"
            else:
                status = "server_input_only"

    known_minimum: Optional[int] = canonical_input
    if canonical_input is not None and output is not None:
        known_minimum = canonical_input + output
    cache_share = (
        cache_read / canonical_input
        if cache_read is not None and canonical_input not in (None, 0)
        else None
    )
    incomplete_status = status not in {
        "session_reconciled",
        "complete_no_trace_crosscheck",
        "complete_terminal_no_trace",
        "journal_observed_no_trace",
        "server_reconciled",
        "server_input_output_only",
    }
    is_lower_bound = bool(llm_request_timeout or incomplete_status)
    return {
        "model_activity_observed": model_activity_observed,
        "llm_calls_with_input_usage": (
            trace.get("call_count") if trace.get("path_present") else None
        ),
        "journal_pipeline_feedback_count": (
            len(feedback) if journal_telemetry_present else None
        ),
        "background_agent_result_count": (
            len(stdout.get("background_agent_results"))
            if isinstance(stdout.get("background_agent_results"), list)
            else None
        ),
        "token_input": canonical_input,
        "token_fresh_input": fresh,
        "token_cache_read": cache_read,
        "token_cache_creation": cache_creation,
        "token_output": output,
        "token_total": total,
        "token_known_minimum": known_minimum,
        "token_cache_share": cache_share,
        "token_source": source,
        "token_detail_source": detail_source,
        "token_accounting_scope": scope,
        "token_accounting_status": status,
        "token_sources_consistent": (
            server_components_consistent if matrixone_usage is not None else sources_consistent
        ),
        "token_is_lower_bound": is_lower_bound,
        "token_retry_attempts_included": retry_attempts_included,
        "token_reconciliation_delta": reconciliation_delta,
        "token_server_status": server_status,
        "token_server_request_count": server_request_count,
        "token_server_input": server_input,
        "token_server_fresh_input": server_fresh,
        "token_server_cache_read": server_cache_read,
        "token_server_cache_creation": server_cache_creation,
        "token_server_output": server_output,
        "token_server_total": server_total,
        "token_server_components_consistent": server_components_consistent,
        "token_server_local_trace_delta": server_local_trace_delta,
        "token_trace_input": trace_input,
        "token_stdout_input": stdout_values.get("input") if stdout_values else None,
        "token_stdout_fresh_input": stdout_values.get("fresh") if stdout_values else None,
        "token_stdout_cache_read": stdout_values.get("cache_read") if stdout_values else None,
        "token_stdout_cache_creation": (
            stdout_values.get("cache_creation") if stdout_values else None
        ),
        "token_stdout_output": stdout_values.get("output") if stdout_values else None,
        "token_journal_input": journal_all.get("input") if journal_all else None,
        "token_journal_output": journal_all.get("output") if journal_all else None,
        "token_pre_final_retry_input": (
            journal_pre_final.get("input") if journal_pre_final else None
        ),
        "token_pre_final_retry_output": (
            journal_pre_final.get("output") if journal_pre_final else None
        ),
        "token_reconstructed_input": reconstructed_input,
        "token_reconstructed_output": reconstructed_output,
        "token_harbor_input": integer(agent_result.get("n_input_tokens")),
        "token_harbor_cache_read": integer(agent_result.get("n_cache_tokens")),
        "token_harbor_output": integer(agent_result.get("n_output_tokens")),
    }


def timeout_summary(
    trial_dir: Path,
    result: Dict[str, Any],
    metadata: Dict[str, Any],
    journal_rows: List[Dict[str, Any]],
    retry: Dict[str, Any],
) -> Dict[str, Any]:
    interruption_count = 0
    llm_timeout_count = 0
    timeout_values: Set[float] = set()
    evidence: List[str] = []
    interruption_kinds: List[str] = []
    for row in journal_rows:
        if row.get("type") != "interruption_recorded":
            continue
        row_metadata = row.get("metadata")
        row_metadata = row_metadata if isinstance(row_metadata, dict) else {}
        interruption = row_metadata.get("interruption")
        interruption = interruption if isinstance(interruption, dict) else {}
        kind = interruption.get("kind")
        if isinstance(kind, str) and kind:
            interruption_kinds.append(kind)
        if kind != "stream_transport":
            continue
        interruption_count += 1
        detail = str(interruption.get("error_detail") or "")
        matches = FALLBACK_TIMEOUT_RE.findall(detail)
        if matches:
            llm_timeout_count += 1
            timeout_values.update(float(value) for value in matches)
            evidence.append("journal stream_transport: {}".format(detail[:500]))

    stderr_text = "\n".join(
        read_text(trial_dir / "agent" / name)
        for name in ("adapter-exec.stderr.txt", "astra.stderr.txt")
    )
    stderr_matches = FALLBACK_TIMEOUT_RE.findall(stderr_text)
    if stderr_matches:
        timeout_values.update(float(value) for value in stderr_matches)
        if llm_timeout_count == 0:
            llm_timeout_count = 1
        evidence.append("stderr contains explicit LLM fallback request timeout")

    exception = result.get("exception_info")
    exception = exception if isinstance(exception, dict) else {}
    exception_type = str(exception.get("exception_type") or "")
    exception_message = str(exception.get("exception_message") or "")
    product_status = str(metadata.get("product_terminal_status") or "unknown")
    product_error_type = str(metadata.get("product_error_type") or "")
    product_timeout = bool(
        product_status.lower() == "timeout"
        or "timeout" in product_error_type.lower()
    )
    verifier_timeout = bool(
        "verifiertimeout" in exception_type.lower()
        or ("verifier" in exception_message.lower() and "timed out" in exception_message.lower())
    )
    adapter_timeout = bool(
        not verifier_timeout
        and (
            "timeout" in exception_type.lower()
            or "timed out" in exception_message.lower()
        )
    )
    llm_request_timeout = llm_timeout_count > 0
    controller_suspected = bool(retry.get("controller_deadline_suspected"))
    observed = llm_request_timeout or product_timeout or verifier_timeout or adapter_timeout
    inferred = controller_suspected
    timeout_any = observed or inferred
    types: List[str] = []
    if llm_request_timeout:
        types.append("llm_request_timeout")
    if controller_suspected:
        types.append("controller_deadline_suspected")
        evidence.append(
            "retry report remained attempt_running/incomplete and agent duration reached configured product deadline"
        )
    if product_timeout:
        types.append("product_timeout")
        evidence.append("product terminal status/error type explicitly indicates timeout")
    if verifier_timeout:
        types.append("verifier_timeout")
        evidence.append("Harbor verifier exception explicitly indicates timeout")
    if adapter_timeout:
        types.append("adapter_timeout")
        evidence.append("Harbor non-verifier exception explicitly indicates timeout")
    sorted_values = sorted(timeout_values)
    return {
        "timeout": timeout_any,
        "timeout_or_deadline_suspected": timeout_any,
        "timeout_observed": observed,
        "timeout_inferred": inferred,
        "timeout_types": compact_json(types),
        "timeout_evidence": compact_json(list(dict.fromkeys(evidence))),
        "llm_request_timeout": llm_request_timeout,
        "llm_timeout_event_count": llm_timeout_count,
        "stream_transport_interruption_count": interruption_count,
        "controller_deadline_suspected": controller_suspected,
        "product_timeout": product_timeout,
        "verifier_timeout": verifier_timeout,
        "adapter_timeout": adapter_timeout,
        "configured_product_timeout_s": retry.get("configured_deadline"),
        "configured_llm_fallback_timeout_s": number(
            metadata.get("llm_fallback_timeout_sec")
        ),
        "observed_llm_fallback_timeout_s": (
            sorted_values[0] if len(sorted_values) == 1 else None
        ),
        "observed_llm_fallback_timeout_values": compact_json(sorted_values),
        "interruption_kind": ";".join(sorted(set(interruption_kinds))),
    }


def derive_outcome_bucket(row: Dict[str, Any]) -> str:
    if row["verify_status"] == "pass":
        if row["timeout_observed"]:
            return "verifier_pass_after_timeout"
        if row["controller_deadline_suspected"]:
            return "verifier_pass_with_deadline_suspected"
        if row["normal_e2e_pass"]:
            return "normal_e2e_pass"
        return "verifier_pass_with_abnormal_lifecycle"
    if row["timeout_observed"]:
        return "timeout_no_pass"
    if row["controller_deadline_suspected"]:
        return "deadline_suspected_no_pass"
    if row["product_terminal_status"] == "completed":
        return "completed_no_pass"
    return "failed_no_pass"


def extract_trial(
    attempt: Dict[str, Any],
    diagnostics: ParseDiagnostics,
    matrixone_usage: Optional[Dict[str, Any]] = None,
    matrixone_query_status: str = "not_queried",
) -> Dict[str, Any]:
    result = attempt["_result"]
    trial_dir = attempt["_trial_dir"]
    reward = int(attempt["reward"])
    agent_result = result.get("agent_result")
    agent_result = agent_result if isinstance(agent_result, dict) else {}
    metadata = agent_result.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    session_id = metadata.get("astra_session_id")
    session_id = session_id if isinstance(session_id, str) else None

    # An empty stdout file is the expected artifact of a CLI invocation that
    # ended before returning JSON (for example a stream transport failure).  It
    # is missing telemetry, not malformed JSON, so keep it out of parser-error
    # counts and recover usage from the session journal instead.
    stdout = read_json(
        trial_dir / "agent" / "astra.stdout.json",
        diagnostics,
        empty_is_missing=True,
    ) or {}
    journal_rows, step_rows, journal_bad, step_bad, journal_paths, step_paths = (
        load_local_session(trial_dir, session_id, diagnostics)
    )
    agent_execution_s = seconds_between(result.get("agent_execution"))
    retry = retry_summary(
        trial_dir, metadata, agent_execution_s, stdout, diagnostics
    )
    timeout = timeout_summary(trial_dir, result, metadata, journal_rows, retry)
    trace = context_trace_usage(trial_dir, session_id, diagnostics)
    tools = extract_tools(step_rows, step_paths, step_bad)
    model_activity_observed = bool(
        trace.get("call_count")
        or feedback_rows(journal_rows)
        or (tools.get("agentic_steps") or 0) > 0
        or stdout_usage(stdout) is not None
    )
    token = token_accounting(
        trace,
        stdout,
        journal_rows,
        retry,
        agent_result,
        bool(timeout["llm_request_timeout"]),
        model_activity_observed,
        bool(journal_paths),
        matrixone_usage,
        matrixone_query_status,
    )
    verifier = verifier_summary(trial_dir, reward, diagnostics)

    exception = result.get("exception_info")
    exception = exception if isinstance(exception, dict) else {}
    product_status = str(metadata.get("product_terminal_status") or "unknown")
    product_rc = integer(metadata.get("product_return_code"))
    normal_e2e_pass = bool(
        reward == 1
        and product_status == "completed"
        and product_rc == 0
        and not exception
    )
    retry_count = retry.get("retry_count")
    clean_e2e_pass = bool(
        normal_e2e_pass
        and not timeout["timeout"]
        and (retry_count in (None, 0))
    )
    row: Dict[str, Any] = {
        "task_id": attempt["task_id"],
        "attempt_count_for_task": attempt["attempt_count_for_task"],
        "selected_source_root": attempt["source_root"],
        "selected_run_dir": attempt["run_dir"],
        "selected_trial_name": attempt["trial_name"],
        "selected_trial_path": attempt["trial_path"],
        "selected_started_at": attempt["started_at"],
        "selected_finished_at": attempt["finished_at"],
        "reward": reward,
        "verify_status": "pass" if reward == 1 else "no_pass",
        "verify_reward_present": True,
        "normal_e2e_pass": normal_e2e_pass,
        "clean_e2e_pass": clean_e2e_pass,
        "outcome_bucket": "",
        "harbor_exception": bool(exception),
        "harbor_exception_type": exception.get("exception_type"),
        "harbor_exception_message": exception.get("exception_message"),
        "product_terminal_status": product_status,
        "product_return_code": product_rc,
        "product_completion_claim": metadata.get("product_completion_claim"),
        "product_error_type": metadata.get("product_error_type"),
        "astra_final_state": stdout.get("final_state"),
        "astra_exit_code": integer(stdout.get("exit_code")),
        "trajectory_capture_status": metadata.get("astra_trajectory_status"),
        "trajectory_capture_failed": metadata.get("astra_trajectory_capture_failed"),
        "trajectory_terminal_event": metadata.get(
            "astra_trajectory_local_journal_terminal_event"
        ),
        "formal_score_eligible": metadata.get("formal_score_eligible"),
        "evaluation_status": metadata.get("evaluation_status"),
        "lifecycle_gate_passed": metadata.get("lifecycle_gate_passed"),
        "trigger_hit": metadata.get("trigger_hit"),
        "product_attempt_count": retry.get("attempt_count"),
        "stream_transport_retry_count": retry_count,
        "stream_transport_recovered": retry.get("recovered"),
        "stream_transport_retry_exhausted": retry.get("exhausted"),
        "stream_transport_retry_status": retry.get("status"),
        "stream_transport_failure_classification": retry.get(
            "failure_classification"
        ),
        "stream_transport_retry_skip_reason": retry.get("skip_reason"),
        "e2e_s": seconds_between(result),
        "environment_setup_s": seconds_between(result.get("environment_setup")),
        "agent_setup_s": seconds_between(result.get("agent_setup")),
        "agent_execution_s": agent_execution_s,
        "verifier_s": seconds_between(result.get("verifier")),
        "product_attempt_duration_sum_s": retry.get("duration_sum_s"),
        "llm_call_duration_sum_s": trace.get("llm_duration_sum_s"),
        "cost_usd": number(agent_result.get("cost_usd")),
        **verifier,
        **timeout,
        **tools,
        **token,
    }
    row["outcome_bucket"] = derive_outcome_bucket(row)
    # Internal-only values used to explain data quality without leaking into
    # the stable trial CSV schema.
    row["_journal_bad_lines"] = journal_bad
    row["_step_bad_lines"] = step_bad
    row["_journal_path_count"] = len(journal_paths)
    row["_step_path_count"] = len(step_paths)
    row["_journal_session_exact"] = bool(
        not session_id
        or (journal_paths and all(path.stem == session_id for path in journal_paths))
    )
    row["_step_session_exact"] = bool(
        not session_id
        or (step_paths and all(path.parent.name == session_id for path in step_paths))
    )
    row["_foreign_context_trace_events_ignored"] = trace.get(
        "foreign_session_events_ignored", 0
    )
    row["_retry_report_incomplete"] = retry.get("report_incomplete")
    return row


def quality_issues(rows: List[Dict[str, Any]], diagnostics: ParseDiagnostics) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    def add(row: Dict[str, Any], severity: str, code: str, detail: str) -> None:
        issues.append(
            {
                "task_id": row.get("task_id"),
                "severity": severity,
                "issue_code": code,
                "detail": detail,
                "trial_path": row.get("selected_trial_path"),
            }
        )

    for row in rows:
        if not row.get("ctrf_present"):
            add(row, "warning", "missing_ctrf", "numeric reward exists but verifier/ctrf.json is missing or invalid")
        elif row.get("reward_ctrf_consistent") is False:
            add(row, "warning", "reward_ctrf_mismatch", "binary reward and CTRF failed-test summary do not imply the same pass state")
        token_status = str(row.get("token_accounting_status"))
        if token_status in ("session_input_only", "server_input_only"):
            add(row, "warning", "token_input_only", "session input is observed, but fresh/cache/output split is unavailable")
        elif token_status == "session_source_mismatch":
            add(row, "error", "token_source_mismatch", "context-trace input disagrees with reconstructed stdout/journal input")
        elif "component_mismatch" in token_status:
            add(row, "error", "token_component_mismatch", "reported input does not equal fresh + cache_read + cache_creation")
        elif token_status.startswith("missing"):
            add(row, "error", "token_missing", "no usable provider-reported token usage was recovered")
        if row.get("token_server_local_trace_delta") not in (None, 0):
            add(
                row,
                "warning",
                "matrixone_local_trace_delta",
                "retained MatrixOne session input differs from local context trace; server-side response rows are canonical",
            )
        if row.get("background_agent_result_count") not in (None, 0):
            add(row, "warning", "background_agent_usage_unreviewed", "background_agent_results is non-empty and requires separate token attribution")
        if row.get("tool_telemetry_status") != "ledger_internally_complete":
            add(row, "warning", "tool_telemetry_incomplete", "local step-event ledger is missing, malformed, or has unmatched calls")
        if (
            row.get("_journal_path_count", 0) > 1
            or row.get("_step_path_count", 0) > 1
            or not row.get("_journal_session_exact")
            or not row.get("_step_session_exact")
        ):
            add(row, "warning", "local_session_source_ambiguous", "local session artifacts did not resolve to exactly one journal and one step ledger for the selected session id")
        if row.get("_foreign_context_trace_events_ignored"):
            add(row, "warning", "foreign_context_trace_ignored", "context-trace events from a different session id were excluded")
        if row.get("controller_deadline_suspected"):
            add(row, "warning", "controller_deadline_inferred", "timeout is inferred from an incomplete running retry report plus duration near the configured deadline")
        if row.get("_retry_report_incomplete"):
            add(row, "warning", "retry_report_incomplete", "stream-transport retry report was not finalized")
        configured = number(row.get("configured_llm_fallback_timeout_s"))
        observed_values = json.loads(str(row.get("observed_llm_fallback_timeout_values") or "[]"))
        if configured is not None and observed_values and any(
            float(value) != configured for value in observed_values
        ):
            add(
                row,
                "warning",
                "fallback_timeout_config_mismatch",
                "configured fallback timeout {}s, but explicit runtime evidence reports {}".format(
                    format_number(configured), observed_values
                ),
            )
        if row.get("_journal_bad_lines"):
            add(row, "warning", "journal_jsonl_bad_lines", "{} malformed local journal line(s)".format(row["_journal_bad_lines"]))
        if row.get("_step_bad_lines"):
            add(row, "warning", "step_jsonl_bad_lines", "{} malformed step-event line(s)".format(row["_step_bad_lines"]))

    for path, detail in diagnostics.json_parse_errors:
        issues.append(
            {
                "task_id": "",
                "severity": "error",
                "issue_code": "json_parse_error",
                "detail": detail,
                "trial_path": path,
            }
        )
    return sorted(
        issues,
        key=lambda issue: (
            str(issue["task_id"]),
            str(issue["severity"]),
            str(issue["issue_code"]),
        ),
    )


def percentile(values: Iterable[Optional[float]], p: float) -> Optional[float]:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    index = (len(clean) - 1) * p
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return clean[low]
    return clean[low] + (clean[high] - clean[low]) * (index - low)


def metric_stats(values: Iterable[Any]) -> Dict[str, Any]:
    clean = [value_number for value in values if (value_number := number(value)) is not None]
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


TIME_FIELDS = (
    "e2e_s",
    "environment_setup_s",
    "agent_setup_s",
    "agent_execution_s",
    "verifier_s",
    "product_attempt_duration_sum_s",
    "llm_call_duration_sum_s",
)
TOOL_FIELDS = (
    "agentic_steps",
    "tool_calls_started",
    "tool_calls_completed",
    "tool_calls_failed",
    "tool_calls_skipped",
    "tool_calls_terminal",
    "tool_calls_unpaired",
    "tool_call_duration_sum_s",
)
TOKEN_FIELDS = (
    "token_input",
    "token_fresh_input",
    "token_cache_read",
    "token_cache_creation",
    "token_output",
    "token_total",
    "token_known_minimum",
)


def group_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "n": len(rows),
        "time": {
            field: metric_stats(row.get(field) for row in rows) for field in TIME_FIELDS
        },
        "tools": {
            field: metric_stats(row.get(field) for row in rows) for field in TOOL_FIELDS
        },
        "token": {
            "accounting_status": dict(
                sorted(Counter(str(row.get("token_accounting_status")) for row in rows).items())
            ),
            "metrics": {
                field: metric_stats(row.get(field) for row in rows)
                for field in TOKEN_FIELDS
            },
            "complete_total_coverage": sum(row.get("token_total") is not None for row in rows),
            "input_coverage": sum(row.get("token_input") is not None for row in rows),
            "detail_coverage": sum(
                all(
                    row.get(field) is not None
                    for field in (
                        "token_fresh_input",
                        "token_cache_read",
                        "token_cache_creation",
                        "token_output",
                    )
                )
                for row in rows
            ),
            "source_mismatch_count": sum(
                row.get("token_sources_consistent") is False for row in rows
            ),
        },
        "cost_usd": metric_stats(row.get("cost_usd") for row in rows),
    }


def aggregate_tool_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    tool_counts: Counter[str] = Counter()
    failed_counts: Counter[str] = Counter()
    for row in rows:
        try:
            tool_counts.update(json.loads(str(row.get("tool_breakdown") or "{}")))
            failed_counts.update(
                json.loads(str(row.get("failed_tool_breakdown") or "{}"))
            )
        except json.JSONDecodeError:
            continue
    started = sum(int(row.get("tool_calls_started") or 0) for row in rows)
    completed = sum(int(row.get("tool_calls_completed") or 0) for row in rows)
    failed = sum(int(row.get("tool_calls_failed") or 0) for row in rows)
    skipped = sum(int(row.get("tool_calls_skipped") or 0) for row in rows)
    terminal = completed + failed + skipped
    return {
        "telemetry_status": dict(
            sorted(Counter(str(row.get("tool_telemetry_status")) for row in rows).items())
        ),
        "started": started,
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "terminal": terminal,
        "unpaired": sum(int(row.get("tool_calls_unpaired") or 0) for row in rows),
        "orphan_terminal": sum(
            int(row.get("tool_terminal_orphan_count") or 0) for row in rows
        ),
        "weighted_failure_rate": failed / (completed + failed) if completed + failed else None,
        "weighted_terminal_coverage": terminal / started if started else None,
        "tool_breakdown": dict(tool_counts.most_common()),
        "failed_tool_breakdown": dict(failed_counts.most_common()),
    }


def summarize(
    roots: Sequence[Path],
    attempts: List[Dict[str, Any]],
    latest: List[Dict[str, Any]],
    included: List[Dict[str, Any]],
    excluded_tasks: Set[str],
    diagnostics: ParseDiagnostics,
    issues: List[Dict[str, Any]],
    matrixone_query: Dict[str, Any],
) -> Dict[str, Any]:
    latest_by_task = {str(row["task_id"]): row for row in latest}
    excluded_present = sorted(set(latest_by_task) & excluded_tasks)
    unverified = [
        row
        for row in latest
        if row["task_id"] not in excluded_tasks and row["reward"] is None
    ]
    groups = {
        "all_included": included,
        "verify_pass": [row for row in included if row["verify_status"] == "pass"],
        "verify_no_pass": [row for row in included if row["verify_status"] == "no_pass"],
        "observed_timeout": [row for row in included if row["timeout_observed"]],
        "no_observed_timeout": [row for row in included if not row["timeout_observed"]],
        "timeout": [row for row in included if row["timeout"]],
        "non_timeout": [row for row in included if not row["timeout"]],
        "timeout_or_deadline_suspected": [
            row for row in included if row["timeout_or_deadline_suspected"]
        ],
        "neither_timeout_nor_deadline_suspected": [
            row for row in included if not row["timeout_or_deadline_suspected"]
        ],
        "normal_e2e_pass": [row for row in included if row["normal_e2e_pass"]],
        "clean_e2e_pass": [row for row in included if row["clean_e2e_pass"]],
    }
    pass_timeout = sum(
        row["verify_status"] == "pass" and row["timeout"] for row in included
    )
    pass_non_timeout = sum(
        row["verify_status"] == "pass" and not row["timeout"] for row in included
    )
    no_pass_timeout = sum(
        row["verify_status"] == "no_pass" and row["timeout"] for row in included
    )
    no_pass_non_timeout = sum(
        row["verify_status"] == "no_pass" and not row["timeout"] for row in included
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "input_roots": [str(root.resolve()) for root in roots],
        "selection_policy": {
            "order": [
                "discover all valid attempts across every input root",
                "select one deterministic latest attempt per task_id",
                "exclude configured task ids",
                "include only latest attempts whose verifier reward is numeric 0 or 1",
            ],
            "latest_key": "nearest batch directory timestamp YYYY-MM-DD__HH-MM-SS, then result.started_at, result.finished_at, and absolute result path",
            "no_verified_fallback": "If the latest attempt has no numeric reward, the task is excluded; an older verified attempt is never substituted.",
            "excluded_tasks": sorted(excluded_tasks),
        },
        "scope": {
            "discovered_result_files": diagnostics.result_files_seen,
            "discovered_valid_attempts": len(attempts),
            "unique_tasks_before_exclusion": len(latest),
            "repeated_task_count": sum(
                int(row.get("attempt_count_for_task") or 0) > 1 for row in latest
            ),
            "repeated_attempt_excess": len(attempts) - len(latest),
            "excluded_tasks_present": excluded_present,
            "excluded_tasks_with_numeric_verifier": [
                task_id
                for task_id in excluded_present
                if latest_by_task[task_id]["reward"] is not None
            ],
            "latest_without_numeric_verifier_after_exclusion": [
                {
                    "task_id": row["task_id"],
                    "trial_path": row["trial_path"],
                    "finished_at": row["finished_at"],
                }
                for row in unverified
            ],
            "included_latest_verified_tasks": len(included),
        },
        "completion": {
            "verify_pass": sum(row["verify_status"] == "pass" for row in included),
            "verify_no_pass": sum(
                row["verify_status"] == "no_pass" for row in included
            ),
            "verify_pass_rate": (
                sum(row["verify_status"] == "pass" for row in included) / len(included)
                if included
                else None
            ),
            "timeout": sum(bool(row["timeout"]) for row in included),
            "non_timeout": sum(not row["timeout"] for row in included),
            "timeout_rate": (
                sum(bool(row["timeout"]) for row in included) / len(included)
                if included
                else None
            ),
            "timeout_observed": sum(bool(row["timeout_observed"]) for row in included),
            "timeout_inferred": sum(bool(row["timeout_inferred"]) for row in included),
            "controller_deadline_suspected": sum(
                bool(row["controller_deadline_suspected"]) for row in included
            ),
            "timeout_or_deadline_suspected": sum(
                bool(row["timeout_or_deadline_suspected"]) for row in included
            ),
            "neither_timeout_nor_deadline_suspected": sum(
                not row["timeout_or_deadline_suspected"] for row in included
            ),
            "timeout_type": dict(
                sorted(
                    Counter(
                        timeout_type
                        for row in included
                        for timeout_type in json.loads(str(row["timeout_types"]))
                    ).items()
                )
            ),
            "verify_by_timeout": {
                "pass_timeout": pass_timeout,
                "pass_non_timeout": pass_non_timeout,
                "no_pass_timeout": no_pass_timeout,
                "no_pass_non_timeout": no_pass_non_timeout,
            },
            "normal_e2e_pass": sum(bool(row["normal_e2e_pass"]) for row in included),
            "clean_e2e_pass": sum(bool(row["clean_e2e_pass"]) for row in included),
            "harbor_exception": sum(bool(row["harbor_exception"]) for row in included),
            "outcome_bucket": dict(
                sorted(Counter(str(row["outcome_bucket"]) for row in included).items())
            ),
            "product_terminal_status": dict(
                sorted(
                    Counter(str(row["product_terminal_status"]) for row in included).items()
                )
            ),
            "trajectory_capture_status": dict(
                sorted(
                    Counter(str(row["trajectory_capture_status"]) for row in included).items()
                )
            ),
            "formal_score_eligible": dict(
                sorted(Counter(str(row["formal_score_eligible"]) for row in included).items())
            ),
        },
        "metrics_by_group": {
            name: group_metrics(group_rows) for name, group_rows in groups.items()
        },
        "tools": aggregate_tool_summary(included),
        "verifier_detail": {
            "ctrf_coverage": sum(bool(row["ctrf_present"]) for row in included),
            "reward_ctrf_consistent": sum(
                row["reward_ctrf_consistent"] is True for row in included
            ),
            "reward_ctrf_mismatch": sum(
                row["reward_ctrf_consistent"] is False for row in included
            ),
        },
        "timeout_definition": {
            "timeout_observed": "Explicit LLM fallback timeout, product timeout, verifier timeout, or Harbor adapter timeout evidence.",
            "controller_deadline_suspected": "Inference only: retry report is still running/incomplete and agent duration reached at least 95% of the configured product deadline.",
            "timeout_or_deadline_suspected": "Union of timeout_observed and controller_deadline_suspected.",
            "compatibility_alias": "The trial-level timeout field and summary timeout/non_timeout groups currently use timeout_or_deadline_suspected; use timeout_observed when only literal timeout evidence is acceptable.",
        },
        "token_definition": {
            "source_kind": "Provider-reported usage persisted by Astra; no local tokenizer is used.",
            "canonical_priority": "When a selected session is retained in MatrixOne astra_runtime.agent_events with event_type=llm_response, its aggregate is canonical. Otherwise the local session artifacts below are used.",
            "matrixone_lookup": matrixone_query,
            "input_formula": "token_input = token_fresh_input + token_cache_read + token_cache_creation",
            "total_formula": "token_total = token_input + token_output; cache is a subset of input and is never added twice",
            "session_input": "Local fallback: sum deduplicated server-events.jsonl context_trace_signal metadata.budget.total_used values across the selected Astra session, including resumed outer retries.",
            "detail_reconstruction": "Use final astra.stdout.json plus pipeline_feedback events timestamped before the final successful retry; without successful stdout, use all returned pipeline_feedback usage.",
            "harbor_role": "result.json n_input/n_cache/n_output is a terminal-attempt cross-check only, not the canonical session-wide retry total.",
            "missing_rule": "Missing usage remains null, never zero. token_total is null unless both canonical input and reconciled output are available.",
            "known_minimum": "token_known_minimum is the sum of components actually observed; an in-flight request that never returned usage can be absent.",
            "billing_caveat": "Observed telemetry is not a provider invoice. No USD estimate is made without reliable billing and model pricing data.",
        },
        "resource_metric_availability": {
            "time": "available as task/phase durations; sums are task-seconds, not batch wall-clock",
            "provider_reported_tokens": "available with per-field coverage in metrics_by_group",
            "tool_calls": "available from local step-event ledgers with telemetry status and terminal coverage",
            "cpu": "unavailable",
            "ram": "unavailable",
            "gpu": "unavailable",
            "disk_io": "unavailable",
            "network_bytes": "unavailable",
            "provider_billing": "unavailable",
        },
        "data_quality": {
            "parse_diagnostics": diagnostics.as_dict(),
            "issue_count": len(issues),
            "issue_by_code": dict(
                sorted(Counter(str(issue["issue_code"]) for issue in issues).items())
            ),
            "issue_by_severity": dict(
                sorted(Counter(str(issue["severity"]) for issue in issues).items())
            ),
        },
        "limitations": [
            "Verifier reward is the inclusion and pass/no-pass authority. CTRF is independent diagnostic detail and may be missing.",
            "timeout is orthogonal to verifier outcome: recovered request timeouts and deadline termination can still leave passing artifacts.",
            "controller_deadline_suspected is explicitly an inference, requiring an incomplete running retry report and observed agent duration near the configured deadline; it is not presented as a literal timeout log event.",
            "Cumulative LLM and tool-call latency can overlap and must not be added to phase wall times as a resource decomposition.",
            "CPU, RAM, GPU, disk, network bytes, and actual provider billing are absent and intentionally not estimated.",
        ],
    }


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def format_number(value: Any, digits: int = 2) -> str:
    value_number = number(value)
    if value_number is None:
        return "—"
    if value_number.is_integer():
        return "{:,}".format(int(value_number))
    return ("{:,.%df}" % digits).format(value_number)


def format_duration(value: Any) -> str:
    value_number = number(value)
    if value_number is None:
        return "—"
    return "{:.2f} min".format(value_number / 60.0)


def format_percent(value: Any) -> str:
    value_number = number(value)
    if value_number is None:
        return "—"
    return "{:.2f}%".format(100.0 * value_number)


def md_escape(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def write_markdown(
    path: Path,
    summary: Dict[str, Any],
    rows: List[Dict[str, Any]],
) -> None:
    scope = summary["scope"]
    completion = summary["completion"]
    all_metrics = summary["metrics_by_group"]["all_included"]
    token = all_metrics["token"]
    matrixone_lookup = summary["token_definition"]["matrixone_lookup"]
    tools = summary["tools"]
    matrix = completion["verify_by_timeout"]
    unverified = scope["latest_without_numeric_verifier_after_exclusion"]
    lines = [
        "# Astra C0 latest verified benchmark statistics",
        "",
        "本报告由 `extract_astra_c0_trials.py` 自动生成。新增或替换部分 case 的运行结果后，重新执行脚本即可；不要手工修改产物。",
        "",
        "## 范围与最新运行选择",
        "",
        "| 项目 | 数量/内容 |",
        "| --- | ---: |",
        "| 扫描到的有效 attempt | {} |".format(scope["discovered_valid_attempts"]),
        "| 排除前唯一 task | {} |".format(scope["unique_tasks_before_exclusion"]),
        "| 存在重复运行的 task | {} |".format(scope["repeated_task_count"]),
        "| 重复产生的额外 attempt | {} |".format(scope["repeated_attempt_excess"]),
        "| 排除 task | {} |".format(", ".join(scope["excluded_tasks_present"]) or "—"),
        "| 最终纳入的 latest + verified task | {} |".format(scope["included_latest_verified_tasks"]),
        "",
        "选择顺序是：先跨所有输入目录按 task 选最后一次运行，再排除 `tune-mjcf`，最后只纳入 latest reward 为数字 `0/1` 的 case。latest 没有 verifier reward 时不会回退到旧的已评分运行。",
        "",
        "最新运行无数字 verifier reward：{}。".format(
            ", ".join(str(item["task_id"]) for item in unverified) or "无"
        ),
        "",
        "## 完成情况",
        "",
        "| 指标 | 数量 |",
        "| --- | ---: |",
        "| Verify pass | {} |".format(completion["verify_pass"]),
        "| Verify no-pass | {} |".format(completion["verify_no_pass"]),
        "| Verify pass rate | {} |".format(format_percent(completion["verify_pass_rate"])),
        "| Observed timeout（明确证据） | {} |".format(completion["timeout_observed"]),
        "| Controller deadline suspected（推断） | {} |".format(completion["controller_deadline_suspected"]),
        "| Timeout or deadline suspected（并集） | {} |".format(completion["timeout_or_deadline_suspected"]),
        "| Neither timeout nor deadline suspected | {} |".format(completion["neither_timeout_nor_deadline_suspected"]),
        "| Combined rate | {} |".format(format_percent(completion["timeout_rate"])),
        "| Normal E2E pass | {} |".format(completion["normal_e2e_pass"]),
        "| Clean E2E pass | {} |".format(completion["clean_e2e_pass"]),
        "| Harbor exception | {} |".format(completion["harbor_exception"]),
        "",
        "`normal_e2e_pass` 要求 verifier pass、product completed、return code 0 且无 Harbor exception；`clean_e2e_pass` 进一步要求没有 timeout 且没有外层 retry。轨迹完整性、formal eligibility 和 lifecycle gate 分开报告，不用来改写 verifier 分数。",
        "",
        "| Verify × Timeout-or-deadline-suspected | Yes | No |",
        "| --- | ---: | ---: |",
        "| Pass | {} | {} |".format(matrix["pass_timeout"], matrix["pass_non_timeout"]),
        "| No-pass | {} | {} |".format(matrix["no_pass_timeout"], matrix["no_pass_non_timeout"]),
        "",
        "Timeout 类型：{}。其中 `controller_deadline_suspected` 是由“retry report 仍为 running/incomplete + agent 时长达到配置 deadline”推断的单列指标；其余是显式日志/状态/异常证据。".format(
            ", ".join(
                "{}={}".format(key, value)
                for key, value in completion["timeout_type"].items()
            )
            or "无"
        ),
        "",
        "## 时间与资源",
        "",
        "| 指标 | 覆盖 | 累计 | 中位数 | P90 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, field in (
        ("端到端 task 时间", "e2e_s"),
        ("Environment setup", "environment_setup_s"),
        ("Agent setup", "agent_setup_s"),
        ("Agent execution", "agent_execution_s"),
        ("Verifier", "verifier_s"),
        ("外层 product attempt 累计", "product_attempt_duration_sum_s"),
        ("LLM 调用累计延迟", "llm_call_duration_sum_s"),
    ):
        stats = all_metrics["time"][field]
        lines.append(
            "| {} | {}/{} | {} | {} | {} |".format(
                label,
                stats["n"],
                len(rows),
                format_duration(stats["sum"]),
                format_duration(stats["median"]),
                format_duration(stats["p90"]),
            )
        )
    lines.extend(
        [
            "",
            "这些累计值是 task-seconds 或调用延迟之和，不是整批并行 benchmark 的墙钟时间。LLM 与工具调用可能重叠，不能与 agent wall time 相加做资源分解。CPU、RAM、GPU、磁盘、网络字节和实际供应商账单在现有 artifact 中不可用，脚本不做估算。",
            "",
            "## Token 数据口径",
            "",
            "- 数据来自 Astra 落盘的供应商 usage，不使用本地 tokenizer。若本次查询命中 MatrixOne，则优先采用 `astra_runtime.agent_events` 中该 session 的 `llm_response` 聚合；未命中才回退到本地落盘记录。",
            "- `input = fresh + cache_read + cache_creation`；`total = input + output`。cache 已包含在 input 内，绝不再次相加。",
            "- 本地回退的 session input 汇总 `server-events.jsonl` 中去重后的 `context_trace_signal.metadata.budget.total_used`，可覆盖同 session 的外层 resume/retry。",
            "- fresh/cache/output 由最终成功的 `astra.stdout.json` 加上最终 attempt 开始前的 `pipeline_feedback` 重建；没有成功 stdout 时使用全部已经返回的 feedback usage。",
            "- `result.json` 的 Harbor token 只作终态交叉检查；它通常只覆盖最后一次 CLI invocation，不能替代 session-wide retry 总量。",
            "- 缺失不是 0。只有 canonical input 和重建 output 都完整时才给“完整可观测 `token_total`”；否则只给明确命名的 `token_known_minimum`。断流中未返回 usage 的在途请求仍可能漏记，因此这不是账单口径。",
            "- MatrixOne 查询：mode={mode}，status={status}，请求 session={requested}，命中 session={found}。数据库保留期外的旧 session 会显示为未命中，而不是 token=0。".format(
                mode=matrixone_lookup.get("mode"),
                status=matrixone_lookup.get("status"),
                requested=matrixone_lookup.get("requested_session_count"),
                found=matrixone_lookup.get("found_session_count"),
            ),
            "",
            "| Token 指标 | 覆盖 | 合计 | 中位数 | P90 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    token_labels = (
        ("Input（含 cache）", "token_input"),
        ("Fresh input", "token_fresh_input"),
        ("Cache read", "token_cache_read"),
        ("Cache creation", "token_cache_creation"),
        ("Output", "token_output"),
        ("完整可观测 total", "token_total"),
        ("可观测 minimum", "token_known_minimum"),
    )
    for label, field in token_labels:
        stats = token["metrics"][field]
        lines.append(
            "| {} | {}/{} | {} | {} | {} |".format(
                label,
                stats["n"],
                len(rows),
                format_number(stats["sum"]),
                format_number(stats["median"]),
                format_number(stats["p90"]),
            )
        )
    lines.extend(
        [
            "",
            "| Token accounting status | Tasks |",
            "| --- | ---: |",
        ]
    )
    for status, count in token["accounting_status"].items():
        lines.append("| {} | {} |".format(status, count))
    lines.extend(
        [
            "",
            "## 工具调用",
            "",
            "工具以 local `step_events.jsonl` 为账本，按 event/call id 去重。`ledger_internally_complete` 只表示现有账本内部 started/terminal 闭合，不保证 partial trajectory 没有漏捕。started、completed、failed、skipped 分开；失败率是 `failed / (completed + failed)`。工具 elapsed 之和是累计调用延迟，并行时会重复覆盖墙钟时间。",
            "",
            "| 指标 | 数量 |",
            "| --- | ---: |",
            "| Agentic StepStarted | {} |".format(format_number(all_metrics["tools"]["agentic_steps"]["sum"])),
            "| ToolCallStarted | {} |".format(format_number(tools["started"])),
            "| ToolCallCompleted | {} |".format(format_number(tools["completed"])),
            "| ToolCallFailed | {} |".format(format_number(tools["failed"])),
            "| ToolCallSkipped | {} |".format(format_number(tools["skipped"])),
            "| 终态覆盖率 | {} |".format(format_percent(tools["weighted_terminal_coverage"])),
            "| 加权失败率 | {} |".format(format_percent(tools["weighted_failure_rate"])),
            "",
            "工具分布：`{}`。".format(compact_json(tools["tool_breakdown"])),
            "",
            "失败工具分布：`{}`。".format(compact_json(tools["failed_tool_breakdown"])),
            "",
            "## 数据质量与 no-pass 明细",
            "",
            "CTRF 覆盖 {}/{}；数据质量 issue 共 {} 条。逐项记录见 `astra-c0-data-quality.csv`，全部 attempt 的选择过程见 `astra-c0-attempt-selection.csv`。".format(
                summary["verifier_detail"]["ctrf_coverage"],
                len(rows),
                summary["data_quality"]["issue_count"],
            ),
            "",
            "Issue 类型：{}。".format(
                ", ".join(
                    "{}={}".format(code, count)
                    for code, count in summary["data_quality"]["issue_by_code"].items()
                )
                or "无"
            ),
            "",
            "| Task | Timeout 类型 | Product 状态 | Token 状态 | Tool started/failed | 路径 |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in rows:
        if row["verify_status"] != "no_pass":
            continue
        timeout_types = ", ".join(json.loads(str(row["timeout_types"]))) or "no"
        lines.append(
            "| {} | {} | {} | {} | {}/{} | `{}` |".format(
                md_escape(row["task_id"]),
                md_escape(timeout_types),
                md_escape(row["product_terminal_status"]),
                md_escape(row["token_accounting_status"]),
                format_number(row["tool_calls_started"]),
                format_number(row["tool_calls_failed"]),
                md_escape(row["selected_trial_path"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    roots = [root.expanduser().resolve() for root in args.root]
    output_dir = args.output_dir.expanduser().resolve()
    for root in roots:
        if not root.is_dir():
            raise SystemExit("Astra work root does not exist: {}".format(root))
    excluded_tasks = DEFAULT_EXCLUDED_TASKS | set(args.exclude_task)
    diagnostics = ParseDiagnostics()
    attempts = discover_attempts(roots, diagnostics)
    latest, audit = select_latest(attempts, excluded_tasks)
    selected_attempts = [
        attempt
        for attempt in latest
        if attempt["task_id"] not in excluded_tasks and attempt["reward"] is not None
    ]
    matrixone_usage_by_session, matrixone_query = matrixone_session_usage(
        (attempt_session_id(attempt) for attempt in selected_attempts), args
    )
    included = [
        extract_trial(
            attempt,
            diagnostics,
            matrixone_usage_by_session.get(attempt_session_id(attempt)),
            str(matrixone_query.get("status") or "not_queried"),
        )
        for attempt in selected_attempts
    ]
    issues = quality_issues(included, diagnostics)
    summary = summarize(
        roots,
        attempts,
        latest,
        included,
        excluded_tasks,
        diagnostics,
        issues,
        matrixone_query,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    trials_path = output_dir / "astra-c0-latest-verified-trials.csv"
    no_pass_path = output_dir / "astra-c0-latest-verified-no-pass.csv"
    summary_path = output_dir / "astra-c0-latest-verified-summary.json"
    report_path = output_dir / "astra-c0-latest-verified-report.md"
    audit_path = output_dir / "astra-c0-attempt-selection.csv"
    quality_path = output_dir / "astra-c0-data-quality.csv"
    write_csv(trials_path, included, TRIAL_FIELDS)
    write_csv(
        no_pass_path,
        [row for row in included if row["verify_status"] == "no_pass"],
        TRIAL_FIELDS,
    )
    write_csv(audit_path, audit, ATTEMPT_FIELDS)
    write_csv(quality_path, issues, QUALITY_FIELDS)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(report_path, summary, included)

    print(
        "Extracted {} latest verified tasks from {} attempts ({} unique tasks before exclusion).".format(
            len(included), len(attempts), len(latest)
        )
    )
    print(
        "Verify pass/no-pass: {}/{}; observed timeout: {}; timeout-or-deadline-suspected/neither: {}/{}.".format(
            summary["completion"]["verify_pass"],
            summary["completion"]["verify_no_pass"],
            summary["completion"]["timeout_observed"],
            summary["completion"]["timeout"],
            summary["completion"]["non_timeout"],
        )
    )
    print("Trials CSV: {}".format(trials_path))
    print("Summary: {}".format(summary_path))
    print("Report: {}".format(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
