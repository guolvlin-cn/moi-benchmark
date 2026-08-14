from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shlex
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Optional

from astra.runners.astra_smoke.core import (
    ControllerError as SmokeControllerError,
    parse_identity,
    probe_run_command,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RESERVED_LEDGER_FIELDS = {
    "schema_version",
    "run_id",
    "sequence",
    "timestamp",
    "monotonic_ns",
    "event",
}


class LifecycleConfigurationError(ValueError):
    """A C0 configuration cannot preserve the lifecycle contract."""


class LifecycleControllerError(RuntimeError):
    """The external C0 controller could not establish ground truth."""


_CLEANUP_REPORT_PUBLISH_GRACE_SEC = 1.0
_CLEANUP_REPORT_POLL_INTERVAL_SEC = 0.05


class JsonlLedger:
    """Append-only host-side evidence; prompts and credentials never enter it."""

    def __init__(self, path: Path, run_id: str):
        if not run_id or "\n" in run_id or "\x00" in run_id:
            raise LifecycleConfigurationError("run_id must be a non-empty safe string")
        if path.exists() and path.stat().st_size:
            raise LifecycleConfigurationError(
                f"refusing to append a new run to non-empty ledger {path}"
            )
        self.path = path
        self.run_id = run_id
        self._sequence = 0
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, **fields: Any) -> None:
        if not _SAFE_ID.fullmatch(event):
            raise LifecycleConfigurationError(f"invalid ledger event {event!r}")
        overlap = _RESERVED_LEDGER_FIELDS.intersection(fields)
        if overlap:
            raise LifecycleConfigurationError(
                f"ledger fields override reserved names: {sorted(overlap)}"
            )
        self._sequence += 1
        record = {
            "schema_version": 1,
            "run_id": self.run_id,
            "sequence": self._sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


@dataclass(frozen=True)
class ExternalTriggerManifest:
    task_id: str
    predicate_id: str
    stable_observations: int = 2

    def __post_init__(self) -> None:
        for name, value in (
            ("task_id", self.task_id),
            ("predicate_id", self.predicate_id),
        ):
            if not _SAFE_ID.fullmatch(value):
                raise LifecycleConfigurationError(
                    f"{name} must contain only letters, digits, dot, underscore, or dash"
                )
        if self.stable_observations < 2:
            raise LifecycleConfigurationError(
                "stable_observations must be at least 2 for a stable trigger"
            )

    @property
    def sha256(self) -> str:
        payload = {
            "predicate_id": self.predicate_id,
            "stable_observations": self.stable_observations,
            "task_id": self.task_id,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def probe_command(self, remote_probe_path: str) -> str:
        _validate_absolute_path("predicate_probe_path", remote_probe_path)
        return shlex.join(
            [
                "python3",
                remote_probe_path,
                "--predicate",
                self.predicate_id,
            ]
        )


_TERMINAL_BENCH_TRIGGERS = MappingProxyType(
    {
        "modernize-scientific-stack": ExternalTriggerManifest(
            task_id="modernize-scientific-stack",
            predicate_id="terminal-bench.modernize-scientific-stack.partial-outputs",
        ),
        "overfull-hbox": ExternalTriggerManifest(
            task_id="overfull-hbox",
            predicate_id="terminal-bench.overfull-hbox.changed-input-before-clean-log",
        ),
        "build-pmars": ExternalTriggerManifest(
            task_id="build-pmars",
            predicate_id="terminal-bench.build-pmars.source-before-install",
        ),
        "db-wal-recovery": ExternalTriggerManifest(
            task_id="db-wal-recovery",
            predicate_id="terminal-bench.db-wal-recovery.valid-wal-before-output",
        ),
    }
)

_TERMINAL_BENCH_INSTRUCTION_SHA256_TO_TASK = MappingProxyType(
    {
        "ce5cc4b2dd0124585075e05bb2ac9fe054db84505775c6abd510494730fd52c9": (
            "modernize-scientific-stack"
        ),
        "ed35ef98fea7c2c20aed08a1b7a672f9598b559b64bc55420ca95d2ecd58e383": (
            "overfull-hbox"
        ),
        "2dafecb550250ca7041a15c4214508e65ca9ec92bbd62b35f36289183d2f161f": (
            "build-pmars"
        ),
        "a4c35219925fea21dd614ca42eb4392a79a03d41b951d5f4c1e9012b8349239a": (
            "db-wal-recovery"
        ),
    }
)


def get_terminal_bench_trigger(task_id: str) -> ExternalTriggerManifest:
    try:
        return _TERMINAL_BENCH_TRIGGERS[task_id]
    except KeyError as exc:
        raise LifecycleConfigurationError(
            f"no pre-registered Terminal-Bench C0 trigger for {task_id!r}"
        ) from exc


def get_terminal_bench_trigger_for_instruction(
    instruction: str,
) -> ExternalTriggerManifest:
    if not isinstance(instruction, str):
        raise LifecycleConfigurationError("instruction must be a string")
    instruction_sha256 = hashlib.sha256(instruction.strip().encode()).hexdigest()
    try:
        task_id = _TERMINAL_BENCH_INSTRUCTION_SHA256_TO_TASK[instruction_sha256]
    except KeyError as exc:
        raise LifecycleConfigurationError(
            "instruction does not match a pre-registered Terminal-Bench C0 case "
            f"(sha256={instruction_sha256})"
        ) from exc
    return get_terminal_bench_trigger(task_id)


def process_probe_source_path() -> Path:
    """Locate, but do not duplicate, the existing Linux process launcher."""
    path = Path(__file__).resolve().parents[1] / "astra_smoke" / "probe.py"
    if not path.is_file():
        raise LifecycleConfigurationError(f"process probe is missing: {path}")
    return path


def lifecycle_predicate_probe_source_path() -> Path:
    path = Path(__file__).with_name("predicate_probe.py").resolve()
    if not path.is_file():
        raise LifecycleConfigurationError(f"predicate probe is missing: {path}")
    return path


def lifecycle_predicate_probe_source_sha256() -> str:
    digest = hashlib.sha256()
    with lifecycle_predicate_probe_source_path().open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_probe_run_command(
    *,
    probe_path: str,
    identity_path: str,
    stdout_path: str,
    stderr_path: str,
    stdin_path: str,
    cwd: str,
    child_argv: list[str],
    deadline_sec: Optional[float] = None,
    cleanup_report_path: Optional[str] = None,
    cleanup_grace_sec: float = 2.0,
    strict_cleanup: bool = False,
    exclude_stdout_json_events: Optional[list[str]] = None,
) -> str:
    return probe_run_command(
        probe_path=probe_path,
        identity_path=identity_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        stdin_path=stdin_path,
        cwd=cwd,
        child_argv=child_argv,
        deadline_sec=deadline_sec,
        cleanup_report_path=cleanup_report_path,
        cleanup_grace_sec=cleanup_grace_sec,
        strict_cleanup=strict_cleanup,
        exclude_stdout_json_events=exclude_stdout_json_events,
    )


def process_probe_cleanup_command(
    *,
    probe_path: str,
    identity_path: str,
    cleanup_report_path: str,
    timeout_sec: float,
) -> str:
    for name, value in (
        ("probe_path", probe_path),
        ("identity_path", identity_path),
        ("cleanup_report_path", cleanup_report_path),
    ):
        _validate_absolute_path(name, value)
    if timeout_sec <= 0:
        raise LifecycleConfigurationError("cleanup timeout must be positive")
    return shlex.join(
        [
            "python3",
            probe_path,
            "cleanup",
            "--identity",
            identity_path,
            "--cleanup-report",
            cleanup_report_path,
            "--timeout-sec",
            str(timeout_sec),
        ]
    )


def parse_process_cleanup_report(raw: str) -> dict[str, Any]:
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LifecycleControllerError(
            f"process cleanup report is invalid JSON: {exc}"
        ) from exc
    if not isinstance(report, dict):
        raise LifecycleControllerError("process cleanup report must be an object")
    if (
        report.get("schema_version") != 1
        or report.get("status") != "clean"
        or report.get("fault_action") is not False
        or report.get("zero_live_proven") is not True
        or report.get("remaining_pids_count") != 0
        or report.get("remaining_pids") != []
        or not isinstance(report.get("reason"), str)
        or report.get("product_terminal_status")
        not in {"completed", "failed", "timeout", "cancelled"}
    ):
        raise LifecycleControllerError(
            "process cleanup report does not prove a fault-free zero-live state"
        )
    return report


async def collect_process_cleanup_report(
    environment: Any,
    *,
    probe_path: str,
    identity_path: str,
    cleanup_report_path: str,
    request_cleanup: bool,
    cleanup_timeout_sec: float = 10.0,
) -> tuple[dict[str, Any], str]:
    """Optionally stop a supervisor, then return verified zero-live evidence."""
    cleanup_request_failed = False
    if request_cleanup:
        cleanup = await environment.exec(
            command=process_probe_cleanup_command(
                probe_path=probe_path,
                identity_path=identity_path,
                cleanup_report_path=cleanup_report_path,
                timeout_sec=cleanup_timeout_sec,
            ),
            timeout_sec=cleanup_timeout_sec + 2,
        )
        cleanup_request_failed = cleanup.return_code != 0
    loop = asyncio.get_running_loop()
    publish_deadline = loop.time() + min(
        cleanup_timeout_sec,
        _CLEANUP_REPORT_PUBLISH_GRACE_SEC,
    )
    read_timeout_sec = max(0.1, min(1.0, cleanup_timeout_sec))
    while True:
        result = await environment.exec(
            command=f"cat {shlex.quote(cleanup_report_path)}",
            timeout_sec=read_timeout_sec,
        )
        if result.return_code == 0 and result.stdout:
            report = parse_process_cleanup_report(result.stdout)
            report_sha256 = hashlib.sha256(result.stdout.encode()).hexdigest()
            return report, report_sha256
        remaining = publish_deadline - loop.time()
        if remaining <= 0:
            if cleanup_request_failed:
                raise LifecycleControllerError(
                    "registered process cleanup request failed"
                )
            raise LifecycleControllerError(
                "process cleanup report is unavailable"
            )
        await asyncio.sleep(
            min(_CLEANUP_REPORT_POLL_INTERVAL_SEC, remaining)
        )


def _validate_absolute_path(name: str, value: str) -> None:
    if not value.startswith("/") or "\n" in value or "\x00" in value:
        raise LifecycleConfigurationError(f"{name} must be a safe absolute path")


@dataclass(frozen=True)
class C0ControllerConfig:
    identity_path: str
    predicate_probe_path: str
    trigger: ExternalTriggerManifest
    trigger_timeout_sec: float
    process_probe_path: Optional[str] = None
    poll_interval_sec: float = 0.25
    exec_timeout_sec: float = 5.0

    def __post_init__(self) -> None:
        _validate_absolute_path("identity_path", self.identity_path)
        _validate_absolute_path("predicate_probe_path", self.predicate_probe_path)
        if self.process_probe_path is not None:
            _validate_absolute_path("process_probe_path", self.process_probe_path)
        if self.trigger_timeout_sec <= 0:
            raise LifecycleConfigurationError("trigger_timeout_sec must be positive")
        if self.poll_interval_sec <= 0:
            raise LifecycleConfigurationError("poll_interval_sec must be positive")
        if self.exec_timeout_sec <= 0:
            raise LifecycleConfigurationError("exec_timeout_sec must be positive")


@dataclass(frozen=True)
class C0Outcome:
    trigger_hit: bool
    fault_injected: bool
    reason: str
    identity: Optional[dict[str, Any]] = None
    evidence_sha256: Optional[str] = None


class C0Controller:
    """Product-neutral, host-side lifecycle controller with a no-op fault action."""

    def __init__(
        self,
        config: C0ControllerConfig,
        emit: Callable[..., None],
    ):
        self.config = config
        self.emit = emit

    async def run(self, environment: Any, product_done: asyncio.Event) -> C0Outcome:
        self.emit(
            "lifecycle_controller_started",
            condition="C0",
            fault_action="noop",
            source="terminal-bench",
            task_id=self.config.trigger.task_id,
            predicate_id=self.config.trigger.predicate_id,
            predicate_probe_source_sha256=lifecycle_predicate_probe_source_sha256(),
            trigger_manifest_sha256=self.config.trigger.sha256,
            stable_observations=self.config.trigger.stable_observations,
        )
        try:
            return await self._run(environment, product_done)
        except LifecycleControllerError as exc:
            self.emit(
                "lifecycle_controller_failed",
                error_type=type(exc).__name__,
                reason=str(exc),
            )
            raise
        except Exception as exc:
            wrapped = LifecycleControllerError(
                f"unexpected controller failure: {type(exc).__name__}: {exc}"
            )
            self.emit(
                "lifecycle_controller_failed",
                error_type=type(exc).__name__,
                reason=str(wrapped),
            )
            raise wrapped from exc

    async def _run(
        self, environment: Any, product_done: asyncio.Event
    ) -> C0Outcome:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.config.trigger_timeout_sec
        identity, no_identity_reason = await self._wait_for_identity(
            environment, product_done, deadline
        )
        if identity is None:
            self.emit("trigger_no_hit", reason=no_identity_reason)
            return C0Outcome(False, False, no_identity_reason)

        identity_payload = json.dumps(
            identity, sort_keys=True, separators=(",", ":")
        ).encode()
        self.emit(
            "product_process_registered",
            pid=identity["pid"],
            ppid=identity["ppid"],
            pgid=identity["pgid"],
            sid=identity["sid"],
            start_ticks=identity["start_ticks"],
            exe=identity["exe"],
            cgroup_sha256=hashlib.sha256(identity["cgroup"].encode()).hexdigest(),
            supervisor_pid=identity["supervisor"]["pid"],
            identity_sha256=hashlib.sha256(identity_payload).hexdigest(),
        )

        probe_command = self.config.trigger.probe_command(
            self.config.predicate_probe_path
        )
        stable_count = 0
        previous_evidence_sha256: Optional[str] = None
        while loop.time() < deadline:
            if product_done.is_set():
                terminal_status = getattr(
                    product_done, "_c0_product_terminal_status", None
                )
                reason = {
                    "timeout": "product_timeout",
                    "cancelled": "product_cancelled",
                }.get(terminal_status, "product_exited")
                self.emit("trigger_no_hit", reason=reason)
                return C0Outcome(False, False, reason, identity)

            result = await environment.exec(
                command=probe_command,
                timeout_sec=self.config.exec_timeout_sec,
            )
            matched, evidence, evidence_sha256 = _parse_predicate_result(
                result, self.config.trigger.predicate_id
            )
            if matched:
                if evidence_sha256 == previous_evidence_sha256:
                    stable_count += 1
                else:
                    stable_count = 1
                    previous_evidence_sha256 = evidence_sha256
            if stable_count >= self.config.trigger.stable_observations:
                if self.config.process_probe_path is not None:
                    inspect_command = shlex.join(
                        [
                            "python3",
                            self.config.process_probe_path,
                            "inspect",
                            "--identity",
                            self.config.identity_path,
                            "--expected-exe",
                            identity["exe"],
                        ]
                    )
                    inspect = await environment.exec(
                        command=inspect_command,
                        timeout_sec=self.config.exec_timeout_sec,
                    )
                    if inspect.return_code != 0:
                        reason = "product_exited_before_noop"
                        self.emit("trigger_no_hit", reason=reason)
                        return C0Outcome(False, False, reason, identity)
                self.emit(
                    "trigger_observed",
                    task_id=self.config.trigger.task_id,
                    predicate_id=self.config.trigger.predicate_id,
                    stable_observations=stable_count,
                    evidence=evidence,
                    evidence_sha256=evidence_sha256,
                )
                self.emit("fault_action", action="noop", executed=True)
                return C0Outcome(
                    True,
                    False,
                    "clean_noop",
                    identity,
                    evidence_sha256,
                )
            if not matched:
                stable_count = 0
                previous_evidence_sha256 = None
            await asyncio.sleep(self.config.poll_interval_sec)

        self.emit("trigger_no_hit", reason="controller_trigger_timeout")
        return C0Outcome(False, False, "controller_trigger_timeout", identity)

    async def _wait_for_identity(
        self,
        environment: Any,
        product_done: asyncio.Event,
        deadline: float,
    ) -> tuple[Optional[dict[str, Any]], str]:
        command = f"cat {shlex.quote(self.config.identity_path)}"
        loop = asyncio.get_running_loop()
        while loop.time() < deadline:
            if product_done.is_set():
                terminal_status = getattr(
                    product_done, "_c0_product_terminal_status", None
                )
                return None, {
                    "timeout": "product_timeout_before_identity",
                    "cancelled": "product_cancelled_before_identity",
                }.get(terminal_status, "product_exited_before_identity")
            result = await environment.exec(
                command=command,
                timeout_sec=self.config.exec_timeout_sec,
            )
            if result.return_code == 0:
                if not result.stdout:
                    raise LifecycleControllerError(
                        "identity probe returned an empty identity file"
                    )
                try:
                    return parse_identity(result.stdout), ""
                except SmokeControllerError as exc:
                    raise LifecycleControllerError(
                        f"invalid registered process identity: {exc}"
                    ) from exc
            if result.return_code != 1:
                raise LifecycleControllerError(
                    "identity probe failed with return code "
                    f"{result.return_code}"
                )
            await asyncio.sleep(self.config.poll_interval_sec)
        return None, "controller_trigger_timeout_before_identity"


def _parse_predicate_result(
    result: Any, expected_predicate_id: str
) -> tuple[bool, dict[str, Any], str]:
    try:
        payload = json.loads(result.stdout or "")
    except (TypeError, json.JSONDecodeError) as exc:
        raise LifecycleControllerError(
            "predicate probe returned malformed JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise LifecycleControllerError("predicate probe output is not an object")
    if payload.get("schema_version") != 1:
        raise LifecycleControllerError("predicate probe schema version is invalid")
    if payload.get("predicate_id") != expected_predicate_id:
        raise LifecycleControllerError("predicate probe returned the wrong predicate ID")
    matched = payload.get("matched")
    if not isinstance(matched, bool):
        raise LifecycleControllerError("predicate probe has no boolean matched field")
    if (result.return_code, matched) not in {(0, True), (1, False)}:
        detail = payload.get("error_type", "invalid_status")
        raise LifecycleControllerError(
            f"predicate probe failed closed: return_code={result.return_code}, "
            f"error_type={detail}"
        )
    evidence = payload.get("evidence", {})
    if not isinstance(evidence, dict):
        raise LifecycleControllerError("predicate probe evidence is not an object")
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    return matched, evidence, hashlib.sha256(canonical).hexdigest()
