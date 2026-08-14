#!/usr/bin/env python3
"""Capture the minimal Toolathlon M0 authority roots and qualification evidence."""

from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import platform
import pwd
import re
import subprocess
from pathlib import Path
from typing import Any


EXPECTED_TASK_IMAGE = (
    "lockon0927/toolathlon-task-image@"
    "sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f"
)
EXPECTED_BYTES_8_GIB = 8 * 1024**3
EXPECTED_CPU_COUNT = 8


def run(*command: str, check: bool = True) -> str:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(command)}: {detail}")
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_sha_manifest(path: Path) -> int:
    count = 0
    root = path.parent.resolve()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as exc:
            raise SystemExit(f"invalid checksum line in {path}: {line!r}") from exc
        candidate = (root / relative).resolve()
        if candidate.parent != root or not candidate.is_file():
            raise SystemExit(f"unsafe or missing checksum target: {candidate}")
        if sha256_file(candidate) != digest:
            raise SystemExit(f"checksum mismatch: {candidate}")
        count += 1
    if count == 0:
        raise SystemExit(f"empty checksum manifest: {path}")
    return count


def read_os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([^:]+):\s+(\d+)\s+kB", line)
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    return values


def firmware_memory_bytes() -> tuple[int | None, str | None]:
    output = run("sudo", "dmesg", check=False)
    matches = re.findall(r"Memory:\s+\d+K/(\d+)K available", output)
    if not matches:
        return None, None
    kib = int(matches[-1])
    line = next(
        item.strip()
        for item in reversed(output.splitlines())
        if re.search(r"Memory:\s+\d+K/\d+K available", item)
    )
    return kib * 1024, line


def stat_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "mode": oct(stat.st_mode & 0o777),
        "owner": pwd.getpwuid(stat.st_uid).pw_name,
        "group": grp.getgrgid(stat.st_gid).gr_name,
        "sha256": sha256_file(path) if path.is_file() and stat.st_size < 1024**2 else None,
    }


def parse_swap() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    lines = Path("/proc/swaps").read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 5:
            continue
        records.append(
            {
                "path": fields[0],
                "type": fields[1],
                "usable_size_bytes": int(fields[2]) * 1024,
                "used_bytes_at_capture": int(fields[3]) * 1024,
                "priority": int(fields[4]),
            }
        )
    selected = next((item for item in records if item["path"] == "/swapfile"), None)
    if selected is None:
        selected = {
            "path": "/swapfile",
            "type": None,
            "usable_size_bytes": 0,
            "used_bytes_at_capture": 0,
            "priority": None,
        }
    swapfile = Path("/swapfile")
    selected["allocated_size_bytes"] = swapfile.stat().st_size if swapfile.is_file() else 0
    selected["size_bytes"] = selected["allocated_size_bytes"]
    selected["file"] = stat_record(swapfile) if swapfile.is_file() else {"path": "/swapfile"}
    selected["enabled"] = any(item["path"] == "/swapfile" for item in records)
    selected["zram_enabled"] = any(
        item["path"].startswith("/dev/zram") for item in records
    ) or any(Path("/sys/block").glob("zram*"))
    selected["vm_swappiness"] = int(run("sysctl", "-n", "vm.swappiness"))
    selected["cgroup_memory_swap_max_bytes"] = EXPECTED_BYTES_8_GIB
    fstab_lines = Path("/etc/fstab").read_text(encoding="utf-8").splitlines()
    selected["persistent_fstab_entry"] = next(
        (line for line in fstab_lines if line.split()[:1] == ["/swapfile"]), None
    )
    selected["persistent_configuration"] = [
        stat_record(Path("/etc/sysctl.d/99-toolathlon-benchmark.conf")),
        stat_record(Path("/etc/modprobe.d/99-toolathlon-disable-zram.conf")),
    ]
    return selected


