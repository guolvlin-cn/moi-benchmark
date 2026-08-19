#!/usr/bin/env python3
"""Prepare the full MultiHop-RAG corpus and a frozen stratified evaluation set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUESTION_TYPES = (
    "comparison_query",
    "inference_query",
    "temporal_query",
    "null_query",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return clean[:72] or "article"


def normalize_title(value: str) -> str:
    return " ".join(value.split())


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    if not isinstance(corpus, list) or len(corpus) != 609:
        raise ValueError(f"expected 609 corpus articles, got {len(corpus)}")

    upload = args.output / "upload-to-dify"
    upload.mkdir(parents=True, exist_ok=True)
    packed_upload = args.output / "upload-to-dify-packed"
    packed_upload.mkdir(parents=True, exist_ok=True)
    bundle_count = 40
    bundled_upload = args.output / "upload-to-dify-bundled-40"
    bundled_upload.mkdir(parents=True, exist_ok=True)
    title_to_file: dict[str, str] = {}
    documents: list[dict[str, Any]] = []
    packed_articles: list[str] = []
    for index, article in enumerate(corpus, 1):
        title = str(article["title"]).strip()
        filename = f"article-{index:04d}-{slug(title)}.md"
        normalized_title = normalize_title(title)
        if normalized_title in title_to_file:
            raise ValueError(f"duplicate corpus title: {title}")
        title_to_file[normalized_title] = filename
        metadata = [
            f"# {title}",
            "",
            f"- Source: {article.get('source') or 'Unknown'}",
            f"- Author: {article.get('author') or 'Unknown'}",
            f"- Published at: {article.get('published_at') or 'Unknown'}",
            f"- Category: {article.get('category') or 'Unknown'}",
            f"- URL: {article.get('url') or 'Unknown'}",
            "",
            str(article.get("body") or "").strip(),
            "",
        ]
        content = "\n".join(metadata)
        packed_articles.append(
            f"<!-- ARTICLE {index:04d} START -->\n{content}"
            f"<!-- ARTICLE {index:04d} END -->\n"
        )
        path = upload / filename
        path.write_text(content, encoding="utf-8")
        documents.append(
            {
                "article_index": index - 1,
                "title": title,
                "filename": filename,
                "sha256": sha256_bytes(content.encode("utf-8")),
                "bytes": len(content.encode("utf-8")),
                "source_url": article.get("url"),
            }
        )

    selected: list[dict[str, Any]] = []
    selection: dict[str, list[dict[str, str]]] = {}
    for question_type in QUESTION_TYPES:
        group = [row for row in questions if row.get("question_type") == question_type]
        ranked = sorted(
            group,
            key=lambda row: sha256_bytes(str(row["query"]).encode("utf-8")),
        )
        chosen = ranked[:5]
        selection[question_type] = [
            {
                "query_sha256": sha256_bytes(str(row["query"]).encode("utf-8")),
                "query": str(row["query"]),
            }
            for row in chosen
        ]
        for row in chosen:
            evidence = list(row.get("evidence_list") or [])
            missing = [
                item.get("title")
                for item in evidence
                if normalize_title(str(item.get("title") or "")) not in title_to_file
            ]
            if missing:
                raise ValueError(f"evidence titles absent from corpus: {missing}")
            digest = sha256_bytes(str(row["query"]).encode("utf-8"))
            is_null = question_type == "null_query"
            selected.append(
                {
                    "id": f"multihop-{question_type.removesuffix('_query')}-{digest[:12]}",
                    "question": row["query"],
                    "references": [row["answer"]],
                    "answerable": not is_null,
                    "refusal_keywords": (
                        ["insufficient", "cannot answer", "unable to answer", "无法回答", "资料不足"]
                        if is_null
                        else []
                    ),
                    # Packed ingestion preserves all evidence text and article boundaries,
                    # but Dify exposes one physical document name. Match retrieval against
                    # frozen evidence spans rather than pretending physical document IDs.
                    "gold_document_names": [],
                    "gold_evidence": [str(item["fact"]) for item in evidence],
                    "question_type": question_type,
                    "query_sha256": digest,
                    "evidence_sources": [
                        {
                            "title": item["title"],
                            "document_name": title_to_file[normalize_title(item["title"])],
                            "fact": item["fact"],
                            "url": item.get("url"),
                            "published_at": item.get("published_at"),
                        }
                        for item in evidence
                    ],
                    "selection_rule": (
                        "group by question_type; sort by SHA256(query) ascending; take first 5"
                    ),
                }
            )

    selected.sort(key=lambda row: (QUESTION_TYPES.index(row["question_type"]), row["query_sha256"]))
    questions_path = args.output / "questions.jsonl"
    questions_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in selected
        ),
        encoding="utf-8",
    )
    (args.output / "questions-chatflow-diagnostic-smoke.jsonl").write_text(
        json.dumps(selected[0], ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dump_json(args.output / "corpus-manifest.json", {"documents": documents})
    packed_path = packed_upload / "multihop-rag-corpus-609-full-articles.md"
    packed_path.write_text(
        "# MultiHop-RAG corpus: 609 full articles\n\n"
        + "\n\n".join(packed_articles),
        encoding="utf-8",
    )
    bundle_records: list[dict[str, Any]] = []
    for bundle_index in range(bundle_count):
        start = bundle_index * len(packed_articles) // bundle_count
        end = (bundle_index + 1) * len(packed_articles) // bundle_count
        bundle_path = bundled_upload / (
            f"multihop-rag-bundle-{bundle_index + 1:02d}"
            f"-articles-{start + 1:04d}-{end:04d}.md"
        )
        bundle_path.write_text(
            f"# MultiHop-RAG bundle {bundle_index + 1:02d}: "
            f"articles {start + 1}–{end}\n\n"
            + "\n\n".join(packed_articles[start:end]),
            encoding="utf-8",
        )
        bundle_records.append(
            {
                "path": str(bundle_path.resolve()),
                "sha256": sha256_file(bundle_path),
                "bytes": bundle_path.stat().st_size,
                "article_start": start + 1,
                "article_end": end,
                "articles": end - start,
            }
        )
    dump_json(args.output / "selection-freeze.json", selection)
    dump_json(
        args.output / "manifest.json",
        {
            "schema_version": "multihop-rag-dify-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": str(Path(__file__).resolve()),
            "generator_sha256": sha256_file(Path(__file__)),
            "source": {
                "corpus": str(args.corpus.resolve()),
                "corpus_sha256": sha256_file(args.corpus),
                "questions": str(args.questions.resolve()),
                "questions_sha256": sha256_file(args.questions),
            },
            "documents": len(documents),
            "packed_upload": {
                "path": str(packed_path.resolve()),
                "sha256": sha256_file(packed_path),
                "bytes": packed_path.stat().st_size,
                "articles": len(documents),
                "reason": "Dify subscription document-count quota",
            },
            "bundled_upload_40": {
                "documents": bundle_records,
                "articles": sum(item["articles"] for item in bundle_records),
                "reason": (
                    "non-destructive recovery after the single packed document "
                    "remained indexing with 0/0 segments for 30 minutes"
                ),
            },
            "questions": len(selected),
            "question_type_counts": Counter(
                row["question_type"] for row in selected
            ),
            "selection_rule": (
                "group MultiHopRAG.json by question_type; sort each group by "
                "SHA256(query) ascending; take 5 from comparison_query, "
                "inference_query, temporal_query, null_query"
            ),
            "questions_sha256": sha256_file(questions_path),
            "corpus_manifest_sha256": sha256_file(
                args.output / "corpus-manifest.json"
            ),
        },
    )
    print(f"prepared {len(documents)} documents and {len(selected)} questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
