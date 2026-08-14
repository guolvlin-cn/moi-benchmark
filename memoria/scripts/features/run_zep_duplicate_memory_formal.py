#!/usr/bin/env python3
"""采集 Zep Cloud 重复与近重复记忆处理 50-case 正式证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from competitor_smoke_common import JsonClient, append_jsonl, load_all_cases, read_env, store_operations, utc_now, write_json


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve(); project = script.parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=project / "memoria/datasets/feature/duplicate-memory-handling/duplicate-memory-handling-formal-v1.jsonl")
    parser.add_argument("--env-file", type=Path, default=project / "memoria/.env.competitors")
    parser.add_argument("--run-dir", type=Path, required=True); parser.add_argument("--run-id", required=True)
    parser.add_argument("--poll-timeout", type=float, default=900.0); parser.add_argument("--poll-interval", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_episode(client: JsonClient, episode_id: str, timeout: float, interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        _, body, _ = client.request("GET", f"/api/v2/graph/episodes/{episode_id}")
        if body.get("processed") is True: return body
        if time.monotonic() >= deadline: raise TimeoutError(f"episode timed out: {episode_id}")
        time.sleep(interval)


def get_edges(client: JsonClient, user_id: str) -> list[dict[str, Any]]:
    _, body, _ = client.request("POST", f"/api/v2/graph/edge/user/{user_id}", json_body={"limit": 200})
    return body.get("edges", []) if isinstance(body, dict) else body


def scope_identity(case: dict[str, Any], operation: dict[str, Any], run_id: str) -> tuple[str, str]:
    number = case["case_id"].split("-")[2]
    logical = f"{operation['user_ref']}:{operation['branch']}:{operation['subject_id']}:{operation['memory_type']}"
    adapted = case["subtype"] in {"subject_isolation", "memory_type_isolation", "branch_isolation"}
    suffix = f"-{operation['branch']}-{operation['subject_id']}-{operation['memory_type']}" if adapted else ""
    return logical, f"dmh-zep-{run_id}-{number}-{operation['user_ref']}{suffix}"


def main() -> int:
    args = parse_args()
    for key in ("dataset", "env_file", "run_dir"): setattr(args, key, getattr(args, key).resolve())
    cases = load_all_cases(args.dataset); env = read_env(args.env_file); key = env.get("ZEP_API_KEY")
    if not key: raise RuntimeError("ZEP_API_KEY is missing")
    if args.run_dir.exists(): raise FileExistsError(f"immutable run directory exists: {args.run_dir}")
    args.run_dir.mkdir(parents=True)
    source_diff = subprocess.check_output(["git", "diff", "--binary", "--", str(Path(__file__).resolve())])
    manifest = {
        "provider": "Zep Cloud", "run_id": args.run_id, "started_at": utc_now(), "dataset": str(args.dataset),
        "dataset_sha256": sha256(args.dataset), "runner_sha256": sha256(Path(__file__).resolve()), "runner_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
        "case_count": 50, "write_count": sum(len(store_operations(case)) for case in cases), "workers": args.workers,
        "native_scope": ["user"], "adapted_scope": ["subject_id", "memory_type", "branch"],
        "adapted_scope_method": "separate Zep user graph per logical scope; excluded from native-scope headline score",
        "protocol": "graph.add text episode; await processed=true before next write in same case; retain episode mentions and all active/invalid edges",
    }
    write_json(args.run_dir / "manifest.json", manifest); (args.run_dir / "cases.jsonl").write_text(args.dataset.read_text(encoding="utf-8"), encoding="utf-8")
    result_lock = threading.Lock(); results: list[dict[str, Any]] = []

    def run_case(case: dict[str, Any]) -> dict[str, Any]:
        client = JsonClient("https://api.getzep.com", f"Api-Key {key}", args.run_dir / "operations.jsonl", timeout=90.0)
        steps = []; created_users: set[str] = set(); scopes: dict[str, str] = {}
        try:
            for op_index, operation in enumerate(store_operations(case), 1):
                scope, user_id = scope_identity(case, operation, args.run_id); scopes[scope] = user_id
                if user_id not in created_users:
                    subject = operation["content"].split()[0].strip(".,")
                    client.request("POST", "/api/v2/users", json_body={"user_id": user_id, "first_name": subject}, expected={200, 201})
                    created_users.add(user_id)
                # 使用固定的历史时间保持操作顺序可复现，同时避免把 episode
                # 写入未来时间而延迟 Zep 的异步图处理。
                number = int(case["case_id"].split("-")[2]); created_at = (datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=number * 10 + op_index)).isoformat().replace("+00:00", "Z")
                payload = {"user_id": user_id, "type": "text", "data": operation["content"], "created_at": created_at,
                           "source_description": "Memoria duplicate-memory-handling formal competitor benchmark",
                           "metadata": {"benchmark": "memoria-features", "suite": "duplicate-memory-handling-formal-v1", "case_id": case["case_id"], "memory_alias": operation["memory_alias"], "logical_scope": scope}}
                _, added, _ = client.request("POST", "/api/v2/graph", json_body=payload, expected={200, 201, 202})
                episode_id = added.get("uuid") or added.get("uuid_")
                if not episode_id: raise RuntimeError(f"add response missing episode UUID: {added}")
                episode = wait_episode(client, episode_id, args.poll_timeout, args.poll_interval)
                _, mentions, _ = client.request("GET", f"/api/v2/graph/episodes/{episode_id}/mentions")
                edges = get_edges(client, user_id)
                steps.append({"alias": operation["memory_alias"], "input": operation["content"], "logical_scope": scope, "user_id": user_id, "episode_id": episode_id, "episode": episode, "episode_mentions": mentions, "edges_after": edges})
            final_scopes = {}
            for scope, user_id in scopes.items():
                edges = get_edges(client, user_id)
                final_scopes[scope] = {"user_id": user_id, "all_edges": edges, "active_edges": [edge for edge in edges if not edge.get("invalid_at") and not edge.get("expired_at")]}
            return {"case_id": case["case_id"], "category": case["category"], "subtype": case["subtype"], "scope_mode": "adapted" if case["subtype"] in {"subject_isolation", "memory_type_isolation", "branch_isolation"} else "native", "status": "COMPLETED", "steps": steps, "final_scopes": final_scopes}
        except Exception as exc:
            return {"case_id": case["case_id"], "category": case["category"], "subtype": case["subtype"], "scope_mode": "adapted" if case["subtype"] in {"subject_isolation", "memory_type_isolation", "branch_isolation"} else "native", "status": "ERROR", "steps": steps, "created_users": sorted(created_users), "error": f"{type(exc).__name__}: {exc}"}

    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(run_case, case): case for case in cases}
        for future in as_completed(future_map):
            result = future.result()
            with result_lock:
                results.append(result); append_jsonl(args.run_dir / "case-results.jsonl", result); completed += 1
                print(f"[Zep {completed:02d}/50] {result['case_id']}: {result['status']}", flush=True)
    ordered = sorted(results, key=lambda row: row["case_id"]); counts = Counter(row["status"] for row in ordered)
    metrics = {"completed_at": utc_now(), "status_counts": dict(counts), "total_cases": 50, "case_results": [{key: row.get(key) for key in ("case_id", "category", "subtype", "scope_mode", "status", "error")} for row in ordered]}
    write_json(args.run_dir / "collection-metrics.json", metrics); manifest.update({"completed_at": metrics["completed_at"], "status": "complete"}); write_json(args.run_dir / "manifest.json", manifest)
    print(json.dumps(metrics, ensure_ascii=False, indent=2)); return 0 if counts["ERROR"] == 0 else 1


if __name__ == "__main__": sys.exit(main())
