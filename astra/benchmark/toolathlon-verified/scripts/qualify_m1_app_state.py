#!/usr/bin/env python3
"""Capture and compare Toolathlon local application reset-replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


EXPECTED_COMMIT = "2aed2468858f15818acafa178518390cc4b0f5cb"
INSTANCE_SUFFIX = "-inst-alpha"
CONTAINERS = {
    "canvas": f"canvas-docker{INSTANCE_SUFFIX}",
    "poste": f"poste{INSTANCE_SUFFIX}",
    "woocommerce_web": f"woo-wp{INSTANCE_SUFFIX}",
    "woocommerce_db": f"woo-db{INSTANCE_SUFFIX}",
    "k8s": f"cluster{INSTANCE_SUFFIX}1-control-plane",
}
SENTINEL_PATHS = {
    "canvas": "/tmp/toolathlon-reset-sentinel",
    "poste": "/data/toolathlon-reset-sentinel",
    "woocommerce_web": "/var/www/html/toolathlon-reset-sentinel",
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def command(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sudo", "docker", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def inspect_container(name: str) -> dict[str, Any]:
    result = command("inspect", name)
    if result.returncode != 0:
        return {"exists": False, "name": name}
    raw = json.loads(result.stdout)[0]
    state = raw.get("State", {})
    config = raw.get("Config", {})
    network = raw.get("NetworkSettings", {})
    ports = network.get("Ports", {}) or {}
    normalized_ports = {
        key: sorted(
            f"{item.get('HostIp', '')}:{item.get('HostPort', '')}"
            for item in (value or [])
        )
        for key, value in sorted(ports.items())
    }
    return {
        "exists": True,
        "name": name,
        "container_id": raw.get("Id"),
        "created": raw.get("Created"),
        "image_reference": config.get("Image"),
        "image_id": raw.get("Image"),
        "running": bool(state.get("Running")),
        "status": state.get("Status"),
        "health": (state.get("Health") or {}).get("Status"),
        "oom_killed": bool(state.get("OOMKilled")),
        "ports": normalized_ports,
    }


def http_probe(url: str, accepted: set[int]) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception as exc:
        return {"ok": False, "error_type": type(exc).__name__}
    return {"ok": status in accepted, "status": status}


def tcp_probe(port: int, expected: bytes | None = None) -> dict[str, Any]:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
            connection.settimeout(5)
            banner = connection.recv(512)
    except Exception as exc:
        return {"ok": False, "error_type": type(exc).__name__}
    return {
        "ok": expected is None or expected in banner,
        "banner_sha256": hashlib.sha256(banner).hexdigest(),
    }


def k8s_probe() -> dict[str, Any]:
    result = command(
        "exec",
        CONTAINERS["k8s"],
        "kubectl",
        "--kubeconfig=/etc/kubernetes/admin.conf",
        "get",
        "nodes",
        "--no-headers",
        timeout=30,
    )
    return {
        "ok": result.returncode == 0 and " Ready " in f" {result.stdout} ",
        "node_line_count": len([line for line in result.stdout.splitlines() if line.strip()]),
    }


def sentinel_state() -> dict[str, bool]:
    states: dict[str, bool] = {}
    for service, path in SENTINEL_PATHS.items():
        result = command("exec", CONTAINERS[service], "test", "-e", path)
        states[service] = result.returncode == 0
    namespace = command(
        "exec",
        CONTAINERS["k8s"],
        "kubectl",
        "--kubeconfig=/etc/kubernetes/admin.conf",
        "get",
        "namespace",
        "toolathlon-reset-sentinel",
    )
    states["k8s"] = namespace.returncode == 0
    return states


def semantic_view(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "containers": {
            service: {
                "exists": item["exists"],
                "image_reference": item.get("image_reference"),
                "image_id": item.get("image_id"),
                "running": item.get("running"),
                "ports": item.get("ports"),
            }
            for service, item in snapshot["containers"].items()
        },
        "readiness": snapshot["readiness"],
        "sentinels": snapshot["sentinels"],
    }


def port_contract(service: str, ports: dict[str, list[str]] | None) -> dict[str, list[str]]:
    """Normalize ports whose host value is intentionally allocated at reset time."""
    normalized = dict(ports or {})
    if service == "k8s":
        normalized["6443/tcp"] = [
            f"{binding.rsplit(':', 1)[0]}:<ephemeral>"
            for binding in normalized.get("6443/tcp", [])
        ]
    return normalized


def capture(source: Path, captured_at: str) -> dict[str, Any]:
    containers = {
        service: inspect_container(name) for service, name in CONTAINERS.items()
    }
    readiness = {
        "canvas": http_probe("http://127.0.0.1:10001/api/v1/accounts", {200, 401, 403}),
        "poste_web": http_probe("http://127.0.0.1:10005/", {200, 302}),
        "poste_imap": tcp_probe(1143, b"IMAP"),
        "poste_smtp": tcp_probe(2525, b"SMTP"),
        "poste_submission": tcp_probe(1587, b"SMTP"),
        "woocommerce": http_probe("http://127.0.0.1:10003/", {200, 301, 302}),
        "k8s": k8s_probe(),
    }
    snapshot = {
        "schema_version": "toolathlon.app-state.snapshot.v1",
        "source_commit": EXPECTED_COMMIT,
        "captured_at": captured_at,
        "containers": containers,
        "readiness": readiness,
        "sentinels": sentinel_state(),
    }
    snapshot["all_ready"] = all(item.get("ok") for item in readiness.values())
    snapshot["semantic_sha256"] = canonical_sha256(semantic_view(snapshot))
    return snapshot


def build_manifest(source: Path, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    recipes = []
    for relative in (
        "deployment/canvas/scripts/setup.sh",
        "deployment/poste/scripts/setup.sh",
        "deployment/woocommerce/scripts/setup.sh",
        "deployment/k8s/scripts/setup.sh",
    ):
        path = source / relative
        recipes.append({
            "path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    sentinels_injected = all(before["sentinels"].values())
    sentinels_removed = not any(after["sentinels"].values())
    images_stable = all(
        before["containers"][service].get("image_id")
        == after["containers"][service].get("image_id")
        for service in CONTAINERS
    )
    raw_ports_stable = all(
        before["containers"][service].get("ports")
        == after["containers"][service].get("ports")
        for service in CONTAINERS
    )
    port_contract_stable = all(
        port_contract(service, before["containers"][service].get("ports"))
        == port_contract(service, after["containers"][service].get("ports"))
        for service in CONTAINERS
    )
    generations_changed = all(
        before["containers"][service].get("container_id")
        != after["containers"][service].get("container_id")
        for service in CONTAINERS
    )
    local_go = all(
        (
            sentinels_injected,
            sentinels_removed,
            after.get("all_ready"),
            images_stable,
            port_contract_stable,
            generations_changed,
        )
    )
    return {
        "schema_version": "toolathlon.app-state.live.v1",
        "source_commit": EXPECTED_COMMIT,
        "state": "PARTIAL_GO",
        "local_applications": {
            "state": "GO" if local_go else "NO_GO",
            "services": sorted(CONTAINERS),
            "reset_method": "targeted frozen setup.sh reprovision; no global prune",
            "sentinels_injected": sentinels_injected,
            "sentinels_removed": sentinels_removed,
            "all_ready_after_reset": after.get("all_ready"),
            "image_ids_stable": images_stable,
            "raw_port_bindings_stable": raw_ports_stable,
            "port_binding_contract_stable": port_contract_stable,
            "port_binding_policy": {
                "fixed": ["canvas", "poste", "woocommerce_db", "woocommerce_web"],
                "k8s": "6443/tcp remains loopback-bound; Kind host port is ephemeral per cluster generation",
            },
            "container_generations_changed": generations_changed,
            "successful_replays": 1 if local_go else 0,
            "before_snapshot_sha256": canonical_sha256(before),
            "after_snapshot_sha256": canonical_sha256(after),
            "baseline_semantic_sha256": after["semantic_sha256"],
            "reset_recipes": recipes,
        },
        "external_applications": {
            "state": "PENDING",
            "reason": "task-scoped preprocess/reset replay requires explicit credential access inside the frozen task image",
        },
        "secret_values_recorded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--captured-at", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if args.output:
        value = capture(source, args.captured_at)
        write_json(args.output.resolve(), value)
        print(json.dumps({
            "all_ready": value["all_ready"],
            "sentinels": value["sentinels"],
            "semantic_sha256": value["semantic_sha256"],
        }, sort_keys=True))
        return 0 if value["all_ready"] else 1
    if not args.before or not args.after or not args.manifest:
        raise SystemExit("comparison mode requires --before, --after, and --manifest")
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    manifest = build_manifest(source, before, after)
    write_json(args.manifest.resolve(), manifest)
    print(json.dumps({
        "state": manifest["state"],
        "local_state": manifest["local_applications"]["state"],
        "external_state": manifest["external_applications"]["state"],
        "successful_replays": manifest["local_applications"]["successful_replays"],
    }, sort_keys=True))
    return 0 if manifest["local_applications"]["state"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
