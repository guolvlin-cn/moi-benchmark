#!/usr/bin/env python3
"""对三个产品统一格式的多轮预测计算准确性、成功率和稳定性。"""

from __future__ import annotations

import argparse
import json
import math
import os
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
    validate_read_only,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一评测多轮 NL2SQL 运行记录")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--product", required=True)
    parser.add_argument("--run-id", default="")
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
            raise ValueError(f"JSONL第{line_number}行缺少question_id")
        value["question_id"] = str(question_id)
        value["repeat_index"] = int(value.get("repeat_index") or value.get("attempt") or 1)
        records.append(value)
    return records


def generated_sql(record: dict[str, Any]) -> str:
    return str(record.get("generated_sql") or record.get("sql") or "").strip()


def latency_ms(record: dict[str, Any]) -> float | None:
    value = record.get("latency_ms")
    if value is not None:
        return float(value)
    seconds = record.get("latency_seconds")
    return float(seconds) * 1000 if seconds is not None else None


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * ratio
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 3)


def rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 4) if denominator else None,
        "percent": round(numerator / denominator * 100, 2) if denominator else None,
    }


def main() -> int:
    args = parse_args()
    cases = load_cases(args.cases)
    cases_by_id = {short_id(str(item["case_id"])): item for item in cases}
    source_records = load_records(args.predictions)
    records_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for record in source_records:
        key = (short_id(record["question_id"]), record["repeat_index"])
        if key in records_by_key:
            raise ValueError(f"重复记录：{key[0]} 第{key[1]}轮")
        records_by_key[key] = record

    conn = connection()
    evaluated: list[dict[str, Any]] = []
    try:
        for case_id, case in cases_by_id.items():
            gold_sql = str(case["gold_sql"]).strip().rstrip(";").strip()
            for repeat_index in range(1, args.expected_repeats + 1):
                source = records_by_key.get((case_id, repeat_index))
                item: dict[str, Any] = {
                    "case_id": str(case["case_id"]),
                    "difficulty": case["difficulty"],
                    "question": case["question"],
                    "repeat_index": repeat_index,
                    "generation_status": source.get("status") if source else "missing",
                    "pred_sql": generated_sql(source or {}),
                    "sql_success": False,
                    "execution_correct": False,
                    "reason": "missing_prediction" if source is None else "",
                    "latency_ms": latency_ms(source or {}),
                    "prompt_tokens": (source or {}).get("prompt_tokens"),
                    "completion_tokens": (source or {}).get("completion_tokens"),
                    "total_tokens": (source or {}).get("total_tokens"),
                }
                readonly_error = validate_read_only(item["pred_sql"])
                if readonly_error:
                    item["reason"] = readonly_error
                    evaluated.append(item)
                    continue
                try:
                    gold_columns, gold_rows, gold_ms = execute(conn, gold_sql)
                    pred_columns, pred_rows, pred_ms = execute(conn, item["pred_sql"])
                    item["sql_success"] = True
                    ordered = "order by" in gold_sql.lower()
                    passed, reason = compare_rows(gold_rows, pred_rows, ordered)
                    item.update(
                        {
                            "execution_correct": passed,
                            "reason": reason,
                            "ordered_comparison": ordered,
                            "gold_columns": gold_columns,
                            "pred_columns": pred_columns,
                            "gold_row_count": len(gold_rows),
                            "pred_row_count": len(pred_rows),
                            "gold_sample": sample(gold_rows),
                            "pred_sample": sample(pred_rows),
                            "gold_execution_ms": gold_ms,
                            "pred_execution_ms": pred_ms,
                        }
                    )
                except Exception as exc:
                    item["reason"] = f"execution_error: {exc}"
                    try:
                        conn.ping(reconnect=True)
                    except Exception:
                        conn.close()
                        conn = connection()
                evaluated.append(item)
    finally:
        conn.close()

    total = len(evaluated)
    correct = sum(bool(item["execution_correct"]) for item in evaluated)
    sql_success = sum(bool(item["sql_success"]) for item in evaluated)
    repeat_correct = 0
    for case_id in cases_by_id:
        attempts = [
            item for item in evaluated if short_id(item["case_id"]) == case_id
        ]
        if len(attempts) == args.expected_repeats and all(
            item["execution_correct"] for item in attempts
        ):
            repeat_correct += 1

    latencies = [item["latency_ms"] for item in evaluated if item["latency_ms"] is not None]
    prompt_values = [int(item["prompt_tokens"]) for item in evaluated if item["prompt_tokens"] is not None]
    completion_values = [
        int(item["completion_tokens"])
        for item in evaluated
        if item["completion_tokens"] is not None
    ]
    total_token_values = [
        int(item["total_tokens"]) for item in evaluated if item["total_tokens"] is not None
    ]
    first_round = [item for item in evaluated if item["repeat_index"] == 1]
    report = {
        "benchmark_id": "enron_golden50_v1",
        "product": args.product,
        "run_id": args.run_id or None,
        "database": os.getenv("ENRON_DB_NAME", "enron_eval"),
        "expected_repeats": args.expected_repeats,
        "metrics": {
            "execution_accuracy": rate(correct, total),
            "sql_success_rate": rate(sql_success, total),
            "repeat_correct_rate": rate(repeat_correct, len(cases)),
            "first_round_execution_accuracy": rate(
                sum(bool(item["execution_correct"]) for item in first_round),
                len(first_round),
            ),
            "end_to_end_latency_ms": {
                "observed": len(latencies),
                "mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
            },
            "token_usage": {
                "observed": len(total_token_values),
                "prompt_total": sum(prompt_values),
                "completion_total": sum(completion_values),
                "total": sum(total_token_values),
                "mean_per_attempt": (
                    round(sum(total_token_values) / len(total_token_values), 3)
                    if total_token_values
                    else None
                ),
            },
        },
        "predictions_file": str(args.predictions),
        "records": evaluated,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        f"{args.product}: Execution Accuracy {correct}/{total}; "
        f"SQL Success {sql_success}/{total}; Repeat Correct {repeat_correct}/{len(cases)}"
    )
    print(f"报告：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
