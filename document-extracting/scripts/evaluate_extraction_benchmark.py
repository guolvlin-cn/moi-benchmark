#!/usr/bin/env python3
"""Evaluate MOI and LandingAI on the frozen document-extraction benchmark.

The script reads the repository's current 100-case SROIE, VRDU Registration,
and Kleister-NDA subsets. It scores semantic extraction quality without
repairing field choices, while allowing a representation-only adapter for
MOI's ``party: [{"value": "..."}]`` serialization.

Outputs:
  summary.json       Full machine-readable metrics.
  comparison.csv     One row per dataset/system.
  field_metrics.csv  One row per dataset/system/field.
  details.jsonl      One row per case/field, including gold, prediction, and
                     error classification.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import lzma
import math
import re
import statistics
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
DOCUMENT_EXTRACTING_ROOT = SCRIPT_DIR.parent
DEFAULT_DATASETS_ROOT = DOCUMENT_EXTRACTING_ROOT / "datasets"
DEFAULT_RUNS_ROOT = DOCUMENT_EXTRACTING_ROOT / "runs"
DEFAULT_OUTPUT_DIR = DOCUMENT_EXTRACTING_ROOT / "evaluation" / "latest"

DATASET_FIELDS = {
    "sroie": ("company", "date", "address", "total"),
    "vrdu": (
        "file_date",
        "foreign_principle_name",
        "registrant_name",
        "registration_num",
        "signer_name",
        "signer_title",
    ),
    "kleister": ("effective_date", "jurisdiction", "party", "term"),
}

ARRAY_FIELDS = {("kleister", "party")}

DEFAULT_RUN_DIRS = {
    ("sroie", "moi"): "matrixflow-sroie2019-workflow-2b084712",
    ("sroie", "landingai"): "landingai-sroie-batch-20260724T063234Z",
    ("vrdu", "moi"): "matrixflow-vrdu-registration-schema-fixed",
    ("vrdu", "landingai"): "landingai-vrdu-batch-20260724T055842Z",
    ("kleister", "moi"): "matrixflow-kleister-nda-schema-fixed",
    ("kleister", "landingai"): "landingai-kleister-batch-20260724T072322Z",
}

DEFAULT_EXCLUSIONS = {
    "vrdu": {
        "19920101_Office of Tibet_Dissemination Report_Dissemination Report": (
            "Excluded from both systems because the MOI run was blocked by the "
            "configured model provider's content-safety inspection, which is outside "
            "the intended information-extraction quality scope."
        ),
        "19930501_Office of Tibet_Dissemination Report_Dissemination Report": (
            "Excluded from both systems because the MOI run was blocked by the "
            "configured model provider's content-safety inspection, which is outside "
            "the intended information-extraction quality scope."
        ),
        "19950710_Far East Trade Services, Inc._Dissemination Report_Dissemination Report": (
            "Excluded from both systems because the MOI run was blocked by the "
            "configured model provider's content-safety inspection, which is outside "
            "the intended information-extraction quality scope."
        ),
    }
}


@dataclass
class Prediction:
    status: str
    extraction: dict[str, Any] | None
    error: str | None
    duration_ms: float | None
    credits: float | None


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: "Counts") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    def metrics(self) -> dict[str, float | int]:
        precision = safe_ratio(self.tp, self.tp + self.fp)
        recall = safe_ratio(self.tp, self.tp + self.fn)
        f1 = (
            0.0
            if precision + recall == 0
            else 2.0 * precision * recall / (precision + recall)
        )
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return 0.0 if denominator == 0 else float(numerator) / float(denominator)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clean_scalar(value: Any) -> str | None:
    """Canonicalize all supported empty scalar forms to None.

    Products may emit JSON null while a golden file may contain "" or only
    whitespace. Treating all three as absent makes empty-field evaluation
    representation-independent without changing any non-empty value.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value).strip() or None


def prediction_values(dataset: str, field: str, value: Any) -> list[str]:
    if (dataset, field) in ARRAY_FIELDS:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        values = []
        for item in value:
            # Representation-only adapter: MOI serializes array<string> values
            # as [{"value": "..."}] in the downloadable ZIP.
            if isinstance(item, dict) and set(item) == {"value"}:
                item = item["value"]
            cleaned = clean_scalar(item)
            if cleaned is not None:
                values.append(cleaned)
        return values
    cleaned = clean_scalar(value)
    return [] if cleaned is None else [cleaned]


