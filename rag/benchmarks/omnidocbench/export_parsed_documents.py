#!/usr/bin/env python3
"""Export completed OmniDocBench parsing artifacts into an engine-isolated local store."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


SCHEMA_VERSION = "parsed-document-export-v1"
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def validate_component(label: str, value: str) -> str:
    if not SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"{label} must be a safe path component, got {value!r}")
    return value


def safe_document_directory_name(document_id: str) -> str:
    if not document_id:
        raise ValueError("document_id must be non-empty")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", document_id).strip("._-") or "document"
    if cleaned != document_id or len(cleaned) > 120:
        suffix = hashlib.sha256(document_id.encode("utf-8")).hexdigest()[:12]
        cleaned = f"{cleaned[:100].rstrip('._-')}--{suffix}"
    return validate_component("document directory name", cleaned)


def copy_verified(source: Path, destination: Path) -> str:
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = sha256_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != source_hash:
            raise FileExistsError(f"destination exists with different content: {destination}")
        return source_hash
    shutil.copy2(source, destination)
    if sha256_file(destination) != source_hash:
        raise IOError(f"copy hash mismatch: {source} -> {destination}")
    return source_hash


def export_run(run_dir: Path, output_root: Path, engine: str, pipeline: str) -> Path:
    run_dir = run_dir.resolve()
    output_root = output_root.resolve()
    engine = validate_component("engine", engine)
    pipeline = validate_component("pipeline", pipeline)
    run_name = validate_component("run directory name", run_dir.name)

    sample_manifest_path = run_dir / "artifacts" / "sample-manifest.jsonl"
    attempts_path = run_dir / "moi-unified" / "attempts.jsonl"
    if not sample_manifest_path.is_file():
        raise FileNotFoundError(sample_manifest_path)
    if not attempts_path.is_file():
        raise FileNotFoundError(attempts_path)

    samples = {row["page_id"]: row for row in read_jsonl(sample_manifest_path)}
    attempts = read_jsonl(attempts_path)
    successful = [row for row in attempts if row.get("status") == "ok" and row.get("pipeline") == pipeline]
    if not successful:
        raise ValueError(f"no successful attempts for pipeline={pipeline!r} in {run_dir}")

    export_dir = output_root / engine / pipeline / run_name
    documents_dir = export_dir / "documents"
    exported_rows = []
    seen_page_ids: set[str] = set()

    for attempt in sorted(successful, key=lambda row: row["page_id"]):
        page_id = attempt["page_id"]
        if not isinstance(page_id, str) or not page_id:
            raise ValueError(f"page_id must be a non-empty string, got {page_id!r}")
        if page_id in seen_page_ids:
            raise ValueError(f"duplicate successful attempt for page_id={page_id!r}")
        seen_page_ids.add(page_id)
        sample = samples.get(page_id)
        if sample is None:
            raise ValueError(f"successful page is absent from sample manifest: {page_id}")

        input_pdf = Path(sample["input_pdf"]).resolve()
        prediction = Path(attempt["prediction"]).resolve()
        parser_run = Path(attempt["parser_run_dir"]).resolve()
        directory_id = safe_document_directory_name(page_id)
        document_dir = documents_dir / directory_id

        files = {
            "input_pdf": (input_pdf, document_dir / "input.pdf"),
            "parsed_markdown": (prediction, document_dir / "parsed.md"),
        }
        optional_files = {
            "parser_result": (parser_run / "result.json", document_dir / "parser-result.json"),
            "parser_summary": (parser_run / "summary.json", document_dir / "parser-summary.json"),
        }
        file_records = {}
        for key, (source, destination) in files.items():
            digest = copy_verified(source, destination)
            file_records[key] = {"path": str(destination), "sha256": digest}
        for key, (source, destination) in optional_files.items():
            if source.is_file():
                digest = copy_verified(source, destination)
                file_records[key] = {"path": str(destination), "sha256": digest}

        exported_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "benchmark": "OmniDocBench",
                "engine": engine,
                "pipeline": pipeline,
                "source_run": str(run_dir),
                "source_parser_run": str(parser_run),
                "page_id": page_id,
                "directory_id": directory_id,
                "files": file_records,
            }
        )

    metadata_sources = {
        "sample-manifest.jsonl": sample_manifest_path,
        "attempts.jsonl": attempts_path,
        "metrics.json": run_dir / "moi-unified" / "metrics.json",
        "error-taxonomy.json": run_dir / "moi-unified" / "error-taxonomy.json",
        "protocol.json": run_dir / "official" / "protocol.json",
    }
    for name, source in metadata_sources.items():
        if source.is_file():
            copy_verified(source, export_dir / "metadata" / name)

    export_manifest = export_dir / "export-manifest.jsonl"
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in exported_rows)
    if export_manifest.exists() and export_manifest.read_text(encoding="utf-8") != payload:
        raise FileExistsError(f"export manifest exists with different content: {export_manifest}")
    export_manifest.parent.mkdir(parents=True, exist_ok=True)
    export_manifest.write_text(payload, encoding="utf-8")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "benchmark": "OmniDocBench",
        "engine": engine,
        "pipeline": pipeline,
        "source_run": str(run_dir),
        "exported_documents": len(exported_rows),
        "output_directory": str(export_dir),
    }
    summary_path = export_dir / "export-summary.json"
    summary_payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if summary_path.exists() and summary_path.read_text(encoding="utf-8") != summary_payload:
        raise FileExistsError(f"export summary exists with different content: {summary_path}")
    summary_path.write_text(summary_payload, encoding="utf-8")
    return export_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--engine", required=True, help="e.g. mineru, moi, docling")
    parser.add_argument("--pipeline", required=True, help="e.g. precision, agent, native")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    export_dir = export_run(Path(args.run_dir), Path(args.output_root), args.engine, args.pipeline)
    print(f"export_dir={export_dir}")


if __name__ == "__main__":
    main()
