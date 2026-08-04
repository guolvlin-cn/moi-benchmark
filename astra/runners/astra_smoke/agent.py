from __future__ import annotations

import asyncio
import hashlib
import math
import shlex
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from astra.runners.astra_smoke.core import (
    CLEAN,
    ControllerConfig,
    ControllerError,
    FaultController,
    JsonlLedger,
    astra_args,
    lifecycle_gate_passes,
    normalize_linux_arch,
    parse_astra_json,
    probe_run_command,
    validate_condition,
    validate_linux_elf,
    write_minimal_credentials,
)


REMOTE_BINARY = "/installed-agent/astra"
REMOTE_PROBE = "/installed-agent/astra-smoke-probe.py"
HANDSHAKE_PROMPT = "Reply with exactly READY. Do not call tools."
RECOVERY_PROMPT = (
    "Continue the original task in this same session. "
    "Inspect the existing workspace and its task-owned recovery checkpoint "
    "before acting."
)
RECOVERY_PENDING_JSON = (
    '{"attempt":1,"expected_result":"astra-lifecycle-smoke:complete",'
    '"resume_command":"/usr/local/bin/astra-smoke-workload",'
    '"status":"resume-required"}\n'
)
RECOVERY_COMPLETE_JSON = (
    '{"attempt":2,"expected_result":"astra-lifecycle-smoke:complete",'
    '"resume_command":"/usr/local/bin/astra-smoke-workload",'
    '"status":"complete"}\n'
)
TERMINAL_RESULT = "astra-lifecycle-smoke:complete\n"
RECOVERY_PENDING_SHA256 = hashlib.sha256(
    RECOVERY_PENDING_JSON.encode("utf-8")
).hexdigest()
RECOVERY_COMPLETE_SHA256 = hashlib.sha256(
    RECOVERY_COMPLETE_JSON.encode("utf-8")
).hexdigest()
TERMINAL_RESULT_SHA256 = hashlib.sha256(
    TERMINAL_RESULT.encode("utf-8")
).hexdigest()


