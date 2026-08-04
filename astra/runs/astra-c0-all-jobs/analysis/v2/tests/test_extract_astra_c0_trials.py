import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "extract_astra_c0_trials.py"
SPEC = importlib.util.spec_from_file_location("extract_astra_c0_trials", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
extractor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)

MISSING = object()


class AstraC0ExtractorTests(unittest.TestCase):
    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def write_result(
        self,
        root,
        batch,
        trial,
        task_id,
        reward=MISSING,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
    ):
        result = {
            "task_name": "terminal-bench/{}".format(task_id),
            "trial_name": trial,
            "started_at": started_at,
            "finished_at": finished_at,
            "agent_result": {
                "metadata": {
                    "task_id": task_id,
                    "product_terminal_status": "completed",
                    "product_return_code": 0,
                }
            },
        }
        if reward is not MISSING:
            result["verifier_result"] = {"rewards": {"reward": reward}}
        path = root / batch / trial / "result.json"
        self.write_json(path, result)
        return path.parent

    def run_main(self, roots, output_dir):
        argv = []
        for root in roots:
            argv.extend(["--root", str(root)])
        argv.extend(["--output-dir", str(output_dir)])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(extractor.main(argv), 0)

    def read_csv(self, path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_latest_is_global_across_roots_and_missing_reward_does_not_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first_root = base / "first"
            second_root = base / "second"
            output = base / "output"

            self.write_result(
                first_root,
                "2026-01-01__00-00-00",
                "drops-old-score__old",
                "drops-old-score",
                reward=1,
            )
            newer_unverified = self.write_result(
                second_root,
                "2026-02-01__00-00-00",
                "drops-old-score__new",
                "drops-old-score",
            )
            self.write_result(
                first_root,
                "2026-01-01__00-00-00",
                "keeps-latest-score__old",
                "keeps-latest-score",
                reward=0,
            )
            newer_verified = self.write_result(
                second_root,
                "2026-02-01__00-00-00",
                "keeps-latest-score__new",
                "keeps-latest-score",
                reward=1,
            )

            self.run_main([first_root, second_root], output)

            rows = self.read_csv(output / "astra-c0-latest-verified-trials.csv")
            self.assertEqual([row["task_id"] for row in rows], ["keeps-latest-score"])
            self.assertEqual(rows[0]["selected_trial_path"], str(newer_verified.resolve()))
            self.assertEqual(rows[0]["attempt_count_for_task"], "2")

            audit = self.read_csv(output / "astra-c0-attempt-selection.csv")
            dropped = [row for row in audit if row["task_id"] == "drops-old-score"]
            self.assertEqual(len(dropped), 2)
            selected = [row for row in dropped if row["selected_latest"] == "True"]
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["trial_path"], str(newer_unverified.resolve()))
            self.assertEqual(
                selected[0]["selection_status"],
                "selected_without_numeric_verifier",
            )

    def test_tune_is_excluded_and_bool_or_string_rewards_are_not_numeric(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            output = base / "output"
            batch = "2026-03-01__00-00-00"
            self.write_result(root, batch, "valid__one", "valid", reward=1)
            self.write_result(root, batch, "tune__one", "tune-mjcf", reward=1)
            self.write_result(root, batch, "bool__one", "bool-reward", reward=True)
            self.write_result(root, batch, "string__one", "string-reward", reward="1")

            self.run_main([root], output)

            rows = self.read_csv(output / "astra-c0-latest-verified-trials.csv")
            self.assertEqual([row["task_id"] for row in rows], ["valid"])
            audit = self.read_csv(output / "astra-c0-attempt-selection.csv")
            statuses = {row["task_id"]: row["selection_status"] for row in audit}
            self.assertEqual(statuses["tune-mjcf"], "selected_excluded_task")
            self.assertEqual(
                statuses["bool-reward"], "selected_without_numeric_verifier"
            )
            self.assertEqual(
                statuses["string-reward"], "selected_without_numeric_verifier"
            )

    def test_same_batch_uses_result_timestamps_as_deterministic_tie_break(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first_root = base / "first"
            second_root = base / "second"
            output = base / "output"
            batch = "2026-04-01__00-00-00"
            self.write_result(
                first_root,
                batch,
                "same-batch__old",
                "same-batch",
                reward=0,
                # Same instant family, but a lexical comparison would make
                # this +08:00 string look later than the newer UTC attempt.
                started_at="2026-04-01T08:00:01+08:00",
                finished_at="2026-04-01T08:01:00+08:00",
            )
            newer = self.write_result(
                second_root,
                batch,
                "same-batch__new",
                "same-batch",
                reward=1,
                started_at="2026-04-01T00:00:02Z",
                finished_at="2026-04-01T00:00:30Z",
            )

            self.run_main([first_root, second_root], output)

            rows = self.read_csv(output / "astra-c0-latest-verified-trials.csv")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["reward"], "1")
            self.assertEqual(rows[0]["selected_trial_path"], str(newer.resolve()))

    def test_token_total_does_not_add_cache_twice(self):
        token = extractor.token_accounting(
            trace={"input": 100, "call_count": 1},
            stdout={
                "prompt_tokens": 100,
                "fresh_prompt_tokens": 25,
                "cache": {"read_tokens": 60, "creation_tokens": 15},
                "completion_tokens": 20,
            },
            journal_rows=[],
            retry={},
            agent_result={},
            llm_request_timeout=False,
            model_activity_observed=True,
        )

        self.assertEqual(token["token_input"], 100)
        self.assertEqual(token["token_fresh_input"], 25)
        self.assertEqual(token["token_cache_read"], 60)
        self.assertEqual(token["token_cache_creation"], 15)
        self.assertEqual(token["token_output"], 20)
        self.assertEqual(token["token_total"], 120)
        self.assertAlmostEqual(token["token_cache_share"], 0.6)
        self.assertEqual(token["token_accounting_status"], "session_reconciled")

    def test_matrixone_usage_is_canonical_when_session_is_retained(self):
        token = extractor.token_accounting(
            trace={"input": 100, "call_count": 1},
            stdout={
                "prompt_tokens": 100,
                "fresh_prompt_tokens": 25,
                "cache": {"read_tokens": 60, "creation_tokens": 15},
                "completion_tokens": 20,
            },
            journal_rows=[],
            retry={"retry_count": 1},
            agent_result={},
            llm_request_timeout=False,
            model_activity_observed=True,
            matrixone_usage={
                "request_count": 2,
                "input": 130,
                "fresh": 30,
                "cache_read": 100,
                "cache_creation": 0,
                "output": 25,
                "total": 155,
                "detail_complete": True,
                "components_consistent": True,
                "total_consistent": True,
            },
            matrixone_query_status="queried",
        )

        self.assertEqual(token["token_input"], 130)
        self.assertEqual(token["token_output"], 25)
        self.assertEqual(token["token_total"], 155)
        self.assertEqual(token["token_source"], "matrixone.agent_events.llm_response")
        self.assertEqual(token["token_accounting_status"], "server_reconciled")
        self.assertEqual(token["token_server_status"], "queried_found")
        self.assertEqual(token["token_server_local_trace_delta"], 30)

    def test_token_reconstruction_adds_only_pre_final_retry_feedback(self):
        journal_rows = [
            {
                "type": "pipeline_feedback",
                "ts": "2026-05-01T00:00:10Z",
                "turn": 1,
                "metadata": {
                    "prompt_tokens": 10,
                    "cache_read_tokens": 50,
                    "cache_creation_tokens": 0,
                    "completion_tokens": 5,
                },
            },
            # This feedback belongs to the final invocation and is already
            # represented by stdout, so it must be excluded by the cutoff.
            {
                "type": "pipeline_feedback",
                "ts": "2026-05-01T00:01:10Z",
                "turn": 2,
                "metadata": {
                    "prompt_tokens": 25,
                    "cache_read_tokens": 60,
                    "cache_creation_tokens": 15,
                    "completion_tokens": 20,
                },
            },
        ]
        token = extractor.token_accounting(
            trace={"input": 160, "call_count": 2},
            stdout={
                "prompt_tokens": 100,
                "fresh_prompt_tokens": 25,
                "cache": {"read_tokens": 60, "creation_tokens": 15},
                "completion_tokens": 20,
            },
            journal_rows=journal_rows,
            retry={
                "final_start": extractor.parse_time("2026-05-01T00:01:00Z"),
                "final_attempt_index": 1,
                "retry_count": 1,
            },
            agent_result={},
            llm_request_timeout=True,
            model_activity_observed=True,
        )

        self.assertEqual(token["token_input"], 160)
        self.assertEqual(token["token_fresh_input"], 35)
        self.assertEqual(token["token_cache_read"], 110)
        self.assertEqual(token["token_cache_creation"], 15)
        self.assertEqual(token["token_output"], 25)
        self.assertEqual(token["token_total"], 185)
        self.assertEqual(token["token_pre_final_retry_input"], 60)
        self.assertEqual(token["token_retry_attempts_included"], 1)
        self.assertEqual(token["token_accounting_status"], "session_reconciled")

    def test_input_only_usage_stays_partial_and_preserves_known_minimum(self):
        token = extractor.token_accounting(
            trace={"input": 123, "call_count": 1, "path_present": True},
            stdout={},
            journal_rows=[],
            retry={},
            agent_result={},
            llm_request_timeout=False,
            model_activity_observed=True,
            journal_telemetry_present=False,
        )

        self.assertEqual(token["token_input"], 123)
        self.assertIsNone(token["token_output"])
        self.assertIsNone(token["token_total"])
        self.assertEqual(token["token_known_minimum"], 123)
        self.assertEqual(token["token_accounting_status"], "session_input_only")
        self.assertTrue(token["token_is_lower_bound"])
        self.assertIsNone(token["journal_pipeline_feedback_count"])

    def test_step_events_are_deduplicated_and_closed_by_call_id(self):
        with tempfile.TemporaryDirectory() as directory:
            trial_dir = Path(directory) / "trial"
            step_path = (
                trial_dir
                / "agent"
                / "astra-trajectory"
                / "local-sessions"
                / "v1"
                / "users"
                / "local"
                / "sessions"
                / "session-1"
                / "step_events.jsonl"
            )
            events = [
                {
                    "payload": {
                        "event_id": "step-1",
                        "event_type": "StepStarted",
                        "payload": {},
                    }
                },
                {
                    "payload": {
                        "event_id": "tool-1-start",
                        "event_type": "ToolCallStarted",
                        "payload": {"call_id": "call-1", "tool_name": "bash"},
                    }
                },
                {
                    "payload": {
                        "event_id": "tool-1-start",
                        "event_type": "ToolCallStarted",
                        "payload": {"call_id": "call-1", "tool_name": "bash"},
                    }
                },
                {
                    "payload": {
                        "event_id": "tool-1-done",
                        "event_type": "ToolCallCompleted",
                        "payload": {
                            "call_id": "call-1",
                            "tool_name": "bash",
                            "elapsed_ms": 120,
                        },
                    }
                },
                {
                    "payload": {
                        "event_id": "tool-2-start",
                        "event_type": "ToolCallStarted",
                        "payload": {"call_id": "call-2", "tool_name": "read_file"},
                    }
                },
                {
                    "payload": {
                        "event_id": "tool-2-failed",
                        "event_type": "ToolCallFailed",
                        "payload": {
                            "call_id": "call-2",
                            "tool_name": "read_file",
                            "elapsed_ms": 80,
                        },
                    }
                },
                {
                    "payload": {
                        "event_id": "tool-2-failed",
                        "event_type": "ToolCallFailed",
                        "payload": {
                            "call_id": "call-2",
                            "tool_name": "read_file",
                            "elapsed_ms": 80,
                        },
                    }
                },
            ]
            step_path.parent.mkdir(parents=True, exist_ok=True)
            step_path.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )
            diagnostics = extractor.ParseDiagnostics()

            _, step_rows, _, step_bad, _, step_paths = extractor.load_local_session(
                trial_dir, "session-1", diagnostics
            )
            tools = extractor.extract_tools(step_rows, step_paths, step_bad)

            self.assertEqual(len(step_rows), 5)
            self.assertEqual(tools["agentic_steps"], 1)
            self.assertEqual(tools["tool_calls_started"], 2)
            self.assertEqual(tools["tool_calls_completed"], 1)
            self.assertEqual(tools["tool_calls_failed"], 1)
            self.assertEqual(tools["tool_calls_terminal"], 2)
            self.assertEqual(tools["tool_calls_unpaired"], 0)
            self.assertEqual(tools["tool_terminal_orphan_count"], 0)
            self.assertEqual(tools["tool_terminal_coverage"], 1.0)
            self.assertEqual(tools["tool_call_failure_rate"], 0.5)
            self.assertAlmostEqual(tools["tool_call_duration_sum_s"], 0.2)
            self.assertEqual(json.loads(tools["tool_breakdown"]), {"bash": 1, "read_file": 1})
            self.assertEqual(json.loads(tools["failed_tool_breakdown"]), {"read_file": 1})
            self.assertEqual(
                tools["tool_telemetry_status"], "ledger_internally_complete"
            )


if __name__ == "__main__":
    unittest.main()
