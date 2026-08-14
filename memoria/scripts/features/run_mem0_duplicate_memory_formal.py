#!/usr/bin/env python3
"""采集 Mem0 Platform v3 重复与近重复记忆处理 50-case 正式证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from competitor_smoke_common import (
    JsonClient, append_jsonl, load_all_cases, read_env, store_operations,
    utc_now, write_json,
)


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve(); project = script.parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=project / "memoria/datasets/feature/duplicate-memory-handling/duplicate-memory-handling-formal-v1.jsonl")
    parser.add_argument("--env-file", type=Path, default=project / "memoria/.env.competitors")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--poll-timeout", type=float, default=600.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_event(client: JsonClient, event_id: str, timeout: float, interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        _, body, _ = client.request("GET", f"/v1/event/{event_id}/")
        status = str(body.get("status", "")).upper()
        if status == "SUCCEEDED": return body
        if status == "FAILED": raise RuntimeError(f"event failed: {event_id}: {body}")
        if time.monotonic() >= deadline: raise TimeoutError(f"event timed out: {event_id}")
        time.sleep(interval)


def identity(case: dict[str, Any], operation: dict[str, Any], run_id: str) -> dict[str, str]:
    user_ref = operation["user_ref"]
    case_number = case["case_id"].split("-")[2]
    return {
        "user_id": f"dmh-mem0-{run_id}-{case_number}-{user_ref}",
        "agent_id": f"subject-{operation['subject_id']}",
        "app_id": f"type-{operation['memory_type']}",
        "run_id": f"branch-{operation['branch']}",
    }


def list_memories(client: JsonClient, filters: dict[str, Any]) -> dict[str, Any]:
    _, body, _ = client.request("POST", "/v3/memories/", params={"page": 1, "page_size": 200}, json_body={"filters": filters})
    return body


def main() -> int:
    args = parse_args()
    for key in ("dataset", "env_file", "run_dir"): setattr(args, key, getattr(args, key).resolve())
    cases = load_all_cases(args.dataset); env = read_env(args.env_file)
    key = env.get("MEM0_API_KEY")
    if not key: raise RuntimeError("MEM0_API_KEY is missing")
    if args.run_dir.exists(): raise FileExistsError(f"immutable run directory exists: {args.run_dir}")
    args.run_dir.mkdir(parents=True)
    source_diff = subprocess.check_output(["git", "diff", "--binary", "--", str(Path(__file__).resolve())])
    manifest = {
        "provider": "Mem0 Platform", "api_generation": "v3-add-only", "run_id": args.run_id,
        "started_at": utc_now(), "dataset": str(args.dataset), "dataset_sha256": sha256(args.dataset),
        "runner_sha256": sha256(Path(__file__).resolve()), "runner_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
        "case_count": 50, "write_count": sum(len(store_operations(case)) for case in cases),
        "scope_mapping": {"user": "user_id", "subject_id": "agent_id", "memory_type": "app_id", "branch": "run_id"},
        "protocol": "infer=true; await each event SUCCEEDED before next write; list after every write",
    }
    write_json(args.run_dir / "manifest.json", manifest)
    (args.run_dir / "cases.jsonl").write_text(args.dataset.read_text(encoding="utf-8"), encoding="utf-8")
    client = JsonClient("https://api.mem0.ai", f"Token {key}", args.run_dir / "operations.jsonl")
    results = []
    for index, case in enumerate(cases, 1):
        steps = []
        try:
            for operation in store_operations(case):
                ids = identity(case, operation, args.run_id)
                payload = {
                    **ids, "messages": [{"role": "user", "content": operation["content"]}], "infer": True,
                    "metadata": {"benchmark": "memoria-features", "suite": "duplicate-memory-handling-formal-v1", "case_id": case["case_id"], "memory_alias": operation["memory_alias"]},
                }
                _, queued, _ = client.request("POST", "/v3/memories/add/", json_body=payload, expected={200, 201, 202})
                event_id = queued.get("event_id")
                if not event_id: raise RuntimeError(f"add response missing event_id: {queued}")
                event = wait_event(client, event_id, args.poll_timeout, args.poll_interval)
                exact_state = list_memories(client, {"AND": [{key: value} for key, value in ids.items()]})
                user_state = list_memories(client, {"user_id": ids["user_id"]})
                steps.append({"alias": operation["memory_alias"], "input": operation["content"], "identity": ids, "event_id": event_id, "event": event, "exact_scope_state": exact_state, "user_state": user_state})
            scopes: dict[str, dict[str, str]] = {}
            for operation in store_operations(case):
                ids = identity(case, operation, args.run_id)
                scope = f"{operation['user_ref']}:{operation['branch']}:{operation['subject_id']}:{operation['memory_type']}"
                scopes[scope] = ids
            final_scopes = {scope: list_memories(client, {"AND": [{key: value} for key, value in ids.items()]}) for scope, ids in scopes.items()}
            result = {"case_id": case["case_id"], "category": case["category"], "subtype": case["subtype"], "status": "COMPLETED", "steps": steps, "final_scopes": final_scopes}
        except Exception as exc:
            result = {"case_id": case["case_id"], "category": case["category"], "subtype": case["subtype"], "status": "ERROR", "steps": steps, "error": f"{type(exc).__name__}: {exc}"}
        results.append(result); append_jsonl(args.run_dir / "case-results.jsonl", result)
        print(f"[Mem0 {index:02d}/50] {case['case_id']}: {result['status']}", flush=True)
    counts = Counter(row["status"] for row in results)
    metrics = {"completed_at": utc_now(), "status_counts": dict(counts), "total_cases": 50, "case_results": [{key: row.get(key) for key in ("case_id", "category", "subtype", "status", "error")} for row in results]}
    write_json(args.run_dir / "collection-metrics.json", metrics)
    manifest.update({"completed_at": metrics["completed_at"], "status": "complete"}); write_json(args.run_dir / "manifest.json", manifest)
    print(json.dumps(metrics, ensure_ascii=False, indent=2)); return 0 if counts["ERROR"] == 0 else 1
if __name__ == "__main__": sys.exit(main())
