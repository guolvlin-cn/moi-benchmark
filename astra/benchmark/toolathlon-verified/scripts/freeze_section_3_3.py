#!/usr/bin/env python3
"""Generate the content-addressed freeze for evaluation plan section 3.3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


FROZEN_ON = "2026-08-06"
ASTRA_COMMIT = "844473c68649d8ea43e10b616dc4fbf98e2321e8"
ASTRA_TREE = "bfd88d2fe30ad7a04b2611a42c70d5dc993280bf"
HERMES_COMMIT = "f4df260f26c93f15694698869f3ea8e965eea301"
HERMES_TREE = "40f0136a9995a9a1712a3ab28c231a2812748cdf"
TASK_COUNT = 108
TIER_DEADLINES = {"R1": 1800, "R2": 2700, "R3": 3600, "R4": 5400}
EXPECTED_TIER_COUNTS = {"R1": 8, "R2": 15, "R3": 11, "R4": 74}
SMOKE_TASKS = [
    "find-alita-paper",
    "set-conf-cr-ddl",
    "course-schedule",
    "canvas-homework-grader-python",
    "arrange-workspace",
    "notion-movies",
    "price-comparison",
    "quantitative-financial-analysis",
    "excel-data-transformation",
    "notion-hr",
    "shopping-helper",
    "woocommerce-stock-alert",
    "git-bug-hunt",
    "k8s-safety-audit",
]
FIRST_BATCH_SYSTEM_ORDERS = [
    ["astra", "hermes"] if position % 2 == 1 else ["hermes", "astra"]
    for position in range(1, len(SMOKE_TASKS) + 1)
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_git(source: Path, *args: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=not allow_failure,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode and not allow_failure:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": relative(path, root),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def executable_record(path: Path, root: Path, *, require_elf_amd64: bool) -> dict[str, Any]:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f"frozen executable is unavailable: {path}")
    if path.is_symlink():
        base_record = {
            "path": path.absolute().relative_to(root.absolute()).as_posix(),
            "resolved_path": str(path.resolve()),
            "symlink_target": os.readlink(path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    else:
        base_record = file_record(path, root)
    record = {
        **base_record,
        "mode": oct(path.stat().st_mode & 0o777),
        "executable": True,
    }
    if not require_elf_amd64:
        return record
    with path.open("rb") as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:5] != b"\x7fELF\x02":
        raise RuntimeError(f"frozen executable is not ELF64: {path}")
    byte_order = "little" if header[5] == 1 else "big" if header[5] == 2 else ""
    if not byte_order:
        raise RuntimeError(f"frozen executable has an unknown ELF byte order: {path}")
    machine = int.from_bytes(header[18:20], byteorder=byte_order)
    if machine != 62:
        raise RuntimeError(f"frozen executable is not Linux/amd64 ELF: {path}")
    record.update(
        {
            "format": "ELF64",
            "elf_byte_order": byte_order,
            "elf_machine": "EM_X86_64",
            "target_platform": "linux/amd64",
        }
    )
    return record


def run_command(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"command failed with exit {result.returncode}: {command[0]}: {detail}"
        )
    return result.stdout.strip()


def hash_records(source: Path, paths: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in sorted(set(paths)):
        path = source / name
        if not path.is_file():
            raise RuntimeError(f"freeze source file is missing: {path}")
        records.append(
            {
                "path": name,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return records


def assert_clean_source(source: Path, commit: str, tree: str, label: str) -> dict[str, Any]:
    if run_git(source, "rev-parse", "HEAD^{commit}") != commit:
        raise RuntimeError(f"{label} HEAD does not match frozen commit")
    if run_git(source, "rev-parse", "HEAD^{tree}") != tree:
        raise RuntimeError(f"{label} tree does not match frozen tree")
    dirty = run_git(source, "status", "--porcelain=v1")
    if dirty:
        raise RuntimeError(f"{label} freeze source must be clean")
    symbolic = run_git(source, "symbolic-ref", "-q", "--short", "HEAD", allow_failure=True)
    return {
        "commit": commit,
        "describe": run_git(source, "describe", "--tags", "--always", "--dirty"),
        "detached_head": not bool(symbolic),
        "symbolic_ref": symbolic or None,
        "tree": tree,
        "working_tree": "clean",
    }


def create_git_archive(source: Path, commit: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "archive",
            "--format=tar",
            f"--output={temporary}",
            commit,
        ],
        check=True,
    )
    os.replace(temporary, destination)


def create_deterministic_tar(root: Path, paths: list[Path], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with tarfile.open(temporary, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(paths, key=lambda item: relative(item, root)):
            name = relative(path, root)
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    os.replace(temporary, destination)


def parse_runtime_tiers(
    addendum: Path, *, expected_tasks: set[str], task_universe_path: Path
) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"^\| `(?P<task>[^`]+)` \| (?P<n>\d+) \| "
        r"(?P<median>[^|]+) \| (?P<p95>[^|]+) \| (?P<maximum>[^|]+) \| "
        r"(?P<missing>\d+) \| (?P<tier>R[1-4]) \| (?P<minutes>\d+) min \|$"
    )
    for line in addendum.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        values = match.groupdict()
        task = values["task"]
        tier = values["tier"]
        deadline = TIER_DEADLINES[tier]
        if int(values["minutes"]) * 60 != deadline:
            raise RuntimeError(f"tier minutes disagree with tier label for {task}")
        rows[task] = {
            "deadline_seconds": deadline,
            "historical_maximum": values["maximum"].strip(),
            "historical_median": values["median"].strip(),
            "historical_missing_or_timeout_records": int(values["missing"]),
            "historical_p95": values["p95"].strip(),
            "historical_records_with_duration": int(values["n"]),
            "tier": tier,
        }
    if len(rows) != TASK_COUNT:
        raise RuntimeError(f"runtime addendum yielded {len(rows)} tasks, expected {TASK_COUNT}")
    if set(rows) != expected_tasks:
        missing = sorted(expected_tasks - set(rows))
        extra = sorted(set(rows) - expected_tasks)
        raise RuntimeError(
            f"runtime tiers disagree with frozen task universe; missing={missing}, extra={extra}"
        )
    counts = Counter(item["tier"] for item in rows.values())
    if dict(sorted(counts.items())) != EXPECTED_TIER_COUNTS:
        raise RuntimeError(f"runtime tier counts are inconsistent: {counts}")
    if any(task not in rows for task in SMOKE_TASKS):
        raise RuntimeError("runtime tier table is missing a smoke task")
    per_system = sum(item["deadline_seconds"] for item in rows.values())
    smoke_per_system = sum(rows[task]["deadline_seconds"] for task in SMOKE_TASKS)
    return {
        "schema_version": "toolathlon.task-runtime-tiers.v1",
        "frozen_on": FROZEN_ON,
        "authority": {
            "document": relative(addendum, addendum.parents[3]),
            "sha256": sha256_file(addendum),
            "verification_scope": (
                "document hash plus 108-row/table internal consistency only; "
                "trajectory source data was not re-audited by this freeze"
            ),
            "task_universe": {
                "path": relative(task_universe_path, addendum.parents[3]),
                "sha256": sha256_file(task_universe_path),
            },
        },
        "budget_scope": "agent_execution_only",
        "tier_deadlines_seconds": TIER_DEADLINES,
        "tier_task_counts": EXPECTED_TIER_COUNTS,
        "tool_call_limit": None,
        "max_product_model_requests": 100,
        "tasks": dict(sorted(rows.items())),
        "slot_ceiling_seconds": {
            "smoke_per_system": smoke_per_system,
            "smoke_two_systems": smoke_per_system * 2,
            "formal_per_system": per_system,
            "formal_two_systems": per_system * 2,
        },
    }


def adapter_files(root: Path) -> list[Path]:
    runner = root / "astra/runners/toolathlon_verified"
    config = root / "astra/benchmark/toolathlon-verified/config"
    runtime = root / "astra/benchmark/toolathlon-verified/runtime"
    lifecycle_scripts = (
        root
        / "astra/benchmark/toolathlon-verified/scripts/run_minimal_e2e_pair.sh",
        root
        / "astra/benchmark/toolathlon-verified/scripts/validate_minimal_e2e_pair.py",
        root
        / "astra/benchmark/toolathlon-verified/scripts/check_astra_model_precondition.py",
        root
        / "astra/benchmark/toolathlon-verified/scripts/run_m2_first_batch.sh",
        root
        / "astra/benchmark/toolathlon-verified/scripts/validate_m2_first_batch.py",
        root
        / "astra/benchmark/toolathlon-verified/scripts/run_m3_remaining_batch.sh",
        root
        / "astra/benchmark/toolathlon-verified/scripts/validate_m3_remaining_batch.py",
        root
        / "astra/benchmark/toolathlon-verified/scripts/freeze_m1_credentials.py",
    )
    script = root / "astra/benchmark/toolathlon-verified/scripts/freeze_section_3_3.py"
    files = [
        path
        for path in runner.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]
    files.extend(path for path in config.rglob("*") if path.is_file())
    files.extend(
        path
        for path in runtime.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    files.extend(lifecycle_scripts)
    files.append(script)
    return sorted(set(files))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--astra-source", type=Path)
    parser.add_argument("--hermes-source", type=Path)
    args = parser.parse_args()

    root = (args.repo_root or Path(__file__).resolve().parents[4]).resolve()
    astra_source = (
        args.astra_source
        or root / "astra/work/toolathlon-verified/systems/astra-844473c68649"
    ).resolve()
    hermes_source = (args.hermes_source or root / "external/hermes-agent").resolve()
    freeze = root / "astra/benchmark/toolathlon-verified/freeze"
    work = root / "astra/work/toolathlon-verified/freeze-3.3"
    runtime_work = root / "astra/work/toolathlon-verified"
    addendum = root / "astra/plans/drafts/toolathlon-trajectories-runtime-budget-addendum.md"
    plan = root / "astra/plans/drafts/toolathlon-verified-astra-hermes-evaluation-plan copy.md"
    artifact_contract_path = (
        root
        / "astra/benchmark/toolathlon-verified/config/run-artifact-contract.json"
    )
    test_report_path = freeze / "adapter-test-report.json"

    astra_source_state = assert_clean_source(
        astra_source, ASTRA_COMMIT, ASTRA_TREE, "Astra"
    )
    hermes_source_state = assert_clean_source(
        hermes_source, HERMES_COMMIT, HERMES_TREE, "Hermes"
    )
    if not astra_source_state["detached_head"]:
        raise RuntimeError("Astra freeze worktree must use detached HEAD")

    astra_archive = work / f"astra-{ASTRA_COMMIT}.tar"
    hermes_archive = work / f"hermes-agent-{HERMES_COMMIT}.tar"
    create_git_archive(astra_source, ASTRA_COMMIT, astra_archive)
    create_git_archive(hermes_source, HERMES_COMMIT, hermes_archive)

    astra_dependencies = hash_records(
        astra_source,
        [
            "Cargo.lock",
            "Cargo.toml",
            "package-lock.json",
            "package.json",
            "packages/sdk/package-lock.json",
            "packages/sdk/package.json",
            "web/package-lock.json",
            "web/package.json",
        ],
    )
    astra_prompt_paths = [
        path
        for path in run_git(astra_source, "ls-files").splitlines()
        if (
            (path.startswith("crates/astra-prompts/") and path.endswith(".rs"))
            or (path.startswith("crates/runtime/src/prompts/") and path.endswith(".rs"))
            or path
            in {
                "crates/astra-cli/src/cli/command_router.rs",
                "crates/astra-cli/src/manifest_loader.rs",
            }
        )
    ]
    astra_prompts = hash_records(astra_source, astra_prompt_paths)
    astra_default_sources = hash_records(
        astra_source,
        [
            "crates/astra-cli/src/main.rs",
            "crates/astra-cli/src/cli/cli_config/cli_args.rs",
            "crates/astra-config/src/config_overlay.rs",
            "crates/astra-config/src/runtime_config.rs",
            "crates/core/src/runtime_limits.rs",
            "crates/runtime/src/turn/llm/client.rs",
            "crates/astra-server-types/src/lib.rs",
            "crates/services/src/runs.rs",
            "crates/runtime/src/server/chat_handlers.rs",
            "crates/runtime/src/server/bridge_prep.rs",
            "crates/runtime/src/server/session/session_quota.rs",
            "crates/runtime/src/server/runtime_mcp.rs",
            "crates/runtime/src/server/run/lifecycle/mod.rs",
            "crates/runtime/src/server/server_loop_host.rs",
            "crates/runtime/src/server/tool_admission.rs",
            "crates/runtime/src/server/tool_binding_projection.rs",
            "crates/astra-mcp/src/lib.rs",
            "crates/astra-mcp/src/manager.rs",
            "crates/astra-mcp/src/tools.rs",
            "crates/astra-mcp/src/types.rs",
            "crates/astra-cli/src/cli/command_router.rs",
        ],
    )

    astra_cli = astra_source / "target/release/astra"
    astra_server = astra_source / "target/release/astra-server"
    astra_cli_record = executable_record(astra_cli, root, require_elf_amd64=True)
    astra_server_record = executable_record(
        astra_server, root, require_elf_amd64=True
    )
    astra_version = run_command([str(astra_cli), "--version"])
    if not astra_version.startswith("astra "):
        raise RuntimeError("Astra CLI version probe returned an unexpected value")
    astra_runtime_path = runtime_work / "rendered-astra-runtime.json"
    write_json(
        astra_runtime_path,
        {
            "schema_version": 1,
            "source_commit": ASTRA_COMMIT,
            "source_tree": ASTRA_TREE,
            "executable": str(astra_cli),
            "executable_sha256": astra_cli_record["sha256"],
            "server_executable": str(astra_server),
            "server_executable_sha256": astra_server_record["sha256"],
            "api_url": "http://127.0.0.1:17001",
            "admin_token_env": "ASTRA_ADMIN_ACCESS_TOKEN",
            "server_mode": "shared_frozen_loopback",
            "configure_model": True,
        },
    )
    astra_freeze = {
        "schema_version": "toolathlon.system-freeze.v1",
        "system_id": "astra",
        "frozen_on": FROZEN_ON,
        "source": {
            **astra_source_state,
            "canonical_checkout": relative(astra_source, root),
            "repository": "https://github.com/matrixorigin/astra.git",
            "archive": file_record(astra_archive, root),
            "excluded_checkout": {
                "path": "external/astra",
                "reason": (
                    "working tree is dirty and contains local environment examples; "
                    "it is excluded from all benchmark build and freeze inputs"
                ),
            },
        },
        "dependency_locks": astra_dependencies,
        "product_prompt_sources": astra_prompts,
        "resolved_internal_defaults": {
            "freeze_semantics": (
                "only the source-resolved values enumerated in this object remain product "
                "defaults; common isolation, permission/no-resume, and task-scoped MCP "
                "surfacing are explicit benchmark overrides"
            ),
            "max_turns": 300,
            "turn_timeout_seconds": 300,
            "llm_transient_max_retries": 3,
            "llm_retry_base_milliseconds": 1000,
            "llm_tpm_max_retries": 5,
            "llm_total_budget_seconds_per_call": 300,
            "max_tool_retries": 2,
            "tool_retry_base_milliseconds": 500,
            "mcp_connection_max_retries": 5,
            "mcp_connection_initial_delay_milliseconds": 1000,
            "mcp_connection_max_delay_milliseconds": 30000,
            "mcp_connect_timeout_seconds": 30,
            "mcp_tool_timeout_seconds": 120,
            "max_turn_input_tokens": 200000,
            "internal_permission_default": "prompt",
            "benchmark_effective_permission_mode": "auto",
            "adapter_overrides_product_retry_values": False,
            "benchmark_overrides": {
                "permission_mode": "auto",
                "resume": False,
                "tool_surface": (
                    "the frozen Astra server receives one native /chat/stream "
                    "runtime_profile=request_scoped_runtime_mcp binding for the "
                    "current-attempt Gateway"
                ),
                "other_task_mcp_tools_allowed": False,
                "builtin_tools": "retained at the frozen product default",
            },
            "evidence": astra_default_sources,
        },
        "state_and_startup": {
            "fresh_home_per_run": True,
            "resume": False,
            "shared_frozen_loopback_server": True,
            "shared_database": True,
            "database_prefix_per_run": False,
            "product_identity": "new registered Astra user for every attempt",
            "attempt_identity_mapping": {"original": "a1", "replacement": "a2"},
            "private_identity_record": {
                "path": "product-identity.private.json",
                "mode": "0o600",
                "username_and_plaintext_password_persisted": True,
                "access_and_refresh_tokens_persisted": False,
                "publish": False,
            },
            "server_real_provider_credentials": "must be absent; record environment names only",
            "active_model_registry": "pre-provisioned deepseek-v4-flash routed to the run-local proxy",
            "runtime_model_mutation": (
                "update base_url, active and quirks only; model add and api-key update are forbidden"
            ),
            "runtime_connectivity_probe": False,
            "provider_requests_before_agent_required": 0,
            "model_fallback_chain": [],
            "session_strategy": {
                "request_session_id": "omitted",
                "creation": "native_chat_stream_auto_create_under_attempt_user",
                "observed_session_id_recorded_from_sse": True,
                "resume": False,
            },
            "task_tool_exposure": {
                "scope": "current task and attempt only",
                "source": "that attempt's live Gateway tools/list",
                "native_endpoint": "/chat/stream",
                "runtime_profile": "request_scoped_runtime_mcp",
                "binding_id": "toolathlon",
                "all_current_task_mcp_tools_required": True,
                "other_task_mcp_tools_allowed": False,
                "binding_artifact": "astra-runtime-mcp-binding.json",
                "provider_request_tool_names_and_hash_recorded": True,
            },
            "adapter_command_shape": [
                "<python>",
                "<astra-api-client>",
                "--api-url",
                "<run-local-loopback-url>",
                "--gateway-url",
                "<current-attempt-gateway-url>",
                "--model",
                "deepseek-v4-flash",
            ],
            "adapter_stdin": "exact public system and task prompts as JSON",
            "agent_loop_owner": "frozen Astra server; transport shim contains no Agent logic",
        },
        "runtime_artifacts": {
            "target_platform": "linux/amd64",
            "build_command": (
                "cargo build --release --locked -p astra-cli -p astra-runtime"
            ),
            "cli": {**astra_cli_record, "version_output": astra_version},
            "server": astra_server_record,
            "rendered_runtime_config": file_record(astra_runtime_path, root),
            "source_commit_and_tree_verified": True,
            "runtime_qualification": "go",
        },
    }
    write_json(freeze / "astra.freeze.json", astra_freeze)

    hermes_dependencies = hash_records(
        hermes_source,
        ["pyproject.toml", "uv.lock", "package.json", "package-lock.json"],
    )
    hermes_prompt_paths = [
        "agent/system_prompt.py",
        "agent/prompt_builder.py",
        "agent/agent_init.py",
        "agent/conversation_loop.py",
        "run_agent.py",
        "tools/mcp_tool.py",
        "hermes_cli/config.py",
        "hermes_cli/gateway.py",
    ]
    hermes_prompts = hash_records(hermes_source, hermes_prompt_paths)
    hermes_default_sources = hash_records(
        hermes_source,
        [
            "hermes_cli/config.py",
            "agent/agent_init.py",
            "agent/conversation_loop.py",
            "tools/mcp_tool.py",
        ],
    )
    uv_executable = shutil.which("uv")
    if not uv_executable:
        raise RuntimeError("uv is required to qualify the Hermes environment")
    hermes_venv = hermes_source / "hermes-venv"
    hermes_python = hermes_venv / "bin/python"
    hermes_executable = hermes_venv / "bin/hermes"
    hermes_python_record = executable_record(
        hermes_python, root, require_elf_amd64=True
    )
    hermes_executable_record = executable_record(
        hermes_executable, root, require_elf_amd64=False
    )
    python_probe = json.loads(
        run_command(
            [
                str(hermes_python),
                "-c",
                (
                    "import json,platform,sys; "
                    "print(json.dumps({'implementation': platform.python_implementation(), "
                    "'machine': platform.machine(), 'system': platform.system(), "
                    "'version': platform.python_version(), "
                    "'version_info': list(sys.version_info[:3])}, sort_keys=True))"
                ),
            ],
            cwd=hermes_source,
        )
    )
    version_info = tuple(int(item) for item in python_probe["version_info"])
    if not ((3, 11) <= version_info < (3, 14)):
        raise RuntimeError("Hermes environment Python is outside >=3.11,<3.14")
    if python_probe["system"] != "Linux" or python_probe["machine"] != "x86_64":
        raise RuntimeError("Hermes environment is not Linux/amd64")
    uv_version = run_command([uv_executable, "--version"])
    run_command(
        [
            uv_executable,
            "--no-cache",
            "pip",
            "check",
            "--python",
            str(hermes_python),
        ],
        cwd=hermes_source,
    )
    pip_check = "passed"
    package_inventory = run_command(
        [
            uv_executable,
            "--no-cache",
            "pip",
            "freeze",
            "--python",
            str(hermes_python),
        ],
        cwd=hermes_source,
    )
    hermes_packages_path = runtime_work / "hermes-packages.txt"
    hermes_packages_path.write_text(package_inventory + "\n", encoding="utf-8")
    hermes_environment_path = runtime_work / "hermes-environment.json"
    write_json(
        hermes_environment_path,
        {
            "schema_version": "toolathlon.hermes-environment.v1",
            "system_id": "hermes",
            "source": {
                "directory": str(hermes_source),
                "commit": HERMES_COMMIT,
                "tree": HERMES_TREE,
            },
            "python": {
                "executable": str(hermes_python),
                "version": python_probe["version"],
                "implementation": python_probe["implementation"],
                "target": "linux/amd64",
                "executable_sha256": hermes_python_record["sha256"],
            },
            "uv": {
                "executable": uv_executable,
                "version": uv_version.removeprefix("uv "),
                "sha256": sha256_file(Path(uv_executable)),
            },
            "dependency_locks": hermes_dependencies,
            "environment": {
                "path": str(hermes_venv),
                "pyvenv_cfg": file_record(hermes_venv / "pyvenv.cfg", root),
                "hermes_executable": hermes_executable_record,
                "packages": file_record(hermes_packages_path, root),
                "pip_check": pip_check,
                "lock_resolution_evidence": (
                    "uv.lock hash + complete package inventory + uv pip check"
                ),
            },
        },
    )
    hermes_runtime_path = runtime_work / "rendered-hermes-runtime.json"
    write_json(
        hermes_runtime_path,
        {
            "schema_version": 1,
            "source_commit": HERMES_COMMIT,
            "source_tree": HERMES_TREE,
            "source_dir": str(hermes_source),
            "command": [str(hermes_executable)],
            "executable_sha256": hermes_executable_record["sha256"],
            "environment_manifest": str(hermes_environment_path),
            "environment_manifest_sha256": sha256_file(hermes_environment_path),
            "gateway_startup_timeout_seconds": 600,
        },
    )
    hermes_freeze = {
        "schema_version": "toolathlon.system-freeze.v1",
        "system_id": "hermes",
        "frozen_on": FROZEN_ON,
        "source": {
            **hermes_source_state,
            "canonical_checkout": relative(hermes_source, root),
            "repository": "https://github.com/NousResearch/hermes-agent.git",
            "release_descriptor": "v2026.7.20-63-gf4df260f2",
            "project_version": "0.19.0",
            "archive": file_record(hermes_archive, root),
        },
        "dependency_locks": hermes_dependencies,
        "product_prompt_sources": hermes_prompts,
        "resolved_internal_defaults": {
            "freeze_semantics": (
                "only the source-resolved values enumerated in this object remain product "
                "defaults; common isolation, permission/no-resume, and task-scoped Gateway "
                "selection are explicit benchmark overrides"
            ),
            "max_turns": 90,
            "gateway_inactivity_timeout_seconds": 1800,
            "app_level_model_max_attempts": 3,
            "openai_sdk_low_level_max_retries": 2,
            "compression_enabled": True,
            "compression_threshold": 0.50,
            "mcp_tool_timeout_seconds": 300,
            "mcp_connect_timeout_seconds": 60,
            "mcp_initial_connect_max_retries": 3,
            "mcp_reconnect_max_retries": 5,
            "internal_approval_default": "smart",
            "benchmark_effective_approval_mode": "smart",
            "adapter_overrides_product_retry_values": False,
            "benchmark_overrides": {
                "resume": False,
                "task_gateway": "fresh single-task Gateway process per attempt",
                "other_task_mcp_tools_allowed": False,
            },
            "evidence": hermes_default_sources,
        },
        "state_and_startup": {
            "fresh_hermes_home_per_run": True,
            "resume": False,
            "random_session_id_per_attempt": True,
            "fresh_gateway_process_per_attempt": True,
            "fresh_gateway_api_key_per_attempt": True,
            "memory_provider": "",
            "true_server_user_identity": False,
            "hooks": False,
            "hooks_auto_accept": False,
            "yolo": False,
            "gateway_api": "foreground Runs API",
            "task_tool_exposure": {
                "scope": "current task and attempt only",
                "source": "that attempt's live Gateway tools/list",
                "all_current_task_mcp_tools_required": True,
                "other_task_mcp_tools_allowed": False,
                "provider_request_tool_names_and_hash_recorded": True,
            },
            "adapter_command_shape": [
                "<hermes>",
                "gateway",
                "run",
                "--no-supervise",
                "--external-supervisor",
            ],
        },
        "runtime_artifacts": {
            "target_python": ">=3.11,<3.14",
            "target_platform": "linux/amd64",
            "python": hermes_python_record,
            "python_probe": python_probe,
            "uv": {
                "path": uv_executable,
                "version": uv_version,
                "sha256": sha256_file(Path(uv_executable)),
            },
            "hermes_executable": hermes_executable_record,
            "lock_resolved_environment_manifest": file_record(
                hermes_environment_path, root
            ),
            "rendered_runtime_config": file_record(hermes_runtime_path, root),
            "source_commit_and_tree_verified": True,
            "runtime_qualification": "go",
        },
    }
    write_json(freeze / "hermes.freeze.json", hermes_freeze)

    docs_snapshot = {
        "schema_version": "deepseek.official-docs.snapshot.v1",
        "accessed_on": FROZEN_ON,
        "authority": "DeepSeek official API documentation",
        "sources": [
            {
                "url": "https://api-docs.deepseek.com/zh-cn/",
                "facts": {
                    "openai_base_url": "https://api.deepseek.com",
                    "request_model_id": "deepseek-v4-flash",
                    "current_alias_version": "DeepSeek-V4-Flash-0731",
                    "alias_calling_method_unchanged": True,
                },
            },
            {
                "url": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
                "facts": {
                    "context_length_tokens": 1000000,
                    "maximum_output_tokens": 384000,
                    "thinking_supported": True,
                    "thinking_is_default_mode": True,
                    "tool_calls_supported": True,
                },
            },
            {
                "url": "https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/",
                "facts": {
                    "thinking_default": "enabled",
                    "reasoning_effort_default": "high",
                    "ignored_in_thinking_mode": [
                        "temperature",
                        "top_p",
                        "presence_penalty",
                        "frequency_penalty",
                    ],
                    "tool_call_history_requires_reasoning_content_replay": True,
                },
            },
            {
                "url": "https://api-docs.deepseek.com/zh-cn/quick_start/rate_limit/",
                "facts": {
                    "concurrency_limit_scope": "provider account",
                    "concurrency_limit_independent_of_api_key": True,
                    "user_id_isolates": [
                        "content_safety_identity",
                        "KVCache",
                        "scheduling",
                    ],
                    "normal_account_user_ids_share_account_concurrency_limit": True,
                    "user_id_pattern": "[a-zA-Z0-9\\-_]+",
                    "user_id_max_length": 512,
                },
            },
        ],
        "snapshot_boundary": (
            "semantic facts and retrieval date are frozen; the upstream live pages are not "
            "content-addressed by DeepSeek"
        ),
    }
    write_json(freeze / "deepseek-official-docs.snapshot.json", docs_snapshot)

    model_freeze = {
        "schema_version": "toolathlon.model-freeze.v1",
        "frozen_on": FROZEN_ON,
        "endpoint": {
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "api_format": "OpenAI-compatible Chat Completions",
            "api_version": "provider current; no version path/header exposed by official docs",
            "routing": "official direct API only; no OpenRouter or product fallback",
        },
        "model": {
            "request_id": "deepseek-v4-flash",
            "documented_version": "DeepSeek-V4-Flash-0731",
            "alias_semantics": "request ID resolves to the provider's current documented 0731 version",
            "context_length_tokens": 1000000,
            "maximum_output_tokens": 384000,
            "tool_calls_supported": True,
        },
        "credential_isolation": {
            "astra_environment": "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY",
            "hermes_environment": "TOOLATHLON_DEEPSEEK_HERMES_API_KEY",
            "distinct_key_values_required": True,
            "legacy_shared_deepseek_api_key_forbidden": True,
            "orchestrator_pair_preflight": "abort before a slot if either key is missing or the values are equal",
            "selected_key_only_in_model_proxy_config": True,
            "products_receive_real_provider_keys": False,
            "evaluator_receives_real_provider_keys": False,
            "task_container_receives_real_provider_keys": False,
            "artifact_identity": "full sha256 fingerprints only; key values are redacted and scanned",
            "same_endpoint_and_model_across_keys": True,
            "provider_account_relationship": "not inferable from keys; record during credential provisioning",
        },
        "provider_request_identity": {
            "user_id_wire_behavior": "proxy removes product values and injects a frozen value",
            "user_id_derivation": "toolathlon-<system_id>-<first24hex(sha256(run_id))>",
            "cross_system_and_cross_run_user_id_overlap": False,
            "purpose": "DeepSeek content-safety identity, KVCache, and scheduling isolation",
            "account_concurrency_scope": "account-level and independent of API key",
            "separate_accounts_required_for_concurrency_quota_isolation": True,
        },
        "generation": {
            "thinking": {
                "value": "enabled",
                "wire_behavior": "sent",
                "wire_value": {"type": "enabled"},
                "source": "benchmark_override",
                "provider_default": "enabled",
            },
            "reasoning_effort": {
                "value": "max",
                "wire_behavior": "sent",
                "source": "benchmark_override",
                "provider_default": "high",
            },
            "temperature": {
                "value": 0,
                "sent": True,
                "effective": False,
                "reason": "official docs state temperature is accepted but ignored in Thinking mode",
            },
            "top_p": {"wire_behavior": "omitted", "resolved": "provider default"},
            "presence_penalty": {"wire_behavior": "omitted", "resolved": "provider default"},
            "frequency_penalty": {"wire_behavior": "omitted", "resolved": "provider default"},
            "max_output_tokens": {"wire_behavior": "omitted", "resolved": "provider default"},
            "tool_choice": {"wire_behavior": "omitted", "resolved": "provider default"},
            "parallel_tool_calls": {"wire_behavior": "omitted", "resolved": "provider default"},
            "stream": "product-native value preserved",
        },
        "wire_enforcement": {
            "local_proxy": "127.0.0.1 per run",
            "model_is_rewritten": True,
            "provider_key_visible_to_products": False,
            "provider_key_visible_to_evaluator": False,
            "provider_key_visible_to_task_container": False,
            "messages_and_tools_preserved": True,
            "thinking_override": "strip product value and send {type: enabled}",
            "reasoning_effort_override": "strip product value and send max",
            "reasoning_content_replay": (
                "product responsibility; missing replay or provider 400 is a valid product result"
            ),
        },
        "request_budget": {
            "max_product_model_requests": 100,
            "count_product_internal_retries": True,
            "count_product_planning_reflection_summary_recovery": True,
            "count_tool_calls": False,
            "tool_call_limit": None,
            "allow_request_number_100": True,
            "reject_request_number_101": True,
        },
        "official_docs_snapshot": {
            "path": "deepseek-official-docs.snapshot.json",
            "sha256": sha256_file(freeze / "deepseek-official-docs.snapshot.json"),
        },
    }
    write_json(freeze / "model.freeze.json", model_freeze)

    task_universe_path = freeze / "task-requirements.json"
    task_universe = json.loads(task_universe_path.read_text(encoding="utf-8"))
    expected_tasks = set(task_universe.get("tasks", {}))
    if len(expected_tasks) != TASK_COUNT:
        raise RuntimeError("frozen task-requirements.json does not contain 108 tasks")
    remaining_tasks = sorted(expected_tasks - set(SMOKE_TASKS))
    if len(remaining_tasks) != TASK_COUNT - len(SMOKE_TASKS):
        raise RuntimeError("the first and remaining formal task sets do not partition 108 tasks")
    runtime_tiers = parse_runtime_tiers(
        addendum,
        expected_tasks=expected_tasks,
        task_universe_path=task_universe_path,
    )
    write_json(freeze / "task-runtime-tiers.json", runtime_tiers)

    permission_freeze = {
        "schema_version": "toolathlon.permission-and-state-freeze.v1",
        "frozen_on": FROZEN_ON,
        "policy_id": "toolathlon-task-scoped-v1",
        "agent_internal_defaults": {
            "astra": {"permission": "prompt", "retries": "resolved in astra.freeze.json"},
            "hermes": {"permission": "smart", "retries": "resolved in hermes.freeze.json"},
        },
        "common_noninteractive_boundary": {
            "astra_effective_permission_mode": "auto",
            "hermes_effective_approval_mode": "smart",
            "task_gateway": "one run-local loopback /sse endpoint",
            "workspace": "one fresh task workspace; direct file approvals must resolve inside it",
            "unresolved_or_out_of_scope_approval": "deny",
            "shell_string_auto_approval_by_adapter": False,
            "external_side_effect_scope": "only credentials/tenant provisioned for the current task",
        },
        "state": {
            "fresh_product_home_per_run": True,
            "fresh_session_id_per_run": True,
            "resume": False,
            "cross_task_memory": False,
            "adapter_retry_count": 0,
            "whole_run_retry": "only pre-registered external infrastructure-invalid rule",
        },
        "rendered_run_policy": {
            "template": "../config/permission-policy.example.json",
            "dynamic_fields": ["task_scope.gateway_url", "task_scope.workspace"],
            "hash_must_be_recorded_in": "resolved-config.json",
        },
    }
    write_json(freeze / "permission-policy.freeze.json", permission_freeze)

    artifact_contract = json.loads(
        artifact_contract_path.read_text(encoding="utf-8")
    )
    execution_protocol = {
        "schema_version": "toolathlon.execution-protocol.v0.5",
        "frozen_on": FROZEN_ON,
        "authority": {
            "plan": file_record(plan, root),
            "artifact_contract": file_record(artifact_contract_path, root),
            "runtime_budget": file_record(addendum, root),
        },
        "scope": {
            "formal_task_count": 108,
            "systems": ["astra", "hermes"],
            "runs_per_system_task": 1,
            "formal_slot_count": 216,
            "workers": 1,
        },
        "qualification": {
            "independent_108_task_tools_schema_prescan": False,
            "independent_gold_evaluator_replay": False,
            "single_task": SMOKE_TASKS[0],
            "real_end_to_end_runs": [
                {"system": "astra", "count": 1},
                {"system": "hermes", "count": 1},
            ],
            "count_as_formal_when_artifact_gate_passes": True,
            "go_requires": [
                "run_validity=valid",
                "terminal_status=completed",
                "evaluator status is pass or no_pass",
                "at least one successful Agent model request",
                "zero provider requests before Agent execution",
            ],
        },
        "formal_phases": {
            "first_batch": {
                "task_count": len(SMOKE_TASKS),
                "tasks": SMOKE_TASKS,
                "system_orders": [
                    {"task_id": task_id, "systems": systems}
                    for task_id, systems in zip(
                        SMOKE_TASKS, FIRST_BATCH_SYSTEM_ORDERS
                    )
                ],
                "rerun_after_batch": False,
                "workers": 1,
                "m1_reused_effective_slots": 2,
                "new_effective_slots": 26,
                "runner": "astra/benchmark/toolathlon-verified/scripts/run_m2_first_batch.sh",
                "validator": "astra/benchmark/toolathlon-verified/scripts/validate_m2_first_batch.py",
                "resume_policy": "same batch root; validate and skip complete slots; never overwrite attempt directories",
            },
            "remaining_batch": {
                "task_count": TASK_COUNT - len(SMOKE_TASKS),
                "tasks": remaining_tasks,
                "workers": 1,
                "new_effective_slots": 188,
                "system_order_rule": "alternate_by_remaining_position_astra_first",
                "runner": "astra/benchmark/toolathlon-verified/scripts/run_m3_remaining_batch.sh",
                "validator": "astra/benchmark/toolathlon-verified/scripts/validate_m3_remaining_batch.py",
                "requires_m2_status": "GO",
                "resume_policy": "same batch root; validate and skip complete slots; never overwrite attempt directories",
            },
        },
        "per_run_lifecycle": [
            "reset",
            "fresh_task_container",
            "preprocess",
            "gateway",
            "tools_list",
            "adapter_agent",
            "evaluator",
            "complete_metric_artifacts",
            "cleanup",
            "final_artifact_hash",
        ],
        "tools_list": {
            "capture": "every_run_after_gateway_ready_before_agent",
            "raw_schema_and_content_hash_required": True,
            "exposure_scope": "current task and attempt only",
            "all_current_task_mcp_tools_required": True,
            "other_task_mcp_tools_allowed": False,
            "product_builtin_tools_retained": True,
            "astra_mechanism": (
                "submit the fresh single-task Gateway as a native /chat/stream "
                "request_scoped_runtime_mcp binding"
            ),
            "hermes_mechanism": "fresh single-task Gateway process",
            "provider_request_tool_names_and_hash_required": True,
            "provider_request_cross_task_mcp_tools_forbidden": True,
            "complete_current_task_surface_required_in_at_least_one_request": True,
        },
        "agent_model_boundary": {
            "provider_requests_before_agent": 0,
            "setup_connectivity_probes_during_scored_run": False,
            "generation_override": {
                "thinking": "enabled",
                "thinking_wire_behavior": "sent",
                "reasoning_effort": "max",
                "reasoning_effort_wire_behavior": "sent",
                "source": "benchmark_override",
            },
            "qualification_successful_model_requests_minimum": 1,
            "failed_requests_are_retained_outcomes": True,
            "post_terminal_model_drain_systems": ["astra", "hermes"],
            "post_terminal_model_drain_seconds": 120,
            "post_terminal_model_quiet_seconds": 1,
            "violation_classification": "infra_invalid/adapter_error",
        },
        "artifact_gate": {
            "required_artifacts": artifact_contract["required_artifacts"],
            "system_conditional_required_artifacts": artifact_contract[
                "system_conditional_required_artifacts"
            ],
            "raw_evidence_blocks_next_run": True,
            "aggregation_blocks_next_run": False,
            "aggregation_phase": "M4",
            "structured_missing_values_required": True,
            "zero_fill_or_inference_for_missing_provider_metrics": False,
            "native_tool_transport_start_terminal_pairing_required": True,
            "duplicate_product_tool_terminals_normalized_once": True,
            "terminal_argument_hash_inherited_from_matching_start": True,
            "astra_server_declared_tool_count_must_match_terminal_transports": True,
        },
        "retry": {
            "automatic_replacement_maximum": 1,
            "replacement_only_for_infra_invalid": True,
            "replacement_for_run_id_required": True,
            "never_retry_product_model_timeout_budget_or_evaluator_no_pass": True,
        },
    }
    write_json(freeze / "execution-protocol.freeze.json", execution_protocol)

    test_report = json.loads(test_report_path.read_text(encoding="utf-8"))
    if (
        test_report.get("status") != "waived_not_rerun_by_user_instruction"
        or test_report.get("tests_run") != 0
        or test_report.get("previous_baseline_tests_run") != 20
    ):
        raise RuntimeError("adapter test report does not record the approved test waiver")
    adapter_paths = adapter_files(root)
    adapter_archive = work / "toolathlon-verified-adapters-v1.tar"
    create_deterministic_tar(root, adapter_paths, adapter_archive)
    adapter_records = [file_record(path, root) for path in adapter_paths]
    adapter_freeze = {
        "schema_version": "toolathlon.adapter-freeze.v1",
        "frozen_on": FROZEN_ON,
        "revision": {
            "type": "content-addressed snapshot",
            "repository_base_commit": run_git(root, "rev-parse", "HEAD^{commit}"),
            "archive": file_record(adapter_archive, root),
            "reason": (
                "benchmark files are an uncommitted worktree addition; exact file hashes and a "
                "deterministic archive freeze the implementation without committing unrelated changes"
            ),
        },
        "implementation": {
            "python_dependencies": "standard library only",
            "event_schema_version": "toolathlon.adapter.events.v1",
            "model_event_schema_version": "toolathlon.model-proxy.events.v1",
            "resource_event_schema_version": "toolathlon.resource-usage.v1",
            "adapter_retry_count": 0,
            "files": adapter_records,
        },
        "interfaces": {
            "scope": "single complete Toolathlon lifecycle",
            "outer_toolathlon_lifecycle_required": False,
            "public_bundle_only": True,
            "raw_mcp_tools_list_captured_before_agent": True,
            "task_scoped_mcp_tools_only": True,
            "all_current_task_mcp_tools_exposed": True,
            "astra_native_request_scoped_runtime_mcp": True,
            "provider_request_tool_names_and_hash_validated": True,
            "thinking_wire_override": "enabled",
            "reasoning_effort_wire_override": "max",
            "generation_override_recorded_per_request": True,
            "four_way_tool_name_mapping": True,
            "native_tool_transport_events_normalized_and_paired": True,
            "duplicate_product_tool_terminals_normalized_once": True,
            "terminal_argument_hash_inherited_from_matching_start": True,
            "astra_server_declared_tool_count_validated": True,
            "post_terminal_model_drain_required": True,
            "fresh_state_no_resume": True,
            "distinct_provider_keys_preflighted": True,
            "provider_keys_stripped_from_products_and_evaluator": True,
            "provider_user_id_forced_per_system_run": True,
            "agent_deadline_starts_at_prompt_handoff": True,
            "evaluator_after_all_agent_terminal_states": True,
            "m2_first_batch_workers": 1,
            "m2_m1_formal_slots_reused": 2,
            "m2_new_effective_slots": 26,
            "m2_resume_without_overwrite": True,
            "m2_incomplete_or_unclassified_attempt_blocks": True,
            "lifecycle_task_scope": "all 108 frozen tasks",
            "per_attempt_reset": (
                "fresh product identity/home plus fresh task container/workspace; "
                "task preprocess restores task-scoped application state"
            ),
            "host_application_setup_replay": "qualification and recovery only; not per attempt",
            "container_application_credential_layout": (
                "frozen Google OAuth files are installed in the Calendar MCP home layout; "
                "Notion MCP OAuth state and the frozen OpenAPI patch are mounted only for Notion tasks"
            ),
            "runtime_refreshable_oauth_evidence": (
                "only allowlisted configs/.mcp-auth/*_tokens.json files may rotate; "
                "every attempt records before/after SHA-256 values"
            ),
            "m3_remaining_batch_workers": 1,
            "m3_new_effective_slots": 188,
            "m3_requires_m2_go": True,
            "m3_resume_without_overwrite": True,
        },
        "test_report": file_record(test_report_path, root),
        "live_runtime_qualification": {
            "status": "pending_single_task_e2e",
            "product_runtime_artifacts": "go",
            "blockers": [
                "Astra and Hermes must each pass one real find-alita-paper lifecycle artifact gate",
            ],
        },
    }
    write_json(freeze / "adapter.freeze.json", adapter_freeze)

    component_names = [
        "adapter-test-report.json",
        "adapter.freeze.json",
        "astra.freeze.json",
        "deepseek-official-docs.snapshot.json",
        "execution-protocol.freeze.json",
        "hermes.freeze.json",
        "model.freeze.json",
        "permission-policy.freeze.json",
        "task-runtime-tiers.json",
    ]
    components = {
        name: {
            "sha256": sha256_file(freeze / name),
            "size_bytes": (freeze / name).stat().st_size,
        }
        for name in component_names
    }
    section_freeze = {
        "schema_version": "toolathlon.section-3.3.freeze.v1",
        "frozen_on": FROZEN_ON,
        "decision_status": "frozen",
        "runtime_qualification": "go",
        "runtime_qualification_reason": (
            "3.3 product artifacts, rendered runtime configs, model/permission contracts, "
            "and an explicit user waiver of regression rerun are frozen; overall experiment execution still requires "
            "the independent section 3.1/3.2 and M1 gates"
        ),
        "approved_decisions": {
            "systems": "exact clean source commits/trees in astra.freeze.json and hermes.freeze.json",
            "model": "deepseek-v4-flash aliasing DeepSeek-V4-Flash-0731 via official direct API",
            "provider_credentials": (
                "Astra and Hermes use different keys selected from fixed environment names; "
                "both keys call the same official endpoint and model"
            ),
            "provider_user_id": "force a different deterministic user_id for every system/run",
            "generation_override": (
                "strip product thinking/reasoning_effort values and explicitly send "
                "thinking={type:enabled}, reasoning_effort=max on every request"
            ),
            "temperature": "send and record 0; ineffective while explicit Thinking is enabled",
            "budget_precedence": (
                "toolathlon-trajectories-runtime-budget-addendum.md hash overrides every old "
                "5400-second end-to-end statement"
            ),
            "agent_defaults": (
                "retain only the source-resolved values enumerated in each system freeze; "
                "common isolation, permission/no-resume, and task-scoped MCP exposure are "
                "explicit benchmark overrides"
            ),
            "task_tool_exposure": (
                "each attempt exposes every MCP tool returned by its current task Gateway "
                "tools/list and no MCP tools from other tasks; Astra uses its native /chat/stream "
                "request-scoped runtime MCP binding, Hermes uses a fresh single-task Gateway; "
                "frozen product built-ins remain"
            ),
            "adapter_retry_count": 0,
            "automatic_infra_replacement_maximum": 1,
            "m2_first_batch_scheduler": "single worker; M1 two-slot reuse plus 26 new effective slots",
            "m3_remaining_batch_scheduler": "single worker; 94 tasks and 188 effective slots after M2 GO",
            "reset_scope": (
                "per attempt: fresh product identity/home, fresh task container/workspace, "
                "then frozen Toolathlon task preprocess for application-state restoration; "
                "host setup replay is qualification/recovery only"
            ),
            "m2_automatic_replacement_allowlist": [
                "environment_error",
                "evaluator_error",
            ],
            "post_terminal_model_drain_systems": ["astra", "hermes"],
            "post_terminal_model_drain_seconds": 120,
            "post_terminal_model_quiet_seconds": 1,
            "tools_list_capture": "per run; no independent 108-task prescan",
            "gold_evaluator_replay": "independent qualification replay waived",
        },
        "budget": {
            "authority_sha256": sha256_file(addendum),
            "max_product_model_requests": 100,
            "tool_call_limit": None,
            "agent_deadline_tiers_seconds": TIER_DEADLINES,
        },
        "infrastructure_timeouts": {
            "preprocess_seconds": 3600,
            "gateway_readiness_seconds": 600,
            "model_proxy_readiness_seconds": 60,
            "post_terminal_model_drain_seconds": 120,
            "post_terminal_model_quiet_seconds": 1,
            "product_startup_seconds": 600,
            "evaluator_seconds": 3600,
            "app_reset_seconds": 3600,
            "cleanup_seconds": 1800,
            "artifact_finalize_seconds": 600,
            "scope": (
                "independent safety guards; none is subtracted from or added to the Agent "
                "execution deadline and none converts a product terminal state into infra-invalid"
            ),
        },
        "prompt_freeze": {
            "toolathlon_task_and_system_prompts": {
                "manifest": "task-manifest.sha256",
                "manifest_sha256": sha256_file(freeze / "task-manifest.sha256"),
            },
            "astra_product_prompt_source_count": len(astra_prompts),
            "hermes_product_prompt_source_count": len(hermes_prompts),
            "adapter_wrapper": "none; exact task/system fields are passed separately",
            "adapter_source_snapshot_sha256": sha256_file(adapter_archive),
        },
        "tool_name_semantics": {
            "gateway_and_canonical": "raw Gateway name",
            "astra": "mcp__toolathlon__ prefix; non [alnum,_,-] replaced with underscore",
            "hermes": "mcp__toolathlon__ prefix; non [A-Za-z0-9,_] replaced with underscore",
            "hyphenated_names_equal": False,
            "exposure_scope": "all and only current-task Gateway MCP tools per attempt",
            "astra_surface": (
                "all observed names discovered and installed by the frozen Astra server from "
                "the per-attempt request_scoped_runtime_mcp binding"
            ),
            "hermes_surface": "all observed names supplied by the fresh single-task Gateway",
            "provider_request_evidence": (
                "full tool-name list, count, and canonical SHA-256 per request; no request may "
                "contain another task's MCP name and at least one request must contain the "
                "complete current-task MCP set"
            ),
            "analysis_boundary": (
                "record four-way mapping; if model-visible names/schemas are not equivalent, "
                "report native-product-stack comparison rather than controlled-wrapper causality"
            ),
        },
        "components": components,
    }
    write_json(freeze / "section-3.3.freeze.json", section_freeze)

    checksum_names = [*component_names, "section-3.3.freeze.json"]
    checksum_path = freeze / "section-3.3.sha256"
    checksum_path.write_text(
        "".join(f"{sha256_file(freeze / name)}  {name}\n" for name in checksum_names),
        encoding="utf-8",
    )

    # Re-read every output and archive so a partial write cannot be reported as success.
    for name in checksum_names:
        if not (freeze / name).is_file() or not sha256_file(freeze / name):
            raise RuntimeError(f"freeze verification failed for {name}")
    for archive in (astra_archive, hermes_archive, adapter_archive):
        if not archive.is_file() or not sha256_file(archive):
            raise RuntimeError(f"archive verification failed for {archive}")

    print(
        json.dumps(
            {
                "section_3_3_manifest": relative(checksum_path, root),
                "section_3_3_manifest_sha256": sha256_file(checksum_path),
                "runtime_qualification": "go",
                "task_count": len(runtime_tiers["tasks"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
