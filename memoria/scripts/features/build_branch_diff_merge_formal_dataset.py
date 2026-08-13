#!/usr/bin/env python3
"""Build the 50-case Memoria Branch/Diff/Merge Formal v1 dataset."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


SUITE = "branch-diff-merge-formal-v1"
CATEGORY_COUNTS = {
    "branch_isolation": 12,
    "diff_correctness": 14,
    "merge_correctness": 12,
    "conflict_detection": 12,
}

PEOPLE = [
    "Alice", "Ben", "Chloe", "Daniel", "Emma", "Felix", "Grace", "Henry",
    "Iris", "Jack", "Karen", "Leo", "Mia", "Noah", "Olivia", "Peter",
    "Queenie", "Ryan", "Sophia", "Thomas", "Uma", "Victor", "Wendy",
    "Xavier", "Yvonne", "Zach", "Aaron", "Bella", "Caleb", "Diana",
    "Ethan", "Fiona", "George", "Helen", "Ian", "Julia", "Kevin", "Laura",
    "Martin", "Nina", "Oscar", "Paula", "Quinn", "Rachel", "Simon",
    "Tina", "Ulysses", "Vera", "Will", "Zoe",
]
CITIES = [
    "Beijing", "Suzhou", "Hangzhou", "Chengdu", "Shenzhen", "Nanjing",
    "Wuhan", "Xiamen", "Qingdao", "Kunming", "Tianjin", "Ningbo",
]
NEW_CITIES = [
    "Shanghai", "Guangzhou", "Dalian", "Changsha", "Fuzhou", "Xi'an",
    "Jinan", "Harbin", "Wuxi", "Zhuhai", "Hefei", "Haikou",
]
PROJECTS = [
    "Cedar", "Harbor", "Atlas", "Willow", "Beacon", "Quartz", "Nimbus",
    "Falcon", "Lotus", "Summit", "Aurora", "Meadow",
]
BRANCH_PROJECTS = [
    "Maple", "Orion", "River", "Pine", "Coral", "Nova", "Juniper",
    "Sparrow", "Opal", "Canyon", "Comet", "Garden",
]
MAIN_PROJECTS = [
    "Orchid", "Delta", "Forest", "Elm", "Tide", "Lumen", "Aspen",
    "Robin", "Pearl", "Ridge", "Meteor", "Grove",
]
DRINKS = [
    "Americano coffee", "green tea", "flat white coffee", "oolong tea",
    "sparkling water", "black tea", "lemon water", "cappuccino coffee",
]
PETS = [
    ("cat", "Luna"), ("dog", "Pepper"), ("rabbit", "Mochi"),
    ("parrot", "Kiwi"), ("cat", "Milo"), ("dog", "Coco"),
]
LANGUAGES = ["Spanish", "Japanese", "French", "German", "Korean", "Italian"]
ACTIVITIES = [
    "goes swimming on Saturday mornings",
    "attends a pottery class on Wednesday evenings",
    "plays badminton on Sunday afternoons",
    "practices yoga before work on Tuesdays",
    "visits the library on Friday evenings",
    "goes hiking on the first Sunday of each month",
]


def profile(number: int) -> dict[str, str]:
    index = number - 1
    return {
        "name": PEOPLE[index],
        "subject": PEOPLE[index].lower(),
        "city": CITIES[index % len(CITIES)],
        "new_city": NEW_CITIES[index % len(NEW_CITIES)],
        "project": PROJECTS[index % len(PROJECTS)],
        "branch_project": BRANCH_PROJECTS[index % len(BRANCH_PROJECTS)],
        "main_project": MAIN_PROJECTS[index % len(MAIN_PROJECTS)],
        "drink": DRINKS[index % len(DRINKS)],
    }


def ids(number: int, slug: str) -> tuple[str, str]:
    return f"bdm-formal-{number:03d}-{slug}", f"feature-bdm-formal-{number:03d}"


def memory(
    case_id: str,
    alias: str,
    content: str,
    field: str,
    subject: str,
    memory_type: str = "semantic",
    session: str = "session-01",
) -> dict[str, Any]:
    return {
        "alias": alias,
        "content": content,
        "memory_type": memory_type,
        "session_id": f"{case_id}-{session}",
        "subject_id": subject,
        "trust_tier": "T2",
        "initial_confidence": 0.95,
        "observed_at": "2025-06-01T08:00:00Z",
        "extra_metadata": {
            "benchmark": "memoria-features",
            "suite": SUITE,
            "case_id": case_id,
            "memory_alias": alias,
            "field": field,
        },
    }


def baseline(case_id: str, p: dict[str, str]) -> list[dict[str, Any]]:
    name = p["name"]
    subject = p["subject"]
    return [
        memory(case_id, "residence_old", f"{name} lives in {p['city']}.", "residence", subject),
        memory(
            case_id,
            "project_old",
            f"{name} is working on Project {p['project']}.",
            "project",
            subject,
            "working",
        ),
        memory(
            case_id,
            "drink_old",
            f"{name} prefers {p['drink']} in the afternoon.",
            "beverage",
            subject,
            "profile",
        ),
        memory(
            case_id,
            "timezone_main",
            f"{name} uses the Asia/Shanghai time zone.",
            "timezone",
            subject,
            "profile",
        ),
    ]


def added_memories(case_id: str, p: dict[str, str], count: int, prefix: str = "branch") -> list[dict[str, Any]]:
    name = p["name"]
    subject = p["subject"]
    pet, pet_name = PETS[(int(case_id.split("-")[2]) - 1) % len(PETS)]
    specs = [
        (f"pet_{prefix}", f"{name} has a {pet} named {pet_name}.", "pet", "semantic"),
        (f"language_{prefix}", f"{name} is learning {LANGUAGES[(int(case_id.split('-')[2]) - 1) % len(LANGUAGES)]}.", "language", "semantic"),
        (f"activity_{prefix}", f"{name} {ACTIVITIES[(int(case_id.split('-')[2]) - 1) % len(ACTIVITIES)]}.", "activity", "episodic"),
        (f"device_{prefix}", f"{name} uses a mechanical keyboard for focused work.", "device", "profile"),
        (f"goal_{prefix}", f"{name} plans to finish a professional certificate this year.", "goal", "working"),
    ]
    return [
        memory(case_id, alias, content, field, subject, memory_type, "session-02")
        for alias, content, field, memory_type in specs[:count]
    ]


def main_advance_memory(case_id: str, p: dict[str, str]) -> dict[str, Any]:
    return memory(
        case_id,
        "schedule_main",
        f"{p['name']} reviews weekly plans on Monday evenings.",
        "schedule",
        p["subject"],
        "episodic",
        "session-03",
    )


def post_merge_memory(case_id: str, p: dict[str, str]) -> dict[str, Any]:
    return memory(
        case_id,
        "book_club_main",
        f"{p['name']} attends a book club on Thursday evenings.",
        "activity",
        p["subject"],
        "episodic",
        "session-04",
    )


def assertion(at: str, kind: str, **values: Any) -> dict[str, Any]:
    return {"at": at, "type": kind, "required": True, **values}


def capture(alias: str) -> dict[str, Any]:
    return {"op": "capture_state", "state_alias": alias}


def retrieve(alias: str, query: str) -> dict[str, Any]:
    return {"op": "retrieve", "retrieval_alias": alias, "query": query, "top_k": 20}


def create_branch(alias: str, number: int, suffix: str) -> dict[str, Any]:
    return {
        "op": "create_branch",
        "branch_alias": alias,
        "branch_name": f"bdm_formal_{number:03d}_{suffix}",
        "expected_status": 201,
    }


def checkout(alias: str, operation_alias: str) -> dict[str, Any]:
    return {
        "op": "checkout_branch",
        "branch_alias": alias,
        "operation_alias": operation_alias,
        "expected_status": 200,
    }


def diff(branch_alias: str, diff_alias: str) -> dict[str, Any]:
    return {
        "op": "diff_items",
        "branch_alias": branch_alias,
        "diff_alias": diff_alias,
        "limit": 100,
        "expected_status": 200,
    }


def correct(target: str, result: str, content: str, reason: str) -> dict[str, Any]:
    return {
        "op": "correct",
        "target_alias": target,
        "result_alias": result,
        "new_content": content,
        "reason": reason,
    }


def append_merge(branch_alias: str, operation_alias: str) -> dict[str, Any]:
    return {
        "op": "merge_branch",
        "branch_alias": branch_alias,
        "strategy": "append",
        "operation_alias": operation_alias,
        "expected_status": 200,
    }


def diff_assertions(
    at: str,
    *,
    added: list[str] | None = None,
    updated: list[str] | None = None,
    removed: list[str] | None = None,
    conflicts: list[str] | None = None,
    behind_main: list[str] | None = None,
) -> list[dict[str, Any]]:
    expected = {
        "added": added or [],
        "updated": updated or [],
        "removed": removed or [],
        "conflicts": conflicts or [],
        "behind_main": behind_main or [],
    }
    return [assertion(at, "diff_aliases_equal", field=field, aliases=aliases) for field, aliases in expected.items()]


def case(
    number: int,
    slug: str,
    category: str,
    subtype: str,
    description: str,
    initial: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    tags: list[str],
) -> dict[str, Any]:
    case_id, user_id = ids(number, slug)
    assert all(row["extra_metadata"]["case_id"] == case_id for row in initial)
    return {
        "schema_version": "1.0",
        "suite": SUITE,
        "case_id": case_id,
        "category": category,
        "subtype": subtype,
        "track": "controlled-direct-store",
        "user_id": user_id,
        "description": description,
        "initial_memories": initial,
        "operations": operations,
        "assertions": assertions,
        "tags": tags,
    }


def build_branch_isolation(number: int, subtype: str, variant: int) -> dict[str, Any]:
    slug = f"{subtype.replace('_', '-')}-{variant}"
    case_id, _ = ids(number, slug)
    p = profile(number)
    initial = baseline(case_id, p)
    base_aliases = ["residence_old", "project_old", "drink_old", "timezone_main"]
    name = p["name"]

    if subtype == "branch_add":
        count = variant
        additions = added_memories(case_id, p, count)
        added_aliases = [row["alias"] for row in additions]
        operations = [capture("main_baseline"), create_branch("experiment", number, "add"), checkout("experiment", "checkout_branch")]
        operations += [{"op": "store", "memory": row} for row in additions]
        operations += [capture("branch_state"), retrieve("branch_added", f"What pet does {name} have?"), diff("experiment", "branch_diff"), checkout("main", "checkout_main"), capture("main_final"), retrieve("main_added", f"What pet does {name} have?")]
        assertions = [
            assertion("branch_state", "exact_active_aliases", aliases=base_aliases + added_aliases),
            assertion("branch_state", "state_hash_differs", **{"from": "main_baseline"}),
            assertion("branch_added", "retrieval_contains", aliases=[added_aliases[0]]),
            assertion("main_final", "state_hash_equals", **{"from": "main_baseline"}),
            assertion("main_added", "retrieval_excludes", aliases=added_aliases),
        ] + diff_assertions("branch_diff", added=added_aliases)
        description = f"Keep {count} branch-only addition(s) isolated from main."
        tags = ["branch-isolation", "add", "retrieval"]
    elif subtype == "branch_correct":
        targets = [
            ("residence_old", "residence_branch", f"{name} lives in {p['new_city']}.", f"Where does {name} live?"),
            ("project_old", "project_branch", f"{name} is working on Project {p['branch_project']}.", f"Which project is {name} working on?"),
            ("drink_old", "drink_branch", f"{name} prefers jasmine tea in the afternoon.", f"What does {name} prefer to drink?")
        ]
        target, result, content, query = targets[variant - 1]
        branch_aliases = [result if alias == target else alias for alias in base_aliases]
        operations = [capture("main_baseline"), create_branch("experiment", number, "correct"), checkout("experiment", "checkout_branch"), correct(target, result, content, "Branch-local correction"), capture("branch_state"), retrieve("branch_value", query), diff("experiment", "branch_diff"), checkout("main", "checkout_main"), capture("main_final"), retrieve("main_value", query)]
        assertions = [
            assertion("branch_state", "exact_active_aliases", aliases=branch_aliases),
            assertion("branch_value", "retrieval_contains", aliases=[result]),
            assertion("branch_value", "retrieval_excludes", aliases=[target]),
            assertion("main_final", "state_hash_equals", **{"from": "main_baseline"}),
            assertion("main_value", "retrieval_contains", aliases=[target]),
            assertion("main_value", "retrieval_excludes", aliases=[result]),
        ] + diff_assertions("branch_diff", updated=[result])
        description = f"Keep a branch-only correction of {target} isolated from main."
        tags = ["branch-isolation", "correct", "retrieval"]
    elif subtype == "branch_delete":
        target, query = [("project_old", f"Which project is {name} working on?"), ("drink_old", f"What does {name} prefer to drink?")][variant - 1]
        branch_aliases = [alias for alias in base_aliases if alias != target]
        operations = [capture("main_baseline"), create_branch("experiment", number, "delete"), checkout("experiment", "checkout_branch"), {"op": "delete", "target_alias": target}, capture("branch_state"), retrieve("branch_value", query), diff("experiment", "branch_diff"), checkout("main", "checkout_main"), capture("main_final"), retrieve("main_value", query)]
        assertions = [
            assertion("branch_state", "exact_active_aliases", aliases=branch_aliases),
            assertion("branch_value", "retrieval_excludes", aliases=[target]),
            assertion("main_final", "state_hash_equals", **{"from": "main_baseline"}),
            assertion("main_value", "retrieval_contains", aliases=[target]),
        ] + diff_assertions("branch_diff", removed=[target])
        description = f"Keep a branch-only deletion of {target} isolated from main."
        tags = ["branch-isolation", "delete", "retrieval"]
    elif subtype == "sibling_branches":
        operations = [
            capture("main_baseline"), create_branch("branch_a", number, "a"), checkout("branch_a", "checkout_a_first"),
            correct("residence_old", "residence_a", f"{name} lives in {p['new_city']}.", "Branch A relocation"), capture("branch_a_state"),
            checkout("main", "checkout_main_between"), create_branch("branch_b", number, "b"), checkout("branch_b", "checkout_b"),
            correct("project_old", "project_b", f"{name} is working on Project {p['branch_project']}.", "Branch B project proposal"), capture("branch_b_state"),
            checkout("branch_a", "checkout_a_again"), capture("branch_a_again"), diff("branch_a", "diff_a"),
            checkout("branch_b", "checkout_b_again"), diff("branch_b", "diff_b"), checkout("main", "checkout_main_final"), capture("main_final"),
        ]
        assertions = [
            assertion("branch_a_state", "exact_active_aliases", aliases=["residence_a", "project_old", "drink_old", "timezone_main"]),
            assertion("branch_b_state", "exact_active_aliases", aliases=["residence_old", "project_b", "drink_old", "timezone_main"]),
            assertion("branch_a_again", "state_hash_equals", **{"from": "branch_a_state"}),
            assertion("main_final", "state_hash_equals", **{"from": "main_baseline"}),
        ] + diff_assertions("diff_a", updated=["residence_a"]) + diff_assertions("diff_b", updated=["project_b"])
        description = "Keep two sibling branches independent from each other and from main."
        tags = ["branch-isolation", "siblings", "checkout"]
    elif subtype == "repeated_checkout":
        addition = added_memories(case_id, p, 1)[0]
        operations = [capture("main_baseline"), create_branch("experiment", number, "repeat"), checkout("experiment", "checkout_branch_first"), {"op": "store", "memory": addition}, capture("branch_first"), retrieve("branch_retrieval_first", f"What pet does {name} have?"), checkout("main", "checkout_main_first"), capture("main_first"), checkout("experiment", "checkout_branch_second"), capture("branch_second"), retrieve("branch_retrieval_second", f"What pet does {name} have?"), checkout("main", "checkout_main_second"), capture("main_second")]
        assertions = [
            assertion("branch_second", "state_hash_equals", **{"from": "branch_first"}),
            assertion("main_first", "state_hash_equals", **{"from": "main_baseline"}),
            assertion("main_second", "state_hash_equals", **{"from": "main_baseline"}),
            assertion("branch_retrieval_first", "retrieval_contains", aliases=[addition["alias"]]),
            assertion("branch_retrieval_second", "retrieval_contains", aliases=[addition["alias"]]),
        ]
        description = "Preserve branch and main state across repeated checkouts."
        tags = ["branch-isolation", "checkout", "retrieval"]
    else:
        main_add = main_advance_memory(case_id, p)
        operations = [capture("main_baseline"), create_branch("experiment", number, "main_advance"), checkout("main", "checkout_main"), {"op": "store", "memory": main_add}, capture("main_advanced"), checkout("experiment", "checkout_branch"), capture("branch_unchanged"), diff("experiment", "branch_diff"), checkout("main", "checkout_main_final"), capture("main_final")]
        assertions = [
            assertion("branch_unchanged", "state_hash_equals", **{"from": "main_baseline"}),
            assertion("main_final", "state_hash_equals", **{"from": "main_advanced"}),
        ] + diff_assertions("branch_diff", behind_main=[main_add["alias"]])
        description = "Keep a pre-existing branch stable when main advances independently."
        tags = ["branch-isolation", "behind-main", "main-advance"]

    return case(number, slug, "branch_isolation", subtype, description, initial, operations, assertions, tags)


def build_diff_case(number: int, subtype: str, variant: int) -> dict[str, Any]:
    slug = f"{subtype.replace('_', '-')}-{variant}"
    case_id, _ = ids(number, slug)
    p = profile(number)
    initial = baseline(case_id, p)
    base_aliases = ["residence_old", "project_old", "drink_old", "timezone_main"]
    name = p["name"]
    operations = [capture("main_baseline"), create_branch("experiment", number, "diff"), checkout("experiment", "checkout_branch")]
    added: list[str] = []
    updated: list[str] = []
    removed: list[str] = []
    behind: list[str] = []
    active = list(base_aliases)

    needs_add = subtype in {"single_add", "repeat_diff", "behind_main"} or (
        subtype == "mixed" and variant in {1, 2, 4, 5}
    )
    if needs_add:
        add_count = 1
        if subtype == "mixed" and variant == 5:
            add_count = 2
        additions = added_memories(case_id, p, add_count)
        for row in additions:
            operations.append({"op": "store", "memory": row})
            added.append(row["alias"])
            active.append(row["alias"])

    if subtype == "single_update" or (subtype == "mixed" and variant in {1, 3, 4, 5}) or subtype == "repeat_diff":
        operations.append(correct("residence_old", "residence_new", f"{name} lives in {p['new_city']}.", "Diff update"))
        active[active.index("residence_old")] = "residence_new"
        updated.append("residence_new")
        if subtype == "mixed" and variant == 5:
            operations.append(correct("project_old", "project_new", f"{name} is working on Project {p['branch_project']}.", "Second diff update"))
            active[active.index("project_old")] = "project_new"
            updated.append("project_new")

    if subtype == "single_remove" or (subtype == "mixed" and variant in {2, 3, 4, 5}) or subtype == "repeat_diff":
        target = "drink_old"
        operations.append({"op": "delete", "target_alias": target})
        active.remove(target)
        removed.append(target)
        if subtype == "mixed" and variant == 5:
            operations.append({"op": "delete", "target_alias": "timezone_main"})
            active.remove("timezone_main")
            removed.append("timezone_main")

    if subtype == "behind_main":
        operations += [checkout("main", "checkout_main_advance")]
        main_add = main_advance_memory(case_id, p)
        operations.append({"op": "store", "memory": main_add})
        behind.append(main_add["alias"])
        operations.append(checkout("experiment", "checkout_branch_again"))

    operations += [capture("branch_state"), diff("experiment", "diff_first")]
    if subtype == "repeat_diff":
        operations.append(diff("experiment", "diff_second"))
    operations += [checkout("main", "checkout_main_final"), capture("main_final")]

    assertions = [assertion("branch_state", "exact_active_aliases", aliases=active)]
    assertions += diff_assertions("diff_first", added=added, updated=updated, removed=removed, behind_main=behind)
    if subtype == "repeat_diff":
        assertions += diff_assertions("diff_second", added=added, updated=updated, removed=removed, behind_main=behind)
    if subtype == "behind_main":
        assertions.append(assertion("main_final", "exact_active_aliases", aliases=base_aliases + behind))
    else:
        assertions.append(assertion("main_final", "state_hash_equals", **{"from": "main_baseline"}))
    description = f"Classify the {subtype.replace('_', ' ')} change set exactly."
    tags = ["diff", subtype.replace("_", "-")]
    return case(number, slug, "diff_correctness", subtype, description, initial, operations, assertions, tags)


def build_merge_case(number: int, subtype: str, variant: int) -> dict[str, Any]:
    slug = f"{subtype.replace('_', '-')}-{variant}"
    case_id, _ = ids(number, slug)
    p = profile(number)
    initial = baseline(case_id, p)[:2]
    base_aliases = ["residence_old", "project_old"]
    add_count = {"append_count": [1, 2, 3, 5][variant - 1], "mixed_types": 4}.get(subtype, 2)
    additions = added_memories(case_id, p, add_count)
    added_aliases = [row["alias"] for row in additions]
    operations = [capture("main_baseline"), create_branch("experiment", number, "merge"), checkout("experiment", "checkout_branch")]
    operations += [{"op": "store", "memory": row} for row in additions]
    operations += [capture("branch_ready"), diff("experiment", "premerge_diff"), checkout("main", "checkout_main")]
    main_added: list[str] = []
    if subtype == "main_advance_merge":
        row = main_advance_memory(case_id, p)
        operations += [{"op": "store", "memory": row}, capture("main_before_merge")]
        main_added.append(row["alias"])
    operations += [append_merge("experiment", "merge_first"), capture("main_after_merge"), retrieve("main_added_retrieval", f"What pet does {p['name']} have?"), diff("experiment", "postmerge_diff")]
    if subtype == "repeat_merge":
        operations += [append_merge("experiment", "merge_second"), capture("main_after_second_merge")]
    post_added: list[str] = []
    if subtype == "post_merge_write":
        row = post_merge_memory(case_id, p)
        operations += [{"op": "store", "memory": row}, capture("main_after_continue"), retrieve("postmerge_retrieval", f"What does {p['name']} do on Thursday evenings?")]
        post_added.append(row["alias"])

    expected_main = base_aliases + main_added + added_aliases
    assertions = [
        *diff_assertions("premerge_diff", added=added_aliases),
        assertion("merge_first", "operation_status_equals", expected=200),
        assertion("merge_first", "operation_body_contains", expected=f"{add_count} new"),
        assertion("main_after_merge", "exact_active_aliases", aliases=expected_main),
        assertion("main_added_retrieval", "retrieval_contains", aliases=[added_aliases[0]]),
        *diff_assertions("postmerge_diff", behind_main=main_added),
    ]
    if subtype == "repeat_merge":
        assertions += [
            assertion("merge_second", "operation_body_contains", expected="0 new"),
            assertion("main_after_second_merge", "state_hash_equals", **{"from": "main_after_merge"}),
        ]
    if subtype == "post_merge_write":
        assertions += [
            assertion("main_after_continue", "exact_active_aliases", aliases=expected_main + post_added),
            assertion("postmerge_retrieval", "retrieval_contains", aliases=post_added),
        ]
    description = f"Validate append-only merge behavior for {subtype.replace('_', ' ')}."
    tags = ["merge", "append", subtype.replace("_", "-"), "retrieval"]
    return case(number, slug, "merge_correctness", subtype, description, initial, operations, assertions, tags)


def build_conflict_case(number: int, subtype: str, variant: int) -> dict[str, Any]:
    slug = f"{subtype.replace('_', '-')}-{variant}"
    case_id, _ = ids(number, slug)
    p = profile(number)
    name = p["name"]
    initial = [
        memory(case_id, "project_old", f"{name} is working on Project {p['project']}.", "project", p["subject"], "working"),
        memory(case_id, "timezone_main", f"{name} uses the Asia/Shanghai time zone.", "timezone", p["subject"], "profile"),
    ]
    operations = [capture("main_baseline"), create_branch("experiment", number, "conflict"), checkout("experiment", "checkout_branch")]
    branch_content: str | None = None
    main_content: str | None = None
    branch_aliases = ["timezone_main"]
    main_aliases = ["timezone_main"]

    if subtype in {"update_update", "update_delete", "same_update"}:
        branch_content = f"{name} is working on Project {p['branch_project']}."
        if subtype == "same_update":
            main_content = branch_content
        elif subtype == "update_update":
            main_content = f"{name} is working on Project {p['main_project']}."
        operations.append(correct("project_old", "project_branch", branch_content, "Branch project proposal"))
        branch_aliases.insert(0, "project_branch")
    else:
        operations.append({"op": "delete", "target_alias": "project_old"})

    operations += [capture("branch_state"), checkout("main", "checkout_main")]
    if subtype in {"update_update", "delete_update", "same_update"}:
        if main_content is None:
            main_content = f"{name} is working on Project {p['main_project']}."
        operations.append(correct("project_old", "project_main", main_content, "Main-line project decision"))
        main_aliases.insert(0, "project_main")
    else:
        operations.append({"op": "delete", "target_alias": "project_old"})

    operations += [capture("main_before_diff"), retrieve("main_project_before_diff", f"Which project is {name} working on?"), diff("experiment", "conflict_diff"), capture("main_after_diff"), retrieve("main_project_after_diff", f"Which project is {name} working on?")]

    positive = subtype in {"update_update", "update_delete", "delete_update"}
    expected_conflicts = ["project_old"] if positive else []
    assertions = [
        assertion("branch_state", "exact_active_aliases", aliases=branch_aliases),
        assertion("main_before_diff", "exact_active_aliases", aliases=main_aliases),
        assertion("conflict_diff", "diff_aliases_equal", field="conflicts", aliases=expected_conflicts),
        assertion("main_after_diff", "state_hash_equals", **{"from": "main_before_diff"}),
    ]
    if positive:
        assertions.append(assertion("conflict_diff", "diff_conflict_contents_equal", memory_alias="project_old", branch_content=branch_content, main_content=main_content))
    if "project_main" in main_aliases:
        assertions += [
            assertion("main_project_before_diff", "retrieval_contains", aliases=["project_main"]),
            assertion("main_project_after_diff", "retrieval_contains", aliases=["project_main"]),
        ]
        if "project_branch" in branch_aliases:
            assertions.append(
                assertion(
                    "main_project_after_diff",
                    "retrieval_excludes",
                    aliases=["project_branch"],
                )
            )
    else:
        excluded = ["project_old"]
        if "project_branch" in branch_aliases:
            excluded.append("project_branch")
        assertions += [
            assertion("main_project_before_diff", "retrieval_excludes", aliases=excluded),
            assertion("main_project_after_diff", "retrieval_excludes", aliases=excluded),
        ]
    description = (
        f"Detect {subtype.replace('_', '/')} as a conflict without mutating main."
        if positive
        else f"Use equivalent {subtype.replace('_', ' ')} as a conflict false-positive control."
    )
    tags = ["conflict-detection", subtype.replace("_", "-"), "main-preservation", "negative-control" if not positive else "positive"]
    return case(number, slug, "conflict_detection", subtype, description, initial, operations, assertions, tags)


def validate(cases: list[dict[str, Any]]) -> None:
    assert len(cases) == 50
    assert Counter(row["category"] for row in cases) == CATEGORY_COUNTS
    assert len({row["case_id"] for row in cases}) == 50
    assert len({row["user_id"] for row in cases}) == 50
    for row in cases:
        all_memories = list(row["initial_memories"])
        all_memories.extend(
            operation["memory"]
            for operation in row["operations"]
            if operation["op"] == "store"
        )
        aliases = {memory_row["alias"] for memory_row in row["initial_memories"]}
        assert aliases
        for memory_row in all_memories:
            assert "[" not in memory_row["content"] and "]" not in memory_row["content"]
            assert memory_row["extra_metadata"]["suite"] == SUITE
            assert memory_row["extra_metadata"]["case_id"] == row["case_id"]
        for operation in row["operations"]:
            if operation["op"] == "store":
                aliases.add(operation["memory"]["alias"])
            elif operation["op"] == "correct":
                assert operation["target_alias"] in aliases
                aliases.add(operation["result_alias"])
            elif operation["op"] == "delete":
                assert operation["target_alias"] in aliases
        for check in row["assertions"]:
            for alias in check.get("aliases", []):
                assert alias in aliases, (row["case_id"], alias)
            if "memory_alias" in check:
                assert check["memory_alias"] in aliases


def build() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    number = 1

    for subtype, count in [
        ("branch_add", 3),
        ("branch_correct", 3),
        ("branch_delete", 2),
        ("sibling_branches", 2),
        ("repeated_checkout", 1),
        ("main_advance", 1),
    ]:
        for variant in range(1, count + 1):
            cases.append(build_branch_isolation(number, subtype, variant))
            number += 1

    for subtype, count in [
        ("single_add", 2),
        ("single_update", 2),
        ("single_remove", 2),
        ("mixed", 5),
        ("behind_main", 2),
        ("repeat_diff", 1),
    ]:
        for variant in range(1, count + 1):
            cases.append(build_diff_case(number, subtype, variant))
            number += 1

    for subtype, count in [
        ("append_count", 4),
        ("mixed_types", 2),
        ("main_advance_merge", 2),
        ("repeat_merge", 2),
        ("post_merge_write", 2),
    ]:
        for variant in range(1, count + 1):
            cases.append(build_merge_case(number, subtype, variant))
            number += 1

    for subtype, count in [
        ("update_update", 4),
        ("update_delete", 3),
        ("delete_update", 3),
        ("same_update", 1),
        ("same_delete", 1),
    ]:
        for variant in range(1, count + 1):
            cases.append(build_conflict_case(number, subtype, variant))
            number += 1

    validate(cases)
    return cases


def main() -> None:
    output = (
        Path(__file__).resolve().parents[2]
        / "datasets/feature/branch-diff-merge/branch-diff-merge-formal-v1.jsonl"
    )
    rows = build()
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "cases": len(rows),
                "categories": Counter(row["category"] for row in rows),
                "subtypes": Counter(row["subtype"] for row in rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
