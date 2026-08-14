#!/usr/bin/env python3
"""Execute product and Golden SQL on the same MySQL Spider snapshot."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
from decimal import Decimal, InvalidOperation
from itertools import permutations
from pathlib import Path
from typing import Any


QUESTION_LINE = re.compile(
    r"^\s*(\d+)\.\s*\[(easy|medium|hard)\]\s*\[([^\]]+)\]\s*(.+?)\s*$"
)
ORDER_BY = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)
READ_ONLY_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
PROHIBITED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|RENAME|GRANT|REVOKE|"
    r"CALL|EXECUTE|LOAD\s+DATA|INTO\s+OUTFILE|LOCK|UNLOCK|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--product", default="wren")
    parser.add_argument("--model", default="qwen3.7-plus-2026-05-26")
    parser.add_argument("--mysql-bin", default=os.getenv("MYSQL_BIN") or shutil.which("mysql") or "mysql")
    parser.add_argument("--mysql-host", default=os.getenv("SPIDERMIX_DB_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(os.getenv("SPIDERMIX_DB_PORT", "3306")))
    parser.add_argument("--mysql-user", default=os.getenv("SPIDERMIX_DB_USER", "root"))
    parser.add_argument("--mysql-password", default=os.getenv("SPIDERMIX_DB_PASSWORD", ""))
    return parser.parse_args()


def load_questions(path: Path) -> list[dict[str, str]]:
    rows = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        match = QUESTION_LINE.match(raw)
        if not match:
            raise ValueError(f"Cannot parse question line {line_number}: {raw}")
        number, difficulty, database, question = match.groups()
        rows.append(
            {
                "case_id": f"mix50_{int(number):03d}",
                "difficulty": difficulty,
                "database": database,
                "question": question,
            }
        )
    if len(rows) != 50:
        raise ValueError(f"Expected 50 questions, got {len(rows)}")
    return rows


def load_gold(path: Path) -> list[dict[str, str]]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            sql, database = raw.rsplit("\t", 1)
            rows.append({"sql": sql.strip().rstrip(";"), "database": database.strip()})
    if len(rows) != 50:
        raise ValueError(f"Expected 50 Golden rows, got {len(rows)}")
    return rows


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    rows = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        item = json.loads(raw)
        rows[item["question_id"]] = item
    return rows


def validate_read_only(sql: str):
    normalized = sql.strip().rstrip(";").strip()
    if not normalized:
        return "no_sql"
    if not READ_ONLY_START.match(normalized):
        return "not_select_or_cte"
    if PROHIBITED.search(normalized):
        return "prohibited_statement"
    if ";" in normalized:
        return "multiple_statements"
    return None


def execute(args: argparse.Namespace, database: str, sql: str) -> tuple[list[str], list[tuple[str, ...]]]:
    statement = (
        "SET SESSION sql_mode = REPLACE(@@SESSION.sql_mode, 'ONLY_FULL_GROUP_BY', ''); "
        + sql.strip().rstrip(";")
    )
    command = [
        args.mysql_bin,
        "--protocol=TCP",
        "-h",
        args.mysql_host,
        "-P",
        str(args.mysql_port),
        f"-u{args.mysql_user}",
        "--connect-timeout=10",
        "--batch",
        "--raw",
        "--default-character-set=utf8mb4",
        f"--database={database}",
        "--execute",
        statement,
    ]
    environment = os.environ.copy()
    if args.mysql_password:
        environment["MYSQL_PWD"] = args.mysql_password
    result = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"mysql exited {result.returncode}")
    lines = result.stdout.splitlines()
    if not lines:
        return [], []
    columns = lines[0].split("\t")
    return columns, [tuple(line.split("\t")) for line in lines[1:]]


def normalized(value: str) -> tuple[str, Any]:
    if value == "NULL":
        return "null", None
    stripped = value.strip()
    try:
        return "number", Decimal(stripped).normalize()
    except (InvalidOperation, ValueError):
        return "text", stripped


def values_equal(left: str, right: str) -> bool:
    left_kind, left_value = normalized(left)
    right_kind, right_value = normalized(right)
    if left_kind != right_kind:
        return False
    if left_kind == "number":
        return math.isclose(float(left_value), float(right_value), rel_tol=1e-8, abs_tol=1e-6)
    return left_value == right_value


def rows_equal(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return len(left) == len(right) and all(values_equal(a, b) for a, b in zip(left, right))


def compare(
    gold_rows: list[tuple[str, ...]], pred_rows: list[tuple[str, ...]], ordered: bool
) -> tuple[bool, str]:
    if len(gold_rows) != len(pred_rows):
        return False, f"row_count_mismatch: gold={len(gold_rows)} pred={len(pred_rows)}"
    if not gold_rows:
        return True, ""
    if len(gold_rows[0]) != len(pred_rows[0]):
        return False, f"column_count_mismatch: gold={len(gold_rows[0])} pred={len(pred_rows[0])}"
    width = len(gold_rows[0])
    for order in permutations(range(width)):
        permuted = [tuple(row[index] for index in order) for row in pred_rows]
        if ordered and all(rows_equal(a, b) for a, b in zip(gold_rows, permuted)):
            return True, ""
        if not ordered:
            remaining = list(permuted)
            for gold_row in gold_rows:
                for index, pred_row in enumerate(remaining):
                    if rows_equal(gold_row, pred_row):
                        remaining.pop(index)
                        break
                else:
                    break
            else:
                return True, ""
    return False, "ordered_value_mismatch" if ordered else "unordered_value_mismatch"


def metric(value: int, total: int) -> dict[str, Any]:
    return {"numerator": value, "denominator": total, "percent": round(value / total * 100, 2)}


def main() -> int:
    args = parse_args()
    questions = load_questions(args.questions)
    gold = load_gold(args.gold)
    predictions = load_predictions(args.predictions)
    records = []
    for question, golden in zip(questions, gold):
        case_id = question["case_id"]
        source = predictions[case_id]
        pred_sql = str(source.get("generated_sql") or "")
        reason = validate_read_only(pred_sql)
        item = {
            **question,
            "gold_sql": golden["sql"],
            "generated_sql": pred_sql,
            "sql_success": False,
            "execution_correct": False,
            "reason": reason or "",
        }
        gold_columns, gold_rows = execute(args, golden["database"], golden["sql"])
        item["gold_row_count"] = len(gold_rows)
        if reason:
            records.append(item)
            continue
        try:
            pred_columns, pred_rows = execute(args, golden["database"], pred_sql)
            item["sql_success"] = True
            item["pred_row_count"] = len(pred_rows)
            if len(gold_columns) != len(pred_columns):
                item["reason"] = (
                    f"column_count_mismatch: gold={len(gold_columns)} pred={len(pred_columns)}"
                )
            else:
                passed, compare_reason = compare(
                    gold_rows, pred_rows, bool(ORDER_BY.search(golden["sql"]))
                )
                item["execution_correct"] = passed
                item["reason"] = compare_reason
        except Exception as exc:
            item["reason"] = f"execution_error: {exc}"
        records.append(item)

    total = len(records)
    correct = sum(bool(item["execution_correct"]) for item in records)
    successful = sum(bool(item["sql_success"]) for item in records)
    report = {
        "benchmark_id": "spider_mix50",
        "product": args.product,
        "model": args.model,
        "run_id": args.run_id or args.predictions.parent.name,
        "comparison": f"Golden and {args.product} SQL executed on the same MySQL snapshot",
        "metrics": {
            "execution_accuracy": metric(correct, total),
            "sql_success_rate": metric(successful, total),
        },
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