def cgroup_probe() -> dict[str, Any]:
    command = [
        "sudo",
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=8g",
        "--memory-swap=16g",
        "--cpus=8",
        "--entrypoint=/bin/sh",
        EXPECTED_TASK_IMAGE,
        "-c",
        (
            "printf 'memory.max='; cat /sys/fs/cgroup/memory.max; "
            "printf 'memory.swap.max='; cat /sys/fs/cgroup/memory.swap.max; "
            "printf 'cpu.max='; cat /sys/fs/cgroup/cpu.max; "
            "printf 'controllers='; cat /sys/fs/cgroup/cgroup.controllers"
        ),
    ]
    output = run(*command)
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value.strip()
    return {
        "image": EXPECTED_TASK_IMAGE,
        "network": "none",
        "ephemeral_container_removed": True,
        "requested": {
            "cpu_count": 8,
            "memory_max_bytes": EXPECTED_BYTES_8_GIB,
            "memory_swap_max_bytes": EXPECTED_BYTES_8_GIB,
        },
        "observed": {
            "memory_max_bytes": int(values["memory.max"]),
            "memory_swap_max_bytes": int(values["memory.swap.max"]),
            "cpu_max": values["cpu.max"],
            "controllers": values["controllers"].split(),
        },
    }


def timedate_state() -> dict[str, Any]:
    values: dict[str, str] = {}
    output = run(
        "timedatectl",
        "show",
        "--property=Timezone",
        "--property=NTPSynchronized",
        "--property=NTP",
        "--property=LocalRTC",
    )
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return {
        "timezone": values.get("Timezone"),
        "ntp_enabled": values.get("NTP") == "yes",
        "ntp_synchronized": values.get("NTPSynchronized") == "yes",
        "rtc_in_local_timezone": values.get("LocalRTC") == "yes",
        "ntp_service": "systemd-timesyncd.service",
        "ntp_service_enabled": run(
            "systemctl", "is-enabled", "systemd-timesyncd.service", check=False
        )
        == "enabled",
        "ntp_service_active": run(
            "systemctl", "is-active", "systemd-timesyncd.service", check=False
        )
        == "active",
        "wall_clock": "CLOCK_REALTIME",
        "monotonic_clock": "CLOCK_MONOTONIC/time.monotonic_ns",
        "kernel_clocksource": Path(
            "/sys/devices/system/clocksource/clocksource0/current_clocksource"
        ).read_text(encoding="utf-8").strip(),
    }


def disk_state(path: Path) -> dict[str, Any]:
    fields = run("findmnt", "-n", "-T", str(path), "-o", "SOURCE,FSTYPE,TARGET").split()
    stat = os.statvfs(path)
    return {
        "path": str(path),
        "source": fields[0],
        "filesystem": fields[1],
        "mountpoint": fields[2],
        "total_bytes": stat.f_frsize * stat.f_blocks,
        "available_bytes_at_capture": stat.f_frsize * stat.f_bavail,
    }


