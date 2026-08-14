#!/usr/bin/env python3
"""Run one or more independent Spider Mix50 requests against local Wren."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = ROOT / "benchmark/questions/questions_mix50.tsv"
DEFAULT_DATABASES = ROOT / "benchmark/questions/case_databases.tsv"
DEFAULT_MODEL = "qwen3.7-plus-2026-05-26"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--databases", type=Path, default=DEFAULT_DATABASES)
    parser.add_argument("--url", default="http://localhost:3001/api/v1/generate_sql")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--case")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def load_tsv(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split("\t", 1)
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise ValueError(f"Invalid TSV line {number}: {raw!r}")
        rows.append((parts[0].strip(), parts[1].strip()))
    return rows


def load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()


def ask_wren(url: str, question: str, timeout: float) -> dict:
    body = json.dumps(
        {"question": question, "language": "English", "returnSqlDialect": True}
    ).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            http_status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        http_status = error.code
        raw = error.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw}
    except (TimeoutError, urllib.error.URLError) as error:
        http_status = 0
        payload = {"error": str(error)}

    sql = payload.get("sql")
    if http_status == 0:
        status = "collector_error"
    elif sql:
        status = "ok"
    elif http_status == 200:
        status = "empty_sql"
    else:
        status = "generation_error"
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "generated_sql": sql,
        "status": status,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "sql_execution_ms": None,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "error": payload.get("error") or payload.get("message"),
        "thread_id": payload.get("threadId"),
        "response_id": payload.get("id"),
        "http_status": http_status,
        "error_code": payload.get("code"),
    }


def write_summary(path: Path, records: list[dict], expected: int) -> None:
    latencies = sorted(
        int(item["latency_ms"])
        for item in records
        if item.get("latency_ms") is not None
    )
    generated = [item for item in records if item.get("generated_sql")]

    def nearest_rank_percentile(percent: int):
        if not latencies:
            return None
        index = max(0, (len(latencies) * percent + 99) // 100 - 1)
        return latencies[index]

    write_json(
        path,
        {
            "expected_attempts": expected,
            "recorded_attempts": len(records),
            "sql_generated": len(generated),
            "failed": len(records) - len(generated),
            "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
            "p50_latency_ms": nearest_rank_percentile(50),
            "p95_latency_ms": nearest_rank_percentile(95),
            "min_latency_ms": min(latencies) if latencies else None,
            "max_latency_ms": max(latencies) if latencies else None,
            "token_collection": (
                "api_response" if any(item.get("total_tokens") is not None for item in records)
                else "unavailable"
            ),
            "failed_attempts": [
                {
                    "question_id": item["question_id"],
                    "repeat_index": item["repeat_index"],
                    "status": item["status"],
                    "error": item.get("error"),
                }
                for item in records
                if not item.get("generated_sql")
            ],
        },
    )


def main() -> int:
    args = parse_args()
    if args.repeats < 1:
        raise ValueError("--repeats must be at least 1")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_id):
        raise ValueError("Invalid --run-id")
    questions = load_tsv(args.questions)
    databases = dict(load_tsv(args.databases))
    if len(questions) != 50 or len(databases) != 50:
        raise ValueError("Spider Mix50 inputs must contain exactly 50 cases")
    if args.case:
        questions = [item for item in questions if item[0] == args.case]
        if not questions:
            raise ValueError(f"Unknown case: {args.case}")

    output = args.output or ROOT / "runs/wren" / args.run_id / "predictions.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    run_path = output.parent / "run.json"
    summary_path = output.parent / "run_summary.json"
    records = load_existing(output)
    completed = {(item["question_id"], int(item["repeat_index"])) for item in records}
    thread_ids = {item.get("metadata", {}).get("thread_id") for item in records}
    thread_ids.discard(None)
    expected = len(questions) * args.repeats

    if not run_path.exists():
        write_json(
            run_path,
            {
                "run_id": args.run_id,
                "product": "wren",
                "model": args.model,
                "benchmark_id": "spider_mix50",
                "databases": ["pets_1", "concert_singer", "car_1"],
                "semantic_rules": "native_schema_and_original_foreign_keys_only",
                "repeats": args.repeats,
                "endpoint": args.url,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "token_collection": "api_response_if_available_otherwise_null",
            },
        )

    sequence = 0
    for repeat_index in range(1, args.repeats + 1):
        for question_id, question in questions:
            sequence += 1
            if (question_id, repeat_index) in completed:
                print(f"[{sequence:03d}/{expected}] {question_id} r{repeat_index} SKIP", flush=True)
                continue
            result = ask_wren(args.url, question, args.timeout)
            thread_id = result.pop("thread_id")
            response_id = result.pop("response_id")
            if result["status"] == "collector_error":
                append_jsonl(
                    output.parent / "collection_errors.jsonl",
                    {
                        "question_id": question_id,
                        "question": question,
                        "repeat_index": repeat_index,
                        **result,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                print(f"[{sequence:03d}/{expected}] {question_id} COLLECTOR_ERROR; stopped", flush=True)
                return 2
            if thread_id and thread_id in thread_ids:
                result.update(
                    status="context_error",
                    error="Wren reused a thread_id from another attempt",
                    generated_sql=None,
                )
            if thread_id:
                thread_ids.add(thread_id)
            record = {
                "question_id": question_id,
                "question": question,
                "repeat_index": repeat_index,
                **result,
                "raw_answer": None,
                "metadata": {
                    "model": args.model,
                    "thread_id": thread_id,
                    "response_id": response_id,
                    "database": databases[question_id],
                    "new_thread": True,
                },
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            append_jsonl(output, record)
            records.append(record)
            completed.add((question_id, repeat_index))
            write_summary(summary_path, records, expected)
            outcome = "OK" if record.get("generated_sql") else record["status"]
            print(
                f"[{sequence:03d}/{expected}] {question_id} r{repeat_index} "
                f"{outcome} {record['latency_ms']}ms",
                flush=True,
            )

    write_summary(summary_path, records, expected)
    return 0 if len(completed) >= expected else 2


if __name__ == "__main__":
    raise SystemExit(main())
