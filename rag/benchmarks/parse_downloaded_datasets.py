#!/usr/bin/env python3
"""Parse every downloaded benchmark corpus into MOI-ready document blocks.

The runner is resumable. Each source item owns one stable output directory and
is considered complete only when record.json says status=ok and its payload
contains result.json, documents.jsonl, and summary.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq


SCHEMA_VERSION = "moi-parsed-corpus-v1"
RUN_ID = "downloaded-benchmarks-20260804"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "parsed-documents" / "moi-ready-v1"
DEFAULT_ENV = ROOT / ".env"
DEFAULT_PARSER = Path("/tmp/moi-local-matrixflow-parser-datasets")
DOCUMENT_RAG = ROOT / "datasets" / "downloads" / "document-rag"
PUBLIC = ROOT / "datasets" / "downloads" / "public"
OMNI_RUN = ROOT / "runs" / "stage1" / "omnidocbench" / "20260804-precision-full-1651"
SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class Task:
    dataset: str
    document_id: str
    source_path: str
    mode: str
    pipeline: str
    profile: str = "v3-native"
    source_kind: str = "file"
    reuse_run: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

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
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hardlink_or_copy(source: str, destination: str) -> str:
    try:
        os.link(source, destination)
        return destination
    except OSError:
        return shutil.copy2(source, destination)


def copy_payload(source_run: Path, destination: Path) -> None:
    required = ("result.json", "documents.jsonl", "summary.json")
    for name in required:
        if not (source_run / name).is_file():
            raise FileNotFoundError(source_run / name)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    for name in (*required, "plain-text.txt"):
        source = source_run / name
        if source.is_file():
            hardlink_or_copy(str(source), str(temporary / name))
    artifacts = source_run / "product-artifacts"
    if artifacts.is_dir():
        shutil.copytree(artifacts, temporary / "product-artifacts", copy_function=hardlink_or_copy)
    os.replace(temporary, destination)


def task_output(output_root: Path, task: Task) -> Path:
    return output_root / "datasets" / task.dataset / "documents" / task.directory_id


def completed_record(output_root: Path, task: Task) -> dict[str, Any] | None:
    path = task_output(output_root, task) / "record.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    payload = task_output(output_root, task) / "payload"
    if record.get("status") != "ok":
        return None
    if not all((payload / name).is_file() for name in ("result.json", "documents.jsonl", "summary.json")):
        return None
    return record


def prepare_mmdocir_sources(output_root: Path) -> list[Path]:
    source_root = output_root / "sources" / "mmdocir"
    pdf_root = source_root / "doc_pdfs"
    existing = sorted(pdf_root.glob("*.pdf"))
    if len(existing) == 313:
        return existing
    source_root.mkdir(parents=True, exist_ok=True)
    archive = DOCUMENT_RAG / "mmdocir" / "data" / "doc_miscellaneous" / "doc_pdfs.rar"
    subprocess.run(["bsdtar", "-xf", str(archive), "-C", str(source_root)], check=True)
    pdfs = sorted(pdf_root.glob("*.pdf"))
    if len(pdfs) != 313:
        raise RuntimeError(f"MMDocIR extraction produced {len(pdfs)} PDFs, want 313")
    return pdfs


def prepare_vidore_sources(output_root: Path) -> list[Task]:
    tasks: list[Task] = []
    root = DOCUMENT_RAG / "vidore-v2" / "data"
    for subset_dir in sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")):
        corpus = subset_dir / "corpus"
        if not corpus.is_dir():
            continue
        parquet_files = sorted(corpus.glob("test-*.parquet"))
        for parquet_path in parquet_files:
            parquet = pq.ParquetFile(parquet_path)
            for batch in parquet.iter_batches(batch_size=64):
                for row in batch.to_pylist():
                    image = row.get("image") or {}
                    raw = image.get("bytes")
                    if not raw:
                        raise ValueError(f"missing image bytes in {parquet_path}")
                    corpus_id = str(row["corpus-id"])
                    path_hint = str(image.get("path") or f"{corpus_id}.jpg")
                    extension = Path(path_hint).suffix.lower()
                    if extension not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}:
                        extension = ".jpg"
                    document_id = f"{subset_dir.name}/test/{corpus_id}"
                    destination = output_root / "sources" / "vidore-v2" / subset_dir.name / f"{corpus_id}{extension}"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if not destination.is_file() or destination.stat().st_size != len(raw):
                        temporary = destination.with_suffix(destination.suffix + ".tmp")
                        temporary.write_bytes(raw)
                        os.replace(temporary, destination)
                    metadata = {key: value for key, value in row.items() if key != "image"}
                    metadata.update({"subset": subset_dir.name, "split": "test", "image_path": path_hint})
                    tasks.append(Task(
                        dataset="vidore-v2",
                        document_id=document_id,
                        source_path=str(destination),
                        mode="parse",
                        pipeline="vlm",
                        source_kind="parquet-image",
                        metadata=metadata,
                    ))
    if len(tasks) != 4544:
        raise RuntimeError(f"ViDoRe extraction produced {len(tasks)} test pages, want 4544")
    return tasks


def prepare_multihop_sources(output_root: Path) -> list[Task]:
    corpus = json.loads((PUBLIC / "multihop-rag" / "corpus.json").read_text(encoding="utf-8"))
    tasks: list[Task] = []
    for index, row in enumerate(corpus):
        document_id = f"article-{index:04d}"
        destination = output_root / "sources" / "multihop-rag" / f"{document_id}.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        title = str(row.get("title") or document_id).strip()
        body = str(row.get("body") or "").strip()
        payload = f"# {title}\n\n{body}\n"
        if not destination.is_file() or destination.read_text(encoding="utf-8") != payload:
            destination.write_text(payload, encoding="utf-8")
        metadata = {key: value for key, value in row.items() if key != "body"}
        tasks.append(Task(
            dataset="multihop-rag",
            document_id=document_id,
            source_path=str(destination),
            mode="parse",
            pipeline="local",
            source_kind="json-to-markdown",
            metadata=metadata,
        ))
    if len(tasks) != 609:
        raise RuntimeError(f"MultiHop-RAG produced {len(tasks)} documents, want 609")
    return tasks


def omnidocbench_tasks() -> list[Task]:
    samples = {row["page_id"]: row for row in read_jsonl(OMNI_RUN / "artifacts" / "sample-manifest.jsonl")}
    attempts = [
        row for row in read_jsonl(OMNI_RUN / "moi-unified" / "attempts.jsonl")
        if row.get("status") == "ok" and row.get("pipeline") == "precision"
    ]
    tasks: list[Task] = []
    for row in attempts:
        page_id = row["page_id"]
        sample = samples[page_id]
        tasks.append(Task(
            dataset="omnidocbench",
            document_id=page_id,
            source_path=sample["input_pdf"],
            mode="reuse",
            pipeline="precision",
            source_kind="page-pdf",
            reuse_run=row["parser_run_dir"],
            metadata={
                "data_source": sample.get("data_source"),
                "language": sample.get("language"),
                "layout": sample.get("layout"),
                "special_issue": sample.get("special_issue"),
                "original_image": sample.get("image_path"),
                "reused": bool(row.get("reused")),
            },
        ))
    if len(tasks) != 1651:
        raise RuntimeError(f"OmniDocBench reuse has {len(tasks)} pages, want 1651")
    return tasks


def pdf_tasks(dataset: str, paths: Iterable[Path], prefix: str = "") -> list[Task]:
    tasks = []
    for path in sorted(paths):
        relative = f"{prefix}/{path.stem}" if prefix else path.stem
        tasks.append(Task(
            dataset=dataset,
            document_id=relative,
            source_path=str(path.resolve()),
            mode="parse",
            pipeline="precision",
            source_kind="pdf",
        ))
    return tasks


def round_robin(groups: list[list[Task]]) -> list[Task]:
    pending = [iter(group) for group in groups]
    result: list[Task] = []
    while pending:
        next_round = []
        for iterator in pending:
            try:
                result.append(next(iterator))
                next_round.append(iterator)
            except StopIteration:
                pass
        pending = next_round
    return result


def build_tasks(output_root: Path) -> list[Task]:
    readoc_arxiv = pdf_tasks(
        "readoc", (DOCUMENT_RAG / "readoc" / "data" / "arxiv" / "pdf").glob("*.pdf"), "arxiv"
    )
    readoc_github = pdf_tasks(
        "readoc", (DOCUMENT_RAG / "readoc" / "data" / "github" / "pdf").glob("*.pdf"), "github"
    )
    readoc = readoc_arxiv + readoc_github
    if len(readoc) != 2233:
        raise RuntimeError(f"READoc has {len(readoc)} PDFs, want 2233")

    mmdocir = pdf_tasks("mmdocir", prepare_mmdocir_sources(output_root))
    docbench = pdf_tasks("docbench", (DOCUMENT_RAG / "docbench" / "data").glob("*/*.pdf"))
    mmdocrag = pdf_tasks("mmdocrag", (DOCUMENT_RAG / "mmdocrag" / "data" / "doc_pdfs").glob("*.pdf"))
    expected = {"mmdocir": (mmdocir, 313), "docbench": (docbench, 229), "mmdocrag": (mmdocrag, 220)}
    for name, (tasks, count) in expected.items():
        if len(tasks) != count:
            raise RuntimeError(f"{name} has {len(tasks)} PDFs, want {count}")

    precision = round_robin([readoc, mmdocir, docbench, mmdocrag])
    return omnidocbench_tasks() + precision + prepare_vidore_sources(output_root) + prepare_multihop_sources(output_root)


class Progress:
    def __init__(self, output_root: Path, tasks: list[Task]) -> None:
        self.output_root = output_root
        self.path = output_root / "progress.json"
        self.events = output_root / "events.jsonl"
        self.lock = threading.Lock()
        datasets: dict[str, dict[str, int]] = {}
        for task in tasks:
            datasets.setdefault(task.dataset, {"planned": 0, "running": 0, "succeeded": 0, "failed": 0, "reused": 0})
            datasets[task.dataset]["planned"] += 1
        self.state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "status": "preparing",
            "started_at_epoch": time.time(),
            "updated_at_epoch": time.time(),
            "planned": len(tasks),
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped_completed": 0,
            "datasets": datasets,
            "tool_invocations": {
                "mineru_official_precision": 0,
                "taas_qwen3_vl_plus": 0,
                "matrixflow_native_parser": 0,
                "reused_mineru_precision_result": 0,
                "openxml_service": 0,
                "soffice_converter": 0,
                "pdfium_native": 0,
            },
            "backend_successes": {},
        }
        atomic_json(self.path, self.state)

    def _save(self) -> None:
        self.state["updated_at_epoch"] = time.time()
        atomic_json(self.path, self.state)

    def set_running(self) -> None:
        with self.lock:
            self.state["status"] = "running"
            self._save()

    def mark_existing(self, task: Task, record: dict[str, Any]) -> None:
        with self.lock:
            self.state["succeeded"] += 1
            self.state["skipped_completed"] += 1
            dataset = self.state["datasets"][task.dataset]
            dataset["succeeded"] += 1
            if record.get("reused"):
                dataset["reused"] += 1
                key = "reused_mineru_precision_result"
                self.state["tool_invocations"][key] = self.state["tool_invocations"].get(key, 0) + 1
            else:
                for attempt in record.get("attempts", []):
                    tool = attempt.get("tool")
                    if tool:
                        self.state["tool_invocations"][tool] = self.state["tool_invocations"].get(tool, 0) + 1
            backend = record.get("backend_used")
            if backend:
                self.state["backend_successes"][backend] = self.state["backend_successes"].get(backend, 0) + 1
            self._save()

    def started(self, task: Task) -> None:
        with self.lock:
            self.state["running"] += 1
            self.state["datasets"][task.dataset]["running"] += 1
            self._save()

    def invocation(self, task: Task, tool: str, attempt: int) -> None:
        with self.lock:
            self.state["tool_invocations"][tool] = self.state["tool_invocations"].get(tool, 0) + 1
            self.events.parent.mkdir(parents=True, exist_ok=True)
            with self.events.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "event": "tool_invocation", "tool": tool, "attempt": attempt,
                    "dataset": task.dataset, "document_id": task.document_id, "time": time.time(),
                }, ensure_ascii=False) + "\n")
            self._save()

    def finished(self, task: Task, ok: bool, record: dict[str, Any]) -> None:
        with self.lock:
            self.state["running"] -= 1
            dataset = self.state["datasets"][task.dataset]
            dataset["running"] -= 1
            key = "succeeded" if ok else "failed"
            self.state[key] += 1
            dataset[key] += 1
            if record.get("reused"):
                dataset["reused"] += 1
            backend = record.get("backend_used")
            if ok and backend:
                self.state["backend_successes"][backend] = self.state["backend_successes"].get(backend, 0) + 1
            self._save()

    def complete(self) -> None:
        with self.lock:
            self.state["status"] = "completed" if self.state["failed"] == 0 else "completed_with_failures"
            self.state["finished_at_epoch"] = time.time()
            self._save()


def tool_for(task: Task) -> str:
    if task.mode == "reuse":
        return "reused_mineru_precision_result"
    if task.pipeline == "precision":
        return "mineru_official_precision"
    if task.pipeline == "vlm":
        return "taas_qwen3_vl_plus"
    return "matrixflow_native_parser"


def run_task(
    task: Task,
    output_root: Path,
    parser_bin: Path,
    env_file: Path,
    progress: Progress,
) -> dict[str, Any]:
    progress.started(task)
    document_dir = task_output(output_root, task)
    document_dir.mkdir(parents=True, exist_ok=True)
    source = Path(task.source_path)
    started = time.time()
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "dataset": task.dataset,
        "document_id": task.document_id,
        "directory_id": task.directory_id,
        "source_path": str(source),
        "source_kind": task.source_kind,
        "source_sha256": sha256_file(source),
        "mode": task.mode,
        "pipeline": task.pipeline,
        "profile": task.profile,
        "metadata": task.metadata,
        "started_at_epoch": started,
        "status": "failed",
        "attempts": [],
    }
    try:
        payload = document_dir / "payload"
        if payload.exists():
            raise FileExistsError(f"incomplete destination already has payload: {payload}")
        if task.mode == "reuse":
            progress.invocation(task, tool_for(task), 0)
            copy_payload(Path(task.reuse_run), payload)
            record["reused"] = True
            record["reused_from"] = task.reuse_run
        else:
            max_attempts = 3 if task.pipeline == "vlm" else 2 if task.pipeline == "precision" else 1
            timeout = 20 * 60 if task.pipeline == "precision" else 5 * 60
            success_run: Path | None = None
            for attempt in range(1, max_attempts + 1):
                tool = tool_for(task)
                progress.invocation(task, tool, attempt)
                command = [
                    str(parser_bin), "parse", "--input", str(source),
                    "--env-file", str(env_file), "--run", str(document_dir / ".runs"),
                ]
                if task.pipeline == "local":
                    command.extend(["--profile", task.profile])
                else:
                    command.extend(["--pipeline", task.pipeline])
                attempt_started = time.time()
                try:
                    completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
                    attempt_row = {
                        "attempt": attempt,
                        "tool": tool,
                        "returncode": completed.returncode,
                        "duration_seconds": time.time() - attempt_started,
                        "stdout": completed.stdout[-12000:],
                        "stderr": completed.stderr[-12000:],
                    }
                    record["attempts"].append(attempt_row)
                    run_match = re.search(r"^run_dir=(.+)$", completed.stdout, re.MULTILINE)
                    if completed.returncode == 0 and run_match:
                        success_run = Path(run_match.group(1).strip())
                        break
                except subprocess.TimeoutExpired as error:
                    record["attempts"].append({
                        "attempt": attempt, "tool": tool, "timeout": timeout,
                        "duration_seconds": time.time() - attempt_started,
                        "stdout": str(error.stdout or "")[-12000:], "stderr": str(error.stderr or "")[-12000:],
                    })
                if attempt < max_attempts:
                    time.sleep(min(20, 3 * attempt))
            if success_run is None:
                raise RuntimeError("all parser attempts failed")
            os.replace(success_run, payload)
        summary = json.loads((payload / "summary.json").read_text(encoding="utf-8"))
        record.update({
            "status": "ok",
            "payload_path": str(payload),
            "result_path": str(payload / "result.json"),
            "documents_path": str(payload / "documents.jsonl"),
            "summary_path": str(payload / "summary.json"),
            "backend_used": summary.get("backend_used"),
            "parser_version": summary.get("parser_version"),
            "documents": summary.get("documents"),
            "content_chars": summary.get("content_chars"),
            "parser_duration_ms": summary.get("duration_ms"),
        })
    except Exception as error:  # keep the exact item in the denominator
        record["error"] = f"{type(error).__name__}: {error}"
    record["finished_at_epoch"] = time.time()
    record["wall_seconds"] = record["finished_at_epoch"] - started
    atomic_json(document_dir / "record.json", record)
    progress.finished(task, record["status"] == "ok", record)
    return record


def aggregate(output_root: Path, tasks: list[Task], progress: Progress) -> None:
    records: list[dict[str, Any]] = []
    for task in sorted(tasks, key=lambda item: (item.dataset, item.document_id)):
        path = task_output(output_root, task) / "record.json"
        if path.is_file():
            records.append(json.loads(path.read_text(encoding="utf-8")))
    write_jsonl(output_root / "manifest.jsonl", records)

    by_dataset: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_dataset.setdefault(record["dataset"], []).append(record)
    for dataset, dataset_records in by_dataset.items():
        dataset_root = output_root / "datasets" / dataset
        write_jsonl(dataset_root / "manifest.jsonl", dataset_records)
        combined = dataset_root / "moi-documents.jsonl"
        temporary = combined.with_suffix(".jsonl.tmp")
        block_count = 0
        with temporary.open("w", encoding="utf-8") as destination:
            for record in dataset_records:
                if record.get("status") != "ok":
                    continue
                with Path(record["documents_path"]).open(encoding="utf-8") as source:
                    for index, line in enumerate(source):
                        if not line.strip():
                            continue
                        document = json.loads(line)
                        metadata = document.setdefault("metadata", {})
                        metadata.update({
                            "benchmark_dataset": dataset,
                            "benchmark_document_id": record["document_id"],
                            "benchmark_run_id": RUN_ID,
                        })
                        destination.write(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n")
                        block_count += 1
        os.replace(temporary, combined)
        atomic_json(dataset_root / "summary.json", {
            "schema_version": SCHEMA_VERSION,
            "dataset": dataset,
            "planned_documents": len(dataset_records),
            "successful_documents": sum(row.get("status") == "ok" for row in dataset_records),
            "failed_documents": sum(row.get("status") != "ok" for row in dataset_records),
            "moi_document_blocks": block_count,
            "moi_documents_jsonl": str(combined),
        })

    state = json.loads(progress.path.read_text(encoding="utf-8"))
    atomic_json(output_root / "tool-calls.json", {
        "schema_version": SCHEMA_VERSION,
        "counting_unit": "parser task invocation; retries count as additional invocations",
        "tool_invocations": state["tool_invocations"],
        "backend_successes": state["backend_successes"],
    })
    write_report(output_root, state)


def write_report(output_root: Path, state: dict[str, Any]) -> None:
    rows = []
    for name, data in sorted(state["datasets"].items()):
        rows.append(
            f"| {name} | {data['planned']} | {data['succeeded']} | {data['failed']} | {data['reused']} |"
        )
    tools = [f"| {name} | {count} |" for name, count in sorted(state["tool_invocations"].items())]
    report = f"""# Downloaded benchmark parser report

