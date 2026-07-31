#!/usr/bin/env python3
"""Compatibility launcher for the MatrixFlow product-RAG Go benchmark."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def load_dotenv(path: Path, environ: dict[str, str]) -> None:
    """Load simple KEY=VALUE entries without overriding explicit environment values."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        environ.setdefault(key, value)


def main() -> None:
    root = Path(__file__).resolve().parent
    environment = os.environ.copy()
    load_dotenv(root / ".env", environment)
    completed = subprocess.run(
        ["go", "run", ".", *sys.argv[1:]],
        cwd=root,
        env=environment,
        check=False,
    )
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
