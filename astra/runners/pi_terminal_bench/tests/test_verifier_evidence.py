from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astra.runners.pi_terminal_bench.verifier_evidence import (
    VerifierEvidenceError,
    validate_binary_reward,
    validate_ctrf_report,
)


class VerifierEvidenceTests(unittest.TestCase):
    def test_accepts_binary_rewards(self) -> None:
        self.assertEqual(validate_binary_reward(0), 0.0)
        self.assertEqual(validate_binary_reward(1.0), 1.0)

    def test_rejects_non_binary_or_non_finite_rewards(self) -> None:
        for value in (True, -1, 0.5, 2, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(
                VerifierEvidenceError, "finite number 0 or 1"
            ):
                validate_binary_reward(value)

    def test_accepts_nonempty_ctrf_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ctrf.json"
            path.write_text(
                json.dumps(
                    {
                        "results": {
                            "summary": {"tests": 1},
                            "tests": [{"name": "test_answer", "status": "failed"}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            report = validate_ctrf_report(path)

        self.assertEqual(report, {"test_count": 1})

    def test_rejects_missing_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                VerifierEvidenceError, "did not produce ctrf.json"
            ):
                validate_ctrf_report(Path(directory) / "ctrf.json")

    def test_rejects_zero_test_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ctrf.json"
            path.write_text(
                json.dumps(
                    {"results": {"summary": {"tests": 0}, "tests": []}}
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                VerifierEvidenceError, "any tests were executed"
            ):
                validate_ctrf_report(path)

    def test_rejects_malformed_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ctrf.json"
            path.write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(
                VerifierEvidenceError, "unreadable ctrf.json"
            ):
                validate_ctrf_report(path)

    def test_rejects_inconsistent_test_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ctrf.json"
            path.write_text(
                json.dumps(
                    {
                        "results": {
                            "summary": {"tests": 2},
                            "tests": [
                                {"name": "test_answer", "status": "passed"}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                VerifierEvidenceError, "any tests were executed"
            ):
                validate_ctrf_report(path)

    def test_rejects_skipped_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ctrf.json"
            path.write_text(
                json.dumps(
                    {
                        "results": {
                            "summary": {"tests": 1},
                            "tests": [
                                {"name": "test_answer", "status": "skipped"}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                VerifierEvidenceError, "any test completed"
            ):
                validate_ctrf_report(path)