def normalize_unicode(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def normalize_alphanumeric(value: str) -> str:
    value = normalize_unicode(value).casefold()
    return "".join(character for character in value if character.isalnum())


def normalize_whitespace(value: str) -> str:
    return " ".join(normalize_unicode(value).split())


def normalize_sroie_date_candidates(value: str) -> set[str]:
    value = normalize_unicode(value)
    value = re.sub(r"\s+\d{1,2}:\d{2}(?::\d{2})?\s*$", "", value)
    value = re.sub(r"(?i)\b(?:date|dated)\s*[:\-]\s*", "", value).strip()
    candidates: set[str] = set()
    formats = (
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d/%m/%y",
        "%m/%d/%y",
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%d.%m.%Y",
        "%m.%d.%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d %Y",
        "%B %d %Y",
    )
    for date_format in formats:
        try:
            parsed = dt.datetime.strptime(value, date_format).date()
        except ValueError:
            continue
        candidates.add(parsed.isoformat())
    if candidates:
        return candidates
    fallback = normalize_alphanumeric(value)
    return {fallback} if fallback else set()


def normalize_amount(value: str) -> Decimal | str:
    value = normalize_unicode(value).replace(",", "")
    matches = re.findall(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)", value)
    if len(matches) == 1:
        try:
            return Decimal(matches[0])
        except InvalidOperation:
            pass
    return normalize_alphanumeric(value)


def match_sroie(field: str, prediction: str, gold: str) -> bool:
    if field == "date":
        return bool(
            normalize_sroie_date_candidates(prediction)
            & normalize_sroie_date_candidates(gold)
        )
    if field == "total":
        return normalize_amount(prediction) == normalize_amount(gold)
    return normalize_alphanumeric(prediction) == normalize_alphanumeric(gold)


def remove_redundant_whitespace(value: str) -> str:
    return " ".join(value.strip().split())


def vrdu_decode_date(value: str) -> dict[str, int] | None:
    value = re.sub(r"[^0-9a-zA-Z/\-,]", "", value)
    for date_format in (
        "%m/%d/%y",
        "%m/%d/%Y",
        "%m/%d",
        "%b%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%B%d,%Y",
        "%Y/%m/%d",
    ):
        try:
            parsed = dt.datetime.strptime(value, date_format).date()
        except ValueError:
            continue
        return {"year": parsed.year, "month": parsed.month, "day": parsed.day}
    return None


def ascii_alphanumeric(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]", "", value)


def match_vrdu(field: str, prediction: str, gold: str) -> bool:
    prediction = remove_redundant_whitespace(prediction)
    gold = remove_redundant_whitespace(gold)

    if field == "file_date":
        prediction_date = vrdu_decode_date(prediction)
        gold_date = vrdu_decode_date(gold)
        if prediction_date and gold_date:
            same = (
                prediction_date["year"] == gold_date["year"]
                and prediction_date["month"] == gold_date["month"]
                and prediction_date["day"] == gold_date["day"]
            )
            swapped = (
                prediction_date["year"] == gold_date["year"]
                and prediction_date["day"] == gold_date["month"]
                and prediction_date["month"] == gold_date["day"]
            )
            return same or swapped
        return ascii_alphanumeric(prediction) == ascii_alphanumeric(gold)

    if field in {"foreign_principle_name", "registrant_name", "signer_name"}:
        return re.sub(r"\s", "", prediction) == re.sub(r"\s", "", gold)

    if field == "registration_num":
        return re.sub(r"[^0-9]", "", prediction) == re.sub(r"[^0-9]", "", gold)

    if field == "signer_title":
        return ascii_alphanumeric(prediction) == ascii_alphanumeric(gold)

    raise KeyError(f"Unknown VRDU field: {field}")


def normalize_kleister(value: str) -> str:
    value = normalize_unicode(value)
    value = re.sub(r"[ :]+", "_", value)
    return value.upper()


def match_kleister(_field: str, prediction: str, gold: str) -> bool:
    return normalize_kleister(prediction) == normalize_kleister(gold)


def strict_match(_field: str, prediction: str, gold: str) -> bool:
    return prediction.strip() == gold.strip()


def matcher_for(dataset: str, strict: bool) -> Callable[[str, str, str], bool]:
    if strict:
        return strict_match
    return {
        "sroie": match_sroie,
        "vrdu": match_vrdu,
        "kleister": match_kleister,
    }[dataset]


def match_value_lists(
    field: str,
    predictions: list[str],
    gold_values: list[str],
    matcher: Callable[[str, str, str], bool],
    scalar: bool,
) -> tuple[Counts, bool, list[tuple[int, int]]]:
    if scalar:
        predictions = predictions[:1]
        if not predictions and not gold_values:
            return Counts(), True, []
        if not predictions:
            return Counts(fn=1), False, []
        if not gold_values:
            return Counts(fp=1), False, []
        for gold_index, gold in enumerate(gold_values):
            if matcher(field, predictions[0], gold):
                return Counts(tp=1), True, [(0, gold_index)]
        return Counts(fp=1, fn=1), False, []

    available_gold = set(range(len(gold_values)))
    matches: list[tuple[int, int]] = []
    for prediction_index, prediction in enumerate(predictions):
        for gold_index in sorted(available_gold):
            if matcher(field, prediction, gold_values[gold_index]):
                matches.append((prediction_index, gold_index))
                available_gold.remove(gold_index)
                break
    counts = Counts(
        tp=len(matches),
        fp=len(predictions) - len(matches),
        fn=len(gold_values) - len(matches),
    )
    return counts, counts.fp == 0 and counts.fn == 0, matches


def load_sroie_gold(datasets_root: Path) -> dict[str, dict[str, list[str]]]:
    root = datasets_root / "SROIE2019"
    manifest = read_json(root / "selection_manifest.json")
    result = {}
    for case in manifest["cases"]:
        entities = read_json(root / case["entities"])
        result[case["case_id"]] = {
            field: prediction_values("sroie", field, entities.get(field))
            for field in DATASET_FIELDS["sroie"]
        }
    return result


def load_vrdu_gold(datasets_root: Path) -> dict[str, dict[str, list[str]]]:
    root = datasets_root / "VRDU"
    manifest = read_json(root / "selection_manifest.json")
    selected = {case["case_id"] for case in manifest["cases"]}
    result: dict[str, dict[str, list[str]]] = {}
    dataset_path = root / "registration-form" / "main" / "dataset.jsonl"
    with dataset_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            case_id = Path(row["filename"]).stem
            if case_id not in selected:
                continue
            fields = {field: [] for field in DATASET_FIELDS["vrdu"]}
            for field, appearances in row.get("annotations", []):
                if field not in fields:
                    continue
                values = [
                    clean_scalar(appearance[0])
                    for appearance in appearances
                    if appearance and clean_scalar(appearance[0]) is not None
                ]
                # Multiple annotations usually represent appearances of one
                # scalar value. Retain them as accepted alternatives.
                fields[field].extend(value for value in values if value not in fields[field])
            result[case_id] = fields
    if set(result) != selected:
        raise RuntimeError(f"VRDU gold mismatch: missing {sorted(selected - set(result))}")
    return result


def read_xz_rows(path: Path) -> list[list[str]]:
    with lzma.open(path, "rt", encoding="utf-8") as handle:
        return list(csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE))


