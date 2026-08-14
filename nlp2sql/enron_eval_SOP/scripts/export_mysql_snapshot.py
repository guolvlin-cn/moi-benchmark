#!/usr/bin/env python3
"""维护者工具：从已验证的MySQL评测库导出六个规范CSV。"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import pymysql


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/raw"
TABLES = {
    "enron_email": ["id", "people", "mailbox", "nnn"],
    "enron_emailinfo": ["id", "messageid", "date", "subject", "from", "to", "xfrom", "xto", "body"],
    "enron_emailorig": ["id", "nth", "subject", "from", "to", "xfrom", "xto"],
    "enron_emailto": ["id", "nthto", "to"],
    "enron_emailxto": ["id", "nthxto", "xto"],
    "enron_source": ["id", "source_file_id", "source_name", "xfilename", "xfolder", "xorigin"],
}
ORDER_KEYS = {
    "enron_email": ["id"],
    "enron_emailinfo": ["id"],
    "enron_emailorig": ["id", "nth"],
    "enron_emailto": ["id", "nthto"],
    "enron_emailxto": ["id", "nthxto"],
    "enron_source": ["id"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从MySQL导出enron_eval_v1规范CSV")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def connection() -> pymysql.Connection:
    database = os.getenv("ENRON_DB_NAME", "enron_eval")
    if database != "enron_eval":
        raise ValueError("权威快照导出只允许ENRON_DB_NAME=enron_eval")
    return pymysql.connect(
        host=os.getenv("ENRON_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("ENRON_DB_PORT", "3306")),
        user=os.getenv("ENRON_DB_USER", "root"),
        password=os.getenv("ENRON_DB_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=300,
        write_timeout=300,
    )


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    conn = connection()
    try:
        with conn.cursor() as cursor:
            for table, columns in TABLES.items():
                quoted = ", ".join(f"`{column}`" for column in columns)
                order = ", ".join(f"`{column}`" for column in ORDER_KEYS[table])
                cursor.execute(f"SELECT {quoted} FROM `{table}` ORDER BY {order}")
                path = args.output_dir / f"{table}.csv"
                count = 0
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle, lineterminator="\n")
                    writer.writerow(columns)
                    while True:
                        rows = cursor.fetchmany(2000)
                        if not rows:
                            break
                        writer.writerows(
                            [["\\N" if value is None else value for value in row] for row in rows]
                        )
                        count += len(rows)
                print(f"EXPORTED  {table}: {count}行 -> {path}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
