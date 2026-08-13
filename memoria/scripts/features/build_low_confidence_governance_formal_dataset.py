#!/usr/bin/env python3
"""构造 50 个 Memoria 低置信记忆治理正式用例。"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


SUITE = "low-confidence-governance-formal-v1"
CATEGORY_COUNTS = {
    "clear_delete": 10,
    "clear_retain": 10,
    "tier_comparison": 10,
    "mixed_batch": 10,
    "safety_boundary": 10,
}
HALF_LIFE_DAYS = {"T1": 365.0, "T2": 180.0, "T3": 60.0, "T4": 30.0}
GOVERNANCE_THRESHOLD = 0.2
RETRIEVAL_MIN_CONFIDENCE = 0.05

PEOPLE = [
    "Alice", "Ben", "Chloe", "Daniel", "Emma", "Felix", "Grace", "Henry",
    "Iris", "Jack", "Karen", "Leo", "Mia", "Noah", "Olivia", "Peter",
    "Queenie", "Ryan", "Sophia", "Thomas", "Uma", "Victor", "Wendy",
    "Xavier", "Yvonne", "Zach", "Aaron", "Bella", "Caleb", "Diana",
    "Ethan", "Fiona", "George", "Helen", "Ian", "Julia", "Kevin", "Laura",
    "Martin", "Nina", "Oscar", "Paula", "Quinn", "Rachel", "Simon",
    "Tina", "Ulysses", "Vera", "Will", "Zoe",
]

FIELDS = [
    ("seat", "may prefer a window seat when flying"),
    ("planner", "may switch to a paper planner"),
    ("language", "may be learning Italian"),
    ("class", "may take an evening yoga class on Thursdays"),
    ("route", "may use the riverside route for weekend walks"),
    ("device", "may replace the desk lamp this month"),
    ("drink", "may order green tea in the afternoon"),
    ("reading", "may start reading historical fiction"),
    ("commute", "may take the metro to work on Fridays"),
    ("hobby", "may join a pottery workshop this season"),
    ("office", "works primarily from the Shanghai office"),
    ("passport", "keeps the passport in the home safe"),
    ("meetings", "prefers project meetings in the morning"),
    ("keyboard", "uses a mechanical keyboard for focused work"),
    ("calendar", "reviews the weekly calendar every Monday"),
    ("backup", "stores encrypted backups on an external drive"),
    ("exercise", "goes swimming on Saturday mornings"),
    ("timezone", "uses the Asia/Shanghai time zone"),
    ("contact", "keeps an emergency contact in the phone"),
    ("notebook", "uses green notebooks for design sketches"),
]


def effective_confidence(tier: str, confidence: float, age_days: int) -> float:
    return confidence * math.exp(-age_days / HALF_LIFE_DAYS[tier])


def ids(number: int, slug: str) -> tuple[str, str]:
    return f"lcg-formal-{number:03d}-{slug}", f"feature-lcg-formal-{number:03d}"


def memory(
    case_id: str,
    alias: str,
    content: str,
    field: str,
    subject: str,
    tier: str,
    confidence: float,
    age_days: int,
    expected_action: str,
    *,
    require_pre_retrieval: bool = True,
    memory_type: str = "semantic",
) -> dict[str, Any]:
    effective = effective_confidence(tier, confidence, age_days)
    return {
        "alias": alias,
        "content": content,
        "memory_type": memory_type,
        "session_id": f"{case_id}-{alias}-session",
        "subject_id": subject,
        "trust_tier": tier,
        "initial_confidence": confidence,
        "age_days": age_days,
        "expected_effective_confidence": round(effective, 6),
        "expected_action": expected_action,
        "require_pre_retrieval": require_pre_retrieval,
        "extra_metadata": {
            "benchmark": "memoria-features",
            "suite": SUITE,
            "case_id": case_id,
            "memory_alias": alias,
            "field": field,
        },
    }


def natural_memory(
    case_id: str,
    number: int,
    slot: int,
    tier: str,
    confidence: float,
    age_days: int,
    expected_action: str,
    *,
    require_pre_retrieval: bool = True,
) -> dict[str, Any]:
    person = PEOPLE[number - 1]
    field, phrase = FIELDS[(number * 3 + slot) % len(FIELDS)]
    alias = f"{field}_{slot + 1}"
    return memory(
        case_id,
        alias,
        f"{person} {phrase}.",
        field,
        person.lower(),
        tier,
        confidence,
        age_days,
        expected_action,
        require_pre_retrieval=require_pre_retrieval,
        memory_type="profile" if field in {"seat", "drink", "office", "meetings", "timezone", "notebook"} else "semantic",
    )


def assertion(at: str, kind: str, **values: Any) -> dict[str, Any]:
    return {"at": at, "type": kind, "required": True, **values}


def build_operations(memories: list[dict[str, Any]], repeat: bool) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = [{"op": "capture_state", "state_alias": "before"}]
    for item in memories:
        if item["require_pre_retrieval"]:
            operations.append({
                "op": "retrieve",
                "retrieval_alias": f"before_{item['alias']}",
                "query": item["content"],
                "top_k": 20,
            })
    operations.extend([
        {
            "op": "governance",
            "operation_alias": "governance_1",
            "force": True,
            "expected_status": 200,
        },
        {"op": "capture_state", "state_alias": "after"},
    ])
    for item in memories:
        operations.extend([
            {
                "op": "get_memory",
                "operation_alias": f"get_after_{item['alias']}",
                "target_alias": item["alias"],
                "expected_status": 200,
            },
            {
                "op": "retrieve",
                "retrieval_alias": f"after_{item['alias']}",
                "query": item["content"],
                "top_k": 20,
            },
        ])
    if repeat:
        operations.extend([
            {
                "op": "governance",
                "operation_alias": "governance_2",
                "force": True,
                "expected_status": 200,
            },
            {"op": "capture_state", "state_alias": "after_repeat"},
        ])
    return operations


def build_assertions(memories: list[dict[str, Any]], repeat: bool) -> list[dict[str, Any]]:
    all_aliases = [item["alias"] for item in memories]
    deleted = [item["alias"] for item in memories if item["expected_action"] == "delete"]
    kept = [item["alias"] for item in memories if item["expected_action"] == "retain"]
    checks = [assertion("before", "exact_active_aliases", aliases=all_aliases)]
    for item in memories:
        if item["require_pre_retrieval"]:
            checks.append(assertion(f"before_{item['alias']}", "retrieval_contains", aliases=[item["alias"]]))
    checks.extend([
        assertion("governance_1", "operation_body_value_equals", field="quarantined", expected=len(deleted)),
        assertion("governance_1", "operation_body_value_equals", field="cleaned_stale", expected=0),
        assertion("after", "exact_active_aliases", aliases=kept),
    ])
    for item in memories:
        alias = item["alias"]
        if item["expected_action"] == "delete":
            checks.extend([
                assertion(f"get_after_{alias}", "operation_body_is_null"),
                assertion(f"after_{alias}", "retrieval_excludes", aliases=[alias]),
            ])
        else:
            checks.extend([
                assertion(f"get_after_{alias}", "operation_body_memory_equals", memory_alias=alias, float_tolerance=1e-6),
                assertion(f"after_{alias}", "retrieval_contains", aliases=[alias]),
            ])
    if repeat:
        checks.extend([
            assertion("governance_2", "operation_body_value_equals", field="quarantined", expected=0),
            assertion("after_repeat", "state_hash_equals", **{"from": "after"}),
        ])
    checks.append(assertion("case_end", "canary_state_hash_equals"))
    return checks


def make_case(
    number: int,
    slug: str,
    category: str,
    subtype: str,
    description: str,
    memories: list[dict[str, Any]],
    tags: list[str],
    *,
    repeat: bool = False,
) -> dict[str, Any]:
    case_id, user_id = ids(number, slug)
    if any(item["extra_metadata"]["case_id"] != case_id for item in memories):
        raise ValueError(f"case id mismatch in {case_id}")
    return {
        "schema_version": "1.0",
        "suite": SUITE,
        "case_id": case_id,
        "category": category,
        "subtype": subtype,
        "track": "controlled-direct-store",
        "user_id": user_id,
        "description": description,
        "initial_memories": memories,
        "operations": build_operations(memories, repeat),
        "assertions": build_assertions(memories, repeat),
        "tags": tags,
    }


def build_clear_delete(number: int, spec: tuple[str, float, int, bool]) -> dict[str, Any]:
    tier, confidence, age, pre_retrieval = spec
    case_id, _ = ids(number, "clear-delete")
    item = natural_memory(case_id, number, 0, tier, confidence, age, "delete", require_pre_retrieval=pre_retrieval)
    subtype = "retrievable_before_governance" if pre_retrieval else "below_retrieval_floor"
    return make_case(
        number, "clear-delete", "clear_delete", subtype,
        "验证明显低于治理阈值的单条记忆被准确淘汰。",
        [item], ["delete", tier.lower(), subtype],
    )


def build_clear_retain(number: int, spec: tuple[str, float, int]) -> dict[str, Any]:
    tier, confidence, age = spec
    case_id, _ = ids(number, "clear-retain")
    item = natural_memory(case_id, number, 0, tier, confidence, age, "retain")
    return make_case(
        number, "clear-retain", "clear_retain", "well_above_threshold",
        "验证明显高于治理阈值的单条记忆保持活动且仍可检索。",
        [item], ["retain", tier.lower(), "negative-control"],
    )


def build_tier_comparison(number: int, spec: tuple[str, str, float, int]) -> dict[str, Any]:
    retain_tier, delete_tier, confidence, age = spec
    case_id, _ = ids(number, "tier-comparison")
    memories = [
        natural_memory(case_id, number, 0, retain_tier, confidence, age, "retain"),
        natural_memory(case_id, number, 1, delete_tier, confidence, age, "delete"),
    ]
    return make_case(
        number, "tier-comparison", "tier_comparison", f"{retain_tier.lower()}_vs_{delete_tier.lower()}",
        "在年龄和初始置信度相同时，验证不同信任等级因半衰期不同产生不同治理结果。",
        memories, ["tier-comparison", retain_tier.lower(), delete_tier.lower()],
    )


MIXED_SPECS = [
    ("T4", 0.40, 35, "delete"),
    ("T3", 0.40, 55, "delete"),
    ("T1", 0.90, 30, "retain"),
    ("T2", 0.80, 60, "retain"),
    ("T4", 0.95, 5, "retain"),
]


def build_mixed(number: int, variant: int) -> dict[str, Any]:
    case_id, _ = ids(number, "mixed-batch")
    rotated = MIXED_SPECS[variant:] + MIXED_SPECS[:variant]
    memories = [
        natural_memory(case_id, number, slot, tier, confidence, age, action)
        for slot, (tier, confidence, age, action) in enumerate(rotated)
    ]
    return make_case(
        number, "mixed-batch", "mixed_batch", "two_delete_three_retain",
        "验证同一用户混合批次中只淘汰目标记忆，并保持治理计数、列表和检索一致。",
        memories, ["mixed-batch", "count-accuracy", "selective-delete"],
    )


def build_safety(number: int, variant: int) -> dict[str, Any]:
    case_id, _ = ids(number, "safety-boundary")
    if variant == 0:
        specs = [("T4", 0.40, 45, "delete", True)]
        subtype = "repeat_after_delete"
    elif variant == 1:
        specs = [("T1", 0.95, 30, "retain", True)]
        subtype = "repeat_without_delete"
    elif variant == 2:
        specs = [("T4", 0.30, 55, "delete", False), ("T1", 0.90, 20, "retain", True)]
        subtype = "deep_expiry_with_retain"
    elif variant == 3:
        specs = [("T4", 0.55, 32, "delete", True), ("T4", 0.55, 28, "retain", True)]
        subtype = "near_threshold_pair"
    elif variant == 4:
        specs = [("T3", 0.45, 50, "delete", True), ("T3", 0.45, 45, "retain", True)]
        subtype = "same_tier_age_boundary"
    elif variant == 5:
        specs = [("T2", 0.30, 80, "delete", True), ("T2", 0.30, 60, "retain", True)]
        subtype = "t2_age_boundary"
    elif variant == 6:
        specs = [("T1", 0.25, 90, "delete", True), ("T1", 0.25, 70, "retain", True)]
        subtype = "t1_age_boundary"
    elif variant == 7:
        specs = [("T4", 0.25, 20, "delete", True), ("T4", 0.35, 15, "retain", True)]
        subtype = "confidence_boundary"
    elif variant == 8:
        specs = [("T4", 0.40, 40, "delete", True), ("T3", 0.65, 40, "retain", True), ("T1", 0.95, 40, "retain", True)]
        subtype = "multi_tier_idempotency"
    else:
        specs = [("T4", 0.30, 35, "delete", True), ("T3", 0.35, 50, "delete", True), ("T2", 0.85, 90, "retain", True)]
        subtype = "multiple_delete_idempotency"

    memories = [
        natural_memory(
            case_id, number, slot, tier, confidence, age, action,
            require_pre_retrieval=pre_retrieval,
        )
        for slot, (tier, confidence, age, action, pre_retrieval) in enumerate(specs)
    ]
    return make_case(
        number, "safety-boundary", "safety_boundary", subtype,
        "验证阈值邻近样本、重复治理、状态幂等和运行时金丝雀用户隔离。",
        memories, ["safety", "boundary", "idempotency", "canary-isolation"], repeat=True,
    )


def validate(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 50:
        raise ValueError(f"expected 50 cases, got {len(cases)}")
    if Counter(case["category"] for case in cases) != Counter(CATEGORY_COUNTS):
        raise ValueError("category distribution mismatch")
    if len({case["case_id"] for case in cases}) != 50:
        raise ValueError("duplicate case_id")
    if len({case["user_id"] for case in cases}) != 50:
        raise ValueError("duplicate user_id")

    for case in cases:
        aliases = [item["alias"] for item in case["initial_memories"]]
        if len(aliases) != len(set(aliases)):
            raise ValueError(f"duplicate alias in {case['case_id']}")
        operation_refs = {"case_end"}
        state_refs = set()
        for operation in case["operations"]:
            for key in ("operation_alias", "state_alias", "retrieval_alias"):
                if operation.get(key):
                    operation_refs.add(operation[key])
            if operation.get("state_alias"):
                state_refs.add(operation["state_alias"])
        for check in case["assertions"]:
            if check["at"] not in operation_refs:
                raise ValueError(
                    f"unknown assertion reference {case['case_id']}:{check['at']}"
                )
            if check.get("from") and check["from"] not in state_refs:
                raise ValueError(
                    f"unknown state reference {case['case_id']}:{check['from']}"
                )
        for item in case["initial_memories"]:
            effective = effective_confidence(
                item["trust_tier"], item["initial_confidence"], item["age_days"]
            )
            expected_action = "delete" if effective < GOVERNANCE_THRESHOLD else "retain"
            if item["expected_action"] != expected_action:
                raise ValueError(
                    f"classification mismatch {case['case_id']}:{item['alias']} "
                    f"effective={effective:.6f}"
                )
            if item["require_pre_retrieval"] and effective < RETRIEVAL_MIN_CONFIDENCE:
                raise ValueError(
                    f"pre-retrieval impossible {case['case_id']}:{item['alias']} "
                    f"effective={effective:.6f}"
                )
            if abs(item["expected_effective_confidence"] - effective) > 0.000001:
                raise ValueError(f"effective confidence drift in {case['case_id']}")


def build() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    quarantine_specs = [
        ("T4", 0.40, 30, True), ("T4", 0.60, 40, True),
        ("T3", 0.40, 60, True), ("T3", 0.50, 80, True),
        ("T2", 0.35, 120, True), ("T2", 0.50, 180, True),
        ("T1", 0.30, 180, True), ("T1", 0.40, 270, True),
        ("T4", 0.30, 60, False), ("T3", 0.30, 120, False),
    ]
    retain_specs = [
        ("T1", 0.95, 30), ("T1", 0.80, 180),
        ("T2", 0.85, 60), ("T2", 0.70, 120),
        ("T3", 0.65, 30), ("T3", 0.80, 60),
        ("T4", 0.40, 10), ("T4", 0.75, 30),
        ("T2", 0.95, 180), ("T1", 0.50, 300),
    ]
    comparison_specs = [
        ("T1", "T4", 0.50, 30), ("T2", "T4", 0.45, 30),
        ("T1", "T3", 0.40, 50), ("T2", "T3", 0.50, 60),
        ("T1", "T4", 0.55, 60), ("T2", "T4", 0.60, 45),
        ("T1", "T3", 0.35, 45), ("T2", "T3", 0.40, 50),
        ("T1", "T4", 0.45, 35), ("T2", "T4", 0.50, 40),
    ]

    number = 1
    for spec in quarantine_specs:
        cases.append(build_clear_delete(number, spec))
        number += 1
    for spec in retain_specs:
        cases.append(build_clear_retain(number, spec))
        number += 1
    for spec in comparison_specs:
        cases.append(build_tier_comparison(number, spec))
        number += 1
    for variant in range(10):
        cases.append(build_mixed(number, variant % len(MIXED_SPECS)))
        number += 1
    for variant in range(10):
        cases.append(build_safety(number, variant))
        number += 1

    validate(cases)
    return cases


def main() -> None:
    script = Path(__file__).resolve()
    output = script.parents[2] / "datasets/feature/low-confidence-governance/low-confidence-governance-formal-v1.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    cases = build()
    output.write_text(
        "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )
    print(f"wrote {len(cases)} cases to {output}")
    print("categories", dict(Counter(case["category"] for case in cases)))
    print("memories", sum(len(case["initial_memories"]) for case in cases))
    print("operations", sum(len(case["operations"]) for case in cases))
    print("assertions", sum(len(case["assertions"]) for case in cases))


if __name__ == "__main__":
    main()
