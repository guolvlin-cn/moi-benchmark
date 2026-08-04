import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from astra.runners.lifecycle_c0.core import (
    C0Controller,
    C0ControllerConfig,
    JsonlLedger,
    LifecycleConfigurationError,
    LifecycleControllerError,
    collect_process_cleanup_report,
    get_terminal_bench_trigger,
    get_terminal_bench_trigger_for_instruction,
    lifecycle_predicate_probe_source_sha256,
    parse_process_cleanup_report,
    process_probe_run_command,
    process_probe_source_path,
)


class Result:
    def __init__(self, return_code=0, stdout="", stderr=""):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


IDENTITY = {
    "pid": 1234,
    "ppid": 1200,
    "pgid": 1234,
    "sid": 1234,
    "start_ticks": 99,
    "exe": "/installed-agent/product",
    "cgroup": "0::/docker/test\n",
    "supervisor": {
        "pid": 1200,
        "ppid": 1,
        "pgid": 1200,
        "sid": 1200,
        "start_ticks": 90,
        "exe": "/usr/bin/python3",
        "cgroup": "0::/docker/test\n",
    },
}


def predicate_result(predicate_id, matched, evidence=None, return_code=None):
    payload = {
        "schema_version": 1,
        "predicate_id": predicate_id,
        "matched": matched,
        "evidence": evidence or {},
    }
    return Result(
        return_code=(0 if matched else 1) if return_code is None else return_code,
        stdout=json.dumps(payload),
    )


class FakeEnvironment:
    def __init__(self, predicate_results):
        self.predicate_results = list(predicate_results)
        self.commands = []

    async def exec(self, command, timeout_sec=None):
        self.commands.append(command)
        if command.startswith("cat "):
            return Result(stdout=json.dumps(IDENTITY))
        if self.predicate_results:
            return self.predicate_results.pop(0)
        return predicate_result(
            "terminal-bench.modernize-scientific-stack.partial-outputs", False
        )