def parse_kleister_expected(line: str) -> dict[str, list[str]]:
    fields = {field: [] for field in DATASET_FIELDS["kleister"]}
    for key, value in re.findall(r"([a-z_]+)=(\S+)", line.strip()):
        if key in fields:
            fields[key].append(value)
    return fields


def load_kleister_gold(datasets_root: Path) -> dict[str, dict[str, list[str]]]:
    root = datasets_root / "Kleister-NDA"
    result = {}
    for split in ("dev-0", "train"):
        input_rows = read_xz_rows(root / split / "in.tsv.xz")
        expected_lines = (root / split / "expected.tsv").read_text(
            encoding="utf-8"
        ).splitlines()
        if len(input_rows) != len(expected_lines):
            raise RuntimeError(f"Kleister {split} input/gold length mismatch")
        for input_row, expected in zip(input_rows, expected_lines):
            case_id = Path(input_row[0]).stem
            result[case_id] = parse_kleister_expected(expected)

    manifest = read_json(root / "selection_manifest.json")
    selected = {case["case_id"] for case in manifest["cases"]}
    if set(result) != selected:
        raise RuntimeError(
            "Kleister gold mismatch: "
            f"missing={sorted(selected - set(result))}, "
            f"extra={sorted(set(result) - selected)}"
        )
    return result


