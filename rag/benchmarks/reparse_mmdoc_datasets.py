#!/usr/bin/env python3
"""Force-reparse MMDocIR, DocBench, and MMDocRAG into MOI-ready payloads.

The first launch archives the three existing dataset directories, then rebuilds
them in place.  A successful result must contain every local image referenced
by MinerU Markdown/documents, and every image must be decodable.  Interrupted
runs are resumable: relaunching skips records from the active run whose status
is already ``ok``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from PIL import Image
from pypdf import PdfReader, PdfWriter


SCHEMA_VERSION = "moi-mmdoc-reparse-v1"
DATASETS = ("mmdocir", "docbench", "mmdocrag")
EXPECTED_COUNTS = {"mmdocir": 313, "docbench": 229, "mmdocrag": 220}
TOTAL_TASKS = sum(EXPECTED_COUNTS.values())
ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_RAG = ROOT / "datasets" / "downloads" / "document-rag"
DEFAULT_OUTPUT = ROOT / "outputs" / "parsed-documents" / "moi-ready-v1"
DEFAULT_ENV = ROOT / ".env"
DEFAULT_PARSER = Path("/tmp/moi-local-matrixflow-parser-mmdoc")
SAFE = re.compile(r"[^A-Za-z0-9._-]+")
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)")


@dataclass(frozen=True)
class Task:
    dataset: str
    document_id: str
    source_path: str

    @property
    def key(self) -> str:
        return f"{self.dataset}:{self.document_id}"

    @property
    def directory_id(self) -> str:
        cleaned = SAFE.sub("_", self.document_id).strip("._-") or "document"
        digest = hashlib.sha256(self.document_id.encode("utf-8")).hexdigest()[:12]
        if cleaned != self.document_id or len(cleaned) > 100:
            cleaned = cleaned[:90].rstrip("._-")
            return f"{cleaned}--{digest}"
        return cleaned


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(temporary, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_tasks(output_root: Path) -> list[Task]:
    mmdocir_root = output_root / "sources" / "mmdocir" / "doc_pdfs"
    mmdocir_paths = sorted(mmdocir_root.glob("*.pdf"))
    docbench_paths = sorted((DOCUMENT_RAG / "docbench" / "data").glob("*/*.pdf"))
    mmdocrag_paths = sorted((DOCUMENT_RAG / "mmdocrag" / "data" / "doc_pdfs").glob("*.pdf"))
    paths = {
        "mmdocir": mmdocir_paths,
        "docbench": docbench_paths,
        "mmdocrag": mmdocrag_paths,
    }
    tasks: list[Task] = []
    for dataset in DATASETS:
        dataset_paths = paths[dataset]
        if len(dataset_paths) != EXPECTED_COUNTS[dataset]:
            raise RuntimeError(
                f"{dataset} has {len(dataset_paths)} PDFs, want {EXPECTED_COUNTS[dataset]}"
            )
        tasks.extend(
            Task(dataset=dataset, document_id=path.stem, source_path=str(path.resolve()))
            for path in dataset_paths
        )
    keys = [task.key for task in tasks]
    if len(keys) != len(set(keys)):
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        raise RuntimeError(f"duplicate task keys: {duplicates[:10]}")
    return tasks


def target_dir(output_root: Path, task: Task) -> Path:
    return output_root / "datasets" / task.dataset / "documents" / task.directory_id


def current_run_path(output_root: Path) -> Path:
    return output_root / "reparse-mmdoc-current.json"


def new_run_id() -> str:
    return time.strftime("reparse-mmdoc-%Y%m%d-%H%M%S")


def initialize_or_resume(output_root: Path, tasks: list[Task]) -> tuple[dict[str, Any], bool]:
    pointer = current_run_path(output_root)
    if pointer.is_file():
        try:
            current = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        if current.get("status") in {"running", "paused", "interrupted"} and current.get("run_id"):
            current["status"] = "running"
            current["resumed_at_epoch"] = time.time()
            atomic_json(pointer, current)
            return current, True

    run_id = new_run_id()
    archive_root = output_root / "archive" / run_id
    for dataset in DATASETS:
        source = output_root / "datasets" / dataset
        destination = archive_root / "datasets" / dataset
        if source.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
        (source / "documents").mkdir(parents=True, exist_ok=True)
    current = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "running",
        "started_at_epoch": time.time(),
        "archive_root": str(archive_root),
        "output_root": str(output_root),
        "datasets": list(DATASETS),
        "planned": len(tasks),
    }
    atomic_json(pointer, current)
    write_jsonl(output_root / "reparse-mmdoc-task-manifest.jsonl", (asdict(task) for task in tasks))
    return current, False


def completed_record(output_root: Path, task: Task, run_id: str) -> dict[str, Any] | None:
    record_path = target_dir(output_root, task) / "record.json"
    if not record_path.is_file():
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    payload = record_path.parent / "payload"
    if record.get("status") != "ok" or record.get("reparse_run_id") != run_id:
        return None
    if not all((payload / name).is_file() for name in ("result.json", "documents.jsonl", "summary.json")):
        return None
    try:
        validate_payload(payload)
    except Exception:
        return None
    return record


class Progress:
    def __init__(self, output_root: Path, tasks: list[Task], run: dict[str, Any]) -> None:
        self.path = output_root / "reparse-mmdoc-progress.json"
        self.events = output_root / "reparse-mmdoc-events.jsonl"
        self.lock = threading.Lock()
        self.started = time.time()
        self.state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run["run_id"],
            "status": "running",
            "started_at_epoch": run.get("started_at_epoch", self.started),
            "updated_at_epoch": self.started,
            "planned": len(tasks),
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped_completed": 0,
            "pending": len(tasks),
            "tool_invocations": {"mineru_official_precision": 0},
            "image_validation": {"referenced": 0, "files": 0, "bytes": 0},
            "datasets": {
                dataset: {
                    "planned": EXPECTED_COUNTS[dataset],
                    "running": 0,
                    "succeeded": 0,
                    "failed": 0,
                }
                for dataset in DATASETS
            },
        }
        self._save()

    def _save(self) -> None:
        self.state["updated_at_epoch"] = time.time()
        atomic_json(self.path, self.state)

    def _event(self, value: dict[str, Any]) -> None:
        self.events.parent.mkdir(parents=True, exist_ok=True)
        with self.events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False) + "\n")

    def existing(self, task: Task, record: dict[str, Any]) -> None:
        with self.lock:
            self.state["succeeded"] += 1
            self.state["skipped_completed"] += 1
            self.state["pending"] -= 1
            self.state["datasets"][task.dataset]["succeeded"] += 1
            for attempt in record.get("attempts", []):
                if attempt.get("tool") == "mineru_official_precision":
                    self.state["tool_invocations"]["mineru_official_precision"] += 1
            validation = record.get("image_validation") or {}
            for key in ("referenced", "files", "bytes"):
                self.state["image_validation"][key] += int(validation.get(key, 0))
            self._save()

    def task_started(self, task: Task) -> None:
        with self.lock:
            self.state["running"] += 1
            self.state["pending"] -= 1
            self.state["datasets"][task.dataset]["running"] += 1
            self._save()

    def invocation(self, task: Task, part: int, attempt: int) -> None:
        with self.lock:
            self.state["tool_invocations"]["mineru_official_precision"] += 1
            self._event({
                "event": "tool_invocation",
                "tool": "mineru_official_precision",
                "dataset": task.dataset,
                "document_id": task.document_id,
                "part": part,
                "attempt": attempt,
                "time": time.time(),
            })
            self._save()

    def task_finished(self, task: Task, record: dict[str, Any]) -> None:
        ok = record.get("status") == "ok"
        with self.lock:
            self.state["running"] -= 1
            self.state["datasets"][task.dataset]["running"] -= 1
            key = "succeeded" if ok else "failed"
            self.state[key] += 1
            self.state["datasets"][task.dataset][key] += 1
            if ok:
                validation = record.get("image_validation") or {}
                for name in ("referenced", "files", "bytes"):
                    self.state["image_validation"][name] += int(validation.get(name, 0))
            self._save()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def finish(self, status: str) -> None:
        with self.lock:
            self.state["status"] = status
            self.state["finished_at_epoch"] = time.time()
            self._save()


def page_count(source: Path) -> int:
    reader = PdfReader(str(source), strict=False)
    return len(reader.pages)


def split_pdf(source: Path, parts_root: Path, chunk_pages: int) -> list[tuple[Path, int, int]]:
    reader = PdfReader(str(source), strict=False)
    total = len(reader.pages)
    parts_root.mkdir(parents=True, exist_ok=True)
    parts: list[tuple[Path, int, int]] = []
    for start in range(0, total, chunk_pages):
        end = min(start + chunk_pages, total)
        destination = parts_root / f"part-{start + 1:05d}-{end:05d}.pdf"
        if not destination.is_file():
            writer = PdfWriter()
            for index in range(start, end):
                writer.add_page(reader.pages[index])
            temporary = destination.with_suffix(".pdf.tmp")
            with temporary.open("wb") as handle:
                writer.write(handle)
            os.replace(temporary, destination)
        parts.append((destination, start, end))
    return parts


def run_parser(
    task: Task,
    source: Path,
    run_root: Path,
    parser_bin: Path,
    env_file: Path,
    progress: Progress,
    part_number: int,
    attempts: int,
    timeout: int,
) -> tuple[Path, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        progress.invocation(task, part_number, attempt)
        command = [
            str(parser_bin), "parse",
            "--input", str(source),
            "--env-file", str(env_file),
            "--run", str(run_root),
            "--pipeline", "precision",
        ]
        started = time.time()
        try:
            completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
            row: dict[str, Any] = {
                "attempt": attempt,
                "part": part_number,
                "tool": "mineru_official_precision",
                "returncode": completed.returncode,
                "duration_seconds": time.time() - started,
                "stdout": completed.stdout[-12000:],
                "stderr": completed.stderr[-12000:],
            }
            rows.append(row)
            match = re.search(r"^run_dir=(.+)$", completed.stdout, re.MULTILINE)
            if completed.returncode == 0 and match:
                run_dir = Path(match.group(1).strip())
                validate_payload(run_dir)
                return run_dir, rows
        except subprocess.TimeoutExpired as error:
            rows.append({
                "attempt": attempt,
                "part": part_number,
                "tool": "mineru_official_precision",
                "timeout": timeout,
                "duration_seconds": time.time() - started,
                "stdout": str(error.stdout or "")[-12000:],
                "stderr": str(error.stderr or "")[-12000:],
            })
        except Exception as error:
            rows.append({
                "attempt": attempt,
                "part": part_number,
                "tool": "mineru_official_precision",
                "returncode": 1,
                "duration_seconds": time.time() - started,
                "validation_error": f"{type(error).__name__}: {error}",
            })
        if attempt < attempts:
            time.sleep(5 * attempt)
    raise RuntimeError(f"part {part_number} failed after {attempts} attempts: {rows[-1]}")


def local_image_reference(raw: str) -> str | None:
    value = unquote(raw.strip().strip("<>"))
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or value.startswith(("data:", "#")):
        return None
    value = value.split("?", 1)[0].split("#", 1)[0].replace("\\", "/")
    clean = PurePosixPath(value)
    if clean.is_absolute() or ".." in clean.parts:
        raise ValueError(f"unsafe image reference: {raw!r}")
    parts = clean.parts
    if "images" not in parts:
        return None
    image_index = parts.index("images")
    normalized = PurePosixPath(*parts[image_index:]).as_posix()
    if normalized == "images":
        raise ValueError(f"invalid image reference: {raw!r}")
    return normalized


def validate_image(path: Path) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
        raise ValueError(f"missing or unsafe image asset: {path}")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.width <= 0 or image.height <= 0:
            raise ValueError(f"invalid image dimensions: {path}")


def collect_image_references(payload: Path) -> set[str]:
    references: set[str] = set()
    documents_path = payload / "documents.jsonl"
    if documents_path.is_file():
        for document in read_jsonl(documents_path):
            metadata = document.get("metadata") or {}
            raw = metadata.get("image_url")
            if isinstance(raw, str):
                normalized = local_image_reference(raw)
                if normalized:
                    references.add(normalized)
    markdown_path = payload / "product-artifacts" / "mineru-full.md"
    if markdown_path.is_file():
        markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
        for match in MARKDOWN_IMAGE.finditer(markdown):
            normalized = local_image_reference(match.group(1) or match.group(2) or "")
            if normalized:
                references.add(normalized)
    return references


def validate_payload(payload: Path) -> dict[str, int]:
    required = ("result.json", "documents.jsonl", "summary.json")
    missing = [name for name in required if not (payload / name).is_file()]
    if missing:
        raise FileNotFoundError(f"payload missing required files: {missing}")
    references = collect_image_references(payload)
    artifact_root = payload / "product-artifacts"
    for reference in sorted(references):
        validate_image(artifact_root / Path(reference))
    image_root = artifact_root / "images"
    files = sorted(path for path in image_root.rglob("*") if path.is_file()) if image_root.is_dir() else []
    for path in files:
        validate_image(path)
    return {
        "referenced": len(references),
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


def copy_image_assets(source: Path, destination: Path) -> None:
    if not source.is_dir():
        return
    for image in sorted(path for path in source.rglob("*") if path.is_file()):
        relative = image.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha256_file(target) != sha256_file(image):
                raise RuntimeError(f"conflicting image asset {relative}")
            continue
        shutil.copy2(image, target)


def normalize_documents(
    documents: list[dict[str, Any]],
    task: Task,
    final_payload: Path,
    page_offset: int = 0,
    start_index: int = 0,
    part_number: int = 0,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    file_id = f"local_{hashlib.sha256(task.key.encode()).hexdigest()[:24]}"
    for local_index, document in enumerate(documents):
        row = dict(document)
        metadata = dict(row.get("metadata") or {})
        if isinstance(metadata.get("page_num"), int):
            metadata["page_num"] += page_offset
        metadata.update({
            "file_id": file_id,
            "raw_file_id": file_id,
            "file_name": Path(task.source_path).name,
            "source_path": task.source_path,
            "benchmark_dataset": task.dataset,
            "benchmark_document_id": task.document_id,
            "reparse_part": part_number,
        })
        raw_image = metadata.get("image_url")
        if isinstance(raw_image, str):
            reference = local_image_reference(raw_image)
            if reference:
                metadata["image_artifact_path"] = f"product-artifacts/{reference}"
                metadata["image_path"] = str(final_payload / "product-artifacts" / Path(reference))
        index = start_index + local_index
        row["metadata"] = metadata
        row["document_index"] = index
        row["block_uuid"] = f"{file_id}-block-{index}"
        normalized.append(row)
    return normalized


def materialize_single_run(run_dir: Path, staging_payload: Path, final_payload: Path, task: Task) -> None:
    shutil.copytree(run_dir, staging_payload)
    documents = normalize_documents(read_jsonl(staging_payload / "documents.jsonl"), task, final_payload)
    result = json.loads((staging_payload / "result.json").read_text(encoding="utf-8"))
    result.update({
        "source_path": task.source_path,
        "file_type": "pdf",
        "documents": documents,
        "md_file_id": str(final_payload / "product-artifacts" / "mineru-full.md"),
    })
    summary = json.loads((staging_payload / "summary.json").read_text(encoding="utf-8"))
    summary["source_path"] = task.source_path
    atomic_json(staging_payload / "result.json", result)
    write_jsonl(staging_payload / "documents.jsonl", documents)
    atomic_json(staging_payload / "summary.json", summary)


def materialize_split_runs(
    parts: list[tuple[Path, int, int, Path]],
    staging_payload: Path,
    final_payload: Path,
    task: Task,
    chunk_pages: int,
) -> None:
    staging_payload.mkdir(parents=True)
    artifacts = staging_payload / "product-artifacts"
    images = artifacts / "images"
    artifacts.mkdir(parents=True)
    documents: list[dict[str, Any]] = []
    text_parts: list[str] = []
    markdown_parts: list[str] = []
    summaries: list[dict[str, Any]] = []
    mineru_parts: list[dict[str, Any]] = []
    result_template: dict[str, Any] | None = None
    for part_number, (part_path, start, end, run_dir) in enumerate(parts):
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        if result_template is None:
            result_template = result
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        summaries.append(summary)
        rows = normalize_documents(
            read_jsonl(run_dir / "documents.jsonl"), task, final_payload,
            page_offset=start, start_index=len(documents), part_number=part_number,
        )
        documents.extend(rows)
        plain = (run_dir / "plain-text.txt")
        if plain.is_file():
            text_parts.append(plain.read_text(encoding="utf-8", errors="replace"))
        markdown = run_dir / "product-artifacts" / "mineru-full.md"
        if markdown.is_file():
            markdown_parts.append(
                f"<!-- pages {start + 1}-{end}; part {part_number} -->\n\n"
                + markdown.read_text(encoding="utf-8", errors="replace")
            )
        copy_image_assets(run_dir / "product-artifacts" / "images", images)
        mineru_parts.append({
            "part": part_number,
            "source": str(part_path),
            "page_start": start + 1,
            "page_end": end,
            "mineru": result.get("mineru"),
        })
    if result_template is None:
        raise RuntimeError("split parse produced no results")
    plain_text = "\n\n".join(text_parts)
    (artifacts / "mineru-full.md").write_text("\n\n".join(markdown_parts), encoding="utf-8")
    (staging_payload / "plain-text.txt").write_text(plain_text, encoding="utf-8")
    block_types = Counter(str(row.get("type", "unknown")) for row in documents)
    duration_ms = sum(float(summary.get("duration_ms") or 0) for summary in summaries)
    split_info = {
        "method": "pypdf-split-and-merge",
        "chunk_pages": chunk_pages,
        "original_pages": parts[-1][2],
        "parts": mineru_parts,
    }
    result = dict(result_template)
    result.update({
        "source_path": task.source_path,
        "file_type": "pdf",
        "documents": documents,
        "plain_text": plain_text,
        "md_file_id": str(final_payload / "product-artifacts" / "mineru-full.md"),
        "mineru": None,
        "mineru_parts": mineru_parts,
        "split_parse": split_info,
        "duration_ms": duration_ms,
    })
    metadata = dict(result.get("metadata") or {})
    metadata["backend_used"] = "mineru-official-precision-split"
    metadata["split_parse"] = split_info
    result["metadata"] = metadata
    first = summaries[0]
    summary = {
        "schema_version": first.get("schema_version"),
        "engine": first.get("engine"),
        "source_path": task.source_path,
        "file_type": "pdf",
        "documents": len(documents),
        "block_types": dict(block_types),
        "content_chars": sum(len(str(row.get("content", ""))) for row in documents),
        "duration_ms": duration_ms,
        "backend_used": "mineru-official-precision-split",
        "parser_version": first.get("parser_version"),
        "tier_requested": "precision",
        "tier_effective": "precision",
        "split_parse": split_info,
    }
    atomic_json(staging_payload / "result.json", result)
    write_jsonl(staging_payload / "documents.jsonl", documents)
    atomic_json(staging_payload / "summary.json", summary)


def replace_directory(staging: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = target.with_name(target.name + ".replace-old")
    if previous.exists():
        shutil.rmtree(previous)
    if target.exists():
        os.replace(target, previous)
    try:
        os.replace(staging, target)
    except Exception:
        if previous.exists() and not target.exists():
            os.replace(previous, target)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def parse_task(
    task: Task,
    output_root: Path,
    work_root: Path,
    run_id: str,
    parser_bin: Path,
    env_file: Path,
    progress: Progress,
    max_upload_pages: int,
    chunk_pages: int,
    attempts: int,
    timeout: int,
) -> dict[str, Any]:
    progress.task_started(task)
    started = time.time()
    source = Path(task.source_path)
    work = work_root / task.dataset / task.directory_id
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    staging = work / "staging-document"
    staging_payload = staging / "payload"
    final_payload = target_dir(output_root, task) / "payload"
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "reparse_run_id": run_id,
        "dataset": task.dataset,
        "document_id": task.document_id,
        "directory_id": task.directory_id,
        "source_path": task.source_path,
        "source_sha256": sha256_file(source),
        "pipeline": "precision",
        "status": "failed",
        "started_at_epoch": started,
        "attempts": [],
    }
    try:
        pages = page_count(source)
        record["source_pages"] = pages
        raw_parts = (
            split_pdf(source, work / "parts", chunk_pages)
            if pages > max_upload_pages
            else [(source, 0, pages)]
        )
        parsed_parts: list[tuple[Path, int, int, Path]] = []
        for part_number, (part_path, start, end) in enumerate(raw_parts):
            run_dir, rows = run_parser(
                task, part_path, work / f"part-{part_number:03d}" / "runs",
                parser_bin, env_file, progress, part_number, attempts, timeout,
            )
            record["attempts"].extend(rows)
            parsed_parts.append((part_path, start, end, run_dir))
        staging.mkdir(parents=True, exist_ok=True)
        if len(parsed_parts) == 1 and parsed_parts[0][0] == source:
            materialize_single_run(parsed_parts[0][3], staging_payload, final_payload, task)
            backend = "mineru-official-precision"
        else:
            materialize_split_runs(parsed_parts, staging_payload, final_payload, task, chunk_pages)
            backend = "mineru-official-precision-split"
        validation = validate_payload(staging_payload)
        summary = json.loads((staging_payload / "summary.json").read_text(encoding="utf-8"))
        record.update({
            "status": "ok",
            "backend_used": backend,
            "payload_path": str(final_payload),
            "result_path": str(final_payload / "result.json"),
            "documents_path": str(final_payload / "documents.jsonl"),
            "summary_path": str(final_payload / "summary.json"),
            "documents": summary.get("documents"),
            "content_chars": summary.get("content_chars"),
            "parser_duration_ms": summary.get("duration_ms"),
            "image_validation": validation,
        })
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
    record["finished_at_epoch"] = time.time()
    record["wall_seconds"] = record["finished_at_epoch"] - started
    atomic_json(staging / "record.json", record)
    replace_directory(staging, target_dir(output_root, task))
    progress.task_finished(task, record)
    return record


def aggregate(output_root: Path, tasks: list[Task], run_id: str) -> None:
    all_records: list[dict[str, Any]] = []
    for dataset in DATASETS:
        records: list[dict[str, Any]] = []
        for task in sorted((item for item in tasks if item.dataset == dataset), key=lambda item: item.document_id):
            path = target_dir(output_root, task) / "record.json"
            if path.is_file():
                records.append(json.loads(path.read_text(encoding="utf-8")))
        all_records.extend(records)
        dataset_root = output_root / "datasets" / dataset
        write_jsonl(dataset_root / "manifest.jsonl", records)
        combined = dataset_root / "moi-documents.jsonl"
        temporary = combined.with_suffix(".jsonl.tmp")
        blocks = 0
        with temporary.open("w", encoding="utf-8") as destination:
            for record in records:
                if record.get("status") != "ok" or record.get("reparse_run_id") != run_id:
                    continue
                for document in read_jsonl(Path(record["documents_path"])):
                    destination.write(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n")
                    blocks += 1
        os.replace(temporary, combined)
        atomic_json(dataset_root / "summary.json", {
            "schema_version": SCHEMA_VERSION,
            "reparse_run_id": run_id,
            "dataset": dataset,
            "planned_documents": EXPECTED_COUNTS[dataset],
            "successful_documents": sum(record.get("status") == "ok" for record in records),
            "failed_documents": sum(record.get("status") != "ok" for record in records),
            "moi_document_blocks": blocks,
            "images_validated": sum(int((record.get("image_validation") or {}).get("files", 0)) for record in records),
            "moi_documents_jsonl": str(combined),
        })
    write_jsonl(output_root / "reparse-mmdoc-manifest.jsonl", all_records)


def render_progress(state: dict[str, Any], task: Task, record: dict[str, Any]) -> str:
    completed = state["succeeded"] + state["failed"]
    percent = completed / state["planned"] * 100 if state["planned"] else 100.0
    validation = record.get("image_validation") or {}
    return (
        f"[{record['status']}] {completed}/{state['planned']} ({percent:5.1f}%) "
        f"ok={state['succeeded']} failed={state['failed']} running={state['running']} "
        f"dataset={task.dataset} document={task.document_id} "
        f"images={validation.get('files', 0)}/{validation.get('referenced', 0)} "
        f"wall={record.get('wall_seconds', 0):.1f}s"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--parser-bin", type=Path, default=DEFAULT_PARSER)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--max-upload-pages", type=int, default=200)
    parser.add_argument("--chunk-pages", type=int, default=180)
    parser.add_argument("--timeout", type=int, default=30 * 60)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(output_root)
    if args.dry_run:
        print(json.dumps({
            "datasets": EXPECTED_COUNTS,
            "planned": len(tasks),
            "output_root": str(output_root),
            "parser_bin": str(args.parser_bin),
        }, ensure_ascii=False, indent=2))
        return 0
    if not args.parser_bin.is_file():
        raise FileNotFoundError(f"parser binary not found: {args.parser_bin}")
    if not args.env_file.is_file():
        raise FileNotFoundError(f"env file not found: {args.env_file}")
    if args.workers < 1 or args.attempts < 1 or args.chunk_pages < 1 or args.max_upload_pages < 1:
        raise ValueError("workers, attempts, max-upload-pages, and chunk-pages must be positive")
    if args.chunk_pages > args.max_upload_pages:
        raise ValueError("chunk-pages cannot exceed max-upload-pages")

    lock_path = output_root / ".reparse-mmdoc.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as error:
        raise RuntimeError(f"another reparse appears active; remove stale lock only after checking: {lock_path}") from error
    os.write(lock_fd, f"pid={os.getpid()} started={time.time()}\n".encode())
    os.close(lock_fd)

    run: dict[str, Any] | None = None
    progress: Progress | None = None
    interrupted = False

    def mark_interrupted(signum: int, _frame: Any) -> None:
        nonlocal interrupted
        interrupted = True
        print(f"\n[signal] received {signum}; waiting for active parser calls to stop", flush=True)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, mark_interrupted)
    signal.signal(signal.SIGTERM, mark_interrupted)
    try:
        run, resumed = initialize_or_resume(output_root, tasks)
        progress = Progress(output_root, tasks, run)
        pending: list[Task] = []
        for task in tasks:
            record = completed_record(output_root, task, run["run_id"])
            if record is not None:
                progress.existing(task, record)
            else:
                pending.append(task)
        print(
            f"run_id={run['run_id']} resumed={str(resumed).lower()} planned={len(tasks)} "
            f"completed={len(tasks) - len(pending)} pending={len(pending)} workers={args.workers}",
            flush=True,
        )
        print(f"archive_root={run['archive_root']}", flush=True)
        work_root = output_root / "reparse-work" / run["run_id"]
        futures: dict[Future[dict[str, Any]], Task] = {}
        with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="mmdoc-mineru") as executor:
            for task in pending:
                future = executor.submit(
                    parse_task, task, output_root, work_root, run["run_id"],
                    args.parser_bin, args.env_file, progress,
                    args.max_upload_pages, args.chunk_pages, args.attempts, args.timeout,
                )
                futures[future] = task
            for future in as_completed(futures):
                task = futures[future]
                try:
                    record = future.result()
                    print(render_progress(progress.snapshot(), task, record), flush=True)
                except Exception as error:
                    print(f"[worker-error] {task.key}: {type(error).__name__}: {error}", flush=True)
        state = progress.snapshot()
        status = "completed" if state["failed"] == 0 else "completed_with_failures"
        progress.finish(status)
        aggregate(output_root, tasks, run["run_id"])
        run.update({"status": status, "finished_at_epoch": time.time()})
        atomic_json(current_run_path(output_root), run)
        print(f"status={status}", flush=True)
        print(f"progress={progress.path}", flush=True)
        return 0 if status == "completed" else 2
    except KeyboardInterrupt:
        interrupted = True
        if progress is not None:
            progress.finish("paused")
        if run is not None:
            run.update({"status": "paused", "paused_at_epoch": time.time()})
            atomic_json(current_run_path(output_root), run)
        print("status=paused; relaunch the same command to resume", flush=True)
        return 130
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
