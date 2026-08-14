#!/usr/bin/env python3
"""Evaluate saved MOI/MatrixOne results against Spider Golden SQL on MySQL."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from itertools import permutations
from pathlib import Path
from typing import Any

import pymysql


ORDER_BY = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)
QUESTION_LINE = re.compile(
    r"^\s*(\d+)\.\s*\[(easy|medium|hard)\]\s*\[([^\]]+)\]\s*(.+?)\s*$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare MOI MatrixOne-native results with MySQL Spider Golden results"
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--mysql-host", default=os.getenv("SPIDERMIX_DB_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(os.getenv("SPIDERMIX_DB_PORT", "3306")))
    parser.add_argument("--mysql-socket", default=os.getenv("SPIDERMIX_DB_SOCKET", ""))
    parser.add_argument("--mysql-user", default=os.getenv("SPIDERMIX_DB_USER", "root"))
    parser.add_argument("--mysql-password", default=os.getenv("SPIDERMIX_DB_PASSWORD", ""))
    return parser.parse_args()


def load_questions(path: Path) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        match = QUESTION_LINE.match(raw)
        if not match:
            raise ValueError(f"Cannot parse question line {line_number}: {raw}")
        number, difficulty, database, question = match.groups()
        questions.append(
            {
                "case_id": f"mix50_{int(number):03d}",
                "difficulty": difficulty,
                "database": database,
                "question": question,
            }
        )
    if len(questions) != 50:
        raise ValueError(f"Expected 50 questions, got {len(questions)}")
    return questions


def load_gold(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            sql, database = raw.rsplit("\t", 1)
        except ValueError as exc:
            raise ValueError(f"Golden line {line_number} has no tab-separated database") from exc
        rows.append({"sql": sql.strip().rstrip(";"), "database": database.strip()})
    if len(rows) != 50:
        raise ValueError(f"Expected 50 Golden SQL rows, got {len(rows)}")
    return rows


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        record = json.loads(raw)
        case_id = str(record.get("question_id") or "")
        if not case_id:
            raise ValueError(f"Prediction line {line_number} has no question_id")
        if case_id in records:
            raise ValueError(f"Duplicate prediction: {case_id}")
        records[case_id] = record
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


def metric(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 4) if denominator else None,
        "percent": round(100 * numerator / denominator, 2) if denominator else None,
    }


def normalized_value(value: Any) -> tuple[str, Any]:
    if value is None:
        return ("null", None)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, bool):
        return ("number", Decimal(int(value)).normalize())
    if isinstance(value, (int, float, Decimal)):
        try:
            return ("number", Decimal(str(value)).normalize())
        except InvalidOperation:
            pass
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return ("number", Decimal(stripped).normalize())
        except (InvalidOperation, ValueError):
            return ("text", stripped)
    return ("text", str(value).strip())


def values_equal(left: Any, right: Any) -> bool:
    left_kind, left_value = normalized_value(left)
    right_kind, right_value = normalized_value(right)
    if left_kind != right_kind:
        return False
    if left_kind == "number":
        return math.isclose(
            float(left_value), float(right_value), rel_tol=1e-8, abs_tol=1e-6
        )
    return left_value == right_value


def rows_equal(left: tuple[Any, ...], right: tuple[Any, ...]) -> bool:
    return len(left) == len(right) and all(
        values_equal(left_value, right_value)
        for left_value, right_value in zip(left, right)
    )


def results_equal(
    gold_rows: list[tuple[Any, ...]], pred_rows: list[tuple[Any, ...]], ordered: bool
) -> tuple[bool, str]:
    if len(gold_rows) != len(pred_rows):
        return False, f"row_count_mismatch: gold={len(gold_rows)} pred={len(pred_rows)}"
    if not gold_rows and not pred_rows:
        return True, ""
    gold_width = len(gold_rows[0])
    pred_width = len(pred_rows[0])
    if gold_width != pred_width:
        return False, f"column_count_mismatch: gold={gold_width} pred={pred_width}"
    for permutation in permutations(range(gold_width)):
        permuted = [tuple(row[index] for index in permutation) for row in pred_rows]
        if ordered:
            if all(rows_equal(gold_row, pred_row) for gold_row, pred_row in zip(gold_rows, permuted)):
                return True, ""
        else:
            used = [False] * len(permuted)
            matched = True
            for gold_row in gold_rows:
                for index, pred_row in enumerate(permuted):
                    if not used[index] and rows_equal(gold_row, pred_row):
                        used[index] = True
                        break
                else:
                    matched = False
                    break
            if matched:
                return True, ""
    return False, "ordered_value_mismatch" if ordered else "unordered_value_mismatch"


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def sample(rows: list[tuple[Any, ...]], limit: int = 5) -> list[list[Any]]:
    return [[json_value(value) for value in row] for row in rows[:limit]]


def native_rows(result: dict[str, Any]) -> list[tuple[Any, ...]]:
    rows = result.get("rows") or []
    return [tuple(row) if isinstance(row, (list, tuple)) else (row,) for row in rows]


def execute_gold(
    connection: pymysql.Connection, database: str, sql: str
) -> tuple[list[str], list[tuple[Any, ...]]]:
    connection.select_db(database)
    with connection.cursor() as cursor:
        cursor.execute(sql)
        columns = [item[0] for item in (cursor.description or [])]
        rows = list(cursor.fetchall())
    return columns, rows


def failure_reason(
    gold_columns: list[str], gold_rows: list[tuple[Any, ...]], result: dict[str, Any], ordered: bool
) -> tuple[bool, str, list[tuple[Any, ...]]]:
    rows = native_rows(result)
    columns = result.get("columns") or []
    if len(gold_columns) != len(columns):
        return False, f"column_count_mismatch: gold={len(gold_columns)} pred={len(columns)}", rows
    passed, reason = results_equal(gold_rows, rows, ordered)
    return passed, reason, rows


def main() -> int:
    args = parse_args()
    questions = load_questions(args.questions)
    gold = load_gold(args.gold)
    predictions = load_predictions(args.predictions)
    expected_ids = {item["case_id"] for item in questions}
    if set(predictions) != expected_ids:
        missing = sorted(expected_ids - set(predictions))
        extra = sorted(set(predictions) - expected_ids)
        raise ValueError(f"Prediction IDs differ; missing={missing}, extra={extra}")

    connection_options = {
        "host": args.mysql_host,
        "port": args.mysql_port,
        "user": args.mysql_user,
        "password": args.mysql_password,
        "charset": "utf8mb4",
        "connect_timeout": 10,
        "read_timeout": 120,
        "write_timeout": 120,
    }
    if args.mysql_socket:
        connection_options["unix_socket"] = args.mysql_socket
    connection = pymysql.connect(**connection_options)
    # Spider was authored for SQLite and includes a legacy aggregate query that
    # MySQL's ONLY_FULL_GROUP_BY mode rejects. Limit this compatibility change to
    # the read-only evaluation session; no server or database setting is changed.
    with connection.cursor() as cursor:
        cursor.execute(
            "SET SESSION sql_mode = REPLACE(@@SESSION.sql_mode, 'ONLY_FULL_GROUP_BY', '')"
        )
    records: list[dict[str, Any]] = []
    try:
        for question, golden in zip(questions, gold):
            if question["database"] != golden["database"]:
                raise ValueError(f"Database mismatch for {question['case_id']}")
            source = predictions[question["case_id"]]
            gold_columns, gold_rows = execute_gold(connection, golden["database"], golden["sql"])
            ordered = bool(ORDER_BY.search(golden["sql"]))
            selected = list(source.get("selected_native_results") or [])
            native = list(source.get("native_query_results") or [])
            sql_success = bool(
                source.get("generated_sql")
                and source.get("native_execution_success")
                and native
            )
            item: dict[str, Any] = {
                **question,
                "gold_sql": golden["sql"],
                "generated_sql": source.get("generated_sql") or "",
                "generation_status": source.get("status"),
                "sql_success": sql_success,
                "execution_correct": False,
                "reason": "",
                "ordered_comparison": ordered,
                "gold_columns": gold_columns,
                "gold_row_count": len(gold_rows),
                "gold_sample": sample(gold_rows),
                "selected_result_count": len(selected),
                "native_result_count": len(native),
                "candidate_results": [],
                "latency_ms": source.get("latency_ms"),
                "sql_execution_ms_matrixone": source.get("sql_execution_ms"),
                "prompt_tokens": source.get("prompt_tokens"),
                "completion_tokens": source.get("completion_tokens"),
                "total_tokens": source.get("total_tokens"),
                "cached_tokens": source.get("cached_tokens"),
                "reasoning_tokens": source.get("reasoning_tokens"),
                "llm_call_count": source.get("llm_call_count"),
            }
            if not sql_success:
                item["reason"] = source.get("error") or "sql_or_native_execution_failed"
                records.append(item)
                continue
            candidates = selected or native
            for index, result in enumerate(candidates):
                passed, reason, rows = failure_reason(gold_columns, gold_rows, result, ordered)
                item["candidate_results"].append(
                    {
                        "index": index,
                        "artifact_id": result.get("artifact_id"),
                        "sql": result.get("sql"),
                        "columns": result.get("columns") or [],
                        "row_count": len(rows),
                        "sample": sample(rows),
                        "passed": passed,
                        "reason": reason,
                    }
                )
                if passed:
                    item["execution_correct"] = True
                    item["matched_candidate_index"] = index
                    break
            if not item["execution_correct"]:
                item["reason"] = (
                    item["candidate_results"][0]["reason"]
                    if item["candidate_results"]
                    else "no_native_result"
                )
            records.append(item)
    finally:
        connection.close()

    total = len(records)
    correct = sum(bool(item["execution_correct"]) for item in records)
    sql_success = sum(bool(item["sql_success"]) for item in records)
    latencies = [float(item["latency_ms"]) for item in records if item["latency_ms"] is not None]
    tokens = [int(item["total_tokens"]) for item in records if item["total_tokens"] is not None]
    by_difficulty: dict[str, Any] = {}
    for difficulty in ("easy", "medium", "hard"):
        subset = [item for item in records if item["difficulty"] == difficulty]
        by_difficulty[difficulty] = metric(
            sum(bool(item["execution_correct"]) for item in subset), len(subset)
        )
    by_database: dict[str, Any] = {}
    for database in ("car_1", "concert_singer", "pets_1"):
        subset = [item for item in records if item["database"] == database]
        by_database[database] = metric(
            sum(bool(item["execution_correct"]) for item in subset), len(subset)
        )
    reasons = Counter(item["reason"].split(":", 1)[0] for item in records if item["reason"])
    report = {
        "benchmark_id": "spider_mix50",
        "product": "moi",
        "model": "qwen3.7-plus-2026-05-26",
        "run_id": args.run_id or args.predictions.parent.name,
        "comparison": {
            "gold_engine": "mysql_9.6",
            "prediction_engine": "matrixone",
            "prediction_result_scope": "selected_native_results_fallback_native_results",
            "rule": "Spider-style denotation equivalence; rows ordered only when Golden SQL has ORDER BY; column permutation allowed; bag semantics preserved",
        },
        "metrics": {
            "execution_accuracy": metric(correct, total),
            "sql_success_rate": metric(sql_success, total),
            "execution_accuracy_by_difficulty": by_difficulty,
            "execution_accuracy_by_database": by_database,
            "end_to_end_latency_ms": {
                "observed": len(latencies),
                "mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
                "min": round(min(latencies), 3) if latencies else None,
                "max": round(max(latencies), 3) if latencies else None,
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
            },
            "token_usage": {
                "observed": len(tokens),
                "total": sum(tokens),
                "mean_per_question": round(sum(tokens) / len(tokens), 3) if tokens else None,
            },
            "repeat_correct_rate": {
                "available": False,
                "reason": "Only one 50-question round was run; three repeats are required",
            },
        },
        "failure_reason_counts": dict(sorted(reasons.items())),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    failures = [item for item in records if not item["execution_correct"]]
    lines = [
        "# MOI Spider Mix50 第一轮评测结果",
        "",
        f"- 模型：`{report['model']}`",
        "- 比较方式：MOI 在 MatrixOne 中的原生执行结果，对比 Golden SQL 在本地 MySQL 中的执行结果。",
        f"- Execution Accuracy：**{correct}/{total} = {100 * correct / total:.1f}%**",
        f"- SQL Success Rate：**{sql_success}/{total} = {100 * sql_success / total:.1f}%**",
        f"- 端到端延迟：平均 **{report['metrics']['end_to_end_latency_ms']['mean'] / 1000:.2f}s**，P50 **{report['metrics']['end_to_end_latency_ms']['p50'] / 1000:.2f}s**，P95 **{report['metrics']['end_to_end_latency_ms']['p95'] / 1000:.2f}s**。",
        f"- Token：总计 **{sum(tokens):,}**，平均每题 **{report['metrics']['token_usage']['mean_per_question']:,.0f}**。",
        "- Repeat Correct Rate：本轮只执行 1 次，暂不计算。",
        "",
        "## 分项准确率",
        "",
        "| 维度 | 正确/总数 | 正确率 |",
        "|---|---:|---:|",
    ]
    for difficulty in ("easy", "medium", "hard"):
        value = by_difficulty[difficulty]
        lines.append(
            f"| 难度-{difficulty} | {value['numerator']}/{value['denominator']} | {value['percent']:.1f}% |"
        )
    for database in ("car_1", "concert_singer", "pets_1"):
        value = by_database[database]
        lines.append(
            f"| 数据库-{database} | {value['numerator']}/{value['denominator']} | {value['percent']:.1f}% |"
        )
    lines.extend(["", f"## 失败题目（{len(failures)} 题）", ""])
    if failures:
        lines.extend(["| 题号 | 难度 | 数据库 | 原因 |", "|---|---|---|---|"])
        for item in failures:
            lines.append(
                f"| {item['case_id']} | {item['difficulty']} | {item['database']} | {item['reason']} |"
            )
        lines.extend(["", "## 失败详情", ""])
        for item in failures:
            candidate = item["candidate_results"][0] if item["candidate_results"] else {}
            lines.extend(
                [
                    f"### {item['case_id']}",
                    "",
                    f"- 问题：{item['question']}",
                    f"- 原因：`{item['reason']}`",
                    f"- Golden SQL：`{item['gold_sql']}`",
                    f"- MOI SQL：`{item['generated_sql']}`",
                    f"- Golden 样例：`{json.dumps(item['gold_sample'], ensure_ascii=False)}`",
                    f"- MOI 样例：`{json.dumps(candidate.get('sample', []), ensure_ascii=False)}`",
                    "",
                ]
            )
    else:
        lines.append("无。")
    args.summary.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
