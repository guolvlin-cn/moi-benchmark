#!/usr/bin/env python3
"""Current-corpus-only MOI evaluation orchestrator.

This runner deliberately performs no ingestion.  It snapshots the questions and
configuration, queries the already populated MatrixOne tables with bounded
parallelism, and checkpoints every terminal QA so a run can be resumed safely.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Permit direct execution from the repository root.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks import moi_rag_benchmark as legacy

ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = ROOT / "prototypes" / "local-matrixflow-rag"
LAUNCHER = RAG_ROOT / "local_matrixflow_rag.py"
PREPARED = ROOT / "datasets" / "downloads" / "prepared"
DATASETS = ("docbench", "mmdocrag", "enterpriserag-bench", "fab-bench")
CONFIGS = {name: RAG_ROOT / f"config.{name}.maas.json" for name in DATASETS}


def iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_environment() -> dict[str, str]:
    environment = os.environ.copy()
    legacy.load_dotenv(ROOT / ".env", environment)
    legacy.load_dotenv(RAG_ROOT / ".env", environment)
    return environment


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def alloc(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:-3]
    suffix = 0
    while path.exists():
        suffix += 1
        path = root / f"{path.name}-{suffix:02d}"
    path.mkdir()
    return path


def emit(run: Path, message: str) -> None:
    print(message, flush=True)
    append_jsonl(run / "events.jsonl", {"time": iso(), "message": message})


def current_file_ids(config: Path) -> set[str]:
    """Return DISTINCT file_id values from the configured MatrixOne table.

    PyMySQL is optional; the mysql client is used as a dependency-free fallback.
    """
    cfg = json.loads(config.read_text(encoding="utf-8"))
    matrix = cfg["matrixone"]
    dsn = str(matrix["dsn"])
    database = str(matrix["database"])
    table = str(matrix.get("vector_table", "embedding_results"))
    if not re.fullmatch(r"[A-Za-z0-9_]+", table):
        raise ValueError("unsafe MatrixOne table name")
    try:
        import pymysql  # type: ignore
        match = re.match(r"([^:]+):([^@]*)@tcp\(([^:]+):(\d+)\)/", dsn)
        if not match:
            raise ValueError(f"unsupported MatrixOne DSN: {dsn}")
        user, password, host, port = match.groups()
        with pymysql.connect(host=host, port=int(port), user=user, password=password, database=database) as db:
            with db.cursor() as cur:
                cur.execute(f"SELECT DISTINCT file_id FROM `{table}` WHERE file_id IS NOT NULL")
                return {str(row[0]) for row in cur.fetchall() if row[0]}
    except ImportError:
        pass
    command = ["mysql", "--batch", "--skip-column-names", database, "-e", f"SELECT DISTINCT file_id FROM `{table}` WHERE file_id IS NOT NULL"]
    # mysql accepts the same credentials through MYSQL_PWD; avoid exposing it in argv.
    match = re.match(r"([^:]+):([^@]*)@tcp\(([^:]+):(\d+)\)/", dsn)
    if not match:
        raise RuntimeError("pymysql unavailable and MatrixOne DSN cannot be passed to mysql")
    user, password, host, port = match.groups()
    env = os.environ.copy()
    env["MYSQL_PWD"] = password
    out = subprocess.run(command + ["-h", host, "-P", port, "-u", user], env=env, text=True, capture_output=True, check=False)
    if out.returncode:
        raise RuntimeError(out.stderr.strip() or "MatrixOne DISTINCT query failed")
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def frozen_file_ids(run: Path, dataset: str, config: Path) -> tuple[set[str], Path]:
    path = run / "corpus-manifests" / f"{dataset}-file-ids.json"
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return set(payload["file_ids"]), path
    ids = current_file_ids(config)
    write_json(path, {
        "dataset": dataset,
        "database": json.loads(config.read_text(encoding="utf-8"))["matrixone"]["database"],
        "table": json.loads(config.read_text(encoding="utf-8"))["matrixone"].get("vector_table", "embedding_results"),
        "captured_at": iso(),
        "file_ids": sorted(ids),
    })
    return ids, path


def verify_resume_snapshot(run: Path, dataset: str, config: Path, questions: Path) -> None:
    start_path = run / "start-record.json"
    if not start_path.is_file():
        raise RuntimeError("resume requires start-record.json")
    snapshot = (json.loads(start_path.read_text(encoding="utf-8")).get("dataset_snapshots") or {}).get(dataset)
    if not snapshot:
        raise RuntimeError(f"resume snapshot missing for {dataset}")
    expected_config = snapshot.get("config_sha256")
    expected_questions = snapshot.get("questions_sha256")
    if expected_config != sha256_file(config):
        raise RuntimeError(f"resume config hash mismatch for {dataset}")
    if expected_questions != sha256_file(questions):
        raise RuntimeError(f"resume questions hash mismatch for {dataset}")


def build_mapping(dataset: str) -> dict[str, dict[str, Any]]:
    # Enterprise/FAB gold files use expected_doc_ids/gold_context_sources rather
    # than the legacy benchmark document names.
    try:
        return legacy.build_file_map(dataset)
    except RuntimeError:
        path = legacy.parsed_document_path(dataset)
        mapping: dict[str, dict[str, Any]] = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line); meta = row.get("metadata") or {}
                file_id = str(meta.get("file_id") or "").strip()
                name = str(meta.get("benchmark_source_file") or meta.get("file_name") or "").strip()
                if not file_id or not name: continue
                record = {"file_id": file_id, "file_name": str(meta.get("file_name") or name), "benchmark_document_id": Path(name).stem}
                for key in (name, Path(name).name, Path(name).stem, str(meta.get("benchmark_document_id") or "")):
                    if key: mapping.setdefault(key, record)
        if not mapping: raise
        return mapping


def prepare_enterprise(run: Path, limit: int = 0) -> Path:
    source = PREPARED / "moi-ragbench-20260805-full-enterprise" / "enterprise-rag-bench" / "gold-questions.jsonl"
    mapping = build_mapping("enterpriserag-bench")
    rows = legacy.read_jsonl(source)[:limit or None]
    out = run / "datasets/enterpriserag-bench/questions.jsonl"
    excluded = run / "datasets/enterpriserag-bench/excluded-unmapped.jsonl"
    for i, row in enumerate(rows):
        docs = row.get("expected_doc_ids") or [x.get("doc_id") for x in row.get("gold_context_sources", [])]
        try:
            records = [legacy.lookup_file(mapping, d) for d in docs]
        except KeyError as exc:
            append_jsonl(excluded, {"id": row.get("question_id"), "reason": "gold_document_unmapped", "detail": str(exc), "gold_documents": docs})
            continue
        case = {"id": row.get("question_id", f"enterprise-{i:05d}"), "question": row.get("question", ""), "retrieval_keywords": [row.get("question", "")], "file_ids": [], "relevant_documents": [r["file_name"] for r in records], "relevant_evidence": [x.get("evidence", "") for x in row.get("gold_context_sources", [])] + [str(x) for x in row.get("answer_facts", [])], "expected_answer_keywords": legacy.answer_keywords(row.get("gold_answer", "")), "expected_answerable": row.get("question_type") != "info_not_found", "metadata": {**row, "benchmark_document_ids": docs, "gold_file_ids": [r["file_id"] for r in records], "reference_answer": row.get("gold_answer", ""), "question_type": row.get("question_type"), "global_scope": True}}
        append_jsonl(out, case)
    return out


def prepare_fab(run: Path, limit: int = 0) -> Path:
    source = PREPARED / "fab-bench-complete-20260805" / "gold-questions.jsonl"
    # The active MatrixOne table was ingested from the MinerU/evidence-ready
    # snapshot, whose file IDs intentionally differ from the older plain
    # Markdown snapshot at datasets/fab-bench.
    mapping = build_mapping("fab-bench-mineru")
    rows = legacy.read_jsonl(source)[:limit or None]
    out = run / "datasets/fab-bench/questions.jsonl"
    excluded = run / "datasets/fab-bench/excluded-unmapped.jsonl"
    for i, row in enumerate(rows):
        sources = row.get("gold_context_sources") or []
        docs = [x.get("doc_id") for x in sources if x.get("doc_id")]
        try:
            records = [legacy.lookup_file(mapping, d) for d in docs]
        except KeyError as exc:
            append_jsonl(excluded, {"id": row.get("test_id"), "reason": "gold_document_unmapped", "detail": str(exc), "gold_documents": docs})
            continue
        if not records: continue
        answer = row.get("ground_truth_answer", row.get("gold_answer", row.get("expected_answer", "")))
        case = {"id": row.get("test_id", f"fab-{i:05d}"), "question": row.get("question", ""), "retrieval_keywords": [row.get("question", "")], "file_ids": [], "relevant_documents": [r["file_name"] for r in records], "relevant_evidence": [x.get("evidence", "") for x in sources], "expected_answer_keywords": legacy.answer_keywords(answer), "expected_answerable": True, "metadata": {**row, "benchmark_document_ids": docs, "gold_file_ids": [r["file_id"] for r in records], "reference_answer": answer, "question_type": row.get("question_format") or row.get("test_type"), "global_scope": True}}
        append_jsonl(out, case)
    return out


def filter_questions(path: Path, ids: set[str], smoke: int = 0) -> Path:
    rows = legacy.read_jsonl(path)
    kept: list[dict[str, Any]] = []
    excluded_path = path.with_name("excluded-not-in-current-db.jsonl")
    for row in rows:
        metadata = row.get("metadata", {})
        gold_ids = set(metadata.get("gold_file_ids") or [])
        if metadata.get("global_scope"):
            in_scope = gold_ids <= ids
            # Freeze global retrieval to every file present at run start. This
            # is the full current corpus, not a Gold-only scope.
            row["file_ids"] = sorted(ids)
        else:
            in_scope = bool(set(row.get("file_ids", [])) & ids)
        if in_scope:
            kept.append(row)
        else:
            append_jsonl(excluded_path, {"id": row.get("id"), "reason": "gold_document_not_fully_present_in_current_db", "gold_file_ids": sorted(gold_ids or set(row.get("file_ids", [])))})
    rows = kept
    if smoke > 0: rows = rows[:smoke]
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def frozen_config(run: Path, dataset: str, environ: dict[str, str] | None = None) -> Path:
    config = json.loads(CONFIGS[dataset].read_text(encoding="utf-8"))
    config.setdefault("embedding", {})["retry_max_attempts"] = 1
    config["embedding"]["mode"] = "maas"
    config.setdefault("generation", {})["enabled"] = True
    config["generation"]["provider"] = "maas"
    environ = environ or os.environ
    # These current tables contain no page_image_file_id values, so this run is
    # explicitly text-only even for the two multimodal source datasets.
    config["generation"]["model"] = environ.get("MAAS_LLM_MODEL", "qwen3-30b-a3b")
    config["generation"]["base_url"] = environ.get("MAAS_BASE_URL", "https://api.modelarts-maas.com/v1")
    config["generation"]["api_key_env"] = "MAAS_API_KEY"
    config["generation"]["retry_max_attempts"] = 1
    config["generation"].pop("fallback", None)
    path = run / "configs" / f"config.{dataset}.maas.json"; write_json(path, config); return path


def latest_child_error(run: Path, dataset: str, result_root: Path | None = None) -> str:
    root = result_root or (run / "datasets" / dataset / "results")
    result_files = sorted(root.rglob("results.jsonl"), key=lambda path: path.stat().st_mtime)
    if not result_files:
        return ""
    rows = legacy.read_jsonl(result_files[-1])
    return str(rows[-1].get("error") or "") if rows else ""


def is_api_failure(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in (
        "api_error", "http ", "http_", "timeout", "timed out", "connection reset",
        "connection refused", "transport", "tls", "dns", "unauthorized", "forbidden",
        "rate limit", "status 401", "status 403", "status 405", "status 429",
    ))


def stop_process(process: subprocess.Popen[str]) -> None:
    # The launcher starts `go run`, which in turn starts the compiled Go
    # binary.  Stopping only the launcher can orphan both descendants while
    # they keep stdout open, leaving the coordinator blocked in pump().
    # Workers are therefore started in their own session below and stopped as
    # a process group here.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        if process.poll() is None:
            process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            if process.poll() is None:
                process.kill()
        process.wait(timeout=10)


class MatrixOneRestartRequired(RuntimeError):
    pass


def matrixone_probe(config: Path) -> bool:
    matrix = json.loads(config.read_text(encoding="utf-8"))["matrixone"]
    match = re.fullmatch(r"([^:]+):(.+)@tcp\(([^:]+):(\d+)\)/.*", str(matrix["dsn"]))
    mysql = shutil.which("mysql") or "/opt/homebrew/opt/mysql-client/bin/mysql"
    if not match or not Path(mysql).is_file():
        raise RuntimeError("cannot health-check MatrixOne: unsupported DSN or mysql client missing")
    user, password, host, port = match.groups()
    ping_env = os.environ.copy(); ping_env["MYSQL_PWD"] = password
    command = [mysql, "--connect-timeout=2", "--batch", "--skip-column-names", "-h", host, "-P", port, "-u", user, str(matrix["database"]), "-e", "SELECT 1"]
    try:
        probe = subprocess.run(command, env=ping_env, text=True, capture_output=True, timeout=4)
        return probe.returncode == 0 and probe.stdout.strip() == "1"
    except subprocess.TimeoutExpired:
        return False


def wait_for_matrixone_ready(run: Path, dataset: str, config: Path, max_probes: int = 180) -> None:
    for attempt in range(1, max_probes + 1):
        if matrixone_probe(config):
            emit(run, f"MATRIXONE ready for {dataset} after probe {attempt}")
            return
        if attempt == 1 or attempt % 6 == 0:
            emit(run, f"MATRIXONE waiting for {dataset}; probe={attempt}; competitors remain untouched")
        time.sleep(10)
    raise RuntimeError(f"MatrixOne SQL readiness timed out after {max_probes * 10} seconds for {dataset}")


def restart_matrixone(run: Path, dataset: str, config: Path) -> None:
    """Restart the dedicated MatrixOne container and wait for SQL readiness."""
    emit(run, f"MATRIXONE AUTO-RESTART requested by {dataset}")
    restarted = subprocess.run(["docker", "restart", "matrixone"], text=True, capture_output=True, timeout=45)
    if restarted.returncode:
        state = subprocess.run(["docker", "inspect", "matrixone", "--format", "{{.State.Status}}"], text=True, capture_output=True, timeout=10).stdout.strip()
        if state != "exited":
            raise RuntimeError(f"MatrixOne restart failed in state={state}: {restarted.stderr.strip()}")
        info = subprocess.run(["docker", "info", "--format", "{{.NCPU}}"], text=True, capture_output=True, timeout=10)
        available_cpus = max(1, int((info.stdout or "2").strip()))
        subprocess.run(["docker", "update", "--cpus", str(min(2, available_cpus)), "matrixone"], check=True, timeout=15)
        subprocess.run(["docker", "start", "matrixone"], check=True, timeout=30)

    for attempt in range(1, 31):
        if matrixone_probe(config):
            emit(run, f"MATRIXONE AUTO-RESTART ready after probe {attempt}")
            return
        time.sleep(2)
    emit(run, "MATRIXONE restart completed but SQL recovery is still running")
    wait_for_matrixone_ready(run, dataset, config)


def run_child(run: Path, dataset: str, config: Path, questions: Path, environment: dict[str, str], workers: int = 2) -> Path:
    log = run / "datasets" / dataset / "raw-results.log"; log.parent.mkdir(parents=True, exist_ok=True)
    question_rows = legacy.read_jsonl(questions)
    workers = max(1, min(workers, len(question_rows)))
    batch_root = run / "datasets" / dataset / "results" / f"parallel-{datetime.now().strftime('%Y%m%d-%H%M%S.%f')[:-3]}"
    batch_root.mkdir(parents=True, exist_ok=True)
    shards: list[Path] = []
    for index in range(workers):
        shard = questions.with_name(f"{questions.stem}.worker-{index + 1}.jsonl")
        shard.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in question_rows[index::workers]), encoding="utf-8")
        shards.append(shard)
    processes: list[subprocess.Popen[str]] = []
    output_lock = threading.Lock()
    restart_event = threading.Event()
    db_timeout_count = 0
    # The Go context deadline cannot interrupt every MatrixOne driver call
    # (some deadlocked sessions remain inside a socket/condition wait).  Keep
    # a coordinator-side silence deadline so such a worker is still bounded
    # and the normal MatrixOne recovery path can run.
    last_output = {index: time.monotonic() for index in range(1, workers + 1)}
    worker_silence_seconds = 190.0

    def pump(worker_index: int, process: subprocess.Popen[str], worker_root: Path, handle: Any) -> None:
        nonlocal db_timeout_count
        assert process.stdout
        for line in process.stdout:
            rendered = f"[{dataset}/w{worker_index}] {line.rstrip()}"
            lowered_line = line.lower()
            last_output[worker_index] = time.monotonic()
            with output_lock:
                handle.write(rendered + "\n"); handle.flush(); print(rendered, flush=True)
                if "status=ok" in line:
                    db_timeout_count = 0
                if "unexpected eof" in lowered_line:
                    restart_event.set()
            if "status=failed" not in line:
                continue
            error = latest_child_error(run, dataset, worker_root) or line.rstrip()
            append_jsonl(run / "datasets" / dataset / "skipped-errors.jsonl", {
                "time": iso(), "dataset": dataset, "worker": worker_index,
                "line": line.rstrip(), "error": error,
                "api_failure": is_api_failure(error), "policy": "record_and_continue",
            })
            emit(run, f"SKIP failed QA in {dataset}/w{worker_index}; continuing: {error[:240]}")
            lowered_error = error.lower()
            if "fulltext route: context deadline exceeded" in lowered_error or "driver: bad connection" in lowered_error:
                with output_lock:
                    db_timeout_count += 1
                    restart_event.set()

    # Keep prior resume logs; every child result row is the durable per-QA
    # checkpoint used by run_or_resume_questions.
    with log.open("a", encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for index, shard in enumerate(shards, 1):
                worker_root = batch_root / f"worker-{index}"
                command = [sys.executable, str(LAUNCHER), "run", "--config", str(config), "--dataset", str(shard), "--run", str(worker_root), "--max-hits", "10", "--repeats", "1", "--attempt-timeout-seconds", "180"]
                process = subprocess.Popen(
                    command,
                    cwd=RAG_ROOT,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
                processes.append(process)
                futures.append(pool.submit(pump, index, process, worker_root, handle))
            while any(process.poll() is None for process in processes):
                if restart_event.is_set():
                    for process in processes:
                        if process.poll() is None:
                            stop_process(process)
                    break
                now = time.monotonic()
                silent_workers = [
                    index for index, process in enumerate(processes, 1)
                    if process.poll() is None and now - last_output[index] >= worker_silence_seconds
                ]
                if silent_workers:
                    emit(
                        run,
                        f"MATRIXONE watchdog: no worker output for {worker_silence_seconds:.0f}s; "
                        f"workers={','.join(map(str, silent_workers))}",
                    )
                    restart_event.set()
                    for process in processes:
                        if process.poll() is None:
                            stop_process(process)
                    break
                time.sleep(0.5)
            for future in futures:
                future.result()
    if restart_event.is_set():
        raise MatrixOneRestartRequired(f"{dataset}: two MatrixOne route timeouts")
    bad = [process.returncode for process in processes if process.returncode]
    if bad: raise RuntimeError(f"{dataset} parallel children exited {bad}")
    matches = sorted(batch_root.rglob("results.jsonl"))
    if not matches: raise RuntimeError(f"missing results for {dataset}")
    return batch_root


def collect_result_history(run: Path, dataset: str) -> dict[str, list[dict[str, Any]]]:
    history: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((run / "datasets" / dataset / "results").rglob("results.jsonl")):
        for row in legacy.read_jsonl(path):
            case_id = str((row.get("case") or {}).get("id") or "")
            if not case_id:
                continue
            history.setdefault(case_id, []).append(row)
    return history


def run_or_resume_questions(
    run: Path,
    dataset: str,
    config: Path,
    questions_path: Path,
    environment: dict[str, str],
    workers: int = 2,
    retry_failed: bool = False,
) -> tuple[Path, list[dict[str, Any]], int]:
    questions = legacy.read_jsonl(questions_path)
    history = collect_result_history(run, dataset)
    # Both success and failure are terminal initial dispositions. Normal resume
    # only runs unfinished questions; an explicit retry_failed pass is the one
    # opt-in path that replays questions whose history has no successful row.
    if retry_failed:
        retry_targets = [
            row for row in questions
            if str(row.get("id")) in history
            and not any(attempt.get("status") == "ok" for attempt in history[str(row.get("id"))])
        ]
        pending = list(retry_targets)
    else:
        completed_ids = set(history)
        pending = [row for row in questions if str(row.get("id")) not in completed_ids]
    initial_pending_count = len(pending)
    if pending:
        if retry_failed:
            # A retry pass is intentionally bounded. If the MatrixOne
            # watchdog asks for a restart, rerun only cases that did not
            # obtain a new successful row, and stop after three recovery
            # rounds rather than looping forever on a pathological query.
            retry_path = questions_path.with_name("questions.retry-failed.jsonl")
            baseline_counts = {str(row.get("id")): len(history.get(str(row.get("id")), [])) for row in pending}
            for recovery_round in range(3):
                retry_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in pending), encoding="utf-8")
                try:
                    run_child(run, dataset, config, retry_path, environment, workers)
                    break
                except MatrixOneRestartRequired:
                    restart_matrixone(run, dataset, config)
                    history = collect_result_history(run, dataset)
                    pending = [
                        row for row in retry_targets
                        if not any(
                            attempt.get("status") == "ok"
                            for attempt in history.get(str(row.get("id")), [])[baseline_counts.get(str(row.get("id")), 0):]
                        )
                    ]
                    if not pending:
                        break
                    if recovery_round == 2:
                        raise
        else:
            while pending:
                pending_path = questions_path.with_name("questions.pending.jsonl")
                pending_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in pending), encoding="utf-8")
                try:
                    run_child(run, dataset, config, pending_path, environment, workers)
                except MatrixOneRestartRequired:
                    restart_matrixone(run, dataset, config)
                history = collect_result_history(run, dataset)
                pending = [row for row in questions if str(row.get("id")) not in history]
    else:
        emit(run, f"{'RETRY' if retry_failed else 'RESUME'} reuse all {len(questions)} completed query attempts for {dataset}")
    # The primary ledger is first-pass by contract. Later successful retries
    # remain auditable in raw child results and the recovery ledger, but never
    # overwrite initial availability or quality denominators.
    ordered = [history[str(case["id"])][0] for case in questions if history.get(str(case["id"]))]
    recovered = []
    for case in questions:
        attempts = history.get(str(case["id"]), [])
        success = next((row for row in attempts if row.get("status") == "ok"), None)
        if success:
            recovered.append(success)
    canonical = run / "datasets" / dataset / "combined-results.jsonl"
    canonical.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered), encoding="utf-8")
    recovery = run / "datasets" / dataset / "recovered-results.jsonl"
    recovery.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in recovered), encoding="utf-8")
    return canonical, ordered, initial_pending_count


def metrics(dataset: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval = legacy.retrieve_metrics(rows)
    result = {"retrieval": retrieval, "latency_ms": retrieval.get("retrieval_latency_ms")}
    if dataset == "mmdocrag": result["answer"] = legacy.mmdocrag_answer_metrics(rows)
    if dataset == "docbench": result["correctness_by_type"] = {}
    if dataset in {"enterpriserag-bench", "fab-bench"}:
        result.update({"judge": None, "na_reason": "N/A: official dataset judge/scorer is unavailable in the local checkout"})
    if dataset in {"enterpriserag-bench", "fab-bench"}:
        recalls=[]; complete=[]; extras=[]; avail=[]; f1=[]; slices={}; unanswerable=[]
        for row in rows:
            avail.append(float(row.get("status")=="ok"))
            if row.get("status") != "ok":
                continue
            case=row.get("case") or {}; gold=set((case.get("metadata") or {}).get("gold_file_ids", [])); got=[str(c.get("file_id")) for c in row.get("chunks", [])[:10]]; gotset=set(got)
            hit = len(gold & gotset)/len(gold) if gold else None
            if hit is not None:
                recalls.append(hit)
                complete.append(float(gold <= gotset))
                extras.append(float(len(gotset-gold)))
            ref = re.findall(r"\w+", str((case.get("metadata") or {}).get("reference_answer", "")).lower())
            pred = re.findall(r"\w+", str(row.get("answer", "")).lower())
            if ref:
                overlap = sum((Counter(ref) & Counter(pred)).values())
                p = overlap / len(pred) if pred else 0
                r = overlap / len(ref)
                f1.append(2*p*r/(p+r) if p+r else 0)
            key=str((case.get("metadata") or {}).get("question_type") or (case.get("metadata") or {}).get("test_type") or "unknown")
            if hit is not None:
                slices.setdefault(key,[]).append(hit)
            if key == "info_not_found":
                answer = str(row.get("answer", "")).lower()
                unanswerable.append(float(any(marker in answer for marker in ("not found", "insufficient", "not available", "cannot", "can't", "unable", "not fully", "documents do not", "no information"))))
        result.update({"doc_recall_at_10":sum(recalls)/len(recalls) if recalls else None,"doc_recall_valid_n":len(recalls),"complete_evidence_set_recall_at_10":sum(complete)/len(complete) if complete else None,"invalid_extra_docs":sum(extras)/len(extras) if extras else None,"answer_lexical_f1":sum(f1)/len(f1) if f1 else None,"answer_lexical_f1_valid_n":len(f1),"availability":sum(avail)/len(avail) if avail else None,"failed_n":sum(1 for value in avail if value == 0),"strict_unanswerable_success":sum(unanswerable)/len(unanswerable) if unanswerable else None,"strict_unanswerable_valid_n":len(unanswerable),"question_type_slices":{k:sum(v)/len(v) for k,v in slices.items()}})
        if dataset == "fab-bench": result["objective_accuracy"] = objective_accuracy(rows)
    return result

def extract_objective_answer(text: str) -> str | None:
    patterns = (
        r"(?:correct answer is|answer is)\s*[:：]?\s*\**\(?([A-D]|true|false)\)?",
        r"^\s*\**\(?([A-D])\)\s*",
        r"^\s*\**([A-D])[\.:：\-]\s*",
        r"^\s*(true|false)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).lower()
    return None


def objective_accuracy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = correct = 0
    objective_n = 0
    for row in rows:
        metadata = (row.get("case") or {}).get("metadata", {})
        if str(metadata.get("question_format", "")).upper() != "OBJECTIVE":
            continue
        objective_n += 1
        expected = extract_objective_answer(str(metadata.get("reference_answer", "")))
        predicted = extract_objective_answer(str(row.get("answer", "")))
        if expected and predicted:
            valid += 1
            correct += int(expected == predicted)
    return {"accuracy": correct / valid if valid else None, "correct": correct, "valid_n": valid, "objective_n": objective_n}

def failfast_docbench_judge(run: Path, rows: list[dict[str, Any]], env: dict[str, str], cfg: dict[str, Any], workers: int = 2) -> dict[str, Any]:
    out = run / "datasets/docbench/judgements.jsonl"
    prompt = legacy.DOCBENCH_EVAL_PROMPT.read_text(encoding="utf-8")
    scores: list[int] = []
    by: dict[str, list[int]] = {}
    existing = {str(row.get("id")): row for row in legacy.read_jsonl(out)} if out.is_file() else {}
    provider = {"base_url": cfg["generation"].get("base_url"), "model": cfg["generation"].get("model")}
    pending: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        case = row.get("case", {})
        meta = case.get("metadata", {})
        prior = existing.get(str(case.get("id")))
        if prior and prior.get("status") == "ok" and isinstance(prior.get("score"), int):
            score = int(prior["score"])
            scores.append(score)
            by.setdefault(str(meta.get("question_type") or "unknown"), []).append(score)
            continue
        # A prior API/format failure is not a terminal judgement.  Keep it in
        # the audit file, but send the case through the judge again so a
        # transient provider error cannot become the final denominator.
        pending.append(row)

    def judge_one(row: dict[str, Any]) -> dict[str, Any]:
        case = row.get("case", {})
        meta = case.get("metadata", {})
        text = prompt.replace("{{question}}", str(case.get("question", ""))).replace("{{sys_ans}}", str(row.get("answer", ""))).replace("{{ref_ans}}", str(meta.get("reference_answer", ""))).replace("{{ref_text}}", str(meta.get("reference_evidence", "")))
        try:
            raw = legacy.openai_chat(env, provider["base_url"], provider["model"], [{"role": "system", "content": "You are a helpful evaluator."}, {"role": "user", "content": text}], api_key_env="MAAS_API_KEY")
            match = re.search(r"(?:correctness|score)\s*\**\s*[:：]\s*\**\s*([01])\b", raw, flags=re.I)
            if not match and raw.strip() in {"0", "1"}:
                match = re.match(r"([01])", raw.strip())
            if not match:
                # Some judge responses put the binary score on the first line
                # and explanation below it instead of emitting the requested
                # ``Correctness: 0/1`` label.  Treat that unambiguous form as
                # valid while still rejecting arbitrary prose containing a
                # digit later in the response.
                match = re.match(r"^\s*(?:[-*]\s*)?([01])\s*(?:\n|$)", raw)
            if not match:
                raise legacy.APIError(f"API_ERROR: invalid DocBench judge response for {case.get('id')}: {raw[:300]}")
        except legacy.APIError as exc:
            return {"id": case.get("id"), "question_type": str(meta.get("question_type") or "unknown"), "status": "failed", "score": None, "error": str(exc), "provider": "maas", "model": provider["model"], "policy": "record_and_continue"}
        score = int(match.group(1))
        return {"id": case.get("id"), "question_type": str(meta.get("question_type") or "unknown"), "status": "ok", "score": score, "raw": raw, "provider": "maas", "model": provider["model"]}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(judge_one, row) for row in pending]
        for future in as_completed(futures):
            record = future.result()
            question_type = str(record.pop("question_type"))
            append_jsonl(out, record)
            if record["status"] != "ok":
                append_jsonl(run / "datasets/docbench/skipped-errors.jsonl", {"time": iso(), "stage": "judge", **record})
                emit(run, f"DOCBENCH judge skipped id={record.get('id')} error={str(record.get('error'))[:240]}")
                continue
            score = int(record["score"])
            scores.append(score)
            by.setdefault(question_type, []).append(score)
            emit(run, f"DOCBENCH judge {len(scores)}/{len(rows)} id={record.get('id')} score={score}")
    return {"correctness": sum(scores)/len(scores) if scores else None, "valid_n": len(scores), "failed_n": len([row for row in legacy.read_jsonl(out) if row.get('status') == 'failed']), "correctness_by_type": {k: sum(v)/len(v) for k, v in by.items() if v}, "raw_path": str(out)}


def failfast_mmdocrag_judge(run: Path, rows: list[dict[str, Any]], env: dict[str, str], cfg: dict[str, Any], workers: int = 2) -> dict[str, Any]:
    out = run / "datasets/mmdocrag/judgements.jsonl"
    prompt = legacy.MMDOCRAG_JUDGE_PROMPT.read_text(encoding="utf-8")
    dimensions = ("Fluency", "Citation Quality", "Text-Image Coherence", "Reasoning Logic", "Factuality")
    scored: list[dict[str, Any]] = []
    existing = {str(row.get("id")): row for row in legacy.read_jsonl(out)} if out.is_file() else {}
    pending: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        case = row.get("case") or {}
        metadata = case.get("metadata") or {}
        prior = existing.get(str(case.get("id")))
        if prior:
            if prior.get("status") == "ok" and all(isinstance((prior.get("scores") or {}).get(dimension), int) for dimension in dimensions):
                scored.append(prior)
            continue
        pending.append(row)

    def judge_one(row: dict[str, Any]) -> dict[str, Any]:
        case = row.get("case") or {}
        metadata = case.get("metadata") or {}
        user = (
            f"The question is: {case.get('question', '')}\n"
            f"The short answer is: {metadata.get('answer_short', '')}\n"
            f"The perfect answer is: {metadata.get('answer_interleaved', '')}\n"
            f"The interleaved answer is: {row.get('answer', '')}\n"
            "This CURRENT_CORPUS_ADAPTED run is text-only; no image input was supplied."
        )
        try:
            raw = legacy.openai_chat(env, cfg["generation"]["base_url"], cfg["generation"]["model"], [{"role": "system", "content": prompt}, {"role": "user", "content": user}], api_key_env="MAAS_API_KEY")
            parsed = legacy.extract_json_object(raw)
            if not parsed:
                raise legacy.APIError(f"API_ERROR: invalid MMDocRAG judge response for {case.get('id')}: {raw[:300]}")
            values: dict[str, int] = {}
            for dimension in dimensions:
                value = next((candidate for key, candidate in parsed.items() if str(key).lower().replace(" ", "") == dimension.lower().replace(" ", "")), None)
                try:
                    score = int(value)
                except (TypeError, ValueError) as exc:
                    raise legacy.APIError(f"API_ERROR: MMDocRAG judge missing {dimension} for {case.get('id')}: {raw[:300]}") from exc
                values[dimension] = score
        except legacy.APIError as exc:
            return {"id": case.get("id"), "status": "failed", "scores": {}, "average": None, "error": str(exc), "provider": "maas", "model": cfg["generation"]["model"], "text_only_adapter": True, "policy": "record_and_continue"}
        return {"id": case.get("id"), "status": "ok", "scores": values, "average": sum(values.values()) / len(values), "raw": raw, "provider": "maas", "model": cfg["generation"]["model"], "text_only_adapter": True}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(judge_one, row) for row in pending]
        for future in as_completed(futures):
            record = future.result()
            append_jsonl(out, record)
            if record["status"] != "ok":
                append_jsonl(run / "datasets/mmdocrag/skipped-errors.jsonl", {"time": iso(), "stage": "judge", **record})
                emit(run, f"MMDOCRAG judge skipped id={record.get('id')} error={str(record.get('error'))[:240]}")
                continue
            scored.append(record)
            emit(run, f"MMDOCRAG judge {len(scored)}/{len(rows)} id={record.get('id')} avg={record['average']:.3f}")
    means = {dimension: (sum(row["scores"][dimension] for row in scored) / len(scored) if scored else None) for dimension in dimensions}
    return {"scored": len(scored), "failed_n": len([row for row in legacy.read_jsonl(out) if row.get('status') == 'failed']), "average": (sum(row["average"] for row in scored) / len(scored) if scored else None), "dimensions": means, "raw_path": str(out), "text_only_adapter": True}


def per_qa_computed_metrics(dataset: str, row: dict[str, Any]) -> dict[str, Any]:
    computed: dict[str, Any] = {
        "first_pass_available": row.get("status") == "ok",
        "source_recall": (row.get("metrics") or {}).get("source_recall"),
        "evidence_recall": (row.get("metrics") or {}).get("evidence_recall"),
        "reciprocal_rank": (row.get("metrics") or {}).get("reciprocal_rank"),
        "source_recall_at_k": (row.get("metrics") or {}).get("source_recall_at_k"),
        "answer_keyword_recall": (row.get("metrics") or {}).get("answer_keyword_recall"),
    }
    if row.get("status") != "ok":
        return computed
    case = row.get("case") or {}
    metadata = case.get("metadata") or {}
    if dataset == "mmdocrag":
        gold = [legacy.normalized(item.get("text")) for item in metadata.get("gold_text_quotes", []) if item.get("text")]
        retrieved = [legacy.normalized(chunk.get("content")) for chunk in row.get("chunks") or []]
        hit = sum(1 for quote in gold if any(quote and quote in chunk for chunk in retrieved))
        predicted = sum(1 for chunk in retrieved if any(quote and quote in chunk for quote in gold))
        precision = predicted / len(retrieved) if retrieved else 0.0
        recall = hit / len(gold) if gold else None
        computed.update({
            "text_quote_precision_adapted": precision,
            "text_quote_recall_adapted": recall,
            "text_quote_f1_adapted": (2 * precision * recall / (precision + recall) if recall is not None and precision + recall else 0.0),
            "bleu_1_adapted": legacy.bleu_1(str(metadata.get("answer_interleaved") or ""), str(row.get("answer") or "")),
            "rouge_l": legacy.rouge_l(str(metadata.get("answer_interleaved") or ""), str(row.get("answer") or "")),
        })
    elif dataset in {"enterpriserag-bench", "fab-bench"}:
        gold = set(metadata.get("gold_file_ids") or [])
        retrieved = {str(chunk.get("file_id")) for chunk in (row.get("chunks") or [])[:10]}
        computed.update({
            "doc_recall_at_10": len(gold & retrieved) / len(gold) if gold else None,
            "complete_evidence_set_at_10": gold <= retrieved if gold else None,
            "invalid_extra_docs_at_10": len(retrieved - gold) if gold else None,
        })
        if dataset == "fab-bench" and str(metadata.get("question_format", "")).upper() == "OBJECTIVE":
            expected = extract_objective_answer(str(metadata.get("reference_answer", "")))
            predicted = extract_objective_answer(str(row.get("answer", "")))
            computed.update({"objective_expected": expected, "objective_predicted": predicted, "objective_correct": expected == predicted if expected and predicted else None})
    return computed


def write_qa_ledger(run: Path, dataset: str, rows: list[dict[str, Any]]) -> Path:
    judge_path = run / "datasets" / dataset / "judgements.jsonl"
    judges = {str(row.get("id")): row for row in legacy.read_jsonl(judge_path)} if judge_path.is_file() else {}
    path = run / "datasets" / dataset / "qa-ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for row in rows:
        case = row.get("case") or {}
        records.append({
            "id": case.get("id"),
            "question": case.get("question"),
            "status": row.get("status"),
            "error": row.get("error"),
            "answer": row.get("answer"),
            "chunks": row.get("chunks") or [],
            "routes": row.get("routes") or [],
            "generation_provider": row.get("generation_provider"),
            "generation_model": row.get("generation_model"),
            "retrieval_latency_ms": row.get("retrieval_latency_ms"),
            "generation_latency_ms": row.get("generation_latency_ms"),
            "raw_metrics": row.get("metrics") or {},
            "computed_metrics": per_qa_computed_metrics(dataset, row),
            "judge": judges.get(str(case.get("id"))),
            "metadata": case.get("metadata") or {},
        })
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--run-root", type=Path, default=ROOT / "runs/current-corpus-eval"); parser.add_argument("--resume", type=Path); parser.add_argument("--retry-failed", action="store_true", help="explicitly replay questions whose prior history has no successful result"); parser.add_argument("--datasets", nargs="+", choices=DATASETS, default=list(DATASETS)); parser.add_argument("--docbench-questions", type=Path, help="use an explicit DocBench questions JSONL for a new run; skips current-corpus question filtering"); parser.add_argument("--docbench-config", type=Path, help="use an explicit DocBench config JSON for a new run"); parser.add_argument("--smoke", type=int, default=0); parser.add_argument("--query-workers", type=int, default=1); parser.add_argument("--judge-workers", type=int, default=2)
    args = parser.parse_args(argv)
    if args.retry_failed and not args.resume:
        parser.error("--retry-failed requires --resume")
    if args.docbench_questions and "docbench" not in args.datasets:
        parser.error("--docbench-questions requires docbench in --datasets")
    if args.docbench_questions and args.resume:
        parser.error("--docbench-questions is only supported when creating a new run")
    if args.docbench_config and "docbench" not in args.datasets:
        parser.error("--docbench-config requires docbench in --datasets")
    if args.docbench_config and args.resume:
        parser.error("--docbench-config is only supported when creating a new run")
    run = args.resume.resolve() if args.resume else alloc(args.run_root.resolve())
    environment = load_environment()
    emit(run, f"RUN {run}")
    state = {"status": "running", "stage": "start", "datasets": list(args.datasets), "updated_at": iso()}; write_json(run / "state.json", state)
    progress_path = run / "progress.json"
    if args.resume and progress_path.is_file():
        progress_seed = json.loads(progress_path.read_text(encoding="utf-8"))
        progress_seed.setdefault("datasets", {}).update({name: {"status": "pending"} for name in args.datasets if name not in progress_seed.get("datasets", {})})
    else:
        progress_seed = {"datasets": {name: {"status": "pending"} for name in args.datasets}}
    progress_seed["updated_at"] = iso(); write_json(progress_path, progress_seed)
    if not (args.resume and (run / "start-record.json").is_file()):
        write_json(run / "start-record.json", {"started_at": iso(), "datasets": args.datasets, "smoke": args.smoke, "no_ingest": True})
    start_record = json.loads((run / "start-record.json").read_text(encoding="utf-8"))
    start_record["execution_controls"] = {
        "query_workers": max(1, args.query_workers),
        "judge_workers": max(1, args.judge_workers),
        "attempt_timeout_seconds": 180,
        "retry_failed": bool(args.retry_failed),
        "matrixone_auto_restart_after_fulltext_timeout_or_bad_connection": 1,
    }
    write_json(run / "start-record.json", start_record)
    try:
        prior_progress = json.loads((run / "progress.json").read_text(encoding="utf-8")) if (run / "progress.json").is_file() else {"datasets": {}}
        for dataset in DATASETS:
            if dataset not in args.datasets: continue
            if args.resume and not args.retry_failed and prior_progress.get("datasets", {}).get(dataset, {}).get("status") == "succeeded":
                emit(run, f"RESUME skip completed {dataset}")
                continue
            resume_snapshot = ((json.loads((run / "start-record.json").read_text(encoding="utf-8")).get("dataset_snapshots") or {}).get(dataset) if args.resume else None)
            config = run / "configs" / f"config.{dataset}.maas.json"
            q = run / "datasets" / dataset / "questions.jsonl"
            if resume_snapshot and (not config.is_file() or not q.is_file()):
                raise RuntimeError(f"resume frozen artifacts missing for {dataset}")
            if not (args.resume and config.is_file()):
                if dataset == "docbench" and args.docbench_config:
                    source_config = args.docbench_config.expanduser().resolve()
                    if not source_config.is_file():
                        raise RuntimeError(f"explicit DocBench config missing: {source_config}")
                    config.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_config, config)
                else:
                    config = frozen_config(run, dataset, environment)
            start_record = json.loads((run / "start-record.json").read_text(encoding="utf-8")); start_record.setdefault("frozen_models", {})[dataset] = json.loads(config.read_text(encoding="utf-8")).get("generation", {}).get("model"); write_json(run / "start-record.json", start_record)
            wait_for_matrixone_ready(run, dataset, config)
            ids, corpus_manifest = frozen_file_ids(run, dataset, config)
            if not (args.resume and q.is_file()):
                # Build the complete current-corpus candidate set first, then
                # apply smoke. Pre-limiting before DB filtering can select only
                # an absent document and accidentally create a zero-question run.
                if dataset == "docbench" and args.docbench_questions:
                    source = args.docbench_questions.expanduser().resolve()
                    if not source.is_file():
                        raise RuntimeError(f"explicit DocBench questions file missing: {source}")
                    q.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, q)
                    if args.smoke > 0:
                        rows = legacy.read_jsonl(q)[:args.smoke]
                        q.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
                else:
                    if dataset == "docbench": q = legacy.prepare_docbench(run, 0, 0)[0]
                    elif dataset == "mmdocrag": q = legacy.prepare_mmdocrag(run, 0)[0]
                    elif dataset == "enterpriserag-bench": q = prepare_enterprise(run, 0)
                    else: q = prepare_fab(run, 0)
                    filter_questions(q, ids, args.smoke)
            if resume_snapshot:
                verify_resume_snapshot(run, dataset, config, q)
            questions = legacy.read_jsonl(q)
            ledger = run / "datasets" / dataset / "initial-ledger.jsonl"
            ledger.parent.mkdir(parents=True, exist_ok=True)
            if not ledger.is_file():
                ledger.write_text("".join(json.dumps({"id": row["id"], "status": "not_started"}, ensure_ascii=False) + "\n" for row in questions), encoding="utf-8")
            start_record = json.loads((run / "start-record.json").read_text(encoding="utf-8"))
            start_record.setdefault("dataset_snapshots", {})[dataset] = {
                "current_file_ids": len(ids),
                "file_id_manifest": str(corpus_manifest),
                "file_id_manifest_sha256": sha256_file(corpus_manifest),
                "questions": len(questions),
                "questions_path": str(q),
                "questions_sha256": sha256_file(q),
                "config_path": str(config),
                "config_sha256": sha256_file(config),
                "protocol": "CURRENT_CORPUS_ADAPTED",
                "image_trace": False if dataset in {"docbench", "mmdocrag"} else "N/A",
            }
            write_json(run / "start-record.json", start_record)
            (run / "start-record.json.sha256").write_text(sha256_file(run / "start-record.json") + "\n", encoding="utf-8")
            write_json(run / "state.json", {"status": "running", "stage": f"query:{dataset}", "updated_at": iso()})
            progress = json.loads((run / "progress.json").read_text(encoding="utf-8")); progress["datasets"][dataset] = {"status": "running", "questions": len(questions), "updated_at": iso()}; write_json(run / "progress.json", progress)
            combined_results, rows, pending_count = run_or_resume_questions(run, dataset, config, q, environment, max(1, args.query_workers), retry_failed=args.retry_failed)
            dataset_metrics = metrics(dataset, rows)
            if dataset == "docbench":
                judge_cfg = json.loads(config.read_text(encoding="utf-8")); judge_cfg["generation"]["retry_max_attempts"] = 1; judge_cfg["generation"].pop("fallback", None)
                dataset_metrics["correctness"] = failfast_docbench_judge(run, rows, environment, judge_cfg, max(1, args.judge_workers))
            elif dataset == "mmdocrag":
                judge_cfg = json.loads(config.read_text(encoding="utf-8")); judge_cfg["generation"]["retry_max_attempts"] = 1; judge_cfg["generation"].pop("fallback", None)
                dataset_metrics["judge"] = failfast_mmdocrag_judge(run, rows, environment, judge_cfg, max(1, args.judge_workers))
            qa_ledger = write_qa_ledger(run, dataset, rows)
            query_failed_n = sum(1 for row in rows if row.get("status") != "ok")
            judge_failed_n = int((dataset_metrics.get("correctness") or {}).get("failed_n") or 0) if dataset == "docbench" else int((dataset_metrics.get("judge") or {}).get("failed_n") or 0)
            write_json(run / "datasets" / dataset / "metrics.json", dataset_metrics)
            write_json(run / "datasets" / dataset / "summary.json", {"dataset": dataset, "rows": len(rows), "planned": len(questions), "pending_at_launch": pending_count, "query_failed_n": query_failed_n, "judge_failed_n": judge_failed_n, "results": str(combined_results), "qa_ledger": str(qa_ledger), "error_policy": "record_and_continue"})
            write_json(run / "datasets" / dataset / "report.json", {"dataset": dataset, "metrics": dataset_metrics, "results": str(combined_results), "qa_ledger": str(qa_ledger), "summary": str(run / "datasets" / dataset / "summary.json")})
            progress["datasets"][dataset] = {"status": "succeeded", "questions": len(rows), "query_failed_n": query_failed_n, "judge_failed_n": judge_failed_n, "updated_at": iso()}; write_json(run / "progress.json", progress)
        aggregate = {}
        for dataset in args.datasets:
            metric_path = run / "datasets" / dataset / "metrics.json"
            if metric_path.is_file(): aggregate[dataset] = json.loads(metric_path.read_text(encoding="utf-8"))
        write_json(run / "aggregated-metrics.json", aggregate)
        write_json(run / "report.json", {"datasets": list(aggregate), "metrics": aggregate, "generated_at": iso()})
        lines = [
            "# MOI current-corpus evaluation",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: experiment-agent",
            "- Origin Mode: run",
            f"- Origin Date: {iso()}",
            "- Verification Status: UNVERIFIED",
            "- Version Label: current_corpus_adapted_v1",
            "",
            "These results use only documents already present in MatrixOne and do not claim the official full-corpus protocol.",
            "",
            "| Dataset | Attempts | Availability | Retrieval core | Answer core | N/A / protocol note |",
            "|---|---:|---:|---|---|---|",
        ]
        for name, value in aggregate.items():
            core = value.get("retrieval", {}) if isinstance(value, dict) else {}
            retrieval_text = f"Source R@1={core.get('source_recall_at_1', 'N/A')}; Source R@10={core.get('source_recall_at_10', 'N/A')}; MRR={core.get('reciprocal_rank', 'N/A')}"
            if name in {"enterpriserag-bench", "fab-bench"}:
                retrieval_text = f"Doc R@10={value.get('doc_recall_at_10')}; Complete@10={value.get('complete_evidence_set_recall_at_10')}; invalid extras={value.get('invalid_extra_docs')}"
            answer_text = f"lexical F1={value.get('answer_lexical_f1', 'N/A')}"
            if name == "docbench":
                answer_text = f"correctness={value.get('correctness', {}).get('correctness', 'N/A')}"
            elif name == "mmdocrag":
                answer_text = f"BLEU-1={value.get('answer', {}).get('bleu_1_adapted', 'N/A')}; ROUGE-L={value.get('answer', {}).get('rouge_l', 'N/A')}; judge={value.get('judge', {}).get('average', 'N/A')}"
            elif name == "fab-bench":
                answer_text += f"; objective accuracy={value.get('objective_accuracy', {}).get('accuracy', 'N/A')}"
            lines.append(f"| {name} | {core.get('attempts', 'N/A')} | {core.get('initial_availability', value.get('availability', 'N/A'))} | {retrieval_text} | {answer_text} | {value.get('na_reason', 'CURRENT_CORPUS_ADAPTED')} |")
        (run / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_json(run / "state.json", {"status": "succeeded", "stage": "complete", "updated_at": iso()}); return 0
    except Exception as exc:
        if is_api_failure(str(exc)):
            write_json(run / "control" / "API_ERROR_STOP.json", {"time": iso(), "error": str(exc)})
        write_json(run / "state.json", {"status": "failed", "stage": "stopped", "error": str(exc), "updated_at": iso()}); return 2


if __name__ == "__main__": raise SystemExit(main())
