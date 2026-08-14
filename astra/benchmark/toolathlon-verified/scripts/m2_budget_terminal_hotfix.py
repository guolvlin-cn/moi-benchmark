#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from astra.runners.toolathlon_verified import artifact_contract, m2_batch
from astra.runners.toolathlon_verified.contract import (
    ContractError,
    read_json_object,
    sha256_file,
    utc_now,
    write_json_atomic,
    write_sha256_manifest,
)

_BASE_MODEL_USAGE_VALIDATOR = artifact_contract._validate_model_usage
_BASE_AGENT_MODEL_BOUNDARY_VALIDATOR = (
    artifact_contract._validate_agent_model_boundary
)


POLICY = "toolathlon.astra-budget-terminal-missing-tool-count.v1"
TRIGGER = "Astra native tool transport count has no unique server declaration"
COUNT_SCOPE_POLICY = (
    "toolathlon.astra-server-model-tool-count-vs-native-transport.v1"
)
COUNT_SCOPE_TRIGGER = (
    "Astra server-declared tool count differs from terminal transports"
)
COUNT_SCOPE_ARTIFACT = "astra-tool-count-observability.json"
COUNT_SCOPE_RECOVERY_NAME = "astra-tool-count-observability-recovery.json"
COUNT_SCOPE_RECOVERY_HASH_NAME = "astra-tool-count-observability-recovery.sha256"
HERMES_DRAIN_POLICY = (
    "toolathlon.hermes-post-shutdown-model-drain-reconciliation.v1"
)
HERMES_DRAIN_TIMEOUT_POLICY = (
    "toolathlon.hermes-drain-timeout-boundary-reconciliation.v2"
)
HERMES_DRAIN_TRIGGER = "valid run has an unsettled post-terminal model drain"
HERMES_DRAIN_ARTIFACT = "hermes-post-shutdown-model-drain.json"
HERMES_DRAIN_RECOVERY_NAME = "hermes-model-drain-recovery.json"
HERMES_DRAIN_RECOVERY_HASH_NAME = "hermes-model-drain-recovery.sha256"
HERMES_OPEN_REQUEST_POLICY = (
    "toolathlon.hermes-post-drain-open-request-infra-invalid.v1"
)
HERMES_OPEN_REQUEST_ARTIFACT = "hermes-open-model-request.json"
HERMES_OPEN_REQUEST_RECOVERY_NAME = "hermes-open-model-request-recovery.json"
HERMES_OPEN_REQUEST_RECOVERY_HASH_NAME = (
    "hermes-open-model-request-recovery.sha256"
)
ASTRA_DEADLINE_POLICY = (
    "toolathlon.astra-agent-deadline-observability-boundary.v1"
)
ASTRA_DEADLINE_ARTIFACT = "astra-agent-deadline-observability.json"
ASTRA_DEADLINE_RECOVERY_NAME = "astra-agent-deadline-recovery.json"
ASTRA_DEADLINE_RECOVERY_HASH_NAME = "astra-agent-deadline-recovery.sha256"
FORMAL_TRIGGER = "effective formal run has no evaluator conclusion"
RECOVERY_NAME = "astra-budget-terminal-recovery.json"
RECOVERY_HASH_NAME = "astra-budget-terminal-recovery.sha256"
EVALUATOR_POLICY = "toolathlon.budget-terminal-task-specific-evaluation.v1"
PRODUCT_FAILURE_POLICY = (
    "toolathlon.product-failure-evaluator-unavailable-effective-result.v1"
)
PRODUCT_FAILURE_RECOVERY_NAME = "product-failure-evaluator-unavailable-recovery.json"
PRODUCT_FAILURE_RECOVERY_HASH_NAME = (
    "product-failure-evaluator-unavailable-recovery.sha256"
)
BUDGET_EVALUATOR_RECOVERY_NAME = "budget-terminal-evaluator-recovery.json"
BUDGET_EVALUATOR_RECOVERY_HASH_NAME = (
    "budget-terminal-evaluator-recovery.sha256"
)
INTERRUPTION_POLICY = "toolathlon.user-interrupted-formal-attempt-a2-replacement.v1"
INTERRUPTION_RECOVERY_NAME = "user-interrupted-attempt-recovery.json"
INTERRUPTED_PREPROCESS_CLASSIFICATION = (
    "user_keyboard_interrupt_during_preprocess"
)
INTERRUPTED_PREPROCESS_RUN_ID = (
    "m3-20260807T155211Z-89-task-tracker-hermes-a1"
)
INTERRUPTED_PREPROCESS_TASK_ID = "task-tracker"
INTERRUPTED_PREPROCESS_POSITION = 89
PREPROCESS_INFRA_POLICY = (
    "toolathlon.pre-agent-preprocess-infrastructure-a2-replacement.v1"
)
PREPROCESS_INFRA_RECOVERY_NAME = "preprocess-infrastructure-recovery.json"
PREPROCESS_INFRA_RECOVERY_HASH_NAME = "preprocess-infrastructure-recovery.sha256"
TASK_TRACKER_SETUP_POLICY = (
    "toolathlon.task-tracker-container-setup-a3-recovery.v1"
)
TASK_TRACKER_SETUP_RECOVERY_NAME = (
    "task-tracker-container-setup-recovery.json"
)
TASK_TRACKER_SETUP_RECOVERY_HASH_NAME = (
    "task-tracker-container-setup-recovery.sha256"
)
TASK_TRACKER_SETUP_TASK = "task-tracker"
TASK_TRACKER_SETUP_SYSTEM = "hermes"
TASK_TRACKER_SETUP_POSITION = 89
DATASET_REPAIR_POLICY = (
    "toolathlon.filter-low-selling-products-preprocess-repair.v1"
)
DATASET_REPAIR_TASK = "filter-low-selling-products"
DATASET_REPAIR_SYSTEM = "hermes"
DATASET_REPAIR_POSITION = 38
DATASET_REPAIR_NAME = "filter-low-selling-products-preprocess-repair.json"
DATASET_REPAIR_HASH_NAME = "filter-low-selling-products-preprocess-repair.sha256"
DATASET_REPAIR_HARNESS_POLICY = (
    "toolathlon.filter-low-selling-products-overlay-boundary-a4.v1"
)
DATASET_REPAIR_HARNESS_NAME = (
    "filter-low-selling-products-overlay-boundary-recovery.json"
)
DATASET_REPAIR_HARNESS_HASH_NAME = (
    "filter-low-selling-products-overlay-boundary-recovery.sha256"
)
DATASET_REPAIR_SOURCE_RELATIVE = (
    "tasks/finalpool/filter-low-selling-products/preprocess/setup_test_products.py"
)
DATASET_REPAIR_ORIGINAL_SHA256 = (
    "6b841e92fb3bd783ee3bcfbaa87c005767fd470132d9b218a9d2a11ae0e29e88"
)
DATASET_REPAIR_PATCHED_SHA256 = (
    "ba0e476cce9b1e5e0509c044eb92e673d5e72783b8522c13f24849c8649587b6"
)
DATASET_REPAIR_REPLACEMENTS = (
    (
        "self.wc_client.batch_delete_products(all_products)",
        "self.wc_client.batch_delete_products(all_products, batch_size=10)",
    ),
    (
        "self.wc_client.batch_create_products(test_products)",
        "self.wc_client.batch_create_products(test_products, batch_size=10)",
    ),
)
M3_OUTER_POLICY = "toolathlon.m3-outer-lifecycle-hotfix.v1"
M3_OUTER_AMENDMENT_POLICY = (
    "toolathlon.m3-outer-lifecycle-hotfix-amendment.v1"
)
M3_OUTER_AMENDMENT_NAME = "outer-lifecycle-hotfix-amendment.json"
M3_OUTER_AMENDMENT_HASH_NAME = "outer-lifecycle-hotfix-amendment.sha256"
GATE_V2_POLICY = "toolathlon.artifact-gate-structural-hard-observability-soft.v2"
GATE_V2_ROOT_NAME = "artifact-gate-v2"
GATE_V2_POLICY_NAME = "policy.json"
GATE_V2_PROJECTION_NAME = "artifact-gate-v2-projection.json"
GATE_V2_PROJECTION_HASH_NAME = "artifact-gate-v2-projection.sha256"

_COUNT_SCOPE_BY_RUN_ID: dict[str, dict[str, Any]] = {}
_ASTRA_DEADLINE_BY_RUN_ID: dict[str, dict[str, Any]] = {}


def _astra_tool_count_source_evidence() -> dict[str, Any]:
    systems_root = REPO_ROOT / "astra/work/toolathlon-verified/systems"
    roots = sorted(path for path in systems_root.glob("astra-*") if path.is_dir())
    if len(roots) != 1:
        raise ContractError("frozen Astra source root is not unique")
    source_root = roots[0]
    counter = source_root / "crates/astra-turn-core/src/agentic/turn_ingest.rs"
    declaration = source_root / "crates/runtime/src/server/run/lifecycle/mod.rs"
    if not counter.is_file() or not declaration.is_file():
        raise ContractError("Astra tool-count source evidence is missing")
    counter_text = counter.read_text(encoding="utf-8")
    declaration_text = declaration.read_text(encoding="utf-8")
    if (
        "*st.total_tool_calls += if !snap.tool_calls.is_empty()" not in counter_text
        or "snap.tool_calls.len()" not in counter_text
        or '"tool_call_count": loop_state.total_tool_calls' not in declaration_text
    ):
        raise ContractError("Astra tool-count source semantics changed")
    return {
        "semantics": (
            "server declaration counts model-response tool calls before the "
            "interception and transport phases"
        ),
        "counter_source": {
            "path": counter.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(counter),
        },
        "declaration_source": {
            "path": declaration.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(declaration),
        },
    }


def _astra_model_count_vs_transport_evidence(
    trajectory_rows: list[dict[str, Any]], run: dict[str, Any]
) -> dict[str, Any]:
    normal_completion = (
        run.get("terminal_status") == "completed"
        and run.get("primary_failure_category") == "none"
        and run.get("verify_status") in {"pass", "no_pass"}
    )
    product_failure = (
        run.get("terminal_status") == "crashed"
        and run.get("primary_failure_category") == "product_error"
        and run.get("verify_status") == "unavailable"
        and isinstance(run.get("evaluator_error"), dict)
        and run["evaluator_error"].get("reliability") == "observed"
    )
    if (
        run.get("system_id") != "astra"
        or run.get("termination_reason") != "product_exit"
        or run.get("run_validity") != "valid"
        or not (normal_completion or product_failure)
    ):
        raise ContractError(
            "tool-count scope exception is not a completed or product-failed Astra run"
        )

    model_budget = run.get("model_budget")
    if (
        not isinstance(model_budget, dict)
        or model_budget.get("limit_exceeded") is not False
        or not isinstance(model_budget.get("provider_requests_forwarded"), int)
        or model_budget.get("provider_requests_completed")
        != model_budget.get("provider_requests_forwarded")
        or not isinstance(model_budget.get("provider_requests_failed"), int)
        or model_budget.get("provider_requests_failed") < 0
    ):
        raise ContractError("Astra model counters are incomplete for tool-count scope")

    by_type: dict[str, dict[str, dict[str, Any]]] = {
        "tool_routing_decision": {},
        "tool_transport_started": {},
        "tool_transport_terminal": {},
        "tool_call_end": {},
    }
    declared_counts: set[int] = set()
    for row in trajectory_rows:
        native = row.get("native")
        if not isinstance(native, dict):
            continue
        native_type = str(native.get("type", "")).lower()
        if native_type == "usage" and isinstance(native.get("tool_call_count"), int):
            declared_counts.add(native["tool_call_count"])
            continue
        bucket_name = native_type
        if native_type in {"tool_transport_completed", "tool_transport_failed"}:
            bucket_name = "tool_transport_terminal"
        if bucket_name not in by_type:
            continue
        call_id = native.get("call_id")
        tool_name = native.get("tool")
        if not isinstance(call_id, str) or not call_id:
            raise ContractError("Astra tool-count scope event has no call_id")
        if not isinstance(tool_name, str) or not tool_name:
            raise ContractError("Astra tool-count scope event has no tool name")
        bucket = by_type[bucket_name]
        if call_id in bucket:
            raise ContractError(
                f"Astra tool-count scope duplicates {bucket_name} for {call_id}"
            )
        bucket[call_id] = native

    if len(declared_counts) != 1:
        raise ContractError("Astra tool-count scope has no unique server declaration")
    declared = next(iter(declared_counts))
    transport_ids = set(by_type["tool_transport_started"])
    if not transport_ids:
        raise ContractError("Astra tool-count scope has no native transports")
    for event_type, rows in by_type.items():
        if set(rows) != transport_ids:
            raise ContractError(
                f"Astra tool-count scope {event_type} calls differ from transports"
            )
    for call_id in transport_ids:
        names = {rows[call_id]["tool"] for rows in by_type.values()}
        if len(names) != 1:
            raise ContractError(
                f"Astra tool-count scope tool name differs for {call_id}"
            )
    terminal_count = len(transport_ids)
    if declared <= terminal_count:
        raise ContractError(
            "Astra server declaration is not greater than complete transports"
        )

    return {
        "server_declared_model_tool_call_count": declared,
        "native_routing_decision_count": len(by_type["tool_routing_decision"]),
        "native_transport_started_count": len(by_type["tool_transport_started"]),
        "native_transport_terminal_count": terminal_count,
        "native_tool_call_end_count": len(by_type["tool_call_end"]),
        "server_declared_minus_transport_terminal_count": declared - terminal_count,
        "non_transport_call_identity_and_disposition": {
            "value": None,
            "source": "astra_product_event_stream",
            "reliability": "missing",
            "missing_reason": (
                "product_reports_only_an_aggregate_pre_transport_count_for_calls_"
                "handled_or_suppressed_before_native_transport"
            ),
        },
        "interpretation": (
            "native transport events are complete execution evidence; the server "
            "aggregate is a broader model-response call metric and is not an "
            "executed-transport total"
        ),
        "run_disposition": (
            "completed_evaluator_conclusion"
            if normal_completion
            else "product_failure_evaluator_unavailable"
        ),
        "source_evidence": _astra_tool_count_source_evidence(),
    }


def _observation_value(value: Any) -> Any:
    if isinstance(value, dict) and set(value) >= {
        "value",
        "source",
        "reliability",
        "missing_reason",
    }:
        return value.get("value")
    return value


def _hermes_post_shutdown_drain_evidence(
    model_rows: list[dict[str, Any]],
    adapter_rows: list[dict[str, Any]],
    run: dict[str, Any],
) -> dict[str, Any]:
    if (
        run.get("system_id") != "hermes"
        or run.get("terminal_status") != "completed"
        or run.get("termination_reason") != "product_exit"
        or run.get("run_validity") != "valid"
        or run.get("verify_status") not in {"pass", "no_pass"}
    ):
        raise ContractError("model-drain reconciliation is not a completed Hermes run")

    adapter = run.get("adapter")
    if not isinstance(adapter, dict):
        raise ContractError("Hermes model-drain adapter metadata is missing")
    initial = adapter.get("post_terminal_model_drain")
    if (
        not isinstance(initial, dict)
        or initial.get("settled") is not False
        or not isinstance(initial.get("provider_requests_forwarded"), int)
        or not isinstance(initial.get("provider_requests_completed"), int)
        or initial["provider_requests_forwarded"]
        <= initial["provider_requests_completed"]
        or not isinstance(initial.get("timeout_seconds"), (int, float))
        or not isinstance(initial.get("wait_seconds"), (int, float))
        or initial["wait_seconds"] < initial["timeout_seconds"]
    ):
        raise ContractError("Hermes pre-shutdown drain is not a timed-out snapshot")

    _BASE_MODEL_USAGE_VALIDATOR(model_rows, run)
    starts = {
        str(row["model_request_id"]): row
        for row in model_rows
        if row.get("event") == "model_request.started"
    }
    completions = {
        str(row["model_request_id"]): row
        for row in model_rows
        if row.get("event") == "model_request.completed"
    }
    stopped = [row for row in model_rows if row.get("event") == "proxy.stopped"]
    if len(stopped) != 1:
        raise ContractError("Hermes model-drain has no unique proxy stop event")
    stopped_ns = stopped[0].get("monotonic_ns")
    if not isinstance(stopped_ns, int):
        raise ContractError("Hermes proxy stop has no monotonic timestamp")
    if any(row.get("monotonic_ns", stopped_ns) > stopped_ns for row in starts.values()):
        raise ContractError("Hermes started a model request after proxy stop")

    missing_at_snapshot = (
        initial["provider_requests_forwarded"]
        - initial["provider_requests_completed"]
    )
    ordered_completions = sorted(
        completions.values(),
        key=lambda item: int(item.get("monotonic_ns", -1)),
    )
    closing = ordered_completions[-missing_at_snapshot:]
    if (
        not closing
        or len(closing) != missing_at_snapshot
        or any(not isinstance(row.get("monotonic_ns"), int) for row in closing)
    ):
        raise ContractError(
            "Hermes final terminals do not close the timed-out drain snapshot"
        )

    closing_evidence: list[dict[str, Any]] = []
    for row in closing:
        request_id = str(row["model_request_id"])
        start = starts[request_id]
        relative_seconds = (row["monotonic_ns"] - stopped_ns) / 1_000_000_000
        error_type = _observation_value(row.get("error_type"))
        if (
            row.get("success") is not False
            or row.get("http_status") != 502
            or error_type != "downstream_disconnected"
            or abs(relative_seconds) > 10
        ):
            raise ContractError(
                "Hermes drain-closing terminal is not the bounded disconnect race"
            )
        closing_evidence.append(
            {
                "model_request_id": request_id,
                "product_attempt": row.get("product_attempt"),
                "started_monotonic_ns": start.get("monotonic_ns"),
                "completed_monotonic_ns": row.get("monotonic_ns"),
                "seconds_relative_to_proxy_stopped": round(
                    relative_seconds, 6
                ),
                "terminal_phase": (
                    "after_proxy_stopped"
                    if relative_seconds > 0
                    else "before_proxy_stopped"
                ),
                "success": False,
                "http_status": 502,
                "error_type": error_type,
            }
        )

    agent_ends = [
        row for row in adapter_rows if row.get("event") == "agent.execution_end"
    ]
    if len(agent_ends) != 1:
        raise ContractError("Hermes model-drain has no unique Agent terminal event")
    agent_end_ns = agent_ends[0].get("monotonic_ns")
    if not isinstance(agent_end_ns, int):
        raise ContractError("Hermes Agent terminal has no monotonic timestamp")

    budget = run.get("model_budget")
    failed = sum(row.get("success") is False for row in completions.values())
    if (
        not isinstance(budget, dict)
        or budget.get("provider_requests_forwarded") != len(starts)
        or budget.get("provider_requests_completed") != len(completions)
        or budget.get("provider_requests_failed") != failed
        or len(starts) != len(completions)
        or initial["provider_requests_forwarded"] != len(starts)
        or initial["provider_requests_completed"] + len(closing)
        != len(completions)
    ):
        raise ContractError("Hermes final model counters do not reconcile the drain")

    post_shutdown = [
        item
        for item in closing_evidence
        if item["terminal_phase"] == "after_proxy_stopped"
    ]
    pre_shutdown = [
        item
        for item in closing_evidence
        if item["terminal_phase"] == "before_proxy_stopped"
    ]
    return {
        "reconciliation_policy": HERMES_DRAIN_TIMEOUT_POLICY,
        "pre_proxy_shutdown_drain": initial,
        "proxy_stopped_monotonic_ns": stopped_ns,
        "agent_execution_end_monotonic_ns": agent_end_ns,
        "final_provider_requests_forwarded": len(starts),
        "final_provider_requests_completed": len(completions),
        "final_provider_requests_failed": failed,
        "snapshot_closing_terminal_count": len(closing_evidence),
        "snapshot_closing_terminals": closing_evidence,
        "pre_shutdown_terminal_count": len(pre_shutdown),
        "pre_shutdown_terminals": pre_shutdown,
        "post_shutdown_terminal_count": len(post_shutdown),
        "post_shutdown_terminals": post_shutdown,
        "all_forwarded_requests_have_unique_terminal_events": True,
        "formal_result_preserved": {
            "run_validity": run["run_validity"],
            "verify_status": run["verify_status"],
            "primary_failure_category": run.get("primary_failure_category"),
        },
    }


def _hermes_open_request_shutdown_evidence(
    model_rows: list[dict[str, Any]],
    adapter_rows: list[dict[str, Any]],
    run: dict[str, Any],
) -> dict[str, Any]:
    projected = (
        run.get("run_validity") == "infra_invalid"
        and run.get("verify_status") == "unavailable"
        and run.get("primary_failure_category") == "environment_error"
        and run.get("artifact_gate", {}).get("validator")
        == HERMES_OPEN_REQUEST_POLICY
    )
    if (
        run.get("system_id") != "hermes"
        or run.get("terminal_status") != "completed"
        or run.get("termination_reason") != "product_exit"
        or not (
            projected
            or (
                run.get("run_validity") == "valid"
                and run.get("verify_status") in {"pass", "no_pass"}
            )
        )
    ):
        raise ContractError(
            "open-request projection is not a completed Hermes attempt"
        )

    try:
        _BASE_MODEL_USAGE_VALIDATOR(model_rows, run)
    except ContractError as exc:
        if str(exc) != "one or more forwarded model requests have no terminal event":
            raise
    else:
        raise ContractError("Hermes open-request projection has no open request")

    starts = {
        str(row["model_request_id"]): row
        for row in model_rows
        if row.get("event") == "model_request.started"
    }
    completions = {
        str(row["model_request_id"]): row
        for row in model_rows
        if row.get("event") == "model_request.completed"
    }
    missing = sorted(set(starts) - set(completions))
    stopped = [row for row in model_rows if row.get("event") == "proxy.stopped"]
    if len(missing) != 1 or len(stopped) != 1:
        raise ContractError(
            "Hermes shutdown projection requires one open request and one proxy stop"
        )
    stopped_ns = stopped[0].get("monotonic_ns")
    if not isinstance(stopped_ns, int):
        raise ContractError("Hermes open-request proxy stop has no monotonic timestamp")
    if any(row.get("monotonic_ns", stopped_ns) > stopped_ns for row in starts.values()):
        raise ContractError("Hermes started a model request after proxy stop")

    adapter = run.get("adapter")
    drain = (
        adapter.get("post_terminal_model_drain")
        if isinstance(adapter, dict)
        else None
    )
    if not isinstance(drain, dict) or not isinstance(
        drain.get("provider_requests_forwarded"), int
    ):
        raise ContractError("Hermes open request has no drain snapshot")
    settled_race = (
        drain.get("settled") is True
        and drain.get("provider_requests_completed")
        == drain.get("provider_requests_forwarded")
    )
    timeout_open = (
        drain.get("settled") is False
        and drain.get("provider_requests_completed")
        == drain.get("provider_requests_forwarded") - 1
        and isinstance(drain.get("timeout_seconds"), (int, float))
        and isinstance(drain.get("wait_seconds"), (int, float))
        and drain["wait_seconds"] >= drain["timeout_seconds"] - 1
    )
    if not (settled_race or timeout_open):
        raise ContractError("Hermes open request drain boundary is inconsistent")

    request_id = missing[0]
    open_start = starts[request_id]
    start_ns = open_start.get("monotonic_ns")
    relative_seconds = (
        (start_ns - stopped_ns) / 1_000_000_000
        if isinstance(start_ns, int)
        else None
    )
    snapshot_count = drain["provider_requests_forwarded"]
    minimum_relative = -10 if settled_race else -float(drain["timeout_seconds"])
    expected_open_ordinal = snapshot_count + 1 if settled_race else snapshot_count
    if (
        relative_seconds is None
        or relative_seconds >= 0
        or relative_seconds < minimum_relative
        or open_start.get("provider_request") != expected_open_ordinal
        or open_start.get("product_attempt") != expected_open_ordinal
    ):
        raise ContractError(
            "Hermes open request is not the bounded post-drain shutdown race"
        )

    budget = run.get("model_budget")
    failed = sum(row.get("success") is False for row in completions.values())
    if (
        not isinstance(budget, dict)
        or budget.get("provider_requests_forwarded") != len(starts)
        or budget.get("provider_requests_completed") != len(completions)
        or budget.get("provider_requests_failed") != failed
        or len(starts) != (snapshot_count + 1 if settled_race else snapshot_count)
        or len(completions) != snapshot_count - (0 if settled_race else 1)
    ):
        raise ContractError("Hermes open-request final counters do not reconcile")

    agent_ends = [
        row for row in adapter_rows if row.get("event") == "agent.execution_end"
    ]
    if adapter_rows:
        if len(agent_ends) != 1 or not isinstance(
            agent_ends[0].get("monotonic_ns"), int
        ):
            raise ContractError("Hermes open-request projection has no Agent terminal")
        agent_end_ns = agent_ends[0]["monotonic_ns"]
    else:
        agent_end_ns = run.get("infrastructure_projection", {}).get(
            "agent_execution_end_monotonic_ns"
        )
        if not projected or not isinstance(agent_end_ns, int):
            raise ContractError("Hermes open-request projection lost Agent terminal")

    original_result = (
        run.get("infrastructure_projection", {}).get("original_formal_result")
        if projected
        else {
            "run_validity": run["run_validity"],
            "verify_status": run["verify_status"],
            "primary_failure_category": run.get("primary_failure_category"),
        }
    )
    if not isinstance(original_result, dict):
        raise ContractError("Hermes open-request original result is missing")
    return {
        "policy": HERMES_OPEN_REQUEST_POLICY,
        "drain_boundary": (
            "post_settled_shutdown_race" if settled_race else "drain_timeout_open_request"
        ),
        "settled_drain_snapshot": drain,
        "snapshot_provider_request_count": snapshot_count,
        "final_provider_requests_forwarded": len(starts),
        "final_provider_requests_completed": len(completions),
        "final_provider_requests_failed": failed,
        "open_request_count": 1,
        "open_request": {
            "model_request_id": request_id,
            "product_attempt": open_start.get("product_attempt"),
            "provider_request": open_start.get("provider_request"),
            "started_monotonic_ns": start_ns,
            "proxy_stopped_monotonic_ns": stopped_ns,
            "seconds_before_proxy_stopped": round(-relative_seconds, 6),
            "terminal_event_observed": False,
            "token_usage": {
                "value": None,
                "source": "provider_response",
                "reliability": "missing",
                "missing_reason": "request_unterminalized_at_proxy_shutdown",
            },
        },
        "agent_execution_end_monotonic_ns": agent_end_ns,
        "original_formal_result": original_result,
        "replacement_disposition": "eligible_infrastructure_a2_only",
    }


def _astra_agent_deadline_tool_evidence(
    trajectory_rows: list[dict[str, Any]], run: dict[str, Any]
) -> dict[str, Any]:
    if (
        run.get("system_id") != "astra"
        or run.get("terminal_status") != "timeout"
        or run.get("termination_reason") != "agent_deadline"
        or run.get("run_validity") != "valid"
        or run.get("verify_status") != "unavailable"
        or run.get("primary_failure_category") != "agent_deadline"
        or run.get("timeout") is not True
        or run.get("timeout_scope") != "agent"
        or not isinstance(run.get("deadline_s"), int)
        or run["deadline_s"] <= 0
        or not isinstance(run.get("agent_duration_seconds"), (int, float))
        or not (
            run["deadline_s"]
            <= run["agent_duration_seconds"]
            <= run["deadline_s"] + 15
        )
    ):
        raise ContractError("missing server declaration is not an Astra Agent deadline")

    budget = run.get("model_budget")
    if (
        not isinstance(budget, dict)
        or budget.get("max_requests") != 100
        or budget.get("limit_exceeded") is not False
        or budget.get("limit_rejections") != 0
        or not isinstance(budget.get("provider_requests_forwarded"), int)
        or budget["provider_requests_forwarded"] < 1
        or budget.get("provider_requests_completed")
        != budget["provider_requests_forwarded"] - 1
        or budget.get("product_attempts")
        != budget["provider_requests_forwarded"]
        or not isinstance(budget.get("provider_requests_failed"), int)
    ):
        raise ContractError("Astra Agent-deadline model counters are inconsistent")

    starts: dict[str, dict[str, Any]] = {}
    terminals: dict[str, dict[str, Any]] = {}
    declarations: list[int] = []
    for row in trajectory_rows:
        native = row.get("native")
        if not isinstance(native, dict):
            continue
        native_type = str(native.get("type", "")).lower()
        if native_type == "usage" and isinstance(native.get("tool_call_count"), int):
            declarations.append(native["tool_call_count"])
            continue
        if native_type not in {
            "tool_transport_started",
            "tool_transport_completed",
            "tool_transport_failed",
        }:
            continue
        call_id = native.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ContractError("Astra Agent-deadline transport has no call_id")
        target = starts if native_type == "tool_transport_started" else terminals
        if call_id in target:
            raise ContractError("Astra Agent-deadline duplicates a transport event")
        target[call_id] = native

    summary = run.get("trajectory")
    failed = sum(
        str(item.get("type", "")).lower() == "tool_transport_failed"
        for item in terminals.values()
    )
    if (
        declarations
        or not starts
        or set(starts) != set(terminals)
        or not isinstance(summary, dict)
        or summary.get("tool_started_events") != len(starts)
        or summary.get("tool_terminal_events") != len(terminals)
        or summary.get("tool_failed_events") != failed
        or summary.get("started_only_tool_calls") != 0
    ):
        raise ContractError("Astra Agent-deadline transport evidence is incomplete")
    return {
        "policy": ASTRA_DEADLINE_POLICY,
        "native_transport_started": len(starts),
        "native_transport_terminal": len(terminals),
        "native_transport_failed": failed,
        "all_native_transports_have_unique_terminal_events": True,
        "server_declared_tool_call_count": {
            "value": None,
            "source": "astra_server_usage_event",
            "reliability": "missing",
            "missing_reason": "agent_deadline_preempted_final_server_summary",
        },
        "formal_result_preserved": {
            "terminal_status": run["terminal_status"],
            "termination_reason": run["termination_reason"],
            "run_validity": run["run_validity"],
            "verify_status": run["verify_status"],
            "primary_failure_category": run["primary_failure_category"],
        },
        "replacement_disposition": "not_eligible_product_agent_deadline",
    }


def _astra_agent_deadline_model_evidence(
    model_rows: list[dict[str, Any]], run: dict[str, Any]
) -> dict[str, Any]:
    try:
        _BASE_MODEL_USAGE_VALIDATOR(model_rows, run)
    except ContractError as exc:
        if str(exc) != "one or more forwarded model requests have no terminal event":
            raise
    else:
        raise ContractError("Astra Agent deadline has no open model request")

    starts = {
        str(row["model_request_id"]): row
        for row in model_rows
        if row.get("event") == "model_request.started"
    }
    completions = {
        str(row["model_request_id"]): row
        for row in model_rows
        if row.get("event") == "model_request.completed"
    }
    missing = sorted(set(starts) - set(completions))
    stopped = [row for row in model_rows if row.get("event") == "proxy.stopped"]
    if len(missing) != 1 or len(stopped) != 1:
        raise ContractError(
            "Astra Agent deadline requires one open request and one proxy stop"
        )
    stopped_ns = stopped[0].get("monotonic_ns")
    if not isinstance(stopped_ns, int):
        raise ContractError("Astra Agent-deadline proxy stop has no timestamp")
    if any(row.get("monotonic_ns", stopped_ns) > stopped_ns for row in starts.values()):
        raise ContractError("Astra started a model request after proxy stop")
    if any(
        row.get("monotonic_ns", stopped_ns) > stopped_ns
        for row in completions.values()
    ):
        raise ContractError("Astra model request completed after proxy stop")

    ordered = sorted(
        row.get("provider_request") for row in starts.values()
    )
    if ordered != list(range(1, len(starts) + 1)):
        raise ContractError("Astra Agent-deadline provider requests are not contiguous")
    request_id = missing[0]
    open_start = starts[request_id]
    start_ns = open_start.get("monotonic_ns")
    drain = run.get("adapter", {}).get("post_terminal_model_drain")
    if (
        not isinstance(start_ns, int)
        or not isinstance(drain, dict)
        or drain.get("settled") is not False
        or drain.get("timeout_seconds") != 120.0
        or not isinstance(drain.get("wait_seconds"), (int, float))
        or drain["wait_seconds"] < drain["timeout_seconds"] - 1
        or drain.get("provider_requests_forwarded") != len(starts)
        or drain.get("provider_requests_completed") != len(completions)
        or not (0 < stopped_ns - start_ns <= 125_000_000_000)
        or open_start.get("provider_request") != len(starts)
        or open_start.get("product_attempt") != len(starts)
    ):
        raise ContractError(
            "Astra open request is not the bounded Agent-deadline drain request"
        )

    budget = run.get("model_budget")
    failed = sum(row.get("success") is False for row in completions.values())
    if (
        not isinstance(budget, dict)
        or budget.get("provider_requests_forwarded") != len(starts)
        or budget.get("provider_requests_completed") != len(completions)
        or budget.get("provider_requests_failed") != failed
    ):
        raise ContractError("Astra Agent-deadline final model counters differ")
    return {
        "final_provider_requests_forwarded": len(starts),
        "final_provider_requests_completed": len(completions),
        "final_provider_requests_failed": failed,
        "open_request_count": 1,
        "open_request": {
            "model_request_id": request_id,
            "product_attempt": open_start.get("product_attempt"),
            "provider_request": open_start.get("provider_request"),
            "started_monotonic_ns": start_ns,
            "proxy_stopped_monotonic_ns": stopped_ns,
            "seconds_before_proxy_stopped": round(
                (stopped_ns - start_ns) / 1_000_000_000, 6
            ),
            "terminal_event_observed": False,
            "token_usage": {
                "value": None,
                "source": "provider_response",
                "reliability": "missing",
                "missing_reason": "request_unterminalized_at_agent_deadline_shutdown",
            },
        },
        "post_terminal_model_drain": drain,
    }


def _astra_agent_deadline_boundary_evidence(
    adapter_rows: list[dict[str, Any]],
    model_rows: list[dict[str, Any]],
    run: dict[str, Any],
) -> dict[str, Any]:
    try:
        _BASE_AGENT_MODEL_BOUNDARY_VALIDATOR(adapter_rows, model_rows, run)
    except ContractError as exc:
        if str(exc) != "valid run has an unsettled post-terminal model drain":
            raise
    else:
        raise ContractError("Astra Agent deadline has no unsettled drain boundary")

    starts = [row for row in adapter_rows if row.get("event") == "agent.execution_start"]
    ends = [row for row in adapter_rows if row.get("event") == "agent.execution_end"]
    stops = [row for row in model_rows if row.get("event") == "proxy.stopped"]
    if len(starts) != 1 or len(ends) != 1 or len(stops) != 1:
        raise ContractError("Astra Agent-deadline boundary events are not unique")
    start_ns = starts[0].get("monotonic_ns")
    end_ns = ends[0].get("monotonic_ns")
    stop_ns = stops[0].get("monotonic_ns")
    deadline = starts[0].get("deadline_seconds")
    drain = run.get("adapter", {}).get("post_terminal_model_drain", {})
    timeout = drain.get("timeout_seconds")
    if (
        not isinstance(start_ns, int)
        or not isinstance(end_ns, int)
        or not isinstance(stop_ns, int)
        or deadline != run.get("deadline_s")
        or not isinstance(deadline, int)
        or not isinstance(timeout, (int, float))
        or ends[0].get("terminal_status") != "timeout"
        or ends[0].get("termination_reason") != "agent_deadline"
    ):
        raise ContractError("Astra Agent-deadline boundary metadata differs")
    deadline_ns = start_ns + deadline * 1_000_000_000
    maximum_stop_ns = deadline_ns + int(timeout + 15) * 1_000_000_000
    open_request = _astra_agent_deadline_model_evidence(model_rows, run)[
        "open_request"
    ]
    if (
        not (deadline_ns <= open_request["started_monotonic_ns"] < stop_ns)
        or not (deadline_ns <= stop_ns <= maximum_stop_ns)
        or not (stop_ns <= end_ns <= stop_ns + 10_000_000_000)
    ):
        raise ContractError("Astra server continuation is outside the deadline drain")
    return {
        "agent_execution_start_monotonic_ns": start_ns,
        "agent_deadline_monotonic_ns": deadline_ns,
        "agent_execution_end_monotonic_ns": end_ns,
        "proxy_stopped_monotonic_ns": stop_ns,
        "server_request_started_after_agent_deadline": True,
        "seconds_from_deadline_to_open_request": round(
            (open_request["started_monotonic_ns"] - deadline_ns)
            / 1_000_000_000,
            6,
        ),
        "seconds_from_deadline_to_proxy_stop": round(
            (stop_ns - deadline_ns) / 1_000_000_000, 6
        ),
    }