- Run ID: `{RUN_ID}`
- Status: `{state['status']}`
- Planned documents: {state['planned']}
- Successful documents: {state['succeeded']}
- Failed documents: {state['failed']}
- Output schema: MatrixFlow standard `types.Document`, one JSON object per line

## Dataset results

| Dataset | Planned | Succeeded | Failed | Reused |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## Tool invocations

Retries are counted as additional invocations. Reused OmniDocBench results are
reported separately and did not create a new cloud request during this run.

| Tool | Invocations |
| --- | ---: |
{chr(10).join(tools)}

## Excluded datasets

- Double-Bench: corpus was not downloaded.
- Stage 2/Stage 3 MOI Benchmark Dataset v1: not yet created under `datasets/`.
- RAGBench: processed-context reader/evaluator data, not a raw document corpus.
- ALCE, RGB, RAGTruth: authorization/Judge calibration lanes; the plan does not
  permit treating them as MOI raw-document ingestion datasets.

Each dataset directory contains `manifest.jsonl`, `summary.json`, a directly
loadable `moi-documents.jsonl`, and per-source immutable parser payloads.
"""
    (output_root / "REPORT.md").write_text(report, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--parser-bin", type=Path, default=DEFAULT_PARSER)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--precision-workers", type=int, default=4)
    parser.add_argument("--vlm-workers", type=int, default=4)
    parser.add_argument("--local-workers", type=int, default=8)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(output_root)
    task_keys = [task.key for task in tasks]
    if len(set(task_keys)) != len(task_keys):
        raise RuntimeError("duplicate dataset/document task key")
    write_jsonl(output_root / "task-manifest.jsonl", (asdict(task) for task in tasks))
    progress = Progress(output_root, tasks)

    pending: list[Task] = []
    for task in tasks:
        existing = completed_record(output_root, task)
        if existing is not None:
            progress.mark_existing(task, existing)
        else:
            pending.append(task)
    progress.set_running()

    executors = {
        "precision": ThreadPoolExecutor(max_workers=args.precision_workers, thread_name_prefix="mineru"),
        "vlm": ThreadPoolExecutor(max_workers=args.vlm_workers, thread_name_prefix="taas"),
        "local": ThreadPoolExecutor(max_workers=args.local_workers, thread_name_prefix="local"),
    }
    futures: dict[Future[dict[str, Any]], Task] = {}
    try:
        for task in pending:
            pool = "precision" if task.mode != "reuse" and task.pipeline == "precision" else "vlm" if task.pipeline == "vlm" else "local"
            future = executors[pool].submit(run_task, task, output_root, args.parser_bin, args.env_file, progress)
            futures[future] = task
        for future in as_completed(futures):
            task = futures[future]
            try:
                record = future.result()
                print(
                    f"[{record['status']}] {task.dataset}/{task.document_id} "
                    f"backend={record.get('backend_used', '-')} wall={record.get('wall_seconds', 0):.1f}s",
                    flush=True,
                )
            except Exception as error:
                print(f"[worker-error] {task.key}: {error}", flush=True)
    finally:
        for executor in executors.values():
            executor.shutdown(wait=True, cancel_futures=False)
    progress.complete()
    aggregate(output_root, tasks, progress)
    print(f"report={output_root / 'REPORT.md'}", flush=True)


if __name__ == "__main__":
    main()
