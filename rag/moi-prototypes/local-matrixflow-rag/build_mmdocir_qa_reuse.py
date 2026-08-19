#!/usr/bin/env python3
"""Select reusable MMDocIR QA rows without mixing generator routes.

The previous full attempts used Qwen for every question. This adapter keeps
only successful rows whose released MMDocIR evidence type is multimodal; the
new split-model runner regenerates all text-only rows with dsv4f.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def route(evidence_type: Any) -> str:
    value = str(evidence_type or "").strip().lower()
    if value in {"multimodal-t", "multimodal-f"}:
        return "multimodal"
    if any(marker in value for marker in ("chart", "figure", "table", "image")):
        return "multimodal"
    return "text"


def read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            rows.append(value)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    selected: dict[str, dict[str, Any]] = {}
    for path in args.input:
        for row in read_rows(path):
            if str(row.get("status", "")) != "ok":
                continue
            case = row.get("case")
            if not isinstance(case, dict):
                continue
            question_id = str(case.get("id", "")).strip()
            if not question_id or question_id in selected:
                continue
            metadata = case.get("metadata") if isinstance(case.get("metadata"), dict) else {}
            if route(metadata.get("question_type", "")) != "multimodal":
                continue
            if str(row.get("generation_model", "")).strip() != "qwen3.5-35b-a3b":
                continue
            selected[question_id] = row

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in selected.values():
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(json.dumps({
        "reusable_rows": len(selected),
        "output": str(args.output),
        "route": "multimodal",
        "source_files": [str(path) for path in args.input],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