def _native_transport_evidence(
    trajectory_rows: list[dict[str, Any]], run: dict[str, Any]
) -> dict[str, Any]:
    if (
        run.get("system_id") != "astra"
        or run.get("terminal_status") != "max_steps"
        or run.get("termination_reason") != "max_model_requests"
        or run.get("run_validity") != "valid"
        or run.get("primary_failure_category") != "model_request_budget"
    ):
        raise ContractError("missing server declaration is not an Astra budget terminal")

    budget = run.get("model_budget")
    if not isinstance(budget, dict):
        raise ContractError("Astra budget terminal has no model budget evidence")
    if (
        budget.get("max_requests") != 100
        or budget.get("limit_exceeded") is not True
        or budget.get("provider_requests_forwarded") != 100
        or budget.get("provider_requests_completed") != 100
        or not isinstance(budget.get("provider_requests_failed"), int)
        or not isinstance(budget.get("product_attempts"), int)
        or budget["product_attempts"] < 100
        or not isinstance(budget.get("limit_rejections"), int)
        or budget["limit_rejections"] < 0
    ):
        raise ContractError("Astra budget terminal model counters are inconsistent")

    starts: dict[str, dict[str, Any]] = {}
    terminals: dict[str, dict[str, Any]] = {}
    declarations: set[int] = set()
    for row in trajectory_rows:
        native = row.get("native")
        if not isinstance(native, dict):
            continue
        native_type = str(native.get("type", "")).lower()
        if native_type == "usage" and isinstance(native.get("tool_call_count"), int):
            declarations.add(native["tool_call_count"])
            continue
        if native_type not in {
            "tool_transport_started",
            "tool_transport_completed",
            "tool_transport_failed",
        }:
            continue
        call_id = native.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ContractError("Astra budget terminal transport has no call_id")
        target = starts if native_type == "tool_transport_started" else terminals
        if call_id in target:
            raise ContractError("Astra budget terminal duplicates a transport event")
        target[call_id] = native

    if declarations:
        raise ContractError("Astra budget terminal unexpectedly has a server declaration")
    open_ids = sorted(set(starts) - set(terminals))
    if not starts or set(terminals) - set(starts) or len(open_ids) > 1:
        raise ContractError("Astra budget terminal transport evidence is not fully paired")
    if open_ids:
        last_native = next(
            (
                row.get("native")
                for row in reversed(trajectory_rows)
                if isinstance(row.get("native"), dict)
                and str(row["native"].get("type", "")).lower().startswith(
                    "tool_transport_"
                )
            ),
            None,
        )
        if (
            not isinstance(last_native, dict)
            or last_native.get("type") != "tool_transport_started"
            or last_native.get("call_id") != open_ids[0]
            or run.get("trajectory", {}).get("started_only_tool_calls") != 1
        ):
            raise ContractError("Astra budget terminal open transport boundary differs")
    return {
        "native_transport_started_count": len(starts),
        "native_transport_terminal_count": len(terminals),
        "open_transport_count": len(open_ids),
        "open_transport_call_id_sha256": (
            _sha256_text(open_ids[0]) if open_ids else None
        ),
        "run_disposition": "model_request_budget_terminal",
        "server_declared_model_tool_call_count": None,
        "server_declared_tool_call_count": {
            "value": None,
            "source": "astra_server_usage_event",
            "reliability": "missing",
            "missing_reason": "server_terminated_at_model_request_budget",
        },
    }


def install_artifact_gate_hotfix() -> Callable[..., None]:
    current = artifact_contract._validate_tool_event_completeness
    if getattr(current, "_toolathlon_budget_terminal_hotfix", False):
        return current

    original = current

    def validate(
        trajectory_rows: list[dict[str, Any]],
        tool_rows: list[dict[str, Any]],
        run: dict[str, Any],
    ) -> None:
        try:
            original(trajectory_rows, tool_rows, run)
        except ContractError as exc:
            if str(exc) == TRIGGER:
                # The frozen validator has already checked every normalized/native
                # event before raising at its optional server-summary cross-check.
                if (
                    run.get("system_id") == "astra"
                    and run.get("termination_reason") == "agent_deadline"
                ):
                    evidence = _astra_agent_deadline_tool_evidence(
                        trajectory_rows, run
                    )
                    run_id = run.get("run_id")
                    if not isinstance(run_id, str) or not run_id:
                        raise ContractError("Astra Agent-deadline run_id is missing")
                    _ASTRA_DEADLINE_BY_RUN_ID[run_id] = evidence
                    return
                evidence = _native_transport_evidence(trajectory_rows, run)
                if evidence.get("open_transport_count") == 1:
                    run_id = run.get("run_id")
                    if not isinstance(run_id, str) or not run_id:
                        raise ContractError("Astra budget terminal run_id is missing")
                    _COUNT_SCOPE_BY_RUN_ID[run_id] = evidence
                return
            if str(exc) == COUNT_SCOPE_TRIGGER:
                evidence = _astra_model_count_vs_transport_evidence(
                    trajectory_rows, run
                )
                run_id = run.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    raise ContractError("Astra tool-count scope run_id is missing")
                _COUNT_SCOPE_BY_RUN_ID[run_id] = evidence
                return
            raise

    setattr(validate, "_toolathlon_budget_terminal_hotfix", True)
    artifact_contract._validate_tool_event_completeness = validate
    return original


def install_model_usage_infra_hotfix() -> Callable[..., None]:
    current = artifact_contract._validate_model_usage
    if getattr(current, "_toolathlon_open_request_infra_hotfix", False):
        return current
    original = current

    def validate(
        model_rows: list[dict[str, Any]], run: dict[str, Any]
    ) -> None:
        try:
            original(model_rows, run)
        except ContractError as exc:
            run_id = str(run.get("run_id", ""))
            if (
                str(exc)
                == "one or more forwarded model requests have no terminal event"
                and run_id in _ASTRA_DEADLINE_BY_RUN_ID
            ):
                _ASTRA_DEADLINE_BY_RUN_ID[run_id].update(
                    _astra_agent_deadline_model_evidence(model_rows, run)
                )
                return
            if (
                str(exc)
                != "one or more forwarded model requests have no terminal event"
                or run.get("artifact_gate", {}).get("validator")
                != HERMES_OPEN_REQUEST_POLICY
            ):
                raise
            _hermes_open_request_shutdown_evidence(model_rows, [], run)

    setattr(validate, "_toolathlon_open_request_infra_hotfix", True)
    artifact_contract._validate_model_usage = validate
    return original


def install_agent_model_boundary_hotfix() -> Callable[..., None]:
    current = artifact_contract._validate_agent_model_boundary
    if getattr(current, "_toolathlon_astra_deadline_boundary_hotfix", False):
        return current
    original = current

    def validate(
        adapter_rows: list[dict[str, Any]],
        model_rows: list[dict[str, Any]],
        run: dict[str, Any],
    ) -> None:
        try:
            original(adapter_rows, model_rows, run)
        except ContractError as exc:
            run_id = str(run.get("run_id", ""))
            if (
                str(exc) != "valid run has an unsettled post-terminal model drain"
                or run_id not in _ASTRA_DEADLINE_BY_RUN_ID
            ):
                raise
            _ASTRA_DEADLINE_BY_RUN_ID[run_id].update(
                _astra_agent_deadline_boundary_evidence(
                    adapter_rows, model_rows, run
                )
            )

    setattr(validate, "_toolathlon_astra_deadline_boundary_hotfix", True)
    artifact_contract._validate_agent_model_boundary = validate
    return original


def _write_count_scope_artifact(
    directory: Path, run: dict[str, Any], evidence: dict[str, Any]
) -> Path:
    path = directory / COUNT_SCOPE_ARTIFACT
    record = {
        "schema_version": "toolathlon.astra-tool-count-observability.v1",
        "policy": COUNT_SCOPE_POLICY,
        "run_id": run["run_id"],
        "system_id": run["system_id"],
        "task_id": run["task_id"],
        "recorded_at": utc_now(),
        "raw_append_only_evidence_modified": False,
        "evidence": evidence,
    }
    write_json_atomic(path, record, mode=0o644)
    return path


def _rehash_attempt(directory: Path) -> None:
    hash_path = directory / "artifacts.sha256"
    candidates = [
        path
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != hash_path.name
    ]
    write_sha256_manifest(hash_path, candidates, root=directory)


def install_lifecycle_count_scope_hotfix(lifecycle_module: Any) -> Callable[..., Any]:
    current = lifecycle_module.SingleTaskLifecycle._finalize
    if getattr(current, "_toolathlon_count_scope_hotfix", False):
        return current
    original = current

    def finalize(self: Any) -> dict[str, Any]:
        validation = original(self)
        run_path = self.output / "run.json"
        run = read_json_object(run_path)
        evidence = _COUNT_SCOPE_BY_RUN_ID.get(str(run.get("run_id")))
        if evidence is None:
            return validation

        artifact = _write_count_scope_artifact(self.output, run, evidence)
        previous_gate = run["artifact_gate"]
        run["artifact_gate"] = {
            "status": "passed",
            "validator": COUNT_SCOPE_POLICY,
            "validated_at": utc_now(),
            "base_validator": previous_gate,
            "observability_artifact": artifact.name,
            "server_declared_model_tool_call_count": evidence[
                "server_declared_model_tool_call_count"
            ],
            "native_transport_terminal_count": evidence[
                "native_transport_terminal_count"
            ],
        }
        write_json_atomic(run_path, run, mode=0o644)
        self.lifecycle.append(
            "artifact_validation.observability_boundary",
            status="passed",
            policy=COUNT_SCOPE_POLICY,
            observability_artifact=artifact.name,
            server_declared_model_tool_call_count=evidence[
                "server_declared_model_tool_call_count"
            ],
            native_transport_terminal_count=evidence[
                "native_transport_terminal_count"
            ],
        )
        _rehash_attempt(self.output)
        return artifact_contract.validate_run_artifacts(self.output, verify_hash=True)

    setattr(finalize, "_toolathlon_count_scope_hotfix", True)
    lifecycle_module.SingleTaskLifecycle._finalize = finalize
    return original


def _write_astra_deadline_artifact(
    directory: Path, run: dict[str, Any], evidence: dict[str, Any]
) -> Path:
    path = directory / ASTRA_DEADLINE_ARTIFACT
    required = {
        "native_transport_started",
        "native_transport_terminal",
        "open_request",
        "agent_deadline_monotonic_ns",
        "proxy_stopped_monotonic_ns",
    }
    if not required.issubset(evidence):
        raise ContractError("Astra Agent-deadline evidence is incomplete")
    write_json_atomic(
        path,
        {
            "schema_version": "toolathlon.astra-agent-deadline-observability.v1",
            "policy": ASTRA_DEADLINE_POLICY,
            "run_id": run["run_id"],
            "system_id": run["system_id"],
            "task_id": run["task_id"],
            "recorded_at": utc_now(),
            "formal_attempt_rerun": False,
            "agent_rerun": False,
            "evaluator_rerun": False,
            "replacement_authorized": False,
            "raw_append_only_evidence_modified": False,
            "evidence": evidence,
        },
        mode=0o644,
    )
    return path


def install_lifecycle_astra_deadline_observability(
    lifecycle_module: Any,
) -> Callable[..., Any]:
    current = lifecycle_module.SingleTaskLifecycle._finalize
    if getattr(current, "_toolathlon_astra_deadline_observability", False):
        return current
    original = current

    def finalize(self: Any) -> dict[str, Any]:
        validation = original(self)
        run_path = self.output / "run.json"
        run = read_json_object(run_path)
        evidence = _ASTRA_DEADLINE_BY_RUN_ID.get(str(run.get("run_id")))
        if evidence is None:
            return validation
        artifact = _write_astra_deadline_artifact(self.output, run, evidence)
        previous_gate = run["artifact_gate"]
        run["artifact_gate"] = {
            "status": "passed",
            "validator": ASTRA_DEADLINE_POLICY,
            "validated_at": utc_now(),
            "base_validator": previous_gate,
            "observability_artifact": artifact.name,
            "formal_attempt_rerun": False,
            "replacement_authorized": False,
        }
        write_json_atomic(run_path, run, mode=0o644)
        self.lifecycle.append(
            "artifact_validation.observability_boundary",
            status="passed",
            policy=ASTRA_DEADLINE_POLICY,
            observability_artifact=artifact.name,
            formal_attempt_rerun=False,
            replacement_authorized=False,
        )
        _rehash_attempt(self.output)
        return artifact_contract.validate_run_artifacts(
            self.output, verify_hash=True
        )

    setattr(finalize, "_toolathlon_astra_deadline_observability", True)
    lifecycle_module.SingleTaskLifecycle._finalize = finalize
    return original


def install_formal_result_hotfix() -> Callable[[m2_batch.Attempt], None]:
    current = m2_batch.validate_formal_effective
    if getattr(current, "_toolathlon_budget_terminal_hotfix", False):
        return current

    original = current

    def validate(attempt: m2_batch.Attempt) -> None:
        try:
            original(attempt)
        except ContractError as exc:
            if str(exc) != FORMAL_TRIGGER:
                raise
            run = attempt.run
            if (
                run.get("artifact_gate", {}).get("validator")
                == ASTRA_DEADLINE_POLICY
            ):
                evidence = read_json_object(
                    attempt.directory / ASTRA_DEADLINE_ARTIFACT
                )
                evaluator = read_json_object(
                    attempt.directory / "evaluator/eval_res.json"
                )
                if (
                    evidence.get("policy") != ASTRA_DEADLINE_POLICY
                    or evidence.get("run_id") != run.get("run_id")
                    or evidence.get("formal_attempt_rerun") is not False
                    or evidence.get("replacement_authorized") is not False
                    or run.get("terminal_status") != "timeout"
                    or run.get("termination_reason") != "agent_deadline"
                    or run.get("run_validity") != "valid"
                    or run.get("verify_status") != "unavailable"
                    or run.get("primary_failure_category") != "agent_deadline"
                    or evaluator.get("pass") is not None
                ):
                    raise ContractError(
                        "Astra Agent-deadline formal evidence differs"
                    )
                return
            if run.get("primary_failure_category") == "model_request_budget":
                raise ContractError("budget-terminal evaluator replay is missing")
            if (
                run.get("system_id") in {"astra", "hermes"}
                and run.get("terminal_status") in {"crashed", "failed"}
                and run.get("termination_reason") == "product_exit"
                and run.get("run_validity") == "valid"
                and run.get("primary_failure_category") == "product_error"
                and run.get("verify_status") == "unavailable"
                and isinstance(run.get("evaluator_error"), dict)
                and run["evaluator_error"].get("reliability") == "observed"
            ):
                return
            raise

    setattr(validate, "_toolathlon_budget_terminal_hotfix", True)
    m2_batch.validate_formal_effective = validate
    return original


def _budget_terminal_model_state(spec: Any) -> dict[str, Any] | None:
    path = spec.output_dir / "model-proxy-state.json"
    if not path.is_file():
        return None
    state = read_json_object(path)
    budget = state.get("budget")
    if not isinstance(budget, dict):
        return None
    if (
        budget.get("max_requests") == 100
        and budget.get("limit_exceeded") is True
        and budget.get("provider_requests_forwarded") == 100
        and budget.get("provider_requests_completed") == 100
        and isinstance(budget.get("product_attempts"), int)
        and budget["product_attempts"] >= 100
        and isinstance(budget.get("provider_requests_failed"), int)
        and isinstance(budget.get("limit_rejections"), int)
        and budget["limit_rejections"] >= 0
    ):
        return budget
    return None


def install_budget_evaluator_hotfix() -> Callable[..., dict[str, Any]]:
    from astra.runners.toolathlon_verified import orchestrator

    current = orchestrator._run_evaluator
    if getattr(current, "_toolathlon_budget_terminal_hotfix", False):
        return current
    original = current

    def evaluate(*args: Any, **kwargs: Any) -> dict[str, Any]:
        spec = kwargs.get("spec")
        supplied_exit_code = kwargs.get("agent_exit_code")
        budget = _budget_terminal_model_state(spec) if spec is not None else None
        grading_exit_code = supplied_exit_code
        if budget is not None and supplied_exit_code != 0:
            # Toolathlon's trusted wrapper treats zero solely as grading
            # eligibility.  The product terminal remains max_model_requests in
            # run.json and the override is recorded as a separate artifact.
            grading_exit_code = 0
            kwargs["agent_exit_code"] = 0
        result = original(*args, **kwargs)
        if budget is not None and supplied_exit_code != grading_exit_code:
            evaluator_dir = spec.output_dir / "evaluator"
            write_json_atomic(
                evaluator_dir / "budget-terminal-grading-policy.json",
                {
                    "schema_version": "toolathlon.budget-terminal-grading-policy.v1",
                    "policy": EVALUATOR_POLICY,
                    "run_id": spec.run_id,
                    "system_id": spec.system_id,
                    "product_terminal_preserved": "max_model_requests",
                    "host_product_exit_code": supplied_exit_code,
                    "evaluator_grading_eligibility_exit_code": grading_exit_code,
                    "model_budget": budget,
                    "verify_status": result.get("verify_status"),
                    "recorded_at": utc_now(),
                },
                mode=0o644,
            )
        return result

    setattr(evaluate, "_toolathlon_budget_terminal_hotfix", True)
    orchestrator._run_evaluator = evaluate
    return original


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _docker_container_absence_evidence(container_id: str) -> dict[str, Any]:
    if (
        len(container_id) != 64
        or any(character not in "0123456789abcdef" for character in container_id)
    ):
        raise ContractError("interrupted preprocess container ID is invalid")
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", container_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContractError(
            "cannot prove interrupted preprocess container cleanup"
        ) from exc
    stderr = result.stderr.decode("utf-8", errors="replace")
    stderr_lower = stderr.lower()
    if result.returncode == 0:
        raise ContractError("interrupted preprocess container still exists")
    if result.returncode != 1 or not any(
        marker in stderr_lower
        for marker in ("no such object", "no such container")
    ):
        raise ContractError(
            "Docker inspect did not prove interrupted preprocess container absence"
        )
    return {
        "status": "absent_after_operator_cleanup",
        "container_id": container_id,
        "docker_inspect_returncode": result.returncode,
        "docker_inspect_stderr_sha256": hashlib.sha256(
            result.stderr
        ).hexdigest(),
        "observed_at": utc_now(),
    }


def _qualify_interrupted_preprocess_boundary(
    partial: Path,
    *,
    start: dict[str, Any],
    interrupted: dict[str, Any],
    lifecycle_events: list[dict[str, Any]],
) -> dict[str, Any]:
    run_id = INTERRUPTED_PREPROCESS_RUN_ID
    task_id = INTERRUPTED_PREPROCESS_TASK_ID
    if (
        start.get("run_id") != run_id
        or start.get("task_id") != task_id
        or start.get("system") != "hermes"
        or start.get("position") != INTERRUPTED_PREPROCESS_POSITION
        or start.get("attempt_ordinal") != 1
        or start.get("replacement_for_run_id") is not None
        or interrupted.get("run_id") != run_id
        or interrupted.get("task_id") != task_id
        or interrupted.get("system") != "hermes"
        or interrupted.get("position") != INTERRUPTED_PREPROCESS_POSITION
        or interrupted.get("attempt_ordinal") != 1
        or interrupted.get("error_type") != "KeyboardInterrupt"
    ):
        raise ContractError("interrupted preprocess scheduler identity differs")

    expected_events = [
        "reset.start",
        "reset.end",
        "container.start",
        "container.ready",
        "preprocess.start",
        "cleanup.start",
    ]
    if [row.get("event") for row in lifecycle_events] != expected_events:
        raise ContractError("interrupted preprocess lifecycle boundary differs")
    if [row.get("sequence") for row in lifecycle_events] != list(range(1, 7)):
        raise ContractError("interrupted preprocess lifecycle sequence differs")
    if any(
        row.get("run_id") != run_id or row.get("system_id") != "hermes"
        for row in lifecycle_events
    ):
        raise ContractError("interrupted preprocess lifecycle identity differs")
    if lifecycle_events[1].get("status") != "passed":
        raise ContractError("interrupted preprocess reset did not pass")

    expected_top_entries = {
        "lifecycle-events.jsonl",
        "resource-usage.jsonl",
        "task-state",
    }
    if {path.name for path in partial.iterdir()} != expected_top_entries:
        raise ContractError("interrupted preprocess partial surface differs")
    if not (partial / "task-state").is_dir():
        raise ContractError("interrupted preprocess task state is missing")
    task_state_path = partial / "task-state/status.json"
    task_state = read_json_object(task_state_path)
    if task_state != {"preprocess": "done", "running": None, "evaluation": None}:
        raise ContractError("interrupted preprocess task state differs")

    resource_rows = artifact_contract.read_jsonl(
        partial / "resource-usage.jsonl", allow_empty=False
    )
    for row in resource_rows:
        product = row.get("product")
        if (
            row.get("run_id") != run_id
            or row.get("system_id") != "hermes"
            or not isinstance(product, dict)
            or product.get("value") is not None
            or product.get("source") != "process_sampler"
            or product.get("reliability") != "missing"
            or product.get("missing_reason") != "process_not_started"
        ):
            raise ContractError(
                "a product process existed during interrupted preprocess"
            )

    container_id = lifecycle_events[3].get("container_id")
    if not isinstance(container_id, str):
        raise ContractError("interrupted preprocess container evidence is missing")
    return {
        "classification": INTERRUPTED_PREPROCESS_CLASSIFICATION,
        "container_cleanup": _docker_container_absence_evidence(container_id),
        "preprocess_started": True,
        "preprocess_completed": False,
        "preprocess_completion_source": "lifecycle_preprocess_end_missing",
        "preprocess_task_state_status": "done",
        "preprocess_task_state_sha256": sha256_file(task_state_path),
        "cleanup_started": True,
        "cleanup_completed": False,
        "model_proxy_started": False,
        "gateway_started": False,
        "tools_list_started": False,
        "agent_started": False,
        "evaluator_started": False,
        "state_restoration": "replacement_attempt_preprocess_required",
        "mutable_oauth_fingerprints_before": lifecycle_events[0].get(
            "mutable_oauth_fingerprints_before"
        ),
        "mutable_oauth_fingerprints_after": {
            "value": None,
            "source": "interrupted_lifecycle",
            "reliability": "missing",
            "missing_reason": "cleanup_end_not_recorded",
        },
    }


def install_interrupted_attempt_hotfix(
    output_root: Path,
    helper_path: Path,
    *,
    require_existing_projection: bool = False,
) -> list[str]:
    output_root = output_root.resolve()
    scheduler_rows = artifact_contract.read_jsonl(
        output_root / "scheduler-events.jsonl", allow_empty=False
    )
    recovery_base = output_root / "recovery-evidence/user-interrupted-hermes"
    # Materialize a recovery projection when the scheduler was interrupted
    # before a formal result existed. The original partial directory remains
    # append-only and is never rerun.
    for start in scheduler_rows:
        if not (
            start.get("event") == "attempt.start"
            and start.get("system") == "hermes"
            and start.get("attempt_ordinal") == 1
        ):
            continue
        run_id = str(start["run_id"])
        task_id = str(start["task_id"])
        partial = output_root / "runs" / "hermes" / task_id / run_id
        interrupted = [
            row for row in scheduler_rows
            if row.get("run_id") == run_id
            and row.get("event") == "attempt.process_interrupted"
        ]
        lifecycle_path = partial / "lifecycle-events.jsonl"
        if (
            len(interrupted) != 1
            or not partial.is_dir()
            or (partial / "run.json").exists()
            or not lifecycle_path.is_file()
        ):
            continue
        lifecycle_events = artifact_contract.read_jsonl(
            lifecycle_path, allow_empty=False
        )
        lifecycle_event_names = [row.get("event") for row in lifecycle_events]
        pre_agent_tools_list = lifecycle_event_names[-1:] == ["tools_list.start"]
        interrupted_preprocess = (
            run_id == INTERRUPTED_PREPROCESS_RUN_ID
            and task_id == INTERRUPTED_PREPROCESS_TASK_ID
            and lifecycle_event_names
            == [
                "reset.start",
                "reset.end",
                "container.start",
                "container.ready",
                "preprocess.start",
                "cleanup.start",
            ]
        )
        if not pre_agent_tools_list and not interrupted_preprocess:
            continue
        recovery_root = recovery_base / run_id
        recovery_root.mkdir(parents=True, exist_ok=True)
        record_path = recovery_root / "recovery.json"
        if not record_path.exists():
            if interrupted_preprocess:
                boundary = _qualify_interrupted_preprocess_boundary(
                    partial,
                    start=start,
                    interrupted=interrupted[0],
                    lifecycle_events=lifecycle_events,
                )
                validation_boundary = (
                    "during_preprocess_after_cleanup_start_before_cleanup_end"
                )
            else:
                boundary = {
                    "classification": (
                        "user_keyboard_interrupt_after_tools_list_start_before_agent"
                    ),
                    "gateway_started": True,
                    "tools_list_started": True,
                    "agent_started": False,
                    "evaluator_started": False,
                }
                validation_boundary = "after_tools_list_start_before_agent"
            write_json_atomic(record_path, {
                "schema_version": "toolathlon.user-interrupted-attempt-recovery.v1",
                "policy": INTERRUPTION_POLICY,
                "created_at": utc_now(),
                **boundary,
                "run_id": run_id, "system_id": "hermes", "task_id": task_id,
                "attempt_ordinal": 1, "replacement_for_run_id": None,
                "directory": str(partial),
                "partial_attempt_directory": str(partial),
                "partial_file_evidence": _partial_file_evidence(partial),
                "lifecycle_events": lifecycle_event_names,
                "lifecycle_events_sha256": sha256_file(lifecycle_path),
                "scheduler_start": start,
                "scheduler_process_interrupted": interrupted[0],
                "formal_run_artifacts_complete": False,
                "formal_attempt_rerun": False, "agent_rerun": False,
                "evaluator_rerun": False, "raw_append_only_evidence_modified": False,
                "partial_artifacts_modified": False,
                "replacement_eligible": True, "replacement_maximum": 1,
                "projected_run_validity": "infra_invalid",
                "projected_verify_status": "unavailable",
                "projected_primary_failure_category": "environment_error",
                "resume_disposition": "requires_controlled_a2_replacement; a1 must never be rerun",
                "helper": str(helper_path.resolve()),
                "helper_sha256": sha256_file(helper_path.resolve()),
                "validation": {
                    "status": "passed",
                    "boundary": validation_boundary,
                },
            }, mode=0o644)
    records = sorted(
        (output_root / "recovery-evidence/user-interrupted-hermes").glob(
            "*/recovery.json"
        )
    )
    if not records:
        return []

    virtual_by_partial: dict[Path, m2_batch.Attempt] = {}
    run_ids: list[str] = []
    for record_path in records:
        recovery = read_json_object(record_path)
        if (
            recovery.get("schema_version")
            != "toolathlon.user-interrupted-attempt-recovery.v1"
            or recovery.get("classification") not in {
                "user_initiated_keyboard_interrupt_after_agent_start",
                "user_keyboard_interrupt_after_tools_list_start_before_agent",
                INTERRUPTED_PREPROCESS_CLASSIFICATION,
            }
            or recovery.get("system_id") != "hermes"
            or recovery.get("evaluator_started") is not False
            or recovery.get("formal_run_artifacts_complete") is not False
            or recovery.get("resume_disposition")
            != "requires_controlled_a2_replacement; a1 must never be rerun"
        ):
            raise ContractError("user-interrupted Hermes recovery record is invalid")
        pre_agent_tools_list = (
            recovery.get("classification")
            == "user_keyboard_interrupt_after_tools_list_start_before_agent"
        )
        interrupted_preprocess = (
            recovery.get("classification")
            == INTERRUPTED_PREPROCESS_CLASSIFICATION
        )
        if interrupted_preprocess:
            container_cleanup = recovery.get("container_cleanup")
            if (
                recovery.get("run_id") != INTERRUPTED_PREPROCESS_RUN_ID
                or recovery.get("task_id") != INTERRUPTED_PREPROCESS_TASK_ID
                or recovery.get("preprocess_started") is not True
                or recovery.get("preprocess_completed") is not False
                or recovery.get("preprocess_completion_source")
                != "lifecycle_preprocess_end_missing"
                or recovery.get("preprocess_task_state_status") != "done"
                or not isinstance(
                    recovery.get("preprocess_task_state_sha256"), str
                )
                or recovery.get("cleanup_started") is not True
                or recovery.get("cleanup_completed") is not False
                or recovery.get("model_proxy_started") is not False
                or recovery.get("gateway_started") is not False
                or recovery.get("tools_list_started") is not False
                or recovery.get("agent_started") is not False
                or recovery.get("replacement_eligible") is not True
                or recovery.get("replacement_maximum") != 1
                or recovery.get("projected_run_validity") != "infra_invalid"
                or recovery.get("projected_verify_status") != "unavailable"
                or recovery.get("projected_primary_failure_category")
                != "environment_error"
                or recovery.get("state_restoration")
                != "replacement_attempt_preprocess_required"
                or not isinstance(container_cleanup, dict)
                or container_cleanup.get("status")
                != "absent_after_operator_cleanup"
                or recovery.get("validation", {}).get("status") != "passed"
                or recovery.get("validation", {}).get("boundary")
                != "during_preprocess_after_cleanup_start_before_cleanup_end"
            ):
                raise ContractError(
                    "interrupted preprocess recovery record differs"
                )
        elif pre_agent_tools_list:
            if (
                recovery.get("gateway_started") is not True
                or recovery.get("tools_list_started") is not True
                or recovery.get("agent_started") is not False
                or recovery.get("replacement_eligible") is not True
                or recovery.get("replacement_maximum") != 1
                or recovery.get("projected_run_validity") != "infra_invalid"
                or recovery.get("projected_verify_status") != "unavailable"
                or recovery.get("projected_primary_failure_category")
                != "environment_error"
                or recovery.get("validation", {}).get("status") != "passed"
            ):
                raise ContractError("pre-Agent tools-list interruption recovery differs")
        elif recovery.get("agent_started") is not True:
            raise ContractError("post-Agent interruption recovery differs")
        run_id = str(recovery.get("run_id"))
        task_id = str(recovery.get("task_id"))
        partial = Path(str(recovery.get("partial_attempt_directory"))).resolve()
        expected_partial = output_root / "runs" / "hermes" / task_id / run_id
        if partial != expected_partial.resolve() or not partial.is_dir():
            raise ContractError("user-interrupted Hermes partial directory differs")
        if (partial / "run.json").exists() or (partial / "artifacts.sha256").exists():
            raise ContractError("interrupted Hermes a1 unexpectedly became a formal run")
        evidence = recovery.get("partial_file_evidence")
        if not isinstance(evidence, dict) or not evidence:
            raise ContractError("interrupted Hermes partial hashes are missing")
        if interrupted_preprocess:
            if evidence != _partial_file_evidence(partial):
                raise ContractError(
                    "interrupted preprocess partial evidence changed"
                )
        else:
            for relative, item in evidence.items():
                path = partial / str(relative)
                if (
                    not isinstance(item, dict)
                    or not path.is_file()
                    or item.get("sha256") != sha256_file(path)
                    or item.get("size_bytes") != path.stat().st_size
                ):
                    raise ContractError(
                        f"interrupted Hermes partial evidence changed: {relative}"
                    )
        events = [
            row
            for row in scheduler_rows
            if row.get("run_id") == run_id
            and row.get("event")
            in {"attempt.start", "attempt.process_interrupted", "attempt.process_exit"}
        ]
        if [row.get("event") for row in events] != [
            "attempt.start",
            "attempt.process_interrupted",
        ]:
            raise ContractError("interrupted Hermes scheduler evidence is not unique")
        if events[0].get("attempt_ordinal") != 1:
            raise ContractError("interrupted Hermes attempt is not a1")

        resolved_path = partial / "resolved-config.json"
        if resolved_path.is_file():
            resolved = read_json_object(resolved_path)
        elif pre_agent_tools_list or interrupted_preprocess:
            manifest = read_json_object(output_root / "m3-batch-manifest.json")
            boundary = (
                "during_preprocess_after_cleanup_start_before_cleanup_end"
                if interrupted_preprocess
                else "after_tools_list_start_before_agent"
            )
            resolved = {
                "schema_version": "toolathlon.interrupted-resolved-projection.v1",
                "run_id": run_id,
                "freeze": manifest["freeze"],
                "projection": {
                    "formal_resolved_config_was_not_created": True,
                    "boundary": boundary,
                },
            }
        else:
            raise ContractError("interrupted Hermes resolved config is missing")
        recovery_root = record_path.parent
        synthetic_path = recovery_root / "interrupted-attempt.json"
        synthetic = {
            "schema_version": "toolathlon.interrupted-attempt.v1",
            "policy": INTERRUPTION_POLICY,
            "run_id": run_id,
            "system_id": "hermes",
            "task_id": task_id,
            "replacement_for_run_id": {
                "value": None,
                "source": "orchestrator_scheduling_record",
                "reliability": "missing",
                "missing_reason": "original_run",
            },
            "run_validity": "infra_invalid",
            "terminal_status": "interrupted",
            "termination_reason": "user_keyboard_interrupt",
            "verify_status": "unavailable",
            "primary_failure_category": "environment_error",
            "adapter": {
                "setup_provider_requests_before_agent": 0,
                "product_identity": {
                    "strategy": (
                        "product_process_not_started"
                        if pre_agent_tools_list or interrupted_preprocess
                        else "hermes_ephemeral_runtime_session"
                    ),
                    "attempt_session_id_sha256": None,
                    "identity_observation": {
                        "value": None,
                        "source": (
                            "interrupted_preprocess_boundary"
                            if interrupted_preprocess
                            else (
                                "pre_agent_tools_list_boundary"
                                if pre_agent_tools_list
                                else "interrupted_hermes_adapter"
                            )
                        ),
                        "reliability": "missing",
                        "missing_reason": "process_interrupted_before_identity_projection",
                    },
                },
            },
            "interruption_recovery": {
                "record": str(record_path),
                "record_sha256": sha256_file(record_path),
                "partial_directory": str(partial),
                "partial_artifacts_modified": False,
                "a1_must_never_be_rerun": True,
                "only_a2_replacement_allowed": True,
            },
        }
        if interrupted_preprocess:
            synthetic["interruption_recovery"]["classification"] = (
                INTERRUPTED_PREPROCESS_CLASSIFICATION
            )
            synthetic["interruption_recovery"]["state_restoration"] = (
                "replacement_attempt_preprocess_required"
            )
        if synthetic_path.exists():
            if read_json_object(synthetic_path) != synthetic:
                raise ContractError("interrupted attempt projection changed")
        elif require_existing_projection:
            raise ContractError(
                "interrupted attempt projection is missing from the qualified prior batch"
            )
        else:
            write_json_atomic(synthetic_path, synthetic, mode=0o644)
        artifact_manifest = recovery_root / "artifacts.sha256"
        artifact_files = [
            path
            for path in recovery_root.iterdir()
            if path.is_file() and path.name != artifact_manifest.name
        ]
        if require_existing_projection:
            if not artifact_manifest.is_file():
                raise ContractError(
                    "interrupted attempt artifact manifest is missing from the qualified prior batch"
                )
            expected_records = [
                (
                    sha256_file(path),
                    path.resolve().relative_to(recovery_root.resolve()).as_posix(),
                )
                for path in sorted(
                    (item.resolve() for item in artifact_files), key=str
                )
            ]
            expected_payload = "".join(
                f"{digest}  {relative}\n"
                for digest, relative in expected_records
            )
            if artifact_manifest.read_text(encoding="utf-8") != expected_payload:
                raise ContractError(
                    "interrupted attempt artifact manifest changed after qualification"
                )
        else:
            write_sha256_manifest(
                artifact_manifest,
                artifact_files,
                root=recovery_root,
            )
        virtual_by_partial[partial] = m2_batch.Attempt(
            directory=recovery_root,
            run=synthetic,
            resolved=resolved,
            validation={
                "schema_version": "toolathlon.interrupted-attempt.v1",
                "status": "qualified_for_a2_replacement_only",
                "formal_run_artifacts_complete": False,
            },
        )
        run_ids.append(run_id)

    aggregate_path = output_root / INTERRUPTION_RECOVERY_NAME
    observed_incidents = [read_json_object(path) for path in records]
    observed_by_run_id = {
        str(item.get("run_id")): item for item in observed_incidents
    }
    if len(observed_by_run_id) != len(observed_incidents):
        raise ContractError("interrupted attempt recovery run IDs are not unique")
    aggregate_changed = False
    if aggregate_path.exists():
        existing = read_json_object(aggregate_path)
        existing_incidents = existing.get("incidents")
        if (
            existing.get("schema_version")
            != "toolathlon.user-interrupted-attempt-recovery-summary.v1"
            or existing.get("policy") != INTERRUPTION_POLICY
            or not isinstance(existing_incidents, list)
            or existing.get("incident_count") != len(existing_incidents)
        ):
            raise ContractError("interrupted attempt recovery summary is invalid")
        existing_run_ids: set[str] = set()
        for incident in existing_incidents:
            if not isinstance(incident, dict):
                raise ContractError(
                    "interrupted attempt recovery history is invalid"
                )
            run_id = str(incident.get("run_id"))
            if run_id in existing_run_ids or observed_by_run_id.get(run_id) != incident:
                raise ContractError(
                    "interrupted attempt recovery history changed"
                )
            existing_run_ids.add(run_id)
        appended = [
            item
            for item in observed_incidents
            if str(item.get("run_id")) not in existing_run_ids
        ]
        aggregate_changed = bool(appended)
        aggregate = {
            **existing,
            "updated_at": utc_now(),
            "incident_count": len(existing_incidents) + len(appended),
            "incidents": [*existing_incidents, *appended],
            "helper": str(helper_path.resolve()),
            "helper_sha256": sha256_file(helper_path.resolve()),
        }
    else:
        aggregate = {
            "schema_version": (
                "toolathlon.user-interrupted-attempt-recovery-summary.v1"
            ),
            "policy": INTERRUPTION_POLICY,
            "created_at": utc_now(),
            "incident_count": len(observed_incidents),
            "incidents": observed_incidents,
            "helper": str(helper_path.resolve()),
            "helper_sha256": sha256_file(helper_path.resolve()),
        }
        aggregate_changed = True
    if aggregate_changed:
        write_json_atomic(aggregate_path, aggregate, mode=0o644)

    original_load = m2_batch.load_attempt

    def load(directory: Path, *, task_id: str, system: str) -> m2_batch.Attempt:
        virtual = virtual_by_partial.get(directory.resolve())
        if virtual is None:
            return original_load(directory, task_id=task_id, system=system)
        if task_id != virtual.run["task_id"] or system != "hermes":
            raise ContractError("interrupted attempt virtual identity mismatch")
        return virtual

    m2_batch.load_attempt = load

    original_identity = m2_batch._identity_key

    def identity(attempt: m2_batch.Attempt) -> tuple[str, str]:
        interruption = attempt.run.get("interruption_recovery")
        if isinstance(interruption, dict):
            run_id = str(attempt.run["run_id"])
            # This is an evidence-surrogate key, explicitly not a recovered
            # Hermes session fingerprint.  It prevents the missing observation
            # from weakening uniqueness checks for every observable attempt.
            return (
                f"unobserved-interrupted-identity:{run_id}",
                _sha256_text(f"missing-interrupted-session:{run_id}"),
            )
        return original_identity(attempt)

    m2_batch._identity_key = identity
    return run_ids


