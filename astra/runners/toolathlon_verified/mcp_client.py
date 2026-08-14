from __future__ import annotations

import json
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin, urlparse

from .contract import (
    ContractError,
    canonical_json_sha256,
    utc_now,
    validate_loopback_url,
    write_json_atomic,
)


MCP_PROTOCOL_VERSION = "2024-11-05"


def _iter_sse(response: Any) -> Iterator[tuple[str, str]]:
    event = "message"
    data: list[str] = []
    while True:
        raw = response.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="strict").rstrip("\r\n")
        if not line:
            if data:
                yield event, "\n".join(data)
            event = "message"
            data = []
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
    if data:
        yield event, "\n".join(data)


class ClassicSseMcpClient:
    """Small read-only MCP client used to freeze a Gateway tools/list view."""

    def __init__(self, sse_url: str, *, timeout_s: float = 30.0) -> None:
        self.sse_url = validate_loopback_url("gateway_url", sse_url, require_sse=True)
        self.timeout_s = float(timeout_s)
        if self.timeout_s <= 0:
            raise ContractError("MCP timeout must be positive")
        self._endpoint: str | None = None
        self._endpoint_ready = threading.Event()
        self._stop = threading.Event()
        self._error: BaseException | None = None
        self._responses: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._response: Any = None
        self._thread: threading.Thread | None = None
        self._next_id = 0

    def __enter__(self) -> "ClassicSseMcpClient":
        self.connect()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def connect(self) -> None:
        if self._thread is not None:
            raise ContractError("MCP client is already connected")
        self._thread = threading.Thread(target=self._reader, name="mcp-sse-reader", daemon=True)
        self._thread.start()
        if not self._endpoint_ready.wait(self.timeout_s):
            self.close()
            raise TimeoutError("Gateway did not publish an MCP message endpoint")
        self._raise_reader_error()
        if self._endpoint is None:
            raise ContractError("Gateway SSE stream did not supply an endpoint")

    def close(self) -> None:
        self._stop.set()
        response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        self._thread = None

    def _reader(self) -> None:
        try:
            request = urllib.request.Request(
                self.sse_url,
                headers={"Accept": "text/event-stream"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                self._response = response
                content_type = response.headers.get_content_type()
                if content_type != "text/event-stream":
                    raise ContractError(
                        f"Gateway /sse returned unexpected content type {content_type}"
                    )
                for event, data in _iter_sse(response):
                    if self._stop.is_set():
                        break
                    if event == "endpoint":
                        self._endpoint = self._validated_endpoint(data)
                        self._endpoint_ready.set()
                        continue
                    if event not in {"message", "response"}:
                        continue
                    try:
                        value = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ContractError("Gateway emitted invalid JSON over SSE") from exc
                    if isinstance(value, dict) and "id" in value:
                        self._responses.put(value)
        except BaseException as exc:
            if not self._stop.is_set():
                self._error = exc
        finally:
            self._endpoint_ready.set()

    def _validated_endpoint(self, value: str) -> str:
        endpoint = urljoin(self.sse_url, value.strip())
        sse = urlparse(self.sse_url)
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != sse.scheme
            or parsed.hostname != sse.hostname
            or parsed.port != sse.port
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ContractError("Gateway advertised a cross-origin MCP message endpoint")
        return endpoint

    def _raise_reader_error(self) -> None:
        if self._error is not None:
            raise ContractError(f"Gateway SSE reader failed: {self._error}") from self._error

    def _post(self, value: dict[str, Any]) -> None:
        if self._endpoint is None:
            raise ContractError("MCP client is not connected")
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(value, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                if response.status not in {200, 202, 204}:
                    raise ContractError(f"Gateway message POST returned HTTP {response.status}")
                response.read()
        except urllib.error.HTTPError as exc:
            raise ContractError(f"Gateway message POST returned HTTP {exc.code}") from exc

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._post(payload)

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._next_id += 1
        request_id = self._next_id
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        self._post(payload)
        deadline = time.monotonic() + self.timeout_s
        deferred: list[dict[str, Any]] = []
        try:
            while time.monotonic() < deadline:
                self._raise_reader_error()
                try:
                    remaining = max(0.001, deadline - time.monotonic())
                    value = self._responses.get(timeout=min(0.2, remaining))
                except queue.Empty:
                    continue
                if value.get("id") != request_id:
                    deferred.append(value)
                    continue
                if "error" in value:
                    raise ContractError(f"Gateway MCP error for {method}: {value['error']}")
                if "result" not in value:
                    raise ContractError(f"Gateway MCP response for {method} has no result")
                return value["result"]
        finally:
            for item in deferred:
                self._responses.put(item)
        raise TimeoutError(f"Gateway MCP request timed out: {method}")

    def initialize(self) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "toolathlon-freeze-inspector",
                    "version": "1.0.0",
                },
            },
        )
        if not isinstance(result, dict):
            raise ContractError("Gateway initialize result is not an object")
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        initialized = self.initialize()
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            params = {"cursor": cursor} if cursor else None
            result = self.request("tools/list", params)
            if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                raise ContractError("Gateway tools/list result is invalid")
            for tool in result["tools"]:
                if not isinstance(tool, dict):
                    raise ContractError("Gateway returned a non-object tool schema")
                name = tool.get("name")
                schema = tool.get("inputSchema")
                if not isinstance(name, str) or not name:
                    raise ContractError("Gateway returned a tool with no name")
                if not isinstance(schema, dict):
                    raise ContractError(f"Gateway tool {name} has no inputSchema")
                tools.append(
                    {
                        "name": name,
                        "description": tool.get("description") or "",
                        "inputSchema": schema,
                    }
                )
            next_cursor = result.get("nextCursor")
            if not next_cursor:
                break
            if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
                raise ContractError("Gateway tools/list pagination cursor is invalid")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        names = [item["name"] for item in tools]
        if len(names) != len(set(names)):
            raise ContractError("Gateway tools/list contains duplicate names")
        return initialized, sorted(tools, key=lambda item: item["name"])


