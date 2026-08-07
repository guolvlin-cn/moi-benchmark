#!/usr/bin/env python3
"""安全导入 Enron 六张 CSV 到 MySQL 8 兼容数据库。"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = PROJECT_ROOT / "database/schema/enron_eval_schema.sql"
DEFAULT_CSV_DIR = PROJECT_ROOT / "data/private"
TABLES = [
    "enron_email",
    "enron_emailinfo",
    "enron_emailorig",
    "enron_emailto",
    "enron_emailxto",
    "enron_source",
]
EXPECTED_ROWS = {
    "enron_email": 10401,
    "enron_emailinfo": 10401,
    "enron_emailorig": 1161,
    "enron_emailto": 71670,
    "enron_emailxto": 72349,
    "enron_source": 10401,
}
INT_COLUMNS = {"id", "nnn", "nth", "nthto", "nthxto"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入 Enron CSV 到 MySQL")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser.parse_args()


def connection_config(database: str | None = "enron_eval") -> dict:
    config = {
        "host": os.getenv("ENRON_DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("ENRON_DB_PORT", "3306")),
        "user": os.getenv("ENRON_DB_USER", "root"),
        "password": os.getenv("ENRON_DB_PASSWORD", ""),
        "charset": "utf8mb4",
        "autocommit": False,
        "connect_timeout": 10,
        "read_timeout": 300,
        "write_timeout": 300,
    }
    if database:
        config["database"] = database
    return config


def resolve_csv(csv_dir: Path, table: str) -> Path:
    direct = csv_dir / f"{table}.csv"
    if direct.exists():
        return direct
    matches = sorted(csv_dir.glob(f"{table}__*.csv"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"无法唯一定位 {table}.csv：{csv_dir}")


def execute_schema(path: Path) -> None:
    connection = pymysql.connect(**connection_config(database=None))
    connection.autocommit(True)
    try:
        with connection.cursor() as cursor:
            for statement in path.read_text(encoding="utf-8").split(";"):
                sql = statement.strip()
                if sql and not sql.startswith("--"):
                    cursor.execute(sql)
    finally:
        connection.close()


def clean_value(column: str, value: str | None):
    if value in {None, "", "\\N"}:
        return None
    if column in INT_COLUMNS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return value


def import_table(csv_path: Path, table: str, batch_size: int) -> int:
    connection = pymysql.connect(**connection_config())
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE TABLE `{table}`")
            with csv_path.open(newline="", encoding="utf-8", errors="replace") as handle:
                reader = csv.reader(handle)
                header = next(reader)
                columns = ", ".join(f"`{column}`" for column in header)
                placeholders = ", ".join(["%s"] * len(header))
                statement = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"
                batch: list[tuple] = []
                count = 0
                for row in reader:
                    values = tuple(
                        clean_value(column, row[index] if index < len(row) else None)
                        for index, column in enumerate(header)
                    )
                    batch.append(values)
                    if len(batch) >= batch_size:
                        cursor.executemany(statement, batch)
                        count += len(batch)
                        batch.clear()
                if batch:
                    cursor.executemany(statement, batch)
                    count += len(batch)
        connection.commit()
        return count
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    args = parse_args()
    if not os.getenv("ENRON_DB_PASSWORD"):
        print("提示：未设置 ENRON_DB_PASSWORD，将使用空密码连接。")
    execute_schema(args.schema)
    for table in TABLES:
        csv_path = resolve_csv(args.csv_dir, table)
        count = import_table(csv_path, table, args.batch_size)
        expected = EXPECTED_ROWS[table]
        status = "正确" if count == expected else f"异常，预期 {expected}"
        print(f"{table}: {count} 行（{status}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
