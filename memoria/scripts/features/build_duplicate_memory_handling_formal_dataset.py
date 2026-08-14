#!/usr/bin/env python3
"""构造 50 个 Memoria 重复与近重复记忆处理正式用例。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


SUITE = "duplicate-memory-handling-formal-v1"
THRESHOLD = 0.3162
CATEGORY_COUNTS = {
    "exact_duplicate_reuse": 10,
    "semantic_equivalent_handling": 24,
    "coexistence_scope_isolation": 16,
}


EXACT = [
    ("identical", "Alice drinks coffee every morning.", "Alice drinks coffee every morning.", "alice", "drink", "profile"),
    ("identical", "Ben works from the Shanghai office on Tuesdays.", "Ben works from the Shanghai office on Tuesdays.", "ben", "office", "working"),
    ("identical", "Chloe prefers a window seat on long flights.", "Chloe prefers a window seat on long flights.", "chloe", "seat", "profile"),
    ("identical", "Daniel backs up his laptop every Friday evening.", "Daniel backs up his laptop every Friday evening.", "daniel", "backup", "procedural"),
    ("identical", "Emma is learning Japanese for an autumn trip.", "Emma is learning Japanese for an autumn trip.", "emma", "language", "semantic"),
    ("identical", "Felix swims at the community pool on Saturdays.", "Felix swims at the community pool on Saturdays.", "felix", "exercise", "episodic"),
    ("leading_space", "Grace uses a mechanical keyboard at her desk.", " Grace uses a mechanical keyboard at her desk.", "grace", "device", "profile"),
    ("trailing_space", "Henry attends the planning meeting every Monday.", "Henry attends the planning meeting every Monday. ", "henry", "meeting", "working"),
    ("single_edge_spaces", "Iris keeps her passport in the home safe.", " Iris keeps her passport in the home safe. ", "iris", "passport", "profile"),
    ("multiple_edge_spaces", "Jack reviews his calendar every Sunday evening.", "   Jack reviews his calendar every Sunday evening.   ", "jack", "calendar", "profile"),
]


INSIDE = [
    ("Iris drinks green tea every afternoon.", "Iris drinks green tea each afternoon.", "iris", "drink", 0.993257410, 0.116125709),
    ("Jack works remotely on Fridays.", "Jack works remotely each Friday.", "jack", "work_mode", 0.978868911, 0.205577661),
    ("Karen reviews her calendar every Monday morning.", "Karen reviews her calendar each Monday morning.", "karen", "calendar", 0.998358640, 0.057295036),
    ("Leo keeps his passport in the home safe.", "Leo keeps his passport inside the home safe.", "leo", "passport", 0.995707935, 0.092650585),
    ("Mia takes the metro to work every weekday.", "Mia takes the metro to work each weekday.", "mia", "commute", 0.998032817, 0.062724524),
    ("Noah reads historical fiction before bed every night.", "Noah reads historical fiction before bed each night.", "noah", "reading", 0.998607148, 0.052779777),
    ("Olivia practices yoga before work every Tuesday.", "Olivia practices yoga before work each Tuesday.", "olivia", "exercise", 0.998276911, 0.058704158),
    ("Peter plans the weekly meals every Sunday.", "Peter plans the weekly meals each Sunday.", "peter", "meal_plan", 0.995054785, 0.099450642),
]


NEAR_OUTSIDE = [
    ("Thomas walks along the river after dinner.", "Thomas takes a walk along the river after dinner.", "thomas", "walk", 0.906078904, 0.433407662),
    ("Uma checks the project board every morning.", "Every morning, Uma checks the project board.", "uma", "project_board", 0.942036178, 0.340481499),
    ("Xavier stores backups on an external drive.", "Xavier keeps backup copies on an external drive.", "xavier", "backup", 0.949178463, 0.318815115),
    ("Zach prefers a window seat on long flights.", "For lengthy flights, Zach likes sitting next to the window.", "zach", "seat", 0.927966155, 0.379562515),
    ("Caleb attends a pottery class on Saturdays.", "Saturday is the day Caleb takes lessons in making pottery.", "caleb", "class", 0.902528634, 0.441523205),
    ("Diana walks her dog in the park every evening.", "Each evening, Diana takes her dog out for a walk in the park.", "diana", "dog_walk", 0.947734981, 0.323311044),
    ("Gavin works remotely on Fridays.", "Gavin works from home on Fridays.", "gavin", "work_mode", 0.943962631, 0.334775661),
    ("Hazel enjoys historical fiction before bed.", "Hazel likes reading historical novels at bedtime.", "hazel", "reading", 0.949031455, 0.319275877),
]


CLEAR_OUTSIDE = [
    ("Yvonne reads for thirty minutes before sleeping.", "Before going to sleep, Yvonne spends half an hour reading.", "yvonne", "reading", 0.867536391, 0.514710831),
    ("Aaron exercises at the gym after work.", "Once his workday ends, Aaron goes to the gym to exercise.", "aaron", "exercise", 0.777836964, 0.666577920),
    ("Bella reviews her task list before lunch.", "Prior to her midday meal, Bella goes through the tasks on her list.", "bella", "planning", 0.855276198, 0.538003383),
    ("Fiona drinks coffee without sugar.", "Fiona takes her coffee unsweetened.", "fiona", "drink", 0.889205516, 0.470732378),
]


CHAINS = [
    (["Grace drinks green tea every morning.", "Grace drinks green tea each morning.", "Grace drinks green tea every morning of the week."], "grace", "drink", [(0.996440023, 0.084379827), (0.969040331, 0.248835956)]),
    (["Henry reviews his calendar every Monday.", "Henry reviews his calendar each Monday.", "Henry reviews his calendar every Monday morning."], "henry", "calendar", [(0.997285347, 0.073683831), (0.988109740, 0.154209339)]),
    (["Julia walks by the river every evening.", "Julia walks by the river each evening.", "Julia takes a walk by the river each evening."], "julia", "walk", [(0.993020812, 0.118145572), (0.968453346, 0.251183817)]),
    (["Nina works remotely every Friday.", "Nina works remotely each Friday.", "Nina works remotely on every Friday."], "nina", "work_mode", [(0.996538198, 0.083208194), (0.992473805, 0.122688183)]),
]


INDEPENDENT = [
    ("Ian prefers coffee in the morning.", "Ian owns a coffee grinder at home.", "ian", "coffee"),
    ("Julia works from home on Fridays.", "Julia attends a team lunch on Fridays.", "julia", "friday"),
    ("Kevin studies Japanese in the evening.", "Kevin watches Japanese films on weekends.", "kevin", "japanese"),
    ("Laura keeps her passport in the home safe.", "Laura keeps spare keys in the home safe.", "laura", "safe"),
    ("Martin runs in the park before work.", "Martin walks his dog in the park after work.", "martin", "park"),
    ("Nina uses a tablet for reading.", "Nina uses a laptop for programming.", "nina", "device"),
    ("Oscar reviews the budget every Monday.", "Oscar submits the weekly report every Monday.", "oscar", "monday"),
    ("Paula attends a pottery class downtown.", "Paula buys pottery supplies downtown.", "paula", "pottery"),
]


def ids(number: int, slug: str) -> tuple[str, str]:
    return f"dmh-formal-{number:03d}-{slug}", f"feature-dmh-formal-{number:03d}"


def store(case_id: str, alias: str, content: str, subject: str, field: str, *, session: str, memory_type: str = "profile", user_ref: str = "primary", branch: str = "main", metadata_alias: str | None = None) -> dict[str, Any]:
    return {
        "op": "store_memory", "operation_alias": f"store_{alias}", "memory_alias": alias,
        "user_ref": user_ref, "branch": branch, "content": content,
        "memory_type": memory_type, "subject_id": subject,
        "session_id": f"{case_id}-{session}", "trust_tier": "T2", "initial_confidence": 0.95,
        "extra_metadata": {"benchmark": "memoria-features", "suite": SUITE, "case_id": case_id, "memory_alias": metadata_alias or alias, "field": field},
        "expected_status": 201,
    }


def relation(source: str, target: str, semantic_relation: str, semantic_action: str, *, cosine: float | None = None, l2: float | None = None, selection_band: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "from_alias": source, "to_alias": target,
        "semantic_relation": semantic_relation,
        "semantic_expected_action": semantic_action,
    }
    if cosine is not None and l2 is not None:
        item["selection_measurement"] = {
            "embedding_model": "text-embedding-v4", "embedding_dimension": 1024,
            "cosine_similarity": cosine, "l2_distance": l2,
            "threshold_l2": THRESHOLD, "selection_band": selection_band,
        }
    return item


def finish(last: str, root: str = "v1") -> list[dict[str, Any]]:
    return [
        {"op": "capture_state", "state_alias": "after_writes"},
        {"op": "get_history", "operation_alias": "history", "target_alias": root, "expected_status": 200},
        {"op": "retrieve", "retrieval_alias": "final_retrieval", "query_alias": last, "top_k": 10},
    ]


def expected(actions: list[str], active: dict[str, list[str]], history: dict[str, int], contains: dict[str, list[str]], excludes: dict[str, list[str]]) -> dict[str, Any]:
    return {"semantic_actions": actions, "active_aliases_by_scope": active, "history_lengths": history, "retrieval_contains_by_scope": contains, "retrieval_excludes_by_scope": excludes}


def make_case(number: int, slug: str, category: str, subtype: str, description: str, operations: list[dict[str, Any]], relations: list[dict[str, Any]], expected_state: dict[str, Any], tags: list[str], *, secondary: bool = False) -> dict[str, Any]:
    case_id, user_id = ids(number, slug)
    users = {"primary": user_id}
    if secondary:
        users["secondary"] = f"{user_id}-secondary"
    return {"schema_version": "1.0", "suite": SUITE, "case_id": case_id, "category": category, "subtype": subtype, "track": "controlled-direct-store", "users": users, "description": description, "operations": operations, "relations": relations, "expected_semantic_state": expected_state, "tags": tags}


def exact_case(number: int, spec: tuple[str, str, str, str, str, str]) -> dict[str, Any]:
    subtype, first, second, subject, field, memory_type = spec
    case_id, _ = ids(number, "exact-duplicate")
    ops = [
        store(case_id, "v1", first, subject, field, session="session-a", memory_type=memory_type),
        store(case_id, "v2", second, subject, field, session="session-b", memory_type=memory_type, metadata_alias="v1"),
        *finish("v2"),
    ]
    return make_case(number, "exact-duplicate", "exact_duplicate_reuse", subtype, "验证完全相同或仅首尾空格不同的文本能否复用原记忆。", ops,
        [relation("v1", "v2", "exact_duplicate", "reuse")],
        expected(["reuse"], {"primary:main": ["v1"]}, {"v1": 1}, {"primary:main": ["v1"]}, {"primary:main": []}),
        ["exact-duplicate", subtype])


def equivalent_case(number: int, spec: tuple[str, str, str, str, float, float], subtype: str, band: str) -> dict[str, Any]:
    first, second, subject, field, cosine, l2 = spec
    case_id, _ = ids(number, "semantic-equivalent")
    ops = [store(case_id, "v1", first, subject, field, session="session-a"), store(case_id, "v2", second, subject, field, session="session-b"), *finish("v2")]
    return make_case(number, "semantic-equivalent", "semantic_equivalent_handling", subtype, "验证人类判断语义等价但文本不同的记忆是否建立版本替换。", ops,
        [relation("v1", "v2", "semantic_equivalent", "supersede", cosine=cosine, l2=l2, selection_band=band)],
        expected(["supersede"], {"primary:main": ["v2"]}, {"v1": 2}, {"primary:main": ["v2"]}, {"primary:main": ["v1"]}),
        ["semantic-equivalent", band])


def chain_case(number: int, spec: tuple[list[str], str, str, list[tuple[float, float]]]) -> dict[str, Any]:
    texts, subject, field, measurements = spec
    case_id, _ = ids(number, "semantic-chain")
    ops = [store(case_id, f"v{i}", text, subject, field, session=f"session-{i}") for i, text in enumerate(texts, 1)] + finish(f"v{len(texts)}")
    relations = [relation(f"v{i}", f"v{i+1}", "semantic_equivalent", "supersede", cosine=cosine, l2=l2, selection_band="inside_threshold") for i, (cosine, l2) in enumerate(measurements, 1)]
    latest = f"v{len(texts)}"
    return make_case(number, "semantic-chain", "semantic_equivalent_handling", "continuous_inside_threshold_chain", "验证相邻改写均在阈值内时能否形成完整连续版本链。", ops, relations,
        expected(["supersede"] * len(relations), {"primary:main": [latest]}, {"v1": len(texts)}, {"primary:main": [latest]}, {"primary:main": [f"v{i}" for i in range(1, len(texts))]}),
        ["semantic-equivalent", "inside-threshold", "continuous-chain"])


def independent_case(number: int, spec: tuple[str, str, str, str]) -> dict[str, Any]:
    first, second, subject, field = spec
    case_id, _ = ids(number, "independent-facts")
    ops = [store(case_id, "v1", first, subject, field, session="session-a"), store(case_id, "v2", second, subject, field, session="session-b"), *finish("v2")]
    return make_case(number, "independent-facts", "coexistence_scope_isolation", "same_scope_independent_facts", "验证同一作用域内共享主题词但可同时成立的事实不会互相覆盖。", ops,
        [relation("v1", "v2", "independent", "coexist")],
        expected(["coexist"], {"primary:main": ["v1", "v2"]}, {"v1": 1, "v2": 1}, {"primary:main": ["v1", "v2"]}, {"primary:main": []}),
        ["coexistence", "independent-facts"])


def scope_case(number: int, subtype: str) -> dict[str, Any]:
    case_id, _ = ids(number, "scope-isolation")
    text = {"subject": "The user prefers a window seat on long flights.", "memory_type": "The user reviews weekly plans every Monday.", "branch": "The user prepares a quarterly budget.", "user": "The user keeps emergency contacts in the phone."}[subtype]
    first = {"subject": "alice", "memory_type": "profile", "user_ref": "primary", "branch": "main"}
    second = dict(first)
    secondary = False
    prefix: list[dict[str, Any]] = []
    if subtype == "subject": second["subject"] = "bob"
    elif subtype == "memory_type": second["memory_type"] = "semantic"
    elif subtype == "branch":
        prefix = [{"op": "create_branch", "operation_alias": "create_experiment", "branch": "experiment", "expected_status": 201}]
        second["branch"] = "experiment"
    else:
        second["user_ref"] = "secondary"; secondary = True
    ops = prefix + [
        store(case_id, "v1", text, first["subject"], "scope", session="session-a", memory_type=first["memory_type"], user_ref=first["user_ref"], branch=first["branch"]),
        store(case_id, "v2", text, second["subject"], "scope", session="session-b", memory_type=second["memory_type"], user_ref=second["user_ref"], branch=second["branch"]),
        {"op": "capture_all_scopes", "state_alias": "after_writes"},
        {"op": "retrieve_all_scopes", "retrieval_alias": "final_retrieval", "query_alias": "v1", "top_k": 10},
    ]
    scopes = {"primary:main": ["v1"]}
    if subtype in {"subject", "memory_type"}: scopes["primary:main"] = ["v1", "v2"]
    elif subtype == "branch": scopes["primary:experiment"] = ["v2"]
    else: scopes["secondary:main"] = ["v2"]
    return make_case(number, "scope-isolation", "coexistence_scope_isolation", f"{subtype}_isolation", f"验证完全相同文本不会跨 {subtype} 作用域复用或替换。", ops,
        [relation("v1", "v2", "scope_isolated", "coexist")],
        expected(["coexist"], scopes, {"v1": 1, "v2": 1}, {scope: aliases[:] for scope, aliases in scopes.items()}, {scope: [] for scope in scopes}),
        ["coexistence", "scope-isolation", subtype], secondary=secondary)


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for spec in EXACT: cases.append(exact_case(len(cases) + 1, spec))
    for spec in INSIDE: cases.append(equivalent_case(len(cases) + 1, spec, "single_inside_threshold", "inside_threshold"))
    for spec in NEAR_OUTSIDE: cases.append(equivalent_case(len(cases) + 1, spec, "single_near_outside_threshold", "near_outside_threshold"))
    for spec in CLEAR_OUTSIDE: cases.append(equivalent_case(len(cases) + 1, spec, "single_clear_outside_threshold", "clear_outside_threshold"))
    for spec in CHAINS: cases.append(chain_case(len(cases) + 1, spec))
    for spec in INDEPENDENT: cases.append(independent_case(len(cases) + 1, spec))
    for subtype in ["subject", "subject", "memory_type", "memory_type", "branch", "branch", "user", "user"]:
        cases.append(scope_case(len(cases) + 1, subtype))
    return cases


def validate(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 50: raise ValueError(f"expected 50 cases, got {len(cases)}")
    if Counter(case["category"] for case in cases) != Counter(CATEGORY_COUNTS): raise ValueError("category distribution mismatch")
    if len({case["case_id"] for case in cases}) != 50: raise ValueError("duplicate case_id")
    for case in cases:
        stores = [op for op in case["operations"] if op["op"] == "store_memory"]
        if len(case["relations"]) != len(stores) - 1: raise ValueError(f"relation mismatch: {case['case_id']}")
        for item in case["relations"]:
            measurement = item.get("selection_measurement")
            if measurement:
                inside = measurement["l2_distance"] <= THRESHOLD
                expected_inside = measurement["selection_band"] == "inside_threshold"
                if inside != expected_inside: raise ValueError(f"selection band mismatch: {case['case_id']}")
        for op in stores:
            if op["content"].lstrip().startswith("["): raise ValueError(f"synthetic anchor: {case['case_id']}")


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    output = root / "memoria/datasets/feature/duplicate-memory-handling/duplicate-memory-handling-formal-v1.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    cases = build_cases(); validate(cases)
    with output.open("w", encoding="utf-8") as handle:
        for case in cases: handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "cases": len(cases), "categories": CATEGORY_COUNTS, "writes": sum(sum(op["op"] == "store_memory" for op in case["operations"]) for case in cases), "relations": sum(len(case["relations"]) for case in cases)}, ensure_ascii=False))


if __name__ == "__main__": main()
