#!/usr/bin/env python3
"""Run independent Enron NL2SQL requests against the local Wren API."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS = PROJECT_ROOT / "benchmark/questions/user/questions_enron_50_user_mix.txt"
DEFAULT_URL = "http://localhost:3000/api/v1/generate_sql"
DEFAULT_MODEL = "qwen3.7-plus-2026-05-26"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--case", help="Only run one question_id")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
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
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def token_usage(response_body: dict) -> tuple[int | None, int | None, int | None]:
    usage = response_body.get("usage")
    if not isinstance(usage, dict):
        return None, None, None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    return prompt, completion, total


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
            http_status = response.status
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        http_status = error.code
        raw_body = error.read().decode("utf-8")
        try:
            response_body = json.loads(raw_body)
        except json.JSONDecodeError:
            response_body = {"error": raw_body}
    except (TimeoutError, urllib.error.URLError) as error:
        http_status = 0
        response_body = {"error": str(error)}

    latency_ms = round((time.monotonic() - started) * 1000)
    sql = response_body.get("sql")
    prompt_tokens, completion_tokens, total_tokens = token_usage(response_body)
    error_message = response_body.get("error") or response_body.get("message")
    if http_status == 0:
        status = "collector_error"
    elif sql:
        status = "ok"
    elif http_status == 200:
        status = "empty_sql"
    else:
        status = "generation_error"

    return {
        "generated_sql": sql,
        "status": status,
        "latency_ms": latency_ms,
        "sql_execution_ms": None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "error": error_message,
        "thread_id": response_body.get("threadId"),
        "response_id": response_body.get("id"),
        "http_status": http_status,
        "error_code": response_body.get("code"),
    }


def write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def append_jsonl(path: Path, data: dict) -> None:
    with path.open("a", encoding="utf-8") as output_file:
        output_file.write(json.dumps(data, ensure_ascii=False) + "\n")
        output_file.flush()


def write_summary(path: Path, records: list[dict], expected: int) -> None:
    latencies = [
        record["latency_ms"]
        for record in records
        if record.get("latency_ms") is not None
    ]
    successful = [record for record in records if record.get("generated_sql")]
    write_json(
        path,
        {
            "expected_attempts": expected,
            "recorded_attempts": len(records),
            "sql_generated": len(successful),
            "failed": len(records) - len(successful),
            "average_latency_ms": (
                round(sum(latencies) / len(latencies)) if latencies else None
            ),
            "min_latency_ms": min(latencies) if latencies else None,
            "max_latency_ms": max(latencies) if latencies else None,
            "token_collection": (
                "api_response" if any(r.get("total_tokens") is not None for r in records)
                else "unavailable"
            ),
            "failed_attempts": [
                {
                    "question_id": record["question_id"],
                    "repeat_index": record["repeat_index"],
                    "status": record["status"],
                }
                for record in records
                if not record.get("generated_sql")
            ],
        },
    )


def main() -> int:
    args = parse_args()
    if args.repeats < 1:
        raise ValueError("--repeats must be at least 1")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_id):
        raise ValueError("--run-id may only contain letters, digits, dot, underscore, hyphen")

    questions = load_questions(args.questions)
    if len(questions) != 50:
        raise ValueError(f"Expected 50 questions, found {len(questions)}")
    if args.case:
        questions = [item for item in questions if item[0] == args.case]
        if not questions:
            raise ValueError(f"Unknown question_id: {args.case}")

    output = args.output or (
        PROJECT_ROOT
        / "products/wren/results/automated"
        / args.run_id
        / "predictions.jsonl"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run_path = output.parent / "run.json"
    summary_path = output.parent / "run_summary.json"
    records = load_existing(output)
    completed = {
        (record["question_id"], int(record["repeat_index"])) for record in records
    }
    thread_ids = {record.get("metadata", {}).get("thread_id") for record in records}
    thread_ids.discard(None)
    expected = len(questions) * args.repeats

    if run_path.exists():
        existing_run = json.loads(run_path.read_text(encoding="utf-8"))
        expected_run = {
            "run_id": args.run_id,
            "model": args.model,
            "repeats": args.repeats,
            "endpoint": args.url,
        }
        mismatches = {
            key: (existing_run.get(key), value)
            for key, value in expected_run.items()
            if existing_run.get(key) != value
        }
        if mismatches:
            raise ValueError(
                f"Existing run.json does not match this command: {mismatches}"
            )
    else:
        write_json(
            run_path,
            {
                "run_id": args.run_id,
                "product": "wren",
                "model": args.model,
                "benchmark_id": "enron_golden50_v1",
                "database": "enron_eval",
                "semantic_rules": "native_semantic_model_only",
                "repeats": args.repeats,
                "endpoint": args.url,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "token_collection": "api_response_if_available_otherwise_null",
            },
        )

    expected_keys = {
        (question_id, repeat_index)
        for repeat_index in range(1, args.repeats + 1)
        for question_id, _ in questions
    }
    sequence = 0
    for repeat_index in range(1, args.repeats + 1):
        for question_id, question in questions:
            sequence += 1
            if (question_id, repeat_index) in completed:
                print(
                    f"[{sequence:03d}/{expected}] {question_id} "
                    f"r{repeat_index} SKIP",
                    flush=True,
                )
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
                print(
                    f"[{sequence:03d}/{expected}] {question_id} r{repeat_index} "
                    "COLLECTOR_ERROR；停止且不占用本轮记录",
                    flush=True,
                )
                return 2
            if thread_id and thread_id in thread_ids:
                result["status"] = "context_error"
                result["error"] = "Wren returned a thread_id already used by another attempt"
                result["generated_sql"] = None
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
                    "database": "enron_eval",
                    "new_thread": True,
                },
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            with output.open("a", encoding="utf-8") as output_file:
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            records.append(record)
            completed.add((question_id, repeat_index))
            write_summary(summary_path, records, expected)

            outcome = "OK" if record["generated_sql"] else record["status"]
            print(
                f"[{sequence:03d}/{expected}] {question_id} r{repeat_index} "
                f"{outcome} {record['latency_ms']}ms",
                flush=True,
            )

    write_summary(summary_path, records, expected)
    recorded_keys = {
        (record["question_id"], int(record["repeat_index"])) for record in records
    }
    return 0 if expected_keys <= recorded_keys else 2


if __name__ == "__main__":
    raise SystemExit(main())
