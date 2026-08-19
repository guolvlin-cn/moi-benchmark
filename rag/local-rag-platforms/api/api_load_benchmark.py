#!/usr/bin/env python3
"""Compatibility entrypoint for the unified competitor API controller."""

from __future__ import annotations

from pathlib import Path
import sys


PLATFORM_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLATFORM_ROOT.parent
if str(PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(PLATFORM_ROOT))

from api.control import main  # noqa: E402


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if not arguments:
        arguments = ["benchmark"]
    elif arguments[0] == "api-benchmark":
        arguments = arguments[1:]
        if "--dry-run" in arguments:
            arguments = ["dry-run", *(item for item in arguments if item != "--dry-run")]
        else:
            arguments = ["benchmark", *arguments]
    elif "--dry-run" in arguments:
        arguments = ["dry-run", *(item for item in arguments if item != "--dry-run")]
    elif arguments[0] not in {"list", "dry-run", "request", "benchmark"}:
        arguments = ["benchmark", *arguments]
    raise SystemExit(main(arguments))
