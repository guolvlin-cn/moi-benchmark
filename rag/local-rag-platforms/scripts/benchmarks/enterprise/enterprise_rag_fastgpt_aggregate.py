#!/usr/bin/env python3
"""Aggregate the FastGPT EnterpriseRAG adapted-slice run from immutable ledgers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    return values[max(0, min(len(values) - 1, math.ceil(len(values) * fraction) - 1))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    run = Path(args.run_dir).resolve()
    package = Path(args.package).resolve()

    questions = {row["question_id"]: row for row in load_jsonl(package / "questions.jsonl")}
    product = load_jsonl(run / "terminal-ledger.jsonl")
    retrieval_rows = load_jsonl(run / "retrieval-top10-replay/results.jsonl")
    retrieval_metrics = json.loads((run / "retrieval-top10-replay/metrics.json").read_text())
    judge_rows = load_jsonl(run / "judge/judge-terminal-ledger.jsonl")
    judge_latest = {}
    judge_first = {}
    for row in judge_rows:
        key = (row["question_id"], int(row.get("repeat_id", 1)))
        judge_first.setdefault(key, row)
        judge_latest[key] = row

    planned_n = len(questions)
    latest_success = [row for row in judge_latest.values() if row.get("status") == "SUCCESS"]

    def dimension(row: dict, name: str):
        item = row.get("judgement", {}).get("dimensions", {}).get(name, {})
        value = item.get("score")
        return float(value) if item.get("supported") and isinstance(value, (int, float)) else None

    def planned_mean(name: str) -> float:
        return sum(dimension(row, name) or 0.0 for row in latest_success) / planned_n

    aggregate = sum(
        (dimension(row, "correctness") or 0.0) * (dimension(row, "completeness") or 0.0)
        for row in latest_success
    ) / planned_n

    qa_latency = {
        row["question_id"]: float(row["latency_ms"])
        for row in product
        if row.get("stage") == "qa" and row.get("status") == "SUCCESS"
    }
    retrieval_latency = {
        row["question_id"]: float(row["latency_ms"])
        for row in retrieval_rows
        if row.get("status") == "SUCCESS"
    }
    e2e = [retrieval_latency[qid] + qa_latency[qid] for qid in questions if qid in retrieval_latency and qid in qa_latency]

    by_type = {}
    for label in sorted({row.get("question_type", "unknown") for row in questions.values()}):
        ids = {qid for qid, row in questions.items() if row.get("question_type", "unknown") == label}
        rows = [row for key, row in judge_latest.items() if key[0] in ids and row.get("status") == "SUCCESS"]
        by_type[label] = {
            "planned_n": len(ids),
            "valid_judge_n": len(rows),
            "correctness": sum(dimension(row, "correctness") or 0.0 for row in rows) / len(ids),
            "completeness": sum(dimension(row, "completeness") or 0.0 for row in rows) / len(ids),
        }

    result = {
        "schema": "enterprise-rag-fastgpt-evaluation-v1",
        "status": "COMPLETE" if len(judge_latest) == planned_n and len(latest_success) == planned_n else "PARTIAL",
        "dataset_status": "CURRENT_CORPUS_ADAPTED",
        "corpus": {"documents": 722, "questions": planned_n, "official_full_corpus": False},
        "retrieval": retrieval_metrics,
        "qa": {
            "product_success_n": len(qa_latency),
            "first_pass_availability": len(qa_latency) / planned_n,
            "e2e_latency_ms_p50": percentile(e2e, 0.5),
            "e2e_latency_ms_p95": percentile(e2e, 0.95),
        },
        "judge": {
            "planned_n": planned_n,
            "terminal_unique_n": len(judge_latest),
            "valid_n": len(latest_success),
            "latest_status_counts": dict(Counter(row.get("status") for row in judge_latest.values())),
            "first_attempt_success_n": sum(row.get("status") == "SUCCESS" for row in judge_first.values()),
            "recovery_rows_n": sum(bool(row.get("recovery_of_failed_terminal")) for row in judge_rows),
            "correctness": planned_mean("correctness"),
            "completeness": planned_mean("completeness"),
            "dataset_aggregate": aggregate,
            "strict_unanswerable_success": None,
            "strict_unanswerable_reason": "PACKAGE_MARKS_ALL_500_ANSWERABLE",
            "info_not_found_correctness": by_type.get("info_not_found", {}).get("correctness"),
            "by_question_type": by_type,
        },
        "notes": [
            "FastGPT searchTest limit is a token budget; retrieval replay used limit=20000 and first 10 unique source documents.",
            "Retrieval metrics exclude 30 questions with no gold_doc_ids (eligible_n=470).",
            "Judge aggregation uses the latest append-only terminal per question; failed first attempts remain auditable.",
        ],
    }
    path = run / "enterprise-evaluation-metrics.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