class AstraSmokeAgent(BaseInstalledAgent):
    """Harbor 0.20 execution-plane smoke agent for C0/F1 lifecycle checks."""

    def __init__(
        self,
        logs_dir: Path,
        model_name: Optional[str] = None,
        linux_binary_path: Optional[str] = None,
        condition: str = CLEAN,
        trigger_path: str = "/tmp/astra-smoke/trigger",
        recovery_checkpoint_path: str = "/app/recovery.json",
        terminal_artifact_path: str = "/app/result.txt",
        trigger_timeout_sec: float = 60.0,
        poll_interval_sec: float = 0.2,
        max_turns: int = 20,
        turn_timeout_sec: int = 900,
        *args,
        **kwargs,
    ):
        super().__init__(logs_dir=logs_dir, model_name=model_name, *args, **kwargs)
        self._access_token = self._get_env("ASTRA_ACCESS_TOKEN")
        self._extra_env.pop("ASTRA_ACCESS_TOKEN", None)
        self.condition = validate_condition(condition)
        self.linux_binary_path = linux_binary_path
        self.trigger_path = trigger_path
        self.recovery_checkpoint_path = recovery_checkpoint_path
        self.terminal_artifact_path = terminal_artifact_path
        self.trigger_timeout_sec = float(trigger_timeout_sec)
        self.poll_interval_sec = float(poll_interval_sec)
        self.max_turns = int(max_turns)
        self.turn_timeout_sec = int(turn_timeout_sec)
        self.astra_model_name = model_name or self._get_env("ASTRA_SMOKE_MODEL")
        self._artifact_arch: Optional[str] = None
        self._artifact_sha256: Optional[str] = None
        if not trigger_path.startswith("/tmp/astra-smoke/"):
            raise ValueError("smoke trigger_path must stay below /tmp/astra-smoke/")
        for name, value in (
            ("recovery_checkpoint_path", recovery_checkpoint_path),
            ("terminal_artifact_path", terminal_artifact_path),
        ):
            if not value.startswith("/app/") or "\n" in value or "\x00" in value:
                raise ValueError(f"{name} must be a safe path below /app/")
        if self.max_turns <= 0 or self.turn_timeout_sec <= 0:
            raise ValueError("max_turns and turn_timeout_sec must be positive")

    @staticmethod
    def name() -> str:
        return "astra-smoke"

    def get_version_command(self) -> str:
        return f"{REMOTE_BINARY} --version"

    async def install(self, environment: BaseEnvironment) -> None:
        source_value = self.linux_binary_path or self._get_env(
            "ASTRA_SMOKE_LINUX_BINARY"
        )
        if not source_value:
            raise ValueError(
                "set linux_binary_path or ASTRA_SMOKE_LINUX_BINARY to a Linux Astra ELF"
            )
        source = Path(source_value).expanduser().resolve()
        artifact_arch = validate_linux_elf(source)
        api_url = self._get_env("ASTRA_API_URL")
        parsed_api_url = urlparse(api_url or "")
        if (
            parsed_api_url.scheme not in {"http", "https"}
            or parsed_api_url.hostname != "host.docker.internal"
        ):
            raise ValueError(
                "local Docker smoke requires ASTRA_API_URL with host "
                "host.docker.internal (for example http://host.docker.internal:17001)"
            )
        if not self._access_token:
            raise ValueError("ASTRA_ACCESS_TOKEN must be supplied through Harbor agent env")
        if not self.astra_model_name:
            raise ValueError(
                "set model_name or ASTRA_SMOKE_MODEL to an Astra model ID"
            )

        arch_result = await environment.exec(command="uname -m", timeout_sec=10)
        if arch_result.return_code != 0:
            raise RuntimeError("could not determine the Harbor task container architecture")
        container_arch = normalize_linux_arch(arch_result.stdout or "")
        if artifact_arch != container_arch:
            raise ValueError(
                f"Astra artifact architecture {artifact_arch} does not match "
                f"task container architecture {container_arch}"
            )

        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        self._artifact_arch = artifact_arch
        self._artifact_sha256 = digest.hexdigest()

        python_result = await environment.exec(command="command -v python3", timeout_sec=10)
        if python_result.return_code != 0:
            await self.exec_as_root(
                environment,
                (
                    "if command -v apt-get >/dev/null 2>&1; then "
                    "DEBIAN_FRONTEND=noninteractive apt-get update && "
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y python3; "
                    "elif command -v apk >/dev/null 2>&1; then apk add --no-cache python3; "
                    "elif command -v dnf >/dev/null 2>&1; then dnf install -y python3; "
                    "elif command -v yum >/dev/null 2>&1; then yum install -y python3; "
                    "else echo 'no supported package manager for python3' >&2; exit 127; fi"
                ),
                timeout_sec=300,
            )

        await environment.upload_file(source, REMOTE_BINARY)
        await environment.upload_file(Path(__file__).with_name("probe.py"), REMOTE_PROBE)
        await self.exec_as_root(
            environment,
            f"chmod 0555 {shlex.quote(REMOTE_BINARY)} {shlex.quote(REMOTE_PROBE)}",
        )
        await self.exec_as_agent(environment, "python3 --version")

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        run_id = str(uuid.uuid4())
        ledger = JsonlLedger(self.logs_dir / "controller.jsonl", run_id)
        remote_root = f"/tmp/astra-smoke/run-{run_id}"
        await self._prepare_remote(environment, remote_root)
        ledger.append(
            "controller_started",
            condition=self.condition,
            fault_scope="astra_cli_process_tree",
            trigger_kind="path_exists_smoke_only",
            artifact_arch=self._artifact_arch,
            artifact_sha256=self._artifact_sha256,
            astra_version=self.version(),
            model_name=self.astra_model_name,
            recovery_pending_sha256=RECOVERY_PENDING_SHA256,
            recovery_complete_sha256=RECOVERY_COMPLETE_SHA256,
            terminal_result_sha256=TERMINAL_RESULT_SHA256,
        )
        health_result = await environment.exec(
            command=f"{REMOTE_BINARY} health",
            env=self._runtime_env(remote_root),
            timeout_sec=30,
        )
        ledger.append(
            "api_preflight_completed",
            reachable=health_result.return_code == 0,
            return_code=health_result.return_code,
        )
        if health_result.return_code != 0:
            raise ControllerError(
                "Astra API is not reachable from the Harbor task container"
            )
        auth_result = await environment.exec(
            command=f"{REMOTE_BINARY} whoami",
            env=self._runtime_env(remote_root),
            timeout_sec=30,
        )
        ledger.append(
            "auth_preflight_completed",
            authenticated=auth_result.return_code == 0,
            return_code=auth_result.return_code,
        )
        if auth_result.return_code != 0:
            raise ControllerError(
                "Astra credentials are not accepted in the Harbor task container"
            )

        handshake = await self._turn(
            environment,
            ledger,
            remote_root,
            "handshake",
            HANDSHAKE_PROMPT,
            session_id=None,
            permission_mode="deny",
            max_turns=1,
        )
        if (
            handshake.get("success") is not True
            or str(handshake.get("text", "")).strip() != "READY"
            or handshake.get("tool_calls_count") != 0
        ):
            raise ControllerError(
                "handshake must succeed with exact READY and tool_calls_count=0"
            )
        session_id = handshake["session_id"]
        ledger.append(
            "handshake_completed",
            session_id=session_id,
            tool_calls_count=0,
        )

        task_paths = self._remote_turn_paths(remote_root, "task")
        await self._upload_prompt(environment, instruction, task_paths["stdin"], "task")
        turn_done = asyncio.Event()
        controller = FaultController(
            ControllerConfig(
                condition=self.condition,
                trigger_path=self.trigger_path,
                identity_path=task_paths["identity"],
                probe_path=REMOTE_PROBE,
                expected_exe=REMOTE_BINARY,
                trigger_timeout_sec=self.trigger_timeout_sec,
                poll_interval_sec=self.poll_interval_sec,
            ),
            ledger.append,
        )
        ledger.append("task_turn_started", session_id=session_id)
        task_deadline = asyncio.get_running_loop().time() + self.turn_timeout_sec

        async def execute_task():
            try:
                return await environment.exec(
                    command=self._turn_command(
                        task_paths,
                        session_id=session_id,
                        permission_mode="bypass",
                        max_turns=self.max_turns,
                    ),
                    cwd="/app",
                    env=self._runtime_env(remote_root),
                    timeout_sec=self._remaining_timeout(task_deadline),
                )
            finally:
                turn_done.set()

        async with asyncio.TaskGroup() as group:
            task_exec = group.create_task(execute_task())
            controller_exec = group.create_task(controller.run(environment, turn_done))
        task_result = task_exec.result()
        fault = controller_exec.result()
        await self._collect_turn(environment, task_paths, "task")
        ledger.append(
            "task_turn_exited",
            return_code=task_result.return_code,
            trigger_hit=fault.trigger_hit,
            fault_injected=fault.fault_injected,
        )
        if fault.fault_injected:
            await self._assert_post_fault_workspace_state(environment, ledger)

        lifecycle_ok = lifecycle_gate_passes(
            self.condition,
            trigger_hit=fault.trigger_hit,
            fault_injected=fault.fault_injected,
            turn_return_code=task_result.return_code,
        )
        metadata = {
            "astra_session_id": session_id,
            "condition": self.condition,
            "trigger_hit": fault.trigger_hit,
            "fault_injected": fault.fault_injected,
            "fault_scope": "astra_cli_process_tree",
            "lifecycle_gate_passed": lifecycle_ok,
            "controller_ledger": str(self.logs_dir / "controller.jsonl"),
        }
        context.metadata = metadata
        if not lifecycle_ok:
            ledger.append(
                "controller_completed",
                session_id=session_id,
                trigger_hit=fault.trigger_hit,
                fault_injected=fault.fault_injected,
                lifecycle_gate_passed=False,
                astra_turn_success=False,
            )
            raise ControllerError(
                f"Astra smoke lifecycle gate failed ({fault.reason}, "
                f"return_code={task_result.return_code})"
            )

        final = None
        if fault.fault_injected:
            ledger.append(
                "same_session_relaunch_started",
                session_id=session_id,
                recovery_kind="explicit_cli_relaunch",
            )
            final = await self._turn(
                environment,
                ledger,
                remote_root,
                "relaunch",
                RECOVERY_PROMPT,
                session_id=session_id,
                permission_mode="bypass",
                max_turns=self.max_turns,
                timeout_sec=self._remaining_timeout(task_deadline),
            )
            tool_calls_count = final.get("tool_calls_count")
            if type(tool_calls_count) is not int or tool_calls_count <= 0:
                raise ControllerError(
                    "same-session relaunch did not perform a recovery tool action"
                )
            await self._assert_post_relaunch_workspace_state(environment, ledger)
            ledger.append(
                "same_session_relaunch_completed",
                session_id=session_id,
                success=final.get("success") is True,
                tool_calls_count=tool_calls_count,
            )
        elif task_result.return_code == 0:
            final = parse_astra_json(
                (self.logs_dir / "task.stdout").read_text(encoding="utf-8"),
                expected_session_id=session_id,
            )

        success = final is not None and final.get("success") is True
        ledger.append(
            "controller_completed",
            session_id=session_id,
            trigger_hit=fault.trigger_hit,
            fault_injected=fault.fault_injected,
            lifecycle_gate_passed=True,
            astra_turn_success=success,
        )
        if not success:
            raise RuntimeError(
                f"Astra smoke turn did not finish successfully ({fault.reason})"
            )

    async def _prepare_remote(
        self, environment: BaseEnvironment, remote_root: str
    ) -> None:
        command = (
            f"mkdir -p {shlex.quote(remote_root)} "
            f"{shlex.quote(remote_root + '/home')} "
            f"{shlex.quote(remote_root + '/credentials')} /tmp/astra-smoke && "
            f"chmod 0700 {shlex.quote(remote_root)} "
            f"{shlex.quote(remote_root + '/home')} "
            f"{shlex.quote(remote_root + '/credentials')} && "
            f"rm -f -- {shlex.quote(self.trigger_path)}"
        )
        result = await environment.exec(command=command, timeout_sec=10)
        if result.return_code != 0:
            raise RuntimeError("could not prepare the isolated smoke control directory")
        remote_credentials = f"{remote_root}/credentials/credentials.json"
        with tempfile.TemporaryDirectory(prefix="astra-smoke-credentials-") as directory:
            local_credentials = Path(directory) / "credentials.json"
            write_minimal_credentials(local_credentials, self._access_token or "")
            await environment.upload_file(local_credentials, remote_credentials)
        credentials_result = await environment.exec(
            command=f"chmod 0600 {shlex.quote(remote_credentials)}",
            timeout_sec=10,
        )
        if credentials_result.return_code != 0:
            raise RuntimeError("could not protect the isolated Astra credential profile")

    async def _remote_sha256(
        self, environment: BaseEnvironment, path: str
    ) -> tuple[bool, Optional[str], int]:
        result = await environment.exec(
            command=f"sha256sum -- {shlex.quote(path)}",
            timeout_sec=10,
        )
        digest = None
        if result.return_code == 0 and result.stdout:
            candidate = result.stdout.split()[0].lower()
            if len(candidate) == 64 and all(
                character in "0123456789abcdef" for character in candidate
            ):
                digest = candidate
        return digest is not None, digest, result.return_code

    async def _assert_post_fault_workspace_state(
        self, environment: BaseEnvironment, ledger: JsonlLedger
    ) -> None:
        present, digest, return_code = await self._remote_sha256(
            environment, self.recovery_checkpoint_path
        )
        checkpoint_matches = present and digest == RECOVERY_PENDING_SHA256
        ledger.append(
            "workspace_checkpoint_post_fault_probe",
            present=present,
            sha256=digest,
            matches_expected=checkpoint_matches,
            return_code=return_code,
        )
        artifact_probe = await environment.exec(
            command=f"test ! -e {shlex.quote(self.terminal_artifact_path)}",
            timeout_sec=10,
        )
        artifact_absent = artifact_probe.return_code == 0
        ledger.append(
            "terminal_artifact_post_fault_probe",
            absent=artifact_absent,
            return_code=artifact_probe.return_code,
        )
        if not checkpoint_matches or not artifact_absent:
            raise ControllerError(
                "post-fault workspace is not at the registered recovery boundary"
            )

    async def _assert_post_relaunch_workspace_state(
        self, environment: BaseEnvironment, ledger: JsonlLedger
    ) -> None:
        checkpoint_present, checkpoint_digest, checkpoint_return_code = (
            await self._remote_sha256(environment, self.recovery_checkpoint_path)
        )
        checkpoint_matches = (
            checkpoint_present
            and checkpoint_digest == RECOVERY_COMPLETE_SHA256
        )
        ledger.append(
            "workspace_checkpoint_post_relaunch_probe",
            present=checkpoint_present,
            sha256=checkpoint_digest,
            matches_expected=checkpoint_matches,
            return_code=checkpoint_return_code,
        )
        result_present, result_digest, result_return_code = await self._remote_sha256(
            environment, self.terminal_artifact_path
        )
        result_matches = result_present and result_digest == TERMINAL_RESULT_SHA256
        ledger.append(
            "terminal_artifact_post_relaunch_probe",
            present=result_present,
            sha256=result_digest,
            matches_expected=result_matches,
            return_code=result_return_code,
        )
        if not checkpoint_matches or not result_matches:
            raise ControllerError(
                "same-session relaunch did not complete the registered recovery state"
            )

    @staticmethod
    def _runtime_env(remote_root: str) -> dict[str, str]:
        return {
            "HOME": f"{remote_root}/home",
            "ASTRA_CLI_CREDENTIALS_DIR": f"{remote_root}/credentials",
        }

    @staticmethod
    def _remaining_timeout(deadline: float) -> int:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("Astra smoke task lifecycle deadline expired")
        return max(1, math.ceil(remaining))

    def _remote_turn_paths(self, root: str, phase: str) -> dict[str, str]:
        return {
            "identity": f"{root}/{phase}.identity.json",
            "stdout": f"{root}/{phase}.stdout",
            "stderr": f"{root}/{phase}.stderr",
            "stdin": f"{root}/{phase}.prompt",
        }

    async def _upload_prompt(
        self,
        environment: BaseEnvironment,
        prompt: str,
        remote_path: str,
        phase: str,
    ) -> None:
        local_path = self.logs_dir / f"{phase}.prompt"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(prompt, encoding="utf-8")
        await environment.upload_file(local_path, remote_path)

    def _turn_command(
        self,
        paths: dict[str, str],
        *,
        session_id: Optional[str],
        permission_mode: str,
        max_turns: int,
    ) -> str:
        return probe_run_command(
            probe_path=REMOTE_PROBE,
            identity_path=paths["identity"],
            stdout_path=paths["stdout"],
            stderr_path=paths["stderr"],
            stdin_path=paths["stdin"],
            cwd="/app",
            child_argv=astra_args(
                remote_binary=REMOTE_BINARY,
                model_name=self.astra_model_name,
                max_turns=max_turns,
                session_id=session_id,
                permission_mode=permission_mode,
            ),
        )

    async def _collect_turn(
        self,
        environment: BaseEnvironment,
        paths: dict[str, str],
        phase: str,
    ) -> None:
        await environment.download_file(paths["stdout"], self.logs_dir / f"{phase}.stdout")
        await environment.download_file(paths["stderr"], self.logs_dir / f"{phase}.stderr")
        await environment.download_file(
            paths["identity"], self.logs_dir / f"{phase}.identity.json"
        )

    async def _turn(
        self,
        environment: BaseEnvironment,
        ledger: JsonlLedger,
        remote_root: str,
        phase: str,
        prompt: str,
        *,
        session_id: Optional[str],
        permission_mode: str,
        max_turns: int,
        timeout_sec: Optional[int] = None,
    ) -> dict:
        paths = self._remote_turn_paths(remote_root, phase)
        await self._upload_prompt(environment, prompt, paths["stdin"], phase)
        ledger.append(f"{phase}_turn_started", session_id=session_id)
        result = await environment.exec(
            command=self._turn_command(
                paths,
                session_id=session_id,
                permission_mode=permission_mode,
                max_turns=max_turns,
            ),
            cwd="/app",
            env=self._runtime_env(remote_root),
            timeout_sec=timeout_sec or self.turn_timeout_sec,
        )
        await self._collect_turn(environment, paths, phase)
        if result.return_code != 0:
            raise RuntimeError(f"{phase} Astra process exited {result.return_code}")
        value = parse_astra_json(
            (self.logs_dir / f"{phase}.stdout").read_text(encoding="utf-8"),
            expected_session_id=session_id,
        )
        ledger.append(
            f"{phase}_turn_exited",
            return_code=result.return_code,
            success=value.get("success") is True,
            tool_calls_count=value.get("tool_calls_count"),
        )
        return value
