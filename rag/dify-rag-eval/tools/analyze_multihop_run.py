#!/usr/bin/env python3
"""Create an auditable metrics bundle for a 20x2 MultiHop-RAG Chatflow run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median, mean

from dify_rag_eval.metrics import normalize_text, token_f1, tokens


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ratio(numerator: int, denominator: int, **extra: object) -> dict[str, object]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
        **extra,
    }


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(q * len(values)) - 1)]


def reference_token_recall(answer: str, reference: str) -> float:
    expected = tokens(reference)
    if not expected:
        return float(not tokens(answer))
    predicted = Counter(tokens(answer))
    gold = Counter(expected)
    return sum((predicted & gold).values()) / sum(gold.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--ingest-state", required=True, type=Path)
    parser.add_argument("--direct-summary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in args.results.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases = {
        row["id"]: row
        for row in (
            json.loads(line)
            for line in args.questions.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    judged = []
    for row in rows:
        case = row["case"]
        answer = str(row.get("answer") or "")
        refs = case.get("references") or []
        exact = max(
            [float(normalize_text(answer) == normalize_text(ref)) for ref in refs],
            default=0.0,
        )
        f1 = max([token_f1(answer, ref) for ref in refs], default=0.0)
        token_recall = max(
            [reference_token_recall(answer, ref) for ref in refs], default=0.0
        )
        refusal_terms = case.get("refusal_keywords") or []
        lowered = answer.lower()
        refusal = any(term.lower() in lowered for term in refusal_terms)
        contexts = row.get("contexts") or []
        context_text = [normalize_text(str(item.get("content") or "")) for item in contexts]
        evidence = [normalize_text(value) for value in case.get("gold_evidence") or []]
        evidence_hits = sum(
            any(item and item in context for context in context_text)
            for item in evidence
        )
        judged.append(
            {
                "attempt_id": row.get("attempt_id"),
                "question_id": case["id"],
                "question_type": case["question_type"],
                "repeat": row["repeat"],
                "available": row.get("error") is None,
                "nonempty_answer": bool(answer.strip()),
                "nonempty_context": bool(contexts),
                "exact_match": exact,
                "token_f1": f1,
                "reference_token_recall": token_recall,
                "null_refusal_success": (
                    refusal if case["question_type"] == "null_query" else None
                ),
                "evidence_hits": evidence_hits,
                "evidence_total": len(evidence),
                "latency_seconds": row.get("latency_seconds"),
                "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            }
        )

    by_question: dict[str, list[dict]] = {}
    for item in judged:
        by_question.setdefault(item["question_id"], []).append(item)
    exact_stable = 0
    pair_f1: list[float] = []
    paired = 0
    for question_id, attempts in by_question.items():
        attempts.sort(key=lambda item: item["repeat"])
        if len(attempts) != 2:
            continue
        paired += 1
        raw = [row for row in rows if row["case"]["id"] == question_id]
        raw.sort(key=lambda row: row["repeat"])
        a1, a2 = (str(item.get("answer") or "") for item in raw)
        exact_stable += normalize_text(a1) == normalize_text(a2)
        pair_f1.append(token_f1(a1, a2))

    successful = [item for item in judged if item["available"]]
    answerable = [
        item for item in judged if item["question_type"] != "null_query"
    ]
    nulls = [item for item in judged if item["question_type"] == "null_query"]
    evidence_hits = sum(item["evidence_hits"] for item in judged)
    evidence_total = sum(item["evidence_total"] for item in judged)
    latencies = [
        float(item["latency_seconds"])
        for item in judged
        if isinstance(item["latency_seconds"], (int, float))
    ]
    summary = {
        "scope": {
            "questions": len(cases),
            "attempts_expected": len(cases) * 2,
            "attempts_observed": len(rows),
            "question_type_counts": Counter(
                case["question_type"] for case in cases.values()
            ),
        },
        "availability": ratio(
            sum(item["available"] for item in judged), len(judged)
        ),
        "nonempty_answer": ratio(
            sum(item["nonempty_answer"] for item in judged), len(judged)
        ),
        "nonempty_chatflow_trace": ratio(
            sum(item["nonempty_context"] for item in judged), len(judged)
        ),
        "answer_correctness": {
            "normalized_exact_match": ratio(
                int(sum(item["exact_match"] for item in answerable)),
                len(answerable),
                population="answerable attempts",
            ),
            "mean_token_f1": (
                mean(item["token_f1"] for item in answerable) if answerable else None
            ),
            "mean_reference_token_recall": (
                mean(item["reference_token_recall"] for item in answerable)
                if answerable
                else None
            ),
        },
        "chatflow_evidence_recall_at_k": ratio(
            evidence_hits,
            evidence_total,
            match_rule="normalized frozen evidence span exact substring in returned context",
        ),
        "null_query_refusal_success": ratio(
            sum(bool(item["null_refusal_success"]) for item in nulls), len(nulls)
        ),
        "latency_seconds": {
            "p50": median(latencies) if latencies else None,
            "p95": percentile(latencies, 0.95),
        },
        "repeat_stability": {
            "paired_questions": paired,
            "normalized_exact_answer_pairs": ratio(exact_stable, paired),
            "mean_pairwise_token_f1": mean(pair_f1) if pair_f1 else None,
        },
        "citations": {
            "value": None,
            "reason": "NO_SUBMITTED_CITATION",
        },
        "chatflow_trace": {
            "status": "AVAILABLE" if any(item["nonempty_context"] for item in judged) else "UNAVAILABLE",
            "reason": None if any(item["nonempty_context"] for item in judged) else "TRACE_UNAVAILABLE",
        },
        "hashes": {
            "questions_sha256": sha256_file(args.questions),
            "config_sha256": sha256_file(args.config),
            "ingest_state_sha256": sha256_file(args.ingest_state),
            "chatflow_results_sha256": sha256_file(args.results),
            "direct_retrieval_summary_sha256": sha256_file(args.direct_summary),
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    judged_path = args.output / "judgements.jsonl"
    judged_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in judged),
        encoding="utf-8",
    )
    summary["hashes"]["judgements_sha256"] = sha256_file(judged_path)
    (args.output / "metrics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
