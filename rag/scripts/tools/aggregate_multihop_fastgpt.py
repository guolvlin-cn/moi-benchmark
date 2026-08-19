#!/usr/bin/env python3
"""Aggregate a FastGPT MultiHop-RAG native run with explicit metric contracts.

The official retrieval scorer matches Gold evidence sentences against returned
chunk text and excludes null queries.  This script preserves that score as an
"official-compatible" diagnostic, while also reporting document-level metrics
from the stable sourceName identifiers emitted by FastGPT.  The native runner
deduplicates results by source document, so the former is not claimed as an
exact reproduction of the paper's 256-token Top-20/rerank setup.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


VALID = {"SUCCESS", "EMPTY"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def norm_id(value: Any) -> str:
    return Path(str(value or "").strip().casefold()).name


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).casefold())


def lexical_tokens(value: Any) -> list[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", unicodedata.normalize("NFKC", str(value or "")).casefold())


def token_f1(prediction: str, reference: str) -> float:
    predicted = Counter(lexical_tokens(prediction))
    expected = Counter(lexical_tokens(reference))
    if not expected:
        return 0.0
    if not predicted:
        return 0.0
    overlap = sum((predicted & expected).values())
    if not overlap:
        return 0.0
    precision = overlap / sum(predicted.values())
    recall = overlap / sum(expected.values())
    return 2 * precision * recall / (precision + recall)


def answer_from_row(row: Mapping[str, Any] | None) -> str:
    if not row:
        return ""
    for key in ("answer", "generated_answer", "prediction", "output", "content"):
        if isinstance(row.get(key), str):
            return str(row[key])
    for key in ("response", "result", "qa", "native", "generation", "response_payload"):
        child = row.get(key)
        if isinstance(child, Mapping):
            answer = answer_from_row(child)
            if answer:
                return answer
    return ""


def hits_from_row(row: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not row or str(row.get("status", "")).upper() not in VALID:
        return []
    hits = row.get("hits")
    return [dict(item) for item in hits if isinstance(item, Mapping)] if isinstance(hits, list) else []


def hit_doc_id(hit: Mapping[str, Any]) -> str:
    for key in ("sourceName", "source_name", "fileName", "filename", "document_id", "doc_id"):
        if hit.get(key):
            return norm_id(hit[key])
    return ""


def hit_text(hit: Mapping[str, Any]) -> str:
    for key in ("q", "text", "content", "chunk", "page_content"):
        if isinstance(hit.get(key), str):
            return str(hit[key])
    return ""


def ranked_document_scores(hits: Sequence[Mapping[str, Any]], gold_ids: Sequence[str], k: int) -> tuple[float, float, float, float]:
    gold = [norm_id(value) for value in gold_ids]
    matched: set[str] = set()
    precision_sum = 0.0
    first_rank: int | None = None
    for rank, hit in enumerate(hits[:k], 1):
        candidate = hit_doc_id(hit)
        if candidate in gold and candidate not in matched:
            matched.add(candidate)
            precision_sum += len(matched) / rank
            if first_rank is None:
                first_rank = rank
    denominator = min(len(gold), k)
    ap = precision_sum / denominator if denominator else 0.0
    recall = len(matched) / len(gold) if gold else 0.0
    return ap, (1 / first_rank if first_rank else 0.0), float(bool(matched)), recall


def official_fact_scores(hits: Sequence[Mapping[str, Any]], facts: Sequence[str], k: int = 10) -> tuple[float, float, float, float]:
    """Mirror the official scorer's fact-substring relevance and AP formula."""

    gold = [norm_text(value) for value in facts]
    found: set[str] = set()
    precision_sum = 0.0
    first_rank: int | None = None
    hit4 = 0.0
    for rank, hit in enumerate(hits[:k], 1):
        retrieved = norm_text(hit_text(hit))
        newly_found = [fact for fact in gold if fact and fact in retrieved and fact not in found]
        if newly_found:
            if first_rank is None:
                first_rank = rank
            if rank <= 4:
                hit4 = 1.0
            found.update(newly_found)
            # This intentionally follows the repository scorer's count/rank
            # formula, rather than substituting conventional precision@rank.
            precision_sum += len(newly_found) / rank
    denominator = min(len(gold), k)
    return (
        precision_sum / denominator if denominator else 0.0,
        1 / first_rank if first_rank else 0.0,
        hit4,
        float(first_rank is not None),
    )


def mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return sum(materialized) / len(materialized) if materialized else None


def metric(value: float | None, numerator: float | None, denominator: int, **extra: Any) -> dict[str, Any]:
    result = {"value": value, "numerator": numerator, "denominator": denominator}
    result.update(extra)
    return result


