from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from astra.runners.toolathlon_verified.m2_batch import FIRST_BATCH
from astra.runners.toolathlon_verified.m3_batch import (
    M3Batch,
    M3_EFFECTIVE_SLOT_COUNT,
    frozen_remaining_schedule,
)


class M3BatchTests(unittest.TestCase):
    def _freeze(self, root: Path) -> Path:
        freeze = root / "freeze"
        freeze.mkdir()
        first = [task_id for task_id, _order in FIRST_BATCH]
        remaining = [f"remaining-{index:03d}" for index in range(1, 95)]
        (freeze / "task-requirements.json").write_text(
            json.dumps(
                {"tasks": {task_id: {} for task_id in [*first, *remaining]}}
            ),
            encoding="utf-8",
        )
        (freeze / "execution-protocol.freeze.json").write_text(
            json.dumps(
                {
                    "scope": {"workers": 1},
                    "retry": {"automatic_replacement_maximum": 1},
                    "formal_phases": {
                        "remaining_batch": {
                            "tasks": remaining,
                            "workers": 1,
                            "system_order_rule": "alternate_by_remaining_position_astra_first",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return freeze

    def test_remaining_schedule_is_balanced_and_partitions_all_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schedule = frozen_remaining_schedule(self._freeze(Path(directory)))

        self.assertEqual(len(schedule), 94)
        self.assertEqual(len(schedule) * 2, M3_EFFECTIVE_SLOT_COUNT)
        self.assertEqual(schedule[0][1], ("astra", "hermes"))
        self.assertEqual(schedule[1][1], ("hermes", "astra"))
        first_system_counts = Counter(order[0] for _task_id, order in schedule)
        self.assertEqual(first_system_counts, {"astra": 47, "hermes": 47})
        overall_first_counts = Counter(order[0] for _task_id, order in FIRST_BATCH)
        overall_first_counts.update(first_system_counts)
        self.assertEqual(overall_first_counts, {"astra": 54, "hermes": 54})

    def test_manifest_positions_continue_from_15_through_108(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schedule = frozen_remaining_schedule(self._freeze(Path(directory)))
        batch = object.__new__(M3Batch)
        batch.schedule = schedule

        manifest = batch._task_manifest()

        self.assertEqual(manifest[0]["formal_position"], 15)
        self.assertEqual(manifest[0]["remaining_position"], 1)
        self.assertEqual(manifest[-1]["formal_position"], 108)
        self.assertEqual(manifest[-1]["remaining_position"], 94)


if __name__ == "__main__":
    unittest.main()
