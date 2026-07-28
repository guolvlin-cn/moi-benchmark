#!/usr/bin/env python3
"""Run the configured Matrixflow extraction workflow over Kleister-NDA."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BASE_RUNNER = SCRIPT_DIR / "run_matrixflow_sroie_extraction.py"
INPUT_DIR = SCRIPT_DIR.parent / "datasets" / "Kleister-NDA" / "documents"
RUN_DIR = SCRIPT_DIR.parent / "runs" / "matrixflow-kleister-nda-schema-fixed"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "effective_date": {
            "type": "string",
            "description": (
                "The date on which the NDA or confidentiality agreement becomes "
                "effective, normalized to YYYY-MM-DD. Return an empty string when "
                "absent or uncertain; do not substitute a signature or filing date."
            ),
        },
        "jurisdiction": {
            "type": "string",
            "description": (
                "The country, state, or legal jurisdiction whose laws govern the "
                "agreement. Return an empty string when absent or uncertain; do not "
                "guess from an address, venue, or incorporation location."
            ),
        },
        "party": {
            "type": "array",
            "description": (
                "All contracting parties to the agreement, each listed once. "
                "Return an empty array when no party can be identified; do not include "
                "signers, representatives, advisers, or other non-parties."
            ),
            "items": {"type": "string"},
        },
        "term": {
            "type": "string",
            "description": (
                "The confidentiality-obligation duration normalized as number_unit, "
                "for example 1_year or 18_months. Return an empty string when absent "
                "or uncertain; do not guess."
            ),
        },
    },
    "required": ["effective_date", "jurisdiction", "party", "term"],
}


def main() -> None:
    values = json.dumps({"extract_schema": SCHEMA}, ensure_ascii=False)
    argv = [
        sys.executable,
        str(BASE_RUNNER),
        "--input-dir",
        str(INPUT_DIR),
        "--run-dir",
        str(RUN_DIR),
        "--values-json",
        values,
        *sys.argv[1:],
    ]
    os.execv(sys.executable, argv)


if __name__ == "__main__":
    main()
