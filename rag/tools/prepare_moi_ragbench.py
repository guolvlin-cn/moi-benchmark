#!/usr/bin/env python3
"""Prepare downloaded RAGBench data for the local MatrixFlow/MOI path.

The public EnterpriseRAG-Bench mirror is a Parquet table rather than a file
corpus, so this adapter materializes a reproducible document sample as
Markdown.  FAB-Bench publishes the questions and selected evidence snippets,
but not its complete source corpus; this adapter therefore materializes only
the public Gold Context snippets and marks that boundary in the manifest.

When ``--parser-bin`` is supplied, each materialized Markdown file is parsed
with the local ``local-matrixflow-parser`` binary and the standard documents
are combined into ``parsed-documents.jsonl``.  That file can be passed to
``local-matrixflow-rag pipeline --documents`` to exercise the product split,
multi-level index, embedding, and MatrixOne retrieval stages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_VERSION = "1.1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    name = name.strip("._") or "document"
    return name[:180]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected an object at {path}:{line_number}")
            rows.append(value)
    return rows


def enterprise_questions(path: Path, question_limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    all_questions = read_jsonl(path)
    selected = all_questions if question_limit <= 0 else all_questions[:question_limit]
    required_ids: list[str] = []
    for question in selected:
        for doc_id in question.get("expected_doc_ids") or []:
            doc_id = str(doc_id)
            if doc_id and doc_id not in required_ids:
                required_ids.append(doc_id)
    return selected, required_ids


def materialize_enterprise(
    parquet_path: Path,
    questions_path: Path,
    output_root: Path,
    question_limit: int,
) -> dict[str, Any]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment diagnostic
        raise RuntimeError("EnterpriseRAG preparation requires pyarrow") from exc

    selected_questions, required_ids = enterprise_questions(questions_path, question_limit)
    parquet = pq.ParquetFile(parquet_path)
    found: dict[str, dict[str, Any]] = {}
    required = set(required_ids)
    for batch in parquet.iter_batches(
        batch_size=8192,
        columns=["doc_id", "source_type", "title", "content"],
    ):
        for row in batch.to_pylist():
            doc_id = str(row.get("doc_id") or "")
            if doc_id in required:
                found[doc_id] = row
        if len(found) == len(required):
            break
    missing = [doc_id for doc_id in required_ids if doc_id not in found]
    if missing:
        raise RuntimeError(f"EnterpriseRAG document ids missing from Parquet: {missing[:5]}")

    dataset_root = output_root / "enterprise-rag-bench"
    corpus_root = dataset_root / "corpus"
    corpus_root.mkdir(parents=True, exist_ok=True)
    doc_files: dict[str, str] = {}
    doc_manifest: list[dict[str, Any]] = []
    for doc_id in required_ids:
        row = found[doc_id]
        filename = safe_name(doc_id) + ".md"
        doc_files[doc_id] = filename
        title = str(row.get("title") or doc_id).strip()
        source_type = str(row.get("source_type") or "unknown").strip()
        content = str(row.get("content") or "").strip()
        markdown = (
            "# EnterpriseRAG-Bench document\n\n"
            f"- dataset_doc_id: `{doc_id}`\n"
            f"- source_type: `{source_type}`\n"
            f"- title: {title}\n\n"
            "## Source content\n\n"
            f"{content}\n"
        )
        path = corpus_root / filename
        path.write_text(markdown, encoding="utf-8")
        doc_manifest.append(
            {
                "doc_id": doc_id,
                "file_name": filename,
                "title": title,
                "source_type": source_type,
                "content_chars": len(content),
                "materialized_chars": len(markdown),
                "materialized_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            }
        )

    question_rows: list[dict[str, Any]] = []
    for question in selected_questions:
        relevant_documents = [doc_files[str(doc_id)] for doc_id in question.get("expected_doc_ids") or []]
        question_rows.append(
            {
                "id": question.get("question_id"),
                "question": question.get("question", ""),
                "retrieval_keywords": [question.get("question", "")],
                "relevant_documents": relevant_documents,
                "relevant_evidence": question.get("answer_facts") or [],
                "expected_answer_keywords": [],
                "expected_answerable": True,
                "metadata": {
                    "dataset": "EnterpriseRAG-Bench",
                    "question_type": question.get("question_type"),
                    "source_types": question.get("source_types"),
                    "gold_answer": question.get("gold_answer"),
                    "expected_doc_ids": question.get("expected_doc_ids"),
                },
            }
        )
    write_jsonl(dataset_root / "questions.jsonl", question_rows)
    write_jsonl(dataset_root / "gold-questions.jsonl", selected_questions)
    manifest = {
        "schema_version": "moi-ragbench-prepared-v1",
        "created_at": now_utc(),
        "adapter_version": SCRIPT_VERSION,
        "dataset": "EnterpriseRAG-Bench",
        "source": {
            "parquet": str(parquet_path),
            "parquet_sha256": sha256_file(parquet_path),
            "parquet_rows": parquet.metadata.num_rows,
            "questions": str(questions_path),
            "questions_sha256": sha256_file(questions_path),
        },
        "selection": {
            "question_limit": question_limit,
            "selected_questions": len(selected_questions),
            "selected_documents": len(doc_manifest),
        },
        "representation": "The Parquet text rows are wrapped as Markdown so the local MatrixFlow text/Markdown parser can consume them. This is not a PDF/OCR parse.",
        "documents": doc_manifest,
    }
    write_json(dataset_root / "source-manifest.json", manifest)
    (dataset_root / "README.md").write_text(
        "# EnterpriseRAG-Bench / local MOI preparation\n\n"
        "This directory is a reproducible representative slice of the official Parquet corpus. "
        "It preserves source `doc_id` values and question-to-document gold links. The full corpus "
        "has 511,962 rows; run the adapter with a larger question limit when a larger local run is intended.\n\n"
        "The materialized Markdown is consumed by MatrixFlow Parse V3 Native and is not a claim that "
        "the remote web `standard_rag` V2 parser was executed.\n",
        encoding="utf-8",
    )
    return {"root": dataset_root, "files": [corpus_root / x["file_name"] for x in doc_manifest]}


def fab_questions(fab_root: Path) -> list[dict[str, Any]]:
    files = sorted(path for path in (fab_root / "QAs").rglob("*.json") if path.name != "_benchmark_summary.json")
    if not files:
        raise RuntimeError(f"no FAB-Bench QA JSON files under {fab_root / 'QAs'}")
    return [json.loads(path.read_text(encoding="utf-8")) for path in files]


def materialize_fab(fab_root: Path, output_root: Path) -> dict[str, Any]:
    cases = fab_questions(fab_root)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for case in cases:
        for source in case.get("gold_context_sources") or []:
            doc_id = str(source.get("doc_id") or "unknown")
            evidence = str(source.get("evidence") or "").strip()
            section = str(source.get("section_title") or "Evidence").strip()
            key = (section, evidence)
            if evidence and key not in seen[doc_id]:
                seen[doc_id].add(key)
                grouped[doc_id].append(
                    {
                        "section_title": section,
                        "evidence": evidence,
                        "has_image": bool(source.get("has_image", False)),
                    }
                )

    dataset_root = output_root / "fab-bench"
    corpus_root = dataset_root / "corpus"
    corpus_root.mkdir(parents=True, exist_ok=True)
    doc_files: dict[str, str] = {}
    doc_manifest: list[dict[str, Any]] = []
    for doc_id in sorted(grouped):
        filename = safe_name(doc_id) + ".md"
        doc_files[doc_id] = filename
        blocks = [
            "# FAB-Bench public Gold Context\n\n",
            f"- dataset_doc_id: `{doc_id}`\n",
            "- source_status: `public_evidence_only`\n\n",
        ]
        for index, source in enumerate(grouped[doc_id], 1):
            blocks.append(f"## {source['section_title']} (evidence {index})\n\n")
            blocks.append(source["evidence"] + "\n\n")
        markdown = "".join(blocks)
        (corpus_root / filename).write_text(markdown, encoding="utf-8")
        doc_manifest.append(
            {
                "doc_id": doc_id,
                "file_name": filename,
                "evidence_blocks": len(grouped[doc_id]),
                "materialized_chars": len(markdown),
                "materialized_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            }
        )

    question_rows: list[dict[str, Any]] = []
    for case in cases:
        sources = case.get("gold_context_sources") or []
        doc_ids = []
        evidence: list[str] = []
        for source in sources:
            doc_id = str(source.get("doc_id") or "")
            if doc_id and doc_id not in doc_ids:
                doc_ids.append(doc_id)
            snippet = str(source.get("evidence") or "").strip()
            if snippet and snippet not in evidence:
                evidence.append(snippet)
        question_rows.append(
            {
                "id": case.get("test_id"),
                "question": case.get("question", ""),
                "retrieval_keywords": [case.get("question", "")],
                "relevant_documents": [doc_files[doc_id] for doc_id in doc_ids],
                "relevant_evidence": evidence,
                "expected_answer_keywords": [],
                "expected_answerable": True,
                "metadata": {
                    "dataset": "FAB-Bench",
                    "test_type": case.get("test_type"),
                    "question_format": case.get("question_format"),
                    "source_chapter": case.get("source_chapter"),
                    "primary_metric": case.get("primary_metric"),
                    "ground_truth_answer": case.get("ground_truth_answer"),
                    "source_status": "public_evidence_only",
                },
            }
        )
    write_jsonl(dataset_root / "questions.jsonl", question_rows)
    write_jsonl(dataset_root / "gold-questions.jsonl", cases)
    manifest = {
        "schema_version": "moi-ragbench-prepared-v1",
        "created_at": now_utc(),
        "adapter_version": SCRIPT_VERSION,
        "dataset": "FAB-Bench",
        "source": {"repo": str(fab_root), "qa_cases": len(cases)},
        "selection": {
            "selected_questions": len(cases),
            "selected_documents": len(doc_manifest),
            "evidence_blocks": sum(x["evidence_blocks"] for x in doc_manifest),
        },
        "representation": "Only the 200 public question files' gold_context_sources are materialized. The complete FAB-Bench source corpus is not included in the public repository, so this is not a full-corpus ingestion.",
        "documents": doc_manifest,
    }
    write_json(dataset_root / "source-manifest.json", manifest)
    (dataset_root / "README.md").write_text(
        "# FAB-Bench / local MOI preparation\n\n"
        "This corpus contains the public Gold Context evidence snippets grouped by source `doc_id`. "
        "The complete FAB-Bench source corpus is not published in the repository; do not interpret this "
        "as full-corpus parsing.\n\n"
        "The snippets are Markdown and can be consumed by MatrixFlow Parse V3 Native and the local "
        "MatrixOne RAG path.\n",
        encoding="utf-8",
    )
    return {"root": dataset_root, "files": [corpus_root / x["file_name"] for x in doc_manifest]}


def parser_run_dir(stdout: str) -> Path:
    for line in stdout.splitlines():
        if line.startswith("run_dir="):
            return Path(line[len("run_dir=") :].strip())
    raise RuntimeError(f"parser output did not contain run_dir: {stdout[-500:]}")


def run_parser(parser_bin: Path, dataset_root: Path, files: list[Path], dataset_name: str, output_root: Path) -> dict[str, Any]:
    parse_root = output_root / dataset_name / "parser-runs"
    combined_path = output_root / dataset_name / "parsed-documents.jsonl"
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    combined: list[dict[str, Any]] = []
    for index, source in enumerate(sorted(files), 1):
        result = subprocess.run(
            [
                str(parser_bin),
                "parse",
                "--input",
                str(source),
                "--profile",
                "v3-native",
                "--run",
                str(parse_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"MatrixFlow parser failed for {source} (exit {result.returncode}): {result.stderr[-2000:]}"
            )
        run_dir = parser_run_dir(result.stdout)
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        summaries.append(summary)
        documents_path = run_dir / "documents.jsonl"
        for document in read_jsonl(documents_path):
            metadata = document.setdefault("metadata", {})
            metadata["benchmark_dataset"] = dataset_name
            metadata["benchmark_source_file"] = source.name
            combined.append(document)
        if index == 1 or index == len(files) or index % 25 == 0:
            print(f"parsed {dataset_name} {index}/{len(files)}", flush=True)
    write_jsonl(combined_path, combined)
    backend_counts: dict[str, int] = defaultdict(int)
    route_counts: dict[str, int] = defaultdict(int)
    for summary in summaries:
        backend_counts[str(summary.get("backend_used", "unknown"))] += 1
        route_counts[str(summary.get("route", "unknown"))] += 1
    result = {
        "schema_version": "moi-ragbench-parse-run-v1",
        "created_at": now_utc(),
        "dataset": dataset_name,
        "parser_binary": str(parser_bin),
        "parser_profile": "v3-native",
        "web_equivalent": False,
        "route_counts": dict(route_counts),
        "backend_counts": dict(backend_counts),
        "input_files": len(files),
        "output_documents": len(combined),
        "content_chars": sum(len(str(document.get("content", ""))) for document in combined),
        "duration_ms_sum": round(sum(float(summary.get("duration_ms", 0)) for summary in summaries), 3),
        "per_file": summaries,
        "combined_documents": str(combined_path),
    }
    write_json(output_root / dataset_name / "parse-summary.json", result)
    return result


def export_moi_ready(
    prepared_root: Path,
    moi_ready_root: Path,
    parse_result: dict[str, Any],
    dataset_label: str,
) -> dict[str, Any]:
    """Export the stable parser boundary in the repository's moi-ready-v1 shape."""

    ready_root = moi_ready_root / dataset_label
    ready_root.mkdir(parents=True, exist_ok=True)
    parsed_path = prepared_root / "parsed-documents.jsonl"
    if not parsed_path.is_file():
        raise FileNotFoundError(f"parsed documents not found: {parsed_path}")

    # Keep the parser block content and metadata, but promote a stable block
    # identity to the same top-level shape used by other moi-ready-v1 exports.
    normalized_rows: list[dict[str, Any]] = []
    for fallback_index, row in enumerate(read_jsonl(parsed_path)):
        metadata = dict(row.get("metadata") or {})
        file_id = str(metadata.get("file_id") or metadata.get("raw_file_id") or "")
        document_index = metadata.get("document_index", fallback_index)
        try:
            document_index = int(document_index)
        except (TypeError, ValueError):
            document_index = fallback_index
        block_uuid = str(metadata.get("block_uuid") or f"block-{document_index}")
        stable_block_uuid = f"{file_id or 'local'}-{block_uuid}"
        metadata["moi_ready_dataset"] = dataset_label
        metadata["moi_ready_schema"] = "moi-ready-v1"
        metadata["moi_ready_block_uuid"] = stable_block_uuid
        normalized_rows.append(
            {
                "block_uuid": stable_block_uuid,
                "content": str(row.get("content") or ""),
                "document_index": document_index,
                "metadata": metadata,
                "type": str(row.get("type") or "text"),
            }
        )
    moi_documents_path = ready_root / "moi-documents.jsonl"
    write_jsonl(moi_documents_path, normalized_rows)

    prepared_source_manifest_path = prepared_root / "source-manifest.json"
    prepared_source_manifest = (
        json.loads(prepared_source_manifest_path.read_text(encoding="utf-8"))
        if prepared_source_manifest_path.is_file()
        else {}
    )
    per_file = parse_result.get("per_file") or []
    manifest_rows: list[dict[str, Any]] = []
    for index, summary in enumerate(per_file):
        source_path = str(summary.get("source_path") or "")
        source_name = Path(source_path).name or f"source-{index:06d}.md"
        manifest_rows.append(
            {
                "schema_version": "moi-ready-v1",
                "status": "ok",
                "dataset": dataset_label,
                "document_id": Path(source_name).stem,
                "source_path": source_path,
                "source_file_name": source_name,
                "source_sha256": next(
                    (
                        str(item.get("materialized_sha256"))
                        for item in prepared_source_manifest.get("documents", [])
                        if str(item.get("file_name")) == source_name
                    ),
                    None,
                ),
                "documents": int(summary.get("documents") or 0),
                "content_chars": int(summary.get("content_chars") or 0),
                "backend_used": summary.get("backend_used"),
                "parser_version": summary.get("parser_version"),
                "route": summary.get("route"),
                "web_equivalent": bool(summary.get("web_equivalent", False)),
                "moi_documents_path": str(moi_documents_path),
            }
        )
    write_jsonl(ready_root / "manifest.jsonl", manifest_rows)

    for filename in ("questions.jsonl", "gold-questions.jsonl", "source-manifest.json"):
        source = prepared_root / filename
        if source.is_file():
            shutil.copy2(source, ready_root / filename)

    summary = {
        "schema_version": "moi-ready-v1",
        "created_at": now_utc(),
        "dataset": dataset_label,
        "status": "ready",
        "parser_profile": parse_result.get("parser_profile", "v3-native"),
        "parser_route": "moi:parse/v3/native",
        "web_equivalent": False,
        "planned_documents": len(manifest_rows),
        "successful_documents": sum(1 for row in manifest_rows if row["status"] == "ok"),
        "failed_documents": sum(1 for row in manifest_rows if row["status"] != "ok"),
        "moi_document_blocks": len(normalized_rows),
        "content_chars": sum(len(row["content"]) for row in normalized_rows),
        "backend_counts": parse_result.get("backend_counts", {}),
        "route_counts": parse_result.get("route_counts", {}),
        "moi_documents_path": str(moi_documents_path),
        "manifest_path": str(ready_root / "manifest.jsonl"),
        "source_representation": prepared_source_manifest.get("representation"),
    }
    write_json(ready_root / "summary.json", summary)
    (ready_root / "README.md").write_text(
        f"# {dataset_label} / MOI-ready v1\n\n"
        "This directory is the stable MatrixFlow parser boundary for local MOI/RAG ingestion.\n\n"
        "- parser profile: `v3-native`\n"
        "- route: `moi:parse/v3/native`\n"
        "- web equivalent: `false` (local V3 Native compatibility route)\n"
        f"- source files: {len(manifest_rows)}\n"
        f"- standard parser blocks: {len(normalized_rows)}\n\n"
        "Use `moi-documents.jsonl` as the `--documents` input to the local MatrixFlow RAG "
        "ingest stage. `manifest.jsonl` preserves one source-level record per input file.\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enterprise-parquet", type=Path, required=True)
    parser.add_argument("--enterprise-questions", type=Path, required=True)
    parser.add_argument("--fab-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--enterprise-question-limit",
        type=int,
        default=32,
        help="number of EnterpriseRAG questions whose gold documents are materialized; <=0 means all",
    )
    parser.add_argument("--parser-bin", type=Path, help="optional local-matrixflow-parser binary")
    parser.add_argument(
        "--moi-ready-root",
        type=Path,
        help="optional root for repository-style moi-ready-v1 exports",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    enterprise = materialize_enterprise(
        args.enterprise_parquet,
        args.enterprise_questions,
        args.out,
        args.enterprise_question_limit,
    )
    fab = materialize_fab(args.fab_root, args.out)
    parse_runs: dict[str, Any] = {}
    if args.parser_bin:
        parser_bin = args.parser_bin.resolve()
        if not parser_bin.is_file():
            raise FileNotFoundError(f"parser binary not found: {parser_bin}")
        parse_runs["enterprise-rag-bench"] = run_parser(
            parser_bin,
            enterprise["root"],
            enterprise["files"],
            "enterprise-rag-bench",
            args.out,
        )
        parse_runs["fab-bench"] = run_parser(
            parser_bin,
            fab["root"],
            fab["files"],
            "fab-bench",
            args.out,
        )
        if args.moi_ready_root:
            export_moi_ready(
                args.out / "enterprise-rag-bench",
                args.moi_ready_root,
                parse_runs["enterprise-rag-bench"],
                "enterpriserag-bench",
            )
            export_moi_ready(
                args.out / "fab-bench",
                args.moi_ready_root,
                parse_runs["fab-bench"],
                "fab-bench",
            )
    write_json(
        args.out / "run-manifest.json",
        {
            "schema_version": "moi-ragbench-preparation-run-v1",
            "created_at": now_utc(),
            "adapter_version": SCRIPT_VERSION,
            "enterprise_root": str(enterprise["root"]),
            "fab_root": str(fab["root"]),
            "moi_ready_root": str(args.moi_ready_root) if args.moi_ready_root else None,
            "parse_runs": parse_runs,
            "next_step": "Pass each parsed-documents.jsonl to local-matrixflow-rag pipeline --documents for MatrixFlow split/index/embedding/retrieval.",
        },
    )
    print(json.dumps({"out": str(args.out), "parse_runs": list(parse_runs)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
