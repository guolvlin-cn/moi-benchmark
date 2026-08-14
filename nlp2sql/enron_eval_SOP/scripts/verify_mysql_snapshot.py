#!/usr/bin/env python3
"""只读验证MySQL中的enron_eval是否与六个CSV完全一致。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pymysql

from verify_csv_files import canonical_rows_fingerprint


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/manifest.json"
DEFAULT_FINGERPRINTS = ROOT / "data/snapshot/expected_fingerprints.json"
SAFE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证Enron MySQL数据快照")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fingerprints", type=Path, default=DEFAULT_FINGERPRINTS)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def database_name() -> str:
    value = os.getenv("ENRON_DB_NAME", "enron_eval")
    if not SAFE_NAME.fullmatch(value):
        raise ValueError("ENRON_DB_NAME只能包含字母、数字和下划线")
    return value


def connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.getenv("ENRON_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("ENRON_DB_PORT", "3306")),
        user=os.getenv("ENRON_DB_USER", "root"),
        password=os.getenv("ENRON_DB_PASSWORD", ""),
        database=database_name(),
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=300,
        write_timeout=300,
    )


def schema_digest(columns: list[dict[str, Any]]) -> str:
    encoded = json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify(
    manifest_path: Path, fingerprints_path: Path = DEFAULT_FINGERPRINTS
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_fingerprints = json.loads(fingerprints_path.read_text(encoding="utf-8"))
    db = database_name()
    conn = connection()
    table_results: dict[str, Any] = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME",
                (db,),
            )
            actual_tables = [row[0] for row in cursor.fetchall()]
            expected_tables = sorted(spec["table"] for spec in manifest["files"].values())
            if actual_tables != expected_tables:
                raise AssertionError(f"表集合不一致：实际={actual_tables}，预期={expected_tables}")

            for filename, spec in manifest["files"].items():
                table = spec["table"]
                columns = list(spec["columns"])
                quoted_columns = ", ".join(f"`{column}`" for column in columns)
                cursor.execute(f"SELECT {quoted_columns} FROM `{table}`")
                rows = [list(row) for row in cursor.fetchall()]
                fingerprint = canonical_rows_fingerprint(
                    rows, columns, set(spec.get("integer_columns") or [])
                )
                if len(rows) != spec["rows"]:
                    raise AssertionError(f"{table}行数不一致")
                if fingerprint != spec["canonical_row_fingerprint_sha256"]:
                    raise AssertionError(f"{table}内容指纹不一致")

                null_counts: dict[str, int] = {}
                for column in columns:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` IS NULL")
                    null_counts[column] = int(cursor.fetchone()[0])
                if null_counts != spec["null_counts"]:
                    raise AssertionError(f"{table}的NULL统计不一致")

                cursor.execute(
                    "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, ORDINAL_POSITION, COLUMN_COMMENT "
                    "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "ORDER BY ORDINAL_POSITION",
                    (db, table),
                )
                schema_columns = [
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2],
                        "position": int(row[3]),
                        "comment": row[4],
                    }
                    for row in cursor.fetchall()
                ]
                if [item["name"] for item in schema_columns] != columns:
                    raise AssertionError(f"{table}字段名称或顺序不一致")
                if any(not item["comment"] for item in schema_columns):
                    raise AssertionError(f"{table}存在缺失字段注释")

                digest = schema_digest(schema_columns)
                expected_table = expected_fingerprints["tables"][table]
                if digest != expected_table["schema_sha256"]:
                    raise AssertionError(f"{table}字段类型、顺序、可空性或注释不一致")
                table_results[table] = {
                    "rows": len(rows),
                    "null_counts": null_counts,
                    "canonical_row_fingerprint_sha256": fingerprint,
                    "schema_sha256": digest,
                    "schema": schema_columns,
                }
    finally:
        conn.close()
    return {
        "status": "ok",
        "dataset_id": manifest["dataset_id"],
        "database": db,
        "engine": "mysql",
        "tables": table_results,
    }


def main() -> int:
    args = parse_args()
    report = verify(args.manifest, args.fingerprints)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"报告：{args.output}")
    for table, item in report["tables"].items():
        print(f"OK  {table}: {item['rows']}行，NULL、Schema和内容指纹一致")
    print("OK  MySQL数据库可用于enron_eval_v1正式评测")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
