#!/usr/bin/env python3
"""Prepare the Lenovo-Bench formal split for the generic Dify evaluator.

The evaluator uploads the original PDFs as Dify ``source_document`` artifacts.
The page-level representation is materialized separately for auditability and
for the one scanned PDF, using the existing precision MinerU output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lenovo_bench_fastgpt_eval import LenovoFixture  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_question_row(row: dict[str, Any]) -> dict[str, Any]:
    source_documents = [str(value) for value in row.get("source_documents", [])]
    answerability = str(row.get("answerability", ""))
    enriched = dict(row)
    enriched.update(
        {
            "id": str(row["question_id"]),
            "answer": str(row.get("reference_answer", "")),
            "document_ids": source_documents,
            "gold_document_ids": source_documents,
            "gold_evidence": row.get("evidence_sets", []),
            "media": ["text"],
            "answerable": answerability == "answerable",
            "metadata": {
                "benchmark": "lenovo-bench",
                "split": "formal",
                "question_language": row.get("question_language"),
                "answer_language": row.get("answer_language"),
                "citation_required": row.get("citation_required"),
                "citation_requirements": row.get("citation_requirements", []),
                "primary_type": row.get("primary_type"),
                "subtypes": row.get("subtypes", []),
                "claims": row.get("claims", []),
                "evidence_sets": row.get("evidence_sets", []),
                "negative_reason": row.get("negative_reason"),
            },
        }
    )
    return enriched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "datasets/lenovo-bench")
    parser.add_argument(
        "--mineru",
        type=Path,
        default=ROOT / "runs/stage1/lenovo-bench-parsing/mineru-precision/20260812-233036.403/documents.jsonl",
    )
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs/dify-lenovo-bench-20260813")
    parser.add_argument("--package-name", default="lenovo-bench-formal-v1")
    args = parser.parse_args()

    dataset = args.dataset.expanduser().resolve()
    mineru = args.mineru.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    run_root = output_root / args.package_name
    package_root = run_root / "package"
    audit_root = run_root / "audit"
    if run_root.exists() and any(run_root.iterdir()):
        raise SystemExit(f"Refusing to overwrite existing non-empty output: {run_root}")
    if not mineru.is_file():
        raise SystemExit(f"MinerU documents.jsonl is missing: {mineru}")

    fixture = LenovoFixture(dataset, mineru)
    pages, profile = fixture.pages()
    formal_path = dataset / "moi-corpus-100q-v1" / "questions.formal.jsonl"
    formal_rows = [
        json.loads(line)
        for line in formal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(formal_rows) != 60 or any(str(row.get("split")) != "formal" for row in formal_rows):
        raise SystemExit(f"Unexpected formal QA contract: rows={len(formal_rows)}")
    if len(fixture.manifest) != 46 or len(pages) != 1104:
        raise SystemExit(f"Unexpected corpus contract: documents={len(fixture.manifest)} pages={len(pages)}")

    package_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)
    corpus_rows: list[dict[str, Any]] = []
    for source in fixture.manifest:
        pdf = (dataset / "corpus" / str(source["source_file"])).resolve()
        if not pdf.is_file():
            raise SystemExit(f"Corpus PDF is missing: {pdf}")
        actual_hash = sha256_file(pdf)
        if actual_hash != str(source["sha256"]):
            raise SystemExit(f"Corpus hash mismatch: {pdf.name}")
        corpus_rows.append(
            {
                "id": str(source["doc_id"]),
                "scope_id": "__global__",
                "ingest_role": "source_document",
                "path": str(pdf),
                "media": ["pdf"],
                "sha256": actual_hash,
                "pages": int(source["pdf_pages"]),
                "metadata": {
                    "source_file": source["source_file"],
                    "family": source.get("family"),
                    "document_kind": source.get("document_kind"),
                    "language": source.get("language"),
                    "pages": int(source["pdf_pages"]),
                    "source_snapshot": source.get("source_snapshot"),
                },
            }
        )

    question_rows = [build_question_row(row) for row in formal_rows]
    manifest = {
        "schema": "competitor-eval-ready-v1",
        "dataset": "lenovo-bench",
        "revision": "moi-corpus-100q-v1",
        "split": "formal",
        "protocol_tag": "LENOVO_BENCH_FORMAL_NATIVE_PDF_V1",
        "condition": "native_pdf",
        "scope": "global",
        "ingest_representation": "source_document",
        "documents": "corpus.jsonl",
        "questions": "questions.jsonl",
        "document_count": 46,
        "page_count": 1104,
        "question_count": 60,
        "parser": "dify_native_pdf",
        "chunking": "dify_custom_separator_newline_max_tokens_512_overlap_64",
        "embedding": "dify_configured_qianfan_bge_m3",
        "retriever": "platform_native_semantic",
        "reranker": "disabled",
        "prompt_hash": "dify_native_default_chat_prompt_v1",
        "latency_mode": "warm",
        "context_budget": "dify_native_default",
        "citation_required": True,
        "metric_contract": {
            "primary_split": "formal",
            "answerability": "answerability_accuracy_over_all_60_cases",
            "retrieval": "evidence_set_recall_at_1_3_5_10_and_mrr",
            "answer": "claim_recall_and_answerable_answer_quality; unanswerable_abstention",
            "citation": "citation_precision_recall_and_required_metadata_completeness",
            "latency": "retrieval_and_native_qa_latency_p50_p95",
            "runner_note": "generic runner metrics are retained; Lenovo-specific metrics are computed post-hoc from the formal gold contract",
        },
        "source_inputs": {
            "dataset_root": str(dataset),
            "corpus_manifest": str(dataset / "moi-corpus-100q-v1" / "corpus_manifest.jsonl"),
            "questions_formal": str(formal_path),
            "mineru_documents": str(mineru),
            "mineru_documents_sha256": sha256_file(mineru),
            "corpus_combined_sha256": profile["corpus_combined_sha256"],
        },
    }

    write_jsonl(package_root / "corpus.jsonl", corpus_rows)
    write_jsonl(package_root / "questions.jsonl", question_rows)
    write_json(package_root / "manifest.json", manifest)
    write_jsonl(audit_root / "prepared-pages.jsonl", pages)
    write_json(
        audit_root / "parse-profile.json",
        {
            "schema": "lenovo-bench-page-audit-v1",
            "created_at": utc_now(),
            "dataset": "lenovo-bench",
            "split": "formal",
            "source_representation_for_dify": "original_pdf",
            "formal_question_count": len(formal_rows),
            **profile,
        },
    )
    write_json(
        run_root / "preparation.json",
        {
            "schema": "dify-lenovo-bench-preparation-v1",
            "created_at": utc_now(),
            "package": str(package_root),
            "manifest": str(package_root / "manifest.json"),
            "corpus_records": len(corpus_rows),
            "formal_questions": len(question_rows),
            "formal_answerable": sum(row.get("answerability") == "answerable" for row in formal_rows),
            "formal_unanswerable": sum(row.get("answerability") == "unanswerable" for row in formal_rows),
            "page_audit_records": len(pages),
            "page_audit": str(audit_root / "prepared-pages.jsonl"),
            "parse_profile": str(audit_root / "parse-profile.json"),
            "dify_ingest_mode": "46 original PDFs uploaded as one global source-document dataset",
            "mineru_role": "audit/fallback text for the scanned Anti-Slavery PDF; not substituted for native PDF upload",
        },
    )
    print(json.dumps({"run_root": str(run_root), "package": str(package_root), **profile, "formal_questions": len(question_rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
