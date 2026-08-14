#!/usr/bin/env python3
"""Verify the archived MOI OmniDocBench final inputs and official scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


EXPECTED_GOLDEN_SHA256 = (
    "a45cd84b04ad8b793e775089640e6b681209abea33ead54c1828ddca35fae496"
)
EXPECTED_PAGE_COUNT = 1651
EXPECTED_METRICS = {
    "text_edit": 0.10021964692514598,
    "formula_cdm": 0.9403592033185544,
    "table_teds": 0.8666337554802815,
    "table_teds_structure_only": 0.8977578026780131,
    "reading_order_edit": 0.3134844644103374,
    "overall": 90.22577706245634,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--prediction-dir", type=Path, required=True)
    parser.add_argument("--adapter-report", type=Path, required=True)
    parser.add_argument(
        "--result-dir",
        type=Path,
        help="official evaluator output; omit to validate scoring inputs only",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_inputs(args: argparse.Namespace) -> None:
    require(args.golden.is_file(), f"Golden does not exist: {args.golden}")
    actual_golden_sha = sha256_file(args.golden)
    require(
        actual_golden_sha == EXPECTED_GOLDEN_SHA256,
        "Golden SHA-256 differs: "
        f"expected {EXPECTED_GOLDEN_SHA256}, got {actual_golden_sha}",
    )

    markdown_files = sorted(args.prediction_dir.glob("*.md"))
    require(
        len(markdown_files) == EXPECTED_PAGE_COUNT,
        f"expected {EXPECTED_PAGE_COUNT} prediction Markdown files, "
        f"found {len(markdown_files)}",
    )

    report = load_json(args.adapter_report)
    require(isinstance(report, dict), "adapter report must be a JSON object")
    require(report.get("manifest_version") == 1, "unsupported adapter manifest")
    require(report.get("golden_sha256") == EXPECTED_GOLDEN_SHA256, "manifest Golden SHA mismatch")
    require(report.get("zip_count") == EXPECTED_PAGE_COUNT, "manifest ZIP count mismatch")
    require(report.get("output_count") == EXPECTED_PAGE_COUNT, "manifest output count mismatch")
    require(report.get("empty_output_count") == 4, "manifest empty-output count mismatch")
    counts = report.get("counts", {})
    require(counts.get("failed") == 0, "adapter manifest contains failed records")

    records = report.get("records")
    require(isinstance(records, list), "adapter manifest records must be a list")
    require(len(records) == EXPECTED_PAGE_COUNT, "adapter manifest record count mismatch")
    manifest_outputs: set[str] = set()
    for record in records:
        require(isinstance(record, dict), "adapter manifest record must be an object")
        output_name = record.get("output")
        expected_sha = record.get("output_sha256")
        require(isinstance(output_name, str), "manifest record has no output name")
        require(isinstance(expected_sha, str), f"manifest has no SHA for {output_name}")
        require(output_name not in manifest_outputs, f"duplicate manifest output: {output_name}")
        manifest_outputs.add(output_name)
        output_path = args.prediction_dir / output_name
        require(output_path.is_file(), f"manifest output is missing: {output_name}")
        actual_sha = sha256_file(output_path)
        require(actual_sha == expected_sha, f"prediction SHA mismatch: {output_name}")

    require(
        manifest_outputs == {path.name for path in markdown_files},
        "prediction directory and adapter manifest contain different filenames",
    )


def metric_values(metric_result: dict) -> dict[str, float]:
    text_edit = metric_result["text_block"]["page"]["Edit_dist"]["ALL"]
    formula_cdm = metric_result["display_formula"]["page"]["CDM"]["ALL"]
    table_teds = metric_result["table"]["page"]["TEDS"]["ALL"]
    table_teds_structure = metric_result["table"]["page"][
        "TEDS_structure_only"
    ]["ALL"]
    reading_order_edit = metric_result["reading_order"]["page"]["Edit_dist"]["ALL"]
    overall = ((1 - text_edit) + formula_cdm + table_teds) / 3 * 100
    return {
        "text_edit": text_edit,
        "formula_cdm": formula_cdm,
        "table_teds": table_teds,
        "table_teds_structure_only": table_teds_structure,
        "reading_order_edit": reading_order_edit,
        "overall": overall,
    }


def validate_scores(result_dir: Path) -> dict[str, float]:
    matches = sorted(result_dir.glob("*_metric_result.json"))
    require(len(matches) == 1, f"expected one metric_result JSON, found {len(matches)}")
    metric_result = load_json(matches[0])
    require(isinstance(metric_result, dict), "metric result must be a JSON object")
    actual = metric_values(metric_result)
    for name, expected in EXPECTED_METRICS.items():
        require(
            math.isclose(actual[name], expected, rel_tol=0, abs_tol=1e-12),
            f"{name} differs: expected {expected}, got {actual[name]}",
        )
    return actual


def main() -> int:
    args = parse_args()
    validate_inputs(args)
    print(
        f"PASS inputs: {EXPECTED_PAGE_COUNT} predictions, "
        f"Golden SHA-256 {EXPECTED_GOLDEN_SHA256}"
    )
    if args.result_dir is not None:
        actual = validate_scores(args.result_dir)
        print(
            "PASS scores: "
            f"Overall={actual['overall']:.12f}, "
            f"Text Edit={actual['text_edit']:.12f}, "
            f"Formula CDM={actual['formula_cdm']:.12f}, "
            f"Table TEDS={actual['table_teds']:.12f}, "
            f"Reading Order Edit={actual['reading_order_edit']:.12f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
