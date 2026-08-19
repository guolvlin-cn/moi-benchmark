#!/usr/bin/env python3
"""Recover failed downloaded-corpus parser tasks.

The normal batch runner intentionally keeps the original source as one task.
MinerU's official precision API rejects PDFs over 200 pages, so this recovery
runner splits those PDFs into 180-page parts, parses each part, and merges the
blocks back into one MOI-ready payload. Exact duplicate PDFs are grouped by
SHA-256 and parsed only once. ViDoRe/TaaS failures are retried one at a time to
reduce gateway pressure.

This script is resumable: successful recovery records are skipped, and the
failed task records retain their previous attempts plus the recovery attempts.
It does not ingest anything into the MOI database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "parsed-documents" / "moi-ready-v1"
DEFAULT_ENV = ROOT / ".env"
DEFAULT_PARSER = Path("/tmp/moi-local-matrixflow-parser-datasets")
DEFAULT_PDFCPU = Path("/tmp/moi-pdfcpu")
SAFE = re.compile(r"[^A-Za-z0-9._-]+")
RECOVERY_CHUNK_PAGES = 180


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_failed_records(output_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((output_root / "datasets").glob("*/documents/*/record.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("status") != "failed":
            continue
        record["_record_path"] = str(path)
        records.append(record)
    return records


def task_dir(record: dict[str, Any]) -> Path:
    return Path(record["_record_path"]).parent


def append_attempts(record: dict[str, Any], attempts: list[dict[str, Any]]) -> None:
    record["attempts"] = list(record.get("attempts", [])) + attempts


def run_parser(
    parser_bin: Path,
    env_file: Path,
    source: Path,
    run_root: Path,
    pipeline: str,
    attempt: int,
    timeout: int,
) -> tuple[Path | None, dict[str, Any]]:
    run_root.mkdir(parents=True, exist_ok=True)
    command = [
        str(parser_bin),
        "parse",
        "--input",
        str(source),
        "--env-file",
        str(env_file),
        "--run",
        str(run_root),
        "--pipeline",
        pipeline,
    ]
    started = time.time()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        stdout = completed.stdout[-12000:]
        stderr = completed.stderr[-12000:]
        row: dict[str, Any] = {
            "attempt": attempt,
            "tool": "mineru_official_precision" if pipeline == "precision" else "taas_qwen3_vl_plus",
            "returncode": completed.returncode,
            "duration_seconds": time.time() - started,
            "stdout": stdout,
            "stderr": stderr,
            "recovery": True,
        }
        match = re.search(r"^run_dir=(.+)$", stdout, re.MULTILINE)
        if completed.returncode == 0 and match:
            return Path(match.group(1).strip()), row
        return None, row
    except subprocess.TimeoutExpired as error:
        return None, {
            "attempt": attempt,
            "tool": "mineru_official_precision" if pipeline == "precision" else "taas_qwen3_vl_plus",
            "timeout": timeout,
            "duration_seconds": time.time() - started,
            "stdout": str(error.stdout or "")[-12000:],
            "stderr": str(error.stderr or "")[-12000:],
            "recovery": True,
        }


def split_pdf(source: Path, parts_root: Path, pdfcpu_bin: Path) -> list[tuple[Path, int, int]]:
    """Split with pdfcpu and recover the original page span from filenames."""
    parts_root.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(r"_(\d+)-(\d+)\.pdf$")
    part_files = []
    for path in parts_root.glob("*.pdf"):
        match = pattern.search(path.name)
        if match:
            part_files.append((int(match.group(1)), int(match.group(2)), path))
    if not part_files:
        completed = subprocess.run(
            [str(pdfcpu_bin), "split", "-m", "span", str(source), str(parts_root), str(RECOVERY_CHUNK_PAGES)],
            text=True,
            capture_output=True,
            timeout=30 * 60,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"pdfcpu split failed: {completed.stderr[-4000:]}")
        for path in parts_root.glob("*.pdf"):
            match = pattern.search(path.name)
            if match:
                part_files.append((int(match.group(1)), int(match.group(2)), path))
    if not part_files:
        raise RuntimeError("pdfcpu produced no page-span files")
    part_files.sort(key=lambda row: row[0])
    return [(path, start - 1, end) for start, end, path in part_files]


def read_payload(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str, dict[str, Any]]:
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    documents = [
        json.loads(line)
        for line in (run_dir / "documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    plain_text = result.get("plain_text", "")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    return result, documents, plain_text, summary


def merge_precision_parts(
    source: Path,
    source_sha: str,
    parts: list[tuple[Path, int, int, Path]],
    cache_payload: Path,
) -> dict[str, Any]:
    merged_documents: list[dict[str, Any]] = []
    plain_text_parts: list[str] = []
    result_template: dict[str, Any] | None = None
    summaries: list[dict[str, Any]] = []
    part_manifest: list[dict[str, Any]] = []
    file_id = f"local_{source_sha[:24]}"

    for part_number, (part_path, start, end, run_dir) in enumerate(parts):
        result, documents, plain_text, summary = read_payload(run_dir)
        if result_template is None:
            result_template = result
        summaries.append(summary)
        if plain_text:
            plain_text_parts.append(plain_text)
        part_manifest.append({
            "part": part_number,
            "path": str(part_path),
            "page_start": start + 1,
            "page_end": end,
            "run_dir": str(run_dir),
        })
        for document in documents:
            metadata = dict(document.get("metadata") or {})
            block_index = len(merged_documents)
            page_num = metadata.get("page_num")
            if isinstance(page_num, int):
                metadata["page_num"] = page_num + start
            metadata.update({
                "file_id": file_id,
                "raw_file_id": file_id,
                "file_name": source.name,
                "source_path": str(source),
                "rescue_split": True,
                "rescue_part": part_number,
                "rescue_page_start": start + 1,
                "rescue_page_end": end,
                "original_source_path": str(source),
            })
            normalized = dict(document)
            normalized["metadata"] = metadata
            normalized["document_index"] = block_index
            normalized["block_uuid"] = f"{file_id}-rescue-{block_index}"
            merged_documents.append(normalized)

    if result_template is None:
        raise RuntimeError("no successful MinerU split payloads")
    block_types = Counter(str(document.get("type", "unknown")) for document in merged_documents)
    content_chars = sum(len(str(document.get("content", ""))) for document in merged_documents)
    total_duration = sum(float(summary.get("duration_ms") or 0) for summary in summaries)
    first_summary = summaries[0]
    rescue_info = {
        "method": "pdf-split-and-merge",
        "chunk_pages": RECOVERY_CHUNK_PAGES,
        "original_page_count": sum(end - start for _, start, end, _ in parts),
        "parts": part_manifest,
    }
    result = dict(result_template)
    result.update({
        "source_path": str(source),
        "file_type": "pdf",
        "documents": merged_documents,
        "plain_text": "\n\n".join(plain_text_parts),
        "md_file_id": file_id,
        "metadata": {
            **dict(result_template.get("metadata") or {}),
            "backend_used": "mineru-official-precision-rescue-split",
            "rescue": rescue_info,
        },
        "rescue": rescue_info,
        "duration_ms": total_duration,
    })
    summary = {
        "schema_version": first_summary.get("schema_version"),
        "engine": first_summary.get("engine"),
        "source_path": str(source),
        "file_type": "pdf",
        "documents": len(merged_documents),
        "block_types": dict(block_types),
        "content_chars": content_chars,
        "duration_ms": total_duration,
        "backend_used": "mineru-official-precision-rescue-split",
        "parser_version": first_summary.get("parser_version"),
        "tier_requested": first_summary.get("tier_requested"),
        "tier_effective": first_summary.get("tier_effective"),
        "web_equivalent": first_summary.get("web_equivalent", False),
        "route": first_summary.get("route"),
        "rescue": rescue_info,
    }
    cache_payload.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_payload.with_name(cache_payload.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    atomic_json(temporary / "result.json", result)
    write_jsonl(temporary / "documents.jsonl", merged_documents)
    atomic_json(temporary / "summary.json", summary)
    (temporary / "plain-text.txt").write_text(result["plain_text"], encoding="utf-8")
    atomic_json(temporary / "rescue.json", rescue_info)
    if cache_payload.exists():
        shutil.rmtree(cache_payload)
    os.replace(temporary, cache_payload)
    return {"summary": summary, "rescue": rescue_info}


def materialize_cached_payload(cache_payload: Path, record: dict[str, Any], source: Path) -> None:
    target_dir = task_dir(record)
    payload = target_dir / "payload"
    temporary = target_dir / "payload.rescue-tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(cache_payload, temporary)
    result = json.loads((temporary / "result.json").read_text(encoding="utf-8"))
    documents = [
        json.loads(line)
        for line in (temporary / "documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # The cache is content-addressed, but each MOI dataset needs its own source
    # and benchmark identity in block metadata.
    for document in documents:
        metadata = dict(document.get("metadata") or {})
        metadata["source_path"] = str(source)
        metadata["file_name"] = source.name
        metadata["benchmark_dataset"] = record["dataset"]
        metadata["benchmark_document_id"] = record["document_id"]
        document["metadata"] = metadata
    result["source_path"] = str(source)
    result["documents"] = documents
    result["rescue"] = {**dict(result.get("rescue") or {}), "materialized_from_cache": True}
    summary = json.loads((temporary / "summary.json").read_text(encoding="utf-8"))
    summary["source_path"] = str(source)
    summary["rescue"] = {**dict(summary.get("rescue") or {}), "materialized_from_cache": True}
    atomic_json(temporary / "result.json", result)
    write_jsonl(temporary / "documents.jsonl", documents)
    atomic_json(temporary / "summary.json", summary)
    if payload.exists():
        shutil.rmtree(payload)
    os.replace(temporary, payload)


def update_record_ok(
    record: dict[str, Any],
    attempts: list[dict[str, Any]],
    backend: str,
    rescue: dict[str, Any],
) -> None:
    append_attempts(record, attempts)
    record_path = task_dir(record) / "record.json"
    record.pop("_record_path", None)
    payload = record_path.parent / "payload"
    summary = json.loads((payload / "summary.json").read_text(encoding="utf-8"))
    record.update({
        "status": "ok",
        "payload_path": str(payload),
        "result_path": str(payload / "result.json"),
        "documents_path": str(payload / "documents.jsonl"),
        "summary_path": str(payload / "summary.json"),
        "backend_used": backend,
        "parser_version": summary.get("parser_version"),
        "documents": summary.get("documents"),
        "content_chars": summary.get("content_chars"),
        "parser_duration_ms": summary.get("duration_ms"),
        "rescue": rescue,
        "recovered_at_epoch": time.time(),
    })
    record.pop("error", None)
    atomic_json(record_path, record)


def update_record_failed(record: dict[str, Any], attempts: list[dict[str, Any]], rescue: dict[str, Any]) -> None:
    append_attempts(record, attempts)
    record_path = task_dir(record) / "record.json"
    record.pop("_record_path", None)
    record["rescue"] = rescue
    record["recovered_at_epoch"] = time.time()
    record["error"] = "RuntimeError: recovery attempts failed"
    atomic_json(record_path, record)


def recover_precision_group(
    source_sha: str,
    records: list[dict[str, Any]],
    output_root: Path,
    parser_bin: Path,
    env_file: Path,
    pdfcpu_bin: Path,
    max_attempts: int,
) -> dict[str, Any]:
    source = Path(records[0]["source_path"])
    work_root = output_root / "rescue-work" / "precision" / source_sha
    parts_root = work_root / "pdfcpu-parts"
    cache_payload = work_root / "payload"
    if cache_payload.is_dir() and all((cache_payload / name).is_file() for name in ("result.json", "documents.jsonl", "summary.json")):
        rescue = {"method": "pdf-split-and-merge", "source_sha256": source_sha, "cache_hit": True}
        for index, record in enumerate(records):
            materialize_cached_payload(cache_payload, record, Path(record["source_path"]))
            attempts = [{
                "attempt": 0,
                "tool": "reused_rescue_precision_result",
                "returncode": 0,
                "recovery": True,
                "cache_key": source_sha,
            }]
            update_record_ok(record, attempts, "mineru-official-precision-rescue-split", {**rescue, "cache_reuse": index > 0})
        return {"source_sha256": source_sha, "tasks": len(records), "recovered": len(records), "tool_calls": 0, "cache_reuses": len(records)}

    try:
        raw_parts = split_pdf(source, parts_root, pdfcpu_bin)
        parsed_parts: list[tuple[Path, int, int, Path]] = []
        attempts: list[dict[str, Any]] = []
        for part_number, (part_path, start, end) in enumerate(raw_parts):
            part_run_root = parts_root / f"part-{part_number:03d}" / "runs"
            successful_run: Path | None = None
            for attempt in range(1, max_attempts + 1):
                successful_run, row = run_parser(parser_bin, env_file, part_path, part_run_root, "precision", attempt, 30 * 60)
                row.update({"part": part_number, "page_start": start + 1, "page_end": end})
                attempts.append(row)
                if successful_run is not None:
                    break
                if attempt < max_attempts:
                    time.sleep(15 * attempt)
            if successful_run is None:
                raise RuntimeError(f"part {part_number} failed")
            parsed_parts.append((part_path, start, end, successful_run))
        merge_precision_parts(source, source_sha, parsed_parts, cache_payload)
        rescue = {"method": "pdf-split-and-merge", "source_sha256": source_sha, "parts": len(parsed_parts), "cache_hit": False}
        for index, record in enumerate(records):
            materialize_cached_payload(cache_payload, record, Path(record["source_path"]))
            task_attempts = attempts if index == 0 else [{
                "attempt": 0,
                "tool": "reused_rescue_precision_result",
                "returncode": 0,
                "recovery": True,
                "cache_key": source_sha,
            }]
            update_record_ok(record, task_attempts, "mineru-official-precision-rescue-split", {**rescue, "cache_reuse": index > 0})
        return {"source_sha256": source_sha, "tasks": len(records), "recovered": len(records), "tool_calls": len(attempts), "cache_reuses": max(0, len(records) - 1)}
    except Exception as error:
        rescue = {"method": "pdf-split-and-merge", "source_sha256": source_sha, "error": f"{type(error).__name__}: {error}"}
        for record in records:
            update_record_failed(record, attempts if "attempts" in locals() else [], rescue)
        return {"source_sha256": source_sha, "tasks": len(records), "recovered": 0, "tool_calls": len(attempts) if "attempts" in locals() else 0, "error": str(error)}


def recover_vlm(
    record: dict[str, Any],
    output_root: Path,
    parser_bin: Path,
    env_file: Path,
    max_attempts: int,
) -> dict[str, Any]:
    source = Path(record["source_path"])
    work_root = output_root / "rescue-work" / "vlm" / SAFE.sub("_", record["dataset"] + "-" + record["document_id"])
    run_root = work_root / "runs"
    attempts: list[dict[str, Any]] = []
    successful_run: Path | None = None
    for attempt in range(1, max_attempts + 1):
        successful_run, row = run_parser(parser_bin, env_file, source, run_root, "vlm", attempt, 10 * 60)
        attempts.append(row)
        if successful_run is not None:
            break
        if attempt < max_attempts:
            time.sleep(30 * attempt)
    if successful_run is None:
        update_record_failed(record, attempts, {"method": "vlm-serial-retry", "error": "all attempts failed"})
        return {"dataset": record["dataset"], "document_id": record["document_id"], "recovered": 0, "tool_calls": len(attempts)}
    target_dir = task_dir(record)
    payload = target_dir / "payload"
    temporary = target_dir / "payload.rescue-tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(successful_run, temporary)
    if payload.exists():
        shutil.rmtree(payload)
    os.replace(temporary, payload)
    update_record_ok(record, attempts, "taas-vlm", {"method": "vlm-serial-retry", "attempts": len(attempts)})
    return {"dataset": record["dataset"], "document_id": record["document_id"], "recovered": 1, "tool_calls": len(attempts)}


def update_progress_snapshot(output_root: Path, rescue_results: list[dict[str, Any]]) -> None:
    path = output_root / "progress.json"
    if not path.is_file():
        return
    state = json.loads(path.read_text(encoding="utf-8"))
    recovered = sum(int(row.get("recovered", 0)) for row in rescue_results)
    failed_retried = sum(int(row.get("tasks", 1)) for row in rescue_results if not row.get("recovered"))
    # The stopped batch has no active workers. Keep its paused status while
    # bringing the counts in line with the per-document records.
    records = []
    for record_path in (output_root / "datasets").glob("*/documents/*/record.json"):
        try:
            records.append(json.loads(record_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    state["succeeded"] = sum(record.get("status") == "ok" for record in records)
    state["failed"] = sum(record.get("status") != "ok" for record in records)
    state["running"] = 0
    state["status"] = "paused_by_user"
    for dataset, data in state.get("datasets", {}).items():
        dataset_records = [record for record in records if record.get("dataset") == dataset]
        data["succeeded"] = sum(record.get("status") == "ok" for record in dataset_records)
        data["failed"] = sum(record.get("status") != "ok" for record in dataset_records)
        data["running"] = 0
    state["recovery"] = {
        "recovered_documents": recovered,
        "recovery_results": rescue_results,
        "failed_after_recovery": state["failed"],
        "updated_at_epoch": time.time(),
    }
    state["updated_at_epoch"] = time.time()
    atomic_json(path, state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--parser-bin", type=Path, default=DEFAULT_PARSER)
    parser.add_argument("--pdfcpu-bin", type=Path, default=DEFAULT_PDFCPU)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--precision-workers", type=int, default=2)
    parser.add_argument("--vlm-workers", type=int, default=1)
    parser.add_argument("--precision-attempts", type=int, default=2)
    parser.add_argument("--vlm-attempts", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    records = read_failed_records(output_root)
    precision_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    vlm_records: list[dict[str, Any]] = []
    for record in records:
        source = Path(record["source_path"])
        if not source.is_file():
            record["rescue_source_missing"] = True
            continue
        if record.get("pipeline") == "vlm" or record.get("dataset") == "vidore-v2":
            vlm_records.append(record)
        else:
            precision_groups[sha256_file(source)].append(record)
    print(f"failed_records={len(records)} precision_groups={len(precision_groups)} precision_tasks={sum(map(len, precision_groups.values()))} vlm_tasks={len(vlm_records)}", flush=True)
    if args.dry_run:
        for source_sha, group in sorted(precision_groups.items()):
            print(f"precision_group={source_sha[:12]} source={group[0]['source_path']} tasks={len(group)}", flush=True)
        return

    rescue_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.precision_workers), thread_name_prefix="rescue-mineru") as executor:
        futures = {
            executor.submit(recover_precision_group, source_sha, group, output_root, args.parser_bin, args.env_file, args.pdfcpu_bin, args.precision_attempts): source_sha
            for source_sha, group in precision_groups.items()
        }
        for future in as_completed(futures):
            result = future.result()
            rescue_results.append(result)
            print(f"[precision-rescue] {result}", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.vlm_workers), thread_name_prefix="rescue-taas") as executor:
        futures = {
            executor.submit(recover_vlm, record, output_root, args.parser_bin, args.env_file, args.vlm_attempts): record["document_id"]
            for record in vlm_records
        }
        for future in as_completed(futures):
            result = future.result()
            rescue_results.append(result)
            print(f"[vlm-rescue] {result}", flush=True)
    update_progress_snapshot(output_root, rescue_results)
    summary = {
        "schema_version": "moi-parser-recovery-v1",
        "finished_at_epoch": time.time(),
        "failed_records_at_start": len(records),
        "precision_groups": len(precision_groups),
        "vlm_tasks": len(vlm_records),
        "recovered_documents": sum(int(row.get("recovered", 0)) for row in rescue_results),
        "tool_calls": {
            "mineru_official_precision": sum(int(row.get("tool_calls", 0)) for row in rescue_results if "source_sha256" in row),
            "taas_qwen3_vl_plus": sum(int(row.get("tool_calls", 0)) for row in rescue_results if "document_id" in row),
            "reused_rescue_precision_result": sum(int(row.get("cache_reuses", 0)) for row in rescue_results),
        },
        "results": rescue_results,
    }
    atomic_json(output_root / "rescue-summary.json", summary)
    print(f"summary={output_root / 'rescue-summary.json'}", flush=True)


if __name__ == "__main__":
    main()
