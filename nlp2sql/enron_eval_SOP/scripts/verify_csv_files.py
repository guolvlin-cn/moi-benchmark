#!/usr/bin/env python3
"""验证Git内六个Enron CSV的文件哈希、结构和规范化内容指纹。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/manifest.json"
DEFAULT_CSV_DIR = ROOT / "data/raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证Enron六个CSV")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--json", action="store_true", help="以JSON输出验证结果")
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_value(column: str, value: Any, integer_columns: set[str]) -> Any:
    if value is None or value == "\\N":
        return None
    if column in integer_columns:
        return int(value)
    return str(value)


def canonical_rows_fingerprint(rows: list[list[Any]], columns: list[str], integer_columns: set[str]) -> str:
    row_digests: list[bytes] = []
    for row in rows:
        normalized = [
            canonical_value(column, row[index] if index < len(row) else None, integer_columns)
            for index, column in enumerate(columns)
        ]
        encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        row_digests.append(hashlib.sha256(encoded).digest())
    return hashlib.sha256(b"".join(sorted(row_digests))).hexdigest()


def inspect_csv(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    expected_columns = list(spec["columns"])
    integer_columns = set(spec.get("integer_columns") or [])
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        columns = next(reader)
        rows = list(reader)
    malformed = sum(len(row) != len(columns) for row in rows)
    null_counts = {column: 0 for column in columns}
    for row in rows:
        for index, column in enumerate(columns):
            value = row[index] if index < len(row) else None
            if value is None or value == "\\N":
                null_counts[column] += 1
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "rows": len(rows),
        "columns": columns,
        "malformed_rows": malformed,
        "null_counts": null_counts,
        "canonical_row_fingerprint_sha256": canonical_rows_fingerprint(
            rows, expected_columns, integer_columns
        ),
    }


def verify(manifest_path: Path, csv_dir: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_names = set(manifest["files"])
    actual_names = {path.name for path in csv_dir.glob("*.csv")}
    if actual_names != expected_names:
        raise AssertionError(
            f"CSV文件集合不一致：缺少={sorted(expected_names-actual_names)}，多出={sorted(actual_names-expected_names)}"
        )
    results: list[dict[str, Any]] = []
    for filename, spec in manifest["files"].items():
        result = inspect_csv(csv_dir / filename, spec)
        for key in (
            "bytes",
            "sha256",
            "rows",
            "columns",
            "null_counts",
            "canonical_row_fingerprint_sha256",
        ):
            if result[key] != spec[key]:
                raise AssertionError(f"{filename}的{key}不一致")
        if result["malformed_rows"]:
            raise AssertionError(f"{filename}存在{result['malformed_rows']}条列数异常记录")
        results.append(result)
    return results


def main() -> int:
    args = parse_args()
    results = verify(args.manifest, args.csv_dir)
    if args.json:
        print(json.dumps({"status": "ok", "files": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(f"OK  {result['file']}: {result['rows']}行，SHA256和内容指纹一致")
        print("OK  六个CSV可用于enron_eval_v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