def build_vm_freeze(
    *, freeze_dir: Path, captured_at: str, cgroup: dict[str, Any]
) -> dict[str, Any]:
    os_release = read_os_release()
    meminfo = read_meminfo()
    firmware_bytes, firmware_evidence = firmware_memory_bytes()
    swap = parse_swap()
    clock = timedate_state()
    workspace_disk = disk_state(freeze_dir)
    container_runtime_path = freeze_dir / "container-runtime-manifest.json"
    container_runtime = read_json(container_runtime_path)
    docker_root = Path(container_runtime["docker"]["docker_root_dir"])
    docker_disk = disk_state(docker_root)

    checks = {
        "architecture_linux_amd64": platform.system() == "Linux"
        and platform.machine() == "x86_64",
        "cpu_count_is_8": os.cpu_count() == EXPECTED_CPU_COUNT,
        "firmware_memory_is_8_gib": firmware_bytes is not None
        and abs(firmware_bytes - EXPECTED_BYTES_8_GIB) <= 1024**2,
        "docker_runtime_frozen": container_runtime.get("state") == "frozen",
        "task_image_runtime_verified": container_runtime.get(
            "task_image_runtime_verification", {}
        ).get("verified")
        is True,
        "cgroup_v2": run("stat", "-fc", "%T", "/sys/fs/cgroup") == "cgroup2fs",
        "cgroup_cpu_memory_controllers": {"cpu", "memory"}.issubset(
            set(cgroup["observed"]["controllers"])
        ),
        "task_memory_max_is_8_gib": cgroup["observed"]["memory_max_bytes"]
        == EXPECTED_BYTES_8_GIB,
        "task_memory_swap_max_is_8_gib": cgroup["observed"][
            "memory_swap_max_bytes"
        ]
        == EXPECTED_BYTES_8_GIB,
        "swap_enabled": swap["enabled"] is True,
        "swap_is_regular_file": swap["type"] == "file",
        "swap_allocated_size_is_8_gib": swap["allocated_size_bytes"]
        == EXPECTED_BYTES_8_GIB,
        "swap_priority_is_minus_2": swap["priority"] == -2,
        "swappiness_is_10": swap["vm_swappiness"] == 10,
        "zram_disabled": swap["zram_enabled"] is False,
        "swap_persistent": swap["persistent_fstab_entry"]
        == "/swapfile none swap sw 0 0",
        "timezone_is_utc": clock["timezone"] == "Etc/UTC",
        "ntp_synchronized": clock["ntp_synchronized"] is True,
        "rtc_is_utc": clock["rtc_in_local_timezone"] is False,
    }
    qualification = "GO" if all(checks.values()) else "NO_GO"
    return {
        "schema_version": "toolathlon.vm.freeze.v1",
        "captured_at": captured_at,
        "qualification": qualification,
        "qualification_checks": checks,
        "host": {
            "distribution": os_release.get("PRETTY_NAME"),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "virtualization": run("systemd-detect-virt", check=False) or "none",
            "cpu_count": os.cpu_count(),
            "memory": {
                "plan_nominal_bytes": EXPECTED_BYTES_8_GIB,
                "firmware_reported_bytes": firmware_bytes,
                "linux_memtotal_bytes": meminfo.get("MemTotal"),
                "firmware_evidence": firmware_evidence,
            },
        },
        "disk": {
            "workspace": workspace_disk,
            "docker_root": docker_disk,
            "docker_root_path": str(docker_root),
        },
        "swap": swap,
        "cgroup": {
            "version": 2,
            "host_controllers": Path("/sys/fs/cgroup/cgroup.controllers")
            .read_text(encoding="utf-8")
            .split(),
            "task_limit_probe": cgroup,
        },
        "time": clock,
        "randomness": {
            "python_hash_seed": 0,
            "preprocess_seed_override": None,
            "policy": "preserve task-source fixed seeds bound by task-manifest.sha256",
            "known_source_seed_values": [7, 42],
        },
        "oom_evidence_contract": {
            "sources": [
                "cgroup-v2 memory.events and memory.events.local",
                "Docker inspect State.OOMKilled and container exit code",
                "kernel journal for the run monotonic interval",
                "per-second VM/container/Adapter resource samples",
            ],
            "classification": {
                "product_or_adapter_cgroup": "valid/product_resource_exhausted",
                "shared_task_container_preprocess_gateway_or_evaluator": (
                    "infra_invalid/infra_resource_exhausted"
                ),
            },
        },
        "resource_policy": {
            "workers": 1,
            "sample_interval_seconds": 1,
            "other_build_training_or_benchmark_workloads_during_scored_runs": "forbidden",
        },
    }


