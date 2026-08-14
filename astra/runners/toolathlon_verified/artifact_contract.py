from __future__ import annotations

import json
import hashlib
import os
import re
from pathlib import Path
from typing import Any, Iterable

from .contract import ContractError, canonical_json_sha256, sha256_file


ARTIFACT_SCHEMA_VERSION = "toolathlon.run-artifacts.v1"
OBSERVATION_RELIABILITIES = frozenset(
    {"reported", "observed", "derived", "missing"}
)
REQUIRED_ARTIFACTS = (
    "resolved-config.json",
    "tool-schema-observed.json",
    "lifecycle-events.jsonl",
    "adapter-events.jsonl",
    "trajectory.jsonl",
    "tool-calls.jsonl",
    "model-usage.jsonl",
    "resource-usage.jsonl",
    "evaluator/eval_res.json",
    "evaluator/eval.log",
    "failure-evidence.json",
    "run.json",
    "artifacts.sha256",
)
REQUIRED_LIFECYCLE_EVENTS = frozenset(
    {
        "reset.start",
        "reset.end",
        "container.start",
        "container.ready",
        "preprocess.start",
        "preprocess.end",
        "gateway.start",
        "gateway.ready",
        "tools_list.start",
        "tools_list.end",
        "adapter.start",
        "adapter.end",
        "evaluator.start",
        "evaluator.end",
        "cleanup.start",
        "cleanup.end",
        "artifact_validation.start",
        "artifact_validation.end",
    }
)
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
)
_SHA_LINE = re.compile(r"^([0-9a-f]{64})  ([^\0\r\n]+)$")
PRIVATE_IDENTITY_FILENAME = "product-identity.private.json"
ASTRA_RUNTIME_MCP_BINDING_FILENAME = "astra-runtime-mcp-binding.json"


