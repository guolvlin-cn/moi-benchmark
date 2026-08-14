from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .artifact_contract import read_jsonl, validate_run_artifacts
from .contract import (
    ContractError,
    ensure_descendant,
    read_json_object,
    sha256_file,
    utc_now,
    validate_id,
    write_json_atomic,
    write_sha256_manifest,
)


EXPERIMENT_ID = "toolathlon-verified-v0.5"
SYSTEMS = ("astra", "hermes")
M1_TASK = "find-alita-paper"
FIRST_BATCH: tuple[tuple[str, tuple[str, str]], ...] = (
    ("find-alita-paper", ("astra", "hermes")),
    ("set-conf-cr-ddl", ("hermes", "astra")),
    ("course-schedule", ("astra", "hermes")),
    ("canvas-homework-grader-python", ("hermes", "astra")),
    ("arrange-workspace", ("astra", "hermes")),
    ("notion-movies", ("hermes", "astra")),
    ("price-comparison", ("astra", "hermes")),
    ("quantitative-financial-analysis", ("hermes", "astra")),
    ("excel-data-transformation", ("astra", "hermes")),
    ("notion-hr", ("hermes", "astra")),
    ("shopping-helper", ("astra", "hermes")),
    ("woocommerce-stock-alert", ("hermes", "astra")),
    ("git-bug-hunt", ("astra", "hermes")),
    ("k8s-safety-audit", ("hermes", "astra")),
)
AUTO_REPLACEMENT_FAILURES = frozenset({"environment_error", "evaluator_error"})
COMMON_FREEZE_FIELDS = (
    "m0_manifest_sha256",
    "sections_3_1_3_2_manifest_sha256",
    "section_3_3_sha256",
    "section_3_3_manifest_sha256",
    "adapter_freeze_sha256",
    "model_sha256",
    "runtime_tiers_sha256",
    "task_requirements_sha256",
    "execution_protocol_sha256",
    "vm_freeze_sha256",
    "credential_manifest_sha256",
    "app_state_live_sha256",
    "task_image_reference",
)
MODEL_PAIR_FIELDS = (
    "provider",
    "provider_base_url",
    "request_id",
    "documented_version",
    "temperature",
    "temperature_effective",
    "thinking",
    "thinking_wire_behavior",
    "reasoning_effort",
    "reasoning_effort_wire_behavior",
    "generation_parameter_source",
)


class M2Blocked(ContractError):
    """The batch cannot safely advance without preserving or reviewing evidence."""


@dataclass(frozen=True)
class Attempt:
    directory: Path
    run: dict[str, Any]
    resolved: dict[str, Any]
    validation: dict[str, Any]


@dataclass(frozen=True)
class SlotDecision:
    state: str
    effective: Attempt | None
    original: Attempt | None
    replacement: Attempt | None
    reason: str


def observation_value(value: Any, label: str) -> Any:
    if not isinstance(value, dict) or set(value) != {
        "value",
        "source",
        "reliability",
        "missing_reason",
    }:
        raise ContractError(f"{label} is not a structured observation")
    return value["value"]


def _safe_root(path: Path, label: str) -> Path:
    resolved = path.resolve()
    allowed = (Path("/home/vagrant/moi-benchmark"), Path("/tmp"))
    if not any(resolved == root or root in resolved.parents for root in allowed):
        raise ContractError(f"{label} must be below /home/vagrant/moi-benchmark or /tmp")
    return resolved


def _verify_single_file_manifest(manifest_path: Path, target_path: Path) -> None:
    expected = f"{sha256_file(target_path)}  {target_path.name}"
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"cannot read checksum manifest {manifest_path}: {exc}") from exc
    if lines != [expected]:
        raise ContractError(f"checksum manifest mismatch: {manifest_path}")


def _freeze_snapshot(freeze: Path) -> dict[str, Any]:
    records = {
        "m0_manifest_sha256": sha256_file(freeze / "m0.sha256"),
        "sections_3_1_3_2_manifest_sha256": sha256_file(
            freeze / "sections-3.1-3.2.sha256"
        ),
        "section_3_3_sha256": sha256_file(freeze / "section-3.3.freeze.json"),
        "section_3_3_manifest_sha256": sha256_file(freeze / "section-3.3.sha256"),
        "adapter_freeze_sha256": sha256_file(freeze / "adapter.freeze.json"),
        "model_sha256": sha256_file(freeze / "model.freeze.json"),
        "runtime_tiers_sha256": sha256_file(freeze / "task-runtime-tiers.json"),
        "task_requirements_sha256": sha256_file(freeze / "task-requirements.json"),
        "execution_protocol_sha256": sha256_file(
            freeze / "execution-protocol.freeze.json"
        ),
        "vm_freeze_sha256": sha256_file(freeze / "vm.freeze.json"),
        "credential_manifest_sha256": sha256_file(
            freeze / "credential-manifest.json"
        ),
        "app_state_live_sha256": sha256_file(freeze / "m1-app-state-live.json"),
        "task_image_reference": (
            "docker.io/lockon0927/toolathlon-task-image@"
            "sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f"
        ),
    }
    return records


