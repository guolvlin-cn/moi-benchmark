#!/usr/bin/env python3
"""Resume FAB-Bench PDF precision parsing and build one public MOI-ready corpus."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

from reparse_mmdoc_datasets import (  # noqa: E402
    Task,
    atomic_json,
    parse_task,
    read_jsonl,
    target_dir,
    write_jsonl,
)

DATASET = "fab-bench"
SOURCE_ROOT = ROOT / "datasets/downloads/prepared/fab-bench-complete-20260805"
ORIGINALS = SOURCE_ROOT / "assets/originals"
BASE_READY = SOURCE_ROOT / "moi-ready/moi-documents.jsonl"
OUTPUT_ROOT = ROOT / "outputs/parsed-documents/fab-bench-mineru-work"
READY_ROOT = ROOT / "outputs/parsed-documents/moi-ready-v1/datasets/fab-bench-mineru"
ENV_FILE = ROOT / ".env"
PARSER_SOURCE = ROOT / "prototypes/local-matrixflow-parser"
PARSER_BIN = OUTPUT_ROOT / "local-matrixflow-parser"


class Progress:
    def __init__(self, total: int) -> None:
        self.path = OUTPUT_ROOT / "progress.json"
        self.events = OUTPUT_ROOT / "events.jsonl"
        self.lock = threading.Lock()
        self.state = {
            "status": "running",
            "planned": total,
            "pending": total,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "tool_invocations": {"mineru_official_precision": 0},
            "datasets": {DATASET: {"planned": total, "running": 0, "succeeded": 0, "failed": 0}},
        }
        self._save()

    def _save(self) -> None:
        self.state["updated_at_epoch"] = time.time()
        atomic_json(self.path, self.state)

    def task_started(self, task: Task) -> None:
        with self.lock:
            self.state["pending"] -= 1
            self.state["running"] += 1
            self.state["datasets"][DATASET]["running"] += 1
            self._save()

    def invocation(self, task: Task, part: int, attempt: int) -> None:
        with self.lock:
            self.state["tool_invocations"]["mineru_official_precision"] += 1
            with self.events.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"event": "mineru", "document_id": task.document_id,
                                         "part": part, "attempt": attempt, "time": time.time()}) + "\n")
            self._save()

    def task_finished(self, task: Task, record: dict) -> None:
        key = "succeeded" if record.get("status") == "ok" else "failed"
        with self.lock:
            self.state["running"] -= 1
            self.state[key] += 1
            self.state["datasets"][DATASET]["running"] -= 1
            self.state["datasets"][DATASET][key] += 1
            self._save()

    def finish(self, status: str) -> None:
        with self.lock:
            self.state["status"] = status
            self.state["finished_at_epoch"] = time.time()
            self._save()


def metadata_doc_id(row: dict) -> str:
    metadata = row.get("metadata") or {}
    return str(metadata.get("benchmark_document_id") or metadata.get("document_id") or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    READY_ROOT.mkdir(parents=True, exist_ok=True)
    sources = sorted(ORIGINALS.glob("*.pdf"))
    if len(sources) != 45:
        raise SystemExit(f"expected 45 acquired FAB PDFs, found {len(sources)}")
    if not BASE_READY.is_file():
        raise SystemExit(f"missing public FAB MOI-ready base: {BASE_READY}")
    subprocess.run(["go", "build", "-o", str(PARSER_BIN), "./cmd/local-matrixflow-parser"],
                   cwd=PARSER_SOURCE, check=True)
    tasks = [Task(DATASET, source.stem, str(source.resolve())) for source in sources]
    run_id = "fab-mineru-public-v1"
    progress = Progress(len(tasks))
    pending: list[Task] = []
    for task in tasks:
        record_path = target_dir(OUTPUT_ROOT, task) / "record.json"
        if record_path.is_file():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("status") == "ok" and record.get("reparse_run_id") == run_id:
                progress.state["pending"] -= 1
                progress.state["succeeded"] += 1
                progress.state["datasets"][DATASET]["succeeded"] += 1
                progress.state["tool_invocations"]["mineru_official_precision"] += sum(
                    attempt.get("tool") == "mineru_official_precision"
                    for attempt in record.get("attempts", [])
                )
                progress._save()
                continue
        pending.append(task)
    work = OUTPUT_ROOT / "work"
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        futures = {
            pool.submit(parse_task, task, OUTPUT_ROOT, work, run_id, PARSER_BIN, ENV_FILE,
                        progress, 200, 180, 3, 3600): task
            for task in pending
        }
        for future in as_completed(futures):
            record = future.result()
            state = progress.state
            done = state["succeeded"] + state["failed"]
            print(f"[{record['status']}] FAB MinerU {done}/{len(tasks)} {record['document_id']}", flush=True)
    records = []
    precision_rows = []
    for task in tasks:
        record = json.loads((target_dir(OUTPUT_ROOT, task) / "record.json").read_text(encoding="utf-8"))
        records.append(record)
        if record.get("status") == "ok":
            precision_rows.extend(read_jsonl(Path(record["documents_path"])))
    failed = [record for record in records if record.get("status") != "ok"]
    if failed:
        progress.finish("failed")
        write_jsonl(OUTPUT_ROOT / "manifest.jsonl", records)
        raise SystemExit(f"{len(failed)} FAB MinerU parses failed; refusing partial ingest")
    acquired = {task.document_id for task in tasks}
    evidence_rows = [row for row in read_jsonl(BASE_READY) if metadata_doc_id(row) not in acquired]
    combined = evidence_rows + precision_rows
    write_jsonl(READY_ROOT / "moi-documents.jsonl", combined)
    write_jsonl(READY_ROOT / "manifest.jsonl", records)
    atomic_json(READY_ROOT / "summary.json", {
        "schema_version": "moi-ready-v1",
        "dataset": DATASET,
        "status": "ready-public-evidence-mineru",
        "public_complete": True,
        "source_complete": False,
        "mineru_precision_documents": len(tasks),
        "evidence_only_documents": 82,
        "moi_document_blocks": len(combined),
        "mineru_tool_invocations": progress.state["tool_invocations"]["mineru_official_precision"],
        "moi_documents_path": str(READY_ROOT / "moi-documents.jsonl"),
    })
    progress.finish("succeeded")
    print(f"FAB MOI-ready: blocks={len(combined)} path={READY_ROOT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