def observation(
    value: Any,
    *,
    source: str,
    reliability: str,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    if reliability not in OBSERVATION_RELIABILITIES:
        raise ContractError(f"invalid observation reliability: {reliability}")
    if not isinstance(source, str) or not source:
        raise ContractError("observation source must be non-empty")
    if value is None:
        if reliability != "missing" or not missing_reason:
            raise ContractError("null observation requires reliability=missing and a reason")
    elif reliability == "missing" or missing_reason is not None:
        raise ContractError("non-null observation cannot be marked missing")
    return {
        "value": value,
        "source": source,
        "reliability": reliability,
        "missing_reason": missing_reason,
    }


def missing_observation(source: str, reason: str) -> dict[str, Any]:
    return observation(
        None,
        source=source,
        reliability="missing",
        missing_reason=reason,
    )


def reported_observation(value: Any, source: str) -> dict[str, Any]:
    return observation(value, source=source, reliability="reported")


def observed_observation(value: Any, source: str) -> dict[str, Any]:
    return observation(value, source=source, reliability="observed")


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def validate_observation(value: Any, label: str) -> dict[str, Any]:
    item = _require_object(value, label)
    if set(item) != {"value", "source", "reliability", "missing_reason"}:
        raise ContractError(f"{label} has an invalid observation shape")
    source = item["source"]
    reliability = item["reliability"]
    missing_reason = item["missing_reason"]
    if not isinstance(source, str) or not source:
        raise ContractError(f"{label}.source must be non-empty")
    if reliability not in OBSERVATION_RELIABILITIES:
        raise ContractError(f"{label}.reliability is invalid")
    if item["value"] is None:
        if reliability != "missing" or not isinstance(missing_reason, str) or not missing_reason:
            raise ContractError(f"{label} null value has no structured missing reason")
    elif reliability == "missing" or missing_reason is not None:
        raise ContractError(f"{label} non-null value has invalid missing metadata")
    return item


def read_jsonl(path: Path, *, allow_empty: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"cannot read JSONL {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise ContractError(f"blank JSONL line in {path}:{line_number}")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid JSONL in {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ContractError(f"JSONL row is not an object in {path}:{line_number}")
        rows.append(value)
    if not rows and not allow_empty:
        raise ContractError(f"required evidence stream is empty: {path}")
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON object {path}: {exc}") from exc
    return _require_object(value, str(path))


def _validate_identity(rows: Iterable[dict[str, Any]], run: dict[str, Any], label: str) -> None:
    for index, row in enumerate(rows, start=1):
        if row.get("run_id") != run["run_id"]:
            raise ContractError(f"{label}[{index}] run_id mismatch")
        if row.get("system_id") != run["system_id"]:
            raise ContractError(f"{label}[{index}] system_id mismatch")
        if not isinstance(row.get("timestamp"), str) or not row["timestamp"]:
            raise ContractError(f"{label}[{index}] has no wall-clock timestamp")
        if not isinstance(row.get("monotonic_ns"), int) or row["monotonic_ns"] < 0:
            raise ContractError(f"{label}[{index}] has no monotonic timestamp")


def _validate_lifecycle(
    rows: list[dict[str, Any]], run: dict[str, Any], *, require_validation_end: bool
) -> None:
    _validate_identity(rows, run, "lifecycle-events")
    events = {row.get("event") for row in rows}
    required = REQUIRED_LIFECYCLE_EVENTS
    if not require_validation_end:
        required = required - {"artifact_validation.end"}
    missing = sorted(required - events)
    if missing:
        raise ContractError(f"lifecycle evidence is incomplete: {missing}")
    sequences = [row.get("sequence") for row in rows]
    if sequences != list(range(1, len(rows) + 1)):
        raise ContractError("lifecycle event sequence is not contiguous")


def _validate_model_usage(rows: list[dict[str, Any]], run: dict[str, Any]) -> None:
    _validate_identity(rows, run, "model-usage")
    started: dict[str, dict[str, Any]] = {}
    completed: set[str] = set()
    attempts: list[int] = []
    for index, row in enumerate(rows, start=1):
        event = row.get("event")
        if event not in {
            "model_request.started",
            "model_request.completed",
            "model_request.rejected_limit",
            "proxy.ready",
            "proxy.stopped",
        }:
            raise ContractError(f"model-usage[{index}] has unknown event: {event}")
        if event in {"proxy.ready", "proxy.stopped"}:
            continue
        attempt = row.get("product_attempt")
        if not isinstance(attempt, int) or attempt < 1:
            raise ContractError(f"model-usage[{index}] has invalid product_attempt")
        attempts.append(attempt)
        validate_observation(row.get("retry_of"), f"model-usage[{index}].retry_of")
        if event == "model_request.started":
            required_generation = {
                "thinking": "enabled",
                "thinking_wire_behavior": "sent",
                "reasoning_effort": "max",
                "reasoning_effort_wire_behavior": "sent",
                "generation_parameter_source": "benchmark_override",
            }
            for field, expected in required_generation.items():
                if row.get(field) != expected:
                    raise ContractError(
                        f"model-usage[{index}] generation field mismatch: {field}"
                    )
            request_id = row.get("model_request_id")
            if not isinstance(request_id, str) or not request_id or request_id in started:
                raise ContractError(f"model-usage[{index}] has invalid model_request_id")
            started[request_id] = row
            continue
        usage = _require_object(row.get("token_usage"), f"model-usage[{index}].token_usage")
        for field in TOKEN_FIELDS:
            validate_observation(usage.get(field), f"model-usage[{index}].token_usage.{field}")
        validate_observation(row.get("finish_reason"), f"model-usage[{index}].finish_reason")
        if event == "model_request.completed":
            request_id = row.get("model_request_id")
            if request_id not in started or request_id in completed:
                raise ContractError(f"model-usage[{index}] has no unique matching start")
            completed.add(str(request_id))
    if set(started) != completed:
        raise ContractError("one or more forwarded model requests have no terminal event")
    if attempts and min(attempts) != 1:
        raise ContractError("model product_attempt sequence does not start at 1")


def _validate_agent_model_boundary(
    adapter_rows: list[dict[str, Any]],
    model_rows: list[dict[str, Any]],
    run: dict[str, Any],
) -> None:
    if run.get("run_validity") != "valid":
        return
    starts = [
        row for row in adapter_rows if row.get("event") == "agent.execution_start"
    ]
    if len(starts) != 1:
        raise ContractError("valid run must have exactly one Agent execution start")
    agent_start = starts[0]["monotonic_ns"]
    for index, row in enumerate(model_rows, start=1):
        if (
            row.get("event") == "model_request.started"
            and row.get("monotonic_ns", -1) < agent_start
        ):
            raise ContractError(
                f"model-usage[{index}] was forwarded before Agent execution"
            )
    adapter_metadata = _require_object(run.get("adapter"), "run.adapter")
    if adapter_metadata.get("setup_provider_requests_before_agent") != 0:
        raise ContractError("valid run has nonzero or missing setup model requests")
    drain = _require_object(
        adapter_metadata.get("post_terminal_model_drain"),
        "run.adapter.post_terminal_model_drain",
    )
    if drain.get("settled") is not True:
        raise ContractError("valid run has an unsettled post-terminal model drain")
    forwarded = drain.get("provider_requests_forwarded")
    completed = drain.get("provider_requests_completed")
    if (
        not isinstance(forwarded, int)
        or not isinstance(completed, int)
        or forwarded != completed
    ):
        raise ContractError("post-terminal model drain request counts differ")


def _validate_tool_calls(rows: list[dict[str, Any]], run: dict[str, Any]) -> None:
    _validate_identity(rows, run, "tool-calls")
    states_by_call: dict[str, set[str]] = {}
    for index, row in enumerate(rows, start=1):
        for field in (
            "tool_call_id",
            "model_visible_tool_name",
            "gateway_tool_name",
            "canonical_tool_name",
            "state",
        ):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ContractError(f"tool-calls[{index}] has no {field}")
        for field in (
            "native_tool_call_id",
            "arguments_sha256",
            "error_type",
            "raw_error_code",
            "evidence_path",
        ):
            validate_observation(row.get(field), f"tool-calls[{index}].{field}")
        state = row["state"]
        if state not in {"started", "succeeded", "failed"}:
            raise ContractError(f"tool-calls[{index}] has invalid state: {state}")
        states = states_by_call.setdefault(row["tool_call_id"], set())
        if state in states:
            raise ContractError(
                f"tool-calls[{index}] duplicates state {state} for one tool call"
            )
        if state in {"succeeded", "failed"} and states & {"succeeded", "failed"}:
            raise ContractError(
                f"tool-calls[{index}] has multiple terminal states for one tool call"
            )
        states.add(state)


def _validate_tool_event_completeness(
    trajectory_rows: list[dict[str, Any]],
    tool_rows: list[dict[str, Any]],
    run: dict[str, Any],
) -> None:
    state_counts = {
        "started": sum(row.get("state") == "started" for row in tool_rows),
        "terminal": sum(
            row.get("state") in {"succeeded", "failed"} for row in tool_rows
        ),
        "failed": sum(row.get("state") == "failed" for row in tool_rows),
    }
    summary = run.get("trajectory")
    if summary is not None:
        summary = _require_object(summary, "run.trajectory")
        expected_counts = {
            "tool_started_events": state_counts["started"],
            "tool_terminal_events": state_counts["terminal"],
            "tool_failed_events": state_counts["failed"],
        }
        for field, observed_count in expected_counts.items():
            if summary.get(field) != observed_count:
                raise ContractError(
                    f"run trajectory summary differs from normalized tool evidence: {field}"
                )

    terminal_by_call: dict[str, int] = {}
    started_calls: set[str] = set()
    for row in tool_rows:
        call_id = row["tool_call_id"]
        if row["state"] == "started":
            started_calls.add(call_id)
        elif row["state"] in {"succeeded", "failed"}:
            terminal_by_call[call_id] = terminal_by_call.get(call_id, 0) + 1
    if run.get("terminal_status") == "completed":
        open_calls = sorted(call_id for call_id in started_calls if not terminal_by_call.get(call_id))
        if open_calls:
            raise ContractError(
                f"completed run has normalized tool starts without terminal evidence: {open_calls}"
            )

    if run.get("system_id") != "astra":
        return

    transport_starts: dict[str, dict[str, Any]] = {}
    transport_terminals: dict[str, dict[str, Any]] = {}
    declared_counts: set[int] = set()
    for index, row in enumerate(trajectory_rows, start=1):
        native = row.get("native")
        if not isinstance(native, dict):
            continue
        native_type = str(native.get("type", "")).lower()
        if native_type == "usage" and isinstance(native.get("tool_call_count"), int):
            declared_counts.add(native["tool_call_count"])
            continue
        if native_type not in {
            "tool_transport_started",
            "tool_transport_completed",
            "tool_transport_failed",
        }:
            continue
        call_id = native.get("call_id")
        tool_name = native.get("tool")
        if not isinstance(call_id, str) or not call_id:
            raise ContractError(f"trajectory[{index}] transport event has no call_id")
        if not isinstance(tool_name, str) or not tool_name:
            raise ContractError(f"trajectory[{index}] transport event has no tool name")
        target = (
            transport_starts
            if native_type == "tool_transport_started"
            else transport_terminals
        )
        if call_id in target:
            raise ContractError(
                f"trajectory[{index}] duplicates {native_type} for {call_id}"
            )
        if native_type in {
            "tool_transport_completed",
            "tool_transport_failed",
        } and not isinstance(native.get("success"), bool):
            raise ContractError(
                f"trajectory[{index}] transport terminal has no boolean success"
            )
        if (
            native_type == "tool_transport_failed"
            and native.get("success") is not False
        ):
            raise ContractError(
                f"trajectory[{index}] failed transport is not marked success=false"
            )
        target[call_id] = native

    if run.get("terminal_status") == "completed" and set(transport_starts) != set(
        transport_terminals
    ):
        raise ContractError(
            "completed Astra run has unpaired native tool transport evidence"
        )
    if not set(transport_terminals).issubset(transport_starts):
        raise ContractError("Astra tool transport terminal has no matching start")

    normalized_by_native: dict[str, list[dict[str, Any]]] = {}
    for row in tool_rows:
        native_id = validate_observation(
            row.get("native_tool_call_id"), "tool-calls.native_tool_call_id"
        )["value"]
        if isinstance(native_id, str):
            normalized_by_native.setdefault(native_id, []).append(row)

    for call_id, native_start in transport_starts.items():
        normalized = normalized_by_native.get(call_id, [])
        starts = [
            row
            for row in normalized
            if row.get("event") == "tool_transport_started"
            and row.get("state") == "started"
        ]
        if len(starts) != 1:
            raise ContractError(
                f"native tool transport start has no unique normalized start: {call_id}"
            )
        if starts[0]["model_visible_tool_name"] != native_start["tool"]:
            raise ContractError(f"normalized transport tool name mismatch: {call_id}")
        if "arguments" in native_start:
            expected_arguments_sha256 = canonical_json_sha256(native_start["arguments"])
            if starts[0]["arguments_sha256"].get("value") != expected_arguments_sha256:
                raise ContractError(
                    f"normalized transport start lost argument evidence: {call_id}"
                )

        native_terminal = transport_terminals.get(call_id)
        if native_terminal is None:
            continue
        native_terminal_type = str(native_terminal["type"]).lower()
        expected_state = "succeeded" if native_terminal["success"] else "failed"
        terminals = [
            row
            for row in normalized
            if row.get("event") == native_terminal_type
            and row.get("state") == expected_state
        ]
        if len(terminals) != 1:
            raise ContractError(
                f"native tool transport terminal has no unique normalized terminal: {call_id}"
            )
        if terminals[0]["model_visible_tool_name"] != native_terminal["tool"]:
            raise ContractError(f"normalized transport terminal tool name mismatch: {call_id}")
        if "arguments" in native_start and terminals[0]["arguments_sha256"].get(
            "value"
        ) != canonical_json_sha256(native_start["arguments"]):
            raise ContractError(
                f"normalized transport terminal lost paired argument evidence: {call_id}"
            )

    if transport_starts:
        if len(declared_counts) != 1:
            raise ContractError(
                "Astra native tool transport count has no unique server declaration"
            )
        if next(iter(declared_counts)) != len(transport_terminals):
            raise ContractError(
                "Astra server-declared tool count differs from terminal transports"
            )


def _validate_task_tool_exposure(
    root: Path,
    run: dict[str, Any],
    resolved: dict[str, Any],
    model_rows: list[dict[str, Any]],
) -> None:
    observed = _read_json(root / "tool-schema-observed.json")
    if observed.get("schema_version") != 1:
        raise ContractError("runtime tools/list manifest schema mismatch")
    if observed.get("task_id") != run["task_id"]:
        raise ContractError("runtime tools/list manifest task_id mismatch")
    if observed.get("run_qualification") != "go" or observed.get("collisions") != []:
        raise ContractError("runtime tools/list manifest is not qualified")
    rows = observed.get("tools")
    if not isinstance(rows, list) or observed.get("tool_count") != len(rows):
        raise ContractError("runtime tools/list rows do not match tool_count")
    raw_tools: list[dict[str, Any]] = []
    system_name_field = f"{run['system_id']}_model_visible_tool_name"
    names: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not isinstance(row.get("raw"), dict):
            raise ContractError(f"runtime tools/list row {index} is incomplete")
        raw_tools.append(row["raw"])
        name = row.get(system_name_field)
        if not isinstance(name, str) or not name.startswith("mcp__toolathlon__"):
            raise ContractError(
                f"runtime tools/list row {index} has no valid product MCP name"
            )
        names.append(name)
    names.sort()
    if len(names) != len(set(names)):
        raise ContractError("runtime product-visible MCP tool names are not unique")
    if observed.get("tool_set_sha256") != canonical_json_sha256(raw_tools):
        raise ContractError("runtime tools/list content hash mismatch")

    adapter = _require_object(resolved.get("adapter"), "resolved-config.adapter")
    exposure = _require_object(
        adapter.get("tool_exposure"), "resolved-config.adapter.tool_exposure"
    )
    required = {
        "scope": "current_task_attempt_only",
        "mcp_tool_count": len(names),
        "mcp_tool_names_sha256": canonical_json_sha256(names),
        "all_observed_task_mcp_tools_required": True,
        "other_task_mcp_tools_allowed": False,
        "product_builtin_tools_retained": True,
        "provider_request_tool_names_recorded": True,
    }
    for field, expected in required.items():
        if exposure.get(field) != expected:
            raise ContractError(f"task tool exposure field mismatch: {field}")
    if adapter.get("tool_set_sha256") != observed.get("tool_set_sha256"):
        raise ContractError("resolved task tool set hash mismatch")
    gateway = _require_object(observed.get("gateway"), "tool-schema-observed.gateway")
    if exposure.get("gateway_url") != gateway.get("url"):
        raise ContractError("task tool exposure Gateway mismatch")

    binding_path = root / ASTRA_RUNTIME_MCP_BINDING_FILENAME
    if run["system_id"] == "astra":
        if exposure.get("mechanism") != "astra_native_request_scoped_runtime_mcp":
            raise ContractError("Astra task tool exposure mechanism mismatch")
        if not binding_path.is_file() or binding_path.is_symlink():
            raise ContractError("Astra runtime MCP binding artifact is missing")
        binding = _read_json(binding_path)
        expected_binding = {
            "schema_version": "toolathlon.astra-runtime-mcp-binding.v1",
            "endpoint": "/chat/stream",
            "runtime_profile": "request_scoped_runtime_mcp",
            "binding": {
                "id": "toolathlon",
                "transport": "sse",
                "url": gateway.get("url"),
                "headers_present": False,
                "auth_token_present": False,
            },
            "interaction_mode": "auto",
            "expected_mcp_tool_names": names,
            "expected_mcp_tool_names_sha256": canonical_json_sha256(names),
        }
        if binding != expected_binding:
            raise ContractError("Astra runtime MCP binding differs from current tools/list")
        if exposure.get("binding_artifact") != ASTRA_RUNTIME_MCP_BINDING_FILENAME:
            raise ContractError("Astra runtime MCP binding artifact path mismatch")
        if exposure.get("binding_sha256") != sha256_file(binding_path):
            raise ContractError("Astra runtime MCP binding artifact hash mismatch")
        if exposure.get("astra_endpoint") != "/chat/stream":
            raise ContractError("Astra task tool endpoint mismatch")
        if exposure.get("runtime_profile") != "request_scoped_runtime_mcp":
            raise ContractError("Astra runtime MCP profile mismatch")
        if exposure.get("session_strategy") != "native_chat_stream_auto_create":
            raise ContractError("Astra session strategy mismatch")
    else:
        if exposure.get("mechanism") != "hermes_fresh_single_task_gateway":
            raise ContractError("Hermes task tool exposure mechanism mismatch")
        if binding_path.exists():
            raise ContractError("Hermes produced an Astra runtime MCP binding artifact")

    started_request_count = 0
    full_task_surface_observed = False
    for index, row in enumerate(model_rows, start=1):
        if row.get("event") != "model_request.started":
            continue
        started_request_count += 1
        request_names = row.get("request_tool_names")
        if not isinstance(request_names, list) or any(
            not isinstance(name, str) or not name for name in request_names
        ):
            raise ContractError(f"model-usage[{index}] has invalid request tool names")
        if request_names != sorted(set(request_names)):
            raise ContractError(f"model-usage[{index}] request tool names are not canonical")
        if row.get("request_tool_count") != len(request_names):
            raise ContractError(f"model-usage[{index}] request tool count mismatch")
        if row.get("request_tool_names_sha256") != canonical_json_sha256(request_names):
            raise ContractError(f"model-usage[{index}] request tool names hash mismatch")
        request_mcp_names = [
            name for name in request_names if name.startswith("mcp__toolathlon__")
        ]
        unexpected = sorted(set(request_mcp_names) - set(names))
        if unexpected:
            raise ContractError(
                f"model-usage[{index}] exposes MCP tools outside the current task: {unexpected}"
            )
        if request_mcp_names == names:
            full_task_surface_observed = True
    if started_request_count and names and not full_task_surface_observed:
        raise ContractError(
            "no model request exposed the complete current-task MCP tool surface"
        )


def _validate_product_identity(
    root: Path, run: dict[str, Any], resolved: dict[str, Any]
) -> None:
    replacement = validate_observation(
        run.get("replacement_for_run_id"), "run.replacement_for_run_id"
    )["value"]
    expected_ordinal = 2 if replacement is not None else 1
    planned = _require_object(
        _require_object(resolved.get("adapter"), "resolved-config.adapter").get(
            "product_identity"
        ),
        "resolved-config.adapter.product_identity",
    )
    if planned.get("attempt_ordinal") != expected_ordinal:
        raise ContractError("resolved product identity attempt ordinal mismatch")
    if planned.get("attempt_label") != f"a{expected_ordinal}":
        raise ContractError("resolved product identity attempt label mismatch")
    if planned.get("provider_user_id_is_product_identity") is not False:
        raise ContractError("provider user_id is incorrectly classified as product identity")

    observed = _require_object(run.get("adapter"), "run.adapter").get(
        "product_identity"
    )
    if run["system_id"] == "hermes":
        if planned.get("strategy") != "hermes_ephemeral_runtime_session":
            raise ContractError("Hermes planned identity strategy mismatch")
        if run.get("run_validity") == "valid":
            item = _require_object(observed, "run.adapter.product_identity")
            required = {
                "strategy": "hermes_ephemeral_runtime_session",
                "fresh_hermes_home": True,
                "fresh_gateway_process": True,
                "fresh_gateway_api_key": True,
                "memory_provider": "",
                "true_server_user_identity": False,
                "provider_user_id_is_product_identity": False,
            }
            for field, value in required.items():
                if item.get(field) != value:
                    raise ContractError(f"Hermes product identity field mismatch: {field}")
            if re.fullmatch(r"[0-9a-f]{64}", str(item.get("attempt_session_id_sha256"))) is None:
                raise ContractError("Hermes session identity fingerprint is missing")
        if (root / PRIVATE_IDENTITY_FILENAME).exists():
            raise ContractError("Hermes must not produce an Astra private identity record")
        return

    if planned.get("strategy") != "astra_registered_user_per_attempt":
        raise ContractError("Astra planned identity strategy mismatch")
    private_path = root / PRIVATE_IDENTITY_FILENAME
    if not private_path.is_file() or private_path.is_symlink():
        raise ContractError("Astra private product identity record is missing")
    if os.stat(private_path).st_mode & 0o077:
        raise ContractError("Astra private product identity record is not mode 0600")
    private = _read_json(private_path)
    if private.get("schema_version") != "toolathlon.astra-product-identity.private.v1":
        raise ContractError("Astra private product identity schema mismatch")
    if private.get("run_id") != run["run_id"] or private.get("task_id") != run["task_id"]:
        raise ContractError("Astra private product identity run mismatch")
    if private.get("attempt_ordinal") != expected_ordinal or private.get(
        "attempt_label"
    ) != f"a{expected_ordinal}":
        raise ContractError("Astra private product identity attempt mismatch")
    username = private.get("username")
    password = private.get("password")
    if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
        raise ContractError("Astra private product credentials are incomplete")
    if "access_token" in private or "refresh_token" in private:
        raise ContractError("Astra access or refresh token was persisted")
    item = _require_object(observed, "run.adapter.product_identity")
    if item.get("attempt_ordinal") != expected_ordinal:
        raise ContractError("Astra observed identity attempt mismatch")
    if item.get("private_record") != PRIVATE_IDENTITY_FILENAME:
        raise ContractError("Astra private identity path mismatch")
    if item.get("private_record_sha256") != sha256_file(private_path):
        raise ContractError("Astra private identity hash mismatch")
    if item.get("username_sha256") != hashlib.sha256(username.encode()).hexdigest():
        raise ContractError("Astra username fingerprint mismatch")
    if item.get("plaintext_password_persisted") is not True:
        raise ContractError("Astra password persistence is not recorded")
    if item.get("access_or_refresh_token_persisted") is not False:
        raise ContractError("Astra token persistence boundary is invalid")
    if run.get("run_validity") == "valid":
        if private.get("registration_status") != "verified":
            raise ContractError("valid Astra run has no verified registration")
        if private.get("auth_me_verified") is not True or item.get("auth_me_verified") is not True:
            raise ContractError("valid Astra run has no /auth/me verification")
        if re.fullmatch(r"[0-9a-f]{64}", str(item.get("server_user_id_sha256"))) is None:
            raise ContractError("valid Astra run has no server user fingerprint")

    serialized_public = "\n".join(
        (root / name).read_text(encoding="utf-8", errors="replace")
        for name in ("resolved-config.json", "run.json", "adapter-events.jsonl")
    )
    if password in serialized_public or username in serialized_public:
        raise ContractError("Astra private product credentials leaked into public metadata")


def _validate_hash_manifest(root: Path) -> int:
    path = root / "artifacts.sha256"
    expected: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SHA_LINE.fullmatch(line)
        if match is None:
            raise ContractError(f"invalid artifacts.sha256 line {line_number}")
        digest, relative = match.groups()
        candidate = (root / relative).resolve()
        if root.resolve() not in candidate.parents or not candidate.is_file() or candidate.is_symlink():
            raise ContractError(f"unsafe or missing hashed artifact: {relative}")
        if relative in expected:
            raise ContractError(f"duplicate artifact hash entry: {relative}")
        if sha256_file(candidate) != digest:
            raise ContractError(f"artifact digest mismatch: {relative}")
        expected[relative] = digest
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "artifacts.sha256"
    }
    if set(expected) != actual:
        missing = sorted(actual - set(expected))
        extra = sorted(set(expected) - actual)
        raise ContractError(f"artifact hash coverage mismatch; missing={missing}, extra={extra}")
    return len(expected)


def validate_run_artifacts(
    root: Path,
    *,
    verify_hash: bool = True,
    require_validation_end: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    if missing:
        raise ContractError(f"required run artifacts are missing: {missing}")

    run = _read_json(root / "run.json")
    resolved = _read_json(root / "resolved-config.json")
    failure = _read_json(root / "failure-evidence.json")
    _read_json(root / "evaluator/eval_res.json")
    for field in ("run_id", "system_id", "task_id", "experiment_id"):
        if not isinstance(run.get(field), str) or not run[field]:
            raise ContractError(f"run.json has no {field}")
        if resolved.get(field) != run[field]:
            raise ContractError(f"resolved-config identity mismatch: {field}")
    if run.get("pair_id") != f"{run['experiment_id']}:{run['task_id']}":
        raise ContractError("run.json pair_id mismatch")
    if resolved.get("pair_id") != run["pair_id"]:
        raise ContractError("resolved-config pair_id mismatch")
    freeze = _require_object(resolved.get("freeze"), "resolved-config.freeze")
    for field in (
        "m0_manifest_sha256",
        "sections_3_1_3_2_manifest_sha256",
        "section_3_3_sha256",
        "section_3_3_manifest_sha256",
        "adapter_freeze_sha256",
        "system_freeze_sha256",
        "model_sha256",
        "runtime_tiers_sha256",
        "runtime_config_sha256",
        "permission_policy_sha256",
        "task_requirements_sha256",
        "execution_protocol_sha256",
        "vm_freeze_sha256",
        "credential_manifest_sha256",
        "app_state_live_sha256",
    ):
        value = freeze.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ContractError(f"resolved-config.freeze has no valid {field}")
    if run.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ContractError("run.json artifact schema version mismatch")
    if verify_hash and run.get("artifact_gate", {}).get("status") != "passed":
        raise ContractError("run.json artifact gate is not passed")
    if failure.get("run_id") != run["run_id"] or failure.get("system_id") != run["system_id"]:
        raise ContractError("failure-evidence identity mismatch")
    validate_observation(failure.get("raw_error_code"), "failure-evidence.raw_error_code")
    if not isinstance(failure.get("evidence_paths"), list):
        raise ContractError("failure-evidence.evidence_paths must be a list")
    _validate_product_identity(root, run, resolved)

    lifecycle = read_jsonl(root / "lifecycle-events.jsonl", allow_empty=False)
    adapter = read_jsonl(root / "adapter-events.jsonl", allow_empty=False)
    trajectory = read_jsonl(root / "trajectory.jsonl", allow_empty=True)
    tools = read_jsonl(root / "tool-calls.jsonl", allow_empty=True)
    models = read_jsonl(root / "model-usage.jsonl", allow_empty=True)
    resources = read_jsonl(root / "resource-usage.jsonl", allow_empty=False)
    _validate_lifecycle(
        lifecycle, run, require_validation_end=require_validation_end
    )
    _validate_identity(adapter, run, "adapter-events")
    _validate_identity(trajectory, run, "trajectory")
    _validate_tool_calls(tools, run)
    _validate_tool_event_completeness(trajectory, tools, run)
    _validate_model_usage(models, run)
    _validate_task_tool_exposure(root, run, resolved, models)
    _validate_agent_model_boundary(adapter, models, run)
    _validate_identity(resources, run, "resource-usage")

    hash_count = _validate_hash_manifest(root) if verify_hash else None
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "status": "passed",
        "required_artifacts": len(REQUIRED_ARTIFACTS)
        + (1 if run["system_id"] == "astra" else 0),
        "hashed_artifacts": hash_count,
        "lifecycle_events": len(lifecycle),
        "adapter_events": len(adapter),
        "trajectory_events": len(trajectory),
        "tool_events": len(tools),
        "model_events": len(models),
        "resource_samples": len(resources),
    }