class CoreTests(unittest.TestCase):
    def test_ledger_is_new_ordered_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.jsonl"
            ledger = JsonlLedger(path, "run-1")
            ledger.append("first")
            ledger.append("second", value=2)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([row["sequence"] for row in rows], [1, 2])
            self.assertEqual(rows[1]["value"], 2)

    def test_process_probe_is_reused_from_smoke(self):
        path = process_probe_source_path()
        self.assertEqual(path.name, "probe.py")
        self.assertEqual(path.parent.name, "astra_smoke")

    def test_strict_process_command_carries_container_deadline_and_report(self):
        command = process_probe_run_command(
            probe_path="/installed/probe.py",
            identity_path="/tmp/run/identity.json",
            stdout_path="/tmp/run/stdout",
            stderr_path="/tmp/run/stderr",
            stdin_path="/tmp/run/stdin",
            cwd="/app",
            child_argv=["/installed/product", "run"],
            deadline_sec=1200,
            cleanup_report_path="/tmp/run/cleanup.json",
            cleanup_grace_sec=2,
            strict_cleanup=True,
        )
        self.assertIn("--deadline-sec 1200", command)
        self.assertIn("--cleanup-report /tmp/run/cleanup.json", command)
        self.assertIn("--strict-cleanup", command)

    def test_cleanup_report_requires_zero_live_fault_free_terminal_status(self):
        report = {
            "schema_version": 1,
            "status": "clean",
            "reason": "deadline",
            "fault_action": False,
            "product_terminal_status": "timeout",
            "zero_live_proven": True,
            "remaining_pids_count": 0,
            "remaining_pids": [],
        }
        self.assertEqual(
            parse_process_cleanup_report(json.dumps(report)),
            report,
        )
        report["remaining_pids_count"] = 1
        with self.assertRaises(LifecycleControllerError):
            parse_process_cleanup_report(json.dumps(report))

    def test_four_terminal_bench_manifests_are_registered(self):
        for task_id in (
            "modernize-scientific-stack",
            "overfull-hbox",
            "build-pmars",
            "db-wal-recovery",
        ):
            manifest = get_terminal_bench_trigger(task_id)
            self.assertEqual(manifest.task_id, task_id)
            self.assertEqual(manifest.stable_observations, 2)

    def test_c0_jobs_keep_two_x_product_budget_and_separate_wrapper_overhead(self):
        repo_root = Path(__file__).resolve().parents[4]
        for runner in ("astra_terminal_bench", "hermes_terminal_bench"):
            config = yaml.safe_load(
                (
                    repo_root
                    / "astra"
                    / "runners"
                    / runner
                    / "c0-four-cases.yaml"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(config["timeout_multiplier"], 2.0)
            self.assertEqual(config["agent_timeout_multiplier"], 2.25)

    def test_instruction_hash_resolves_exactly_and_unknown_fails_closed(self):
        instruction_path = (
            Path(__file__).resolve().parents[4]
            / "work"
            / "terminal-bench-2-1"
            / "tasks"
            / "overfull-hbox"
            / "instruction.md"
        )
        instruction = instruction_path.read_text(encoding="utf-8")
        manifest = get_terminal_bench_trigger_for_instruction(
            f"\n{instruction.strip()}\n"
        )
        self.assertEqual(manifest.task_id, "overfull-hbox")
        with self.assertRaises(LifecycleConfigurationError):
            get_terminal_bench_trigger_for_instruction(instruction + "\nchanged")


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self, events, timeout=0.2, poll=0.001):
        return C0Controller(
            C0ControllerConfig(
                identity_path="/tmp/lifecycle/identity.json",
                predicate_probe_path="/installed-agent/lifecycle-predicate.py",
                trigger=get_terminal_bench_trigger("modernize-scientific-stack"),
                trigger_timeout_sec=timeout,
                poll_interval_sec=poll,
            ),
            lambda event, **fields: events.append((event, fields)),
        )

    async def test_hit_requires_two_identical_observations_then_noops(self):
        predicate_id = get_terminal_bench_trigger(
            "modernize-scientific-stack"
        ).predicate_id
        environment = FakeEnvironment(
            [
                predicate_result(predicate_id, True, {"state": "partial"}),
                predicate_result(predicate_id, True, {"state": "partial"}),
            ]
        )
        events = []
        outcome = await self._controller(events).run(environment, asyncio.Event())
        self.assertTrue(outcome.trigger_hit)
        self.assertFalse(outcome.fault_injected)
        self.assertEqual(outcome.reason, "clean_noop")
        self.assertEqual(
            [event for event, _ in events],
            [
                "lifecycle_controller_started",
                "product_process_registered",
                "trigger_observed",
                "fault_action",
            ],
        )
        self.assertEqual(
            events[0][1]["predicate_probe_source_sha256"],
            lifecycle_predicate_probe_source_sha256(),
        )
        self.assertEqual(events[-1][1], {"action": "noop", "executed": True})
        self.assertFalse(any(" kill " in f" {command} " for command in environment.commands))

    async def test_no_hit_is_an_outcome_not_an_exception(self):
        predicate_id = get_terminal_bench_trigger(
            "modernize-scientific-stack"
        ).predicate_id
        environment = FakeEnvironment([predicate_result(predicate_id, False)] * 20)
        events = []
        outcome = await self._controller(events, timeout=0.01).run(
            environment, asyncio.Event()
        )
        self.assertFalse(outcome.trigger_hit)
        self.assertFalse(outcome.fault_injected)
        self.assertEqual(outcome.reason, "controller_trigger_timeout")
        self.assertEqual(
            events[-1],
            ("trigger_no_hit", {"reason": "controller_trigger_timeout"}),
        )

    async def test_probe_error_fails_closed_and_is_recorded(self):
        predicate_id = get_terminal_bench_trigger(
            "modernize-scientific-stack"
        ).predicate_id
        environment = FakeEnvironment(
            [predicate_result(predicate_id, False, return_code=2)]
        )
        events = []
        with self.assertRaises(LifecycleControllerError):
            await self._controller(events).run(environment, asyncio.Event())
        self.assertEqual(events[-1][0], "lifecycle_controller_failed")


class CleanupCollectorTests(unittest.IsolatedAsyncioTestCase):
    def _report(self, terminal_status: str = "completed") -> dict:
        return {
            "schema_version": 1,
            "status": "clean",
            "reason": "normal_exit",
            "fault_action": False,
            "product_terminal_status": terminal_status,
            "zero_live_proven": True,
            "remaining_pids_count": 0,
            "remaining_pids": [],
        }

    async def test_cleanup_report_is_read_immediately(self) -> None:
        raw = json.dumps(self._report()) + "\n"

        class Environment:
            async def exec(self, **_kwargs):
                return Result(return_code=0, stdout=raw)

        report, digest = await collect_process_cleanup_report(
            Environment(),
            probe_path="/installed/probe.py",
            identity_path="/tmp/identity.json",
            cleanup_report_path="/tmp/cleanup.json",
            request_cleanup=False,
        )

        self.assertEqual(report["product_terminal_status"], "completed")
        self.assertEqual(digest, hashlib.sha256(raw.encode()).hexdigest())

    async def test_delayed_cleanup_report_is_retried(self) -> None:
        raw = json.dumps(self._report()) + "\n"

        class Environment:
            def __init__(self):
                self.calls = 0

            async def exec(self, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return Result(return_code=1)
                if self.calls == 2:
                    return Result(return_code=0, stdout="")
                return Result(return_code=0, stdout=raw)

        environment = Environment()
        report, _digest = await collect_process_cleanup_report(
            environment,
            probe_path="/installed/probe.py",
            identity_path="/tmp/identity.json",
            cleanup_report_path="/tmp/cleanup.json",
            request_cleanup=False,
        )

        self.assertEqual(report, self._report())
        self.assertEqual(environment.calls, 3)

    async def test_cleanup_read_timeout_does_not_shrink_during_retry(
        self,
    ) -> None:
        raw = json.dumps(self._report()) + "\n"

        class Environment:
            def __init__(self):
                self.timeouts = []

            async def exec(self, *, timeout_sec, **_kwargs):
                self.timeouts.append(timeout_sec)
                if len(self.timeouts) == 1:
                    return Result(return_code=1)
                if timeout_sec < 0.2:
                    raise RuntimeError(
                        f"Command timed out after {timeout_sec} seconds"
                    )
                return Result(return_code=0, stdout=raw)

        environment = Environment()
        report, _digest = await collect_process_cleanup_report(
            environment,
            probe_path="/installed/probe.py",
            identity_path="/tmp/identity.json",
            cleanup_report_path="/tmp/cleanup.json",
            request_cleanup=False,
            cleanup_timeout_sec=0.2,
        )

        self.assertEqual(report, self._report())
        self.assertEqual(environment.timeouts, [0.2, 0.2])

    async def test_timeout_cleanup_report_is_preserved(self) -> None:
        timeout_report = self._report("timeout")
        timeout_report["reason"] = "deadline"
        raw = json.dumps(timeout_report) + "\n"

        class Environment:
            async def exec(self, **_kwargs):
                return Result(return_code=0, stdout=raw)

        report, _digest = await collect_process_cleanup_report(
            Environment(),
            probe_path="/installed/probe.py",
            identity_path="/tmp/identity.json",
            cleanup_report_path="/tmp/cleanup.json",
            request_cleanup=False,
        )

        self.assertEqual(report["product_terminal_status"], "timeout")
        self.assertEqual(report["reason"], "deadline")

    async def test_late_report_wins_over_cleanup_request_race(self) -> None:
        raw = json.dumps(self._report("cancelled")) + "\n"

        class Environment:
            def __init__(self):
                self.calls = 0

            async def exec(self, command, **_kwargs):
                self.calls += 1
                if " cleanup " in f" {command} ":
                    return Result(return_code=4)
                if self.calls == 2:
                    return Result(return_code=1)
                return Result(return_code=0, stdout=raw)

        environment = Environment()
        report, _digest = await collect_process_cleanup_report(
            environment,
            probe_path="/installed/probe.py",
            identity_path="/tmp/identity.json",
            cleanup_report_path="/tmp/cleanup.json",
            request_cleanup=True,
            cleanup_timeout_sec=0.2,
        )

        self.assertEqual(report["product_terminal_status"], "cancelled")
        self.assertEqual(environment.calls, 3)

    async def test_missing_cleanup_report_still_fails_strictly(self) -> None:
        class Environment:
            def __init__(self):
                self.calls = 0

            async def exec(self, **_kwargs):
                self.calls += 1
                return Result(return_code=1)

        environment = Environment()
        with self.assertRaisesRegex(
            LifecycleControllerError,
            "cleanup report is unavailable",
        ):
            await collect_process_cleanup_report(
                environment,
                probe_path="/installed/probe.py",
                identity_path="/tmp/identity.json",
                cleanup_report_path="/tmp/cleanup.json",
                request_cleanup=False,
                cleanup_timeout_sec=0.01,
            )
        self.assertGreaterEqual(environment.calls, 2)
