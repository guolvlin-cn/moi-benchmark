#!/usr/bin/env python3
"""校验Spider Mix50本地MySQL的三库表数、行数和可选CHECKSUM。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pymysql


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "database/snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict-checksum",
        action="store_true",
        help="同时要求CHECKSUM TABLE与冻结机器一致；跨MySQL版本复现通常只校验行数",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    conn = pymysql.connect(
        host=os.getenv("SPIDERMIX_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("SPIDERMIX_DB_PORT", "3306")),
        user=os.getenv("SPIDERMIX_DB_USER", "root"),
        password=os.getenv("SPIDERMIX_DB_PASSWORD", ""),
        charset="utf8mb4",
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cursor:
            for database, database_spec in snapshot["databases"].items():
                for table, table_spec in database_spec["tables"].items():
                    cursor.execute(f"SELECT COUNT(*) FROM `{database}`.`{table}`")
                    rows = int(cursor.fetchone()[0])
                    if rows != int(table_spec["rows"]):
                        raise AssertionError(f"行数不一致：{database}.{table}")
                    if args.strict_checksum:
                        cursor.execute(f"CHECKSUM TABLE `{database}`.`{table}`")
                        checksum = int(cursor.fetchone()[1])
                        if checksum != int(table_spec["mysql_checksum"]):
                            raise AssertionError(f"CHECKSUM不一致：{database}.{table}")
                    print(f"OK  {database}.{table}: {rows}行")
    finally:
        conn.close()
    print("OK  Spider Mix50 MySQL快照校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
