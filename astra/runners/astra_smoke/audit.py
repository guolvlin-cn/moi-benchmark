from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from astra.runners.astra_smoke.core import CLEAN, PROCESS_KILL


_RECOVERY_PENDING_SHA256 = hashlib.sha256(
    (
        '{"attempt":1,"expected_result":"astra-lifecycle-smoke:complete",'
        '"resume_command":"/usr/local/bin/astra-smoke-workload",'
        '"status":"resume-required"}\n'
    ).encode("utf-8")
).hexdigest()
_RECOVERY_COMPLETE_SHA256 = hashlib.sha256(
    (
        '{"attempt":2,"expected_result":"astra-lifecycle-smoke:complete",'
        '"resume_command":"/usr/local/bin/astra-smoke-workload",'
        '"status":"complete"}\n'
    ).encode("utf-8")
).hexdigest()
_TERMINAL_RESULT_SHA256 = hashlib.sha256(
    b"astra-lifecycle-smoke:complete\n"
).hexdigest()


class AuditError(RuntimeError):
    """Persisted smoke evidence is missing, inconsistent, or unsuccessful."""


def _event(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get("event") == name]
    if len(matches) != 1:
        raise AuditError(f"expected exactly one {name!r} event, found {len(matches)}")
    return matches[0]


def _assert_order(rows: list[dict[str, Any]], names: list[str]) -> None:
    positions = {name: _event(rows, name)["sequence"] for name in names}
    ordered = [positions[name] for name in names]
    if ordered != sorted(ordered):
        raise AuditError(f"events are out of order: {names}")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read controller ledger {path}: {exc}") from exc
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise AuditError("controller ledger must contain JSON objects")
    return rows


def _validate_envelope(rows: list[dict[str, Any]]) -> None:
    expected_sequence = list(range(1, len(rows) + 1))
    if [row.get("sequence") for row in rows] != expected_sequence:
        raise AuditError("ledger sequence is not contiguous from 1")
    run_ids = {row.get("run_id") for row in rows}
    if len(run_ids) != 1 or not next(iter(run_ids)):
        raise AuditError("ledger must contain one non-empty run_id")
    monotonic_values = [row.get("monotonic_ns") for row in rows]
    if not all(isinstance(value, int) for value in monotonic_values):
        raise AuditError("ledger is missing integer monotonic_ns values")
    if monotonic_values != sorted(monotonic_values):
        raise AuditError("ledger monotonic timestamps moved backwards")
    for row in rows:
        if row.get("schema_version") != 1:
            raise AuditError("unsupported ledger schema version")
        try:
            timestamp = datetime.fromisoformat(str(row["timestamp"]))
        except (KeyError, ValueError) as exc:
            raise AuditError("ledger has an invalid wall-clock timestamp") from exc
        if timestamp.tzinfo is None:
            raise AuditError("ledger wall-clock timestamps must be timezone-aware")