def _astra_component(value: str) -> str:
    return "".join(char if (char.isalnum() or char in "_-") else "_" for char in value)


def _hermes_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def build_observed_tool_manifest(
    *,
    task_id: str,
    gateway_url: str,
    initialize_result: dict[str, Any],
    tools: list[dict[str, Any]],
    server_name: str = "toolathlon",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    hermes_names: set[str] = set()
    astra_names: set[str] = set()
    collisions: list[dict[str, str]] = []
    for tool in tools:
        gateway_name = tool["name"]
        astra_name = f"mcp__{_astra_component(server_name)}__{_astra_component(gateway_name)}"
        hermes_name = f"mcp__{_hermes_component(server_name)}__{_hermes_component(gateway_name)}"
        if astra_name in astra_names:
            collisions.append({"system": "astra", "model_visible_name": astra_name})
        if hermes_name in hermes_names:
            collisions.append({"system": "hermes", "model_visible_name": hermes_name})
        astra_names.add(astra_name)
        hermes_names.add(hermes_name)
        rows.append(
            {
                "canonical_tool_name": gateway_name,
                "gateway_tool_name": gateway_name,
                "astra_model_visible_tool_name": astra_name,
                "hermes_model_visible_tool_name": hermes_name,
                "names_equal": astra_name == hermes_name,
                "schema_sha256": canonical_json_sha256(tool["inputSchema"]),
                "tool_sha256": canonical_json_sha256(tool),
                "raw": tool,
            }
        )
    return {
        "schema_version": 1,
        "captured_at": utc_now(),
        "task_id": task_id,
        "gateway": {
            "url": gateway_url,
            "server_info": initialize_result.get("serverInfo"),
            "protocol_version": initialize_result.get("protocolVersion"),
        },
        "server_name_in_products": server_name,
        "tool_count": len(rows),
        "tool_set_sha256": canonical_json_sha256(tools),
        "model_visible_name_equality": all(row["names_equal"] for row in rows),
        "collisions": collisions,
        "run_qualification": "go" if not collisions else "no_go_name_collision",
        "tools": rows,
    }


def capture_tool_manifest(
    *,
    task_id: str,
    gateway_url: str,
    destination: Path,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    with ClassicSseMcpClient(gateway_url, timeout_s=timeout_s) as client:
        initialized, tools = client.list_tools()
    manifest = build_observed_tool_manifest(
        task_id=task_id,
        gateway_url=gateway_url,
        initialize_result=initialized,
        tools=tools,
    )
    write_json_atomic(destination, manifest, mode=0o644)
    return manifest