def _frozen_first_batch(freeze: Path) -> tuple[tuple[str, tuple[str, str]], ...]:
    protocol = read_json_object(freeze / "execution-protocol.freeze.json")
    phase = protocol.get("formal_phases", {}).get("first_batch", {})
    tasks = phase.get("tasks")
    if tasks != [task for task, _order in FIRST_BATCH]:
        raise ContractError("M2 task order differs from execution-protocol.freeze.json")
    expected_orders = [
        {"task_id": task_id, "systems": list(order)}
        for task_id, order in FIRST_BATCH
    ]
    if phase.get("system_orders") != expected_orders:
        raise ContractError(
            "M2 system order differs from execution-protocol.freeze.json"
        )
    if protocol.get("scope", {}).get("workers") != 1:
        raise ContractError("M2 requires frozen workers=1")
    if protocol.get("retry", {}).get("automatic_replacement_maximum") != 1:
        raise ContractError("M2 requires exactly one allowed infrastructure replacement")
    return FIRST_BATCH


def load_attempt(directory: Path, *, task_id: str, system: str) -> Attempt:
    validation = validate_run_artifacts(directory)
    run = read_json_object(directory / "run.json")
    resolved = read_json_object(directory / "resolved-config.json")
    if run.get("task_id") != task_id or run.get("system_id") != system:
        raise ContractError(f"run identity mismatch: {directory}")
    if resolved.get("run_id") != run.get("run_id"):
        raise ContractError(f"resolved run identity mismatch: {directory}")
    if run.get("artifact_gate", {}).get("status") != "passed":
        raise ContractError(f"run artifact gate is not passed: {directory}")
    return Attempt(directory=directory, run=run, resolved=resolved, validation=validation)


def load_slot_candidates(root: Path, *, task_id: str, system: str) -> list[Attempt]:
    task_root = root / "runs" / system / task_id
    if not task_root.exists():
        return []
    if not task_root.is_dir():
        raise ContractError(f"slot path is not a directory: {task_root}")
    directories = sorted(path for path in task_root.iterdir() if path.is_dir())
    other = sorted(path.name for path in task_root.iterdir() if not path.is_dir())
    if other:
        raise ContractError(f"unexpected non-directory slot entries: {other}")
    if len(directories) > 2:
        raise ContractError(f"more than two attempts exist for {system}/{task_id}")
    return [load_attempt(path, task_id=task_id, system=system) for path in directories]


def _split_candidates(candidates: list[Attempt]) -> tuple[Attempt | None, Attempt | None]:
    originals = [
        item
        for item in candidates
        if observation_value(
            item.run.get("replacement_for_run_id"), "run.replacement_for_run_id"
        )
        is None
    ]
    replacements = [item for item in candidates if item not in originals]
    if len(originals) > 1 or len(replacements) > 1:
        raise ContractError("a slot must contain one original and at most one replacement")
    if replacements and not originals:
        raise ContractError("replacement exists without an original run")
    original = originals[0] if originals else None
    replacement = replacements[0] if replacements else None
    if original is not None and replacement is not None:
        replacement_for = observation_value(
            replacement.run.get("replacement_for_run_id"),
            "run.replacement_for_run_id",
        )
        if replacement_for != original.run.get("run_id"):
            raise ContractError("replacement_for_run_id does not identify the original")
        if original.run.get("run_validity") != "infra_invalid":
            raise ContractError("replacement exists for a non-infrastructure result")
    return original, replacement


def replacement_allowed(original: Attempt) -> bool:
    return (
        original.run.get("run_validity") == "infra_invalid"
        and original.run.get("primary_failure_category")
        in AUTO_REPLACEMENT_FAILURES
    )


def decide_slot(candidates: list[Attempt]) -> SlotDecision:
    original, replacement = _split_candidates(candidates)
    if original is None:
        return SlotDecision("needs_original", None, None, None, "no original run")
    validity = original.run.get("run_validity")
    if validity == "valid":
        return SlotDecision("complete", original, original, None, "original is valid")
    if validity != "infra_invalid":
        raise ContractError("run_validity must be valid or infra_invalid")
    if not replacement_allowed(original):
        return SlotDecision(
            "blocked",
            None,
            original,
            replacement,
            "infra-invalid cause is not in the automatic public-infrastructure allowlist",
        )
    if replacement is None:
        return SlotDecision(
            "needs_replacement",
            None,
            original,
            None,
            "eligible infrastructure-invalid original",
        )
    if replacement.run.get("run_validity") == "valid":
        return SlotDecision(
            "complete", replacement, original, replacement, "replacement is valid"
        )
    return SlotDecision(
        "blocked",
        None,
        original,
        replacement,
        "the one allowed replacement is not valid",
    )


