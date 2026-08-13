#!/usr/bin/env python3
"""运行 Memoria 重复与近重复记忆处理 50 用例正式实验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pymysql
from jsonschema import Draft202012Validator, FormatChecker

from run_branch_diff_merge_smoke import BranchClient
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


SUITE = "duplicate-memory-handling-formal-v1"
EXPECTED_CATEGORIES = {
    "exact_duplicate_reuse": 10,
    "semantic_equivalent_handling": 24,
    "coexistence_scope_isolation": 16,
}


def validate_dataset(cases: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [(i, e) for i, case in enumerate(cases, 1) for e in validator.iter_errors(case)]
    if errors:
        line, error = errors[0]
        raise ValueError(f"dataset line {line} {error.json_path}: {error.message}")
    if len(cases) != 50 or len({c["case_id"] for c in cases}) != 50:
        raise ValueError("formal suite must contain 50 unique cases")
    if Counter(c["category"] for c in cases) != Counter(EXPECTED_CATEGORIES):
        raise ValueError("category distribution mismatch")
    operation_count = Counter(op["op"] for c in cases for op in c["operations"])
    if operation_count["store_memory"] != 104:
        raise ValueError("expected exactly 104 store operations")


class Client(BranchClient):
    def list_on(self, user_id: str, branch: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 500, "branch": branch}
            if cursor:
                params["cursor"] = cursor
            _, body, _ = self.request("GET", "/v1/memories", user_id, params=params)
            items.extend(body.get("items", []))
            cursor = body.get("next_cursor")
            if not cursor:
                return items

    def retrieve_on(self, user_id: str, branch: str, query: str, top_k: int) -> list[dict[str, Any]]:
        _, body, _ = self.request(
            "POST", "/v1/memories/retrieve", user_id,
            json_body={"query": query, "top_k": top_k, "branch": branch},
        )
        return body.get("results", []) if isinstance(body, dict) else body

    def history_on(self, user_id: str, branch: str, memory_id: str) -> list[dict[str, Any]] | None:
        status, body, _ = self.request(
            "GET", f"/v1/memories/{memory_id}/history", user_id,
            params={"branch": branch}, expected={200}, allow={404},
        )
        return list(body.get("versions", [])) if status == 200 else None


class DatabaseInspector:
    def __init__(self, env: dict[str, str]) -> None:
        self.connection = pymysql.connect(
            host="127.0.0.1", port=int(env.get("MATRIXONE_PORT", "6011")),
            user="root", password=env.get("MEMORIA_DB_PASSWORD", ""),
            charset="utf8mb4", autocommit=True,
        )

    @staticmethod
    def ident(value: str) -> str:
        return "`" + value.replace("`", "``") + "`"

    def database(self, user_id: str) -> str:
        with self.connection.cursor() as cur:
            cur.execute("SELECT db_name FROM memoria_shared.mem_user_registry WHERE user_id=%s", (user_id,))
            row = cur.fetchone()
        if not row:
            raise RuntimeError(f"database registry missing for {user_id}")
        return str(row[0])

    def table(self, user_id: str, branch: str) -> tuple[str, str]:
        database = self.database(user_id)
        if branch == "main":
            return database, "mem_memories"
        sql = f"SELECT table_name FROM {self.ident(database)}.mem_branches WHERE name=%s"
        with self.connection.cursor() as cur:
            cur.execute(sql, (branch,))
            row = cur.fetchone()
        if not row:
            raise RuntimeError(f"branch table missing: {user_id}:{branch}")
        return database, str(row[0])

    def rows(self, user_id: str, branch: str) -> list[dict[str, Any]]:
        database, table = self.table(user_id, branch)
        sql = (
            f"SELECT memory_id, content, memory_type, subject_id, session_id, is_active, "
            f"superseded_by, extra_metadata FROM {self.ident(database)}.{self.ident(table)} "
            "WHERE user_id=%s ORDER BY memory_id"
        )
        with self.connection.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (user_id,))
            return list(cur.fetchall())

    def vector_distance(self, user_id: str, branch: str, left: str, right: str) -> dict[str, float] | None:
        if left == right:
            return {"l2_distance": 0.0, "cosine_similarity": 1.0}
        database, table = self.table(user_id, branch)
        qualified = f"{self.ident(database)}.{self.ident(table)}"
        sql = (
            f"SELECT l2_distance(a.embedding,b.embedding), cosine_similarity(a.embedding,b.embedding) "
            f"FROM {qualified} a CROSS JOIN {qualified} b "
            "WHERE a.memory_id=%s AND b.memory_id=%s"
        )
        with self.connection.cursor() as cur:
            cur.execute(sql, (left, right))
            row = cur.fetchone()
        if not row:
            return None
        return {"l2_distance": float(row[0]), "cosine_similarity": float(row[1])}


def scope_parts(case: dict[str, Any], scope: str) -> tuple[str, str, str]:
    user_ref, branch = scope.split(":", 1)
    return user_ref, case["users"][user_ref], branch


def store_definition(case: dict[str, Any], alias: str) -> dict[str, Any]:
    return next(op for op in case["operations"] if op["op"] == "store_memory" and op["memory_alias"] == alias)


def expected_id_set(alias_to_id: dict[str, str], aliases: list[str]) -> set[str]:
    return {alias_to_id[a] for a in aliases}


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    project = script.parents[3]
    data = project / "memoria/datasets/feature/duplicate-memory-handling"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=data / f"{SUITE}.jsonl")
    parser.add_argument("--schema", type=Path, default=data / f"{SUITE}.schema.json")
    parser.add_argument("--runtime", type=Path, default=project.parent / "memoria_runtime")
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--only-case", action="append", default=[])
    parser.add_argument("--allow-nonempty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for key in ("dataset", "schema", "runtime", "run_dir"):
        setattr(args, key, getattr(args, key).resolve())
    if args.run_dir.exists():
        raise FileExistsError(f"immutable run directory already exists: {args.run_dir}")
    cases = load_jsonl(args.dataset)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_dataset(cases, schema)
    if args.only_case:
        wanted = set(args.only_case)
        cases = [case for case in cases if case["case_id"] in wanted]
        if {case["case_id"] for case in cases} != wanted:
            raise ValueError("--only-case contains an unknown case id")
    env = read_env(args.runtime / ".env")
    master_key = os.environ.get("MEMORIA_MASTER_KEY") or env.get("MEMORIA_MASTER_KEY")
    if not master_key:
        raise RuntimeError("MEMORIA_MASTER_KEY is not configured")
    args.run_dir.mkdir(parents=True)
    source = args.runtime / "source/Memoria"
    source_diff = subprocess.check_output(["git", "-C", str(source), "diff", "--binary"])
    manifest = {
        "created_at": utc_now(), "suite": SUITE,
        "protocol": "controlled-direct-store-three-category-v1",
        "dataset_path": str(args.dataset), "dataset_sha256": sha256_file(args.dataset),
        "schema_path": str(args.schema), "schema_sha256": sha256_file(args.schema),
        "runner_sha256": sha256_file(Path(__file__).resolve()), "case_count": len(cases),
        "category_counts": dict(Counter(c["category"] for c in cases)),
        "subtype_counts": dict(Counter(c["subtype"] for c in cases)),
        "memoria_version": "0.4.0", "memoria_commit": git_value(source, "rev-parse", "HEAD"),
        "memoria_source_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
        "embedding_provider": env.get("MEMORIA_EMBEDDING_PROVIDER"),
        "embedding_model": env.get("MEMORIA_EMBEDDING_MODEL"),
        "embedding_dimension": env.get("MEMORIA_EMBEDDING_DIM"),
        "near_duplicate_l2_threshold": 0.3162,
        "matrixone_image": env.get("MATRIXONE_IMAGE"),
        "matrixone_data_dir": env.get("MATRIXONE_DATA_DIR"),
        "canary_user_id": "feature-dmh-formal-canary",
    }
    write_json(args.run_dir / "manifest.json", manifest)
    (args.run_dir / "cases.jsonl").write_text(args.dataset.read_text(encoding="utf-8"), encoding="utf-8")
    client = Client(args.api_url, master_key, args.run_dir / "operations.jsonl", args.timeout, args.max_retries)
    _, stats, _ = client.request("GET", "/admin/stats", "formal-preflight")
    write_json(args.run_dir / "initial-state.json", {"at": utc_now(), "stats": stats})
    expected_empty = {"total_users": 0, "total_memories": 0, "total_snapshots": 0}
    if not args.allow_nonempty and {k: stats.get(k) for k in expected_empty} != expected_empty:
        raise RuntimeError(f"formal database is not empty: {stats}")
    canary = client.store(manifest["canary_user_id"], canary_memory(SUITE))
    canary_hash = sha256_json(canonical_active_state(client.list_memories(manifest["canary_user_id"])))
    write_json(args.run_dir / "canary.json", {"memory_id": canary["memory_id"], "baseline_hash": canary_hash})
    db = DatabaseInspector(env)
    results: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []

    for case in cases:
        alias_to_id: dict[str, str] = {}
        assertions: list[dict[str, Any]] = []
        try:
            for operation in case["operations"]:
                op = operation["op"]
                if op == "create_branch":
                    user_id = case["users"][operation.get("user_ref", "primary")]
                    existing = {row["name"] for row in client.branches(user_id).get("branches", [])}
                    if operation["branch"] not in existing:
                        client.create_branch(user_id, operation["branch"], None, None, operation["expected_status"])
                elif op == "store_memory":
                    user_id = case["users"][operation["user_ref"]]
                    payload = {k: v for k, v in operation.items() if k not in {"op", "operation_alias", "memory_alias", "user_ref", "expected_status"}}
                    stored = client.store(user_id, payload)
                    alias_to_id[operation["memory_alias"]] = str(stored["memory_id"])

            scopes = sorted(set(case["expected_semantic_state"]["active_aliases_by_scope"]) |
                            set(case["expected_semantic_state"]["retrieval_contains_by_scope"]) |
                            set(case["expected_semantic_state"]["retrieval_excludes_by_scope"]))
            for scope in scopes:
                _, user_id, branch = scope_parts(case, scope)
                active = client.list_on(user_id, branch)
                actual_ids = {str(row["memory_id"]) for row in active}
                expected_aliases = case["expected_semantic_state"]["active_aliases_by_scope"].get(scope, [])
                check = {"case_id": case["case_id"], "type": "active_state", "scope": scope,
                         "expected_aliases": expected_aliases, "expected_ids": sorted(expected_id_set(alias_to_id, expected_aliases)),
                         "actual_ids": sorted(actual_ids)}
                check["passed"] = actual_ids == set(check["expected_ids"])
                assertions.append(check); append_jsonl(args.run_dir / "states.jsonl", {**check, "api_rows": active, "db_rows": db.rows(user_id, branch)})

                query_alias = next(iter(case["expected_semantic_state"]["retrieval_contains_by_scope"].get(scope, [])), "v2")
                query = store_definition(case, query_alias)["content"]
                retrieved = client.retrieve_on(user_id, branch, query, 10)
                retrieved_ids = {str(row["memory_id"]) for row in retrieved}
                contains = case["expected_semantic_state"]["retrieval_contains_by_scope"].get(scope, [])
                excludes = case["expected_semantic_state"]["retrieval_excludes_by_scope"].get(scope, [])
                rcheck = {"case_id": case["case_id"], "type": "retrieval", "scope": scope,
                          "contains_aliases": contains, "excludes_aliases": excludes,
                          "actual_ids": sorted(retrieved_ids)}
                rcheck["passed"] = expected_id_set(alias_to_id, contains) <= retrieved_ids and not (expected_id_set(alias_to_id, excludes) & retrieved_ids)
                assertions.append(rcheck); append_jsonl(args.run_dir / "retrievals.jsonl", {**rcheck, "results": retrieved})

            for alias, expected_length in case["expected_semantic_state"]["history_lengths"].items():
                definition = store_definition(case, alias)
                user_id = case["users"][definition["user_ref"]]
                history = client.history_on(user_id, definition["branch"], alias_to_id[alias])
                check = {"case_id": case["case_id"], "type": "history_length", "alias": alias,
                         "expected": expected_length, "actual": None if history is None else len(history)}
                check["passed"] = check["actual"] == expected_length
                assertions.append(check); append_jsonl(args.run_dir / "histories.jsonl", {**check, "history": history})

            observed_actions = []
            for relation in case["relations"]:
                left, right = alias_to_id[relation["from_alias"]], alias_to_id[relation["to_alias"]]
                definition = store_definition(case, relation["from_alias"])
                user_id = case["users"][definition["user_ref"]]; branch = definition["branch"]
                history = client.history_on(user_id, branch, left)
                if left == right:
                    observed = "reuse"
                elif history and any(str(row.get("memory_id")) == right for row in history[1:]):
                    observed = "supersede"
                else:
                    observed = "coexist"
                observed_actions.append(observed)
                row = {"case_id": case["case_id"], **relation, "from_id": left, "to_id": right,
                       "observed_action": observed, "passed": observed == relation["semantic_expected_action"],
                       "database_measurement": db.vector_distance(user_id, branch, left, right)}
                relation_rows.append(row); append_jsonl(args.run_dir / "relations.jsonl", row)
            semantic = {"case_id": case["case_id"], "type": "semantic_actions",
                        "expected": case["expected_semantic_state"]["semantic_actions"], "actual": observed_actions}
            semantic["passed"] = semantic["actual"] == semantic["expected"]
            assertions.append(semantic)
            canary_actual = sha256_json(canonical_active_state(client.list_memories(manifest["canary_user_id"])))
            assertions.append({"case_id": case["case_id"], "type": "canary_isolation", "passed": canary_actual == canary_hash})
            for assertion in assertions:
                append_jsonl(args.run_dir / "assertions.jsonl", assertion)
            status = "PASS" if all(a["passed"] for a in assertions) else "FAIL"
            result = {"case_id": case["case_id"], "category": case["category"], "subtype": case["subtype"],
                      "status": status, "passed_assertions": sum(a["passed"] for a in assertions),
                      "total_assertions": len(assertions), "failed_assertions": [a for a in assertions if not a["passed"]]}
        except Exception as exc:
            result = {"case_id": case["case_id"], "category": case["category"], "subtype": case["subtype"],
                      "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
            append_jsonl(args.run_dir / "errors.jsonl", {"at": utc_now(), **result})
        results.append(result); append_jsonl(args.run_dir / "case-results.jsonl", result)
        print(f"[{len(results):02d}/{len(cases):02d}] {case['case_id']}: {result['status']}", flush=True)

    def grouped(field: str) -> dict[str, Any]:
        output = {}
        for value in sorted({r[field] for r in results}):
            selected = [r for r in results if r[field] == value]
            passed = sum(r["status"] == "PASS" for r in selected)
            output[value] = {"total": len(selected), "pass": passed,
                             "fail": sum(r["status"] == "FAIL" for r in selected),
                             "error": sum(r["status"] == "ERROR" for r in selected),
                             "accuracy": passed / len(selected)}
        return output

    counts = Counter(r["status"] for r in results)
    relation_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in relation_rows:
        relation_groups[row.get("selection_measurement", {}).get("selection_band", "not_applicable")].append(row)
    metrics = {"completed_at": utc_now(), "total_cases": len(cases), "status_counts": dict(counts),
               "strict_pass_rate": counts["PASS"] / len(cases), "category_results": grouped("category"),
               "subtype_results": grouped("subtype"),
               "selection_band_relation_results": {k: {"total": len(v), "pass": sum(x["passed"] for x in v),
                                                        "accuracy": sum(x["passed"] for x in v) / len(v)} for k, v in sorted(relation_groups.items())},
               "case_results": results}
    write_json(args.run_dir / "metrics.json", metrics)
    _, final_stats, _ = client.request("GET", "/admin/stats", "formal-final")
    write_json(args.run_dir / "final-state.json", {"at": utc_now(), "stats": final_stats})
    manifest.update({"completed_at": metrics["completed_at"], "status": "complete"})
    write_json(args.run_dir / "manifest.json", manifest)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if counts["PASS"] == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
