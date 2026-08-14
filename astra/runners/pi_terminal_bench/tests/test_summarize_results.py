from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astra.runners.pi_terminal_bench.prebuilt.summarize_results import (
    result_row,
)


class PiSummaryTests(unittest.TestCase):
    def _write_result(
        self,
        root: Path,
        *,
        reward: float | bool,
        with_ctrf: bool,
        exception: dict | None = None,
    ) -> tuple[dict, Path]:
        trial_dir = root / "job" / "task__trial"
        trial_dir.mkdir(parents=True)
        result = {
            "task_name": "terminal-bench/task",
            "agent_result": {"metadata": {}},
            "verifier_result": {"rewards": {"reward": reward}},
            "exception_info": exception,
            "finished_at": "2026-08-12T00:00:00Z",
        }
        result_path = trial_dir / "result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        if with_ctrf:
            verifier_dir = trial_dir / "verifier"
            verifier_dir.mkdir()
            (verifier_dir / "ctrf.json").write_text(
                json.dumps(
                    {
                        "results": {
                            "summary": {"tests": 1},
                            "tests": [
                                {"name": "test_answer", "status": "failed"}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
        return result, result_path

    def test_reward_without_ctrf_is_infrastructure_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, path = self._write_result(
                Path(directory), reward=0.0, with_ctrf=False
            )

            row = result_row("task", result, path)

        self.assertEqual(row["verifier_status"], "verifier_infra_failure")
        self.assertIsNone(row["scored_reward"])
        self.assertEqual(row["verifier_test_count"], 0)

    def test_reward_with_ctrf_is_scored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, path = self._write_result(
                Path(directory), reward=0.0, with_ctrf=True
            )

            row = result_row("task", result, path)

        self.assertEqual(row["verifier_status"], "failed")
        self.assertEqual(row["scored_reward"], 0.0)
        self.assertEqual(row["verifier_test_count"], 1)

    def test_boolean_reward_is_not_numeric(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, path = self._write_result(
                Path(directory), reward=True, with_ctrf=True
            )

            row = result_row("task", result, path)

        self.assertEqual(row["verifier_status"], "verifier_infra_failure")
        self.assertIsNone(row["scored_reward"])

    def test_agent_exception_does_not_invalidate_real_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result, path = self._write_result(
                Path(directory),
                reward=0.0,
                with_ctrf=True,
                exception={
                    "exception_type": "AgentTimeoutError",
                    "exception_message": "agent timed out",
                },
            )

            row = result_row("task", result, path)

        self.assertEqual(row["verifier_status"], "failed")
        self.assertEqual(row["trial_exception_type"], "AgentTimeoutError")
