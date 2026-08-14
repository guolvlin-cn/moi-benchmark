from __future__ import annotations

import json
import hashlib
import os
import queue
import secrets
import shutil
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from .adapter_common import AdapterOutcome, EphemeralState, strip_provider_credentials
from .contract import ContractError, read_json_object, sha256_file, write_json_atomic
from .permissions import PermissionPolicy
from .process_control import terminate_process_group
from .model_proxy import wait_for_model_requests_to_settle


HERMES_COMMIT = "f4df260f26c93f15694698869f3ea8e965eea301"
HERMES_TREE = "40f0136a9995a9a1712a3ab28c231a2812748cdf"
_TERMINAL_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled"})
_POST_TERMINAL_MODEL_DRAIN_SECONDS = 120.0
_POST_TERMINAL_MODEL_QUIET_SECONDS = 1.0


@dataclass(frozen=True)
class HermesRuntime:
    command: tuple[str, ...]
    source_dir: Path
    environment_manifest: Path
    gateway_startup_timeout_seconds: int

    @classmethod
    def load(cls, path: Path) -> "HermesRuntime":
        raw = read_json_object(path)
        try:
            command = raw["command"]
            if not isinstance(command, list) or not all(
                isinstance(item, str) and item for item in command
            ):
                raise TypeError("command")
            result = cls(
                command=tuple(command),
                source_dir=Path(str(raw["source_dir"])).resolve(),
                environment_manifest=Path(
                    str(raw["environment_manifest"])
                ).resolve(),
                gateway_startup_timeout_seconds=int(
                    raw.get("gateway_startup_timeout_seconds", 300)
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"invalid Hermes runtime config {path}") from exc
        if raw.get("source_commit") != HERMES_COMMIT:
            raise ContractError("Hermes runtime source commit is not frozen")
        if raw.get("source_tree") != HERMES_TREE:
            raise ContractError("Hermes runtime source tree is not frozen")
        if not result.source_dir.is_dir():
            raise ContractError(f"Hermes source directory is unavailable: {result.source_dir}")
        executable = result.command[0]
        if os.path.isabs(executable):
            available = Path(executable).is_file() and os.access(executable, os.X_OK)
        else:
            available = shutil.which(executable) is not None
        if not available:
            raise ContractError(f"Hermes command is unavailable: {executable}")
        executable_path = (
            Path(executable).resolve()
            if os.path.isabs(executable)
            else Path(str(shutil.which(executable))).resolve()
        )
        if sha256_file(executable_path) != raw.get("executable_sha256"):
            raise ContractError("Hermes executable digest is not frozen")
        if not result.environment_manifest.is_file():
            raise ContractError("Hermes environment manifest is unavailable")
        if sha256_file(result.environment_manifest) != raw.get(
            "environment_manifest_sha256"
        ):
            raise ContractError("Hermes environment manifest digest is not frozen")
        if not 1 <= result.gateway_startup_timeout_seconds <= 1800:
            raise ContractError("invalid Hermes Gateway startup timeout")
        return result


def _request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            value = json.loads(raw) if raw else {}
            return response.status, value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            value = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            value = {}
        return exc.code, value if isinstance(value, dict) else {}


def _sse_events(response: Any) -> Iterator[dict[str, Any]]:
    data: list[str] = []
    while True:
        raw = response.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data:
                try:
                    value = json.loads("\n".join(data))
                except json.JSONDecodeError:
                    value = None
                if isinstance(value, dict):
                    yield value
            data = []
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())


