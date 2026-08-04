import argparse
import errno
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import call, patch

from astra.runners.astra_smoke import probe


SUPERVISOR = {
    "pid": 100,
    "state": "S",
    "ppid": 1,
    "pgid": 100,
    "sid": 100,
    "start_ticks": 10,
    "exe": "/usr/bin/python3",
    "cgroup": "0::/docker/test\n",
}
ROOT = {
    "pid": 200,
    "state": "S",
    "ppid": 100,
    "pgid": 200,
    "sid": 200,
    "start_ticks": 20,
    "exe": "/installed-agent/astra",
    "cgroup": "0::/docker/test\n",
}
DETACHED_CHILD = {
    "pid": 201,
    "state": "S",
    "ppid": 200,
    "pgid": 201,
    "sid": 201,
    "start_ticks": 21,
    "exe": "/usr/bin/sleep",
    "cgroup": "0::/docker/test\n",
}
ADOPTED_CHILD = {
    "pid": 202,
    "state": "S",
    "ppid": 100,
    "pgid": 202,
    "sid": 202,
    "start_ticks": 22,
    "exe": "/usr/bin/bash",
    "cgroup": "0::/docker/test\n",
}


class ProbeTests(unittest.TestCase):
    def test_product_terminal_status_preserves_timeout_and_cancel_exit_codes(self):
        self.assertEqual(
            probe._product_terminal_status("normal_exit", 124),
            "timeout",
        )
        self.assertEqual(
            probe._product_terminal_status("normal_exit", 125),
            "cancelled",
        )
        self.assertEqual(
            probe._product_terminal_status("normal_exit", 2),
            "failed",
        )

    def test_atomic_cleanup_report_fsyncs_file_and_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "product.cleanup.json"
            with patch.object(probe.os, "fsync") as fsync:
                probe._atomic_json(
                    path,
                    {
                        "status": "clean",
                        "zero_live_proven": True,
                    },
                )

            self.assertEqual(fsync.call_count, 2)
            self.assertEqual(
                json.loads(path.read_text()),
                {"status": "clean", "zero_live_proven": True},
            )
            self.assertEqual(
                [item.name for item in path.parent.iterdir()],
                ["product.cleanup.json"],
            )

    def test_cleanup_handle_falls_back_only_when_pidfd_is_unimplemented(self):
        unavailable = OSError(errno.ENOSYS, "Function not implemented")
        with patch.object(
            probe, "_open_verified_pidfd", side_effect=unavailable
        ), patch.object(probe, "_proc_identity", return_value=ROOT):
            pidfd, identity = probe._open_verified_cleanup_handle(ROOT)

        self.assertIsNone(pidfd)
        self.assertEqual(identity, ROOT)

        denied = OSError(errno.EPERM, "Operation not permitted")
        with patch.object(
            probe, "_open_verified_pidfd", side_effect=denied
        ):
            with self.assertRaises(OSError) as raised:
                probe._open_verified_cleanup_handle(ROOT)
        self.assertEqual(raised.exception.errno, errno.EPERM)

    def test_cleanup_fallback_accepts_only_rosetta_exe_observer_difference(self):
        unavailable = OSError(errno.ENOSYS, "Function not implemented")
        rosetta = {**SUPERVISOR, "exe": probe._ROSETTA_EXE}
        with patch.object(
            probe, "_open_verified_pidfd", side_effect=unavailable
        ), patch.object(probe, "_proc_identity", return_value=rosetta):
            pidfd, identity = probe._open_verified_cleanup_handle(SUPERVISOR)
        self.assertIsNone(pidfd)
        self.assertEqual(identity, rosetta)

        changed = {**rosetta, "start_ticks": 999}
        with patch.object(
            probe, "_open_verified_pidfd", side_effect=unavailable
        ), patch.object(probe, "_proc_identity", return_value=changed):
            with self.assertRaisesRegex(RuntimeError, "start_ticks,exe|exe,start_ticks"):
                probe._open_verified_cleanup_handle(SUPERVISOR)

    def test_cleanup_fallback_revalidates_identity_before_os_kill(self):
        with patch.object(
            probe, "_proc_identity", return_value=ROOT
        ), patch.object(probe.os, "kill") as kill:
            probe._send_verified_cleanup_signal(ROOT, None, signal.SIGTERM)
        kill.assert_called_once_with(ROOT["pid"], signal.SIGTERM)

        changed = {**ROOT, "start_ticks": 999}
        with patch.object(
            probe, "_proc_identity", return_value=changed
        ), patch.object(probe.os, "kill") as kill:
            with self.assertRaisesRegex(RuntimeError, "changed"):
                probe._send_verified_cleanup_signal(
                    ROOT, None, signal.SIGKILL
                )
        kill.assert_not_called()

    def test_cleanup_signal_falls_back_when_pidfd_send_is_unimplemented(self):
        unavailable = OSError(errno.ENOSYS, "Function not implemented")
        with patch.object(
            probe.signal,
            "pidfd_send_signal",
            side_effect=unavailable,
            create=True,
        ), patch.object(
            probe, "_proc_identity", return_value=ROOT
        ), patch.object(probe.os, "kill") as kill:
            probe._send_verified_cleanup_signal(ROOT, 10, signal.SIGTERM)
        kill.assert_called_once_with(ROOT["pid"], signal.SIGTERM)

    def test_strict_cleanup_failure_publishes_failed_report(self):
        class Child:
            pid = ROOT["pid"]
            returncode = 0

            def poll(self):
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stdin_path = root / "stdin"
            stdin_path.write_text("")
            cleanup_path = root / "product.cleanup.json"
            args = argparse.Namespace(
                command=["/bin/true"],
                stdin=str(stdin_path),
                stdout=str(root / "stdout"),
                stderr=str(root / "stderr"),
                identity=str(root / "identity.json"),
                cwd=str(root),
                strict_cleanup=True,
                deadline_sec=30,
                cleanup_report=str(cleanup_path),
                cleanup_grace_sec=0.1,
            )
            with patch.object(
                probe, "_enable_subreaper"
            ), patch.object(
                probe, "_proc_identity", side_effect=[SUPERVISOR, ROOT]
            ), patch.object(
                probe.subprocess, "Popen", return_value=Child()
            ), patch.object(
                probe,
                "_strict_teardown",
                side_effect=RuntimeError("identity changed"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "before zero-live proof"
                ):
                    probe.run_child(args)

            report = json.loads(cleanup_path.read_text())
            self.assertEqual(report["status"], "cleanup_failed")
            self.assertFalse(report["zero_live_proven"])
            self.assertEqual(report["remaining_pids_count"], 0)
            self.assertEqual(
                report["signal_errors"],
                ["RuntimeError:identity changed"],
            )

    def _run_strict_linux_child(
        self, root: Path, child_script: str, deadline_sec: float
    ) -> tuple[subprocess.CompletedProcess[str], dict, dict]:
        if os.environ.get("ASTRA_SMOKE_RUN_LINUX_INTEGRATION") != "1":
            self.skipTest("set ASTRA_SMOKE_RUN_LINUX_INTEGRATION=1 on Linux")
        if not Path("/proc").exists():
            self.skipTest("Linux /proc is required")
        identity_path = root / "identity.json"
        cleanup_path = root / "cleanup.json"
        stdin_path = root / "stdin"
        stdin_path.write_text("")
        result = subprocess.run(
            [
                sys.executable,
                str(Path(probe.__file__).resolve()),
                "run",
                "--identity",
                str(identity_path),
                "--stdout",
                str(root / "stdout"),
                "--stderr",
                str(root / "stderr"),
                "--stdin",
                str(stdin_path),
                "--cwd",
                str(root),
                "--deadline-sec",
                str(deadline_sec),
                "--cleanup-report",
                str(cleanup_path),
                "--cleanup-grace-sec",
                "0.1",
                "--strict-cleanup",
                "--",
                "/bin/sh",
                "-c",
                child_script,
            ],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        return (
            result,
            json.loads(identity_path.read_text()),
            json.loads(cleanup_path.read_text()),
        )

    def test_target_tree_includes_detached_and_subreaper_adopted_children(self):
        unrelated = {
            **DETACHED_CHILD,
            "pid": 300,
            "ppid": 1,
            "start_ticks": 30,
        }
        table = {
            identity["pid"]: identity
            for identity in (
                SUPERVISOR,
                ROOT,
                DETACHED_CHILD,
                ADOPTED_CHILD,
                unrelated,
            )
        }
        targets = probe._target_product_pids(200, 100, table, set())
        self.assertEqual(targets, {200, 201, 202})

    def test_kill_requires_and_reports_a_registered_descendant(self):
        identity = {**ROOT, "supervisor": SUPERVISOR}
        frozen = {
            200: {**ROOT, "state": "T"},
            201: {**DETACHED_CHILD, "state": "T"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity.json"
            path.write_text(json.dumps(identity))
            args = argparse.Namespace(
                identity=str(path), expected_exe="/installed-agent/astra"
            )
            output = io.StringIO()
            with patch.object(probe, "_require_pidfd_support"), patch.object(
                probe, "_validate_registered_root", return_value=(ROOT, SUPERVISOR)
            ), patch.object(
                probe,
                "_freeze_registered_tree",
                return_value=(frozen, {}, 2),
            ), patch.object(
                probe, "_validate_frozen_tree"
            ), patch.object(
                probe, "_terminate_frozen_tree", return_value=([], [])
            ), redirect_stdout(output):
                result = probe.kill_registered_tree(args)
        detail = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(detail["status"], "killed")
        self.assertEqual(detail["targeted_tree_pids"], [200, 201])
        self.assertEqual(detail["targeted_descendant_pids"], [201])
        self.assertEqual(detail["surviving_tree_pids"], [])

    def test_terminate_signals_detached_child_before_root_by_pidfd(self):
        frozen = {
            200: {**ROOT, "state": "T"},
            201: {**DETACHED_CHILD, "state": "T"},
        }
        identity_reads = {200: 0, 201: 0}

        def current_then_gone(pid):
            identity_reads[pid] += 1
            if identity_reads[pid] == 1:
                return frozen[pid]
            raise FileNotFoundError

        with patch.object(
            probe, "_proc_identity", side_effect=current_then_gone
        ), patch.object(
            signal, "pidfd_send_signal", create=True
        ) as send_signal:
            survivors, errors = probe._terminate_frozen_tree(
                frozen, {200: 10, 201: 11}, 200
            )
        self.assertEqual(survivors, [])
        self.assertEqual(errors, [])
        self.assertEqual(
            send_signal.call_args_list,
            [call(11, signal.SIGKILL), call(10, signal.SIGKILL)],
        )

    def test_registered_root_identity_change_is_refused(self):
        identity = {**ROOT, "supervisor": SUPERVISOR}
        changed = {**ROOT, "start_ticks": 999}
        with patch.object(
            probe, "_proc_identity", side_effect=[changed, SUPERVISOR]
        ):
            with self.assertRaises(RuntimeError):
                probe._validate_registered_root(
                    identity, "/installed-agent/astra"
                )

    def test_linux_integration_kills_descendant_in_another_session(self):
        if os.environ.get("ASTRA_SMOKE_RUN_LINUX_INTEGRATION") != "1":
            self.skipTest("set ASTRA_SMOKE_RUN_LINUX_INTEGRATION=1 on Linux")
        if not Path("/proc").exists():
            self.skipTest("Linux /proc is required")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity_path = root / "identity.json"
            trigger_path = root / "trigger"
            result_path = root / "result"
            stdin_path = root / "stdin"
            stdout_path = root / "stdout"
            stderr_path = root / "stderr"
            stdin_path.write_text("")
            child_script = (
                f"setsid /bin/sh -c 'touch {trigger_path}; "
                f"sleep 30; printf leaked > {result_path}' & wait"
            )
            runner = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(probe.__file__).resolve()),
                    "run",
                    "--identity",
                    str(identity_path),
                    "--stdout",
                    str(stdout_path),
                    "--stderr",
                    str(stderr_path),
                    "--stdin",
                    str(stdin_path),
                    "--cwd",
                    str(root),
                    "--",
                    "/bin/sh",
                    "-c",
                    child_script,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if identity_path.exists() and trigger_path.exists():
                        break
                    time.sleep(0.02)
                self.assertTrue(identity_path.exists())
                self.assertTrue(trigger_path.exists())
                identity = json.loads(identity_path.read_text())
                args = argparse.Namespace(
                    identity=str(identity_path),
                    expected_exe=identity["exe"],
                )
                output = io.StringIO()
                with redirect_stdout(output):
                    result = probe.kill_registered_tree(args)
                detail = json.loads(output.getvalue())
                self.assertEqual(result, 0)
                self.assertEqual(detail["surviving_tree_pids"], [])
                self.assertGreaterEqual(len(detail["targeted_sids"]), 2)
                self.assertFalse(result_path.exists())
                self.assertEqual(runner.wait(timeout=5), 137)
            finally:
                if runner.poll() is None:
                    runner.kill()
                    runner.wait(timeout=5)

    def test_strict_deadline_cleans_root_and_detached_descendant_before_return(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descendant_path = root / "descendant.pid"
            result, identity, cleanup = self._run_strict_linux_child(
                root,
                (
                    "setsid /bin/sh -c 'sleep 30' & "
                    f"echo $! > {descendant_path}; sleep 30"
                ),
                0.2,
            )
            descendant_pid = int(descendant_path.read_text())
            self.assertEqual(result.returncode, 124)
            self.assertEqual(cleanup["reason"], "deadline")
            self.assertEqual(cleanup["product_terminal_status"], "timeout")
            self.assertTrue(cleanup["zero_live_proven"])
            self.assertEqual(cleanup["remaining_pids"], [])
            self.assertFalse(Path(f"/proc/{identity['pid']}").exists())
            self.assertFalse(Path(f"/proc/{descendant_pid}").exists())

    def test_strict_cleanup_reaps_adopted_setsid_child_after_root_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descendant_path = root / "descendant.pid"
            result, identity, cleanup = self._run_strict_linux_child(
                root,
                f"setsid sleep 30 & echo $! > {descendant_path}; exit 0",
                5,
            )
            descendant_pid = int(descendant_path.read_text())
            self.assertEqual(result.returncode, 0)
            self.assertEqual(cleanup["reason"], "normal_exit")
            self.assertEqual(cleanup["product_terminal_status"], "completed")
            self.assertTrue(cleanup["zero_live_proven"])
            self.assertIn(descendant_pid, cleanup["targeted_pids"])
            self.assertFalse(Path(f"/proc/{identity['pid']}").exists())
            self.assertFalse(Path(f"/proc/{descendant_pid}").exists())

    def test_external_cleanup_request_waits_for_zero_live_report(self):
        if os.environ.get("ASTRA_SMOKE_RUN_LINUX_INTEGRATION") != "1":
            self.skipTest("set ASTRA_SMOKE_RUN_LINUX_INTEGRATION=1 on Linux")
        if not Path("/proc").exists():
            self.skipTest("Linux /proc is required")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity_path = root / "identity.json"
            cleanup_path = root / "cleanup.json"
            descendant_path = root / "descendant.pid"
            stdin_path = root / "stdin"
            stdin_path.write_text("")
            runner = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(probe.__file__).resolve()),
                    "run",
                    "--identity",
                    str(identity_path),
                    "--stdout",
                    str(root / "stdout"),
                    "--stderr",
                    str(root / "stderr"),
                    "--stdin",
                    str(stdin_path),
                    "--cwd",
                    str(root),
                    "--deadline-sec",
                    "30",
                    "--cleanup-report",
                    str(cleanup_path),
                    "--cleanup-grace-sec",
                    "0.1",
                    "--strict-cleanup",
                    "--",
                    "/bin/sh",
                    "-c",
                    (
                        "setsid sleep 30 & "
                        f"echo $! > {descendant_path}; sleep 30"
                    ),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if identity_path.exists() and descendant_path.exists():
                        break
                    time.sleep(0.02)
                self.assertTrue(identity_path.exists())
                self.assertTrue(descendant_path.exists())
                cleanup_request = subprocess.run(
                    [
                        sys.executable,
                        str(Path(probe.__file__).resolve()),
                        "cleanup",
                        "--identity",
                        str(identity_path),
                        "--cleanup-report",
                        str(cleanup_path),
                        "--timeout-sec",
                        "5",
                    ],
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(
                    cleanup_request.returncode,
                    0,
                    cleanup_request.stdout + cleanup_request.stderr,
                )
                cleanup = json.loads(cleanup_request.stdout)
                self.assertEqual(cleanup["product_terminal_status"], "cancelled")
                self.assertTrue(cleanup["zero_live_proven"])
                self.assertEqual(runner.wait(timeout=5), 125)
                runner.communicate(timeout=1)
                descendant_pid = int(descendant_path.read_text())
                self.assertFalse(Path(f"/proc/{descendant_pid}").exists())
            finally:
                if runner.poll() is None:
                    runner.kill()
                    runner.wait(timeout=5)
                runner.communicate(timeout=1)

    def test_proc_identity_tracks_parent_session_state_and_cgroup(self):
        if not Path("/proc").exists():
            self.skipTest("Linux /proc is required")
        identity = probe._proc_identity(os.getpid())
        self.assertEqual(identity["pid"], os.getpid())
        self.assertIsInstance(identity["ppid"], int)
        self.assertIsInstance(identity["sid"], int)
        self.assertIsInstance(identity["state"], str)
        self.assertTrue(identity["cgroup"])
