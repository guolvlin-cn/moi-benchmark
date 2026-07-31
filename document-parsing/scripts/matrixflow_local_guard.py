#!/usr/bin/env python3
"""Health guard and automatic recovery for the local Matrixflow parser stack."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


DEFAULT_MATRIXFLOW_DIR = Path(
    os.getenv(
        "MATRIXFLOW_LOCAL_DIR",
        "/Users/wangyaqi/Documents/matrixflow-4.1.14-dev",
    )
)
DEFAULT_VENV = Path(
    os.getenv(
        "MATRIXFLOW_PYTHON_VENV",
        "/Users/wangyaqi/Documents/cursor_project/.venv",
    )
)
DEFAULT_TMUX_SESSION = os.getenv("MATRIXFLOW_TMUX_SESSION", "matrixflow-414")
DEFAULT_MO_OVERRIDE = Path(
    os.getenv(
        "MATRIXFLOW_MO_OVERRIDE",
        "/private/tmp/matrixflow-4.1.14-mo-volume.yaml",
    )
)
DEFAULT_LOCK = Path("/private/tmp/matrixflow-local-guard.lock")

REQUIRED_WORKFLOW_NODE_TYPES = {
    "AudioParseNode",
    "ChunkNode",
    "ChunkNodeV2",
    "CleanerNodeV2",
    "DataAugmentationNode",
    "DocumentCleanerNode",
    "DocumentParseNode",
    "EmbeddingNodeV2",
    "ExtractNode",
    "FileRouterNode",
    "ImageParseNode",
    "RootNode",
    "StructedExtractionNode",
    "VideoParseNode",
    "WriteNode",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=check,
    )


def check_tcp(name: str, host: str, port: int, timeout: float) -> CheckResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return CheckResult(name, True, f"{host}:{port}")
    except OSError as exc:
        return CheckResult(name, False, f"{host}:{port}: {exc}")


def check_sql(args: argparse.Namespace) -> CheckResult:
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = args.mysql_password
    last_detail = "not checked"
    for attempt in range(1, args.sql_probe_attempts + 1):
        try:
            result = run_command(
                [
                    "mysql",
                    "-h",
                    args.mysql_host,
                    "-P",
                    str(args.mysql_port),
                    "-u",
                    args.mysql_user,
                    "--connect-timeout",
                    str(max(1, int(args.check_timeout))),
                    "-N",
                    "-e",
                    "SELECT 1",
                ],
                env=environment,
                timeout=args.check_timeout + 2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            last_detail = str(exc)
        else:
            if result.returncode == 0 and result.stdout.strip() == "1":
                return CheckResult("matrixone_sql", True, "SELECT 1")
            last_detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"mysql exited with status {result.returncode}"
            )
        if attempt < args.sql_probe_attempts:
            time.sleep(args.sql_probe_delay)
    return CheckResult(
        "matrixone_sql",
        False,
        f"failed {args.sql_probe_attempts} consecutive probes: {last_detail}",
    )


def check_minio(args: argparse.Namespace) -> CheckResult:
    url = f"{args.minio_url.rstrip('/')}/minio/health/live"
    try:
        with urllib.request.urlopen(url, timeout=args.check_timeout) as response:
            if response.status != 200:
                return CheckResult("minio", False, f"HTTP {response.status}")
    except (OSError, urllib.error.URLError) as exc:
        return CheckResult("minio", False, str(exc))
    return CheckResult("minio", True, url)


def check_workflow_nodes(args: argparse.Namespace) -> CheckResult:
    url = (
        f"{args.workflow_be_url.rstrip('/')}"
        "/byoa/api/v1/workflow_meta/components/list"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(
            {"node_types": [], "component_names": []},
            separators=(",", ":"),
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=args.check_timeout,
        ) as response:
            body = response.read()
            if response.status != 200:
                return CheckResult(
                    "workflow_nodes",
                    False,
                    f"HTTP {response.status}",
                )
        payload = json.loads(body)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return CheckResult("workflow_nodes", False, str(exc))
    if not isinstance(payload, dict) or payload.get("code") != "ok":
        return CheckResult("workflow_nodes", False, f"invalid response: {payload!r}")
    data = payload.get("data")
    if not isinstance(data, list):
        return CheckResult("workflow_nodes", False, "response data is not a list")
    node_types = {
        item.get("node_type")
        for item in data
        if isinstance(item, dict) and isinstance(item.get("node_type"), str)
    }
    missing = sorted(REQUIRED_WORKFLOW_NODE_TYPES - node_types)
    if missing:
        return CheckResult(
            "workflow_nodes",
            False,
            f"missing node types: {', '.join(missing)}",
        )
    return CheckResult(
        "workflow_nodes",
        True,
        f"{len(node_types)} node types",
    )


def check_process(name: str, pattern: str) -> CheckResult:
    try:
        result = run_command(
            ["pgrep", "-f", pattern],
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CheckResult(name, False, str(exc))
    if result.returncode != 0 or not result.stdout.strip():
        return CheckResult(name, False, f"process not found: {pattern}")
    return CheckResult(name, True, f"pid={result.stdout.splitlines()[0]}")


def run_checks(args: argparse.Namespace) -> list[CheckResult]:
    checks: list[Callable[[], CheckResult]] = [
        lambda: check_sql(args),
        lambda: check_minio(args),
        lambda: check_tcp(
            "rocketmq_nameserver",
            args.rocketmq_host,
            args.rocketmq_nameserver_port,
            args.check_timeout,
        ),
        lambda: check_tcp(
            "rocketmq_broker",
            args.rocketmq_host,
            args.rocketmq_broker_port,
            args.check_timeout,
        ),
        lambda: check_workflow_nodes(args),
        lambda: check_process("job_consumer", "byoa/job_consumer.py"),
        lambda: check_process("workflow_scheduler", "workflow-scheduler -c"),
        lambda: check_tcp(
            "connector",
            args.connector_host,
            args.connector_port,
            args.check_timeout,
        ),
        lambda: check_tcp(
            "catalog",
            args.catalog_host,
            args.catalog_port,
            args.check_timeout,
        ),
    ]
    return [check() for check in checks]


def print_results(results: list[CheckResult], *, verbose: bool = False) -> None:
    for result in results:
        if result.ok and not verbose:
            continue
        status = "ok" if result.ok else "failed"
        print(f"[guard] {result.name}: {status} ({result.detail})", flush=True)


def docker_is_ready(timeout: float) -> bool:
    try:
        result = run_command(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def restart_docker_desktop(args: argparse.Namespace) -> None:
    print(
        "[guard] Docker backend is unavailable; restarting Docker Desktop", flush=True
    )
    try:
        run_command(
            ["osascript", "-e", 'quit app "Docker"'],
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pass
    for process_name in (
        "Docker Desktop",
        "com.docker.virtualization",
        "com.docker.build",
        "com.docker.backend",
    ):
        run_command(
            ["killall", "-TERM", process_name],
            timeout=5,
            check=False,
        )
    run_command(["open", "-a", "Docker"], timeout=10)
    deadline = time.monotonic() + args.docker_start_timeout
    while time.monotonic() < deadline:
        if docker_is_ready(args.check_timeout):
            return
        time.sleep(2)
    raise RuntimeError("Docker Desktop did not become ready")


def ensure_override_file(path: Path) -> None:
    expected = "volumes:\n  mo_data:\n    name: matrixflow_414_mo_data\n"
    if path.is_file() and path.read_text() == expected:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(expected)


def tmux_has_session(session: str) -> bool:
    result = run_command(
        ["tmux", "has-session", "-t", session],
        timeout=5,
        check=False,
    )
    return result.returncode == 0


def process_ids(command: list[str]) -> set[int]:
    result = run_command(command, timeout=5, check=False)
    if result.returncode != 0:
        return set()
    return {
        int(value)
        for value in result.stdout.split()
        if value.isdigit() and int(value) != os.getpid()
    }


def terminate_service(pattern: str | None, port: int | None = None) -> None:
    pids = process_ids(["pgrep", "-f", pattern]) if pattern is not None else set()
    if port is not None:
        pids.update(
            process_ids(
                [
                    "lsof",
                    "-t",
                    f"-iTCP:{port}",
                    "-sTCP:LISTEN",
                ]
            )
        )
    if not pids:
        return
    for pid in sorted(pids):
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        remaining = {pid for pid in pids if Path(f"/proc/{pid}").exists()}
        if sys.platform == "darwin":
            remaining = {
                pid
                for pid in pids
                if run_command(
                    ["kill", "-0", str(pid)],
                    timeout=2,
                    check=False,
                ).returncode
                == 0
            }
        if not remaining:
            return
        time.sleep(0.5)
    for pid in sorted(remaining):
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass


def replace_tmux_window(
    args: argparse.Namespace,
    *,
    index: int,
    name: str,
    cwd: Path,
    command: str,
) -> None:
    target = f"{args.tmux_session}:{index}"
    if (
        run_command(
            ["tmux", "list-windows", "-t", args.tmux_session, "-F", "#{window_index}"],
            timeout=5,
            check=False,
        )
        .stdout.splitlines()
        .count(str(index))
    ):
        run_command(
            ["tmux", "kill-window", "-t", target],
            timeout=10,
            check=False,
        )
    run_command(
        [
            "tmux",
            "new-window",
            "-d",
            "-t",
            target,
            "-n",
            name,
            "-c",
            str(cwd),
        ],
        timeout=10,
    )
    run_command(
        ["tmux", "send-keys", "-t", f"{target}.0", command, "Enter"],
        timeout=10,
    )


def ensure_tmux_session(args: argparse.Namespace, cwd: Path) -> None:
    if tmux_has_session(args.tmux_session):
        return
    run_command(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            args.tmux_session,
            "-n",
            "guard",
            "-c",
            str(cwd),
        ],
        timeout=10,
    )
    run_command(
        [
            "tmux",
            "move-window",
            "-s",
            f"{args.tmux_session}:0",
            "-t",
            f"{args.tmux_session}:11",
        ],
        timeout=10,
    )


def wait_until(
    description: str,
    check: Callable[[], CheckResult],
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    last = CheckResult(description, False, "not checked")
    while time.monotonic() < deadline:
        last = check()
        if last.ok:
            return
        time.sleep(2)
    raise RuntimeError(f"{description} did not become ready: {last.detail}")


def recover(args: argparse.Namespace, failed_names: set[str]) -> None:
    matrixflow_dir = args.matrixflow_dir.expanduser().resolve()
    if not matrixflow_dir.is_dir():
        raise RuntimeError(f"Matrixflow directory not found: {matrixflow_dir}")
    docker_was_unhealthy = not docker_is_ready(args.check_timeout)
    if docker_was_unhealthy:
        restart_docker_desktop(args)

    compose_file = matrixflow_dir / "optools/matrixflow/docker-compose.yaml"
    if docker_was_unhealthy:
        ensure_override_file(args.mo_override)
        run_command(
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-f",
                str(args.mo_override),
                "--profile",
                "launch",
                "up",
                "-d",
            ],
            cwd=matrixflow_dir,
            timeout=args.recovery_command_timeout,
        )
    elif "matrixone_sql" in failed_names:
        ensure_override_file(args.mo_override)
        run_command(
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-f",
                str(args.mo_override),
                "--profile",
                "launch",
                "up",
                "-d",
                "mo",
            ],
            cwd=matrixflow_dir,
            timeout=args.recovery_command_timeout,
        )

    if docker_was_unhealthy or "matrixone_sql" in failed_names:
        run_command(
            ["make", "wait-mo"],
            cwd=matrixflow_dir,
            timeout=args.recovery_command_timeout,
        )

    if docker_was_unhealthy or "minio" in failed_names:
        ensure_override_file(args.mo_override)
        run_command(
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-f",
                str(args.mo_override),
                "--profile",
                "launch",
                "up",
                "-d",
                "minio",
            ],
            cwd=matrixflow_dir,
            timeout=args.recovery_command_timeout,
        )

    if (
        docker_was_unhealthy
        or {
            "rocketmq_nameserver",
            "rocketmq_broker",
        }
        & failed_names
    ):
        run_command(
            ["make", "start-rmq"],
            cwd=matrixflow_dir,
            timeout=args.recovery_command_timeout,
        )

    infrastructure_names = {
        "matrixone_sql",
        "minio",
        "rocketmq_nameserver",
        "rocketmq_broker",
    }
    if docker_was_unhealthy or failed_names & infrastructure_names:
        wait_until("matrixone_sql", lambda: check_sql(args), args.service_start_timeout)
        wait_until("minio", lambda: check_minio(args), args.service_start_timeout)
        wait_until(
            "rocketmq_nameserver",
            lambda: check_tcp(
                "rocketmq_nameserver",
                args.rocketmq_host,
                args.rocketmq_nameserver_port,
                args.check_timeout,
            ),
            args.service_start_timeout,
        )
        wait_until(
            "rocketmq_broker",
            lambda: check_tcp(
                "rocketmq_broker",
                args.rocketmq_host,
                args.rocketmq_broker_port,
                args.check_timeout,
            ),
            args.service_start_timeout,
        )

    restart_connector = not check_tcp(
        "connector",
        args.connector_host,
        args.connector_port,
        args.check_timeout,
    ).ok
    restart_consumer = not check_process("job_consumer", "byoa/job_consumer.py").ok
    restart_scheduler = not check_process(
        "workflow_scheduler",
        "workflow-scheduler -c",
    ).ok
    restart_workflow = not check_workflow_nodes(args).ok
    restart_catalog = (
        restart_workflow
        or not check_tcp(
            "catalog",
            args.catalog_host,
            args.catalog_port,
            args.check_timeout,
        ).ok
    )

    if not any(
        [
            restart_connector,
            restart_consumer,
            restart_scheduler,
            restart_workflow,
            restart_catalog,
        ]
    ):
        return

    ensure_tmux_session(args, matrixflow_dir)

    env_file = matrixflow_dir / "optools/matrixflow/.env"
    workflow_dir = matrixflow_dir / "workflow_be/src"
    workflow_python_path = (
        f"{matrixflow_dir}/workflow_be:{matrixflow_dir}/workflow_be/src"
    )
    activate = args.venv / "bin/activate"
    common = (
        f"source {activate} && source {env_file} && cd {workflow_dir} && "
        f"export PYTHONPATH={workflow_python_path} && "
        "export DYLD_LIBRARY_PATH='' && "
    )
    if restart_connector:
        terminate_service(None, 9000)
        replace_tmux_window(
            args,
            index=0,
            name="connector",
            cwd=matrixflow_dir / "connector_rpc",
            command=(
                f"cd {matrixflow_dir}/connector_rpc && "
                "./moc_connector_server -conf trpc_go.yaml"
            ),
        )
        wait_until(
            "connector",
            lambda: check_tcp(
                "connector",
                args.connector_host,
                args.connector_port,
                args.check_timeout,
            ),
            args.service_start_timeout,
        )

    if restart_consumer:
        terminate_service("byoa/job_consumer.py")
        replace_tmux_window(
            args,
            index=1,
            name="job-consumer",
            cwd=workflow_dir,
            command=(
                common + "export JOB_CONSUMER_METRICS_ENABLED=false && "
                "poetry run python3 byoa/job_consumer.py"
            ),
        )
        wait_until(
            "job_consumer",
            lambda: check_process("job_consumer", "byoa/job_consumer.py"),
            args.service_start_timeout,
        )

    if restart_scheduler:
        terminate_service("workflow-scheduler -c")
        replace_tmux_window(
            args,
            index=3,
            name="workflow-scheduler",
            cwd=matrixflow_dir / "workflow_scheduler",
            command=(
                f"cd {matrixflow_dir}/workflow_scheduler && "
                "./workflow-scheduler -c etc/service.yaml"
            ),
        )
        wait_until(
            "workflow_scheduler",
            lambda: check_process(
                "workflow_scheduler",
                "workflow-scheduler -c",
            ),
            args.service_start_timeout,
        )

    if restart_workflow:
        terminate_service(None, 8910)
        replace_tmux_window(
            args,
            index=8,
            name="apiserver",
            cwd=workflow_dir,
            command=common + "poetry run python3 byoa/main.py",
        )
        wait_until(
            "workflow_nodes",
            lambda: check_workflow_nodes(args),
            args.service_start_timeout,
        )

    if restart_catalog:
        terminate_service(None, 8920)
        replace_tmux_window(
            args,
            index=9,
            name="catalog",
            cwd=matrixflow_dir / "catalog_service",
            command=(
                f"cd {matrixflow_dir}/catalog_service && "
                "./bin/catalog-service -config ./etc/service.yaml"
            ),
        )
        wait_until(
            "catalog",
            lambda: check_tcp(
                "catalog",
                args.catalog_host,
                args.catalog_port,
                args.check_timeout,
            ),
            args.service_start_timeout,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check and automatically recover the local Matrixflow parser stack."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--ensure", action="store_true")
    parser.add_argument("--matrixflow-dir", type=Path, default=DEFAULT_MATRIXFLOW_DIR)
    parser.add_argument("--venv", type=Path, default=DEFAULT_VENV)
    parser.add_argument("--tmux-session", default=DEFAULT_TMUX_SESSION)
    parser.add_argument("--mo-override", type=Path, default=DEFAULT_MO_OVERRIDE)
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=6001)
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument(
        "--mysql-password",
        default=os.getenv("MATRIXFLOW_MYSQL_PASSWORD", "111"),
    )
    parser.add_argument("--minio-url", default="http://127.0.0.1:9100")
    parser.add_argument("--rocketmq-host", default="127.0.0.1")
    parser.add_argument("--rocketmq-nameserver-port", type=int, default=9876)
    parser.add_argument("--rocketmq-broker-port", type=int, default=10911)
    parser.add_argument("--workflow-be-url", default="http://127.0.0.1:8910")
    parser.add_argument("--connector-host", default="127.0.0.1")
    parser.add_argument("--connector-port", type=int, default=9000)
    parser.add_argument("--catalog-host", default="127.0.0.1")
    parser.add_argument("--catalog-port", type=int, default=8920)
    parser.add_argument("--check-timeout", type=float, default=5.0)
    parser.add_argument("--sql-probe-attempts", type=int, default=3)
    parser.add_argument("--sql-probe-delay", type=float, default=2.0)
    parser.add_argument("--docker-start-timeout", type=float, default=120.0)
    parser.add_argument("--service-start-timeout", type=float, default=120.0)
    parser.add_argument("--recovery-command-timeout", type=float, default=180.0)
    parser.add_argument("--max-recovery-attempts", type=int, default=3)
    parser.add_argument("--recovery-delay", type=float, default=10.0)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print successful checks too; healthy checks are silent by default.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_recovery_attempts < 1:
        print("--max-recovery-attempts must be at least 1", file=sys.stderr)
        return 2
    if args.sql_probe_attempts < 1:
        print("--sql-probe-attempts must be at least 1", file=sys.stderr)
        return 2
    with DEFAULT_LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        results = run_checks(args)
        print_results(results, verbose=args.verbose)
        if all(result.ok for result in results):
            return 0
        if args.check_only:
            return 1

        for attempt in range(1, args.max_recovery_attempts + 1):
            print(
                f"[guard] recovery attempt {attempt}/{args.max_recovery_attempts}",
                flush=True,
            )
            try:
                recover(args, {result.name for result in results if not result.ok})
            except Exception as exc:
                print(f"[guard] recovery failed: {exc}", file=sys.stderr, flush=True)
            else:
                results = run_checks(args)
                print_results(results, verbose=args.verbose)
                if all(result.ok for result in results):
                    print("[guard] recovery completed", flush=True)
                    return 0
            if attempt < args.max_recovery_attempts:
                time.sleep(args.recovery_delay * attempt)
        print("[guard] infrastructure remains unhealthy", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
