"""Shared frozen-snapshot validation for LongMemEval-S QA evaluations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CATEGORIES = (
    "single-session-user",
    "single-session-assistant",
    "single-session-preference",
    "knowledge-update",
    "temporal-reasoning",
    "multi-session",
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL {path}:{line_number}: {exc}") from exc
    return records


def validate_and_select(
    dataset: list[dict[str, Any]],
    snapshot: list[dict[str, Any]],
    question_ids: list[str] | None,
    limit: int | None,
    top_k: int,
) -> list[dict[str, Any]]:
    dataset_by_id = {row["question_id"]: row for row in dataset}
    snapshot_by_id: dict[str, dict[str, Any]] = {}
    for record in snapshot:
        question_id = record.get("question_id")
        if question_id in snapshot_by_id:
            raise ValueError(f"Duplicate snapshot question_id: {question_id}")
        snapshot_by_id[question_id] = record
    if len(dataset_by_id) != len(dataset):
        raise ValueError("Dataset contains duplicate question IDs")
    if set(snapshot_by_id) != set(dataset_by_id):
        missing = sorted(set(dataset_by_id) - set(snapshot_by_id))
        extra = sorted(set(snapshot_by_id) - set(dataset_by_id))
        raise ValueError(
            f"Snapshot/dataset ID mismatch: missing={missing[:3]}, extra={extra[:3]}"
        )
    invalid_snapshot = [
        question_id
        for question_id, record in snapshot_by_id.items()
        if record.get("status") != "success"
        or not record.get("validation_ok")
        or len(record.get("results", [])) != 20
    ]
    if invalid_snapshot:
        raise ValueError(
            "Frozen snapshot has non-success, invalid, or non-Top-20 records: "
            f"{invalid_snapshot[:10]}"
        )

    selected_ids = question_ids or [row["question_id"] for row in snapshot]
    if limit is not None:
        selected_ids = selected_ids[:limit]
    if not selected_ids:
        raise ValueError("No questions selected")
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("Selection contains duplicate question IDs")
    unknown = [
        question_id for question_id in selected_ids if question_id not in snapshot_by_id
    ]
    if unknown:
        raise ValueError(f"Selection IDs absent from snapshot: {unknown}")

    selected = []
    for question_id in selected_ids:
        retrieval = snapshot_by_id[question_id]
        source = dataset_by_id[question_id]
        errors = []
        if retrieval.get("status") != "success":
            errors.append(f"status={retrieval.get('status')!r}")
        if not retrieval.get("validation_ok"):
            errors.append("validation_ok is false")
        if len(retrieval.get("results", [])) < top_k:
            errors.append(f"only {len(retrieval.get('results', []))} results")
        for field in ("question", "question_type"):
            if retrieval.get(field) != source.get(field):
                errors.append(f"{field} differs from dataset")
        expected_abs = question_id.endswith("_abs")
        if bool(retrieval.get("is_abstention")) != expected_abs:
            errors.append("is_abstention differs from question_id")
        if errors:
            raise ValueError(f"Invalid snapshot record {question_id}: {errors}")
        # Preserve the date frozen by the retrieval track; the Oracle dataset is
        # still the authority for the reference answer and question metadata.
        selected.append(
            {
                **source,
                "question_date": retrieval["question_date"],
                "oracle_question_date": source["question_date"],
                "results": retrieval["results"],
            }
        )
    return selected
