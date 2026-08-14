#!/usr/bin/env python3
"""校验Spider Mix50三库CSV的行数与SHA256。"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "database/snapshot.json"
CSV_ROOT = ROOT / "database/csv"


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    checked = 0
    for database, database_spec in snapshot["databases"].items():
        for table, table_spec in database_spec["tables"].items():
            path = CSV_ROOT / database / f"{table}.csv"
            if not path.exists():
                raise FileNotFoundError(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != table_spec["csv_sha256"]:
                raise AssertionError(f"CSV哈希不一致：{database}.{table}")
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = sum(1 for _ in csv.reader(handle)) - 1
            if rows != int(table_spec["rows"]):
                raise AssertionError(
                    f"CSV行数不一致：{database}.{table} expected={table_spec['rows']} actual={rows}"
                )
            checked += 1
            print(f"OK  {database}.{table}: {rows}行")
    if checked != 13:
        raise AssertionError(f"预期13张表，实际{checked}张")
    print("OK  Spider Mix50的13个CSV均与冻结快照一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
