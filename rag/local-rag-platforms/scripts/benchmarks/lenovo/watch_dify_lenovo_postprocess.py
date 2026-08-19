#!/usr/bin/env python3
"""Wait for the Dify Lenovo QA ledger, then run the post-score once."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
RUN_ROOT = ROOT / "runs/dify-lenovo-bench-20260813/dify-local-lenovo-bench-formal-v1"
PACKAGE = ROOT / "runs/dify-lenovo-bench-20260813/lenovo-bench-formal-v1/package"
PAGES = ROOT / "runs/dify-lenovo-bench-20260813/lenovo-bench-formal-v1/audit/prepared-pages.jsonl"


def qa_terminal_count() -> int:
    ledger = RUN_ROOT / "terminal-ledger.jsonl"
    if not ledger.is_file():
        return 0
    return sum('"stage": "qa"' in line for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines())


def main() -> int:
    log = RUN_ROOT.parent / "lenovo-bench-formal-v1/logs/postprocess-watch-20260813.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        while True:
            count = qa_terminal_count()
            handle.write(f"watch qa_terminal_rows={count}\n")
            handle.flush()
            if count >= 60:
                command = [
                    "python3",
                    str(ROOT / "local-rag-platforms/scripts/benchmarks/lenovo/score_dify_lenovo_bench.py"),
                    "--run-root",
                    str(RUN_ROOT),
                    "--package",
                    str(PACKAGE),
                    "--audit-pages",
                    str(PAGES),
                ]
                completed = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, check=False)
                return completed.returncode
            time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
