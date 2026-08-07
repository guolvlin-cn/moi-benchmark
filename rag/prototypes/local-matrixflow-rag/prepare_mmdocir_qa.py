#!/usr/bin/env python3
"""Convert the official MMDocIR annotations to the native MOI QA schema.

The official MMDocIR release is a retrieval benchmark.  This adapter keeps
its reference answer and page/layout provenance in ``metadata`` while using
the existing local-rag ``run`` command to retrieve page evidence and generate
an answer.  It deliberately leaves ``expected_answer_keywords`` empty: the
official answers contain lists, percentages, and free-form strings, so a
simple substring score would be misleading.  The raw answer is preserved for
the later metric implementation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            yield value


def to_question_case(row: dict[str, Any]) -> dict[str, Any]:
    question = str(row.get("question", "")).strip()
    file_id = str(row.get("file_id", "")).strip()
    doc_name = str(row.get("doc_name", "")).strip()
    if not question or not file_id or not doc_name:
        raise ValueError(f"incomplete MMDocIR row: {row.get('id')!r}")
    metadata = {
        "benchmark": "MMDocIR",
        "benchmark_variant": "page_text_qa_diagnostic",
        "qa_scope": "page_text",
        "reference_answer": row.get("answer"),
        "domain": row.get("domain"),
        "doc_name": doc_name,
        "gold_page_ids": row.get("page_ids", []),
        "gold_layout_mapping": row.get("layout_mapping", []),
        "question_type": row.get("evidence_type"),
        "query_index": row.get("query_index"),
        "retrieval_table": "moi_stage1_mmdocir_official.pages_bge_m3_vlm",
        "retrieval_protocol": "MOI SearchRAGChunks; document-local page retrieval; top-10 evidence",
        "answer_evaluation": "deferred; retain raw reference and generated answer",
    }
    return {
        "id": str(row["id"]),
        "question": question,
        "retrieval_keywords": [question],
        "file_ids": [file_id],
        "relevant_documents": [doc_name],
        "relevant_evidence": [],
        "expected_answer_keywords": [],
        "expected_answerable": True,
        "metadata": metadata,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="prepared official MMDocIR questions.jsonl")
    parser.add_argument("--output", type=Path, required=True, help="native MOI QA questions.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="write only the first N questions; 0 means all")
    args = parser.parse_args()

    rows = [to_question_case(row) for row in read_jsonl(args.input)]
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("MMDocIR QA input is empty")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"questions": len(rows), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