def load_gold(datasets_root: Path) -> dict[str, dict[str, dict[str, list[str]]]]:
    return {
        "sroie": load_sroie_gold(datasets_root),
        "vrdu": load_vrdu_gold(datasets_root),
        "kleister": load_kleister_gold(datasets_root),
    }


def parse_iso_duration_ms(started_at: Any, completed_at: Any) -> float | None:
    if not isinstance(started_at, str) or not isinstance(completed_at, str):
        return None
    try:
        started = dt.datetime.fromisoformat(started_at)
        completed = dt.datetime.fromisoformat(completed_at)
    except ValueError:
        return None
    return max(0.0, (completed - started).total_seconds() * 1000.0)


def load_landingai_prediction(case_dir: Path) -> Prediction:
    status_path = case_dir / "status.json"
    if not status_path.exists():
        return Prediction("missing", None, "missing status.json", None, None)
    status = read_json(status_path)
    state = status.get("status", "unknown")
    duration_values = [
        (status.get("parse_metadata") or {}).get("duration_ms"),
        (status.get("extract_metadata") or {}).get("duration_ms"),
    ]
    duration_ms = (
        float(sum(value for value in duration_values if isinstance(value, (int, float))))
        if any(isinstance(value, (int, float)) for value in duration_values)
        else None
    )
    credit_values = [
        (status.get("parse_metadata") or {}).get("credit_usage"),
        (status.get("extract_metadata") or {}).get("credit_usage"),
    ]
    credits = (
        float(sum(value for value in credit_values if isinstance(value, (int, float))))
        if any(isinstance(value, (int, float)) for value in credit_values)
        else None
    )
    if state != "completed":
        return Prediction(state, None, status.get("error"), duration_ms, credits)
    response_path = case_dir / "extract-response.json"
    if not response_path.exists():
        return Prediction(
            "invalid_output", None, "missing extract-response.json", duration_ms, credits
        )
    response = read_json(response_path)
    extraction = response.get("extraction")
    if not isinstance(extraction, dict):
        return Prediction(
            "invalid_output", None, "response extraction is not an object", duration_ms, credits
        )
    return Prediction("completed", extraction, None, duration_ms, credits)


def find_moi_extract_member(names: Iterable[str]) -> str | None:
    matches = [
        name
        for name in names
        if name.endswith("_extract.json") and not name.endswith("_extracted_source.json")
    ]
    return matches[0] if len(matches) == 1 else None


def load_moi_prediction(case_dir: Path) -> Prediction:
    status_path = case_dir / "status.json"
    if not status_path.exists():
        return Prediction("missing", None, "missing status.json", None, None)
    status = read_json(status_path)
    state = status.get("status", "unknown")
    duration_ms = parse_iso_duration_ms(
        status.get("started_at"), status.get("completed_at")
    )
    if state != "completed":
        return Prediction(state, None, status.get("error"), duration_ms, None)
    archives = sorted(case_dir.glob("*.zip"))
    if len(archives) != 1:
        return Prediction(
            "invalid_output",
            None,
            f"expected one ZIP, found {len(archives)}",
            duration_ms,
            None,
        )
    try:
        with zipfile.ZipFile(archives[0]) as archive:
            member = find_moi_extract_member(archive.namelist())
            if member is None:
                return Prediction(
                    "invalid_output",
                    None,
                    "ZIP does not contain exactly one *_extract.json",
                    duration_ms,
                    None,
                )
            payload = json.loads(archive.read(member))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        return Prediction("invalid_output", None, str(error), duration_ms, None)
    if not isinstance(payload, list) or len(payload) != 1:
        return Prediction(
            "invalid_output",
            None,
            "MOI extract payload must be a one-item array",
            duration_ms,
            None,
        )
    extraction = payload[0].get("extraction")
    if not isinstance(extraction, dict):
        return Prediction(
            "invalid_output", None, "MOI extraction is not an object", duration_ms, None
        )
    return Prediction("completed", extraction, None, duration_ms, None)


