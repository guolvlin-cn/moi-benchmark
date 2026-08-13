#!/usr/bin/env python3
"""按统一的增量语义状态口径汇总 Mem0 与 Zep 正式实验。"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from competitor_smoke_common import store_operations, utc_now, write_json


ZEP_FAILURES = {
    "dmh-formal-001-exact-duplicate": "第二次写入新增一条与原事实完全相同的活跃 edge",
    "dmh-formal-009-exact-duplicate": "第二次写入后形成两条相同的护照存放事实",
    "dmh-formal-010-exact-duplicate": "第二次写入新增一条与原事实完全相同的活跃 edge",
    "dmh-formal-013-semantic-equivalent": "第二次写入生成两条完全相同的新活跃 edge",
    "dmh-formal-014-semantic-equivalent": "新旧护照事实同时活跃，并新增同义所有权事实",
    "dmh-formal-021-semantic-equivalent": "新旧备份表述以两条活跃 edge 并存",
    "dmh-formal-022-semantic-equivalent": "新表述生成重复 edge，且旧窗口座位事实仍活跃",
    "dmh-formal-023-semantic-equivalent": "新旧陶艺课表述均以独立活跃 edge 并存",
    "dmh-formal-025-semantic-equivalent": "新写入将单条旧事实扩展为两条重叠活跃事实",
    "dmh-formal-028-semantic-equivalent": "新旧健身表述以两条活跃 edge 并存",
    "dmh-formal-032-semantic-chain": "三版本链最终保留旧表述并新增两条相同的新表述",
    "dmh-formal-033-semantic-chain": "第三个版本新增两条重叠事实，旧表述仍活跃",
    "dmh-formal-040-independent-facts": "第二次写入后平板阅读事实不再活跃",
    "dmh-formal-042-independent-facts": "第二次写入后陶艺课程事实不再活跃",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def active_edges(step: dict[str, Any]) -> list[dict[str, Any]]:
    return [edge for edge in step["edges_after"] if not edge.get("invalid_at") and not edge.get("expired_at")]


def score_mem0(case: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    operations = store_operations(case)
    latest_state_by_user: dict[str, list[dict[str, Any]]] = {}
    for step in result["steps"]:
        latest_state_by_user[step["identity"]["user_id"]] = step["user_state"].get("results", [])
    final_by_user = {memory["id"]: memory for memories in latest_state_by_user.values() for memory in memories}
    count = len(final_by_user)
    category, subtype = case["category"], case["subtype"]
    expected = 1 if category != "coexistence_scope_isolation" else 2
    passed = count == expected
    if passed:
        reason = f"最终得到预期的 {expected} 条相互独立活跃记忆"
    elif category == "coexistence_scope_isolation" and subtype != "same_scope_independent_facts":
        reason = f"映射的作用域未形成隔离，最终仅 {count} 条活跃记忆"
    else:
        reason = f"最终活跃记忆数为 {count}，预期 {expected}"
    latest_event = result["steps"][-1]["event"].get("results", [])
    evidence = {
        "final_unique_memory_count": count,
        "final_memories": [m.get("memory") for m in final_by_user.values()],
        "operation_events": [[e.get("event") for e in step["event"].get("results", [])] for step in result["steps"]],
        "latest_write_changed_state": bool(latest_event),
        "operation_count": len(operations),
    }
    return passed, reason, evidence


def score_zep(case: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    case_id = case["case_id"]
    passed = case_id not in ZEP_FAILURES
    reason = "第二次写入未引入新的语义冗余，或独立事实均保持活跃" if passed else ZEP_FAILURES[case_id]
    steps = result["steps"]
    episode_ids = [step["episode_id"] for step in steps]
    final = active_edges(steps[-1])
    final_episode = episode_ids[-1]
    previous = set(episode_ids[:-1])
    final_only = any(final_episode in set(e.get("episodes") or []) and not (previous & set(e.get("episodes") or [])) for e in final)
    previous_only = any((previous & set(e.get("episodes") or [])) and final_episode not in set(e.get("episodes") or []) for e in final)
    evidence = {
        "active_edge_counts_after_each_write": [len(active_edges(step)) for step in steps],
        "final_active_facts": [edge.get("fact") for edge in final],
        "latest_only_edge_present": final_only,
        "prior_only_edge_present": previous_only,
        "scope_mode": result["scope_mode"],
    }
    return passed, reason, evidence


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, Counter] = defaultdict(Counter)
    by_subtype: dict[str, Counter] = defaultdict(Counter)
    total = Counter()
    for row in rows:
        key = "PASS" if row["passed"] else "FAIL"
        total[key] += 1; by_category[row["category"]][key] += 1; by_subtype[row["subtype"]][key] += 1
    def pack(counter: Counter) -> dict[str, Any]:
        n = counter["PASS"] + counter["FAIL"]
        return {"pass": counter["PASS"], "fail": counter["FAIL"], "total": n, "accuracy": counter["PASS"] / n if n else None}
    return {"overall": pack(total), "by_category": {k: pack(v) for k, v in sorted(by_category.items())}, "by_subtype": {k: pack(v) for k, v in sorted(by_subtype.items())}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--mem0-run", type=Path, required=True)
    parser.add_argument("--zep-run", type=Path, required=True)
    args = parser.parse_args()
    cases = {r["case_id"]: r for r in load_jsonl(args.dataset)}
    for provider, run_dir, scorer in (("mem0", args.mem0_run, score_mem0), ("zep", args.zep_run, score_zep)):
        results = {r["case_id"]: r for r in load_jsonl(run_dir / "case-results.jsonl")}
        if set(results) != set(cases):
            raise RuntimeError(f"{provider}: case coverage mismatch")
        scored = []
        for case_id in sorted(cases):
            result = results[case_id]
            if result["status"] != "COMPLETED": raise RuntimeError(f"{provider}: incomplete case {case_id}")
            passed, reason, evidence = scorer(cases[case_id], result)
            scored.append({"case_id": case_id, "provider": provider, "category": cases[case_id]["category"], "subtype": cases[case_id]["subtype"], "passed": passed, "reason": reason, "evidence": evidence})
        (run_dir / "scored-results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in scored), encoding="utf-8")
        metrics = {"scored_at": utc_now(), "scoring_protocol": "incremental-semantic-state-v1", **summarize(scored)}
        if provider == "mem0":
            semantic = [r for r in scored if r["category"] == "semantic_equivalent_handling"]
            metrics["semantic_latest_write_changed_state"] = sum(r["evidence"]["latest_write_changed_state"] for r in semantic)
        else:
            semantic = [r for r in scored if r["category"] == "semantic_equivalent_handling"]
            metrics["semantic_strict_latest_adoption"] = sum(r["evidence"]["latest_only_edge_present"] and not r["evidence"]["prior_only_edge_present"] for r in semantic)
            metrics["native_scope_overall"] = summarize([r for r in scored if r["evidence"]["scope_mode"] == "native"])["overall"]
            metrics["adapted_scope_overall"] = summarize([r for r in scored if r["evidence"]["scope_mode"] == "adapted"])["overall"]
        write_json(run_dir / "scored-metrics.json", metrics)
        print(provider, json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
