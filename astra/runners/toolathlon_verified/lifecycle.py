from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .artifact_contract import ARTIFACT_SCHEMA_VERSION, validate_run_artifacts
from .contract import (
    ContractError,
    JsonlEventWriter,
    read_json_object,
    sha256_file,
    utc_now,
    write_json_atomic,
    write_sha256_manifest,
)
from .orchestrator import run as run_product_slot
from .resources import ResourceSampler


TASK_IMAGE = (
    "docker.io/lockon0927/toolathlon-task-image@"
    "sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f"
)
SOURCE_COMMIT = "2aed2468858f15818acafa178518390cc4b0f5cb"
QUALIFICATION_TASK = "find-alita-paper"
PROJECT_COPY_PATHS = (
    "configs",
    "deployment/k8s",
    "scripts",
    "deployment/canvas/logs",
    "global_preparation/check_installation.py",
    "local_binary/github-mcp-server",
    "utils",
    "main.py",
)
MCP_AUTH_PREFIX = "configs/.mcp-auth/"


class LifecycleError(RuntimeError):
    pass


def _safe_id(value: str, label: str) -> str:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value):
        raise LifecycleError(f"{label} is not a safe identifier")
    return value


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_ready(url: str, *, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not_attempted"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                payload = json.loads(response.read())
                if response.status == 200 and isinstance(payload, dict):
                    return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1)
    raise LifecycleError(f"Gateway readiness timeout: {last_error}")


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int,
    log_path: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LifecycleError(f"command failed to execute: {command[0]}: {exc}") from exc
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_bytes(result.stdout)
    if check and result.returncode != 0:
        detail = result.stdout.decode("utf-8", errors="replace")[-2000:]
        raise LifecycleError(
            f"command exited with {result.returncode}: {command[0]}: {detail}"
        )
    return result


def load_task_reset_contract(
    *, task_id: str, task_source: Path, requirements_path: Path
) -> dict[str, Any]:
    """Resolve the frozen task inputs used by the per-attempt reset boundary."""
    requirements = read_json_object(requirements_path)
    task = requirements.get("tasks", {}).get(task_id)
    if not isinstance(task, dict):
        raise LifecycleError(f"task requirements are missing for {task_id}")
    task_config = task_source / "task_config.json"
    if not task_config.is_file():
        raise LifecycleError(f"task config is unavailable: {task_config}")
    expected_sha256 = task.get("task_config_sha256")
    if not isinstance(expected_sha256, str) or sha256_file(task_config) != expected_sha256:
        raise LifecycleError(f"task config does not match the freeze: {task_id}")
    servers = task.get("mcp_servers")
    if not isinstance(servers, list) or any(
        not isinstance(server, str) or not server for server in servers
    ):
        raise LifecycleError(f"task MCP requirements are invalid: {task_id}")
    return {
        "task_config_sha256": expected_sha256,
        "required_mcp_servers": list(servers),
        "task_preprocess_present": (task_source / "preprocess/main.py").is_file(),
    }


def is_runtime_mutable_credential_record(item: dict[str, Any]) -> bool:
    path = str(item.get("path", ""))
    return (
        item.get("runtime_mutable") is True
        and item.get("category") == "mcp_oauth"
        and item.get("content_policy") == "runtime_refreshable_oauth_token"
        and path.startswith(MCP_AUTH_PREFIX)
        and Path(path).name.endswith("_tokens.json")
    )


