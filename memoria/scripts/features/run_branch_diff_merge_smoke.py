#!/usr/bin/env python3
"""Run the deterministic Memoria Branch/Diff/Merge Smoke suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from run_snapshot_rollback_smoke import (
    MemoriaClient,
    append_jsonl,
    canary_memory,
    canonical_active_state,
    canonical_memory,
    git_value,
    load_jsonl,
    read_env,
    sha256_file,
    sha256_json,
    utc_now,
    write_json,
)


class BranchClient(MemoriaClient):
    def create_branch(
        self,
        user_id: str,
        name: str,
        from_snapshot: str | None,
        from_timestamp: str | None,
        expected_status: int,
    ) -> tuple[int, Any, float]:
        return self.request(
            "POST",
            "/v1/branches",
            user_id,
            json_body={
                "name": name,
                "from_snapshot": from_snapshot,
                "from_timestamp": from_timestamp,
            },
            expected={expected_status},
        )

    def checkout(
        self, user_id: str, name: str, expected_status: int
    ) -> tuple[int, Any, float]:
        return self.request(
            "POST",
            f"/v1/branches/{name}/checkout",
            user_id,
            expected={expected_status},
        )

    def branches(self, user_id: str) -> dict[str, Any]:
        _, body, _ = self.request("GET", "/v1/branches", user_id)
        return body

    def diff_items(
        self, user_id: str, name: str, limit: int, expected_status: int
    ) -> tuple[int, Any, float]:
        return self.request(
            "GET",
            f"/v1/branches/{name}/diff-items",
            user_id,
            params={"limit": limit},
            expected={expected_status},
        )

    def merge(
        self, user_id: str, name: str, strategy: str, expected_status: int
    ) -> tuple[int, Any, float]:
        return self.request(
            "POST",
            f"/v1/branches/{name}/merge",
            user_id,
            json_body={"strategy": strategy},
            expected={expected_status},
        )


class BranchCaseRunner:
    def __init__(
        self,
        client: BranchClient,
        run_dir: Path,
        canary_user: str,
        visibility_timeout: float,
        poll_interval: float,
    ) -> None:
        self.client = client
        self.run_dir = run_dir
        self.canary_user = canary_user
        self.visibility_timeout = visibility_timeout
        self.poll_interval = poll_interval
        self.alias_to_id: dict[str, str] = {}
        self.id_to_alias: dict[str, str] = {}
        self.branches: dict[str, str] = {"main": "main"}
        self.states: dict[str, dict[str, Any]] = {}
        self.retrievals: dict[str, dict[str, Any]] = {}
        self.diffs: dict[str, dict[str, Any]] = {}
        self.operation_results: dict[str, dict[str, Any]] = {}
        self.timings: list[dict[str, Any]] = []

    def bind(self, alias: str, memory: dict[str, Any]) -> None:
        memory_id = str(memory["memory_id"])
        self.alias_to_id[alias] = memory_id
        self.id_to_alias[memory_id] = alias

    def resolve_alias(self, item: dict[str, Any]) -> str | None:
        memory_id = str(item.get("memory_id"))
        alias = self.id_to_alias.get(memory_id)
        if alias:
            return alias
        metadata = item.get("extra_metadata") or {}
        return metadata.get("memory_alias")

    def branch_name(self, alias: str) -> str:
        if alias not in self.branches:
            raise KeyError(f"unknown branch alias: {alias}")
        return self.branches[alias]

    def list_branches(self, user_id: str) -> dict[str, Any]:
        body = self.client.branches(user_id)
        return {
            "body": body,
            "active_branch": next(
                (row["name"] for row in body.get("branches", []) if row.get("active")),
                None,
            ),
            "branch_names": [row["name"] for row in body.get("branches", [])],
        }

    def capture_state(self, user_id: str, alias: str) -> dict[str, Any]:
        branch_info = self.list_branches(user_id)
        active = sorted(
            [canonical_memory(item) for item in self.client.list_memories(user_id)],
            key=lambda item: str(item["memory_id"]),
        )
        record = {
            "case_user_id": user_id,
            "state_alias": alias,
            "captured_at": utc_now(),
            "active_branch": branch_info["active_branch"],
            "active_memories": active,
            "active_aliases": sorted(
                value
                for value in (self.resolve_alias(item) for item in active)
                if value
            ),
            "active_state_hash": sha256_json(active),
        }
        self.states[alias] = record
        append_jsonl(self.run_dir / "states.jsonl", record)
        return record

    def retrieval_requirements(
        self, case: dict[str, Any], alias: str
    ) -> list[dict[str, Any]]:
        return [
            item
            for item in case["assertions"]
            if item["at"] == alias
            and item["required"]
            and item["type"] in {"retrieval_contains", "retrieval_excludes"}
        ]

    def retrieval_ready(
        self, aliases: list[str | None], requirements: list[dict[str, Any]]
    ) -> bool:
        actual = set(aliases)
        for item in requirements:
            expected = set(item["aliases"])
            if item["type"] == "retrieval_contains" and not expected <= actual:
                return False
            if item["type"] == "retrieval_excludes" and expected & actual:
                return False
        return True

    def retrieve(
        self, user_id: str, operation: dict[str, Any], case: dict[str, Any]
    ) -> None:
        alias = operation["retrieval_alias"]
        requirements = self.retrieval_requirements(case, alias)
        deadline = time.monotonic() + self.visibility_timeout
        attempts = 0
        while True:
            attempts += 1
            results = self.client.retrieve(user_id, operation["query"], operation["top_k"])
            result_aliases = [self.resolve_alias(item) for item in results]
            if self.retrieval_ready(result_aliases, requirements) or time.monotonic() >= deadline:
                break
            time.sleep(self.poll_interval)
        record = {
            "case_user_id": user_id,
            "retrieval_alias": alias,
            "captured_at": utc_now(),
            "query": operation["query"],
            "top_k": operation["top_k"],
            "results": results,
            "result_aliases": result_aliases,
            "visibility_attempts": attempts,
            "required_visibility_satisfied": self.retrieval_ready(
                result_aliases, requirements
            ),
        }
        self.retrievals[alias] = record
        append_jsonl(self.run_dir / "retrieval.jsonl", record)

    def diff_aliases(self, body: dict[str, Any], field: str) -> list[str]:
        return sorted(
            alias
            for alias in (self.resolve_alias(item) for item in body.get(field, []))
            if alias
        )

    def execute(self, case: dict[str, Any], operation: dict[str, Any]) -> None:
        user_id = case["user_id"]
        op = operation["op"]
        if op == "capture_state":
            self.capture_state(user_id, operation["state_alias"])
        elif op == "retrieve":
            self.retrieve(user_id, operation, case)
        elif op == "store":
            stored = self.client.store(user_id, operation["memory"])
            self.bind(operation["memory"]["alias"], stored)
        elif op == "correct":
            corrected = self.client.correct(
                user_id,
                self.alias_to_id[operation["target_alias"]],
                operation["new_content"],
                operation.get("reason"),
            )
            self.bind(operation["result_alias"], corrected)
        elif op == "delete":
            self.client.delete(user_id, self.alias_to_id[operation["target_alias"]])
        elif op == "create_branch":
            status, body, elapsed_ms = self.client.create_branch(
                user_id,
                operation["branch_name"],
                operation.get("from_snapshot"),
                operation.get("from_timestamp"),
                operation.get("expected_status", 201),
            )
            self.branches[operation["branch_alias"]] = operation["branch_name"]
            self.timings.append(
                {"operation": op, "status": status, "elapsed_ms": elapsed_ms, "response": body}
            )
        elif op == "checkout_branch":
            name = self.branch_name(operation["branch_alias"])
            status, body, elapsed_ms = self.client.checkout(
                user_id, name, operation.get("expected_status", 200)
            )
            branch_info = self.list_branches(user_id)
            result = {
                "status": status,
                "body": body,
                "active_branch": branch_info["active_branch"],
                "branch_names": branch_info["branch_names"],
            }
            self.operation_results[operation["operation_alias"]] = result
            self.timings.append(
                {"operation": op, "status": status, "elapsed_ms": elapsed_ms, "response": body}
            )
        elif op == "list_branches":
            branch_info = self.list_branches(user_id)
            self.operation_results[operation["operation_alias"]] = {
                "status": operation.get("expected_status", 200),
                **branch_info,
            }
        elif op == "diff_items":
            status, body, elapsed_ms = self.client.diff_items(
                user_id,
                self.branch_name(operation["branch_alias"]),
                operation.get("limit", 100),
                operation.get("expected_status", 200),
            )
            record = {
                "case_user_id": user_id,
                "diff_alias": operation["diff_alias"],
                "captured_at": utc_now(),
                "status": status,
                "body": body,
                "aliases": {
                    field: self.diff_aliases(body, field)
                    for field in ("added", "updated", "removed", "conflicts", "behind_main")
                },
            }
            self.diffs[operation["diff_alias"]] = record
            append_jsonl(self.run_dir / "diffs.jsonl", record)
            self.timings.append(
                {"operation": op, "status": status, "elapsed_ms": elapsed_ms}
            )
        elif op == "merge_branch":
            status, body, elapsed_ms = self.client.merge(
                user_id,
                self.branch_name(operation["branch_alias"]),
                operation["strategy"],
                operation.get("expected_status", 200),
            )
            self.operation_results[operation["operation_alias"]] = {
                "status": status,
                "body": body,
            }
            self.timings.append(
                {"operation": op, "status": status, "elapsed_ms": elapsed_ms, "response": body}
            )
        else:
            raise ValueError(f"unsupported operation: {op}")

    def assertion_result(self, item: dict[str, Any]) -> tuple[bool, Any, Any]:
        kind = item["type"]
        at = item["at"]
        expected: Any = item.get("expected")
        actual: Any = None
        if kind == "exact_active_aliases":
            actual = self.states[at]["active_aliases"]
            expected = sorted(item["aliases"])
        elif kind in {"state_hash_equals", "state_hash_differs"}:
            actual = self.states[at]["active_state_hash"]
            expected = self.states[item["from"]]["active_state_hash"]
            return (actual == expected if kind == "state_hash_equals" else actual != expected), expected, actual
        elif kind in {"retrieval_contains", "retrieval_excludes"}:
            aliases = set(self.retrievals[at]["result_aliases"])
            wanted = set(item["aliases"])
            actual = sorted(alias for alias in aliases if alias)
            expected = sorted(wanted)
            return (wanted <= aliases if kind == "retrieval_contains" else not wanted & aliases), expected, actual
        elif kind == "active_branch_equals":
            actual = self.operation_results[at]["active_branch"]
        elif kind == "branch_exists":
            actual = self.branch_name(item["branch_alias"]) in self.operation_results[at]["branch_names"]
        elif kind == "diff_aliases_equal":
            actual = self.diffs[at]["aliases"][item["field"]]
            expected = sorted(item["aliases"])
        elif kind == "diff_conflict_contents_equal":
            memory_id = self.alias_to_id[item["memory_alias"]]
            conflict = next(
                row for row in self.diffs[at]["body"]["conflicts"] if row["memory_id"] == memory_id
            )
            actual = {
                "branch_content": conflict["branch"].get("superseded_by_content"),
                "main_content": conflict["main"].get("superseded_by_content"),
            }
            expected = {
                "branch_content": item["branch_content"],
                "main_content": item["main_content"],
            }
        elif kind == "operation_status_equals":
            actual = self.operation_results[at]["status"]
        elif kind == "operation_body_contains":
            actual = json.dumps(self.operation_results[at]["body"], ensure_ascii=False)
            return str(expected) in actual, expected, actual
        else:
            raise ValueError(f"unsupported assertion: {kind}")
        return actual == expected, expected, actual

    def run_case(self, case: dict[str, Any], canary_hash: str) -> dict[str, Any]:
        user_id = case["user_id"]
        if self.client.list_memories(user_id):
            raise RuntimeError(f"case user is not empty: {user_id}")
        for item in case["initial_memories"]:
            self.bind(item["alias"], self.client.store(user_id, item))
        for operation in case["operations"]:
            self.execute(case, operation)
        assertions = []
        for index, item in enumerate(case["assertions"], 1):
            passed, expected, actual = self.assertion_result(item)
            record = {
                "case_id": case["case_id"],
                "assertion_index": index,
                "at": item["at"],
                "type": item["type"],
                "required": item["required"],
                "passed": passed,
                "expected": expected,
                "actual": actual,
            }
            assertions.append(record)
            append_jsonl(self.run_dir / "assertions.jsonl", record)
        canary_after = sha256_json(
            canonical_active_state(self.client.list_memories(self.canary_user))
        )
        isolation = {
            "case_id": case["case_id"],
            "assertion_index": len(assertions) + 1,
            "at": "after_case",
            "type": "canary_state_hash_equals",
            "required": True,
            "passed": canary_after == canary_hash,
            "expected": canary_hash,
            "actual": canary_after,
        }
        assertions.append(isolation)
        append_jsonl(self.run_dir / "assertions.jsonl", isolation)
        required = [row for row in assertions if row["required"]]
        return {
            "case_id": case["case_id"],
            "user_id": user_id,
            "category": case["category"],
            "status": "PASS" if all(row["passed"] for row in required) else "FAIL",
            "required_assertions": len(required),
            "required_passed": sum(row["passed"] for row in required),
            "timings": self.timings,
        }


def validate_dataset(dataset: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for line, case in enumerate(dataset, 1):
        errors.extend((line, error) for error in validator.iter_errors(case))
    if errors:
        line, error = errors[0]
        raise ValueError(f"dataset line {line} {error.json_path}: {error.message}")
    if len(dataset) != 5:
        raise ValueError(f"Smoke suite must have exactly 5 cases, got {len(dataset)}")
    if len({case["case_id"] for case in dataset}) != len(dataset):
        raise ValueError("duplicate case_id")
    if len({case["user_id"] for case in dataset}) != len(dataset):
        raise ValueError("duplicate user_id")


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    project_root = script.parents[3]
    workspace_root = project_root.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Dataset path; the historical Smoke dataset is not retained.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        required=True,
        help="Schema path matching --dataset.",
    )
    parser.add_argument("--runtime", type=Path, default=workspace_root / "memoria_runtime")
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--visibility-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for key in ("dataset", "schema", "runtime", "run_dir"):
        setattr(args, key, getattr(args, key).resolve())
    if args.run_dir.exists():
        raise FileExistsError(f"immutable run directory already exists: {args.run_dir}")
    args.run_dir.mkdir(parents=True)
    dataset = load_jsonl(args.dataset)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_dataset(dataset, schema)
    env = read_env(args.runtime / ".env")
    master_key = os.environ.get("MEMORIA_MASTER_KEY") or env.get("MEMORIA_MASTER_KEY")
    if not master_key:
        raise RuntimeError("MEMORIA_MASTER_KEY is not configured")
    source_repo = args.runtime / "source/Memoria"
    source_diff = subprocess.check_output(
        ["git", "-C", str(source_repo), "diff", "--binary"], stderr=subprocess.DEVNULL
    )
    manifest = {
        "created_at": utc_now(),
        "suite": "branch-diff-merge-smoke-v1",
        "protocol": "controlled-direct-store-branch-state-machine-v1",
        "dataset_path": str(args.dataset),
        "dataset_sha256": sha256_file(args.dataset),
        "schema_path": str(args.schema),
        "schema_sha256": sha256_file(args.schema),
        "case_count": len(dataset),
        "case_ids": [case["case_id"] for case in dataset],
        "case_user_ids": [case["user_id"] for case in dataset],
        "canary_user_id": "feature-bdm-smoke-canary",
        "api_url": args.api_url,
        "embedding_provider": env.get("MEMORIA_EMBEDDING_PROVIDER"),
        "embedding_model": env.get("MEMORIA_EMBEDDING_MODEL"),
        "embedding_dimension": env.get("MEMORIA_EMBEDDING_DIM"),
        "memoria_version": "0.4.0",
        "memoria_commit": git_value(source_repo, "rev-parse", "HEAD"),
        "memoria_source_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
        "matrixone_image": env.get("MATRIXONE_IMAGE"),
        "matrixone_data_dir": env.get("MATRIXONE_DATA_DIR"),
        "timeout_seconds": args.timeout,
        "visibility_timeout_seconds": args.visibility_timeout,
        "poll_interval_seconds": args.poll_interval,
        "state_hash_excludes": ["created_at", "retrieval_score"],
        "merge_semantic_boundary": "append is append-only skip-on-conflict, not three-way reconcile",
    }
    write_json(args.run_dir / "manifest.json", manifest)
    (args.run_dir / "cases.jsonl").write_text(args.dataset.read_text(encoding="utf-8"), encoding="utf-8")
    client = BranchClient(
        args.api_url,
        master_key,
        args.run_dir / "operations.jsonl",
        args.timeout,
        args.max_retries,
    )
    canary_user = manifest["canary_user_id"]
    if client.list_memories(canary_user):
        raise RuntimeError(f"canary user is not empty: {canary_user}")
    canary = client.store(canary_user, canary_memory(manifest["suite"]))
    canary_hash = sha256_json(canonical_active_state(client.list_memories(canary_user)))
    write_json(
        args.run_dir / "canary.json",
        {"user_id": canary_user, "memory_id": canary["memory_id"], "baseline_hash": canary_hash},
    )
    results = []
    for case in dataset:
        runner = BranchCaseRunner(
            client,
            args.run_dir,
            canary_user,
            args.visibility_timeout,
            args.poll_interval,
        )
        try:
            result = runner.run_case(case, canary_hash)
        except Exception as exc:
            result = {
                "case_id": case["case_id"],
                "user_id": case["user_id"],
                "category": case["category"],
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }
            append_jsonl(args.run_dir / "errors.jsonl", {"at": utc_now(), **result})
        results.append(result)
        append_jsonl(args.run_dir / "case-results.jsonl", result)
    counts = {
        status: sum(row["status"] == status for row in results)
        for status in ("PASS", "FAIL", "ERROR")
    }
    metrics = {
        "completed_at": utc_now(),
        "total_cases": len(results),
        "status_counts": counts,
        "strict_pass_rate_all_cases": counts["PASS"] / len(results),
        "system_error_rate": counts["ERROR"] / len(results),
        "all_passed": counts["PASS"] == len(results),
        "case_results": results,
    }
    write_json(args.run_dir / "metrics.json", metrics)
    manifest.update({"completed_at": metrics["completed_at"], "status": "complete"})
    write_json(args.run_dir / "manifest.json", manifest)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if metrics["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
