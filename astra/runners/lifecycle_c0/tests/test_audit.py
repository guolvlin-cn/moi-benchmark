from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from astra.runners.lifecycle_c0.audit import (
    AuditError,
    audit_target,
    audit_trial,
    main,
)
from astra.runners.lifecycle_c0.core import JsonlLedger


class C0AuditTests(unittest.TestCase):
    def _create_trial(
        self,
        root: Path,
        name: str,
        *,
        trigger_hit: bool,
        reward: float = 1.0,
        exception_info=None,
        extra_event: str | None = None,
        duplicate_noop: bool = False,
        noop_extra_fields: dict | None = None,
    ) -> tuple[Path, Path]:
        trial_dir = root / "job" / name
        ledger_path = trial_dir / "agent" / "controller.jsonl"
        task_id = "build-pmars"
        predicate_id = "terminal-bench.build-pmars.source-before-install"
        stable_observations = 2
        manifest_payload = {
            "predicate_id": predicate_id,
            "stable_observations": stable_observations,
            "task_id": task_id,
        }
        manifest_sha256 = hashlib.sha256(
            json.dumps(
                manifest_payload, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        probe_sha256 = "a" * 64
        evidence = {"files": ["pmars.c"], "phase": "source"}
        evidence_sha256 = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        trigger_reason = "clean_noop" if trigger_hit else "product_completed"
        cleanup_report = {
            "schema_version": 1,
            "status": "clean",
            "reason": "normal_exit",
            "fault_action": False,
            "product_terminal_status": "completed",
            "zero_live_proven": True,
            "remaining_pids_count": 0,
            "remaining_pids": [],
        }
        cleanup_report_raw = (
            json.dumps(cleanup_report, sort_keys=True) + "\n"
        )
        cleanup_sha256 = hashlib.sha256(
            cleanup_report_raw.encode()
        ).hexdigest()
        metadata = {
            "condition": "C0",
            "fault_action": "noop",
            "fault_injected": False,
            "task_id": task_id,
            "trigger_id": predicate_id,
            "trigger_manifest_sha256": manifest_sha256,
            "predicate_probe_sha256": probe_sha256,
            "controller_ledger": str(ledger_path),
            "trigger_hit": trigger_hit,
            "trigger_reason": trigger_reason,
            "trigger_evidence_sha256": (
                evidence_sha256 if trigger_hit else None
            ),
            "lifecycle_gate_passed": trigger_hit,
            "product_terminal_status": "completed",
            "product_cleanup_zero_live_proven": True,
            "product_cleanup_report_sha256": cleanup_sha256,
        }

        ledger = JsonlLedger(ledger_path, f"run-{name}")
        ledger.append(
            "controller_started",
            product="synthetic",
            **metadata,
        )
        ledger.append(
            "product_preflight",
            check="health",
            passed=True,
            return_code=0,
        )
        ledger.append(
            "trigger_armed",
            task_id=task_id,
            predicate_id=predicate_id,
            trigger_manifest_sha256=manifest_sha256,
        )
        ledger.append("product_turn_started")
        ledger.append(
            "lifecycle_controller_started",
            condition="C0",
            fault_action="noop",
            source="terminal-bench",
            task_id=task_id,
            predicate_id=predicate_id,
            predicate_probe_source_sha256=probe_sha256,
            trigger_manifest_sha256=manifest_sha256,
            stable_observations=stable_observations,
        )
        if trigger_hit:
            ledger.append(
                "product_process_registered",
                pid=40,
                ppid=39,
                pgid=40,
                sid=40,
                start_ticks=100,
                exe="/installed-agent/product",
                supervisor_pid=39,
                identity_sha256="b" * 64,
                cgroup_sha256="d" * 64,
            )
            ledger.append(
                "trigger_observed",
                task_id=task_id,
                predicate_id=predicate_id,
                stable_observations=stable_observations,
                evidence=evidence,
                evidence_sha256=evidence_sha256,
            )
            ledger.append(
                "fault_action",
                action="noop",
                executed=True,
                **(noop_extra_fields or {}),
            )
            if duplicate_noop:
                ledger.append("fault_action", action="noop", executed=True)
        else:
            ledger.append("trigger_no_hit", reason=trigger_reason)
        if extra_event:
            ledger.append(extra_event)
        ledger.append(
            "product_process_cleanup",
            reason="normal_exit",
            product_terminal_status="completed",
            zero_live_proven=True,
            remaining_pids_count=0,
            cleanup_report_sha256=cleanup_sha256,
            fault_action=False,
        )
        ledger.append(
            "product_turn_exited",
            return_code=0,
            error_type=None,
            product_terminal_status="completed",
        )
        ledger.append(
            "controller_completed",
            trigger_hit=trigger_hit,
            fault_injected=False,
            lifecycle_gate_passed=trigger_hit,
            product_completion_claim=True,
            product_return_code=0,
            product_terminal_status="completed",
            product_cleanup_zero_live_proven=True,
        )
        (trial_dir / "agent" / "product.cleanup.json").write_text(
            cleanup_report_raw,
            encoding="utf-8",
        )

        result_path = trial_dir / "result.json"
        result_path.write_text(
            json.dumps(
                {
                    "id": f"id-{name}",
                    "trial_name": name,
                    "task_name": f"local/{task_id}",
                    "agent_result": {"metadata": metadata},
                    "verifier_result": {"rewards": {"reward": reward}},
                    "exception_info": exception_info,
                }
            ),
            encoding="utf-8",
        )
        return result_path, ledger_path

    def _attach_astra_trajectory(
        self,
        result_path: Path,
        ledger_path: Path,
    ) -> tuple[str, Path]:
        session_id = "11111111-1111-4111-8111-111111111111"
        agent_dir = result_path.parent / "agent"
        trajectory_root = agent_dir / "astra-trajectory"
        owner_root = (
            trajectory_root
            / "local-sessions"
            / "v1"
            / "users"
            / "b64-user"
            / "sessions"
        )
        session_dir = owner_root / session_id
        session_dir.mkdir(parents=True)
        journal_path = owner_root / f"{session_id}.jsonl"
        journal_path.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "session_start",
                            "session_id": session_id,
                        }
                    ),
                    json.dumps(
                        {
                            "type": "turn",
                            "session_id": session_id,
                        }
                    ),
                    json.dumps(
                        {
                            "type": "session_end",
                            "session_id": session_id,
                        }
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (session_dir / "step_events.jsonl").write_text(
            '{"event_type":"StepStarted"}\n',
            encoding="utf-8",
        )
        server_session_path = trajectory_root / "server-session.json"
        server_session_path.write_text(
            json.dumps({"session_id": session_id}),
            encoding="utf-8",
        )
        server_events_path = trajectory_root / "server-events.jsonl"
        server_events_path.write_text(
            json.dumps(
                {
                    "event_id": "event-1",
                    "session_id": session_id,
                    "event_type": "turn",
                    "content": "complete event content",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        local_files = [
            {
                "path": str(path.relative_to(trajectory_root)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(
                (trajectory_root / "local-sessions").rglob("*")
            )
            if path.is_file()
        ]
        manifest_path = trajectory_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "session_id": session_id,
                    "product_terminal_status": "completed",
                    "failed": False,
                    "capture_status": "complete",
                    "server_session_saved": True,
                    "server_session_sha256": hashlib.sha256(
                        server_session_path.read_bytes()
                    ).hexdigest(),
                    "server_events_saved": True,
                    "server_event_count": 1,
                    "server_events_sha256": hashlib.sha256(
                        server_events_path.read_bytes()
                    ).hexdigest(),
                    "local_file_count": 2,
                    "local_trace_file_count": 2,
                    "tool_result_file_count": 0,
                    "local_journal_saved": True,
                    "local_journal_path": str(
                        journal_path.relative_to(trajectory_root)
                    ),
                    "local_journal_sha256": hashlib.sha256(
                        journal_path.read_bytes()
                    ).hexdigest(),
                    "local_journal_event_count": 3,
                    "local_journal_terminal_event": "session_end",
                    "local_files": local_files,
                    "errors": [],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        manifest_sha256 = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
        trajectory_file_count = 5
        (agent_dir / "astra-session-created.json").write_text(
            json.dumps({"session_id": session_id}),
            encoding="utf-8",
        )
        (agent_dir / "astra-session.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "astra_session_id": session_id,
                    "product_terminal_status": "completed",
                    "capture_status": "complete",
                    "failed": False,
                    "adapter_cancelled": False,
                }
            ),
            encoding="utf-8",
        )
        (agent_dir / "trajectory-status.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "astra_session_id": session_id,
                    "product_terminal_status": "completed",
                    "capture_status": "complete",
                    "capture_failed": False,
                    "failed": False,
                    "manifest_sha256": manifest_sha256,
                    "trajectory_file_count": trajectory_file_count,
                    "local_file_count": 2,
                    "local_trace_file_count": 2,
                    "tool_result_file_count": 0,
                    "server_event_count": 1,
                    "local_journal_event_count": 3,
                    "local_journal_terminal_event": "session_end",
                    "errors": [],
                }
            ),
            encoding="utf-8",
        )

        result = json.loads(result_path.read_text(encoding="utf-8"))
        metadata = result["agent_result"]["metadata"]
        metadata.update(
            {
                "product_completion_claim": True,
                "astra_session_id": session_id,
                "astra_trajectory_status": "complete",
                "astra_trajectory_capture_failed": False,
                "trajectory_capture_blocking": False,
                "astra_trajectory_manifest": (
                    "agent/astra-trajectory/manifest.json"
                ),
                "astra_trajectory_manifest_sha256": manifest_sha256,
                "astra_trajectory_file_count": trajectory_file_count,
                "astra_trajectory_local_file_count": 2,
                "astra_trajectory_local_trace_file_count": 2,
                "astra_trajectory_tool_result_file_count": 0,
                "astra_trajectory_server_event_count": 1,
                "astra_trajectory_local_journal_event_count": 3,
                "astra_trajectory_local_journal_terminal_event": (
                    "session_end"
                ),
            }
        )
        result_path.write_text(json.dumps(result), encoding="utf-8")

        rows = [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
        ]
        rows[0].update(
            {
                "product": "astra",
                "trajectory_capture_required": True,
                "trajectory_capture_mode": (
                    "astra_server_and_local_session"
                ),
                "trajectory_capture_blocking": False,
            }
        )
        registered = {
            "event": "astra_session_registered",
            "astra_session_id": session_id,
        }
        terminal = {
            "event": "astra_session_terminal",
            "astra_session_id": session_id,
            "product_terminal_status": "completed",
            "failed": False,
        }
        persisted = {
            "event": "astra_trajectory_persisted",
            "astra_session_id": session_id,
            "capture_status": "complete",
            "capture_failed": False,
            "failed": False,
            "manifest_path": "agent/astra-trajectory/manifest.json",
            "manifest_sha256": manifest_sha256,
            "trajectory_file_count": trajectory_file_count,
            "local_file_count": 2,
            "local_trace_file_count": 2,
            "tool_result_file_count": 0,
            "server_event_count": 1,
            "local_journal_event_count": 3,
            "local_journal_terminal_event": "session_end",
        }
        session_outcome = {
            "event": "astra_session_outcome",
            "astra_session_id": session_id,
            "product_terminal_status": "completed",
            "product_completion_claim": True,
            "failed": False,
        }
        trigger_armed_index = next(
            index
            for index, row in enumerate(rows)
            if row["event"] == "trigger_armed"
        )
        rows.insert(trigger_armed_index, registered)
        cleanup_index = next(
            index
            for index, row in enumerate(rows)
            if row["event"] == "product_process_cleanup"
        )
        rows[cleanup_index + 1:cleanup_index + 1] = [
            terminal,
            persisted,
        ]
        product_exited_index = next(
            index
            for index, row in enumerate(rows)
            if row["event"] == "product_turn_exited"
        )
        rows.insert(product_exited_index + 1, session_outcome)
        rows[-1].update(
            {
                "astra_session_id": session_id,
                "astra_trajectory_status": "complete",
                "astra_trajectory_capture_failed": False,
                "trajectory_capture_blocking": False,
                "astra_trajectory_manifest_sha256": manifest_sha256,
                "astra_trajectory_file_count": trajectory_file_count,
                "astra_trajectory_server_event_count": 1,
                "astra_trajectory_local_journal_event_count": 3,
                "astra_trajectory_local_journal_terminal_event": (
                    "session_end"
                ),
            }
        )
        envelope = rows[0]
        for sequence, row in enumerate(rows, 1):
            row.update(
                {
                    "schema_version": 1,
                    "sequence": sequence,
                    "run_id": envelope["run_id"],
                    "monotonic_ns": sequence,
                    "timestamp": envelope["timestamp"],
                }
            )
        ledger_path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        return session_id, journal_path

    def _degrade_astra_trajectory(
        self,
        result_path: Path,
        ledger_path: Path,
        *,
        status: str,
    ) -> None:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        metadata = result["agent_result"]["metadata"]
        rows = [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
        ]
        persisted = next(
            row for row in rows if row["event"] == "astra_trajectory_persisted"
        )
        completed = rows[-1]
        status_record_path = result_path.parent / "agent" / "trajectory-status.json"
        status_record = json.loads(status_record_path.read_text(encoding="utf-8"))
        session_record_path = result_path.parent / "agent" / "astra-session.json"
        session_record = json.loads(session_record_path.read_text(encoding="utf-8"))

        if status == "partial":
            terminal_event = "permission_audit"
            manifest_sha256 = metadata["astra_trajectory_manifest_sha256"]
            counts = {
                "trajectory_file_count": 5,
                "local_file_count": 2,
                "local_trace_file_count": 2,
                "tool_result_file_count": 0,
                "server_event_count": 1,
                "local_journal_event_count": 3,
            }
        elif status == "missing":
            terminal_event = None
            manifest_sha256 = None
            counts = {
                "trajectory_file_count": 0,
                "local_file_count": 0,
                "local_trace_file_count": 0,
                "tool_result_file_count": 0,
                "server_event_count": 0,
                "local_journal_event_count": 0,
            }
        else:
            raise ValueError(status)

        metadata.update(
            {
                "astra_trajectory_status": status,
                "astra_trajectory_capture_failed": True,
                "astra_trajectory_manifest_sha256": manifest_sha256,
                "astra_trajectory_file_count": counts["trajectory_file_count"],
                "astra_trajectory_local_file_count": counts["local_file_count"],
                "astra_trajectory_local_trace_file_count": counts[
                    "local_trace_file_count"
                ],
                "astra_trajectory_tool_result_file_count": counts[
                    "tool_result_file_count"
                ],
                "astra_trajectory_server_event_count": counts[
                    "server_event_count"
                ],
                "astra_trajectory_local_journal_event_count": counts[
                    "local_journal_event_count"
                ],
                "astra_trajectory_local_journal_terminal_event": terminal_event,
            }
        )
        persisted.update(
            {
                "capture_status": status,
                "capture_failed": True,
                "failed": True,
                "manifest_sha256": manifest_sha256,
                "local_journal_terminal_event": terminal_event,
                **counts,
            }
        )
        completed.update(
            {
                "astra_trajectory_status": status,
                "astra_trajectory_capture_failed": True,
                "astra_trajectory_manifest_sha256": manifest_sha256,
                "astra_trajectory_file_count": counts["trajectory_file_count"],
                "astra_trajectory_server_event_count": counts[
                    "server_event_count"
                ],
                "astra_trajectory_local_journal_event_count": counts[
                    "local_journal_event_count"
                ],
                "astra_trajectory_local_journal_terminal_event": terminal_event,
            }
        )
        status_record.update(
            {
                "capture_status": status,
                "capture_failed": True,
                "failed": True,
                "manifest_sha256": manifest_sha256,
                "local_journal_terminal_event": terminal_event,
                **counts,
            }
        )
        session_record.update(
            {
                "capture_status": status,
                "failed": False,
            }
        )
        result_path.write_text(json.dumps(result), encoding="utf-8")
        ledger_path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        status_record_path.write_text(
            json.dumps(status_record),
            encoding="utf-8",
        )
        session_record_path.write_text(
            json.dumps(session_record),
            encoding="utf-8",
        )

    def test_accepts_trigger_hit_and_merges_upstream(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, _ = self._create_trial(
                Path(directory),
                "hit",
                trigger_hit=True,
                reward=0.75,
                exception_info={"type": "VerifierWarning"},
            )
            report = audit_trial(result_path)
            self.assertEqual(report["audit_status"], "pass")
            self.assertTrue(report["lifecycle_gate_passed"])
            self.assertFalse(report["infrastructure_failure"])
            self.assertEqual(
                report["upstream"]["verifier_rewards"], {"reward": 0.75}
            )
            self.assertEqual(
                report["upstream"]["exception_info"],
                {"type": "VerifierWarning"},
            )

    def _attach_pi_trajectory(
        self,
        result_path: Path,
        ledger_path: Path,
        *,
        failed: bool = False,
    ) -> Path:
        agent_dir = result_path.parent / "agent"
        event_path = agent_dir / "pi.txt"
        session_path = agent_dir / "pi-sessions" / "session.jsonl"
        session_path.parent.mkdir(parents=True)
        session_id = "pi-session-1"
        if failed:
            event_path.write_text('{"type":"session"\n', encoding="utf-8")
            session_path.write_text("", encoding="utf-8")
            trajectory_status = "failed"
            trajectory_error = "RuntimeError: invalid Pi JSONL"
            session_sha256 = None
            session_entry_count = 0
            stop_reason = None
            provider_model_verified = False
            event_count = 0
        else:
            header = {
                "type": "session",
                "version": 3,
                "id": session_id,
                "cwd": "/app",
            }
            events = [
                header,
                {"type": "agent_start"},
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "provider": "zai",
                        "model": "glm-5.2",
                        "stopReason": "stop",
                    },
                },
                {"type": "agent_end", "messages": []},
            ]
            event_path.write_text(
                "\n".join(json.dumps(row) for row in events) + "\n",
                encoding="utf-8",
            )
            session_path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [header, {"type": "message"}]
                )
                + "\n",
                encoding="utf-8",
            )
            trajectory_status = "saved"
            trajectory_error = None
            session_sha256 = hashlib.sha256(
                session_path.read_bytes()
            ).hexdigest()
            session_entry_count = 2
            stop_reason = "stop"
            provider_model_verified = True
            event_count = 4
        trajectory_sha256 = hashlib.sha256(event_path.read_bytes()).hexdigest()
        result = json.loads(result_path.read_text(encoding="utf-8"))
        metadata = result["agent_result"]["metadata"]
        metadata.update(
            {
                "pi_version": "0.73.1",
                "pi_models_sha256": "e" * 64,
                "pi_trajectory_status": trajectory_status,
                "pi_trajectory_error": trajectory_error,
                "pi_trajectory_sha256": trajectory_sha256,
                "pi_event_count": event_count,
                "pi_session_id": session_id if not failed else None,
                "pi_session_sha256": session_sha256,
                "pi_session_entry_count": session_entry_count,
                "pi_final_stop_reason": stop_reason,
                "pi_provider_model_verified": provider_model_verified,
                "trajectory_capture_blocking": False,
            }
        )
        result_path.write_text(json.dumps(result), encoding="utf-8")
        rows = [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
        ]
        started = rows[0]
        started.update(
            {
                "product": "pi",
                "product_version": "0.73.1",
                "model_name": "zai/glm-5.2",
                "pi_models_sha256": "e" * 64,
                "trajectory_capture_required": True,
                "trajectory_capture_mode": "pi_jsonl_and_saved_session",
                "trajectory_capture_blocking": False,
            }
        )
        completed = rows[-1]
        completed.update(
            {
                "pi_trajectory_status": trajectory_status,
                "pi_trajectory_error": trajectory_error,
                "pi_trajectory_sha256": trajectory_sha256,
                "pi_event_count": event_count,
                "pi_session_id": session_id if not failed else None,
                "pi_session_sha256": session_sha256,
                "pi_session_entry_count": session_entry_count,
                "pi_final_stop_reason": stop_reason,
                "pi_provider_model_verified": provider_model_verified,
                "trajectory_capture_blocking": False,
            }
        )
        ledger_path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        return session_path

    def test_audits_pi_trajectory_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, ledger_path = self._create_trial(
                Path(directory), "pi-trajectory", trigger_hit=True
            )
            session_path = self._attach_pi_trajectory(
                result_path, ledger_path
            )

            report = audit_trial(result_path)
            trajectory = report["product"]["pi_trajectory"]
            self.assertEqual(trajectory["status"], "saved")
            self.assertEqual(trajectory["model"], "glm-5.2")

            session_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(AuditError, "matching saved session"):
                audit_trial(result_path)

    def test_pi_partial_trajectory_is_nonblocking(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, ledger_path = self._create_trial(
                Path(directory), "pi-partial", trigger_hit=True
            )
            self._attach_pi_trajectory(
                result_path, ledger_path, failed=True
            )

            report = audit_trial(result_path)

            self.assertEqual(report["audit_status"], "pass")
            self.assertEqual(
                report["product"]["pi_trajectory"]["status"], "failed"
            )
            self.assertFalse(
                report["product"]["pi_trajectory"]["blocking"]
            )

    def test_audits_astra_trajectory_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, ledger_path = self._create_trial(
                Path(directory),
                "astra-trajectory",
                trigger_hit=True,
            )
            session_id, journal_path = self._attach_astra_trajectory(
                result_path,
                ledger_path,
            )

            report = audit_trial(result_path)
            trajectory = report["product"]["trajectory"]
            self.assertEqual(trajectory["session_id"], session_id)
            self.assertEqual(trajectory["server_event_count"], 1)

            journal_path.write_text(
                journal_path.read_text(encoding="utf-8") + "{}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                AuditError,
                "invalid Astra trajectory bundle",
            ):
                audit_trial(result_path)

    def test_astra_partial_and_missing_trajectory_are_nonblocking(self):
        for status in ("partial", "missing"):
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as directory:
                    result_path, ledger_path = self._create_trial(
                        Path(directory),
                        f"astra-{status}",
                        trigger_hit=True,
                        reward=0.75,
                    )
                    self._attach_astra_trajectory(result_path, ledger_path)
                    self._degrade_astra_trajectory(
                        result_path,
                        ledger_path,
                        status=status,
                    )

                    report = audit_trial(result_path)

                    self.assertEqual(report["audit_status"], "pass")
                    self.assertFalse(report["infrastructure_failure"])
                    self.assertEqual(
                        report["upstream"]["verifier_rewards"],
                        {"reward": 0.75},
                    )
                    trajectory = report["product"]["trajectory"]
                    self.assertEqual(trajectory["status"], status)
                    self.assertFalse(trajectory["complete"])
                    self.assertTrue(trajectory["capture_failed"])
                    self.assertFalse(trajectory["blocking"])

    def test_no_hit_is_gate_false_but_not_infrastructure_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, _ = self._create_trial(
                Path(directory), "no-hit", trigger_hit=False
            )
            report = audit_trial(result_path)
            self.assertEqual(report["audit_status"], "no_hit")
            self.assertFalse(report["lifecycle_gate_passed"])
            self.assertFalse(report["infrastructure_failure"])
            self.assertEqual(report["trigger"]["reason"], "product_completed")

    def test_rejects_metadata_predicate_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, _ = self._create_trial(
                Path(directory), "mismatch", trigger_hit=True
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["agent_result"]["metadata"]["trigger_id"] = "wrong-predicate"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaisesRegex(AuditError, "predicate_id is inconsistent"):
                audit_trial(result_path)

    def test_rejects_duplicate_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, _ = self._create_trial(
                Path(directory),
                "duplicate",
                trigger_hit=True,
                duplicate_noop=True,
            )
            with self.assertRaisesRegex(AuditError, "exactly one no-op"):
                audit_trial(result_path)

    def test_rejects_fault_evidence_hidden_on_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, _ = self._create_trial(
                Path(directory),
                "hidden-fault",
                trigger_hit=True,
                noop_extra_fields={"targeted_tree_pids": [40]},
            )
            with self.assertRaisesRegex(AuditError, "unexpected fault-action"):
                audit_trial(result_path)

    def test_rejects_kill_signal_or_relaunch_events(self):
        for forbidden_event in (
            "process_tree_killed",
            "signal_dispatched",
            "same_session_relaunch_started",
        ):
            with self.subTest(event=forbidden_event):
                with tempfile.TemporaryDirectory() as directory:
                    result_path, _ = self._create_trial(
                        Path(directory),
                        forbidden_event,
                        trigger_hit=True,
                        extra_event=forbidden_event,
                    )
                    with self.assertRaisesRegex(AuditError, "forbidden fault event"):
                        audit_trial(result_path)

    def test_rejects_non_contiguous_sequence_and_mixed_run_id(self):
        for field, value, message in (
            ("sequence", 99, "sequence is not contiguous"),
            ("run_id", "different-run", "one non-empty run_id"),
        ):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    result_path, ledger_path = self._create_trial(
                        Path(directory), field, trigger_hit=True
                    )
                    rows = [
                        json.loads(line)
                        for line in ledger_path.read_text(
                            encoding="utf-8"
                        ).splitlines()
                    ]
                    rows[2][field] = value
                    ledger_path.write_text(
                        "\n".join(json.dumps(row) for row in rows) + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(AuditError, message):
                        audit_trial(result_path)

    def test_rejects_cleanup_without_zero_live_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, ledger_path = self._create_trial(
                Path(directory), "unclean", trigger_hit=True
            )
            rows = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
            ]
            cleanup = next(
                row for row in rows if row["event"] == "product_process_cleanup"
            )
            cleanup["zero_live_proven"] = False
            cleanup["remaining_pids_count"] = 1
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "zero-live"):
                audit_trial(result_path)

    def test_rejects_inconsistent_product_terminal_status(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, ledger_path = self._create_trial(
                Path(directory), "status", trigger_hit=True
            )
            rows = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
            ]
            exited = next(
                row for row in rows if row["event"] == "product_turn_exited"
            )
            exited["product_terminal_status"] = "timeout"
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "product_terminal_status"):
                audit_trial(result_path)

    def test_audits_hermes_managed_policy_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, ledger_path = self._create_trial(
                Path(directory), "hermes-policy", trigger_hit=True
            )
            policy_path = Path(
                "astra/runners/hermes_terminal_bench/managed/config.yaml"
            )
            policy_bytes = policy_path.read_bytes()
            policy_sha256 = hashlib.sha256(policy_bytes).hexdigest()
            env_path = Path(
                "astra/runners/hermes_terminal_bench/managed/.env"
            )
            env_bytes = env_path.read_bytes()
            env_sha256 = hashlib.sha256(env_bytes).hexdigest()
            guard_path = Path(
                "astra/runners/hermes_terminal_bench/"
                "policy_guard/sitecustomize.py"
            )
            guard_bytes = guard_path.read_bytes()
            guard_sha256 = hashlib.sha256(guard_bytes).hexdigest()
            artifact_path = (
                result_path.parent / "agent" / "hermes-managed-config.yaml"
            )
            artifact_path.write_bytes(policy_bytes)
            env_artifact_path = (
                result_path.parent / "agent" / "hermes-managed.env"
            )
            env_artifact_path.write_bytes(env_bytes)
            guard_artifact_path = (
                result_path.parent / "agent" / "hermes-policy-guard.py"
            )
            guard_artifact_path.write_bytes(guard_bytes)
            gateway_pid = 4242
            trajectory_bytes = (
                b'{"event":"gateway.started","pid":4242,'
                b'"session_id":"session-1"}\n'
                b'{"event":"run.submitted","run_id":"run-1",'
                b'"session_id":"session-1"}\n'
                b'{"event":"run.completed","run_id":"run-1"}\n'
            )
            trajectory_sha256 = hashlib.sha256(
                trajectory_bytes
            ).hexdigest()
            (
                result_path.parent
                / "agent"
                / "hermes-run-events.jsonl"
            ).write_bytes(trajectory_bytes)
            session_bytes = (
                b'{"id":"session-1","messages":'
                b'[{"role":"user","content":"task"}]}\n'
            )
            session_sha256 = hashlib.sha256(session_bytes).hexdigest()
            session_artifact_path = (
                result_path.parent / "agent" / "hermes-session.jsonl"
            )
            session_artifact_path.write_bytes(session_bytes)
            (result_path.parent / "agent" / "hermes-run.json").write_text(
                json.dumps(
                    {
                        "gateway_pid": gateway_pid,
                        "run_id": "run-1",
                        "session_id": "session-1",
                        "stream_event_count": 3,
                        "stream_submitted_count": 1,
                        "stream_terminal_event_count": 1,
                        "stream_terminal_event": "run.completed",
                        "policy_guard_active": True,
                        "policy_guard": {
                            "event": "policy_guard.loaded",
                            "pid": gateway_pid,
                            "source_sha256": guard_sha256,
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = json.loads(result_path.read_text(encoding="utf-8"))
            metadata = result["agent_result"]["metadata"]
            metadata.update(
                {
                    "managed_policy_path": "/etc/hermes/config.yaml",
                    "managed_policy_read_only": True,
                    "managed_policy_sha256": policy_sha256,
                    "managed_env_path": "/etc/hermes/.env",
                    "managed_env_read_only": True,
                    "managed_env_sha256": env_sha256,
                    "policy_guard_path": (
                        "/installed-agent/hermes-c0-policy/sitecustomize.py"
                    ),
                    "policy_guard_sha256": guard_sha256,
                    "policy_guard_active": True,
                    "trajectory_capture_required": True,
                    "trajectory_capture_mode": "streaming_runs_api_jsonl",
                    "trajectory_session_export_required": True,
                    "trajectory_capture_blocking": False,
                    "trajectory_capture_status": "saved",
                    "trajectory_capture_error": None,
                    "trajectory_event_stream_status": "saved",
                    "trajectory_capture_path": (
                        "agent/hermes-run-events.jsonl"
                    ),
                    "trajectory_capture_format": "hermes_runs_api_jsonl",
                    "trajectory_capture_sha256": trajectory_sha256,
                    "trajectory_event_count": 3,
                    "trajectory_submitted_count": 1,
                    "trajectory_terminal_event_count": 1,
                    "trajectory_terminal_event": "run.completed",
                    "trajectory_session_export_status": "saved",
                    "trajectory_session_export_path": (
                        "agent/hermes-session.jsonl"
                    ),
                    "trajectory_session_export_format": (
                        "hermes_session_jsonl"
                    ),
                    "trajectory_session_sha256": session_sha256,
                    "trajectory_session_id": "session-1",
                    "trajectory_session_message_count": 1,
                    "hermes_run_id": "run-1",
                    "hermes_session_id": "session-1",
                    "driver_session_id_consistent": True,
                }
            )
            result_path.write_text(json.dumps(result), encoding="utf-8")

            rows = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
            ]
            rows[0].update(
                {
                    "product": "hermes",
                    "managed_policy_path": "/etc/hermes/config.yaml",
                    "managed_policy_read_only": True,
                    "managed_policy_sha256": policy_sha256,
                    "managed_env_path": "/etc/hermes/.env",
                    "managed_env_read_only": True,
                    "managed_env_sha256": env_sha256,
                    "policy_guard_path": (
                        "/installed-agent/hermes-c0-policy/sitecustomize.py"
                    ),
                    "policy_guard_sha256": guard_sha256,
                    "trajectory_capture_required": True,
                    "trajectory_capture_mode": "streaming_runs_api_jsonl",
                    "trajectory_session_export_required": True,
                    "trajectory_capture_blocking": False,
                }
            )
            rows[-1]["managed_policy_sha256"] = policy_sha256
            rows[-1]["managed_env_sha256"] = env_sha256
            rows[-1]["policy_guard_sha256"] = guard_sha256
            rows[-1]["policy_guard_active"] = True
            rows[-1]["trajectory_capture_status"] = "saved"
            rows[-1]["trajectory_capture_blocking"] = False
            rows[-1]["trajectory_capture_error"] = None
            rows[-1]["trajectory_capture_sha256"] = trajectory_sha256
            rows[-1]["trajectory_event_count"] = 3
            rows[-1]["trajectory_submitted_count"] = 1
            rows[-1]["trajectory_terminal_event_count"] = 1
            rows[-1]["trajectory_terminal_event"] = "run.completed"
            rows[-1]["trajectory_session_export_status"] = "saved"
            rows[-1]["trajectory_session_sha256"] = session_sha256
            rows[-1]["trajectory_session_id"] = "session-1"
            rows[-1]["trajectory_session_message_count"] = 1
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            report = audit_trial(result_path)
            self.assertEqual(
                report["product"]["managed_policy"]["sha256"],
                policy_sha256,
            )
            self.assertEqual(
                report["product"]["managed_policy"]["environment"]["sha256"],
                env_sha256,
            )
            self.assertEqual(
                report["product"]["managed_policy"]["trajectory"]["sha256"],
                trajectory_sha256,
            )
            self.assertEqual(
                report["product"]["managed_policy"]["trajectory"][
                    "session_export"
                ]["sha256"],
                session_sha256,
            )

            saved_result = json.loads(json.dumps(result))
            saved_rows = json.loads(json.dumps(rows))
            cleanup_path = result_path.parent / "agent" / "product.cleanup.json"
            normal_cleanup_raw = cleanup_path.read_text(encoding="utf-8")

            timeout_result = json.loads(json.dumps(saved_result))
            timeout_rows = json.loads(json.dumps(saved_rows))
            timeout_trajectory_bytes = (
                b'{"event":"gateway.started","pid":4242,'
                b'"session_id":"session-1"}\n'
                b'{"event":"run.submitted","run_id":"run-1",'
                b'"session_id":"session-1"}\n'
                b'{"event":"run.timed_out","run_id":"run-1",'
                b'"session_id":"session-1","source":"driver",'
                b'"reason":"ProductDeadlineExpired"}\n'
            )
            timeout_trajectory_sha256 = hashlib.sha256(
                timeout_trajectory_bytes
            ).hexdigest()
            trajectory_path = (
                result_path.parent / "agent" / "hermes-run-events.jsonl"
            )
            trajectory_path.write_bytes(timeout_trajectory_bytes)
            timeout_metadata = timeout_result["agent_result"]["metadata"]
            timeout_metadata.update(
                {
                    "product_terminal_status": "timeout",
                    "trajectory_capture_sha256": timeout_trajectory_sha256,
                    "trajectory_terminal_event": "run.timed_out",
                    "trajectory_terminal_event_source": "driver",
                    "trajectory_terminal_reason": "ProductDeadlineExpired",
                }
            )
            timeout_cleanup_report = {
                "schema_version": 1,
                "status": "clean",
                "reason": "timeout_exit",
                "fault_action": False,
                "product_terminal_status": "timeout",
                "zero_live_proven": True,
                "remaining_pids_count": 0,
                "remaining_pids": [],
            }
            timeout_cleanup_raw = (
                json.dumps(timeout_cleanup_report, sort_keys=True) + "\n"
            )
            timeout_cleanup_sha256 = hashlib.sha256(
                timeout_cleanup_raw.encode()
            ).hexdigest()
            timeout_metadata["product_cleanup_report_sha256"] = (
                timeout_cleanup_sha256
            )
            cleanup_path.write_text(timeout_cleanup_raw, encoding="utf-8")
            for row in timeout_rows:
                if row["event"] == "product_process_cleanup":
                    row.update(
                        {
                            "reason": "timeout_exit",
                            "product_terminal_status": "timeout",
                            "cleanup_report_sha256": timeout_cleanup_sha256,
                        }
                    )
                elif row["event"] == "product_turn_exited":
                    row.update(
                        {
                            "return_code": 124,
                            "product_terminal_status": "timeout",
                        }
                    )
                elif row["event"] == "controller_completed":
                    row.update(
                        {
                            "product_completion_claim": False,
                            "product_return_code": 124,
                            "product_terminal_status": "timeout",
                            "trajectory_capture_sha256": (
                                timeout_trajectory_sha256
                            ),
                            "trajectory_terminal_event": "run.timed_out",
                            "trajectory_terminal_event_source": "driver",
                            "trajectory_terminal_reason": (
                                "ProductDeadlineExpired"
                            ),
                        }
                    )
            (result_path.parent / "agent" / "hermes-run.json").write_text(
                json.dumps(
                    {
                        "status": "timed_out",
                        "gateway_pid": gateway_pid,
                        "run_id": "run-1",
                        "session_id": "session-1",
                        "stream_event_count": 3,
                        "stream_submitted_count": 1,
                        "stream_terminal_event_count": 1,
                        "stream_terminal_event": "run.timed_out",
                        "stream_terminal_event_source": "driver",
                        "stream_terminal_reason": "ProductDeadlineExpired",
                        "policy_guard_active": True,
                        "policy_guard": {
                            "event": "policy_guard.loaded",
                            "pid": gateway_pid,
                            "source_sha256": guard_sha256,
                        },
                    }
                ),
                encoding="utf-8",
            )
            result_path.write_text(
                json.dumps(timeout_result),
                encoding="utf-8",
            )
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in timeout_rows) + "\n",
                encoding="utf-8",
            )

            timeout_report = audit_trial(result_path)
            timeout_trajectory = timeout_report["product"]["managed_policy"][
                "trajectory"
            ]
            self.assertEqual(
                timeout_report["upstream"]["verifier_rewards"],
                {"reward": 1.0},
            )
            self.assertTrue(timeout_trajectory["complete"])
            self.assertEqual(
                timeout_trajectory["terminal_event"],
                "run.timed_out",
            )
            self.assertEqual(
                timeout_trajectory["terminal_event_source"],
                "driver",
            )

            result = json.loads(json.dumps(saved_result))
            metadata = result["agent_result"]["metadata"]
            rows = json.loads(json.dumps(saved_rows))
            result_path.write_text(json.dumps(result), encoding="utf-8")
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            trajectory_path.write_bytes(trajectory_bytes)
            cleanup_path.write_text(normal_cleanup_raw, encoding="utf-8")
            (result_path.parent / "agent" / "hermes-run.json").write_text(
                json.dumps(
                    {
                        "gateway_pid": gateway_pid,
                        "run_id": "run-1",
                        "session_id": "session-1",
                        "stream_event_count": 3,
                        "stream_submitted_count": 1,
                        "stream_terminal_event_count": 1,
                        "stream_terminal_event": "run.completed",
                        "policy_guard_active": True,
                        "policy_guard": {
                            "event": "policy_guard.loaded",
                            "pid": gateway_pid,
                            "source_sha256": guard_sha256,
                        },
                    }
                ),
                encoding="utf-8",
            )

            metadata.update(
                {
                    "trajectory_capture_status": "failed",
                    "trajectory_capture_error": (
                        "RuntimeError: capture unavailable"
                    ),
                    "trajectory_event_stream_status": "failed",
                    "trajectory_capture_sha256": None,
                    "trajectory_event_count": 0,
                    "trajectory_submitted_count": 0,
                    "trajectory_terminal_event_count": 0,
                    "trajectory_terminal_event": None,
                    "trajectory_session_export_status": "failed",
                    "trajectory_session_sha256": None,
                    "trajectory_session_id": None,
                    "trajectory_session_message_count": 0,
                }
            )
            rows[-1].update(
                {
                    "trajectory_capture_status": "failed",
                    "trajectory_capture_error": (
                        "RuntimeError: capture unavailable"
                    ),
                    "trajectory_capture_sha256": None,
                    "trajectory_event_count": 0,
                    "trajectory_submitted_count": 0,
                    "trajectory_terminal_event_count": 0,
                    "trajectory_terminal_event": None,
                    "trajectory_session_export_status": "failed",
                    "trajectory_session_sha256": None,
                    "trajectory_session_id": None,
                    "trajectory_session_message_count": 0,
                }
            )
            result_path.write_text(json.dumps(result), encoding="utf-8")
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            degraded_report = audit_trial(result_path)
            degraded_trajectory = degraded_report["product"][
                "managed_policy"
            ]["trajectory"]
            self.assertEqual(degraded_report["audit_status"], "pass")
            self.assertFalse(degraded_report["infrastructure_failure"])
            self.assertEqual(
                degraded_report["upstream"]["verifier_rewards"],
                {"reward": 1.0},
            )
            self.assertEqual(degraded_trajectory["status"], "failed")
            self.assertFalse(degraded_trajectory["complete"])
            self.assertFalse(degraded_trajectory["blocking"])

            result = saved_result
            rows = saved_rows
            result_path.write_text(json.dumps(result), encoding="utf-8")
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            for invalid_session in (
                None,
                b'{"id":"wrong","messages":[{"role":"user"}]}\n',
                b'{"id":"session-1","messages":[]}\n',
            ):
                if invalid_session is None:
                    session_artifact_path.unlink()
                else:
                    session_artifact_path.write_bytes(invalid_session)
                with self.assertRaisesRegex(
                    AuditError, "invalid Hermes session export"
                ):
                    audit_trial(result_path)
                session_artifact_path.write_bytes(session_bytes)

            artifact_path.write_text(
                "approvals:\n  mode: off\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "SHA-256"):
                audit_trial(result_path)
            artifact_path.write_bytes(policy_bytes)
            guard_artifact_path.write_text(
                "raise SystemExit(0)\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "SHA-256"):
                audit_trial(result_path)
            guard_artifact_path.write_bytes(guard_bytes)
            env_artifact_path.write_text(
                "HERMES_YOLO_MODE=1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "SHA-256"):
                audit_trial(result_path)

    def test_rejects_missing_or_modified_cleanup_artifact(self):
        for mutation, message in (
            ("missing", "cannot validate process cleanup artifact"),
            ("modified", "artifact SHA-256"),
        ):
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory() as directory:
                    result_path, _ = self._create_trial(
                        Path(directory),
                        f"cleanup-{mutation}",
                        trigger_hit=True,
                    )
                    cleanup_path = (
                        result_path.parent
                        / "agent"
                        / "product.cleanup.json"
                    )
                    if mutation == "missing":
                        cleanup_path.unlink()
                    else:
                        cleanup = json.loads(
                            cleanup_path.read_text(encoding="utf-8")
                        )
                        cleanup["reason"] = "changed"
                        cleanup_path.write_text(
                            json.dumps(cleanup),
                            encoding="utf-8",
                        )
                    with self.assertRaisesRegex(AuditError, message):
                        audit_trial(result_path)

    def test_rejects_failed_product_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, ledger_path = self._create_trial(
                Path(directory), "preflight", trigger_hit=True
            )
            rows = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
            ]
            preflight = next(
                row for row in rows if row["event"] == "product_preflight"
            )
            preflight["passed"] = False
            preflight["return_code"] = 1
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "preflight did not pass"):
                audit_trial(result_path)

    def test_rejects_unsafe_registered_process_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path, ledger_path = self._create_trial(
                Path(directory), "identity", trigger_hit=True
            )
            rows = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
            ]
            registered = next(
                row
                for row in rows
                if row["event"] == "product_process_registered"
            )
            registered["sid"] = registered["pid"] + 1
            ledger_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuditError, "identity is unsafe"):
                audit_trial(result_path)

    def test_jobs_root_summary_is_read_only_until_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hit_result, _ = self._create_trial(
                root, "hit", trigger_hit=True, reward=1.0
            )
            no_hit_result, _ = self._create_trial(
                root,
                "no-hit",
                trigger_hit=False,
                reward=0.0,
                exception_info={"type": "AgentTimeout"},
            )

            report = audit_target(root)
            self.assertEqual(report["status"], "gate_incomplete")
            self.assertEqual(report["summary"]["n_trials"], 2)
            self.assertEqual(report["summary"]["n_no_hit"], 1)
            self.assertEqual(
                report["summary"]["n_infrastructure_failures"], 0
            )
            self.assertEqual(
                report["summary"]["n_upstream_exceptions"], 1
            )
            self.assertEqual(
                report["summary"]["verifier_rewards"]["reward"]["mean"], 0.5
            )
            self.assertFalse((hit_result.parent / "c0-audit.json").exists())
            self.assertFalse((no_hit_result.parent / "c0-audit.json").exists())
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main([str(root)]), 0)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "gate_incomplete")

            written = audit_target(root, write=True)
            self.assertTrue(written["write_sidecars"])
            self.assertTrue((hit_result.parent / "c0-audit.json").is_file())
            no_hit_sidecar = json.loads(
                (no_hit_result.parent / "c0-audit.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(no_hit_sidecar["audit_status"], "no_hit")
            self.assertFalse(no_hit_sidecar["infrastructure_failure"])

    def test_invalid_trial_is_reported_as_infrastructure_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path, _ = self._create_trial(
                root, "bad", trigger_hit=True
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["agent_result"]["metadata"]["trigger_manifest_sha256"] = (
                "f" * 64
            )
            result_path.write_text(json.dumps(result), encoding="utf-8")

            report = audit_target(root)
            self.assertEqual(report["status"], "infra_error")
            self.assertEqual(
                report["summary"]["n_infrastructure_failures"], 1
            )
            self.assertEqual(
                report["trials"][0]["audit_status"], "infra_error"
            )


if __name__ == "__main__":
    unittest.main()
