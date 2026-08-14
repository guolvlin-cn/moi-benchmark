#!/usr/bin/env python3
"""从Git内六个CSV安全建立enron_eval MySQL数据库。"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql

from verify_csv_files import verify as verify_csv
from verify_mysql_snapshot import database_name, verify as verify_mysql


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/manifest.json"
DEFAULT_CSV_DIR = ROOT / "data/raw"
DEFAULT_SCHEMA = ROOT / "database/schema/enron_eval_schema.sql"
DEFAULT_REPORT = ROOT / "runs/setup/mysql_import_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="建立并导入Enron MySQL数据库")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="明确删除同名数据库后重建；未指定时已有数据库会被保护",
    )
    return parser.parse_args()


def server_connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.getenv("ENRON_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("ENRON_DB_PORT", "3306")),
        user=os.getenv("ENRON_DB_USER", "root"),
        password=os.getenv("ENRON_DB_PASSWORD", ""),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=10,
        read_timeout=300,
        write_timeout=300,
    )


def data_connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.getenv("ENRON_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("ENRON_DB_PORT", "3306")),
        user=os.getenv("ENRON_DB_USER", "root"),
        password=os.getenv("ENRON_DB_PASSWORD", ""),
        database=database_name(),
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        read_timeout=300,
        write_timeout=300,
    )


def sql_statements(path: Path) -> list[str]:
    without_comments = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--")
    )
    return [statement.strip() for statement in without_comments.split(";") if statement.strip()]


def prepare_database(schema_path: Path, rebuild: bool) -> None:
    db = database_name()
    conn = server_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (db,))
            exists = cursor.fetchone() is not None
            if exists and not rebuild:
                raise RuntimeError(
                    "数据库enron_eval已存在。为保护已有数据已停止；先运行verify_mysql_snapshot.py，"
                    "或明确使用--rebuild删除并重建。"
                )
            if exists:
                cursor.execute(f"DROP DATABASE `{db}`")
            for statement in sql_statements(schema_path):
                statement = statement.replace("`enron_eval`", f"`{db}`")
                cursor.execute(statement)
    finally:
        conn.close()


def clean_value(column: str, value: str | None, integer_columns: set[str]) -> Any:
    if value is None or value == "\\N":
        return None
    if column in integer_columns:
        return int(value)
    return value


def import_table(path: Path, spec: dict[str, Any], batch_size: int) -> int:
    table = spec["table"]
    expected_columns = list(spec["columns"])
    integer_columns = set(spec.get("integer_columns") or [])
    conn = data_connection()
    try:
        with conn.cursor() as cursor, path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            columns = next(reader)
            if columns != expected_columns:
                raise AssertionError(f"{path.name}表头不一致")
            quoted_columns = ", ".join(f"`{column}`" for column in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            statement = f"INSERT INTO `{table}` ({quoted_columns}) VALUES ({placeholders})"
            batch: list[tuple[Any, ...]] = []
            count = 0
            for row in reader:
                batch.append(
                    tuple(
                        clean_value(column, row[index], integer_columns)
                        for index, column in enumerate(columns)
                    )
                )
                if len(batch) >= batch_size:
                    cursor.executemany(statement, batch)
                    count += len(batch)
                    batch.clear()
            if batch:
                cursor.executemany(statement, batch)
                count += len(batch)
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("batch-size必须大于0")
    verify_csv(args.manifest, args.csv_dir)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    prepare_database(args.schema, args.rebuild)
    imported: dict[str, int] = {}
    for filename, spec in manifest["files"].items():
        count = import_table(args.csv_dir / filename, spec, args.batch_size)
        if count != spec["rows"]:
            raise AssertionError(f"{spec['table']}导入行数不一致")
        imported[spec["table"]] = count
        print(f"IMPORTED  {spec['table']}: {count}行")

    verification = verify_mysql(args.manifest)
    report = {
        "status": "ok",
        "dataset_id": manifest["dataset_id"],
        "database": database_name(),
        "completed_at": datetime.now().astimezone().isoformat(),
        "imported_rows": imported,
        "verification": verification,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK  enron_eval_v1导入并通过完整校验；报告：{args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
