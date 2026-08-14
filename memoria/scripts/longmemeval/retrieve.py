#!/usr/bin/env python3
"""Create an immutable LongMemEval-S Top-K retrieval snapshot from Memoria."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()

    def write(self, value: dict[str, Any]) -> None:
        line = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.lock:
            self.handle.write(line + "\n")
            self.handle.flush()
            os.fsync(self.handle.fileno())

    def close(self) -> None:
        with self.lock:
            self.handle.close()


def latest_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            question_id = record.get("question_id")
            if question_id:
                records[str(question_id)] = record
    return records


def select_questions(
    questions: list[dict[str, Any]],
    question_ids: list[str],
    start_index: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    if question_ids:
        selected_ids = set(question_ids)
        selected = [q for q in questions if str(q["question_id"]) in selected_ids]
        missing = selected_ids - {str(q["question_id"]) for q in selected}
        if missing:
            raise ValueError(f"unknown question ids: {sorted(missing)}")
        return selected
    selected = questions[start_index:]
    return selected if limit is None else selected[:limit]


def normalize_item(
    item: dict[str, Any], rank: int, question_id: str, legacy_v023: bool
) -> dict[str, Any]:
    metadata = item.get("extra_metadata") or {}
    return {
        "rank": rank,
        "memory_id": item.get("memory_id"),
        "user_id": item.get("user_id"),
        "session_id": item.get("session_id"),
        "original_session_id": (
            item.get("session_id")
            if legacy_v023
            else metadata.get("original_session_id") or item.get("session_id")
        ),
        "chunk_index": metadata.get("chunk_index"),
        "chunk_count": metadata.get("chunk_count"),
        "ingest_key": metadata.get("ingest_key"),
        "question_id": question_id if legacy_v023 else metadata.get("question_id"),
        "observed_at": item.get("observed_at"),
        "retrieval_score": item.get("retrieval_score"),
        "subject_id": item.get("subject_id"),
    }


class Retriever:
    def __init__(
        self,
        *,
        api_url: str,
        master_key: str,
        user_prefix: str,
        top_k: int,
        explain: str,
        timeout: float,
        max_retries: int,
        legacy_v023: bool,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.master_key = master_key
        self.user_prefix = user_prefix
        self.top_k = top_k
        self.explain = explain
        self.timeout = timeout
        self.max_retries = max_retries
        self.legacy_v023 = legacy_v023
        self.local = threading.local()

    def session(self) -> requests.Session:
        session = getattr(self.local, "session", None)
        if session is None:
            session = requests.Session()
            self.local.session = session
        return session

    def retrieve(self, question: dict[str, Any]) -> dict[str, Any]:
        question_id = str(question["question_id"])
        user_id = f"{self.user_prefix}{question_id}"
        request_body = {
            "query": str(question["question"]),
            "top_k": self.top_k,
            "explain": self.explain,
        }
        attempts: list[dict[str, Any]] = []
        response_body: Any = None
        final_error: str | None = None
        started = time.perf_counter()

        for attempt_number in range(1, self.max_retries + 2):
            attempt_started = time.perf_counter()
            try:
                response = self.session().post(
                    f"{self.api_url}/v1/memories/retrieve",
                    headers={
                        "Authorization": f"Bearer {self.master_key}",
                        "X-Impersonate-User": user_id,
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                    timeout=self.timeout,
                )
                attempt_ms = (time.perf_counter() - attempt_started) * 1000
                attempt_record = {
                    "attempt": attempt_number,
                    "status_code": response.status_code,
                    "elapsed_ms": round(attempt_ms, 3),
                }
                attempts.append(attempt_record)
                if response.status_code == 200:
                    response_body = response.json()
                    break
                final_error = f"HTTP {response.status_code}: {response.text[:1000]}"
                attempt_record["error"] = final_error
                if response.status_code not in TRANSIENT_STATUS:
                    break
            except (requests.RequestException, ValueError) as exc:
                attempt_ms = (time.perf_counter() - attempt_started) * 1000
                final_error = str(exc)
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "status_code": None,
                        "elapsed_ms": round(attempt_ms, 3),
                        "error": final_error,
                    }
                )
            if attempt_number <= self.max_retries:
                time.sleep(min(2 ** (attempt_number - 1), 8))

        total_ms = (time.perf_counter() - started) * 1000
        if response_body is None:
            return {
                "at": utc_now(),
                "question_id": question_id,
                "question_type": question.get("question_type"),
                "is_abstention": question_id.endswith("_abs"),
                "question": question.get("question"),
                "question_date": question.get("question_date"),
                "answer_session_ids": question.get("answer_session_ids", []),
                "user_id": user_id,
                "request": request_body,
                "status": "failed",
                "first_pass_success": False,
                "attempts": attempts,
                "client_total_ms": round(total_ms, 3),
                "error": final_error or "empty response",
                "results": [],
                "normalized_results": [],
                "explain": {},
                "validation_errors": [],
                "validation_ok": False,
            }

        if isinstance(response_body, dict):
            items = response_body.get("results", [])
            explain = response_body.get("explain", {})
        else:
            items = response_body
            explain = {}
        if not isinstance(items, list):
            items = []

        normalized = [
            normalize_item(item, rank, question_id, self.legacy_v023)
            for rank, item in enumerate(items, 1)
        ]
        validation_errors: list[str] = []
        if len(items) != self.top_k:
            validation_errors.append(
                f"expected {self.top_k} results, received {len(items)}"
            )
        for item in normalized:
            if item["user_id"] != user_id:
                validation_errors.append(
                    f"cross-user memory {item['memory_id']}: {item['user_id']}"
                )
            if item["question_id"] != question_id:
                validation_errors.append(
                    f"cross-question memory {item['memory_id']}: {item['question_id']}"
                )
            if not item["original_session_id"]:
                validation_errors.append(
                    f"missing original_session_id: {item['memory_id']}"
                )
            if not self.legacy_v023 and not item["ingest_key"]:
                validation_errors.append(f"missing ingest_key: {item['memory_id']}")

        return {
            "at": utc_now(),
            "question_id": question_id,
            "question_type": question.get("question_type"),
            "is_abstention": question_id.endswith("_abs"),
            "question": question.get("question"),
            "question_date": question.get("question_date"),
            "answer_session_ids": question.get("answer_session_ids", []),
            "user_id": user_id,
            "request": request_body,
            "status": "success",
            "first_pass_success": len(attempts) == 1,
            "attempts": attempts,
            "client_total_ms": round(total_ms, 3),
            "results": items,
            "normalized_results": normalized,
            "explain": explain,
            "validation_errors": validation_errors,
            "validation_ok": not validation_errors,
        }


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[3]
    runtime_root = Path("/Users/wangyaqi/Documents/cursor_project/agent评估/memoria_runtime")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root
        / "memoria/datasets/downloads/public-benchmarks/longmemeval/longmemeval_s_cleaned.json",
    )
    parser.add_argument("--runtime-env", type=Path, default=runtime_root / ".env")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--user-prefix", default="longmemeval-")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--explain", default="verbose")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument(
        "--legacy-v023",
        action="store_true",
        help="Infer provenance fields unavailable in Memoria v0.2.3 responses.",
    )
    parser.add_argument("--memoria-commit")
    parser.add_argument("--memoria-patch-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if not 1 <= args.top_k <= 100:
        raise ValueError("top-k must be between 1 and 100")
    if not args.dataset.is_file():
        raise FileNotFoundError(args.dataset)
    if not args.runtime_env.is_file():
        raise FileNotFoundError(args.runtime_env)

    env = read_env(args.runtime_env)
    master_key = env.get("MEMORIA_MASTER_KEY", "")
    if not master_key:
        raise ValueError("MEMORIA_MASTER_KEY is missing from runtime env")
    questions = json.loads(args.dataset.read_text(encoding="utf-8"))
    selected = select_questions(
        questions, args.question_id, args.start_index, args.limit
    )
    selected_ids = [str(question["question_id"]) for question in selected]

    args.run_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = args.run_dir / "retrieval.jsonl"
    manifest_path = args.run_dir / "manifest.json"
    manifest_frozen = {
        "dataset_path": str(args.dataset.resolve()),
        "dataset_sha256": sha256_file(args.dataset),
        "selected_question_ids": selected_ids,
        "api_url": args.api_url.rstrip("/"),
        "endpoint": "/v1/memories/retrieve",
        "top_k": args.top_k,
        "explain": args.explain,
        "query_template": "raw_question",
        "user_prefix": args.user_prefix,
        "session_id_filter": None,
        "subject_id_filter": None,
        "memory_types_filter": None,
        "branch": None,
        "workers": args.workers,
        "timeout_seconds": args.timeout,
        "max_retries": args.max_retries,
        "runner_sha256": sha256_file(Path(__file__)),
        "memoria_compatibility": (
            "legacy-v0.2.3-no-extra-metadata"
            if args.legacy_v023
            else "current"
        ),
        "memoria_commit": args.memoria_commit,
        "memoria_patch_sha256": args.memoria_patch_sha256,
    }
    if manifest_path.exists():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing_frozen = {key: existing_manifest.get(key) for key in manifest_frozen}
        if existing_frozen != manifest_frozen:
            raise ValueError("run manifest does not match requested frozen configuration")
    else:
        atomic_json(manifest_path, {"created_at": utc_now(), **manifest_frozen})

    previous = latest_records(snapshot_path)
    completed_ids = {
        qid
        for qid, record in previous.items()
        if record.get("status") == "success" and record.get("validation_ok") is True
    }
    pending = [q for q in selected if str(q["question_id"]) not in completed_ids]
    snapshot = JsonlWriter(snapshot_path)
    checkpoint = JsonlWriter(args.run_dir / "checkpoint.jsonl")
    errors = JsonlWriter(args.run_dir / "errors.jsonl")
    retriever = Retriever(
        api_url=args.api_url,
        master_key=master_key,
        user_prefix=args.user_prefix,
        top_k=args.top_k,
        explain=args.explain,
        timeout=args.timeout,
        max_retries=args.max_retries,
        legacy_v023=args.legacy_v023,
    )

    started = time.monotonic()
    processed = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_map = {
                pool.submit(retriever.retrieve, question): str(question["question_id"])
                for question in pending
            }
            for future in concurrent.futures.as_completed(future_map):
                record = future.result()
                snapshot.write(record)
                checkpoint.write(
                    {
                        "at": record["at"],
                        "question_id": record["question_id"],
                        "status": record["status"],
                        "validation_ok": record["validation_ok"],
                    }
                )
                if record["status"] != "success" or not record["validation_ok"]:
                    errors.write(record)
                processed += 1
                print(
                    f"[{processed}/{len(pending)}] question={record['question_id']} "
                    f"status={record['status']} attempts={len(record['attempts'])} "
                    f"results={len(record['results'])} "
                    f"latency_ms={record['client_total_ms']:.1f}",
                    flush=True,
                )
    finally:
        snapshot.close()
        checkpoint.close()
        errors.close()

    current = latest_records(snapshot_path)
    selected_records = [current[qid] for qid in selected_ids if qid in current]
    success = sum(
        record.get("status") == "success" and record.get("validation_ok") is True
        for record in selected_records
    )
    summary = {
        "finished_at": utc_now(),
        "selected_questions": len(selected_ids),
        "snapshot_records": len(selected_records),
        "successful_questions": success,
        "failed_questions": len(selected_ids) - success,
        "processed_this_invocation": processed,
        "resumed_existing": len(selected_ids) - len(pending),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    atomic_json(args.run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if success == len(selected_ids) else 1


if __name__ == "__main__":
    raise SystemExit(main())
