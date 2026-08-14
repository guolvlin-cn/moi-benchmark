from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            digest.update(raw_line)
            try:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"invalid Pi JSONL at line {line_number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise RuntimeError(
                    f"Pi JSONL line {line_number} is not an object"
                )
            rows.append(value)
    if not rows:
        raise RuntimeError("Pi JSONL is empty")
    return rows, digest.hexdigest()


def validate_event_stream(
    path: Path,
    *,
    expected_provider: str,
    expected_model: str,
) -> dict[str, Any]:
    rows, sha256 = _load_jsonl(path)
    header = rows[0]
    session_id = header.get("id")
    if (
        header.get("type") != "session"
        or not isinstance(session_id, str)
        or not session_id
        or not isinstance(header.get("cwd"), str)
    ):
        raise RuntimeError("Pi event stream has no valid session header")
    if sum(row.get("type") == "session" for row in rows) != 1:
        raise RuntimeError("Pi event stream must contain one session header")
    if sum(row.get("type") == "agent_start" for row in rows) != 1:
        raise RuntimeError("Pi event stream must contain one agent_start")
    if sum(row.get("type") == "agent_end" for row in rows) != 1:
        raise RuntimeError("Pi event stream must contain one agent_end")
    if rows[-1].get("type") != "agent_end":
        raise RuntimeError("Pi event stream does not end with agent_end")

    assistants: list[dict[str, Any]] = []
    for row in rows:
        if row.get("type") != "message_end":
            continue
        message = row.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            assistants.append(message)
    if not assistants:
        raise RuntimeError("Pi event stream has no assistant message_end")
    providers = {message.get("provider") for message in assistants}
    models = {message.get("model") for message in assistants}
    if providers != {expected_provider} or models != {expected_model}:
        raise RuntimeError(
            "Pi event stream provider/model does not match the frozen cohort"
        )
    stop_reason = assistants[-1].get("stopReason")
    if not isinstance(stop_reason, str) or not stop_reason:
        raise RuntimeError("Pi final assistant message has no stopReason")

    starts: dict[str, str] = {}
    completed: set[str] = set()
    for row in rows:
        event_type = row.get("type")
        if event_type == "tool_execution_start":
            call_id = row.get("toolCallId")
            tool_name = row.get("toolName")
            if not isinstance(call_id, str) or not isinstance(tool_name, str):
                raise RuntimeError("Pi tool start has an invalid identity")
            if call_id in starts:
                raise RuntimeError("Pi tool call starts more than once")
            starts[call_id] = tool_name
        elif event_type == "tool_execution_end":
            call_id = row.get("toolCallId")
            if call_id not in starts or call_id in completed:
                raise RuntimeError("Pi tool end has no unique matching start")
            if row.get("toolName") != starts[call_id]:
                raise RuntimeError("Pi tool start/end names disagree")
            completed.add(call_id)
    if completed != set(starts):
        raise RuntimeError("Pi event stream has incomplete tool calls")

    return {
        "sha256": sha256,
        "event_count": len(rows),
        "session_id": session_id,
        "cwd": header["cwd"],
        "assistant_message_count": len(assistants),
        "tool_call_count": len(starts),
        "provider": expected_provider,
        "model": expected_model,
        "stop_reason": stop_reason,
        "complete": stop_reason not in {"error", "aborted"},
    }


def validate_session(path: Path, *, session_id: str) -> dict[str, Any]:
    rows, sha256 = _load_jsonl(path)
    header = rows[0]
    if header.get("type") != "session" or header.get("id") != session_id:
        raise RuntimeError("Pi saved session identity does not match stdout")
    if len(rows) < 2:
        raise RuntimeError("Pi saved session contains no entries")
    return {
        "sha256": sha256,
        "entry_count": len(rows),
        "session_id": session_id,
    }
