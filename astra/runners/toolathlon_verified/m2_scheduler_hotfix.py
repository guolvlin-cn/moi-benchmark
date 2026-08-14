from __future__ import annotations

import argparse
import copy
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from . import m2_batch
from .artifact_contract import read_jsonl
from .contract import (
    ContractError,
    canonical_json_sha256,
    read_json_object,
    sha256_file,
    utc_now,
    write_json_atomic,
    write_sha256_manifest,
)


POLICY = "toolathlon.paired-tools-list.normalize-unordered-terminal-commands.v1"
SCHEMA_VERSION = "toolathlon.m2-scheduler-hotfix.v1"
FROZEN_M2_BATCH_SHA256 = (
    "ba441e1be270ce912f32d4d3e2a4d131edeab5053bf7d5f0175de21fe4a97c41"
)
FAILED_TASK_POSITION = 5
FAILED_TASK_ID = "arrange-workspace"
FAILED_SYSTEM = "astra"


def _normalized_tool_set_sha256(manifest: dict[str, Any]) -> str:
    rows = manifest.get("tools")
    if not isinstance(rows, list):
        raise ContractError("runtime tools/list manifest has no tools array")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("raw"), dict):
            raise ContractError("runtime tools/list manifest has no raw tool Schema")
        tool = copy.deepcopy(row["raw"])
        description = tool.get("description")
        if not isinstance(description, str):
            raise ContractError("runtime tools/list tool description is not a string")
        lines: list[str] = []
        for line in description.split("\n"):
            prefix = "Available commands:"
            if line.startswith(prefix):
                commands = [item.strip() for item in line[len(prefix) :].split(",")]
                if not commands or any(not item for item in commands):
                    raise ContractError("invalid terminal Available commands description")
                line = f"{prefix} {', '.join(sorted(commands))}"
            lines.append(line)
        tool["description"] = "\n".join(lines)
        normalized.append(tool)
    normalized.sort(key=lambda item: str(item.get("name", "")))
    return canonical_json_sha256(normalized)


class HotfixEventLog:
    def __init__(self, path: Path, *, schema_version: str = SCHEMA_VERSION) -> None:
        self.path = path
        self.schema_version = schema_version
        rows = read_jsonl(path, allow_empty=True) if path.exists() else []
        if any(row.get("schema_version") != schema_version for row in rows):
            raise ContractError("scheduler hotfix event schema changed")
        sequences = [row.get("sequence") for row in rows]
        if sequences != list(range(1, len(rows) + 1)):
            raise ContractError("scheduler hotfix event sequence is not contiguous")
        self.sequence = len(rows)
        self.recorded_pairs = {
            (
                row.get("task_id"),
                row.get("astra_run_id"),
                row.get("hermes_run_id"),
            )
            for row in rows
            if row.get("event") == "pair_schema.compared"
        }

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


def _pair_validator(
    output_root: Path, event_log: HotfixEventLog
) -> Callable[[m2_batch.Attempt, m2_batch.Attempt], None]:
    original = m2_batch.validate_pair

    def validate(astra: m2_batch.Attempt, hermes: m2_batch.Attempt) -> None:
        raw_exact = True
        try:
            original(astra, hermes)
        except ContractError as exc:
            if str(exc) != "paired runtime tools/list Schema differs":
                raise
            raw_exact = False

        astra_manifest = read_json_object(
            astra.directory / "tool-schema-observed.json"
        )
        hermes_manifest = read_json_object(
            hermes.directory / "tool-schema-observed.json"
        )
        astra_normalized = _normalized_tool_set_sha256(astra_manifest)
        hermes_normalized = _normalized_tool_set_sha256(hermes_manifest)
        if astra_normalized != hermes_normalized:
            raise ContractError("paired runtime tools/list Schema differs")

        key = (
            str(astra.run.get("task_id")),
            str(astra.run.get("run_id")),
            str(hermes.run.get("run_id")),
        )
        if key not in event_log.recorded_pairs:
            event_log.append(
                "pair_schema.compared",
                policy=POLICY,
                comparison="raw_exact" if raw_exact else "normalized_equivalent",
                task_id=key[0],
                astra_run_id=key[1],
                hermes_run_id=key[2],
                astra_raw_tool_set_sha256=astra_manifest.get("tool_set_sha256"),
                hermes_raw_tool_set_sha256=hermes_manifest.get("tool_set_sha256"),
                normalized_tool_set_sha256=astra_normalized,
                hotfix_source_sha256=sha256_file(Path(__file__)),
                output_root=str(output_root),
            )
            event_log.recorded_pairs.add(key)

    return validate


