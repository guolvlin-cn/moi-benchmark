#!/usr/bin/env python3
"""Preflight and freeze the exact 33 Terminal-Bench reruns.

This script never launches Harbor and never changes task or image contents.
Its mutating mode is limited to sequential ``docker pull`` calls and creating
one write-once JSON manifest.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import time
from typing import Any, Iterable, Sequence

if __name__ == "__main__" and sys.version_info < (3, 11):
    # Reuse Harbor's pinned Python on macOS instead of downloading dependencies.
    candidates = [
        os.environ.get("HARBOR_PYTHON"),
        str(Path.home() / ".local" / "share" / "uv" / "tools" / "harbor" / "bin" / "python"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            os.execv(candidate, [candidate, str(Path(__file__).resolve()), *sys.argv[1:]])

try:
    import tomllib

    _toml_loads = tomllib.loads
    _toml_decode_error = tomllib.TOMLDecodeError
except ModuleNotFoundError:  # macOS system Python is currently 3.9.
    try:
        import toml
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        raise SystemExit("Python 3.11+ or the 'toml' package is required") from exc

    _toml_loads = toml.loads
    _toml_decode_error = toml.TomlDecodeError


EXPECTED_TASK_COUNT = 33
DEFAULT_MODEL = "c5bde5de-9805-48d4-a016-1db6e6018fc4"
DEFAULT_ASTRA_API_URL = "http://host.docker.internal:17001"
DEFAULT_ASTRA_API_HOST = "host.docker.internal"
DEFAULT_FALLBACK_TIMEOUT_SEC = 600
DEFAULT_LLM_TOTAL_BUDGET_SEC = 900
DEFAULT_STREAM_TRANSPORT_RETRIES = 2
DEFAULT_OPTIONAL_RETRY_MIN_REMAINING_SEC = 930
DEFAULT_PRODUCT_TIMEOUT_MULTIPLIER = 2.25
DEFAULT_HARBOR_TIMEOUT_MULTIPLIER = 2.0
DEFAULT_HARBOR_AGENT_TIMEOUT_MULTIPLIER = 2.5
DEFAULT_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER = 2.0
DEFAULT_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER = 2.0
DEFAULT_HARBOR_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER = 2.0
DEFAULT_HARBOR_AGENT_SETUP_BASE_TIMEOUT_SEC = 360
DEFAULT_MAX_TURNS = 50


class FreezeError(RuntimeError):
    """A preflight invariant was not satisfied."""


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_task_names(path: Path) -> list[str]:
    if not path.is_file():
        raise FreezeError(f"missing rerun task manifest: {path}")
    names = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(names) != EXPECTED_TASK_COUNT:
        raise FreezeError(
            f"expected exactly {EXPECTED_TASK_COUNT} rerun tasks; found {len(names)}"
        )
    duplicates = sorted(name for name in set(names) if names.count(name) > 1)
    if duplicates:
        raise FreezeError(f"duplicate rerun task names: {', '.join(duplicates)}")
    invalid = sorted(
        name
        for name in names
        if name in {".", ".."}
        or "/" in name
        or "\\" in name
        or Path(name).name != name
    )
    if invalid:
        raise FreezeError(f"invalid rerun task names: {', '.join(invalid)}")
    return names


def load_task_config(task_dir: Path) -> tuple[Path, dict[str, Any]]:
    task_toml = task_dir / "task.toml"
    if not task_toml.is_file():
        raise FreezeError(f"missing task.toml: {task_toml}")
    try:
        config = _toml_loads(task_toml.read_text(encoding="utf-8"))
    except (OSError, _toml_decode_error) as exc:
        raise FreezeError(f"cannot parse {task_toml}: {exc}") from exc
    return task_toml, config


def image_from_task_config(task_name: str, config: dict[str, Any]) -> str:
    image = config.get("environment", {}).get("docker_image")
    if not isinstance(image, str) or not image.strip():
        raise FreezeError(f"{task_name}: [environment].docker_image is missing")
    return image.strip()


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def task_file_manifest(task_dir: Path) -> tuple[list[dict[str, Any]], str]:
    records: list[dict[str, Any]] = []
    for path in sorted(task_dir.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(task_dir).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            records.append(
                {
                    "path": relative,
                    "type": "symlink",
                    "target": target,
                    "sha256": sha256_text(target),
                }
            )
        elif path.is_file():
            records.append(
                {
                    "path": relative,
                    "type": "file",
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return records, sha256_text(canonical)


def detect_elf_arch(path: Path) -> str:
    if not path.is_file():
        raise FreezeError(f"missing Astra artifact: {path}")
    with path.open("rb") as handle:
        header = handle.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise FreezeError(f"Astra artifact is not an ELF binary: {path}")
    byte_order = {1: "<", 2: ">"}.get(header[5])
    if byte_order is None:
        raise FreezeError(f"Astra artifact has an invalid ELF byte order: {path}")
    machine = struct.unpack(f"{byte_order}H", header[18:20])[0]
    architectures = {62: "amd64", 183: "arm64"}
    if machine not in architectures:
        raise FreezeError(f"unsupported Astra ELF machine {machine}: {path}")
    return architectures[machine]


def artifact_metadata(path: Path, expected_arch: str) -> dict[str, Any]:
    actual_arch = detect_elf_arch(path)
    if actual_arch != expected_arch:
        raise FreezeError(
            f"Astra artifact architecture mismatch for {path}: "
            f"expected {expected_arch}, found {actual_arch}"
        )
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "os": "linux",
        "architecture": actual_arch,
    }


def binary_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FreezeError(f"missing frozen runtime binary: {path}")
    description_result = run_command(["file", "--brief", str(path)])
    description = (
        description_result.stdout.strip()
        if description_result.returncode == 0
        else None
    )
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "file_description": description,
    }


def model_freeze_metadata(path: Path, expected_model_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise FreezeError(f"missing frozen model metadata: {path}")
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"cannot parse frozen model metadata {path}: {exc}") from exc
    model = snapshot.get("model")
    if not isinstance(model, dict):
        raise FreezeError(f"frozen model metadata has no model object: {path}")
    model_id = model.get("model_id")
    if model_id != expected_model_id:
        raise FreezeError(
            f"frozen model ID mismatch: expected {expected_model_id}, "
            f"found {model_id!r}"
        )
    if snapshot.get("secrets_included") is not False:
        raise FreezeError(
            "frozen model metadata must declare secrets_included=false"
        )
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "model_id": model_id,
        "secrets_included": False,
    }


def run_command(
    command: Sequence[str],
    *,
    timeout_sec: float | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except FileNotFoundError as exc:
        raise FreezeError(f"command not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FreezeError(
            f"command timed out after {timeout_sec}s: {' '.join(command[:3])}"
        ) from exc


def pull_image_with_retry(
    docker_bin: str,
    image: str,
    *,
    attempts: int,
    base_delay_sec: float,
    max_delay_sec: float,
    jitter_sec: float,
    sleep_fn: Any = time.sleep,
    random_fn: Any = random.uniform,
) -> dict[str, Any]:
    started = time.monotonic()
    last_error = ""
    for attempt in range(1, attempts + 1):
        print(
            f"[pull {attempt}/{attempts}] {image}",
            file=sys.stderr,
            flush=True,
        )
        result = run_command([docker_bin, "pull", image])
        if result.returncode == 0:
            return {
                "attempts": attempt,
                "duration_sec": round(time.monotonic() - started, 3),
            }
        last_error = (result.stderr or result.stdout or "").strip()[-4000:]
        if attempt < attempts:
            delay = min(max_delay_sec, base_delay_sec * (2 ** (attempt - 1)))
            delay += random_fn(0.0, jitter_sec)
            sleep_fn(delay)
    raise FreezeError(
        f"docker pull failed after {attempts} attempts for {image}: {last_error}"
    )


def inspect_image(docker_bin: str, image: str) -> dict[str, Any]:
    result = run_command([docker_bin, "image", "inspect", image])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-4000:]
        raise FreezeError(f"cannot inspect Docker image {image}: {detail}")
    try:
        entries = json.loads(result.stdout)
        entry = entries[0]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise FreezeError(f"invalid docker image inspect output for {image}") from exc

    architecture = normalize_arch(str(entry.get("Architecture", "")))
    os_name = str(entry.get("Os", "")).lower()
    image_id = str(entry.get("Id", ""))
    repo_digests = sorted(
        digest
        for digest in entry.get("RepoDigests", [])
        if isinstance(digest, str) and "@sha256:" in digest
    )
    if not image_id.startswith("sha256:"):
        raise FreezeError(f"{image}: docker inspect returned no image ID")
    if not repo_digests:
        raise FreezeError(f"{image}: docker inspect returned no repository digest")
    if os_name != "linux":
        raise FreezeError(f"{image}: expected a Linux image, found {os_name or 'unknown'}")

    config = entry.get("Config") or {}
    raw_working_dir = config.get("WorkingDir") or ""
    if not isinstance(raw_working_dir, str):
        raise FreezeError(f"{image}: invalid Config.WorkingDir")
    return {
        "configured_ref": image,
        "image_id": image_id,
        "repo_digests": repo_digests,
        "frozen_ref": select_repo_digest(image, repo_digests),
        "os": os_name,
        "architecture": architecture,
        "working_dir": raw_working_dir,
        "effective_working_dir": raw_working_dir or "/",
        "config_user": config.get("User") or "",
        "entrypoint": config.get("Entrypoint"),
        "cmd": config.get("Cmd"),
    }


def normalize_arch(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "amd64": "amd64",
        "x86_64": "amd64",
        "x86-64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    if normalized not in aliases:
        raise FreezeError(f"unsupported container architecture: {value or 'unknown'}")
    return aliases[normalized]


def image_repository(image: str) -> str:
    without_digest = image.split("@", 1)[0]
    slash = without_digest.rfind("/")
    colon = without_digest.rfind(":")
    if colon > slash:
        return without_digest[:colon]
    return without_digest


def select_repo_digest(image: str, repo_digests: Sequence[str]) -> str:
    repository = image_repository(image)
    matching = sorted(
        digest for digest in repo_digests if digest.startswith(f"{repository}@")
    )
    return matching[0] if matching else sorted(repo_digests)[0]


def probe_astra_version(
    docker_bin: str,
    image_metadata: dict[str, Any],
    artifact: dict[str, Any],
    *,
    timeout_sec: float,
) -> dict[str, Any]:
    image_arch = image_metadata["architecture"]
    if artifact["architecture"] != image_arch:
        raise FreezeError(
            f"{image_metadata['configured_ref']}: image is {image_arch}, "
            f"but selected Astra artifact is {artifact['architecture']}"
        )
    command = [
        docker_bin,
        "run",
        "--rm",
        "--network",
        "none",
        "--platform",
        f"linux/{image_arch}",
        "--entrypoint",
        "/tmp/astra-freeze-probe",
        "--volume",
        f"{artifact['path']}:/tmp/astra-freeze-probe:ro",
        image_metadata["image_id"],
        "--version",
    ]
    started = time.monotonic()
    result = run_command(command, timeout_sec=timeout_sec)
    duration = round(time.monotonic() - started, 3)
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if result.returncode != 0:
        raise FreezeError(
            f"{image_metadata['configured_ref']}: Astra --version failed with "
            f"rc={result.returncode}: {output[-4000:]}"
        )
    if not output:
        raise FreezeError(
            f"{image_metadata['configured_ref']}: Astra --version returned no output"
        )
    return {
        "returncode": result.returncode,
        "duration_sec": duration,
        "output": output[:4096],
        "output_sha256": sha256_text(output),
    }


def docker_server_metadata(docker_bin: str) -> dict[str, Any]:
    result = run_command([docker_bin, "info", "--format", "{{json .}}"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-4000:]
        raise FreezeError(f"Docker daemon is unavailable: {detail}")
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FreezeError("invalid docker info output") from exc
    architecture = info.get("Architecture")
    return {
        "server_version": info.get("ServerVersion"),
        "operating_system": info.get("OperatingSystem"),
        "os_type": info.get("OSType"),
        "architecture": architecture,
        "normalized_architecture": normalize_arch(str(architecture or "")),
        "kernel_version": info.get("KernelVersion"),
    }


def git_revision(path: Path) -> str | None:
    result = run_command(["git", "-C", str(path), "rev-parse", "HEAD"])
    if result.returncode != 0:
        return None
    revision = result.stdout.strip()
    return revision or None


def git_state(path: Path) -> dict[str, Any]:
    revision = git_revision(path)
    if revision is None:
        return {
            "revision": None,
            "dirty": None,
            "status_porcelain_sha256": None,
        }
    status_result = run_command(
        [
            "git",
            "-C",
            str(path),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ]
    )
    if status_result.returncode != 0:
        raise FreezeError(f"cannot read git status for frozen source: {path}")
    status = status_result.stdout
    return {
        "revision": revision,
        "dirty": bool(status),
        "status_porcelain_sha256": sha256_text(status),
    }


def runner_file_metadata(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.is_file():
            raise FreezeError(f"missing runner input: {resolved}")
        records.append(
            {
                "path": str(resolved),
                "sha256": sha256_file(resolved),
                "size_bytes": resolved.stat().st_size,
            }
        )
    return records


def task_permissions(config: dict[str, Any]) -> dict[str, Any]:
    environment = config.get("environment", {})
    return {
        "permission_mode": "auto",
        "read_memory": False,
        "allow_internet": environment.get("allow_internet"),
        "cpus": environment.get("cpus"),
        "memory_mb": environment.get("memory_mb"),
        "storage_mb": environment.get("storage_mb"),
        "gpus": environment.get("gpus"),
        "mcp_servers": json_safe(environment.get("mcp_servers", [])),
        "environment_env": json_safe(environment.get("env", {})),
        "verifier_env": json_safe(config.get("verifier", {}).get("env", {})),
        "solution_env": json_safe(config.get("solution", {}).get("env", {})),
    }


def prepare_tasks(
    tasks_dir: Path,
    names: Sequence[str],
    *,
    product_timeout_multiplier: float,
    harbor_agent_timeout_multiplier: float,
    harbor_verifier_timeout_multiplier: float,
    harbor_agent_setup_timeout_multiplier: float,
    harbor_environment_build_timeout_multiplier: float,
    harbor_agent_setup_base_timeout_sec: float,
) -> list[dict[str, Any]]:
    if not tasks_dir.is_dir():
        raise FreezeError(f"missing Terminal-Bench task directory: {tasks_dir}")
    records: list[dict[str, Any]] = []
    resolved_root = tasks_dir.resolve()
    for name in names:
        task_dir = (tasks_dir / name).resolve()
        if task_dir.parent != resolved_root or not task_dir.is_dir():
            raise FreezeError(f"rerun task does not exist in snapshot: {name}")
        task_toml, config = load_task_config(task_dir)
        configured_name = config.get("task", {}).get("name")
        expected_configured_name = f"terminal-bench/{name}"
        if configured_name != expected_configured_name:
            raise FreezeError(
                f"{name}: task.name must be {expected_configured_name!r}; "
                f"found {configured_name!r}"
            )
        dockerfile = task_dir / "environment" / "Dockerfile"
        if not dockerfile.is_file():
            raise FreezeError(f"{name}: missing environment/Dockerfile")
        files, tree_sha256 = task_file_manifest(task_dir)
        agent_timeout = config.get("agent", {}).get("timeout_sec")
        if not isinstance(agent_timeout, (int, float)) or agent_timeout <= 0:
            raise FreezeError(f"{name}: invalid [agent].timeout_sec")
        verifier_timeout = config.get("verifier", {}).get("timeout_sec")
        if (
            not isinstance(verifier_timeout, (int, float))
            or verifier_timeout <= 0
        ):
            raise FreezeError(f"{name}: invalid [verifier].timeout_sec")
        build_timeout = config.get("environment", {}).get("build_timeout_sec")
        if not isinstance(build_timeout, (int, float)) or build_timeout <= 0:
            raise FreezeError(
                f"{name}: invalid [environment].build_timeout_sec"
            )
        records.append(
            {
                "name": name,
                "task_dir": str(task_dir),
                "task_toml": {
                    "path": str(task_toml),
                    "sha256": sha256_file(task_toml),
                },
                "dockerfile": {
                    "path": str(dockerfile),
                    "sha256": sha256_file(dockerfile),
                },
                "task_tree_sha256": tree_sha256,
                "task_files": files,
                "configured_image": image_from_task_config(name, config),
                "permissions": task_permissions(config),
                "timeouts": {
                    "upstream_agent_timeout_sec": agent_timeout,
                    "product_timeout_multiplier": product_timeout_multiplier,
                    "product_timeout_sec": agent_timeout
                    * product_timeout_multiplier,
                    "harbor_agent_timeout_multiplier": (
                        harbor_agent_timeout_multiplier
                    ),
                    "harbor_agent_timeout_sec": agent_timeout
                    * harbor_agent_timeout_multiplier,
                    "upstream_verifier_timeout_sec": verifier_timeout,
                    "harbor_verifier_timeout_multiplier": (
                        harbor_verifier_timeout_multiplier
                    ),
                    "harbor_verifier_timeout_sec": verifier_timeout
                    * harbor_verifier_timeout_multiplier,
                    "upstream_environment_build_timeout_sec": build_timeout,
                    "harbor_environment_build_timeout_multiplier": (
                        harbor_environment_build_timeout_multiplier
                    ),
                    "harbor_environment_build_timeout_sec": build_timeout
                    * harbor_environment_build_timeout_multiplier,
                    "harbor_agent_setup_base_timeout_sec": (
                        harbor_agent_setup_base_timeout_sec
                    ),
                    "harbor_agent_setup_timeout_multiplier": (
                        harbor_agent_setup_timeout_multiplier
                    ),
                    "harbor_agent_setup_timeout_sec": (
                        harbor_agent_setup_base_timeout_sec
                        * harbor_agent_setup_timeout_multiplier
                    ),
                },
                "task_config": json_safe(config),
            }
        )
    return records


def build_parser() -> argparse.ArgumentParser:
    root = workspace_root()
    package_dir = root / "astra" / "runners" / "astra_terminal_bench"
    parser = argparse.ArgumentParser(
        description=(
            "Pre-pull, preflight, and freeze the exact 33 from-scratch reruns "
            "without launching Harbor."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="inspect cached images and run Astra --version; do not pull or write",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="validate static inputs and print the plan; do not call Docker or write",
    )
    parser.add_argument(
        "--task-list",
        type=Path,
        default=package_dir / "rerun-from-scratch-33.tasks.txt",
    )
    parser.add_argument(
        "--tasks-dir",
        type=Path,
        default=root / "work" / "terminal-bench-2-1" / "tasks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root
        / "work"
        / "astra-c0-rerun-from-scratch-33"
        / "frozen-inputs.json",
    )
    parser.add_argument(
        "--astra-amd64",
        type=Path,
        default=root
        / "work"
        / "astra-linux-build-amd64"
        / "target"
        / "release"
        / "astra",
    )
    parser.add_argument(
        "--astra-arm64",
        type=Path,
        default=root
        / "work"
        / "astra-linux-build"
        / "target"
        / "release"
        / "astra",
    )
    parser.add_argument(
        "--astra-server-binary",
        type=Path,
        default=root / "external" / "astra" / "target" / "release" / "astra-server",
    )
    parser.add_argument("--runner-file", action="append", type=Path, default=[])
    parser.add_argument(
        "--model",
        default=os.environ.get("ASTRA_TBENCH_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--fallback-timeout-sec",
        type=int,
        default=DEFAULT_FALLBACK_TIMEOUT_SEC,
    )
    parser.add_argument(
        "--llm-total-budget-sec",
        type=int,
        default=DEFAULT_LLM_TOTAL_BUDGET_SEC,
    )
    parser.add_argument(
        "--stream-transport-retries",
        type=int,
        default=DEFAULT_STREAM_TRANSPORT_RETRIES,
    )
    parser.add_argument(
        "--optional-retry-min-remaining-sec",
        type=int,
        default=DEFAULT_OPTIONAL_RETRY_MIN_REMAINING_SEC,
    )
    parser.add_argument(
        "--product-timeout-multiplier",
        type=float,
        default=DEFAULT_PRODUCT_TIMEOUT_MULTIPLIER,
    )
    parser.add_argument(
        "--timeout-multiplier",
        type=float,
        default=DEFAULT_HARBOR_TIMEOUT_MULTIPLIER,
    )
    parser.add_argument(
        "--agent-timeout-multiplier",
        type=float,
        default=DEFAULT_HARBOR_AGENT_TIMEOUT_MULTIPLIER,
    )
    parser.add_argument(
        "--verifier-timeout-multiplier",
        type=float,
        default=DEFAULT_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER,
    )
    parser.add_argument(
        "--agent-setup-timeout-multiplier",
        type=float,
        default=DEFAULT_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER,
    )
    parser.add_argument(
        "--environment-build-timeout-multiplier",
        type=float,
        default=DEFAULT_HARBOR_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER,
    )
    parser.add_argument(
        "--agent-setup-base-timeout-sec",
        type=float,
        default=DEFAULT_HARBOR_AGENT_SETUP_BASE_TIMEOUT_SEC,
    )
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--docker-bin", default=os.environ.get("DOCKER_BIN", "docker"))
    parser.add_argument("--pull-attempts", type=int, default=5)
    parser.add_argument("--pull-base-delay-sec", type=float, default=2.0)
    parser.add_argument("--pull-max-delay-sec", type=float, default=30.0)
    parser.add_argument("--pull-jitter-sec", type=float, default=1.0)
    parser.add_argument("--version-probe-timeout-sec", type=float, default=30.0)
    return parser


def validate_args(args: argparse.Namespace) -> None:
    positive = {
        "--fallback-timeout-sec": args.fallback_timeout_sec,
        "--llm-total-budget-sec": args.llm_total_budget_sec,
        "--stream-transport-retries": args.stream_transport_retries,
        "--optional-retry-min-remaining-sec": args.optional_retry_min_remaining_sec,
        "--product-timeout-multiplier": args.product_timeout_multiplier,
        "--timeout-multiplier": args.timeout_multiplier,
        "--agent-timeout-multiplier": args.agent_timeout_multiplier,
        "--verifier-timeout-multiplier": args.verifier_timeout_multiplier,
        "--agent-setup-timeout-multiplier": (
            args.agent_setup_timeout_multiplier
        ),
        "--environment-build-timeout-multiplier": (
            args.environment_build_timeout_multiplier
        ),
        "--agent-setup-base-timeout-sec": args.agent_setup_base_timeout_sec,
        "--max-turns": args.max_turns,
        "--pull-attempts": args.pull_attempts,
        "--pull-base-delay-sec": args.pull_base_delay_sec,
        "--pull-max-delay-sec": args.pull_max_delay_sec,
        "--version-probe-timeout-sec": args.version_probe_timeout_sec,
    }
    invalid = [name for name, value in positive.items() if value <= 0]
    if args.pull_jitter_sec < 0:
        invalid.append("--pull-jitter-sec")
    if invalid:
        raise FreezeError(f"values must be positive: {', '.join(invalid)}")
    if not args.model.strip():
        raise FreezeError("--model must not be empty")
    if args.llm_total_budget_sec < args.fallback_timeout_sec:
        raise FreezeError(
            "--llm-total-budget-sec must be at least --fallback-timeout-sec"
        )
    if args.stream_transport_retries != 2:
        raise FreezeError(
            "this frozen rerun requires exactly 2 stream transport retries"
        )


def default_runner_files(root: Path, task_list: Path) -> list[Path]:
    package = root / "astra" / "runners" / "astra_terminal_bench"
    paths = [
        package / "agent.py",
        package / "stream_transport_retry.py",
        package / "trajectory_export.py",
        package / "c0-four-cases.yaml",
        package / "host-docker-internal.compose.yaml",
        package / "model-c5bde5de.freeze.json",
        Path(__file__).resolve(),
        task_list,
    ]
    rerun_driver = (
        root
        / "astra"
        / "runners"
        / "scripts"
        / "astra-terminal-bench-rerun-33-c0.sh"
    )
    if rerun_driver.is_file():
        paths.append(rerun_driver)
    return paths


def static_plan(args: argparse.Namespace) -> tuple[
    list[str],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
]:
    validate_args(args)
    names = load_task_names(args.task_list)
    tasks = prepare_tasks(
        args.tasks_dir,
        names,
        product_timeout_multiplier=args.product_timeout_multiplier,
        harbor_agent_timeout_multiplier=args.agent_timeout_multiplier,
        harbor_verifier_timeout_multiplier=args.verifier_timeout_multiplier,
        harbor_agent_setup_timeout_multiplier=(
            args.agent_setup_timeout_multiplier
        ),
        harbor_environment_build_timeout_multiplier=(
            args.environment_build_timeout_multiplier
        ),
        harbor_agent_setup_base_timeout_sec=args.agent_setup_base_timeout_sec,
    )
    artifacts = {
        "amd64": artifact_metadata(args.astra_amd64, "amd64"),
        "arm64": artifact_metadata(args.astra_arm64, "arm64"),
    }
    astra_server = binary_metadata(args.astra_server_binary)
    root = workspace_root()
    model_freeze = model_freeze_metadata(
        (
            root
            / "astra"
            / "runners"
            / "astra_terminal_bench"
            / "model-c5bde5de.freeze.json"
        ),
        args.model,
    )
    runner_files = runner_file_metadata(
        [*default_runner_files(root, args.task_list), *args.runner_file]
    )
    return names, tasks, artifacts, astra_server, model_freeze, runner_files


def dry_run_payload(
    args: argparse.Namespace,
    names: Sequence[str],
    tasks: Sequence[dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    astra_server: dict[str, Any],
    model_freeze: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "harbor_will_run": False,
        "docker_will_be_called": False,
        "output_will_be_written": False,
        "task_count": len(names),
        "task_names": list(names),
        "unique_images": sorted({task["configured_image"] for task in tasks}),
        "pull_policy": {
            "sequential": True,
            "max_attempts": args.pull_attempts,
            "base_delay_sec": args.pull_base_delay_sec,
            "max_delay_sec": args.pull_max_delay_sec,
            "jitter_sec": args.pull_jitter_sec,
        },
        "artifacts": artifacts,
        "astra_server_binary": astra_server,
        "model_freeze": model_freeze,
        "planned_output": str(args.output.resolve()),
    }


def freeze_manifest(
    args: argparse.Namespace,
    *,
    names: Sequence[str],
    tasks: list[dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    astra_server: dict[str, Any],
    model_freeze: dict[str, Any],
    runner_files: list[dict[str, Any]],
    docker_metadata: dict[str, Any],
    pull_images: bool,
) -> dict[str, Any]:
    images: dict[str, dict[str, Any]] = {}
    pull_results: dict[str, dict[str, Any] | None] = {}
    docker_arch = normalize_arch(str(docker_metadata.get("architecture", "")))
    for image in dict.fromkeys(task["configured_image"] for task in tasks):
        if pull_images:
            pull_results[image] = pull_image_with_retry(
                args.docker_bin,
                image,
                attempts=args.pull_attempts,
                base_delay_sec=args.pull_base_delay_sec,
                max_delay_sec=args.pull_max_delay_sec,
                jitter_sec=args.pull_jitter_sec,
            )
        else:
            pull_results[image] = None
        metadata = inspect_image(args.docker_bin, image)
        metadata["native_on_docker_server"] = (
            metadata["architecture"] == docker_arch
        )
        artifact = artifacts[metadata["architecture"]]
        metadata["astra_artifact_sha256"] = artifact["sha256"]
        metadata["astra_version_probe"] = probe_astra_version(
            args.docker_bin,
            metadata,
            artifact,
            timeout_sec=args.version_probe_timeout_sec,
        )
        metadata["astra_version_probe"]["scope"] = (
            "astra-binary-only; task runtime and native libraries are not validated"
        )
        metadata["astra_version_probe"]["native_on_docker_server"] = metadata[
            "native_on_docker_server"
        ]
        metadata["pull"] = pull_results[image]
        images[image] = metadata

    queues: dict[str, list[str]] = {
        "amd64": [],
        "arm64": [],
        "native_amd64_required": [],
    }
    blockers: list[dict[str, str]] = []
    for task in tasks:
        image_metadata = images[task["configured_image"]]
        architecture = image_metadata["architecture"]
        task["image"] = image_metadata
        task["astra_artifact"] = artifacts[architecture]
        if task["name"] == "tune-mjcf":
            queues["native_amd64_required"].append(task["name"])
        else:
            queues[architecture].append(task["name"])
        task_blockers: list[str] = []
        if (
            task["name"] == "tune-mjcf"
            and not image_metadata["native_on_docker_server"]
        ):
            reason = (
                "tune-mjcf requires a native linux/amd64 Docker server; "
                "Astra --version through emulation does not validate MuJoCo"
            )
            task_blockers.append(reason)
            blockers.append({"task": task["name"], "reason": reason})
        task["preflight"] = {
            "ready_on_this_docker_server": not task_blockers,
            "blockers": task_blockers,
        }

    root = workspace_root()
    return {
        "schema_version": 1,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "exact-33-from-scratch-c0-rerun-input-freeze",
        "harbor_tasks_started": False,
        "write_once": True,
        "freeze_scope": [
            "task-selection",
            "task-files",
            "docker-images",
            "task-permissions-and-resources",
            "astra-model",
            "execution-budgets",
            "outer-runner-files",
            "astra-linux-artifacts",
        ],
        "task_selection": {
            "manifest_path": str(args.task_list.resolve()),
            "manifest_sha256": sha256_file(args.task_list),
            "expected_count": EXPECTED_TASK_COUNT,
            "actual_count": len(names),
            "unique": len(set(names)) == EXPECTED_TASK_COUNT,
            "names": list(names),
        },
        "source_states": {
            "workspace": git_state(root),
            "terminal_bench_snapshot": git_state(args.tasks_dir),
            "external_astra": git_state(root / "external" / "astra"),
        },
        "execution": {
            "condition": "C0",
            "astra_api_url": DEFAULT_ASTRA_API_URL,
            "model": args.model,
            "model_freeze": model_freeze,
            "max_turns": args.max_turns,
            "concurrency": 1,
            "environment": {
                "type": "docker",
                "force_build": False,
                "delete": True,
                "extra_allowed_hosts": [DEFAULT_ASTRA_API_HOST],
                "extra_docker_compose": [
                    str(
                        (
                            root
                            / "astra"
                            / "runners"
                            / "astra_terminal_bench"
                            / "host-docker-internal.compose.yaml"
                        ).resolve()
                    )
                ],
            },
            "permissions": {
                "permission_mode": "auto",
                "read_memory": False,
            },
            "budgets": {
                "llm_fallback_timeout_sec": args.fallback_timeout_sec,
                "llm_total_budget_sec": args.llm_total_budget_sec,
                "stream_transport_retries": args.stream_transport_retries,
                "retry_policy": {
                    "first_retry_guaranteed": True,
                    "additional_retries_require_remaining_budget": True,
                    "optional_retry_min_remaining_seconds": (
                        args.optional_retry_min_remaining_sec
                    ),
                },
                "product_timeout_multiplier": args.product_timeout_multiplier,
                "harbor_timeout_multipliers": {
                    "timeout_multiplier": args.timeout_multiplier,
                    "agent_timeout_multiplier": args.agent_timeout_multiplier,
                    "verifier_timeout_multiplier": (
                        args.verifier_timeout_multiplier
                    ),
                    "agent_setup_timeout_multiplier": (
                        args.agent_setup_timeout_multiplier
                    ),
                    "environment_build_timeout_multiplier": (
                        args.environment_build_timeout_multiplier
                    ),
                },
            },
        },
        "pull_policy": {
            "sequential": True,
            "max_attempts": args.pull_attempts,
            "base_delay_sec": args.pull_base_delay_sec,
            "max_delay_sec": args.pull_max_delay_sec,
            "jitter_sec": args.pull_jitter_sec,
        },
        "docker_server": docker_metadata,
        "preflight": {
            "ready_to_run_all_tasks_on_this_docker_server": not blockers,
            "blockers": blockers,
        },
        "astra_server_binary": astra_server,
        "astra_artifacts": artifacts,
        "runner_files": runner_files,
        "images": images,
        "queues_by_architecture": queues,
        "tasks": tasks,
    }


def write_manifest_once(path: Path, manifest: dict[str, Any]) -> str:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise FreezeError(
            f"refusing to overwrite frozen manifest: {path}; choose a new --output"
        ) from exc
    return sha256_text(payload)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        (
            names,
            tasks,
            artifacts,
            astra_server,
            model_freeze,
            runner_files,
        ) = static_plan(args)
        if args.dry_run:
            print(
                json.dumps(
                    dry_run_payload(
                        args,
                        names,
                        tasks,
                        artifacts,
                        astra_server,
                        model_freeze,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        rerun_driver = (
            workspace_root()
            / "astra"
            / "runners"
            / "scripts"
            / "astra-terminal-bench-rerun-33-c0.sh"
        )
        if not rerun_driver.is_file() and not args.runner_file:
            raise FreezeError(
                "the rerun driver does not exist yet; pass its final path with "
                "--runner-file so the frozen manifest binds its SHA-256"
            )
        docker_metadata = docker_server_metadata(args.docker_bin)
        manifest = freeze_manifest(
            args,
            names=names,
            tasks=tasks,
            artifacts=artifacts,
            astra_server=astra_server,
            model_freeze=model_freeze,
            runner_files=runner_files,
            docker_metadata=docker_metadata,
            pull_images=not args.check,
        )
        if args.check:
            summary = {
                "mode": "check",
                "harbor_tasks_started": False,
                "docker_images_pulled": False,
                "output_written": False,
                "task_count": len(names),
                "queues_by_architecture": manifest["queues_by_architecture"],
                "images_ready": len(manifest["images"]),
                "preflight": manifest["preflight"],
            }
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0 if manifest["preflight"][
                "ready_to_run_all_tasks_on_this_docker_server"
            ] else 3

        output_sha256 = write_manifest_once(args.output, manifest)
        print(
            json.dumps(
                {
                    "mode": "freeze",
                    "harbor_tasks_started": False,
                    "task_count": len(names),
                    "output": str(args.output.resolve()),
                    "output_sha256": output_sha256,
                    "queues_by_architecture": manifest["queues_by_architecture"],
                    "preflight": manifest["preflight"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        # Freezing succeeds even when a special queue is not runnable here.
        # The frozen preflight blocker is enforced by the execution driver.
        return 0
    except FreezeError as exc:
        print(f"freeze preflight failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
