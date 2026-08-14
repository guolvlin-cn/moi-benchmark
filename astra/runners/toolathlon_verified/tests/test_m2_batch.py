from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from astra.runners.toolathlon_verified.m2_batch import (
    FIRST_BATCH,
    Attempt,
    BatchEventLog,
    M2Batch,
    decide_slot,
)


def _observation(value: str | None) -> dict:
    return {
        "value": value,
        "source": "test",
        "reliability": "observed" if value is not None else "missing",
        "missing_reason": None if value is not None else "original_run",
    }


def _attempt(
    run_id: str,
    *,
    validity: str,
    failure: str,
    replacement_for: str | None = None,
) -> Attempt:
    return Attempt(
        directory=Path("/tmp") / run_id,
        run={
            "run_id": run_id,
            "run_validity": validity,
            "primary_failure_category": failure,
            "replacement_for_run_id": _observation(replacement_for),
            "verify_status": "no_pass",
            "adapter": {"setup_provider_requests_before_agent": 0},
        },
        resolved={},
        validation={"status": "passed"},
    )


class M2BatchTests(unittest.TestCase):
    def test_serial_plan_resume_and_single_infrastructure_replacement(self) -> None:
        self.assertEqual(len(FIRST_BATCH), 14)
        self.assertEqual(FIRST_BATCH[0], ("find-alita-paper", ("astra", "hermes")))
        self.assertEqual(FIRST_BATCH[1], ("set-conf-cr-ddl", ("hermes", "astra")))
        self.assertEqual(FIRST_BATCH[-1], ("k8s-safety-audit", ("hermes", "astra")))

        valid = _attempt("valid-a1", validity="valid", failure="product_error")
        self.assertEqual(decide_slot([valid]).state, "complete")
        infra = _attempt("infra-a1", validity="infra_invalid", failure="evaluator_error")
        self.assertEqual(decide_slot([infra]).state, "needs_replacement")
        replacement = _attempt(
            "infra-a2",
            validity="valid",
            failure="none",
            replacement_for="infra-a1",
        )
        decision = decide_slot([infra, replacement])
        self.assertEqual(decision.state, "complete")
        self.assertIs(decision.effective, replacement)
        adapter_error = _attempt(
            "adapter-a1", validity="infra_invalid", failure="adapter_error"
        )
        self.assertEqual(decide_slot([adapter_error]).state, "blocked")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = M2Batch(
                repo_root=Path("/home/vagrant/moi-benchmark"),
                output_root=root,
                m1_root=root,
                source_root=Path("/home/vagrant/dataset/Toolathlon"),
            )
            batch.output_root.mkdir(exist_ok=True)
            batch.manifest = {"batch_id": "m2-test", "freeze": {}}
            batch.events = BatchEventLog(root / "scheduler-events.jsonl")
            captured: list[str] = []

            def fake_lifecycle(argv: list[str]) -> int:
                captured.extend(argv)
                output = Path(argv[argv.index("--output-dir") + 1])
                output.mkdir(parents=True)
                return 0

            fake = _attempt("m2-test-02-set-conf-cr-ddl-hermes-a1", validity="valid", failure="none")
            with patch(
                "astra.runners.toolathlon_verified.m2_batch.load_attempt",
                return_value=fake,
            ), patch(
                "astra.runners.toolathlon_verified.m2_batch._validate_new_run_freeze"
            ):
                batch.lifecycle_runner = fake_lifecycle
                batch._run_attempt(
                    position=2,
                    task_id="set-conf-cr-ddl",
                    system="hermes",
                    ordinal=1,
                    replacement_for=None,
                )
            self.assertIn("astra.runners.toolathlon_verified.lifecycle", captured)
            self.assertEqual(captured[captured.index("--system") + 1], "hermes")
            self.assertEqual(captured[captured.index("--task-id") + 1], "set-conf-cr-ddl")
            events = [
                json.loads(line)
                for line in (root / "scheduler-events.jsonl").read_text().splitlines()
            ]
            self.assertEqual(
                [row["event"] for row in events],
                ["attempt.start", "attempt.process_exit", "attempt.artifact_gate_passed"],
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = M2Batch(
                repo_root=Path("/home/vagrant/moi-benchmark"),
                output_root=root,
                m1_root=root,
                source_root=Path("/home/vagrant/dataset/Toolathlon"),
            )
            events = BatchEventLog(root / "scheduler-events.jsonl")
            for position, (task_id, order) in enumerate(FIRST_BATCH[1:], start=2):
                for system in order:
                    run_id = f"m2-test-{position:02d}-{task_id}-{system}-a1"
                    events.append(
                        "attempt.start",
                        position=position,
                        task_id=task_id,
                        system=system,
                        attempt_ordinal=1,
                        run_id=run_id,
                    )
                    events.append(
                        "attempt.process_exit",
                        position=position,
                        task_id=task_id,
                        system=system,
                        attempt_ordinal=1,
                        run_id=run_id,
                        exit_code=0,
                    )
            batch._validate_schedule_events()


if __name__ == "__main__":
    unittest.main()
