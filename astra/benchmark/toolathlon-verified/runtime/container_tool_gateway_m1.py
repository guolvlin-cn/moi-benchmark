#!/usr/bin/env python3
"""M1 Gateway overlay for Toolathlon task-semantic local tools.

The frozen upstream decoupled Gateway owns all MCP servers and claim_done.  This
overlay exposes the remaining task-semantic local tools through that same
Gateway so Astra and Hermes receive one identical tool surface.  Agent-scaffold
tools (context/history/overlong management) intentionally stay product-native.
"""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from typing import Any

from aiohttp import web

from scripts.decoupled.container_tool_gateway import (
    ContainerToolGateway,
    ToolRecord,
)
from utils.roles.task_agent import local_tool_mappings


BRIDGED_LOCAL_TOOLS = frozenset({"python_execute", "web_search", "sleep"})
SCAFFOLD_LOCAL_TOOLS = frozenset(
    {"manage_context", "history", "handle_overlong_tool_outputs"}
)
BRIDGE_SERVER_NAME = "__toolathlon_local_bridge__"


def _function_tool(name: str) -> Any:
    tool = local_tool_mappings[name]
    if isinstance(tool, list):
        raise RuntimeError(f"M1 local bridge does not accept a toolset: {name}")
    return tool


def _result_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


class QualifiedContainerToolGateway(ContainerToolGateway):
    """Upstream Gateway plus common task-semantic Toolathlon local tools."""

    def __init__(self, bundle_file: str, debug: bool = False) -> None:
        super().__init__(bundle_file=bundle_file, debug=debug)
        self._bridged_tools: dict[str, Any] = {}

    async def startup(self, app: Any) -> None:
        await super().startup(app)
        needed = set(self.bundle.get("needed_local_tools", []) or [])
        for logical_name in sorted(needed & BRIDGED_LOCAL_TOOLS):
            tool = _function_tool(logical_name)
            exposed_name = str(tool.name)
            if self.registry.get(exposed_name) is not None:
                raise RuntimeError(f"duplicate bridged local tool name: {exposed_name}")
            schema = dict(tool.params_json_schema)
            self.registry._records[exposed_name] = ToolRecord(
                exposed_name=exposed_name,
                backend_type="bridge",
                backend_name=logical_name,
                description=str(tool.description or ""),
                input_schema=schema,
                server_name=BRIDGE_SERVER_NAME,
            )
            self._bridged_tools[logical_name] = tool

    async def cleanup(self, app: Any) -> None:
        for task in list(self._request_tasks):
            task.cancel()
        if self._request_tasks:
            import asyncio

            await asyncio.gather(*self._request_tasks, return_exceptions=True)
        self._request_tasks.clear()
        if self.mcp_manager is not None:
            await self.mcp_manager.disconnect_servers(max_disconnect_retries=0)
            # The frozen upstream lifecycle re-raises CancelledError before its
            # bookkeeping epilogue.  All tasks have already been awaited here;
            # clear only the stale manager indexes to avoid four false retries.
            self.mcp_manager._server_tasks.clear()
            self.mcp_manager.connected_servers.clear()
            self.mcp_manager._connection_events.clear()

    async def _remote_call(
        self,
        tool_record: ToolRecord,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_record.backend_type != "bridge":
            return await super()._remote_call(tool_record, arguments)
        tool = self._bridged_tools[tool_record.backend_name]
        workspace = self.bundle["container_paths"]["agent_workspace"]
        context = SimpleNamespace(context={"_agent_workspace": workspace})
        try:
            result = await tool.on_invoke_tool(
                context,
                json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
            )
            return {
                "content": [{"type": "text", "text": _result_text(result)}],
                "isError": False,
            }
        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                "isError": True,
            }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Frozen benchmark MCP SSE Gateway")
    parser.add_argument("--bundle_file", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gateway = QualifiedContainerToolGateway(
        bundle_file=args.bundle_file,
        debug=args.debug,
    )
    web.run_app(gateway.create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
