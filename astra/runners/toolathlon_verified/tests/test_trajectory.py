from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astra.runners.toolathlon_verified.contract import canonical_json_sha256
from astra.runners.toolathlon_verified.trajectory import normalize_product_events


class TrajectoryTests(unittest.TestCase):
    def test_recovers_tool_name_for_server_tool_result(self) -> None:
        rows = [
            {
                "type": "tool_call_start",
                "tool": "mcp__toolathlon__local-claim_done",
                "call_id": "server-1",
                "arguments": {},
            },
            {"type": "tool_result", "call_id": "server-1", "result": "ok"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = normalize_product_events(
                rows,
                run_id="run-1",
                system_id="astra",
                trajectory_path=root / "trajectory.jsonl",
                tool_calls_path=root / "tools.jsonl",
                observed_tool_manifest={
                    "tools": [
                        {
                            "canonical_tool_name": "local-claim_done",
                            "gateway_tool_name": "local-claim_done",
                            "astra_model_visible_tool_name": "mcp__toolathlon__local-claim_done",
                        }
                    ]
                },
            )
            self.assertEqual(summary["tool_terminal_events"], 1)
            self.assertEqual(summary["started_only_tool_calls"], 0)
            self.assertTrue(summary["claim_done_seen"])
            records = [
                json.loads(line)
                for line in (root / "tools.jsonl").read_text().splitlines()
            ]
            self.assertEqual(records[1]["state"], "succeeded")
            self.assertEqual(
                records[1]["model_visible_tool_name"],
                "mcp__toolathlon__local-claim_done",
            )

    def test_only_terminal_tool_events_count_as_completed(self) -> None:
        rows = [
            {"type": "tool_started", "tool_name": "mcp__toolathlon__local_claim_done", "tool_call_id": "1"},
            {"type": "tool_completed", "tool_name": "mcp__toolathlon__local_claim_done", "tool_call_id": "1"},
            {"type": "tool_started", "tool_name": "mcp__toolathlon__b", "tool_call_id": "2"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = normalize_product_events(
                rows,
                run_id="run-1",
                system_id="hermes",
                trajectory_path=root / "trajectory.jsonl",
                tool_calls_path=root / "tools.jsonl",
                observed_tool_manifest={
                    "tools": [
                        {
                            "canonical_tool_name": "local-claim_done",
                            "gateway_tool_name": "local-claim_done",
                            "hermes_model_visible_tool_name": "mcp__toolathlon__local_claim_done",
                        },
                        {
                            "canonical_tool_name": "b",
                            "gateway_tool_name": "b",
                            "hermes_model_visible_tool_name": "mcp__toolathlon__b",
                        },
                    ]
                },
            )
            self.assertEqual(summary["tool_terminal_events"], 1)
            self.assertEqual(summary["started_only_tool_calls"], 1)
            self.assertTrue(summary["claim_done_seen"])
            records = [json.loads(line) for line in (root / "tools.jsonl").read_text().splitlines()]
            self.assertEqual([row["state"] for row in records], ["started", "succeeded", "started"])
            self.assertEqual(records[0]["gateway_tool_name"], "local-claim_done")
            self.assertEqual(records[0]["name_mapping_reliability"], "observed_tools_list")
            self.assertEqual(records[0]["native_tool_call_id"]["value"], "1")
            self.assertEqual(
                records[0]["arguments_sha256"]["reliability"], "missing"
            )

    def test_transport_events_are_paired_and_later_terminals_are_deduplicated(self) -> None:
        rows = [
            {
                "type": "tool_transport_started",
                "tool": "web_fetch",
                "call_id": "call-1",
                "arguments": {"value": 1},
            },
            {
                "type": "tool_transport_started",
                "tool": "web_fetch",
                "call_id": "call-2",
                "arguments": {"value": 2},
            },
            {
                "type": "tool_transport_completed",
                "tool": "web_fetch",
                "call_id": "call-1",
                "success": True,
            },
            {
                "type": "tool_call_end",
                "tool": "web_fetch",
                "call_id": "call-1",
                "success": True,
                "result": "duplicate higher-level terminal",
            },
            {
                "type": "tool_transport_failed",
                "tool": "web_fetch",
                "call_id": "call-2",
                "success": False,
            },
            {
                "type": "tool_call_end",
                "tool": "web_fetch",
                "call_id": "call-2",
                "success": False,
                "result": "duplicate higher-level failure terminal",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = normalize_product_events(
                rows,
                run_id="run-transport",
                system_id="astra",
                trajectory_path=root / "trajectory.jsonl",
                tool_calls_path=root / "tools.jsonl",
            )
            self.assertEqual(summary["trajectory_events"], 6)
            self.assertEqual(summary["tool_started_events"], 2)
            self.assertEqual(summary["tool_terminal_events"], 2)
            self.assertEqual(summary["tool_failed_events"], 1)
            self.assertEqual(summary["started_only_tool_calls"], 0)
            records = [
                json.loads(line)
                for line in (root / "tools.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(records), 4)
            by_call = {
                call_id: [row for row in records if row["tool_call_id"] == call_id]
                for call_id in ("call-1", "call-2")
            }
            self.assertEqual(
                [row["state"] for row in by_call["call-1"]],
                ["started", "succeeded"],
            )
            self.assertEqual(
                [row["state"] for row in by_call["call-2"]],
                ["started", "failed"],
            )
            for call_id, value in (("call-1", 1), ("call-2", 2)):
                expected = canonical_json_sha256({"value": value})
                self.assertEqual(
                    [row["arguments_sha256"]["value"] for row in by_call[call_id]],
                    [expected, expected],
                )
                self.assertEqual(
                    by_call[call_id][1]["arguments_sha256"]["source"],
                    "product_event.arguments:paired_start",
                )


if __name__ == "__main__":
    unittest.main()
