#!/usr/bin/env python3
"""Run the configured Matrixflow extraction workflow over VRDU Registration."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BASE_RUNNER = SCRIPT_DIR / "run_matrixflow_sroie_extraction.py"
INPUT_DIR = (
    SCRIPT_DIR.parent
    / "datasets"
    / "VRDU"
    / "registration-form"
    / "main"
    / "pdfs"
)
RUN_DIR = SCRIPT_DIR.parent / "runs" / "matrixflow-vrdu-registration-schema-fixed"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "file_date": {
            "type": "string",
            "description": (
                "The filing or registration date shown on the document. "
                "Return an empty string when the field is absent or uncertain; do not guess."
            ),
        },
        "foreign_principle_name": {
            "type": "string",
            "description": (
                "The foreign principal represented by the registrant. Keep this exact "
                "field-name spelling. Return an empty string when absent or uncertain; "
                "do not confuse it with the registrant."
            ),
        },
        "registrant_name": {
            "type": "string",
            "description": (
                "The official name of the registrant individual or organization. "
                "Return an empty string when absent or uncertain."
            ),
        },
        "registration_num": {
            "type": "string",
            "description": (
                "The registration number as text, preserving leading zeros. "
                "Return an empty string when absent or uncertain."
            ),
        },
        "signer_name": {
            "type": "string",
            "description": (
                "The name of the person who signed or executed the document. "
                "Return an empty string when absent or uncertain."
            ),
        },
        "signer_title": {
            "type": "string",
            "description": (
                "The signer's title, position, capacity, or role. Return an empty "
                "string when absent or uncertain; do not return the signer name."
            ),
        },
    },
    "required": [
        "file_date",
        "foreign_principle_name",
        "registrant_name",
        "registration_num",
        "signer_name",
        "signer_title",
    ],
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
