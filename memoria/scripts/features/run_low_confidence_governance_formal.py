#!/usr/bin/env python3
"""运行 Memoria 低置信记忆治理 50 用例正式实验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from run_snapshot_rollback_smoke import (
    MemoriaClient,
    append_jsonl,
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


SUITE = "low-confidence-governance-formal-v1"
EXPECTED_CATEGORIES = {
    "clear_delete": 10,
    "clear_retain": 10,
    "tier_comparison": 10,
    "mixed_batch": 10,
    "safety_boundary": 10,
}
HALF_LIFE_DAYS = {"T1": 365.0, "T2": 180.0, "T3": 60.0, "T4": 30.0}
GOVERNANCE_THRESHOLD = 0.2
RETRIEVAL_MIN_CONFIDENCE = 0.05


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def normalized_time(value: str | None) -> str | None:
    if value is None:
        return None
    return parse_time(value).isoformat().replace("+00:00", "Z")


def effective_confidence(tier: str, confidence: float, age_days: int) -> float:
    return confidence * math.exp(-age_days / HALF_LIFE_DAYS[tier])


def validate_dataset(dataset: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for line, case in enumerate(dataset, 1):
        errors.extend((line, error) for error in validator.iter_errors(case))
    if errors:
        line, error = errors[0]
        raise ValueError(f"dataset line {line} {error.json_path}: {error.message}")
    if len(dataset) != 50:
        raise ValueError(f"formal suite must contain 50 cases, got {len(dataset)}")
    if len({case["case_id"] for case in dataset}) != 50:
        raise ValueError("duplicate case_id")
    if len({case["user_id"] for case in dataset}) != 50:
        raise ValueError("duplicate user_id")
    if Counter(case["category"] for case in dataset) != Counter(EXPECTED_CATEGORIES):
        raise ValueError("category distribution mismatch")

    for case in dataset:
        aliases = [memory["alias"] for memory in case["initial_memories"]]
        if len(aliases) != len(set(aliases)):
            raise ValueError(f"duplicate memory alias in {case['case_id']}")
        for memory in case["initial_memories"]:
            effective = effective_confidence(
                memory["trust_tier"],
                memory["initial_confidence"],
                memory["age_days"],
            )
            expected = "delete" if effective < GOVERNANCE_THRESHOLD else "retain"
            if memory["expected_action"] != expected:
                raise ValueError(
                    f"governance expectation mismatch: {case['case_id']}:"
                    f"{memory['alias']} effective={effective:.6f}"
                )
            if memory["require_pre_retrieval"] and effective < RETRIEVAL_MIN_CONFIDENCE:
                raise ValueError(
                    f"pre-governance retrieval is impossible: {case['case_id']}:"
                    f"{memory['alias']} effective={effective:.6f}"
                )


class GovernanceClient(MemoriaClient):
    def governance(self, user_id: str, force: bool) -> tuple[Any, float]:
        _, body, elapsed_ms = self.request(
            "POST",
            "/v1/governance",
            user_id,
            json_body={"force": force},
            expected={200},
        )
        return body, elapsed_ms

    def get_memory(self, user_id: str, memory_id: str) -> tuple[Any, float]:
        _, body, elapsed_ms = self.request(
            "GET", f"/v1/memories/{memory_id}", user_id, expected={200}
        )
        return body, elapsed_ms


class GovernanceCaseRunner:
    def __init__(
        self,
        client: GovernanceClient,
        run_dir: Path,
        run_anchor: datetime,
        canary_user: str,
        canary_hash: str,
        visibility_timeout: float,
        poll_interval: float,
    ) -> None:
        self.client = client
        self.run_dir = run_dir
        self.run_anchor = run_anchor
        self.canary_user = canary_user
        self.canary_hash = canary_hash
        self.visibility_timeout = visibility_timeout
        self.poll_interval = poll_interval
        self.alias_to_id: dict[str, str] = {}
        self.id_to_alias: dict[str, str] = {}
        self.expected_memories: dict[str, dict[str, Any]] = {}
        self.states: dict[str, dict[str, Any]] = {}
        self.retrievals: dict[str, dict[str, Any]] = {}
        self.operation_results: dict[str, dict[str, Any]] = {}
        self.timings: list[dict[str, Any]] = []

    def write_memory(self, user_id: str, definition: dict[str, Any]) -> None:
        observed_at = self.run_anchor - timedelta(days=definition["age_days"])
        payload = {
            key: value
            for key, value in definition.items()
            if key
            not in {
                "alias",
                "age_days",
                "expected_effective_confidence",
                "expected_action",
                "require_pre_retrieval",
            }
        }
        payload["observed_at"] = observed_at.isoformat().replace("+00:00", "Z")
        started = time.perf_counter()
        stored = self.client.store(user_id, payload)
        elapsed_ms = (time.perf_counter() - started) * 1000
        alias = definition["alias"]
        memory_id = str(stored["memory_id"])
        self.alias_to_id[alias] = memory_id
        self.id_to_alias[memory_id] = alias
        self.expected_memories[alias] = {**payload, "memory_id": memory_id}
        self.timings.append(
            {"operation": "store", "alias": alias, "elapsed_ms": round(elapsed_ms, 3)}
        )

    def aliases_for(self, memories: list[dict[str, Any]]) -> list[str]:
        aliases = []
        for memory in memories:
            memory_id = str(memory.get("memory_id"))
            alias = self.id_to_alias.get(memory_id)
            if alias is None:
                alias = str((memory.get("extra_metadata") or {}).get("memory_alias", ""))
            if alias:
                aliases.append(alias)
        return sorted(aliases)

    def capture_state(self, user_id: str, state_alias: str, case_id: str) -> None:
        active = canonical_active_state(self.client.list_memories(user_id))
        record = {
            "at": utc_now(),
            "case_id": case_id,
            "user_id": user_id,
            "state_alias": state_alias,
            "active_memories": active,
            "active_aliases": self.aliases_for(active),
            "active_state_hash": sha256_json(active),
        }
        self.states[state_alias] = record
        append_jsonl(self.run_dir / "states.jsonl", record)

    def retrieval_expectation(self, case: dict[str, Any], alias: str) -> tuple[set[str], set[str]]:
        contains: set[str] = set()
        excludes: set[str] = set()
        for check in case["assertions"]:
            if check["at"] != alias:
                continue
            if check["type"] == "retrieval_contains":
                contains.update(check["aliases"])
            elif check["type"] == "retrieval_excludes":
                excludes.update(check["aliases"])
        return contains, excludes

    def retrieve(self, user_id: str, operation: dict[str, Any], case: dict[str, Any]) -> None:
        alias = operation["retrieval_alias"]
        required_contains, required_excludes = self.retrieval_expectation(case, alias)
        deadline = time.monotonic() + self.visibility_timeout
        attempts = 0
        started = time.perf_counter()
        results: list[dict[str, Any]] = []
        result_aliases: set[str] = set()
        while True:
            attempts += 1
            results = self.client.retrieve(user_id, operation["query"], operation["top_k"])
            result_aliases = set(self.aliases_for(results))
            met = required_contains <= result_aliases and not (required_excludes & result_aliases)
            if met or time.monotonic() >= deadline:
                break
            time.sleep(self.poll_interval)
        elapsed_ms = (time.perf_counter() - started) * 1000
        record = {
            "at": utc_now(),
            "case_id": case["case_id"],
            "user_id": user_id,
            "retrieval_alias": alias,
            "query": operation["query"],
            "top_k": operation["top_k"],
            "attempts": attempts,
            "elapsed_ms": round(elapsed_ms, 3),
            "required_contains": sorted(required_contains),
            "required_excludes": sorted(required_excludes),
            "returned_aliases": sorted(result_aliases),
            "results": results,
        }
        self.retrievals[alias] = record
        self.timings.append(
            {"operation": "retrieve", "alias": alias, "elapsed_ms": round(elapsed_ms, 3)}
        )
        append_jsonl(self.run_dir / "retrieval.jsonl", record)

    def run_operation(self, user_id: str, operation: dict[str, Any], case: dict[str, Any]) -> None:
        op = operation["op"]
        if op == "capture_state":
            self.capture_state(user_id, operation["state_alias"], case["case_id"])
            return
        if op == "retrieve":
            self.retrieve(user_id, operation, case)
            return
        if op == "governance":
            body, elapsed_ms = self.client.governance(user_id, operation["force"])
            alias = operation["operation_alias"]
            self.operation_results[alias] = {
                "status": operation["expected_status"],
                "body": body,
                "elapsed_ms": round(elapsed_ms, 3),
            }
            self.timings.append(
                {"operation": "governance", "alias": alias, "elapsed_ms": round(elapsed_ms, 3)}
            )
            return
        if op == "get_memory":
            target_alias = operation["target_alias"]
            body, elapsed_ms = self.client.get_memory(
                user_id, self.alias_to_id[target_alias]
            )
            alias = operation["operation_alias"]
            self.operation_results[alias] = {
                "status": operation["expected_status"],
                "body": body,
                "elapsed_ms": round(elapsed_ms, 3),
            }
            self.timings.append(
                {"operation": "get_memory", "alias": alias, "elapsed_ms": round(elapsed_ms, 3)}
            )
            return
        raise ValueError(f"unsupported operation: {op}")

    def memory_matches(
        self, alias: str, actual: Any, tolerance: float
    ) -> tuple[bool, dict[str, Any]]:
        expected = self.expected_memories[alias]
        if not isinstance(actual, dict):
            return False, {"reason": "response is not a memory object", "actual": actual}
        comparisons = {
            "memory_id": actual.get("memory_id") == expected["memory_id"],
            "content": actual.get("content") == expected["content"],
            "memory_type": actual.get("memory_type") == expected["memory_type"],
            "session_id": actual.get("session_id") == expected["session_id"],
            "subject_id": actual.get("subject_id") == expected["subject_id"],
            "trust_tier": actual.get("trust_tier") == expected["trust_tier"],
            "is_active": actual.get("is_active") is True,
            "observed_at": normalized_time(actual.get("observed_at"))
            == normalized_time(expected["observed_at"]),
            "extra_metadata": (actual.get("extra_metadata") or None)
            == (expected.get("extra_metadata") or None),
        }
        actual_confidence = float(actual.get("initial_confidence", -1))
        expected_confidence = float(expected["initial_confidence"])
        comparisons["initial_confidence"] = (
            abs(actual_confidence - expected_confidence) <= tolerance
        )
        return all(comparisons.values()), {
            "field_matches": comparisons,
            "actual_initial_confidence": actual_confidence,
            "expected_initial_confidence": expected_confidence,
            "float_tolerance": tolerance,
        }

    def evaluate_assertion(
        self, case: dict[str, Any], check: dict[str, Any]
    ) -> dict[str, Any]:
        kind = check["type"]
        actual: Any
        expected: Any
        passed: bool
        details: dict[str, Any] | None = None
        if kind == "exact_active_aliases":
            actual = self.states[check["at"]]["active_aliases"]
            expected = sorted(check["aliases"])
            passed = actual == expected
        elif kind in {"retrieval_contains", "retrieval_excludes"}:
            returned = set(self.retrievals[check["at"]]["returned_aliases"])
            targets = set(check["aliases"])
            actual = sorted(returned)
            expected = sorted(targets)
            passed = targets <= returned if kind == "retrieval_contains" else not (targets & returned)
        elif kind == "operation_body_value_equals":
            body = self.operation_results[check["at"]]["body"]
            actual = body.get(check["field"]) if isinstance(body, dict) else None
            expected = check["expected"]
            passed = actual == expected
        elif kind == "operation_body_is_null":
            actual = self.operation_results[check["at"]]["body"]
            expected = None
            passed = actual is None
        elif kind == "operation_body_memory_equals":
            actual = self.operation_results[check["at"]]["body"]
            expected = check["memory_alias"]
            passed, details = self.memory_matches(
                check["memory_alias"], actual, float(check["float_tolerance"])
            )
        elif kind == "state_hash_equals":
            actual = self.states[check["at"]]["active_state_hash"]
            expected = self.states[check["from"]]["active_state_hash"]
            passed = actual == expected
        elif kind == "canary_state_hash_equals":
            current = canonical_active_state(self.client.list_memories(self.canary_user))
            actual = sha256_json(current)
            expected = self.canary_hash
            passed = actual == expected
        else:
            raise ValueError(f"unsupported assertion: {kind}")
        result = {
            "at": utc_now(),
            "case_id": case["case_id"],
            "user_id": case["user_id"],
            "assertion_at": check["at"],
            "type": kind,
            "required": check["required"],
            "passed": passed,
            "actual": actual,
            "expected": expected,
        }
        if details is not None:
            result["details"] = details
        append_jsonl(self.run_dir / "assertions.jsonl", result)
        return result

    def run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        user_id = case["user_id"]
        if self.client.list_memories(user_id):
            raise RuntimeError(f"case user is not empty: {user_id}")
        for definition in case["initial_memories"]:
            self.write_memory(user_id, definition)
        for operation in case["operations"]:
            self.run_operation(user_id, operation, case)
        assertions = [self.evaluate_assertion(case, check) for check in case["assertions"]]
        required = [check for check in assertions if check["required"]]
        return {
            "case_id": case["case_id"],
            "user_id": user_id,
            "category": case["category"],
            "subtype": case["subtype"],
            "status": "PASS" if all(check["passed"] for check in required) else "FAIL",
            "required_assertions": len(required),
            "required_passed": sum(check["passed"] for check in required),
            "expected_deleted": sum(
                memory["expected_action"] == "delete"
                for memory in case["initial_memories"]
            ),
            "expected_retained": sum(
                memory["expected_action"] == "retain"
                for memory in case["initial_memories"]
            ),
            "timings": self.timings,
        }


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    project_root = script.parents[3]
    workspace_root = project_root.parent
    dataset_dir = project_root / "memoria/datasets/feature/low-confidence-governance"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=dataset_dir / "low-confidence-governance-formal-v1.jsonl",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=dataset_dir / "low-confidence-governance-formal-v1.schema.json",
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

    dataset = load_jsonl(args.dataset)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_dataset(dataset, schema)
    env = read_env(args.runtime / ".env")
    master_key = os.environ.get("MEMORIA_MASTER_KEY") or env.get("MEMORIA_MASTER_KEY")
    if not master_key:
        raise RuntimeError("MEMORIA_MASTER_KEY is not configured")

    args.run_dir.mkdir(parents=True)
    run_anchor = datetime.now(timezone.utc).replace(microsecond=0)
    source_repo = args.runtime / "source/Memoria"
    source_diff = subprocess.check_output(
        ["git", "-C", str(source_repo), "diff", "--binary"],
        stderr=subprocess.DEVNULL,
    )
    manifest = {
        "created_at": utc_now(),
        "suite": SUITE,
        "protocol": "controlled-direct-store-low-confidence-governance-v1",
        "dataset_path": str(args.dataset),
        "dataset_sha256": sha256_file(args.dataset),
        "schema_path": str(args.schema),
        "schema_sha256": sha256_file(args.schema),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "case_count": len(dataset),
        "category_counts": dict(Counter(case["category"] for case in dataset)),
        "case_ids": [case["case_id"] for case in dataset],
        "case_user_ids": [case["user_id"] for case in dataset],
        "canary_user_id": "feature-lcg-formal-canary",
        "run_anchor_utc": run_anchor.isoformat().replace("+00:00", "Z"),
        "governance_threshold": GOVERNANCE_THRESHOLD,
        "retrieval_min_effective_confidence": RETRIEVAL_MIN_CONFIDENCE,
        "half_life_days": HALF_LIFE_DAYS,
        "write_endpoint": "/v1/memories",
        "governance_endpoint": "/v1/governance",
        "governance_force": True,
        "deleted_memory_get_semantics": "HTTP 200 with null body",
        "orphan_graph_cleaned_scope": "diagnostic-only",
        "api_url": args.api_url,
        "embedding_provider": env.get("MEMORIA_EMBEDDING_PROVIDER"),
        "embedding_model": env.get("MEMORIA_EMBEDDING_MODEL"),
        "embedding_dimension": env.get("MEMORIA_EMBEDDING_DIM"),
        "internal_llm": False,
        "memoria_version": "0.4.0",
        "memoria_commit": git_value(source_repo, "rev-parse", "HEAD"),
        "memoria_source_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
        "matrixone_image": env.get("MATRIXONE_IMAGE"),
        "matrixone_data_dir": env.get("MATRIXONE_DATA_DIR"),
        "timeout_seconds": args.timeout,
        "visibility_timeout_seconds": args.visibility_timeout,
        "poll_interval_seconds": args.poll_interval,
        "state_hash_excludes": ["created_at", "retrieval_score"],
    }
    write_json(args.run_dir / "manifest.json", manifest)
    (args.run_dir / "cases.jsonl").write_text(
        args.dataset.read_text(encoding="utf-8"), encoding="utf-8"
    )

    client = GovernanceClient(
        args.api_url,
        master_key,
        args.run_dir / "operations.jsonl",
        args.timeout,
        args.max_retries,
    )
    _, stats, _ = client.request("GET", "/admin/stats", "formal-preflight")
    write_json(args.run_dir / "initial-state.json", {"at": utc_now(), "stats": stats})
    expected_empty = {"total_users": 0, "total_memories": 0, "total_snapshots": 0}
    actual_empty = {key: stats.get(key) for key in expected_empty}
    if actual_empty != expected_empty:
        raise RuntimeError(
            f"formal database is not empty: expected {expected_empty}, got {actual_empty}"
        )

    canary_user = manifest["canary_user_id"]
    canary_payload = {
        "content": "The benchmark canary prefers green notebooks.",
        "memory_type": "semantic",
        "session_id": f"{SUITE}-canary-session",
        "subject_id": "benchmark-canary",
        "trust_tier": "T1",
        "initial_confidence": 0.99,
        "observed_at": manifest["run_anchor_utc"],
        "extra_metadata": {
            "benchmark": "memoria-features",
            "suite": SUITE,
            "case_id": "canary",
            "memory_alias": "canary",
            "field": "control",
        },
    }
    canary = client.store(canary_user, canary_payload)
    canary_hash = sha256_json(canonical_active_state(client.list_memories(canary_user)))
    write_json(
        args.run_dir / "canary.json",
        {
            "user_id": canary_user,
            "memory_id": canary["memory_id"],
            "baseline_hash": canary_hash,
        },
    )

    results = []
    for case in dataset:
        runner = GovernanceCaseRunner(
            client,
            args.run_dir,
            run_anchor,
            canary_user,
            canary_hash,
            args.visibility_timeout,
            args.poll_interval,
        )
        try:
            result = runner.run_case(case)
        except Exception as exc:
            result = {
                "case_id": case["case_id"],
                "user_id": case["user_id"],
                "category": case["category"],
                "subtype": case["subtype"],
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }
            append_jsonl(args.run_dir / "errors.jsonl", {"at": utc_now(), **result})
        results.append(result)
        append_jsonl(args.run_dir / "case-results.jsonl", result)
        print(
            f"{result['status']} {result['case_id']} "
            f"{result.get('required_passed', 0)}/{result.get('required_assertions', 0)}"
        )

    counts = {
        status: sum(result["status"] == status for result in results)
        for status in ("PASS", "FAIL", "ERROR")
    }
    category_results = {}
    for category in EXPECTED_CATEGORIES:
        selected = [result for result in results if result["category"] == category]
        category_results[category] = {
            "total": len(selected),
            "pass": sum(result["status"] == "PASS" for result in selected),
            "fail": sum(result["status"] == "FAIL" for result in selected),
            "error": sum(result["status"] == "ERROR" for result in selected),
        }
    declared_assertions = sum(
        result.get("required_assertions", 0) for result in results
    )
    passed_assertions = sum(result.get("required_passed", 0) for result in results)
    metrics = {
        "completed_at": utc_now(),
        "total_cases": len(results),
        "status_counts": counts,
        "strict_pass_rate_all_cases": counts["PASS"] / len(results),
        "system_error_rate": counts["ERROR"] / len(results),
        "all_passed": counts["PASS"] == len(results),
        "category_results": category_results,
        "required_assertions": declared_assertions,
        "required_assertions_passed": passed_assertions,
        "expected_deleted_memories": sum(
            result.get("expected_deleted", 0) for result in results
        ),
        "expected_retained_memories": sum(
            result.get("expected_retained", 0) for result in results
        ),
        "case_results": results,
    }
    write_json(args.run_dir / "metrics.json", metrics)
    _, final_stats, _ = client.request("GET", "/admin/stats", "formal-postflight")
    write_json(args.run_dir / "final-state.json", {"at": utc_now(), "stats": final_stats})
    manifest.update(
        {"completed_at": metrics["completed_at"], "status": "complete"}
    )
    write_json(args.run_dir / "manifest.json", manifest)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if metrics["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
