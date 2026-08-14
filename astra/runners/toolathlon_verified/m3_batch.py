from __future__ import annotations

import argparse
import fcntl
import json
import time
from pathlib import Path
from typing import Any, Callable

from .artifact_contract import read_jsonl
from .contract import (
    ContractError,
    read_json_object,
    sha256_file,
    utc_now,
    validate_id,
    write_json_atomic,
    write_sha256_manifest,
)
from .m2_batch import (
    AUTO_REPLACEMENT_FAILURES,
    EXPERIMENT_ID,
    FIRST_BATCH,
    SYSTEMS,
    Attempt,
    BatchEventLog,
    M2Batch,
    M2Blocked,
    _candidate_record,
    _freeze_snapshot,
    _identity_key,
    _safe_root,
    _validate_new_run_freeze,
    _verify_single_file_manifest,
    decide_slot,
    load_slot_candidates,
    validate_formal_effective,
    validate_pair,
)


M3_TASK_COUNT = 94
M3_EFFECTIVE_SLOT_COUNT = M3_TASK_COUNT * len(SYSTEMS)


def frozen_remaining_schedule(
    freeze: Path,
) -> tuple[tuple[str, tuple[str, str]], ...]:
    requirements = read_json_object(freeze / "task-requirements.json")
    tasks = requirements.get("tasks")
    if not isinstance(tasks, dict) or len(tasks) != 108:
        raise ContractError("the frozen formal task set is not exactly 108 tasks")
    first_batch = {task_id for task_id, _order in FIRST_BATCH}
    remaining = sorted(set(tasks) - first_batch)
    if len(remaining) != M3_TASK_COUNT:
        raise ContractError("the frozen remaining task set is not exactly 94 tasks")
    schedule = tuple(
        (
            task_id,
            ("astra", "hermes")
            if remaining_position % 2 == 1
            else ("hermes", "astra"),
        )
        for remaining_position, task_id in enumerate(remaining, start=1)
    )
    protocol = read_json_object(freeze / "execution-protocol.freeze.json")
    phase = protocol.get("formal_phases", {}).get("remaining_batch", {})
    if phase.get("tasks") != remaining:
        raise ContractError("M3 task order differs from execution-protocol.freeze.json")
    if phase.get("system_order_rule") != "alternate_by_remaining_position_astra_first":
        raise ContractError("M3 system-order rule differs from the freeze")
    if phase.get("workers") != 1 or protocol.get("scope", {}).get("workers") != 1:
        raise ContractError("M3 requires frozen workers=1")
    if protocol.get("retry", {}).get("automatic_replacement_maximum") != 1:
        raise ContractError("M3 requires exactly one allowed infrastructure replacement")
    return schedule


