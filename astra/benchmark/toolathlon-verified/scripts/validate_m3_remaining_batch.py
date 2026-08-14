#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from astra.runners.toolathlon_verified.m3_batch import main


if __name__ == "__main__":
    raise SystemExit(main(["validate", *sys.argv[1:]]))
