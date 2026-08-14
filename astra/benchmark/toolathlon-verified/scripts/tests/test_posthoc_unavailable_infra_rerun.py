from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
POLICY = (
    SCRIPT_ROOT.parent
    / "config/posthoc-unavailable-infra-rerun-policy.v1.json"
)


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scheduler = load(
    "posthoc_rerun_scheduler_test",
    SCRIPT_ROOT / "run_posthoc_unavailable_infra_reruns.py",
)
lifecycle = load(
    "posthoc_rerun_lifecycle_test",
    SCRIPT_ROOT / "posthoc_unavailable_infra_lifecycle.py",
)


class ImportBootstrapTests(unittest.TestCase):
    def test_scheduler_imports_astra_from_outside_repository(self) -> None:
        script = SCRIPT_ROOT / "run_posthoc_unavailable_infra_reruns.py"
        code = f"""
import importlib.util
spec = importlib.util.spec_from_file_location('isolated_posthoc', {str(script)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from astra.runners.toolathlon_verified import artifact_contract
assert artifact_contract.ARTIFACT_SCHEMA_VERSION == 'toolathlon.run-artifacts.v1'
"""
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, "-I", "-c", code],
                cwd=temporary,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)


class AttemptInspectionTests(unittest.TestCase):
    def make_attempt(self, root: Path, *, system: str = "astra") -> tuple[Path, str]:
        run_id = f"posthoc-test-task-{system}-a1"
        directory = root / "runs" / system / "task" / run_id
        for relative in scheduler.REQUIRED_ARTIFACTS:
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative == "run.json":
                path.write_text(
                    json.dumps(
                        {
                            "run_id": run_id,
                            "task_id": "task",
                            "system_id": system,
                            "replacement_for_run_id": {
                                "value": None,
                                "source": "orchestrator_scheduling_record",
                                "reliability": "missing",
                                "missing_reason": "original_run",
                            },
                            "run_validity": "valid",
                            "verify_status": "pass",
                            "artifact_gate": {"status": "passed"},
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            elif relative == "artifacts.sha256":
                continue
            elif path.suffix in {".json", ".jsonl"}:
                path.write_text("{}\n", encoding="utf-8")
            else:
                path.write_text("test\n", encoding="utf-8")
        if system == "astra":
            (directory / "astra-runtime-mcp-binding.json").write_text(
                "{}\n", encoding="utf-8"
            )
        candidates = sorted(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.name != "artifacts.sha256"
        )
        (directory / "artifacts.sha256").write_text(
            "".join(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                f"{path.relative_to(directory).as_posix()}\n"
                for path in candidates
            ),
            encoding="utf-8",
        )
        return directory, run_id

    def test_complete_attempt_is_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory, run_id = self.make_attempt(Path(temporary))
            state, run, reason = scheduler.inspect_attempt(
                directory,
                task_id="task",
                system_id="astra",
                run_id=run_id,
                replacement_for=None,
            )
            self.assertEqual("complete", state)
            self.assertEqual(run_id, run["run_id"])
            self.assertIsNone(reason)

    def test_tampered_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory, run_id = self.make_attempt(Path(temporary))
            (directory / "trajectory.jsonl").write_text(
                '{"tampered":true}\n', encoding="utf-8"
            )
            with self.assertRaises(scheduler.RerunBlocked):
                scheduler.inspect_attempt(
                    directory,
                    task_id="task",
                    system_id="astra",
                    run_id=run_id,
                    replacement_for=None,
                )

    def test_missing_artifact_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory, run_id = self.make_attempt(Path(temporary), system="hermes")
            (directory / "model-usage.jsonl").unlink()
            state, run, reason = scheduler.inspect_attempt(
                directory,
                task_id="task",
                system_id="hermes",
                run_id=run_id,
                replacement_for=None,
            )
            self.assertEqual("incomplete", state)
            self.assertIsNone(run)
            self.assertIn("model-usage.jsonl", reason)

    def make_pending_successful_hermes_drain_attempt(
        self, root: Path
    ) -> tuple[Path, str, dict]:
        run_id = "posthoc-test-task-hermes-a1"
        directory = root / "runs" / "hermes" / "task" / run_id
        directory.mkdir(parents=True)
        observed = lambda value, source="test": {
            "value": value,
            "source": source,
            "reliability": "observed",
            "missing_reason": None,
        }
        missing = {
            "value": None,
            "source": "orchestrator_scheduling_record",
            "reliability": "missing",
            "missing_reason": "original_run",
        }
        identity = {
            "run_id": run_id,
            "system_id": "hermes",
            "timestamp": "2026-08-12T00:00:00+00:00",
        }
        model_rows = [
            {**identity, "event": "proxy.ready", "monotonic_ns": 1},
            {
                **identity,
                "event": "model_request.started",
                "monotonic_ns": 10,
                "model_request_id": f"{run_id}:model:1",
                "product_attempt": 1,
                "retry_of": missing,
                "thinking": "enabled",
                "thinking_wire_behavior": "sent",
                "reasoning_effort": "max",
                "reasoning_effort_wire_behavior": "sent",
                "generation_parameter_source": "benchmark_override",
            },
            {
                **identity,
                "event": "model_request.completed",
                "monotonic_ns": 20,
                "model_request_id": f"{run_id}:model:1",
                "product_attempt": 1,
                "retry_of": missing,
                "success": True,
                "http_status": 200,
                "finish_reason": observed("stop"),
                "token_usage": {
                    "input_tokens": observed(1),
                    "output_tokens": observed(1),
                    "cache_read_tokens": observed(0),
                    "cache_write_tokens": observed(0),
                    "total_tokens": observed(2),
                },
            },
            {**identity, "event": "proxy.stopped", "monotonic_ns": 21},
        ]
        adapter_rows = [
            {**identity, "event": "agent.execution_end", "monotonic_ns": 22},
            {
                **identity,
                "event": "evaluator.end",
                "monotonic_ns": 23,
                "verify_status": "no_pass",
            },
        ]
        lifecycle_rows = [
            {**identity, "event": "cleanup.end", "monotonic_ns": 24},
            {
                **identity,
                "event": "artifact_validation.start",
                "monotonic_ns": 25,
            },
        ]
        run = {
            "run_id": run_id,
            "task_id": "task",
            "system_id": "hermes",
            "replacement_for_run_id": missing,
            "terminal_status": "completed",
            "termination_reason": "product_exit",
            "run_validity": "valid",
            "verify_status": "no_pass",
            "artifact_gate": {"status": "pending_cleanup_and_validation"},
            "adapter": {
                "post_terminal_model_drain": {
                    "settled": False,
                    "provider_requests_forwarded": 1,
                    "provider_requests_completed": 0,
                    "timeout_seconds": 120.0,
                    "wait_seconds": 120.0,
                }
            },
            "model_budget": {
                "provider_requests_forwarded": 1,
                "provider_requests_completed": 1,
            },
        }
        for relative in scheduler.REQUIRED_ARTIFACTS:
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative == "run.json":
                path.write_text(json.dumps(run) + "\n", encoding="utf-8")
            elif relative == "model-usage.jsonl":
                path.write_text(
                    "".join(json.dumps(row) + "\n" for row in model_rows),
                    encoding="utf-8",
                )
            elif relative == "adapter-events.jsonl":
                path.write_text(
                    "".join(json.dumps(row) + "\n" for row in adapter_rows),
                    encoding="utf-8",
                )
            elif relative == "lifecycle-events.jsonl":
                path.write_text(
                    "".join(json.dumps(row) + "\n" for row in lifecycle_rows),
                    encoding="utf-8",
                )
            elif relative == "evaluator/eval_res.json":
                path.write_text('{"pass":false}\n', encoding="utf-8")
            elif relative == "artifacts.sha256":
                path.write_text("", encoding="utf-8")
            elif path.suffix in {".json", ".jsonl"}:
                path.write_text("{}\n", encoding="utf-8")
            else:
                path.write_text("test\n", encoding="utf-8")
        return directory, run_id, run

    def test_successful_terminal_after_drain_snapshot_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory, run_id, _ = self.make_pending_successful_hermes_drain_attempt(
                Path(temporary)
            )
            state, run, reason = scheduler.inspect_attempt(
                directory,
                task_id="task",
                system_id="hermes",
                run_id=run_id,
                replacement_for=None,
            )
            self.assertEqual("recoverable", state)
            self.assertEqual(run_id, run["run_id"])
            self.assertEqual(scheduler.HERMES_SUCCESSFUL_DRAIN_POLICY, reason)

    def test_failed_drain_terminal_is_not_success_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory, run_id, _ = self.make_pending_successful_hermes_drain_attempt(
                Path(temporary)
            )
            rows = [
                json.loads(line)
                for line in (directory / "model-usage.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            completion = next(
                row for row in rows if row["event"] == "model_request.completed"
            )
            completion["success"] = False
            completion["http_status"] = 502
            (directory / "model-usage.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            state, run, reason = scheduler.inspect_attempt(
                directory,
                task_id="task",
                system_id="hermes",
                run_id=run_id,
                replacement_for=None,
            )
            self.assertEqual("incomplete", state)
            self.assertEqual(run_id, run["run_id"])
            self.assertIn("not the bounded successful pre-stop race", reason)


class LifecycleAuthorizationTests(unittest.TestCase):
    def test_manifest_authorizes_only_selected_target(self) -> None:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_id = "posthoc-test-task-astra-a1"
            output = root / "runs" / "astra" / "task" / run_id
            manifest = {
                "schema_version": lifecycle.MANIFEST_SCHEMA
                if hasattr(lifecycle, "MANIFEST_SCHEMA")
                else "toolathlon.posthoc-unavailable-infra-rerun-manifest.v1",
                "policy_sha256": lifecycle.sha256_file(POLICY),
                "formal_result_mutation": False,
                "cases": [
                    {
                        "task_id": "task",
                        "system_id": "astra",
                        "target_run_ids": [run_id],
                    }
                ],
            }
            (root / lifecycle.BATCH_MANIFEST).write_text(
                json.dumps(manifest) + "\n", encoding="utf-8"
            )
            batch_root, case = lifecycle.authorize_invocation(
                [
                    "--system",
                    "astra",
                    "--task-id",
                    "task",
                    "--experiment-id",
                    policy["runtime"]["experiment_id"],
                    "--run-id",
                    run_id,
                    "--output-dir",
                    str(output),
                ],
                POLICY,
                policy,
            )
            self.assertEqual(root, batch_root)
            self.assertEqual(run_id, case["target_run_ids"][0])


if __name__ == "__main__":
    unittest.main()