class M3Batch(M2Batch):
    """Serial remaining-94 scheduler reusing the frozen single-task lifecycle."""

    def __init__(
        self,
        *,
        repo_root: Path,
        output_root: Path,
        m2_root: Path,
        source_root: Path,
        lifecycle_runner: Callable[[list[str]], int] | None = None,
    ) -> None:
        self.m2_root = _safe_root(m2_root, "m2_root")
        super().__init__(
            repo_root=repo_root,
            output_root=output_root,
            m1_root=self.m2_root,
            source_root=source_root,
            lifecycle_runner=lifecycle_runner,
        )
        self.manifest_path = self.output_root / "m3-batch-manifest.json"
        self.checkpoint_path = self.output_root / "checkpoint.json"
        self.report_path = self.output_root / "m3-remaining-batch-qualification.json"
        self.report_hash_path = self.output_root / "m3-remaining-batch-qualification.sha256"
        self.batch_hash_path = self.output_root / "m3-batch-artifacts.sha256"
        self.schedule = frozen_remaining_schedule(self.freeze)
        self.prior_identity_ids: set[str] = set()
        self.prior_identity_fingerprints: set[str] = set()

    def _acquire_lock(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.output_root / ".m3.lock"
        self._lock_stream = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise M2Blocked("another M3 scheduler process holds the batch lock") from exc

    def _task_manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "formal_position": formal_position,
                "remaining_position": remaining_position,
                "task_id": task_id,
                "system_order": list(order),
                "source": "m3_run",
            }
            for remaining_position, (task_id, order) in enumerate(
                self.schedule, start=1
            )
            for formal_position in [len(FIRST_BATCH) + remaining_position]
        ]

    def _validate_m2_qualification(self) -> dict[str, Any]:
        m2_manifest_path = self.m2_root / "m2-batch-manifest.json"
        m2_manifest = read_json_object(m2_manifest_path)
        m1_root = Path(str(m2_manifest.get("m1", {}).get("root", ""))).resolve()
        validator = M2Batch(
            repo_root=self.repo_root,
            output_root=self.m2_root,
            m1_root=m1_root,
            source_root=self.source_root,
        )
        validator.manifest = validator._load_manifest()
        validator.events = BatchEventLog(self.m2_root / "scheduler-events.jsonl")
        validator._verify_batch_hash()
        computed = validator.validate_complete(write_report=False)
        report = read_json_object(validator.report_path)
        _verify_single_file_manifest(validator.report_hash_path, validator.report_path)
        if (
            computed.get("status") != "GO"
            or report.get("status") != "GO"
            or report.get("batch_id") != computed.get("batch_id")
            or report.get("effective_slot_count") != 28
            or report.get("task_count") != 14
        ):
            raise ContractError("M2 qualification is not a complete 14-task GO result")
        identity_ids: set[str] = set()
        identity_fingerprints: set[str] = set()
        _selected, candidates = validator._validate_m1_reuse()
        for task_id, _order in FIRST_BATCH[1:]:
            for system in SYSTEMS:
                candidates.extend(
                    load_slot_candidates(
                        self.m2_root, task_id=task_id, system=system
                    )
                )
        for attempt in candidates:
            identity_id, fingerprint = _identity_key(attempt)
            if identity_id in identity_ids or fingerprint in identity_fingerprints:
                raise ContractError("an attempt product identity was reused before M3")
            identity_ids.add(identity_id)
            identity_fingerprints.add(fingerprint)
        self.prior_identity_ids = identity_ids
        self.prior_identity_fingerprints = identity_fingerprints
        return report

    def _create_manifest(self) -> dict[str, Any]:
        m2_report = self._validate_m2_qualification()
        if any(path.name != ".m3.lock" for path in self.output_root.iterdir()):
            raise ContractError(
                "new M3 output root must be empty except for the scheduler lock"
            )
        batch_id = validate_id(
            "batch_id", f"m3-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
        )
        manifest = {
            "schema_version": "toolathlon.m3-remaining-batch-manifest.v1",
            "created_at": utc_now(),
            "batch_id": batch_id,
            "experiment_id": EXPERIMENT_ID,
            "workers": 1,
            "source_root": str(self.source_root),
            "m2": {
                "root": str(self.m2_root),
                "qualification": str(
                    self.m2_root / "m2-first-batch-qualification.json"
                ),
                "qualification_sha256": sha256_file(
                    self.m2_root / "m2-first-batch-qualification.json"
                ),
                "batch_id": m2_report["batch_id"],
                "effective_slots_completed": 28,
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
        if manifest.get("schema_version") != "toolathlon.m3-remaining-batch-manifest.v1":
            raise ContractError("unsupported M3 batch manifest")
        if manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("workers") != 1:
            raise ContractError("M3 batch identity or worker count mismatch")
        if manifest.get("tasks") != self._task_manifest():
            raise ContractError("M3 batch task/order manifest changed")
        if Path(str(manifest.get("source_root"))).resolve() != self.source_root:
            raise ContractError("M3 Toolathlon source root changed")
        if Path(str(manifest.get("m2", {}).get("root"))).resolve() != self.m2_root:
            raise ContractError("M3 M2 qualification root changed")
        if manifest.get("freeze") != _freeze_snapshot(self.freeze):
            raise ContractError("current freeze differs from the initialized M3 batch")
        m2_report = self._validate_m2_qualification()
        if manifest.get("m2", {}).get("qualification_sha256") != sha256_file(
            self.m2_root / "m2-first-batch-qualification.json"
        ) or manifest.get("m2", {}).get("batch_id") != m2_report.get("batch_id"):
            raise ContractError("M2 qualification changed after M3 initialization")
        return manifest

    def initialize(self) -> None:
        self._acquire_lock()
        self.manifest = (
            self._load_manifest() if self.manifest_path.exists() else self._create_manifest()
        )
        self.events = BatchEventLog(
            self.output_root / "scheduler-events.jsonl",
            schema_version="toolathlon.m3-scheduler-events.v1",
            phase="M3",
        )
        checkpoint = (
            read_json_object(self.checkpoint_path)
            if self.checkpoint_path.exists()
            else {}
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
                "schema_version": "toolathlon.m3-checkpoint.v1",
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
            raise ContractError("M3 batch-level evidence is incomplete")
        write_sha256_manifest(self.batch_hash_path, required, root=self.output_root)

    def _verify_batch_hash(self) -> None:
        try:
            lines = self.batch_hash_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ContractError(f"cannot read M3 batch checksum manifest: {exc}") from exc
        observed: dict[str, str] = {}
        for line in lines:
            digest, separator, relative = line.partition("  ")
            if not separator or len(digest) != 64 or relative in observed:
                raise ContractError("invalid M3 batch checksum manifest")
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
            raise ContractError("M3 batch checksum manifest does not match evidence")

    def _validate_schedule_events(self) -> None:
        rows = read_jsonl(self.output_root / "scheduler-events.jsonl", allow_empty=False)
        expected_slots = [
            (formal_position, task_id, system)
            for remaining_position, (task_id, order) in enumerate(
                self.schedule, start=1
            )
            for formal_position in [len(FIRST_BATCH) + remaining_position]
            for system in order
        ]
        observed_originals: list[tuple[int, str, str]] = []
        active: tuple[str, int] | None = None
        seen_attempts: set[tuple[str, int]] = set()
        for row in rows:
            if row.get("schema_version") != "toolathlon.m3-scheduler-events.v1":
                raise ContractError("M3 scheduler event schema changed")
            event = row.get("event")
            if event == "attempt.start":
                run_id = row.get("run_id")
                ordinal = row.get("attempt_ordinal")
                if not isinstance(run_id, str) or ordinal not in {1, 2}:
                    raise ContractError("M3 scheduler has an invalid attempt.start event")
                key = (run_id, ordinal)
                if key in seen_attempts:
                    raise ContractError("M3 scheduler started the same attempt twice")
                if active is not None:
                    raise ContractError("M3 scheduler overlapped two attempts")
                seen_attempts.add(key)
                active = key
                slot = (
                    int(row.get("position")),
                    str(row.get("task_id")),
                    str(row.get("system")),
                )
                if ordinal == 1:
                    observed_originals.append(slot)
                elif not observed_originals or observed_originals[-1] != slot:
                    raise ContractError("M3 replacement was not adjacent to its original slot")
            elif event in {"attempt.process_exit", "attempt.process_interrupted"}:
                key = (str(row.get("run_id")), int(row.get("attempt_ordinal")))
                if active != key:
                    raise ContractError(
                        "M3 process terminal event does not match the active attempt"
                    )
                active = None
        if active is not None:
            raise ContractError("M3 scheduler has an attempt with no process-exit event")
        if observed_originals != expected_slots:
            raise ContractError("M3 original attempts were not run in frozen serial order")

    def validate_complete(self, *, write_report: bool) -> dict[str, Any]:
        if not self.manifest:
            self.manifest = self._load_manifest()
        self._validate_schedule_events()
        self._validate_m2_qualification()
        expected_tasks = {task_id for task_id, _order in self.schedule}
        runs_root = self.output_root / "runs"
        if runs_root.exists():
            for system_root in runs_root.iterdir():
                if not system_root.is_dir() or system_root.name not in SYSTEMS:
                    raise ContractError(f"unexpected M3 runs entry: {system_root}")
                observed_tasks = {
                    item.name for item in system_root.iterdir() if item.is_dir()
                }
                if not observed_tasks.issubset(expected_tasks):
                    raise ContractError(
                        f"unexpected task directories for {system_root.name}: "
                        f"{sorted(observed_tasks - expected_tasks)}"
                    )
        candidates: list[Attempt] = []
        task_rows: list[dict[str, Any]] = []
        effective_slots = 0
        for remaining_position, (task_id, order) in enumerate(
            self.schedule, start=1
        ):
            formal_position = len(FIRST_BATCH) + remaining_position
            selected: dict[str, Attempt] = {}
            system_rows: dict[str, Any] = {}
            for system in SYSTEMS:
                slot_candidates = load_slot_candidates(
                    self.output_root, task_id=task_id, system=system
                )
                decision = decide_slot(slot_candidates)
                if decision.state != "complete" or decision.effective is None:
                    raise ContractError(f"M3 slot is incomplete: {system}/{task_id}")
                for attempt in slot_candidates:
                    _validate_new_run_freeze(attempt, self.manifest)
                validate_formal_effective(decision.effective)
                selected[system] = decision.effective
                candidates.extend(slot_candidates)
                effective_slots += 1
                system_rows[system] = {
                    "effective_run_id": decision.effective.run["run_id"],
                    "effective_run_directory": str(decision.effective.directory),
                    "candidate_count": len(slot_candidates),
                    "verify_status": decision.effective.run.get("verify_status"),
                    "terminal_status": decision.effective.run.get("terminal_status"),
                    "candidates": [
                        _candidate_record(item) for item in slot_candidates
                    ],
                }
            validate_pair(selected["astra"], selected["hermes"])
            task_rows.append(
                {
                    "formal_position": formal_position,
                    "remaining_position": remaining_position,
                    "task_id": task_id,
                    "source": "m3_run",
                    "system_order": list(order),
                    "systems": system_rows,
                }
            )
        identity_ids = set(self.prior_identity_ids)
        identity_fingerprints = set(self.prior_identity_fingerprints)
        for attempt in candidates:
            identity_id, fingerprint = _identity_key(attempt)
            if identity_id in identity_ids or fingerprint in identity_fingerprints:
                raise ContractError("an attempt product identity was reused across M2/M3")
            identity_ids.add(identity_id)
            identity_fingerprints.add(fingerprint)
        if effective_slots != M3_EFFECTIVE_SLOT_COUNT:
            raise ContractError(
                f"M3 effective slot count is not {M3_EFFECTIVE_SLOT_COUNT}: "
                f"{effective_slots}"
            )
        report = {
            "schema_version": "toolathlon.m3-remaining-batch-qualification.v1",
            "created_at": utc_now(),
            "status": "GO",
            "batch_id": self.manifest["batch_id"],
            "experiment_id": EXPERIMENT_ID,
            "manifest": {
                "path": str(self.manifest_path),
                "sha256": sha256_file(self.manifest_path),
            },
            "m2_qualification_sha256": self.manifest["m2"][
                "qualification_sha256"
            ],
            "task_count": M3_TASK_COUNT,
            "effective_slot_count": M3_EFFECTIVE_SLOT_COUNT,
            "cumulative_task_count": 108,
            "cumulative_effective_slot_count": 216,
            "candidate_attempt_count": len(candidates),
            "automatic_replacement_count": len(candidates)
            - M3_EFFECTIVE_SLOT_COUNT,
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
                    or existing.get("effective_slot_count")
                    != M3_EFFECTIVE_SLOT_COUNT
                ):
                    raise ContractError("existing M3 qualification report is inconsistent")
                return existing
            self.events.append(
                "m2.qualification_validated",
                m2_batch_id=self.manifest["m2"]["batch_id"],
                effective_slots=28,
            )
            completed_slots = 0
            for remaining_position, (task_id, order) in enumerate(
                self.schedule, start=1
            ):
                formal_position = len(FIRST_BATCH) + remaining_position
                selected: dict[str, Attempt] = {}
                for system in order:
                    self._checkpoint(
                        "running",
                        next_formal_position=formal_position,
                        next_remaining_position=remaining_position,
                        next_task_id=task_id,
                        next_system=system,
                        completed_effective_slots=completed_slots,
                    )
                    selected[system] = self._complete_slot(
                        position=formal_position,
                        task_id=task_id,
                        system=system,
                    )
                    completed_slots += 1
                validate_pair(selected["astra"], selected["hermes"])
                self.events.append(
                    "task.pair_gate_passed",
                    position=formal_position,
                    remaining_position=remaining_position,
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
                completed_effective_slots=M3_EFFECTIVE_SLOT_COUNT,
                qualification_report=str(self.report_path),
                qualification_sha256=sha256_file(self.report_path),
            )
            self._write_batch_hash()
            return report
        except BaseException as exc:
            if self.events is not None:
                self.events.append(
                    "batch.blocked", error_type=type(exc).__name__, error=str(exc)
                )
                self._checkpoint(
                    "blocked", error_type=type(exc).__name__, error=str(exc)
                )
            raise
        finally:
            self._release_lock()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or validate Toolathlon M3 remaining batch"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "validate"):
        command = subparsers.add_parser(name)
        command.add_argument("--output-root", type=Path, required=True)
        command.add_argument("--m2-root", type=Path, required=True)
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
    batch = M3Batch(
        repo_root=args.repo_root,
        output_root=args.output_root,
        m2_root=args.m2_root,
        source_root=args.source_root,
    )
    if args.command == "run":
        report = batch.run()
    else:
        batch._acquire_lock()
        try:
            batch.manifest = batch._load_manifest()
            batch.events = BatchEventLog(
                batch.output_root / "scheduler-events.jsonl",
                schema_version="toolathlon.m3-scheduler-events.v1",
                phase="M3",
            )
            report = batch.validate_complete(write_report=True)
            batch._checkpoint(
                "GO",
                completed_effective_slots=M3_EFFECTIVE_SLOT_COUNT,
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
