import tempfile
import unittest
import uuid
from pathlib import Path

from astra.runners.astra_smoke.audit import (
    AuditError,
    _RECOVERY_COMPLETE_SHA256,
    _RECOVERY_PENDING_SHA256,
    _TERMINAL_RESULT_SHA256,
    audit_ledger,
)
from astra.runners.astra_smoke.core import CLEAN, PROCESS_KILL, JsonlLedger


class AuditTests(unittest.TestCase):
    def _ledger(self, condition):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "trial" / "agent" / "controller.jsonl"
        ledger = JsonlLedger(path, "run-1")
        session_id = str(uuid.uuid4())
        ledger.append(
            "controller_started",
            condition=condition,
            fault_scope="astra_cli_process_tree",
            artifact_arch="aarch64",
            artifact_sha256="a" * 64,
            recovery_pending_sha256=_RECOVERY_PENDING_SHA256,
            recovery_complete_sha256=_RECOVERY_COMPLETE_SHA256,
            terminal_result_sha256=_TERMINAL_RESULT_SHA256,
        )
        ledger.append("api_preflight_completed", reachable=True, return_code=0)
        ledger.append("auth_preflight_completed", authenticated=True, return_code=0)
        ledger.append("handshake_turn_started", session_id=None)
        ledger.append("handshake_turn_exited", return_code=0, success=True)
        ledger.append(
            "handshake_completed", session_id=session_id, tool_calls_count=0
        )
        ledger.append("task_turn_started", session_id=session_id)
        ledger.append(
            "product_process_registered",
            pid=42,
            ppid=40,
            pgid=42,
            sid=42,
            start_ticks=9,
            exe="/installed-agent/astra",
            supervisor_pid=40,
        )
        ledger.append("trigger_observed", predicate="path_exists")
        return directory, path, ledger, session_id

    def test_accepts_c0_evidence(self):
        directory, path, ledger, session_id = self._ledger(CLEAN)
        with directory:
            ledger.append("fault_action", action="noop", executed=True)
            ledger.append(
                "task_turn_exited",
                return_code=0,
                trigger_hit=True,
                fault_injected=False,
            )
            ledger.append(
                "controller_completed",
                session_id=session_id,
                lifecycle_gate_passed=True,
                astra_turn_success=True,
            )
            summary = audit_ledger(path, require_reward=False)
            self.assertEqual(summary["condition"], CLEAN)
            self.assertEqual(summary["session_id"], session_id)

    def test_accepts_f1_same_session_evidence(self):
        directory, path, ledger, session_id = self._ledger(PROCESS_KILL)
        with directory:
            ledger.append(
                "fault_action",
                action="freeze_kill_tree_sigkill",
                executed=True,
                return_code=0,
                root_pid=42,
                supervisor_pid=40,
                freeze_rounds=2,
                targeted_tree_pids=[42, 43],
                targeted_descendant_pids=[43],
                surviving_tree_pids=[],
                signal_errors=[],
            )
            ledger.append("task_environment_post_fault_probe", alive=True)
            ledger.append(
                "task_turn_exited",
                return_code=137,
                trigger_hit=True,
                fault_injected=True,
            )
            ledger.append(
                "workspace_checkpoint_post_fault_probe",
                present=True,
                sha256=_RECOVERY_PENDING_SHA256,
                matches_expected=True,
            )
            ledger.append("terminal_artifact_post_fault_probe", absent=True)
            ledger.append("same_session_relaunch_started", session_id=session_id)
            ledger.append("relaunch_turn_started", session_id=session_id)
            ledger.append(
                "relaunch_turn_exited",
                return_code=0,
                success=True,
                tool_calls_count=2,
            )
            ledger.append(
                "workspace_checkpoint_post_relaunch_probe",
                present=True,
                sha256=_RECOVERY_COMPLETE_SHA256,
                matches_expected=True,
            )
            ledger.append(
                "terminal_artifact_post_relaunch_probe",
                present=True,
                sha256=_TERMINAL_RESULT_SHA256,
                matches_expected=True,
            )
            ledger.append(
                "same_session_relaunch_completed",
                session_id=session_id,
                success=True,
                tool_calls_count=2,
            )
            ledger.append(
                "controller_completed",
                session_id=session_id,
                lifecycle_gate_passed=True,
                astra_turn_success=True,
            )
            summary = audit_ledger(path, require_reward=False)
            self.assertEqual(summary["condition"], PROCESS_KILL)

    def test_rejects_f1_terminal_artifact_present_before_relaunch(self):
        directory, path, ledger, session_id = self._ledger(PROCESS_KILL)
        with directory:
            ledger.append(
                "fault_action",
                action="freeze_kill_tree_sigkill",
                executed=True,
                return_code=0,
                root_pid=42,
                supervisor_pid=40,
                freeze_rounds=2,
                targeted_tree_pids=[42, 43],
                targeted_descendant_pids=[43],
                surviving_tree_pids=[],
                signal_errors=[],
            )
            ledger.append("task_environment_post_fault_probe", alive=True)
            ledger.append(
                "task_turn_exited",
                return_code=137,
                trigger_hit=True,
                fault_injected=True,
            )
            ledger.append(
                "workspace_checkpoint_post_fault_probe",
                present=True,
                sha256=_RECOVERY_PENDING_SHA256,
                matches_expected=True,
            )
            ledger.append("terminal_artifact_post_fault_probe", absent=False)
            ledger.append("same_session_relaunch_started", session_id=session_id)
            ledger.append("relaunch_turn_started", session_id=session_id)
            ledger.append(
                "relaunch_turn_exited",
                return_code=0,
                success=True,
                tool_calls_count=1,
            )
            ledger.append(
                "workspace_checkpoint_post_relaunch_probe",
                present=True,
                sha256=_RECOVERY_COMPLETE_SHA256,
                matches_expected=True,
            )
            ledger.append(
                "terminal_artifact_post_relaunch_probe",
                present=True,
                sha256=_TERMINAL_RESULT_SHA256,
                matches_expected=True,
            )
            ledger.append(
                "same_session_relaunch_completed",
                session_id=session_id,
                success=True,
                tool_calls_count=1,
            )
            ledger.append(
                "controller_completed",
                session_id=session_id,
                lifecycle_gate_passed=True,
                astra_turn_success=True,
            )
            with self.assertRaises(AuditError):
                audit_ledger(path, require_reward=False)

    def test_rejects_no_hit(self):
        directory, path, ledger, session_id = self._ledger(CLEAN)
        with directory:
            ledger.append("fault_action", action="noop", executed=True)
            ledger.append(
                "task_turn_exited",
                return_code=0,
                trigger_hit=False,
                fault_injected=False,
            )
            ledger.append(
                "controller_completed",
                session_id=session_id,
                lifecycle_gate_passed=True,
                astra_turn_success=True,
            )
            with self.assertRaises(AuditError):
                audit_ledger(path, require_reward=False)
