#!/usr/bin/env python3
"""Collect completed OmniDocBench parsing/scoring results for record export."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path("/Users/muuushroom/gitrepos/moi-benchmark/rag")
RUNS = ROOT / "runs" / "stage1" / "omnidocbench"
SPECS = (
    ("S1-ODB-PREC-SMOKE", "20260803-precision-smoke-20"),
    ("S1-ODB-AGENT-SMOKE", "20260803-agent-smoke-20"),
    ("S1-ODB-PREC-200", "20260804-precision-stratified-200"),
    ("S1-ODB-AGENT-200", "20260804-agent-stratified-200"),
    ("S1-ODB-FULL", "20260804-precision-full-1651"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_official_summary(run_dir: Path) -> Path | None:
    candidates = sorted(
        (run_dir / "official").glob("scorer-output*/predictions_quick_match_run_summary.json"),
        key=lambda path: path.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def parser_metadata(attempts: list[dict[str, Any]]) -> tuple[str | None, str | None, str | None, str | None]:
    summaries = []
    for attempt in attempts:
        path_value = attempt.get("parser_summary")
        if path_value:
            path = Path(path_value)
            if path.is_file():
                summaries.append(path)
    if not summaries:
        return None, None, None, None
    mtimes = [path.stat().st_mtime for path in summaries]
    sample = load_json(summaries[-1])
    return (
        sample.get("engine") or sample.get("backend_used"),
        sample.get("parser_version"),
        datetime.fromtimestamp(min(mtimes)).astimezone().isoformat(timespec="seconds"),
        datetime.fromtimestamp(max(mtimes)).astimezone().isoformat(timespec="seconds"),
    )


def official_metric(summary: dict[str, Any], name: str) -> tuple[float, int | None]:
    metric = summary["notebook_metric_summary"]["metrics"][name]
    return metric["notebook_value"], metric.get("page_denominator")


def collect_one(experiment_id: str, run_name: str) -> dict[str, Any] | None:
    run_dir = RUNS / run_name
    summary_path = latest_official_summary(run_dir)
    metrics_path = run_dir / "moi-unified" / "metrics.json"
    progress_path = run_dir / "moi-unified" / "progress.json"
    attempts_path = run_dir / "moi-unified" / "attempts.jsonl"
    if not summary_path or not metrics_path.is_file() or not attempts_path.is_file():
        return None

    official = load_json(summary_path)
    local_metrics = load_json(metrics_path)
    attempts = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line]
    progress = load_json(progress_path) if progress_path.is_file() else {}
    planned = int(progress.get("planned_pages", local_metrics["planned_pages"]))
    completed = int(progress.get("completed_pages", len(attempts)))
    accepted = int(progress.get("accepted_pages", local_metrics["accepted_pages"]))
    if completed != planned:
        return None

    edit_distance, edit_denominator = official_metric(official, "text_block_Edit_dist")
    cdm, cdm_denominator = official_metric(official, "display_formula_CDM")
    teds, teds_denominator = official_metric(official, "table_TEDS")
    metrics: dict[str, dict[str, Any]] = {
        "Normalized Edit Distance": {
            "value": edit_distance,
            "numerator": None,
            "denominator": edit_denominator,
            "na_reason": None,
        },
        "CDM": {"value": cdm, "numerator": None, "denominator": cdm_denominator, "na_reason": None},
        "TEDS": {"value": teds, "numerator": None, "denominator": teds_denominator, "na_reason": None},
        "Accepted-page rate": {
            "value": local_metrics["accepted_page_rate"],
            "numerator": accepted,
            "denominator": planned,
            "na_reason": None,
        },
    }
    if experiment_id == "S1-ODB-FULL":
        metrics["Gold Evidence Preservation"] = {
            "value": None,
            "numerator": None,
            "denominator": None,
            "na_reason": "N/A: GOLD_LINEAGE_NOT_COMPUTED",
        }
        metrics["Run completeness"] = {
            "value": completed / planned if planned else 0,
            "numerator": completed,
            "denominator": planned,
            "na_reason": None,
        }
    else:
        if experiment_id.endswith("-200"):
            metrics["Gold Evidence Preservation"] = {
                "value": None,
                "numerator": None,
                "denominator": None,
                "na_reason": "N/A: GOLD_LINEAGE_NOT_COMPUTED",
            }
        metrics["P50/P95 latency"] = {
            "value": (
                f"P50={local_metrics['parse_latency_p50_ms']:.3f} ms; "
                f"P95={local_metrics['parse_latency_p95_ms']:.3f} ms"
            ),
            "numerator": None,
            "denominator": len(attempts),
            "na_reason": None,
        }

    parser_name, product_version, started_at, ended_at = parser_metadata(attempts)
    hashes_path = run_dir / "artifacts" / "hashes.txt"
    dataset_revision = None
    if hashes_path.is_file():
        first = hashes_path.read_text(encoding="utf-8").splitlines()[0]
        dataset_revision = first.split()[0] if first else None
    return {
        "experiment_id": experiment_id,
        "run_id": run_name,
        "run_dir": str(run_dir),
        "pipeline": local_metrics.get("pipeline"),
        "planned_pages": planned,
        "completed_pages": completed,
        "accepted_pages": accepted,
        "failed_pages": int(progress.get("failed_pages", completed - accepted)),
        "official_summary": str(summary_path),
        "official_summary_sha256": sha256_file(summary_path),
        "metrics": metrics,
        "ledger": {
            "run_id": run_name,
            "batch_id": "omnidocbench-stage1-20260804",
            "dataset_revision_hash": dataset_revision,
            "code_commit": git_commit(),
            "product_version": product_version,
            "parser": parser_name,
            "started_at": started_at,
            "ended_at": ended_at,
            "planned_attempts": planned,
            "actual_attempts": completed,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    runs = []
    missing = []
    for experiment_id, run_name in SPECS:
        result = collect_one(experiment_id, run_name)
        if result is None:
            missing.append(run_name)
        else:
            runs.append(result)
    if missing and not args.allow_partial:
        raise SystemExit(f"OmniDocBench experiments are incomplete: {', '.join(missing)}")
    payload = {
        "schema_version": "moi-omnidocbench-results-v1",
        "complete": not missing,
        "missing_runs": missing,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"collected={len(runs)} missing={len(missing)} output={args.output}")


if __name__ == "__main__":
    main()
