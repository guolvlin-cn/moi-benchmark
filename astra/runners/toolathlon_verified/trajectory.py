from __future__ import annotations

import hashlib
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

from .artifact_contract import missing_observation, observed_observation
from .contract import canonical_json_sha256, utc_now


_START_EVENTS = frozenset(
    {
        "tool_started",
        "tool.start",
        "tool.started",
        "tool_call.started",
        "tool_call_start",
        "tool.execution_start",
        "tool_transport_started",
    }
)
_SUCCESS_EVENTS = frozenset(
    {
        "tool_completed",
        "tool.complete",
        "tool.completed",
        "tool_call.completed",
        "tool_call_end",
        "tool_result",
        "tool.execution_end",
        "tool_transport_completed",
    }
)
_FAILURE_EVENTS = frozenset(
    {
        "tool_failed",
        "tool.error",
        "tool.failed",
        "tool_call.failed",
        "tool.execution_error",
        "tool_transport_failed",
    }
)


def _event_name(row: dict[str, Any]) -> str:
    value = row.get("event") or row.get("type") or row.get("kind") or "unknown"
    return str(value).strip().lower()


def _tool_name(row: dict[str, Any]) -> str | None:
    for key in ("tool_name", "name", "tool"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    function = row.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    return None


def _tool_call_id(row: dict[str, Any]) -> str | None:
    for key in ("tool_call_id", "call_id", "id", "request_id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _arguments(row: dict[str, Any]) -> Any:
    for key in ("arguments", "args", "input"):
        if key in row:
            return row[key]
    function = row.get("function")
    if isinstance(function, dict) and "arguments" in function:
        return function["arguments"]
    return None


def _first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _model_visible_to_gateway(name: str) -> str:
    prefix = "mcp__toolathlon__"
    return name[len(prefix) :] if name.startswith(prefix) else name


def _stable_call_id(run_id: str, sequence: int, name: str) -> str:
    payload = f"{run_id}\0{sequence}\0{name}".encode("utf-8")
    return "adapter_" + hashlib.sha256(payload).hexdigest()[:24]


def read_json_rows(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def normalize_product_events(
    rows: Iterable[dict[str, Any]],
    *,
    run_id: str,
    system_id: str,
    trajectory_path: Path,
    tool_calls_path: Path,
    observed_tool_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trajectory_path.parent.mkdir(parents=True, exist_ok=True)
    pending_by_native: dict[str, str] = {}
    pending_name_by_native: dict[str, str] = {}
    pending_arguments_by_call_id: dict[str, Any] = {}
    pending_by_name: dict[str, deque[str]] = defaultdict(deque)
    started_call_ids: set[str] = set()
    terminal_call_ids: set[str] = set()
    terminal_native_ids: set[str] = set()
    trajectory_count = 0
    started_count = 0
    terminal_count = 0
    failed_count = 0
    claim_done_seen = False
    mapped_tools: dict[str, dict[str, Any]] = {}
    if isinstance(observed_tool_manifest, dict):
        visible_key = f"{system_id}_model_visible_tool_name"
        for item in observed_tool_manifest.get("tools", []):
            if not isinstance(item, dict):
                continue
            visible_name = item.get(visible_key)
            if isinstance(visible_name, str):
                mapped_tools[visible_name] = item

    with trajectory_path.open("w", encoding="utf-8") as trajectory, tool_calls_path.open(
        "w", encoding="utf-8"
    ) as tools:
        for sequence, raw in enumerate(rows, start=1):
            captured_at = utc_now()
            captured_monotonic_ns = time.monotonic_ns()
            event = _event_name(raw)
            name = _tool_name(raw)
            native_id = _tool_call_id(raw)
            normalized = {
                "schema_version": "toolathlon.trajectory.v1",
                "timestamp": captured_at,
                "monotonic_ns": captured_monotonic_ns,
                "run_id": run_id,
                "system_id": system_id,
                "sequence": sequence,
                "event": event,
                "native_event_sha256": canonical_json_sha256(raw),
                "source_timestamp": (
                    observed_observation(raw["timestamp"], "product_event.timestamp")
                    if raw.get("timestamp") is not None
                    else missing_observation("product_event", "product_not_reported")
                ),
                "native": raw,
            }
            trajectory.write(
                json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
            trajectory_count += 1

            is_start = event in _START_EVENTS or event.endswith("tool_started")
            is_success = event in _SUCCESS_EVENTS or event.endswith("tool_completed")
            is_failure = event in _FAILURE_EVENTS or event.endswith("tool_failed")
            if (is_success or is_failure) and raw.get("success") is False:
                is_success = False
                is_failure = True
            if (
                name is None
                and native_id is not None
                and (is_success or is_failure)
            ):
                name = pending_name_by_native.get(native_id)
            if name is None or not (is_start or is_success or is_failure):
                continue

            if is_start:
                call_id = native_id or _stable_call_id(run_id, sequence, name)
                arguments = _arguments(raw)
                if call_id in started_call_ids:
                    if arguments is not None and call_id not in pending_arguments_by_call_id:
                        pending_arguments_by_call_id[call_id] = arguments
                    continue
                started_call_ids.add(call_id)
                if native_id:
                    pending_by_native[native_id] = call_id
                    pending_name_by_native[native_id] = name
                pending_by_name[name].append(call_id)
                if arguments is not None:
                    pending_arguments_by_call_id[call_id] = arguments
                state = "started"
                started_count += 1
            else:
                if native_id and native_id in terminal_native_ids:
                    continue
                call_id = pending_by_native.pop(native_id, "") if native_id else ""
                if native_id:
                    pending_name_by_native.pop(native_id, None)
                if not call_id and pending_by_name[name]:
                    call_id = pending_by_name[name].popleft()
                if not call_id:
                    call_id = native_id or _stable_call_id(run_id, sequence, name)
                else:
                    try:
                        pending_by_name[name].remove(call_id)
                    except ValueError:
                        pass
                if call_id in terminal_call_ids:
                    continue
                terminal_call_ids.add(call_id)
                if native_id:
                    terminal_native_ids.add(native_id)
                state = "failed" if is_failure else "succeeded"
                terminal_count += 1
                failed_count += int(is_failure)

            mapping = mapped_tools.get(name)
            if mapping is not None:
                gateway_name = str(mapping["gateway_tool_name"])
                canonical_name = str(mapping["canonical_tool_name"])
                mapping_reliability = "observed_tools_list"
            else:
                gateway_name = _model_visible_to_gateway(name)
                canonical_name = gateway_name
                mapping_reliability = "fallback_inference"
            if canonical_name.endswith("local-claim_done") or canonical_name.endswith(
                "claim_done"
            ):
                claim_done_seen = True
            direct_arguments = _arguments(raw)
            paired_arguments = pending_arguments_by_call_id.get(call_id)
            arguments = (
                direct_arguments if direct_arguments is not None else paired_arguments
            )
            if not is_start:
                pending_arguments_by_call_id.pop(call_id, None)
            arguments_source = (
                "product_event.arguments"
                if direct_arguments is not None
                else "product_event.arguments:paired_start"
            )
            error_type = _first_value(raw, ("error_type", "exception_type", "error"))
            raw_error_code = _first_value(raw, ("error_code", "code", "status_code"))
            record = {
                "schema_version": "toolathlon.tool-calls.v1",
                "run_id": run_id,
                "system_id": system_id,
                "tool_call_id": call_id,
                "native_tool_call_id": (
                    observed_observation(native_id, "product_event")
                    if native_id is not None
                    else missing_observation("product_event", "product_not_reported")
                ),
                "model_visible_tool_name": name,
                "gateway_tool_name": gateway_name,
                "canonical_tool_name": canonical_name,
                "name_mapping_reliability": mapping_reliability,
                "arguments_sha256": (
                    observed_observation(
                        canonical_json_sha256(arguments), arguments_source
                    )
                    if arguments is not None
                    else missing_observation("product_event", "product_not_reported")
                ),
                "state": state,
                "event": event,
                "timestamp": captured_at,
                "monotonic_ns": captured_monotonic_ns,
                "source_timestamp": normalized["source_timestamp"],
                "error_type": (
                    observed_observation(str(error_type), "product_event")
                    if error_type is not None
                    else missing_observation(
                        "product_event",
                        "no_tool_error" if not is_failure else "product_not_reported",
                    )
                ),
                "raw_error_code": (
                    observed_observation(raw_error_code, "product_event")
                    if raw_error_code is not None
                    else missing_observation(
                        "product_event",
                        "no_tool_error" if not is_failure else "product_not_reported",
                    )
                ),
                "evidence_path": observed_observation(
                    "trajectory.jsonl", "adapter_normalization"
                ),
                "native_event_sha256": normalized["native_event_sha256"],
            }
            tools.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
        trajectory.flush()
        tools.flush()
        os.fsync(trajectory.fileno())
        os.fsync(tools.fileno())

    return {
        "trajectory_events": trajectory_count,
        "tool_started_events": started_count,
        "tool_terminal_events": terminal_count,
        "tool_failed_events": failed_count,
        "claim_done_seen": claim_done_seen,
        "started_only_tool_calls": sum(len(values) for values in pending_by_name.values()),
    }
