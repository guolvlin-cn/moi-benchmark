#!/usr/bin/env python3
"""维护者工具：根据规范CSV重建manifest中的文件指纹。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from verify_csv_files import inspect_csv


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/manifest.json"
DEFAULT_CSV_DIR = ROOT / "data/raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重建Enron数据manifest")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    for filename, old_spec in manifest["files"].items():
        result = inspect_csv(args.csv_dir / filename, old_spec)
        if result["malformed_rows"]:
            raise AssertionError(f"{filename}存在列数异常记录")
        manifest["files"][filename] = {
            "table": old_spec["table"],
            "bytes": result["bytes"],
            "sha256": result["sha256"],
            "rows": result["rows"],
            "columns": result["columns"],
            "integer_columns": old_spec.get("integer_columns") or [],
            "null_counts": result["null_counts"],
            "canonical_row_fingerprint_sha256": result[
                "canonical_row_fingerprint_sha256"
            ],
        }
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"UPDATED  {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