def file_ref(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def build_experiment_freeze(
    *, freeze_dir: Path, captured_at: str, vm_path: Path, generator_path: Path
) -> dict[str, Any]:
    sections_31_32 = freeze_dir / "sections-3.1-3.2.sha256"
    section_33 = freeze_dir / "section-3.3.sha256"
    count_31_32 = verify_sha_manifest(sections_31_32)
    count_33 = verify_sha_manifest(section_33)

    section_31 = read_json(freeze_dir / "section-3.1.freeze.json")
    section_32 = read_json(freeze_dir / "section-3.2.freeze.json")
    section_33_root = read_json(freeze_dir / "section-3.3.freeze.json")
    vm = read_json(vm_path)
    model = read_json(freeze_dir / "model.freeze.json")
    astra = read_json(freeze_dir / "astra.freeze.json")
    hermes = read_json(freeze_dir / "hermes.freeze.json")
    tiers = read_json(freeze_dir / "task-runtime-tiers.json")
    protocol = read_json(freeze_dir / "execution-protocol.freeze.json")
    formal_phases = protocol.get("formal_phases", {})
    first_batch = formal_phases.get("first_batch", {})
    remaining_batch = formal_phases.get("remaining_batch", {})
    first_tasks = first_batch.get("tasks", [])
    remaining_tasks = remaining_batch.get("tasks", [])
    first_system_orders = first_batch.get("system_orders", [])

    checks = {
        "section_3_1_3_2_checksum_root_valid": count_31_32 >= 1,
        "section_3_3_checksum_root_valid": count_33 >= 1,
        "task_count_is_108": section_31.get("tasks", {}).get("count") == 108,
        "toolathlon_source_clean_and_detached": section_31.get("source", {}).get("clean")
        is True
        and section_31.get("source", {}).get("detached_head") is True,
        "all_image_digests_resolved": section_32.get("auxiliary_images", {}).get(
            "unresolved_count"
        )
        == 0,
        "task_image_runtime_verified": section_32.get("task_image", {}).get(
            "docker_runtime_verified"
        )
        is True,
        "section_3_3_runtime_qualified": section_33_root.get("runtime_qualification")
        == "go",
        "astra_runtime_qualified": astra.get("runtime_artifacts", {}).get(
            "runtime_qualification"
        )
        == "go",
        "hermes_runtime_qualified": hermes.get("runtime_artifacts", {}).get(
            "runtime_qualification"
        )
        == "go",
        "vm_qualified": vm.get("qualification") == "GO",
        "formal_phase_task_partition_is_14_plus_94": (
            len(first_tasks) == 14
            and len(remaining_tasks) == 94
            and len(set(first_tasks) | set(remaining_tasks)) == 108
            and not (set(first_tasks) & set(remaining_tasks))
        ),
        "formal_phase_system_order_is_frozen": (
            len(first_system_orders) == 14
            and all(
                isinstance(item, dict)
                and item.get("task_id") == task_id
                and item.get("systems")
                in (["astra", "hermes"], ["hermes", "astra"])
                for item, task_id in zip(first_system_orders, first_tasks)
            )
            and sum(
                item.get("systems", [None])[0] == "astra"
                for item in first_system_orders
                if isinstance(item, dict)
            )
            == 7
            and sum(
                item.get("systems", [None])[0] == "hermes"
                for item in first_system_orders
                if isinstance(item, dict)
            )
            == 7
            and remaining_batch.get("system_order_rule")
            == "alternate_by_remaining_position_astra_first"
        ),
    }
    m0_status = "GO" if all(checks.values()) else "NO_GO"
    return {
        "schema_version": "toolathlon.experiment.freeze.v1",
        "captured_at": captured_at,
        "benchmark": {
            "id": "toolathlon-verified",
            "source_commit": section_31["source"]["commit"],
            "source_tree": section_31["source"]["tree"],
            "task_split": section_31["tasks"]["split"],
            "task_count": section_31["tasks"]["count"],
            "task_manifest_sha256": section_31["tasks"]["sha256_manifest"]["sha256"],
        },
        "minimal_authority_roots": {
            "sections_3_1_3_2": {
                **file_ref(sections_31_32),
                "verified_entry_count": count_31_32,
            },
            "section_3_3": {
                **file_ref(section_33),
                "verified_entry_count": count_33,
            },
            "vm": file_ref(vm_path),
        },
        "generator": {
            "path": generator_path.relative_to(generator_path.parents[4]).as_posix(),
            "sha256": sha256_file(generator_path),
        },
        "m0_qualification": {
            "status": m0_status,
            "checks": checks,
            "scope": (
                "immutable benchmark/system/model inputs, resolved execution contract, "
                "and qualification-host evidence"
            ),
        },
        "systems": {
            "astra": {
                "commit": astra["source"]["commit"],
                "tree": astra["source"]["tree"],
                "cli_sha256": astra["runtime_artifacts"]["cli"]["sha256"],
                "server_sha256": astra["runtime_artifacts"]["server"]["sha256"],
                "runtime_config_sha256": astra["runtime_artifacts"][
                    "rendered_runtime_config"
                ]["sha256"],
                "product_identity": astra["state_and_startup"]["product_identity"],
                "database_prefix_per_run": astra["state_and_startup"][
                    "database_prefix_per_run"
                ],
            },
            "hermes": {
                "commit": hermes["source"]["commit"],
                "tree": hermes["source"]["tree"],
                "version": hermes["source"]["project_version"],
                "python": hermes["runtime_artifacts"]["python_probe"]["version"],
                "executable_sha256": hermes["runtime_artifacts"]["hermes_executable"][
                    "sha256"
                ],
                "runtime_config_sha256": hermes["runtime_artifacts"][
                    "rendered_runtime_config"
                ]["sha256"],
            },
        },
        "model": {
            "provider": model["endpoint"]["provider"],
            "base_url": model["endpoint"]["base_url"],
            "request_id": model["model"]["request_id"],
            "documented_version": model["model"]["documented_version"],
            "temperature": model["generation"]["temperature"],
            "thinking": model["generation"]["thinking"],
            "reasoning_effort": model["generation"]["reasoning_effort"],
            "credential_contract": {
                "astra_environment": model["credential_isolation"]["astra_environment"],
                "hermes_environment": model["credential_isolation"]["hermes_environment"],
                "distinct_values_required": True,
                "same_endpoint_and_model": True,
                "secret_values_or_fingerprints_in_m0": False,
                "storage": "runtime-only Model Proxy configuration",
            },
        },
        "execution": {
            "workers": 1,
            "formal_repetitions_per_system_task": 1,
            "task_order": (
                "M2 uses the frozen 14-task first-batch order; M3 uses the lexicographically "
                "sorted remaining 94 tasks"
            ),
            "system_order": (
                "M2 freezes each task order explicitly; M3 alternates by remaining-batch "
                "position with Astra first on odd positions; each system runs first on 54 tasks overall"
            ),
            "fresh_state_per_system_task": True,
            "attempt_identity": {
                "astra": "new registered product user per attempt; original=a1, replacement=a2",
                "hermes": "fresh HERMES_HOME, random session_id, new Gateway/API key per attempt",
                "deepseek_provider_user_id_is_separate": True,
            },
            "product_resume": False,
            "scheduler_resume": (
                "same batch root validates and skips complete slots without overwriting attempts"
            ),
            "python_hash_seed": 0,
            "agent_deadline_tiers_seconds": tiers["tier_deadlines_seconds"],
            "max_product_model_requests": tiers["max_product_model_requests"],
            "tool_call_limit": tiers["tool_call_limit"],
            "budget_authority_sha256": tiers["authority"]["sha256"],
            "infrastructure_timeouts": section_33_root["infrastructure_timeouts"],
        },
        "result_contract": {
            "directory": "runs/<system>/<task_id>/<run_id>/",
            "required_at_finalization": [
                "resolved-config.json",
                "lifecycle-events.jsonl",
                "adapter-events.jsonl",
                "trajectory.jsonl",
                "tool-calls.jsonl",
                "model-usage.jsonl",
                "resource-usage.jsonl",
                "evaluator/eval_res.json",
                "evaluator/eval.log",
                "failure-evidence.json",
                "run.json",
                "artifacts.sha256",
            ],
            "tools_list_capture": "per run after Gateway ready; no independent prescan",
            "raw_evidence_blocks_next_run": True,
            "aggregation_deferred_to": "M4",
            "enums": {
                "verify_status": ["pass", "no_pass", "unavailable"],
                "terminal_status": [
                    "completed",
                    "failed",
                    "max_steps",
                    "timeout",
                    "interrupted",
                    "crashed",
                ],
                "timeout_scope": [
                    "none",
                    "preprocess",
                    "gateway",
                    "model",
                    "tool",
                    "agent",
                    "evaluator",
                    "cleanup",
                ],
                "run_validity": ["valid", "infra_invalid"],
            },
        },
        "failure_and_rerun_policy": {
            "one_primary_failure_category": True,
            "priority_high_to_low": [
                "infra_resource_exhausted",
                "environment_error",
                "evaluator_error",
                "adapter_error",
                "product_resource_exhausted",
                "agent_deadline",
                "model_request_budget",
                "llm_request_timeout",
                "stream_transport_error",
                "model_error",
                "tool_error",
                "product_error",
                "completed_but_no_pass",
                "none",
            ],
            "replacement_allowed_only_when": (
                "run_validity=infra_invalid and independent evidence places the cause "
                "outside both products' experiment fault domain"
            ),
            "never_rerun_for": [
                "product failure",
                "model failure",
                "agent or model timeout",
                "model request budget",
                "evaluator no_pass",
            ],
            "evidence_retention": (
                "retain original run, replacement run, reason, mapping, logs, and hashes"
            ),
            "automatic_replacement_maximum": 1,
        },
        "m1_live_qualification": {
            "status": "PENDING",
            "not_part_of_m0_freeze": True,
            "required_before_m2": [
                "use the frozen application credential fingerprints and two distinct DeepSeek keys",
                "reference the already-qualified local application baseline and reset replay",
                "pass one complete find-alita-paper lifecycle with Astra",
                "reset and pass one complete find-alita-paper lifecycle with Hermes",
                "pass the strict per-run artifact schema and hash gate for both runs",
            ],
            "waived": [
                "independent 108-task tools/list Schema prescan",
                "independent gold/evaluator replay",
            ],
            "formal_reuse": "both qualified runs count in the first 14-task formal batch",
            "secret_policy": (
                "DeepSeek keys, Astra admin token, JWT and refresh token are never persisted; "
                "Astra attempt username and plaintext product password are the sole exception, "
                "stored in run-local product-identity.private.json mode 0600 and forbidden to publish"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--captured-at", required=True)
    parser.add_argument(
        "--reuse-vm-freeze",
        action="store_true",
        help="Reuse the existing qualified VM evidence while rebinding protocol roots",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    generator_path = Path(__file__).resolve()
    freeze_dir = repo_root / "astra/benchmark/toolathlon-verified/freeze"
    if not freeze_dir.is_dir():
        raise SystemExit(f"freeze directory does not exist: {freeze_dir}")

    vm_path = freeze_dir / "vm.freeze.json"
    if args.reuse_vm_freeze:
        if not vm_path.is_file() or read_json(vm_path).get("qualification") != "GO":
            raise SystemExit("existing VM freeze is unavailable or not qualified")
    else:
        probe = cgroup_probe()
        write_json(
            vm_path,
            build_vm_freeze(
                freeze_dir=freeze_dir,
                captured_at=args.captured_at,
                cgroup=probe,
            ),
        )
    experiment_path = freeze_dir / "experiment.freeze.json"
    write_json(
        experiment_path,
        build_experiment_freeze(
            freeze_dir=freeze_dir,
            captured_at=args.captured_at,
            vm_path=vm_path,
            generator_path=generator_path,
        ),
    )
    experiment = read_json(experiment_path)

    m0_path = freeze_dir / "m0.sha256"
    roots = [
        freeze_dir / "sections-3.1-3.2.sha256",
        freeze_dir / "section-3.3.sha256",
        vm_path,
        experiment_path,
    ]
    m0_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in roots),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "m0_qualification": experiment["m0_qualification"]["status"],
                "m1_live_qualification": experiment["m1_live_qualification"]["status"],
                "vm_qualification": read_json(vm_path)["qualification"],
                "m0_manifest": str(m0_path),
                "m0_manifest_sha256": sha256_file(m0_path),
            },
            sort_keys=True,
        )
    )
    return 0 if experiment["m0_qualification"]["status"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
