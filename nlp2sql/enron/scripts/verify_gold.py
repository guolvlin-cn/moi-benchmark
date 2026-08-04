#!/usr/bin/env python3
"""Verify all gold SQL in cases_enron_50.yaml against enron.sqlite."""
import sqlite3
import sys
import yaml
from pathlib import Path

CASES_PATH = Path(__file__).resolve().parent.parent / "cases" / "cases_enron_50.yaml"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "enron.sqlite"


def main():
    with open(CASES_PATH) as f:
        spec = yaml.safe_load(f)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cases = spec["cases"]
    passed = 0
    failed = 0
    failures = []

    for case in cases:
        cid = case["case_id"]
        sql = case["gold_sql"].strip()
        question = case["question"]
        diff = case["difficulty"]

        try:
            cur.execute(sql)
            rows = cur.fetchall()
            row_count = len(rows)
            col_count = len(cur.description) if cur.description else 0
            print(f"  ✓ {cid:<35} [{diff:<6}] {col_count}列 {row_count:>5}行  {question[:50]}")
            passed += 1
        except Exception as e:
            err_msg = str(e)[:80]
            print(f"  ✗ {cid:<35} [{diff:<6}] ERROR: {err_msg}")
            failed += 1
            failures.append((cid, diff, question, sql, err_msg))

    conn.close()

    print(f"\n{'='*60}")
    print(f"结果: {passed}/{passed+failed} 通过, {failed} 失败")

    if failures:
        print(f"\n失败详情:")
        for cid, diff, q, sql, err in failures:
            print(f"\n  [{cid}] [{diff}] {q}")
            print(f"  SQL: {sql[:100]}")
            print(f"  错误: {err}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