def _event_reader(
    *,
    base_url: str,
    run_id: str,
    api_key: str,
    destination: "queue.Queue[dict[str, Any] | BaseException | None]",
) -> None:
    request = urllib.request.Request(
        f"{base_url}/v1/runs/{run_id}/events",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            for event in _sse_events(response):
                destination.put(event)
    except BaseException as exc:
        destination.put(exc)
    finally:
        destination.put(None)


def _wait_gateway(
    base_url: str,
    *,
    api_key: str,
    process: subprocess.Popen[bytes],
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Hermes Gateway exited during startup ({process.returncode})")
        try:
            status, value = _request_json(
                "GET", f"{base_url}/health", api_key=api_key, timeout=2
            )
            if status == 200 and value.get("status") == "ok":
                return
        except (OSError, TimeoutError, urllib.error.URLError):
            pass
        time.sleep(0.2)
    raise TimeoutError("Hermes Gateway readiness timeout")


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_model_requests_to_settle(
    snapshot: Callable[[], dict[str, Any]],
    *,
    timeout_seconds: float = _POST_TERMINAL_MODEL_DRAIN_SECONDS,
    quiet_seconds: float = _POST_TERMINAL_MODEL_QUIET_SECONDS,
    poll_seconds: float = 0.05,
) -> dict[str, Any]:
    """Let Hermes' already-started post-turn auxiliary requests finish.

    Hermes may start an internal auto-title/background request immediately
    before publishing ``run.completed``. Destroying the Gateway at that point
    disconnects the proxy downstream and creates an artificial model failure.
    The quiet period closes the adjacent thread-start race.
    """
    return wait_for_model_requests_to_settle(
        snapshot,
        timeout_seconds=timeout_seconds,
        quiet_seconds=quiet_seconds,
        poll_seconds=poll_seconds,
        context="Hermes post-terminal",
    )


def run_hermes(
    *,
    runtime: HermesRuntime,
    public_bundle: dict[str, Any],
    gateway_url: str,
    workspace: Path,
    output_dir: Path,
    proxy_url: str,
    permission_policy: PermissionPolicy,
    deadline_seconds: int,
    budget_exceeded: Callable[[], bool],
    model_request_snapshot: Callable[[], dict[str, Any]],
    on_product_pid: Callable[[int], None] | None = None,
    on_agent_start: Callable[[], None] | None = None,
    ephemeral_root: Path | None = None,
) -> AdapterOutcome:
    gateway_log_path = output_dir / "container.log"
    policy_evidence_path = output_dir / "hermes-policy-guard.jsonl"
    port = _free_port()
    api_base = f"http://127.0.0.1:{port}"
    api_key = secrets.token_urlsafe(32)
    session_id = f"toolathlon-{secrets.token_hex(16)}"
    prompt = public_bundle["prompt"]
    native_events: list[dict[str, Any]] = []
    gateway: subprocess.Popen[bytes] | None = None
    product_started = time.monotonic()
    agent_started: float | None = None
    agent_finished: float | None = None
    trigger_reason = "product_exit"
    terminal_event: dict[str, Any] | None = None
    final_status: dict[str, Any] = {}
    escalated = False
    post_terminal_model_drain: dict[str, Any] = {
        "settled": False,
        "missing_reason": "agent_terminal_event_not_observed",
    }

    policy_guard = Path(__file__).with_name("policy_guard") / "sitecustomize.py"
    policy_guard_hash = sha256_file(policy_guard)

    with EphemeralState(prefix="toolathlon-hermes-", preferred_root=ephemeral_root) as state:
        home = state.path / "home"
        home.mkdir(mode=0o700)
        config = {
            "model": {"default": "deepseek-v4-flash", "provider": "deepseek"},
            "memory": {"provider": ""},
            "approvals": {"mode": "smart"},
            "hooks": False,
            "hooks_auto_accept": False,
            "terminal": {"backend": "local", "cwd": str(workspace)},
            "mcp_servers": {
                "toolathlon": {
                    "url": gateway_url,
                    "transport": "sse",
                }
            },
            "mcp": {"auto_reload_on_config_change": False},
        }
        # JSON is valid YAML and avoids a runtime dependency in the Adapter.
        write_json_atomic(home / "config.yaml", config, mode=0o600)

        env = dict(os.environ)
        strip_provider_credentials(env)
        python_path = str(policy_guard.parent)
        if str(runtime.source_dir) not in python_path.split(os.pathsep):
            python_path += os.pathsep + str(runtime.source_dir)
        existing_python_path = env.get("PYTHONPATH")
        if existing_python_path:
            python_path += os.pathsep + existing_python_path
        env.update(
            {
                "HERMES_HOME": str(home),
                "HERMES_YOLO_MODE": "0",
                "HERMES_ACCEPT_HOOKS": "0",
                "HERMES_EXEC_ASK": "1",
                "API_SERVER_ENABLED": "true",
                "API_SERVER_HOST": "127.0.0.1",
                "API_SERVER_PORT": str(port),
                "API_SERVER_KEY": api_key,
                "HERMES_GATEWAY_NO_SUPERVISE": "1",
                "DEEPSEEK_API_KEY": "toolathlon-run-proxy",
                "DEEPSEEK_BASE_URL": proxy_url,
                "TERMINAL_CWD": str(workspace),
                "TERMINAL_ENV": "local",
                "PYTHONPATH": python_path,
                "TOOLATHLON_POLICY_GUARD_SHA256": policy_guard_hash,
                "TOOLATHLON_POLICY_GUARD_EVIDENCE": str(policy_evidence_path),
            }
        )
        argv = [
            *runtime.command,
            "gateway",
            "run",
            "--no-supervise",
            "--external-supervisor",
        ]
        gateway_log_path.parent.mkdir(parents=True, exist_ok=True)
        with gateway_log_path.open("wb") as gateway_log:
            gateway = subprocess.Popen(
                argv,
                cwd=workspace,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=gateway_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            if on_product_pid is not None:
                on_product_pid(gateway.pid)
            try:
                _wait_gateway(
                    api_base,
                    api_key=api_key,
                    process=gateway,
                    timeout_seconds=runtime.gateway_startup_timeout_seconds,
                )
                setup_model_requests = int(
                    model_request_snapshot().get("provider_requests_forwarded", -1)
                )
                if setup_model_requests != 0:
                    raise ContractError(
                        "Hermes forwarded a model request before Agent execution"
                    )
                status, response = _request_json(
                    "POST",
                    f"{api_base}/v1/runs",
                    api_key=api_key,
                    body={
                        "input": prompt["task"],
                        "instructions": prompt["system"],
                        "model": "deepseek-v4-flash",
                        "session_id": session_id,
                    },
                    timeout=30,
                )
                run_id = response.get("run_id")
                if status != 202 or not isinstance(run_id, str):
                    raise RuntimeError(f"Hermes run submission failed (HTTP {status})")
                agent_started = time.monotonic()
                deadline_monotonic = agent_started + deadline_seconds
                if on_agent_start is not None:
                    on_agent_start()
                native_events.append(
                    {
                        "event": "run.submitted",
                        "run_id": run_id,
                        "session_id": session_id,
                        "timestamp": time.time(),
                    }
                )
                event_queue: "queue.Queue[dict[str, Any] | BaseException | None]" = queue.Queue()
                reader = threading.Thread(
                    target=_event_reader,
                    kwargs={
                        "base_url": api_base,
                        "run_id": run_id,
                        "api_key": api_key,
                        "destination": event_queue,
                    },
                    daemon=True,
                    name="hermes-run-events",
                )
                reader.start()
                stop_requested = False
                stream_closed = False
                while terminal_event is None:
                    if gateway.poll() is not None:
                        raise RuntimeError(
                            f"Hermes Gateway exited during run ({gateway.returncode})"
                        )
                    if not stop_requested and budget_exceeded():
                        trigger_reason = "max_model_requests"
                        stop_requested = True
                    if not stop_requested and time.monotonic() >= deadline_monotonic:
                        trigger_reason = "agent_deadline"
                        stop_requested = True
                    if stop_requested:
                        _request_json(
                            "POST",
                            f"{api_base}/v1/runs/{run_id}/stop",
                            api_key=api_key,
                            body={},
                            timeout=5,
                        )
                        stop_deadline = time.monotonic() + 10
                        stop_requested = False
                        # Do not repeatedly send /stop; force process cleanup if
                        # no terminal event arrives during the grace window.
                        while terminal_event is None and time.monotonic() < stop_deadline:
                            try:
                                item = event_queue.get(timeout=0.2)
                            except queue.Empty:
                                continue
                            if isinstance(item, BaseException):
                                raise item
                            if item is None:
                                stream_closed = True
                                break
                            native_events.append(item)
                            if _event_name(item) in _TERMINAL_EVENTS:
                                terminal_event = item
                        break
                    try:
                        item = event_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if isinstance(item, BaseException):
                        raise item
                    if item is None:
                        stream_closed = True
                        break
                    native_events.append(item)
                    event_name = _event_name(item)
                    if event_name == "approval.request":
                        decision = permission_policy.decide_hermes_approval(item)
                        approval_status, _ = _request_json(
                            "POST",
                            f"{api_base}/v1/runs/{run_id}/approval",
                            api_key=api_key,
                            body={"choice": decision.choice},
                            timeout=10,
                        )
                        native_events.append(
                            {
                                "event": "adapter.approval_decision",
                                "run_id": run_id,
                                "choice": decision.choice,
                                "reason": decision.reason,
                                "http_status": approval_status,
                                "timestamp": time.time(),
                            }
                        )
                    if event_name in _TERMINAL_EVENTS:
                        terminal_event = item
                if terminal_event is None and trigger_reason == "product_exit":
                    if stream_closed:
                        status_code, final_status = _request_json(
                            "GET",
                            f"{api_base}/v1/runs/{run_id}",
                            api_key=api_key,
                            timeout=10,
                        )
                        if status_code != 200 or final_status.get("status") not in {
                            "completed",
                            "failed",
                            "cancelled",
                        }:
                            raise RuntimeError("Hermes event stream closed without terminal status")
                    else:
                        raise RuntimeError("Hermes run ended without a terminal event")
                if not final_status:
                    status_code, final_status = _request_json(
                        "GET",
                        f"{api_base}/v1/runs/{run_id}",
                        api_key=api_key,
                        timeout=10,
                    )
                    if status_code != 200:
                        final_status = {}
                agent_finished = time.monotonic()
            finally:
                if gateway.poll() is None:
                    try:
                        if terminal_event is not None:
                            post_terminal_model_drain = _wait_for_model_requests_to_settle(
                                model_request_snapshot
                            )
                    finally:
                        escalated = terminate_process_group(gateway, grace_seconds=10)

        if trigger_reason == "product_exit" and budget_exceeded():
            trigger_reason = "max_model_requests"
        if trigger_reason == "agent_deadline":
            terminal_status = "timeout"
        elif trigger_reason == "max_model_requests":
            terminal_status = "max_steps"
        else:
            native_status = final_status.get("status")
            terminal_status = {
                "completed": "completed",
                "failed": "failed",
                "cancelled": "interrupted",
            }.get(str(native_status), "crashed")
        output = final_status.get("output")
        error = final_status.get("error")
        return AdapterOutcome(
            terminal_status=terminal_status,
            product_exit_code=gateway.returncode if gateway is not None else None,
            termination_reason=trigger_reason,
            output=output if isinstance(output, str) else "",
            error=str(error) if error else None,
            duration_seconds=(
                agent_finished if agent_finished is not None else time.monotonic()
            )
            - (agent_started if agent_started is not None else product_started),
            product_pid=gateway.pid if gateway is not None else None,
            escalated_to_sigkill=escalated,
            native_events=native_events,
            metadata={
                "ephemeral_state_on_tmpfs": state.on_tmpfs,
                "setup_provider_requests_before_agent": setup_model_requests,
                "post_terminal_model_drain": post_terminal_model_drain,
                "product_identity": {
                    "strategy": "hermes_ephemeral_runtime_session",
                    "attempt_session_id_sha256": hashlib.sha256(
                        session_id.encode("utf-8")
                    ).hexdigest(),
                    "fresh_hermes_home": True,
                    "fresh_gateway_process": True,
                    "fresh_gateway_api_key": True,
                    "memory_provider": "",
                    "true_server_user_identity": False,
                    "provider_user_id_is_product_identity": False,
                },
                "model": {
                    "provider": "deepseek",
                    "requested": "deepseek-v4-flash",
                    "base_url": proxy_url,
                },
                "command": {
                    "argv": ["<hermes>", "gateway", "run", "--no-supervise", "--external-supervisor"],
                    "max_turns_source": "hermes_internal_default",
                    "api_max_retries_source": "hermes_internal_default",
                    "adapter_retry_count": 0,
                },
                "permission": {
                    "mode": "smart",
                    "yolo": False,
                    "accept_hooks": False,
                    "policy_guard_sha256": policy_guard_hash,
                },
            },
        )


def _event_name(event: dict[str, Any]) -> str:
    return str(event.get("event") or event.get("type") or "").lower()
