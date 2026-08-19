from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            validate_case(row, path=str(path), line_number=line_number)
            case_id = str(row["id"])
            if case_id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate id {case_id!r}")
            seen.add(case_id)
            rows.append(row)
    if not rows:
        raise ValueError(f"{path}: dataset is empty")
    return rows


def validate_case(row: dict[str, Any], *, path: str, line_number: int) -> None:
    prefix = f"{path}:{line_number}"
    for field in ("id", "question"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"{prefix}: {field!r} must be a non-empty string")
    if "references" in row and not (
        isinstance(row["references"], list)
        and all(isinstance(value, str) for value in row["references"])
    ):
        raise ValueError(f"{prefix}: 'references' must be a list of strings")
    for field in (
        "required_keywords",
        "refusal_keywords",
        "gold_document_ids",
        "gold_document_names",
        "gold_evidence",
    ):
        if field in row and not (
            isinstance(row[field], list)
            and all(isinstance(value, str) for value in row[field])
        ):
            raise ValueError(f"{prefix}: {field!r} must be a list of strings")
    if "answerable" in row and not isinstance(row["answerable"], bool):
        raise ValueError(f"{prefix}: 'answerable' must be a boolean")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_result_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]