def _identity_key(attempt: Attempt) -> tuple[str, str]:
    run = attempt.run
    system = str(run["system_id"])
    replacement = observation_value(
        run.get("replacement_for_run_id"), "run.replacement_for_run_id"
    )
    ordinal = 2 if replacement is not None else 1
    identity = run.get("adapter", {}).get("product_identity")
    if not isinstance(identity, dict):
        raise ContractError("run has no product identity evidence")
    if system == "astra":
        if identity.get("attempt_ordinal") != ordinal:
            raise ContractError("Astra attempt identity ordinal mismatch")
        identity_id = identity.get("identity_id")
        fingerprint = identity.get("server_user_id_sha256") or identity.get(
            "username_sha256"
        )
    else:
        identity_id = f"{run['run_id']}:hermes-a{ordinal}"
        fingerprint = identity.get("attempt_session_id_sha256")
    if not isinstance(identity_id, str) or not identity_id:
        raise ContractError("attempt identity ID is missing")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ContractError("attempt identity fingerprint is missing")
    return identity_id, fingerprint


def validate_formal_effective(attempt: Attempt) -> None:
    run = attempt.run
    if run.get("run_validity") != "valid":
        raise ContractError("effective formal run is not valid")
    if run.get("verify_status") not in {"pass", "no_pass"}:
        raise ContractError("effective formal run has no evaluator conclusion")
    if run.get("adapter", {}).get("setup_provider_requests_before_agent") != 0:
        raise ContractError("effective formal run made a setup provider request")


def validate_m1_effective(attempt: Attempt) -> None:
    validate_formal_effective(attempt)
    run = attempt.run
    if run.get("terminal_status") != "completed":
        raise ContractError("M1 effective Agent did not complete")
    budget = run.get("model_budget")
    if not isinstance(budget, dict):
        raise ContractError("M1 model budget evidence is missing")
    forwarded = budget.get("provider_requests_forwarded")
    completed = budget.get("provider_requests_completed")
    failed = budget.get("provider_requests_failed")
    if (
        not isinstance(forwarded, int)
        or not isinstance(completed, int)
        or not isinstance(failed, int)
        or completed != forwarded
        or completed - failed < 1
    ):
        raise ContractError("M1 has no complete successful Agent model request")
    adapter_rows = read_jsonl(attempt.directory / "adapter-events.jsonl", allow_empty=False)
    model_rows = read_jsonl(attempt.directory / "model-usage.jsonl", allow_empty=False)
    starts = [row for row in adapter_rows if row.get("event") == "agent.execution_start"]
    if len(starts) != 1:
        raise ContractError("M1 has no unique Agent start event")
    start = starts[0].get("monotonic_ns")
    if any(
        row.get("event") == "model_request.started"
        and row.get("monotonic_ns", -1) < start
        for row in model_rows
    ):
        raise ContractError("M1 forwarded a provider request before Agent start")


def validate_pair(astra: Attempt, hermes: Attempt) -> None:
    for field in ("experiment_id", "task_id", "pair_id"):
        if astra.run.get(field) != hermes.run.get(field):
            raise ContractError(f"paired run mismatch: {field}")
    for field in COMMON_FREEZE_FIELDS:
        if astra.resolved.get("freeze", {}).get(field) != hermes.resolved.get(
            "freeze", {}
        ).get(field):
            raise ContractError(f"paired freeze mismatch: {field}")
    for field in MODEL_PAIR_FIELDS:
        if astra.resolved.get("model", {}).get(field) != hermes.resolved.get(
            "model", {}
        ).get(field):
            raise ContractError(f"paired model mismatch: {field}")
    fingerprints = astra.resolved["model"]["credential"]["pair_fingerprints"]
    if fingerprints != hermes.resolved["model"]["credential"]["pair_fingerprints"]:
        raise ContractError("paired provider credential fingerprints differ")
    if fingerprints.get("astra") == fingerprints.get("hermes"):
        raise ContractError("paired provider credential fingerprints are not distinct")
    astra_tools = read_json_object(astra.directory / "tool-schema-observed.json")
    hermes_tools = read_json_object(hermes.directory / "tool-schema-observed.json")
    if astra_tools.get("tool_set_sha256") != hermes_tools.get("tool_set_sha256"):
        raise ContractError("paired runtime tools/list Schema differs")


def _validate_new_run_freeze(attempt: Attempt, manifest: dict[str, Any]) -> None:
    expected = manifest.get("freeze")
    actual = attempt.resolved.get("freeze")
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        raise ContractError("batch/run freeze evidence is missing")
    for field in COMMON_FREEZE_FIELDS:
        if actual.get(field) != expected.get(field):
            raise ContractError(f"run does not use the batch freeze: {field}")


