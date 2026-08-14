from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Sequence

from .contract import ContractError


@dataclass(frozen=True)
class ProcessResult:
    return_code: int
    duration_seconds: float
    termination_reason: str
    terminated_pid: int
    escalated_to_sigkill: bool


def _copy_stream(
    source: BinaryIO,
    destination: BinaryIO,
    line_filter: Callable[[bytes], bytes | None] | None = None,
) -> None:
    try:
        if line_filter is not None:
            for line in source:
                filtered = line_filter(line)
                if filtered is not None:
                    destination.write(filtered)
                    destination.flush()
            return
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                break
            destination.write(chunk)
            destination.flush()
    finally:
        source.close()


def terminate_process_group(
    process: subprocess.Popen[bytes], *, grace_seconds: float = 10.0
) -> bool:
    if process.poll() is not None:
        return False
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    try:
        process.wait(timeout=grace_seconds)
        return False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=grace_seconds)
        return True


def run_monitored_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdin_payload: bytes,
    stdout_path: Path,
    stderr_path: Path,
    deadline_seconds: int,
    budget_exceeded: Callable[[], bool],
    on_start: Callable[[int], None] | None = None,
    on_agent_start: Callable[[], None] | None = None,
    stdout_line_filter: Callable[[bytes], bytes | None] | None = None,
    poll_interval_seconds: float = 0.1,
) -> ProcessResult:
    if not argv or any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise ContractError("invalid product argv")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        if on_start is not None:
            on_start(process.pid)
        stdout_thread = threading.Thread(
            target=_copy_stream,
            args=(process.stdout, stdout_file, stdout_line_filter),
            name="product-stdout-copy",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_copy_stream,
            args=(process.stderr, stderr_file),
            name="product-stderr-copy",
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            process.stdin.write(stdin_payload)
            process.stdin.close()
        except BrokenPipeError:
            pass

        # Product process creation is an infrastructure/startup phase. The
        # frozen Agent window starts only after the prompt is handed over.
        agent_started = time.monotonic()
        deadline_monotonic = agent_started + deadline_seconds
        if on_agent_start is not None:
            on_agent_start()

        reason = "product_exit"
        escalated = False
        while process.poll() is None:
            if budget_exceeded():
                reason = "max_model_requests"
                escalated = terminate_process_group(process)
                break
            if time.monotonic() >= deadline_monotonic:
                reason = "agent_deadline"
                escalated = terminate_process_group(process)
                break
            time.sleep(poll_interval_seconds)
        if reason == "product_exit" and budget_exceeded():
            reason = "max_model_requests"
        if process.poll() is None:
            escalated = terminate_process_group(process) or escalated
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        return ProcessResult(
            return_code=int(process.returncode),
            duration_seconds=time.monotonic() - agent_started,
            termination_reason=reason,
            terminated_pid=process.pid,
            escalated_to_sigkill=escalated,
        )
