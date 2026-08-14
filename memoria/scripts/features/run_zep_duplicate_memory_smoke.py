#!/usr/bin/env python3
"""运行 Zep Cloud 重复与近重复记忆处理 5-case Smoke。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
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
    parser.add_argument("--poll-timeout", type=float, default=360.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--only-case", action="append", default=[])
    return parser.parse_args()


def wait_episode(client: JsonClient, episode_id: str, timeout: float, interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        _, body, _ = client.request("GET", f"/api/v2/graph/episodes/{episode_id}")
        if body.get("processed") is True:
            return body
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Zep episode timed out: {episode_id}")
        time.sleep(interval)


def get_edges(client: JsonClient, user_id: str) -> list[dict[str, Any]]:
    _, body, _ = client.request(
        "POST", f"/api/v2/graph/edge/user/{user_id}", json_body={"limit": 100}
    )
    return body.get("edges", []) if isinstance(body, dict) else body


def cleanup_user(client: JsonClient, user_id: str) -> dict[str, Any]:
    try:
        status, body, _ = client.request(
            "DELETE", f"/api/v2/users/{user_id}", expected={200, 202, 204}
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
    api_key = env.get("ZEP_API_KEY")
    if not api_key:
        raise RuntimeError("ZEP_API_KEY is missing")
    cases = load_smoke_cases(args.dataset)
    if args.only_case:
        wanted = set(args.only_case)
        cases = [case for case in cases if case["case_id"] in wanted]
        if {case["case_id"] for case in cases} != wanted:
            raise ValueError("--only-case contains an unknown Smoke case id")
    client = JsonClient(
        "https://api.getzep.com", f"Api-Key {api_key}", args.output_dir / "operations.jsonl"
    )
    write_json(args.output_dir / "manifest.json", {
        "provider": "zep-cloud", "ingestion": "user-graph-text-episode",
        "run_id": args.run_id, "started_at": utc_now(),
        "case_ids": [case["case_id"] for case in cases], "cleanup_requested": args.cleanup,
    })
    results: list[dict[str, Any]] = []
    users: list[str] = []
    anchor = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)
    try:
        for index, case in enumerate(cases, 1):
            user_id = f"dmh-zep-smoke-{args.run_id}-{index:03d}"
            users.append(user_id)
            steps = []
            try:
                subject_name = store_operations(case)[0]["content"].split()[0].strip(".,")
                client.request(
                    "POST", "/api/v2/users",
                    json_body={"user_id": user_id, "first_name": subject_name},
                    expected={200, 201},
                )
                for op_index, operation in enumerate(store_operations(case), 1):
                    created_at = (anchor + timedelta(minutes=index * 10 + op_index)).isoformat().replace("+00:00", "Z")
                    payload = {
                        "user_id": user_id, "type": "text", "data": operation["content"],
                        "created_at": created_at,
                        "source_description": "Memoria duplicate-memory-handling competitor smoke",
                        "metadata": {
                            "benchmark": "memoria-features", "suite": "dmh-competitor-smoke",
                            "run_id": args.run_id, "case_id": case["case_id"],
                            "memory_alias": operation["memory_alias"],
                        },
                    }
                    _, added, _ = client.request(
                        "POST", "/api/v2/graph", json_body=payload, expected={200, 201, 202}
                    )
                    episode_id = added.get("uuid") or added.get("uuid_")
                    if not episode_id:
                        raise RuntimeError(f"Zep add response has no episode UUID: {added}")
                    episode = wait_episode(client, episode_id, args.poll_timeout, args.poll_interval)
                    _, mentions, _ = client.request(
                        "GET", f"/api/v2/graph/episodes/{episode_id}/mentions"
                    )
                    edges = get_edges(client, user_id)
                    steps.append({
                        "alias": operation["memory_alias"], "input": operation["content"],
                        "episode_id": episode_id, "episode": episode,
                        "episode_mentions": mentions, "edges_after": edges,
                    })
                final_edges = get_edges(client, user_id)
                active_edges = [edge for edge in final_edges if not edge.get("invalid_at") and not edge.get("expired_at")]
                result = {
                    "case_id": case["case_id"], "category": case["category"],
                    "subtype": case["subtype"], "user_id": user_id, "steps": steps,
                    "final_edges": final_edges, "active_edges": active_edges,
                    "final_edge_count": len(final_edges), "active_edge_count": len(active_edges),
                    "status": "COMPLETED",
                }
            except Exception as exc:
                result = {
                    "case_id": case["case_id"], "category": case["category"],
                    "subtype": case["subtype"], "user_id": user_id, "steps": steps,
                    "status": "ERROR", "error": f"{type(exc).__name__}: {exc}",
                }
            results.append(result)
            write_json(args.output_dir / "results.json", results)
            if result["status"] == "COMPLETED":
                print(f"[Zep {index}/{len(cases)}] {case['case_id']}: {result['active_edge_count']} active / {result['final_edge_count']} total edges", flush=True)
            else:
                print(f"[Zep {index}/{len(cases)}] {case['case_id']}: {result['error']}", flush=True)
    finally:
        cleanup = {user_id: cleanup_user(client, user_id) for user_id in users} if args.cleanup else {}
        write_json(args.output_dir / "cleanup.json", cleanup)
    write_json(args.output_dir / "results.json", results)
    print(json.dumps([{"case_id": r["case_id"], "status": r["status"],
                       "active_edge_count": r.get("active_edge_count"),
                       "total_edge_count": r.get("final_edge_count"),
                       "active_facts": [edge.get("fact") for edge in r.get("active_edges", [])],
                       "error": r.get("error")} for r in results],
                     ensure_ascii=False, indent=2))
    return 0 if all(result["status"] == "COMPLETED" for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
