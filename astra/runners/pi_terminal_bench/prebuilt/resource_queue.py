#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path


EXPECTED_SOURCE_TASKS = 89
EXCLUDED_TASKS = frozenset({"tune-mjcf"})


def task_resources(path: Path) -> tuple[str, float, int, int]:
    with (path / "task.toml").open("rb") as stream:
        value = tomllib.load(stream)
    return (
        path.name,
        float(value["agent"]["timeout_sec"]),
        int(value["environment"]["memory_mb"]),
        int(value["environment"]["cpus"]),
    )


def build_queue(tasks_root: Path) -> list[tuple[str, float, int, int]]:
    source_rows = sorted(
        (
            task_resources(path)
            for path in tasks_root.iterdir()
            if (path / "task.toml").is_file()
        ),
        key=lambda row: (-row[2], -row[1], -row[3], row[0]),
    )
    if len(source_rows) != EXPECTED_SOURCE_TASKS:
        raise RuntimeError(
            f"expected {EXPECTED_SOURCE_TASKS} source tasks, "
            f"found {len(source_rows)}"
        )
    source_names = {row[0] for row in source_rows}
    missing_exclusions = EXCLUDED_TASKS - source_names
    if missing_exclusions:
        raise RuntimeError(
            "excluded Pi tasks are missing from the source cohort: "
            + ", ".join(sorted(missing_exclusions))
        )
    return [row for row in source_rows if row[0] not in EXCLUDED_TASKS]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a long-first, 8GB-safe Terminal-Bench Pi queue"
    )
    parser.add_argument("--tasks-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_queue(args.tasks_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            f"{name}\t{timeout:g}\t{memory}\t{cpus}\n"
            for name, timeout, memory, cpus in rows
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