def _scheduler_incident(
    output_root: Path,
) -> tuple[set[int], Path | None]:
    manifest = read_json_object(output_root / "m2-batch-manifest.json")
    batch_id = manifest.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise ContractError("M2 batch ID is missing")
    run_id = (
        f"{batch_id}-{FAILED_TASK_POSITION:02d}-{FAILED_TASK_ID}-"
        f"{FAILED_SYSTEM}-a1"
    )
    source = output_root / "runs" / FAILED_SYSTEM / FAILED_TASK_ID / run_id
    recovery_root = output_root / "recovery-evidence" / "freeze-source-mismatch"
    destination = recovery_root / run_id
    record_path = recovery_root / "recovery.json"

    if record_path.exists():
        existing = read_json_object(record_path)
        if (
            existing.get("run_id") != run_id
            or existing.get("classification")
            != "scheduler_preflight_incident_not_formal_attempt"
            or not destination.is_dir()
        ):
            raise ContractError("existing scheduler recovery record is invalid")
        sequences = existing.get("retired_scheduler_event_sequences")
        if (
            not isinstance(sequences, list)
            or not sequences
            or any(not isinstance(item, int) for item in sequences)
        ):
            raise ContractError("existing scheduler recovery sequences are invalid")
        return set(sequences), record_path

    scheduler_rows = read_jsonl(
        output_root / "scheduler-events.jsonl", allow_empty=False
    )
    attempt_rows = [
        row
        for row in scheduler_rows
        if row.get("run_id") == run_id
        and row.get("event") in {"attempt.start", "attempt.process_exit"}
    ]
    if not attempt_rows:
        if source.exists() or destination.exists() or record_path.exists():
            raise ContractError("recovery evidence exists without scheduler incident")
        return set(), None
    if len(attempt_rows) != 2 or [row.get("event") for row in attempt_rows] != [
        "attempt.start",
        "attempt.process_exit",
    ]:
        raise ContractError("unexpected scheduler incident shape")
    if attempt_rows[1].get("exit_code") == 0:
        raise ContractError("refusing to retire a successful attempt process")
    if any(
        row.get("event") == "attempt.artifact_gate_passed"
        and row.get("run_id") == run_id
        for row in scheduler_rows
    ):
        raise ContractError("refusing to retire an artifact-qualified attempt")
    retired_sequences = {int(row["sequence"]) for row in attempt_rows}

    if source.exists() and destination.exists():
        raise ContractError("both active and recovered incident directories exist")
    incident_directory = source if source.exists() else destination
    if not incident_directory.is_dir():
        raise ContractError("scheduler incident directory is missing")
    required_formal = {
        "resolved-config.json",
        "adapter-events.jsonl",
        "trajectory.jsonl",
        "tool-calls.jsonl",
        "model-usage.jsonl",
        "run.json",
        "artifacts.sha256",
    }
    if any((incident_directory / name).exists() for name in required_formal):
        raise ContractError("refusing to retire an attempt containing formal artifacts")
    lifecycle_path = incident_directory / "lifecycle-events.jsonl"
    lifecycle_rows = read_jsonl(lifecycle_path, allow_empty=False)
    lifecycle_events = [str(row.get("event")) for row in lifecycle_rows]
    if any(
        event.startswith("tools_list")
        or event.startswith("agent")
        or event.startswith("evaluator")
        for event in lifecycle_events
    ):
        raise ContractError("refusing to retire an attempt that reached formal execution")
    for required in ("preprocess.end", "gateway.ready", "cleanup.end"):
        if required not in lifecycle_events:
            raise ContractError(f"scheduler incident lacks {required} evidence")

    recovery_root.mkdir(parents=True, exist_ok=True)
    if source.exists():
        source.rename(destination)
    recovery = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "classification": "scheduler_preflight_incident_not_formal_attempt",
        "cause": "frozen_adapter_source_mismatch_before_orchestrator_start",
        "run_id": run_id,
        "task_id": FAILED_TASK_ID,
        "system": FAILED_SYSTEM,
        "position": FAILED_TASK_POSITION,
        "original_directory": str(source),
        "preserved_directory": str(destination),
        "retired_scheduler_event_sequences": sorted(retired_sequences),
        "agent_started": False,
        "evaluator_started": False,
        "cleanup_completed": True,
        "lifecycle_events_sha256": sha256_file(
            destination / "lifecycle-events.jsonl"
        ),
        "frozen_m2_batch_sha256": FROZEN_M2_BATCH_SHA256,
        "hotfix_source_sha256": sha256_file(Path(__file__)),
    }
    if record_path.exists():
        existing = read_json_object(record_path)
        stable_fields = (
            "classification",
            "cause",
            "run_id",
            "retired_scheduler_event_sequences",
            "lifecycle_events_sha256",
            "frozen_m2_batch_sha256",
        )
        if any(existing.get(field) != recovery.get(field) for field in stable_fields):
            raise ContractError("existing scheduler recovery record differs")
    else:
        write_json_atomic(record_path, recovery, mode=0o644)
    return retired_sequences, record_path


