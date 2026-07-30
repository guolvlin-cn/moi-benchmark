#!/usr/bin/env python3
"""Runnable benchmark smoke pipeline for the local Matrixflow RAG prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
SUPPORTED_SUFFIXES = {".md", ".txt"}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error


def load_documents(source: Path) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        documents.append(
            {
                "document_id": "doc_" + sha256_text(text)[:16],
                "path": str(path.relative_to(source)),
                "sha256": sha256_text(text),
                "text": text,
            }
        )
    if not documents:
        raise ValueError(f"no non-empty .md or .txt documents under {source}")
    return documents


def ingest(source: Path, run: Path, base_url: str, force: bool = False) -> dict[str, Any]:
    run.mkdir(parents=True, exist_ok=True)
    previous_path = run / "ingest-state.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    previous_hashes = set(previous.get("ingested_sha256", []))
    rows: list[dict[str, Any]] = []
    ingested_hashes = set(previous_hashes)

    for document in load_documents(source):
        if not force and document["sha256"] in previous_hashes:
            rows.append({**document, "status": "skipped_existing"})
            continue
        started = time.perf_counter()
        try:
            response = request_json(base_url, "/ingest", {"text": document["text"]})
            rows.append(
                {
                    **document,
                    "status": "ingested",
                    "service_document_id": response.get("id"),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
            ingested_hashes.add(document["sha256"])
        except Exception as error:
            rows.append(
                {
                    **document,
                    "status": "failed",
                    "error": str(error),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )

    state = {
        "schema_version": "local-rag-ingest-v1",
        "base_url": base_url,
        "source": str(source.resolve()),
        "ingested_sha256": sorted(ingested_hashes),
        "documents": rows,
        "summary": {
            "total": len(rows),
            "ingested": sum(row["status"] == "ingested" for row in rows),
            "skipped_existing": sum(row["status"] == "skipped_existing" for row in rows),
            "failed": sum(row["status"] == "failed" for row in rows),
        },
    }
    write_json(previous_path, state)
    return state


def keyword_recall(answer: str, expected_keywords: list[str]) -> float | None:
    if not expected_keywords:
        return None
    answer_folded = answer.casefold()
    return sum(keyword.casefold() in answer_folded for keyword in expected_keywords) / len(expected_keywords)


def run_questions(dataset: Path, run: Path, base_url: str, repeats: int) -> list[dict[str, Any]]:
    cases = read_jsonl(dataset)
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    results: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        question = str(case.get("question", "")).strip()
        if not case_id or not question:
            raise ValueError("each dataset row requires non-empty id and question")
        for repeat in range(1, repeats + 1):
            started = time.perf_counter()
            try:
                response = request_json(base_url, "/chat", {"message": question})
                answer = str(response.get("answer", ""))
                sources = response.get("sources") or []
                results.append(
                    {
                        "case": case,
                        "repeat": repeat,
                        "status": "ok",
                        "answer": answer,
                        "sources": sources,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        "metrics": {
                            "request_success": 1.0,
                            "answer_keyword_recall": keyword_recall(answer, case.get("expected_keywords") or []),
                            "source_keyword_recall": keyword_recall(
                                "\n".join(str(source.get("text", "")) for source in sources),
                                case.get("expected_source_keywords") or case.get("expected_keywords") or [],
                            ),
                            "retrieved_source_count": len(sources),
                        },
                    }
                )
            except Exception as error:
                results.append(
                    {
                        "case": case,
                        "repeat": repeat,
                        "status": "failed",
                        "answer": "",
                        "sources": [],
                        "error": str(error),
                        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        "metrics": {
                            "request_success": 0.0,
                            "answer_keyword_recall": None,
                            "source_keyword_recall": None,
                            "retrieved_source_count": 0,
                        },
                    }
                )
    append_jsonl(run / "results.jsonl", results)
    return results


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize(run: Path) -> dict[str, Any]:
    results = read_jsonl(run / "results.jsonl")
    latencies = [float(row["latency_ms"]) for row in results]
    answer_recalls = [
        row["metrics"]["answer_keyword_recall"]
        for row in results
        if row["metrics"]["answer_keyword_recall"] is not None
    ]
    source_recalls = [
        row["metrics"]["source_keyword_recall"]
        for row in results
        if row["metrics"]["source_keyword_recall"] is not None
    ]
    summary = {
        "schema_version": "local-rag-summary-v1",
        "attempts": len(results),
        "distinct_questions": len({row["case"]["id"] for row in results}),
        "request_success_rate": sum(row["status"] == "ok" for row in results) / len(results) if results else 0.0,
        "mean_answer_keyword_recall": statistics.mean(answer_recalls) if answer_recalls else None,
        "mean_source_keyword_recall": statistics.mean(source_recalls) if source_recalls else None,
        "latency_ms": {"mean": statistics.mean(latencies) if latencies else None, "p95": percentile(latencies, 0.95)},
    }
    write_json(run / "summary.json", summary)
    report = "\n".join(
        [
            "# Local Matrixflow RAG benchmark smoke report",
            "",
            f"- Attempts: {summary['attempts']}",
            f"- Distinct questions: {summary['distinct_questions']}",
            f"- Request success rate: {summary['request_success_rate']:.3f}",
            f"- Mean answer keyword recall: {summary['mean_answer_keyword_recall']}",
            f"- Mean source keyword recall: {summary['mean_source_keyword_recall']}",
            f"- Mean latency (ms): {summary['latency_ms']['mean']}",
            f"- P95 latency (ms): {summary['latency_ms']['p95']}",
            "",
            "This is a pipeline smoke result, not a formal Golden/Judge-based RAG score.",
        ]
    )
    (run / "report.md").write_text(report + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subcommands.add_parser("ingest")
    ingest_parser.add_argument("--source", type=Path, required=True)
    ingest_parser.add_argument("--run", type=Path, required=True)
    ingest_parser.add_argument("--force", action="store_true")

    run_parser = subcommands.add_parser("run")
    run_parser.add_argument("--dataset", type=Path, required=True)
    run_parser.add_argument("--run", type=Path, required=True)
    run_parser.add_argument("--repeats", type=int, default=1)

    pipeline_parser = subcommands.add_parser("pipeline")
    pipeline_parser.add_argument("--source", type=Path, required=True)
    pipeline_parser.add_argument("--dataset", type=Path, required=True)
    pipeline_parser.add_argument("--run", type=Path, required=True)
    pipeline_parser.add_argument("--repeats", type=int, default=1)
    pipeline_parser.add_argument("--force", action="store_true")

    report_parser = subcommands.add_parser("report")
    report_parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "ingest":
        print(json.dumps(ingest(args.source, args.run, args.base_url, args.force), ensure_ascii=False))
    elif args.command == "run":
        run_questions(args.dataset, args.run, args.base_url, args.repeats)
        print(json.dumps(summarize(args.run), ensure_ascii=False))
    elif args.command == "pipeline":
        ingest(args.source, args.run, args.base_url, args.force)
        run_questions(args.dataset, args.run, args.base_url, args.repeats)
        print(json.dumps(summarize(args.run), ensure_ascii=False))
    else:
        print(json.dumps(summarize(args.run), ensure_ascii=False))


if __name__ == "__main__":
    main()
