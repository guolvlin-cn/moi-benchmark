#!/usr/bin/env python3
"""Merge and summarize DocBench failed-case recovery runs without overwriting history."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def case_type(question: dict) -> str:
    return str((question.get("metadata") or {}).get("question_type") or "unknown")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-root", type=Path, required=True)
    parser.add_argument("--recovery-root", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    historical = args.historical_root.expanduser().resolve()
    recovery_roots = [path.expanduser().resolve() for path in args.recovery_root]
    output = args.output_root.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    questions = read_jsonl(historical / "questions.jsonl")
    question_map = {str(row.get("id")): row for row in questions}
    historical_rows = read_jsonl(historical / "combined-results.jsonl")
    historical_judgements = read_jsonl(historical / "judgements.jsonl")
    rows_by_id = {str((row.get("case") or {}).get("id")): row for row in historical_rows}
    judgements_by_id = {str(row.get("id")): row for row in historical_judgements}

    failed_ids = {
        case_id for case_id, row in rows_by_id.items() if row.get("status") != "ok"
    } | {
        case_id for case_id, row in judgements_by_id.items() if row.get("status") == "failed"
    }
    recovery_rows: dict[str, dict] = {}
    recovery_judgements: dict[str, dict] = {}
    recovery_sources: dict[str, list[str]] = defaultdict(list)
    for root in recovery_roots:
        dataset = root / "datasets" / "docbench"
        run_id = root.name
        for row in read_jsonl(dataset / "combined-results.jsonl"):
            case_id = str((row.get("case") or {}).get("id"))
            recovery_sources[case_id].append(run_id)
            if row.get("status") == "ok" or case_id not in recovery_rows:
                recovery_rows[case_id] = row
        for row in read_jsonl(dataset / "judgements.jsonl"):
            case_id = str(row.get("id"))
            if row.get("status") == "ok" or case_id not in recovery_judgements:
                recovery_judgements[case_id] = row

    final_rows = dict(rows_by_id)
    final_judgements = dict(judgements_by_id)
    ledger: list[dict] = []
    for case_id in sorted(failed_ids, key=lambda value: [int(part) if part.isdigit() else part for part in value.replace("docbench-", "").replace("-", " ").split()]):
        question = question_map[case_id]
        historical_row = rows_by_id.get(case_id, {})
        historical_judge = judgements_by_id.get(case_id, {})
        recovered_row = recovery_rows.get(case_id, {})
        recovered_judge = recovery_judgements.get(case_id, {})
        if recovered_row.get("status") == "ok":
            final_rows[case_id] = recovered_row
        if recovered_judge.get("status") == "ok":
            final_judgements[case_id] = recovered_judge
        final_row = final_rows.get(case_id, {})
        final_judge = final_judgements.get(case_id, {})
        ledger.append({
            "id": case_id,
            "question_type": case_type(question),
            "historical_query_status": historical_row.get("status"),
            "historical_query_error": historical_row.get("error"),
            "historical_judge_status": historical_judge.get("status"),
            "historical_judge_error": historical_judge.get("error"),
            "recovery_runs": recovery_sources.get(case_id, []),
            "recovered_query_status": recovered_row.get("status"),
            "recovered_query_error": recovered_row.get("error"),
            "recovered_judge_status": recovered_judge.get("status"),
            "recovered_judge_score": recovered_judge.get("score"),
            "final_query_status": final_row.get("status"),
            "final_judge_status": final_judge.get("status"),
            "final_judge_score": final_judge.get("score"),
        })

    final_valid_judgements = [row for row in final_judgements.values() if row.get("status") == "ok"]
    by_type: dict[str, dict[str, int | float | None]] = {}
    for question in questions:
        case_id = str(question.get("id"))
        typ = case_type(question)
        bucket = by_type.setdefault(typ, {"total": 0, "query_ok": 0, "query_failed": 0, "judge_valid": 0, "score_sum": 0})
        bucket["total"] = int(bucket["total"]) + 1
        if final_rows.get(case_id, {}).get("status") == "ok":
            bucket["query_ok"] = int(bucket["query_ok"]) + 1
        else:
            bucket["query_failed"] = int(bucket["query_failed"]) + 1
        judge = final_judgements.get(case_id, {})
        if judge.get("status") == "ok":
            bucket["judge_valid"] = int(bucket["judge_valid"]) + 1
            bucket["score_sum"] = int(bucket["score_sum"]) + int(judge.get("score", 0))
    for bucket in by_type.values():
        valid = int(bucket["judge_valid"])
        total = int(bucket["total"])
        score_sum = int(bucket["score_sum"])
        bucket["judge_rate"] = score_sum / valid if valid else None
        bucket["full_denominator_rate"] = score_sum / total if total else None

    remaining = [row for row in ledger if row["final_query_status"] != "ok"]
    summary = {
        "dataset": "docbench",
        "historical_root": str(historical),
        "recovery_roots": [str(path) for path in recovery_roots],
        "questions": len(questions),
        "historical_query_failed_n": sum(row.get("status") != "ok" for row in rows_by_id.values()),
        "historical_judge_failed_n": sum(row.get("status") == "failed" for row in judgements_by_id.values()),
        "failed_case_n": len(failed_ids),
        "recovered_query_ok_n": sum(row.get("final_query_status") == "ok" for row in ledger),
        "remaining_query_failed_n": len(remaining),
        "final_query_ok_n": sum(row.get("status") == "ok" for row in final_rows.values()),
        "final_judge_valid_n": len(final_valid_judgements),
        "final_judge_failed_n": sum(row.get("status") == "failed" for row in final_judgements.values()),
        "final_judge_score_sum": sum(int(row.get("score", 0)) for row in final_valid_judgements),
        "final_correctness": (sum(int(row.get("score", 0)) for row in final_valid_judgements) / len(final_valid_judgements) if final_valid_judgements else None),
        "final_full_run_correctness": (sum(int(row.get("score", 0)) for row in final_valid_judgements) / len(questions) if questions else None),
        "remaining_failure_ids": [row["id"] for row in remaining],
        "remaining_failure_types": {typ: sum(row["question_type"] == typ for row in remaining) for typ in sorted({row["question_type"] for row in remaining})},
        "by_question_type": by_type,
        "protocol": "CURRENT_CORPUS_ADAPTED; generation-enabled failure-case recovery; LIKE full-text fallback; vector exact scan; retries are recovery audit and do not replace historical primary result",
    }
    (output / "recovery-ledger.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ledger),
        encoding="utf-8",
    )
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
