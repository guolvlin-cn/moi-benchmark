#!/usr/bin/env python3
"""Prepare a small Dify-uploadable corpus and eval JSONL from RAGBench."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def document_index(sentence_key: str) -> int | None:
    match = re.match(r"^(\d+)", sentence_key)
    return int(match.group(1)) if match else None


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be positive")
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("pyarrow is required: python -m pip install pyarrow") from exc

    rows = pq.read_table(args.input).to_pylist()
    selected = [
        row
        for row in rows
        if row.get("adherence_score") is True
        and row.get("all_relevant_sentence_keys")
        and row.get("documents")
    ][: args.limit]
    if len(selected) < args.limit:
        raise SystemExit(
            f"only {len(selected)} eligible rows; requested {args.limit}"
        )

    corpus_dir = args.output / "upload-to-dify"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    document_names: dict[str, str] = {}
    cases: list[dict[str, Any]] = []

    for row in selected:
        row_document_names: list[str] = []
        for document in row["documents"]:
            digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
            name = document_names.setdefault(digest, f"doc-{digest[:16]}.md")
            destination = corpus_dir / name
            if not destination.exists():
                destination.write_text(
                    "# RAGBench source context\n\n" + document.strip() + "\n",
                    encoding="utf-8",
                )
            row_document_names.append(name)

        relevant_keys = set(row["all_relevant_sentence_keys"])
        relevant_indices = sorted(
            {
                index
                for key in relevant_keys
                if (index := document_index(key)) is not None
                and index < len(row_document_names)
            }
        )
        sentences_by_key = {
            sentence_key: sentence
            for document in row.get("documents_sentences") or []
            for sentence_key, sentence in document
        }
        cases.append(
            {
                "id": str(row["id"]),
                "question": row["question"],
                "references": [row["response"]],
                "required_keywords": [],
                "answerable": True,
                "gold_document_names": [
                    row_document_names[index] for index in relevant_indices
                ],
                "gold_evidence": [
                    sentences_by_key[key]
                    for key in row["all_relevant_sentence_keys"]
                    if key in sentences_by_key
                ],
                "tags": [
                    "ragbench",
                    str(row.get("dataset_name") or args.input.parent.name),
                    "smoke",
                ],
                "metadata": {
                    "source_split": args.input.stem.split("-")[0],
                    "reference_is_ragbench_generated_response": True,
                    "ragbench_adherence_score": row["adherence_score"],
                },
            }
        )

    with (args.output / "questions.jsonl").open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(
                json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n"
            )

    manifest = {
        "source": str(args.input.resolve()),
        "selected_cases": len(cases),
        "unique_upload_documents": len(document_names),
        "selection": (
            "first rows with adherence_score=true and non-empty relevant evidence"
        ),
        "limitations": [
            "RAGBench response is a generated response, not a canonical gold answer.",
            "The corpus is reconstructed from per-example retrieved documents.",
            "Use this package for pipeline smoke testing, not decision-grade ranking.",
        ],
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"prepared {len(cases)} cases and {len(document_names)} unique documents "
        f"under {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
