#!/usr/bin/env python3
"""Serial, resumable scheduler for the 11 post-hoc unavailable/infra reruns."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

POLICY_SCHEMA = "toolathlon.posthoc-unavailable-infra-rerun-policy.v1"
MANIFEST_SCHEMA = "toolathlon.posthoc-unavailable-infra-rerun-manifest.v1"
EVENT_SCHEMA = "toolathlon.posthoc-unavailable-infra-rerun-events.v1"
REPORT_SCHEMA = "toolathlon.posthoc-unavailable-infra-rerun-qualification.v1"
HERMES_SUCCESSFUL_DRAIN_POLICY = (
    "toolathlon.posthoc-hermes-drain-timeout-successful-terminal-race.v1"
)
HERMES_SUCCESSFUL_DRAIN_ARTIFACT = (
    "posthoc-hermes-successful-drain-reconciliation.json"
)
SAFE_ID = re.compile(r"[A-Za-z0-9._-]+")
REQUIRED_ARTIFACTS = (
    "resolved-config.json",
    "tool-schema-observed.json",
    "lifecycle-events.jsonl",
    "adapter-events.jsonl",
    "trajectory.jsonl",
    "tool-calls.jsonl",
    "model-usage.jsonl",
    "resource-usage.jsonl",
    "evaluator/eval_res.json",
    "evaluator/eval.log",
    "failure-evidence.json",
    "run.json",
    "artifacts.sha256",
)


class RerunBlocked(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RerunBlocked(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RerunBlocked(f"expected JSON object: {path}")
    return value


def write_object(path: Path, value: dict[str, Any], *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def observation_value(value: Any) -> Any:
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def read_jsonl(path: Path, *, allow_empty: bool) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise RerunBlocked(f"cannot read JSONL {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line:
            raise RerunBlocked(f"blank JSONL line: {path}:{line_number}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RerunBlocked(f"invalid JSONL: {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise RerunBlocked(f"JSONL row is not an object: {path}:{line_number}")
        rows.append(row)
    if not rows and not allow_empty:
        raise RerunBlocked(f"required JSONL is empty: {path}")
    return rows


def is_below(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def validate_output_root(path: Path, protected: tuple[Path, ...]) -> Path:
    resolved = path.resolve()
    allowed = (Path("/home/vagrant/moi-benchmark"), Path("/tmp"))
    if not any(is_below(resolved, root) and resolved != root for root in allowed):
        raise RerunBlocked("output root must be below /home/vagrant/moi-benchmark or /tmp")
    for root in protected:
        if is_below(resolved, root) or is_below(root, resolved):
            raise RerunBlocked(f"output root overlaps protected evidence root: {root}")
    return resolved


def validate_id(label: str, value: Any) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise RerunBlocked(f"{label} is not a safe identifier")
    return value


def validate_policy(
    policy_path: Path,
    *,
    repo_root: Path,
    m1_root: Path,
    m2_root: Path,
    m3_root: Path,
    source_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    policy = read_object(policy_path)
    scope = policy.get("scope")
    runtime = policy.get("runtime")
    cases = policy.get("cases")
    if (
        policy.get("schema_version") != POLICY_SCHEMA
        or policy.get("policy")
        != "toolathlon.posthoc-unavailable-infra-sensitivity-rerun.v1"
        or not isinstance(scope, dict)
        or scope.get("formal_result_mutation") is not False
        or scope.get("result_use") != "posthoc_sensitivity_only"
        or scope.get("workers") != 1
        or scope.get("automatic_infrastructure_replacement_maximum") != 1
        or not isinstance(runtime, dict)
        or not isinstance(cases, list)
        or len(cases) != scope.get("selected_slot_count")
        or len(cases) != 11
    ):
        raise RerunBlocked("post-hoc rerun policy header is invalid")
    if source_root != Path(str(runtime.get("toolathlon_source"))).resolve():
        raise RerunBlocked("Toolathlon source root differs from rerun policy")
    helper_relative = Path(str(runtime.get("lifecycle_hotfix_path", "")))
    if helper_relative.is_absolute() or ".." in helper_relative.parts:
        raise RerunBlocked("unsafe lifecycle hotfix path in policy")
    helper = (repo_root / helper_relative).resolve()
    if sha256_file(helper) != runtime.get("lifecycle_hotfix_sha256"):
        raise RerunBlocked("outer lifecycle helper changed after rerun policy freeze")

    roots = {"m1": m1_root, "m2": m2_root, "m3": m3_root}
    labels: set[str] = set()
    for item in policy.get("source_inputs", []):
        if not isinstance(item, dict):
            raise RerunBlocked("source input record is invalid")
        label = validate_id("source input label", item.get("label"))
        root = roots.get(str(item.get("root")))
        relative = Path(str(item.get("relative_path", "")))
        if label in labels or root is None or relative.is_absolute() or ".." in relative.parts:
            raise RerunBlocked("source input identity or path is invalid")
        labels.add(label)
        path = (root / relative).resolve()
        if not is_below(path, root) or sha256_file(path) != item.get("sha256"):
            raise RerunBlocked(f"source input changed after selection: {label}")

    normalized: list[dict[str, Any]] = []
    keys: set[tuple[str, str]] = set()
    sequences: list[int] = []
    for raw in cases:
        if not isinstance(raw, dict):
            raise RerunBlocked("case record is invalid")
        case = dict(raw)
        sequence = case.get("sequence")
        position = case.get("position")
        task_id = validate_id("task_id", case.get("task_id"))
        system_id = case.get("system_id")
        source_run_id = validate_id("source_run_id", case.get("source_run_id"))
        if (
            not isinstance(sequence, int)
            or not isinstance(position, int)
            or not 1 <= position <= 108
            or system_id not in {"astra", "hermes"}
            or (task_id, system_id) in keys
            or case.get("source_verify_status") != "unavailable"
            or case.get("source_run_validity") not in {"valid", "infra_invalid"}
        ):
            raise RerunBlocked(f"invalid selected case: {task_id}/{system_id}")
        keys.add((task_id, system_id))
        sequences.append(sequence)
        relative = Path(str(case.get("source_run_relative_directory", "")))
        expected_relative = Path("runs") / system_id / task_id / source_run_id
        if relative != expected_relative or relative.is_absolute():
            raise RerunBlocked(f"source run path mismatch: {task_id}/{system_id}")
        directory = (m3_root / relative).resolve()
        if not is_below(directory, m3_root):
            raise RerunBlocked("source run escapes M3 root")
        run_path = directory / "run.json"
        artifacts_path = directory / "artifacts.sha256"
        if (
            sha256_file(run_path) != case.get("source_run_json_sha256")
            or sha256_file(artifacts_path)
            != case.get("source_artifacts_manifest_sha256")
        ):
            raise RerunBlocked(f"source run evidence changed: {source_run_id}")
        run = read_object(run_path)
        expected_fields = {
            "run_id": source_run_id,
            "task_id": task_id,
            "system_id": system_id,
            "verify_status": case.get("source_verify_status"),
            "run_validity": case.get("source_run_validity"),
            "terminal_status": case.get("source_terminal_status"),
            "primary_failure_category": case.get("source_failure_category"),
        }
        if any(run.get(field) != value for field, value in expected_fields.items()):
            raise RerunBlocked(f"source run classification changed: {source_run_id}")
        normalized.append(case)
    if sequences != list(range(1, 12)):
        raise RerunBlocked("case sequence is not contiguous")
    if Counter(item[1] for item in keys) != Counter({"astra": 6, "hermes": 5}):
        raise RerunBlocked("selected system counts differ from the frozen 6/5 split")
    if sum(item["source_run_validity"] == "infra_invalid" for item in normalized) != 1:
        raise RerunBlocked("selected infra-invalid count differs from one")
    return policy, normalized


class EventLog:
    def __init__(self, path: Path, batch_id: str) -> None:
        self.path = path
        self.batch_id = batch_id
        self.sequence = 0
        if path.exists():
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        row = json.loads(line)
                        self.sequence = max(self.sequence, int(row.get("sequence", 0)))

    def append(self, event: str, **fields: Any) -> None:
        self.sequence += 1
        row = {
            "schema_version": EVENT_SCHEMA,
            "batch_id": self.batch_id,
            "sequence": self.sequence,
            "event": event,
            "timestamp": utc_now(),
            "monotonic_ns": time.monotonic_ns(),
            **fields,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def rows_for_run(self, run_id: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    if row.get("run_id") == run_id:
                        rows.append(row)
        return rows


def verify_artifact_manifest(root: Path) -> None:
    manifest = root / "artifacts.sha256"
    observed: set[str] = set()
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        digest, separator, relative_text = line.partition("  ")
        relative = Path(relative_text)
        if (
            not separator
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() in observed
        ):
            raise RerunBlocked(f"invalid artifacts.sha256 line {line_number}: {root}")
        observed.add(relative.as_posix())
        path = (root / relative).resolve()
        if not is_below(path, root) or path.is_symlink() or not path.is_file():
            raise RerunBlocked(f"unsafe or missing hashed artifact: {path}")
        if sha256_file(path) != digest:
            raise RerunBlocked(f"artifact hash mismatch: {path}")
    expected = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and not item.is_symlink() and item.name != "artifacts.sha256"
    }
    if observed != expected:
        raise RerunBlocked(f"artifact manifest coverage differs: {root}")


def successful_hermes_drain_race_evidence(
    directory: Path, run: dict[str, Any]
) -> dict[str, Any]:
    if (
        run.get("system_id") != "hermes"
        or run.get("terminal_status") != "completed"
        or run.get("termination_reason") != "product_exit"
        or run.get("run_validity") != "valid"
        or run.get("verify_status") not in {"pass", "no_pass"}
        or run.get("artifact_gate", {}).get("status")
        != "pending_cleanup_and_validation"
    ):
        raise RerunBlocked("attempt is not a pending completed Hermes result")
    adapter = run.get("adapter")
    initial = adapter.get("post_terminal_model_drain") if isinstance(adapter, dict) else None
    if (
        not isinstance(initial, dict)
        or initial.get("settled") is not False
        or not isinstance(initial.get("provider_requests_forwarded"), int)
        or not isinstance(initial.get("provider_requests_completed"), int)
        or initial["provider_requests_forwarded"]
        <= initial["provider_requests_completed"]
        or not isinstance(initial.get("timeout_seconds"), (int, float))
        or not isinstance(initial.get("wait_seconds"), (int, float))
        or initial["wait_seconds"] < initial["timeout_seconds"]
    ):
        raise RerunBlocked("Hermes drain is not a timed-out unsettled snapshot")

    models = read_jsonl(directory / "model-usage.jsonl", allow_empty=False)
    adapters = read_jsonl(directory / "adapter-events.jsonl", allow_empty=False)
    lifecycle = read_jsonl(directory / "lifecycle-events.jsonl", allow_empty=False)
    try:
        from astra.runners.toolathlon_verified import artifact_contract

        artifact_contract._validate_model_usage(models, run)
    except Exception as exc:
        raise RerunBlocked(f"final model evidence is not structurally closed: {exc}") from exc

    starts = {
        str(row["model_request_id"]): row
        for row in models
        if row.get("event") == "model_request.started"
    }
    completions = {
        str(row["model_request_id"]): row
        for row in models
        if row.get("event") == "model_request.completed"
    }
    stopped = [row for row in models if row.get("event") == "proxy.stopped"]
    if set(starts) != set(completions) or len(stopped) != 1:
        raise RerunBlocked("final model request or proxy-stop evidence is not unique")
    stopped_ns = stopped[0].get("monotonic_ns")
    if not isinstance(stopped_ns, int):
        raise RerunBlocked("proxy stop has no monotonic timestamp")
    forwarded = len(starts)
    completed = len(completions)
    missing_at_snapshot = (
        initial["provider_requests_forwarded"]
        - initial["provider_requests_completed"]
    )
    if (
        forwarded != initial["provider_requests_forwarded"]
        or completed != forwarded
        or missing_at_snapshot < 1
    ):
        raise RerunBlocked("final model totals do not close the drain snapshot")
    ordered = sorted(
        completions.values(), key=lambda row: int(row.get("monotonic_ns", -1))
    )
    closing = ordered[-missing_at_snapshot:]
    closing_evidence: list[dict[str, Any]] = []
    for row in closing:
        request_id = str(row.get("model_request_id"))
        completed_ns = row.get("monotonic_ns")
        if not isinstance(completed_ns, int):
            raise RerunBlocked("drain-closing terminal has no monotonic timestamp")
        relative_seconds = (completed_ns - stopped_ns) / 1_000_000_000
        if (
            row.get("success") is not True
            or row.get("http_status") != 200
            or not -10 <= relative_seconds <= 0
        ):
            raise RerunBlocked(
                "drain-closing terminal is not the bounded successful pre-stop race"
            )
        closing_evidence.append(
            {
                "model_request_id": request_id,
                "product_attempt": row.get("product_attempt"),
                "started_monotonic_ns": starts[request_id].get("monotonic_ns"),
                "completed_monotonic_ns": completed_ns,
                "seconds_before_proxy_stopped": round(-relative_seconds, 6),
                "success": True,
                "http_status": 200,
            }
        )

    agent_ends = [
        row for row in adapters if row.get("event") == "agent.execution_end"
    ]
    evaluator_ends = [
        row for row in adapters if row.get("event") == "evaluator.end"
    ]
    if (
        len(agent_ends) != 1
        or len(evaluator_ends) != 1
        or evaluator_ends[0].get("verify_status") != run.get("verify_status")
    ):
        raise RerunBlocked("Agent/evaluator terminal evidence is not unique")
    eval_result = read_object(directory / "evaluator/eval_res.json")
    expected_pass = run.get("verify_status") == "pass"
    if eval_result.get("pass") is not expected_pass:
        raise RerunBlocked("evaluator conclusion differs from run.json")
    events = [row.get("event") for row in lifecycle]
    if (
        events[-1:] != ["artifact_validation.start"]
        or events.count("artifact_validation.start") != 1
        or "artifact_validation.end" in events
        or "cleanup.end" not in events
    ):
        raise RerunBlocked("pending lifecycle boundary is not recoverable")
    hash_path = directory / "artifacts.sha256"
    recovery_path = directory / HERMES_SUCCESSFUL_DRAIN_ARTIFACT
    if (
        not hash_path.is_file()
        or hash_path.stat().st_size != 0
        or recovery_path.exists()
    ):
        raise RerunBlocked("pending hash/reconciliation boundary is not fresh")
    budget = run.get("model_budget")
    if (
        not isinstance(budget, dict)
        or budget.get("provider_requests_forwarded") != forwarded
        or budget.get("provider_requests_completed") != completed
    ):
        raise RerunBlocked("run model budget differs from final model evidence")
    return {
        "policy": HERMES_SUCCESSFUL_DRAIN_POLICY,
        "pre_proxy_shutdown_drain": dict(initial),
        "final_provider_requests_forwarded": forwarded,
        "final_provider_requests_completed": completed,
        "final_provider_requests_failed": sum(
            row.get("success") is False for row in completions.values()
        ),
        "snapshot_closing_terminal_count": missing_at_snapshot,
        "closing_successful_terminals": closing_evidence,
        "proxy_stopped_monotonic_ns": stopped_ns,
        "agent_terminal_monotonic_ns": agent_ends[0].get("monotonic_ns"),
        "evaluator_verify_status": run.get("verify_status"),
        "interpretation": (
            "the timed-out adapter snapshot lagged the append-only model log; "
            "all forwarded requests had unique successful terminals before proxy stop"
        ),
    }


def append_lifecycle_event(path: Path, run: dict[str, Any], **fields: Any) -> None:
    rows = read_jsonl(path, allow_empty=False)
    if [row.get("sequence") for row in rows] != list(range(1, len(rows) + 1)):
        raise RerunBlocked("lifecycle event sequence is not contiguous")
    record = {
        "schema_version": "toolathlon.adapter.events.v1",
        "run_id": run["run_id"],
        "system_id": run["system_id"],
        "sequence": len(rows) + 1,
        "timestamp": utc_now(),
        "monotonic_ns": time.monotonic_ns(),
        **fields,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def rehash_attempt(directory: Path) -> None:
    candidates = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.name != "artifacts.sha256"
    )
    (directory / "artifacts.sha256").write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(directory).as_posix()}\n"
            for path in candidates
        ),
        encoding="utf-8",
    )


def recover_successful_hermes_drain_race(
    directory: Path, run: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = successful_hermes_drain_race_evidence(directory, run)
    run_path = directory / "run.json"
    lifecycle_path = directory / "lifecycle-events.jsonl"
    hash_path = directory / "artifacts.sha256"
    recovery_path = directory / HERMES_SUCCESSFUL_DRAIN_ARTIFACT
    original_run = run_path.read_bytes()
    original_lifecycle = lifecycle_path.read_bytes()
    original_hash = hash_path.read_bytes()
    before = {
        relative: sha256_file(directory / relative)
        for relative in (
            "run.json",
            "lifecycle-events.jsonl",
            "adapter-events.jsonl",
            "model-usage.jsonl",
            "trajectory.jsonl",
            "tool-calls.jsonl",
            "evaluator/eval_res.json",
        )
    }
    try:
        write_object(
            recovery_path,
            {
                "schema_version": (
                    "toolathlon.posthoc-hermes-successful-drain-reconciliation.v1"
                ),
                "policy": HERMES_SUCCESSFUL_DRAIN_POLICY,
                "recorded_at": utc_now(),
                "run_id": run["run_id"],
                "task_id": run["task_id"],
                "system_id": run["system_id"],
                "formal_result_mutation": False,
                "agent_rerun": False,
                "evaluator_rerun": False,
                "raw_append_only_evidence_modified": False,
                "pre_finalization_sha256": before,
                "evidence": evidence,
            },
        )
        initial = evidence["pre_proxy_shutdown_drain"]
        run["adapter"]["post_terminal_model_drain"] = {
            "settled": True,
            "settlement_phase": "posthoc_drain_timeout_successful_terminal_race",
            "settled_basis": "all_forwarded_requests_have_unique_terminals",
            "provider_requests_forwarded": evidence[
                "final_provider_requests_forwarded"
            ],
            "provider_requests_completed": evidence[
                "final_provider_requests_completed"
            ],
            "provider_requests_failed": evidence["final_provider_requests_failed"],
            "pre_proxy_shutdown_settled": False,
            "pre_proxy_shutdown_timeout_seconds": initial["timeout_seconds"],
            "pre_proxy_shutdown_wait_seconds": initial["wait_seconds"],
            "snapshot_closing_terminal_count": evidence[
                "snapshot_closing_terminal_count"
            ],
            "reconciliation_artifact": HERMES_SUCCESSFUL_DRAIN_ARTIFACT,
            "reconciliation_policy": HERMES_SUCCESSFUL_DRAIN_POLICY,
        }
        run["artifact_gate"] = {
            "status": "passed",
            "validator": HERMES_SUCCESSFUL_DRAIN_POLICY,
            "validated_at": utc_now(),
            "frozen_validator_error": (
                "valid run has an unsettled post-terminal model drain"
            ),
            "observability_artifact": HERMES_SUCCESSFUL_DRAIN_ARTIFACT,
            "formal_result_mutation": False,
        }
        write_object(run_path, run)
        append_lifecycle_event(
            lifecycle_path,
            run,
            event="artifact_validation.end",
            status="passed",
            validator=HERMES_SUCCESSFUL_DRAIN_POLICY,
            observability_artifact=HERMES_SUCCESSFUL_DRAIN_ARTIFACT,
            formal_result_mutation=False,
        )
        rehash_attempt(directory)
        from astra.runners.toolathlon_verified import artifact_contract

        validation = artifact_contract.validate_run_artifacts(
            directory, verify_hash=True
        )
    except BaseException:
        run_path.write_bytes(original_run)
        lifecycle_path.write_bytes(original_lifecycle)
        hash_path.write_bytes(original_hash)
        recovery_path.unlink(missing_ok=True)
        raise
    return read_object(run_path), {
        "policy": HERMES_SUCCESSFUL_DRAIN_POLICY,
        "observability_artifact": str(recovery_path),
        "observability_artifact_sha256": sha256_file(recovery_path),
        "artifacts_manifest_sha256": sha256_file(hash_path),
        "validation": validation,
        "formal_result_mutation": False,
        "agent_rerun": False,
        "evaluator_rerun": False,
    }


def inspect_attempt(
    directory: Path,
    *,
    task_id: str,
    system_id: str,
    run_id: str,
    replacement_for: str | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    if not directory.exists():
        return "absent", None, None
    missing = [relative for relative in REQUIRED_ARTIFACTS if not (directory / relative).is_file()]
    if system_id == "astra" and not (directory / "astra-runtime-mcp-binding.json").is_file():
        missing.append("astra-runtime-mcp-binding.json")
    if missing:
        return "incomplete", None, f"missing required artifacts: {missing}"
    run = read_object(directory / "run.json")
    if (
        run.get("run_id") != run_id
        or run.get("task_id") != task_id
        or run.get("system_id") != system_id
        or observation_value(run.get("replacement_for_run_id")) != replacement_for
    ):
        return "incomplete", run, "run identity or replacement differs"
    if run.get("artifact_gate", {}).get("status") != "passed":
        try:
            successful_hermes_drain_race_evidence(directory, run)
        except RerunBlocked as exc:
            return "incomplete", run, f"artifact gate is not passed: {exc}"
        return "recoverable", run, HERMES_SUCCESSFUL_DRAIN_POLICY
    verify_artifact_manifest(directory)
    return "complete", run, None


def lifecycle_has_adapter_start(directory: Path) -> bool:
    path = directory / "lifecycle-events.jsonl"
    if not path.is_file():
        return False
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip() and json.loads(line).get("event") == "adapter.start":
                return True
    return False


class Scheduler:
    def __init__(
        self,
        *,
        repo_root: Path,
        source_root: Path,
        output_root: Path,
        policy_path: Path,
        policy: dict[str, Any],
        cases: list[dict[str, Any]],
        roots: dict[str, Path],
    ) -> None:
        self.repo_root = repo_root
        self.source_root = source_root
        self.output_root = output_root
        self.policy_path = policy_path
        self.policy = policy
        self.cases = cases
        self.roots = roots
        self.manifest_path = output_root / "posthoc-rerun-manifest.json"
        self.events_path = output_root / "scheduler-events.jsonl"
        self.checkpoint_path = output_root / "checkpoint.json"
        self.report_path = output_root / "posthoc-rerun-qualification.json"
        self.report_hash_path = output_root / "posthoc-rerun-qualification.sha256"
        self.batch_hash_path = output_root / "posthoc-rerun-batch.sha256"
        self.lock_stream: Any = None
        self.source_lock_stream: Any = None
        self.manifest: dict[str, Any] = {}
        self.events: EventLog | None = None

    def acquire_lock(self) -> None:
        source_lock = self.roots["m3"] / ".m3.lock"
        if not source_lock.is_file():
            raise RerunBlocked("M3 source lock file is missing")
        self.source_lock_stream = source_lock.open("r", encoding="utf-8")
        try:
            fcntl.flock(
                self.source_lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
            )
        except BlockingIOError as exc:
            raise RerunBlocked(
                "formal M3 is still running; post-hoc reruns require an idle M3 root"
            ) from exc
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.lock_stream = (self.output_root / ".posthoc-rerun.lock").open("a+")
        try:
            fcntl.flock(self.lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RerunBlocked("another post-hoc rerun scheduler holds the lock") from exc

    def expected_case_records(self, batch_id: str) -> list[dict[str, Any]]:
        records = []
        for case in self.cases:
            stem = (
                f"{batch_id}-{case['position']:03d}-{case['task_id']}-"
                f"{case['system_id']}"
            )
            records.append(
                {
                    **case,
                    "target_run_ids": [f"{stem}-a1", f"{stem}-a2"],
                    "formal_result_mutation": False,
                }
            )
        return records

    def initialize(self) -> None:
        self.acquire_lock()
        policy_sha = sha256_file(self.policy_path)
        if self.manifest_path.exists():
            manifest = read_object(self.manifest_path)
            batch_id = validate_id("batch_id", manifest.get("batch_id"))
            if (
                manifest.get("schema_version") != MANIFEST_SCHEMA
                or manifest.get("policy_sha256") != policy_sha
                or manifest.get("formal_result_mutation") is not False
                or manifest.get("workers") != 1
                or manifest.get("cases") != self.expected_case_records(batch_id)
                or manifest.get("roots")
                != {key: str(value) for key, value in sorted(self.roots.items())}
            ):
                raise RerunBlocked("existing post-hoc rerun manifest differs")
            self.manifest = manifest
        else:
            unexpected = [
                path.name
                for path in self.output_root.iterdir()
                if path.name != ".posthoc-rerun.lock"
            ]
            if unexpected:
                raise RerunBlocked(
                    f"new output root is not empty: {sorted(unexpected)}"
                )
            batch_id = f"posthoc-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
            self.manifest = {
                "schema_version": MANIFEST_SCHEMA,
                "created_at": utc_now(),
                "batch_id": batch_id,
                "experiment_id": self.policy["runtime"]["experiment_id"],
                "policy": str(self.policy_path),
                "policy_sha256": policy_sha,
                "formal_result_mutation": False,
                "result_use": "posthoc_sensitivity_only",
                "workers": 1,
                "automatic_infrastructure_replacement_maximum": 1,
                "roots": {key: str(value) for key, value in sorted(self.roots.items())},
                "cases": self.expected_case_records(batch_id),
            }
            write_object(self.manifest_path, self.manifest)
        self.events = EventLog(self.events_path, self.manifest["batch_id"])
        checkpoint = read_object(self.checkpoint_path) if self.checkpoint_path.exists() else {}
        if checkpoint.get("status") != "GO":
            self.events.append("batch.resume" if checkpoint else "batch.start")

    def checkpoint(self, status: str, **fields: Any) -> None:
        assert self.events is not None
        write_object(
            self.checkpoint_path,
            {
                "schema_version": "toolathlon.posthoc-unavailable-infra-rerun-checkpoint.v1",
                "batch_id": self.manifest["batch_id"],
                "status": status,
                "updated_at": utc_now(),
                "scheduler_event_sequence": self.events.sequence,
                **fields,
            },
        )

    def attempt_path(self, case: dict[str, Any], run_id: str) -> Path:
        return self.output_root / "runs" / case["system_id"] / case["task_id"] / run_id

    def run_attempt(
        self,
        case: dict[str, Any],
        *,
        ordinal: int,
        replacement_for: str | None,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        assert self.events is not None
        run_id = case["target_run_ids"][ordinal - 1]
        directory = self.attempt_path(case, run_id)
        if directory.exists():
            raise RerunBlocked(f"attempt directory already exists but is not reusable: {directory}")
        wrapper = (
            self.repo_root
            / "astra/benchmark/toolathlon-verified/scripts/"
            "posthoc_unavailable_infra_lifecycle.py"
        )
        command = [
            sys.executable,
            str(wrapper),
            "--posthoc-rerun-policy",
            str(self.policy_path),
            "--system",
            case["system_id"],
            "--task-id",
            case["task_id"],
            "--experiment-id",
            self.policy["runtime"]["experiment_id"],
            "--run-id",
            run_id,
            "--output-dir",
            str(directory),
            "--toolathlon-source",
            str(self.source_root),
        ]
        if replacement_for is not None:
            command.extend(["--replacement-for-run-id", replacement_for])
        self.events.append(
            "attempt.start",
            case_sequence=case["sequence"],
            position=case["position"],
            task_id=case["task_id"],
            system=case["system_id"],
            run_id=run_id,
            attempt_ordinal=ordinal,
            replacement_for_run_id=replacement_for,
            source_formal_run_id=case["source_run_id"],
            formal_result_mutation=False,
        )
        try:
            result = subprocess.run(command, cwd=self.repo_root, check=False)
        except KeyboardInterrupt:
            self.events.append(
                "attempt.process_interrupted",
                run_id=run_id,
                task_id=case["task_id"],
                system=case["system_id"],
                error_type="KeyboardInterrupt",
            )
            raise
        self.events.append(
            "attempt.process_exit",
            run_id=run_id,
            task_id=case["task_id"],
            system=case["system_id"],
            exit_code=result.returncode,
        )
        state, run, reason = inspect_attempt(
            directory,
            task_id=case["task_id"],
            system_id=case["system_id"],
            run_id=run_id,
            replacement_for=replacement_for,
        )
        state, run, reason = self.reconcile_observability_boundary(
            case,
            ordinal=ordinal,
            replacement_for=replacement_for,
            state=state,
            run=run,
            reason=reason,
        )
        if state == "complete":
            assert run is not None
            self.events.append(
                "attempt.artifact_gate_passed",
                run_id=run_id,
                task_id=case["task_id"],
                system=case["system_id"],
                exit_code=result.returncode,
                run_validity=run.get("run_validity"),
                verify_status=run.get("verify_status"),
            )
        else:
            self.events.append(
                "attempt.evidence_incomplete",
                run_id=run_id,
                task_id=case["task_id"],
                system=case["system_id"],
                exit_code=result.returncode,
                reason=reason,
            )
        return state, run, reason

    def reconcile_observability_boundary(
        self,
        case: dict[str, Any],
        *,
        ordinal: int,
        replacement_for: str | None,
        state: str,
        run: dict[str, Any] | None,
        reason: str | None,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        if state != "recoverable":
            return state, run, reason
        assert self.events is not None
        if run is None or reason != HERMES_SUCCESSFUL_DRAIN_POLICY:
            raise RerunBlocked("recoverable attempt has no qualified reconciliation")
        run_id = case["target_run_ids"][ordinal - 1]
        directory = self.attempt_path(case, run_id)
        self.events.append(
            "attempt.observability_reconciliation_start",
            case_sequence=case["sequence"],
            position=case["position"],
            task_id=case["task_id"],
            system=case["system_id"],
            run_id=run_id,
            attempt_ordinal=ordinal,
            replacement_for_run_id=replacement_for,
            policy=HERMES_SUCCESSFUL_DRAIN_POLICY,
            agent_rerun=False,
            evaluator_rerun=False,
            formal_result_mutation=False,
        )
        try:
            _, reconciliation = recover_successful_hermes_drain_race(
                directory, run
            )
            final_state, final_run, final_reason = inspect_attempt(
                directory,
                task_id=case["task_id"],
                system_id=case["system_id"],
                run_id=run_id,
                replacement_for=replacement_for,
            )
            if final_state != "complete" or final_run is None:
                raise RerunBlocked(
                    "reconciled attempt did not pass the artifact gate: "
                    f"{final_reason}"
                )
        except BaseException as exc:
            self.events.append(
                "attempt.observability_reconciliation_failed",
                task_id=case["task_id"],
                system=case["system_id"],
                run_id=run_id,
                policy=HERMES_SUCCESSFUL_DRAIN_POLICY,
                error=str(exc),
                error_type=type(exc).__name__,
                agent_rerun=False,
                evaluator_rerun=False,
                formal_result_mutation=False,
            )
            raise
        self.events.append(
            "attempt.observability_reconciliation_end",
            task_id=case["task_id"],
            system=case["system_id"],
            run_id=run_id,
            status="passed",
            policy=HERMES_SUCCESSFUL_DRAIN_POLICY,
            observability_artifact=reconciliation["observability_artifact"],
            observability_artifact_sha256=reconciliation[
                "observability_artifact_sha256"
            ],
            artifacts_manifest_sha256=reconciliation[
                "artifacts_manifest_sha256"
            ],
            agent_rerun=False,
            evaluator_rerun=False,
            formal_result_mutation=False,
        )
        return "complete", final_run, None

    def inspect_existing(
        self,
        case: dict[str, Any],
        *,
        ordinal: int,
        replacement_for: str | None,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        run_id = case["target_run_ids"][ordinal - 1]
        state, run, reason = inspect_attempt(
            self.attempt_path(case, run_id),
            task_id=case["task_id"],
            system_id=case["system_id"],
            run_id=run_id,
            replacement_for=replacement_for,
        )
        return self.reconcile_observability_boundary(
            case,
            ordinal=ordinal,
            replacement_for=replacement_for,
            state=state,
            run=run,
            reason=reason,
        )

    def incomplete_is_pre_agent_infrastructure(
        self, case: dict[str, Any], run_id: str, directory: Path
    ) -> bool:
        assert self.events is not None
        rows = self.events.rows_for_run(run_id)
        if any(row.get("event") == "attempt.process_interrupted" for row in rows):
            return False
        return (
            any(row.get("event") == "attempt.process_exit" for row in rows)
            and not lifecycle_has_adapter_start(directory)
        )

    def complete_case(self, case: dict[str, Any]) -> dict[str, Any]:
        assert self.events is not None
        a1 = case["target_run_ids"][0]
        a2 = case["target_run_ids"][1]
        state1, run1, reason1 = self.inspect_existing(
            case, ordinal=1, replacement_for=None
        )
        if state1 == "absent":
            state1, run1, reason1 = self.run_attempt(
                case, ordinal=1, replacement_for=None
            )
        replacement_reason: str | None = None
        if state1 == "complete":
            assert run1 is not None
            if run1.get("run_validity") == "infra_invalid":
                replacement_reason = "rerun_a1_infra_invalid"
            else:
                return self.case_result(case, effective_run=run1, attempts=[run1])
        elif state1 == "incomplete":
            directory = self.attempt_path(case, a1)
            if self.incomplete_is_pre_agent_infrastructure(case, a1, directory):
                replacement_reason = "rerun_a1_pre_agent_infrastructure_failure"
            else:
                raise RerunBlocked(f"incomplete a1 cannot be replaced: {directory}: {reason1}")
        else:
            raise RerunBlocked(f"unexpected a1 state for {case['task_id']}/{case['system_id']}")

        self.events.append(
            "slot.replacement_authorized",
            case_sequence=case["sequence"],
            position=case["position"],
            task_id=case["task_id"],
            system=case["system_id"],
            original_run_id=a1,
            replacement_run_id=a2,
            reason=replacement_reason,
            automatic_replacement_ordinal=1,
        )
        state2, run2, reason2 = self.inspect_existing(
            case, ordinal=2, replacement_for=a1
        )
        if state2 == "absent":
            state2, run2, reason2 = self.run_attempt(
                case, ordinal=2, replacement_for=a1
            )
        if state2 != "complete" or run2 is None:
            raise RerunBlocked(
                f"the one allowed replacement is incomplete: {self.attempt_path(case, a2)}: {reason2}"
            )
        attempts = [item for item in (run1, run2) if item is not None]
        return self.case_result(
            case,
            effective_run=run2,
            attempts=attempts,
            replacement_reason=replacement_reason,
            replacement_exhausted=run2.get("run_validity") == "infra_invalid",
        )

    def case_result(
        self,
        case: dict[str, Any],
        *,
        effective_run: dict[str, Any],
        attempts: list[dict[str, Any]],
        replacement_reason: str | None = None,
        replacement_exhausted: bool = False,
    ) -> dict[str, Any]:
        result = {
            "sequence": case["sequence"],
            "position": case["position"],
            "task_id": case["task_id"],
            "system_id": case["system_id"],
            "source_formal_run_id": case["source_run_id"],
            "source_verify_status": case["source_verify_status"],
            "source_run_validity": case["source_run_validity"],
            "effective_run_id": effective_run["run_id"],
            "effective_run_directory": str(
                self.attempt_path(case, effective_run["run_id"])
            ),
            "verify_status": effective_run.get("verify_status"),
            "run_validity": effective_run.get("run_validity"),
            "terminal_status": effective_run.get("terminal_status"),
            "primary_failure_category": effective_run.get(
                "primary_failure_category"
            ),
            "candidate_run_ids": [item["run_id"] for item in attempts],
            "replacement_reason": replacement_reason,
            "replacement_exhausted": replacement_exhausted,
            "formal_result_mutation": False,
        }
        assert self.events is not None
        self.events.append(
            "slot.complete",
            case_sequence=case["sequence"],
            position=case["position"],
            task_id=case["task_id"],
            system=case["system_id"],
            effective_run_id=effective_run["run_id"],
            verify_status=effective_run.get("verify_status"),
            run_validity=effective_run.get("run_validity"),
            formal_result_mutation=False,
        )
        self.checkpoint(
            "running",
            completed_case_count=case["sequence"],
            last_completed_task=case["task_id"],
            last_completed_system=case["system_id"],
        )
        return result

    def write_final(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        assert self.events is not None
        self.events.append(
            "batch.complete",
            selected_case_count=len(self.cases),
            completed_case_count=len(results),
            formal_result_mutation=False,
        )
        self.checkpoint("GO", completed_case_count=len(results))
        verify_counts = Counter(str(item.get("verify_status")) for item in results)
        validity_counts = Counter(str(item.get("run_validity")) for item in results)
        report = {
            "schema_version": REPORT_SCHEMA,
            "created_at": utc_now(),
            "status": "GO",
            "batch_id": self.manifest["batch_id"],
            "experiment_id": self.manifest["experiment_id"],
            "policy": self.manifest["policy"],
            "policy_sha256": self.manifest["policy_sha256"],
            "formal_result_mutation": False,
            "result_use": "posthoc_sensitivity_only",
            "selected_case_count": len(self.cases),
            "completed_case_count": len(results),
            "automatic_replacement_count": sum(
                item.get("replacement_reason") is not None for item in results
            ),
            "replacement_exhausted_count": sum(
                item.get("replacement_exhausted") is True for item in results
            ),
            "verify_status": dict(sorted(verify_counts.items())),
            "run_validity": dict(sorted(validity_counts.items())),
            "cases": results,
        }
        write_object(self.report_path, report)
        self.report_hash_path.write_text(
            f"{sha256_file(self.report_path)}  {self.report_path.name}\n",
            encoding="utf-8",
        )
        batch_paths = (
            self.manifest_path,
            self.events_path,
            self.checkpoint_path,
            self.report_path,
            self.report_hash_path,
        )
        self.batch_hash_path.write_text(
            "".join(
                f"{sha256_file(path)}  {path.name}\n" for path in batch_paths
            ),
            encoding="utf-8",
        )
        return report

    def run(self) -> dict[str, Any]:
        self.initialize()
        if self.checkpoint_path.exists() and read_object(self.checkpoint_path).get("status") == "GO":
            if not self.report_path.is_file() or not self.batch_hash_path.is_file():
                raise RerunBlocked("GO checkpoint has no final qualification evidence")
            return read_object(self.report_path)
        results: list[dict[str, Any]] = []
        try:
            for case in self.manifest["cases"]:
                results.append(self.complete_case(case))
            return self.write_final(results)
        except KeyboardInterrupt:
            assert self.events is not None
            self.events.append("batch.interrupted", error_type="KeyboardInterrupt")
            self.checkpoint("blocked", error="user interruption", error_type="KeyboardInterrupt")
            raise
        except Exception as exc:
            assert self.events is not None
            self.events.append(
                "batch.blocked", error=str(exc), error_type=type(exc).__name__
            )
            self.checkpoint("blocked", error=str(exc), error_type=type(exc).__name__)
            raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--m1-root", type=Path, required=True)
    parser.add_argument("--m2-root", type=Path, required=True)
    parser.add_argument("--m3-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    source_root = args.source_root.resolve()
    m1_root = args.m1_root.resolve()
    m2_root = args.m2_root.resolve()
    m3_root = args.m3_root.resolve()
    policy_path = args.policy.resolve()
    if repo_root != Path("/home/vagrant/moi-benchmark"):
        raise RerunBlocked("unexpected repository root")
    policy, cases = validate_policy(
        policy_path,
        repo_root=repo_root,
        m1_root=m1_root,
        m2_root=m2_root,
        m3_root=m3_root,
        source_root=source_root,
    )
    output_root = validate_output_root(
        args.output_root, (m1_root, m2_root, m3_root, source_root)
    )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "GO",
                    "mode": "dry_run",
                    "selected_case_count": len(cases),
                    "system_counts": dict(
                        sorted(Counter(item["system_id"] for item in cases).items())
                    ),
                    "infra_invalid_source_count": sum(
                        item["source_run_validity"] == "infra_invalid"
                        for item in cases
                    ),
                    "formal_result_mutation": False,
                    "output_root": str(output_root),
                    "cases": [
                        {
                            "sequence": item["sequence"],
                            "position": item["position"],
                            "task_id": item["task_id"],
                            "system_id": item["system_id"],
                            "source_run_id": item["source_run_id"],
                            "source_verify_status": item["source_verify_status"],
                            "source_run_validity": item["source_run_validity"],
                        }
                        for item in cases
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    scheduler = Scheduler(
        repo_root=repo_root,
        source_root=source_root,
        output_root=output_root,
        policy_path=policy_path,
        policy=policy,
        cases=cases,
        roots={"m1": m1_root, "m2": m2_root, "m3": m3_root},
    )
    report = scheduler.run()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except RerunBlocked as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
