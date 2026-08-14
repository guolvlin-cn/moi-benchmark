#!/usr/bin/env python3
"""Audit Pi tool arguments for possible benchmark answer/path leakage."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Iterator


SENSITIVE_PATTERNS = {
    "evaluation": re.compile(r"(?i)\bevaluation\b"),
    "groundtruth_workspace": re.compile(r"(?i)\bgroundtruth_workspace\b"),
    "moi_benchmark": re.compile(r"(?i)(?:/home/vagrant/)?moi-benchmark(?:[/\\]|$)"),
}
RECURSIVE_SCAN = re.compile(
    r"(?ix)(?:"
    r"\bfind\s+(?:/|/home(?:/vagrant)?)(?:\s|/)|"
    r"\b(?:grep|ls)\b[^\n;&|]*\s-(?:[A-Za-z]*R[A-Za-z]*|[A-Za-z]*r[A-Za-z]*)"
    r"[^\n;&|]*(?:\s/|\s/home(?:/vagrant)?(?:\s|/))|"
    r"\b(?:rg|tree|fd)\b[^\n;&|]*(?:\s/|\s/home(?:/vagrant)?(?:\s|/))|"
    r"\bos\.walk\(\s*['\"](?:/|/home(?:/vagrant)?)(?:['\"]|/)|"
    r"\.rglob\([^)]*\)"
    r")"
)


def bounded_lines(path: Path, max_line_bytes: int) -> Iterator[tuple[int, bytes | None]]:
    """Yield complete small lines and discard oversized lines with bounded memory."""
    with path.open("rb") as stream:
        number = 0
        parts: list[bytes] = []
        size = 0
        oversized = False
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                if parts or oversized:
                    number += 1
                    yield number, None if oversized else b"".join(parts)
                return
            start = 0
            while True:
                newline = chunk.find(b"\n", start)
                end = len(chunk) if newline < 0 else newline
                piece = chunk[start:end]
                if not oversized:
                    size += len(piece)
                    if size <= max_line_bytes:
                        parts.append(piece)
                    else:
                        parts.clear()
                        oversized = True
                if newline < 0:
                    break
                number += 1
                yield number, None if oversized else b"".join(parts)
                parts = []
                size = 0
                oversized = False
                start = newline + 1


def scalar_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def find_run_logs(roots: list[Path]) -> Iterator[Path]:
    seen: set[Path] = set()
    for root in roots:
        if root.is_file() and root.name == "adapter.stdout.log":
            candidates = [root]
        else:
            candidates = []
            for directory, names, files in os.walk(root, topdown=True):
                names[:] = [name for name in names if name not in {"task-state", "evaluator"}]
                if "adapter.stdout.log" in files:
                    candidates.append(Path(directory) / "adapter.stdout.log")
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue
            run_json = path.parent / "run.json"
            is_pi = "/pi/" in path.as_posix() or "-pi-" in path.parent.name
            if run_json.is_file():
                try:
                    is_pi = json.loads(run_json.read_text(encoding="utf-8")).get("system_id") == "pi"
                except (OSError, ValueError):
                    pass
            if is_pi:
                seen.add(resolved)
                yield path


def expected_starts(run_dir: Path) -> int | None:
    path = run_dir / "tool-calls.jsonl"
    if not path.is_file():
        return None
    count = 0
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("state") == "started" or row.get("event") == "tool.execution_start":
                    count += 1
    except OSError:
        return None
    return count


def audit_log(path: Path, max_line_bytes: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    starts = 0
    oversized = 0
    invalid = 0
    seen_calls: set[tuple[str, str]] = set()
    for line_number, raw in bounded_lines(path, max_line_bytes):
        if raw is None:
            oversized += 1
            continue
        if b"tool_execution_start" not in raw:
            continue
        try:
            event = json.loads(raw)
        except ValueError:
            invalid += 1
            continue
        if event.get("type") != "tool_execution_start":
            continue
        call_id = str(event.get("toolCallId") or event.get("tool_call_id") or "")
        tool_name = str(event.get("toolName") or event.get("tool_name") or "")
        key = (call_id, tool_name)
        if key in seen_calls:
            continue
        seen_calls.add(key)
        starts += 1
        arguments = event.get("args", event.get("arguments", {}))
        text = scalar_text(arguments)
        categories = [name for name, pattern in SENSITIVE_PATTERNS.items() if pattern.search(text)]
        command = arguments.get("command") if isinstance(arguments, dict) else None
        if tool_name == "bash" and isinstance(command, str) and RECURSIVE_SCAN.search(command):
            categories.append("recursive_host_scan")
        if categories:
            findings.append(
                {
                    "run_dir": str(path.parent),
                    "source": str(path),
                    "line": line_number,
                    "tool_call_id": call_id,
                    "tool_name": tool_name,
                    "categories": sorted(set(categories)),
                    "arguments": text[:8000],
                    "arguments_truncated": len(text) > 8000,
                }
            )
    expected = expected_starts(path.parent)
    return findings, {
        "run_dir": str(path.parent),
        "parsed_tool_starts": starts,
        "tool_calls_expected_starts": expected,
        "coverage_complete": expected is None or starts == expected,
        "oversized_lines_skipped": oversized,
        "invalid_candidate_lines": invalid,
        "finding_count": len(findings),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[Path("astra/results")],
        help="result roots or individual adapter.stdout.log files",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/pi-path-audit"))
    parser.add_argument("--max-line-mib", type=int, default=16)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    findings_path = args.output_dir / "findings.jsonl"
    runs_path = args.output_dir / "runs.jsonl"
    findings_count = 0
    run_count = 0
    incomplete = 0
    with findings_path.open("w", encoding="utf-8") as findings_file, runs_path.open(
        "w", encoding="utf-8"
    ) as runs_file:
        for log in find_run_logs(args.roots):
            findings, run = audit_log(log, args.max_line_mib * 1024 * 1024)
            run_count += 1
            findings_count += len(findings)
            incomplete += not run["coverage_complete"]
            runs_file.write(json.dumps(run, ensure_ascii=False, sort_keys=True) + "\n")
            for finding in findings:
                findings_file.write(json.dumps(finding, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "runs_scanned": run_count,
        "findings": findings_count,
        "runs_with_incomplete_tool_start_coverage": incomplete,
        "findings_path": str(findings_path),
        "runs_path": str(runs_path),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if incomplete == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
