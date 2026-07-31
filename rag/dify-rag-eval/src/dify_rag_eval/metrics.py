from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff]", re.IGNORECASE)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    return " ".join(TOKEN_RE.findall(value))


def tokens(value: str) -> list[str]:
    return TOKEN_RE.findall(unicodedata.normalize("NFKC", value).lower())


def normalize_document_name(value: str) -> str:
    """Match Dify names whether the response retains the upload extension or not."""
    return normalize_text(Path(value).stem)


def token_f1(prediction: str, reference: str) -> float:
    predicted = tokens(prediction)
    expected = tokens(reference)
    if not predicted or not expected:
        return float(predicted == expected)
    overlap = sum((Counter(predicted) & Counter(expected)).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


def best_reference_score(answer: str, references: list[str]) -> tuple[float, float]:
    if not references:
        return math.nan, math.nan
    exact = max(float(normalize_text(answer) == normalize_text(ref)) for ref in references)
    f1 = max(token_f1(answer, ref) for ref in references)
    return exact, f1


def keyword_recall(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return math.nan
    normalized = unicodedata.normalize("NFKC", answer).lower()
    return sum(
        unicodedata.normalize("NFKC", keyword).lower() in normalized
        for keyword in keywords
    ) / len(keywords)


def _gold_items(case: dict[str, Any]) -> tuple[str, list[str]]:
    ids = [str(value) for value in case.get("gold_document_ids") or []]
    names = [
        normalize_document_name(value)
        for value in case.get("gold_document_names") or []
    ]
    evidence = [normalize_text(value) for value in case.get("gold_evidence") or []]
    if ids:
        return "id", ids
    if names:
        return "name", names
    return "evidence", evidence


def _context_matches(
    context: dict[str, Any], label_type: str, gold_items: list[str]
) -> set[str]:
    document_id = str(context.get("document_id") or "")
    document_name = normalize_document_name(
        str(context.get("document_name") or "")
    )
    content = normalize_text(str(context.get("content") or ""))
    if label_type == "id":
        return {item for item in gold_items if document_id == item}
    if label_type == "name":
        return {item for item in gold_items if document_name == item}
    return {item for item in gold_items if item and item in content}


def retrieval_metrics(
    contexts: list[dict[str, Any]], case: dict[str, Any], top_k: int
) -> dict[str, float]:
    label_type, gold_items = _gold_items(case)
    if not gold_items:
        return {
            "retrieval_hit_at_k": math.nan,
            "retrieval_recall_at_k": math.nan,
            "retrieval_precision_at_k": math.nan,
            "mrr": math.nan,
        }
    returned = contexts[:top_k]
    matches = [
        _context_matches(context, label_type, gold_items) for context in returned
    ]
    first_rank = next(
        (index + 1 for index, matched in enumerate(matches) if matched), None
    )
    covered = set().union(*matches) if matches else set()
    return {
        "retrieval_hit_at_k": float(bool(covered)),
        "retrieval_recall_at_k": len(covered) / len(set(gold_items)),
        "retrieval_precision_at_k": (
            sum(bool(matched) for matched in matches) / len(returned)
            if returned
            else 0.0
        ),
        "mrr": 1.0 / first_rank if first_rank else 0.0,
    }


def score_result(result: dict[str, Any], top_k: int) -> dict[str, Any]:
    case = result["case"]
    if result.get("error"):
        metrics = {
            "request_success": 0.0,
            "exact_match": math.nan,
            "token_f1": math.nan,
            "keyword_recall": math.nan,
            "refusal_match": math.nan,
            "retrieval_hit_at_k": math.nan,
            "retrieval_recall_at_k": math.nan,
            "retrieval_precision_at_k": math.nan,
            "mrr": math.nan,
        }
    else:
        answer = result.get("answer") or ""
        references = case.get("references") or []
        exact, f1 = best_reference_score(answer, references)
        answerable = case.get("answerable", True)
        refusal = (
            keyword_recall(answer, case.get("refusal_keywords") or [])
            if not answerable
            else math.nan
        )
        metrics = {
            "request_success": 1.0,
            "exact_match": exact,
            "token_f1": f1,
            "keyword_recall": keyword_recall(
                answer, case.get("required_keywords") or []
            ),
            "refusal_match": refusal,
            **retrieval_metrics(result.get("contexts") or [], case, top_k),
        }
    scored = dict(result)
    scored["metrics"] = metrics
    return scored


def finite_mean(values: list[Any]) -> float | None:
    numbers = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    return mean(numbers) if numbers else None


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = sorted(
        {name for result in results for name in (result.get("metrics") or {})}
    )
    latencies = [result.get("latency_seconds") for result in results]
    summary: dict[str, Any] = {
        "attempts": len(results),
        "distinct_questions": len({result["case"]["id"] for result in results}),
        "metrics": {
            name: finite_mean(
                [result.get("metrics", {}).get(name) for result in results]
            )
            for name in metric_names
        },
        "latency_seconds": {
            "mean": finite_mean(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
    }
    return summary


def percentile(values: list[Any], quantile: float) -> float | None:
    numbers = sorted(
        float(value)
        for value in values
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    )
    if not numbers:
        return None
    index = max(0, math.ceil(quantile * len(numbers)) - 1)
    return numbers[index]
