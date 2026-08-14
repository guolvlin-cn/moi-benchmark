#!/usr/bin/env python3
"""在统一 MySQL 8 快照中比较候选 SQL 与 Golden SQL 的执行结果。"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymysql
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = PROJECT_ROOT / "benchmark/cases/cases_enron_50.yaml"
CASE_PREFIX = re.compile(r"^(e\d{2}|m\d{2}|h\d{2})")
BLOCK_MARKER = re.compile(r"^--\s+((?:e|m|h)\d{2}(?:_[A-Za-z0-9_]+)?)\b")
READ_ONLY_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
PROHIBITED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|RENAME|GRANT|REVOKE|"
    r"REPLACE\s+INTO|CALL|EXECUTE|LOAD\s+DATA|INTO\s+OUTFILE|INTO\s+DUMPFILE|LOCK|UNLOCK|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行 Enron Golden SQL 与候选 SQL 对比")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--product", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = list(data.get("cases") or [])
    if len(cases) != 50:
        raise ValueError(f"cases 文件必须包含 50 题，实际为 {len(cases)}")
    return cases


def short_id(value: str) -> str:
    match = CASE_PREFIX.match(value.strip())
    return match.group(1) if match else value.strip()


def load_jsonl(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        record = json.loads(raw)
        case_id = record.get("question_id") or record.get("case_id") or record.get("id")
        sql = record.get("generated_sql") or record.get("sql") or ""
        if not case_id:
            raise ValueError(f"JSONL 第 {line_number} 行缺少题号")
        result[short_id(str(case_id))] = str(sql).strip()
    return result


def load_block_sql(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current = ""
    sql_lines: list[str] = []

    def flush() -> None:
        if current:
            result[short_id(current)] = "\n".join(sql_lines).strip().rstrip(";").strip()

    for raw in text.splitlines():
        marker = BLOCK_MARKER.match(raw.strip())
        if marker:
            flush()
            current = marker.group(1)
            sql_lines = []
            continue
        if current and raw.strip() and not raw.lstrip().startswith("--"):
            sql_lines.append(raw)
    flush()
    return result


def load_line_sql(text: str, case_ids: list[str]) -> dict[str, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != len(case_ids):
        raise ValueError(f"逐行 SQL 文件应为 {len(case_ids)} 行，实际为 {len(lines)} 行")
    result: dict[str, str] = {}
    for case_id, line in zip(case_ids, lines):
        result[case_id] = "" if line.startswith("--") else line.rstrip(";").strip()
    return result


def load_predictions(path: Path, case_ids: list[str]) -> dict[str, str]:
    if path.suffix.lower() == ".jsonl":
        return load_jsonl(path)
    text = path.read_text(encoding="utf-8")
    marker_count = sum(1 for line in text.splitlines() if BLOCK_MARKER.match(line.strip()))
    return load_block_sql(text) if marker_count >= 10 else load_line_sql(text, case_ids)


def connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.getenv("ENRON_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("ENRON_DB_PORT", "3306")),
        user=os.getenv("ENRON_DB_USER", "root"),
        password=os.getenv("ENRON_DB_PASSWORD", ""),
        database=os.getenv("ENRON_DB_NAME", "enron_eval"),
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=int(os.getenv("ENRON_DB_READ_TIMEOUT", "120")),
        write_timeout=120,
    )


def validate_read_only(sql: str) -> str | None:
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


def execute(conn: pymysql.Connection, sql: str) -> tuple[list[str], list[tuple], float]:
    started = time.perf_counter()
    with conn.cursor() as cursor:
        cursor.execute(sql)
        rows = list(cursor.fetchall())
        columns = [item[0] for item in (cursor.description or [])]
    return columns, rows, round((time.perf_counter() - started) * 1000, 3)


def values_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float, Decimal)) and isinstance(right, (int, float, Decimal)):
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(left, bytes):
        left = left.decode("utf-8", errors="replace")
    if isinstance(right, bytes):
        right = right.decode("utf-8", errors="replace")
    return str(left).strip() == str(right).strip()


def rows_equal(left: tuple, right: tuple) -> bool:
    return len(left) == len(right) and all(values_equal(a, b) for a, b in zip(left, right))


def compare_rows(gold: list[tuple], pred: list[tuple], ordered: bool) -> tuple[bool, str]:
    if len(gold) != len(pred):
        return False, f"row_count_mismatch: gold={len(gold)} pred={len(pred)}"
    if gold and pred and len(gold[0]) != len(pred[0]):
        return False, f"column_count_mismatch: gold={len(gold[0])} pred={len(pred[0])}"
    if ordered:
        for index, (gold_row, pred_row) in enumerate(zip(gold, pred)):
            if not rows_equal(gold_row, pred_row):
                return False, f"ordered_value_mismatch_at_row_{index}"
        return True, ""

    used = [False] * len(pred)
    for gold_row in gold:
        for index, pred_row in enumerate(pred):
            if not used[index] and rows_equal(gold_row, pred_row):
                used[index] = True
                break
        else:
            return False, "unordered_value_mismatch"
    return True, ""


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def sample(rows: list[tuple], limit: int = 5) -> list[list[Any]]:
    return [[json_value(value) for value in row] for row in rows[:limit]]


def main() -> int:
    args = parse_args()
    cases = load_cases(args.cases)
    case_ids = [short_id(str(case["case_id"])) for case in cases]
    predictions = load_predictions(args.predictions, case_ids)
    conn = connection()
    records: list[dict[str, Any]] = []
    try:
        for case in cases:
            full_id = str(case["case_id"])
            case_id = short_id(full_id)
            gold_sql = str(case["gold_sql"]).strip().rstrip(";").strip()
            pred_sql = predictions.get(case_id, "")
            readonly_error = validate_read_only(pred_sql)
            record: dict[str, Any] = {
                "case_id": full_id,
                "difficulty": case["difficulty"],
                "question": case["question"],
                "gold_sql": gold_sql,
                "pred_sql": pred_sql,
                "passed": False,
                "reason": readonly_error or "",
            }
            if readonly_error:
                records.append(record)
                continue
            try:
                gold_columns, gold_rows, gold_ms = execute(conn, gold_sql)
                pred_columns, pred_rows, pred_ms = execute(conn, pred_sql)
                ordered = bool(re.search(r"\bORDER\s+BY\b", gold_sql, re.IGNORECASE))
                passed, reason = compare_rows(gold_rows, pred_rows, ordered)
                record.update(
                    {
                        "passed": passed,
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
                record["reason"] = f"execution_error: {exc}"
                try:
                    conn.ping(reconnect=True)
                except Exception:
                    conn.close()
                    conn = connection()
            records.append(record)
    finally:
        conn.close()

    passed = sum(1 for record in records if record["passed"])
    by_difficulty = {}
    for difficulty in ("easy", "medium", "hard"):
        subset = [record for record in records if record["difficulty"] == difficulty]
        by_difficulty[difficulty] = {
            "total": len(subset),
            "passed": sum(1 for record in subset if record["passed"]),
        }
    report = {
        "benchmark_id": "enron_golden50_v1",
        "product": args.product,
        "run_id": args.run_id or None,
        "database": os.getenv("ENRON_DB_NAME", "enron_eval"),
        "total": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "pass_rate": round(passed / len(records) * 100, 2),
        "by_difficulty": by_difficulty,
        "predictions_file": str(args.predictions),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.product}: {passed}/{len(records)} ({report['pass_rate']}%)")
    print(f"报告：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
