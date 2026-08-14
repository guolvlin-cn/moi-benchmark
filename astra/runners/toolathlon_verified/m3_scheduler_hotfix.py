from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from . import m2_batch, m3_batch
from .contract import (
    ContractError,
    read_json_object,
    sha256_file,
    utc_now,
    write_json_atomic,
    write_sha256_manifest,
)
from .m2_scheduler_hotfix import (
    FROZEN_M2_BATCH_SHA256,
    POLICY,
    HotfixEventLog,
    HotfixM2Batch,
    _pair_validator,
    _verify_frozen_scheduler,
)


SCHEMA_VERSION = "toolathlon.m3-scheduler-hotfix.v1"
FROZEN_M3_BATCH_SHA256 = (
    "f1ecc8afce2f67dd95487a2ec470535d6ba7b5ac4c6fee5e11ec637faad84669"
)


def _verify_sha256_manifest(path: Path, root: Path) -> None:
    if not path.is_file():
        raise ContractError(f"checksum manifest is missing: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or len(digest) != 64:
            raise ContractError(f"invalid checksum manifest: {path}")
        target = (root / relative).resolve()
        if root.resolve() not in target.parents or sha256_file(target) != digest:
            raise ContractError(f"checksum manifest mismatch: {target}")


def _m2_recovery_sequences(m2_root: Path) -> set[int]:
    record_path = (
        m2_root
        / "recovery-evidence"
        / "freeze-source-mismatch"
        / "recovery.json"
    )
    if not record_path.exists():
        return set()
    record = read_json_object(record_path)
    sequences = record.get("retired_scheduler_event_sequences")
    if (
        record.get("classification")
        != "scheduler_preflight_incident_not_formal_attempt"
        or not isinstance(sequences, list)
        or not sequences
        or any(not isinstance(item, int) for item in sequences)
    ):
        raise ContractError("M2 scheduler recovery record is invalid")
    return set(sequences)


def _write_provenance(
    output_root: Path,
    m2_root: Path,
    event_log: HotfixEventLog,
) -> Path:
    path = output_root / "scheduler-hotfix-provenance.json"
    value = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "policy": POLICY,
        "scope": "M3 pair gate plus audited M2 qualification",
        "formal_run_artifacts_modified": False,
        "frozen_m2_batch_sha256": FROZEN_M2_BATCH_SHA256,
        "frozen_m3_batch_sha256": FROZEN_M3_BATCH_SHA256,
        "hotfix_source": str(Path(__file__).resolve()),
        "hotfix_source_sha256": sha256_file(Path(__file__)),
        "m2_root": str(m2_root),
        "m2_scheduler_hotfix_sha256": sha256_file(
            m2_root / "scheduler-hotfix.sha256"
        ),
        "events": str(event_log.path),
    }
    if path.exists():
        existing = read_json_object(path)
        for field in (
            "policy",
            "frozen_m2_batch_sha256",
            "frozen_m3_batch_sha256",
            "hotfix_source_sha256",
            "m2_root",
            "m2_scheduler_hotfix_sha256",
        ):
            if existing.get(field) != value.get(field):
                raise ContractError("existing M3 scheduler hotfix provenance differs")
    else:
        write_json_atomic(path, value, mode=0o644)
    return path


class AuditedM3Batch(m3_batch.M3Batch):
    def __init__(
        self,
        *args: Any,
        provenance_writer: Callable[[], Path],
        **kwargs: Any,
    ) -> None:
        self.provenance_writer = provenance_writer
        self.hotfix_provenance: Path | None = None
        super().__init__(*args, **kwargs)

    def initialize(self) -> None:
        super().initialize()
        self.hotfix_provenance = self.provenance_writer()


def _verify_frozen_m3(repo_root: Path) -> None:
    path = repo_root / "astra/runners/toolathlon_verified/m3_batch.py"
    if sha256_file(path) != FROZEN_M3_BATCH_SHA256:
        raise ContractError("m3_batch.py is not restored to its frozen hash")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run M3 with audited Schema gate hotfix")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--m2-root", type=Path, required=True)
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
    m2_root = args.m2_root.resolve()
    _verify_frozen_scheduler(repo_root)
    _verify_frozen_m3(repo_root)
    _verify_sha256_manifest(m2_root / "scheduler-hotfix.sha256", m2_root)
    retired_sequences = _m2_recovery_sequences(m2_root)

    frozen_pair_validator = m2_batch.validate_pair
    m2_event_log = HotfixEventLog(m2_root / "scheduler-hotfix-events.jsonl")
    if len(m2_event_log.recorded_pairs) != 14:
        raise ContractError("M2 scheduler hotfix does not contain all 14 pair records")
    m2_readonly_validator = _pair_validator(m2_root, m2_event_log)
    m2_batch.validate_pair = frozen_pair_validator
    m3_event_log = HotfixEventLog(
        output_root / "scheduler-hotfix-events.jsonl",
        schema_version=SCHEMA_VERSION,
    )
    m3_pair_validator = _pair_validator(output_root, m3_event_log)
    m2_batch.validate_pair = m2_readonly_validator
    m3_batch.validate_pair = m3_pair_validator

    class PriorM2Validator(HotfixM2Batch):
        def __init__(self, *inner_args: Any, **inner_kwargs: Any) -> None:
            super().__init__(
                *inner_args,
                retired_sequences=retired_sequences,
                **inner_kwargs,
            )

    m3_batch.M2Batch = PriorM2Validator
    provenance_writer = lambda: _write_provenance(
        output_root, m2_root, m3_event_log
    )
    batch = AuditedM3Batch(
        repo_root=repo_root,
        output_root=output_root,
        m2_root=m2_root,
        source_root=args.source_root,
        provenance_writer=provenance_writer,
    )
    report = batch.run()
    if batch.hotfix_provenance is None:
        raise ContractError("M3 scheduler hotfix provenance was not created")
    hotfix_hash = output_root / "scheduler-hotfix.sha256"
    write_sha256_manifest(
        hotfix_hash,
        [batch.hotfix_provenance, m3_event_log.path],
        root=output_root,
    )
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
