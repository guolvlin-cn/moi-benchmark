#!/usr/bin/env python3
"""Read-only external-state predicates for the initial Terminal-Bench C0 cases."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Callable


OVERFULL_INPUT_INITIAL_SHA256 = (
    "7bf7dbe58dbbfb08b6a652c547daa09a57cdbccc0fd18141b4968756061326a3"
)


class ProbeError(RuntimeError):
    pass


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _stable_file_snapshot(
    path: Path,
    *,
    scan_for: bytes | None = None,
    prefix_bytes: int = 0,
) -> tuple[dict[str, Any], bool] | None:
    try:
        before_path = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProbeError(f"cannot stat {path}: {exc}") from exc
    if not stat.S_ISREG(before_path.st_mode):
        return None

    digest = hashlib.sha256()
    found = False
    prefix = b""
    scan_tail = b""
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                before.st_dev,
                before.st_ino,
                before.st_mode,
            ) != (
                before_path.st_dev,
                before_path.st_ino,
                before_path.st_mode,
            ):
                return None
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                if prefix_bytes and len(prefix) < prefix_bytes:
                    prefix += chunk[: prefix_bytes - len(prefix)]
                if scan_for is not None:
                    combined = scan_tail + chunk
                    if scan_for in combined:
                        found = True
                    tail_length = max(0, len(scan_for) - 1)
                    scan_tail = combined[-tail_length:] if tail_length else b""
            after = os.fstat(stream.fileno())
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None
        raise ProbeError(f"cannot read {path}: {exc}") from exc

    fingerprint_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    fingerprint_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    if fingerprint_before != fingerprint_after:
        return None
    return (
        {
            "path": str(path),
            "size": after.st_size,
            "mtime_ns": after.st_mtime_ns,
            "sha256": digest.hexdigest(),
            **({"prefix_hex": prefix.hex()} if prefix_bytes else {}),
        },
        found,
    )


def _ready_file(path: Path) -> dict[str, Any] | None:
    observed = _stable_file_snapshot(path)
    if observed is None or observed[0]["size"] == 0:
        return None
    return observed[0]


def modernize_partial_outputs(
    workspace: Path, _pmars_binary: Path
) -> tuple[bool, dict[str, Any]]:
    script = _ready_file(workspace / "analyze_climate_modern.py")
    dependencies = [
        snapshot
        for path in (workspace / "requirements.txt", workspace / "pyproject.toml")
        if (snapshot := _ready_file(path)) is not None
    ]
    script_ready = script is not None
    dependency_ready = bool(dependencies)
    return (
        script_ready != dependency_ready,
        {
            "dependency_outputs": dependencies,
            "dependency_ready": dependency_ready,
            "script_output": script,
            "script_ready": script_ready,
        },
    )


def overfull_changed_before_clean_log(
    workspace: Path, _pmars_binary: Path
) -> tuple[bool, dict[str, Any]]:
    input_observation = _stable_file_snapshot(workspace / "input.tex")
    if input_observation is None:
        return False, {"input_state": "missing_or_unstable"}
    input_snapshot = input_observation[0]
    changed = input_snapshot["sha256"] != OVERFULL_INPUT_INITIAL_SHA256

    log_path = workspace / "main.log"
    if not _lexists(log_path):
        log_state = "absent"
        log_snapshot = None
        has_overfull = False
        before_clean_log = True
    else:
        log_observation = _stable_file_snapshot(log_path, scan_for=b"Overfull")
        if log_observation is None:
            return False, {
                "input": input_snapshot,
                "input_changed": changed,
                "log_state": "missing_nonregular_or_unstable",
            }
        log_snapshot, has_overfull = log_observation
        log_state = "overfull" if has_overfull else "clean"
        before_clean_log = has_overfull
    return (
        changed and before_clean_log,
        {
            "input": input_snapshot,
            "input_changed": changed,
            "log": log_snapshot,
            "log_has_overfull": has_overfull,
            "log_state": log_state,
        },
    )


def pmars_source_before_install(
    workspace: Path, pmars_binary: Path
) -> tuple[bool, dict[str, Any]]:
    binary_absent = not _lexists(pmars_binary)
    candidates = []
    try:
        source_directories = sorted(workspace.glob("pmars-*"))
    except OSError as exc:
        raise ProbeError(f"cannot scan {workspace}: {exc}") from exc
    for directory in source_directories:
        try:
            if not directory.is_dir():
                continue
        except OSError as exc:
            raise ProbeError(f"cannot inspect {directory}: {exc}") from exc
        changelog = _ready_file(directory / "debian" / "changelog")
        makefile = _ready_file(directory / "src" / "Makefile")
        if changelog is not None and makefile is not None:
            candidates.append(
                {
                    "source_directory": str(directory),
                    "debian_changelog": changelog,
                    "src_makefile": makefile,
                }
            )
    return (
        binary_absent and bool(candidates),
        {
            "install_path": str(pmars_binary),
            "install_path_absent": binary_absent,
            "ready_source_trees": candidates,
        },
    )


def valid_wal_before_output(
    workspace: Path, _pmars_binary: Path
) -> tuple[bool, dict[str, Any]]:
    wal_observation = _stable_file_snapshot(
        workspace / "main.db-wal",
        prefix_bytes=4,
    )
    output_path = workspace / "recovered.json"
    output_absent = not _lexists(output_path)
    if wal_observation is None:
        return False, {
            "output_absent": output_absent,
            "wal_state": "missing_nonregular_or_unstable",
        }
    wal_snapshot = wal_observation[0]
    magic = wal_snapshot["prefix_hex"]
    valid_magic = magic in {"377f0682", "377f0683"}
    return (
        valid_magic and output_absent,
        {
            "output_absent": output_absent,
            "wal": wal_snapshot,
            "wal_magic_hex": magic,
            "wal_magic_valid": valid_magic,
        },
    )


def generic_product_live(
    _workspace: Path, _pmars_binary: Path
) -> tuple[bool, dict[str, Any]]:
    # C0Controller waits for the registered product identity before invoking
    # predicates and revalidates that identity before recording its no-op.
    return True, {"state": "product_live"}


PREDICATES: dict[str, Callable[[Path, Path], tuple[bool, dict[str, Any]]]] = {
    "terminal-bench.generic.product-live": generic_product_live,
    "terminal-bench.modernize-scientific-stack.partial-outputs": (
        modernize_partial_outputs
    ),
    "terminal-bench.overfull-hbox.changed-input-before-clean-log": (
        overfull_changed_before_clean_log
    ),
    "terminal-bench.build-pmars.source-before-install": pmars_source_before_install,
    "terminal-bench.db-wal-recovery.valid-wal-before-output": (
        valid_wal_before_output
    ),
}


def observe(
    predicate_id: str,
    *,
    workspace: Path = Path("/app"),
    pmars_binary: Path = Path("/usr/local/bin/pmars"),
) -> tuple[bool, dict[str, Any]]:
    try:
        predicate = PREDICATES[predicate_id]
    except KeyError as exc:
        raise ProbeError(f"unknown predicate {predicate_id!r}") from exc
    return predicate(workspace, pmars_binary)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predicate", required=True)
    parser.add_argument("--workspace", type=Path, default=Path("/app"))
    parser.add_argument(
        "--pmars-binary", type=Path, default=Path("/usr/local/bin/pmars")
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        matched, evidence = observe(
            args.predicate,
            workspace=args.workspace,
            pmars_binary=args.pmars_binary,
        )
        payload = {
            "schema_version": 1,
            "predicate_id": args.predicate,
            "matched": matched,
            "evidence": evidence,
        }
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 0 if matched else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "predicate_id": args.predicate,
                    "matched": False,
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
