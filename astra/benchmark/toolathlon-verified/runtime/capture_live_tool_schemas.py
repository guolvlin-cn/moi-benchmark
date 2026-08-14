#!/usr/bin/env python3
"""Capture one real Gateway tools/list result for each frozen Toolathlon task."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiohttp
from aiohttp import web
import yaml

from configs.token_key_session import all_token_key_session
from utils.data_structures.task_config import TaskConfig

from container_tool_gateway_m1 import (
    BRIDGED_LOCAL_TOOLS,
    SCAFFOLD_LOCAL_TOOLS,
    QualifiedContainerToolGateway,
)


EXPECTED_COMMIT = "2aed2468858f15818acafa178518390cc4b0f5cb"


class SanitizedCaptureError(RuntimeError):
    """Capture failure whose message is safe to persist in qualification output."""

    def __init__(self, original_type: str, message: str) -> None:
        super().__init__(message)
        self.original_type = original_type


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def astra_component(value: str) -> str:
    return "".join(char if (char.isalnum() or char in "_-") else "_" for char in value)


def hermes_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


async def read_sse_event(response: aiohttp.ClientResponse) -> tuple[str, str]:
    event = "message"
    data: list[str] = []
    while True:
        raw = await response.content.readline()
        if not raw:
            raise RuntimeError("Gateway SSE stream ended unexpectedly")
        line = raw.decode("utf-8", errors="strict").rstrip("\r\n")
        if not line:
            if data:
                return event, "\n".join(data)
            event = "message"
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)


async def rpc_tools_list(base_url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        response = await session.get(f"{base_url}/sse", headers={"Accept": "text/event-stream"})
        if response.status != 200:
            raise RuntimeError(f"Gateway SSE status {response.status}")
        event, endpoint_data = await read_sse_event(response)
        if event != "endpoint":
            raise RuntimeError(f"Gateway first SSE event was {event}, expected endpoint")
        endpoint = urljoin(f"{base_url}/sse", endpoint_data.strip())

        async def request(request_id: int, method: str, params: Any = None) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
            }
            if params is not None:
                payload["params"] = params
            posted = await session.post(endpoint, json=payload)
            if posted.status not in {200, 202, 204}:
                raise RuntimeError(f"Gateway message status {posted.status}")
            while True:
                response_event, data = await read_sse_event(response)
                if response_event not in {"message", "response"}:
                    continue
                value = json.loads(data)
                if value.get("id") != request_id:
                    continue
                if "error" in value:
                    raise RuntimeError(f"Gateway RPC error for {method}: {value['error']}")
                return value["result"]

        initialized = await request(
            1,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "toolathlon-m1-freeze", "version": "1.0.0"},
            },
        )
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        posted = await session.post(endpoint, json=notification)
        if posted.status not in {200, 202, 204}:
            raise RuntimeError(f"Gateway initialized notification status {posted.status}")
        listed = await request(2, "tools/list")
        response.release()
    tools = listed.get("tools")
    if not isinstance(tools, list):
        raise RuntimeError("Gateway tools/list did not return a list")
    normalized = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise RuntimeError("Gateway emitted a non-object tool")
        name = tool.get("name")
        schema = tool.get("inputSchema")
        if not isinstance(name, str) or not isinstance(schema, dict):
            raise RuntimeError("Gateway emitted an invalid tool name or inputSchema")
        normalized.append(
            {
                "name": name,
                "description": tool.get("description") or "",
                "inputSchema": schema,
            }
        )
    normalized.sort(key=lambda item: item["name"])
    if len({item["name"] for item in normalized}) != len(normalized):
        raise RuntimeError("Gateway emitted duplicate tool names")
    return initialized, normalized


def collect_secret_strings(local_mapping: Any) -> list[str]:
    values: set[str] = set()
    mappings = [all_token_key_session]
    if local_mapping is not None:
        mappings.append(local_mapping)
    for mapping in mappings:
        for key, value in mapping.items():
            lowered = str(key).lower()
            if not any(marker in lowered for marker in ("key", "token", "secret", "password")):
                continue
            if isinstance(value, str) and len(value) >= 8 and value.lower() not in {"null", "none"}:
                values.add(value)
    return sorted(values, key=len, reverse=True)


def assert_no_secrets(serialized: str, secret_values: list[str]) -> None:
    for value in secret_values:
        if value in serialized:
            raise RuntimeError("a credential value appeared in tools/list output")


def redact_secrets(text: str, secret_values: list[str]) -> str:
    redacted = text
    for value in secret_values:
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def prepare_runtime_mcp_configs(source: Path, runtime_root: Path) -> Path:
    """Create private runtime configs without changing the frozen source tree."""

    config_dir = runtime_root / "mcp-configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    for source_config in sorted((source / "configs" / "mcp_servers").glob("*.yaml")):
        shutil.copyfile(source_config, config_dir / source_config.name)

    private_dir = runtime_root / "private"
    private_dir.mkdir(mode=0o700)
    calendar_oauth = private_dir / "calendar-oauth.json"
    calendar_credentials = private_dir / "calendar-credentials.json"
    shutil.copyfile(source / "configs" / "gcp-oauth.keys.json", calendar_oauth)
    shutil.copyfile(source / "configs" / "google_credentials.json", calendar_credentials)
    os.chmod(calendar_oauth, 0o600)
    os.chmod(calendar_credentials, 0o600)

    calendar_path = config_dir / "google_calendar.yaml"
    calendar_config = yaml.safe_load(calendar_path.read_text(encoding="utf-8"))
    params = calendar_config.setdefault("params", {})
    environment = params.setdefault("env", {})
    environment["CALENDAR_OAUTH_PATH"] = str(calendar_oauth)
    environment["CALENDAR_CREDENTIALS_PATH"] = str(calendar_credentials)
    calendar_path.write_text(
        yaml.safe_dump(calendar_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return config_dir


def build_task_manifest(
    *,
    task_id: str,
    initialized: dict[str, Any],
    tools: list[dict[str, Any]],
    required_mcp: list[str],
    required_local: list[str],
    connected_servers: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    astra_names: set[str] = set()
    hermes_names: set[str] = set()
    collisions: list[dict[str, str]] = []
    for order, tool in enumerate(tools):
        gateway_name = tool["name"]
        astra_name = f"mcp__toolathlon__{astra_component(gateway_name)}"
        hermes_name = f"mcp__toolathlon__{hermes_component(gateway_name)}"
        if astra_name in astra_names:
            collisions.append({"system": "astra", "model_visible_tool_name": astra_name})
        if hermes_name in hermes_names:
            collisions.append({"system": "hermes", "model_visible_tool_name": hermes_name})
        astra_names.add(astra_name)
        hermes_names.add(hermes_name)
        schema = tool["inputSchema"]
        rows.append(
            {
                "order": order,
                "canonical_tool_name": gateway_name,
                "gateway_tool_name": gateway_name,
                "astra_model_visible_tool_name": astra_name,
                "hermes_model_visible_tool_name": hermes_name,
                "description": tool["description"],
                "input_schema": schema,
                "required_fields": sorted(schema.get("required", [])),
                "schema_sha256": canonical_sha256(schema),
                "sha256": canonical_sha256(tool),
            }
        )

    required_semantic = sorted(set(required_local) & set(BRIDGED_LOCAL_TOOLS))
    expected_local_names = {
        "python_execute": "local-python-execute",
        "web_search": "local-web-search",
        "sleep": "local-sleep",
    }
    observed_names = {tool["name"] for tool in tools}
    missing_semantic = [
        name for name in required_semantic if expected_local_names[name] not in observed_names
    ]
    missing_servers = sorted(set(required_mcp) - set(connected_servers))
    task_state = "GO" if not collisions and not missing_semantic and not missing_servers else "NO_GO"
    return {
        "schema_version": "toolathlon.task-tools.live.v1",
        "task_id": task_id,
        "state": task_state,
        "gateway": {
            "protocol_version": initialized.get("protocolVersion"),
            "server_info": initialized.get("serverInfo"),
            "rpc": "real_sse_tools_list",
        },
        "required_mcp_servers": required_mcp,
        "connected_mcp_servers": connected_servers,
        "missing_mcp_servers": missing_servers,
        "required_local_tools": required_local,
        "bridged_task_semantic_local_tools": required_semantic,
        "excluded_agent_scaffold_local_tools": sorted(
            set(required_local) & set(SCAFFOLD_LOCAL_TOOLS)
        ),
        "missing_task_semantic_local_tools": missing_semantic,
        "tool_count": len(rows),
        "tool_set_sha256": canonical_sha256(tools),
        "collisions": collisions,
        "tools": rows,
    }


async def capture_one(
    source: Path,
    task_id: str,
    requirements: dict[str, Any],
    work_root: Path,
    mcp_config_dir: Path,
) -> dict[str, Any]:
    secret_values = collect_secret_strings(None)
    task_dir = f"finalpool/{task_id}"
    task_workspace = work_root / "workspaces" / task_id
    task_workspace.mkdir(parents=True, exist_ok=True)
    task_config = TaskConfig.build(
        task_dir=task_dir,
        agent_short_name="m1-schema-freeze",
        global_task_config={
            "dump_path": str(work_root / "task-roots"),
            "max_turns": 1,
            "max_steps_under_single_turn_mode": 100,
        },
        single_turn_mode=True,
        cn_mode=False,
    )
    task_config.agent_workspace = str(task_workspace)
    task_config.load_local_token_key_session()
    secret_values = collect_secret_strings(task_config.local_token_key_session)
    bundle = {
        "schema_version": 2,
        "task_dir": task_dir,
        "needed_mcp_servers": list(requirements["mcp_servers"]),
        "needed_local_tools": list(requirements["local_tools"]),
        "container_paths": {"agent_workspace": str(task_workspace)},
        "eval_config": {
            "mcp": {"server_config_path": str(mcp_config_dir)}
        },
        "local_token_key_session": task_config.local_token_key_session,
    }
    bundle_path = work_root / "bundles" / f"{task_id}.private.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    os.chmod(bundle_path, 0o600)

    try:
        gateway = QualifiedContainerToolGateway(str(bundle_path), debug=False)
        app = gateway.create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            sockets = getattr(site, "_server").sockets
            port = int(sockets[0].getsockname()[1])
            base_url = f"http://127.0.0.1:{port}"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                health_response = await session.get(f"{base_url}/health")
                health = await health_response.json()
            initialized, tools = await rpc_tools_list(base_url)
            result = build_task_manifest(
                task_id=task_id,
                initialized=initialized,
                tools=tools,
                required_mcp=list(requirements["mcp_servers"]),
                required_local=list(requirements["local_tools"]),
                connected_servers=list(health.get("connected_servers", [])),
            )
            serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
            assert_no_secrets(serialized, secret_values)
            return result
        finally:
            await runner.cleanup()
    except SanitizedCaptureError:
        raise
    except Exception as exc:
        raise SanitizedCaptureError(
            type(exc).__name__,
            redact_secrets(str(exc), secret_values),
        ) from None
    finally:
        try:
            bundle_path.unlink()
        except FileNotFoundError:
            pass


async def main_async(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    output = args.output.resolve()
    requirements_root = json.loads(args.requirements.read_text(encoding="utf-8"))
    if requirements_root.get("source_commit") != EXPECTED_COMMIT:
        raise SystemExit("task requirement source commit mismatch")
    all_tasks = requirements_root["tasks"]
    if len(all_tasks) != 108:
        raise SystemExit(f"expected 108 tasks, found {len(all_tasks)}")
    if args.task_id:
        missing = sorted(set(args.task_id) - set(all_tasks))
        if missing:
            raise SystemExit(f"unknown task ids: {missing}")
        tasks = {task_id: all_tasks[task_id] for task_id in sorted(set(args.task_id))}
    else:
        tasks = all_tasks
    output.mkdir(parents=True, exist_ok=True)
    work_root = args.work_root.resolve()
    work_root.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="toolathlon-m1-private-") as private:
        mcp_config_dir = prepare_runtime_mcp_configs(source, Path(private))
        for index, task_id in enumerate(sorted(tasks), start=1):
            last_error: Exception | None = None
            result: dict[str, Any] | None = None
            for attempt in range(1, 3):
                try:
                    result = await asyncio.wait_for(
                        capture_one(
                            source,
                            task_id,
                            tasks[task_id],
                            work_root,
                            mcp_config_dir,
                        ),
                        timeout=args.task_timeout,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt == 1:
                        await asyncio.sleep(1)
            if result is None:
                failure = {
                    "task_id": task_id,
                    "state": "NO_GO",
                    "error_type": (
                        last_error.original_type
                        if isinstance(last_error, SanitizedCaptureError)
                        else type(last_error).__name__ if last_error else "unknown"
                    ),
                    "error": str(last_error) if last_error else "unknown error",
                }
                failures.append(failure)
                write_json(output / "tasks" / f"{task_id}.json", failure)
                print(json.dumps({"index": index, **failure}, sort_keys=True), flush=True)
                continue
            write_json(output / "tasks" / f"{task_id}.json", result)
            summary = {
                "task_id": task_id,
                "state": result["state"],
                "tool_count": result["tool_count"],
                "tool_set_sha256": result["tool_set_sha256"],
            }
            summaries.append(summary)
            print(json.dumps({"index": index, **summary}, sort_keys=True), flush=True)

    root_input = sorted(summaries, key=lambda item: item["task_id"])
    full_scope = not args.task_id
    state = "GO" if full_scope and len(summaries) == 108 and not failures and all(
        item["state"] == "GO" for item in summaries
    ) else ("TEST_ONLY" if not full_scope and not failures else "NO_GO")
    manifest = {
        "schema_version": "toolathlon.tools.live-root.v1",
        "source_commit": EXPECTED_COMMIT,
        "captured_at": args.captured_at,
        "state": state,
        "expected_task_count": 108,
        "qualification_scope": "all_108" if full_scope else "selected_test_tasks",
        "observed_task_count": len(summaries),
        "failed_task_count": len(failures),
        "task_schema_root_sha256": canonical_sha256(root_input),
        "tasks": root_input,
        "failures": failures,
        "local_tool_policy": {
            "gateway_claim_done": True,
            "common_task_semantic_bridge": sorted(BRIDGED_LOCAL_TOOLS),
            "agent_scaffold_not_injected": sorted(SCAFFOLD_LOCAL_TOOLS),
        },
    }
    write_json(output / "tool-schema-manifest.json", manifest)
    return 0 if state == "GO" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, default=Path(tempfile.gettempdir()) / "toolathlon-m1-schema")
    parser.add_argument("--captured-at", required=True)
    parser.add_argument("--task-timeout", type=float, default=600.0)
    parser.add_argument("--task-id", action="append")
    return parser.parse_args()


def main() -> int:
    return asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
