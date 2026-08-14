from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from astra.runners.toolathlon_verified.adapter_common import (
    AdapterOutcome,
    EphemeralState,
    strip_provider_credentials,
)
from astra.runners.toolathlon_verified.contract import (
    ContractError,
    canonical_json_sha256,
    sha256_file,
    write_json_atomic,
)
from astra.runners.toolathlon_verified.lifecycle import TASK_IMAGE
from astra.runners.toolathlon_verified.process_control import run_monitored_process
from astra.runners.toolathlon_verified.trajectory import read_json_rows


PI_VERSION = "0.73.1"
CONTAINER_WORKSPACE = "/workspace/dumps/workspace"
CONTAINER_PI_ROOT = "/opt/pi"
CONTAINER_EXTENSION = "/opt/toolathlon_mcp.ts"
CONTAINER_STATE = "/run/pi-state"
DOCKER = Path("/usr/bin/docker")
_MESSAGE_UPDATE = re.compile(
    rb'^\s*\{\s*"type"\s*:\s*"message_update"\s*[,}]'
)
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
_SANDBOX_PREFLIGHT = """\
for path in \
  /home/vagrant/dataset/Toolathlon \
  /home/vagrant/moi-benchmark \
  /tmp/toolathlon_src \
  /var/run/docker.sock
do
  if [ -e "$path" ]; then
    echo "Pi sandbox exposed forbidden host path: $path" >&2
    exit 78
  fi
done
if [ ! -d /workspace/dumps/workspace ]; then
  echo "Pi sandbox workspace mount is unavailable" >&2
  exit 78
fi
exec "$@"
"""


class _PiStdoutFilter:
    def __init__(self) -> None:
        self.dropped_message_updates = 0

    def __call__(self, line: bytes) -> bytes | None:
        if _MESSAGE_UPDATE.match(line):
            self.dropped_message_updates += 1
            return None
        return line


