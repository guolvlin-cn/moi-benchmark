#!/usr/bin/env python3
"""Merge per-database Chat2DB Spider runs into one validated Mix50 run."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASES = ROOT / "benchmark/questions/case_databases.tsv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-run", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--databases", type=Path, default=DEFAULT_DATABASES)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_database_map(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case_id, database = line.split("\t", 1)
        rows[case_id.strip()] = database.strip()
    return rows


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def main() -> int:
    args = parse_args()
    expected = load_database_map(args.databases)
    if len(expected) != 50:
        raise ValueError(f"Expected 50 database mappings, got {len(expected)}")

    records: dict[str, dict[str, Any]] = {}
    source_runs: list[str] = []
    for run_dir in args.input_run:
        run_info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        source_runs.append(str(run_info.get("run_id") or run_dir.name))
        for record in load_jsonl(run_dir / "predictions.jsonl"):
            case_id = str(record["question_id"])
            if case_id in records:
                raise ValueError(f"Duplicate question: {case_id}")
            records[case_id] = record

    missing = sorted(set(expected) - set(records))
    unexpected = sorted(set(records) - set(expected))
    if missing or unexpected:
        raise ValueError(f"Missing={missing}; unexpected={unexpected}")

    for case_id, record in records.items():
        actual_database = record.get("metadata", {}).get("database")
        if actual_database != expected[case_id]:
            raise ValueError(
                f"{case_id}: expected database {expected[case_id]}, got {actual_database}"
            )

    ordered = [records[f"mix50_{index:03d}"] for index in range(1, 51)]
    models = sorted({str(item.get("metadata", {}).get("model")) for item in ordered})
    if len(models) != 1:
        raise ValueError(f"Expected one model, got {models}")

    latencies = [float(item["latency_ms"]) for item in ordered]
    token_total = sum(int(item.get("total_tokens") or 0) for item in ordered)
    sql_count = sum(bool(str(item.get("generated_sql") or "").strip()) for item in ordered)
    status_counts: dict[str, int] = {}
    for item in ordered:
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions = "".join(
        json.dumps(item, ensure_ascii=False) + "\n" for item in ordered
    )
    (args.output_dir / "predictions.jsonl").write_text(predictions, encoding="utf-8")

    run_info = {
        "run_id": args.output_dir.name,
        "product": "chat2db",
        "benchmark_id": "spider_mix50",
        "database_context": "per_question_fixed_database",
        "databases": sorted(set(expected.values())),
        "model": models[0],
        "repeats": 1,
        "collection_mode": "merged_validated_per_database_runs",
        "source_runs": source_runs,
        "completed_at": datetime.now().astimezone().isoformat(),
        "record_count": len(ordered),
        "generated_sql_count": sql_count,
        "status_counts": status_counts,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 1),
            "p95": round(percentile(latencies, 0.95), 1),
        },
        "token_total": token_total,
    }
    (args.output_dir / "run.json").write_text(
        json.dumps(run_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(run_info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
