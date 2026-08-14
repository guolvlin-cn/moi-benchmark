#!/usr/bin/env python3
"""Container-local launcher and fail-closed registered process-tree killer."""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


_PR_SET_CHILD_SUBREAPER = 36
_STOPPED_STATES = {"T", "t"}
_FINGERPRINT_FIELDS = ("pid", "pgid", "sid", "start_ticks", "exe", "cgroup")
_ROSETTA_EXE = "/run/rosetta/rosetta"


def _proc_identity(pid: int) -> dict[str, Any]:
    stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    close_paren = stat_text.rfind(")")
    if close_paren < 0:
        raise RuntimeError("malformed /proc stat")
    fields = stat_text[close_paren + 2 :].split()
    if len(fields) <= 19:
        raise RuntimeError("incomplete /proc stat")
    return {
        "pid": pid,
        "state": fields[0],
        "ppid": int(fields[1]),
        "pgid": os.getpgid(pid),
        "sid": os.getsid(pid),
        "start_ticks": int(fields[19]),
        "exe": os.path.realpath(os.readlink(f"/proc/{pid}/exe")),
        "cgroup": Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8"),
    }


def _enable_subreaper() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = getattr(libc, "prctl", None)
    if prctl is None:
        raise RuntimeError("Linux prctl is unavailable")
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    prctl.restype = ctypes.c_int
    if prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _same_process(expected: dict[str, Any], current: dict[str, Any]) -> bool:
    return all(
        expected.get(field) == current.get(field) for field in _FINGERPRINT_FIELDS
    )


def _same_cleanup_process(
    expected: dict[str, Any], current: dict[str, Any]
) -> bool:
    if _same_process(expected, current):
        return True
    changed = {
        field
        for field in _FINGERPRINT_FIELDS
        if expected.get(field) != current.get(field)
    }
    return changed == {"exe"} and _ROSETTA_EXE in {
        expected.get("exe"),
        current.get("exe"),
    }


