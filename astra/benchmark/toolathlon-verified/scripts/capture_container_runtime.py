#!/usr/bin/env python3
"""Capture the qualified Docker runtime and task-image software inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any


IMAGE_REFERENCE = (
    "lockon0927/toolathlon-task-image@"
    "sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f"
)


def run(*command: str) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip('"')
    return values


def image_run(*command: str, entrypoint: str) -> str:
    return run(
        "sudo",
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        entrypoint,
        IMAGE_REFERENCE,
        *command,
    )


def capture_task_image_software(frozen_at: str) -> dict[str, Any]:
    dpkg_lines = image_run(
        "-W",
        "-f=${binary:Package}\t${Version}\t${Architecture}\n",
        entrypoint="/usr/bin/dpkg-query",
    ).splitlines()
    system_packages = []
    for line in dpkg_lines:
        name, version, architecture = line.split("\t", 2)
        system_packages.append(
            {
                "name": name,
                "version": version,
                "architecture": architecture,
            }
        )

    python_packages = json.loads(
        image_run(
            "-m",
            "pip",
            "list",
            "--format=json",
            "--disable-pip-version-check",
            entrypoint="/usr/bin/python3",
        )
    )
    npm_global = json.loads(
        image_run(
            "ls",
            "-g",
            "--depth=0",
            "--json",
            entrypoint="/usr/bin/npm",
        )
    )
    browser_probe_source = """
import glob
import json
import os
import shutil
import subprocess