def load_prediction(system: str, case_dir: Path) -> Prediction:
    if system == "moi":
        return load_moi_prediction(case_dir)
    if system == "landingai":
        return load_landingai_prediction(case_dir)
    raise KeyError(system)


def schema_issues(dataset: str, extraction: dict[str, Any] | None) -> list[str]:
    if extraction is None:
        return ["output_not_available"]
    expected = set(DATASET_FIELDS[dataset])
    issues = []
    missing = expected - set(extraction)
    extra = set(extraction) - expected
    if missing:
        issues.append(f"missing_fields:{','.join(sorted(missing))}")
    if extra:
        issues.append(f"extra_fields:{','.join(sorted(extra))}")
    for field in expected & set(extraction):
        value = extraction[field]
        if (dataset, field) in ARRAY_FIELDS:
            # Treat MOI's representation-only {"value": "..."} wrapper as
            # equivalent to an array<string> item for benchmark compliance.
            # This matches the adapter already used by semantic scoring.
            def valid_array_item(item: Any) -> bool:
                return isinstance(item, str) or (
                    isinstance(item, dict)
                    and set(item) == {"value"}
                    and isinstance(item["value"], str)
                )

            if not isinstance(value, list) or any(
                not valid_array_item(item) for item in value
            ):
                issues.append(f"invalid_type:{field}:expected_array_of_strings")
        elif value is not None and not isinstance(value, str):
            issues.append(f"invalid_type:{field}:expected_nullable_string")
    return issues


def classify_error(
    gold_values: list[str],
    prediction_values_: list[str],
    correct: bool,
    status: str,
    scalar: bool,
    counts: Counts,
) -> str:
    if status != "completed":
        return "system_failure"
    if correct:
        return "correct"
    if not prediction_values_ and gold_values:
        return "missing_field"
    if prediction_values_ and not gold_values:
        return "false_positive"
    if not scalar and counts.fp and counts.fn:
        return "array_missing_and_extra"
    if not scalar and counts.fp:
        return "array_extra_item"
    if not scalar and counts.fn:
        return "array_missing_item"
    return "wrong_value"


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p95": None, "sum": None}
    ordered = sorted(values)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": ordered[p95_index],
        "sum": sum(values),
    }


