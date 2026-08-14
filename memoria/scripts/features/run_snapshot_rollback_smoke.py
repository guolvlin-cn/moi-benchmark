#!/usr/bin/env python3
"""Run a deterministic Memoria snapshot/rollback dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from jsonschema import Draft202012Validator, FormatChecker


TRANSIENT_STATUS = {429, 500, 502, 503, 504}
def canary_memory(suite: str) -> dict[str, Any]:
    return {
        "content": "The benchmark canary prefers green notebooks.",
        "memory_type": "semantic",
        "session_id": f"{suite}-canary-session-01",
        "subject_id": "benchmark-canary",
        "trust_tier": "T1",
        "initial_confidence": 0.99,
        "observed_at": "2025-01-01T00:00:00Z",
        "extra_metadata": {
            "benchmark": "memoria-features",
            "suite": suite,
            "case_id": "canary",
            "memory_alias": "canary",
            "field": "control",
        },
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    output = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            output.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL {path}:{line_number}: {exc}") from exc
    return output


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def git_value(repo: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


class ApiError(RuntimeError):
    pass


class MemoriaClient:
    def __init__(
        self,
        api_url: str,
        master_key: str,
        operations_path: Path,
        timeout: float,
        max_retries: int,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.master_key = master_key
        self.operations_path = operations_path
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    def headers(self, user_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.master_key}",
            "X-User-Id": user_id,
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        user_id: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expected: set[int] | None = None,
        allow: set[int] | None = None,
    ) -> tuple[int, Any, float]:
        expected = expected or {200}
        allow = allow or set()
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(min(2 ** (attempt - 1), 8))
            started = time.perf_counter()
            response = None
            try:
                response = self.session.request(
                    method,
                    f"{self.api_url}{path}",
                    headers=self.headers(user_id),
                    json=json_body,
                    params=params,
                    timeout=self.timeout,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                try:
                    body: Any = response.json()
                except ValueError:
                    body = response.text
                append_jsonl(
                    self.operations_path,
                    {
                        "at": utc_now(),
                        "user_id": user_id,
                        "method": method,
                        "path": path,
                        "params": params,
                        "request_body": json_body,
                        "status_code": response.status_code,
                        "elapsed_ms": round(elapsed_ms, 3),
                        "response_body": body,
                        "attempt": attempt,
                    },
                )
                if response.status_code in expected | allow:
                    return response.status_code, body, elapsed_ms
                last_error = f"HTTP {response.status_code}: {str(body)[:1000]}"
                if response.status_code not in TRANSIENT_STATUS:
                    break
            except requests.RequestException as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                last_error = str(exc)
                append_jsonl(
                    self.operations_path,
                    {
                        "at": utc_now(),
                        "user_id": user_id,
                        "method": method,
                        "path": path,
                        "params": params,
                        "request_body": json_body,
                        "elapsed_ms": round(elapsed_ms, 3),
                        "attempt": attempt,
                        "error": last_error,
                    },
                )
        raise ApiError(f"{method} {path} failed for {user_id}: {last_error}")

    def list_memories(self, user_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 500}
            if cursor:
                params["cursor"] = cursor
            _, body, _ = self.request("GET", "/v1/memories", user_id, params=params)
            items.extend(body.get("items", []))
            cursor = body.get("next_cursor")
            if not cursor:
                break
        return items

    def store(self, user_id: str, memory: dict[str, Any]) -> dict[str, Any]:
        payload = {key: value for key, value in memory.items() if key != "alias"}
        _, body, _ = self.request(
            "POST", "/v1/memories", user_id, json_body=payload, expected={201}
        )
        return body

    def correct(
        self, user_id: str, memory_id: str, content: str, reason: str | None
    ) -> dict[str, Any]:
        _, body, _ = self.request(
            "PUT",
            f"/v1/memories/{memory_id}/correct",
            user_id,
            json_body={"new_content": content, "reason": reason},
        )
        return body

    def delete(self, user_id: str, memory_id: str) -> None:
        self.request(
            "DELETE", f"/v1/memories/{memory_id}", user_id, expected={204}
        )

    def history(self, user_id: str, memory_id: str) -> list[dict[str, Any]] | None:
        status, body, _ = self.request(
            "GET",
            f"/v1/memories/{memory_id}/history",
            user_id,
            expected={200},
            allow={404},
        )
        return list(body.get("versions", [])) if status == 200 else None

    def retrieve(self, user_id: str, query: str, top_k: int) -> list[dict[str, Any]]:
        _, body, _ = self.request(
            "POST",
            "/v1/memories/retrieve",
            user_id,
            json_body={"query": query, "top_k": top_k},
        )
        return body.get("results", []) if isinstance(body, dict) else body

    def create_snapshot(
        self, user_id: str, name: str, description: str | None, expected_status: int
    ) -> tuple[int, Any, float]:
        status, body, elapsed_ms = self.request(
            "POST",
            "/v1/snapshots",
            user_id,
            json_body={"name": name, "description": description},
            expected={expected_status},
        )
        return status, body, elapsed_ms

    def rollback(
        self, user_id: str, name: str, expected_status: int
    ) -> tuple[int, Any, float]:
        return self.request(
            "POST",
            f"/v1/snapshots/{name}/rollback",
            user_id,
            json_body={},
            expected={expected_status},
        )

    def delete_snapshot(
        self, user_id: str, name: str, expected_status: int
    ) -> tuple[int, Any, float]:
        return self.request(
            "DELETE", f"/v1/snapshots/{name}", user_id, expected={expected_status}
        )


def canonical_memory(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("extra_metadata") or None
    return {
        "memory_id": memory.get("memory_id"),
        "user_id": memory.get("user_id"),
        "author_id": memory.get("author_id"),
        "subject_id": memory.get("subject_id"),
        "memory_type": memory.get("memory_type"),
        "content": memory.get("content"),
        "trust_tier": memory.get("trust_tier"),
        "initial_confidence": round(float(memory.get("initial_confidence", 0)), 10),
        "is_active": bool(memory.get("is_active")),
        "session_id": memory.get("session_id"),
        "observed_at": memory.get("observed_at"),
        "extra_metadata": metadata,
    }


def canonical_history(history: list[dict[str, Any]] | None) -> Any:
    if history is None:
        return None
    return [
        {
            "memory_id": row.get("memory_id"),
            "content": row.get("content"),
            "is_active": bool(row.get("is_active")),
            "superseded_by": row.get("superseded_by"),
            "observed_at": row.get("observed_at"),
            "memory_type": row.get("memory_type"),
        }
        for row in history
    ]


class CaseRunner:
    def __init__(
        self,
        client: MemoriaClient,
        run_dir: Path,
        visibility_timeout: float,
        poll_interval: float,
        canary_user: str,
    ) -> None:
        self.client = client
        self.run_dir = run_dir
        self.visibility_timeout = visibility_timeout
        self.poll_interval = poll_interval
        self.canary_user = canary_user
        self.alias_to_id: dict[str, str] = {}
        self.id_to_alias: dict[str, str] = {}
        self.states: dict[str, dict[str, Any]] = {}
        self.retrievals: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, str] = {}
        self.operation_results: dict[str, dict[str, Any]] = {}
        self.timings: list[dict[str, Any]] = []

    def bind(self, alias: str, memory: dict[str, Any]) -> None:
        memory_id = str(memory["memory_id"])
        self.alias_to_id[alias] = memory_id
        self.id_to_alias[memory_id] = alias

    def active_aliases(self, state: dict[str, Any]) -> set[str]:
        output = set()
        for memory in state["active_memories"]:
            memory_id = str(memory["memory_id"])
            alias = self.id_to_alias.get(memory_id)
            if alias:
                output.add(alias)
                continue
            metadata = memory.get("extra_metadata") or {}
            if metadata.get("memory_alias"):
                output.add(str(metadata["memory_alias"]))
        return output

    def capture_state(self, user_id: str, state_alias: str) -> dict[str, Any]:
        active = sorted(
            [canonical_memory(item) for item in self.client.list_memories(user_id)],
            key=lambda item: str(item["memory_id"]),
        )
        histories = {}
        for alias, memory_id in sorted(self.alias_to_id.items()):
            histories[alias] = canonical_history(self.client.history(user_id, memory_id))
        state = {
            "case_user_id": user_id,
            "state_alias": state_alias,
            "captured_at": utc_now(),
            "active_memories": active,
            "histories": histories,
            "active_state_hash": sha256_json(active),
            "history_state_hash": sha256_json(histories),
        }
        self.states[state_alias] = state
        append_jsonl(self.run_dir / "states.jsonl", state)
        return state

    def retrieval_requirements(
        self, case: dict[str, Any], retrieval_alias: str
    ) -> list[dict[str, Any]]:
        return [
            assertion
            for assertion in case["assertions"]
            if assertion["at"] == retrieval_alias
            and assertion["required"]
            and assertion["type"]
            in {"retrieval_contains", "retrieval_excludes", "retrieval_rank_at_most"}
        ]

    def retrieval_ready(
        self, result_aliases: list[str | None], requirements: list[dict[str, Any]]
    ) -> bool:
        aliases = set(result_aliases)
        for assertion in requirements:
            if assertion["type"] == "retrieval_contains" and not set(assertion["aliases"]) <= aliases:
                return False
            if assertion["type"] == "retrieval_excludes" and set(assertion["aliases"]) & aliases:
                return False
            if assertion["type"] == "retrieval_rank_at_most":
                memory_alias = assertion["memory_alias"]
                if memory_alias not in result_aliases:
                    return False
                if result_aliases.index(memory_alias) + 1 > assertion["max_rank"]:
                    return False
        return True

    def retrieve(
        self, user_id: str, operation: dict[str, Any], case: dict[str, Any]
    ) -> dict[str, Any]:
        alias = operation["retrieval_alias"]
        requirements = self.retrieval_requirements(case, alias)
        deadline = time.monotonic() + self.visibility_timeout
        attempts = 0
        while True:
            attempts += 1
            results = self.client.retrieve(user_id, operation["query"], operation["top_k"])
            result_aliases = [
                self.id_to_alias.get(str(item.get("memory_id"))) for item in results
            ]
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
            "required_visibility_satisfied": self.retrieval_ready(result_aliases, requirements),
        }
        self.retrievals[alias] = record
        append_jsonl(self.run_dir / "retrieval.jsonl", record)
        return record

    def execute_operation(self, case: dict[str, Any], operation: dict[str, Any]) -> None:
        user_id = case["user_id"]
        op = operation["op"]
        if op == "capture_state":
            self.capture_state(user_id, operation["state_alias"])
        elif op == "retrieve":
            self.retrieve(user_id, operation, case)
        elif op == "create_snapshot":
            status, body, elapsed_ms = self.client.create_snapshot(
                user_id,
                operation["snapshot_name"],
                operation.get("description"),
                operation.get("expected_status", 201),
            )
            # Memoria normalizes snapshot names (for example, '-' becomes '_').
            # Rollback must use the canonical name returned by the API.
            canonical_name = body.get("name") if isinstance(body, dict) else None
            if not canonical_name:
                raise RuntimeError(f"snapshot response has no canonical name: {body!r}")
            self.snapshots[operation["snapshot_alias"]] = str(canonical_name)
            if operation_alias := operation.get("operation_alias"):
                self.operation_results[operation_alias] = {
                    "status": status,
                    "body": body,
                    "canonical_name": str(canonical_name),
                }
            self.timings.append(
                {
                    "operation": "snapshot",
                    "elapsed_ms": elapsed_ms,
                    "status": status,
                    "response": body,
                }
            )
        elif op == "store":
            memory = operation["memory"]
            stored = self.client.store(user_id, memory)
            self.bind(memory["alias"], stored)
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
        elif op == "delete_snapshot":
            snapshot_name = self.snapshots[operation["snapshot_alias"]]
            status, body, elapsed_ms = self.client.delete_snapshot(
                user_id, snapshot_name, operation.get("expected_status", 204)
            )
            if operation_alias := operation.get("operation_alias"):
                self.operation_results[operation_alias] = {
                    "status": status,
                    "body": body,
                    "canonical_name": snapshot_name,
                }
            self.timings.append(
                {
                    "operation": "delete_snapshot",
                    "elapsed_ms": elapsed_ms,
                    "status": status,
                    "response": body,
                }
            )
        elif op == "rollback":
            if "snapshot_alias" in operation:
                snapshot_name = self.snapshots[operation["snapshot_alias"]]
            else:
                snapshot_name = operation["snapshot_name"]
            expected_status = operation.get("expected_status", 200)
            status, body, elapsed_ms = self.client.rollback(
                user_id, snapshot_name, expected_status
            )
            if operation_alias := operation.get("operation_alias"):
                self.operation_results[operation_alias] = {
                    "status": status,
                    "body": body,
                    "canonical_name": snapshot_name,
                }
            expected_state_alias = operation.get("expected_state_from")
            expected_hash = (
                self.states.get(expected_state_alias, {}).get("active_state_hash")
                if status == 200 and expected_state_alias
                else None
            )
            deadline = time.monotonic() + self.visibility_timeout
            visibility_attempts = 0
            visibility_hash = None
            while expected_hash:
                visibility_attempts += 1
                visibility_hash = sha256_json(
                    canonical_active_state(self.client.list_memories(user_id))
                )
                if visibility_hash == expected_hash or time.monotonic() >= deadline:
                    break
                time.sleep(self.poll_interval)
            self.timings.append(
                {
                    "operation": "rollback",
                    "elapsed_ms": elapsed_ms,
                    "status": status,
                    "response": body,
                    "visibility_attempts": visibility_attempts,
                    "expected_state_from": expected_state_alias,
                    "visibility_converged": (
                        visibility_hash == expected_hash if expected_hash else None
                    ),
                }
            )
        else:
            raise ValueError(f"unsupported operation: {op}")

    def assertion_result(self, assertion: dict[str, Any]) -> tuple[bool, Any, Any]:
        assertion_type = assertion["type"]
        at = assertion["at"]
        state = self.states.get(at)
        retrieval = self.retrievals.get(at)
        expected: Any = assertion.get("expected")
        actual: Any = None

        if assertion_type in {"exact_active_aliases", "active_aliases_include"}:
            actual_set = self.active_aliases(state or {})
            expected_set = set(assertion["aliases"])
            actual = sorted(actual_set)
            expected = sorted(expected_set)
            passed = actual_set == expected_set if assertion_type == "exact_active_aliases" else expected_set <= actual_set
        elif assertion_type == "inactive_aliases_include":
            inactive = set()
            for alias, history in (state or {}).get("histories", {}).items():
                if history and any(not row["is_active"] for row in history):
                    inactive.add(alias)
            expected_set = set(assertion["aliases"])
            actual = sorted(inactive)
            expected = sorted(expected_set)
            passed = expected_set <= inactive
        elif assertion_type == "absent_aliases":
            present = self.active_aliases(state or {})
            for alias, history in (state or {}).get("histories", {}).items():
                if history is not None:
                    present.add(alias)
            expected_set = set(assertion["aliases"])
            actual = sorted(present & expected_set)
            expected = []
            passed = not actual
        elif assertion_type == "history_chain_equals":
            chain_aliases = list(assertion["expected"])
            root = chain_aliases[0]
            history = (state or {}).get("histories", {}).get(root)
            actual = [self.id_to_alias.get(str(row["memory_id"])) for row in history or []]
            expected = chain_aliases
            passed = actual == expected
        elif assertion_type == "state_hash_differs":
            actual = (state or {}).get("active_state_hash")
            expected = self.states[assertion["from"]]["active_state_hash"]
            passed = actual != expected
        elif assertion_type == "state_hash_equals":
            actual = (state or {}).get("active_state_hash")
            expected = self.states[assertion["from"]]["active_state_hash"]
            passed = actual == expected
        elif assertion_type == "memory_identity_equals":
            memory_alias = assertion["memory_alias"]
            memory_id = self.alias_to_id[memory_alias]
            actual = memory_id in {str(item["memory_id"]) for item in (state or {}).get("active_memories", [])}
            expected = True
            passed = actual
        elif assertion_type in {"retrieval_contains", "retrieval_excludes"}:
            actual_set = set((retrieval or {}).get("result_aliases", []))
            expected_set = set(assertion["aliases"])
            actual = sorted(value for value in actual_set if value)
            expected = sorted(expected_set)
            passed = expected_set <= actual_set if assertion_type == "retrieval_contains" else not (expected_set & actual_set)
        elif assertion_type == "retrieval_rank_at_most":
            result_aliases = (retrieval or {}).get("result_aliases", [])
            memory_alias = assertion["memory_alias"]
            actual = result_aliases.index(memory_alias) + 1 if memory_alias in result_aliases else None
            expected = assertion["max_rank"]
            passed = actual is not None and actual <= expected
        elif assertion_type == "retrieval_order_equals":
            actual = (retrieval or {}).get("result_aliases", [])
            expected = self.retrievals[assertion["from"]].get("result_aliases", [])
            passed = actual == expected
        elif assertion_type == "operation_status_equals":
            actual = self.operation_results.get(at, {}).get("status")
            passed = actual == expected
        elif assertion_type == "operation_body_contains":
            body = self.operation_results.get(at, {}).get("body")
            actual = json.dumps(body, ensure_ascii=False, sort_keys=True)
            passed = str(expected) in actual
        elif assertion_type == "snapshot_canonical_name_equals":
            actual = self.operation_results.get(at, {}).get("canonical_name")
            passed = actual == expected
        else:
            raise ValueError(f"unsupported assertion: {assertion_type}")
        return passed, expected, actual

    def evaluate_assertions(self, case: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        for index, assertion in enumerate(case["assertions"], 1):
            passed, expected, actual = self.assertion_result(assertion)
            record = {
                "case_id": case["case_id"],
                "assertion_index": index,
                "at": assertion["at"],
                "type": assertion["type"],
                "required": assertion["required"],
                "passed": passed,
                "expected": expected,
                "actual": actual,
            }
            results.append(record)
            append_jsonl(self.run_dir / "assertions.jsonl", record)
        return results

    def run_case(self, case: dict[str, Any], canary_hash: str) -> dict[str, Any]:
        user_id = case["user_id"]
        if self.client.list_memories(user_id):
            raise RuntimeError(f"case user is not empty: {user_id}")
        for memory in case["initial_memories"]:
            stored = self.client.store(user_id, memory)
            self.bind(memory["alias"], stored)
        for operation in case["operations"]:
            self.execute_operation(case, operation)
        assertions = self.evaluate_assertions(case)
        canary_after = canonical_active_state(self.client.list_memories(self.canary_user))
        canary_after_hash = sha256_json(canary_after)
        isolation_ok = canary_after_hash == canary_hash
        isolation_record = {
            "case_id": case["case_id"],
            "assertion_index": len(assertions) + 1,
            "at": "after_case",
            "type": "canary_state_hash_equals",
            "required": True,
            "passed": isolation_ok,
            "expected": canary_hash,
            "actual": canary_after_hash,
        }
        assertions.append(isolation_record)
        append_jsonl(self.run_dir / "assertions.jsonl", isolation_record)
        required = [item for item in assertions if item["required"]]
        return {
            "case_id": case["case_id"],
            "user_id": user_id,
            "category": case["category"],
            "status": "PASS" if all(item["passed"] for item in required) else "FAIL",
            "required_assertions": len(required),
            "required_passed": sum(item["passed"] for item in required),
            "diagnostic_assertions": len(assertions) - len(required),
            "diagnostic_passed": sum(item["passed"] for item in assertions if not item["required"]),
            "timings": self.timings,
        }


def canonical_active_state(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted([canonical_memory(item) for item in memories], key=lambda item: str(item["memory_id"]))


def validate_dataset(dataset: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for index, case in enumerate(dataset, 1):
        errors = sorted(validator.iter_errors(case), key=lambda error: list(error.path))
        if errors:
            error = errors[0]
            raise ValueError(f"dataset line {index} {error.json_path}: {error.message}")
    if not dataset:
        raise ValueError("dataset must contain at least one case")
    if len({case["case_id"] for case in dataset}) != len(dataset):
        raise ValueError("duplicate case_id")
    if len({case["user_id"] for case in dataset}) != len(dataset):
        raise ValueError("duplicate user_id")


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    project_root = script.parents[3]
    workspace_root = project_root.parent
    runtime = workspace_root / "memoria_runtime"
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
    parser.add_argument("--runtime", type=Path, default=runtime)
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--visibility-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument(
        "--user-suffix",
        default="",
        help="Append a suffix to case and canary user IDs for an isolated retry.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run only this case ID; repeat to select multiple cases.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.dataset = args.dataset.resolve()
    args.schema = args.schema.resolve()
    args.runtime = args.runtime.resolve()
    args.run_dir = args.run_dir.resolve()
    if args.run_dir.exists():
        raise FileExistsError(f"immutable run directory already exists: {args.run_dir}")
    args.run_dir.mkdir(parents=True)

    env = read_env(args.runtime / ".env")
    master_key = os.environ.get("MEMORIA_MASTER_KEY") or env.get("MEMORIA_MASTER_KEY")
    if not master_key:
        raise RuntimeError("MEMORIA_MASTER_KEY is not configured")
    full_dataset = load_jsonl(args.dataset)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_dataset(full_dataset, schema)
    if args.case_id:
        requested = set(args.case_id)
        dataset = [case for case in full_dataset if case["case_id"] in requested]
        missing = sorted(requested - {case["case_id"] for case in dataset})
        if missing:
            raise ValueError(f"unknown --case-id values: {missing}")
    else:
        dataset = full_dataset
    suites = {case["suite"] for case in dataset}
    if len(suites) != 1:
        raise ValueError(f"selected cases must use one suite, got {sorted(suites)}")
    suite = next(iter(suites))
    logical_user_ids = [case["user_id"] for case in dataset]
    if args.user_suffix:
        dataset = [{**case, "user_id": case["user_id"] + args.user_suffix} for case in dataset]
    canary_prefix = suite.replace("snapshot-rollback-", "feature-sr-").replace("-v1", "")
    canary_user = f"{canary_prefix}-canary{args.user_suffix}"

    source_repo = args.runtime / "source/Memoria"
    source_diff = subprocess.check_output(
        ["git", "-C", str(source_repo), "diff", "--binary"], stderr=subprocess.DEVNULL
    )
    manifest = {
        "created_at": utc_now(),
        "suite": suite,
        "protocol": "controlled-direct-store-state-machine-v2",
        "dataset_path": str(args.dataset),
        "dataset_sha256": sha256_file(args.dataset),
        "schema_path": str(args.schema),
        "schema_sha256": sha256_file(args.schema),
        "api_url": args.api_url,
        "case_count": len(dataset),
        "case_ids": [case["case_id"] for case in dataset],
        "source_case_count": len(full_dataset),
        "logical_case_user_ids": logical_user_ids,
        "case_user_ids": [case["user_id"] for case in dataset],
        "user_suffix": args.user_suffix,
        "canary_user_id": canary_user,
        "write_endpoint": "/v1/memories",
        "internal_llm": False,
        "embedding_provider": env.get("MEMORIA_EMBEDDING_PROVIDER", "openai"),
        "embedding_model": env.get("MEMORIA_EMBEDDING_MODEL"),
        "embedding_dimension": env.get("MEMORIA_EMBEDDING_DIM"),
        "memoria_commit": git_value(source_repo, "rev-parse", "HEAD"),
        "memoria_version": "0.4.0",
        "memoria_source_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
        "matrixone_image": env.get("MATRIXONE_IMAGE"),
        "matrixone_data_dir": env.get("MATRIXONE_DATA_DIR"),
        "timeout_seconds": args.timeout,
        "visibility_timeout_seconds": args.visibility_timeout,
        "poll_interval_seconds": args.poll_interval,
        "state_hash_excludes": ["created_at", "retrieval_score"],
    }
    write_json(args.run_dir / "manifest.json", manifest)
    cases_path = args.run_dir / "cases.jsonl"
    for selected_case in dataset:
        append_jsonl(cases_path, selected_case)
    manifest["selected_cases_sha256"] = sha256_file(cases_path)
    write_json(args.run_dir / "manifest.json", manifest)

    client = MemoriaClient(
        args.api_url,
        master_key,
        args.run_dir / "operations.jsonl",
        args.timeout,
        args.max_retries,
    )
    if client.list_memories(canary_user):
        raise RuntimeError(f"canary user is not empty: {canary_user}")
    canary = client.store(canary_user, canary_memory(suite))
    canary_hash = sha256_json(canonical_active_state(client.list_memories(canary_user)))
    write_json(
        args.run_dir / "canary.json",
        {"user_id": canary_user, "memory_id": canary["memory_id"], "baseline_hash": canary_hash},
    )

    case_results = []
    for case in dataset:
        runner = CaseRunner(
            client,
            args.run_dir,
            args.visibility_timeout,
            args.poll_interval,
            canary_user,
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
            append_jsonl(
                args.run_dir / "errors.jsonl",
                {"at": utc_now(), **result},
            )
        case_results.append(result)
        append_jsonl(args.run_dir / "case-results.jsonl", result)

    counts = {status: sum(row["status"] == status for row in case_results) for status in ("PASS", "FAIL", "ERROR")}
    metrics = {
        "completed_at": utc_now(),
        "total_cases": len(case_results),
        "status_counts": counts,
        "strict_pass_rate_all_cases": counts["PASS"] / len(case_results),
        "system_error_rate": counts["ERROR"] / len(case_results),
        "all_passed": counts["PASS"] == len(case_results),
        "case_results": case_results,
    }
    write_json(args.run_dir / "metrics.json", metrics)
    manifest["completed_at"] = metrics["completed_at"]
    manifest["status"] = "complete"
    write_json(args.run_dir / "manifest.json", manifest)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if metrics["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