def _validate_reward(ledger_path: Path) -> float:
    reward_path = ledger_path.parent.parent / "verifier" / "reward.txt"
    try:
        reward = float(reward_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise AuditError(f"cannot read Harbor reward at {reward_path}: {exc}") from exc
    if reward != 1.0:
        raise AuditError(f"Harbor verifier reward is {reward}, expected 1")
    return reward


def audit_ledger(path: Path, *, require_reward: bool = True) -> dict[str, Any]:
    rows = _load_rows(path)
    _validate_envelope(rows)

    started = _event(rows, "controller_started")
    completed = _event(rows, "controller_completed")
    condition = started.get("condition")
    if condition not in {CLEAN, PROCESS_KILL}:
        raise AuditError(f"unknown condition {condition!r}")
    if rows[0] is not started or rows[-1] is not completed:
        raise AuditError("controller_started/controller_completed must bound the ledger")
    if started.get("fault_scope") != "astra_cli_process_tree":
        raise AuditError("unexpected fault scope")
    if not started.get("artifact_arch") or not started.get("artifact_sha256"):
        raise AuditError("controller did not pin the Linux Astra artifact")
    expected_hashes = {
        "recovery_pending_sha256": _RECOVERY_PENDING_SHA256,
        "recovery_complete_sha256": _RECOVERY_COMPLETE_SHA256,
        "terminal_result_sha256": _TERMINAL_RESULT_SHA256,
    }
    for field, expected in expected_hashes.items():
        if started.get(field) != expected:
            raise AuditError(f"controller pinned an unexpected {field}")

    api = _event(rows, "api_preflight_completed")
    auth = _event(rows, "auth_preflight_completed")
    handshake = _event(rows, "handshake_completed")
    task_started = _event(rows, "task_turn_started")
    registered = _event(rows, "product_process_registered")
    trigger = _event(rows, "trigger_observed")
    action = _event(rows, "fault_action")
    task_exited = _event(rows, "task_turn_exited")
    session_id = handshake.get("session_id")
    try:
        uuid.UUID(str(session_id))
    except ValueError as exc:
        raise AuditError("handshake session_id is not a UUID") from exc

    if api.get("reachable") is not True or api.get("return_code") != 0:
        raise AuditError("container-to-Astra API preflight failed")
    if auth.get("authenticated") is not True or auth.get("return_code") != 0:
        raise AuditError("container-to-Astra authentication preflight failed")
    if handshake.get("tool_calls_count") != 0:
        raise AuditError("handshake used tools")
    if task_started.get("session_id") != session_id:
        raise AuditError("task turn did not use the handshake session")
    if completed.get("session_id") != session_id:
        raise AuditError("controller completion changed session_id")
    if trigger.get("predicate") != "path_exists":
        raise AuditError("unexpected trigger predicate")
    if not (
        registered.get("pid")
        == registered.get("pgid")
        == registered.get("sid")
    ):
        raise AuditError("registered Astra process is not a group/session leader")
    if (
        not isinstance(registered.get("supervisor_pid"), int)
        or registered["supervisor_pid"] <= 1
        or registered["supervisor_pid"] == registered["pid"]
        or registered.get("ppid") != registered["supervisor_pid"]
    ):
        raise AuditError("registered Astra process has an invalid supervisor")
    if task_exited.get("trigger_hit") is not True:
        raise AuditError("task exited without the registered trigger")
    if completed.get("lifecycle_gate_passed") is not True:
        raise AuditError("controller lifecycle gate did not pass")
    if completed.get("astra_turn_success") is not True:
        raise AuditError("Astra turn did not finish successfully")

    common_order = [
        "controller_started",
        "api_preflight_completed",
        "auth_preflight_completed",
        "handshake_turn_started",
        "handshake_turn_exited",
        "handshake_completed",
        "task_turn_started",
        "product_process_registered",
        "trigger_observed",
        "fault_action",
        "task_turn_exited",
    ]

    if condition == CLEAN:
        if action.get("action") != "noop" or action.get("executed") is not True:
            raise AuditError("C0 did not execute its registered no-op")
        if task_exited.get("return_code") != 0:
            raise AuditError("C0 Astra task turn did not exit cleanly")
        if task_exited.get("fault_injected") is not False:
            raise AuditError("C0 unexpectedly records a fault")
        _assert_order(rows, [*common_order, "controller_completed"])
    else:
        environment_probe = _event(rows, "task_environment_post_fault_probe")
        post_fault_checkpoint = _event(
            rows, "workspace_checkpoint_post_fault_probe"
        )
        post_fault_artifact = _event(rows, "terminal_artifact_post_fault_probe")
        relaunch_started = _event(rows, "same_session_relaunch_started")
        relaunch_exited = _event(rows, "relaunch_turn_exited")
        post_relaunch_checkpoint = _event(
            rows, "workspace_checkpoint_post_relaunch_probe"
        )
        post_relaunch_artifact = _event(
            rows, "terminal_artifact_post_relaunch_probe"
        )
        relaunch_completed = _event(rows, "same_session_relaunch_completed")
        if action.get("action") != "freeze_kill_tree_sigkill":
            raise AuditError("F1 did not freeze and kill the registered process tree")
        if action.get("executed") is not True:
            raise AuditError("F1 kill action was not executed")
        if (
            action.get("return_code") != 0
            or action.get("root_pid") != registered["pid"]
        ):
            raise AuditError("F1 kill did not target the registered root")
        targeted_tree = action.get("targeted_tree_pids")
        targeted_descendants = action.get("targeted_descendant_pids")
        if (
            not isinstance(targeted_tree, list)
            or registered["pid"] not in targeted_tree
            or not all(isinstance(pid, int) for pid in targeted_tree)
        ):
            raise AuditError("F1 evidence does not include the registered root")
        if (
            not isinstance(targeted_descendants, list)
            or not targeted_descendants
            or not all(
                isinstance(pid, int)
                and pid in targeted_tree
                and pid != registered["pid"]
                for pid in targeted_descendants
            )
        ):
            raise AuditError("F1 evidence has no registered product descendants")
        if action.get("supervisor_pid") != registered["supervisor_pid"]:
            raise AuditError("F1 kill used a different process-tree supervisor")
        if (
            not isinstance(action.get("freeze_rounds"), int)
            or action["freeze_rounds"] < 2
        ):
            raise AuditError("F1 process tree was not frozen to a stable boundary")
        if action.get("surviving_tree_pids") != []:
            raise AuditError("registered process-tree members survived F1")
        if action.get("signal_errors") != []:
            raise AuditError("F1 process-tree signaling was incomplete")
        if task_exited.get("return_code") == 0:
            raise AuditError("F1 killed turn unexpectedly exited zero")
        if task_exited.get("fault_injected") is not True:
            raise AuditError("F1 task exit does not record an injected fault")
        if environment_probe.get("alive") is not True:
            raise AuditError("Harbor task environment did not survive F1")
        if (
            post_fault_checkpoint.get("present") is not True
            or post_fault_checkpoint.get("matches_expected") is not True
            or post_fault_checkpoint.get("sha256") != _RECOVERY_PENDING_SHA256
        ):
            raise AuditError("F1 did not preserve the pending recovery checkpoint")
        if post_fault_artifact.get("absent") is not True:
            raise AuditError("F1 terminal artifact existed before relaunch")
        if relaunch_started.get("session_id") != session_id:
            raise AuditError("F1 relaunch changed session_id")
        if (
            relaunch_exited.get("return_code") != 0
            or relaunch_exited.get("success") is not True
        ):
            raise AuditError("F1 relaunch turn did not exit successfully")
        if (
            type(relaunch_exited.get("tool_calls_count")) is not int
            or relaunch_exited["tool_calls_count"] <= 0
        ):
            raise AuditError("F1 relaunch performed no recovery tool action")
        if (
            post_relaunch_checkpoint.get("present") is not True
            or post_relaunch_checkpoint.get("matches_expected") is not True
            or post_relaunch_checkpoint.get("sha256")
            != _RECOVERY_COMPLETE_SHA256
        ):
            raise AuditError("F1 relaunch did not complete the recovery checkpoint")
        if (
            post_relaunch_artifact.get("present") is not True
            or post_relaunch_artifact.get("matches_expected") is not True
            or post_relaunch_artifact.get("sha256") != _TERMINAL_RESULT_SHA256
        ):
            raise AuditError("F1 relaunch did not create the expected terminal artifact")
        if relaunch_completed.get("session_id") != session_id:
            raise AuditError("F1 completion changed session_id")
        if relaunch_completed.get("success") is not True:
            raise AuditError("F1 same-session relaunch did not succeed")
        if relaunch_completed.get("tool_calls_count") != relaunch_exited.get(
            "tool_calls_count"
        ):
            raise AuditError("F1 relaunch tool count changed across evidence")
        _assert_order(
            rows,
            [
                *common_order[:-1],
                "task_environment_post_fault_probe",
                "task_turn_exited",
                "workspace_checkpoint_post_fault_probe",
                "terminal_artifact_post_fault_probe",
                "same_session_relaunch_started",
                "relaunch_turn_started",
                "relaunch_turn_exited",
                "workspace_checkpoint_post_relaunch_probe",
                "terminal_artifact_post_relaunch_probe",
                "same_session_relaunch_completed",
                "controller_completed",
            ],
        )

    reward = _validate_reward(path) if require_reward else None
    return {
        "condition": condition,
        "session_id": session_id,
        "artifact_arch": started["artifact_arch"],
        "artifact_sha256": started["artifact_sha256"],
        "event_count": len(rows),
        "reward": reward,
        "status": "pass",
    }


def _ledger_paths(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    paths = sorted(target.rglob("agent/controller.jsonl"))
    if not paths:
        raise AuditError(f"no agent/controller.jsonl found below {target}")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit persisted Astra smoke evidence")
    parser.add_argument("target", type=Path, help="controller.jsonl or Harbor job directory")
    parser.add_argument(
        "--no-reward",
        action="store_true",
        help="skip Harbor reward validation (intended only for unit tests)",
    )
    args = parser.parse_args()
    try:
        summaries = [
            {
                "ledger": str(path),
                **audit_ledger(path, require_reward=not args.no_reward),
            }
            for path in _ledger_paths(args.target)
        ]
    except AuditError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summaries, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
