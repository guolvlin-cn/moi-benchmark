#!/usr/bin/env python3
"""Continuously display progress for a frozen RAGAS run.

This is a read-only monitor.  It reads ``manifest.json``, per-system
``checkpoint.json``, ``summary.json`` and ``scores.jsonl``; it never starts a
QA request or changes a result file.

Examples::

    python tools/watch_ragas_progress.py
    python tools/watch_ragas_progress.py --run-dir runs/stage1/ragas-wikieval-calibrated/20260812-ragas-0215-maas-unified
    python tools/watch_ragas_progress.py --once --no-color
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PARENT = ROOT / "runs/stage1/ragas-wikieval-calibrated"
FALLBACK_SYSTEMS = ("moi", "dify", "fastgpt", "maxkb")
FALLBACK_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


class Colors:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, value: str) -> str:
        return f"\033[{code}m{value}\033[0m" if self.enabled else value

    def good(self, value: str) -> str:
        return self._wrap("32", value)

    def warn(self, value: str) -> str:
        return self._wrap("33", value)

    def bad(self, value: str) -> str:
        return self._wrap("31", value)

    def dim(self, value: str) -> str:
        return self._wrap("2", value)

    def bold(self, value: str) -> str:
        return self._wrap("1", value)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    except (json.JSONDecodeError, OSError):
        return rows
    return rows


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def choose_run(value: Path) -> Path:
    value = value.expanduser().resolve()
    if (value / "manifest.json").is_file():
        return value
    candidates = [
        path.parent
        for path in value.glob("*/manifest.json")
        if path.is_file()
    ]
    if not candidates:
        raise SystemExit(f"No RAGAS run manifest found under: {value}")
    def run_mtime(path: Path) -> float:
        watched = [path / "manifest.json"]
        for pattern in ("*/checkpoint.json", "*/summary.json", "*/scores.jsonl"):
            watched.extend(path.glob(pattern))
        return latest_mtime(watched)

    return max(candidates, key=run_mtime)


def metric_names(manifest: dict[str, Any]) -> list[str]:
    names = manifest.get("evaluation", {}).get("metrics")
    if isinstance(names, list) and names:
        return [str(name) for name in names]
    return list(FALLBACK_METRICS)


def system_names(manifest: dict[str, Any], run_dir: Path) -> list[str]:
    names = manifest.get("systems")
    if isinstance(names, dict) and names:
        ordered = [name for name in FALLBACK_SYSTEMS if name in names]
        ordered.extend(name for name in names if name not in ordered)
        return ordered
    present = [name for name in FALLBACK_SYSTEMS if (run_dir / name).is_dir()]
    return present or list(FALLBACK_SYSTEMS)


def planned_questions(manifest: dict[str, Any], system_dirs: Iterable[Path]) -> int:
    rows = manifest.get("benchmark", {}).get("rows")
    if isinstance(rows, int) and rows > 0:
        return rows
    for system_dir in system_dirs:
        summary_rows = load_json(system_dir / "summary.json").get("rows")
        if isinstance(summary_rows, int) and summary_rows > 0:
            return summary_rows
        score_rows = load_jsonl(system_dir / "scores.jsonl")
        if score_rows:
            return len(score_rows)
    return 0


def latest_mtime(paths: Iterable[Path]) -> float:
    values: list[float] = []
    for path in paths:
        try:
            values.append(path.stat().st_mtime)
        except OSError:
            pass
    return max(values, default=0.0)


def metric_state(
    metric: str,
    checkpoint: dict[str, Any],
    rows: list[dict[str, Any]],
    planned: int,
) -> dict[str, Any]:
    checkpoint_ids = checkpoint.get("metric_row_ids", {})
    attempted_ids = checkpoint_ids.get(metric, []) if isinstance(checkpoint_ids, dict) else []
    attempted = len(attempted_ids) if isinstance(attempted_ids, list) else 0
    if not attempted and rows and not checkpoint:
        attempted = sum(1 for row in rows if metric in row)

    # A score row with a finite value is the strict definition of a valid
    # result.  The checkpoint counts failed attempts as completed because the
    # runner can resume them with --retry-errors, so both figures are shown.
    valid = sum(1 for row in rows if finite(row.get(metric)))
    errors = 0
    for row in rows:
        row_errors = row.get("errors")
        if isinstance(row_errors, dict) and metric in row_errors:
            errors += 1
    errors = max(errors, attempted - valid)
    pending = max(planned - attempted, 0)
    if valid >= planned > 0:
        status = "complete"
    elif pending > 0:
        status = "running" if attempted else "pending"
    else:
        status = "failed"
    return {
        "metric": metric,
        "attempted": min(attempted, planned),
        "valid": min(valid, planned),
        "errors": min(errors, planned),
        "pending": pending,
        "status": status,
    }


def system_state(system_dir: Path, metrics: list[str], planned: int) -> dict[str, Any]:
    checkpoint = load_json(system_dir / "checkpoint.json")
    rows = load_jsonl(system_dir / "scores.jsonl")
    states = [metric_state(metric, checkpoint, rows, planned) for metric in metrics]
    completed = [state["metric"] for state in states if state["status"] == "complete"]
    pending = [state["metric"] for state in states if state["status"] in {"pending", "running"}]
    last_metric = checkpoint.get("last_metric")
    last_row = checkpoint.get("last_row_id")
    last_metric = checkpoint.get("last_metric")
    last_state = next((state for state in states if state["metric"] == last_metric), None)
    current = (
        last_metric
        if last_state is not None and last_state["status"] != "complete"
        else next((state["metric"] for state in states if state["status"] != "complete"), None)
    )
    files = [system_dir / name for name in ("checkpoint.json", "summary.json", "scores.jsonl")]
    return {
        "name": system_dir.name,
        "checkpoint": checkpoint,
        "rows": rows,
        "states": states,
        "completed": completed,
        "pending": pending,
        "current": current,
        "last_metric": last_metric,
        "last_row": last_row,
        "mtime": latest_mtime(files),
    }


def pct(value: int, total: int) -> str:
    return "--" if total <= 0 else f"{100.0 * value / total:5.1f}%"


def bar(value: int, total: int, width: int = 22) -> str:
    if total <= 0:
        return "[" + "?" * width + "]"
    filled = max(0, min(width, round(width * value / total)))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def status_text(state: str, colors: Colors) -> str:
    labels = {
        "complete": colors.good("DONE"),
        "running": colors.warn("RUNNING"),
        "pending": colors.dim("PENDING"),
        "failed": colors.bad("ERRORS"),
    }
    return labels.get(state, state.upper())


def short_error_summary(states: list[dict[str, Any]]) -> list[str]:
    counter: Counter[str] = Counter()
    for state in states:
        for row in state["rows"]:
            errors = row.get("errors")
            if not isinstance(errors, dict):
                continue
            for metric, message in errors.items():
                text = " ".join(str(message).split())
                if text:
                    counter[f"{metric}: {text[:180]}"] += 1
    return [f"{count}x {message}" for message, count in counter.most_common(3)]


def render(run_dir: Path, no_color: bool, stale_after: float) -> str:
    manifest = load_json(run_dir / "manifest.json")
    metrics = metric_names(manifest)
    systems = system_names(manifest, run_dir)
    system_dirs = [run_dir / system for system in systems]
    planned = planned_questions(manifest, system_dirs)
    states = [system_state(path, metrics, planned) for path in system_dirs]
    colors = Colors(not no_color and sys.stdout.isatty())

    total_cells = max(planned * len(metrics) * len(systems), 0)
    attempted_cells = sum(state["attempted"] for item in states for state in item["states"])
    valid_cells = sum(state["valid"] for item in states for state in item["states"])
    latest_system = max(states, key=lambda item: item["mtime"], default=None)
    now = time.time()
    if latest_system and latest_system["mtime"]:
        latest_time = datetime.fromtimestamp(latest_system["mtime"]).strftime("%H:%M:%S")
        if now - latest_system["mtime"] <= stale_after:
            activity = colors.good(f"{latest_system['name']} / {latest_system['current'] or 'finalizing'} (updated {latest_time})")
        else:
            activity = colors.warn(f"no recent write; last {latest_system['name']} at {latest_time}")
    else:
        activity = colors.dim("no checkpoint yet")

    benchmark = manifest.get("benchmark", {}).get("name", "WikiEval")
    qa_reuse = manifest.get("evaluation", {}).get("qa_reuse")
    qa_text = "reused; QA not rerun" if qa_reuse else "not specified"
    lines = [
        colors.bold("RAGAS realtime progress"),
        f"run:       {run_dir}",
        f"benchmark: {benchmark} | questions={planned} | QA={qa_text}",
        f"activity:  {activity}",
        f"overall execution: {bar(attempted_cells, total_cells)} {pct(attempted_cells, total_cells)} ({attempted_cells}/{total_cells})",
        f"overall valid:     {bar(valid_cells, total_cells)} {pct(valid_cells, total_cells)} ({valid_cells}/{total_cells})",
        "",
        "system     current metric             metric progress (attempted / valid)              completed",
        "-" * 112,
    ]
    for item in states:
        progress = " | ".join(
            f"{state['metric']} {pct(state['attempted'], planned)}/{pct(state['valid'], planned)}"
            for state in item["states"]
        )
        completed = ", ".join(item["completed"]) or "-"
        current = item["current"] or "-"
        lines.append(f"{item['name']:<10} {current:<25} {progress:<70} {completed}")

    lines.extend(["", "details (bar = execution attempted; valid = finite score):"])
    for item in states:
        lines.append(f"\n{colors.bold(item['name'])}  last={item['last_metric'] or '-'} {item['last_row'] or ''}")
        for state in item["states"]:
            detail = (
                f"  {state['metric']:<20} {bar(state['attempted'], planned, 18)} "
                f"attempted={state['attempted']}/{planned} ({pct(state['attempted'], planned)}) "
                f"valid={state['valid']}/{planned} ({pct(state['valid'], planned)}) "
                f"errors={state['errors']} {status_text(state['status'], colors)}"
            )
            lines.append(detail)
        if item["completed"]:
            lines.append("  completed: " + ", ".join(item["completed"]))
        failed = [state["metric"] for state in item["states"] if state["errors"]]
        if failed:
            lines.append("  needs retry: " + ", ".join(failed))

    errors = short_error_summary(states)
    if errors:
        lines.extend(["", colors.warn("recent error summary:")])
        lines.extend(f"  {error}" for error in errors)
    lines.extend(["", colors.dim("Refreshes from checkpoint/scores files only. Ctrl-C to exit.")])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=DEFAULT_PARENT,
        help="A run directory or parent containing run directories (default: %(default)s)",
    )
    parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds")
    parser.add_argument("--stale-after", type=float, default=30.0, help="Seconds before latest write is shown as stale")
    parser.add_argument("--once", action="store_true", help="Render once and exit")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_dir = choose_run(args.run_dir)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    try:
        while True:
            if not args.once:
                sys.stdout.write("\033[2J\033[H")
            print(render(run_dir, args.no_color, args.stale_after), flush=True)
            if args.once:
                return 0
            time.sleep(max(0.2, args.interval))
    except KeyboardInterrupt:
        print("\nmonitor stopped", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
