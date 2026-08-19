#!/usr/bin/env python3
"""Merge the completed DocBench remainder into the prior 906-question run."""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks import moi_current_corpus_eval as runner
from benchmarks import moi_rag_benchmark as legacy


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    os.replace(temporary, path)


def write_json(path: Path, value: Any) -> None:
    runner.write_json(path, value)


def latest_successes(incremental_run: Path, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Choose the latest successful durable row for every incremental case."""
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    result_root = incremental_run / "datasets" / "docbench" / "results"
    for path in sorted(result_root.rglob("results.jsonl")):
        for row in read_jsonl(path):
            case_id = str((row.get("case") or {}).get("id") or "")
            if case_id:
                history[case_id].append(row)
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for case in questions:
        case_id = str(case["id"])
        attempts = history.get(case_id, [])
        success = next((row for row in reversed(attempts) if row.get("status") == "ok"), None)
        if success is None:
            missing.append(case_id)
            if attempts:
                selected.append(attempts[-1])
            continue
        selected.append(success)
    if missing:
        raise RuntimeError(f"incremental DocBench cases without a successful result: {missing[:10]}")
    return selected


def merged_judgements(
    out: Path,
    old_run: Path,
    incremental_run: Path,
    incremental_rows: list[dict[str, Any]],
    full_questions: list[dict[str, Any]],
    config: Path,
    judge_workers: int,
) -> list[dict[str, Any]]:
    old_path = old_run / "datasets" / "docbench" / "judgements.jsonl"
    old_rows = read_jsonl(old_path) if old_path.is_file() else []
    new_path = incremental_run / "datasets" / "docbench" / "judgements.jsonl"
    new_rows = read_jsonl(new_path) if new_path.is_file() else []
    judge_path = out / "datasets" / "docbench" / "judgements.jsonl"
    # Preserve a previous merge's successful judge records when this script is
    # rerun.  On the first pass seed the new-question audit, including failed
    # records; the runner retries failed prior judgements.
    if judge_path.is_file():
        seed_rows = read_jsonl(judge_path)
    else:
        seed_rows = new_rows
    write_jsonl(judge_path, seed_rows)
    cfg = json.loads(config.read_text(encoding="utf-8"))
    cfg["generation"]["retry_max_attempts"] = 1
    cfg["generation"].pop("fallback", None)
    for _ in range(3):
        runner.failfast_docbench_judge(
            out,
            incremental_rows,
            runner.load_environment(),
            cfg,
            max(1, judge_workers),
        )
        current = read_jsonl(judge_path)
        incremental_ids = {str((row.get("case") or {}).get("id")) for row in incremental_rows}
        if not any(str(row.get("id")) in incremental_ids and row.get("status") == "failed" for row in current):
            break
    final_new = read_jsonl(judge_path)
    by_id = {str(row.get("id")): row for row in old_rows}
    by_id.update({str(row.get("id")): row for row in final_new})
    merged: list[dict[str, Any]] = []
    for case in full_questions:
        record = by_id.get(str(case["id"]))
        if record is not None:
            merged.append(record)
    write_jsonl(judge_path, merged)
    return merged


def correctness_metrics(judgements: list[dict[str, Any]], cases_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    scores: list[int] = []
    by_type: dict[str, list[int]] = defaultdict(list)
    failed = 0
    for record in judgements:
        if record.get("status") == "ok" and isinstance(record.get("score"), int):
            score = int(record["score"])
            scores.append(score)
            question_type = str((cases_by_id.get(str(record.get("id")), {}).get("metadata") or {}).get("question_type") or "unknown")
            by_type[question_type].append(score)
        elif record.get("status") == "failed":
            failed += 1
    return {
        "correctness": sum(scores) / len(scores) if scores else None,
        "valid_n": len(scores),
        "failed_n": failed,
        "correctness_by_type": {key: sum(values) / len(values) for key, values in sorted(by_type.items())},
        "raw_path": "",
    }


def latency_summary(values: list[float]) -> dict[str, Any]:
    values = sorted(values)
    if not values:
        return {"mean": None, "p50": None, "p95": None, "n": 0}

    def percentile(fraction: float) -> float:
        position = (len(values) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return values[lower]
        return values[lower] + (values[upper] - values[lower]) * (position - lower)

    return {
        "mean": sum(values) / len(values),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "n": len(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-run", type=Path, required=True)
    parser.add_argument("--incremental-run", type=Path, required=True)
    parser.add_argument("--full-questions", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--judge-workers", type=int, default=2)
    args = parser.parse_args()

    old_run = args.old_run.resolve()
    incremental_run = args.incremental_run.resolve()
    full_questions = read_jsonl(args.full_questions.resolve())
    old_questions = read_jsonl(old_run / "datasets" / "docbench" / "questions.jsonl")
    incremental_questions = read_jsonl(incremental_run / "datasets" / "docbench" / "questions.jsonl")
    if len(full_questions) != 1102 or len(old_questions) != 906 or len(incremental_questions) != 196:
        raise RuntimeError("unexpected DocBench question counts; refusing to merge")
    full_ids = {str(row["id"]) for row in full_questions}
    if {str(row["id"]) for row in old_questions} | {str(row["id"]) for row in incremental_questions} != full_ids:
        raise RuntimeError("old and incremental question IDs do not partition the official 1102 questions")

    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out.resolve()
    old_rows = read_jsonl(old_run / "datasets" / "docbench" / "combined-results.jsonl")
    incremental_rows = latest_successes(incremental_run, incremental_questions)
    old_by_id = {str((row.get("case") or {}).get("id")): row for row in old_rows}
    new_by_id = {str((row.get("case") or {}).get("id")): row for row in incremental_rows}
    combined = []
    for case in full_questions:
        case_id = str(case["id"])
        row = old_by_id.get(case_id) or new_by_id.get(case_id)
        if row is None:
            raise RuntimeError(f"missing merged result for {case_id}")
        combined.append(row)

    write_jsonl(out / "datasets" / "docbench" / "questions.jsonl", full_questions)
    write_jsonl(out / "datasets" / "docbench" / "incremental-results-196.jsonl", incremental_rows)
    write_jsonl(out / "datasets" / "docbench" / "combined-results.jsonl", combined)
    write_jsonl(out / "datasets" / "docbench" / "recovered-results.jsonl", incremental_rows)
    (out / "configs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.config.resolve(), out / "configs" / "config.docbench.maas.json")

    judgements = merged_judgements(
        out,
        old_run,
        incremental_run,
        incremental_rows,
        full_questions,
        args.config.resolve(),
        args.judge_workers,
    )
    cases_by_id = {str(case["id"]): case for case in full_questions}
    metric = runner.metrics("docbench", combined)
    metric["correctness"] = correctness_metrics(judgements, cases_by_id)
    metric["correctness"]["raw_path"] = str(out / "datasets" / "docbench" / "judgements.jsonl")
    successful_rows = [row for row in combined if row.get("status") == "ok"]
    retrieval_values = [
        float(row["retrieval_latency_ms"])
        for row in successful_rows
        if isinstance(row.get("retrieval_latency_ms"), (int, float))
    ]
    generation_values = [
        float(row["generation_latency_ms"])
        for row in successful_rows
        if isinstance(row.get("generation_latency_ms"), (int, float))
    ]
    e2e_values = [
        float(row["retrieval_latency_ms"]) + float(row["generation_latency_ms"])
        for row in successful_rows
        if isinstance(row.get("retrieval_latency_ms"), (int, float))
        and isinstance(row.get("generation_latency_ms"), (int, float))
    ]
    metric["successful_retrieval_latency_ms"] = latency_summary(retrieval_values)
    metric["generation_latency_ms"] = latency_summary(generation_values)
    metric["e2e_latency_ms"] = latency_summary(e2e_values)
    qa_ledger = runner.write_qa_ledger(out, "docbench", combined)
    query_failed_n = sum(row.get("status") != "ok" for row in combined)
    judge_failed_n = sum(row.get("status") == "failed" for row in judgements)
    summary = {
        "dataset": "docbench",
        "rows": len(combined),
        "planned": len(full_questions),
        "incremental_rows": len(incremental_rows),
        "query_failed_n": query_failed_n,
        "judge_failed_n": judge_failed_n,
        "e2e_latency_ms": metric["e2e_latency_ms"],
        "results": str(out / "datasets" / "docbench" / "combined-results.jsonl"),
        "qa_ledger": str(qa_ledger),
        "error_policy": "record_and_continue",
        "protocol": "CURRENT_CORPUS_ADAPTED",
        "fulltext_route": "LIKE fallback because MatrixOne FULLTEXT index was unavailable",
        "vector_route": "exact scan because IVFFLAT rebuild was skipped",
    }
    write_json(out / "datasets" / "docbench" / "metrics.json", metric)
    write_json(out / "datasets" / "docbench" / "summary.json", summary)
    write_json(out / "datasets" / "docbench" / "report.json", {"dataset": "docbench", "metrics": metric, "summary": str(out / "datasets" / "docbench" / "summary.json")})
    write_json(out / "merge-manifest.json", {
        "dataset": "docbench",
        "official_questions": len(full_questions),
        "prior_questions": len(old_questions),
        "incremental_questions": len(incremental_questions),
        "old_run": str(old_run),
        "incremental_run": str(incremental_run),
        "incremental_results_selection": "latest successful durable row per question ID",
        "judge_selection": "prior 906 judgements plus rejudged incremental 196; prior failed judge records retained",
        "protocol": "CURRENT_CORPUS_ADAPTED",
        "fulltext_route": "LIKE fallback because MatrixOne FULLTEXT index was unavailable",
        "vector_route": "exact scan because IVFFLAT rebuild was skipped",
        "query_failed_n": query_failed_n,
        "judge_failed_n": judge_failed_n,
    })
    print(json.dumps({"out": str(out), "rows": len(combined), "query_failed_n": query_failed_n, "judge_failed_n": judge_failed_n, "correctness": metric["correctness"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
