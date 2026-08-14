#!/usr/bin/env python3
"""Build the 50-case deterministic Memoria snapshot/rollback formal dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUITE = "snapshot-rollback-formal-v1"
PEOPLE = [
    "Alice", "Ben", "Chloe", "Daniel", "Emma", "Felix", "Grace", "Henry", "Iris", "Jack",
    "Kelly", "Leo", "Maya", "Noah", "Olivia", "Peter", "Quinn", "Ruby", "Simon", "Tina",
    "Uma", "Victor", "Wendy", "Xavier", "Yuki", "Zoe", "Aaron", "Bella", "Caleb", "Diana",
    "Ethan", "Fiona", "Gavin", "Hannah", "Ian", "Julia", "Kevin", "Lina", "Martin", "Nina",
    "Owen", "Paula", "Ryan", "Sara", "Tom", "Vera", "Will", "Xena", "Yan", "Zara",
]
CITIES = ["Beijing", "Shanghai", "Hangzhou", "Suzhou", "Nanjing", "Chengdu", "Wuhan", "Xiamen"]
PROJECTS = ["Cedar", "Maple", "Orchid", "Harbor", "Nimbus", "Quartz", "Willow", "Atlas"]
DRINKS = ["Americano coffee", "green tea", "flat white", "oolong tea", "sparkling water"]
LANGUAGES = ["Spanish", "Japanese", "French", "German", "Korean"]


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def memory(
    number: int,
    person: str,
    alias: str,
    content: str,
    field: str,
    memory_type: str = "semantic",
) -> dict[str, Any]:
    return {
        "alias": alias,
        "content": content,
        "memory_type": memory_type,
        "session_id": f"sr-formal-{number:03d}-session-01",
        "subject_id": person.lower(),
        "trust_tier": "T2",
        "initial_confidence": 0.95,
        "observed_at": f"2025-{((number - 1) % 12) + 1:02d}-{((number - 1) % 27) + 1:02d}T08:00:00Z",
        "extra_metadata": {
            "benchmark": "memoria-features",
            "suite": SUITE,
            "case_id": f"sr-formal-{number:03d}",
            "memory_alias": alias,
            "field": field,
        },
    }


def base_memories(number: int, person: str, count: int = 3) -> list[dict[str, Any]]:
    city = CITIES[number % len(CITIES)]
    project = PROJECTS[number % len(PROJECTS)]
    rows = [
        memory(number, person, "residence_old", f"{person} lives in {city}.", "residence"),
        memory(
            number,
            person,
            "project_old",
            f"{person} is working on Project {project}.",
            "project",
            "working",
        ),
        memory(
            number,
            person,
            "drink_old",
            f"{person} prefers {DRINKS[number % len(DRINKS)]} in the afternoon.",
            "beverage",
            "profile",
        ),
        memory(
            number,
            person,
            "language_old",
            f"{person} is learning {LANGUAGES[number % len(LANGUAGES)]}.",
            "language",
        ),
        memory(
            number,
            person,
            "timezone_old",
            f"{person} uses the Asia/Shanghai time zone.",
            "timezone",
            "profile",
        ),
    ]
    return rows[:count]


def capture(alias: str) -> dict[str, Any]:
    return {"op": "capture_state", "state_alias": alias}


def retrieve(alias: str, query: str) -> dict[str, Any]:
    return {"op": "retrieve", "retrieval_alias": alias, "query": query, "top_k": 20}


def snapshot(alias: str, name: str, *, operation_alias: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "op": "create_snapshot",
        "snapshot_alias": alias,
        "snapshot_name": name,
        "description": f"Formal benchmark snapshot {name}",
        "expected_status": 201,
    }
    if operation_alias:
        row["operation_alias"] = operation_alias
    return row


def rollback(alias: str, expected_state: str, *, operation_alias: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "op": "rollback",
        "snapshot_alias": alias,
        "expected_state_from": expected_state,
        "expected_status": 200,
    }
    if operation_alias:
        row["operation_alias"] = operation_alias
    return row


def assertion(at: str, kind: str, **values: Any) -> dict[str, Any]:
    return {"at": at, "type": kind, "required": True, **values}


def state_assertions(at: str, aliases: list[str], from_state: str | None = None) -> list[dict[str, Any]]:
    rows = [assertion(at, "exact_active_aliases", aliases=aliases)]
    if from_state:
        rows.append(assertion(at, "state_hash_equals", **{"from": from_state}))
    return rows


def retrieval_assertions(
    at: str,
    contains: list[str] | None = None,
    excludes: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if contains:
        rows.append(assertion(at, "retrieval_contains", aliases=contains))
    if excludes:
        rows.append(assertion(at, "retrieval_excludes", aliases=excludes))
    return rows


def case(
    number: int,
    slug: str,
    category: str,
    description: str,
    initial: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    tags: list[str],
) -> dict[str, Any]:
    case_id = f"sr-formal-{number:03d}-{slug}"
    for item in initial:
        item["extra_metadata"]["case_id"] = case_id
    for operation in operations:
        if operation.get("op") == "store":
            operation["memory"]["extra_metadata"]["case_id"] = case_id
    return {
        "schema_version": "1.0",
        "suite": SUITE,
        "case_id": case_id,
        "category": category,
        "track": "controlled-direct-store",
        "user_id": f"feature-sr-formal-{number:03d}",
        "description": description,
        "initial_memories": initial,
        "operations": operations,
        "assertions": assertions,
        "tags": tags,
    }


def single_cases() -> list[dict[str, Any]]:
    rows = []
    for number in range(1, 13):
        person = PEOPLE[number - 1]
        initial = base_memories(number, person, 3)
        baseline = [item["alias"] for item in initial]
        snap = f"sr_formal_{number:03d}_s1"
        mode = (number - 1) // 4
        if mode == 0:  # correct
            new_city = CITIES[(number + 3) % len(CITIES)]
            query = f"Where does {person} live?"
            mutated = ["residence_new", "project_old", "drink_old"]
            operations = [
                capture("baseline"), retrieve("baseline_query", query), snapshot("s1", snap),
                {"op": "correct", "target_alias": "residence_old", "result_alias": "residence_new", "new_content": f"{person} lives in {new_city}.", "reason": "Formal post-snapshot correction"},
                capture("mutated"), retrieve("mutated_query", query), rollback("s1", "baseline"),
                capture("rolled_back"), retrieve("rollback_query", query),
            ]
            checks = state_assertions("baseline", baseline) + retrieval_assertions("baseline_query", ["residence_old"])
            checks += state_assertions("mutated", mutated) + [assertion("mutated", "state_hash_differs", **{"from": "baseline"})]
            checks += retrieval_assertions("mutated_query", ["residence_new"], ["residence_old"])
            checks += state_assertions("rolled_back", baseline, "baseline") + [assertion("rolled_back", "absent_aliases", aliases=["residence_new"])]
            checks += retrieval_assertions("rollback_query", ["residence_old"], ["residence_new"])
            slug = "single-correct"
        elif mode == 1:  # add
            pet = memory(number, person, "pet_added", f"{person} has a dog named Pepper.", "pet")
            query = f"What pet does {person} have?"
            operations = [
                capture("baseline"), retrieve("baseline_query", query), snapshot("s1", snap),
                {"op": "store", "memory": pet}, capture("mutated"), retrieve("mutated_query", query),
                rollback("s1", "baseline"), capture("rolled_back"), retrieve("rollback_query", query),
            ]
            checks = state_assertions("baseline", baseline) + retrieval_assertions("baseline_query", excludes=["pet_added"])
            checks += state_assertions("mutated", baseline + ["pet_added"]) + [assertion("mutated", "state_hash_differs", **{"from": "baseline"})]
            checks += retrieval_assertions("mutated_query", ["pet_added"])
            checks += state_assertions("rolled_back", baseline, "baseline") + [assertion("rolled_back", "absent_aliases", aliases=["pet_added"])]
            checks += retrieval_assertions("rollback_query", excludes=["pet_added"])
            slug = "single-add"
        else:  # delete
            query = f"What does {person} prefer to drink in the afternoon?"
            operations = [
                capture("baseline"), retrieve("baseline_query", query), snapshot("s1", snap),
                {"op": "delete", "target_alias": "drink_old"}, capture("mutated"),
                retrieve("mutated_query", query), rollback("s1", "baseline"), capture("rolled_back"),
                retrieve("rollback_query", query),
            ]
            checks = state_assertions("baseline", baseline) + retrieval_assertions("baseline_query", ["drink_old"])
            checks += state_assertions("mutated", ["residence_old", "project_old"]) + [assertion("mutated", "state_hash_differs", **{"from": "baseline"})]
            checks += retrieval_assertions("mutated_query", excludes=["drink_old"])
            checks += state_assertions("rolled_back", baseline, "baseline") + [assertion("rolled_back", "memory_identity_equals", memory_alias="drink_old", **{"from": "baseline"})]
            checks += retrieval_assertions("rollback_query", ["drink_old"])
            slug = "single-delete"
        rows.append(case(number, slug, "single_operation", f"Restore one {slug.removeprefix('single-')} operation for {person}.", initial, operations, checks, ["single-operation", slug.removeprefix("single-"), "retrieval"]))
    return rows


def mixed_cases() -> list[dict[str, Any]]:
    rows = []
    patterns = ["add-correct"] * 3 + ["add-delete"] * 3 + ["correct-delete"] * 3 + ["add-correct-delete"] * 5
    for number, pattern in zip(range(13, 27), patterns, strict=True):
        person = PEOPLE[number - 1]
        initial = base_memories(number, person, 5)
        baseline = [item["alias"] for item in initial]
        current = baseline.copy()
        ops: list[dict[str, Any]] = [capture("baseline"), snapshot("s1", f"sr_formal_{number:03d}_s1")]
        added: list[str] = []
        corrected: list[tuple[str, str]] = []
        deleted: list[str] = []
        if "correct" in pattern:
            new_city = CITIES[(number + 2) % len(CITIES)]
            ops.append({"op": "correct", "target_alias": "residence_old", "result_alias": "residence_new", "new_content": f"{person} lives in {new_city}.", "reason": "Formal mixed correction"})
            current[current.index("residence_old")] = "residence_new"
            corrected.append(("residence_old", "residence_new"))
        if "delete" in pattern:
            ops.append({"op": "delete", "target_alias": "drink_old"})
            current.remove("drink_old")
            deleted.append("drink_old")
        if "add" in pattern:
            pet = memory(number, person, "pet_added", f"{person} has a cat named Luna.", "pet")
            ops.append({"op": "store", "memory": pet})
            current.append("pet_added")
            added.append("pet_added")
        if pattern == "add-correct-delete" and number % 2 == 0:
            sport = memory(number, person, "activity_added", f"{person} goes swimming on Saturday mornings.", "activity", "episodic")
            ops.append({"op": "store", "memory": sport})
            current.append("activity_added")
            added.append("activity_added")
            ops.append({"op": "correct", "target_alias": "project_old", "result_alias": "project_new", "new_content": f"{person} is working on Project {PROJECTS[(number + 4) % len(PROJECTS)]}.", "reason": "Formal mixed correction"})
            current[current.index("project_old")] = "project_new"
            corrected.append(("project_old", "project_new"))
        query = f"Where does {person} live?" if corrected else f"What does {person} prefer to drink in the afternoon?"
        target_old = corrected[0][0] if corrected else deleted[0]
        target_new = corrected[0][1] if corrected else None
        ops += [capture("mutated"), retrieve("mutated_query", query), rollback("s1", "baseline"), capture("rolled_back"), retrieve("rollback_query", query)]
        checks = state_assertions("baseline", baseline)
        checks += state_assertions("mutated", current) + [assertion("mutated", "state_hash_differs", **{"from": "baseline"})]
        checks += retrieval_assertions("mutated_query", [target_new] if target_new else None, [target_old])
        checks += state_assertions("rolled_back", baseline, "baseline")
        checks += [assertion("rolled_back", "absent_aliases", aliases=added + [new for _, new in corrected])]
        checks += retrieval_assertions("rollback_query", [target_old], [target_new] if target_new else None)
        rows.append(case(number, f"mixed-{pattern}", "mixed_operation", f"Restore the baseline after mixed {pattern} operations for {person}.", initial, ops, checks, ["mixed-operation", *pattern.split("-"), "retrieval"]))
    return rows


def multi_snapshot_cases() -> list[dict[str, Any]]:
    rows = []
    modes = ["correct", "correct", "correct", "add", "add", "add", "delete", "delete"]
    for number, mode in zip(range(27, 35), modes, strict=True):
        person = PEOPLE[number - 1]
        initial = base_memories(number, person, 3)
        baseline = [item["alias"] for item in initial]
        ops: list[dict[str, Any]] = [capture("baseline"), snapshot("s1", f"sr_formal_{number:03d}_s1")]
        if mode == "correct":
            query = f"Which project is {person} working on?"
            ops += [
                {"op": "correct", "target_alias": "project_old", "result_alias": "project_mid", "new_content": f"{person} is working on Project Harbor.", "reason": "First formal correction"},
                capture("state_s2"), snapshot("s2", f"sr_formal_{number:03d}_s2"),
                {"op": "correct", "target_alias": "project_mid", "result_alias": "project_new", "new_content": f"{person} is working on Project Nimbus.", "reason": "Second formal correction"},
                capture("latest"), retrieve("latest_query", query), rollback("s2", "state_s2"),
                capture("rolled_s2"), retrieve("rolled_s2_query", query), rollback("s1", "baseline"),
                capture("rolled_s1"), retrieve("rolled_s1_query", query),
            ]
            s2_aliases = ["residence_old", "project_mid", "drink_old"]
            latest = ["residence_old", "project_new", "drink_old"]
            checks = state_assertions("state_s2", s2_aliases) + state_assertions("latest", latest)
            checks += retrieval_assertions("latest_query", ["project_new"], ["project_mid", "project_old"])
            checks += state_assertions("rolled_s2", s2_aliases, "state_s2") + retrieval_assertions("rolled_s2_query", ["project_mid"], ["project_new"])
            checks += state_assertions("rolled_s1", baseline, "baseline") + retrieval_assertions("rolled_s1_query", ["project_old"], ["project_mid", "project_new"])
        elif mode == "add":
            query = f"What pets does {person} have?"
            first = memory(number, person, "pet_mid", f"{person} has a dog named Milo.", "pet")
            second = memory(number, person, "pet_new", f"{person} has a cat named Coco.", "pet")
            ops += [
                {"op": "store", "memory": first}, capture("state_s2"), snapshot("s2", f"sr_formal_{number:03d}_s2"),
                {"op": "store", "memory": second}, capture("latest"), retrieve("latest_query", query),
                rollback("s2", "state_s2"), capture("rolled_s2"), retrieve("rolled_s2_query", query),
                rollback("s1", "baseline"), capture("rolled_s1"), retrieve("rolled_s1_query", query),
            ]
            s2_aliases = baseline + ["pet_mid"]
            latest = baseline + ["pet_mid", "pet_new"]
            checks = state_assertions("state_s2", s2_aliases) + state_assertions("latest", latest)
            checks += retrieval_assertions("latest_query", ["pet_mid", "pet_new"])
            checks += state_assertions("rolled_s2", s2_aliases, "state_s2") + retrieval_assertions("rolled_s2_query", ["pet_mid"], ["pet_new"])
            checks += state_assertions("rolled_s1", baseline, "baseline") + retrieval_assertions("rolled_s1_query", excludes=["pet_mid", "pet_new"])
        else:
            query = f"What does {person} prefer to drink in the afternoon?"
            note = memory(number, person, "note_new", f"{person} schedules focused work before lunch.", "schedule", "profile")
            ops += [
                {"op": "delete", "target_alias": "drink_old"}, capture("state_s2"), snapshot("s2", f"sr_formal_{number:03d}_s2"),
                {"op": "store", "memory": note}, capture("latest"), retrieve("latest_query", query),
                rollback("s2", "state_s2"), capture("rolled_s2"), retrieve("rolled_s2_query", query),
                rollback("s1", "baseline"), capture("rolled_s1"), retrieve("rolled_s1_query", query),
            ]
            s2_aliases = ["residence_old", "project_old"]
            checks = state_assertions("state_s2", s2_aliases) + state_assertions("latest", s2_aliases + ["note_new"])
            checks += retrieval_assertions("latest_query", excludes=["drink_old"])
            checks += state_assertions("rolled_s2", s2_aliases, "state_s2") + retrieval_assertions("rolled_s2_query", excludes=["drink_old"])
            checks += state_assertions("rolled_s1", baseline, "baseline") + retrieval_assertions("rolled_s1_query", ["drink_old"])
        rows.append(case(number, f"multi-snapshot-{mode}", "multi_snapshot", f"Rollback across two snapshots after {mode} operations for {person}.", initial, ops, checks, ["multi-snapshot", "cross-level", mode, "retrieval"]))
    return rows


def post_rollback_cases() -> list[dict[str, Any]]:
    rows = []
    for number in range(35, 41):
        person = PEOPLE[number - 1]
        initial = base_memories(number, person, 3)
        baseline = [item["alias"] for item in initial]
        query = f"Which project is {person} working on?"
        continued = memory(number, person, "activity_after", f"{person} practices yoga on Sunday mornings.", "activity", "episodic")
        ops = [
            capture("baseline"), snapshot("s1", f"sr_formal_{number:03d}_s1"),
            {"op": "correct", "target_alias": "project_old", "result_alias": "project_temp", "new_content": f"{person} is working on Project Quartz.", "reason": "Temporary formal change"},
            capture("mutated"), rollback("s1", "baseline"), capture("rolled_back"),
            retrieve("rollback_query", query), {"op": "store", "memory": continued},
            capture("continued"), retrieve("continued_query", f"What activity does {person} practice on Sunday mornings?"),
        ]
        checks = state_assertions("mutated", ["residence_old", "project_temp", "drink_old"])
        checks += state_assertions("rolled_back", baseline, "baseline") + retrieval_assertions("rollback_query", ["project_old"], ["project_temp"])
        checks += state_assertions("continued", baseline + ["activity_after"]) + [assertion("continued", "state_hash_differs", **{"from": "baseline"})]
        checks += retrieval_assertions("continued_query", ["activity_after"])
        rows.append(case(number, "post-rollback-write", "post_rollback_continue", f"Continue writing safely after rollback for {person}.", initial, ops, checks, ["post-rollback", "continue-write", "retrieval"]))
    return rows


def idempotency_cases() -> list[dict[str, Any]]:
    rows = []
    for number in range(41, 45):
        person = PEOPLE[number - 1]
        initial = base_memories(number, person, 3)
        baseline = [item["alias"] for item in initial]
        query = f"Where does {person} live?"
        ops = [
            capture("baseline"), snapshot("s1", f"sr_formal_{number:03d}_s1"),
            {"op": "correct", "target_alias": "residence_old", "result_alias": "residence_new", "new_content": f"{person} lives in Shenzhen.", "reason": "Formal idempotency mutation"},
            capture("mutated"), rollback("s1", "baseline", operation_alias="rollback_first"),
            capture("rolled_first"), retrieve("rolled_first_query", query),
            rollback("s1", "baseline", operation_alias="rollback_second"), capture("rolled_second"),
            retrieve("rolled_second_query", query),
        ]
        checks = state_assertions("rolled_first", baseline, "baseline") + retrieval_assertions("rolled_first_query", ["residence_old"], ["residence_new"])
        checks += state_assertions("rolled_second", baseline, "rolled_first") + retrieval_assertions("rolled_second_query", ["residence_old"], ["residence_new"])
        checks += [assertion("rollback_first", "operation_status_equals", expected=200), assertion("rollback_second", "operation_status_equals", expected=200)]
        rows.append(case(number, "rollback-idempotency", "idempotency", f"Repeat the same rollback without changing the restored state for {person}.", initial, ops, checks, ["idempotency", "repeat-rollback", "retrieval"]))
    return rows


def edge_cases() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # 45: empty snapshot
    number, person = 45, PEOPLE[44]
    added = memory(number, person, "temporary_added", f"{person} keeps a temporary travel checklist.", "note", "working")
    ops = [capture("baseline"), snapshot("s1", "sr_formal_045_s1"), {"op": "store", "memory": added}, capture("mutated"), retrieve("mutated_query", "Who keeps a temporary travel checklist?"), rollback("s1", "baseline"), capture("rolled_back"), retrieve("rollback_query", "Who keeps a temporary travel checklist?")]
    checks = state_assertions("baseline", []) + state_assertions("mutated", ["temporary_added"]) + retrieval_assertions("mutated_query", ["temporary_added"])
    checks += state_assertions("rolled_back", [], "baseline") + retrieval_assertions("rollback_query", excludes=["temporary_added"])
    rows.append(case(number, "empty-snapshot", "edge_failure", "Restore an empty snapshot after adding one temporary memory.", [], ops, checks, ["edge", "empty-snapshot", "retrieval"]))

    # 46: no-op rollback
    number, person = 46, PEOPLE[45]
    initial = base_memories(number, person, 2)
    baseline = [m["alias"] for m in initial]
    ops = [capture("baseline"), retrieve("baseline_query", f"Where does {person} live?"), snapshot("s1", "sr_formal_046_s1"), rollback("s1", "baseline", operation_alias="noop_rollback"), capture("rolled_back"), retrieve("rollback_query", f"Where does {person} live?")]
    checks = state_assertions("rolled_back", baseline, "baseline") + retrieval_assertions("rollback_query", ["residence_old"]) + [assertion("noop_rollback", "operation_status_equals", expected=200)]
    rows.append(case(number, "noop-rollback", "edge_failure", "Rollback a snapshot without intervening mutations.", initial, ops, checks, ["edge", "no-op", "retrieval"]))

    # 47: name normalization
    number, person = 47, PEOPLE[46]
    initial = base_memories(number, person, 2)
    baseline = [m["alias"] for m in initial]
    ops = [capture("baseline"), snapshot("s1", "formal-name-with-hyphens", operation_alias="create_normalized"), {"op": "delete", "target_alias": "residence_old"}, capture("mutated"), rollback("s1", "baseline"), capture("rolled_back"), retrieve("rollback_query", f"Where does {person} live?")]
    checks = [assertion("create_normalized", "snapshot_canonical_name_equals", expected="formal_name_with_hyphens")] + state_assertions("rolled_back", baseline, "baseline") + retrieval_assertions("rollback_query", ["residence_old"])
    rows.append(case(number, "snapshot-name-normalization", "edge_failure", "Use the canonical snapshot name returned after hyphen normalization.", initial, ops, checks, ["edge", "name-normalization", "retrieval"]))

    # 48: missing snapshot
    number, person = 48, PEOPLE[47]
    initial = base_memories(number, person, 2)
    baseline = [m["alias"] for m in initial]
    ops = [capture("baseline"), {"op": "rollback", "snapshot_name": "snapshot_that_does_not_exist", "expected_status": 404, "operation_alias": "missing_rollback"}, capture("after_error"), retrieve("after_error_query", f"Where does {person} live?")]
    checks = [assertion("missing_rollback", "operation_status_equals", expected=404)] + state_assertions("after_error", baseline, "baseline") + retrieval_assertions("after_error_query", ["residence_old"])
    rows.append(case(number, "missing-snapshot", "edge_failure", "Reject rollback to a nonexistent snapshot without changing state.", initial, ops, checks, ["edge", "missing-snapshot", "expected-error", "retrieval"]))

    # 49: deleted snapshot
    number, person = 49, PEOPLE[48]
    initial = base_memories(number, person, 2)
    baseline = [m["alias"] for m in initial]
    ops = [capture("baseline"), snapshot("s1", "sr_formal_049_s1"), {"op": "delete_snapshot", "snapshot_alias": "s1", "expected_status": 204, "operation_alias": "delete_s1"}, {"op": "rollback", "snapshot_alias": "s1", "expected_status": 404, "operation_alias": "deleted_rollback"}, capture("after_error"), retrieve("after_error_query", f"Where does {person} live?")]
    checks = [assertion("delete_s1", "operation_status_equals", expected=204), assertion("deleted_rollback", "operation_status_equals", expected=404)] + state_assertions("after_error", baseline, "baseline") + retrieval_assertions("after_error_query", ["residence_old"])
    rows.append(case(number, "deleted-snapshot", "edge_failure", "Reject rollback after a snapshot is deleted without changing state.", initial, ops, checks, ["edge", "deleted-snapshot", "expected-error", "retrieval"]))

    # 50: duplicate name preserves original snapshot
    number, person = 50, PEOPLE[49]
    initial = base_memories(number, person, 2)
    baseline = [m["alias"] for m in initial]
    duplicate_name = "sr_formal_050_s1"
    ops = [capture("baseline"), snapshot("s1", duplicate_name), {"op": "correct", "target_alias": "residence_old", "result_alias": "residence_new", "new_content": f"{person} lives in Guangzhou.", "reason": "Mutation before duplicate snapshot request"}, snapshot("duplicate", duplicate_name, operation_alias="duplicate_create"), capture("mutated"), rollback("s1", "baseline"), capture("rolled_back"), retrieve("rollback_query", f"Where does {person} live?")]
    ops[3]["expected_result_contains"] = "already exists"
    checks = [assertion("duplicate_create", "operation_status_equals", expected=201), assertion("duplicate_create", "operation_body_contains", expected="already exists")]
    checks += state_assertions("rolled_back", baseline, "baseline") + retrieval_assertions("rollback_query", ["residence_old"], ["residence_new"])
    rows.append(case(number, "duplicate-snapshot-name", "edge_failure", "Keep the original snapshot when the same name is requested twice.", initial, ops, checks, ["edge", "duplicate-name", "retrieval"]))
    return rows


def build() -> list[dict[str, Any]]:
    rows = single_cases() + mixed_cases() + multi_snapshot_cases() + post_rollback_cases() + idempotency_cases() + edge_cases()
    assert len(rows) == 50
    assert [int(row["case_id"].split("-")[2]) for row in rows] == list(range(1, 51))
    return rows


def main() -> None:
    output = (
        Path(__file__).resolve().parents[2]
        / "datasets/feature/snapshot-rollback/snapshot-rollback-formal-v1.jsonl"
    )
    rows = build()
    dump_jsonl(output, rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    print(json.dumps({"output": str(output), "cases": len(rows), "categories": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
