#!/usr/bin/env python3
"""Compare MOI's saved MatrixOne-native results with MySQL Golden results."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from evaluate_mysql import (
    DEFAULT_CASES,
    compare_rows,
    connection,
    execute,
    load_cases,
    sample,
    short_id,
)


ORDER_BY = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare MOI MatrixOne-native results with MySQL Golden results"
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--variant", default="baseline_no_semantic")
    parser.add_argument("--expected-repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        question_id = value.get("question_id") or value.get("case_id") or value.get("id")
        if not question_id:
            raise ValueError(f"JSONL line {line_number} has no question_id")
        value["question_id"] = str(question_id)
        value["repeat_index"] = int(value.get("repeat_index") or value.get("attempt") or 1)
        records.append(value)
    return records


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * ratio
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 3)


def rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 4) if denominator else None,
        "percent": round(100 * numerator / denominator, 2) if denominator else None,
    }


def result_rows(result: dict[str, Any]) -> list[tuple[Any, ...]]:
    rows = result.get("rows")
    if not isinstance(rows, list):
        return []
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        if isinstance(row, (list, tuple)):
            normalized.append(tuple(row))
        else:
            normalized.append((row,))
    return normalized


def compare_result(
    gold_columns: list[str],
    gold_rows: list[tuple[Any, ...]],
    result: dict[str, Any],
    ordered: bool,
) -> tuple[bool, str, list[tuple[Any, ...]], bool]:
    pred_columns = result.get("columns") or []
    pred_rows = result_rows(result)
    if len(gold_columns) != len(pred_columns):
        return (
            False,
            f"column_count_mismatch: gold={len(gold_columns)} pred={len(pred_columns)}",
            pred_rows,
            False,
        )
    passed, reason = compare_rows(gold_rows, pred_rows, ordered)
    unordered_equivalent = False
    if ordered and not passed:
        unordered_equivalent, _ = compare_rows(gold_rows, pred_rows, False)
    return passed, reason, pred_rows, unordered_equivalent


def candidate_summary(
    result: dict[str, Any], passed: bool, reason: str, rows: list[tuple[Any, ...]],
    unordered_equivalent: bool = False,
) -> dict[str, Any]:
    return {
        "artifact_id": result.get("artifact_id"),
        "sql": result.get("sql"),
        "columns": result.get("columns") or [],
        "row_count": len(rows),
        "sample": sample(rows),
        "execution_ms": result.get("execution_ms"),
        "passed": passed,
        "reason": reason,
        "unordered_equivalent": unordered_equivalent,
        "combined_candidate": bool(result.get("combined_candidate")),
    }


def choose_failure(candidates: list[dict[str, Any]]) -> tuple[str, int | None]:
    if not candidates:
        return "no_selected_native_result", None
    priority = {
        "ordered_value_mismatch": 0,
        "unordered_value_mismatch": 1,
        "column_count_mismatch": 2,
        "row_count_mismatch": 3,
    }
    ranked: list[tuple[int, int]] = []
    for index, candidate in enumerate(candidates):
        reason = str(candidate.get("reason") or "")
        prefix = next((key for key in priority if reason.startswith(key)), "")
        ranked.append((priority.get(prefix, 9), index))
    _, best_index = min(ranked)
    return str(candidates[best_index].get("reason") or "result_mismatch"), best_index


def main() -> int:
    args = parse_args()
    cases = load_cases(args.cases)
    cases_by_id = {short_id(str(case["case_id"])): case for case in cases}
    source_records = load_records(args.predictions)
    records_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for record in source_records:
        key = (short_id(record["question_id"]), record["repeat_index"])
        if key in records_by_key:
            raise ValueError(f"Duplicate record: {key}")
        records_by_key[key] = record

    expected_keys = {
        (case_id, repeat_index)
        for case_id in cases_by_id
        for repeat_index in range(1, args.expected_repeats + 1)
    }
    extra_keys = sorted(set(records_by_key) - expected_keys)
    if extra_keys:
        raise ValueError(f"Unexpected prediction records: {extra_keys[:10]}")

    conn = connection()
    evaluated: list[dict[str, Any]] = []
    gold_cache: dict[str, tuple[list[str], list[tuple[Any, ...]], float]] = {}
    try:
        for case_id, case in cases_by_id.items():
            gold_sql = str(case["gold_sql"]).strip().rstrip(";").strip()
            gold_cache[case_id] = execute(conn, gold_sql)
            gold_columns, gold_rows, gold_ms = gold_cache[case_id]
            ordered = bool(ORDER_BY.search(gold_sql))
            for repeat_index in range(1, args.expected_repeats + 1):
                source = records_by_key.get((case_id, repeat_index))
                selected = list((source or {}).get("selected_native_results") or [])
                native = list((source or {}).get("native_query_results") or [])
                item: dict[str, Any] = {
                    "case_id": str(case["case_id"]),
                    "difficulty": case["difficulty"],
                    "question": case["question"],
                    "repeat_index": repeat_index,
                    "generation_status": (source or {}).get("status", "missing"),
                    "generated_sql": (source or {}).get("generated_sql") or "",
                    "native_execution_success": bool(
                        source and source.get("native_execution_success") and native
                    ),
                    "sql_success": bool(source and source.get("native_execution_success") and native),
                    "execution_correct": False,
                    "reason": "missing_prediction" if source is None else "",
                    "ordered_comparison": ordered,
                    "gold_sql": gold_sql,
                    "gold_columns": gold_columns,
                    "gold_row_count": len(gold_rows),
                    "gold_sample": sample(gold_rows),
                    "gold_execution_ms_mysql": gold_ms,
                    "latency_ms": (source or {}).get("latency_ms"),
                    "sql_execution_ms_matrixone": (source or {}).get("sql_execution_ms"),
                    "prompt_tokens": (source or {}).get("prompt_tokens"),
                    "completion_tokens": (source or {}).get("completion_tokens"),
                    "total_tokens": (source or {}).get("total_tokens"),
                    "cached_tokens": (source or {}).get("cached_tokens"),
                    "reasoning_tokens": (source or {}).get("reasoning_tokens"),
                    "llm_call_count": (source or {}).get("llm_call_count"),
                    "selected_result_count": len(selected),
                    "native_result_count": len(native),
                    "candidate_results": [],
                    "matched_candidate_index": None,
                    "unselected_exact_match": False,
                }
                if source is None or not item["sql_success"]:
                    if source is not None:
                        item["reason"] = (source.get("error") or "native_execution_failed")
                    evaluated.append(item)
                    continue

                for index, result in enumerate(selected):
                    passed, reason, rows, unordered_equivalent = compare_result(
                        gold_columns, gold_rows, result, ordered
                    )
                    item["candidate_results"].append(
                        candidate_summary(
                            result, passed, reason, rows, unordered_equivalent
                        )
                    )
                    if passed and not item["execution_correct"]:
                        item["execution_correct"] = True
                        item["matched_candidate_index"] = index

                groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
                for result in selected:
                    columns = tuple(str(value) for value in (result.get("columns") or []))
                    if columns:
                        groups.setdefault(columns, []).append(result)
                for columns, group in groups.items():
                    if len(group) < 2:
                        continue
                    combined_rows = [
                        list(row)
                        for result in group
                        for row in result_rows(result)
                    ]
                    combined_result: dict[str, Any] = {
                        "artifact_id": "+".join(
                            str(result.get("artifact_id") or "") for result in group
                        ),
                        "sql": "\n-- combined selected page/result --\n".join(
                            str(result.get("sql") or "") for result in group
                        ),
                        "columns": list(columns),
                        "rows": combined_rows,
                        "execution_ms": sum(
                            float(result.get("execution_ms") or 0) for result in group
                        ),
                        "combined_candidate": True,
                    }
                    passed, reason, rows, unordered_equivalent = compare_result(
                        gold_columns, gold_rows, combined_result, ordered
                    )
                    combined_index = len(item["candidate_results"])
                    item["candidate_results"].append(
                        candidate_summary(
                            combined_result, passed, reason, rows, unordered_equivalent
                        )
                    )
                    if passed and not item["execution_correct"]:
                        item["execution_correct"] = True
                        item["matched_candidate_index"] = combined_index

                if item["execution_correct"]:
                    item["reason"] = ""
                else:
                    item["reason"], item["best_candidate_index"] = choose_failure(
                        item["candidate_results"]
                    )
                    selected_ids = {
                        str(result.get("artifact_id")) for result in selected
                        if result.get("artifact_id") is not None
                    }
                    for result in native:
                        if str(result.get("artifact_id")) in selected_ids:
                            continue
                        passed, _, _, _ = compare_result(
                            gold_columns, gold_rows, result, ordered
                        )
                        if passed:
                            item["unselected_exact_match"] = True
                            break
                evaluated.append(item)
    finally:
        conn.close()

    total = len(evaluated)
    correct = sum(bool(item["execution_correct"]) for item in evaluated)
    sql_success = sum(bool(item["sql_success"]) for item in evaluated)
    repeat_correct = sum(
        all(
            item["execution_correct"]
            for item in evaluated
            if short_id(item["case_id"]) == case_id
        )
        for case_id in cases_by_id
    )
    first_round = [item for item in evaluated if item["repeat_index"] == 1]
    latencies = [float(item["latency_ms"]) for item in evaluated if item["latency_ms"] is not None]
    total_tokens = [int(item["total_tokens"]) for item in evaluated if item["total_tokens"] is not None]
    prompt_tokens = [int(item["prompt_tokens"]) for item in evaluated if item["prompt_tokens"] is not None]
    completion_tokens = [int(item["completion_tokens"]) for item in evaluated if item["completion_tokens"] is not None]

    by_difficulty: dict[str, Any] = {}
    for difficulty in ("easy", "medium", "hard"):
        subset = [item for item in evaluated if item["difficulty"] == difficulty]
        by_difficulty[difficulty] = rate(
            sum(bool(item["execution_correct"]) for item in subset), len(subset)
        )
    by_round: dict[str, Any] = {}
    for repeat_index in range(1, args.expected_repeats + 1):
        subset = [item for item in evaluated if item["repeat_index"] == repeat_index]
        by_round[str(repeat_index)] = rate(
            sum(bool(item["execution_correct"]) for item in subset), len(subset)
        )

    report = {
        "benchmark_id": "enron_golden50_v1",
        "product": "moi",
        "variant": args.variant,
        "run_id": args.run_id or None,
        "comparison": {
            "gold_engine": "mysql8",
            "prediction_engine": "matrixone",
            "prediction_result_scope": "selected_native_results",
            "multi_result_rule": "correct_if_any_selected_result_exactly_matches_golden",
        },
        "database": os.getenv("ENRON_DB_NAME", "enron_eval"),
        "expected_repeats": args.expected_repeats,
        "metrics": {
            "execution_accuracy": rate(correct, total),
            "sql_success_rate": rate(sql_success, total),
            "repeat_correct_rate": rate(repeat_correct, len(cases)),
            "first_round_execution_accuracy": rate(
                sum(bool(item["execution_correct"]) for item in first_round), len(first_round)
            ),
            "execution_accuracy_by_round": by_round,
            "execution_accuracy_by_difficulty": by_difficulty,
            "end_to_end_latency_ms": {
                "observed": len(latencies),
                "mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
            },
            "token_usage": {
                "observed": len(total_tokens),
                "prompt_total": sum(prompt_tokens),
                "completion_total": sum(completion_tokens),
                "total": sum(total_tokens),
                "mean_per_attempt": round(sum(total_tokens) / len(total_tokens), 3)
                if total_tokens else None,
                "p50_per_attempt": percentile([float(value) for value in total_tokens], 0.50),
                "p95_per_attempt": percentile([float(value) for value in total_tokens], 0.95),
            },
            "unselected_exact_matches": sum(
                bool(item["unselected_exact_match"]) for item in evaluated
            ),
        },
        "predictions_file": str(args.predictions.resolve()),
        "records": evaluated,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        f"MOI native: Execution Accuracy {correct}/{total}; "
        f"SQL Success {sql_success}/{total}; Repeat Correct {repeat_correct}/{len(cases)}"
    )
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
