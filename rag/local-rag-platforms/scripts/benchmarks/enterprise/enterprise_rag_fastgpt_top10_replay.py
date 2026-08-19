#!/usr/bin/env python3
"""Replay EnterpriseRAG-Bench direct retrieval with FastGPT's true Top-10 contract."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    return values[max(0, min(len(values) - 1, int(len(values) * fraction + 0.999999) - 1))]


def unwrap(value):
    while isinstance(value, dict) and isinstance(value.get("data"), (dict, list)):
        value = value["data"]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    package = Path(args.package).resolve()
    output = run_dir / "retrieval-top10-replay"
    output.mkdir(parents=True, exist_ok=True)
    resource_map = json.loads((run_dir / "resource-map.json").read_text())
    resource = next(iter(resource_map["resources"].values()))
    dataset_id = resource.get("dataset_id", resource.get("resource_id"))
    questions = [json.loads(line) for line in (package / "questions.jsonl").read_text().splitlines() if line]
    base_url = os.environ.get("FASTGPT_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
    api_key = os.environ["FASTGPT_API_KEY"]

    def evaluate(question):
        body = {
            "datasetId": dataset_id,
            "text": question["question"],
            # FastGPT defines limit as a token budget, not a result count.
            "limit": 20000,
            "similarity": 0,
            "searchMode": "embedding",
            "usingReRank": False,
            "datasetSearchUsingExtensionQuery": False,
        }
        started = time.monotonic()
        error = None
        payload = None
        for attempt in range(1, 5):
            request = urllib.request.Request(
                base_url + "/api/core/dataset/searchTest",
                data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    payload = unwrap(json.load(response))
                break
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                error = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
                if attempt < 4:
                    time.sleep(attempt * 1.5)
        latency_ms = (time.monotonic() - started) * 1000
        if not isinstance(payload, dict):
            return {"question_id": question["question_id"], "status": "FAILED", "error": error, "latency_ms": latency_ms}
        chunks = payload.get("list", [])
        ranked_docs = []
        seen = set()
        for chunk in chunks:
            source = str(chunk.get("sourceName", ""))
            doc_id = source[:-3] if source.endswith(".md") else source
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            ranked_docs.append(doc_id)
            if len(ranked_docs) == 10:
                break
        gold = list(dict.fromkeys(question.get("gold_doc_ids", [])))
        gold_set = set(gold)
        retrieved = set(ranked_docs)
        return {
            "question_id": question["question_id"],
            "question_type": question.get("question_type"),
            "source_types": question.get("metadata", {}).get("source_types", []),
            "status": "SUCCESS",
            "latency_ms": round(latency_ms, 3),
            "returned_chunk_count": len(chunks),
            "ranked_doc_ids": ranked_docs,
            "gold_doc_ids": gold,
            "doc_recall_at_10": (len(gold_set & retrieved) / len(gold_set)) if gold else None,
            "complete_evidence_set_recall_at_10": gold_set.issubset(retrieved) if gold else None,
            "invalid_extra_docs": len(retrieved - gold_set) if gold else None,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        rows = list(pool.map(evaluate, questions))
    rows.sort(key=lambda row: row["question_id"])
    ledger = output / "results.jsonl"
    ledger.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))
    (output / "results.jsonl.sha256").write_text(hashlib.sha256(ledger.read_bytes()).hexdigest() + "  results.jsonl\n")

    successful = [row for row in rows if row["status"] == "SUCCESS"]
    eligible = [row for row in successful if row["gold_doc_ids"]]
    by_type = {}
    for question_type in sorted({row["question_type"] for row in eligible}):
        group = [row for row in eligible if row["question_type"] == question_type]
        by_type[question_type] = {
            "n": len(group),
            "doc_recall_at_10": statistics.fmean(row["doc_recall_at_10"] for row in group),
            "complete_evidence_set_recall_at_10": statistics.fmean(row["complete_evidence_set_recall_at_10"] for row in group),
            "invalid_extra_docs_mean": statistics.fmean(row["invalid_extra_docs"] for row in group),
        }
    latencies = [row["latency_ms"] for row in successful]
    metrics = {
        "schema": "enterprise-rag-fastgpt-top10-replay-v1",
        "status": "COMPLETE" if len(successful) == len(questions) else "PARTIAL",
        "planned_n": len(questions),
        "successful_n": len(successful),
        "eligible_gold_doc_n": len(eligible),
        "no_gold_doc_n": len(successful) - len(eligible),
        "doc_recall_at_10": statistics.fmean(row["doc_recall_at_10"] for row in eligible),
        "complete_evidence_set_recall_at_10": statistics.fmean(row["complete_evidence_set_recall_at_10"] for row in eligible),
        "invalid_extra_docs_mean": statistics.fmean(row["invalid_extra_docs"] for row in eligible),
        "retrieval_latency_ms_p50": percentile(latencies, 0.50),
        "retrieval_latency_ms_p95": percentile(latencies, 0.95),
        "by_question_type": by_type,
        "contract": "FastGPT searchTest limit=20000 token budget; first 10 unique source documents",
    }
    metrics_path = output / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    (output / "metrics.json.sha256").write_text(hashlib.sha256(metrics_path.read_bytes()).hexdigest() + "  metrics.json\n")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if metrics["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
