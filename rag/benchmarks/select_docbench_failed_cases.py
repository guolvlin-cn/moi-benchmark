#!/usr/bin/env python3
"""Select the failed DocBench cases from a preserved historical run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.historical_root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    questions = read_jsonl(root / "questions.jsonl")
    results = read_jsonl(root / "combined-results.jsonl")
    judgements = read_jsonl(root / "judgements.jsonl")

    query_failure_ids = {
        str((row.get("case") or {}).get("id"))
        for row in results
        if row.get("status") != "ok"
    }
    judge_failure_ids = {
        str(row.get("id"))
        for row in judgements
        if row.get("status") == "failed"
    }
    selected_ids = query_failure_ids | judge_failure_ids
    selected = [row for row in questions if str(row.get("id")) in selected_ids]
    seen = {str(row.get("id")) for row in selected}
    missing = sorted(selected_ids - seen)
    if missing:
        raise SystemExit(f"failed IDs missing from questions.jsonl: {missing[:10]}")
    if not selected:
        raise SystemExit("no failed DocBench cases found")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )
    manifest = {
        "source": str(root),
        "questions_source": str(root / "questions.jsonl"),
        "results_source": str(root / "combined-results.jsonl"),
        "judgements_source": str(root / "judgements.jsonl"),
        "selected_questions": len(selected),
        "query_failure_n": len(query_failure_ids),
        "judge_failure_n": len(judge_failure_ids),
        "overlap_n": len(query_failure_ids & judge_failure_ids),
        "query_failure_ids": sorted(query_failure_ids),
        "judge_failure_ids": sorted(judge_failure_ids),
        "selection_policy": "union of historical query failures and judge failures; preserve original question order",
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output),
        "selected_questions": len(selected),
        "query_failure_n": len(query_failure_ids),
        "judge_failure_n": len(judge_failure_ids),
        "overlap_n": len(query_failure_ids & judge_failure_ids),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
