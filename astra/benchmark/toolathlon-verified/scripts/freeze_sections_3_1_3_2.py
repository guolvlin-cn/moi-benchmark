#!/usr/bin/env python3
"""Generate source-level freeze artifacts for plan sections 3.1 and 3.2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Any, Iterable


EXPECTED_COMMIT = "2aed2468858f15818acafa178518390cc4b0f5cb"
EXPECTED_TASK_COUNT = 108
TASK_IMAGE = "docker.io/lockon0927/toolathlon-task-image:1016beta"
TASK_IMAGE_DIGEST = (
    "sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f"
)

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

DECLARED_AUXILIARY_IMAGES = [
    "docker.io/lbjay/canvas-docker:latest",
    "docker.io/analogic/poste.io:2.5.5",
    "docker.io/library/mysql:8.0",
    "docker.io/library/wordpress:6.8.2-php8.2-apache",
    "docker.io/library/mysql:8.4",
    "docker.io/library/nginx:1.14",
    "docker.io/library/nginx:1.20-alpine",
    "docker.io/oliver006/redis_exporter:v1.45.0",
    "docker.io/library/nginx:1.21-alpine",
    "docker.io/library/alpine:3.20",
    "docker.io/library/busybox:1.36",
    "docker.io/nginxinc/nginx-unprivileged:1.25-alpine",
    "docker.io/prom/prometheus:v2.52.0",
    "docker.io/library/python:3.12-alpine",
    "docker.io/library/redis:7.2",
    "docker.io/library/nginx:1.25-alpine",
    "docker.io/bitnamilegacy/redis:7.2.4-debian-12-r9",
]

CORE_BUNDLE_EVALUATOR_FILES = [
    "scripts/decoupled/container_preprocess.py",
    "scripts/decoupled/container_eval.py",
    "scripts/decoupled/container_tool_gateway.py",
    "scripts/run_single_decoupled.sh",
    "scripts/containerized/task_artifact_guard.py",
    "utils/data_structures/task_config.py",
    "utils/evaluation/evaluator.py",
    "utils/evaluation/retry.py",
    "utils/general/helper.py",
    "utils/status_manager.py",
]

DEPENDENCY_FILES = [
    "uv.lock",
    "pyproject.toml",
    "package-lock.json",
    "package.json",
    "Dockerfile",
    "local_binary/github-mcp-version.txt",
    "local_binary/github-mcp-server",
]

LOCAL_TOOL_FILES = [
    "utils/roles/task_agent.py",
    "utils/aux_tools/basic.py",
    "utils/aux_tools/context_management_tools.py",
    "utils/aux_tools/history_tools.py",
    "utils/aux_tools/overlong_tool_manager.py",
    "utils/aux_tools/python_interpretor.py",
    "utils/aux_tools/web_search.py",
    "utils/openai_agents_monkey_patch/tool_name_aliases.py",
]

APP_BASELINE_FILES = [
    "configs/users_data.json",
    "configs/users_data.csv",
    "configs/ports_config.yaml",
    "global_preparation/deploy_containers.sh",
    "deployment/canvas/scripts/setup.sh",
    "deployment/k8s/scripts/setup.sh",
    "deployment/poste/scripts/setup.sh",
    "deployment/woocommerce/scripts/setup.sh",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def files_below(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


def hash_records(source: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        records.append(
            {
                "path": path.relative_to(source).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_sha_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [f"{item['sha256']}  {item['path']}" for item in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def path_state(path: Path, source: Path | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {"exists": path.exists()}
    if not path.exists():
        return state
    state["type"] = "directory" if path.is_dir() else "file"
    state["mode"] = oct(path.stat().st_mode & 0o777)
    if path.is_file():
        state["size_bytes"] = path.stat().st_size
        state["sha256"] = sha256_file(path)
    if source is not None:
        try:
            state["path"] = path.relative_to(source).as_posix()
        except ValueError:
            state["path"] = str(path)
    else:
        state["path"] = str(path)
    return state


def oci_archive_state(path: Path) -> dict[str, Any]:
    state = path_state(path)
    if not path.is_file():
        return state
    with tarfile.open(path, mode="r") as archive:
        index_member = archive.extractfile("index.json")
        if index_member is None:
            raise SystemExit(f"OCI archive has no index.json: {path}")
        index = json.load(index_member)
        manifests = index.get("manifests", [])
        if len(manifests) != 1:
            raise SystemExit(f"expected one OCI manifest, found {len(manifests)}")
        descriptor = manifests[0]
        digest = descriptor["digest"]
        algorithm, value = digest.split(":", 1)
        manifest_member = archive.extractfile(f"blobs/{algorithm}/{value}")
        if manifest_member is None:
            raise SystemExit(f"OCI manifest blob is missing: {digest}")
        manifest = json.load(manifest_member)
    state["oci_manifest"] = {
        "digest": digest,
        "media_type": descriptor.get("mediaType"),
        "size_bytes": descriptor.get("size"),
        "reference_name": descriptor.get("annotations", {}).get(
            "org.opencontainers.image.ref.name"
        ),
        "config_digest": manifest.get("config", {}).get("digest"),
        "layer_count": len(manifest.get("layers", [])),
        "layer_size_bytes": sum(item.get("size", 0) for item in manifest.get("layers", [])),
    }
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-at", required=True)
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--task-image-archive", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    commit = run_git(source, "rev-parse", "HEAD")
    if commit != EXPECTED_COMMIT:
        raise SystemExit(f"unexpected Toolathlon commit: {commit}")
    if run_git(source, "status", "--porcelain"):
        raise SystemExit("Toolathlon source checkout is dirty")
    branch = run_git(source, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "HEAD":
        raise SystemExit(f"Toolathlon checkout is not detached: {branch}")

    task_root = source / "tasks" / "finalpool"
    task_ids = sorted(path.name for path in task_root.iterdir() if path.is_dir())
    if len(task_ids) != EXPECTED_TASK_COUNT:
        raise SystemExit(f"expected 108 tasks, found {len(task_ids)}")
    missing_configs = [
        task_id for task_id in task_ids if not (task_root / task_id / "task_config.json").is_file()
    ]
    if missing_configs:
        raise SystemExit(f"tasks missing task_config.json: {missing_configs}")
    unknown_smoke = sorted(set(SMOKE_TASKS) - set(task_ids))
    if unknown_smoke:
        raise SystemExit(f"unknown smoke tasks: {unknown_smoke}")

    task_records = hash_records(source, files_below(task_root))
    task_sha_path = output / "task-manifest.sha256"
    write_sha_manifest(task_sha_path, task_records)

    requirements: dict[str, Any] = {}
    all_servers: set[str] = set()
    all_local_tools: set[str] = set()
    for task_id in task_ids:
        config_path = task_root / task_id / "task_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        servers = config.get("needed_mcp_servers", [])
        local_tools = config.get("needed_local_tools", [])
        if not isinstance(servers, list) or not isinstance(local_tools, list):
            raise SystemExit(f"invalid task requirements: {task_id}")
        requirements[task_id] = {
            "mcp_servers": servers,
            "local_tools": local_tools,
            "task_config_sha256": sha256_file(config_path),
        }
        all_servers.update(servers)
        all_local_tools.update(local_tools)

    requirement_payload = {
        "schema_version": 1,
        "source_commit": commit,
        "task_count": len(task_ids),
        "mcp_servers": sorted(all_servers),
        "local_tools": sorted(all_local_tools),
        "tasks": requirements,
    }
    requirement_path = output / "task-requirements.json"
    write_json(requirement_path, requirement_payload)

    core_records = hash_records(source, [source / path for path in CORE_BUNDLE_EVALUATOR_FILES])
    task_evaluator_paths = [
        path for path in files_below(task_root) if "evaluation" in path.relative_to(task_root).parts
    ]
    evaluator_records = hash_records(source, task_evaluator_paths)
    evaluator_sha_path = output / "evaluator-manifest.sha256"
    write_sha_manifest(evaluator_sha_path, core_records + evaluator_records)

    conflict_path = task_root / "task_conflict.json"
    source_archive = (
        path_state(args.source_archive.resolve()) if args.source_archive else {"exists": False}
    )

    section_3_1 = {
        "schema_version": 1,
        "section": "3.1",
        "freeze_state": "source_frozen_runtime_qualification_no_go",
        "frozen_at": args.frozen_at,
        "source": {
            "repository": "https://github.com/hkust-nlp/Toolathlon",
            "checkout_path": str(source),
            "commit": commit,
            "tree": run_git(source, "rev-parse", "HEAD^{tree}"),
            "detached_head": True,
            "clean": True,
            "archive": source_archive,
        },
        "tasks": {
            "split": "tasks/finalpool",
            "count": len(task_ids),
            "ids": task_ids,
            "smoke_count": len(SMOKE_TASKS),
            "smoke_ids_in_order": SMOKE_TASKS,
            "task_conflict": path_state(conflict_path, source),
            "file_count": len(task_records),
            "sha256_manifest": {
                "path": task_sha_path.name,
                "sha256": sha256_file(task_sha_path),
            },
        },
        "bundle_protocol": {
            "schema_version": 2,
            "core_files": core_records,
            "trusted_resolved_task_config_required": True,
            "ground_truth_and_evaluator_hidden_from_agent": True,
        },
        "evaluator": {
            "task_evaluator_file_count": len(evaluator_records),
            "sha256_manifest": {
                "path": evaluator_sha_path.name,
                "sha256": sha256_file(evaluator_sha_path),
            },
            "allow_resume": False,
            "output_pass_values": [True, False, None],
            "whole_check_retry_default": {"max_attempts": 3, "poll_seconds": 5},
            "random_seed_policy": "no evaluator-wide seed declared by frozen source",
            "network_policy": "task-scoped policy must be resolved before runtime qualification",
        },
        "gold_replay": {
            "state": "NO_GO",
            "reason": "container runtime, application snapshots, and credentials are not configured",
        },
    }
    write_json(output / "section-3.1.freeze.json", section_3_1)

    mcp_root = source / "configs" / "mcp_servers"
    mcp_records = hash_records(source, files_below(mcp_root))
    mcp_sha_path = output / "mcp-config-manifest.sha256"
    write_sha_manifest(mcp_sha_path, mcp_records)

    dependency_records = hash_records(source, [source / path for path in DEPENDENCY_FILES])
    dependency_sha_path = output / "dependency-manifest.sha256"
    write_sha_manifest(dependency_sha_path, dependency_records)

    deployment_records = hash_records(source, files_below(source / "deployment"))
    deployment_sha_path = output / "deployment-manifest.sha256"
    write_sha_manifest(deployment_sha_path, deployment_records)

    local_tool_records = hash_records(source, [source / path for path in LOCAL_TOOL_FILES])
    app_baseline_records = hash_records(source, [source / path for path in APP_BASELINE_FILES])
    app_state_path = output / "app-state-manifest.json"
    write_json(
        app_state_path,
        {
            "schema_version": 1,
            "source_commit": commit,
            "frozen_at": args.frozen_at,
            "state": "NO_GO",
            "source_baseline_records": app_baseline_records,
            "runtime_snapshots": [],
            "reset_replay": {"state": "NO_GO", "successful_replays": 0},
            "reason": "application services, disposable tenants, and initial database snapshots are not provisioned",
        },
    )

    tool_schema_path = output / "tool-schema-manifest.json"
    write_json(
        tool_schema_path,
        {
            "schema_version": 1,
            "source_commit": commit,
            "frozen_at": args.frozen_at,
            "state": "NO_GO",
            "expected_task_count": len(task_ids),
            "required_mcp_servers": sorted(all_servers),
            "required_local_tools": sorted(all_local_tools),
            "local_tool_implementation_records": local_tool_records,
            "observed_task_schemas": [],
            "observed_task_count": 0,
            "required_observed_fields": [
                "gateway_tool_name",
                "model_visible_tool_name",
                "canonical_tool_name",
                "description",
                "input_schema",
                "required_fields",
                "order",
                "sha256",
            ],
            "reason": "runtime list_tools requires qualified services and credentials",
        },
    )

    task_image_archive = (
        oci_archive_state(args.task_image_archive.resolve())
        if args.task_image_archive
        else {"exists": False}
    )
    section_3_2 = {
        "schema_version": 1,
        "section": "3.2",
        "freeze_state": (
            "source_and_task_image_archive_frozen_runtime_no_go"
            if task_image_archive.get("exists")
            else "source_and_task_image_reference_frozen_runtime_no_go"
        ),
        "frozen_at": args.frozen_at,
        "task_image": {
            "tag_reference": TASK_IMAGE,
            "platform": {"os": "linux", "architecture": "amd64"},
            "manifest_digest": TASK_IMAGE_DIGEST,
            "immutable_reference": f"{TASK_IMAGE.split(':', 1)[0]}@{TASK_IMAGE_DIGEST}",
            "local_oci_archive": task_image_archive,
        },
        "auxiliary_images": {
            "declared_references": DECLARED_AUXILIARY_IMAGES,
            "state": "NO_GO",
            "reason": "platform manifests/digests and dynamic Kind/Helm images are not yet resolved",
        },
        "container_runtime": {
            "state": "NO_GO",
            "reason": "Docker and Podman are not installed on the qualification VM",
            "oci_transfer_tool": "skopeo",
        },
        "dependencies": {
            "records": dependency_records,
            "sha256_manifest": {
                "path": dependency_sha_path.name,
                "sha256": sha256_file(dependency_sha_path),
            },
        },
        "applications": {
            "deployment_file_count": len(deployment_records),
            "sha256_manifest": {
                "path": deployment_sha_path.name,
                "sha256": sha256_file(deployment_sha_path),
            },
            "runtime_state": "NO_GO",
            "reason": "application services and reset snapshots have not been provisioned or replayed",
            "app_state_manifest": {
                "path": app_state_path.name,
                "sha256": sha256_file(app_state_path),
            },
        },
        "credentials": {
            "secret_values_recorded": False,
            "required_runtime_files": {
                "configs/global_configs.py": path_state(source / "configs/global_configs.py", source),
                "configs/token_key_session.py": path_state(source / "configs/token_key_session.py", source),
                "~/.mcp-auth": path_state(Path.home() / ".mcp-auth"),
            },
            "state": "NO_GO",
            "policy": "disposable task accounts only; freeze identifiers/scopes/hashes, never secret values",
        },
        "mcp_and_tools": {
            "required_mcp_servers": sorted(all_servers),
            "required_local_tools": sorted(all_local_tools),
            "task_requirements": {
                "path": requirement_path.name,
                "sha256": sha256_file(requirement_path),
            },
            "mcp_config_file_count": len(mcp_records),
            "mcp_config_manifest": {
                "path": mcp_sha_path.name,
                "sha256": sha256_file(mcp_sha_path),
            },
            "observed_tool_schema_state": "NO_GO",
            "tool_schema_manifest": {
                "path": tool_schema_path.name,
                "sha256": sha256_file(tool_schema_path),
            },
            "local_tool_implementation_records": local_tool_records,
            "reason": "runtime list_tools cannot be captured until the task image, services, and credentials are qualified",
        },
        "network": {
            "gateway_bind": "127.0.0.1",
            "single_task_gateway": True,
            "runtime_allowlist_state": "NO_GO",
            "reason": "service endpoints and disposable-account tenant identifiers are not configured",
        },
    }
    write_json(output / "section-3.2.freeze.json", section_3_2)

    freeze_files = sorted(path for path in output.iterdir() if path.is_file())
    freeze_records = [
        {
            "path": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in freeze_files
        if path.name != "sections-3.1-3.2.sha256"
    ]
    write_sha_manifest(output / "sections-3.1-3.2.sha256", freeze_records)

    print(
        json.dumps(
            {
                "commit": commit,
                "tasks": len(task_ids),
                "task_files": len(task_records),
                "evaluator_files": len(evaluator_records),
                "mcp_configs": len(mcp_records),
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
