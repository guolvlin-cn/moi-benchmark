#!/usr/bin/env python3
"""Prepare MMDocIR's official page/layout candidates for MOI retrieval.

This adapter intentionally preserves the benchmark's document-local candidate
ranges and evidence locators.  It does not use the previously parsed PDF
chunks, because those chunks do not retain the page/layout identity required by
the official scorer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq


DOMAINS = [
    "Research report / Introduction",
    "Administration/Industry file",
    "Tutorial/Workshop",
    "Academic paper",
    "Brochure",
    "Financial report",
    "Guidebook",
    "Government",
    "Laws",
    "News",
]


def canonical_doc_name(doc_name: str) -> str:
    name = Path(doc_name).name
    return name[:-4] if name.lower().endswith(".pdf") else name


def file_id(doc_name: str) -> str:
    digest = hashlib.sha256(canonical_doc_name(doc_name).encode("utf-8")).hexdigest()[:24]
    return f"mmdocir_doc_{digest}"


def clean_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def read_annotations(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def choose_queries(rows: list[dict[str, Any]], sample_queries: int, seed: int) -> tuple[set[int], set[str]]:
    if sample_queries <= 0:
        query_count = sum(len(row["questions"]) for row in rows)
        return set(range(query_count)), {canonical_doc_name(row["doc_name"]) for row in rows}
    rng = random.Random(seed)
    by_domain: dict[str, list[tuple[int, str]]] = {domain: [] for domain in DOMAINS}
    query_id = 0
    for row in rows:
        for _ in row["questions"]:
            by_domain.setdefault(row["domain"], []).append((query_id, canonical_doc_name(row["doc_name"])))
            query_id += 1
    selected: list[tuple[int, str]] = []
    active = [domain for domain in DOMAINS if by_domain.get(domain)]
    while len(selected) < sample_queries and active:
        next_active: list[str] = []
        for domain in active:
            pool = by_domain[domain]
            if not pool:
                continue
            pick = rng.randrange(len(pool))
            selected.append(pool.pop(pick))
            if pool:
                next_active.append(domain)
            if len(selected) >= sample_queries:
                break
        active = next_active
    return {query_id for query_id, _ in selected}, {doc_name for _, doc_name in selected}


def iter_questions(rows: list[dict[str, Any]], selected_queries: set[int]) -> Iterable[dict[str, Any]]:
    query_id = 0
    for row in rows:
        for qa in row["questions"]:
            if query_id in selected_queries:
                yield {
                    "id": f"mmdocir_q_{query_id:04d}",
                    "query_index": query_id,
                    "question": qa["Q"],
                    "answer": qa.get("A"),
                    "domain": row["domain"],
                    "doc_name": row["doc_name"],
                    "file_id": file_id(row["doc_name"]),
                    "page_ids": qa["page_id"],
                    "layout_mapping": qa["layout_mapping"],
                    "evidence_type": qa.get("type"),
                }
            query_id += 1


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def prepare(args: argparse.Namespace) -> None:
    data = args.data.resolve()
    output = args.output.resolve()
    annotations = read_annotations(data / "MMDocIR_annotations.jsonl")
    selected_queries, selected_docs = choose_queries(annotations, args.sample_queries, args.seed)

    question_count = write_jsonl(output / "questions.jsonl", iter_questions(annotations, selected_queries))

    pages = pq.read_table(
        data / "MMDocIR_pages.parquet",
        columns=["doc_name", "domain", "passage_id", "image_path", "ocr_text", "vlm_text"],
    ).to_pylist()

    def page_rows() -> Iterable[dict[str, Any]]:
        for row_index, row in enumerate(pages):
            if canonical_doc_name(row["doc_name"]) not in selected_docs:
                continue
            page_id = int(row["passage_id"])
            yield {
                "id": f"mmdocir_page_{row_index}",
                "file_id": file_id(row["doc_name"]),
                "content": clean_text(row["vlm_text"], row["ocr_text"]),
                "page_number": page_id,
                "chunk_index": row_index,
                "metadata": {
                    "benchmark": "MMDocIR",
                    "granularity": "page",
                    "candidate_row": row_index,
                    "doc_name": row["doc_name"],
                    "domain": row["domain"],
                    "page_id": page_id,
                    "page_number": page_id,
                    "passage_id": row["passage_id"],
                    "image_path": row["image_path"],
                    "file_name": row["doc_name"],
                },
            }

    page_count = write_jsonl(output / "pages.jsonl", page_rows())
    page_docs = {canonical_doc_name(row["doc_name"]) for row in pages if canonical_doc_name(row["doc_name"]) in selected_docs}

    layouts = pq.read_table(
        data / "MMDocIR_layouts.parquet",
        columns=[
            "doc_name", "domain", "page_id", "layout_id", "type", "text",
            "ocr_text", "vlm_text", "bbox", "page_size", "image_path",
        ],
    ).to_pylist()

    def layout_rows() -> Iterable[dict[str, Any]]:
        for row_index, row in enumerate(layouts):
            if canonical_doc_name(row["doc_name"]) not in selected_docs:
                continue
            layout_type = str(row["type"] or "").lower()
            content = (
                clean_text(row["vlm_text"], row["ocr_text"], row["text"])
                if layout_type in {"table", "image"}
                else clean_text(row["text"], row["vlm_text"], row["ocr_text"])
            )
            yield {
                "id": f"mmdocir_layout_{row_index}",
                "file_id": file_id(row["doc_name"]),
                "content": content,
                "page_number": int(row["page_id"]),
                "chunk_index": row_index,
                "metadata": {
                    "benchmark": "MMDocIR",
                    "granularity": "layout",
                    "candidate_row": row_index,
                    "doc_name": row["doc_name"],
                    "domain": row["domain"],
                    "page_id": int(row["page_id"]),
                    "page_number": int(row["page_id"]),
                    "layout_id": int(row["layout_id"]),
                    "layout_type": row["type"],
                    "bbox": row["bbox"],
                    "page_size": row["page_size"],
                    "image_path": row["image_path"],
                    "file_name": row["doc_name"],
                },
            }

    layout_count = write_jsonl(output / "layouts.jsonl", layout_rows())
    layout_docs = {canonical_doc_name(row["doc_name"]) for row in layouts if canonical_doc_name(row["doc_name"]) in selected_docs}
    missing_pages = sorted(selected_docs - page_docs)
    missing_layouts = sorted(selected_docs - layout_docs)
    if question_count == 0 or page_count == 0 or layout_count == 0 or missing_pages or missing_layouts:
        raise RuntimeError(
            "prepared MMDocIR mapping is incomplete: "
            f"questions={question_count} pages={page_count} layouts={layout_count} "
            f"missing_page_docs={missing_pages} missing_layout_docs={missing_layouts}"
        )
    manifest = {
        "schema_version": "mmdocir-official-moi-v1",
        "source": str(data),
        "seed": args.seed,
        "requested_sample_queries": args.sample_queries,
        "selected_documents": len(selected_docs),
        "questions": question_count,
        "pages": page_count,
        "layouts": layout_count,
        "page_text_condition": "vlm_text, fallback ocr_text",
        "layout_text_condition": "official mixed text rule with non-empty fallbacks",
        "protocol": "document-local retrieval; official page/layout recall cutoffs",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-queries", type=int, default=0, help="0 selects the full set")
    parser.add_argument("--seed", type=int, default=20260806)
    prepare(parser.parse_args())


if __name__ == "__main__":
    main()