def evaluate_one(
    dataset: str,
    system: str,
    gold_cases: dict[str, dict[str, list[str]]],
    run_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    fields = DATASET_FIELDS[dataset]
    normalized_by_field = {field: Counts() for field in fields}
    strict_by_field = {field: Counts() for field in fields}
    field_correct_counts = defaultdict(int)
    strict_field_correct_counts = defaultdict(int)
    normalized_total = Counts()
    strict_total = Counts()
    details = []
    status_counts: dict[str, int] = defaultdict(int)
    document_exact = 0
    strict_document_exact = 0
    schema_compliant = 0
    durations = []
    credits = []

    for case_id, gold_fields in gold_cases.items():
        prediction = load_prediction(system, run_dir / "cases" / case_id)
        status_counts[prediction.status] += 1
        if prediction.duration_ms is not None:
            durations.append(prediction.duration_ms)
        if prediction.credits is not None:
            credits.append(prediction.credits)
        issues = schema_issues(dataset, prediction.extraction)
        if not issues:
            schema_compliant += 1

        normalized_doc_correct = prediction.status == "completed"
        strict_doc_correct = prediction.status == "completed"
        extraction = prediction.extraction or {}

        for field in fields:
            gold_values = gold_fields.get(field, [])
            predicted_values = prediction_values(dataset, field, extraction.get(field))
            scalar = (dataset, field) not in ARRAY_FIELDS

            normalized_counts, normalized_correct, normalized_matches = match_value_lists(
                field,
                predicted_values,
                gold_values,
                matcher_for(dataset, strict=False),
                scalar,
            )
            strict_counts, strict_correct, strict_matches = match_value_lists(
                field,
                predicted_values,
                gold_values,
                matcher_for(dataset, strict=True),
                scalar,
            )

            # A system-level failure never receives document/field correctness,
            # even for fields whose gold value is absent.
            if prediction.status != "completed":
                normalized_correct = False
                strict_correct = False

            normalized_by_field[field].add(normalized_counts)
            strict_by_field[field].add(strict_counts)
            normalized_total.add(normalized_counts)
            strict_total.add(strict_counts)
            field_correct_counts[field] += int(normalized_correct)
            strict_field_correct_counts[field] += int(strict_correct)
            normalized_doc_correct &= normalized_correct
            strict_doc_correct &= strict_correct

            details.append(
                {
                    "dataset": dataset,
                    "system": system,
                    "case_id": case_id,
                    "field": field,
                    "status": prediction.status,
                    "gold": gold_values,
                    "prediction": predicted_values,
                    "normalized_correct": normalized_correct,
                    "strict_correct": strict_correct,
                    "normalized_counts": normalized_counts.metrics(),
                    "strict_counts": strict_counts.metrics(),
                    "normalized_matches": normalized_matches,
                    "strict_matches": strict_matches,
                    "error_type": classify_error(
                        gold_values,
                        predicted_values,
                        normalized_correct,
                        prediction.status,
                        scalar,
                        normalized_counts,
                    ),
                    "schema_issues": issues,
                    "system_error": prediction.error,
                }
            )

        document_exact += int(normalized_doc_correct)
        strict_document_exact += int(strict_doc_correct)

    case_count = len(gold_cases)
    field_rows = []
    normalized_field_f1 = []
    strict_field_f1 = []
    for field in fields:
        normalized_metrics = normalized_by_field[field].metrics()
        strict_metrics = strict_by_field[field].metrics()
        normalized_field_f1.append(float(normalized_metrics["f1"]))
        strict_field_f1.append(float(strict_metrics["f1"]))
        field_rows.append(
            {
                "dataset": dataset,
                "system": system,
                "field": field,
                "normalized_tp": normalized_metrics["tp"],
                "normalized_fp": normalized_metrics["fp"],
                "normalized_fn": normalized_metrics["fn"],
                "normalized_precision": normalized_metrics["precision"],
                "normalized_recall": normalized_metrics["recall"],
                "normalized_f1": normalized_metrics["f1"],
                "normalized_field_accuracy": safe_ratio(
                    field_correct_counts[field], case_count
                ),
                "strict_tp": strict_metrics["tp"],
                "strict_fp": strict_metrics["fp"],
                "strict_fn": strict_metrics["fn"],
                "strict_precision": strict_metrics["precision"],
                "strict_recall": strict_metrics["recall"],
                "strict_f1": strict_metrics["f1"],
                "strict_field_accuracy": safe_ratio(
                    strict_field_correct_counts[field], case_count
                ),
            }
        )

    normalized_metrics = normalized_total.metrics()
    strict_metrics = strict_total.metrics()
    metrics = {
        "dataset": dataset,
        "system": system,
        "run_dir": str(run_dir.resolve()),
        "case_count": case_count,
        "status_counts": dict(sorted(status_counts.items())),
        "success_rate": safe_ratio(status_counts.get("completed", 0), case_count),
        "schema_compliant_count": schema_compliant,
        "schema_compliance_rate": safe_ratio(schema_compliant, case_count),
        "normalized_micro": normalized_metrics,
        "normalized_macro_f1": statistics.fmean(normalized_field_f1),
        "normalized_document_exact_count": document_exact,
        "normalized_document_exact_match": safe_ratio(document_exact, case_count),
        "strict_micro": strict_metrics,
        "strict_macro_f1": statistics.fmean(strict_field_f1),
        "strict_document_exact_count": strict_document_exact,
        "strict_document_exact_match": safe_ratio(strict_document_exact, case_count),
        "duration_ms": distribution(durations),
        "credits": distribution(credits),
    }
    return metrics, field_rows, details


def comparison_row(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": metrics["dataset"],
        "system": metrics["system"],
        "original_case_count": metrics["original_case_count"],
        "excluded_case_count": metrics["excluded_case_count"],
        "case_count": metrics["case_count"],
        "completed_count": metrics["status_counts"].get("completed", 0),
        "success_rate": metrics["success_rate"],
        "schema_compliance_rate": metrics["schema_compliance_rate"],
        "normalized_micro_precision": metrics["normalized_micro"]["precision"],
        "normalized_micro_recall": metrics["normalized_micro"]["recall"],
        "normalized_micro_f1": metrics["normalized_micro"]["f1"],
        "normalized_macro_f1": metrics["normalized_macro_f1"],
        "normalized_document_exact_match": metrics["normalized_document_exact_match"],
        "strict_micro_f1": metrics["strict_micro"]["f1"],
        "strict_macro_f1": metrics["strict_macro_f1"],
        "strict_document_exact_match": metrics["strict_document_exact_match"],
        "duration_mean_ms": metrics["duration_ms"]["mean"],
        "duration_p95_ms": metrics["duration_ms"]["p95"],
        "total_credits": metrics["credits"]["sum"],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"No rows for {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets-root", type=Path, default=DEFAULT_DATASETS_ROOT)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    for dataset in DATASET_FIELDS:
        for system in ("moi", "landingai"):
            parser.add_argument(
                f"--{dataset}-{system}-run",
                type=Path,
                default=None,
                help=f"Override the {dataset}/{system} run directory",
            )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gold = load_gold(args.datasets_root)
    all_metrics = []
    field_rows = []
    details = []

    for dataset in DATASET_FIELDS:
        excluded = DEFAULT_EXCLUSIONS.get(dataset, {})
        unknown_exclusions = set(excluded) - set(gold[dataset])
        if unknown_exclusions:
            raise RuntimeError(
                f"{dataset} exclusions are not present in gold: "
                f"{sorted(unknown_exclusions)}"
            )
        scored_gold = {
            case_id: fields
            for case_id, fields in gold[dataset].items()
            if case_id not in excluded
        }
        for system in ("moi", "landingai"):
            override = getattr(args, f"{dataset}_{system}_run")
            run_dir = (
                override
                if override is not None
                else args.runs_root / DEFAULT_RUN_DIRS[(dataset, system)]
            )
            if not run_dir.is_dir():
                raise FileNotFoundError(run_dir)
            metrics, current_field_rows, current_details = evaluate_one(
                dataset, system, scored_gold, run_dir
            )
            metrics["original_case_count"] = len(gold[dataset])
            metrics["excluded_case_count"] = len(excluded)
            all_metrics.append(metrics)
            field_rows.extend(current_field_rows)
            details.extend(current_details)

    overall = {}
    for system in ("moi", "landingai"):
        system_metrics = [item for item in all_metrics if item["system"] == system]
        overall[system] = {
            "dataset_mean_normalized_micro_f1": statistics.fmean(
                item["normalized_micro"]["f1"] for item in system_metrics
            ),
            "dataset_mean_normalized_document_exact_match": statistics.fmean(
                item["normalized_document_exact_match"] for item in system_metrics
            ),
            "total_completed": sum(
                item["status_counts"].get("completed", 0) for item in system_metrics
            ),
            "total_cases": sum(item["case_count"] for item in system_metrics),
        }
        overall[system]["overall_success_rate"] = safe_ratio(
            overall[system]["total_completed"], overall[system]["total_cases"]
        )

    summary = {
        "scoring_version": "1.3",
        "primary_metric": "dataset_mean_normalized_micro_f1",
        "exclusions": {
            dataset: [
                {"case_id": case_id, "reason": reason}
                for case_id, reason in cases.items()
            ]
            for dataset, cases in DEFAULT_EXCLUSIONS.items()
        },
        "datasets": all_metrics,
        "overall": overall,
        "notes": [
            "System failures are scored as missing predictions and remain in the denominator.",
            "The three documented VRDU provider-safety failures are excluded from both systems, so VRDU accuracy is compared on the same 97-case subset.",
            "Gold-null/prediction-null fields are correct for field/document accuracy but are not true positives in F1.",
            "JSON null, an empty string, and a whitespace-only string are treated as the same absent scalar value in both gold and predictions.",
            "VRDU normalized matching reproduces the dataset's type-specific match functions.",
            "Kleister normalized matching follows its uppercase MultiLabel-F1 convention.",
            "For Kleister party, both string items and single-key {'value': string} items are treated as compliant equivalent representations.",
            "Unexpected fields never repair or substitute an expected field.",
        ],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "summary.json", summary)
    write_csv(
        args.output_dir / "comparison.csv",
        [comparison_row(item) for item in all_metrics],
    )
    write_csv(args.output_dir / "field_metrics.csv", field_rows)
    with (args.output_dir / "details.jsonl").open("w", encoding="utf-8") as handle:
        for row in details:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    print(json.dumps(overall, ensure_ascii=False, indent=2))
    print(f"Wrote evaluation outputs to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
