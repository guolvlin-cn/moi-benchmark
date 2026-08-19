#!/usr/bin/env python3
"""Watch and safely recover the current serialized MOI evaluation run.

The evaluator already has a per-worker watchdog.  This process is a second,
external safety net: it observes only the selected run and the dedicated
``matrixone`` container, preserves the run's resume semantics, and never
touches competitor services.  It deliberately does not retry a terminal
``failed`` state without human review.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Any


RAG_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = RAG_ROOT / "runs" / "current-corpus-eval"
LIVE_LOG = RAG_ROOT / "runs" / "current-corpus-eval-live.log"
DSN_RE = re.compile(r"([^:]+):(.+)@tcp\(([^:]+):(\d+)\)/.*")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def discover_run() -> Path:
    candidates = [p for p in DEFAULT_RUN_ROOT.iterdir() if p.is_dir()]
    if not candidates:
        raise SystemExit(f"no evaluation run found under {DEFAULT_RUN_ROOT}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default


def emit(run: Path, message: str) -> None:
    line = f"[{now()}] {message}"
    control = run / "control"
    control.mkdir(parents=True, exist_ok=True)
    with (control / "monitor.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def process_rows() -> list[tuple[int, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    rows: list[tuple[int, str]] = []
    for raw in result.stdout.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            rows.append((int(parts[0]), parts[1]))
        except ValueError:
            continue
    return rows


def matching_processes(run: Path) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    run_text = str(run)
    main: list[tuple[int, str]] = []
    workers: list[tuple[int, str]] = []
    for pid, command in process_rows():
        if "benchmarks/moi_current_corpus_eval.py" in command and "--resume" in command and run_text in command:
            main.append((pid, command))
        if "local_matrixflow_rag.py run" in command and run_text in command:
            workers.append((pid, command))
    return main, workers


def stage_dataset(state: dict[str, Any]) -> str | None:
    stage = str(state.get("stage") or "")
    if ":" in stage:
        stage = stage.split(":", 1)[1]
    return stage or None


def config_for(run: Path, dataset: str | None) -> Path | None:
    if not dataset:
        return None
    path = run / "configs" / f"config.{dataset}.maas.json"
    return path if path.is_file() else None


def matrixone_dsn(config: Path) -> tuple[str, str, str, str] | None:
    cfg = read_json(config, {})
    try:
        dsn = str(cfg["matrixone"]["dsn"])
    except (KeyError, TypeError):
        return None
    match = DSN_RE.fullmatch(dsn)
    return match.groups() if match else None


def matrixone_sql_ready(config: Path | None) -> bool:
    if config is None:
        return False
    parsed = matrixone_dsn(config)
    if parsed is None:
        return False
    user, password, host, port = parsed
    mysql = shutil.which("mysql") or "/opt/homebrew/opt/mysql-client/bin/mysql"
    if not Path(mysql).is_file():
        return False
    cfg = read_json(config, {})
    try:
        database = str(cfg["matrixone"]["database"])
    except (KeyError, TypeError):
        return False
    env = os.environ.copy()
    # Keep credentials in the child environment; never print them.
    env["MYSQL_PWD"] = password
    command = [
        mysql,
        "--connect-timeout=2",
        "--batch",
        "--skip-column-names",
        "-h",
        host,
        "-P",
        port,
        "-u",
        user,
        database,
        "-e",
        "SELECT 1",
    ]
    try:
        probe = subprocess.run(command, env=env, text=True, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0 and probe.stdout.strip() == "1"


def matrixone_container_running() -> bool:
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", "matrixone"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def log_age() -> float | None:
    try:
        return max(0.0, time.time() - LIVE_LOG.stat().st_mtime)
    except OSError:
        return None


def last_progress_line() -> str:
    try:
        data = LIVE_LOG.read_bytes()[-128 * 1024 :].decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line.strip() for line in data.splitlines() if "attempt=" in line]
    return lines[-1] if lines else ""


def restart_matrixone(run: Path) -> bool:
    emit(run, "RECOVERY restarting dedicated MatrixOne container; competitor services untouched")
    try:
        result = subprocess.run(
            ["docker", "restart", "matrixone"],
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        emit(run, f"RECOVERY MatrixOne restart command failed: {type(exc).__name__}")
        return False
    if result.returncode:
        emit(run, f"RECOVERY MatrixOne restart returned code={result.returncode}")
        return False
    emit(run, "RECOVERY MatrixOne restart command completed; evaluator will resume from checkpoint")
    return True


def launch_resume(run: Path) -> bool:
    command = [
        sys.executable,
        str(RAG_ROOT / "benchmarks" / "moi_current_corpus_eval.py"),
        "--resume",
        str(run),
        "--query-workers",
        "1",
        "--judge-workers",
        "2",
    ]
    log_path = run / "control" / "monitor-restarted-main.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = log_path.open("a", encoding="utf-8")
        subprocess.Popen(
            command,
            cwd=RAG_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except OSError as exc:
        emit(run, f"RECOVERY could not relaunch evaluator: {type(exc).__name__}")
        return False
    emit(run, "RECOVERY relaunched evaluator with --resume; existing per-QA results are retained")
    return True


def event_count(marker: str) -> int:
    try:
        return LIVE_LOG.read_text(encoding="utf-8", errors="replace").count(marker)
    except OSError:
        return 0


def monitor(run: Path, interval: float, stale_seconds: float, once: bool) -> int:
    run = run.resolve()
    state_path = run / "state.json"
    emit(run, f"MONITOR started run={run} interval={interval:.0f}s stale_threshold={stale_seconds:.0f}s")
    seen_restart_events = event_count("MATRIXONE AUTO-RESTART requested")
    last_internal_restart = time.monotonic()
    unhealthy_polls = 0
    while True:
        state = read_json(state_path, {})
        status = str(state.get("status") or "unknown")
        dataset = stage_dataset(state)
        main, workers = matching_processes(run)
        age = log_age()
        container_up = matrixone_container_running()
        config = config_for(run, dataset)
        sql_ready = matrixone_sql_ready(config) if status == "running" else container_up
        current_events = event_count("MATRIXONE AUTO-RESTART requested")
        if current_events > seen_restart_events:
            seen_restart_events = current_events
            last_internal_restart = time.monotonic()
            emit(run, "MONITOR observed evaluator MatrixOne auto-restart; external recovery suppressed for cooldown")

        progress = last_progress_line()
        age_text = "n/a" if age is None else f"{age:.0f}s"
        emit(
            run,
            f"HEARTBEAT status={status} stage={dataset or '-'} main={len(main)} workers={len(workers)} "
            f"matrixone={'up' if container_up else 'down'} sql={'ready' if sql_ready else 'not-ready'} "
            f"log_age={age_text} progress={progress[-160:] if progress else '-'}",
        )

        if status in {"succeeded", "complete", "completed"}:
            emit(run, "MONITOR terminal success; all serialized benchmark stages are complete")
            return 0
        if status in {"failed", "blocked", "error"}:
            emit(run, f"MONITOR terminal non-success state={status}; no blind retry was issued")
            return 2

        if status == "running" and not main:
            emit(run, "ANOMALY evaluator coordinator is missing while run state is running")
            if launch_resume(run):
                time.sleep(min(interval, 10.0))
                if once:
                    return 0
                continue

        stale = age is not None and age >= stale_seconds
        if status == "running" and stale and workers:
            emit(run, f"ANOMALY worker output stale for {age:.0f}s; checking MatrixOne before recovery")
            if not sql_ready:
                unhealthy_polls += 1
                emit(run, f"ANOMALY MatrixOne SQL probe failed consecutive={unhealthy_polls}")
                if unhealthy_polls >= 2 and time.monotonic() - last_internal_restart >= 300:
                    if restart_matrixone(run):
                        unhealthy_polls = 0
                        last_internal_restart = time.monotonic()
            else:
                unhealthy_polls = 0
                emit(run, "ANOMALY log is stale but MatrixOne SQL is ready; no process kill issued")
        else:
            unhealthy_polls = 0

        if once:
            return 0
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None, help="evaluation run directory; defaults to newest current-corpus-eval run")
    parser.add_argument("--interval", type=float, default=600.0)
    parser.add_argument("--stale-seconds", type=float, default=300.0)
    parser.add_argument("--once", action="store_true", help="emit one check and exit")
    args = parser.parse_args()
    run = (args.run or discover_run()).resolve()
    if not run.is_dir():
        raise SystemExit(f"run directory does not exist: {run}")
    return monitor(run, max(5.0, args.interval), max(60.0, args.stale_seconds), args.once)


if __name__ == "__main__":
    raise SystemExit(main())