def _process_table() -> dict[int, dict[str, Any]]:
    table: dict[int, dict[str, Any]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
            table[pid] = _proc_identity(pid)
        except (OSError, RuntimeError):
            pass
    return table


def _ancestor_pids(pid: int, table: dict[int, dict[str, Any]]) -> set[int]:
    ancestors: set[int] = set()
    current = pid
    while current in table:
        parent = table[current]["ppid"]
        if parent <= 0 or parent in ancestors:
            break
        ancestors.add(parent)
        current = parent
    return ancestors


def _target_product_pids(
    root_pid: int,
    supervisor_pid: int,
    table: dict[int, dict[str, Any]],
    retained_pids: set[int],
) -> set[int]:
    """Return root descendants plus product descendants adopted by the subreaper."""
    selected = {root_pid}
    selected.update(pid for pid in retained_pids if pid in table)
    selected.update(
        pid
        for pid, identity in table.items()
        if identity["ppid"] == supervisor_pid and pid != supervisor_pid
    )
    changed = True
    while changed:
        changed = False
        for pid, identity in table.items():
            if pid not in selected and identity["ppid"] in selected:
                selected.add(pid)
                changed = True
    return selected


def _require_pidfd_support() -> None:
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("Linux pidfd support is required for process-tree injection")


def _open_verified_pidfd(
    snapshot: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    pidfd = os.pidfd_open(snapshot["pid"], 0)
    try:
        current = _proc_identity(snapshot["pid"])
        if not _same_process(snapshot, current) or current["state"] == "Z":
            raise RuntimeError(f"process {snapshot['pid']} changed before pidfd binding")
        return pidfd, current
    except Exception:
        os.close(pidfd)
        raise


def _open_verified_cleanup_handle(
    snapshot: dict[str, Any],
) -> tuple[int | None, dict[str, Any]]:
    try:
        return _open_verified_pidfd(snapshot)
    except OSError as exc:
        if exc.errno != errno.ENOSYS:
            raise
    current = _proc_identity(snapshot["pid"])
    if not _same_cleanup_process(snapshot, current) or current["state"] == "Z":
        changed = [
            field
            for field in _FINGERPRINT_FIELDS
            if snapshot.get(field) != current.get(field)
        ]
        raise RuntimeError(
            f"process {snapshot['pid']} changed before cleanup binding: "
            f"{','.join(changed) or 'state'}"
        )
    return None, current


def _send_verified_cleanup_signal(
    snapshot: dict[str, Any], pidfd: int | None, sig: int
) -> None:
    if pidfd is not None:
        try:
            signal.pidfd_send_signal(pidfd, sig)
            return
        except OSError as exc:
            if exc.errno != errno.ENOSYS:
                raise
    current = _proc_identity(snapshot["pid"])
    if not _same_cleanup_process(snapshot, current) or current["state"] == "Z":
        changed = [
            field
            for field in _FINGERPRINT_FIELDS
            if snapshot.get(field) != current.get(field)
        ]
        raise RuntimeError(
            f"process {snapshot['pid']} changed before fallback signal: "
            f"{','.join(changed) or 'state'}"
        )
    os.kill(snapshot["pid"], sig)


def _resume_frozen(
    frozen: dict[int, dict[str, Any]], pidfds: dict[int, int]
) -> None:
    for pid, identity in frozen.items():
        pidfd = pidfds.get(pid)
        if pidfd is None:
            continue
        try:
            current = _proc_identity(pid)
            if _same_process(identity, current) and current["state"] != "Z":
                signal.pidfd_send_signal(pidfd, signal.SIGCONT)
        except (OSError, RuntimeError):
            pass


def _close_pidfds(pidfds: dict[int, int | None]) -> None:
    for pidfd in pidfds.values():
        if pidfd is None:
            continue
        try:
            os.close(pidfd)
        except OSError:
            pass


def _freeze_registered_tree(
    root_identity: dict[str, Any],
    supervisor_identity: dict[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[int, int], int]:
    root_pid = root_identity["pid"]
    supervisor_pid = supervisor_identity["pid"]
    frozen: dict[int, dict[str, Any]] = {}
    pidfds: dict[int, int] = {}
    stable_rounds = 0
    freeze_rounds = 0
    deadline = time.monotonic() + 2.0
    try:
        while time.monotonic() < deadline:
            freeze_rounds += 1
            table = _process_table()
            current_root = table.get(root_pid)
            current_supervisor = table.get(supervisor_pid)
            if (
                current_root is None
                or current_supervisor is None
                or not _same_process(root_identity, current_root)
                or not _same_process(supervisor_identity, current_supervisor)
                or current_root["state"] == "Z"
            ):
                raise RuntimeError("registered root or supervisor identity changed")

            targets = _target_product_pids(
                root_pid, supervisor_pid, table, set(frozen)
            )
            protected = {
                1,
                os.getpid(),
                supervisor_pid,
                *_ancestor_pids(os.getpid(), table),
            }
            unsafe = sorted(targets & protected)
            if unsafe:
                raise RuntimeError(f"refusing unsafe process-tree targets {unsafe}")

            for pid in sorted(targets):
                snapshot = table.get(pid)
                if snapshot is None or snapshot["state"] == "Z":
                    continue
                previous = frozen.get(pid)
                if previous is not None:
                    if not _same_process(previous, snapshot):
                        raise RuntimeError(f"process {pid} identity changed during freeze")
                else:
                    pidfd, current = _open_verified_pidfd(snapshot)
                    pidfds[pid] = pidfd
                    frozen[pid] = current
                signal.pidfd_send_signal(pidfds[pid], signal.SIGSTOP)

            time.sleep(0.01)
            verify_table = _process_table()
            verify_targets = _target_product_pids(
                root_pid, supervisor_pid, verify_table, set(frozen)
            )
            live_targets = {
                pid
                for pid in verify_targets
                if pid in verify_table and verify_table[pid]["state"] != "Z"
            }
            all_stopped = True
            for pid in live_targets:
                current = verify_table[pid]
                if pid not in frozen:
                    all_stopped = False
                    continue
                if not _same_process(frozen[pid], current):
                    raise RuntimeError(f"process {pid} identity changed after freeze")
                if current["state"] not in _STOPPED_STATES:
                    all_stopped = False

            frozen_live = {
                pid
                for pid, identity in frozen.items()
                if pid in verify_table
                and _same_process(identity, verify_table[pid])
                and verify_table[pid]["state"] != "Z"
            }
            if (
                root_pid in live_targets
                and live_targets == frozen_live
                and all_stopped
            ):
                stable_rounds += 1
                if stable_rounds >= 2:
                    return frozen, pidfds, freeze_rounds
            else:
                stable_rounds = 0
        raise RuntimeError("process tree did not reach a stable frozen state")
    except Exception:
        _resume_frozen(frozen, pidfds)
        _close_pidfds(pidfds)
        raise


def _process_depth(pid: int, frozen: dict[int, dict[str, Any]]) -> int:
    depth = 0
    current = pid
    seen: set[int] = set()
    while current in frozen and current not in seen:
        seen.add(current)
        parent = frozen[current]["ppid"]
        if parent not in frozen:
            break
        depth += 1
        current = parent
    return depth


def _validate_frozen_tree(frozen: dict[int, dict[str, Any]]) -> None:
    for pid, expected in frozen.items():
        current = _proc_identity(pid)
        if (
            not _same_process(expected, current)
            or current["state"] not in _STOPPED_STATES
        ):
            raise RuntimeError(f"frozen process {pid} changed before SIGKILL")


def _terminate_frozen_tree(
    frozen: dict[int, dict[str, Any]],
    pidfds: dict[int, int],
    root_pid: int,
) -> tuple[list[int], list[str]]:
    ordered_pids = sorted(
        frozen,
        key=lambda pid: (pid == root_pid, -_process_depth(pid, frozen), pid),
    )
    signal_errors: list[str] = []
    for pid in ordered_pids:
        try:
            signal.pidfd_send_signal(pidfds[pid], signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            signal_errors.append(f"{pid}:{exc.errno}")

    surviving: list[int] = []
    for _ in range(200):
        surviving = []
        for pid, expected in frozen.items():
            try:
                current = _proc_identity(pid)
            except (OSError, RuntimeError):
                continue
            if _same_process(expected, current) and current["state"] != "Z":
                surviving.append(pid)
        if not surviving:
            break
        time.sleep(0.01)
    return sorted(surviving), signal_errors


def _strict_cleanup_targets(
    root_identity: dict[str, Any],
    supervisor_identity: dict[str, Any],
    retained: dict[int, dict[str, Any]],
    table: dict[int, dict[str, Any]],
) -> set[int]:
    """Find the registered tree, including descendants adopted by the subreaper."""
    supervisor_pid = supervisor_identity["pid"]
    current_supervisor = table.get(supervisor_pid)
    if (
        current_supervisor is None
        or not _same_process(supervisor_identity, current_supervisor)
        or current_supervisor["state"] == "Z"
    ):
        raise RuntimeError("strict-cleanup supervisor identity changed")

    selected: set[int] = set()
    current_root = table.get(root_identity["pid"])
    if current_root is not None:
        if not _same_process(root_identity, current_root):
            raise RuntimeError("strict-cleanup root identity changed")
        if current_root["state"] != "Z":
            selected.add(root_identity["pid"])

    for pid, expected in retained.items():
        current = table.get(pid)
        if (
            current is not None
            and _same_process(expected, current)
            and current["state"] != "Z"
        ):
            selected.add(pid)

    selected.update(
        pid
        for pid, identity in table.items()
        if identity["ppid"] == supervisor_pid
        and pid != supervisor_pid
        and identity["state"] != "Z"
    )
    changed = True
    while changed:
        changed = False
        for pid, identity in table.items():
            if (
                pid not in selected
                and identity["ppid"] in selected
                and identity["state"] != "Z"
            ):
                selected.add(pid)
                changed = True
    return selected


def _strict_teardown(
    root_identity: dict[str, Any],
    supervisor_identity: dict[str, Any],
    cleanup_grace_sec: float,
) -> dict[str, Any]:
    """Terminate and prove absence of one registered product tree."""
    _require_pidfd_support()
    retained: dict[int, dict[str, Any]] = {}
    pidfds: dict[int, int | None] = {}
    term_targeted: set[int] = set()
    kill_targeted: set[int] = set()
    signal_errors: list[str] = []
    supervisor_pid = supervisor_identity["pid"]

    def bind_live_targets() -> set[int]:
        table = _process_table()
        targets = _strict_cleanup_targets(
            root_identity,
            supervisor_identity,
            retained,
            table,
        )
        protected = {
            1,
            os.getpid(),
            supervisor_pid,
            *_ancestor_pids(os.getpid(), table),
        }
        unsafe = sorted(targets & protected)
        if unsafe:
            raise RuntimeError(f"refusing unsafe strict-cleanup targets {unsafe}")
        live: set[int] = set()
        for pid in sorted(targets):
            current = table.get(pid)
            if current is None or current["state"] == "Z":
                continue
            previous = retained.get(pid)
            if previous is not None:
                if not _same_process(previous, current):
                    raise RuntimeError(
                        f"process {pid} identity changed during strict cleanup"
                    )
            else:
                pidfd, verified = _open_verified_cleanup_handle(current)
                pidfds[pid] = pidfd
                retained[pid] = verified
            live.add(pid)
        return live

    def send_to(pids: set[int], sig: int, targeted: set[int]) -> None:
        for pid in sorted(pids):
            targeted.add(pid)
            try:
                _send_verified_cleanup_signal(
                    retained[pid], pidfds[pid], sig
                )
            except ProcessLookupError:
                pass
            except OSError as exc:
                signal_errors.append(f"{pid}:{sig}:{exc.errno}")

    remaining: set[int] = set()
    try:
        term_deadline = time.monotonic() + cleanup_grace_sec
        while True:
            remaining = bind_live_targets()
            if not remaining or time.monotonic() >= term_deadline:
                break
            send_to(remaining - term_targeted, signal.SIGTERM, term_targeted)
            time.sleep(0.02)

        kill_deadline = time.monotonic() + 2.0
        zero_rounds = 0
        while time.monotonic() < kill_deadline:
            remaining = bind_live_targets()
            if not remaining:
                zero_rounds += 1
                if zero_rounds >= 2:
                    break
            else:
                zero_rounds = 0
                send_to(remaining, signal.SIGKILL, kill_targeted)
            time.sleep(0.01)
        remaining = bind_live_targets()
    finally:
        _close_pidfds(pidfds)

    return {
        "targeted_pids": sorted(retained),
        "term_targeted_pids": sorted(term_targeted),
        "kill_targeted_pids": sorted(kill_targeted),
        "term_signal": int(signal.SIGTERM),
        "kill_signal": int(signal.SIGKILL),
        "signal_errors": signal_errors,
        "remaining_pids": sorted(remaining),
        "remaining_pids_count": len(remaining),
        "zero_live_proven": not remaining,
    }


def _read_successful_cleanup_report(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        isinstance(value, dict)
        and value.get("status") == "clean"
        and value.get("zero_live_proven") is True
        and value.get("remaining_pids_count") == 0
        and value.get("fault_action") is False
    ):
        return value
    return None


def _product_terminal_status(cleanup_reason: str, return_code: int) -> str:
    if cleanup_reason == "deadline" or return_code == 124:
        return "timeout"
    if cleanup_reason.startswith("supervisor_signal_") or return_code == 125:
        return "cancelled"
    return "completed" if return_code == 0 else "failed"


def _failed_cleanup_detail(exc: Exception) -> dict[str, Any]:
    return {
        "targeted_pids": [],
        "term_targeted_pids": [],
        "kill_targeted_pids": [],
        "term_signal": int(signal.SIGTERM),
        "kill_signal": int(signal.SIGKILL),
        "signal_errors": [f"{type(exc).__name__}:{exc}"],
        "remaining_pids": [],
        "remaining_pids_count": 0,
        "zero_live_proven": False,
    }


def _reap_adopted_children() -> None:
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _validate_registered_root(
    identity: dict[str, Any], expected_exe: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    pid = identity.get("pid")
    pgid = identity.get("pgid")
    sid = identity.get("sid")
    supervisor = identity.get("supervisor")
    if (
        not isinstance(pid, int)
        or pid <= 1
        or pid != pgid
        or pid != sid
        or not isinstance(supervisor, dict)
        or not isinstance(supervisor.get("pid"), int)
        or supervisor["pid"] <= 1
        or supervisor["pid"] == pid
        or identity.get("ppid") != supervisor["pid"]
    ):
        raise RuntimeError("refusing unsafe root or supervisor identity")

    current = _proc_identity(pid)
    current_supervisor = _proc_identity(supervisor["pid"])
    expected_realpath = os.path.realpath(expected_exe)
    if (
        not _same_process(identity, current)
        or not _same_process(supervisor, current_supervisor)
        or current["exe"] != expected_realpath
        or current["ppid"] != supervisor["pid"]
        or current["state"] == "Z"
        or current_supervisor["state"] == "Z"
    ):
        raise RuntimeError("registered root or supervisor identity changed")
    return current, current_supervisor


def _copy_filtered_jsonl(source: Any, destination: Any, excluded: set[str]) -> None:
    for raw_line in source:
        try:
            row = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            destination.write(raw_line)
            continue
        if not isinstance(row, dict) or row.get("type") not in excluded:
            destination.write(raw_line)
    destination.flush()


def run_child(args: argparse.Namespace) -> int:
    if not args.command:
        raise RuntimeError("missing child command")
    command = args.command[1:] if args.command[0] == "--" else args.command
    stdin_path = Path(args.stdin)
    stdout_path = Path(args.stdout)
    stderr_path = Path(args.stderr)
    for path in (stdout_path, stderr_path, Path(args.identity)):
        path.parent.mkdir(parents=True, exist_ok=True)
    strict_cleanup = bool(args.strict_cleanup)
    if strict_cleanup:
        if args.deadline_sec is None or args.deadline_sec <= 0:
            raise RuntimeError("strict cleanup requires a positive deadline")
        if not args.cleanup_report:
            raise RuntimeError("strict cleanup requires --cleanup-report")
        if args.cleanup_grace_sec < 0:
            raise RuntimeError("cleanup grace must be non-negative")
    _enable_subreaper()
    supervisor = _proc_identity(os.getpid())
    requested_signals: list[int] = []
    previous_handlers: dict[int, Any] = {}
    handled_signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    if strict_cleanup:
        def request_cleanup(signum: int, _frame: Any) -> None:
            requested_signals.append(signum)

        for handled_signal in handled_signals:
            previous_handlers[handled_signal] = signal.getsignal(handled_signal)
            signal.signal(handled_signal, request_cleanup)

    cleanup_detail: dict[str, Any] | None = None
    cleanup_reason = "normal_exit"
    return_code: int | None = None
    excluded_stdout_events = frozenset(
        getattr(args, "exclude_stdout_json_event", ())
    )
    output_error: list[BaseException] = []
    with stdin_path.open("rb") as stdin, stdout_path.open(
        "wb"
    ) as stdout, stderr_path.open("wb") as stderr:
        child = subprocess.Popen(
            command,
            cwd=args.cwd,
            stdin=stdin,
            stdout=(subprocess.PIPE if excluded_stdout_events else stdout),
            stderr=stderr,
            start_new_session=True,
            close_fds=True,
        )
        output_thread: threading.Thread | None = None
        if excluded_stdout_events:
            assert child.stdout is not None

            def copy_stdout() -> None:
                try:
                    _copy_filtered_jsonl(
                        child.stdout,
                        stdout,
                        set(excluded_stdout_events),
                    )
                except BaseException as exc:
                    output_error.append(exc)
                finally:
                    child.stdout.close()

            output_thread = threading.Thread(target=copy_stdout, daemon=True)
            output_thread.start()
        identity = None
        for _ in range(100):
            try:
                candidate = _proc_identity(child.pid)
                if (
                    candidate["pid"] == candidate["pgid"] == candidate["sid"]
                    and candidate["ppid"] == supervisor["pid"]
                ):
                    identity = {**candidate, "supervisor": supervisor}
                    break
            except (FileNotFoundError, ProcessLookupError):
                pass
            time.sleep(0.01)
        if identity is None:
            child.wait()
            if output_thread is not None:
                output_thread.join()
            if output_error:
                raise RuntimeError(
                    "failed to filter child stdout"
                ) from output_error[0]
            raise RuntimeError("child exited before an isolated identity was registered")
        _atomic_json(Path(args.identity), identity)
        if not strict_cleanup:
            return_code = child.wait()
        else:
            deadline = time.monotonic() + args.deadline_sec
            try:
                while True:
                    return_code = child.poll()
                    if return_code is not None:
                        cleanup_reason = "normal_exit"
                        break
                    if requested_signals:
                        cleanup_reason = f"supervisor_signal_{requested_signals[0]}"
                        break
                    if time.monotonic() >= deadline:
                        cleanup_reason = "deadline"
                        break
                    time.sleep(0.05)
                cleanup_started = time.monotonic()
                cleanup_error: Exception | None = None
                try:
                    cleanup_detail = _strict_teardown(
                        identity,
                        supervisor,
                        args.cleanup_grace_sec,
                    )
                except Exception as exc:
                    cleanup_error = exc
                    cleanup_detail = _failed_cleanup_detail(exc)
                if cleanup_error is None:
                    if child.poll() is None:
                        return_code = child.wait(timeout=3)
                    else:
                        return_code = child.returncode
                else:
                    observed_return_code = child.poll()
                    return_code = (
                        observed_return_code
                        if observed_return_code is not None
                        else 1
                    )
                if cleanup_reason == "deadline":
                    return_code = 124
                elif cleanup_reason.startswith("supervisor_signal_"):
                    return_code = 125
                _reap_adopted_children()
                terminal_status = _product_terminal_status(
                    cleanup_reason,
                    return_code,
                )
                cleanup_report = {
                    "schema_version": 1,
                    "status": (
                        "clean"
                        if cleanup_detail["zero_live_proven"]
                        else "cleanup_failed"
                    ),
                    "reason": cleanup_reason,
                    "fault_action": False,
                    "deadline_sec": args.deadline_sec,
                    "cleanup_grace_sec": args.cleanup_grace_sec,
                    "root_pid": identity["pid"],
                    "supervisor_pid": supervisor["pid"],
                    "return_code": return_code,
                    "product_terminal_status": terminal_status,
                    "cleanup_duration_sec": round(
                        time.monotonic() - cleanup_started, 6
                    ),
                    **cleanup_detail,
                }
                _atomic_json(Path(args.cleanup_report), cleanup_report)
                if cleanup_error is not None:
                    raise RuntimeError(
                        "strict cleanup failed before zero-live proof"
                    ) from cleanup_error
                if not cleanup_detail["zero_live_proven"]:
                    raise RuntimeError(
                        "strict cleanup could not prove zero live product processes"
                    )
            finally:
                for handled_signal, previous in previous_handlers.items():
                    signal.signal(handled_signal, previous)
        if output_thread is not None:
            output_thread.join()
        if output_error:
            raise RuntimeError("failed to filter child stdout") from output_error[0]
    assert return_code is not None
    summary = {"status": "exited", "return_code": return_code, "identity": identity}
    if strict_cleanup:
        summary.update(
            {
                "cleanup": cleanup_detail,
                "cleanup_reason": cleanup_reason,
            }
        )
    print(json.dumps(summary, sort_keys=True))
    return 128 + (-return_code) if return_code < 0 else return_code


def request_registered_cleanup(args: argparse.Namespace) -> int:
    """Idempotently ask a strict supervisor to clean its registered tree."""
    report_path = Path(args.cleanup_report)
    report = _read_successful_cleanup_report(report_path)
    if report is not None:
        print(json.dumps(report, sort_keys=True))
        return 0

    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    supervisor = identity.get("supervisor")
    if not isinstance(supervisor, dict):
        raise RuntimeError("registered identity has no supervisor")
    pidfd, current = _open_verified_cleanup_handle(supervisor)
    try:
        _send_verified_cleanup_signal(current, pidfd, signal.SIGTERM)
    except ProcessLookupError:
        pass
    finally:
        if pidfd is not None:
            os.close(pidfd)

    deadline = time.monotonic() + args.timeout_sec
    while time.monotonic() < deadline:
        report = _read_successful_cleanup_report(report_path)
        if report is not None:
            print(json.dumps(report, sort_keys=True))
            return 0
        time.sleep(0.05)
    raise RuntimeError("strict supervisor did not publish a successful cleanup report")


def inspect_registered_root(args: argparse.Namespace) -> int:
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    root, supervisor = _validate_registered_root(identity, args.expected_exe)
    print(
        json.dumps(
            {
                "status": "live",
                "pid": root["pid"],
                "start_ticks": root["start_ticks"],
                "supervisor_pid": supervisor["pid"],
            },
            sort_keys=True,
        )
    )
    return 0


def kill_registered_tree(args: argparse.Namespace) -> int:
    _require_pidfd_support()
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    root, supervisor = _validate_registered_root(identity, args.expected_exe)
    frozen, pidfds, freeze_rounds = _freeze_registered_tree(root, supervisor)
    kill_started = False
    try:
        descendant_pids = sorted(pid for pid in frozen if pid != root["pid"])
        if not descendant_pids:
            raise RuntimeError("no registered product descendant was present at trigger")
        _validate_frozen_tree(frozen)
        kill_started = True
        surviving_tree_pids, signal_errors = _terminate_frozen_tree(
            frozen, pidfds, root["pid"]
        )
    finally:
        if not kill_started:
            _resume_frozen(frozen, pidfds)
        _close_pidfds(pidfds)

    status = (
        "killed"
        if not surviving_tree_pids and not signal_errors
        else "tree_members_survived"
    )
    print(
        json.dumps(
            {
                "status": status,
                "root_pid": root["pid"],
                "supervisor_pid": supervisor["pid"],
                "signal": int(signal.SIGKILL),
                "freeze_signal": int(signal.SIGSTOP),
                "freeze_rounds": freeze_rounds,
                "targeted_tree_pids": sorted(frozen),
                "targeted_descendant_pids": descendant_pids,
                "targeted_pgids": sorted(
                    {process["pgid"] for process in frozen.values()}
                ),
                "targeted_sids": sorted(
                    {process["sid"] for process in frozen.values()}
                ),
                "surviving_tree_pids": surviving_tree_pids,
                "signal_errors": signal_errors,
            },
            sort_keys=True,
        )
    )
    return 0 if status == "killed" else 5


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--identity", required=True)
    run.add_argument("--stdout", required=True)
    run.add_argument("--stderr", required=True)
    run.add_argument("--stdin", required=True)
    run.add_argument("--cwd", required=True)
    run.add_argument("--deadline-sec", type=float)
    run.add_argument("--cleanup-report")
    run.add_argument("--cleanup-grace-sec", type=float, default=2.0)
    run.add_argument("--strict-cleanup", action="store_true")
    run.add_argument("--exclude-stdout-json-event", action="append", default=[])
    run.add_argument("command", nargs=argparse.REMAINDER)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--identity", required=True)
    cleanup.add_argument("--cleanup-report", required=True)
    cleanup.add_argument("--timeout-sec", type=float, default=10.0)
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--identity", required=True)
    inspect.add_argument("--expected-exe", required=True)
    kill = subparsers.add_parser("kill")
    kill.add_argument("--identity", required=True)
    kill.add_argument("--expected-exe", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.action == "run":
            return run_child(args)
        if args.action == "cleanup":
            return request_registered_cleanup(args)
        if args.action == "inspect":
            return inspect_registered_root(args)
        return kill_registered_tree(args)
    except Exception as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}))
        return 4


if __name__ == "__main__":
    sys.exit(main())