class HotfixM2Batch(m2_batch.M2Batch):
    def __init__(self, *args: Any, retired_sequences: set[int], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.retired_sequences = set(retired_sequences)

    def _validate_schedule_events(self) -> None:
        rows = read_jsonl(
            self.output_root / "scheduler-events.jsonl", allow_empty=False
        )
        rows = [
            row for row in rows if int(row.get("sequence", -1)) not in self.retired_sequences
        ]
        expected_slots = [
            (position, task_id, system)
            for position, (task_id, order) in enumerate(
                m2_batch.FIRST_BATCH[1:], start=2
            )
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
                        (
                            int(row.get("position")),
                            str(row.get("task_id")),
                            str(row.get("system")),
                        )
                    )
                elif not observed_originals or observed_originals[-1] != (
                    int(row.get("position")),
                    str(row.get("task_id")),
                    str(row.get("system")),
                ):
                    raise ContractError(
                        "M2 replacement was not adjacent to its original slot"
                    )
            elif event in {"attempt.process_exit", "attempt.process_interrupted"}:
                key = (str(row.get("run_id")), int(row.get("attempt_ordinal")))
                if active != key:
                    raise ContractError(
                        "M2 process terminal event does not match the active attempt"
                    )
                active = None
        if active is not None:
            raise ContractError("M2 scheduler has an attempt with no process-exit event")
        if observed_originals != expected_slots:
            raise ContractError("M2 original attempts were not run in the frozen serial order")


def _verify_frozen_scheduler(repo_root: Path) -> None:
    path = repo_root / "astra/runners/toolathlon_verified/m2_batch.py"
    if sha256_file(path) != FROZEN_M2_BATCH_SHA256:
        raise ContractError("m2_batch.py is not restored to its frozen hash")


def _write_provenance(
    output_root: Path, recovery_record: Path | None, event_log: HotfixEventLog
) -> Path:
    path = output_root / "scheduler-hotfix-provenance.json"
    value = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "policy": POLICY,
        "scope": "scheduler pair gate and one pre-agent recovery only",
        "formal_run_artifacts_modified": False,
        "frozen_m2_batch_sha256": FROZEN_M2_BATCH_SHA256,
        "hotfix_source": str(Path(__file__).resolve()),
        "hotfix_source_sha256": sha256_file(Path(__file__)),
        "events": str(event_log.path),
        "recovery_record": str(recovery_record) if recovery_record else None,
    }
    if path.exists():
        existing = read_json_object(path)
        for field in (
            "policy",
            "frozen_m2_batch_sha256",
            "hotfix_source_sha256",
            "recovery_record",
        ):
            if existing.get(field) != value.get(field):
                raise ContractError("existing scheduler hotfix provenance differs")
    else:
        write_json_atomic(path, value, mode=0o644)
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume M2 with audited Schema gate hotfix")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--m1-root", type=Path, required=True)
    parser.add_argument(
        "--repo-root", type=Path, default=Path("/home/vagrant/moi-benchmark")
    )
    parser.add_argument(
        "--source-root", type=Path, default=Path("/home/vagrant/dataset/Toolathlon")
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    _verify_frozen_scheduler(repo_root)
    retired_sequences, recovery_record = _scheduler_incident(output_root)
    event_log = HotfixEventLog(output_root / "scheduler-hotfix-events.jsonl")
    provenance = _write_provenance(output_root, recovery_record, event_log)
    print(
        json.dumps(
            {
                "check": "m2_scheduler_hotfix",
                "status": "GO",
                "frozen_m2_batch_sha256": FROZEN_M2_BATCH_SHA256,
                "retired_scheduler_event_sequences": sorted(retired_sequences),
                "recovery_record": str(recovery_record) if recovery_record else None,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    m2_batch.validate_pair = _pair_validator(output_root, event_log)
    batch = HotfixM2Batch(
        repo_root=repo_root,
        output_root=output_root,
        m1_root=args.m1_root,
        source_root=args.source_root,
        retired_sequences=retired_sequences,
    )
    report = batch.run()
    hotfix_hash = output_root / "scheduler-hotfix.sha256"
    hash_targets = [provenance, event_log.path]
    if recovery_record is not None:
        hash_targets.append(recovery_record)
    write_sha256_manifest(hotfix_hash, hash_targets, root=output_root)
    print(
        json.dumps(
            {
                "status": report["status"],
                "task_count": report["task_count"],
                "effective_slot_count": report["effective_slot_count"],
                "report": str(batch.report_path),
                "scheduler_hotfix_sha256": sha256_file(hotfix_hash),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
