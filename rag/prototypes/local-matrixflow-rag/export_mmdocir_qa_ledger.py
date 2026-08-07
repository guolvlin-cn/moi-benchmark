#!/usr/bin/env python3
"""Export a stable, metric-friendly ledger from a native MOI QA run."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                yield value
            else:
                raise ValueError(f"{path}:{line_number}: expected an object")


def normalized(value: Any) -> str:
    # Keep the answer score consistent with the competitor evaluator: case is
    # ignored and punctuation/formatting (including hyphens) is removed.
    return re.sub(r"\W+", "", str(value or "").lower(), flags=re.UNICODE)


def page_recall(gold_pages: list[int], hits: list[dict[str, Any]], k: int) -> float:
    if not gold_pages:
        return 0.0
    found = {int(hit.get("page_number", 0)) for hit in hits[:k] if hit.get("page_number") is not None}
    return len(found.intersection(gold_pages)) / len(set(gold_pages))


def to_ledger_row(result: dict[str, Any]) -> dict[str, Any]:
    case = result.get("case") or {}
    metadata = case.get("metadata") or {}
    chunks = result.get("chunks") or []
    gold_pages = [int(page) for page in metadata.get("gold_page_ids", [])]
    hits = []
    for chunk in chunks:
        hits.append(
            {
                "rank": chunk.get("rank"),
                "chunk_id": chunk.get("chunk_id"),
                "file_id": chunk.get("file_id"),
                "file_name": chunk.get("file_name"),
                "page_number": chunk.get("page_number"),
                "score": chunk.get("score"),
                "routes": chunk.get("routes", []),
                "level": chunk.get("level"),
                "chunk_index": chunk.get("chunk_index"),
                "bbox": chunk.get("bbox", []),
                "source_uri": chunk.get("source_uri", ""),
                "content": chunk.get("content", ""),
            }
        )
    reference_answer = metadata.get("reference_answer")
    generated_answer = result.get("answer", "")
    answer_contains_gold = bool(reference_answer) and normalized(reference_answer) in normalized(generated_answer)
    return {
        "question_id": case.get("id"),
        "question": case.get("question"),
        "reference_answer": reference_answer,
        "generated_answer": generated_answer,
        "answer_exact_match_normalized": bool(reference_answer) and normalized(reference_answer) == normalized(generated_answer),
        "answer_contains_gold": answer_contains_gold,
        "status": result.get("status"),
        "error": result.get("error", ""),
        "retrieval_latency_ms": result.get("retrieval_latency_ms"),
        "generation_latency_ms": result.get("generation_latency_ms"),
        "generation_provider": result.get("generation_provider", ""),
        "generation_model": result.get("generation_model", ""),
        "embedding_model": result.get("embedding_model", ""),
        "routes": result.get("routes", []),
        "doc_name": metadata.get("doc_name"),
        "file_id": (case.get("file_ids") or [None])[0],
        "domain": metadata.get("domain"),
        "question_type": metadata.get("question_type"),
        "gold_page_ids": gold_pages,
        "gold_layout_mapping": metadata.get("gold_layout_mapping", []),
        "retrieved_page_recall_at_k": {str(k): page_recall(gold_pages, hits, k) for k in (1, 3, 5, 10)},
        "retrieval_hits": hits,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    rows = [to_ledger_row(result) for result in read_jsonl(args.results)]
    if not rows:
        raise SystemExit("QA results are empty")
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.ledger.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    successful = [row for row in rows if row["status"] == "ok"]
    summary = {
        "schema": "mmdocir-moi-qa-ledger-v1",
        "attempts": len(rows),
        "successful_attempts": len(successful),
        "failed_attempts": len(rows) - len(successful),
        "answer_exact_match_normalized_count": sum(row["answer_exact_match_normalized"] for row in successful),
        "answer_exact_match_normalized_rate": (
            sum(row["answer_exact_match_normalized"] for row in successful) / len(successful) if successful else 0.0
        ),
        "answer_contains_gold_count": sum(row["answer_contains_gold"] for row in successful),
        "answer_contains_gold_rate": (
            sum(row["answer_contains_gold"] for row in successful) / len(successful) if successful else 0.0
        ),
        "mean_page_recall_at_k": {
            str(k): (sum(row["retrieved_page_recall_at_k"][str(k)] for row in successful) / len(successful) if successful else 0.0)
            for k in (1, 3, 5, 10)
        },
        "results_source": str(args.results),
        "ledger_source": str(args.ledger),
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
