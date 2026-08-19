#!/usr/bin/env python3
"""Merge isolated per-platform Lenovo benchmark passes into one report."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[2]
LENOVO_DIR = PLATFORM_ROOT / "scripts/benchmarks/lenovo"

if str(LENOVO_DIR) not in sys.path:
    sys.path.insert(0, str(LENOVO_DIR))

from lenovo_latency_benchmark import PLATFORM_ORDER, _make_report  # noqa: E402


ROOT = PLATFORM_ROOT.parent


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge(platform_runs: dict[str, Path], output_dir: Path) -> Path:
    if set(platform_runs) != set(PLATFORM_ORDER):
        raise ValueError(f"exactly these platforms are required: {', '.join(PLATFORM_ORDER)}")
    if output_dir.exists():
        raise FileExistsError(f"output already exists: {output_dir}")

    manifests: dict[str, dict] = {}
    results: dict[str, dict] = {}
    query_paths: dict[str, Path] = {}
    for platform in PLATFORM_ORDER:
        run_dir = platform_runs[platform].resolve()
        manifest = _read_json(run_dir / "manifest.json")
        if manifest.get("platforms") != [platform]:
            raise ValueError(f"{platform} run is not isolated: {run_dir}")
        for key, expected in {
            "count": 10,
            "seed": 20260814,
            "connections": 4,
            "timeout_seconds": 120.0,
            "platform_execution": "serial",
        }.items():
            if manifest.get(key) != expected:
                raise ValueError(f"{platform} manifest {key}={manifest.get(key)!r}, expected {expected!r}")
        query_path = run_dir / "selected-queries.jsonl"
        query_paths[platform] = query_path
        manifests[platform] = manifest
        loaded_results = _read_json(run_dir / "results.json")
        if set(loaded_results) != {platform}:
            raise ValueError(f"unexpected result keys in {run_dir}: {sorted(loaded_results)}")
        results[platform] = loaded_results[platform]

    query_hashes = {platform: _sha256(path) for platform, path in query_paths.items()}
    if len(set(query_hashes.values())) != 1:
        raise ValueError(f"selected query files differ: {query_hashes}")

    queries = [
        json.loads(line)
        for line in query_paths[PLATFORM_ORDER[0]].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    output_dir.mkdir(parents=True)
    shutil.copyfile(query_paths[PLATFORM_ORDER[0]], output_dir / "selected-queries.jsonl")
    manifest = {
        "created_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
        "questions": manifests[PLATFORM_ORDER[0]]["questions"],
        "count": 10,
        "seed": 20260814,
        "connections": 4,
        "timeout_seconds": 120.0,
        "platform_execution": "serial-isolated-platform-passes",
        "platforms": list(PLATFORM_ORDER),
        "quality_evaluation": False,
        "selected_queries_sha256": next(iter(query_hashes.values())),
        "source_runs": {platform: str(platform_runs[platform].resolve()) for platform in PLATFORM_ORDER},
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = _make_report(
        output_dir,
        queries,
        20260814,
        4,
        120.0,
        "serial-isolated-platform-passes",
        results,
        PLATFORM_ORDER,
    )
    report += "\nSource per-platform runs:\n\n"
    for platform in PLATFORM_ORDER:
        report += f"- `{platform}`: `{platform_runs[platform].resolve()}`\n"
    report_path = output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    for platform in PLATFORM_ORDER:
        parser.add_argument(f"--{platform}", type=Path, required=True)
    args = parser.parse_args()
    platform_runs = {platform: getattr(args, platform) for platform in PLATFORM_ORDER}
    print(merge(platform_runs, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
