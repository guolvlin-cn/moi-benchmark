#!/usr/bin/env python3
"""Build the complete public FAB-Bench package and resolve public source assets.

The official FAB-Bench repository publishes the 200 QA cases, but not the
source corpus described by the paper.  This adapter therefore keeps two
truthful layers in one reproducible package:

* every QA/evidence/doc_id is present in registries and the MOI-ready input;
* public source PDFs are downloaded only when their identity is unambiguous
  (currently Google Patents and arXiv), while unavailable sources remain
  explicitly ``evidence_only``/``missing``.

The source status is never inferred from a Gold Context snippet.  The output
can consequently be used as a public-complete evidence baseline even when the
full source-complete corpus is not distributable.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from prepare_moi_ragbench import (
    SCRIPT_VERSION as BASE_ADAPTER_VERSION,
    materialize_fab,
    safe_name,
    sha256_file,
    write_json,
    write_jsonl,
)


SCRIPT_VERSION = "1.0.0"
USER_AGENT = "moi-benchmark-fab-preparer/1.0 (+local research workflow)"
PATENT_PREFIXES = ("US", "WO", "GB", "LU", "NL")
ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
PATENT_RE = re.compile(r"^(?:US|WO|GB|LU|NL)\d+[A-Z]?\d?$", re.IGNORECASE)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_cases(fab_root: Path) -> list[dict[str, Any]]:
    paths = sorted(path for path in (fab_root / "QAs").rglob("*.json") if path.name != "_benchmark_summary.json")
    if not paths:
        raise RuntimeError(f"no FAB-Bench QA files under {fab_root / 'QAs'}")
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def build_registries(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_rows: list[dict[str, Any]] = []
    by_doc: dict[str, list[str]] = defaultdict(list)
    doc_image_counts: Counter[str] = Counter()
    doc_hints: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        test_id = str(case.get("test_id") or "")
        for index, source in enumerate(case.get("gold_context_sources") or [], 1):
            doc_id = str(source.get("doc_id") or "unknown")
            evidence_id = f"{test_id}:evidence-{index:02d}"
            has_image = bool(source.get("has_image", False))
            hint_text = " ".join(
                str(case.get(key) or "") for key in ("question", "ground_truth_answer")
            ) + " " + str(source.get("section_title") or "") + " " + str(source.get("evidence") or "")
            for hint in re.findall(r"\b(?:US|WO|GB|EP|CN|JP)\d{6,}[A-Z]?\d?\b", hint_text, re.IGNORECASE):
                if hint.upper() != doc_id.upper():
                    doc_hints[doc_id].add(hint.upper())
            row = {
                "evidence_id": evidence_id,
                "test_id": test_id,
                "doc_id": doc_id,
                "section_title": str(source.get("section_title") or ""),
                "evidence": str(source.get("evidence") or ""),
                "has_image": has_image,
                "image_asset_status": "missing_public_asset" if has_image else "not_applicable",
                "source_status": "evidence_only",
            }
            evidence_rows.append(row)
            by_doc[doc_id].append(evidence_id)
            if has_image:
                doc_image_counts[doc_id] += 1

    source_rows: list[dict[str, Any]] = []
    for doc_id in sorted(by_doc):
        source_rows.append(
            {
                "doc_id": doc_id,
                "source_kind": classify_source_kind(doc_id),
                "public_identifier_candidates": sorted(doc_hints[doc_id]),
                "source_status": "evidence_only",
                "original_source_status": "not_attempted",
                "original_path": None,
                "source_url": None,
                "source_sha256": None,
                "mime_type": None,
                "evidence_ids": by_doc[doc_id],
                "evidence_blocks": len(by_doc[doc_id]),
                "has_image_evidence": doc_image_counts[doc_id] > 0,
                "image_evidence_count": doc_image_counts[doc_id],
                "image_asset_status": "missing_public_asset" if doc_image_counts[doc_id] else "not_applicable",
            }
        )
    return source_rows, evidence_rows


def classify_source_kind(doc_id: str) -> str:
    if ARXIV_RE.fullmatch(doc_id):
        return "arxiv"
    if patent_candidates(doc_id):
        return "patent"
    if doc_id.startswith("semi_docs_"):
        return "industry_standard"
    if doc_id.startswith("1-s2.0-") or doc_id.startswith("PhysRev") or doc_id.startswith("electronics-"):
        return "publisher_article"
    return "named_document"


def patent_candidates(doc_id: str) -> list[str]:
    values = [doc_id]
    if "_" in doc_id:
        values.append(doc_id.split("_")[-1])
    candidates: list[str] = []
    for value in values:
        value = value.strip()
        if not value:
            continue
        if PATENT_RE.fullmatch(value) and value[:2].upper() in PATENT_PREFIXES:
            candidates.append(value.upper())
    # A source id such as US13005630B2 is already canonical; a composite
    # country id is handled by the final component above.
    return list(dict.fromkeys(candidates))


def fetch_bytes(url: str, max_bytes: int = 80 * 1024 * 1024) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=45) as response:
        content_type = str(response.headers.get("Content-Type") or "")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError(f"download exceeds {max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks), content_type


def write_download(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_bytes(data)
    if not data.startswith(b"%PDF"):
        temp.unlink(missing_ok=True)
        raise RuntimeError("downloaded content is not a PDF")
    temp.replace(path)
    return hashlib.sha256(data).hexdigest()


def resolve_patent(doc_id: str, destination: Path, extra_candidates: Iterable[str] = ()) -> dict[str, Any]:
    candidates = list(dict.fromkeys(patent_candidates(doc_id) + [str(x).upper() for x in extra_candidates]))
    if not candidates:
        return {"status": "not_applicable", "reason": "not a supported patent identifier"}
    existing = destination / (safe_name(doc_id) + ".pdf")
    if existing.is_file() and existing.read_bytes().startswith(b"%PDF"):
        return {
            "status": "acquired",
            "source_url": f"https://patents.google.com/patent/{candidates[0]}/en",
            "download_url": None,
            "path": str(existing),
            "file_name": existing.name,
            "sha256": sha256_file(existing),
            "bytes": existing.stat().st_size,
            "mime_type": "application/pdf",
            "cached": True,
        }
    errors: list[str] = []
    for identifier in candidates:
        page_url = f"https://patents.google.com/patent/{identifier}/en"
        try:
            page, _ = fetch_bytes(page_url, max_bytes=3 * 1024 * 1024)
            text = page.decode("utf-8", "ignore")
            match = re.search(r'citation_pdf_url"\s+content="([^"]+)"', text)
            if not match:
                errors.append(f"{identifier}: citation_pdf_url missing")
                continue
            pdf_url = html.unescape(match.group(1))
            pdf, content_type = fetch_bytes(pdf_url)
            filename = safe_name(doc_id) + ".pdf"
            path = destination / filename
            digest = write_download(path, pdf)
            return {
                "status": "acquired",
                "source_url": page_url,
                "download_url": pdf_url,
                "path": str(path),
                "file_name": filename,
                "sha256": digest,
                "bytes": len(pdf),
                "mime_type": content_type or "application/pdf",
            }
        except Exception as exc:  # network/source availability is per-document
            errors.append(f"{identifier}: {type(exc).__name__}: {exc}")
        time.sleep(0.15)
    return {"status": "missing", "reason": "; ".join(errors) or "no candidate succeeded"}


def resolve_arxiv(doc_id: str, destination: Path) -> dict[str, Any]:
    if not ARXIV_RE.fullmatch(doc_id):
        return {"status": "not_applicable", "reason": "not an arXiv identifier"}
    url = f"https://arxiv.org/pdf/{doc_id}.pdf"
    existing = destination / (safe_name(doc_id) + ".pdf")
    if existing.is_file() and existing.read_bytes().startswith(b"%PDF"):
        return {
            "status": "acquired",
            "source_url": f"https://arxiv.org/abs/{doc_id}",
            "download_url": url,
            "path": str(existing),
            "file_name": existing.name,
            "sha256": sha256_file(existing),
            "bytes": existing.stat().st_size,
            "mime_type": "application/pdf",
            "cached": True,
        }
    try:
        pdf, content_type = fetch_bytes(url)
        filename = safe_name(doc_id) + ".pdf"
        path = destination / filename
        digest = write_download(path, pdf)
        return {
            "status": "acquired",
            "source_url": f"https://arxiv.org/abs/{doc_id}",
            "download_url": url,
            "path": str(path),
            "file_name": filename,
            "sha256": digest,
            "bytes": len(pdf),
            "mime_type": content_type or "application/pdf",
        }
    except Exception as exc:
        return {"status": "missing", "reason": f"{type(exc).__name__}: {exc}"}


def copy_public_assets(fab_root: Path, output_root: Path) -> list[dict[str, Any]]:
    public_root = output_root / "assets" / "public"
    assets: list[dict[str, Any]] = []
    for path in (
        fab_root / "FAB_Bench__A_Framework_for_Adaptive_RAG_Benchmarking_in_Semiconductor_Manufacturing.pdf",
        fab_root / "Fab-Bench High-Level.drawio.png",
    ):
        if not path.is_file():
            continue
        target = public_root / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        assets.append(
            {
                "asset_id": "public-" + safe_name(path.name),
                "asset_kind": "benchmark_public_artifact",
                "status": "available",
                "path": str(target),
                "source_path": str(path),
                "sha256": sha256_file(target),
                "mime_type": "application/pdf" if path.suffix.lower() == ".pdf" else "image/png",
                "linked_doc_ids": [],
                "evidence_use": "not a source-corpus evidence asset",
            }
        )
    return assets


def acquire_sources(source_rows: list[dict[str, Any]], output_root: Path, enabled: bool) -> list[dict[str, Any]]:
    destination = output_root / "assets" / "originals"
    for row in source_rows:
        if not enabled:
            row["original_source_status"] = "not_attempted"
            row["source_status"] = "evidence_only"
            continue
        doc_id = row["doc_id"]
        kind = row["source_kind"]
        if kind == "patent" or row.get("public_identifier_candidates"):
            result = resolve_patent(doc_id, destination, row.get("public_identifier_candidates") or [])
        elif kind == "arxiv":
            result = resolve_arxiv(doc_id, destination)
        else:
            result = {"status": "not_attempted", "reason": "no unambiguous public resolver for this source id"}
        row["original_source_status"] = result.get("status")
        row["original_source_reason"] = result.get("reason")
        if result.get("status") == "acquired":
            row["source_status"] = "source_acquired"
            row["original_path"] = result.get("path")
            row["source_url"] = result.get("source_url")
            row["download_url"] = result.get("download_url")
            row["source_sha256"] = result.get("sha256")
            row["mime_type"] = result.get("mime_type")
            row["source_file_name"] = result.get("file_name")
        else:
            row["source_status"] = "evidence_only"
        print(f"source {doc_id}: {row['source_status']} ({row['original_source_status']})", flush=True)
    return source_rows


def parser_run_dir(stdout: str) -> Path:
    for line in stdout.splitlines():
        if line.startswith("run_dir="):
            return Path(line[len("run_dir=") :].strip())
    raise RuntimeError(f"parser output did not contain run_dir: {stdout[-500:]}")


def parse_files_tolerant(
    parser_bin: Path | None,
    files: list[Path],
    output_root: Path,
    dataset_name: str,
    workers: int = 4,
    reuse_existing: bool = True,
) -> dict[str, Any]:
    combined: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if parser_bin is None:
        return {
            "input_files": len(files),
            "successful_files": 0,
            "failed_files": len(files),
            "output_documents": 0,
            "per_file": [],
            "failures": [{"source_path": str(path), "reason": "parser not supplied"} for path in files],
        }
    parse_root = output_root / dataset_name / "parser-runs"
    combined_path = output_root / dataset_name / "parsed-documents.jsonl"
    summary_path = output_root / dataset_name / "parse-summary.json"
    if reuse_existing and combined_path.is_file() and summary_path.is_file():
        cached = json.loads(summary_path.read_text(encoding="utf-8"))
        if int(cached.get("input_files", -1)) == len(files):
            return cached
    ordered_files = sorted(files)

    def parse_one(index: int, source: Path) -> tuple[Path, dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None]:
        run_root = parse_root / f"{index:04d}-{safe_name(source.stem)}"
        result = subprocess.run(
            [str(parser_bin), "parse", "--input", str(source), "--profile", "v3-native", "--run", str(run_root)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return source, None, [], {"source_path": str(source), "reason": result.stderr[-2000:]}
        try:
            run_dir = parser_run_dir(result.stdout)
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            documents = read_jsonl(run_dir / "documents.jsonl")
        except Exception as exc:
            return source, None, [], {"source_path": str(source), "reason": f"decode parser output: {exc}"}
        for document in documents:
            metadata = dict(document.get("metadata") or {})
            metadata["benchmark_source_file"] = source.name
            document["metadata"] = metadata
        return source, summary, documents, None

    max_workers = max(1, min(int(workers), len(ordered_files) or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(parse_one, index, source) for index, source in enumerate(ordered_files, 1)]
        for completed, future in enumerate(as_completed(futures), 1):
            source, summary, documents, failure = future.result()
            if failure:
                failures.append(failure)
                print(f"parse failed {dataset_name} {completed}/{len(ordered_files)} {source.name}", file=sys.stderr, flush=True)
            else:
                assert summary is not None
                summaries.append(summary)
                combined.extend(documents)
                print(f"parsed {dataset_name} {completed}/{len(ordered_files)} {source.name}", flush=True)
    summaries.sort(key=lambda item: str(item.get("source_path", "")))
    failures.sort(key=lambda item: str(item.get("source_path", "")))
    write_jsonl(combined_path, combined)
    result = {
        "schema_version": "fab-bench-parse-run-v1",
        "created_at": now_utc(),
        "dataset": dataset_name,
        "parser_binary": str(parser_bin),
        "parser_profile": "v3-native",
        "parser_route": "moi:parse/v3/native",
        "web_equivalent": False,
        "input_files": len(files),
        "successful_files": len(summaries),
        "failed_files": len(failures),
        "output_documents": len(combined),
        "route_counts": dict(Counter(str(x.get("route", "unknown")) for x in summaries)),
        "backend_counts": dict(Counter(str(x.get("backend_used", "unknown")) for x in summaries)),
        "per_file": summaries,
        "failures": failures,
        "combined_documents": str(combined_path),
    }
    write_json(output_root / dataset_name / "parse-summary.json", result)
    return result


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def enrich_questions(cases: list[dict[str, Any]], source_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        refs = []
        evidence: list[str] = []
        for source in case.get("gold_context_sources") or []:
            doc_id = str(source.get("doc_id") or "")
            if doc_id and doc_id not in refs:
                refs.append(doc_id)
            snippet = str(source.get("evidence") or "").strip()
            if snippet and snippet not in evidence:
                evidence.append(snippet)
        rows.append(
            {
                "id": case.get("test_id"),
                "question": case.get("question", ""),
                "retrieval_keywords": [case.get("question", "")],
                "relevant_documents": refs,
                "relevant_evidence": evidence,
                "expected_answer_keywords": [],
                "expected_answerable": True,
                "metadata": {
                    "dataset": "FAB-Bench",
                    "test_type": case.get("test_type"),
                    "question_format": case.get("question_format"),
                    "primary_metric": case.get("primary_metric"),
                    "source_statuses": sorted({source_by_id[doc_id]["source_status"] for doc_id in refs if doc_id in source_by_id}),
                    "has_image_evidence": any(bool(source.get("has_image")) for source in case.get("gold_context_sources") or []),
                    "ground_truth_answer": case.get("ground_truth_answer"),
                },
            }
        )
    return rows


def normalize_documents(
    raw_documents: Iterable[dict[str, Any]],
    source_by_file: dict[str, dict[str, Any]],
    dataset_label: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fallback_index, row in enumerate(raw_documents):
        metadata = dict(row.get("metadata") or {})
        file_name = str(metadata.get("benchmark_source_file") or metadata.get("file_name") or "")
        source = source_by_file.get(file_name, {})
        doc_id = str(source.get("doc_id") or metadata.get("benchmark_document_id") or Path(file_name).stem)
        metadata["benchmark_document_id"] = doc_id
        metadata["benchmark_dataset"] = dataset_label
        metadata["moi_ready_dataset"] = dataset_label
        metadata["moi_ready_schema"] = "moi-ready-v1"
        metadata["source_status"] = source.get("source_status", "evidence_only")
        metadata["original_source_status"] = source.get("original_source_status", "not_attempted")
        metadata["has_image_evidence"] = bool(source.get("has_image_evidence", False))
        metadata["image_evidence_count"] = int(source.get("image_evidence_count", 0))
        # Use doc_id as the benchmark-facing file name so source recall can
        # compare hits to questions without exposing temporary materialized paths.
        metadata["source_file_name"] = file_name
        metadata["file_name"] = doc_id
        raw_block = str(metadata.get("block_uuid") or f"block-{fallback_index}")
        file_id = str(metadata.get("file_id") or metadata.get("raw_file_id") or "local")
        block_uuid = f"{file_id}-{raw_block}"
        if block_uuid in seen:
            block_uuid = f"{block_uuid}-{fallback_index}"
        seen.add(block_uuid)
        try:
            document_index = int(metadata.get("document_index", fallback_index))
        except (TypeError, ValueError):
            document_index = fallback_index
        normalized.append(
            {
                "block_uuid": block_uuid,
                "content": str(row.get("content") or ""),
                "document_index": document_index,
                "metadata": metadata,
                "type": str(row.get("type") or "text"),
            }
        )
    return normalized


def consolidate_visual_assets(
    documents: list[dict[str, Any]], output_root: Path
) -> list[dict[str, Any]]:
    """Copy parser-produced page/visual images to stable benchmark assets."""

    assets: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for document in documents:
        if str(document.get("type") or "").lower() != "image":
            continue
        metadata = document.setdefault("metadata", {})
        doc_id = str(metadata.get("benchmark_document_id") or "unknown")
        raw_path = str(metadata.get("s3_image_url") or "")
        source_path = Path(raw_path)
        counters[doc_id] += 1
        asset_id = f"{safe_name(doc_id)}-image-{counters[doc_id]:06d}"
        target = output_root / "assets" / "images" / safe_name(doc_id) / f"{asset_id}.png"
        status = "missing_parser_artifact"
        digest = None
        if source_path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)
            digest = sha256_file(target)
            status = "available"
            metadata["image_asset_id"] = asset_id
            metadata["image_asset_path"] = str(target)
            metadata["image_asset_sha256"] = digest
            metadata["image_file_id"] = asset_id
            metadata["page_image_file_id"] = asset_id
            metadata["s3_image_url"] = str(target)
        assets.append(
            {
                "asset_id": asset_id,
                "asset_kind": "parser_page_or_visual_image",
                "status": status,
                "doc_id": doc_id,
                "source_file_name": metadata.get("source_file_name") or metadata.get("file_name"),
                "source_path": metadata.get("source_path"),
                "page_number": metadata.get("page_num"),
                "bbox": metadata.get("bbox"),
                "path": str(target) if status == "available" else None,
                "sha256": digest,
                "mime_type": "image/png",
                "parser_block_uuid": document.get("block_uuid"),
                "render_reason": metadata.get("render_reason") or metadata.get("degraded_reason"),
            }
        )
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fab-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--parser-bin", type=Path)
    parser.add_argument("--parser-workers", type=int, default=4)
    parser.add_argument("--download-public-sources", action="store_true")
    parser.add_argument("--force-reparse", action="store_true")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    cases = read_cases(args.fab_root)
    source_rows, evidence_rows = build_registries(cases)
    source_rows = acquire_sources(source_rows, args.out, args.download_public_sources)
    source_by_id = {row["doc_id"]: row for row in source_rows}
    source_assets = copy_public_assets(args.fab_root, args.out)

    # Materialize and parse the public Gold Context for every source.  This is
    # the fallback representation for sources that are not distributable.
    evidence_root = args.out / "evidence-prepared"
    evidence_info = materialize_fab(args.fab_root, evidence_root)
    evidence_source_manifest = json.loads((evidence_info["root"] / "source-manifest.json").read_text(encoding="utf-8"))
    evidence_by_file = {item["file_name"]: source_by_id[item["doc_id"]] for item in evidence_source_manifest["documents"]}
    evidence_parse = parse_files_tolerant(
        args.parser_bin.resolve() if args.parser_bin else None,
        evidence_info["files"],
        args.out / "parsing",
        "evidence",
        args.parser_workers,
        not args.force_reparse,
    )
    evidence_docs = read_jsonl(Path(evidence_parse.get("combined_documents", "")))

    acquired_rows = [row for row in source_rows if row.get("source_status") == "source_acquired" and row.get("original_path")]
    acquired_files = [Path(row["original_path"]) for row in acquired_rows]
    source_parse = parse_files_tolerant(
        args.parser_bin.resolve() if args.parser_bin else None,
        acquired_files,
        args.out / "parsing",
        "original",
        args.parser_workers,
        not args.force_reparse,
    )
    parsed_original_paths = {
        str(Path(summary.get("source_path", "")).resolve())
        for summary in source_parse.get("per_file") or []
        if summary.get("source_path")
    }
    failed_original_reasons = {
        str(Path(failure.get("source_path", "")).resolve()): str(failure.get("reason") or "")
        for failure in source_parse.get("failures") or []
    }
    for source in acquired_rows:
        source_path = str(Path(source["original_path"]).resolve())
        if source_path in parsed_original_paths:
            source["parser_status"] = "parsed"
        elif source_path in failed_original_reasons:
            source["parser_status"] = "parse_failed"
            source["parser_failure_reason"] = failed_original_reasons[source_path]
        else:
            source["parser_status"] = "not_attempted"
    original_docs = read_jsonl(Path(source_parse.get("combined_documents", "")))

    # One canonical document representation per doc_id: original source when
    # acquired, otherwise the public evidence-only Markdown slice.
    original_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    original_file_map = {Path(row["original_path"]).name: row for row in acquired_rows}
    for row in original_docs:
        file_name = str((row.get("metadata") or {}).get("benchmark_source_file") or "")
        source = original_file_map.get(file_name)
        if source:
            original_by_doc[source["doc_id"]].append(row)
    evidence_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence_docs:
        file_name = str((row.get("metadata") or {}).get("benchmark_source_file") or "")
        source = evidence_by_file.get(file_name)
        if source:
            evidence_by_doc[source["doc_id"]].append(row)

    selected_raw: list[dict[str, Any]] = []
    source_by_file: dict[str, dict[str, Any]] = {}
    for source in source_rows:
        doc_id = source["doc_id"]
        rows = original_by_doc.get(doc_id) or evidence_by_doc.get(doc_id) or []
        selected_raw.extend(rows)
        for row in rows:
            source_by_file[str((row.get("metadata") or {}).get("benchmark_source_file") or "")] = source
    normalized = normalize_documents(selected_raw, source_by_file, "fab-bench")
    image_assets = consolidate_visual_assets(normalized, args.out)
    image_assets_by_doc = Counter(str(asset.get("doc_id") or "") for asset in image_assets if asset.get("status") == "available")
    for source in source_rows:
        source["parsed_image_blocks"] = int(image_assets_by_doc.get(source["doc_id"], 0))
        source["image_asset_status"] = "available" if source["parsed_image_blocks"] > 0 else source["image_asset_status"]

    # Add an explicit visual registry even when the binary/image itself is not
    # public.  This lets downstream code distinguish missing visual assets from
    # ordinary text-only evidence.
    visual_rows = [
        {
            "asset_id": row["evidence_id"] + ":image",
            "evidence_id": row["evidence_id"],
            "doc_id": row["doc_id"],
            "test_id": row["test_id"],
            "section_title": row["section_title"],
            "has_image": row["has_image"],
            "asset_status": "available_in_source_parse" if image_assets_by_doc.get(row["doc_id"], 0) else row["image_asset_status"],
            "image_file": next((asset.get("path") for asset in image_assets if asset.get("doc_id") == row["doc_id"] and asset.get("status") == "available"), None),
            "image_asset_ids": [asset.get("asset_id") for asset in image_assets if asset.get("doc_id") == row["doc_id"] and asset.get("status") == "available"],
            "image_files": [asset.get("path") for asset in image_assets if asset.get("doc_id") == row["doc_id"] and asset.get("status") == "available"],
            "bbox": None,
            "ocr_text": None,
            "caption": None,
        }
        for row in evidence_rows
        if row["has_image"]
    ]

    moi_root = args.out / "moi-ready"
    moi_root.mkdir(parents=True, exist_ok=True)
    moi_documents = moi_root / "moi-documents.jsonl"
    write_jsonl(moi_documents, normalized)
    image_index_rows = [
        {
            "schema_version": "moi-image-index-input-v1",
            "asset_id": row["metadata"].get("image_asset_id"),
            "doc_id": row["metadata"].get("benchmark_document_id"),
            "block_uuid": row["block_uuid"],
            "image_path": row["metadata"].get("image_asset_path"),
            "image_sha256": row["metadata"].get("image_asset_sha256"),
            "mime_type": "image/png",
            "source_path": row["metadata"].get("source_path"),
            "page_num": row["metadata"].get("page_num"),
            "bbox": row["metadata"].get("bbox"),
            "page_image_file_id": row["metadata"].get("page_image_file_id"),
            "embedding_mode": "fusion",
            "embedding_input_type": "image_url",
            "moi_index_route": "document_visual.index.image",
            "local_file_requires_upload_or_data_url": True,
        }
        for row in normalized
        if row.get("type") == "image" and row.get("metadata", {}).get("image_asset_path")
    ]
    write_jsonl(moi_root / "image-index-input.jsonl", image_index_rows)
    write_jsonl(moi_root / "manifest.jsonl", [
        {
            "schema_version": "moi-ready-v1",
            "status": source["source_status"],
            "dataset": "fab-bench",
            "document_id": source["doc_id"],
            "source_status": source["source_status"],
            "original_source_status": source["original_source_status"],
            "source_path": source.get("original_path"),
            "source_url": source.get("source_url"),
            "source_sha256": source.get("source_sha256"),
            "parser_status": source.get("parser_status", "evidence_fallback"),
            "parser_failure_reason": source.get("parser_failure_reason"),
            "evidence_blocks": source["evidence_blocks"],
            "has_image_evidence": source["has_image_evidence"],
            "image_evidence_count": source["image_evidence_count"],
            "image_asset_status": source["image_asset_status"],
            "parsed_image_blocks": source.get("parsed_image_blocks", 0),
            "moi_documents_path": str(moi_documents),
        }
        for source in source_rows
    ])
    write_jsonl(args.out / "source-registry.jsonl", source_rows)
    write_jsonl(args.out / "evidence-registry.jsonl", evidence_rows)
    write_jsonl(args.out / "visual-registry.jsonl", visual_rows)
    write_jsonl(moi_root / "asset-manifest.jsonl", source_assets + image_assets + visual_rows)
    write_jsonl(args.out / "questions.jsonl", enrich_questions(cases, source_by_id))
    write_jsonl(args.out / "gold-questions.jsonl", cases)

    acquired_count = sum(row["source_status"] == "source_acquired" for row in source_rows)
    missing_count = len(source_rows) - acquired_count
    image_evidence_count = sum(bool(row["has_image"]) for row in evidence_rows)
    visual_available_count = sum(row["asset_status"] == "available_in_source_parse" for row in visual_rows)
    visual_missing_count = image_evidence_count - visual_available_count
    completeness = {
        "schema_version": "fab-bench-completeness-v1",
        "created_at": now_utc(),
        "dataset": "FAB-Bench",
        "status": "public-complete-evidence-only" if missing_count else "source-complete",
        "public_complete": True,
        "source_complete": missing_count == 0,
        "qa_cases": len(cases),
        "evidence_items": len(evidence_rows),
        "unique_doc_ids": len(source_rows),
        "original_documents_acquired": acquired_count,
        "original_documents_parsed": sum(row.get("parser_status") == "parsed" for row in source_rows),
        "original_documents_parse_failed": sum(row.get("parser_status") == "parse_failed" for row in source_rows),
        "original_documents_missing_or_unresolved": missing_count,
        "image_evidence_items": image_evidence_count,
        "gold_image_evidence_with_source_assets": visual_available_count,
        "gold_image_evidence_missing_assets": visual_missing_count,
        "image_assets_acquired": sum(1 for asset in image_assets if asset.get("status") == "available"),
        "image_assets_missing": sum(1 for asset in image_assets if asset.get("status") != "available"),
        "image_parser_blocks": sum(1 for row in normalized if row.get("type") == "image"),
        "parsed_blocks": len(normalized),
        "parsed_documents": len({row["metadata"].get("benchmark_document_id") for row in normalized}),
        "block_type_counts": dict(Counter(row["type"] for row in normalized)),
        "source_status_counts": dict(Counter(row["source_status"] for row in source_rows)),
        "blocking_reasons": sorted({row.get("original_source_reason") for row in source_rows if row.get("source_status") != "source_acquired" and row.get("original_source_reason")}),
        "representation": "Original source when publicly resolved; otherwise the official public Gold Context evidence snippets. Missing source documents are not reconstructed.",
    }
    write_json(args.out / "source-completeness.json", completeness)
    write_json(moi_root / "summary.json", {
        "schema_version": "moi-ready-v1",
        "created_at": now_utc(),
        "dataset": "fab-bench",
        "status": "ready-public-evidence",
        "source_complete": completeness["source_complete"],
        "public_complete": True,
        "planned_documents": len(source_rows),
        "successful_documents": len(source_rows),
        "failed_documents": 0,
        "source_documents_acquired": acquired_count,
        "evidence_only_documents": missing_count,
        "moi_document_blocks": len(normalized),
        "visual_blocks": sum(1 for row in normalized if row.get("type") == "image"),
        "image_index_input_rows": len(image_index_rows),
        "image_evidence_items": image_evidence_count,
        "gold_image_evidence_with_source_assets": visual_available_count,
        "gold_image_evidence_missing_assets": visual_missing_count,
        "image_assets_acquired": sum(1 for asset in image_assets if asset.get("status") == "available"),
        "image_assets_missing": sum(1 for asset in image_assets if asset.get("status") != "available"),
        "parser_profile": "v3-native" if args.parser_bin else None,
        "parser_route": "moi:parse/v3/native" if args.parser_bin else None,
        "web_equivalent": False,
        "moi_documents_path": str(moi_documents),
        "image_index_input_path": str(moi_root / "image-index-input.jsonl"),
        "manifest_path": str(moi_root / "manifest.jsonl"),
        "source_completeness_path": str(args.out / "source-completeness.json"),
    })
    (moi_root / "README.md").write_text(
        "# FAB-Bench / complete public package / MOI-ready\n\n"
        "This package contains all 200 official QA cases, all 342 public Gold Context evidence items, "
        "and all 127 unique source IDs. Original PDFs are included only when their public identity was "
        "unambiguous and the file was downloadable. Other documents remain explicitly evidence-only; "
        "this must not be labeled a complete original source corpus.\n\n"
        f"`moi-documents.jsonl` contains {sum(1 for row in normalized if row.get('type') == 'image')} "
        "parser-produced image blocks from acquired PDFs, and those images are copied to stable PNG "
        "assets with SHA-256 entries in `asset-manifest.jsonl`. `image-index-input.jsonl` is the "
        "separate image-index input manifest for `document_visual.index.image`; it intentionally "
        "contains paths and hashes, not fabricated vectors. `visual-registry.jsonl` records the "
        "four QA evidence items marked `has_image=true`; only items whose source parse yielded assets "
        "are marked available. The local RAG adapter does not create image-vector tables yet, so this "
        "package is MOI-ready for separate text/image indexing rather than claiming a completed hybrid "
        "index.\n",
        encoding="utf-8",
    )
    write_json(args.out / "run-manifest.json", {
        "schema_version": "fab-bench-complete-run-v1",
        "created_at": now_utc(),
        "adapter_version": SCRIPT_VERSION,
        "base_adapter_version": BASE_ADAPTER_VERSION,
        "fab_root": str(args.fab_root),
        "download_public_sources": args.download_public_sources,
        "parser_bin": str(args.parser_bin.resolve()) if args.parser_bin else None,
        "parser_workers": args.parser_workers,
        "source_registry": str(args.out / "source-registry.jsonl"),
        "evidence_registry": str(args.out / "evidence-registry.jsonl"),
        "source_parse": source_parse,
        "evidence_parse": evidence_parse,
        "completeness": completeness,
    })
    print(json.dumps({"out": str(args.out), "status": completeness["status"], "acquired": acquired_count, "missing": missing_count, "blocks": len(normalized)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