def aggregate(
    run_dir: Path,
    package_dir: Path,
    oracle_dir: Path | None = None,
    judge_dir: Path | None = None,
) -> dict[str, Any]:
    questions = {str(row["question_id"]): row for row in read_jsonl(package_dir / "questions.jsonl")}
    latest: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in read_jsonl(run_dir / "terminal-ledger.jsonl"):
        latest[(str(row.get("stage")), str(row.get("question_id")), int(row.get("repeat_id", 1) or 1))] = row

    retrieval_rows = {qid: latest.get(("retrieval", qid, 1)) for qid in questions}
    qa_rows = {qid: latest.get(("qa", qid, 1)) for qid in questions}
    answerable_ids = [qid for qid, q in questions.items() if bool(q.get("answerable", True))]
    null_ids = [qid for qid, q in questions.items() if not bool(q.get("answerable", True))]

    doc_scores: dict[int, list[tuple[float, float, float, float]]] = defaultdict(list)
    complete: dict[int, list[float]] = defaultdict(list)
    official: list[tuple[float, float, float, float]] = []
    for qid in answerable_ids:
        question = questions[qid]
        hits = hits_from_row(retrieval_rows[qid])
        for k in (1, 3, 4, 5, 10):
            score = ranked_document_scores(hits, question.get("gold_doc_ids", []), k)
            doc_scores[k].append(score)
            complete[k].append(float(score[3] == 1.0))
        official.append(official_fact_scores(hits, question.get("gold_evidence", [])))

    retrieval_latencies = [
        float(row["latency_ms"])
        for row in retrieval_rows.values()
        if row is not None and isinstance(row.get("latency_ms"), (int, float))
    ]
    null_empty = sum(bool(retrieval_rows[qid] and str(retrieval_rows[qid].get("status", "")).upper() in VALID and not hits_from_row(retrieval_rows[qid])) for qid in null_ids)
    retrieval_statuses = Counter(str(row.get("status", "MISSING")).upper() if row else "MISSING" for row in retrieval_rows.values())

    retrieval: dict[str, Any] = {
        "planned_n": len(questions),
        "answerable_n": len(answerable_ids),
        "null_n": len(null_ids),
        "status_counts": dict(retrieval_statuses),
        "official_compatible_fact_substring": {
            "map_at_10": metric(mean(value[0] for value in official), sum(value[0] for value in official), len(answerable_ids)),
            "mrr_at_10": metric(mean(value[1] for value in official), sum(value[1] for value in official), len(answerable_ids)),
            "hit_at_4": metric(mean(value[2] for value in official), sum(value[2] for value in official), len(answerable_ids)),
            "hit_at_10": metric(mean(value[3] for value in official), sum(value[3] for value in official), len(answerable_ids)),
            "contract": "Official null exclusion and fact-substring scorer; FastGPT native source-deduplicated Top-10 hits, not paper chunking/reranking.",
        },
        "document_level": {},
        "null_no_result_rate": metric(null_empty / len(null_ids) if null_ids else None, null_empty, len(null_ids)),
        "latency_ms": {"p50": percentile(retrieval_latencies, 0.50), "p95": percentile(retrieval_latencies, 0.95), "observed_n": len(retrieval_latencies)},
    }
    for k in (1, 3, 4, 5, 10):
        values = doc_scores[k]
        retrieval["document_level"][f"map_at_{k}"] = metric(mean(v[0] for v in values), sum(v[0] for v in values), len(answerable_ids))
        retrieval["document_level"][f"mrr_at_{k}"] = metric(mean(v[1] for v in values), sum(v[1] for v in values), len(answerable_ids))
        retrieval["document_level"][f"hit_at_{k}"] = metric(mean(v[2] for v in values), sum(v[2] for v in values), len(answerable_ids))
        retrieval["document_level"][f"evidence_recall_at_{k}"] = metric(mean(v[3] for v in values), sum(v[3] for v in values), len(answerable_ids))
        retrieval["document_level"][f"all_evidence_success_at_{k}"] = metric(mean(complete[k]), sum(complete[k]), len(answerable_ids))

    qa_statuses = Counter(str(row.get("status", "MISSING")).upper() if row else "MISSING" for row in qa_rows.values())
    overlap_values: list[float] = []
    em_values: list[float] = []
    f1_values: list[float] = []
    by_type: dict[str, list[float]] = defaultdict(list)
    for qid in answerable_ids:
        question = questions[qid]
        row = qa_rows[qid]
        answer = answer_from_row(row) if row and str(row.get("status", "")).upper() in VALID else ""
        reference = str(question.get("reference_answer", ""))
        # Mirror the official QA scorer: any whitespace-token intersection.
        overlap = float(bool(set(answer.lower().split()).intersection(reference.lower().split())))
        overlap_values.append(overlap)
        by_type[str(question.get("question_type", "unknown"))].append(overlap)
        em_values.append(float(norm_text(answer) == norm_text(reference) and bool(norm_text(reference))))
        f1_values.append(token_f1(answer, reference))
    refusal_pattern = re.compile(
        r"(?:\b(?:cannot|can't|unable|insufficient|not enough|no (?:relevant )?information|not provided|cannot determine|unknown)\b|"
        r"无法(?:确定|判断|回答|确认)?|不能(?:确定|判断|回答|确认)|信息不足|没有足够|未提供|无相关信息|未包含.{0,12}信息)",
        re.I,
    )
    null_refusals = 0
    for qid in null_ids:
        row = qa_rows[qid]
        answer = answer_from_row(row) if row and str(row.get("status", "")).upper() in VALID else ""
        null_refusals += int(bool(refusal_pattern.search(answer)))

    qa_latencies = [float(row["latency_ms"]) for row in qa_rows.values() if row is not None and isinstance(row.get("latency_ms"), (int, float))]
    e2e_latencies = []
    for qid in questions:
        retrieval_row, qa_row = retrieval_rows[qid], qa_rows[qid]
        if retrieval_row and qa_row and isinstance(retrieval_row.get("latency_ms"), (int, float)) and isinstance(qa_row.get("latency_ms"), (int, float)):
            e2e_latencies.append(float(retrieval_row["latency_ms"]) + float(qa_row["latency_ms"]))
    qa = {
        "planned_n": len(questions),
        "answerable_n": len(answerable_ids),
        "null_n": len(null_ids),
        "status_counts": dict(qa_statuses),
        "official_token_intersection_accuracy": metric(mean(overlap_values), sum(overlap_values), len(answerable_ids), contract="Official QA scorer; null queries excluded."),
        "normalized_exact_match": metric(mean(em_values), sum(em_values), len(answerable_ids)),
        "token_f1": metric(mean(f1_values), sum(f1_values), len(answerable_ids)),
        "accuracy_by_question_type": {key: metric(mean(values), sum(values), len(values)) for key, values in sorted(by_type.items())},
        "deterministic_null_refusal_proxy": metric(null_refusals / len(null_ids) if null_ids else None, null_refusals, len(null_ids), contract="Phrase-based proxy; use judge strict-unanswerable score for conclusions."),
        "generation_latency_ms": {"p50": percentile(qa_latencies, 0.50), "p95": percentile(qa_latencies, 0.95), "observed_n": len(qa_latencies)},
        "e2e_latency_ms": {"p50": percentile(e2e_latencies, 0.50), "p95": percentile(e2e_latencies, 0.95), "observed_n": len(e2e_latencies)},
    }

    resource = json.loads((run_dir / "resource-map.json").read_text(encoding="utf-8"))["resources"]["__global__"]
    result = {
        "schema": "fastgpt-multihop-rag-native-metrics-v1",
        "run_id": run_dir.name,
        "protocol": "MULTIHOP_RAG_OFFICIAL_ALL_609_2556_V1 / FastGPT platform-native",
        "ingest": {
            "planned_documents": 609,
            "ready_documents": resource.get("ready_document_count"),
            "failed_documents": resource.get("failed_document_count"),
            "failed_document_ids": resource.get("failed_document_ids_preview", []),
            "status": resource.get("status"),
        },
        "retrieval": retrieval,
        "qa": qa,
        "limitations": [
            "One source document is partially indexed after MaaS content moderation rejected two chunks.",
            "Some query embeddings may be rejected by the same provider moderation; those rows remain zero-valued failures in frozen denominators.",
            "Gold-evidence oracle generation is not part of this native FastGPT run.",
        ],
    }
    if oracle_dir is not None:
        oracle_rows = {str(row.get("question_id")): row for row in read_jsonl(oracle_dir / "terminal-ledger.jsonl")}
        oracle_overlap: list[float] = []
        oracle_em: list[float] = []
        oracle_f1: list[float] = []
        oracle_by_type: dict[str, list[float]] = defaultdict(list)
        for qid in answerable_ids:
            question = questions[qid]
            row = oracle_rows.get(qid)
            answer = answer_from_row(row) if row and str(row.get("status", "")).upper() in VALID else ""
            reference = str(question.get("reference_answer", ""))
            overlap = float(bool(set(answer.lower().split()).intersection(reference.lower().split())))
            oracle_overlap.append(overlap)
            oracle_by_type[str(question.get("question_type", "unknown"))].append(overlap)
            oracle_em.append(float(norm_text(answer) == norm_text(reference) and bool(norm_text(reference))))
            oracle_f1.append(token_f1(answer, reference))
        oracle_null_refusals = 0
        for qid in null_ids:
            row = oracle_rows.get(qid)
            answer = answer_from_row(row) if row and str(row.get("status", "")).upper() in VALID else ""
            oracle_null_refusals += int(bool(refusal_pattern.search(answer)))
        oracle_latencies = [
            float(row["latency_ms"])
            for row in oracle_rows.values()
            if isinstance(row.get("latency_ms"), (int, float))
        ]
        oracle_statuses = Counter(str(oracle_rows.get(qid, {}).get("status", "MISSING")).upper() for qid in questions)
        result["gold_oracle"] = {
            "condition": "retrieval-free FastGPT chat app with frozen Gold evidence supplied in the user message",
            "planned_n": len(questions),
            "answerable_n": len(answerable_ids),
            "null_n": len(null_ids),
            "status_counts": dict(oracle_statuses),
            "official_token_intersection_accuracy": metric(mean(oracle_overlap), sum(oracle_overlap), len(answerable_ids), contract="Official QA scorer; null queries excluded."),
            "normalized_exact_match": metric(mean(oracle_em), sum(oracle_em), len(answerable_ids)),
            "token_f1": metric(mean(oracle_f1), sum(oracle_f1), len(answerable_ids)),
            "accuracy_by_question_type": {key: metric(mean(values), sum(values), len(values)) for key, values in sorted(oracle_by_type.items())},
            "deterministic_null_refusal_proxy": metric(oracle_null_refusals / len(null_ids) if null_ids else None, oracle_null_refusals, len(null_ids)),
            "generation_latency_ms": {"p50": percentile(oracle_latencies, 0.50), "p95": percentile(oracle_latencies, 0.95), "observed_n": len(oracle_latencies)},
        }
    if judge_dir is not None:
        judge_rows = read_jsonl(judge_dir / "judge-terminal-ledger.jsonl")
        latest_judge = {str(row.get("question_id")): row for row in judge_rows}

        def judge_dimension(ids: Sequence[str], name: str) -> dict[str, Any]:
            scores: list[float] = []
            for qid in ids:
                dimension = (
                    latest_judge.get(qid, {}).get("judgement", {}).get("dimensions", {}).get(name, {})
                )
                if dimension.get("supported") is True and isinstance(dimension.get("score"), (int, float)):
                    scores.append(float(dimension["score"]))
            return metric(
                sum(scores) / len(ids) if ids else None,
                sum(scores),
                len(ids),
                eligible_n=len(scores),
                unsupported_or_empty_n=len(ids) - len(scores),
                aggregation="sum of supported scores / frozen planned slice denominator",
            )

        by_type_ids = {
            question_type: [qid for qid, value in questions.items() if str(value.get("question_type")) == question_type]
            for question_type in ("inference_query", "comparison_query", "temporal_query", "null_query")
        }
        result["judge"] = {
            "condition": "native FastGPT answer judged against actual retrieved context and frozen Gold reference",
            "physical_terminal_rows": len(judge_rows),
            "latest_terminal_n": len(latest_judge),
            "latest_status_counts": dict(Counter(str(row.get("status", "UNKNOWN")) for row in latest_judge.values())),
            "answerable": {
                "actual_context_correctness": judge_dimension(answerable_ids, "actual_context_correctness"),
                "gold_reference_correctness": judge_dimension(answerable_ids, "gold_evidence_correctness"),
                "faithfulness": judge_dimension(answerable_ids, "faithfulness"),
            },
            "null": {
                "strict_refusal": judge_dimension(null_ids, "strict_refusal"),
                "actual_context_correctness": judge_dimension(null_ids, "actual_context_correctness"),
                "faithfulness": judge_dimension(null_ids, "faithfulness"),
            },
            "by_question_type": {
                question_type: {
                    "actual_context_correctness": judge_dimension(ids, "actual_context_correctness"),
                    "faithfulness": judge_dimension(ids, "faithfulness"),
                    **({"strict_refusal": judge_dimension(ids, "strict_refusal")} if question_type == "null_query" else {}),
                }
                for question_type, ids in by_type_ids.items()
            },
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--oracle-run-dir", type=Path)
    parser.add_argument("--judge-dir", type=Path)
    args = parser.parse_args()
    result = aggregate(
        args.run_dir.resolve(),
        args.package.resolve(),
        args.oracle_run_dir.resolve() if args.oracle_run_dir else None,
        args.judge_dir.resolve() if args.judge_dir else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