class SingleTaskLifecycle:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repo_root = Path(__file__).resolve().parents[3]
        self.source = args.toolathlon_source.resolve()
        self.output = args.output_dir.resolve()
        self.task_state = self.output / "task-state"
        self.task_source = self.source / "tasks/finalpool" / args.task_id
        self.freeze = self.repo_root / "astra/benchmark/toolathlon-verified/freeze"
        self.runtime_overlay = (
            self.repo_root
            / "astra/benchmark/toolathlon-verified/runtime/container_tool_gateway_m1.py"
        )
        self.container_name = _safe_id(
            f"toolathlon-{args.task_id}-{args.system}-{args.run_id}"[:180],
            "container_name",
        )
        self.docker = (["sudo"] if args.docker_via_sudo else []) + ["docker"]
        self.host_python = self.source / ".venv/bin/python"
        self.guard = (["sudo"] if args.docker_via_sudo else []) + [
            str(self.host_python),
            "-m",
            "scripts.containerized.task_artifact_guard",
        ]
        self.container_id: list[str | None] = [None]
        self.container_pid: list[int | None] = [None]
        self.product_pid: list[int | None] = [None]
        self.stash_dir: Path | None = None
        self.private_dir: Path | None = None
        self.trusted_bundle: Path | None = None
        self.eval_bundle_container = f"/run/toolathlon-eval-{args.run_id}.json"
        self.lifecycle: JsonlEventWriter | None = None
        self.task_reset_contract: dict[str, Any] | None = None
        self.mutable_credential_paths: list[str] = []
        self.mcp_auth_bind_mounted = False

    def docker_command(self, *args: str) -> list[str]:
        return [*self.docker, *args]

    def _docker(self, *args: str, timeout: int, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        return _run(self.docker_command(*args), timeout=timeout, check=check)

    def preflight(self) -> None:
        if not self.task_source.is_dir():
            raise LifecycleError(f"task source is unavailable: {self.task_source}")
        self.task_reset_contract = load_task_reset_contract(
            task_id=self.args.task_id,
            task_source=self.task_source,
            requirements_path=self.freeze / "task-requirements.json",
        )
        if not self.host_python.is_file():
            raise LifecycleError("Toolathlon frozen Python environment is unavailable")
        if not self.runtime_overlay.is_file():
            raise LifecycleError("benchmark Gateway overlay is unavailable")
        source_commit = _run(
            ["git", "-C", str(self.source), "rev-parse", "HEAD^{commit}"],
            timeout=30,
        ).stdout.decode().strip()
        if source_commit != SOURCE_COMMIT:
            raise LifecycleError("Toolathlon source commit does not match the freeze")
        image = self._docker("image", "inspect", TASK_IMAGE, timeout=60)
        if not image.stdout:
            raise LifecycleError("frozen task image is not available")
        required = (
            "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY",
            "TOOLATHLON_DEEPSEEK_HERMES_API_KEY",
        )
        if self.args.system == "astra":
            required += ("ASTRA_ADMIN_ACCESS_TOKEN",)
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise LifecycleError(f"required runtime credentials are absent: {missing}")
        if os.environ[required[0]] == os.environ[required[1]]:
            raise LifecycleError("Astra and Hermes DeepSeek keys must be distinct")
        self._verify_application_credential_fingerprints()
        if self.args.system == "astra":
            runtime = read_json_object(
                self.repo_root
                / "astra/work/toolathlon-verified/rendered-astra-runtime.json"
            )
            parsed = urlparse(str(runtime.get("api_url", "")))
            try:
                with socket.create_connection(
                    (str(parsed.hostname), int(parsed.port or 80)), timeout=3
                ):
                    pass
            except OSError as exc:
                raise LifecycleError(
                    "frozen shared Astra loopback API server is not listening"
                ) from exc

    def _verify_application_credential_fingerprints(self) -> None:
        manifest = read_json_object(self.freeze / "credential-manifest.json")
        records = manifest.get("toolathlon_application_credentials", {}).get("files")
        if not isinstance(records, list) or not records:
            raise LifecycleError("frozen application credential manifest is empty")
        mutable_paths: list[str] = []
        for item in records:
            if not isinstance(item, dict):
                raise LifecycleError("invalid application credential record")
            relative = Path(str(item.get("path", "")))
            if relative.is_absolute() or ".." in relative.parts:
                raise LifecycleError("unsafe application credential path")
            path = self.source / relative
            if not path.is_file() or path.is_symlink():
                raise LifecycleError(f"application credential fingerprint drift: {path}")
            if is_runtime_mutable_credential_record(item):
                mutable_paths.append(relative.as_posix())
            elif item.get("runtime_mutable") is True:
                raise LifecycleError(
                    f"credential has an invalid runtime-mutable policy: {relative}"
                )
            elif sha256_file(path) != item.get("sha256"):
                raise LifecycleError(f"application credential fingerprint drift: {path}")
        self.mutable_credential_paths = sorted(mutable_paths)
        runtime = manifest.get("runtime_product_and_model_credentials")
        if not isinstance(runtime, dict) or runtime.get("state") != "GO":
            raise LifecycleError(
                "runtime credential fingerprints are not frozen in credential-manifest.json"
            )
        variables = runtime.get("variables")
        if not isinstance(variables, dict):
            raise LifecycleError("runtime credential fingerprint records are missing")
        for name in (
            "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY",
            "TOOLATHLON_DEEPSEEK_HERMES_API_KEY",
            "ASTRA_ADMIN_ACCESS_TOKEN",
        ):
            value = os.environ.get(name, "")
            record = variables.get(name)
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None
            if not isinstance(record, dict) or record.get("value_sha256") != digest:
                raise LifecycleError(f"runtime credential fingerprint drift: {name}")

    def _mutable_credential_fingerprints(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for relative in self.mutable_credential_paths:
            path = self.source / relative
            if not path.is_file() or path.is_symlink():
                raise LifecycleError(f"runtime OAuth credential is unavailable: {relative}")
            records.append({"path": relative, "sha256": sha256_file(path)})
        return records

    def _reset(self) -> None:
        assert self.lifecycle is not None
        assert self.task_reset_contract is not None
        self.lifecycle.append(
            "reset.start",
            reset_scope={
                "product_state": "attempt_scoped_identity_or_home",
                "task_container": "created_fresh_after_reset",
                "workspace": "recreated_by_toolathlon_preprocess",
                "application_state": "restoration_delegated_to_following_task_preprocess",
            },
            required_mcp_servers=self.task_reset_contract["required_mcp_servers"],
            task_preprocess_present=self.task_reset_contract[
                "task_preprocess_present"
            ],
            mutable_oauth_fingerprints_before=self._mutable_credential_fingerprints(),
        )
        baseline = read_json_object(self.freeze / "m1-app-state-live.json")
        if baseline.get("local_applications", {}).get("state") != "GO":
            raise LifecycleError("frozen local application baseline is not GO")
        self.lifecycle.append(
            "reset.end",
            status="passed",
            baseline_sha256=sha256_file(self.freeze / "m1-app-state-live.json"),
            task_config_sha256=self.task_reset_contract["task_config_sha256"],
            method="qualify_fresh_attempt_boundaries_and_task_preprocess_contract",
            host_application_reprovision="qualified_recovery_only_not_per_attempt",
        )

    def _start_container(self) -> None:
        assert self.lifecycle is not None
        self.lifecycle.append("container.start", image=TASK_IMAGE)
        self.task_state.mkdir(mode=0o700)
        command = [
            "run",
            "-d",
            "--name",
            self.container_name,
            "--network",
            "host",
            "--cpus",
            "8",
            "--memory",
            "8g",
            "--memory-swap",
            "16g",
            "-v",
            f"{self.task_state}:/workspace/dumps",
        ]
        required_servers = set(self.task_reset_contract["required_mcp_servers"])  # type: ignore[index]
        auth_root = self.source / "configs/.mcp-auth"
        self.mcp_auth_bind_mounted = "notion" in required_servers
        if self.mcp_auth_bind_mounted:
            if not auth_root.is_dir():
                raise LifecycleError("Notion task requires frozen MCP OAuth state")
            command.extend(
                ["-v", f"{auth_root}:/workspace/configs/.mcp-auth"]
            )
        notion_patch = self.source / "configs/notion-mcp-patches/notion-openapi.json"
        if "notion" in required_servers and notion_patch.is_file():
            command.extend(
                [
                    "-v",
                    f"{notion_patch}:/workspace/node_modules/@notionhq/notion-mcp-server/scripts/notion-openapi.json:ro",
                ]
            )
        if Path("/var/run/docker.sock").exists():
            command.extend(["-v", "/var/run/docker.sock:/var/run/docker.sock"])
        command.extend(["-w", "/workspace", TASK_IMAGE, "sleep", "infinity"])
        result = self._docker(*command, timeout=120)
        container_id = result.stdout.decode().strip()
        if len(container_id) < 12:
            raise LifecycleError("container runtime returned no container ID")
        self.container_id[0] = container_id
        inspect = self._docker(
            "inspect", "--format", "{{.State.Pid}}", self.container_name, timeout=30
        )
        self.container_pid[0] = int(inspect.stdout.decode().strip())
        self._docker("exec", self.container_name, "true", timeout=30)
        self.lifecycle.append(
            "container.ready",
            container_id=container_id,
            container_pid=self.container_pid[0],
            mcp_auth_bind_mounted=self.mcp_auth_bind_mounted,
        )

    def _copy_tree(self) -> None:
        for relative in PROJECT_COPY_PATHS:
            source = self.source / relative
            if not source.exists():
                continue
            target = f"/workspace/{relative}"
            if source.is_dir():
                self._docker(
                    "exec", self.container_name, "mkdir", "-p", target, timeout=30
                )
                if relative == "configs":
                    for child in sorted(source.iterdir(), key=lambda path: path.name):
                        if child.name == ".mcp-auth":
                            continue
                        self._docker(
                            "cp",
                            str(child),
                            f"{self.container_name}:{target}/",
                            timeout=300,
                        )
                else:
                    self._docker(
                        "cp",
                        f"{source}/.",
                        f"{self.container_name}:{target}/",
                        timeout=300,
                    )
            else:
                parent = Path(relative).parent.as_posix()
                target_parent = (
                    "/workspace" if parent == "." else f"/workspace/{parent}"
                )
                self._docker(
                    "exec",
                    self.container_name,
                    "mkdir",
                    "-p",
                    target_parent,
                    timeout=30,
                )
                self._docker(
                    "cp",
                    str(source),
                    f"{self.container_name}:{target}",
                    timeout=300,
                )
        self._docker(
            "exec",
            self.container_name,
            "mkdir",
            "-p",
            "/workspace/tasks/finalpool",
            "/workspace/scripts/decoupled",
            timeout=30,
        )
        self._docker(
            "exec",
            self.container_name,
            "rm",
            "-rf",
            "--",
            f"/workspace/tasks/finalpool/{self.args.task_id}",
            timeout=30,
        )
        self._docker(
            "cp",
            str(self.task_source),
            f"{self.container_name}:/workspace/tasks/finalpool/",
            timeout=300,
        )
        self._docker(
            "cp",
            str(self.runtime_overlay),
            f"{self.container_name}:/workspace/scripts/decoupled/container_tool_gateway_benchmark.py",
            timeout=60,
        )
        self._enforce_container_credential_modes()
        self._install_container_credential_layout()

    def _install_container_credential_layout(self) -> None:
        assert self.lifecycle is not None
        assert self.task_reset_contract is not None
        required_servers = set(self.task_reset_contract["required_mcp_servers"])
        if "google_calendar" not in required_servers:
            return
        required_sources = {
            "configs/gcp-oauth.keys.json",
            "configs/google_credentials.json",
        }
        manifest = read_json_object(self.freeze / "credential-manifest.json")
        frozen_paths = {
            str(item.get("path", ""))
            for item in manifest["toolathlon_application_credentials"]["files"]
            if isinstance(item, dict)
        }
        if not required_sources.issubset(frozen_paths):
            raise LifecycleError("Google Calendar credential layout is not frozen")
        for directory in ("/root/.gmail-mcp", "/root/.calendar-mcp"):
            self._docker(
                "exec", self.container_name, "mkdir", "-p", directory, timeout=30
            )
            self._docker(
                "exec",
                self.container_name,
                "cp",
                "/workspace/configs/gcp-oauth.keys.json",
                f"{directory}/gcp-oauth.keys.json",
                timeout=30,
            )
            self._docker(
                "exec",
                self.container_name,
                "cp",
                "/workspace/configs/google_credentials.json",
                f"{directory}/credentials.json",
                timeout=30,
            )
            self._docker(
                "exec",
                self.container_name,
                "chmod",
                "600",
                f"{directory}/gcp-oauth.keys.json",
                f"{directory}/credentials.json",
                timeout=30,
            )
        self.lifecycle.append(
            "container.credential_layout_ready",
            integration="google_calendar",
            source_fingerprints={
                relative: sha256_file(self.source / relative)
                for relative in sorted(required_sources)
            },
            targets=["/root/.gmail-mcp", "/root/.calendar-mcp"],
        )

    def _enforce_container_credential_modes(self) -> None:
        manifest = read_json_object(self.freeze / "credential-manifest.json")
        records = manifest["toolathlon_application_credentials"]["files"]
        paths: list[str] = []
        for item in records:
            relative = str(item["path"])
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise LifecycleError("unsafe credential path in frozen manifest")
            paths.append(relative)
        script = (
            "import json,os,pathlib,sys; "
            "root=pathlib.Path('/workspace'); "
            "[(os.chmod(root/p,0o600) if (root/p).is_file() else None) "
            "for p in json.loads(sys.argv[1])]"
        )
        self._docker(
            "exec",
            self.container_name,
            "python3",
            "-c",
            script,
            json.dumps(paths, separators=(",", ":")),
            timeout=120,
        )

    def _preprocess(self) -> None:
        assert self.lifecycle is not None
        assert self.private_dir is not None
        assert self.task_reset_contract is not None
        self.lifecycle.append(
            "preprocess.start",
            state_restoration="task_scoped_application_and_workspace_reset",
            task_preprocess_present=self.task_reset_contract[
                "task_preprocess_present"
            ],
        )
        container_bundle = f"/run/toolathlon-preprocess-{self.args.run_id}.json"
        command = self.docker_command(
            "exec",
            "--env",
            "DOCKER_API_VERSION=1.44",
            self.container_name,
            "uv",
            "run",
            "python",
            "-m",
            "scripts.decoupled.container_preprocess",
            "--eval_config",
            "scripts/formal_run_v0.json",
            "--task_dir",
            f"finalpool/{self.args.task_id}",
            "--max_steps_under_single_turn_mode",
            "100",
            "--model_short_name",
            "deepseek-v4-flash",
            "--provider",
            "unified",
            "--bundle_file",
            container_bundle,
            "--host_output_folder",
            str(self.task_state),
        )
        _run(
            command,
            timeout=3600,
            log_path=self.output / "preprocess.log",
        )
        self.trusted_bundle = self.private_dir / "task_bundle.json"
        self._docker(
            "cp",
            f"{self.container_name}:{container_bundle}",
            str(self.trusted_bundle),
            timeout=60,
        )
        os.chmod(self.trusted_bundle, 0o600)
        self._docker("exec", self.container_name, "rm", "-f", container_bundle, timeout=30)
        self._docker(
            "exec",
            self.container_name,
            "chown",
            "-R",
            f"{os.getuid()}:{os.getgid()}",
            "/workspace/dumps",
            timeout=120,
        )
        bundle = read_json_object(self.trusted_bundle)
        if bundle.get("schema_version") != 2 or bundle.get("task_dir") != f"finalpool/{self.args.task_id}":
            raise LifecycleError("preprocess produced an invalid trusted bundle")
        if Path(str(bundle.get("host_paths", {}).get("task_root", ""))).resolve() != self.task_state:
            raise LifecycleError("trusted bundle host task root mismatch")
        self.lifecycle.append(
            "preprocess.end",
            status="passed",
            trusted_bundle_sha256=sha256_file(self.trusted_bundle),
            preprocess_log_sha256=sha256_file(self.output / "preprocess.log"),
            application_state_restored=True,
        )

    def _guard_command(self, action: str, *args: str) -> subprocess.CompletedProcess[bytes]:
        return _run(
            [*self.guard, action, *args],
            cwd=self.source,
            timeout=600,
        )

    def _stash_private_artifacts(self) -> None:
        assert self.private_dir is not None
        result = self._guard_command(
            "stash",
            "--runtime",
            "docker",
            "--container",
            self.container_name,
            "--task-path",
            f"/workspace/tasks/finalpool/{self.args.task_id}",
            "--stash-root",
            str(self.private_dir / "artifact-stash"),
        )
        self.stash_dir = Path(result.stdout.decode().strip())
        if not self.stash_dir.is_dir():
            raise LifecycleError("artifact guard returned no private stash")

    def _start_gateway(self, port: int) -> None:
        assert self.lifecycle is not None
        assert self.trusted_bundle is not None
        self.lifecycle.append("gateway.start", port=port)
        gateway_bundle = f"/run/toolathlon-gateway-{self.args.run_id}.json"
        self._docker(
            "cp",
            str(self.trusted_bundle),
            f"{self.container_name}:{gateway_bundle}",
            timeout=60,
        )
        start = (
            "exec uv run python -m scripts.decoupled.container_tool_gateway_benchmark "
            f"--bundle_file {gateway_bundle} --host 0.0.0.0 --port {port} --debug "
            "> /workspace/dumps/gateway.log 2>&1"
        )
        self._docker(
            "exec", "-d", self.container_name, "bash", "-lc", start, timeout=60
        )
        ready = _http_ready(f"http://127.0.0.1:{port}/health", timeout_seconds=600)
        self._docker("exec", self.container_name, "rm", "-f", gateway_bundle, timeout=30)
        self.lifecycle.append("gateway.ready", status="passed", health=ready)

    def _restore_for_evaluator(self, _outcome: Any) -> None:
        assert self.stash_dir is not None
        assert self.trusted_bundle is not None
        self._guard_command(
            "restore",
            "--runtime",
            "docker",
            "--container",
            self.container_name,
            "--task-path",
            f"/workspace/tasks/finalpool/{self.args.task_id}",
            "--stash-dir",
            str(self.stash_dir),
        )
        self._guard_command("cleanup", "--stash-dir", str(self.stash_dir))
        self.stash_dir = None
        bundle = read_json_object(self.trusted_bundle)
        eval_path = str(bundle["container_paths"]["log_file"])
        eval_path = str(Path(eval_path).with_name("eval_res.json"))
        self._docker("exec", self.container_name, "rm", "-rf", "--", eval_path, timeout=30)
        self._docker(
            "cp",
            str(self.trusted_bundle),
            f"{self.container_name}:{self.eval_bundle_container}",
            timeout=60,
        )

    def _write_slot_config(self, gateway_port: int) -> Path:
        assert self.trusted_bundle is not None
        bundle = read_json_object(self.trusted_bundle)
        workspace = Path(bundle["host_paths"]["agent_workspace"]).resolve()
        permission = self.output / "permission-policy.json"
        gateway_url = f"http://127.0.0.1:{gateway_port}/sse"
        write_json_atomic(
            permission,
            {
                "policy_id": "toolathlon-task-scoped-v1",
                "products": {
                    "astra": {"permission_mode": "auto"},
                    "hermes": {"approval_mode": "smart"},
                },
                "task_scope": {"gateway_url": gateway_url, "workspace": str(workspace)},
                "unresolved_approval_action": "deny",
            },
            mode=0o600,
        )
        runtime_tiers = self.freeze / "task-runtime-tiers.json"
        tier = read_json_object(runtime_tiers)["tasks"][self.args.task_id]
        section_manifest = self.freeze / "section-3.3.sha256"
        system_freeze = self.freeze / f"{self.args.system}.freeze.json"
        runtime_config = (
            self.repo_root
            / f"astra/work/toolathlon-verified/rendered-{self.args.system}-runtime.json"
        )
        config = {
            "replacement_for_run_id": self.args.replacement_for_run_id,
            "adapter_freeze": str(self.freeze / "adapter.freeze.json"),
            "permission_policy_freeze": str(
                self.freeze / "permission-policy.freeze.json"
            ),
            "run": {
                "bundle_file": str(self.trusted_bundle),
                "deadline_s": tier["deadline_seconds"],
                "experiment_id": self.args.experiment_id,
                "gateway_url": gateway_url,
                "max_model_requests": 100,
                "model_freeze": str(self.freeze / "model.freeze.json"),
                "output_dir": str(self.output),
                "permission_policy": str(permission),
                "run_id": self.args.run_id,
                "system_id": self.args.system,
                "task_id": self.args.task_id,
                "task_requirements_manifest": str(
                    self.freeze / "task-requirements.json"
                ),
                "workspace": str(workspace),
            },
            "runtime_config": str(runtime_config),
            "section_3_3_freeze": str(self.freeze / "section-3.3.freeze.json"),
            "section_3_3_manifest": str(section_manifest),
            "section_3_3_manifest_sha256": sha256_file(section_manifest),
            "system_freeze": str(system_freeze),
            "task_runtime_tiers": str(runtime_tiers),
            "evaluator": {
                "command": [
                    *self.docker,
                    "exec",
                    "--env",
                    "DOCKER_API_VERSION=1.44",
                    self.container_name,
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "scripts.decoupled.container_eval",
                    "--bundle_file",
                    self.eval_bundle_container,
                    "--require_resolved_task_config",
                    "--consume_bundle",
                    "--agent_exit_code",
                    "{agent_exit_code}",
                ],
                "result_file": str(self.task_state / "eval_res.json"),
            },
        }
        path = self.private_dir / "run-config.json"  # type: ignore[operator]
        write_json_atomic(path, config, mode=0o600)
        return path

    def _cleanup(self) -> None:
        assert self.lifecycle is not None
        self.lifecycle.append("cleanup.start")
        if self.container_id[0]:
            self._docker(
                "exec",
                self.container_name,
                "chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/workspace/dumps",
                timeout=120,
                check=False,
            )
            logs = self._docker("logs", self.container_name, timeout=60, check=False)
            (self.output / "container.log").write_bytes(logs.stdout)
            self._docker("stop", "-t", "0", self.container_name, timeout=60, check=False)
            self._docker("rm", "-f", self.container_name, timeout=60, check=False)
            self.container_id[0] = None
            self.container_pid[0] = None
        if self.stash_dir is not None:
            self._guard_command("cleanup", "--stash-dir", str(self.stash_dir))
            self.stash_dir = None
        self.lifecycle.append(
            "cleanup.end",
            status="passed",
            mutable_oauth_fingerprints_after=self._mutable_credential_fingerprints(),
        )

    def _finalize(self) -> dict[str, Any]:
        assert self.lifecycle is not None
        hash_path = self.output / "artifacts.sha256"
        hash_path.write_text("", encoding="utf-8")
        self.lifecycle.append("artifact_validation.start")
        preliminary = validate_run_artifacts(
            self.output,
            verify_hash=False,
            require_validation_end=False,
        )
        run_record = read_json_object(self.output / "run.json")
        run_record["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION
        run_record["artifact_gate"] = {
            "status": "passed",
            "validator": "validate_run_artifacts",
            "validated_at": utc_now(),
        }
        write_json_atomic(self.output / "run.json", run_record, mode=0o644)
        self.lifecycle.append(
            "artifact_validation.end",
            status="passed",
            preliminary=preliminary,
        )
        candidates = [
            path
            for path in self.output.rglob("*")
            if path.is_file() and not path.is_symlink() and path.name != "artifacts.sha256"
        ]
        write_sha256_manifest(hash_path, candidates, root=self.output)
        return validate_run_artifacts(self.output, verify_hash=True)

    def execute(self) -> int:
        if self.output.exists() and any(self.output.iterdir()):
            raise LifecycleError("output directory must be absent or empty")
        self.output.mkdir(parents=True, exist_ok=True)
        self.lifecycle = JsonlEventWriter(
            self.output / "lifecycle-events.jsonl",
            run_id=self.args.run_id,
            system_id=self.args.system,
        )
        self.private_dir = Path(tempfile.mkdtemp(prefix=f"toolathlon-{self.args.run_id}-"))
        os.chmod(self.private_dir, 0o700)
        sampler = ResourceSampler(
            self.output / "resource-usage.jsonl",
            run_id=self.args.run_id,
            system_id=self.args.system,
            product_pid=lambda: self.product_pid[0],
            container_id=lambda: self.container_id[0],
            container_pid=lambda: self.container_pid[0],
        )
        sampler.start()
        slot_code = 2
        try:
            self.preflight()
            self._reset()
            self._start_container()
            self._copy_tree()
            self._preprocess()
            self._stash_private_artifacts()
            gateway_port = _free_port()
            self._start_gateway(gateway_port)
            config_path = self._write_slot_config(gateway_port)
            slot_code = run_product_slot(
                config_path,
                before_evaluator=self._restore_for_evaluator,
                lifecycle_writer=self.lifecycle,
                resource_sampler=sampler,
                on_product_pid=lambda pid: self.product_pid.__setitem__(0, pid),
                write_artifact_manifest=False,
            )
        finally:
            try:
                self._cleanup()
            finally:
                sampler.close()
                if self.private_dir is not None:
                    shutil.rmtree(self.private_dir, ignore_errors=True)
                    self.private_dir = None
        validation = self._finalize()
        print(json.dumps(validation, ensure_ascii=False, sort_keys=True))
        return slot_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Toolathlon task lifecycle")
    parser.add_argument("--system", choices=("astra", "hermes"), required=True)
    parser.add_argument("--task-id", default=QUALIFICATION_TASK)
    parser.add_argument("--experiment-id", default="toolathlon-verified-v0.5")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--replacement-for-run-id")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--toolathlon-source",
        type=Path,
        default=Path("/home/vagrant/dataset/Toolathlon"),
    )
    parser.add_argument("--docker-via-sudo", action="store_true")
    args = parser.parse_args(argv)
    args.run_id = _safe_id(args.run_id, "run_id")
    args.experiment_id = _safe_id(args.experiment_id, "experiment_id")
    args.task_id = _safe_id(args.task_id, "task_id")
    if args.replacement_for_run_id is not None:
        args.replacement_for_run_id = _safe_id(
            args.replacement_for_run_id, "replacement_for_run_id"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return SingleTaskLifecycle(args).execute()


if __name__ == "__main__":
    raise SystemExit(main())
