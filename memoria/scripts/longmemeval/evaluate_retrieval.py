#!/usr/bin/env python3
"""Evaluate a frozen LongMemEval-S retrieval JSONL snapshot."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


K_VALUES = (1, 5, 10, 20)


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def latest_records(path: Path) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("question_id"):
                output[str(record["question_id"])] = record
    return output


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def session_ids(record: dict[str, Any], k: int) -> list[str]:
    values: list[str] = []
    for item in record.get("normalized_results", [])[:k]:
        session_id = item.get("original_session_id") or item.get("session_id")
        if session_id:
            values.append(str(session_id))
    return values


def score_record(record: dict[str, Any]) -> dict[str, float]:
    gold = {str(value) for value in record.get("answer_session_ids", [])}
    metrics: dict[str, float] = {}
    ranked_all = session_ids(record, max(K_VALUES))
    reciprocal_rank = 0.0
    for rank, session_id in enumerate(ranked_all, 1):
        if session_id in gold:
            reciprocal_rank = 1.0 / rank
            break
    metrics["mrr"] = reciprocal_rank
    for k in K_VALUES:
        ranked = session_ids(record, k)
        unique = set(ranked)
        hits = gold & unique
        metrics[f"recall@{k}"] = len(hits) / len(gold) if gold else 0.0
        metrics[f"hit@{k}"] = float(bool(hits))
        metrics[f"complete_recall@{k}"] = float(bool(gold) and gold <= unique)
        metrics[f"unique_sessions@{k}"] = float(len(unique))
        metrics[f"duplicate_chunk_rate@{k}"] = (
            (len(ranked) - len(unique)) / len(ranked) if ranked else 0.0
        )
    return metrics


def mean_metrics(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    return {
        key: round(statistics.fmean(row[key] for row in rows), 6)
        for key in rows[0]
    }


def build_report(metrics: dict[str, Any]) -> str:
    operational = metrics["operational"]
    gate = metrics["stability_gate"]
    overall = metrics["evidence_metrics"]["overall_non_abstention"]
    lines = [
        "# LongMemEval-S Retrieval-only report",
        "",
        f"- Selected questions: {operational['selected_questions']}",
        f"- Final successes: {operational['final_successes']}",
        f"- First-pass success rate: {operational['first_pass_success_rate']:.2%}",
        f"- P50/P95 latency: {operational['client_latency_ms']['p50']:.1f} / "
        f"{operational['client_latency_ms']['p95']:.1f} ms",
        f"- Stability gate: **{'PASS' if gate['passed'] else 'FAIL'}**",
        "",
        "## Evidence metrics (non-Abstention)",
        "",
        "| Metric | @1 | @5 | @10 | @20 |",
        "| --- | ---: | ---: | ---: | ---: |",
        "| Recall | "
        + " | ".join(f"{overall[f'recall@{k}']:.4f}" for k in K_VALUES)
        + " |",
        "| Hit | "
        + " | ".join(f"{overall[f'hit@{k}']:.4f}" for k in K_VALUES)
        + " |",
        "| Complete recall | "
        + " | ".join(f"{overall[f'complete_recall@{k}']:.4f}" for k in K_VALUES)
        + " |",
        "",
        f"MRR: {overall.get('mrr', 0.0):.4f}",
        "",
        "## Stability checks",
        "",
    ]
    for name, check in gate["checks"].items():
        lines.append(f"- {'PASS' if check['passed'] else 'FAIL'}: {name} — {check['detail']}")
    lines.extend(["", "## Retrieval paths", ""])
    for path, count in operational["retrieval_paths"].items():
        lines.append(f"- {path}: {count}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--min-first-pass-success", type=float, default=0.99)
    parser.add_argument("--max-p95-ms", type=float, default=30_000.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
    selected_ids = [str(value) for value in manifest["selected_question_ids"]]
    top_k = int(manifest["top_k"])
    records_by_id = latest_records(args.run_dir / "retrieval.jsonl")
    records = [records_by_id[qid] for qid in selected_ids if qid in records_by_id]
    successful = [
        record
        for record in records
        if record.get("status") == "success" and record.get("validation_ok") is True
    ]
    non_abstention = [r for r in successful if not r.get("is_abstention")]
    abstention = [r for r in successful if r.get("is_abstention")]

    overall_rows = [score_record(record) for record in non_abstention]
    category_rows: dict[str, list[dict[str, float]]] = defaultdict(list)
    for record in non_abstention:
        category_rows[str(record.get("question_type"))].append(score_record(record))

    latency = [float(record.get("client_total_ms", 0.0)) for record in successful]
    explain_latency = [
        float((record.get("explain") or {}).get("total_ms", 0.0))
        for record in successful
        if (record.get("explain") or {}).get("total_ms") is not None
    ]
    first_pass_successes = sum(record.get("first_pass_success") is True for record in successful)
    retry_recovered = sum(record.get("first_pass_success") is False for record in successful)
    cross_contamination = sum(
        1
        for record in records
        for error in record.get("validation_errors", [])
        if error.startswith("cross-")
    )
    missing_metadata = sum(
        1
        for record in records
        for error in record.get("validation_errors", [])
        if error.startswith("missing ")
    )
    full_top_k = sum(len(record.get("results", [])) == top_k for record in successful)
    paths = Counter(str((record.get("explain") or {}).get("path", "missing")) for record in successful)

    first_pass_rate = first_pass_successes / len(selected_ids) if selected_ids else 0.0
    p50 = percentile(latency, 0.50) or 0.0
    p95 = percentile(latency, 0.95) or 0.0
    checks = {
        "snapshot_complete": {
            "passed": len(records) == len(selected_ids),
            "detail": f"{len(records)}/{len(selected_ids)} final records",
        },
        "final_success": {
            "passed": len(successful) == len(selected_ids),
            "detail": f"{len(successful)}/{len(selected_ids)} successful",
        },
        "first_pass_success": {
            "passed": first_pass_rate >= args.min_first_pass_success,
            "detail": f"{first_pass_rate:.2%} >= {args.min_first_pass_success:.2%}",
        },
        "no_cross_user_or_question": {
            "passed": cross_contamination == 0,
            "detail": f"{cross_contamination} contaminated results",
        },
        "metadata_complete": {
            "passed": missing_metadata == 0,
            "detail": f"{missing_metadata} missing metadata fields",
        },
        "full_top_k": {
            "passed": full_top_k == len(selected_ids),
            "detail": f"{full_top_k}/{len(selected_ids)} returned Top-{top_k}",
        },
        "latency_p95": {
            "passed": p95 <= args.max_p95_ms,
            "detail": f"{p95:.1f} ms <= {args.max_p95_ms:.1f} ms",
        },
        "retrieval_path_present": {
            "passed": paths.get("none", 0) == 0 and paths.get("missing", 0) == 0,
            "detail": f"paths={dict(paths)}",
        },
    }
    metrics = {
        "operational": {
            "selected_questions": len(selected_ids),
            "snapshot_records": len(records),
            "final_successes": len(successful),
            "final_failures": len(selected_ids) - len(successful),
            "first_pass_successes": first_pass_successes,
            "first_pass_success_rate": first_pass_rate,
            "retry_recovered": retry_recovered,
            "cross_contamination": cross_contamination,
            "missing_metadata": missing_metadata,
            "full_top_k_results": full_top_k,
            "client_latency_ms": {
                "p50": round(p50, 3),
                "p95": round(p95, 3),
                "max": round(max(latency), 3) if latency else None,
            },
            "server_total_ms": {
                "p50": round(percentile(explain_latency, 0.50) or 0.0, 3),
                "p95": round(percentile(explain_latency, 0.95) or 0.0, 3),
            },
            "retrieval_paths": dict(sorted(paths.items())),
        },
        "evidence_metrics": {
            "non_abstention_questions": len(non_abstention),
            "overall_non_abstention": mean_metrics(overall_rows),
            "by_category_non_abstention": {
                category: {"count": len(rows), **mean_metrics(rows)}
                for category, rows in sorted(category_rows.items())
            },
        },
        "abstention_diagnostics": {
            "questions": len(abstention),
            "annotated_session_metrics": mean_metrics(
                [score_record(record) for record in abstention]
            ),
            "note": "Annotated sessions are counterfactual/near-match context, not positive answer evidence.",
        },
        "stability_gate": {
            "passed": all(check["passed"] for check in checks.values()),
            "checks": checks,
        },
    }
    atomic_json(args.run_dir / "metrics.json", metrics)
    (args.run_dir / "report.md").write_text(build_report(metrics), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if metrics["stability_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
