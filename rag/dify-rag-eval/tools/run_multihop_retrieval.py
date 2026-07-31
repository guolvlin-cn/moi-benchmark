#!/usr/bin/env python3
"""Run frozen MultiHop-RAG questions directly against a Dify knowledge base."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from dify_rag_eval.dify import normalize_contexts
from dify_rag_eval.knowledge import KnowledgeClient
from dify_rag_eval.metrics import normalize_text


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--ingest-state", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default="https://api.dify.ai/v1")
    parser.add_argument("--top-k", default=5, type=int)
    parser.add_argument("--search-method", default="semantic_search")
    args = parser.parse_args()
    api_key = os.environ.get("DIFY_DATASET_API_KEY")
    if not api_key:
        raise SystemExit("DIFY_DATASET_API_KEY is absent")
    state = json.loads(args.ingest_state.read_text(encoding="utf-8"))
    questions = [
        json.loads(line)
        for line in args.questions.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    client = KnowledgeClient(args.base_url, api_key)
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(questions, 1):
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        try:
            raw = client.retrieve(
                state["dataset_id"],
                case["question"],
                top_k=args.top_k,
                search_method=args.search_method,
            )
            latency = time.perf_counter() - started
            contexts = normalize_contexts(raw.get("records") or [])
            normalized_contexts = [
                normalize_text(str(context.get("content") or ""))
                for context in contexts
            ]
            gold = [normalize_text(value) for value in case.get("gold_evidence") or []]
            hits = [
                any(item and item in context for context in normalized_contexts)
                for item in gold
            ]
            error = None
        except Exception as exc:
            latency = time.perf_counter() - started
            raw = None
            contexts = []
            gold = [normalize_text(value) for value in case.get("gold_evidence") or []]
            hits = [False] * len(gold)
            error = f"{type(exc).__name__}: {exc}"
        row = {
            "attempt_id": f"direct-retrieval-{case['id']}",
            "case": case,
            "dataset_id": state["dataset_id"],
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "latency_seconds": latency,
            "status": "terminal_success" if error is None else "terminal_error",
            "error": error,
            "contexts": contexts,
            "raw_response": raw,
            "metrics": {
                "request_success": float(error is None),
                "context_count": len(contexts),
                "evidence_hits": sum(hits),
                "evidence_total": len(hits),
                "evidence_recall_at_k": (
                    sum(hits) / len(hits) if hits else None
                ),
            },
        }
        rows.append(row)
        print(f"[{index}/{len(questions)}] {case['id']} {row['status']}", flush=True)

    args.output.mkdir(parents=True, exist_ok=True)
    results_path = args.output / "results.jsonl"
    results_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    latencies = [float(row["latency_seconds"]) for row in rows]
    evidence_total = sum(row["metrics"]["evidence_total"] for row in rows)
    evidence_hits = sum(row["metrics"]["evidence_hits"] for row in rows)
    summary = {
        "attempts": len(rows),
        "request_success": {
            "numerator": sum(row["error"] is None for row in rows),
            "denominator": len(rows),
        },
        "evidence_recall_at_k": {
            "numerator": evidence_hits,
            "denominator": evidence_total,
            "rate": evidence_hits / evidence_total if evidence_total else None,
            "match_rule": "normalized frozen evidence span exact substring in returned context",
        },
        "latency_seconds": {
            "p50": median(latencies) if latencies else None,
            "p95": percentile(latencies, 0.95),
        },
        "trace": "AVAILABLE: Dify Dataset API records, order retained as rank",
        "questions_sha256": sha256_file(args.questions),
        "ingest_state_sha256": sha256_file(args.ingest_state),
        "results_sha256": sha256_file(results_path),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
