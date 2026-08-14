#!/usr/bin/env python3
"""从Git内13个CSV安全建立Spider Mix50的三个MySQL数据库。"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

import pymysql


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "database/schema/mysql_schema.sql"
SNAPSHOT = ROOT / "database/snapshot.json"
CSV_ROOT = ROOT / "database/csv"
DATABASES = ("pets_1", "concert_singer", "car_1")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="建立Spider Mix50三库MySQL快照")
    parser.add_argument("--rebuild", action="store_true", help="删除三个同名数据库后重建")
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser.parse_args()


def connection(database: str | None = None, *, autocommit: bool = True):
    return pymysql.connect(
        host=os.getenv("SPIDERMIX_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("SPIDERMIX_DB_PORT", "3306")),
        user=os.getenv("SPIDERMIX_DB_USER", "root"),
        password=os.getenv("SPIDERMIX_DB_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        autocommit=autocommit,
        connect_timeout=10,
        read_timeout=120,
        write_timeout=120,
    )


def statements(path: Path) -> list[str]:
    text = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    return [item.strip() for item in text.split(";") if item.strip()]


def prepare(rebuild: bool) -> None:
    conn = connection()
    try:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(DATABASES))
            cursor.execute(
                f"SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN ({placeholders})",
                DATABASES,
            )
            existing = sorted(row[0] for row in cursor.fetchall())
            if existing and not rebuild:
                raise RuntimeError(
                    f"数据库已存在：{existing}。为保护数据已停止；校验现有快照，或明确使用--rebuild。"
                )
            if rebuild:
                for database in DATABASES:
                    cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            for statement in statements(SCHEMA):
                cursor.execute(statement)
    finally:
        conn.close()


def clean(value: str) -> Any:
    if value in {"", "NULL", "\\N"}:
        return None
    return value


def import_table(database: str, table: str, path: Path, batch_size: int) -> int:
    conn = connection(database, autocommit=False)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle, conn.cursor() as cursor:
            reader = csv.reader(handle)
            columns = next(reader)
            quoted = ", ".join(f"`{column}`" for column in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"INSERT INTO `{table}` ({quoted}) VALUES ({placeholders})"
            batch: list[tuple[Any, ...]] = []
            count = 0
            for row in reader:
                batch.append(tuple(clean(value) for value in row))
                if len(batch) >= batch_size:
                    cursor.executemany(sql, batch)
                    count += len(batch)
                    batch.clear()
            if batch:
                cursor.executemany(sql, batch)
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
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    prepare(args.rebuild)
    for database, database_spec in snapshot["databases"].items():
        for table, table_spec in database_spec["tables"].items():
            count = import_table(database, table, CSV_ROOT / database / f"{table}.csv", args.batch_size)
            if count != int(table_spec["rows"]):
                raise AssertionError(f"导入行数不一致：{database}.{table}")
            print(f"IMPORTED  {database}.{table}: {count}行")
    print("OK  Spider Mix50三库13表导入完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
