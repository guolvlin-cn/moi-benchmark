from __future__ import annotations

from pathlib import Path
from typing import Any

from . import PUBLIC_BUNDLE_SCHEMA_VERSION
from .contract import (
    ContractError,
    canonical_json_sha256,
    read_json_object,
    sha256_file,
    write_json_atomic,
)


_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "eval_config",
        "evaluation",
        "evaluator",
        "ground_truth",
        "groundtruth",
        "local_token_key_session",
        "resolved_task_config",
        "token",
        "api_key",
        "secret",
    }
)


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractError(f"trusted bundle {label} must be a string list")
    return list(value)


def _task_id_from_bundle(raw: dict[str, Any]) -> str:
    candidates = [raw.get("task_id"), raw.get("task_dir")]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.rstrip("/").rsplit("/", 1)[-1]
    raise ContractError("trusted bundle has no task identifier")


def build_public_bundle(
    trusted_bundle_path: Path,
    *,
    expected_task_id: str,
    workspace: Path,
) -> dict[str, Any]:
    raw = read_json_object(trusted_bundle_path)
    if raw.get("schema_version") != 2:
        raise ContractError("Toolathlon trusted bundle must use schema_version=2")
    actual_task_id = _task_id_from_bundle(raw)
    if actual_task_id != expected_task_id:
        raise ContractError(
            f"trusted bundle task mismatch: expected {expected_task_id}, got {actual_task_id}"
        )

    task = raw.get("task_str")
    prompts = raw.get("system_prompts")
    if not isinstance(task, str) or not task.strip():
        raise ContractError("trusted bundle task_str must be a non-empty string")
    if not isinstance(prompts, dict) or not isinstance(prompts.get("agent"), str):
        raise ContractError("trusted bundle has no agent system prompt")
    system_prompt = prompts["agent"]

    stop = raw.get("stop") or {}
    if not isinstance(stop, dict):
        raise ContractError("trusted bundle stop field must be an object")

    public = {
        "schema_version": PUBLIC_BUNDLE_SCHEMA_VERSION,
        "source_bundle": {
            "schema_version": 2,
            "sha256": sha256_file(trusted_bundle_path),
        },
        "task_id": actual_task_id,
        "prompt": {
            # These are passed verbatim. The Adapter adds no task guidance.
            "system": system_prompt,
            "task": task,
            "system_sha256": canonical_json_sha256(system_prompt),
            "task_sha256": canonical_json_sha256(task),
        },
        "tools": {
            "needed_mcp_servers": _string_list(
                raw.get("needed_mcp_servers"), "needed_mcp_servers"
            ),
            "needed_local_tools": _string_list(
                raw.get("needed_local_tools"), "needed_local_tools"
            ),
        },
        "stop": {
            "user_phrases": _string_list(stop.get("user_phrases"), "stop.user_phrases"),
            "tool_names": _string_list(stop.get("tool_names"), "stop.tool_names"),
        },
        "workspace": {
            "path": str(workspace.resolve()),
            "access": "task_scoped_read_write",
        },
    }
    _assert_public_shape(public)
    return public


def _assert_public_shape(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in _FORBIDDEN_PUBLIC_KEYS:
                raise ContractError(f"private field escaped into public bundle at {path}.{key}")
            _assert_public_shape(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_public_shape(child, path=f"{path}[{index}]")


def write_public_bundle(
    trusted_bundle_path: Path,
    destination: Path,
    *,
    expected_task_id: str,
    workspace: Path,
) -> dict[str, Any]:
    public = build_public_bundle(
        trusted_bundle_path,
        expected_task_id=expected_task_id,
        workspace=workspace,
    )
    write_json_atomic(destination, public, mode=0o644)
    return public
