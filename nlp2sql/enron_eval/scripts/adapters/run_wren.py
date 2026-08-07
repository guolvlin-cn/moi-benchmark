#!/usr/bin/env python3
"""Run the Enron 50-question set against the local Wren NL2SQL API."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS = PROJECT_ROOT / "benchmark/questions/user/questions_enron_50_user_mix.txt"
DEFAULT_OUTPUT = PROJECT_ROOT / "products/wren/results/local_run/predictions.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--url", default="http://localhost:3000/api/v1/generate_sql"
    )
    parser.add_argument("--timeout", type=float, default=300)
    return parser.parse_args()


def load_questions(path: Path) -> list[tuple[str, str]]:
    questions: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"Invalid question line {line_number}: {raw_line!r}")
        questions.append((parts[0].strip(), parts[1].strip()))
    return questions


def load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def ask_wren(url: str, question: str, timeout: float) -> dict:
    payload = json.dumps(
        {
            "question": question,
            "language": "Simplified Chinese",
            "returnSqlDialect": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        status = error.code
        raw_body = error.read().decode("utf-8")
        try:
            response_body = json.loads(raw_body)
        except json.JSONDecodeError:
            response_body = {"error": raw_body}
    except (TimeoutError, urllib.error.URLError) as error:
        status = 0
        response_body = {"error": str(error)}

    return {
        "http_status": status,
        "latency_seconds": round(time.monotonic() - started, 3),
        "sql": response_body.get("sql"),
        "thread_id": response_body.get("threadId"),
        "response_id": response_body.get("id"),
        "error_code": response_body.get("code"),
        "error": response_body.get("error"),
    }


def write_csv(path: Path, records: list[dict]) -> None:
    fieldnames = [
        "index",
        "case_id",
        "question",
        "http_status",
        "latency_seconds",
        "sql",
        "thread_id",
        "response_id",
        "error_code",
        "error",
        "completed_at",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def write_summary(path: Path, records: list[dict], elapsed: float) -> None:
    latencies = [
        record["latency_seconds"]
        for record in records
        if record.get("latency_seconds") is not None
    ]
    successful = [record for record in records if record.get("sql")]
    summary = {
        "question_count": len(records),
        "sql_generated": len(successful),
        "failed": len(records) - len(successful),
        "total_run_seconds": round(elapsed, 3),
        "total_generation_seconds": round(sum(latencies), 3),
        "average_generation_seconds": (
            round(sum(latencies) / len(latencies), 3) if latencies else None
        ),
        "min_generation_seconds": round(min(latencies), 3) if latencies else None,
        "max_generation_seconds": round(max(latencies), 3) if latencies else None,
        "failed_case_ids": [
            record["case_id"] for record in records if not record.get("sql")
        ],
    }
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    questions = load_questions(args.questions)
    if len(questions) != 50:
        raise ValueError(f"Expected 50 questions, found {len(questions)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = load_existing(args.output)
    completed_ids = {record["case_id"] for record in records}
    csv_path = args.output.with_suffix(".csv")
    summary_path = args.output.with_name(args.output.stem + "_summary.json")
    run_started = time.monotonic()

    for index, (case_id, question) in enumerate(questions, start=1):
        if case_id in completed_ids:
            print(f"[{index:02d}/50] {case_id} SKIP (already recorded)", flush=True)
            continue

        result = ask_wren(args.url, question, args.timeout)
        record = {
            "index": index,
            "case_id": case_id,
            "question": question,
            **result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        with args.output.open("a", encoding="utf-8") as output_file:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        records.append(record)
        completed_ids.add(case_id)
        write_csv(csv_path, records)

        outcome = "OK" if record["sql"] else f"FAIL:{record['error_code']}"
        print(
            f"[{index:02d}/50] {case_id} {outcome} "
            f"{record['latency_seconds']:.3f}s",
            flush=True,
        )

    records.sort(key=lambda record: record["index"])
    write_csv(csv_path, records)
    write_summary(summary_path, records, time.monotonic() - run_started)
    return 0 if all(record.get("sql") for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