def _candidate_record(attempt: Attempt) -> dict[str, Any]:
    return {
        "run_id": attempt.run["run_id"],
        "directory": str(attempt.directory),
        "replacement_for_run_id": observation_value(
            attempt.run["replacement_for_run_id"], "run.replacement_for_run_id"
        ),
        "run_validity": attempt.run["run_validity"],
        "terminal_status": attempt.run.get("terminal_status"),
        "verify_status": attempt.run.get("verify_status"),
        "primary_failure_category": attempt.run.get("primary_failure_category"),
        "artifacts_sha256": sha256_file(attempt.directory / "artifacts.sha256"),
    }


class BatchEventLog:
    def __init__(
        self,
        path: Path,
        *,
        schema_version: str = "toolathlon.m2-scheduler-events.v1",
        phase: str = "M2",
    ) -> None:
        self.path = path
        self.schema_version = schema_version
        self.phase = phase
        self.sequence = 0
        if path.exists():
            rows = read_jsonl(path, allow_empty=True)
            if any(row.get("schema_version") != schema_version for row in rows):
                raise ContractError(f"{phase} scheduler event schema changed")
            sequences = [row.get("sequence") for row in rows]
            if sequences != list(range(1, len(rows) + 1)):
                raise ContractError(
                    f"{phase} scheduler event sequence is not contiguous"
                )
            self.sequence = len(rows)

    def append(self, event: str, **fields: Any) -> None:
        self.sequence += 1
        row = {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "timestamp": utc_now(),
            "monotonic_ns": time.monotonic_ns(),
            "event": event,
            **fields,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())


