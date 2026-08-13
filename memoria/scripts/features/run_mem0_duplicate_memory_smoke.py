#!/usr/bin/env python3
"""运行 Mem0 Platform v3 重复与近重复记忆处理 5-case Smoke。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from competitor_smoke_common import (
    JsonClient,
    load_smoke_cases,
    read_env,
    store_operations,
    utc_now,
    write_json,
)


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    project = script.parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path,
        default=project / "memoria/datasets/feature/duplicate-memory-handling/duplicate-memory-handling-formal-v1.jsonl",
    )
    parser.add_argument("--env-file", type=Path, default=project / "memoria/.env.competitors")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--poll-timeout", type=float, default=240.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--cleanup", action="store_true")
    return parser.parse_args()


def wait_event(client: JsonClient, event_id: str, timeout: float, interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        _, body, _ = client.request("GET", f"/v1/event/{event_id}/")
        status = str(body.get("status", "")).upper()
        if status == "SUCCEEDED":
            return body
        if status == "FAILED":
            raise RuntimeError(f"Mem0 event failed: {event_id}: {body}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Mem0 event timed out: {event_id}")
        time.sleep(interval)


def list_memories(client: JsonClient, user_id: str) -> dict[str, Any]:
    _, body, _ = client.request(
        "POST", "/v3/memories/", params={"page": 1, "page_size": 200},
        json_body={"filters": {"user_id": user_id}},
    )
    return body


def cleanup_user(client: JsonClient, user_id: str) -> dict[str, Any]:
    try:
        status, body, _ = client.request(
            "DELETE", "/v1/memories/", params={"user_id": user_id}, expected={200, 204}
        )
        return {"status": "deleted", "status_code": status, "response": body}
    except Exception as exc:
        return {"status": "cleanup_error", "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    args = parse_args()
    for key in ("dataset", "env_file", "output_dir"):
        setattr(args, key, getattr(args, key).resolve())
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True)
    env = read_env(args.env_file)
    api_key = env.get("MEM0_API_KEY")
    if not api_key:
        raise RuntimeError("MEM0_API_KEY is missing")
    cases = load_smoke_cases(args.dataset)
    client = JsonClient(
        "https://api.mem0.ai", f"Token {api_key}", args.output_dir / "operations.jsonl"
    )
    write_json(args.output_dir / "manifest.json", {
        "provider": "mem0-platform", "api_generation": "v3-add-only",
        "run_id": args.run_id, "started_at": utc_now(),
        "case_ids": [case["case_id"] for case in cases], "cleanup_requested": args.cleanup,
    })
    results: list[dict[str, Any]] = []
    users: list[str] = []
    try:
        for index, case in enumerate(cases, 1):
            user_id = f"dmh-mem0-smoke-{args.run_id}-{index:03d}"
            users.append(user_id)
            steps = []
            for operation in store_operations(case):
                payload = {
                    "user_id": user_id,
                    "messages": [{"role": "user", "content": operation["content"]}],
                    "infer": True,
                    "metadata": {
                        "benchmark": "memoria-features", "suite": "dmh-competitor-smoke",
                        "run_id": args.run_id, "case_id": case["case_id"],
                        "memory_alias": operation["memory_alias"],
                    },
                }
                _, queued, _ = client.request(
                    "POST", "/v3/memories/add/", json_body=payload, expected={200, 201, 202}
                )
                event_id = queued.get("event_id")
                if not event_id:
                    raise RuntimeError(f"Mem0 add response has no event_id: {queued}")
                event = wait_event(client, event_id, args.poll_timeout, args.poll_interval)
                state = list_memories(client, user_id)
                steps.append({
                    "alias": operation["memory_alias"], "input": operation["content"],
                    "event_id": event_id, "event": event, "state_after": state,
                })
            final_state = list_memories(client, user_id)
            result = {
                "case_id": case["case_id"], "category": case["category"],
                "subtype": case["subtype"], "user_id": user_id, "steps": steps,
                "final_count": final_state.get("count"),
                "final_memories": final_state.get("results", []), "status": "COMPLETED",
            }
            results.append(result)
            print(f"[Mem0 {index}/5] {case['case_id']}: {result['final_count']} memories", flush=True)
    finally:
        cleanup = {user_id: cleanup_user(client, user_id) for user_id in users} if args.cleanup else {}
        write_json(args.output_dir / "cleanup.json", cleanup)
    write_json(args.output_dir / "results.json", results)
    print(json.dumps([{"case_id": r["case_id"], "final_count": r["final_count"],
                       "memories": [m.get("memory") for m in r["final_memories"]]} for r in results],
                     ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__":
    sys.exit(main())