def _preprocess_partial_event_shape(directory: Path) -> bool:
    lifecycle_path = directory / "lifecycle-events.jsonl"
    if (directory / "run.json").exists() or not lifecycle_path.is_file():
        return False
    try:
        rows = artifact_contract.read_jsonl(lifecycle_path, allow_empty=False)
    except (ContractError, OSError):
        return False
    return [row.get("event") for row in rows] == [
        "reset.start",
        "reset.end",
        "container.start",
        "container.ready",
        "preprocess.start",
        "cleanup.start",
        "cleanup.end",
    ]


def _partial_file_evidence(directory: Path) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ContractError("preprocess partial evidence contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        evidence[relative] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    return evidence


def _qualify_preprocess_infrastructure_partial(
    output_root: Path,
    directory: Path,
    *,
    helper_path: Path,
    manifest: dict[str, Any],
    scheduler_rows: list[dict[str, Any]],
) -> Path:
    directory = directory.resolve()
    try:
        relative = directory.relative_to((output_root / "runs").resolve())
    except ValueError as exc:
        raise ContractError("preprocess partial directory escapes the runs root") from exc
    if len(relative.parts) != 3:
        raise ContractError("preprocess partial directory has an invalid slot path")
    system, task_id, run_id = relative.parts
    if system not in {"astra", "hermes"}:
        raise ContractError("preprocess partial system is invalid")

    top_entries = {path.name for path in directory.iterdir()}
    required_top = {
        "container.log",
        "lifecycle-events.jsonl",
        "preprocess.log",
        "resource-usage.jsonl",
        "task-state",
    }
    if not required_top.issubset(top_entries) or not top_entries.issubset(required_top):
        raise ContractError("preprocess partial file surface is not uniquely qualified")
    forbidden = {
        "resolved-config.json",
        "tool-schema-observed.json",
        "adapter-events.jsonl",
        "trajectory.jsonl",
        "tool-calls.jsonl",
        "model-usage.jsonl",
        "failure-evidence.json",
        "run.json",
        "artifacts.sha256",
    }
    if any((directory / name).exists() for name in forbidden):
        raise ContractError("preprocess partial unexpectedly contains formal run evidence")
    if (directory / "evaluator").exists():
        raise ContractError("preprocess partial unexpectedly reached the evaluator")

    lifecycle_rows = artifact_contract.read_jsonl(
        directory / "lifecycle-events.jsonl", allow_empty=False
    )
    event_names = [row.get("event") for row in lifecycle_rows]
    if event_names != [
        "reset.start",
        "reset.end",
        "container.start",
        "container.ready",
        "preprocess.start",
        "cleanup.start",
        "cleanup.end",
    ]:
        raise ContractError("preprocess partial lifecycle boundary is not unique")
    if [row.get("sequence") for row in lifecycle_rows] != list(range(1, 8)):
        raise ContractError("preprocess partial lifecycle sequence is not contiguous")
    if any(
        row.get("run_id") != run_id or row.get("system_id") != system
        for row in lifecycle_rows
    ):
        raise ContractError("preprocess partial lifecycle identity differs")
    reset_start, reset_end, container_start, _ready, _preprocess, _cleanup, cleanup_end = (
        lifecycle_rows
    )
    freeze = manifest.get("freeze")
    if not isinstance(freeze, dict):
        raise ContractError("batch freeze is missing for preprocess recovery")
    if (
        reset_end.get("status") != "passed"
        or cleanup_end.get("status") != "passed"
        or reset_end.get("baseline_sha256") != freeze.get("app_state_live_sha256")
        or container_start.get("image") != freeze.get("task_image_reference")
        or reset_start.get("mutable_oauth_fingerprints_before")
        != cleanup_end.get("mutable_oauth_fingerprints_after")
    ):
        raise ContractError("preprocess partial reset/cleanup boundary is not qualified")

    status = read_json_object(directory / "task-state/status.json")
    if status != {"preprocess": "fail", "running": None, "evaluation": None}:
        raise ContractError("Toolathlon task state is not an isolated preprocess failure")
    preprocess_text = (directory / "preprocess.log").read_text(
        encoding="utf-8", errors="replace"
    )
    if (
        "PreProcess command failed! returncode: 1" not in preprocess_text
        or "initialize_workspace" not in preprocess_text
    ):
        raise ContractError("preprocess failure log does not match Toolathlon boundary")

    resource_rows = artifact_contract.read_jsonl(
        directory / "resource-usage.jsonl", allow_empty=False
    )
    for row in resource_rows:
        if row.get("run_id") != run_id or row.get("system_id") != system:
            raise ContractError("preprocess resource evidence identity differs")
        product = row.get("product")
        if (
            not isinstance(product, dict)
            or product.get("value") is not None
            or product.get("missing_reason") != "process_not_started"
        ):
            raise ContractError("a product process existed during preprocess failure")

    relevant = [
        row
        for row in scheduler_rows
        if row.get("run_id") == run_id
        and row.get("event") in {
            "attempt.start",
            "attempt.process_exit",
            "attempt.process_interrupted",
        }
    ]
    if [row.get("event") for row in relevant] != [
        "attempt.start",
        "attempt.process_exit",
    ]:
        raise ContractError("preprocess scheduler boundary is not unique")
    start, process_exit = relevant
    ordinal = start.get("attempt_ordinal")
    replacement_for = start.get("replacement_for_run_id")
    dataset_repair_attempt = ordinal == 3
    if dataset_repair_attempt:
        repair_path = output_root / DATASET_REPAIR_NAME
        repair = read_json_object(repair_path)
        repair_incidents = repair.get("incidents")
        if (
            repair.get("policy") != DATASET_REPAIR_POLICY
            or not isinstance(repair_incidents, list)
            or len(repair_incidents) != 1
            or repair_incidents[0].get("repair_run_id") != run_id
            or task_id != DATASET_REPAIR_TASK
            or system != DATASET_REPAIR_SYSTEM
        ):
            raise ContractError("preprocess a3 is not an authorized dataset repair")
    if (
        ordinal not in {1, 2, 3}
        or process_exit.get("attempt_ordinal") != ordinal
        or process_exit.get("exit_code") != 1
        or any(
            row.get(field) != expected
            for row in (start, process_exit)
            for field, expected in (
                ("task_id", task_id),
                ("system", system),
            )
        )
        or (ordinal == 1 and replacement_for is not None)
        or (ordinal == 2 and not isinstance(replacement_for, str))
        or (ordinal == 3 and replacement_for is not None)
    ):
        raise ContractError("preprocess scheduler identity/replacement evidence differs")

    recovery_root = (
        output_root / "recovery-evidence/preprocess-infrastructure" / run_id
    )
    recovery_root.mkdir(parents=True, exist_ok=True)
    record_path = recovery_root / "recovery.json"
    if not record_path.exists():
        record = {
            "schema_version": "toolathlon.preprocess-infrastructure-recovery.v1",
            "policy": PREPROCESS_INFRA_POLICY,
            "created_at": utc_now(),
            "classification": "pre_agent_task_preprocess_infrastructure_failure",
            "run_id": run_id,
            "system_id": system,
            "task_id": task_id,
            "attempt_ordinal": ordinal,
            "replacement_for_run_id": replacement_for,
            "directory": str(directory),
            "partial_attempt_directory": str(directory),
            "partial_file_evidence": _partial_file_evidence(directory),
            "lifecycle_events": event_names,
            "lifecycle_events_sha256": sha256_file(
                directory / "lifecycle-events.jsonl"
            ),
            "preprocess_log_sha256": sha256_file(directory / "preprocess.log"),
            "task_state_sha256": sha256_file(directory / "task-state/status.json"),
            "scheduler_start": start,
            "scheduler_process_exit": process_exit,
            "task_config_sha256": reset_end.get("task_config_sha256"),
            "agent_started": False,
            "model_proxy_started": False,
            "gateway_started": False,
            "tools_list_started": False,
            "evaluator_started": False,
            "formal_run_artifacts_complete": False,
            "formal_attempt_rerun": False,
            "agent_rerun": False,
            "evaluator_rerun": False,
            "raw_append_only_evidence_modified": False,
            "partial_artifacts_modified": False,
            "projected_run_validity": "infra_invalid",
            "projected_verify_status": "unavailable",
            "projected_primary_failure_category": "environment_error",
            "replacement_eligible": ordinal == 1,
            "replacement_maximum": 1,
            "resume_disposition": (
                "requires_controlled_a2_replacement; a1 must never be rerun"
                if ordinal == 1
                else (
                    "the one allowed replacement is consumed; a task-specific "
                    "repair requires an explicit protocol amendment"
                    if ordinal == 2
                    else "the authorized dataset repair failed; no further attempt is allowed"
                )
            ),
            "helper": str(helper_path.resolve()),
            "helper_sha256": sha256_file(helper_path.resolve()),
            "validation": {
                "status": "passed",
                "boundary": "after_cleanup_before_gateway_agent_and_evaluator",
            },
        }
        write_json_atomic(record_path, record, mode=0o644)
    return record_path


def install_preprocess_infrastructure_hotfix(
    output_root: Path,
    helper_path: Path,
) -> list[str]:
    output_root = output_root.resolve()
    manifest_candidates = [
        output_root / "m3-batch-manifest.json",
        output_root / "m2-batch-manifest.json",
    ]
    manifest_path = next((path for path in manifest_candidates if path.is_file()), None)
    if manifest_path is None:
        return []
    manifest = read_json_object(manifest_path)
    scheduler_path = output_root / "scheduler-events.jsonl"
    if not scheduler_path.is_file():
        return []
    scheduler_rows = artifact_contract.read_jsonl(scheduler_path, allow_empty=False)

    runs_root = output_root / "runs"
    if runs_root.is_dir():
        for system_root in sorted(path for path in runs_root.iterdir() if path.is_dir()):
            for task_root in sorted(path for path in system_root.iterdir() if path.is_dir()):
                for directory in sorted(
                    path for path in task_root.iterdir() if path.is_dir()
                ):
                    if _preprocess_partial_event_shape(directory):
                        _qualify_preprocess_infrastructure_partial(
                            output_root,
                            directory,
                            helper_path=helper_path,
                            manifest=manifest,
                            scheduler_rows=scheduler_rows,
                        )

    records = sorted(
        (output_root / "recovery-evidence/preprocess-infrastructure").glob(
            "*/recovery.json"
        )
    )
    if not records:
        return []

    virtual_by_partial: dict[Path, m2_batch.Attempt] = {}
    incidents: list[dict[str, Any]] = []
    for record_path in records:
        recovery = read_json_object(record_path)
        if (
            recovery.get("schema_version")
            != "toolathlon.preprocess-infrastructure-recovery.v1"
            or recovery.get("policy") != PREPROCESS_INFRA_POLICY
            or recovery.get("classification")
            != "pre_agent_task_preprocess_infrastructure_failure"
            or recovery.get("agent_started") is not False
            or recovery.get("model_proxy_started") is not False
            or recovery.get("gateway_started") is not False
            or recovery.get("tools_list_started") is not False
            or recovery.get("evaluator_started") is not False
            or recovery.get("formal_run_artifacts_complete") is not False
            or recovery.get("formal_attempt_rerun") is not False
            or recovery.get("agent_rerun") is not False
            or recovery.get("evaluator_rerun") is not False
            or recovery.get("raw_append_only_evidence_modified") is not False
            or recovery.get("partial_artifacts_modified") is not False
            or recovery.get("projected_run_validity") != "infra_invalid"
            or recovery.get("projected_verify_status") != "unavailable"
            or recovery.get("projected_primary_failure_category")
            != "environment_error"
            or recovery.get("replacement_maximum") != 1
            or recovery.get("validation", {}).get("status") != "passed"
        ):
            raise ContractError("preprocess infrastructure recovery record is invalid")
        run_id = str(recovery.get("run_id"))
        system = str(recovery.get("system_id"))
        task_id = str(recovery.get("task_id"))
        ordinal = recovery.get("attempt_ordinal")
        replacement_for = recovery.get("replacement_for_run_id")
        partial = Path(str(recovery.get("partial_attempt_directory"))).resolve()
        expected_partial = output_root / "runs" / system / task_id / run_id
        if (
            partial != expected_partial.resolve()
            or not partial.is_dir()
            or ordinal not in {1, 2, 3}
            or (ordinal == 1 and replacement_for is not None)
            or (ordinal == 2 and not isinstance(replacement_for, str))
            or (ordinal == 3 and replacement_for is not None)
            or recovery.get("replacement_eligible") != (ordinal == 1)
        ):
            raise ContractError("preprocess recovery identity differs")
        evidence = recovery.get("partial_file_evidence")
        if not isinstance(evidence, dict) or not evidence:
            raise ContractError("preprocess partial hashes are missing")
        if evidence != _partial_file_evidence(partial):
            raise ContractError("preprocess partial evidence changed after qualification")

        recovery_root = record_path.parent
        replacement_observation = {
            "value": replacement_for,
            "source": "m3_scheduler.attempt.start",
            "reliability": "observed" if replacement_for is not None else "missing",
            "missing_reason": (
                None
                if replacement_for is not None
                else (
                    "dataset_repair_first_product_run"
                    if ordinal == 3
                    else "original_run"
                )
            ),
        }
        synthetic = {
            "schema_version": "toolathlon.preprocess-infrastructure-attempt.v1",
            "policy": PREPROCESS_INFRA_POLICY,
            "run_id": run_id,
            "system_id": system,
            "task_id": task_id,
            "replacement_for_run_id": replacement_observation,
            "run_validity": "infra_invalid",
            "terminal_status": "failed",
            "termination_reason": "preprocess_error",
            "verify_status": "unavailable",
            "primary_failure_category": "environment_error",
            "adapter": {
                "setup_provider_requests_before_agent": 0,
                "product_identity": {
                    "strategy": "product_process_not_started",
                    "attempt_session_id_sha256": None,
                    "identity_observation": {
                        "value": None,
                        "source": "preprocess_boundary",
                        "reliability": "missing",
                        "missing_reason": "product_process_not_started",
                    },
                },
            },
            "preprocess_infrastructure_recovery": {
                "record": str(record_path),
                "record_sha256": sha256_file(record_path),
                "partial_directory": str(partial),
                "partial_artifacts_modified": False,
                "a1_must_never_be_rerun": ordinal == 1,
                "only_a2_replacement_allowed": ordinal == 1,
                "no_a3_allowed": ordinal == 2,
            },
        }
        if ordinal == 3:
            synthetic["preprocess_infrastructure_recovery"][
                "no_further_attempt_allowed"
            ] = True
        resolved = {
            "schema_version": "toolathlon.preprocess-infrastructure-resolved.v1",
            "run_id": run_id,
            "freeze": manifest["freeze"],
            "projection": {
                "source": str(record_path),
                "formal_resolved_config_was_not_created": True,
            },
        }
        synthetic_path = recovery_root / "preprocess-attempt.json"
        resolved_path = recovery_root / "resolved-projection.json"
        if synthetic_path.exists():
            if read_json_object(synthetic_path) != synthetic:
                raise ContractError("preprocess attempt projection changed")
        else:
            write_json_atomic(synthetic_path, synthetic, mode=0o644)
        if resolved_path.exists():
            if read_json_object(resolved_path) != resolved:
                raise ContractError("preprocess resolved projection changed")
        else:
            write_json_atomic(resolved_path, resolved, mode=0o644)
        artifact_manifest = recovery_root / "artifacts.sha256"
        artifact_files = [record_path, synthetic_path, resolved_path]
        expected_manifest = "".join(
            f"{sha256_file(path)}  {path.name}\n" for path in sorted(artifact_files)
        )
        if artifact_manifest.exists():
            if artifact_manifest.read_text(encoding="utf-8") != expected_manifest:
                raise ContractError("preprocess projection artifact manifest changed")
        else:
            artifact_manifest.write_text(expected_manifest, encoding="utf-8")

        virtual_by_partial[partial] = m2_batch.Attempt(
            directory=recovery_root,
            run=synthetic,
            resolved=resolved,
            validation={
                "schema_version": "toolathlon.preprocess-infrastructure-attempt.v1",
                "status": (
                    "qualified_dataset_repair_failure_no_further_attempt"
                    if ordinal == 3
                    else "qualified_for_a2_replacement_only"
                ),
                "formal_run_artifacts_complete": False,
            },
        )
        incidents.append(recovery)

    aggregate_path = output_root / PREPROCESS_INFRA_RECOVERY_NAME
    aggregate_hash_path = output_root / PREPROCESS_INFRA_RECOVERY_HASH_NAME
    aggregate_changed = False
    if aggregate_path.exists():
        if not aggregate_hash_path.is_file():
            raise ContractError("preprocess recovery checksum is missing")
        expected = f"{sha256_file(aggregate_path)}  {aggregate_path.name}\n"
        if aggregate_hash_path.read_text(encoding="utf-8") != expected:
            raise ContractError("preprocess recovery checksum differs")
        aggregate = read_json_object(aggregate_path)
        existing_incidents = aggregate.get("incidents")
        if (
            aggregate.get("schema_version")
            != "toolathlon.preprocess-infrastructure-recovery-set.v1"
            or aggregate.get("policy") != PREPROCESS_INFRA_POLICY
            or not isinstance(existing_incidents, list)
            or aggregate.get("incident_count") != len(existing_incidents)
        ):
            raise ContractError("preprocess recovery aggregate is invalid")
        current_by_run = {
            str(item.get("run_id")): item
            for item in incidents
            if isinstance(item, dict)
        }
        for existing in existing_incidents:
            if (
                not isinstance(existing, dict)
                or current_by_run.get(str(existing.get("run_id"))) != existing
            ):
                raise ContractError(
                    "preprocess recovery aggregate history changed"
                )
        aggregate_changed = existing_incidents != incidents
        if aggregate_changed:
            aggregate = {
                **aggregate,
                "updated_at": utc_now(),
                "incident_count": len(incidents),
                "incidents": incidents,
            }
    else:
        aggregate = {
            "schema_version": "toolathlon.preprocess-infrastructure-recovery-set.v1",
            "policy": PREPROCESS_INFRA_POLICY,
            "created_at": utc_now(),
            "incident_count": len(incidents),
            "incidents": incidents,
        }
        aggregate_changed = True
    if aggregate_changed:
        write_json_atomic(aggregate_path, aggregate, mode=0o644)
        aggregate_hash_path.write_text(
            f"{sha256_file(aggregate_path)}  {aggregate_path.name}\n",
            encoding="utf-8",
        )

    original_load = m2_batch.load_attempt

    def load(directory: Path, *, task_id: str, system: str) -> m2_batch.Attempt:
        virtual = virtual_by_partial.get(directory.resolve())
        if virtual is None:
            return original_load(directory, task_id=task_id, system=system)
        if task_id != virtual.run["task_id"] or system != virtual.run["system_id"]:
            raise ContractError("preprocess attempt virtual identity mismatch")
        return virtual

    m2_batch.load_attempt = load

    original_identity = m2_batch._identity_key

    def identity(attempt: m2_batch.Attempt) -> tuple[str, str]:
        recovery = attempt.run.get("preprocess_infrastructure_recovery")
        if isinstance(recovery, dict):
            run_id = str(attempt.run["run_id"])
            return (
                f"unobserved-preprocess-identity:{run_id}",
                _sha256_text(f"missing-preprocess-product-identity:{run_id}"),
            )
        return original_identity(attempt)

    m2_batch._identity_key = identity
    return sorted(virtual.run["run_id"] for virtual in virtual_by_partial.values())


def _task_tracker_setup_run_ids(
    manifest: dict[str, Any],
) -> tuple[str, str, str]:
    batch_id = manifest.get("batch_id")
    retry = manifest.get("retry")
    tasks = manifest.get("tasks")
    task_rows = [
        item
        for item in tasks if isinstance(item, dict)
        and item.get("task_id") == TASK_TRACKER_SETUP_TASK
    ] if isinstance(tasks, list) else []
    if (
        not isinstance(batch_id, str)
        or not batch_id
        or not isinstance(retry, dict)
        or retry.get("automatic_replacement_maximum") != 1
        or len(task_rows) != 1
        or task_rows[0].get("formal_position") != TASK_TRACKER_SETUP_POSITION
        or task_rows[0].get("system_order") != ["astra", "hermes"]
    ):
        raise ContractError(
            "task-tracker setup recovery requires the frozen M3 slot"
        )
    prefix = (
        f"{batch_id}-{TASK_TRACKER_SETUP_POSITION:02d}-"
        f"{TASK_TRACKER_SETUP_TASK}-{TASK_TRACKER_SETUP_SYSTEM}"
    )
    run_ids = tuple(f"{prefix}-a{ordinal}" for ordinal in (1, 2, 3))
    if run_ids[0] != INTERRUPTED_PREPROCESS_RUN_ID:
        raise ContractError("task-tracker setup recovery batch identity differs")
    return run_ids  # type: ignore[return-value]


def qualify_task_tracker_container_setup_recovery(
    output_root: Path,
    helper_path: Path,
) -> Path:
    """Qualify the bounded a2 Docker-copy failure authorized for one a3."""
    output_root = output_root.resolve()
    manifest = read_json_object(output_root / "m3-batch-manifest.json")
    a1_run_id, a2_run_id, a3_run_id = _task_tracker_setup_run_ids(manifest)
    partial = (
        output_root
        / "runs"
        / TASK_TRACKER_SETUP_SYSTEM
        / TASK_TRACKER_SETUP_TASK
        / a2_run_id
    ).resolve()
    record_path = output_root / TASK_TRACKER_SETUP_RECOVERY_NAME
    hash_path = output_root / TASK_TRACKER_SETUP_RECOVERY_HASH_NAME

    if record_path.is_file() or hash_path.is_file():
        if not record_path.is_file() or not hash_path.is_file():
            raise ContractError("task-tracker setup recovery is incomplete")
        record = read_json_object(record_path)
        incidents = record.get("incidents")
        expected_manifest = f"{sha256_file(record_path)}  {record_path.name}\n"
        if (
            record.get("schema_version")
            != "toolathlon.task-tracker-container-setup-recovery.v1"
            or record.get("policy") != TASK_TRACKER_SETUP_POLICY
            or not isinstance(incidents, list)
            or len(incidents) != 1
            or hash_path.read_text(encoding="utf-8") != expected_manifest
        ):
            raise ContractError("task-tracker setup recovery differs")
        incident = incidents[0]
        if (
            not isinstance(incident, dict)
            or incident.get("run_id") != a2_run_id
            or incident.get("authorized_recovery_run_id") != a3_run_id
            or incident.get("partial_file_evidence")
            != _partial_file_evidence(partial)
            or incident.get("validation", {}).get("status") != "passed"
        ):
            raise ContractError(
                "task-tracker setup recovery evidence changed"
            )
        return record_path

    if not partial.is_dir():
        raise ContractError("task-tracker a2 partial directory is unavailable")
    top_entries = {path.name for path in partial.iterdir()}
    expected_top = {
        "container.log",
        "lifecycle-events.jsonl",
        "resource-usage.jsonl",
        "task-state",
    }
    if top_entries != expected_top:
        raise ContractError("task-tracker a2 partial surface differs")
    task_state = partial / "task-state"
    if not task_state.is_dir() or any(task_state.iterdir()):
        raise ContractError("task-tracker a2 unexpectedly reached preprocess state")
    if (partial / "container.log").stat().st_size != 0:
        raise ContractError("task-tracker a2 unexpectedly produced container output")
    forbidden = {
        "preprocess.log",
        "resolved-config.json",
        "tool-schema-observed.json",
        "adapter-events.jsonl",
        "trajectory.jsonl",
        "tool-calls.jsonl",
        "model-usage.jsonl",
        "failure-evidence.json",
        "run.json",
        "artifacts.sha256",
    }
    if any((partial / name).exists() for name in forbidden) or (
        partial / "evaluator"
    ).exists():
        raise ContractError("task-tracker a2 reached a forbidden formal stage")

    lifecycle_path = partial / "lifecycle-events.jsonl"
    lifecycle_rows = artifact_contract.read_jsonl(
        lifecycle_path, allow_empty=False
    )
    event_names = [row.get("event") for row in lifecycle_rows]
    expected_events = [
        "reset.start",
        "reset.end",
        "container.start",
        "container.ready",
        "cleanup.start",
        "cleanup.end",
    ]
    if (
        event_names != expected_events
        or [row.get("sequence") for row in lifecycle_rows]
        != list(range(1, 7))
        or any(
            row.get("run_id") != a2_run_id
            or row.get("system_id") != TASK_TRACKER_SETUP_SYSTEM
            for row in lifecycle_rows
        )
    ):
        raise ContractError("task-tracker a2 lifecycle boundary differs")
    reset_start, reset_end, container_start, ready, _cleanup, cleanup_end = (
        lifecycle_rows
    )
    freeze = manifest.get("freeze")
    container_id = ready.get("container_id")
    if (
        not isinstance(freeze, dict)
        or reset_start.get("required_mcp_servers") != ["github", "notion"]
        or reset_start.get("task_preprocess_present") is not True
        or reset_end.get("status") != "passed"
        or reset_end.get("baseline_sha256") != freeze.get("app_state_live_sha256")
        or container_start.get("image") != freeze.get("task_image_reference")
        or not isinstance(container_id, str)
        or ready.get("mcp_auth_bind_mounted") is not True
        or cleanup_end.get("status") != "passed"
        or reset_start.get("mutable_oauth_fingerprints_before")
        != cleanup_end.get("mutable_oauth_fingerprints_after")
    ):
        raise ContractError("task-tracker a2 reset/container boundary differs")

    resource_path = partial / "resource-usage.jsonl"
    resource_rows = artifact_contract.read_jsonl(resource_path, allow_empty=False)
    one_minute_loads: list[float] = []
    memory_available: list[int] = []
    swap_free: list[int] = []
    for row in resource_rows:
        product = row.get("product")
        vm = row.get("vm")
        load = vm.get("load_average") if isinstance(vm, dict) else None
        if (
            row.get("run_id") != a2_run_id
            or row.get("system_id") != TASK_TRACKER_SETUP_SYSTEM
            or not isinstance(product, dict)
            or product.get("value") is not None
            or product.get("missing_reason") != "process_not_started"
            or not isinstance(vm, dict)
            or not isinstance(load, list)
            or len(load) != 3
            or not isinstance(load[0], (int, float))
            or not isinstance(vm.get("memory_available_bytes"), int)
            or not isinstance(vm.get("swap_free_bytes"), int)
        ):
            raise ContractError("task-tracker a2 resource evidence differs")
        one_minute_loads.append(float(load[0]))
        memory_available.append(int(vm["memory_available_bytes"]))
        swap_free.append(int(vm["swap_free_bytes"]))
    resource_pressure = {
        "sample_count": len(resource_rows),
        "max_load_average_1m": max(one_minute_loads),
        "min_memory_available_bytes": min(memory_available),
        "min_swap_free_bytes": min(swap_free),
        "resource_usage_sha256": sha256_file(resource_path),
    }
    if (
        resource_pressure["max_load_average_1m"] < 32
        or resource_pressure["min_swap_free_bytes"] >= 134217728
    ):
        raise ContractError(
            "task-tracker a2 does not show the authorized host pressure boundary"
        )

    scheduler_path = output_root / "scheduler-events.jsonl"
    scheduler_rows = artifact_contract.read_jsonl(scheduler_path, allow_empty=False)
    relevant = [
        row
        for row in scheduler_rows
        if row.get("run_id") == a2_run_id
        and row.get("event")
        in {"attempt.start", "attempt.process_exit", "attempt.process_interrupted"}
    ]
    if [row.get("event") for row in relevant] != [
        "attempt.start",
        "attempt.process_exit",
    ]:
        raise ContractError("task-tracker a2 scheduler boundary is not unique")
    start, process_exit = relevant
    if (
        start.get("position") != TASK_TRACKER_SETUP_POSITION
        or start.get("task_id") != TASK_TRACKER_SETUP_TASK
        or start.get("system") != TASK_TRACKER_SETUP_SYSTEM
        or start.get("attempt_ordinal") != 2
        or start.get("replacement_for_run_id") != a1_run_id
        or process_exit.get("position") != TASK_TRACKER_SETUP_POSITION
        or process_exit.get("task_id") != TASK_TRACKER_SETUP_TASK
        or process_exit.get("system") != TASK_TRACKER_SETUP_SYSTEM
        or process_exit.get("attempt_ordinal") != 2
        or process_exit.get("exit_code") != 1
    ):
        raise ContractError("task-tracker a2 scheduler identity differs")

    interruption_path = (
        output_root
        / "recovery-evidence/user-interrupted-hermes"
        / a1_run_id
        / "recovery.json"
    )
    interruption = read_json_object(interruption_path)
    if (
        interruption.get("policy") != INTERRUPTION_POLICY
        or interruption.get("classification")
        != INTERRUPTED_PREPROCESS_CLASSIFICATION
        or interruption.get("run_id") != a1_run_id
        or interruption.get("agent_started") is not False
        or interruption.get("model_proxy_started") is not False
        or interruption.get("evaluator_started") is not False
        or interruption.get("validation", {}).get("status") != "passed"
    ):
        raise ContractError("task-tracker a1 interruption is not qualified")

    checkpoint_path = output_root / "checkpoint.json"
    checkpoint = read_json_object(checkpoint_path)
    checkpoint_error = str(checkpoint.get("error"))
    if (
        checkpoint.get("status") != "blocked"
        or checkpoint.get("error_type") != "M2Blocked"
        or str(partial) not in checkpoint_error
        or "required run artifacts are missing" not in checkpoint_error
    ):
        raise ContractError("task-tracker a2 blocked checkpoint differs")

    incident = {
        "policy": TASK_TRACKER_SETUP_POLICY,
        "classification": (
            "docker_copy_boundary_failure_under_host_resource_pressure"
        ),
        "task_id": TASK_TRACKER_SETUP_TASK,
        "system_id": TASK_TRACKER_SETUP_SYSTEM,
        "position": TASK_TRACKER_SETUP_POSITION,
        "directory": str(partial),
        "run_id": a2_run_id,
        "attempt_ordinal": 2,
        "replacement_for_run_id": a1_run_id,
        "failed_pre_agent_run_ids": [a1_run_id, a2_run_id],
        "authorized_recovery_run_id": a3_run_id,
        "authorized_scheduler_ordinal": 3,
        "authorized_product_attempt_ordinal": 1,
        "authorized_replacement_for_run_id": None,
        "container_started": True,
        "container_ready": True,
        "preprocess_started": False,
        "gateway_started": False,
        "tools_list_started": False,
        "agent_started": False,
        "product_started": False,
        "model_proxy_started": False,
        "evaluator_started": False,
        "formal_run_artifacts_complete": False,
        "projected_run_validity": "infra_invalid",
        "projected_verify_status": "unavailable",
        "projected_primary_failure_category": "environment_error",
        "partial_file_evidence": _partial_file_evidence(partial),
        "lifecycle_events": event_names,
        "lifecycle_events_sha256": sha256_file(lifecycle_path),
        "resource_pressure": resource_pressure,
        "container_cleanup": _docker_container_absence_evidence(container_id),
        "scheduler_start": start,
        "scheduler_process_exit": process_exit,
        "blocked_checkpoint_sha256": sha256_file(checkpoint_path),
        "a1_interruption_recovery": {
            "path": str(interruption_path),
            "sha256": sha256_file(interruption_path),
        },
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "raw_append_only_evidence_modified": False,
        "failed_attempt_directories_modified": False,
        "general_automatic_replacement_maximum": 1,
        "general_retry_policy_modified": False,
        "task_specific_container_setup_recovery_maximum": 1,
        "no_a4_allowed": True,
        "authorization": "user_confirmed_task_specific_a3_recovery",
        "validation": {
            "status": "passed",
            "boundary": "after_container_ready_before_preprocess_start",
            "fairness": (
                "a1 and a2 started no Agent, product, model request, or evaluator"
            ),
        },
    }
    record = {
        "schema_version": (
            "toolathlon.task-tracker-container-setup-recovery.v1"
        ),
        "policy": TASK_TRACKER_SETUP_POLICY,
        "created_at": utc_now(),
        "incident_count": 1,
        "incidents": [incident],
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
    }
    write_json_atomic(record_path, record, mode=0o644)
    hash_path.write_text(
        f"{sha256_file(record_path)}  {record_path.name}\n",
        encoding="utf-8",
    )
    return record_path


def install_task_tracker_container_setup_projection(
    output_root: Path,
    recovery_path: Path,
) -> None:
    output_root = output_root.resolve()
    recovery = read_json_object(recovery_path)
    incident = recovery["incidents"][0]
    if (
        recovery.get("policy") != TASK_TRACKER_SETUP_POLICY
        or incident.get("authorization")
        != "user_confirmed_task_specific_a3_recovery"
        or incident.get("validation", {}).get("status") != "passed"
    ):
        raise ContractError("task-tracker setup projection is unauthorized")
    run_id = str(incident["run_id"])
    partial = Path(str(incident["directory"])).resolve()
    manifest = read_json_object(output_root / "m3-batch-manifest.json")
    a1_run_id, a2_run_id, _a3_run_id = _task_tracker_setup_run_ids(manifest)
    if run_id != a2_run_id or partial != (
        output_root
        / "runs"
        / TASK_TRACKER_SETUP_SYSTEM
        / TASK_TRACKER_SETUP_TASK
        / a2_run_id
    ).resolve():
        raise ContractError("task-tracker setup projection identity differs")
    if incident.get("partial_file_evidence") != _partial_file_evidence(partial):
        raise ContractError("task-tracker setup partial evidence changed")

    recovery_root = (
        output_root
        / "recovery-evidence/task-tracker-container-setup"
        / a2_run_id
    )
    recovery_root.mkdir(parents=True, exist_ok=True)
    synthetic = {
        "schema_version": "toolathlon.task-tracker-container-setup-attempt.v1",
        "policy": TASK_TRACKER_SETUP_POLICY,
        "run_id": a2_run_id,
        "system_id": TASK_TRACKER_SETUP_SYSTEM,
        "task_id": TASK_TRACKER_SETUP_TASK,
        "replacement_for_run_id": {
            "value": a1_run_id,
            "source": "m3_scheduler.attempt.start",
            "reliability": "observed",
            "missing_reason": None,
        },
        "run_validity": "infra_invalid",
        "terminal_status": "failed",
        "termination_reason": "container_setup_error",
        "verify_status": "unavailable",
        "primary_failure_category": "environment_error",
        "adapter": {
            "setup_provider_requests_before_agent": 0,
            "product_identity": {
                "strategy": "product_process_not_started",
                "attempt_session_id_sha256": None,
                "identity_observation": {
                    "value": None,
                    "source": "container_setup_boundary",
                    "reliability": "missing",
                    "missing_reason": "product_process_not_started",
                },
            },
        },
        "task_tracker_container_setup_recovery": {
            "record": str(recovery_path),
            "record_sha256": sha256_file(recovery_path),
            "partial_directory": str(partial),
            "partial_artifacts_modified": False,
            "only_task_specific_a3_allowed": True,
            "no_a4_allowed": True,
        },
    }
    resolved = {
        "schema_version": "toolathlon.task-tracker-container-setup-resolved.v1",
        "run_id": a2_run_id,
        "freeze": manifest["freeze"],
        "projection": {
            "source": str(recovery_path),
            "formal_resolved_config_was_not_created": True,
        },
    }
    reference = {
        "schema_version": "toolathlon.task-tracker-container-setup-reference.v1",
        "path": str(recovery_path),
        "sha256": sha256_file(recovery_path),
        "partial_directory": str(partial),
        "partial_file_evidence_sha256": hashlib.sha256(
            json.dumps(
                incident["partial_file_evidence"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    synthetic_path = recovery_root / "container-setup-attempt.json"
    resolved_path = recovery_root / "resolved-projection.json"
    reference_path = recovery_root / "recovery-reference.json"
    for path, payload in (
        (synthetic_path, synthetic),
        (resolved_path, resolved),
        (reference_path, reference),
    ):
        if path.exists():
            if read_json_object(path) != payload:
                raise ContractError("task-tracker setup projection changed")
        else:
            write_json_atomic(path, payload, mode=0o644)
    artifact_manifest = recovery_root / "artifacts.sha256"
    artifact_files = [reference_path, resolved_path, synthetic_path]
    expected_manifest = "".join(
        f"{sha256_file(path)}  {path.name}\n" for path in sorted(artifact_files)
    )
    if artifact_manifest.exists():
        if artifact_manifest.read_text(encoding="utf-8") != expected_manifest:
            raise ContractError("task-tracker setup projection manifest changed")
    else:
        artifact_manifest.write_text(expected_manifest, encoding="utf-8")

    virtual = m2_batch.Attempt(
        directory=recovery_root,
        run=synthetic,
        resolved=resolved,
        validation={
            "schema_version": (
                "toolathlon.task-tracker-container-setup-attempt.v1"
            ),
            "status": "qualified_for_task_specific_a3_only",
            "formal_run_artifacts_complete": False,
        },
    )
    original_load = m2_batch.load_attempt

    def load(directory: Path, *, task_id: str, system: str) -> m2_batch.Attempt:
        if directory.resolve() != partial:
            return original_load(directory, task_id=task_id, system=system)
        if task_id != TASK_TRACKER_SETUP_TASK or system != TASK_TRACKER_SETUP_SYSTEM:
            raise ContractError("task-tracker setup virtual identity differs")
        if incident.get("partial_file_evidence") != _partial_file_evidence(partial):
            raise ContractError("task-tracker setup partial evidence changed")
        return virtual

    m2_batch.load_attempt = load
    original_identity = m2_batch._identity_key

    def identity(attempt: m2_batch.Attempt) -> tuple[str, str]:
        projection = attempt.run.get("task_tracker_container_setup_recovery")
        if isinstance(projection, dict):
            return (
                f"unobserved-task-tracker-setup-identity:{run_id}",
                _sha256_text(f"missing-task-tracker-product-identity:{run_id}"),
            )
        return original_identity(attempt)

    m2_batch._identity_key = identity


def install_task_tracker_container_setup_scheduler_hotfix(
    output_root: Path,
    recovery_path: Path,
) -> None:
    output_root = output_root.resolve()
    manifest = read_json_object(output_root / "m3-batch-manifest.json")
    a1_run_id, a2_run_id, a3_run_id = _task_tracker_setup_run_ids(manifest)
    recovery = read_json_object(recovery_path)
    incident = recovery["incidents"][0]
    if (
        recovery.get("policy") != TASK_TRACKER_SETUP_POLICY
        or incident.get("run_id") != a2_run_id
        or incident.get("authorized_recovery_run_id") != a3_run_id
        or incident.get("no_a4_allowed") is not True
    ):
        raise ContractError("task-tracker setup scheduler authorization differs")

    original_load_slot = m2_batch.load_slot_candidates

    def load_slot(root: Path, *, task_id: str, system: str) -> list[m2_batch.Attempt]:
        if (
            root.resolve() != output_root
            or task_id != TASK_TRACKER_SETUP_TASK
            or system != TASK_TRACKER_SETUP_SYSTEM
        ):
            return original_load_slot(root, task_id=task_id, system=system)
        task_root = root / "runs" / system / task_id
        if not task_root.is_dir():
            return []
        directories = sorted(path for path in task_root.iterdir() if path.is_dir())
        other = sorted(path.name for path in task_root.iterdir() if not path.is_dir())
        allowed = {a1_run_id, a2_run_id, a3_run_id}
        if other or not {path.name for path in directories}.issubset(allowed):
            raise ContractError("task-tracker setup slot contains unexpected evidence")
        if not 2 <= len(directories) <= 3:
            raise ContractError("task-tracker setup slot must contain a1/a2 and at most a3")
        return [
            m2_batch.load_attempt(path, task_id=task_id, system=system)
            for path in directories
        ]

    m2_batch.load_slot_candidates = load_slot
    original_decide = m2_batch.decide_slot

    def decide(candidates: list[m2_batch.Attempt]) -> m2_batch.SlotDecision:
        run_ids = {str(item.run.get("run_id")) for item in candidates}
        target_ids = {a1_run_id, a2_run_id, a3_run_id}
        if not run_ids or not run_ids.issubset(target_ids):
            return original_decide(candidates)
        if not {a1_run_id, a2_run_id}.issubset(run_ids):
            raise ContractError("task-tracker setup decision is missing a1/a2")
        by_id = {str(item.run["run_id"]): item for item in candidates}
        a1 = by_id[a1_run_id]
        a2 = by_id[a2_run_id]
        if (
            a1.run.get("run_validity") != "infra_invalid"
            or not isinstance(a1.run.get("interruption_recovery"), dict)
            or a2.run.get("run_validity") != "infra_invalid"
            or not isinstance(
                a2.run.get("task_tracker_container_setup_recovery"), dict
            )
        ):
            raise ContractError("task-tracker setup failed-run projection differs")
        if a3_run_id not in by_id:
            return m2_batch.SlotDecision(
                "needs_task_tracker_setup_recovery",
                None,
                a1,
                a2,
                "authorized task-specific pre-product container-setup recovery",
            )
        a3 = by_id[a3_run_id]
        replacement_for = m2_batch.observation_value(
            a3.run.get("replacement_for_run_id"),
            "run.replacement_for_run_id",
        )
        if replacement_for is not None:
            raise ContractError("task-tracker a3 must be the first product run")
        if a3.run.get("run_validity") == "valid":
            return m2_batch.SlotDecision(
                "complete",
                a3,
                a1,
                a3,
                "task-specific task-tracker a3 is valid",
            )
        if a3.run.get("run_validity") == "infra_invalid":
            return m2_batch.SlotDecision(
                "blocked",
                None,
                a1,
                a3,
                "the authorized task-tracker a3 is not valid; no a4 is allowed",
            )
        raise ContractError("task-tracker a3 validity is invalid")

    m2_batch.decide_slot = decide
    original_complete = m2_batch.M2Batch._complete_slot

    def complete_slot(
        self: m2_batch.M2Batch,
        *,
        position: int,
        task_id: str,
        system: str,
    ) -> m2_batch.Attempt:
        if (
            self.output_root.resolve() != output_root
            or task_id != TASK_TRACKER_SETUP_TASK
            or system != TASK_TRACKER_SETUP_SYSTEM
        ):
            return original_complete(
                self, position=position, task_id=task_id, system=system
            )
        candidates = m2_batch.load_slot_candidates(
            self.output_root, task_id=task_id, system=system
        )
        for attempt in candidates:
            m2_batch._validate_new_run_freeze(attempt, self.manifest)
        decision = m2_batch.decide_slot(candidates)
        if decision.state == "needs_task_tracker_setup_recovery":
            assert self.events is not None
            self.events.append(
                "slot.task_tracker_container_setup_recovery_authorized",
                position=position,
                task_id=task_id,
                system=system,
                failed_run_ids=[a1_run_id, a2_run_id],
                recovery_run_id=a3_run_id,
                recovery_scheduler_ordinal=3,
                recovery_product_attempt_ordinal=1,
                replacement_for_run_id=None,
                recovery_authorization=str(recovery_path),
                recovery_authorization_sha256=sha256_file(recovery_path),
                no_a4_allowed=True,
            )
            self._run_attempt(
                position=position,
                task_id=task_id,
                system=system,
                ordinal=3,
                replacement_for=None,
            )
        return original_complete(
            self, position=position, task_id=task_id, system=system
        )

    m2_batch.M2Batch._complete_slot = complete_slot


def _dataset_repair_source_projection(source_root: Path) -> dict[str, Any]:
    source_path = source_root.resolve() / DATASET_REPAIR_SOURCE_RELATIVE
    if not source_path.is_file() or source_path.is_symlink():
        raise ContractError("dataset repair source is unavailable")
    original = source_path.read_text(encoding="utf-8")
    if sha256_file(source_path) != DATASET_REPAIR_ORIGINAL_SHA256:
        raise ContractError("dataset repair source differs from the frozen file")
    patched = original
    changes: list[dict[str, Any]] = []
    for before, after in DATASET_REPAIR_REPLACEMENTS:
        if patched.count(before) != 1:
            raise ContractError("dataset repair replacement is not unique")
        patched = patched.replace(before, after)
        changes.append(
            {
                "before": before,
                "after": after,
                "semantic_change": "WooCommerce batch_size 50 default to 10",
            }
        )
    patched_sha256 = hashlib.sha256(patched.encode("utf-8")).hexdigest()
    if patched_sha256 != DATASET_REPAIR_PATCHED_SHA256:
        raise ContractError("dataset repair projection hash differs")
    return {
        "source_path": str(source_path),
        "source_relative": DATASET_REPAIR_SOURCE_RELATIVE,
        "source_modified": False,
        "original_sha256": DATASET_REPAIR_ORIGINAL_SHA256,
        "patched_container_copy_sha256": DATASET_REPAIR_PATCHED_SHA256,
        "changes": changes,
        "scope": "task_container_copy_only",
    }


def qualify_dataset_preprocess_repair(
    output_root: Path,
    source_root: Path,
    helper_path: Path,
) -> Path:
    output_root = output_root.resolve()
    manifest = read_json_object(output_root / "m3-batch-manifest.json")
    batch_id = str(manifest.get("batch_id"))
    retry = manifest.get("retry")
    if (
        not batch_id
        or not isinstance(retry, dict)
        or retry.get("automatic_replacement_maximum") != 1
    ):
        raise ContractError("dataset repair requires the frozen one-replacement M3")
    run_prefix = (
        f"{batch_id}-{DATASET_REPAIR_POSITION:02d}-{DATASET_REPAIR_TASK}-"
        f"{DATASET_REPAIR_SYSTEM}"
    )
    a1_run_id = f"{run_prefix}-a1"
    a2_run_id = f"{run_prefix}-a2"
    a3_run_id = f"{run_prefix}-a3"
    astra_run_id = (
        f"{batch_id}-{DATASET_REPAIR_POSITION:02d}-{DATASET_REPAIR_TASK}-astra-a1"
    )
    recovery_records: list[dict[str, Any]] = []
    recovery_references: list[dict[str, str]] = []
    for ordinal, run_id in ((1, a1_run_id), (2, a2_run_id)):
        path = (
            output_root
            / "recovery-evidence/preprocess-infrastructure"
            / run_id
            / "recovery.json"
        )
        recovery = read_json_object(path)
        if (
            recovery.get("policy") != PREPROCESS_INFRA_POLICY
            or recovery.get("run_id") != run_id
            or recovery.get("system_id") != DATASET_REPAIR_SYSTEM
            or recovery.get("task_id") != DATASET_REPAIR_TASK
            or recovery.get("attempt_ordinal") != ordinal
            or recovery.get("agent_started") is not False
            or recovery.get("model_proxy_started") is not False
            or recovery.get("gateway_started") is not False
            or recovery.get("evaluator_started") is not False
            or recovery.get("projected_run_validity") != "infra_invalid"
            or recovery.get("projected_primary_failure_category")
            != "environment_error"
            or recovery.get("validation", {}).get("status") != "passed"
        ):
            raise ContractError("dataset repair preprocess evidence is unqualified")
        recovery_records.append(recovery)
        recovery_references.append(
            {"path": str(path), "sha256": sha256_file(path)}
        )
    if recovery_records[1].get("replacement_for_run_id") != a1_run_id:
        raise ContractError("dataset repair a2 does not replace the qualified a1")

    source_projection = _dataset_repair_source_projection(source_root)
    a2_directory = str(recovery_records[1]["directory"])
    incident = {
        "policy": DATASET_REPAIR_POLICY,
        "task_id": DATASET_REPAIR_TASK,
        "system_id": DATASET_REPAIR_SYSTEM,
        "directory": a2_directory,
        "run_id": a2_run_id,
        "failed_run_ids": [a1_run_id, a2_run_id],
        "failed_scheduler_ordinals": [1, 2],
        "repair_run_id": a3_run_id,
        "repair_scheduler_ordinal": 3,
        "repair_product_attempt_ordinal": 1,
        "repair_replacement_for_run_id": None,
        "astra_first_product_run_id": astra_run_id,
        "agent_started_in_failed_runs": False,
        "model_proxy_started_in_failed_runs": False,
        "evaluator_started_in_failed_runs": False,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "raw_append_only_evidence_modified": False,
        "failed_attempt_directories_modified": False,
        "general_automatic_replacement_maximum": 1,
        "general_retry_policy_modified": False,
        "task_specific_dataset_repair_maximum": 1,
        "no_attempt_after_repair_failure": True,
        "a2_no_a3_projection_superseded_by_authorized_repair": True,
        "same_overlay_for_astra_and_hermes": True,
        "frozen_toolathlon_source_modified": False,
        "source_overlay": source_projection,
        "root_cause": {
            "classification": "deterministic_dataset_preprocess_timeout",
            "woocommerce_default_timeout_seconds": 10,
            "woocommerce_retry_attempts": 3,
            "original_batch_size": 50,
            "patched_batch_size": 10,
            "generated_product_count": 398,
            "original_expected_create_batch_count": 8,
            "patched_expected_create_batch_count": 40,
            "observation": (
                "both pre-Agent runs stopped after the three retry attempts "
                "for the first product-creation batch while the service "
                "completed the requests server-side"
            ),
        },
        "authorization": "user_accepted_task_specific_protocol_amendment",
        "validation": {
            "status": "passed",
            "fairness_boundary": (
                "neither failed Hermes run started a product or model request; "
                "both systems use the identical repaired preprocess overlay"
            ),
        },
    }
    record = {
        "schema_version": "toolathlon.dataset-preprocess-repair.v1",
        "policy": DATASET_REPAIR_POLICY,
        "created_at": utc_now(),
        "incident_count": 1,
        "incidents": [incident],
        "preprocess_recovery_records": recovery_references,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
    }
    record_path = output_root / DATASET_REPAIR_NAME
    hash_path = output_root / DATASET_REPAIR_HASH_NAME
    if record_path.exists():
        existing = read_json_object(record_path)
        if (
            existing.get("schema_version") != record["schema_version"]
            or existing.get("policy") != DATASET_REPAIR_POLICY
            or existing.get("incidents") != record["incidents"]
            or existing.get("preprocess_recovery_records")
            != recovery_references
        ):
            raise ContractError("existing dataset repair authorization differs")
        if not hash_path.is_file():
            raise ContractError("dataset repair checksum is missing")
    else:
        write_json_atomic(record_path, record, mode=0o644)
        hash_path.write_text(
            f"{sha256_file(record_path)}  {record_path.name}\n",
            encoding="utf-8",
        )
    expected_hash = f"{sha256_file(record_path)}  {record_path.name}\n"
    if hash_path.read_text(encoding="utf-8") != expected_hash:
        raise ContractError("dataset repair checksum differs")
    return record_path


def qualify_dataset_repair_harness_boundary(
    output_root: Path,
    repair_path: Path,
    helper_path: Path,
) -> Path:
    output_root = output_root.resolve()
    repair = read_json_object(repair_path)
    if repair.get("policy") != DATASET_REPAIR_POLICY:
        raise ContractError("dataset repair harness recovery has no repair authorization")
    incident = repair["incidents"][0]
    a3_run_id = str(incident["repair_run_id"])
    if not a3_run_id.endswith("-a3"):
        raise ContractError("dataset repair harness source run is not a3")
    a4_run_id = f"{a3_run_id[:-2]}a4"
    directory = (
        output_root
        / "runs"
        / DATASET_REPAIR_SYSTEM
        / DATASET_REPAIR_TASK
        / a3_run_id
    ).resolve()
    if not directory.is_dir():
        raise ContractError("dataset repair harness a3 evidence is unavailable")

    top_entries = {path.name for path in directory.iterdir()}
    expected_top = {
        "container.log",
        "lifecycle-events.jsonl",
        "permission-policy.json",
        "preprocess-overlay.json",
        "preprocess.log",
        "resource-usage.jsonl",
        "task-state",
    }
    if top_entries != expected_top:
        raise ContractError("dataset repair harness a3 file surface differs")
    prepared_boundary = {
        "lifecycle-events.jsonl",
        "resource-usage.jsonl",
        "task-state",
        "preprocess.log",
        "permission-policy.json",
    }
    if top_entries - prepared_boundary != {
        "container.log",
        "preprocess-overlay.json",
    }:
        raise ContractError("dataset repair harness boundary trigger is not unique")
    forbidden = {
        "resolved-config.json",
        "tool-schema-observed.json",
        "adapter-events.jsonl",
        "trajectory.jsonl",
        "tool-calls.jsonl",
        "model-usage.jsonl",
        "failure-evidence.json",
        "run.json",
        "artifacts.sha256",
    }
    if any((directory / name).exists() for name in forbidden):
        raise ContractError("dataset repair harness a3 reached formal product evidence")
    if (directory / "evaluator").exists():
        raise ContractError("dataset repair harness a3 reached the evaluator")

    lifecycle_rows = artifact_contract.read_jsonl(
        directory / "lifecycle-events.jsonl", allow_empty=False
    )
    expected_events = [
        "reset.start",
        "reset.end",
        "container.start",
        "container.ready",
        "preprocess.overlay_applied",
        "preprocess.start",
        "preprocess.end",
        "gateway.start",
        "gateway.ready",
        "cleanup.start",
        "cleanup.end",
    ]
    if [row.get("event") for row in lifecycle_rows] != expected_events:
        raise ContractError("dataset repair harness a3 lifecycle boundary differs")
    if [row.get("sequence") for row in lifecycle_rows] != list(range(1, 12)):
        raise ContractError("dataset repair harness a3 lifecycle sequence differs")
    if any(
        row.get("run_id") != a3_run_id
        or row.get("system_id") != DATASET_REPAIR_SYSTEM
        for row in lifecycle_rows
    ):
        raise ContractError("dataset repair harness a3 lifecycle identity differs")
    record_path = output_root / DATASET_REPAIR_HARNESS_NAME
    hash_path = output_root / DATASET_REPAIR_HARNESS_HASH_NAME
    overlay_event = lifecycle_rows[4]
    preprocess_end = lifecycle_rows[6]
    gateway_ready = lifecycle_rows[8]
    cleanup_end = lifecycle_rows[10]
    overlay_path = directory / "preprocess-overlay.json"
    overlay = read_json_object(overlay_path)
    health = gateway_ready.get("health")
    if (
        overlay_event.get("policy") != DATASET_REPAIR_POLICY
        or overlay_event.get("overlay_artifact") != "preprocess-overlay.json"
        or overlay_event.get("overlay_artifact_sha256") != sha256_file(overlay_path)
        or overlay_event.get("original_sha256")
        != DATASET_REPAIR_ORIGINAL_SHA256
        or overlay_event.get("patched_container_copy_sha256")
        != DATASET_REPAIR_PATCHED_SHA256
        or overlay.get("policy") != DATASET_REPAIR_POLICY
        or overlay.get("run_id") != a3_run_id
        or overlay.get("task_id") != DATASET_REPAIR_TASK
        or overlay.get("system_id") != DATASET_REPAIR_SYSTEM
        or overlay.get("repair_authorization") != str(repair_path)
        or overlay.get("repair_authorization_sha256") != sha256_file(repair_path)
        or overlay.get("scope") != "task_container_copy_only"
        or overlay.get("source_modified") is not False
        or overlay.get("original_sha256") != DATASET_REPAIR_ORIGINAL_SHA256
        or overlay.get("patched_container_copy_sha256")
        != DATASET_REPAIR_PATCHED_SHA256
        or preprocess_end.get("status") != "passed"
        or preprocess_end.get("application_state_restored") is not True
        or gateway_ready.get("status") != "passed"
        or not isinstance(health, dict)
        or health.get("ok") is not True
        or set(health.get("connected_servers", []))
        != {"filesystem", "woocommerce", "emails"}
        or not isinstance(health.get("tool_count"), int)
        or int(health["tool_count"]) <= 0
        or cleanup_end.get("status") != "passed"
    ):
        raise ContractError("dataset repair harness a3 successful setup evidence differs")
    if read_json_object(directory / "task-state/status.json") != {
        "preprocess": "done",
        "running": None,
        "evaluation": None,
    }:
        raise ContractError("dataset repair harness a3 task state differs")

    resources = artifact_contract.read_jsonl(
        directory / "resource-usage.jsonl", allow_empty=False
    )
    if any(
        row.get("run_id") != a3_run_id
        or row.get("system_id") != DATASET_REPAIR_SYSTEM
        or not isinstance(row.get("product"), dict)
        or row["product"].get("value") is not None
        or row["product"].get("missing_reason") != "process_not_started"
        for row in resources
    ):
        raise ContractError("dataset repair harness a3 unexpectedly started a product")

    scheduler_path = output_root / "scheduler-events.jsonl"
    scheduler_rows = artifact_contract.read_jsonl(scheduler_path, allow_empty=False)
    relevant = [
        row
        for row in scheduler_rows
        if row.get("run_id") == a3_run_id
        or (
            row.get("event") == "slot.dataset_repair_authorized"
            and row.get("repair_run_id") == a3_run_id
        )
    ]
    if [row.get("event") for row in relevant] != [
        "slot.dataset_repair_authorized",
        "attempt.start",
        "attempt.process_exit",
    ]:
        raise ContractError("dataset repair harness a3 scheduler boundary differs")
    authorization, start, process_exit = relevant
    if (
        authorization.get("repair_scheduler_ordinal") != 3
        or authorization.get("repair_product_attempt_ordinal") != 1
        or authorization.get("repair_authorization") != str(repair_path)
        or authorization.get("repair_authorization_sha256")
        != sha256_file(repair_path)
        or start.get("attempt_ordinal") != 3
        or start.get("replacement_for_run_id") is not None
        or process_exit.get("attempt_ordinal") != 3
        or process_exit.get("exit_code") != 1
        or any(
            row.get("task_id") != DATASET_REPAIR_TASK
            or row.get("system") != DATASET_REPAIR_SYSTEM
            for row in relevant
        )
    ):
        raise ContractError("dataset repair harness a3 scheduler identity differs")
    checkpoint_path = output_root / "checkpoint.json"
    checkpoint = read_json_object(checkpoint_path)
    checkpoint_error = str(checkpoint.get("error"))
    checkpoint_matches_a3 = (
        checkpoint.get("status") == "blocked"
        and checkpoint.get("error_type") == "M2Blocked"
        and a3_run_id in checkpoint_error
        and "required run artifacts are missing" in checkpoint_error
    )
    if not checkpoint_matches_a3 and not (record_path.is_file() and hash_path.is_file()):
        raise ContractError("dataset repair harness a3 checkpoint differs")

    harness_incident = {
        "policy": DATASET_REPAIR_HARNESS_POLICY,
        "task_id": DATASET_REPAIR_TASK,
        "system_id": DATASET_REPAIR_SYSTEM,
        "directory": str(directory),
        "run_id": a3_run_id,
        "failed_scheduler_ordinal": 3,
        "authorized_replacement_run_id": a4_run_id,
        "authorized_replacement_scheduler_ordinal": 4,
        "authorized_replacement_product_attempt_ordinal": 1,
        "authorized_replacement_for_run_id": None,
        "classification": (
            "outer_lifecycle_overlay_evidence_prepared_boundary_violation"
        ),
        "overlay_repair_succeeded": True,
        "preprocess_succeeded": True,
        "gateway_succeeded": True,
        "gateway_connected_servers": sorted(health["connected_servers"]),
        "gateway_tool_count": health["tool_count"],
        "agent_started": False,
        "product_started": False,
        "model_proxy_started": False,
        "tools_list_started": False,
        "evaluator_started": False,
        "formal_run_artifacts_complete": False,
        "projected_run_validity": "infra_invalid",
        "projected_verify_status": "unavailable",
        "projected_primary_failure_category": "environment_error",
        "raw_append_only_evidence_modified": False,
        "failed_attempt_directory_modified": False,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "general_automatic_replacement_maximum": 1,
        "general_retry_policy_modified": False,
        "task_specific_harness_replacement_maximum": 1,
        "no_attempt_after_a4_failure": True,
        "same_overlay_for_astra_and_hermes": True,
        "frozen_toolathlon_source_modified": False,
        "overlay_artifact": {
            "path": str(overlay_path),
            "sha256": sha256_file(overlay_path),
            "defective_location": "output_root_top_level",
            "corrected_location": "task-state/preprocess-overlay.json",
        },
        "source_overlay": _dataset_repair_source_projection(
            Path(str(overlay["source_path"])).parents[4]
        ),
        "repair_authorization": {
            "path": str(repair_path),
            "sha256": sha256_file(repair_path),
        },
        "authorization": "user_accepted_a4_harness_infrastructure_replacement",
        "validation": {
            "status": "passed",
            "boundary": "after_gateway_before_orchestrator_product_start",
        },
    }
    record = {
        "schema_version": "toolathlon.dataset-repair-harness-recovery.v1",
        "policy": DATASET_REPAIR_HARNESS_POLICY,
        "created_at": utc_now(),
        "incident_count": 1,
        "incidents": [harness_incident],
        "partial_file_evidence": _partial_file_evidence(directory),
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
    }
    if record_path.exists():
        existing = read_json_object(record_path)
        if (
            existing.get("schema_version") != record["schema_version"]
            or existing.get("policy") != DATASET_REPAIR_HARNESS_POLICY
            or existing.get("incidents") != record["incidents"]
            or existing.get("partial_file_evidence")
            != record["partial_file_evidence"]
        ):
            raise ContractError("existing dataset repair harness recovery differs")
        if not hash_path.is_file():
            raise ContractError("dataset repair harness recovery checksum is missing")
    else:
        write_json_atomic(record_path, record, mode=0o644)
        hash_path.write_text(
            f"{sha256_file(record_path)}  {record_path.name}\n",
            encoding="utf-8",
        )
    expected_hash = f"{sha256_file(record_path)}  {record_path.name}\n"
    if hash_path.read_text(encoding="utf-8") != expected_hash:
        raise ContractError("dataset repair harness recovery checksum differs")
    return record_path


def install_dataset_repair_harness_projection(
    output_root: Path,
    harness_path: Path,
) -> None:
    output_root = output_root.resolve()
    harness = read_json_object(harness_path)
    if harness.get("policy") != DATASET_REPAIR_HARNESS_POLICY:
        raise ContractError("dataset repair harness projection is unauthorized")
    incident = harness["incidents"][0]
    run_id = str(incident["run_id"])
    partial = Path(str(incident["directory"])).resolve()
    expected_partial = (
        output_root
        / "runs"
        / DATASET_REPAIR_SYSTEM
        / DATASET_REPAIR_TASK
        / run_id
    ).resolve()
    if (
        partial != expected_partial
        or incident.get("projected_run_validity") != "infra_invalid"
        or incident.get("projected_primary_failure_category") != "environment_error"
        or incident.get("product_started") is not False
        or incident.get("agent_started") is not False
        or incident.get("model_proxy_started") is not False
        or incident.get("evaluator_started") is not False
        or incident.get("failed_attempt_directory_modified") is not False
        or incident.get("validation", {}).get("status") != "passed"
    ):
        raise ContractError("dataset repair harness projection evidence differs")
    manifest = read_json_object(output_root / "m3-batch-manifest.json")
    recovery_root = output_root / "recovery-evidence/dataset-repair-harness" / run_id
    recovery_root.mkdir(parents=True, exist_ok=True)
    replacement_observation = {
        "value": None,
        "source": "m3_scheduler.attempt.start",
        "reliability": "missing",
        "missing_reason": "first_product_run_never_started",
    }
    synthetic = {
        "schema_version": "toolathlon.dataset-repair-harness-attempt.v1",
        "policy": DATASET_REPAIR_HARNESS_POLICY,
        "run_id": run_id,
        "system_id": DATASET_REPAIR_SYSTEM,
        "task_id": DATASET_REPAIR_TASK,
        "replacement_for_run_id": replacement_observation,
        "run_validity": "infra_invalid",
        "terminal_status": "failed",
        "termination_reason": "outer_lifecycle_prepared_boundary_error",
        "verify_status": "unavailable",
        "primary_failure_category": "environment_error",
        "adapter": {
            "setup_provider_requests_before_agent": 0,
            "product_identity": {
                "strategy": "product_process_not_started",
                "attempt_session_id_sha256": None,
                "identity_observation": {
                    "value": None,
                    "source": "outer_lifecycle_boundary",
                    "reliability": "missing",
                    "missing_reason": "product_process_not_started",
                },
            },
        },
        "dataset_repair_harness_recovery": {
            "record": str(harness_path),
            "record_sha256": sha256_file(harness_path),
            "partial_directory": str(partial),
            "partial_artifacts_modified": False,
            "only_a4_harness_replacement_allowed": True,
            "no_a5_allowed": True,
        },
    }
    resolved = {
        "schema_version": "toolathlon.dataset-repair-harness-resolved.v1",
        "run_id": run_id,
        "freeze": manifest["freeze"],
        "projection": {
            "source": str(harness_path),
            "formal_resolved_config_was_not_created": True,
        },
    }
    reference = {
        "schema_version": "toolathlon.dataset-repair-harness-reference.v1",
        "path": str(harness_path),
        "sha256": sha256_file(harness_path),
        "partial_directory": str(partial),
        "partial_file_evidence_sha256": hashlib.sha256(
            json.dumps(
                harness["partial_file_evidence"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    synthetic_path = recovery_root / "harness-attempt.json"
    resolved_path = recovery_root / "resolved-projection.json"
    reference_path = recovery_root / "recovery-reference.json"
    for path, payload in (
        (synthetic_path, synthetic),
        (resolved_path, resolved),
        (reference_path, reference),
    ):
        if path.exists():
            if read_json_object(path) != payload:
                raise ContractError("dataset repair harness projection changed")
        else:
            write_json_atomic(path, payload, mode=0o644)
    artifact_manifest = recovery_root / "artifacts.sha256"
    artifact_files = [reference_path, resolved_path, synthetic_path]
    expected_manifest = "".join(
        f"{sha256_file(path)}  {path.name}\n" for path in sorted(artifact_files)
    )
    if artifact_manifest.exists():
        if artifact_manifest.read_text(encoding="utf-8") != expected_manifest:
            raise ContractError("dataset repair harness projection manifest changed")
    else:
        artifact_manifest.write_text(expected_manifest, encoding="utf-8")

    virtual = m2_batch.Attempt(
        directory=recovery_root,
        run=synthetic,
        resolved=resolved,
        validation={
            "schema_version": "toolathlon.dataset-repair-harness-attempt.v1",
            "status": "qualified_for_a4_harness_replacement_only",
            "formal_run_artifacts_complete": False,
        },
    )
    original_load = m2_batch.load_attempt

    def load(directory: Path, *, task_id: str, system: str) -> m2_batch.Attempt:
        if directory.resolve() != partial:
            return original_load(directory, task_id=task_id, system=system)
        if task_id != DATASET_REPAIR_TASK or system != DATASET_REPAIR_SYSTEM:
            raise ContractError("dataset repair harness virtual identity differs")
        if harness.get("partial_file_evidence") != _partial_file_evidence(partial):
            raise ContractError("dataset repair harness partial evidence changed")
        return virtual

    m2_batch.load_attempt = load
    original_identity = m2_batch._identity_key

    def identity(attempt: m2_batch.Attempt) -> tuple[str, str]:
        recovery = attempt.run.get("dataset_repair_harness_recovery")
        if isinstance(recovery, dict):
            return (
                f"unobserved-dataset-repair-harness-identity:{run_id}",
                _sha256_text(f"missing-dataset-repair-harness-product:{run_id}"),
            )
        return original_identity(attempt)

    m2_batch._identity_key = identity


def install_lifecycle_dataset_repair_overlay(lifecycle_module: Any) -> None:
    current = lifecycle_module.SingleTaskLifecycle._copy_tree
    if getattr(current, "_toolathlon_dataset_repair_overlay", False):
        return

    def copy_tree(self: Any) -> None:
        current(self)
        if self.args.task_id != DATASET_REPAIR_TASK:
            return
        batch_root = self.output.parents[3]
        repair_path = batch_root / DATASET_REPAIR_NAME
        repair_hash_path = batch_root / DATASET_REPAIR_HASH_NAME
        repair = read_json_object(repair_path)
        expected_manifest = f"{sha256_file(repair_path)}  {repair_path.name}\n"
        if (
            repair.get("policy") != DATASET_REPAIR_POLICY
            or not repair_hash_path.is_file()
            or repair_hash_path.read_text(encoding="utf-8") != expected_manifest
        ):
            raise ContractError("task container dataset repair is not authorized")
        incident = repair["incidents"][0]
        allowed_run_ids = {
            str(incident["repair_run_id"]),
            str(incident["astra_first_product_run_id"]),
        }
        harness_path = batch_root / DATASET_REPAIR_HARNESS_NAME
        harness_hash_path = batch_root / DATASET_REPAIR_HARNESS_HASH_NAME
        if harness_path.is_file():
            harness = read_json_object(harness_path)
            expected_harness_manifest = (
                f"{sha256_file(harness_path)}  {harness_path.name}\n"
            )
            harness_incidents = harness.get("incidents")
            if (
                harness.get("policy") != DATASET_REPAIR_HARNESS_POLICY
                or not harness_hash_path.is_file()
                or harness_hash_path.read_text(encoding="utf-8")
                != expected_harness_manifest
                or not isinstance(harness_incidents, list)
                or len(harness_incidents) != 1
                or harness_incidents[0].get("run_id")
                != incident["repair_run_id"]
                or harness_incidents[0].get("authorization")
                != "user_accepted_a4_harness_infrastructure_replacement"
                or harness_incidents[0].get("no_attempt_after_a4_failure")
                is not True
            ):
                raise ContractError("task container harness replacement is unauthorized")
            allowed_run_ids.add(
                str(harness_incidents[0]["authorized_replacement_run_id"])
            )
        if (
            self.args.run_id not in allowed_run_ids
            or self.args.replacement_for_run_id is not None
        ):
            raise ContractError("dataset repair overlay is not authorized for this run")
        source_projection = _dataset_repair_source_projection(self.source)
        target = f"/workspace/{DATASET_REPAIR_SOURCE_RELATIVE}"
        script = (
            "import hashlib,json,pathlib,sys; "
            "p=pathlib.Path(sys.argv[1]); b=p.read_bytes(); "
            "assert hashlib.sha256(b).hexdigest()==sys.argv[2]; "
            "s=b.decode('utf-8'); changes=json.loads(sys.argv[4]); "
            "assert all(s.count(x[0])==1 for x in changes); "
            "s=''.join([s]); "
            "exec(\"for old,new in changes:\\n s=s.replace(old,new)\"); "
            "p.write_text(s,encoding='utf-8'); "
            "assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[3]"
        )
        self._docker(
            "exec",
            self.container_name,
            "python3",
            "-c",
            script,
            target,
            DATASET_REPAIR_ORIGINAL_SHA256,
            DATASET_REPAIR_PATCHED_SHA256,
            json.dumps(DATASET_REPAIR_REPLACEMENTS, separators=(",", ":")),
            timeout=60,
        )
        overlay = {
            "schema_version": "toolathlon.dataset-preprocess-overlay.v1",
            "policy": DATASET_REPAIR_POLICY,
            "task_id": DATASET_REPAIR_TASK,
            "run_id": self.args.run_id,
            "system_id": self.args.system,
            "repair_authorization": str(repair_path),
            "repair_authorization_sha256": sha256_file(repair_path),
            "frozen_toolathlon_source_modified": False,
            **source_projection,
        }
        # RunSpec validates the top-level output surface immediately before the
        # product slot starts.  Keep the overlay evidence under task-state,
        # which is the prepared lifecycle boundary already reserved for
        # preprocess evidence, instead of adding a new top-level file.
        overlay_path = self.task_state / "preprocess-overlay.json"
        write_json_atomic(overlay_path, overlay, mode=0o644)
        overlay_relative = overlay_path.relative_to(self.output).as_posix()
        self.lifecycle.append(
            "preprocess.overlay_applied",
            policy=DATASET_REPAIR_POLICY,
            overlay_artifact=overlay_relative,
            overlay_artifact_sha256=sha256_file(overlay_path),
            original_sha256=DATASET_REPAIR_ORIGINAL_SHA256,
            patched_container_copy_sha256=DATASET_REPAIR_PATCHED_SHA256,
            frozen_toolathlon_source_modified=False,
        )

    setattr(copy_tree, "_toolathlon_dataset_repair_overlay", True)
    lifecycle_module.SingleTaskLifecycle._copy_tree = copy_tree


def install_dataset_repair_scheduler_hotfix(
    output_root: Path,
    repair_path: Path,
    harness_path: Path,
) -> None:
    output_root = output_root.resolve()
    repair = read_json_object(repair_path)
    if repair.get("policy") != DATASET_REPAIR_POLICY:
        raise ContractError("dataset repair scheduler authorization is invalid")
    incident = repair["incidents"][0]
    failed_run_ids = list(incident["failed_run_ids"])
    repair_run_id = str(incident["repair_run_id"])
    harness = read_json_object(harness_path)
    if harness.get("policy") != DATASET_REPAIR_HARNESS_POLICY:
        raise ContractError("dataset repair harness scheduler authorization is invalid")
    harness_incident = harness["incidents"][0]
    if harness_incident.get("run_id") != repair_run_id:
        raise ContractError("dataset repair harness source run differs")
    harness_replacement_run_id = str(
        harness_incident["authorized_replacement_run_id"]
    )

    original_load_slot = m2_batch.load_slot_candidates

    def load_slot(root: Path, *, task_id: str, system: str) -> list[m2_batch.Attempt]:
        if (
            root.resolve() != output_root
            or task_id != DATASET_REPAIR_TASK
            or system != DATASET_REPAIR_SYSTEM
        ):
            return original_load_slot(root, task_id=task_id, system=system)
        task_root = root / "runs" / system / task_id
        if not task_root.is_dir():
            return []
        directories = sorted(path for path in task_root.iterdir() if path.is_dir())
        other = sorted(path.name for path in task_root.iterdir() if not path.is_dir())
        allowed = {*failed_run_ids, repair_run_id, harness_replacement_run_id}
        if other or not {path.name for path in directories}.issubset(allowed):
            raise ContractError("dataset repair slot contains unexpected evidence")
        if not 2 <= len(directories) <= 4:
            raise ContractError(
                "dataset repair slot must contain a1/a2 and at most a3/a4"
            )
        return [
            m2_batch.load_attempt(path, task_id=task_id, system=system)
            for path in directories
        ]

    m2_batch.load_slot_candidates = load_slot
    original_decide = m2_batch.decide_slot

    def decide(candidates: list[m2_batch.Attempt]) -> m2_batch.SlotDecision:
        run_ids = {str(item.run.get("run_id")) for item in candidates}
        target_ids = {*failed_run_ids, repair_run_id, harness_replacement_run_id}
        if not run_ids or not run_ids.issubset(target_ids):
            return original_decide(candidates)
        if not set(failed_run_ids).issubset(run_ids):
            raise ContractError("dataset repair decision is missing a1/a2")
        by_id = {str(item.run["run_id"]): item for item in candidates}
        for run_id in failed_run_ids:
            failed = by_id[run_id]
            if (
                failed.run.get("run_validity") != "infra_invalid"
                or failed.run.get("primary_failure_category") != "environment_error"
                or not isinstance(
                    failed.run.get("preprocess_infrastructure_recovery"), dict
                )
            ):
                raise ContractError("dataset repair failed attempt projection differs")
        if repair_run_id not in by_id:
            return m2_batch.SlotDecision(
                "needs_dataset_repair",
                None,
                by_id[failed_run_ids[-1]],
                None,
                "authorized deterministic dataset preprocess repair",
            )
        repaired = by_id[repair_run_id]
        replacement = m2_batch.observation_value(
            repaired.run.get("replacement_for_run_id"),
            "run.replacement_for_run_id",
        )
        if replacement is not None:
            raise ContractError("dataset repair product run must be a first attempt")
        if repaired.run.get("run_validity") == "valid":
            if harness_replacement_run_id in by_id:
                raise ContractError("a4 exists after a valid dataset repair a3")
            return m2_batch.SlotDecision(
                "complete",
                repaired,
                by_id[failed_run_ids[0]],
                repaired,
                "task-specific dataset repair run is valid",
            )
        if repaired.run.get("run_validity") == "infra_invalid":
            harness_recovery = repaired.run.get(
                "dataset_repair_harness_recovery"
            )
            if not isinstance(harness_recovery, dict):
                if harness_replacement_run_id in by_id:
                    raise ContractError("a4 exists without the qualified a3 harness failure")
                return m2_batch.SlotDecision(
                    "blocked",
                    None,
                    by_id[failed_run_ids[0]],
                    repaired,
                    "the authorized dataset repair itself failed; no a4 is allowed",
                )
            if harness_replacement_run_id not in by_id:
                return m2_batch.SlotDecision(
                    "needs_dataset_harness_replacement",
                    None,
                    by_id[failed_run_ids[0]],
                    repaired,
                    "authorized a3 harness-boundary infrastructure replacement",
                )
            replacement = by_id[harness_replacement_run_id]
            replacement_for = m2_batch.observation_value(
                replacement.run.get("replacement_for_run_id"),
                "run.replacement_for_run_id",
            )
            if replacement_for is not None:
                raise ContractError("a4 must retain first-product-run semantics")
            if replacement.run.get("run_validity") == "valid":
                return m2_batch.SlotDecision(
                    "complete",
                    replacement,
                    by_id[failed_run_ids[0]],
                    replacement,
                    "task-specific a4 harness replacement is valid",
                )
            if replacement.run.get("run_validity") == "infra_invalid":
                return m2_batch.SlotDecision(
                    "blocked",
                    None,
                    by_id[failed_run_ids[0]],
                    replacement,
                    "the one authorized a4 is not valid; no a5 is allowed",
                )
            raise ContractError("dataset repair harness replacement validity is invalid")
        raise ContractError("dataset repair run validity is invalid")

    m2_batch.decide_slot = decide
    original_complete = m2_batch.M2Batch._complete_slot

    def complete_slot(
        self: m2_batch.M2Batch,
        *,
        position: int,
        task_id: str,
        system: str,
    ) -> m2_batch.Attempt:
        if (
            self.output_root.resolve() != output_root
            or task_id != DATASET_REPAIR_TASK
            or system != DATASET_REPAIR_SYSTEM
        ):
            return original_complete(
                self, position=position, task_id=task_id, system=system
            )
        candidates = m2_batch.load_slot_candidates(
            self.output_root, task_id=task_id, system=system
        )
        for attempt in candidates:
            m2_batch._validate_new_run_freeze(attempt, self.manifest)
        decision = m2_batch.decide_slot(candidates)
        if decision.state == "needs_dataset_repair":
            assert self.events is not None
            self.events.append(
                "slot.dataset_repair_authorized",
                position=position,
                task_id=task_id,
                system=system,
                failed_run_ids=failed_run_ids,
                repair_run_id=repair_run_id,
                repair_scheduler_ordinal=3,
                repair_product_attempt_ordinal=1,
                repair_authorization=str(repair_path),
                repair_authorization_sha256=sha256_file(repair_path),
            )
            self._run_attempt(
                position=position,
                task_id=task_id,
                system=system,
                ordinal=3,
                replacement_for=None,
            )
        elif decision.state == "needs_dataset_harness_replacement":
            assert self.events is not None
            self.events.append(
                "slot.dataset_repair_harness_replacement_authorized",
                position=position,
                task_id=task_id,
                system=system,
                failed_run_id=repair_run_id,
                replacement_run_id=harness_replacement_run_id,
                replacement_scheduler_ordinal=4,
                replacement_product_attempt_ordinal=1,
                replacement_for_run_id=None,
                harness_authorization=str(harness_path),
                harness_authorization_sha256=sha256_file(harness_path),
                no_a5_allowed=True,
            )
            self._run_attempt(
                position=position,
                task_id=task_id,
                system=system,
                ordinal=4,
                replacement_for=None,
            )
        return original_complete(
            self, position=position, task_id=task_id, system=system
        )

    m2_batch.M2Batch._complete_slot = complete_slot


def install_m3_dataset_repair_validation(
    m3_module: Any,
    repair_path: Path,
    harness_path: Path,
    task_tracker_setup_path: Path,
) -> None:
    repair = read_json_object(repair_path)
    incident = repair["incidents"][0]
    repair_run_id = str(incident["repair_run_id"])
    failed_run_ids = list(incident["failed_run_ids"])
    harness = read_json_object(harness_path)
    if harness.get("policy") != DATASET_REPAIR_HARNESS_POLICY:
        raise ContractError("M3 dataset repair harness validation is unauthorized")
    harness_incident = harness["incidents"][0]
    if harness_incident.get("run_id") != repair_run_id:
        raise ContractError("M3 dataset repair harness source run differs")
    harness_replacement_run_id = str(
        harness_incident["authorized_replacement_run_id"]
    )
    task_tracker_setup = read_json_object(task_tracker_setup_path)
    if task_tracker_setup.get("policy") != TASK_TRACKER_SETUP_POLICY:
        raise ContractError("M3 task-tracker setup validation is unauthorized")
    task_tracker_incident = task_tracker_setup["incidents"][0]
    task_tracker_recovery_run_id = str(
        task_tracker_incident["authorized_recovery_run_id"]
    )

    def validate_schedule(self: Any) -> None:
        rows = artifact_contract.read_jsonl(
            self.output_root / "scheduler-events.jsonl", allow_empty=False
        )
        expected_slots = [
            (formal_position, task_id, system)
            for remaining_position, (task_id, order) in enumerate(
                self.schedule, start=1
            )
            for formal_position in [len(m2_batch.FIRST_BATCH) + remaining_position]
            for system in order
        ]
        observed_originals: list[tuple[int, str, str]] = []
        active: tuple[str, int] | None = None
        seen_attempts: set[tuple[str, int]] = set()
        seen_ordinals: dict[tuple[int, str, str], set[int]] = {}
        for row in rows:
            if row.get("schema_version") != "toolathlon.m3-scheduler-events.v1":
                raise ContractError("M3 scheduler event schema changed")
            event = row.get("event")
            if event == "attempt.start":
                run_id = row.get("run_id")
                ordinal = row.get("attempt_ordinal")
                if not isinstance(run_id, str) or ordinal not in {1, 2, 3, 4}:
                    raise ContractError("M3 scheduler has an invalid attempt.start event")
                key = (run_id, ordinal)
                if key in seen_attempts or active is not None:
                    raise ContractError("M3 scheduler attempt overlap or reuse")
                slot = (
                    int(row.get("position")),
                    str(row.get("task_id")),
                    str(row.get("system")),
                )
                prior = seen_ordinals.setdefault(slot, set())
                if ordinal == 1:
                    observed_originals.append(slot)
                elif ordinal == 2:
                    if 1 not in prior:
                        raise ContractError("M3 replacement has no original attempt")
                elif ordinal == 3:
                    dataset_repair_ordinal = (
                        slot
                        == (
                            DATASET_REPAIR_POSITION,
                            DATASET_REPAIR_TASK,
                            DATASET_REPAIR_SYSTEM,
                        )
                        and run_id == repair_run_id
                    )
                    task_tracker_setup_ordinal = (
                        slot
                        == (
                            TASK_TRACKER_SETUP_POSITION,
                            TASK_TRACKER_SETUP_TASK,
                            TASK_TRACKER_SETUP_SYSTEM,
                        )
                        and run_id == task_tracker_recovery_run_id
                    )
                    if (
                        not (dataset_repair_ordinal or task_tracker_setup_ordinal)
                        or prior != {1, 2}
                        or row.get("replacement_for_run_id") is not None
                    ):
                        raise ContractError(
                            "M3 task-specific ordinal 3 is unauthorized"
                        )
                elif ordinal == 4 and (
                    slot
                    != (
                        DATASET_REPAIR_POSITION,
                        DATASET_REPAIR_TASK,
                        DATASET_REPAIR_SYSTEM,
                    )
                    or run_id != harness_replacement_run_id
                    or prior != {1, 2, 3}
                    or row.get("replacement_for_run_id") is not None
                ):
                    raise ContractError(
                        "M3 dataset repair harness replacement is unauthorized"
                    )
                prior.add(int(ordinal))
                seen_attempts.add(key)
                active = key
            elif event in {"attempt.process_exit", "attempt.process_interrupted"}:
                key = (str(row.get("run_id")), int(row.get("attempt_ordinal")))
                if active != key:
                    raise ContractError(
                        "M3 process terminal event does not match the active attempt"
                    )
                active = None
        if active is not None:
            raise ContractError("M3 scheduler has an attempt with no process-exit event")
        if observed_originals != expected_slots:
            raise ContractError("M3 original attempts were not run in frozen serial order")

    m3_module.M3Batch._validate_schedule_events = validate_schedule
    original_validate = m3_module.M3Batch.validate_complete

    def validate_complete(self: Any, *, write_report: bool) -> dict[str, Any]:
        report = original_validate(self, write_report=False)
        task_rows = [
            row for row in report["tasks"] if row.get("task_id") == DATASET_REPAIR_TASK
        ]
        if len(task_rows) != 1:
            raise ContractError("dataset repair task report row is not unique")
        hermes = task_rows[0]["systems"][DATASET_REPAIR_SYSTEM]
        if (
            hermes.get("effective_run_id") != harness_replacement_run_id
            or hermes.get("candidate_count") != 4
        ):
            raise ContractError("dataset repair effective result differs")
        task_tracker_rows = [
            row
            for row in report["tasks"]
            if row.get("task_id") == TASK_TRACKER_SETUP_TASK
        ]
        if len(task_tracker_rows) != 1:
            raise ContractError("task-tracker report row is not unique")
        task_tracker_hermes = task_tracker_rows[0]["systems"][
            TASK_TRACKER_SETUP_SYSTEM
        ]
        if (
            task_tracker_hermes.get("effective_run_id")
            != task_tracker_recovery_run_id
            or task_tracker_hermes.get("candidate_count") != 3
        ):
            raise ContractError("task-tracker setup recovery result differs")

        automatic = report.get("automatic_replacement_count")
        if not isinstance(automatic, int) or automatic < 3:
            raise ContractError("task-specific replacement accounting is invalid")
        report["automatic_replacement_count"] = automatic - 3
        report["dataset_repair_run_count"] = 1
        report["dataset_repair_harness_replacement_count"] = 1
        report["dataset_repair_protocol"] = {
            "policy": DATASET_REPAIR_POLICY,
            "authorization": str(repair_path),
            "authorization_sha256": sha256_file(repair_path),
            "failed_pre_agent_run_ids": failed_run_ids,
            "repair_run_id": repair_run_id,
            "repair_run_disposition": "infra_invalid_harness_boundary",
            "effective_repair_run_id": harness_replacement_run_id,
            "harness_replacement": {
                "policy": DATASET_REPAIR_HARNESS_POLICY,
                "authorization": str(harness_path),
                "authorization_sha256": sha256_file(harness_path),
                "scheduler_ordinal": 4,
                "product_attempt_ordinal": 1,
                "replacement_for_run_id": None,
                "no_a5_allowed": True,
            },
            "general_retry_policy_modified": False,
        }
        hermes["dataset_repair"] = report["dataset_repair_protocol"]
        report["task_tracker_container_setup_recovery_count"] = 1
        report["task_tracker_container_setup_recovery"] = {
            "policy": TASK_TRACKER_SETUP_POLICY,
            "authorization": str(task_tracker_setup_path),
            "authorization_sha256": sha256_file(task_tracker_setup_path),
            "failed_pre_agent_run_ids": task_tracker_incident[
                "failed_pre_agent_run_ids"
            ],
            "recovery_run_id": task_tracker_recovery_run_id,
            "scheduler_ordinal": 3,
            "product_attempt_ordinal": 1,
            "replacement_for_run_id": None,
            "no_a4_allowed": True,
            "general_retry_policy_modified": False,
        }
        task_tracker_hermes["task_tracker_container_setup_recovery"] = report[
            "task_tracker_container_setup_recovery"
        ]
        if write_report:
            write_json_atomic(self.report_path, report, mode=0o644)
            self.report_hash_path.write_text(
                f"{sha256_file(self.report_path)}  {self.report_path.name}\n",
                encoding="utf-8",
            )
        return report

    m3_module.M3Batch.validate_complete = validate_complete


def _append_lifecycle_event(path: Path, run: dict[str, Any], **fields: Any) -> None:
    rows = artifact_contract.read_jsonl(path, allow_empty=False)
    sequences = [row.get("sequence") for row in rows]
    if sequences != list(range(1, len(rows) + 1)):
        raise ContractError("lifecycle event sequence is not contiguous")
    record = {
        "schema_version": "toolathlon.adapter.events.v1",
        "run_id": run["run_id"],
        "system_id": run["system_id"],
        "sequence": len(rows) + 1,
        "timestamp": utc_now(),
        "monotonic_ns": time.monotonic_ns(),
        **fields,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _recover_attempt(directory: Path) -> dict[str, Any]:
    run_path = directory / "run.json"
    lifecycle_path = directory / "lifecycle-events.jsonl"
    hash_path = directory / "artifacts.sha256"
    run = read_json_object(run_path)
    trajectory = artifact_contract.read_jsonl(
        directory / "trajectory.jsonl", allow_empty=True
    )
    evidence = _native_transport_evidence(trajectory, run)

    lifecycle = artifact_contract.read_jsonl(lifecycle_path, allow_empty=False)
    events = [row.get("event") for row in lifecycle]
    if events[-1:] != ["artifact_validation.start"]:
        raise ContractError("pending lifecycle does not end at artifact_validation.start")
    if events.count("artifact_validation.start") != 1 or "artifact_validation.end" in events:
        raise ContractError("pending lifecycle has an unexpected validation shape")
    if not hash_path.is_file() or hash_path.stat().st_size != 0:
        raise ContractError("pending lifecycle artifacts.sha256 is not empty")

    preliminary = artifact_contract.validate_run_artifacts(
        directory, verify_hash=False, require_validation_end=False
    )
    before = {
        name: sha256_file(directory / name)
        for name in (
            "run.json",
            "lifecycle-events.jsonl",
            "trajectory.jsonl",
            "tool-calls.jsonl",
            "model-usage.jsonl",
        )
    }
    original_run = run_path.read_bytes()
    original_lifecycle = lifecycle_path.read_bytes()
    try:
        run["artifact_gate"] = {
            "status": "passed",
            "validator": POLICY,
            "validated_at": utc_now(),
            "validation_exception": {
                "frozen_validator_error": TRIGGER,
                **evidence,
            },
        }
        write_json_atomic(run_path, run, mode=0o644)
        _append_lifecycle_event(
            lifecycle_path,
            run,
            event="artifact_validation.end",
            status="passed",
            validator=POLICY,
            validation_exception=evidence,
            preliminary=preliminary,
        )
        candidates = [
            path
            for path in directory.rglob("*")
            if path.is_file() and not path.is_symlink() and path.name != "artifacts.sha256"
        ]
        write_sha256_manifest(hash_path, candidates, root=directory)
        validation = artifact_contract.validate_run_artifacts(directory, verify_hash=True)
    except BaseException:
        run_path.write_bytes(original_run)
        lifecycle_path.write_bytes(original_lifecycle)
        hash_path.write_text("", encoding="utf-8")
        raise

    return {
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "system_id": run["system_id"],
        "directory": str(directory),
        "policy": POLICY,
        "raw_append_only_evidence_modified": False,
        "finalization_fields_completed": [
            "run.json:artifact_gate",
            "lifecycle-events.jsonl:artifact_validation.end",
            "artifacts.sha256",
        ],
        "pre_finalization_sha256": before,
        "artifacts_manifest_sha256": sha256_file(hash_path),
        "validation": validation,
        **evidence,
    }


def _recover_count_scope_attempt(directory: Path) -> dict[str, Any]:
    run_path = directory / "run.json"
    lifecycle_path = directory / "lifecycle-events.jsonl"
    hash_path = directory / "artifacts.sha256"
    observability_path = directory / COUNT_SCOPE_ARTIFACT
    run = read_json_object(run_path)
    trajectory = artifact_contract.read_jsonl(
        directory / "trajectory.jsonl", allow_empty=True
    )
    if (
        run.get("terminal_status") == "max_steps"
        and run.get("termination_reason") == "max_model_requests"
        and run.get("primary_failure_category") == "model_request_budget"
    ):
        evidence = _native_transport_evidence(trajectory, run)
    else:
        evidence = _astra_model_count_vs_transport_evidence(trajectory, run)

    lifecycle = artifact_contract.read_jsonl(lifecycle_path, allow_empty=False)
    events = [row.get("event") for row in lifecycle]
    if events[-1:] != ["artifact_validation.start"]:
        raise ContractError("pending lifecycle does not end at artifact_validation.start")
    if events.count("artifact_validation.start") != 1 or "artifact_validation.end" in events:
        raise ContractError("pending lifecycle has an unexpected validation shape")
    if not hash_path.is_file() or hash_path.stat().st_size != 0:
        raise ContractError("pending lifecycle artifacts.sha256 is not empty")
    if observability_path.exists():
        raise ContractError("pending lifecycle already has a tool-count artifact")

    preliminary = artifact_contract.validate_run_artifacts(
        directory, verify_hash=False, require_validation_end=False
    )
    before = {
        name: sha256_file(directory / name)
        for name in (
            "run.json",
            "lifecycle-events.jsonl",
            "trajectory.jsonl",
            "tool-calls.jsonl",
            "model-usage.jsonl",
            "evaluator/eval_res.json",
        )
    }
    original_run = run_path.read_bytes()
    original_lifecycle = lifecycle_path.read_bytes()
    try:
        artifact = _write_count_scope_artifact(directory, run, evidence)
        run["artifact_gate"] = {
            "status": "passed",
            "validator": COUNT_SCOPE_POLICY,
            "validated_at": utc_now(),
            "frozen_validator_error": COUNT_SCOPE_TRIGGER,
            "observability_artifact": artifact.name,
            "server_declared_model_tool_call_count": evidence[
                "server_declared_model_tool_call_count"
            ],
            "native_transport_terminal_count": evidence[
                "native_transport_terminal_count"
            ],
        }
        write_json_atomic(run_path, run, mode=0o644)
        _append_lifecycle_event(
            lifecycle_path,
            run,
            event="artifact_validation.end",
            status="passed",
            validator=COUNT_SCOPE_POLICY,
            observability_artifact=artifact.name,
            server_declared_model_tool_call_count=evidence[
                "server_declared_model_tool_call_count"
            ],
            native_transport_terminal_count=evidence[
                "native_transport_terminal_count"
            ],
            preliminary=preliminary,
        )
        _rehash_attempt(directory)
        validation = artifact_contract.validate_run_artifacts(
            directory, verify_hash=True
        )
    except BaseException:
        run_path.write_bytes(original_run)
        lifecycle_path.write_bytes(original_lifecycle)
        hash_path.write_text("", encoding="utf-8")
        observability_path.unlink(missing_ok=True)
        raise

    return {
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "system_id": run["system_id"],
        "directory": str(directory),
        "policy": COUNT_SCOPE_POLICY,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "raw_append_only_evidence_modified": False,
        "finalization_fields_completed": [
            "run.json:artifact_gate",
            f"{COUNT_SCOPE_ARTIFACT}",
            "lifecycle-events.jsonl:artifact_validation.end",
            "artifacts.sha256",
        ],
        "pre_finalization_sha256": before,
        "artifacts_manifest_sha256": sha256_file(hash_path),
        "validation": validation,
        **evidence,
    }


def _recover_hermes_drain_attempt(directory: Path) -> dict[str, Any]:
    run_path = directory / "run.json"
    lifecycle_path = directory / "lifecycle-events.jsonl"
    hash_path = directory / "artifacts.sha256"
    reconciliation_path = directory / HERMES_DRAIN_ARTIFACT
    run = read_json_object(run_path)
    models = artifact_contract.read_jsonl(
        directory / "model-usage.jsonl", allow_empty=False
    )
    adapters = artifact_contract.read_jsonl(
        directory / "adapter-events.jsonl", allow_empty=False
    )
    evidence = _hermes_post_shutdown_drain_evidence(models, adapters, run)
    reconciliation_policy = evidence["reconciliation_policy"]

    lifecycle = artifact_contract.read_jsonl(lifecycle_path, allow_empty=False)
    events = [row.get("event") for row in lifecycle]
    if events[-1:] != ["artifact_validation.start"]:
        raise ContractError("pending lifecycle does not end at artifact_validation.start")
    if events.count("artifact_validation.start") != 1 or "artifact_validation.end" in events:
        raise ContractError("pending lifecycle has an unexpected validation shape")
    if not hash_path.is_file() or hash_path.stat().st_size != 0:
        raise ContractError("pending lifecycle artifacts.sha256 is not empty")
    if reconciliation_path.exists():
        raise ContractError("pending lifecycle already has a Hermes drain artifact")

    before = {
        name: sha256_file(directory / name)
        for name in (
            "run.json",
            "lifecycle-events.jsonl",
            "adapter-events.jsonl",
            "model-usage.jsonl",
            "trajectory.jsonl",
            "tool-calls.jsonl",
            "evaluator/eval_res.json",
        )
    }
    original_run = run_path.read_bytes()
    original_lifecycle = lifecycle_path.read_bytes()
    try:
        write_json_atomic(
            reconciliation_path,
            {
                "schema_version": "toolathlon.hermes-model-drain-reconciliation.v2",
                "policy": reconciliation_policy,
                "run_id": run["run_id"],
                "system_id": run["system_id"],
                "task_id": run["task_id"],
                "recorded_at": utc_now(),
                "formal_attempt_rerun": False,
                "raw_append_only_evidence_modified": False,
                "evidence": evidence,
            },
            mode=0o644,
        )
        initial = evidence["pre_proxy_shutdown_drain"]
        run["adapter"]["post_terminal_model_drain"] = {
            "settled": True,
            "settlement_phase": "drain_timeout_boundary_terminalization",
            "settled_basis": (
                "all_forwarded_model_requests_have_unique_terminal_events"
            ),
            "provider_requests_forwarded": evidence[
                "final_provider_requests_forwarded"
            ],
            "provider_requests_completed": evidence[
                "final_provider_requests_completed"
            ],
            "provider_requests_failed": evidence["final_provider_requests_failed"],
            "pre_proxy_shutdown_settled": False,
            "pre_proxy_shutdown_timeout_seconds": initial["timeout_seconds"],
            "pre_proxy_shutdown_wait_seconds": initial["wait_seconds"],
            "snapshot_closing_terminal_count": evidence[
                "snapshot_closing_terminal_count"
            ],
            "pre_shutdown_terminal_count": evidence[
                "pre_shutdown_terminal_count"
            ],
            "post_shutdown_terminal_count": evidence[
                "post_shutdown_terminal_count"
            ],
            "reconciliation_artifact": reconciliation_path.name,
        }
        run["artifact_gate"] = {
            "status": "passed",
            "validator": reconciliation_policy,
            "validated_at": utc_now(),
            "frozen_validator_error": HERMES_DRAIN_TRIGGER,
            "reconciliation_artifact": reconciliation_path.name,
            "formal_attempt_rerun": False,
        }
        write_json_atomic(run_path, run, mode=0o644)
        preliminary = artifact_contract.validate_run_artifacts(
            directory, verify_hash=False, require_validation_end=False
        )
        _append_lifecycle_event(
            lifecycle_path,
            run,
            event="artifact_validation.end",
            status="passed",
            validator=reconciliation_policy,
            reconciliation_artifact=reconciliation_path.name,
            formal_attempt_rerun=False,
            preliminary=preliminary,
        )
        _rehash_attempt(directory)
        validation = artifact_contract.validate_run_artifacts(
            directory, verify_hash=True
        )
    except BaseException:
        run_path.write_bytes(original_run)
        lifecycle_path.write_bytes(original_lifecycle)
        hash_path.write_text("", encoding="utf-8")
        reconciliation_path.unlink(missing_ok=True)
        raise

    return {
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "system_id": run["system_id"],
        "directory": str(directory),
        "policy": reconciliation_policy,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "hermes_normalizer_modified": False,
        "hermes_artifact_gate_modified": False,
        "raw_append_only_evidence_modified": False,
        "pre_finalization_sha256": before,
        "artifacts_manifest_sha256": sha256_file(hash_path),
        "validation": validation,
        **evidence,
    }


def _recover_hermes_open_request_attempt(directory: Path) -> dict[str, Any]:
    run_path = directory / "run.json"
    failure_path = directory / "failure-evidence.json"
    lifecycle_path = directory / "lifecycle-events.jsonl"
    hash_path = directory / "artifacts.sha256"
    evidence_path = directory / HERMES_OPEN_REQUEST_ARTIFACT
    run = read_json_object(run_path)
    models = artifact_contract.read_jsonl(
        directory / "model-usage.jsonl", allow_empty=False
    )
    adapters = artifact_contract.read_jsonl(
        directory / "adapter-events.jsonl", allow_empty=False
    )
    evidence = _hermes_open_request_shutdown_evidence(models, adapters, run)

    lifecycle = artifact_contract.read_jsonl(lifecycle_path, allow_empty=False)
    events = [row.get("event") for row in lifecycle]
    if events[-1:] != ["artifact_validation.start"]:
        raise ContractError(
            "open-request lifecycle does not end at artifact_validation.start"
        )
    if events.count("artifact_validation.start") != 1 or "artifact_validation.end" in events:
        raise ContractError("open-request lifecycle has an unexpected validation shape")
    if not hash_path.is_file() or hash_path.stat().st_size != 0:
        raise ContractError("open-request artifacts.sha256 is not empty")
    if evidence_path.exists():
        raise ContractError("open-request evidence artifact already exists")

    before = {
        name: sha256_file(directory / name)
        for name in (
            "run.json",
            "failure-evidence.json",
            "lifecycle-events.jsonl",
            "adapter-events.jsonl",
            "model-usage.jsonl",
            "trajectory.jsonl",
            "tool-calls.jsonl",
            "evaluator/eval_res.json",
        )
    }
    original_run = run_path.read_bytes()
    original_failure = failure_path.read_bytes()
    original_lifecycle = lifecycle_path.read_bytes()
    try:
        write_json_atomic(
            evidence_path,
            {
                "schema_version": "toolathlon.hermes-open-model-request.v1",
                "policy": HERMES_OPEN_REQUEST_POLICY,
                "run_id": run["run_id"],
                "system_id": run["system_id"],
                "task_id": run["task_id"],
                "recorded_at": utc_now(),
                "formal_attempt_rerun": False,
                "raw_append_only_evidence_modified": False,
                "evidence": evidence,
            },
            mode=0o644,
        )
        original_result = evidence["original_formal_result"]
        run["run_validity"] = "infra_invalid"
        run["verify_status"] = "unavailable"
        run["primary_failure_category"] = "environment_error"
        run["infrastructure_projection"] = {
            "policy": HERMES_OPEN_REQUEST_POLICY,
            "classification": "model_proxy_shutdown_with_unterminalized_request",
            "original_formal_result": original_result,
            "agent_execution_end_monotonic_ns": evidence[
                "agent_execution_end_monotonic_ns"
            ],
            "open_model_request_id": evidence["open_request"][
                "model_request_id"
            ],
            "replacement_disposition": evidence["replacement_disposition"],
            "evidence_artifact": evidence_path.name,
            "raw_append_only_evidence_modified": False,
        }
        run["artifact_gate"] = {
            "status": "passed",
            "validator": HERMES_OPEN_REQUEST_POLICY,
            "validated_at": utc_now(),
            "frozen_validator_error": (
                "one or more forwarded model requests have no terminal event"
            ),
            "evidence_artifact": evidence_path.name,
            "formal_attempt_rerun": False,
            "replacement_eligible": True,
        }
        write_json_atomic(run_path, run, mode=0o644)

        failure = read_json_object(failure_path)
        failure["primary_failure_category"] = "environment_error"
        failure["raw_error_code"] = {
            "value": "model_proxy_shutdown_with_unterminalized_request",
            "source": "outer_lifecycle_reconciliation",
            "reliability": "observed",
            "missing_reason": None,
        }
        failure["evidence_paths"] = [
            evidence_path.name,
            "model-usage.jsonl",
            "model-proxy-state.json",
            "evaluator/eval.log",
            "evaluator/eval_res.json",
        ]
        write_json_atomic(failure_path, failure, mode=0o644)

        preliminary = artifact_contract.validate_run_artifacts(
            directory, verify_hash=False, require_validation_end=False
        )
        _append_lifecycle_event(
            lifecycle_path,
            run,
            event="artifact_validation.end",
            status="passed",
            validator=HERMES_OPEN_REQUEST_POLICY,
            run_validity="infra_invalid",
            replacement_eligible=True,
            evidence_artifact=evidence_path.name,
            preliminary=preliminary,
        )
        _rehash_attempt(directory)
        validation = artifact_contract.validate_run_artifacts(
            directory, verify_hash=True
        )
    except BaseException:
        run_path.write_bytes(original_run)
        failure_path.write_bytes(original_failure)
        lifecycle_path.write_bytes(original_lifecycle)
        hash_path.write_text("", encoding="utf-8")
        evidence_path.unlink(missing_ok=True)
        raise

    return {
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "system_id": run["system_id"],
        "directory": str(directory),
        "policy": HERMES_OPEN_REQUEST_POLICY,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "raw_append_only_evidence_modified": False,
        "original_formal_result": evidence["original_formal_result"],
        "projected_run_validity": "infra_invalid",
        "projected_verify_status": "unavailable",
        "projected_primary_failure_category": "environment_error",
        "replacement_eligible": True,
        "pre_finalization_sha256": before,
        "artifacts_manifest_sha256": sha256_file(hash_path),
        "validation": validation,
        **evidence,
    }


def _recover_astra_agent_deadline_attempt(directory: Path) -> dict[str, Any]:
    run_path = directory / "run.json"
    lifecycle_path = directory / "lifecycle-events.jsonl"
    hash_path = directory / "artifacts.sha256"
    evidence_path = directory / ASTRA_DEADLINE_ARTIFACT
    run = read_json_object(run_path)
    trajectory = artifact_contract.read_jsonl(
        directory / "trajectory.jsonl", allow_empty=False
    )
    models = artifact_contract.read_jsonl(
        directory / "model-usage.jsonl", allow_empty=False
    )
    adapters = artifact_contract.read_jsonl(
        directory / "adapter-events.jsonl", allow_empty=False
    )
    evidence = _astra_agent_deadline_tool_evidence(trajectory, run)
    evidence.update(_astra_agent_deadline_model_evidence(models, run))
    evidence.update(
        _astra_agent_deadline_boundary_evidence(adapters, models, run)
    )
    _ASTRA_DEADLINE_BY_RUN_ID[str(run["run_id"])] = evidence

    lifecycle = artifact_contract.read_jsonl(lifecycle_path, allow_empty=False)
    events = [row.get("event") for row in lifecycle]
    if events[-1:] != ["artifact_validation.start"]:
        raise ContractError(
            "Astra Agent-deadline lifecycle does not end at validation start"
        )
    if events.count("artifact_validation.start") != 1 or "artifact_validation.end" in events:
        raise ContractError("Astra Agent-deadline validation shape differs")
    if not hash_path.is_file() or hash_path.stat().st_size != 0:
        raise ContractError("Astra Agent-deadline artifacts.sha256 is not empty")
    if evidence_path.exists():
        raise ContractError("Astra Agent-deadline evidence artifact already exists")

    raw_names = (
        "adapter-events.jsonl",
        "model-usage.jsonl",
        "trajectory.jsonl",
        "tool-calls.jsonl",
        "evaluator/eval_res.json",
        "evaluator/eval.log",
    )
    before = {name: sha256_file(directory / name) for name in raw_names}
    original_run = run_path.read_bytes()
    original_lifecycle = lifecycle_path.read_bytes()
    try:
        _write_astra_deadline_artifact(directory, run, evidence)
        run["artifact_gate"] = {
            "status": "passed",
            "validator": ASTRA_DEADLINE_POLICY,
            "validated_at": utc_now(),
            "frozen_validator_errors": [
                TRIGGER,
                "one or more forwarded model requests have no terminal event",
                "valid run has an unsettled post-terminal model drain",
            ],
            "observability_artifact": evidence_path.name,
            "formal_attempt_rerun": False,
            "replacement_authorized": False,
        }
        write_json_atomic(run_path, run, mode=0o644)
        preliminary = artifact_contract.validate_run_artifacts(
            directory, verify_hash=False, require_validation_end=False
        )
        _append_lifecycle_event(
            lifecycle_path,
            run,
            event="artifact_validation.end",
            status="passed",
            validator=ASTRA_DEADLINE_POLICY,
            observability_artifact=evidence_path.name,
            formal_attempt_rerun=False,
            replacement_authorized=False,
            preliminary=preliminary,
        )
        _rehash_attempt(directory)
        validation = artifact_contract.validate_run_artifacts(
            directory, verify_hash=True
        )
    except BaseException:
        run_path.write_bytes(original_run)
        lifecycle_path.write_bytes(original_lifecycle)
        hash_path.write_text("", encoding="utf-8")
        evidence_path.unlink(missing_ok=True)
        raise

    after = {name: sha256_file(directory / name) for name in raw_names}
    if after != before:
        raise ContractError("Astra Agent-deadline raw evidence changed")
    return {
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "system_id": run["system_id"],
        "directory": str(directory),
        "policy": ASTRA_DEADLINE_POLICY,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "replacement_authorized": False,
        "raw_append_only_evidence_modified": False,
        "pre_finalization_sha256": before,
        "artifacts_manifest_sha256": sha256_file(hash_path),
        "validation": validation,
        **evidence,
    }


def recover_pending_attempts(output_root: Path, helper_path: Path) -> list[dict[str, Any]]:
    output_root = output_root.resolve()
    recovery_path = output_root / RECOVERY_NAME
    existing_incidents: list[dict[str, Any]] = []
    if recovery_path.is_file():
        existing = read_json_object(recovery_path)
        if existing.get("schema_version") != "toolathlon.astra-budget-terminal-recovery.v1":
            raise ContractError("existing Astra budget-terminal recovery schema differs")
        if existing.get("policy") != POLICY:
            raise ContractError("existing Astra budget-terminal recovery policy differs")
        incidents = existing.get("incidents")
        if not isinstance(incidents, list):
            raise ContractError("existing Astra budget-terminal incidents are invalid")
        existing_incidents = incidents

    recovered: list[dict[str, Any]] = []
    runs_root = output_root / "runs" / "astra"
    if runs_root.is_dir():
        for run_path in sorted(runs_root.glob("*/*/run.json")):
            run = read_json_object(run_path)
            if run.get("artifact_gate", {}).get("status") == "passed":
                continue
            if run.get("artifact_gate", {}).get("status") != "pending_cleanup_and_validation":
                continue
            if not (
                run.get("terminal_status") == "max_steps"
                and run.get("termination_reason") == "max_model_requests"
            ):
                continue
            recovered.append(_recover_attempt(run_path.parent))

    if not recovered:
        return existing_incidents

    known = {item.get("run_id") for item in existing_incidents}
    if any(item["run_id"] in known for item in recovered):
        raise ContractError("Astra budget-terminal recovery run is duplicated")
    record = {
        "schema_version": "toolathlon.astra-budget-terminal-recovery.v1",
        "created_at": utc_now(),
        "policy": POLICY,
        "scope": "Astra max_model_requests finalization only",
        "hermes_behavior_modified": False,
        "formal_attempt_rerun": False,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "incidents": [*existing_incidents, *recovered],
    }
    write_json_atomic(recovery_path, record, mode=0o644)
    write_sha256_manifest(
        output_root / RECOVERY_HASH_NAME, [recovery_path], root=output_root
    )
    return record["incidents"]


def recover_pending_product_failure_attempts(
    output_root: Path, helper_path: Path
) -> list[dict[str, Any]]:
    output_root = output_root.resolve()
    recovery_path = output_root / PRODUCT_FAILURE_RECOVERY_NAME
    existing_incidents: list[dict[str, Any]] = []
    if recovery_path.is_file():
        existing = read_json_object(recovery_path)
        if (
            existing.get("schema_version")
            != "toolathlon.product-failure-evaluator-unavailable-recovery.v1"
            or existing.get("policy") != PRODUCT_FAILURE_POLICY
        ):
            raise ContractError("existing product-failure recovery record differs")
        incidents = existing.get("incidents")
        if not isinstance(incidents, list):
            raise ContractError("existing product-failure incidents are invalid")
        existing_incidents = incidents

    recovered: list[dict[str, Any]] = []
    known_run_ids = {
        item.get("run_id") for item in existing_incidents if isinstance(item, dict)
    }
    runs_root = output_root / "runs"
    if runs_root.is_dir():
        for run_path in sorted(runs_root.glob("*/*/*/run.json")):
            run = read_json_object(run_path)
            if run.get("artifact_gate", {}).get("status") != "passed":
                continue
            if (
                run.get("system_id") not in {"astra", "hermes"}
                or run.get("terminal_status") not in {"crashed", "failed"}
                or run.get("termination_reason") != "product_exit"
                or run.get("run_validity") != "valid"
                or run.get("primary_failure_category") != "product_error"
                or run.get("verify_status") != "unavailable"
                or not isinstance(run.get("evaluator_error"), dict)
                or run["evaluator_error"].get("reliability") != "observed"
            ):
                continue
            evaluator = read_json_object(run_path.parent / "evaluator/eval_res.json")
            if evaluator.get("pass") is not None:
                raise ContractError(
                    "product-failure evaluator recovery found a non-null conclusion"
                )
            if run.get("run_id") in known_run_ids:
                continue
            raw_names = (
                "run.json",
                "lifecycle-events.jsonl",
                "adapter-events.jsonl",
                "model-usage.jsonl",
                "trajectory.jsonl",
                "tool-calls.jsonl",
                "evaluator/eval_res.json",
                "evaluator/eval.log",
            )
            evidence = {
                "run_id": run["run_id"],
                "task_id": run["task_id"],
                "system_id": run["system_id"],
                "directory": str(run_path.parent),
                "policy": PRODUCT_FAILURE_POLICY,
                "terminal_status": run["terminal_status"],
                "termination_reason": run["termination_reason"],
                "run_validity": run["run_validity"],
                "primary_failure_category": run["primary_failure_category"],
                "verify_status": run["verify_status"],
                "evaluator_pass": {
                    "value": evaluator.get("pass"),
                    "source": "provider_response",
                    "reliability": "missing",
                    "missing_reason": "provider_not_reported",
                },
                "evaluator_error": run["evaluator_error"],
                "formal_attempt_rerun": False,
                "agent_rerun": False,
                "evaluator_rerun": False,
                "raw_append_only_evidence_modified": False,
                "replacement_authorized": False,
                "effective_result": True,
                "raw_evidence_sha256": {
                    name: sha256_file(run_path.parent / name) for name in raw_names
                },
                "validation": {
                    "status": "passed",
                    "scope": "product_failure_is_effective_without_evaluator_conclusion",
                },
            }
            recovered.append(evidence)

    if not recovered:
        return existing_incidents
    record = {
        "schema_version": "toolathlon.product-failure-evaluator-unavailable-recovery.v1",
        "created_at": utc_now(),
        "policy": PRODUCT_FAILURE_POLICY,
        "scope": "valid product failures with evaluator unavailable",
        "formal_attempt_rerun": False,
        "replacement_authorized": False,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "incidents": [*existing_incidents, *recovered],
    }
    write_json_atomic(recovery_path, record, mode=0o644)
    write_sha256_manifest(
        output_root / PRODUCT_FAILURE_RECOVERY_HASH_NAME,
        [recovery_path],
        root=output_root,
    )
    return record["incidents"]


def recover_pending_count_scope_attempts(
    output_root: Path, helper_path: Path
) -> list[dict[str, Any]]:
    output_root = output_root.resolve()
    recovery_path = output_root / COUNT_SCOPE_RECOVERY_NAME
    existing_incidents: list[dict[str, Any]] = []
    if recovery_path.is_file():
        existing = read_json_object(recovery_path)
        if (
            existing.get("schema_version")
            != "toolathlon.astra-tool-count-observability-recovery.v1"
            or existing.get("policy") != COUNT_SCOPE_POLICY
        ):
            raise ContractError("existing Astra tool-count recovery record differs")
        incidents = existing.get("incidents")
        if not isinstance(incidents, list):
            raise ContractError("existing Astra tool-count incidents are invalid")
        existing_incidents = incidents

    recovered: list[dict[str, Any]] = []
    runs_root = output_root / "runs" / "astra"
    if runs_root.is_dir():
        for run_path in sorted(runs_root.glob("*/*/run.json")):
            run = read_json_object(run_path)
            if run.get("artifact_gate", {}).get("status") == "passed":
                continue
            if run.get("artifact_gate", {}).get("status") != "pending_cleanup_and_validation":
                continue
            normal_completion = (
                run.get("terminal_status") == "completed"
                and run.get("termination_reason") == "product_exit"
                and run.get("run_validity") == "valid"
                and run.get("verify_status") in {"pass", "no_pass"}
            )
            product_failure = (
                run.get("terminal_status") in {"crashed", "failed"}
                and run.get("termination_reason") == "product_exit"
                and run.get("run_validity") == "valid"
                and run.get("primary_failure_category") == "product_error"
                and run.get("verify_status") == "unavailable"
                and isinstance(run.get("evaluator_error"), dict)
                and run["evaluator_error"].get("reliability") == "observed"
            )
            budget_terminal = (
                run.get("terminal_status") == "max_steps"
                and run.get("termination_reason") == "max_model_requests"
                and run.get("run_validity") == "valid"
                and run.get("primary_failure_category") == "model_request_budget"
                and run.get("verify_status") in {"pass", "no_pass"}
            )
            if not (normal_completion or product_failure or budget_terminal):
                continue
            if (
                run.get("verify_status") == "no_pass"
                and run.get("primary_failure_category")
                == "completed_but_no_pass"
            ):
                # The legacy count recovery excludes this valid formal category.
                # Gate v2 validates and hashes it without rewriting the attempt.
                continue
            recovered.append(_recover_count_scope_attempt(run_path.parent))

    if not recovered:
        return existing_incidents

    known = {item.get("run_id") for item in existing_incidents}
    if any(item["run_id"] in known for item in recovered):
        raise ContractError("Astra tool-count recovery run is duplicated")
    record = {
        "schema_version": "toolathlon.astra-tool-count-observability-recovery.v1",
        "created_at": utc_now(),
        "policy": COUNT_SCOPE_POLICY,
        "scope": (
            "Astra product_exit runs with complete native transports and model-"
            "request-budget terminals with at most one observed open transport"
        ),
        "hermes_behavior_modified": False,
        "formal_attempt_rerun": False,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "incidents": [*existing_incidents, *recovered],
    }
    write_json_atomic(recovery_path, record, mode=0o644)
    write_sha256_manifest(
        output_root / COUNT_SCOPE_RECOVERY_HASH_NAME,
        [recovery_path],
        root=output_root,
    )
    return record["incidents"]


def recover_pending_astra_agent_deadline_attempts(
    output_root: Path, helper_path: Path
) -> list[dict[str, Any]]:
    output_root = output_root.resolve()
    recovery_path = output_root / ASTRA_DEADLINE_RECOVERY_NAME
    existing_incidents: list[dict[str, Any]] = []
    if recovery_path.is_file():
        existing = read_json_object(recovery_path)
        if (
            existing.get("schema_version")
            != "toolathlon.astra-agent-deadline-recovery.v1"
            or existing.get("policy") != ASTRA_DEADLINE_POLICY
        ):
            raise ContractError("existing Astra Agent-deadline recovery differs")
        incidents = existing.get("incidents")
        if not isinstance(incidents, list):
            raise ContractError("existing Astra Agent-deadline incidents are invalid")
        existing_incidents = incidents

    recovered: list[dict[str, Any]] = []
    runs_root = output_root / "runs" / "astra"
    if runs_root.is_dir():
        for run_path in sorted(runs_root.glob("*/*/run.json")):
            run = read_json_object(run_path)
            if run.get("artifact_gate", {}).get("status") == "passed":
                continue
            if run.get("artifact_gate", {}).get("status") != "pending_cleanup_and_validation":
                continue
            budget = run.get("model_budget")
            drain = run.get("adapter", {}).get("post_terminal_model_drain")
            if not (
                run.get("terminal_status") == "timeout"
                and run.get("termination_reason") == "agent_deadline"
                and run.get("run_validity") == "valid"
                and run.get("verify_status") == "unavailable"
                and run.get("primary_failure_category") == "agent_deadline"
                and isinstance(budget, dict)
                and budget.get("provider_requests_forwarded")
                == budget.get("provider_requests_completed", -1) + 1
                and isinstance(drain, dict)
                and drain.get("settled") is False
            ):
                continue
            recovered.append(
                _recover_astra_agent_deadline_attempt(run_path.parent)
            )

    if not recovered:
        return existing_incidents
    known = {item.get("run_id") for item in existing_incidents}
    if any(item["run_id"] in known for item in recovered):
        raise ContractError("Astra Agent-deadline recovery run is duplicated")
    record = {
        "schema_version": "toolathlon.astra-agent-deadline-recovery.v1",
        "created_at": utc_now(),
        "policy": ASTRA_DEADLINE_POLICY,
        "scope": "Agent deadline with complete tool transports and one open drain request",
        "formal_attempt_rerun": False,
        "replacement_authorized": False,
        "raw_append_only_evidence_modified": False,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "incidents": [*existing_incidents, *recovered],
    }
    write_json_atomic(recovery_path, record, mode=0o644)
    write_sha256_manifest(
        output_root / ASTRA_DEADLINE_RECOVERY_HASH_NAME,
        [recovery_path],
        root=output_root,
    )
    return record["incidents"]


def recover_pending_hermes_drain_attempts(
    output_root: Path, helper_path: Path
) -> list[dict[str, Any]]:
    output_root = output_root.resolve()
    recovery_path = output_root / HERMES_DRAIN_RECOVERY_NAME
    existing_incidents: list[dict[str, Any]] = []
    existing_policy: str | None = None
    if recovery_path.is_file():
        existing = read_json_object(recovery_path)
        if (
            existing.get("schema_version")
            != "toolathlon.hermes-model-drain-recovery.v1"
            or existing.get("policy")
            not in {HERMES_DRAIN_POLICY, HERMES_DRAIN_TIMEOUT_POLICY}
        ):
            raise ContractError("existing Hermes model-drain recovery record differs")
        existing_policy = str(existing["policy"])
        incidents = existing.get("incidents")
        if not isinstance(incidents, list):
            raise ContractError("existing Hermes model-drain incidents are invalid")
        existing_incidents = incidents

    recovered: list[dict[str, Any]] = []
    runs_root = output_root / "runs" / "hermes"
    if runs_root.is_dir():
        for run_path in sorted(runs_root.glob("*/*/run.json")):
            run = read_json_object(run_path)
            if run.get("artifact_gate", {}).get("status") == "passed":
                continue
            if run.get("artifact_gate", {}).get("status") != "pending_cleanup_and_validation":
                continue
            drain = run.get("adapter", {}).get("post_terminal_model_drain", {})
            if not (
                run.get("terminal_status") == "completed"
                and run.get("termination_reason") == "product_exit"
                and run.get("run_validity") == "valid"
                and run.get("verify_status") in {"pass", "no_pass"}
                and isinstance(drain, dict)
                and drain.get("settled") is False
            ):
                continue
            try:
                gate_v2_pending = _gate_v2_pending_hermes_drain_projection(
                    run_path.parent
                )
            except ContractError:
                gate_v2_pending = None
            if gate_v2_pending is not None:
                # Gate v2 records this complete attempt in its derived bundle;
                # do not invoke the legacy in-place reconciliation path.
                continue
            recovered.append(_recover_hermes_drain_attempt(run_path.parent))

    if not recovered:
        return existing_incidents

    known = {item.get("run_id") for item in existing_incidents}
    if any(item["run_id"] in known for item in recovered):
        raise ContractError("Hermes model-drain recovery run is duplicated")
    recovered_policies = {str(item.get("policy")) for item in recovered}
    if len(recovered_policies) != 1:
        raise ContractError("Hermes model-drain recoveries have mixed policies")
    recovered_policy = next(iter(recovered_policies))
    if existing_policy is not None and existing_policy != recovered_policy:
        raise ContractError(
            "Hermes model-drain recovery policy changed within one batch"
        )
    record = {
        "schema_version": "toolathlon.hermes-model-drain-recovery.v1",
        "created_at": utc_now(),
        "policy": recovered_policy,
        "scope": "timed-out drain snapshot boundary reconciliation only",
        "formal_attempt_rerun": False,
        "hermes_normalizer_modified": False,
        "hermes_artifact_gate_modified": False,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "incidents": [*existing_incidents, *recovered],
    }
    write_json_atomic(recovery_path, record, mode=0o644)
    write_sha256_manifest(
        output_root / HERMES_DRAIN_RECOVERY_HASH_NAME,
        [recovery_path],
        root=output_root,
    )
    return record["incidents"]


def recover_pending_hermes_open_request_attempts(
    output_root: Path, helper_path: Path
) -> list[dict[str, Any]]:
    output_root = output_root.resolve()
    recovery_path = output_root / HERMES_OPEN_REQUEST_RECOVERY_NAME
    existing_incidents: list[dict[str, Any]] = []
    if recovery_path.is_file():
        existing = read_json_object(recovery_path)
        if (
            existing.get("schema_version")
            != "toolathlon.hermes-open-model-request-recovery.v1"
            or existing.get("policy") != HERMES_OPEN_REQUEST_POLICY
        ):
            raise ContractError("existing Hermes open-request recovery differs")
        incidents = existing.get("incidents")
        if not isinstance(incidents, list):
            raise ContractError("existing Hermes open-request incidents are invalid")
        existing_incidents = incidents

    recovered: list[dict[str, Any]] = []
    runs_root = output_root / "runs" / "hermes"
    if runs_root.is_dir():
        for run_path in sorted(runs_root.glob("*/*/run.json")):
            run = read_json_object(run_path)
            if run.get("artifact_gate", {}).get("status") == "passed":
                continue
            if run.get("artifact_gate", {}).get("status") != "pending_cleanup_and_validation":
                continue
            budget = run.get("model_budget")
            drain = run.get("adapter", {}).get("post_terminal_model_drain")
            if not (
                run.get("terminal_status") == "completed"
                and run.get("termination_reason") == "product_exit"
                and run.get("run_validity") == "valid"
                and run.get("verify_status") in {"pass", "no_pass"}
                and isinstance(budget, dict)
                and budget.get("provider_requests_forwarded")
                == budget.get("provider_requests_completed", -1) + 1
                and isinstance(drain, dict)
                and drain.get("settled") in {True, False}
            ):
                continue
            try:
                gate_v2_pending = _gate_v2_pending_hermes_drain_projection(
                    run_path.parent
                )
            except ContractError:
                gate_v2_pending = None
            if gate_v2_pending is not None:
                # Final model evidence is complete; run.json only contains the
                # earlier drain snapshot, so this is not an open request.
                continue
            recovered.append(_recover_hermes_open_request_attempt(run_path.parent))

    if not recovered:
        return existing_incidents
    known = {item.get("run_id") for item in existing_incidents}
    if any(item["run_id"] in known for item in recovered):
        raise ContractError("Hermes open-request recovery run is duplicated")
    record = {
        "schema_version": "toolathlon.hermes-open-model-request-recovery.v1",
        "created_at": utc_now(),
        "policy": HERMES_OPEN_REQUEST_POLICY,
        "scope": (
            "single model request left open by post-settled shutdown race or "
            "bounded drain timeout"
        ),
        "formal_attempt_rerun": False,
        "raw_append_only_evidence_modified": False,
        "replacement_maximum": 1,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "incidents": [*existing_incidents, *recovered],
    }
    write_json_atomic(recovery_path, record, mode=0o644)
    write_sha256_manifest(
        output_root / HERMES_OPEN_REQUEST_RECOVERY_HASH_NAME,
        [recovery_path],
        root=output_root,
    )
    return record["incidents"]


def install_lifecycle_hermes_drain_reconciliation(
    lifecycle_module: Any,
) -> Callable[..., Any]:
    current = lifecycle_module.SingleTaskLifecycle._finalize
    if getattr(current, "_toolathlon_hermes_drain_reconciliation", False):
        return current
    original = current

    def finalize(self: Any) -> dict[str, Any]:
        try:
            return original(self)
        except ContractError as exc:
            if str(exc) != HERMES_DRAIN_TRIGGER:
                raise
            return _recover_hermes_drain_attempt(self.output)["validation"]

    setattr(finalize, "_toolathlon_hermes_drain_reconciliation", True)
    lifecycle_module.SingleTaskLifecycle._finalize = finalize
    return original


def install_lifecycle_hermes_open_request_projection(
    lifecycle_module: Any,
) -> Callable[..., Any]:
    current = lifecycle_module.SingleTaskLifecycle._finalize
    if getattr(current, "_toolathlon_hermes_open_request_projection", False):
        return current
    original = current

    def finalize(self: Any) -> dict[str, Any]:
        try:
            return original(self)
        except ContractError as exc:
            if (
                str(exc)
                != "one or more forwarded model requests have no terminal event"
            ):
                raise
            return _recover_hermes_open_request_attempt(self.output)["validation"]

    setattr(finalize, "_toolathlon_hermes_open_request_projection", True)
    lifecycle_module.SingleTaskLifecycle._finalize = finalize
    return original


def _task_specific_evaluator_command(
    directory: Path, source_root: Path
) -> tuple[list[str], str]:
    trajectory = read_json_object(directory / "task-state/traj_log.json")
    config = trajectory.get("config")
    if not isinstance(config, dict):
        raise ContractError("saved task trajectory has no evaluator config")
    evaluation = config.get("evaluation")
    if not isinstance(evaluation, dict):
        raise ContractError("saved task trajectory has no evaluation object")
    raw_command = evaluation.get("evaluation_command")
    task_id = read_json_object(directory / "run.json")["task_id"]
    expected = ["uv", "run", "-m", f"tasks.finalpool.{task_id}.evaluation.main"]
    if not isinstance(raw_command, str) or shlex.split(raw_command) != expected:
        raise ContractError("task-specific evaluator command is not the frozen module form")
    launch_time = config.get("launch_time")
    if not isinstance(launch_time, str) or not launch_time:
        raise ContractError("saved task trajectory has no launch time")

    state = directory / "task-state"
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "--cpus",
        "8",
        "--memory",
        "8g",
        "--memory-swap",
        "16g",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-v",
        f"{source_root / 'tasks'}:/workspace/tasks:ro",
        "-v",
        f"{source_root / 'utils'}:/workspace/utils:ro",
        "-v",
        f"{source_root / 'configs'}:/workspace/configs:ro",
        "-v",
        f"{state}:/workspace/dumps:ro",
        "-w",
        "/workspace",
        (
            "docker.io/lockon0927/toolathlon-task-image@"
            "sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f"
        ),
        *expected,
        "--res_log_file",
        "/workspace/dumps/traj_log.json",
        "--agent_workspace",
        "/workspace/dumps/workspace",
        "--launch_time",
        launch_time,
    ]
    groundtruth = evaluation.get("groundtruth_workspace")
    if isinstance(groundtruth, str) and groundtruth:
        resolved = Path(groundtruth)
        if not str(resolved).startswith("/workspace/tasks/"):
            raise ContractError("task evaluator groundtruth path is outside frozen tasks")
        command.extend(["--groundtruth_workspace", str(resolved)])
    return command, raw_command


def _budget_terminal_evidence(
    directory: Path, run: dict[str, Any]
) -> dict[str, Any]:
    if (
        run.get("system_id") not in {"astra", "hermes"}
        or run.get("terminal_status") != "max_steps"
        or run.get("termination_reason") != "max_model_requests"
        or run.get("run_validity") != "valid"
        or run.get("primary_failure_category") != "model_request_budget"
    ):
        raise ContractError("run is not a valid model-request-budget terminal")
    budget = run.get("model_budget")
    if (
        not isinstance(budget, dict)
        or budget.get("max_requests") != 100
        or budget.get("limit_exceeded") is not True
        or budget.get("provider_requests_forwarded") != 100
        or budget.get("provider_requests_completed") != 100
        or not isinstance(budget.get("provider_requests_failed"), int)
        or not isinstance(budget.get("product_attempts"), int)
        or budget["product_attempts"] < 100
        or not isinstance(budget.get("limit_rejections"), int)
        or budget["limit_rejections"] < 0
    ):
        raise ContractError("budget-terminal model counters are inconsistent")
    state = read_json_object(directory / "model-proxy-state.json")
    if state.get("budget") != budget:
        raise ContractError("budget-terminal Model Proxy state differs from run.json")
    models = artifact_contract.read_jsonl(
        directory / "model-usage.jsonl", allow_empty=False
    )
    _BASE_MODEL_USAGE_VALIDATOR(models, run)
    starts = [row for row in models if row.get("event") == "model_request.started"]
    completions = [
        row for row in models if row.get("event") == "model_request.completed"
    ]
    failed = sum(row.get("success") is False for row in completions)
    drain = run.get("adapter", {}).get("post_terminal_model_drain")
    if (
        len(starts) != 100
        or len(completions) != 100
        or failed != budget["provider_requests_failed"]
        or not isinstance(drain, dict)
        or drain.get("settled") is not True
        or drain.get("provider_requests_forwarded") != 100
        or drain.get("provider_requests_completed") != 100
    ):
        raise ContractError("budget-terminal model completion evidence differs")

    evidence: dict[str, Any] = {
        "budget_terminal_system": run["system_id"],
        "provider_requests_forwarded": 100,
        "provider_requests_completed": 100,
        "provider_requests_failed": failed,
        "product_attempts": budget["product_attempts"],
        "limit_rejections": budget["limit_rejections"],
        "post_terminal_model_drain": drain,
        "all_forwarded_requests_have_unique_terminal_events": True,
    }
    if run["system_id"] == "astra":
        trajectory_rows = artifact_contract.read_jsonl(
            directory / "trajectory.jsonl", allow_empty=True
        )
        evidence.update(_native_transport_evidence(trajectory_rows, run))
    else:
        summary = run.get("trajectory")
        if (
            not isinstance(summary, dict)
            or summary.get("started_only_tool_calls") != 0
            or summary.get("tool_started_events")
            != summary.get("tool_terminal_events")
        ):
            raise ContractError("Hermes budget-terminal tools are incomplete")
        evidence.update(
            {
                "native_transport_started": summary["tool_started_events"],
                "native_transport_terminal": summary["tool_terminal_events"],
                "native_transport_failed": summary["tool_failed_events"],
                "all_native_transports_have_unique_terminal_events": True,
            }
        )
    return evidence


def replay_budget_terminal_evaluator(
    directory: Path, *, output_root: Path, source_root: Path, helper_path: Path
) -> dict[str, Any]:
    directory = directory.resolve()
    output_root = output_root.resolve()
    run = read_json_object(directory / "run.json")
    terminal_evidence = _budget_terminal_evidence(directory, run)
    if run.get("verify_status") != "unavailable":
        raise ContractError("budget-terminal evaluator replay requires unavailable result")
    if run.get("artifact_gate", {}).get("status") != "passed":
        raise ContractError("budget-terminal evaluator replay requires a finalized attempt")
    before_validation = artifact_contract.validate_run_artifacts(directory)

    command, frozen_command = _task_specific_evaluator_command(directory, source_root)
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=source_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=1800,
        check=False,
    )
    duration = time.monotonic() - started
    if completed.returncode not in {0, 1}:
        raise ContractError(
            f"task-specific evaluator replay exited unexpectedly: {completed.returncode}"
        )
    verify_status = "pass" if completed.returncode == 0 else "no_pass"
    passed = completed.returncode == 0
    output = completed.stdout.decode("utf-8", errors="replace")

    recovery_root = (
        output_root
        / "recovery-evidence"
        / "budget-terminal-evaluator"
        / str(run["run_id"])
    )
    if recovery_root.exists():
        raise ContractError("budget-terminal evaluator recovery already exists")
    recovery_root.mkdir(parents=True, mode=0o700)
    preserved = {
        "evaluator/eval_res.json": "original-eval_res.json",
        "evaluator/eval.log": "original-eval.log",
        "task-state/eval_res.json": "original-task-state-eval_res.json",
        "task-state/status.json": "original-status.json",
        "run.json": "original-run.json",
        "failure-evidence.json": "original-failure-evidence.json",
        "lifecycle-events.jsonl": "original-lifecycle-events.jsonl",
        "artifacts.sha256": "original-artifacts.sha256",
    }
    for relative, name in preserved.items():
        source = directory / relative
        if not source.is_file():
            raise ContractError(f"evaluator replay source artifact is missing: {relative}")
        shutil.copy2(source, recovery_root / name)

    replay_result = (
        {
            "pass": True,
            "details": "All task-specific evaluation checks passed",
        }
        if passed
        else {
            "pass": False,
            "failure": output,
            "details": "Task-specific evaluator returned no-pass",
        }
    )
    replay_result["budget_terminal_evaluation_policy"] = EVALUATOR_POLICY
    run_path = directory / "run.json"
    failure_path = directory / "failure-evidence.json"
    lifecycle_path = directory / "lifecycle-events.jsonl"
    hash_path = directory / "artifacts.sha256"

    _append_lifecycle_event(
        lifecycle_path,
        run,
        event="evaluator.budget_terminal_replay.start",
        policy=EVALUATOR_POLICY,
        frozen_evaluation_command=frozen_command,
    )
    (directory / "evaluator/eval.log").write_text(output, encoding="utf-8")
    write_json_atomic(directory / "evaluator/eval_res.json", replay_result, mode=0o644)
    write_json_atomic(directory / "task-state/eval_res.json", replay_result, mode=0o644)
    status = read_json_object(directory / "task-state/status.json")
    status["evaluation"] = "pass" if passed else "fail"
    write_json_atomic(directory / "task-state/status.json", status, mode=0o644)

    run["verify_status"] = verify_status
    run["evaluator_exit_code"] = {
        "value": completed.returncode,
        "source": "budget_terminal_task_specific_evaluator_replay",
        "reliability": "observed",
        "missing_reason": None,
    }
    run["evaluator_error"] = {
        "value": None,
        "source": "budget_terminal_task_specific_evaluator_replay",
        "reliability": "missing",
        "missing_reason": "no_evaluator_error",
    }
    run["evaluator_duration_seconds"] = duration
    previous_gate = run["artifact_gate"]
    run["artifact_gate"] = {
        "status": "passed",
        "validator": EVALUATOR_POLICY,
        "validated_at": utc_now(),
        "previous_gate": previous_gate,
        "budget_terminal_evaluator_replay": {
            "verify_status": verify_status,
            "exit_code": completed.returncode,
            **terminal_evidence,
        },
    }
    write_json_atomic(run_path, run, mode=0o644)

    failure = read_json_object(failure_path)
    failure["evaluator_error"] = {
        "value": None,
        "source": "budget_terminal_task_specific_evaluator_replay",
        "reliability": "missing",
        "missing_reason": "no_evaluator_error",
    }
    failure["evidence_paths"] = [
        "evaluator/eval.log",
        "evaluator/eval_res.json",
        "task-state/workspace",
    ]
    write_json_atomic(failure_path, failure, mode=0o644)
    _append_lifecycle_event(
        lifecycle_path,
        run,
        event="evaluator.budget_terminal_replay.end",
        policy=EVALUATOR_POLICY,
        verify_status=verify_status,
        evaluator_exit_code=completed.returncode,
        duration_seconds=duration,
    )
    _append_lifecycle_event(
        lifecycle_path,
        run,
        event="artifact_validation.replay.start",
        policy=EVALUATOR_POLICY,
    )
    preliminary = artifact_contract.validate_run_artifacts(
        directory, verify_hash=False
    )
    _append_lifecycle_event(
        lifecycle_path,
        run,
        event="artifact_validation.replay.end",
        policy=EVALUATOR_POLICY,
        status="passed",
        preliminary=preliminary,
    )
    candidates = [
        path
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "artifacts.sha256"
    ]
    write_sha256_manifest(hash_path, candidates, root=directory)
    after_validation = artifact_contract.validate_run_artifacts(directory)

    record = {
        "schema_version": "toolathlon.budget-terminal-evaluator-recovery.v1",
        "created_at": utc_now(),
        "policy": EVALUATOR_POLICY,
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "system_id": run["system_id"],
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "product_terminal_preserved": "max_model_requests",
        "frozen_evaluation_command": frozen_command,
        "verify_status": verify_status,
        "evaluator_exit_code": completed.returncode,
        "duration_seconds": duration,
        "before_validation": before_validation,
        "after_validation": after_validation,
        "artifacts_manifest_sha256": sha256_file(hash_path),
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "directory": str(directory),
        "evaluator_replay": True,
        "evaluator_replay_count": 1,
        "original_evaluator_preserved": True,
        "raw_agent_evidence_modified": False,
        "formal_run_artifacts_modified": True,
        "validation": after_validation,
        **terminal_evidence,
    }
    record_path = recovery_root / "recovery.json"
    write_json_atomic(record_path, record, mode=0o644)
    write_sha256_manifest(
        recovery_root / "recovery.sha256",
        [*recovery_root.iterdir()],
        root=recovery_root,
    )
    return record


def recover_pending_budget_terminal_evaluators(
    output_root: Path, source_root: Path, helper_path: Path
) -> list[dict[str, Any]]:
    output_root = output_root.resolve()
    source_root = source_root.resolve()
    aggregate_path = output_root / BUDGET_EVALUATOR_RECOVERY_NAME
    incidents_by_run: dict[str, dict[str, Any]] = {}
    if aggregate_path.is_file():
        existing = read_json_object(aggregate_path)
        if (
            existing.get("schema_version")
            != "toolathlon.budget-terminal-evaluator-recovery-set.v1"
            or existing.get("policy") != EVALUATOR_POLICY
        ):
            raise ContractError("existing budget-terminal evaluator recovery differs")
        incidents = existing.get("incidents")
        if not isinstance(incidents, list):
            raise ContractError("budget-terminal evaluator incidents are invalid")
        for item in incidents:
            if not isinstance(item, dict) or not isinstance(item.get("run_id"), str):
                raise ContractError("budget-terminal evaluator incident is invalid")
            incidents_by_run[str(item["run_id"])] = item

    nested_root = output_root / "recovery-evidence/budget-terminal-evaluator"
    if nested_root.is_dir():
        for record_path in sorted(nested_root.glob("*/recovery.json")):
            item = read_json_object(record_path)
            run_id = item.get("run_id")
            if (
                item.get("schema_version")
                != "toolathlon.budget-terminal-evaluator-recovery.v1"
                or item.get("policy") != EVALUATOR_POLICY
                or not isinstance(run_id, str)
            ):
                raise ContractError("nested budget-terminal evaluator recovery differs")
            incidents_by_run.setdefault(run_id, item)

    recovered: list[dict[str, Any]] = []
    runs_root = output_root / "runs"
    if runs_root.is_dir():
        for run_path in sorted(runs_root.glob("*/*/*/run.json")):
            run = read_json_object(run_path)
            if str(run.get("run_id")) in incidents_by_run:
                continue
            evaluator_path = run_path.parent / "evaluator/eval_res.json"
            if not evaluator_path.is_file():
                continue
            evaluator = read_json_object(evaluator_path)
            if not (
                run.get("terminal_status") == "max_steps"
                and run.get("termination_reason") == "max_model_requests"
                and run.get("run_validity") == "valid"
                and run.get("verify_status") == "unavailable"
                and run.get("primary_failure_category") == "model_request_budget"
                and run.get("artifact_gate", {}).get("status") == "passed"
                and evaluator.get("pass") is None
            ):
                continue
            record = replay_budget_terminal_evaluator(
                run_path.parent,
                output_root=output_root,
                source_root=source_root,
                helper_path=helper_path,
            )
            incidents_by_run[str(record["run_id"])] = record
            recovered.append(record)

    if not recovered and aggregate_path.is_file():
        return list(incidents_by_run.values())
    if not incidents_by_run:
        return []
    record = {
        "schema_version": "toolathlon.budget-terminal-evaluator-recovery-set.v1",
        "created_at": utc_now(),
        "policy": EVALUATOR_POLICY,
        "scope": "valid Astra/Hermes model-request-budget terminals",
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_replay_per_incident": 1,
        "raw_agent_evidence_modified": False,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "incidents": list(incidents_by_run.values()),
    }
    write_json_atomic(aggregate_path, record, mode=0o644)
    write_sha256_manifest(
        output_root / BUDGET_EVALUATOR_RECOVERY_HASH_NAME,
        [aggregate_path],
        root=output_root,
    )
    return record["incidents"]


def _verify_frozen_m2(repo_root: Path) -> str:
    adapter_freeze = read_json_object(
        repo_root / "astra/benchmark/toolathlon-verified/freeze/adapter.freeze.json"
    )
    records = [
        item
        for item in adapter_freeze["implementation"]["files"]
        if item.get("path") == "astra/runners/toolathlon_verified/m2_batch.py"
    ]
    if len(records) != 1:
        raise ContractError("frozen m2_batch.py record is not unique")
    expected = records[0].get("sha256")
    actual = sha256_file(repo_root / "astra/runners/toolathlon_verified/m2_batch.py")
    if expected != actual:
        raise ContractError("m2_batch.py differs from adapter.freeze.json")
    return str(expected)


def _install_lifecycle_runner(helper_path: Path) -> None:
    def run(self: m2_batch.M2Batch, argv: list[str]) -> int:
        if argv[:3] != [sys.executable, "-m", "astra.runners.toolathlon_verified.lifecycle"]:
            raise ContractError("unexpected lifecycle command shape")
        command = [sys.executable, str(helper_path), "lifecycle", *argv[3:]]
        return subprocess.run(command, cwd=self.repo_root, check=False).returncode

    m2_batch.M2Batch._default_lifecycle_runner = run


def _disable_irrelevant_historical_recovery(hotfix: Any, output_root: Path) -> None:
    checkpoint_path = output_root / "checkpoint.json"
    provenance_path = output_root / "scheduler-hotfix-provenance.json"
    schema_pair_resume = False
    if checkpoint_path.is_file():
        checkpoint = read_json_object(checkpoint_path)
        schema_pair_resume = checkpoint.get("error") == "paired runtime tools/list Schema differs"
    if provenance_path.is_file():
        provenance = read_json_object(provenance_path)
        schema_pair_resume = schema_pair_resume or (
            provenance.get("policy")
            == "toolathlon.paired-tools-list.normalize-unordered-terminal-commands.v1"
            and provenance.get("recovery_record") is None
        )
    if schema_pair_resume:
        hotfix._scheduler_incident = lambda _output_root: (set(), None)


def _gate_v2_attempt_role(run: dict[str, Any]) -> str:
    replacement = m2_batch.observation_value(
        run.get("replacement_for_run_id"), "run.replacement_for_run_id"
    )
    return "original" if replacement is None else "replacement"


def _gate_v2_pending_hermes_drain_projection(
    directory: Path,
) -> tuple[m2_batch.Attempt, dict[str, Any]] | None:
    """Qualify a complete run whose frozen finalizer stopped at drain validation."""
    run_path = directory / "run.json"
    resolved_path = directory / "resolved-config.json"
    if not run_path.is_file() or not resolved_path.is_file():
        return None
    run = read_json_object(run_path)
    if (
        run.get("system_id") != "hermes"
        or run.get("artifact_gate", {}).get("status")
        != "pending_cleanup_and_validation"
    ):
        return None
    if (
        run.get("terminal_status") != "completed"
        or run.get("termination_reason") != "product_exit"
        or run.get("run_validity") != "valid"
        or run.get("verify_status") not in {"pass", "no_pass"}
    ):
        raise ContractError("Gate v2 pending drain is not a completed Hermes run")

    model_rows = artifact_contract.read_jsonl(
        directory / "model-usage.jsonl", allow_empty=False
    )
    adapter_rows = artifact_contract.read_jsonl(
        directory / "adapter-events.jsonl", allow_empty=False
    )
    starts = {
        str(row["model_request_id"]): row
        for row in model_rows
        if row.get("event") == "model_request.started"
    }
    completions = {
        str(row["model_request_id"]): row
        for row in model_rows
        if row.get("event") == "model_request.completed"
    }
    stopped = [row for row in model_rows if row.get("event") == "proxy.stopped"]
    agent_ends = [
        row for row in adapter_rows if row.get("event") == "agent.execution_end"
    ]
    drain = run.get("adapter", {}).get("post_terminal_model_drain")
    budget = run.get("model_budget")
    if (
        len(stopped) != 1
        or len(agent_ends) != 1
        or not isinstance(drain, dict)
        or drain.get("settled") is not False
        or not isinstance(drain.get("timeout_seconds"), (int, float))
        or not isinstance(drain.get("provider_requests_forwarded"), int)
        or not isinstance(drain.get("provider_requests_completed"), int)
        or not isinstance(budget, dict)
        or set(starts) != set(completions)
    ):
        raise ContractError("Gate v2 pending Hermes drain structure is incomplete")
    snapshot_forwarded = drain["provider_requests_forwarded"]
    snapshot_completed = drain["provider_requests_completed"]
    missing_at_snapshot = snapshot_forwarded - snapshot_completed
    late_after_snapshot = len(starts) - snapshot_forwarded
    if (
        missing_at_snapshot < 0
        or late_after_snapshot < 0
        or not isinstance(drain.get("wait_seconds"), (int, float))
        or drain["wait_seconds"] < drain["timeout_seconds"]
    ):
        raise ContractError("Gate v2 pending Hermes drain counters do not reconcile")
    stopped_ns = stopped[0].get("monotonic_ns")
    agent_end_ns = agent_ends[0].get("monotonic_ns")
    if not isinstance(stopped_ns, int) or not isinstance(agent_end_ns, int):
        raise ContractError("Gate v2 pending Hermes boundary timestamps are missing")
    if abs(agent_end_ns - stopped_ns) > 5_000_000_000:
        raise ContractError("Gate v2 pending Hermes proxy/Agent boundary is not adjacent")
    if any(
        not isinstance(row.get("monotonic_ns"), int)
        or row["monotonic_ns"] > stopped_ns
        for row in starts.values()
    ):
        raise ContractError("Gate v2 pending Hermes request started after proxy stop")

    ordered = sorted(
        completions.values(), key=lambda row: int(row.get("monotonic_ns", -1))
    )
    late_snapshot_boundary = False
    if missing_at_snapshot >= 1 and late_after_snapshot == 0:
        closing = ordered[-missing_at_snapshot:]
    elif missing_at_snapshot == 0 and late_after_snapshot >= 1:
        late_snapshot_boundary = True
        late_ids = {
            request_id
            for request_id, row in starts.items()
            if isinstance(row.get("provider_request"), int)
            and row["provider_request"] > snapshot_forwarded
        }
        if len(late_ids) != late_after_snapshot:
            raise ContractError(
                "Gate v2 pending Hermes late-request identity is incomplete"
            )
        closing = [completions[request_id] for request_id in late_ids]
        closing.sort(key=lambda row: int(row.get("monotonic_ns", -1)))
    else:
        # A stale snapshot can both omit an in-flight request and precede a
        # later request, or can report equal counters while still saying it did
        # not settle.  Exact request identity is not inferable from aggregate
        # snapshot counters, so retain the final ordered terminal suffix as
        # evidence and let the fully reconciled stream decide validity.
        final_delta = len(starts) - snapshot_completed
        if final_delta < 0:
            raise ContractError(
                "Gate v2 pending Hermes final count predates the snapshot"
            )
        closing = ordered[-final_delta:] if final_delta else []
    closing_evidence: list[dict[str, Any]] = []
    timeout_seconds = float(drain["timeout_seconds"])
    bounded_disconnect_boundary = bool(closing) and not (
        missing_at_snapshot >= 1 and late_after_snapshot >= 1
    )
    for row in closing:
        completed_ns = row.get("monotonic_ns")
        if not isinstance(completed_ns, int):
            raise ContractError(
                "Gate v2 pending Hermes terminal timestamp is missing"
            )
        relative_seconds = (completed_ns - stopped_ns) / 1_000_000_000
        error_type = _observation_value(row.get("error_type"))
        is_bounded_disconnect = (
            row.get("success") is False
            and row.get("http_status") == 502
            and error_type == "downstream_disconnected"
            and 0 <= relative_seconds <= timeout_seconds
        )
        bounded_disconnect_boundary = (
            bounded_disconnect_boundary and is_bounded_disconnect
        )
        # A terminal that arrived after proxy stop must still be bounded by the
        # frozen drain timeout.  Its HTTP outcome is observability, not a hard
        # validity condition, once every forwarded request has a terminal.
        if relative_seconds > timeout_seconds:
            raise ContractError(
                "Gate v2 pending Hermes terminal exceeds the drain timeout"
            )
        closing_evidence.append(
            {
                "model_request_id": row.get("model_request_id"),
                "completed_monotonic_ns": completed_ns,
                "seconds_after_proxy_stopped": round(relative_seconds, 6),
                "success": row.get("success"),
                "http_status": row.get("http_status"),
                "error_type": error_type,
            }
        )
    failed = sum(row.get("success") is False for row in completions.values())
    final_budget_source = "run.json:model_budget"
    if (
        budget.get("provider_requests_forwarded") != len(starts)
        or budget.get("provider_requests_completed") != len(completions)
        or budget.get("provider_requests_failed") != failed
    ):
        proxy_state = read_json_object(directory / "model-proxy-state.json")
        final_budget = proxy_state.get("budget")
        if (
            not isinstance(final_budget, dict)
            or final_budget.get("provider_requests_forwarded") != len(starts)
            or final_budget.get("provider_requests_completed") != len(completions)
            or final_budget.get("provider_requests_failed") != failed
        ):
            raise ContractError("Gate v2 pending Hermes final counters differ")
        final_budget_source = "model-proxy-state.json:budget"

    # Run every frozen structural/content validator.  Only the already-qualified
    # drain boundary and the missing validation.end marker are relaxed here.
    current_boundary = artifact_contract._validate_agent_model_boundary

    def boundary_validator(
        adapters: list[dict[str, Any]],
        models: list[dict[str, Any]],
        candidate_run: dict[str, Any],
    ) -> None:
        try:
            current_boundary(adapters, models, candidate_run)
        except ContractError as exc:
            if (
                candidate_run.get("run_id") != run.get("run_id")
                or str(exc) != HERMES_DRAIN_TRIGGER
            ):
                raise

    artifact_contract._validate_agent_model_boundary = boundary_validator
    try:
        validation = artifact_contract.validate_run_artifacts(
            directory,
            verify_hash=False,
            require_validation_end=False,
        )
    finally:
        artifact_contract._validate_agent_model_boundary = current_boundary

    raw_files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    derived_hashes = [
        {
            "path": path.relative_to(directory).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in raw_files
    ]
    validation = {
        **validation,
        "hashed_artifacts": len(derived_hashes),
        "hash_source": "artifact_gate_v2_derived_manifest",
        "require_validation_end": False,
    }
    projected_run = json.loads(json.dumps(run))
    if bounded_disconnect_boundary:
        # Preserve the already-frozen projection shape for the previously
        # qualified disconnect race.
        drain_source = {
            "frozen_validator_error": HERMES_DRAIN_TRIGGER,
            "legacy_normalizer_error": (
                "Hermes drain-closing terminal is not the bounded disconnect race"
            ),
            "proxy_stopped_monotonic_ns": stopped_ns,
            "agent_execution_end_monotonic_ns": agent_end_ns,
            "drain_timeout_seconds": timeout_seconds,
            "snapshot_closing_terminal_count": len(closing_evidence),
            "snapshot_closing_terminals": closing_evidence,
        }
        incident_type = "bounded_post_shutdown_disconnect_terminal"
    else:
        # The drain snapshot may be stale even though the append-only model
        # stream and final counters are complete.  Treat the snapshot timing as
        # soft observability and retain every raw event for offline analysis.
        drain_source = {
            "frozen_validator_error": HERMES_DRAIN_TRIGGER,
            "legacy_normalizer_error": (
                "Hermes drain-closing terminal is not the bounded disconnect race"
            ),
            "snapshot_boundary": "fully_reconciled_after_unsettled_snapshot",
            "snapshot_provider_requests_forwarded": snapshot_forwarded,
            "snapshot_provider_requests_completed": snapshot_completed,
            "final_provider_requests_forwarded": len(starts),
            "final_provider_requests_completed": len(completions),
            "final_provider_requests_failed": failed,
            "final_budget_source": final_budget_source,
            "proxy_stopped_monotonic_ns": stopped_ns,
            "agent_execution_end_monotonic_ns": agent_end_ns,
            "drain_timeout_seconds": timeout_seconds,
            "snapshot_closing_terminal_count": len(closing_evidence),
            "snapshot_closing_terminals": closing_evidence,
        }
        incident_type = "reconciled_unsettled_drain_snapshot"
    if late_snapshot_boundary and bounded_disconnect_boundary:
        drain_source.update(
            {
                "legacy_normalizer_error": (
                    "Hermes pre-shutdown drain is not a timed-out snapshot"
                ),
                "snapshot_boundary": "late_request_after_snapshot",
                "snapshot_provider_requests_forwarded": snapshot_forwarded,
                "snapshot_provider_requests_completed": snapshot_completed,
                "late_request_count": late_after_snapshot,
                "final_budget_source": final_budget_source,
            }
        )
    projection = {
        "schema_version": "toolathlon.artifact-gate-v2-attempt-projection.v1",
        "policy": GATE_V2_POLICY,
        "classification": "soft_observability_incident",
        "run_id": run.get("run_id"),
        "task_id": run.get("task_id"),
        "system_id": run.get("system_id"),
        "directory": str(directory.resolve()),
        "attempt_role": _gate_v2_attempt_role(run),
        "replacement_for_run_id": m2_batch.observation_value(
            run.get("replacement_for_run_id"), "run.replacement_for_run_id"
        ),
        "hard_contract_passed": True,
        "hard_contract_source": "frozen_validators_plus_derived_raw_hash_manifest",
        "soft_incidents": [
            {
                "type": incident_type,
                "source": drain_source,
            }
        ],
        "raw_run_sha256": sha256_file(run_path),
        "raw_artifacts_manifest_sha256": sha256_file(
            directory / "artifacts.sha256"
        ),
        "derived_raw_artifact_hashes": derived_hashes,
        "raw_append_only_evidence_modified": False,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "replacement_authorized": False,
        "result_agnostic": True,
        "projected_run_validity": run.get("run_validity"),
        "projected_verify_status": run.get("verify_status"),
        "projected_primary_failure_category": run.get(
            "primary_failure_category"
        ),
        "validation": validation,
    }
    projected_run["artifact_gate_v2"] = {
        "policy": GATE_V2_POLICY,
        "status": "passed_with_observability_incidents",
        "classification": projection["classification"],
        "replacement_authorized": False,
        "raw_run_sha256": projection["raw_run_sha256"],
        "hash_source": "artifact_gate_v2_derived_manifest",
    }
    return (
        m2_batch.Attempt(
            directory=directory,
            run=projected_run,
            resolved=read_json_object(resolved_path),
            validation=validation,
        ),
        projection,
    )


def _gate_v2_pending_astra_count_projection(
    directory: Path,
) -> tuple[m2_batch.Attempt, dict[str, Any]] | None:
    """Qualify a complete Astra result stopped by the aggregate count check."""
    run_path = directory / "run.json"
    resolved_path = directory / "resolved-config.json"
    if not run_path.is_file() or not resolved_path.is_file():
        return None
    run = read_json_object(run_path)
    if (
        run.get("system_id") != "astra"
        or run.get("artifact_gate", {}).get("status")
        != "pending_cleanup_and_validation"
    ):
        return None
    expected_category = (
        "none" if run.get("verify_status") == "pass" else "completed_but_no_pass"
    )
    if (
        run.get("terminal_status") != "completed"
        or run.get("termination_reason") != "product_exit"
        or run.get("run_validity") != "valid"
        or run.get("verify_status") not in {"pass", "no_pass"}
        or run.get("primary_failure_category") != expected_category
    ):
        raise ContractError("Gate v2 pending Astra count is not a formal completion")

    trajectory_rows = artifact_contract.read_jsonl(
        directory / "trajectory.jsonl", allow_empty=True
    )
    evidence_run = json.loads(json.dumps(run))
    # The legacy evidence helper incorrectly required category=none for no_pass.
    # The evaluator conclusion remains unchanged; this copy is evidence-only.
    evidence_run["primary_failure_category"] = "none"
    evidence = _astra_model_count_vs_transport_evidence(
        trajectory_rows, evidence_run
    )
    if (
        evidence.get("native_transport_started_count")
        != evidence.get("native_transport_terminal_count")
        or evidence.get("native_transport_terminal_count")
        != evidence.get("native_tool_call_end_count")
        or evidence.get("server_declared_minus_transport_terminal_count", 0)
        <= 0
    ):
        raise ContractError("Gate v2 Astra native transports are not complete")

    current_tool_validator = artifact_contract._validate_tool_event_completeness

    def tool_validator(
        trajectory: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        candidate_run: dict[str, Any],
    ) -> None:
        if candidate_run.get("run_id") == run.get("run_id"):
            return
        current_tool_validator(trajectory, tools, candidate_run)

    artifact_contract._validate_tool_event_completeness = tool_validator
    try:
        validation = artifact_contract.validate_run_artifacts(
            directory,
            verify_hash=False,
            require_validation_end=False,
        )
    finally:
        artifact_contract._validate_tool_event_completeness = current_tool_validator

    raw_files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    derived_hashes = [
        {
            "path": path.relative_to(directory).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in raw_files
    ]
    validation = {
        **validation,
        "hashed_artifacts": len(derived_hashes),
        "hash_source": "artifact_gate_v2_derived_manifest",
        "require_validation_end": False,
    }
    projection = {
        "schema_version": "toolathlon.artifact-gate-v2-attempt-projection.v1",
        "policy": GATE_V2_POLICY,
        "classification": "soft_observability_incident",
        "run_id": run.get("run_id"),
        "task_id": run.get("task_id"),
        "system_id": run.get("system_id"),
        "directory": str(directory.resolve()),
        "attempt_role": _gate_v2_attempt_role(run),
        "replacement_for_run_id": m2_batch.observation_value(
            run.get("replacement_for_run_id"), "run.replacement_for_run_id"
        ),
        "hard_contract_passed": True,
        "hard_contract_source": "frozen_validators_plus_derived_raw_hash_manifest",
        "soft_incidents": [
            {
                "type": "server_model_tool_count_vs_complete_native_transports",
                "source": {
                    "frozen_validator_error": COUNT_SCOPE_TRIGGER,
                    "legacy_normalizer_error": (
                        "tool-count scope exception is not a completed or "
                        "product-failed Astra run"
                    ),
                    **evidence,
                },
            }
        ],
        "raw_run_sha256": sha256_file(run_path),
        "raw_artifacts_manifest_sha256": sha256_file(
            directory / "artifacts.sha256"
        ),
        "derived_raw_artifact_hashes": derived_hashes,
        "raw_append_only_evidence_modified": False,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "replacement_authorized": False,
        "result_agnostic": True,
        "projected_run_validity": run.get("run_validity"),
        "projected_verify_status": run.get("verify_status"),
        "projected_primary_failure_category": run.get(
            "primary_failure_category"
        ),
        "validation": validation,
    }
    projected_run = json.loads(json.dumps(run))
    projected_run["artifact_gate_v2"] = {
        "policy": GATE_V2_POLICY,
        "status": "passed_with_observability_incidents",
        "classification": projection["classification"],
        "replacement_authorized": False,
        "raw_run_sha256": projection["raw_run_sha256"],
        "hash_source": "artifact_gate_v2_derived_manifest",
    }
    return (
        m2_batch.Attempt(
            directory=directory,
            run=projected_run,
            resolved=read_json_object(resolved_path),
            validation=validation,
        ),
        projection,
    )


def _gate_v2_pending_projection(
    directory: Path,
) -> tuple[m2_batch.Attempt, dict[str, Any]] | None:
    hermes = _gate_v2_pending_hermes_drain_projection(directory)
    if hermes is not None:
        return hermes
    return _gate_v2_pending_astra_count_projection(directory)


def _gate_v2_soft_projection(
    attempt: m2_batch.Attempt,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return an in-memory formal projection for observability-only incidents."""
    run = attempt.run
    gate = run.get("artifact_gate")
    if not isinstance(gate, dict) or gate.get("status") != "passed":
        return None
    validator = gate.get("validator")
    soft_validators = {
        POLICY,
        COUNT_SCOPE_POLICY,
        HERMES_DRAIN_POLICY,
        HERMES_DRAIN_TIMEOUT_POLICY,
        HERMES_OPEN_REQUEST_POLICY,
        ASTRA_DEADLINE_POLICY,
    }
    if validator not in soft_validators:
        return None

    projected = json.loads(json.dumps(run))
    incident_type = str(validator)
    source_evidence: dict[str, Any] = {
        "artifact_gate_validator": validator,
        "artifact_gate_evidence_artifact": gate.get("evidence_artifact"),
    }
    if validator == HERMES_OPEN_REQUEST_POLICY:
        evidence_name = gate.get("evidence_artifact")
        if evidence_name != HERMES_OPEN_REQUEST_ARTIFACT:
            raise ContractError("Gate v2 Hermes evidence artifact is not frozen")
        evidence_path = attempt.directory / HERMES_OPEN_REQUEST_ARTIFACT
        evidence_document = read_json_object(evidence_path)
        evidence = evidence_document.get("evidence")
        if not isinstance(evidence, dict):
            raise ContractError("Gate v2 Hermes evidence is missing")
        original = evidence.get("original_formal_result")
        open_request = evidence.get("open_request")
        drain_boundary = evidence.get("drain_boundary")
        drain_boundary_source = "observed"
        settled_snapshot = evidence.get("settled_drain_snapshot")
        if (
            drain_boundary is None
            and isinstance(settled_snapshot, dict)
            and settled_snapshot.get("settled") is True
        ):
            # The first recovery artifact predates the explicit drain_boundary
            # field.  Its settled snapshot plus the later unterminalized request
            # is the same recorded post-settled shutdown race.
            drain_boundary = "post_settled_shutdown_race"
            drain_boundary_source = "derived_from_legacy_settled_snapshot"
        if (
            evidence_document.get("policy") != HERMES_OPEN_REQUEST_POLICY
            or evidence.get("policy") != HERMES_OPEN_REQUEST_POLICY
            or evidence.get("open_request_count") != 1
            or drain_boundary
            not in {"drain_timeout_open_request", "post_settled_shutdown_race"}
            or not isinstance(open_request, dict)
            or open_request.get("terminal_event_observed") is not False
            or not isinstance(original, dict)
            or original.get("run_validity") != "valid"
            or original.get("verify_status") not in {"pass", "no_pass"}
        ):
            raise ContractError(
                "Gate v2 Hermes open-request evidence is not a qualified "
                "shutdown-boundary incident"
            )
        projected["run_validity"] = "valid"
        projected["verify_status"] = original["verify_status"]
        projected["primary_failure_category"] = original.get(
            "primary_failure_category"
        )
        incident_type = "single_open_model_request_at_proxy_shutdown"
        source_evidence.update(
            {
                "path": str(evidence_path),
                "sha256": sha256_file(evidence_path),
                "drain_boundary": drain_boundary,
                "drain_boundary_source": drain_boundary_source,
                "open_request_count": 1,
                "original_formal_result": original,
            }
        )

    replacement_for = m2_batch.observation_value(
        run.get("replacement_for_run_id"), "run.replacement_for_run_id"
    )
    projection = {
        "schema_version": "toolathlon.artifact-gate-v2-attempt-projection.v1",
        "policy": GATE_V2_POLICY,
        "classification": "soft_observability_incident",
        "run_id": run.get("run_id"),
        "task_id": run.get("task_id"),
        "system_id": run.get("system_id"),
        "directory": str(attempt.directory.resolve()),
        "attempt_role": _gate_v2_attempt_role(run),
        "replacement_for_run_id": replacement_for,
        "hard_contract_passed": True,
        "hard_contract_source": "existing_artifact_contract_validation",
        "soft_incidents": [
            {
                "type": incident_type,
                "source": source_evidence,
            }
        ],
        "raw_run_sha256": sha256_file(attempt.directory / "run.json"),
        "raw_artifacts_manifest_sha256": sha256_file(
            attempt.directory / "artifacts.sha256"
        ),
        "raw_append_only_evidence_modified": False,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "replacement_authorized": False,
        "result_agnostic": True,
        "projected_run_validity": projected.get("run_validity"),
        "projected_verify_status": projected.get("verify_status"),
        "projected_primary_failure_category": projected.get(
            "primary_failure_category"
        ),
        "validation": {"status": "passed"},
    }
    projected["artifact_gate_v2"] = {
        "policy": GATE_V2_POLICY,
        "status": "passed_with_observability_incidents",
        "classification": projection["classification"],
        "replacement_authorized": False,
        "raw_run_sha256": projection["raw_run_sha256"],
    }
    return projected, projection


def _gate_v2_write_json_once(path: Path, value: dict[str, Any]) -> None:
    if path.is_file():
        existing = read_json_object(path)
        if existing != value:
            raise ContractError(f"Gate v2 derived artifact changed: {path}")
        return
    write_json_atomic(path, value, mode=0o644)


def _gate_v2_slot_decisions(
    output_root: Path, projections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    by_slot: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in projections:
        key = (str(item.get("system_id")), str(item.get("task_id")))
        by_slot.setdefault(key, []).append(item)
    for (system, task_id), items in sorted(by_slot.items()):
        originals = [item for item in items if item.get("attempt_role") == "original"]
        if len(originals) != 1:
            continue
        original = originals[0]
        task_root = output_root / "runs" / system / task_id
        supplemental: list[str] = []
        if task_root.is_dir():
            for path in sorted(task_root.glob("*/run.json")):
                raw = read_json_object(path)
                replacement = m2_batch.observation_value(
                    raw.get("replacement_for_run_id"),
                    "run.replacement_for_run_id",
                )
                if replacement == original.get("run_id"):
                    supplemental.append(str(raw.get("run_id")))
        decisions.append(
            {
                "system_id": system,
                "task_id": task_id,
                "effective_run_id": original.get("run_id"),
                "effective_attempt_role": "original",
                "supplemental_non_effective_run_ids": supplemental,
                "selection_rule": "original_a1_precedence_for_soft_observability",
                "result_agnostic": True,
                "replacement_counted_as_effective": False,
            }
        )
    return decisions


def _write_gate_v2_projection_bundle(
    output_root: Path,
    helper_path: Path,
    projections_by_run_id: dict[str, dict[str, Any]],
) -> Path:
    output_root = output_root.resolve()
    root = output_root / GATE_V2_ROOT_NAME
    attempts_root = root / "attempt-projections"
    attempts_root.mkdir(parents=True, exist_ok=True)
    policy_path = root / GATE_V2_POLICY_NAME
    policy = {
        "schema_version": "toolathlon.artifact-gate-v2-policy.v1",
        "policy": GATE_V2_POLICY,
        "hard_gate": [
            "required_artifact_structure_and_hashes",
            "freeze_and_identity_consistency",
            "reset_and_secret_boundary",
            "paired_runtime_tool_surface",
        ],
        "soft_observability": [
            "shutdown_or_drain_terminal_race",
            "server_declared_tool_count_vs_transport_scope",
            "deadline_summary_boundary",
            "budget_terminal_transport_summary_boundary",
        ],
        "selection": {
            "original_a1_precedence": True,
            "result_agnostic": True,
            "supplemental_replacement_is_not_effective": True,
        },
        "retry": {
            "automatic_replacement_maximum": 1,
            "replacement_exhausted": "record_unavailable_and_continue",
        },
        "historical_raw_artifacts_modified": False,
        "formal_attempt_rerun": False,
    }
    _gate_v2_write_json_once(policy_path, policy)

    for run_id, projection in sorted(projections_by_run_id.items()):
        _gate_v2_write_json_once(attempts_root / f"{run_id}.json", projection)

    all_projection_paths = sorted(attempts_root.glob("*.json"))
    all_projections = [read_json_object(path) for path in all_projection_paths]
    aggregate_path = output_root / GATE_V2_PROJECTION_NAME
    aggregate = {
        "schema_version": "toolathlon.artifact-gate-v2-projection.v1",
        "policy": GATE_V2_POLICY,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path),
        "policy_artifact": str(policy_path),
        "policy_sha256": sha256_file(policy_path),
        "historical_raw_artifacts_modified": False,
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "incidents": all_projections,
        "slot_decisions": _gate_v2_slot_decisions(output_root, all_projections),
        "validation": {"status": "passed"},
    }
    write_json_atomic(aggregate_path, aggregate, mode=0o644)
    aggregate_hash = output_root / GATE_V2_PROJECTION_HASH_NAME
    aggregate_hash.write_text(
        f"{sha256_file(aggregate_path)}  {aggregate_path.name}\n",
        encoding="utf-8",
    )
    manifest_inputs = [policy_path, *all_projection_paths]
    write_sha256_manifest(root / "artifacts.sha256", manifest_inputs, root=root)
    return aggregate_path


def install_artifact_gate_v2(output_root: Path, helper_path: Path) -> Path:
    """Install the M3 scheduler projection without rewriting run evidence."""
    output_root = output_root.resolve()
    projections_by_run_id: dict[str, dict[str, Any]] = {}
    original_load_attempt = m2_batch.load_attempt

    def remember_projection(projection: dict[str, Any]) -> None:
        run_id = str(projection.get("run_id"))
        known = projections_by_run_id.get(run_id)
        if known is not None and known != projection:
            raise ContractError("Gate v2 attempt projection changed")
        projections_by_run_id[run_id] = projection

    for run_path in sorted(output_root.glob("runs/*/*/*/run.json")):
        raw_run = read_json_object(run_path)
        task_id = raw_run.get("task_id")
        system_id = raw_run.get("system_id")
        if not isinstance(task_id, str) or system_id not in {"astra", "hermes"}:
            raise ContractError(f"Gate v2 run identity is invalid: {run_path}")
        try:
            attempt = original_load_attempt(
                run_path.parent, task_id=task_id, system=system_id
            )
        except ContractError:
            try:
                pending = _gate_v2_pending_projection(
                    run_path.parent
                )
            except ContractError:
                pending = None
            if pending is not None:
                _pending_attempt, projection = pending
                remember_projection(projection)
            # Incomplete/pre-Agent attempts remain governed by their existing
            # structural recovery policies; Gate v2 never guesses missing raw data.
            continue
        result = _gate_v2_soft_projection(attempt)
        if result is not None:
            _projected_run, projection = result
            remember_projection(projection)

    projection_path = _write_gate_v2_projection_bundle(
        output_root, helper_path, projections_by_run_id
    )

    if getattr(m2_batch.load_attempt, "_toolathlon_artifact_gate_v2", False):
        return projection_path

    def load_attempt(
        directory: Path, *, task_id: str, system: str
    ) -> m2_batch.Attempt:
        try:
            attempt = original_load_attempt(
                directory, task_id=task_id, system=system
            )
        except ContractError as original_error:
            try:
                pending = _gate_v2_pending_projection(directory)
            except ContractError:
                raise original_error
            if pending is None:
                raise
            pending_attempt, projection = pending
            if (
                pending_attempt.run.get("task_id") != task_id
                or pending_attempt.run.get("system_id") != system
            ):
                raise ContractError("Gate v2 pending attempt identity mismatch")
            known_before = str(projection["run_id"]) in projections_by_run_id
            remember_projection(projection)
            if not known_before:
                _write_gate_v2_projection_bundle(
                    output_root, helper_path, projections_by_run_id
                )
            return pending_attempt
        result = _gate_v2_soft_projection(attempt)
        if result is None:
            return attempt
        projected_run, projection = result
        run_id = str(attempt.run["run_id"])
        known = run_id in projections_by_run_id
        remember_projection(projection)
        if not known:
            _write_gate_v2_projection_bundle(
                output_root, helper_path, projections_by_run_id
            )
        return m2_batch.Attempt(
            directory=attempt.directory,
            run=projected_run,
            resolved=attempt.resolved,
            validation={
                **attempt.validation,
                "artifact_gate_v2": "passed_with_observability_incidents",
            },
        )

    setattr(load_attempt, "_toolathlon_artifact_gate_v2", True)
    m2_batch.load_attempt = load_attempt

    original_decide_slot = m2_batch.decide_slot

    def decide_slot(candidates: list[m2_batch.Attempt]) -> m2_batch.SlotDecision:
        originals = [
            item
            for item in candidates
            if _gate_v2_attempt_role(item.run) == "original"
        ]
        replacements = [item for item in candidates if item not in originals]
        if len(originals) == 1:
            original = originals[0]
            gate_v2 = original.run.get("artifact_gate_v2")
            if (
                isinstance(gate_v2, dict)
                and gate_v2.get("classification")
                == "soft_observability_incident"
            ):
                replacement = replacements[0] if len(replacements) == 1 else None
                if len(replacements) > 1:
                    raise ContractError("Gate v2 found more than one replacement")
                return m2_batch.SlotDecision(
                    "complete",
                    original,
                    original,
                    replacement,
                    "Gate v2 original a1 precedence for soft observability",
                )
        decision = original_decide_slot(candidates)
        if (
            decision.state == "blocked"
            and decision.original is not None
            and decision.replacement is not None
            and decision.replacement.run.get("run_validity") == "infra_invalid"
        ):
            projected_run = json.loads(json.dumps(decision.replacement.run))
            projected_run["artifact_gate_v2"] = {
                "policy": GATE_V2_POLICY,
                "status": "unavailable_continue",
                "classification": "replacement_exhausted",
                "replacement_exhausted": True,
                "continue_batch": True,
            }
            unavailable = m2_batch.Attempt(
                directory=decision.replacement.directory,
                run=projected_run,
                resolved=decision.replacement.resolved,
                validation={
                    **decision.replacement.validation,
                    "artifact_gate_v2": "unavailable_continue",
                },
            )
            return m2_batch.SlotDecision(
                "complete",
                unavailable,
                decision.original,
                decision.replacement,
                "Gate v2 records exhausted infrastructure replacement as unavailable",
            )
        return decision

    setattr(decide_slot, "_toolathlon_artifact_gate_v2", True)
    m2_batch.decide_slot = decide_slot

    original_validate_formal = m2_batch.validate_formal_effective

    def validate_formal_effective(attempt: m2_batch.Attempt) -> None:
        gate_v2 = attempt.run.get("artifact_gate_v2")
        if (
            isinstance(gate_v2, dict)
            and gate_v2.get("status") == "unavailable_continue"
        ):
            if (
                attempt.run.get("run_validity") != "infra_invalid"
                or attempt.run.get("verify_status") != "unavailable"
                or gate_v2.get("replacement_exhausted") is not True
                or gate_v2.get("continue_batch") is not True
            ):
                raise ContractError("Gate v2 unavailable slot is not qualified")
            return
        original_validate_formal(attempt)

    setattr(validate_formal_effective, "_toolathlon_artifact_gate_v2", True)
    m2_batch.validate_formal_effective = validate_formal_effective
    return projection_path


def _m3_outer_provenance_record(
    *, helper_path: Path, launcher_path: Path
) -> dict[str, Any]:
    return {
        "schema_version": "toolathlon.m3-outer-lifecycle-hotfix.v1",
        "policy": M3_OUTER_POLICY,
        "helper": str(helper_path.resolve()),
        "helper_sha256": sha256_file(helper_path.resolve()),
        "launcher": str(launcher_path.resolve()),
        "launcher_sha256": sha256_file(launcher_path.resolve()),
        "workers": 1,
        "m2_evidence_modified": False,
        "hermes_normalizer_modified": False,
        "hermes_artifact_gate_modified": False,
        "lifecycle_entrypoint": [
            sys.executable,
            str(helper_path.resolve()),
            "lifecycle",
        ],
        "runtime_reconciliation": [
            POLICY,
            COUNT_SCOPE_POLICY,
            HERMES_DRAIN_POLICY,
            HERMES_DRAIN_TIMEOUT_POLICY,
            HERMES_OPEN_REQUEST_POLICY,
            ASTRA_DEADLINE_POLICY,
            EVALUATOR_POLICY,
            PRODUCT_FAILURE_POLICY,
            INTERRUPTION_POLICY,
            PREPROCESS_INFRA_POLICY,
            TASK_TRACKER_SETUP_POLICY,
            DATASET_REPAIR_POLICY,
            DATASET_REPAIR_HARNESS_POLICY,
            GATE_V2_POLICY,
        ],
    }


def _m3_outer_amendment_references(
    provenance: dict[str, Any],
) -> list[dict[str, str]]:
    raw = provenance.get("outer_lifecycle_hotfix_amendments")
    if raw is None:
        legacy = provenance.get("outer_lifecycle_hotfix_amendment")
        raw = [legacy] if legacy is not None else []
    if not isinstance(raw, list):
        raise ContractError("M3 outer lifecycle amendment history is invalid")
    references: list[dict[str, str]] = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
        ):
            raise ContractError("M3 outer lifecycle amendment reference is invalid")
        references.append(
            {"path": str(item["path"]), "sha256": str(item["sha256"])}
        )
    return references


def _verify_m3_outer_amendment_reference(
    reference: dict[str, str], output_root: Path
) -> tuple[Path, dict[str, Any]]:
    path = Path(reference["path"]).resolve()
    if output_root.resolve() not in path.parents:
        raise ContractError("M3 outer lifecycle amendment escapes output root")
    hash_path = path.with_suffix(".sha256")
    if not path.is_file() or not hash_path.is_file():
        raise ContractError("M3 outer lifecycle amendment is incomplete")
    actual_sha256 = sha256_file(path)
    expected_manifest = f"{actual_sha256}  {path.name}\n"
    amendment = read_json_object(path)
    if (
        reference["sha256"] != actual_sha256
        or hash_path.read_text(encoding="utf-8") != expected_manifest
        or amendment.get("policy") != M3_OUTER_AMENDMENT_POLICY
    ):
        raise ContractError("M3 outer lifecycle amendment is invalid")
    return path, amendment


def _validate_m3_outer_change(
    previous: dict[str, Any], active: dict[str, Any]
) -> None:
    immutable = (
        "schema_version",
        "policy",
        "helper",
        "launcher",
        "launcher_sha256",
        "workers",
        "m2_evidence_modified",
        "hermes_normalizer_modified",
        "hermes_artifact_gate_modified",
        "lifecycle_entrypoint",
    )
    if any(previous.get(field) != active.get(field) for field in immutable):
        raise ContractError("M3 outer amendment changes more than helper policy")
    old_policies = previous.get("runtime_reconciliation")
    new_policies = active.get("runtime_reconciliation")
    if (
        not isinstance(old_policies, list)
        or not isinstance(new_policies, list)
        or any(policy not in new_policies for policy in old_policies)
    ):
        raise ContractError("M3 outer amendment removes a runtime policy")


def _qualified_m3_amendment_trigger(
    output_root: Path, checkpoint: dict[str, Any]
) -> tuple[Path, list[dict[str, Any]], str]:
    candidates = (
        (
            output_root / GATE_V2_PROJECTION_NAME,
            GATE_V2_POLICY,
            "adopt structural-hard/observability-soft Artifact Gate v2, "
            "select original a1 without result-based replacement selection, "
            "and preserve all supplemental attempt evidence",
        ),
        (
            output_root / DATASET_REPAIR_HARNESS_NAME,
            DATASET_REPAIR_HARNESS_POLICY,
            "classify the successful a3 preprocess/Gateway followed by the "
            "outer-lifecycle overlay evidence boundary defect as "
            "infrastructure-invalid and authorize only a4",
        ),
        (
            output_root / DATASET_REPAIR_NAME,
            DATASET_REPAIR_POLICY,
            "apply the authorized task-container-only WooCommerce batch-size "
            "overlay and allow one first-product dataset repair run",
        ),
        (
            output_root / COUNT_SCOPE_RECOVERY_NAME,
            COUNT_SCOPE_POLICY,
            "record the Astra server model-tool aggregate versus complete "
            "native transports for a product failure without rerunning it",
        ),
        (
            output_root / PRODUCT_FAILURE_RECOVERY_NAME,
            PRODUCT_FAILURE_POLICY,
            "accept a valid product failure with evaluator unavailable as the "
            "effective result without rerunning the product",
        ),
        (
            output_root / TASK_TRACKER_SETUP_RECOVERY_NAME,
            TASK_TRACKER_SETUP_POLICY,
            "classify the task-tracker Hermes a2 Docker-copy boundary as "
            "pre-product infrastructure-invalid and authorize only the "
            "explicit task-specific a3 recovery",
        ),
        (
            output_root / PREPROCESS_INFRA_RECOVERY_NAME,
            PREPROCESS_INFRA_POLICY,
            "classify one pre-Agent Toolathlon preprocess failure as "
            "infrastructure-invalid and authorize only a2",
        ),
        (
            output_root / INTERRUPTION_RECOVERY_NAME,
            INTERRUPTION_POLICY,
            "classify one bounded user interruption before Agent start as "
            "infrastructure-invalid and authorize only a2",
        ),
        (
            output_root / BUDGET_EVALUATOR_RECOVERY_NAME,
            EVALUATOR_POLICY,
            "replay the frozen task-specific evaluator once after a valid "
            "100-request product terminal without rerunning the Agent",
        ),
        (
            output_root / ASTRA_DEADLINE_RECOVERY_NAME,
            ASTRA_DEADLINE_POLICY,
            "preserve one Astra Agent deadline as a valid product failure while "
            "recording the preempted server summary and open drain request",
        ),
        (
            output_root / HERMES_OPEN_REQUEST_RECOVERY_NAME,
            HERMES_OPEN_REQUEST_POLICY,
            "classify one bounded drain-timeout or post-drain Model Proxy race as "
            "infrastructure-invalid and authorize only a2",
        ),
        (
            output_root / HERMES_DRAIN_RECOVERY_NAME,
            HERMES_DRAIN_TIMEOUT_POLICY,
            "generalize Hermes timed-out drain reconciliation to bounded "
            "timeout-boundary terminals",
        ),
    )
    checkpoint_error = str(checkpoint.get("error"))
    checkpoint_run_id: str | None = None
    checkpoint_sequence = checkpoint.get("scheduler_event_sequence")
    scheduler_path = output_root / "scheduler-events.jsonl"
    if isinstance(checkpoint_sequence, int) and scheduler_path.is_file():
        rows = artifact_contract.read_jsonl(scheduler_path, allow_empty=False)
        blocked = [
            row for row in rows if row.get("sequence") == checkpoint_sequence
        ]
        prior = [
            row
            for row in rows
            if row.get("sequence") == checkpoint_sequence - 1
            and isinstance(row.get("run_id"), str)
        ]
        prior_is_qualified_terminal = (
            len(prior) == 1
            and (
                prior[0].get("event") == "attempt.artifact_gate_passed"
                or (
                    prior[0].get("event") == "attempt.process_interrupted"
                    and prior[0].get("error_type") == "KeyboardInterrupt"
                )
            )
        )
        if (
            len(blocked) == 1
            and blocked[0].get("event") == "batch.blocked"
            and blocked[0].get("error") == checkpoint_error
            and prior_is_qualified_terminal
        ):
            checkpoint_run_id = str(prior[0]["run_id"])
    for recovery_path, policy, reason in candidates:
        if not recovery_path.is_file():
            continue
        recovery = read_json_object(recovery_path)
        incidents = recovery.get("incidents")
        if not isinstance(incidents, list):
            raise ContractError("M3 outer amendment recovery incidents are invalid")
        matched = [
            item
            for item in incidents
            if isinstance(item, dict)
            and item.get("policy") == policy
            and (
                str(item.get("directory")) in checkpoint_error
                or (
                    policy == GATE_V2_POLICY
                    and item.get("attempt_role") == "original"
                    and f"{item.get('system_id')}/{item.get('task_id')}"
                    in checkpoint_error
                    and checkpoint_error.endswith(
                        "the one allowed replacement is not valid"
                    )
                )
                or (
                    policy == INTERRUPTION_POLICY
                    and (
                        (
                            f"{item.get('system_id')}/{item.get('task_id')}"
                            in checkpoint_error
                            and "required run artifacts are missing"
                            in checkpoint_error
                        )
                        or (
                            checkpoint_run_id is not None
                            and item.get("run_id") == checkpoint_run_id
                        )
                    )
                )
                or (
                    policy in {EVALUATOR_POLICY, PRODUCT_FAILURE_POLICY}
                    and checkpoint_run_id is not None
                    and item.get("run_id") == checkpoint_run_id
                    and checkpoint_error
                    in {
                        "missing server declaration is not an Astra budget terminal",
                        "budget-terminal evaluator replay is missing",
                        FORMAL_TRIGGER,
                    }
                )
            )
        ]
        if not matched:
            continue
        for item in matched:
            base_common = (
                item.get("formal_attempt_rerun") is False
                and item.get("agent_rerun") is False
                and item.get("validation", {}).get("status") == "passed"
            )
            common = (
                base_common
                and item.get("evaluator_rerun") is False
                and item.get("raw_append_only_evidence_modified") is False
            )
            if policy == GATE_V2_POLICY:
                qualified = (
                    common
                    and item.get("classification")
                    == "soft_observability_incident"
                    and item.get("attempt_role") == "original"
                    and item.get("hard_contract_passed") is True
                    and item.get("result_agnostic") is True
                    and item.get("replacement_authorized") is False
                    and item.get("projected_run_validity") == "valid"
                    and item.get("projected_verify_status")
                    in {"pass", "no_pass"}
                    and isinstance(item.get("raw_run_sha256"), str)
                    and isinstance(
                        item.get("raw_artifacts_manifest_sha256"), str
                    )
                )
            elif policy == PRODUCT_FAILURE_POLICY:
                qualified = (
                    common
                    and item.get("system_id") in {"astra", "hermes"}
                    and item.get("terminal_status") in {"crashed", "failed"}
                    and item.get("termination_reason") == "product_exit"
                    and item.get("run_validity") == "valid"
                    and item.get("primary_failure_category") == "product_error"
                    and item.get("verify_status") == "unavailable"
                    and item.get("replacement_authorized") is False
                    and item.get("effective_result") is True
                    and item.get("validation", {}).get("status") == "passed"
                )
            elif policy == COUNT_SCOPE_POLICY:
                qualified = (
                    common
                    and item.get("formal_attempt_rerun") is False
                    and item.get("agent_rerun") is False
                    and item.get("evaluator_rerun") is False
                    and item.get("raw_append_only_evidence_modified") is False
                    and item.get("validation", {}).get("status") == "passed"
                    and isinstance(item.get("native_transport_started_count"), int)
                    and isinstance(item.get("native_transport_terminal_count"), int)
                    and (
                        (
                            isinstance(
                                item.get("server_declared_model_tool_call_count"), int
                            )
                            and isinstance(
                                item.get("server_declared_minus_transport_terminal_count"),
                                int,
                            )
                            and item.get(
                                "server_declared_minus_transport_terminal_count"
                            ) > 0
                            and item.get("run_disposition")
                            in {
                                None,
                                "completed_evaluator_conclusion",
                                "product_failure_evaluator_unavailable",
                            }
                        )
                        or (
                            item.get("run_disposition")
                            == "model_request_budget_terminal"
                            and item.get("open_transport_count") == 1
                            and item.get("native_transport_started_count")
                            == item.get("native_transport_terminal_count") + 1
                            and isinstance(
                                item.get("open_transport_call_id_sha256"), str
                            )
                        )
                    )
                )
            elif policy == DATASET_REPAIR_HARNESS_POLICY:
                qualified = (
                    common
                    and item.get("failed_scheduler_ordinal") == 3
                    and item.get("authorized_replacement_scheduler_ordinal") == 4
                    and item.get("authorized_replacement_product_attempt_ordinal")
                    == 1
                    and item.get("authorized_replacement_for_run_id") is None
                    and item.get("classification")
                    == "outer_lifecycle_overlay_evidence_prepared_boundary_violation"
                    and item.get("overlay_repair_succeeded") is True
                    and item.get("preprocess_succeeded") is True
                    and item.get("gateway_succeeded") is True
                    and item.get("agent_started") is False
                    and item.get("product_started") is False
                    and item.get("model_proxy_started") is False
                    and item.get("tools_list_started") is False
                    and item.get("evaluator_started") is False
                    and item.get("formal_run_artifacts_complete") is False
                    and item.get("projected_run_validity") == "infra_invalid"
                    and item.get("projected_verify_status") == "unavailable"
                    and item.get("projected_primary_failure_category")
                    == "environment_error"
                    and item.get("failed_attempt_directory_modified") is False
                    and item.get("general_automatic_replacement_maximum") == 1
                    and item.get("general_retry_policy_modified") is False
                    and item.get("task_specific_harness_replacement_maximum") == 1
                    and item.get("no_attempt_after_a4_failure") is True
                    and item.get("same_overlay_for_astra_and_hermes") is True
                    and item.get("frozen_toolathlon_source_modified") is False
                    and item.get("overlay_artifact", {}).get("defective_location")
                    == "output_root_top_level"
                    and item.get("overlay_artifact", {}).get("corrected_location")
                    == "task-state/preprocess-overlay.json"
                    and item.get("source_overlay", {}).get("scope")
                    == "task_container_copy_only"
                    and item.get("source_overlay", {}).get("original_sha256")
                    == DATASET_REPAIR_ORIGINAL_SHA256
                    and item.get("source_overlay", {}).get(
                        "patched_container_copy_sha256"
                    )
                    == DATASET_REPAIR_PATCHED_SHA256
                    and item.get("authorization")
                    == "user_accepted_a4_harness_infrastructure_replacement"
                )
            elif policy == DATASET_REPAIR_POLICY:
                qualified = (
                    common
                    and item.get("failed_run_ids")
                    and item.get("failed_scheduler_ordinals") == [1, 2]
                    and item.get("repair_scheduler_ordinal") == 3
                    and item.get("repair_product_attempt_ordinal") == 1
                    and item.get("repair_replacement_for_run_id") is None
                    and item.get("agent_started_in_failed_runs") is False
                    and item.get("model_proxy_started_in_failed_runs") is False
                    and item.get("evaluator_started_in_failed_runs") is False
                    and item.get("failed_attempt_directories_modified") is False
                    and item.get("general_automatic_replacement_maximum") == 1
                    and item.get("general_retry_policy_modified") is False
                    and item.get("task_specific_dataset_repair_maximum") == 1
                    and item.get("no_attempt_after_repair_failure") is True
                    and item.get(
                        "a2_no_a3_projection_superseded_by_authorized_repair"
                    )
                    is True
                    and item.get("same_overlay_for_astra_and_hermes") is True
                    and item.get("frozen_toolathlon_source_modified") is False
                    and item.get("source_overlay", {}).get("scope")
                    == "task_container_copy_only"
                    and item.get("source_overlay", {}).get("original_sha256")
                    == DATASET_REPAIR_ORIGINAL_SHA256
                    and item.get("source_overlay", {}).get(
                        "patched_container_copy_sha256"
                    )
                    == DATASET_REPAIR_PATCHED_SHA256
                )
            elif policy == TASK_TRACKER_SETUP_POLICY:
                resource_pressure = item.get("resource_pressure")
                container_cleanup = item.get("container_cleanup")
                qualified = (
                    common
                    and item.get("classification")
                    == "docker_copy_boundary_failure_under_host_resource_pressure"
                    and item.get("task_id") == TASK_TRACKER_SETUP_TASK
                    and item.get("system_id") == TASK_TRACKER_SETUP_SYSTEM
                    and item.get("position") == TASK_TRACKER_SETUP_POSITION
                    and item.get("attempt_ordinal") == 2
                    and item.get("authorized_scheduler_ordinal") == 3
                    and item.get("authorized_product_attempt_ordinal") == 1
                    and item.get("authorized_replacement_for_run_id") is None
                    and item.get("container_started") is True
                    and item.get("container_ready") is True
                    and item.get("preprocess_started") is False
                    and item.get("gateway_started") is False
                    and item.get("tools_list_started") is False
                    and item.get("agent_started") is False
                    and item.get("product_started") is False
                    and item.get("model_proxy_started") is False
                    and item.get("evaluator_started") is False
                    and item.get("formal_run_artifacts_complete") is False
                    and item.get("projected_run_validity") == "infra_invalid"
                    and item.get("projected_verify_status") == "unavailable"
                    and item.get("projected_primary_failure_category")
                    == "environment_error"
                    and item.get("failed_attempt_directories_modified") is False
                    and item.get("general_automatic_replacement_maximum") == 1
                    and item.get("general_retry_policy_modified") is False
                    and item.get(
                        "task_specific_container_setup_recovery_maximum"
                    )
                    == 1
                    and item.get("no_a4_allowed") is True
                    and item.get("authorization")
                    == "user_confirmed_task_specific_a3_recovery"
                    and isinstance(resource_pressure, dict)
                    and resource_pressure.get("sample_count", 0) > 0
                    and resource_pressure.get("max_load_average_1m", 0) >= 32
                    and resource_pressure.get("min_swap_free_bytes", 134217728)
                    < 134217728
                    and isinstance(container_cleanup, dict)
                    and container_cleanup.get("status")
                    == "absent_after_operator_cleanup"
                )
            elif policy == PREPROCESS_INFRA_POLICY:
                qualified = (
                    common
                    and item.get("agent_started") is False
                    and item.get("model_proxy_started") is False
                    and item.get("gateway_started") is False
                    and item.get("tools_list_started") is False
                    and item.get("evaluator_started") is False
                    and item.get("formal_run_artifacts_complete") is False
                    and item.get("partial_artifacts_modified") is False
                    and item.get("replacement_eligible") is True
                    and item.get("replacement_maximum") == 1
                    and item.get("projected_run_validity") == "infra_invalid"
                    and item.get("projected_verify_status") == "unavailable"
                    and item.get("projected_primary_failure_category")
                    == "environment_error"
                )
            elif policy == INTERRUPTION_POLICY:
                classification = item.get("classification")
                interruption_common = (
                    common
                    and item.get("system_id") == "hermes"
                    and item.get("attempt_ordinal") == 1
                    and item.get("replacement_for_run_id") is None
                    and item.get("evaluator_started") is False
                    and item.get("formal_run_artifacts_complete") is False
                    and item.get("partial_artifacts_modified") is False
                    and item.get("replacement_eligible") is True
                    and item.get("replacement_maximum") == 1
                    and item.get("projected_run_validity") == "infra_invalid"
                    and item.get("projected_verify_status") == "unavailable"
                    and item.get("projected_primary_failure_category")
                    == "environment_error"
                )
                tools_list_qualified = (
                    classification
                    == "user_keyboard_interrupt_after_tools_list_start_before_agent"
                    and item.get("gateway_started") is True
                    and item.get("tools_list_started") is True
                    and item.get("agent_started") is False
                )
                container_cleanup = item.get("container_cleanup")
                preprocess_qualified = (
                    classification == INTERRUPTED_PREPROCESS_CLASSIFICATION
                    and item.get("run_id") == INTERRUPTED_PREPROCESS_RUN_ID
                    and item.get("task_id") == INTERRUPTED_PREPROCESS_TASK_ID
                    and item.get("preprocess_started") is True
                    and item.get("preprocess_completed") is False
                    and item.get("preprocess_completion_source")
                    == "lifecycle_preprocess_end_missing"
                    and item.get("preprocess_task_state_status") == "done"
                    and isinstance(
                        item.get("preprocess_task_state_sha256"), str
                    )
                    and item.get("cleanup_started") is True
                    and item.get("cleanup_completed") is False
                    and item.get("model_proxy_started") is False
                    and item.get("gateway_started") is False
                    and item.get("tools_list_started") is False
                    and item.get("agent_started") is False
                    and item.get("state_restoration")
                    == "replacement_attempt_preprocess_required"
                    and isinstance(container_cleanup, dict)
                    and container_cleanup.get("status")
                    == "absent_after_operator_cleanup"
                    and isinstance(container_cleanup.get("container_id"), str)
                )
                qualified = interruption_common and (
                    tools_list_qualified or preprocess_qualified
                )
            elif policy == EVALUATOR_POLICY:
                qualified = (
                    base_common
                    and item.get("evaluator_replay") is True
                    and item.get("evaluator_replay_count") == 1
                    and item.get("original_evaluator_preserved") is True
                    and item.get("raw_agent_evidence_modified") is False
                    and item.get("formal_run_artifacts_modified") is True
                    and item.get("product_terminal_preserved")
                    == "max_model_requests"
                    and item.get("verify_status") in {"pass", "no_pass"}
                    and item.get("all_forwarded_requests_have_unique_terminal_events")
                    is True
                )
            elif policy == ASTRA_DEADLINE_POLICY:
                formal = item.get("formal_result_preserved", {})
                qualified = (
                    common
                    and item.get("replacement_authorized") is False
                    and item.get("open_request_count") == 1
                    and item.get("all_native_transports_have_unique_terminal_events")
                    is True
                    and formal.get("terminal_status") == "timeout"
                    and formal.get("termination_reason") == "agent_deadline"
                    and formal.get("run_validity") == "valid"
                    and formal.get("verify_status") == "unavailable"
                    and formal.get("primary_failure_category") == "agent_deadline"
                )
            elif policy == HERMES_OPEN_REQUEST_POLICY:
                qualified = (
                    common
                    and item.get("replacement_eligible") is True
                    and item.get("open_request_count") == 1
                    and item.get("drain_boundary") in {
                        "post_settled_shutdown_race",
                        "drain_timeout_open_request",
                    }
                    and item.get("projected_run_validity") == "infra_invalid"
                    and item.get("projected_verify_status") == "unavailable"
                    and item.get("projected_primary_failure_category")
                    == "environment_error"
                )
            else:
                qualified = (
                    common
                    and item.get("all_forwarded_requests_have_unique_terminal_events")
                    is True
                    and item.get("snapshot_closing_terminal_count", 0) >= 1
                )
            if not qualified:
                raise ContractError("M3 outer amendment incident is unqualified")
        return recovery_path, matched, reason
    raise ContractError("M3 outer amendment has no matching recovery incident")


def qualify_m3_outer_provenance_amendment(
    output_root: Path,
    *,
    helper_path: Path,
    launcher_path: Path,
) -> Path | None:
    output_root = output_root.resolve()
    provenance_path = output_root / "scheduler-hotfix-provenance.json"
    if not provenance_path.is_file():
        return None
    provenance = read_json_object(provenance_path)
    baseline = provenance.get("outer_lifecycle_hotfix")
    if not isinstance(baseline, dict):
        raise ContractError("existing M3 outer lifecycle provenance is missing")
    previous = provenance.get("outer_lifecycle_hotfix_active", baseline)
    if not isinstance(previous, dict):
        raise ContractError("active M3 outer lifecycle provenance is invalid")
    active = _m3_outer_provenance_record(
        helper_path=helper_path, launcher_path=launcher_path
    )
    if previous == active:
        return None
    _validate_m3_outer_change(previous, active)

    references = _m3_outer_amendment_references(provenance)
    expected_previous = baseline
    for reference in references:
        _path, amendment = _verify_m3_outer_amendment_reference(
            reference, output_root
        )
        if amendment.get("previous_outer_lifecycle_hotfix") != expected_previous:
            raise ContractError("M3 outer lifecycle amendment chain is broken")
        expected_previous = amendment.get("active_outer_lifecycle_hotfix")
    if expected_previous != previous:
        raise ContractError("M3 outer lifecycle active provenance is not in history")

    # A prepared amendment is written before the scheduler updates provenance.
    # Re-entering after that preparation must reuse the same transition instead
    # of allocating another amendment number.  Older, unreferenced transitions
    # to a different helper hash remain immutable evidence and are ignored.
    for candidate in sorted(
        output_root.glob("outer-lifecycle-hotfix-amendment*.json")
    ):
        reference = {"path": str(candidate), "sha256": sha256_file(candidate)}
        candidate_path, amendment = _verify_m3_outer_amendment_reference(
            reference, output_root
        )
        if (
            amendment.get("previous_outer_lifecycle_hotfix") == previous
            and amendment.get("active_outer_lifecycle_hotfix") == active
        ):
            return candidate_path

    amendment_number = len(references) + 1
    while (
        amendment_number > 1
        and (
            output_root
            / f"outer-lifecycle-hotfix-amendment-{amendment_number}.json"
        ).exists()
    ):
        amendment_number += 1
    if amendment_number == 1:
        amendment_path = output_root / M3_OUTER_AMENDMENT_NAME
        amendment_hash_path = output_root / M3_OUTER_AMENDMENT_HASH_NAME
    else:
        amendment_path = output_root / (
            f"outer-lifecycle-hotfix-amendment-{amendment_number}.json"
        )
        amendment_hash_path = amendment_path.with_suffix(".sha256")
    if amendment_path.is_file() or amendment_hash_path.is_file():
        if not amendment_path.is_file() or not amendment_hash_path.is_file():
            raise ContractError("M3 outer lifecycle amendment is incomplete")
        existing_amendment = read_json_object(amendment_path)
        expected_manifest = f"{sha256_file(amendment_path)}  {amendment_path.name}\n"
        if (
            existing_amendment.get("policy") != M3_OUTER_AMENDMENT_POLICY
            or existing_amendment.get("previous_outer_lifecycle_hotfix") != previous
            or existing_amendment.get("active_outer_lifecycle_hotfix") != active
            or amendment_hash_path.read_text(encoding="utf-8") != expected_manifest
        ):
            raise ContractError("existing M3 outer lifecycle amendment differs")
        return amendment_path

    checkpoint_path = output_root / "checkpoint.json"
    if (output_root / "scheduler-hotfix.sha256").exists():
        raise ContractError("cannot amend a completed M3 scheduler hotfix")
    if not checkpoint_path.is_file():
        raise ContractError("M3 outer amendment has no blocked checkpoint")
    checkpoint = read_json_object(checkpoint_path)
    if checkpoint.get("status") != "blocked":
        raise ContractError("M3 outer amendment checkpoint is not blocked")
    recovery_path, qualified_incidents, reason = _qualified_m3_amendment_trigger(
        output_root, checkpoint
    )

    amendment = {
        "schema_version": "toolathlon.m3-outer-lifecycle-hotfix-amendment.v1",
        "policy": M3_OUTER_AMENDMENT_POLICY,
        "created_at": utc_now(),
        "amendment_number": amendment_number,
        "reason": reason,
        "previous_outer_lifecycle_hotfix": previous,
        "active_outer_lifecycle_hotfix": active,
        "trigger_recovery": str(recovery_path),
        "trigger_recovery_sha256": sha256_file(recovery_path),
        "trigger_incidents": qualified_incidents,
        "blocked_checkpoint_sha256": sha256_file(checkpoint_path),
        "trigger_run_ids": [str(item["run_id"]) for item in qualified_incidents],
        "formal_attempt_rerun": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
        "raw_append_only_evidence_modified": False,
        "derived_finalization_completed": all(
            item.get("validation", {}).get("status") == "passed"
            for item in qualified_incidents
        ),
        "m2_evidence_modified": False,
        "hermes_normalizer_modified": False,
        "hermes_artifact_gate_modified": False,
    }
    write_json_atomic(amendment_path, amendment, mode=0o644)
    expected_manifest = (
        f"{sha256_file(amendment_path)}  {amendment_path.name}\n"
    )
    amendment_hash_path.write_text(expected_manifest, encoding="utf-8")
    return amendment_path


def install_m3_outer_provenance(
    m3_scheduler_module: Any,
    *,
    helper_path: Path,
    launcher_path: Path,
) -> Callable[..., Path]:
    current = m3_scheduler_module._write_provenance
    if getattr(current, "_toolathlon_m3_outer_lifecycle_hotfix", False):
        return current
    original = current

    def write(*args: Any, **kwargs: Any) -> Path:
        path = original(*args, **kwargs)
        provenance = read_json_object(path)
        outer = _m3_outer_provenance_record(
            helper_path=helper_path, launcher_path=launcher_path
        )
        existing = provenance.get("outer_lifecycle_hotfix")
        active = provenance.get("outer_lifecycle_hotfix_active", existing)
        if existing is None:
            provenance["outer_lifecycle_hotfix"] = outer
            provenance["outer_lifecycle_hotfix_active"] = outer
            write_json_atomic(path, provenance, mode=0o644)
            return path
        if active == outer:
            return path

        output_root = Path(args[0] if args else kwargs["output_root"]).resolve()
        references = _m3_outer_amendment_references(provenance)
        matched: tuple[Path, dict[str, Any]] | None = None
        for candidate in sorted(output_root.glob("outer-lifecycle-hotfix-amendment*.json")):
            reference = {"path": str(candidate), "sha256": sha256_file(candidate)}
            path_candidate, amendment = _verify_m3_outer_amendment_reference(
                reference, output_root
            )
            if (
                amendment.get("previous_outer_lifecycle_hotfix") == active
                and amendment.get("active_outer_lifecycle_hotfix") == outer
            ):
                matched = (path_candidate, amendment)
                break
        if matched is None:
            raise ContractError("existing M3 outer lifecycle hotfix provenance differs")
        amendment_path, _amendment = matched
        reference = {
            "path": str(amendment_path),
            "sha256": sha256_file(amendment_path),
        }
        if reference not in references:
            references.append(reference)
        provenance["outer_lifecycle_hotfix_active"] = outer
        provenance["outer_lifecycle_hotfix_amendment"] = references[0]
        provenance["outer_lifecycle_hotfix_amendments"] = references
        write_json_atomic(path, provenance, mode=0o644)
        return path

    setattr(write, "_toolathlon_m3_outer_lifecycle_hotfix", True)
    m3_scheduler_module._write_provenance = write
    return original


def resume(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--m1-root", type=Path, required=True)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    helper_path = Path(__file__).resolve()
    from astra.runners.toolathlon_verified import m2_scheduler_hotfix as hotfix

    hotfix.FROZEN_M2_BATCH_SHA256 = _verify_frozen_m2(repo_root)
    _disable_irrelevant_historical_recovery(hotfix, output_root)
    install_artifact_gate_hotfix()
    install_model_usage_infra_hotfix()
    install_agent_model_boundary_hotfix()
    install_formal_result_hotfix()
    incidents = recover_pending_attempts(output_root, helper_path)
    count_scope_incidents = recover_pending_count_scope_attempts(
        output_root, helper_path
    )
    product_failure_incidents = recover_pending_product_failure_attempts(
        output_root, helper_path
    )
    astra_deadline_incidents = recover_pending_astra_agent_deadline_attempts(
        output_root, helper_path
    )
    hermes_drain_incidents = recover_pending_hermes_drain_attempts(
        output_root, helper_path
    )
    hermes_open_request_incidents = recover_pending_hermes_open_request_attempts(
        output_root, helper_path
    )
    budget_evaluator_incidents = recover_pending_budget_terminal_evaluators(
        output_root, args.source_root, helper_path
    )
    interrupted_run_ids = install_interrupted_attempt_hotfix(
        output_root, helper_path
    )
    _install_lifecycle_runner(helper_path)
    if incidents:
        print(
            json.dumps(
                {
                    "check": "astra_budget_terminal_recovery",
                    "status": "GO",
                    "incident_count": len(incidents),
                    "formal_attempt_rerun": False,
                    "hermes_behavior_modified": False,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    if count_scope_incidents:
        print(
            json.dumps(
                {
                    "check": "astra_tool_count_observability_recovery",
                    "status": "GO",
                    "incident_count": len(count_scope_incidents),
                    "formal_attempt_rerun": False,
                    "hermes_behavior_modified": False,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    if astra_deadline_incidents:
        print(
            json.dumps(
                {
                    "check": "astra_agent_deadline_observability",
                    "status": "GO",
                    "incident_count": len(astra_deadline_incidents),
                    "formal_attempt_rerun": False,
                    "replacement_authorized": False,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    if hermes_drain_incidents:
        print(
            json.dumps(
                {
                    "check": "hermes_post_shutdown_model_drain_reconciliation",
                    "status": "GO",
                    "incident_count": len(hermes_drain_incidents),
                    "formal_attempt_rerun": False,
                    "hermes_normalizer_modified": False,
                    "hermes_artifact_gate_modified": False,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    if hermes_open_request_incidents:
        print(
            json.dumps(
                {
                    "check": "hermes_open_model_request_infra_projection",
                    "status": "GO",
                    "incident_count": len(hermes_open_request_incidents),
                    "formal_attempt_rerun": False,
                    "replacement_maximum": 1,
                    "hermes_normalizer_modified": False,
                    "hermes_artifact_gate_modified": False,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    if budget_evaluator_incidents:
        print(
            json.dumps(
                {
                    "check": "budget_terminal_task_specific_evaluator",
                    "status": "GO",
                    "incident_count": len(budget_evaluator_incidents),
                    "formal_attempt_rerun": False,
                    "agent_rerun": False,
                    "evaluator_replay_per_incident": 1,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    if interrupted_run_ids:
        print(
            json.dumps(
                {
                    "check": "interrupted_attempt_a2_replacement",
                    "status": "GO",
                    "interrupted_a1_run_ids": interrupted_run_ids,
                    "a1_rerun": False,
                    "next_attempt_ordinal": 2,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return hotfix.main(
        [
            "--repo-root",
            str(repo_root),
            "--source-root",
            str(args.source_root.resolve()),
            "--output-root",
            str(output_root),
            "--m1-root",
            str(args.m1_root.resolve()),
        ]
    )


def m3_resume(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--m2-root", type=Path, required=True)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    m2_root = args.m2_root.resolve()
    if (
        output_root == m2_root
        or output_root in m2_root.parents
        or m2_root in output_root.parents
    ):
        raise ContractError("M3 output root and M2 qualification root must be disjoint")

    helper_path = Path(__file__).resolve()
    launcher_path = (
        repo_root
        / "astra/benchmark/toolathlon-verified/scripts/"
        "run_m3_remaining_batch_schema_hotfix.sh"
    )
    install_artifact_gate_hotfix()
    install_model_usage_infra_hotfix()
    install_agent_model_boundary_hotfix()
    install_formal_result_hotfix()

    # M3 must validate the qualified M2 interrupted-attempt projection without
    # rewriting any M2 evidence.  M3-local projections, if explicitly prepared
    # after a user interruption, retain the existing create-or-verify behavior.
    prior_interrupted_run_ids = install_interrupted_attempt_hotfix(
        m2_root,
        helper_path,
        require_existing_projection=True,
    )
    current_interrupted_run_ids = install_interrupted_attempt_hotfix(
        output_root,
        helper_path,
    )
    task_tracker_setup_path = qualify_task_tracker_container_setup_recovery(
        output_root,
        helper_path,
    )
    install_task_tracker_container_setup_projection(
        output_root,
        task_tracker_setup_path,
    )
    preprocess_infrastructure_run_ids = install_preprocess_infrastructure_hotfix(
        output_root,
        helper_path,
    )
    dataset_repair_path = qualify_dataset_preprocess_repair(
        output_root,
        source_root,
        helper_path,
    )
    dataset_repair_harness_path = qualify_dataset_repair_harness_boundary(
        output_root,
        dataset_repair_path,
        helper_path,
    )
    install_dataset_repair_harness_projection(
        output_root,
        dataset_repair_harness_path,
    )

    incidents = recover_pending_attempts(output_root, helper_path)
    count_scope_incidents = recover_pending_count_scope_attempts(
        output_root, helper_path
    )
    product_failure_incidents = recover_pending_product_failure_attempts(
        output_root, helper_path
    )
    astra_deadline_incidents = recover_pending_astra_agent_deadline_attempts(
        output_root, helper_path
    )
    hermes_drain_incidents = recover_pending_hermes_drain_attempts(
        output_root, helper_path
    )
    hermes_open_request_incidents = recover_pending_hermes_open_request_attempts(
        output_root, helper_path
    )
    budget_evaluator_incidents = recover_pending_budget_terminal_evaluators(
        output_root, source_root, helper_path
    )
    gate_v2_projection_path = install_artifact_gate_v2(
        output_root, helper_path
    )
    provenance_amendment = qualify_m3_outer_provenance_amendment(
        output_root,
        helper_path=helper_path,
        launcher_path=launcher_path,
    )
    install_dataset_repair_scheduler_hotfix(
        output_root,
        dataset_repair_path,
        dataset_repair_harness_path,
    )
    install_task_tracker_container_setup_scheduler_hotfix(
        output_root,
        task_tracker_setup_path,
    )

    # m3_batch imports selected M2 helpers by value.  Import it only after the
    # M2 interrupted-attempt projection is installed, then bind the identity
    # helper explicitly so M2/M3 uniqueness validation observes the projection.
    from astra.runners.toolathlon_verified import m2_scheduler_hotfix

    frozen_m2_sha256 = _verify_frozen_m2(repo_root)
    m2_scheduler_hotfix.FROZEN_M2_BATCH_SHA256 = frozen_m2_sha256
    from astra.runners.toolathlon_verified import m3_batch, m3_scheduler_hotfix

    m3_batch._identity_key = m2_batch._identity_key
    m3_batch.load_slot_candidates = m2_batch.load_slot_candidates
    m3_batch.decide_slot = m2_batch.decide_slot
    m3_batch.validate_formal_effective = m2_batch.validate_formal_effective
    m3_batch.validate_pair = m2_batch.validate_pair
    install_m3_dataset_repair_validation(
        m3_batch,
        dataset_repair_path,
        dataset_repair_harness_path,
        task_tracker_setup_path,
    )
    m3_scheduler_hotfix.FROZEN_M2_BATCH_SHA256 = frozen_m2_sha256
    install_m3_outer_provenance(
        m3_scheduler_hotfix,
        helper_path=helper_path,
        launcher_path=launcher_path,
    )
    _install_lifecycle_runner(helper_path)

    print(
        json.dumps(
            {
                "check": "m3_outer_lifecycle_hotfix",
                "status": "GO",
                "workers": 1,
                "formal_attempt_rerun": False,
                "m2_evidence_modified": False,
                "prior_interrupted_run_ids": prior_interrupted_run_ids,
                "current_interrupted_run_ids": current_interrupted_run_ids,
                "task_tracker_container_setup_recovery": str(
                    task_tracker_setup_path
                ),
                "task_tracker_container_setup_recovery_sha256": sha256_file(
                    task_tracker_setup_path
                ),
                "task_tracker_container_setup_recovery_run_id": (
                    read_json_object(task_tracker_setup_path)["incidents"][0][
                        "authorized_recovery_run_id"
                    ]
                ),
                "task_tracker_container_setup_no_a4_allowed": True,
                "preprocess_infrastructure_incident_count": len(
                    preprocess_infrastructure_run_ids
                ),
                "preprocess_infrastructure_run_ids": (
                    preprocess_infrastructure_run_ids
                ),
                "dataset_preprocess_repair": str(dataset_repair_path),
                "dataset_preprocess_repair_sha256": sha256_file(
                    dataset_repair_path
                ),
                "dataset_repair_run_id": read_json_object(dataset_repair_path)[
                    "incidents"
                ][0]["repair_run_id"],
                "dataset_repair_harness_recovery": str(
                    dataset_repair_harness_path
                ),
                "dataset_repair_harness_recovery_sha256": sha256_file(
                    dataset_repair_harness_path
                ),
                "dataset_repair_harness_replacement_run_id": read_json_object(
                    dataset_repair_harness_path
                )["incidents"][0]["authorized_replacement_run_id"],
                "no_a5_allowed": True,
                "astra_budget_terminal_incident_count": len(incidents),
                "astra_tool_count_incident_count": len(count_scope_incidents),
                "product_failure_effective_incident_count": len(
                    product_failure_incidents
                ),
                "astra_agent_deadline_incident_count": len(
                    astra_deadline_incidents
                ),
                "hermes_model_drain_incident_count": len(
                    hermes_drain_incidents
                ),
                "hermes_open_request_incident_count": len(
                    hermes_open_request_incidents
                ),
                "budget_evaluator_incident_count": len(
                    budget_evaluator_incidents
                ),
                "artifact_gate_v2_projection": str(
                    gate_v2_projection_path
                ),
                "artifact_gate_v2_projection_sha256": sha256_file(
                    gate_v2_projection_path
                ),
                "artifact_gate_v2_policy": GATE_V2_POLICY,
                "outer_lifecycle_hotfix_sha256": sha256_file(helper_path),
                "outer_lifecycle_hotfix_amendment": (
                    str(provenance_amendment)
                    if provenance_amendment is not None
                    else None
                ),
                "hermes_normalizer_modified": False,
                "hermes_artifact_gate_modified": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return m3_scheduler_hotfix.main(
        [
            "--repo-root",
            str(repo_root),
            "--source-root",
            str(source_root),
            "--output-root",
            str(output_root),
            "--m2-root",
            str(m2_root),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        raise SystemExit(
            "usage: m2_budget_terminal_hotfix.py "
            "lifecycle|recover|resume|m3-resume ..."
        )
    command = values.pop(0)
    if command == "lifecycle":
        install_artifact_gate_hotfix()
        install_model_usage_infra_hotfix()
        install_agent_model_boundary_hotfix()
        install_budget_evaluator_hotfix()
        from astra.runners.toolathlon_verified import lifecycle

        install_lifecycle_count_scope_hotfix(lifecycle)
        install_lifecycle_hermes_drain_reconciliation(lifecycle)
        install_lifecycle_hermes_open_request_projection(lifecycle)
        install_lifecycle_astra_deadline_observability(lifecycle)
        install_lifecycle_dataset_repair_overlay(lifecycle)
        return lifecycle.main(values)
    if command == "recover":
        parser = argparse.ArgumentParser()
        parser.add_argument("--output-root", type=Path, required=True)
        parser.add_argument(
            "--source-root",
            type=Path,
            default=Path("/home/vagrant/dataset/Toolathlon"),
        )
        args = parser.parse_args(values)
        install_artifact_gate_hotfix()
        install_model_usage_infra_hotfix()
        install_agent_model_boundary_hotfix()
        incidents = recover_pending_attempts(args.output_root, Path(__file__))
        count_scope_incidents = recover_pending_count_scope_attempts(
            args.output_root, Path(__file__)
        )
        astra_deadline_incidents = recover_pending_astra_agent_deadline_attempts(
            args.output_root, Path(__file__)
        )
        hermes_drain_incidents = recover_pending_hermes_drain_attempts(
            args.output_root, Path(__file__)
        )
        hermes_open_request_incidents = recover_pending_hermes_open_request_attempts(
            args.output_root, Path(__file__)
        )
        budget_evaluator_incidents = recover_pending_budget_terminal_evaluators(
            args.output_root, args.source_root, Path(__file__)
        )
        print(
            json.dumps(
                {
                    "status": "GO",
                    "budget_terminal_incidents": incidents,
                    "tool_count_scope_incidents": count_scope_incidents,
                    "astra_agent_deadline_incidents": astra_deadline_incidents,
                    "hermes_model_drain_incidents": hermes_drain_incidents,
                    "hermes_open_request_incidents": hermes_open_request_incidents,
                    "budget_evaluator_incidents": budget_evaluator_incidents,
                },
                sort_keys=True,
            )
        )
        return 0
    if command == "replay-evaluator":
        parser = argparse.ArgumentParser()
        parser.add_argument("--attempt", type=Path, required=True)
        parser.add_argument("--output-root", type=Path, required=True)
        parser.add_argument("--source-root", type=Path, required=True)
        args = parser.parse_args(values)
        install_artifact_gate_hotfix()
        install_model_usage_infra_hotfix()
        install_agent_model_boundary_hotfix()
        record = replay_budget_terminal_evaluator(
            args.attempt,
            output_root=args.output_root,
            source_root=args.source_root.resolve(),
            helper_path=Path(__file__),
        )
        print(json.dumps({"status": "GO", "recovery": record}, sort_keys=True))
        return 0
    if command == "resume":
        return resume(values)
    if command == "m3-resume":
        return m3_resume(values)
    raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