class M2Batch:
    def __init__(
        self,
        *,
        repo_root: Path,
        output_root: Path,
        m1_root: Path,
        source_root: Path,
        lifecycle_runner: Callable[[list[str]], int] | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.output_root = _safe_root(output_root, "output_root")
        self.m1_root = _safe_root(m1_root, "m1_root")
        self.source_root = source_root.resolve()
        self.freeze = self.repo_root / "astra/benchmark/toolathlon-verified/freeze"
        self.manifest_path = self.output_root / "m2-batch-manifest.json"
        self.checkpoint_path = self.output_root / "checkpoint.json"
        self.report_path = self.output_root / "m2-first-batch-qualification.json"
        self.report_hash_path = self.output_root / "m2-first-batch-qualification.sha256"
        self.batch_hash_path = self.output_root / "m2-batch-artifacts.sha256"
        self.lifecycle_runner = lifecycle_runner or self._default_lifecycle_runner
        self.events: BatchEventLog | None = None
        self.manifest: dict[str, Any] = {}
        self._lock_stream: Any = None

    def _default_lifecycle_runner(self, argv: list[str]) -> int:
        return subprocess.run(argv, cwd=self.repo_root, check=False).returncode

    def _acquire_lock(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.output_root / ".m2.lock"
        self._lock_stream = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise M2Blocked("another M2 scheduler process holds the batch lock") from exc

    def _release_lock(self) -> None:
        if self._lock_stream is not None:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_UN)
            self._lock_stream.close()
            self._lock_stream = None

    def _task_manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "position": position,
                "task_id": task_id,
                "system_order": list(order),
                "source": "m1_reuse" if position == 1 else "m2_run",
            }
            for position, (task_id, order) in enumerate(FIRST_BATCH, start=1)
        ]

    def _create_manifest(self) -> dict[str, Any]:
        _frozen_first_batch(self.freeze)
        m1_report = self.m1_root / "m1-live-qualification.json"
        m1_hash = self.m1_root / "m1-live-qualification.sha256"
        _verify_single_file_manifest(m1_hash, m1_report)
        if any(
            path.name not in {".m2.lock"}
            for path in self.output_root.iterdir()
        ):
            raise ContractError(
                "new M2 output root must be empty except for the scheduler lock"
            )
        batch_id = validate_id(
            "batch_id", f"m2-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
        )
        manifest = {
            "schema_version": "toolathlon.m2-first-batch-manifest.v1",
            "created_at": utc_now(),
            "batch_id": batch_id,
            "experiment_id": EXPERIMENT_ID,
            "workers": 1,
            "source_root": str(self.source_root),
            "m1": {
                "root": str(self.m1_root),
                "qualification": str(m1_report),
                "qualification_sha256": sha256_file(m1_report),
                "formal_slots_reused": 2,
                "rerun": False,
            },
            "freeze": _freeze_snapshot(self.freeze),
            "tasks": self._task_manifest(),
            "retry": {
                "automatic_replacement_maximum": 1,
                "eligible_primary_failure_categories": sorted(
                    AUTO_REPLACEMENT_FAILURES
                ),
                "incomplete_or_unclassified_evidence": "block",
            },
        }
        write_json_atomic(self.manifest_path, manifest, mode=0o644)
        return manifest

    def _load_manifest(self) -> dict[str, Any]:
        manifest = read_json_object(self.manifest_path)
        if manifest.get("schema_version") != "toolathlon.m2-first-batch-manifest.v1":
            raise ContractError("unsupported M2 batch manifest")
        if manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("workers") != 1:
            raise ContractError("M2 batch identity or worker count mismatch")
        if manifest.get("tasks") != self._task_manifest():
            raise ContractError("M2 batch task/order manifest changed")
        if Path(str(manifest.get("source_root"))).resolve() != self.source_root:
            raise ContractError("M2 Toolathlon source root changed")
        if Path(str(manifest.get("m1", {}).get("root"))).resolve() != self.m1_root:
            raise ContractError("M2 M1 qualification root changed")
        if manifest.get("freeze") != _freeze_snapshot(self.freeze):
            raise ContractError("current freeze differs from the initialized M2 batch")
        m1_report = self.m1_root / "m1-live-qualification.json"
        _verify_single_file_manifest(
            self.m1_root / "m1-live-qualification.sha256", m1_report
        )
        if manifest.get("m1", {}).get("qualification_sha256") != sha256_file(m1_report):
            raise ContractError("M1 qualification changed after M2 initialization")
        return manifest

    def initialize(self) -> None:
        self._acquire_lock()
        self.manifest = (
            self._load_manifest() if self.manifest_path.exists() else self._create_manifest()
        )
        self.events = BatchEventLog(self.output_root / "scheduler-events.jsonl")
        checkpoint = (
            read_json_object(self.checkpoint_path) if self.checkpoint_path.exists() else {}
        )
        if checkpoint.get("status") != "GO":
            self.events.append(
                "batch.resume" if checkpoint else "batch.start",
                batch_id=self.manifest["batch_id"],
            )

    def _checkpoint(self, status: str, **fields: Any) -> None:
        assert self.events is not None
        write_json_atomic(
            self.checkpoint_path,
            {
                "schema_version": "toolathlon.m2-checkpoint.v1",
                "updated_at": utc_now(),
                "batch_id": self.manifest["batch_id"],
                "status": status,
                "scheduler_event_sequence": self.events.sequence,
                **fields,
            },
            mode=0o644,
        )

    def _write_batch_hash(self) -> None:
        required = [
            self.manifest_path,
            self.output_root / "scheduler-events.jsonl",
            self.checkpoint_path,
            self.report_path,
            self.report_hash_path,
        ]
        if not all(path.is_file() for path in required):
            raise ContractError("M2 batch-level evidence is incomplete")
        write_sha256_manifest(self.batch_hash_path, required, root=self.output_root)

    def _verify_batch_hash(self) -> None:
        try:
            lines = self.batch_hash_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ContractError(f"cannot read M2 batch checksum manifest: {exc}") from exc
        observed: dict[str, str] = {}
        for line in lines:
            digest, separator, relative = line.partition("  ")
            if not separator or len(digest) != 64 or relative in observed:
                raise ContractError("invalid M2 batch checksum manifest")
            observed[relative] = digest
        expected = {
            path.relative_to(self.output_root).as_posix(): sha256_file(path)
            for path in (
                self.manifest_path,
                self.output_root / "scheduler-events.jsonl",
                self.checkpoint_path,
                self.report_path,
                self.report_hash_path,
            )
        }
        if observed != expected:
            raise ContractError("M2 batch checksum manifest does not match evidence")

    def _attempt_identity(
        self, *, position: int, task_id: str, system: str, ordinal: int
    ) -> tuple[str, Path]:
        run_id = validate_id(
            "run_id",
            f"{self.manifest['batch_id']}-{position:02d}-{task_id}-{system}-a{ordinal}",
        )
        directory = self.output_root / "runs" / system / task_id / run_id
        return run_id, directory

    def _run_attempt(
        self,
        *,
        position: int,
        task_id: str,
        system: str,
        ordinal: int,
        replacement_for: str | None,
    ) -> None:
        assert self.events is not None
        run_id, directory = self._attempt_identity(
            position=position, task_id=task_id, system=system, ordinal=ordinal
        )
        if directory.exists():
            raise M2Blocked(f"attempt directory already exists but was not reusable: {directory}")
        argv = [
            sys.executable,
            "-m",
            "astra.runners.toolathlon_verified.lifecycle",
            "--system",
            system,
            "--task-id",
            task_id,
            "--experiment-id",
            EXPERIMENT_ID,
            "--run-id",
            run_id,
            "--output-dir",
            str(directory),
            "--toolathlon-source",
            str(self.source_root),
        ]
        if replacement_for is not None:
            argv.extend(["--replacement-for-run-id", replacement_for])
        self.events.append(
            "attempt.start",
            position=position,
            task_id=task_id,
            system=system,
            attempt_ordinal=ordinal,
            run_id=run_id,
            replacement_for_run_id=replacement_for,
        )
        try:
            exit_code = self.lifecycle_runner(argv)
        except BaseException as exc:
            self.events.append(
                "attempt.process_interrupted",
                position=position,
                task_id=task_id,
                system=system,
                attempt_ordinal=ordinal,
                run_id=run_id,
                error_type=type(exc).__name__,
            )
            raise
        else:
            self.events.append(
                "attempt.process_exit",
                position=position,
                task_id=task_id,
                system=system,
                attempt_ordinal=ordinal,
                run_id=run_id,
                exit_code=exit_code,
            )
        if not directory.is_dir():
            raise M2Blocked(f"lifecycle produced no attempt directory: {run_id}")
        try:
            attempt = load_attempt(directory, task_id=task_id, system=system)
        except ContractError as exc:
            raise M2Blocked(
                f"attempt evidence is incomplete or invalid; preserve and inspect {directory}: {exc}"
            ) from exc
        _validate_new_run_freeze(attempt, self.manifest)
        self.events.append(
            "attempt.artifact_gate_passed",
            position=position,
            task_id=task_id,
            system=system,
            attempt_ordinal=ordinal,
            run_id=run_id,
            run_validity=attempt.run["run_validity"],
            verify_status=attempt.run.get("verify_status"),
            process_exit_code=exit_code,
        )

    def _complete_slot(self, *, position: int, task_id: str, system: str) -> Attempt:
        assert self.events is not None
        while True:
            try:
                candidates = load_slot_candidates(
                    self.output_root, task_id=task_id, system=system
                )
            except ContractError as exc:
                raise M2Blocked(
                    f"slot evidence is incomplete or invalid for {system}/{task_id}: {exc}"
                ) from exc
            for attempt in candidates:
                _validate_new_run_freeze(attempt, self.manifest)
            decision = decide_slot(candidates)
            if decision.state == "complete":
                assert decision.effective is not None
                validate_formal_effective(decision.effective)
                self.events.append(
                    "slot.complete",
                    position=position,
                    task_id=task_id,
                    system=system,
                    effective_run_id=decision.effective.run["run_id"],
                    candidate_count=len(candidates),
                )
                return decision.effective
            if decision.state == "blocked":
                raise M2Blocked(f"{system}/{task_id}: {decision.reason}")
            if decision.state == "needs_original":
                self._run_attempt(
                    position=position,
                    task_id=task_id,
                    system=system,
                    ordinal=1,
                    replacement_for=None,
                )
                continue
            if decision.state == "needs_replacement":
                assert decision.original is not None
                self.events.append(
                    "slot.replacement_authorized",
                    position=position,
                    task_id=task_id,
                    system=system,
                    original_run_id=decision.original.run["run_id"],
                    primary_failure_category=decision.original.run.get(
                        "primary_failure_category"
                    ),
                )
                self._run_attempt(
                    position=position,
                    task_id=task_id,
                    system=system,
                    ordinal=2,
                    replacement_for=str(decision.original.run["run_id"]),
                )
                continue
            raise AssertionError(f"unknown slot decision: {decision.state}")

    def _validate_m1_reuse(self) -> tuple[dict[str, Attempt], list[Attempt]]:
        report_path = self.m1_root / "m1-live-qualification.json"
        report = read_json_object(report_path)
        if report.get("status") != "GO" or report.get("task_id") != M1_TASK:
            raise ContractError("M1 qualification is not GO for find-alita-paper")
        reuse = report.get("formal_reuse")
        if not isinstance(reuse, dict) or reuse.get("counted_in_first_14_task_batch") is not True:
            raise ContractError("M1 report does not authorize formal M2 reuse")
        selected: dict[str, Attempt] = {}
        all_candidates: list[Attempt] = []
        for system in SYSTEMS:
            task_root = self.m1_root / system / M1_TASK
            if not task_root.is_dir():
                raise ContractError(f"M1 task root is missing: {task_root}")
            candidates = [
                load_attempt(path, task_id=M1_TASK, system=system)
                for path in sorted(item for item in task_root.iterdir() if item.is_dir())
            ]
            if not 1 <= len(candidates) <= 2:
                raise ContractError("M1 must have one original and at most one replacement")
            decision = decide_slot(candidates)
            if decision.state != "complete" or decision.effective is None:
                raise ContractError(f"M1 effective slot is unavailable for {system}")
            validate_m1_effective(decision.effective)
            reported = report.get("systems", {}).get(system, {})
            effective_path = ensure_descendant(
                Path(str(reported.get("effective_run_directory"))),
                self.m1_root,
                "M1 effective run directory",
            )
            if effective_path != decision.effective.directory.resolve():
                raise ContractError("M1 effective directory differs from qualification report")
            if reported.get("effective_run_id") != decision.effective.run.get("run_id"):
                raise ContractError("M1 effective run ID differs from qualification report")
            if reported.get("artifacts_sha256") != sha256_file(
                decision.effective.directory / "artifacts.sha256"
            ):
                raise ContractError("M1 run artifact hash differs from qualification report")
            selected[system] = decision.effective
            all_candidates.extend(candidates)
        validate_pair(selected["astra"], selected["hermes"])
        return selected, all_candidates

    def _validate_schedule_events(self) -> None:
        rows = read_jsonl(self.output_root / "scheduler-events.jsonl", allow_empty=False)
        expected_slots = [
            (position, task_id, system)
            for position, (task_id, order) in enumerate(FIRST_BATCH[1:], start=2)
            for system in order
        ]
        observed_originals: list[tuple[int, str, str]] = []
        active: tuple[str, int] | None = None
        seen_attempts: set[tuple[str, int]] = set()
        for row in rows:
            event = row.get("event")
            if event == "attempt.start":
                run_id = row.get("run_id")
                ordinal = row.get("attempt_ordinal")
                if not isinstance(run_id, str) or ordinal not in {1, 2}:
                    raise ContractError("M2 scheduler has an invalid attempt.start event")
                key = (run_id, ordinal)
                if key in seen_attempts:
                    raise ContractError("M2 scheduler started the same attempt twice")
                if active is not None:
                    raise ContractError("M2 scheduler overlapped two attempts")
                seen_attempts.add(key)
                active = key
                if ordinal == 1:
                    observed_originals.append(
                        (int(row.get("position")), str(row.get("task_id")), str(row.get("system")))
                    )
                elif not observed_originals or observed_originals[-1] != (
                    int(row.get("position")),
                    str(row.get("task_id")),
                    str(row.get("system")),
                ):
                    raise ContractError("M2 replacement was not adjacent to its original slot")
            elif event in {"attempt.process_exit", "attempt.process_interrupted"}:
                key = (str(row.get("run_id")), int(row.get("attempt_ordinal")))
                if active != key:
                    raise ContractError("M2 process terminal event does not match the active attempt")
                active = None
        if active is not None:
            raise ContractError("M2 scheduler has an attempt with no process-exit event")
        if observed_originals != expected_slots:
            raise ContractError("M2 original attempts were not run in the frozen serial order")

    def validate_complete(self, *, write_report: bool) -> dict[str, Any]:
        if not self.manifest:
            self.manifest = self._load_manifest()
        self._validate_schedule_events()
        m1_selected, candidates = self._validate_m1_reuse()
        effective: dict[tuple[str, str], Attempt] = {
            (M1_TASK, system): attempt for system, attempt in m1_selected.items()
        }
        task_rows: list[dict[str, Any]] = [
            {
                "position": 1,
                "task_id": M1_TASK,
                "source": "m1_reuse",
                "system_order": list(FIRST_BATCH[0][1]),
                "systems": {
                    system: {
                        "effective_run_id": m1_selected[system].run["run_id"],
                        "effective_run_directory": str(m1_selected[system].directory),
                        "candidate_count": sum(
                            1
                            for item in candidates
                            if item.run.get("system_id") == system
                        ),
                        "verify_status": m1_selected[system].run.get("verify_status"),
                    }
                    for system in SYSTEMS
                },
            }
        ]
        expected_new_tasks = {task for task, _order in FIRST_BATCH[1:]}
        runs_root = self.output_root / "runs"
        if runs_root.exists():
            for system_root in runs_root.iterdir():
                if not system_root.is_dir() or system_root.name not in SYSTEMS:
                    raise ContractError(f"unexpected M2 runs entry: {system_root}")
                observed_tasks = {item.name for item in system_root.iterdir() if item.is_dir()}
                if not observed_tasks.issubset(expected_new_tasks):
                    raise ContractError(
                        f"unexpected task directories for {system_root.name}: "
                        f"{sorted(observed_tasks - expected_new_tasks)}"
                    )
        for position, (task_id, order) in enumerate(FIRST_BATCH[1:], start=2):
            selected: dict[str, Attempt] = {}
            system_rows: dict[str, Any] = {}
            for system in SYSTEMS:
                slot_candidates = load_slot_candidates(
                    self.output_root, task_id=task_id, system=system
                )
                decision = decide_slot(slot_candidates)
                if decision.state != "complete" or decision.effective is None:
                    raise ContractError(f"M2 slot is incomplete: {system}/{task_id}")
                for attempt in slot_candidates:
                    _validate_new_run_freeze(attempt, self.manifest)
                validate_formal_effective(decision.effective)
                selected[system] = decision.effective
                effective[(task_id, system)] = decision.effective
                candidates.extend(slot_candidates)
                system_rows[system] = {
                    "effective_run_id": decision.effective.run["run_id"],
                    "effective_run_directory": str(decision.effective.directory),
                    "candidate_count": len(slot_candidates),
                    "verify_status": decision.effective.run.get("verify_status"),
                    "terminal_status": decision.effective.run.get("terminal_status"),
                    "candidates": [_candidate_record(item) for item in slot_candidates],
                }
            validate_pair(selected["astra"], selected["hermes"])
            task_rows.append(
                {
                    "position": position,
                    "task_id": task_id,
                    "source": "m2_run",
                    "system_order": list(order),
                    "systems": system_rows,
                }
            )
        identity_ids: set[str] = set()
        fingerprints: set[str] = set()
        for attempt in candidates:
            identity_id, fingerprint = _identity_key(attempt)
            if identity_id in identity_ids or fingerprint in fingerprints:
                raise ContractError("an attempt product identity was reused across M2")
            identity_ids.add(identity_id)
            fingerprints.add(fingerprint)
        if len(effective) != 28:
            raise ContractError(f"M2 effective slot count is not 28: {len(effective)}")
        report = {
            "schema_version": "toolathlon.m2-first-batch-qualification.v1",
            "created_at": utc_now(),
            "status": "GO",
            "batch_id": self.manifest["batch_id"],
            "experiment_id": EXPERIMENT_ID,
            "manifest": {
                "path": str(self.manifest_path),
                "sha256": sha256_file(self.manifest_path),
            },
            "m1_qualification_sha256": self.manifest["m1"][
                "qualification_sha256"
            ],
            "task_count": 14,
            "effective_slot_count": 28,
            "new_effective_slot_count": 26,
            "candidate_attempt_count": len(candidates),
            "automatic_replacement_count": len(candidates) - 28,
            "workers": 1,
            "tasks": task_rows,
        }
        if write_report:
            write_json_atomic(self.report_path, report, mode=0o644)
            self.report_hash_path.write_text(
                f"{sha256_file(self.report_path)}  {self.report_path.name}\n",
                encoding="utf-8",
            )
        return report

    def run(self) -> dict[str, Any]:
        try:
            self.initialize()
            assert self.events is not None
            checkpoint = (
                read_json_object(self.checkpoint_path)
                if self.checkpoint_path.exists()
                else {}
            )
            if checkpoint.get("status") == "GO":
                self._verify_batch_hash()
                self.validate_complete(write_report=False)
                existing = read_json_object(self.report_path)
                if (
                    existing.get("status") != "GO"
                    or existing.get("batch_id") != self.manifest["batch_id"]
                    or existing.get("effective_slot_count") != 28
                ):
                    raise ContractError("existing M2 qualification report is inconsistent")
                return existing
            self._validate_m1_reuse()
            self.events.append("m1.reuse_validated", task_id=M1_TASK, effective_slots=2)
            completed_slots = 2
            for position, (task_id, order) in enumerate(FIRST_BATCH[1:], start=2):
                selected: dict[str, Attempt] = {}
                for system in order:
                    self._checkpoint(
                        "running",
                        next_position=position,
                        next_task_id=task_id,
                        next_system=system,
                        completed_effective_slots=completed_slots,
                    )
                    selected[system] = self._complete_slot(
                        position=position, task_id=task_id, system=system
                    )
                    completed_slots += 1
                validate_pair(selected["astra"], selected["hermes"])
                self.events.append(
                    "task.pair_gate_passed",
                    position=position,
                    task_id=task_id,
                    first_system=order[0],
                    second_system=order[1],
                )
            report = self.validate_complete(write_report=True)
            self.events.append(
                "batch.complete",
                effective_slot_count=report["effective_slot_count"],
                candidate_attempt_count=report["candidate_attempt_count"],
            )
            self._checkpoint(
                "GO",
                completed_effective_slots=28,
                qualification_report=str(self.report_path),
                qualification_sha256=sha256_file(self.report_path),
            )
            self._write_batch_hash()
            return report
        except BaseException as exc:
            if self.events is not None:
                self.events.append("batch.blocked", error_type=type(exc).__name__, error=str(exc))
                self._checkpoint("blocked", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            self._release_lock()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or validate Toolathlon M2 first batch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "validate"):
        command = subparsers.add_parser(name)
        command.add_argument("--output-root", type=Path, required=True)
        command.add_argument("--m1-root", type=Path, required=True)
        command.add_argument(
            "--source-root",
            type=Path,
            default=Path("/home/vagrant/dataset/Toolathlon"),
        )
        command.add_argument(
            "--repo-root", type=Path, default=Path("/home/vagrant/moi-benchmark")
        )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    batch = M2Batch(
        repo_root=args.repo_root,
        output_root=args.output_root,
        m1_root=args.m1_root,
        source_root=args.source_root,
    )
    if args.command == "run":
        report = batch.run()
    else:
        batch._acquire_lock()
        try:
            batch.manifest = batch._load_manifest()
            batch.events = BatchEventLog(batch.output_root / "scheduler-events.jsonl")
            report = batch.validate_complete(write_report=True)
            batch._checkpoint(
                "GO",
                completed_effective_slots=28,
                qualification_report=str(batch.report_path),
                qualification_sha256=sha256_file(batch.report_path),
            )
            batch._write_batch_hash()
        finally:
            batch._release_lock()
    print(
        json.dumps(
            {
                "status": report["status"],
                "task_count": report["task_count"],
                "effective_slot_count": report["effective_slot_count"],
                "report": str(batch.report_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
