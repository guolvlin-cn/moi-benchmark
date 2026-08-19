#!/usr/bin/env python3
"""Retry failed Lenovo Bench judge rows and recompute aggregate metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from lenovo_bench_fastgpt_eval import (
    DEFAULT_DATASET,
    DEFAULT_MINERU,
    FastGPTRun,
    LenovoFixture,
    Progress,
    json_dump,
    score_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--mineru-documents", type=Path, default=DEFAULT_MINERU)
    parser.add_argument("--judge-timeout", type=int, default=300)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    results_path = run_dir / "results.jsonl"
    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["question_id"]: row for row in rows}
    missing = sorted(set(args.question_id) - set(by_id))
    if missing:
        raise SystemExit(f"unknown question ids: {missing}")

    fixture = LenovoFixture(args.dataset_root, args.mineru_documents)
    recovered: list[str] = []
    if args.question_id:
        recovery_dir = run_dir / "recovery" / ("-".join(args.question_id))
        recovery_dir.mkdir(parents=True, exist_ok=True)
        runner = FastGPTRun(args, fixture, recovery_dir, Progress(recovery_dir / "progress.jsonl"))
        for question_id in args.question_id:
            judge = runner.judge_question(by_id[question_id])
            json_dump(recovery_dir / f"{question_id}-judge.json", judge)
            if judge.get("status") != "success":
                raise SystemExit(f"rejudge failed for {question_id}: {judge.get('error')}")
            by_id[question_id]["judge"] = judge
            recovered.append(question_id)

        backup = run_dir / ("results.before-rejudge-" + "-".join(recovered) + ".jsonl")
        if not backup.exists():
            shutil.copy2(results_path, backup)
        encoded = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
        temporary = results_path.with_suffix(".jsonl.tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, results_path)
        results_path.with_suffix(".jsonl.sha256").write_text(
            f"{hashlib.sha256(encoded).hexdigest()}  {results_path.name}\n", encoding="utf-8"
        )

    all_metrics = score_rows(rows, fixture.manifest)
    by_split = {
        split: score_rows([row for row in rows if row["case"]["split"] == split], fixture.manifest)
        for split in ("dev", "pilot", "formal")
    }
    by_type = {
        kind: score_rows([row for row in rows if row["case"]["primary_type"] == kind], fixture.manifest)
        for kind in sorted({row["case"]["primary_type"] for row in rows})
    }
    prior_rejudged: list[str] = []
    if (run_dir / "metrics.json").exists():
        prior_rejudged = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8")).get("rejudged_question_ids", [])
    rejudged_history = sorted(set(prior_rejudged).union(recovered))
    metrics = {
        "protocol": "Lenovo Bench native FastGPT v1",
        "all": all_metrics,
        "by_split": by_split,
        "by_primary_type": by_type,
        "rejudged_question_ids": rejudged_history,
    }
    json_dump(run_dir / "metrics.json", metrics)
    summary = {
        "status": "success",
        "run_id": run_dir.parents[1].name,
        "output": str(run_dir),
        "headline_formal": by_split["formal"],
        "rejudged_question_ids": rejudged_history,
    }
    json_dump(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
