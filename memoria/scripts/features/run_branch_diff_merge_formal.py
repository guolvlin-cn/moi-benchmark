#!/usr/bin/env python3
"""Run the deterministic 50-case Memoria Branch/Diff/Merge Formal v1 suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from run_branch_diff_merge_smoke import BranchCaseRunner, BranchClient
from run_snapshot_rollback_smoke import (
    append_jsonl,
    canary_memory,
    canonical_active_state,
    git_value,
    load_jsonl,
    read_env,
    sha256_file,
    sha256_json,
    utc_now,
    write_json,
)


SUITE = "branch-diff-merge-formal-v1"
EXPECTED_CATEGORIES = {
    "branch_isolation": 12,
    "diff_correctness": 14,
    "merge_correctness": 12,
    "conflict_detection": 12,
}


def validate_dataset(dataset: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for line, case in enumerate(dataset, 1):
        errors.extend((line, error) for error in validator.iter_errors(case))
    if errors:
        line, error = errors[0]
        raise ValueError(f"dataset line {line} {error.json_path}: {error.message}")
    if len(dataset) != 50:
        raise ValueError(f"Formal suite must have exactly 50 cases, got {len(dataset)}")
    if len({case["case_id"] for case in dataset}) != len(dataset):
        raise ValueError("duplicate case_id")
    if len({case["user_id"] for case in dataset}) != len(dataset):
        raise ValueError("duplicate user_id")
    categories = Counter(case["category"] for case in dataset)
    if categories != EXPECTED_CATEGORIES:
        raise ValueError(
            f"formal category distribution mismatch: {dict(categories)}"
        )
    for case in dataset:
        merge_operations = [
            operation
            for operation in case["operations"]
            if operation["op"] == "merge_branch"
        ]
        if case["category"] == "conflict_detection" and merge_operations:
            raise ValueError(
                f"conflict case contains merge operation: {case['case_id']}"
            )
        for operation in merge_operations:
            if operation["strategy"] != "append":
                raise ValueError(
                    f"unverified merge strategy in {case['case_id']}: "
                    f"{operation['strategy']}"
                )


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    project_root = script.parents[3]
    workspace_root = project_root.parent
    data = project_root / "memoria/datasets/feature/branch-diff-merge"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=data / "branch-diff-merge-formal-v1.jsonl",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=data / "branch-diff-merge-formal-v1.schema.json",
    )
    parser.add_argument(
        "--runtime", type=Path, default=workspace_root / "memoria_runtime"
    )
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
        raise FileExistsError(
            f"immutable run directory already exists: {args.run_dir}"
        )

    dataset = load_jsonl(args.dataset)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_dataset(dataset, schema)
    env = read_env(args.runtime / ".env")
    master_key = os.environ.get("MEMORIA_MASTER_KEY") or env.get(
        "MEMORIA_MASTER_KEY"
    )
    if not master_key:
        raise RuntimeError("MEMORIA_MASTER_KEY is not configured")

    args.run_dir.mkdir(parents=True)
    source_repo = args.runtime / "source/Memoria"
    source_diff = subprocess.check_output(
        ["git", "-C", str(source_repo), "diff", "--binary"],
        stderr=subprocess.DEVNULL,
    )
    categories = Counter(case["category"] for case in dataset)
    subtypes = Counter(case["subtype"] for case in dataset)
    negative_controls = [
        case["case_id"]
        for case in dataset
        if "negative-control" in case["tags"]
    ]
    manifest = {
        "created_at": utc_now(),
        "suite": SUITE,
        "protocol": "controlled-direct-store-branch-state-machine-v1",
        "dataset_path": str(args.dataset),
        "dataset_sha256": sha256_file(args.dataset),
        "schema_path": str(args.schema),
        "schema_sha256": sha256_file(args.schema),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "case_count": len(dataset),
        "category_counts": dict(categories),
        "subtype_counts": dict(subtypes),
        "case_ids": [case["case_id"] for case in dataset],
        "case_user_ids": [case["user_id"] for case in dataset],
        "negative_control_case_ids": negative_controls,
        "canary_user_id": "feature-bdm-formal-canary",
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
        "merge_semantic_boundary": (
            "append-only merge is tested only on logically non-conflicting cases"
        ),
        "conflict_scope": (
            "detection and main-state preservation only; no merge/apply/pick"
        ),
    }
    write_json(args.run_dir / "manifest.json", manifest)
    (args.run_dir / "cases.jsonl").write_text(
        args.dataset.read_text(encoding="utf-8"), encoding="utf-8"
    )

    client = BranchClient(
        args.api_url,
        master_key,
        args.run_dir / "operations.jsonl",
        args.timeout,
        args.max_retries,
    )
    _, stats, _ = client.request("GET", "/admin/stats", "formal-preflight")
    write_json(
        args.run_dir / "initial-state.json", {"at": utc_now(), "stats": stats}
    )
    expected_empty = {
        "total_users": 0,
        "total_memories": 0,
        "total_snapshots": 0,
    }
    actual_empty = {key: stats.get(key) for key in expected_empty}
    if actual_empty != expected_empty:
        raise RuntimeError(
            f"formal database is not empty: expected {expected_empty}, got {actual_empty}"
        )

    canary_user = manifest["canary_user_id"]
    canary = client.store(canary_user, canary_memory(SUITE))
    canary_hash = sha256_json(
        canonical_active_state(client.list_memories(canary_user))
    )
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
                "subtype": case["subtype"],
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }
            append_jsonl(
                args.run_dir / "errors.jsonl", {"at": utc_now(), **result}
            )
        result["subtype"] = case["subtype"]
        results.append(result)
        append_jsonl(args.run_dir / "case-results.jsonl", result)

    counts = {
        status: sum(row["status"] == status for row in results)
        for status in ("PASS", "FAIL", "ERROR")
    }
    category_results = {}
    for category in EXPECTED_CATEGORIES:
        selected = [row for row in results if row["category"] == category]
        category_results[category] = {
            "total": len(selected),
            "pass": sum(row["status"] == "PASS" for row in selected),
            "fail": sum(row["status"] == "FAIL" for row in selected),
            "error": sum(row["status"] == "ERROR" for row in selected),
        }
    metrics = {
        "completed_at": utc_now(),
        "total_cases": len(results),
        "status_counts": counts,
        "strict_pass_rate_all_cases": counts["PASS"] / len(results),
        "system_error_rate": counts["ERROR"] / len(results),
        "all_passed": counts["PASS"] == len(results),
        "category_results": category_results,
        "case_results": results,
    }
    write_json(args.run_dir / "metrics.json", metrics)
    manifest.update({"completed_at": metrics["completed_at"], "status": "complete"})
    write_json(args.run_dir / "manifest.json", manifest)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if metrics["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
