#!/usr/bin/env python3
"""Prepare the official 2,556-question MultiHop-RAG run against the existing MOI index."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".local-services/competitor-eval-ready/v1/multihop-rag"
LEGACY = ROOT / "prototypes/runs/matrixflow-multihop-rag-20260731-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=LEGACY / "config.json")
    args = parser.parse_args()
    output = args.output.resolve()

    package_questions = PACKAGE / "questions.jsonl"
    package_corpus = PACKAGE / "corpus.jsonl"
    legacy_manifest = LEGACY / "prepared/corpus_manifest.json"
    legacy_ingest = LEGACY / "product-run/20260731-170525.330/ingest-state.json"
    legacy_config = args.config.resolve()

    questions = load_jsonl(package_questions)
    corpus = load_jsonl(package_corpus)
    old_docs = json.loads(legacy_manifest.read_text(encoding="utf-8"))["documents"]
    old_by_url = {str(row["url"]): str(row["filename"]) for row in old_docs}
    new_to_old: dict[str, str] = {}
    missing_docs: list[dict[str, str]] = []
    for row in corpus:
        doc_id = str(row["doc_id"])
        url = str((row.get("metadata") or {}).get("url") or "")
        old_name = old_by_url.get(url)
        if old_name:
            new_to_old[doc_id] = old_name
        else:
            missing_docs.append({"doc_id": doc_id, "url": url})
    if missing_docs:
        raise SystemExit(f"unmapped corpus documents: {len(missing_docs)}")

    prepared: list[dict[str, Any]] = []
    missing_gold: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    for row in questions:
        question_type = str(row.get("question_type") or "unknown")
        type_counts[question_type] = type_counts.get(question_type, 0) + 1
        gold_doc_ids = [str(value) for value in row.get("gold_doc_ids") or []]
        mapped = [new_to_old[value] for value in gold_doc_ids if value in new_to_old]
        if len(mapped) != len(gold_doc_ids):
            missing_gold.append({"question_id": row["question_id"], "gold_doc_ids": gold_doc_ids})
        prepared.append(
            {
                "id": row["question_id"],
                "question": row["question"],
                "retrieval_keywords": [row["question"]],
                "relevant_documents": mapped,
                "relevant_evidence": row.get("gold_evidence") or [],
                "expected_answer_keywords": [],
                "expected_answerable": bool(row.get("answerable")),
                "metadata": {
                    "dataset": "MultiHop-RAG",
                    "question_type": question_type,
                    "reference_answer": row.get("reference_answer"),
                    "package_gold_doc_ids": gold_doc_ids,
                },
            }
        )
    if missing_gold:
        raise SystemExit(f"questions with unmapped gold documents: {len(missing_gold)}")
    if len(prepared) != 2556 or len(new_to_old) != 609:
        raise SystemExit(f"count mismatch: documents={len(new_to_old)} questions={len(prepared)}")

    prepared_dir = output / "prepared"
    dataset_path = prepared_dir / "questions.jsonl"
    mapping_path = prepared_dir / "document-id-map.json"
    write_jsonl(dataset_path, prepared)
    write_json(mapping_path, new_to_old)
    write_json(
        prepared_dir / "manifest.json",
        {
            "schema_version": "moi-multihop-rag-full-prepared-v1",
            "documents": len(new_to_old),
            "questions": len(prepared),
            "question_type_counts": type_counts,
            "dataset_sha256": sha256(dataset_path),
            "mapping_sha256": sha256(mapping_path),
            "source_questions_sha256": sha256(package_questions),
            "source_corpus_sha256": sha256(package_corpus),
            "legacy_ingest_state": str(legacy_ingest),
            "legacy_ingest_state_sha256": sha256(legacy_ingest),
            "legacy_config": str(legacy_config),
            "legacy_config_sha256": sha256(legacy_config),
        },
    )

    now = datetime.now(timezone.utc).isoformat()
    start_record = {
        "schema_version": "moi-rag-eval-start-record-v1",
        "run_id": output.name,
        "created_at": now,
        "status_at_start": "not_started",
        "system_id": "moi_local",
        "dataset_id": "multihop-rag",
        "protocol": "official 609 documents / 2,556 QA; one initial attempt per question",
        "corpus_reused": True,
        "corpus_documents": 609,
        "indexed_chunks": 6390,
        "vector_table": "matrixflow_rag_benchmark.embedding_results_multihop_20260731_v1",
        "questions": 2556,
        "max_hits": 10,
        "repeats": 1,
        "dataset_path": str(dataset_path),
        "dataset_sha256": sha256(dataset_path),
        "config_path": str(legacy_config),
        "config_sha256": sha256(legacy_config),
        "resume_policy": "results.jsonl is append-only; on interruption, generate a remaining-question dataset from terminal IDs",
    }
    start_path = output / "start-record.json"
    write_json(start_path, start_record)
    (output / "start-record.json.sha256").write_text(sha256(start_path) + "\n", encoding="utf-8")
    initial = [
        {
            "question_id": row["id"],
            "attempt": 1,
            "status": "planned",
            "created_at": now,
        }
        for row in prepared
    ]
    initial_path = output / "initial-ledger.jsonl"
    write_jsonl(initial_path, initial)
    (output / "initial-ledger.jsonl.sha256").write_text(sha256(initial_path) + "\n", encoding="utf-8")
    print(json.dumps({"run": str(output), "documents": 609, "questions": 2556, "dataset": str(dataset_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
