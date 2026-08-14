from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import ContractError, read_json_object, validate_loopback_url


@dataclass(frozen=True)
class PermissionDecision:
    choice: str
    reason: str


@dataclass(frozen=True)
class PermissionPolicy:
    policy_id: str
    gateway_url: str
    workspace: Path
    astra_mode: str
    hermes_mode: str
    unresolved_action: str

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        expected_gateway_url: str,
        expected_workspace: Path,
    ) -> "PermissionPolicy":
        raw = read_json_object(path)
        try:
            result = cls(
                policy_id=str(raw["policy_id"]),
                gateway_url=validate_loopback_url(
                    "permission gateway_url",
                    str(raw["task_scope"]["gateway_url"]),
                    require_sse=True,
                ),
                workspace=Path(str(raw["task_scope"]["workspace"])).resolve(),
                astra_mode=str(raw["products"]["astra"]["permission_mode"]),
                hermes_mode=str(raw["products"]["hermes"]["approval_mode"]),
                unresolved_action=str(raw["unresolved_approval_action"]),
            )
        except (KeyError, TypeError) as exc:
            raise ContractError(f"invalid permission policy {path}") from exc
        if result.gateway_url != expected_gateway_url:
            raise ContractError("permission policy Gateway does not match this run")
        if result.workspace != expected_workspace.resolve():
            raise ContractError("permission policy workspace does not match this run")
        if (
            result.astra_mode != "auto"
            or result.hermes_mode != "smart"
            or result.unresolved_action != "deny"
        ):
            raise ContractError("permission policy does not match the approved boundary")
        return result

    def decide_hermes_approval(self, event: dict[str, Any]) -> PermissionDecision:
        """Resolve only approvals that can be proven task-scoped from metadata.

        Hermes smart mode already executes ordinary safe workspace operations.
        An approval that reaches this boundary is denied unless it is an
        explicitly identified call to this run's Toolathlon MCP namespace or a
        direct file operation whose canonical path is inside the task workspace.
        Shell command strings are never interpreted or auto-approved here.
        """

        tool_name = event.get("tool_name") or event.get("tool")
        if isinstance(tool_name, str) and tool_name.startswith("mcp__toolathlon__"):
            return PermissionDecision("once", "task_scoped_gateway_tool")

        path_value = event.get("path")
        if not isinstance(path_value, str):
            args = event.get("arguments") or event.get("args")
            if isinstance(args, dict):
                candidate = args.get("path") or args.get("file_path")
                if isinstance(candidate, str):
                    path_value = candidate
        if isinstance(path_value, str) and self._path_in_workspace(path_value):
            if isinstance(tool_name, str) and tool_name in {
                "read_file",
                "write_file",
                "edit_file",
                "patch",
                "list_directory",
                "search_files",
            }:
                return PermissionDecision("once", "task_scoped_workspace_file_operation")
        return PermissionDecision("deny", "unresolved_or_out_of_scope")

    def _path_in_workspace(self, value: str) -> bool:
        if "\x00" in value or "\n" in value:
            return False
        candidate = Path(os.path.expanduser(value))
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(self.workspace)
        except (OSError, ValueError):
            return False
        return True