executables = {}
for name in (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "firefox",
    "playwright",
):
    path = shutil.which(name)
    if not path:
        continue
    try:
        version = subprocess.run(
            [path, "--version"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        ).stdout.strip()
    except Exception as exc:
        version = f"{type(exc).__name__}: {exc}"
    executables[name] = {"path": path, "version": version}

package_json_records = []
for pattern in (
    "/usr/lib/node_modules/*/package.json",
    "/usr/local/lib/node_modules/*/package.json",
    "/workspace/node_modules/*/package.json",
    "/workspace/node_modules/@playwright/*/package.json",
):
    for path in glob.glob(pattern):
        try:
            with open(path, "r", encoding="utf-8") as stream:
                package = json.load(stream)
        except Exception:
            continue
        name = package.get("name")
        if name and ("playwright" in name or name in {"puppeteer", "selenium-webdriver"}):
            package_json_records.append(
                {"name": name, "version": package.get("version"), "path": path}
            )

browser_cache_entries = []
for pattern in (
    "/root/.cache/ms-playwright/*",
    "/home/*/.cache/ms-playwright/*",
    "/ms-playwright/*",
):
    for path in glob.glob(pattern):
        browser_cache_entries.append(
            {
                "path": path,
                "name": os.path.basename(path),
                "is_dir": os.path.isdir(path),
            }
        )

cache_executables = []
for pattern in (
    "/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
    "/root/.cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell",
    "/root/.cache/ms-playwright/ffmpeg-*/ffmpeg-linux",
):
    for path in glob.glob(pattern):
        try:
            version = subprocess.run(
                [path, "--version"],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
            ).stdout.splitlines()[0].strip()
        except Exception as exc:
            version = f"{type(exc).__name__}: {exc}"
        cache_executables.append(
            {
                "path": path,
                "version": version,
                "size_bytes": os.path.getsize(path),
            }
        )

print(
    json.dumps(
        {
            "executables": executables,
            "node_browser_packages": package_json_records,
            "browser_cache_entries": browser_cache_entries,
            "browser_cache_executables": cache_executables,
        },
        sort_keys=True,
    )
)
"""
    browser_inventory = json.loads(
        image_run(
            "-c",
            browser_probe_source,
            entrypoint="/usr/bin/python3",
        )
    )

    return {
        "schema_version": 1,
        "frozen_at": frozen_at,
        "state": "frozen",
        "image_reference": IMAGE_REFERENCE,
        "network_for_capture": "none",
        "system_packages": {
            "manager": "dpkg",
            "count": len(system_packages),
            "records": sorted(
                system_packages,
                key=lambda record: (
                    record["name"],
                    record["architecture"],
                    record["version"],
                ),
            ),
        },
        "python_packages": {
            "interpreter": "python3",
            "count": len(python_packages),
            "records": sorted(
                python_packages,
                key=lambda record: (record["name"].casefold(), record["version"]),
            ),
        },
        "node_global_packages": npm_global,
        "browsers": browser_inventory,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--frozen-at", required=True)
    args = parser.parse_args()

    freeze_dir = args.freeze_dir.resolve()
    freeze_dir.mkdir(parents=True, exist_ok=True)
    docker_version = json.loads(run("sudo", "docker", "version", "--format", "{{json .}}"))
    docker_info = json.loads(run("sudo", "docker", "info", "--format", "{{json .}}"))
    image = json.loads(
        run(
            "sudo",
            "docker",
            "image",
            "inspect",
            IMAGE_REFERENCE,
            "--format",
            "{{json .}}",
        )
    )
    tool_output = run(
        "sudo",
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        "/bin/bash",
        IMAGE_REFERENCE,
        "-lc",
        "python3 --version; uv --version; node --version; npm --version; "
        "kind version; kubectl version --client=true; helm version --short; "
        "docker --version; git --version",
    ).splitlines()

    os_release = read_os_release()
    software_payload = capture_task_image_software(args.frozen_at)
    software_output = freeze_dir / "task-image-software-manifest.json"
    software_output.write_text(
        json.dumps(software_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "frozen_at": args.frozen_at,
        "state": "frozen",
        "execution_mode": "rootful_docker",
        "host": {
            "distribution": os_release.get("PRETTY_NAME"),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "docker": {
            "client": docker_version.get("Client"),
            "server": docker_version.get("Server"),
            "storage_driver": docker_info.get("Driver"),
            "cgroup_version": docker_info.get("CgroupVersion"),
            "cgroup_driver": docker_info.get("CgroupDriver"),
            "docker_root_dir": docker_info.get("DockerRootDir"),
            "security_options": docker_info.get("SecurityOptions"),
            "rootless": False,
            "unprivileged_user_has_socket_access": False,
            "docker_api_version_for_toolathlon_nested_cli": "1.44",
        },
        "transfer_tools": {
            "skopeo": run("skopeo", "--version"),
        },
        "task_image_runtime_verification": {
            "reference": IMAGE_REFERENCE,
            "docker_id": image.get("Id"),
            "repo_digests": image.get("RepoDigests"),
            "architecture": image.get("Architecture"),
            "os": image.get("Os"),
            "created": image.get("Created"),
            "size_bytes": image.get("Size"),
            "network_for_version_probe": "none",
            "version_probe": tool_output,
            "verified": image.get("Id")
            == "sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f",
        },
        "task_image_software_manifest": {
            "path": software_output.name,
            "sha256": sha256_file(software_output),
            "system_package_count": software_payload["system_packages"]["count"],
            "python_package_count": software_payload["python_packages"]["count"],
        },
        "compatibility_note": {
            "formal_reference": IMAGE_REFERENCE,
            "legacy_docker_archive_tag": "lockon0927/toolathlon-task-image:1016beta",
            "legacy_docker_archive_id": "sha256:b3445100f01e2ae5ec2350beee115818a4656a0e402a63a87651d9d8a4ef2372",
            "allowed_for_formal_runs": False,
            "reason": "skopeo 1.4 OCI-to-legacy-Docker conversion changes the daemon identity",
        },
    }

    output = freeze_dir / "container-runtime-manifest.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    section_path = freeze_dir / "section-3.2.freeze.json"
    section = json.loads(section_path.read_text(encoding="utf-8"))
    section["container_runtime"] = {
        "state": "frozen",
        "manifest": {"path": output.name, "sha256": sha256_file(output)},
        "execution_mode": "rootful_docker",
        "formal_image_reference": IMAGE_REFERENCE,
    }
    section["dependencies"]["task_image_software_manifest"] = {
        "path": software_output.name,
        "sha256": sha256_file(software_output),
        "system_package_count": software_payload["system_packages"]["count"],
        "python_package_count": software_payload["python_packages"]["count"],
        "browser_inventory_state": "frozen",
    }
    section["freeze_state"] = (
        "source_data_images_and_container_runtime_frozen_"
        "runtime_qualification_no_go"
    )
    section["task_image"]["docker_runtime_verified"] = payload[
        "task_image_runtime_verification"
    ]["verified"]
    section_path.write_text(
        json.dumps(section, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    aggregate_path = freeze_dir / "sections-3.1-3.2.sha256"
    aggregate_files = sorted(
        path for path in freeze_dir.iterdir() if path.is_file() and path != aggregate_path
    )
    aggregate_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in aggregate_files),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": sha256_file(output),
                "software_manifest_sha256": sha256_file(software_output),
                "image_verified": payload["task_image_runtime_verification"]["verified"],
            },
            sort_keys=True,
        )
    )
    return 0 if payload["task_image_runtime_verification"]["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