@dataclass(frozen=True)
class PiRuntime:
    executable: Path
    extension: Path

    @classmethod
    def load_from_environment(cls) -> "PiRuntime":
        executable_value = os.environ.get("TOOLATHLON_PI_EXECUTABLE", "")
        if not executable_value:
            raise ContractError("missing TOOLATHLON_PI_EXECUTABLE")
        executable = Path(executable_value).resolve()
        extension = Path(__file__).with_name("toolathlon_mcp.ts").resolve()
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ContractError(f"Pi executable is unavailable: {executable}")
        if not extension.is_file():
            raise ContractError(f"Pi MCP extension is unavailable: {extension}")
        if not DOCKER.is_file() or not os.access(DOCKER, os.X_OK):
            raise ContractError(f"Pi container launcher is unavailable: {DOCKER}")
        completed = subprocess.run(
            [str(executable), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        match = re.search(r"(?<![0-9])0\.73\.1(?![0-9])", completed.stdout)
        if completed.returncode != 0 or match is None:
            raise ContractError(
                f"Pi runtime must be exactly {PI_VERSION}; got {completed.stdout.strip()!r}"
            )
        return cls(executable=executable, extension=extension)


def _bind_mount(source: Path, destination: str, *, readonly: bool = False) -> str:
    option = f"type=bind,src={source},dst={destination}"
    return f"{option},readonly" if readonly else option


def _read_container_id(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ContractError(f"could not read Pi sidecar cidfile: {exc}") from exc
    if not value:
        return None
    if _CONTAINER_ID.fullmatch(value) is None:
        raise ContractError("Pi sidecar cidfile contains an invalid container ID")
    return value


def _inspect_container_pid(
    container_name: str, environment: dict[str, str]
) -> tuple[str, int] | None:
    try:
        completed = subprocess.run(
            [
                str(DOCKER),
                "inspect",
                "--format",
                "{{.Id}} {{.State.Pid}}",
                container_name,
            ],
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    fields = completed.stdout.strip().split()
    if completed.returncode != 0 or len(fields) != 2:
        return None
    container_id, raw_pid = fields
    try:
        pid = int(raw_pid)
    except ValueError:
        return None
    if _CONTAINER_ID.fullmatch(container_id) is None or pid <= 0:
        return None
    return container_id, pid


def _observe_container_pid(
    *,
    container_name: str,
    environment: dict[str, str],
    stop: threading.Event,
    observed: list[tuple[str, int] | None],
    callback: Callable[[int], None],
) -> None:
    while not stop.wait(0.05):
        identity = _inspect_container_pid(container_name, environment)
        if identity is None:
            continue
        observed[0] = identity
        callback(identity[1])
        return


def _remove_pi_container(container_name: str, environment: dict[str, str]) -> str:
    try:
        completed = subprocess.run(
            [str(DOCKER), "rm", "-f", container_name],
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContractError(f"could not clean up Pi sidecar: {exc}") from exc
    if completed.returncode == 0:
        return "removed"
    details = completed.stdout.strip()
    if "No such container" in details or "No such object" in details:
        return "already_absent"
    raise ContractError(
        f"could not clean up Pi sidecar {container_name}: {details or completed.returncode}"
    )


def _extract_output(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [
                item.get("text")
                for item in content
                if isinstance(item, dict)
                and item.get("type") == "text"
                and isinstance(item.get("text"), str)
            ]
            if texts:
                return "\n".join(texts)
    return ""


def _extract_error(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        if message.get("stopReason") != "error":
            continue
        error_message = message.get("errorMessage")
        return (
            error_message
            if isinstance(error_message, str) and error_message
            else "Pi assistant stopped with an error"
        )
    return None


def _normalize_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in events:
        row = dict(event)
        if row.get("type") == "tool_execution_start":
            row["event"] = "tool.execution_start"
        elif row.get("type") == "tool_execution_end":
            row["event"] = "tool.execution_end"
        if isinstance(row.get("toolName"), str):
            row["tool_name"] = row["toolName"]
        if isinstance(row.get("toolCallId"), str):
            row["tool_call_id"] = row["toolCallId"]
        if row.get("type") == "tool_execution_end" and row.get("isError") is True:
            row["success"] = False
        normalized.append(row)
    return normalized


def run_pi(
    *,
    runtime: PiRuntime,
    public_bundle: dict[str, Any],
    gateway_url: str,
    workspace: Path,
    output_dir: Path,
    proxy_url: str,
    deadline_seconds: int,
    budget_exceeded: Callable[[], bool],
    model_request_snapshot: Callable[[], dict[str, Any]],
    task_mcp_tool_names: list[str],
    on_product_pid: Callable[[int], None] | None = None,
    on_agent_start: Callable[[], None] | None = None,
) -> AdapterOutcome:
    stdout_path = output_dir / "adapter.stdout.log"
    stderr_path = output_dir / "adapter.stderr.log"
    prompt = public_bundle["prompt"]
    if workspace.is_symlink():
        raise ContractError("Pi workspace must not be a symlink")
    try:
        workspace = workspace.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"Pi workspace is unavailable: {exc}") from exc
    if not workspace.is_dir():
        raise ContractError("Pi workspace must be a directory")
    with EphemeralState(prefix="toolathlon-pi-") as state:
        agent_dir = state.path / "agent"
        agent_dir.mkdir(mode=0o700)
        home = state.path / "home"
        home.mkdir(mode=0o700)
        sessions = state.path / "sessions"
        sessions.mkdir(mode=0o700)
        extension_copy = state.path / "toolathlon_mcp.ts"
        extension_copy.write_bytes(runtime.extension.read_bytes())
        extension_copy.chmod(0o444)
        write_json_atomic(
            agent_dir / "settings.json",
            {
                "enableInstallTelemetry": False,
                "packages": [],
                "extensions": [],
                "skills": [],
                "prompts": [],
            },
            mode=0o600,
        )
        write_json_atomic(
            agent_dir / "models.json",
            {
                "providers": {
                    "toolathlon-proxy": {
                        "baseUrl": proxy_url.rstrip("/"),
                        "api": "openai-completions",
                        "apiKey": "toolathlon-run-proxy",
                        "models": [
                            {
                                "id": "deepseek-v4-flash",
                                "name": "DeepSeek V4 Flash",
                                "reasoning": True,
                                "contextWindow": 128000,
                                "maxTokens": 32768,
                                "compat": {"supportsDeveloperRole": False},
                                "cost": {
                                    "input": 0,
                                    "output": 0,
                                    "cacheRead": 0,
                                    "cacheWrite": 0,
                                },
                            }
                        ],
                    }
                }
            },
            mode=0o600,
        )
        env = dict(os.environ)
        strip_provider_credentials(env)
        env.pop("TOOLATHLON_DEEPSEEK_PI_API_KEY", None)
        env.pop("ASTRA_ADMIN_ACCESS_TOKEN", None)
        env["DOCKER_API_VERSION"] = "1.44"
        setup_requests = int(
            model_request_snapshot().get("provider_requests_forwarded", -1)
        )
        if setup_requests != 0:
            raise ContractError("Pi forwarded a model request before Agent execution")
        container_name = f"toolathlon-pi-agent-{state.path.name}"
        cidfile = state.path / "container.cid"
        container_pi = f"{CONTAINER_PI_ROOT}/{runtime.executable.name}"
        pi_argv = [
            container_pi,
            "--mode",
            "json",
            "--no-session",
            "--no-context-files",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--offline",
            "--provider",
            "toolathlon-proxy",
            "--model",
            "deepseek-v4-flash",
            "--thinking",
            "xhigh",
            "--append-system-prompt",
            prompt["system"],
            "--extension",
            CONTAINER_EXTENSION,
            prompt["task"],
        ]
        argv = [
            str(DOCKER),
            "run",
            "--rm",
            "--name",
            container_name,
            "--cidfile",
            str(cidfile),
            "--network",
            "host",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "512",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=512m",
            "--tmpfs",
            "/root:rw,nosuid,nodev,size=64m",
            "--mount",
            _bind_mount(workspace, CONTAINER_WORKSPACE),
            "--mount",
            _bind_mount(runtime.executable.parent, CONTAINER_PI_ROOT, readonly=True),
            "--mount",
            _bind_mount(extension_copy, CONTAINER_EXTENSION, readonly=True),
            "--mount",
            _bind_mount(state.path, CONTAINER_STATE),
            "--env",
            f"HOME={CONTAINER_STATE}/home",
            "--env",
            f"PI_CODING_AGENT_DIR={CONTAINER_STATE}/agent",
            "--env",
            f"PI_CODING_AGENT_SESSION_DIR={CONTAINER_STATE}/sessions",
            "--env",
            "PI_OFFLINE=1",
            "--env",
            "PI_SKIP_VERSION_CHECK=1",
            "--env",
            "PI_TELEMETRY=0",
            "--env",
            f"TOOLATHLON_MCP_GATEWAY_URL={gateway_url}",
            "--workdir",
            CONTAINER_WORKSPACE,
            TASK_IMAGE,
            "/bin/sh",
            "-eu",
            "-c",
            _SANDBOX_PREFLIGHT,
            "pi-sandbox",
            *pi_argv,
        ]
        stdout_filter = _PiStdoutFilter()
        observer_stop = threading.Event()
        observed_container: list[tuple[str, int] | None] = [None]
        observer: threading.Thread | None = None
        if on_product_pid is not None:
            observer = threading.Thread(
                target=_observe_container_pid,
                kwargs={
                    "container_name": container_name,
                    "environment": env,
                    "stop": observer_stop,
                    "observed": observed_container,
                    "callback": on_product_pid,
                },
                name="pi-sidecar-pid-observer",
                daemon=True,
            )
            observer.start()
        cleanup_status = "not_attempted"
        try:
            result = run_monitored_process(
                argv,
                cwd=workspace,
                env=env,
                stdin_payload=b"",
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                deadline_seconds=deadline_seconds,
                budget_exceeded=budget_exceeded,
                on_agent_start=on_agent_start,
                stdout_line_filter=stdout_filter,
            )
        finally:
            observer_stop.set()
            if observer is not None:
                observer.join(timeout=5)
            cleanup_status = _remove_pi_container(container_name, env)
        cidfile_container_id = _read_container_id(cidfile)
        observed_identity = observed_container[0]
        container_id = (
            observed_identity[0] if observed_identity is not None else cidfile_container_id
        )
        product_pid = observed_identity[1] if observed_identity is not None else None
        events = _normalize_events(read_json_rows(stdout_path))
        agent_end_seen = any(row.get("type") == "agent_end" for row in events)
        agent_error = _extract_error(events)
        error: str | None = None
        if result.termination_reason == "agent_deadline":
            terminal_status = "timeout"
        elif result.termination_reason == "max_model_requests":
            terminal_status = "max_steps"
        elif agent_error is not None:
            terminal_status = "crashed"
            error = agent_error
        elif result.return_code == 0 and agent_end_seen:
            terminal_status = "completed"
        else:
            terminal_status = "crashed"
            error = (
                f"Pi exited with code {result.return_code}"
                if result.return_code != 0
                else "Pi exited without agent_end"
            )
        return AdapterOutcome(
            terminal_status=terminal_status,
            product_exit_code=result.return_code,
            termination_reason=result.termination_reason,
            output=_extract_output(events),
            error=error,
            duration_seconds=result.duration_seconds,
            product_pid=product_pid,
            escalated_to_sigkill=result.escalated_to_sigkill,
            native_events=events,
            metadata={
                "ephemeral_state_on_tmpfs": state.on_tmpfs,
                "setup_provider_requests_before_agent": setup_requests,
                "native_event_filter": {
                    "excluded_event_types": ["message_update"],
                    "dropped_event_count": stdout_filter.dropped_message_updates,
                    "retained_tool_events": True,
                    "retained_terminal_messages": True,
                },
                "product_identity": {
                    "strategy": "pi_fresh_ephemeral_config",
                    "fresh_pi_config": True,
                    "session_persistence": False,
                    "provider_user_id_is_product_identity": False,
                },
                "runtime": {
                    "product": "pi",
                    "version": PI_VERSION,
                    "executable_sha256": sha256_file(runtime.executable),
                    "mcp_extension_sha256": sha256_file(runtime.extension),
                },
                "command": {
                    "mode": "json",
                    "no_session": True,
                    "no_context_files": True,
                    "offline": True,
                    "toolathlon_system_prompt_mode": "append_to_pi_native_system_prompt",
                    "toolathlon_system_prompt_sha256": canonical_json_sha256(
                        prompt["system"]
                    ),
                    "workspace_namespace": {
                        "mode": "docker_sidecar_allowlist",
                        "image": TASK_IMAGE,
                        "container_id": container_id,
                        "root_filesystem_read_only": True,
                        "linux_capabilities": [],
                        "no_new_privileges": True,
                        "docker_socket_exposed": False,
                        "host_home_exposed": False,
                        "host_tmp_exposed": False,
                        "workspace_host_source": str(workspace),
                        "workspace_mount_mode": "read_write",
                        "runtime_mount_mode": "read_only",
                        "product_cwd": CONTAINER_WORKSPACE,
                        "network_mode": "host_for_loopback_gateway_and_proxy",
                        "cleanup_status": cleanup_status,
                        "product_pid_source": (
                            "docker_inspect_state_pid"
                            if product_pid is not None
                            else "not_observed"
                        ),
                    },
                    "adapter_retry_count": 0,
                    "task_tool_exposure": {
                        "mcp_tool_count": len(task_mcp_tool_names),
                        "mcp_tool_names_sha256": canonical_json_sha256(
                            task_mcp_tool_names
                        ),
                        "pi_builtin_tools_retained": True,
                    },
                },
            },
        )
