from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astra.runners.pi_terminal_bench.events import (
    validate_event_stream,
    validate_session,
)


class PiEventTests(unittest.TestCase):
    def _write(self, path: Path, rows: list[dict]) -> None:
        path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )

    def test_validates_complete_frozen_stream_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "pi.txt"
            session = root / "session.jsonl"
            header = {
                "type": "session",
                "version": 3,
                "id": "session-1",
                "cwd": "/app",
            }
            self._write(
                events,
                [
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
                ],
            )
            self._write(session, [header, {"type": "message"}])

            event_summary = validate_event_stream(
                events,
                expected_provider="zai",
                expected_model="glm-5.2",
            )
            session_summary = validate_session(
                session, session_id="session-1"
            )

        self.assertTrue(event_summary["complete"])
        self.assertEqual(event_summary["event_count"], 4)
        self.assertEqual(session_summary["entry_count"], 2)

    def test_rejects_silent_model_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "pi.txt"
            self._write(
                events,
                [
                    {
                        "type": "session",
                        "version": 3,
                        "id": "session-1",
                        "cwd": "/app",
                    },
                    {"type": "agent_start"},
                    {
                        "type": "message_end",
                        "message": {
                            "role": "assistant",
                            "provider": "zai",
                            "model": "glm-5.1",
                            "stopReason": "stop",
                        },
                    },
                    {"type": "agent_end", "messages": []},
                ],
            )
            with self.assertRaisesRegex(RuntimeError, "provider/model"):
                validate_event_stream(
                    events,
                    expected_provider="zai",
                    expected_model="glm-5.2",
                )

    def test_rejects_error_stop_reason_as_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "pi.txt"
            self._write(
                events,
                [
                    {
                        "type": "session",
                        "version": 3,
                        "id": "session-1",
                        "cwd": "/app",
                    },
                    {"type": "agent_start"},
                    {
                        "type": "message_end",
                        "message": {
                            "role": "assistant",
                            "provider": "zai",
                            "model": "glm-5.2",
                            "stopReason": "error",
                        },
                    },
                    {"type": "agent_end", "messages": []},
                ],
            )
            summary = validate_event_stream(
                events,
                expected_provider="zai",
                expected_model="glm-5.2",
            )

        self.assertFalse(summary["complete"])

    def test_requires_balanced_tool_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "pi.txt"
            self._write(
                events,
                [
                    {
                        "type": "session",
                        "version": 3,
                        "id": "session-1",
                        "cwd": "/app",
                    },
                    {"type": "agent_start"},
                    {
                        "type": "tool_execution_start",
                        "toolCallId": "call-1",
                        "toolName": "bash",
                    },
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
                ],
            )
            with self.assertRaisesRegex(RuntimeError, "incomplete tool"):
                validate_event_stream(
                    events,
                    expected_provider="zai",
                    expected_model="glm-5.2",
                )

