#!/usr/bin/env python3
"""Recompute the semiconductor private-dataset scores from tracked artifacts.

The scorer implementation is loaded from an explicit parsing_benchmark source
directory. Use commit 06faf76112c998835f0f9ca174a5f2d311d559f2, the latest
moi-parse-bench commit that predates the formal 2026-07-31 evaluation run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import statistics
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


SCORER_COMMIT = "06faf76112c998835f0f9ca174a5f2d311d559f2"
EXPECTED = {
    "moi-idc-4.1.14": (0.8445537238095239, 0.893841460941976),
    "mineru-precision": (0.5681332404761905, 0.6667336115653937),
    "paddleocr-vl": (0.5855667428571428, 0.7048128339376993),
}


def stable_id(path: Path, source_dir: Path) -> str:
    relative = path.relative_to(source_dir).as_posix()
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]


def source_files(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )


def extract_moi_parsed(zip_path: Path, output_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        members = [name for name in archive.namelist() if name.endswith("_parse.json")]
        if len(members) != 1:
            raise ValueError(
                f"expected one _parse.json in {zip_path}, found {len(members)}"
            )
        output_path.write_bytes(archive.read(members[0]))


def score_product(
    runner: Any,
    product: str,
    files: list[Path],
    source_dir: Path,
    golden_dir: Path,
    runs_dir: Path,
    document_parsing_dir: Path,
    temp_dir: Path,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for source in files:
        case_id = stable_id(source, source_dir)
        case_name = f"{source.name}--{case_id}"
        golden = golden_dir / f"{source.name}.json"
        if product == "moi-idc-4.1.14":
            parsed = temp_dir / f"{case_name}_parse.json"
            zip_path = (
                runs_dir / "半导体场景私有数据集-idc-4.1.14" / f"{case_name}.zip"
            )
            extract_moi_parsed(
                zip_path,
                parsed,
            )
            parsed_reference = f"{zip_path.relative_to(document_parsing_dir)}::_parse.json"
        elif product == "mineru-precision":
            parsed = (
                runs_dir
                / "半导体场景模拟数据-mineru-precision"
                / "converted_parsed"
                / f"{case_name}_parse.json"
            )
            parsed_reference = str(parsed.relative_to(document_parsing_dir))
        else:
            parsed = (
                runs_dir
                / "半导体场景模拟数据-paddleocr-vl"
                / "converted_parsed"
                / f"{case_name}_parse.json"
            )
            parsed_reference = str(parsed.relative_to(document_parsing_dir))

        if not golden.is_file() or not parsed.is_file():
            raise FileNotFoundError(f"missing pair: parsed={parsed}, golden={golden}")
        report = runner.run_single_from_json(parsed, golden)
        dimensions: dict[str, dict[str, Any]] = {}
        applicable: list[dict[str, Any]] = []
        for dimension, score in report.dimension_scores.items():
            payload = score.to_dict()
            dimensions[str(dimension)] = payload
            if not payload.get("not_applicable", False) and payload.get("f1") is not None:
                applicable.append(payload)

        equal_score = (
            statistics.fmean(float(item["f1"]) for item in applicable)
            if applicable
            else 0.0
        )
        weight_total = sum(max(int(item.get("total_count") or 1), 1) for item in applicable)
        weighted_score = (
            sum(
                float(item["f1"]) * max(int(item.get("total_count") or 1), 1)
                for item in applicable
            )
            / weight_total
            if weight_total
            else 0.0
        )
        records.append(
            {
                "case_name": source.name,
                "case_id": case_id,
                "format": source.suffix.lower().lstrip("."),
                "parsed_path": parsed_reference,
                "golden_path": str(golden.relative_to(document_parsing_dir)),
                "dimension_scores": dimensions,
                "per_file_dimension_equal_score": equal_score,
                "per_file_element_count_weighted_score": weighted_score,
            }
        )

    all_dimensions = sorted(
        {dimension for record in records for dimension in record["dimension_scores"]}
    )
    dimension_summary: dict[str, dict[str, Any]] = {}
    for dimension in all_dimensions:
        values = [
            record["dimension_scores"][dimension]
            for record in records
            if dimension in record["dimension_scores"]
            and not record["dimension_scores"][dimension].get("not_applicable", False)
            and record["dimension_scores"][dimension].get("f1") is not None
        ]
        total = sum(max(int(item.get("total_count") or 1), 1) for item in values)
        dimension_summary[dimension] = {
            "contributing_file_count": len(values),
            "total_count": total,
            "f1_avg_across_files": (
                statistics.fmean(float(item["f1"]) for item in values) if values else None
            ),
            "f1_weighted_by_elements": (
                sum(
                    float(item["f1"]) * max(int(item.get("total_count") or 1), 1)
                    for item in values
                )
                / total
                if total
                else None
            ),
        }

    summary = {
        "file_count": len(records),
        "per_file_dimension_equal_avg": statistics.fmean(
            record["per_file_dimension_equal_score"] for record in records
        ),
        "per_file_element_count_weighted_avg": statistics.fmean(
            record["per_file_element_count_weighted_score"] for record in records
        ),
    }
    return {
        "product": product,
        "scorer": {
            "engine": "python:parsing_benchmark",
            "package_version": "1.0.0",
            "source_commit": SCORER_COMMIT,
        },
        "summary": summary,
        "dimension_summary": dimension_summary,
        "records": records,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scorer-src",
        type=Path,
        required=True,
        help="Path to tools/parsing_benchmark/src from scorer commit 06faf76.",
    )
    parser.add_argument("--document-parsing-dir", type=Path, default=repo_root / "document-parsing")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-expected-check", action="store_true")
    args = parser.parse_args()

    scorer_src = args.scorer_src.resolve()
    if not (scorer_src / "parsing_benchmark" / "runner.py").is_file():
        parser.error(f"invalid parsing_benchmark source directory: {scorer_src}")
    sys.path.insert(0, str(scorer_src))
    from parsing_benchmark.runner import BenchmarkRunner  # type: ignore

    # run_single_from_json infers the document type from the parsed JSON path and
    # warns once per case about the .json suffix. The benchmark then deliberately
    # falls back to its PDF-compatible offline profile, so keep reproduction logs
    # focused on score progress and real failures.
    logging.getLogger("parsing_benchmark.runner").setLevel(logging.ERROR)

    base = args.document_parsing_dir.resolve()
    source_dir = base / "datasets" / "半导体场景模拟数据"
    golden_dir = base / "datasets" / "半导体场景模拟数据golden"
    files = source_files(source_dir)
    if len(files) != 50:
        parser.error(f"expected 50 source files, found {len(files)}")

    runner = BenchmarkRunner(strict_contract=False)
    results: dict[str, Any] = {
        "schema_version": "semiconductor-private-score-v1",
        "scorer_commit": SCORER_COMMIT,
        "products": {},
    }
    with tempfile.TemporaryDirectory(prefix="semiconductor-private-score-") as temp:
        for product in EXPECTED:
            print(f"[score] {product}", flush=True)
            result = score_product(
                runner,
                product,
                files,
                source_dir,
                golden_dir,
                base / "runs",
                base,
                Path(temp),
            )
            results["products"][product] = result
            if not args.skip_expected_check:
                actual = (
                    result["summary"]["per_file_dimension_equal_avg"],
                    result["summary"]["per_file_element_count_weighted_avg"],
                )
                expected = EXPECTED[product]
                if any(abs(left - right) > 1e-12 for left, right in zip(actual, expected)):
                    raise RuntimeError(
                        f"{product} score mismatch: actual={actual}, expected={expected}"
                    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
