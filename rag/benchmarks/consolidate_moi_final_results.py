#!/usr/bin/env python3
"""Consolidate the locally available MOI benchmark artifacts.

The benchmark was run in several stages and some stages have retry artifacts
instead of one self-contained result directory.  This script creates a stable,
judge-ready directory for each of the five datasets.  It keeps the selected
per-question result, a common ``judge-input.jsonl`` contract, all relevant
attempt provenance, and a score pass that re-aggregates the frozen per-question
artifacts.  It deliberately does not make new provider calls.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "runs" / "final-results" / "moi" / "20260817-final"
DOCBENCH_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_map(path: Path, key_fn: Callable[[dict[str, Any]], str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        key = key_fn(row)
        if key:
            result[str(key)] = row
    return result


def id_from_case(row: dict[str, Any]) -> str:
    return str((row.get("case") or {}).get("id") or "")


def id_from_question_id(row: dict[str, Any]) -> str:
    return str(row.get("question_id") or row.get("id") or "")


def ok_status(status: Any) -> bool:
    return str(status or "").lower() in {"ok", "success", "completed", "succeeded"}


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def mean(values: Iterable[Any]) -> float | None:
    numbers = [float(v) for v in values if numeric(v) is not None]
    return statistics.fmean(numbers) if numbers else None


def docbench_normalize(value: Any) -> str:
    return re.sub(r"\W+", "", str(value or "").lower(), flags=re.UNICODE)


def docbench_token_f1(prediction: Any, reference: Any) -> float:
    predicted = DOCBENCH_WORD.findall(str(prediction or "").lower())
    expected = DOCBENCH_WORD.findall(str(reference or "").lower())
    if not predicted or not expected:
        return 0.0
    overlap = sum((Counter(predicted) & Counter(expected)).values())
    if not overlap:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


def docbench_lexical_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    contains_gold = 0
    token_f1_sum = 0.0
    gold_n = 0
    for row in rows:
        answer = row.get("answer") or ""
        reference = row.get("reference_answer") or ""
        normalized_reference = docbench_normalize(reference)
        if normalized_reference:
            gold_n += 1
            contains_gold += int(normalized_reference in docbench_normalize(answer))
        token_f1_sum += docbench_token_f1(answer, reference)
    planned_n = len(rows)
    return {
        "planned_n": planned_n,
        "reference_nonempty_n": gold_n,
        "contains_gold_n": contains_gold,
        "contains_gold_rate_full_denominator": contains_gold / planned_n if planned_n else None,
        "contains_gold_rate_reference_nonempty": contains_gold / gold_n if gold_n else None,
        "token_f1_sum": token_f1_sum,
        "token_f1_rate_full_denominator": token_f1_sum / planned_n if planned_n else None,
        "token_f1_rate_reference_nonempty": token_f1_sum / gold_n if gold_n else None,
    }


def chunk_texts(chunks: Any) -> list[str]:
    if not isinstance(chunks, list):
        return []
    result: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            content = chunk.get("content")
            if content is None:
                content = chunk.get("text")
            if content is None:
                content = chunk.get("evidence_text")
            result.append(str(content or ""))
        else:
            result.append(str(chunk))
    return result


def natural_id_key(value: str) -> tuple[Any, ...]:
    pieces: list[Any] = []
    for part in value.replace("_", "-").split("-"):
        pieces.append(int(part) if part.isdigit() else part)
    return tuple(pieces)


def source_file_summary(path: Path, key_fn: Callable[[dict[str, Any]], str]) -> dict[str, Any]:
    rows = read_jsonl(path)
    ids = [key_fn(row) for row in rows]
    statuses = Counter(str(row.get("status") or "") for row in rows)
    return {
        "path": rel(path),
        "rows": len(rows),
        "unique_ids": len({value for value in ids if value}),
        "status_counts": dict(statuses),
    }


def common_result(
    *,
    dataset: str,
    identifier: str,
    question: str,
    reference_answer: Any,
    reference_evidence: Any,
    expected_answerable: Any,
    question_type: Any,
    selected_raw: dict[str, Any],
    selected_source: Path,
    attempts: list[dict[str, Any]],
    retrieval: dict[str, Any],
) -> dict[str, Any]:
    chunks = selected_raw.get("chunks") or selected_raw.get("context") or []
    answer = selected_raw.get("answer")
    return {
        "schema": "moi-final-result-v1",
        "dataset": dataset,
        "id": identifier,
        "status": selected_raw.get("status"),
        "question": question,
        "reference_answer": reference_answer,
        "reference_evidence": reference_evidence,
        "expected_answerable": expected_answerable,
        "question_type": question_type,
        "answer": answer,
        "chunks": chunks,
        "context_text": chunk_texts(chunks),
        "retrieval": retrieval,
        "selected_source": rel(selected_source),
        "attempts": attempts,
        "selected_raw": selected_raw,
    }


def judge_input(record: dict[str, Any], contract: str) -> dict[str, Any]:
    return {
        "schema": "moi-judge-input-v1",
        "judge_contract": contract,
        "dataset": record["dataset"],
        "id": record["id"],
        "status": record["status"],
        "question": record["question"],
        "reference_answer": record["reference_answer"],
        "reference_evidence": record["reference_evidence"],
        "expected_answerable": record["expected_answerable"],
        "question_type": record["question_type"],
        "answer": record["answer"],
        "context": record["chunks"],
        "context_text": record["context_text"],
        "retrieval": record["retrieval"],
        "selected_source": record["selected_source"],
    }


def finish_dataset(
    out: Path,
    *,
    dataset: str,
    results: list[dict[str, Any]],
    inputs: list[dict[str, Any]],
    judgements: list[dict[str, Any]],
    judge_attempts: list[dict[str, Any]],
    metrics: dict[str, Any],
    sources: list[dict[str, Any]],
    notes: list[str],
) -> dict[str, Any]:
    directory = out / dataset
    directory.mkdir(parents=True, exist_ok=True)
    write_jsonl(directory / "results.jsonl", results)
    write_jsonl(directory / "judge-input.jsonl", inputs)
    write_jsonl(directory / "judgements.jsonl", judgements)
    write_jsonl(directory / "judge-attempts.jsonl", judge_attempts)
    write_json(directory / "metrics.json", metrics)
    write_json(directory / "sources.json", {"dataset": dataset, "sources": sources})
    readme = [
        f"# MOI final results: {dataset}",
        "",
        "`results.jsonl` contains one canonical record per benchmark question.",
        "`judge-input.jsonl` is the common judge-ready contract and includes the answer, reference, and retrieved context.",
        "`judgements.jsonl` contains the selected frozen per-question score; `judge-attempts.jsonl` retains duplicate/error judge attempts.",
        "",
        "The final score pass re-aggregates local artifacts and does not make new provider calls. Retry provenance and failures remain in each record's `attempts` field.",
        "",
        "## Notes",
        "",
    ] + [f"- {note}" for note in notes]
    (directory / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    return {
        "directory": rel(directory),
        "questions": len(results),
        "query_ok": sum(ok_status(row.get("status")) for row in results),
        "judge_records": len(judgements),
        "judge_valid": sum(str(row.get("status")) in {"ok", "success", "valid"} for row in judgements),
        "files": {
            "results": rel(directory / "results.jsonl"),
            "judge_input": rel(directory / "judge-input.jsonl"),
            "judgements": rel(directory / "judgements.jsonl"),
            "metrics": rel(directory / "metrics.json"),
        },
        "metrics": metrics,
    }


def consolidate_wikieval(out: Path) -> dict[str, Any]:
    base = ROOT / "runs/stage1/ragas-wikieval-moi/20260807-160000-wikieval"
    artifacts = base / "artifacts"
    result_path = base / "moi-run/20260807-161313.375/results.jsonl"
    question_path = artifacts / "questions.jsonl"
    score_path = artifacts / "ragas/scores.jsonl"
    raw_metrics = read_json(artifacts / "metrics.json")
    ragas_summary = read_json(artifacts / "ragas/summary.json")
    raw = load_map(result_path, id_from_case)
    questions = load_map(question_path, lambda row: str(row.get("id") or ""))
    scores = load_map(score_path, lambda row: str(row.get("id") or ""))
    ids = sorted(raw, key=natural_id_key)
    results: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    judgements: list[dict[str, Any]] = []
    for identifier in ids:
        selected = raw[identifier]
        case = selected.get("case") or questions.get(identifier) or {}
        metadata = case.get("metadata") or {}
        reference_answer = metadata.get("reference") or case.get("reference")
        reference_evidence = case.get("relevant_evidence") or []
        record = common_result(
            dataset="wikieval",
            identifier=identifier,
            question=str(case.get("question") or ""),
            reference_answer=reference_answer,
            reference_evidence=reference_evidence,
            expected_answerable=case.get("expected_answerable"),
            question_type=metadata.get("question_type"),
            selected_raw=selected,
            selected_source=result_path,
            attempts=[{"round": "initial", "path": rel(result_path), "status": selected.get("status")}],
            retrieval={
                "metrics": selected.get("metrics") or {},
                "latency_ms": selected.get("retrieval_latency_ms"),
                "routes": selected.get("routes") or [],
            },
        )
        results.append(record)
        inputs.append(judge_input(record, "wikieval-ragas-v0"))
        score = scores.get(identifier) or {"id": identifier, "status": "missing"}
        judgements.append({
            "id": identifier,
            "status": "valid" if score.get("status") == "ok" else "invalid",
            "judge_contract": "wikieval-ragas-v0",
            "judge": score,
            "source": rel(score_path),
        })
    ragas_values: dict[str, Any] = {}
    for key in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
        values = [scores[i].get(key) for i in ids if numeric(scores.get(i, {}).get(key)) is not None]
        ragas_values[key] = {"mean": mean(values), "valid_n": len(values)}
    recomputed = {
        "questions": len(results),
        "query_ok": sum(ok_status(row.get("status")) for row in results),
        "answer_non_empty_n": sum(bool(str(row.get("answer") or "").strip()) for row in results),
        "judge_valid_n": sum(row["status"] == "valid" for row in judgements),
        "ragas": ragas_values,
    }
    metrics = {
        "dataset": "WikiEval",
        "score_pass": {"mode": "reaggregate_existing_artifacts", "judge_invocations": 0, "scored_at": now()},
        "headline": raw_metrics,
        "ragas_summary_source": ragas_summary,
        "recomputed_checks": recomputed,
        "validation": {
            "question_count_matches_source": len(results) == int(raw_metrics.get("attempts", -1)),
            "ragas_counts_match_source": all(
                ragas_values[key]["valid_n"] == int((ragas_summary.get("metrics", {}).get(key) or {}).get("scored_rows", -1))
                for key in ragas_values
            ),
        },
    }
    sources = [
        source_file_summary(result_path, id_from_case),
        source_file_summary(question_path, lambda row: str(row.get("id") or "")),
        source_file_summary(score_path, lambda row: str(row.get("id") or "")),
        {"path": rel(artifacts / "metrics.json"), "kind": "source_metrics"},
        {"path": rel(artifacts / "ragas/summary.json"), "kind": "source_judge_summary"},
    ]
    return finish_dataset(
        out,
        dataset="wikieval",
        results=results,
        inputs=inputs,
        judgements=judgements,
        judge_attempts=judgements,
        metrics=metrics,
        sources=sources,
        notes=[
            "Selected the completed 50-question MOI run; no retry was present for this dataset.",
            "RAGAS scores are frozen diagnostic judge artifacts; the deterministic source metrics remain primary.",
        ],
    )


def page_fraction(attempt: dict[str, Any], gold_pages: list[Any], k: int) -> float | None:
    gold = {str(value) for value in gold_pages}
    if not gold:
        return None
    hits = [str(hit.get("page_id")) for hit in (attempt.get("hits") or [])[:k] if isinstance(hit, dict) and hit.get("page_id") is not None]
    return len(set(hits) & gold) / len(gold)


def page_mrr(attempt: dict[str, Any], gold_pages: list[Any]) -> float:
    gold = {str(value) for value in gold_pages}
    for rank, hit in enumerate(attempt.get("hits") or [], start=1):
        if isinstance(hit, dict) and str(hit.get("page_id")) in gold:
            return 1.0 / rank
    return 0.0


def consolidate_mmdocir(out: Path) -> dict[str, Any]:
    base = ROOT / "runs/stage1"
    page_path = base / "mmdocir/20260806-161153-full-1658/page/eval/20260806-221922.385/attempts.jsonl"
    layout_path = base / "mmdocir/20260806-161153-full-1658/layout/eval/20260806-222713.393/attempts.jsonl"
    page_metrics_path = page_path.parent / "metrics.json"
    layout_metrics_path = layout_path.parent / "metrics.json"
    prepared_path = base / "mmdocir/20260806-161153-full-1658/artifacts/prepared/questions.jsonl"
    qa_base = base / "mmdocir-qa/20260813-230700-mmdocir-qwen35-recovery-full-1658"
    qa_result_path = qa_base / "20260813-230828.003/results.jsonl"
    qa_ledger_path = qa_base / "qa-ledger.jsonl"
    qa_summary_path = qa_base / "qa-summary.json"
    page = load_map(page_path, lambda row: str(row.get("question_id") or ""))
    layout = load_map(layout_path, lambda row: str(row.get("question_id") or ""))
    qa = load_map(qa_result_path, lambda row: str((row.get("case") or {}).get("id") or ""))
    ledger = load_map(qa_ledger_path, lambda row: str(row.get("question_id") or ""))
    prepared = load_map(prepared_path, lambda row: str(row.get("id") or ""))
    ids = sorted(set(page) | set(layout) | set(qa), key=natural_id_key)
    results: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    judgements: list[dict[str, Any]] = []
    page_values = {str(k): [] for k in (1, 3, 5, 10)}
    page_mrr_values: list[float] = []
    layout_values = {str(k): [] for k in (1, 5, 10)}
    qa_non_empty: list[bool] = []
    qa_contains_gold: list[Any] = []
    qa_token_f1: list[Any] = []
    qa_page_recall: dict[str, list[Any]] = {str(k): [] for k in (1, 3, 5, 10)}
    for identifier in ids:
        qrow = prepared.get(identifier) or {}
        qraw = qa.get(identifier) or {}
        case = qraw.get("case") or {}
        metadata = case.get("metadata") or {}
        gold_pages = list(qrow.get("page_ids") or metadata.get("gold_page_ids") or [])
        page_attempt = page.get(identifier) or {}
        layout_attempt = layout.get(identifier) or {}
        ledger_row = ledger.get(identifier) or {}
        selected = qraw or {
            "case": case,
            "status": ledger_row.get("status", "missing"),
            "answer": ledger_row.get("generated_answer"),
            "chunks": ledger_row.get("retrieval_hits") or [],
        }
        question = str(case.get("question") or qrow.get("question") or ledger_row.get("question") or "")
        reference_answer = metadata.get("reference_answer") or qrow.get("answer")
        question_type = metadata.get("question_type") or qrow.get("evidence_type")
        retrieval = {
            "page": page_attempt,
            "layout": layout_attempt,
            "qa_metrics": selected.get("metrics") or {},
            "qa_retrieval_hits": ledger_row.get("retrieval_hits") or [],
        }
        attempts = [
            {"round": "page-retrieval", "path": rel(page_path), "status": page_attempt.get("status")},
            {"round": "layout-retrieval", "path": rel(layout_path), "status": layout_attempt.get("status")},
            {"round": "qa", "path": rel(qa_result_path), "status": selected.get("status")},
        ]
        record = common_result(
            dataset="mmdocir",
            identifier=identifier,
            question=question,
            reference_answer=reference_answer,
            reference_evidence=case.get("relevant_evidence") or [],
            expected_answerable=case.get("expected_answerable"),
            question_type=question_type,
            selected_raw=selected,
            selected_source=qa_result_path,
            attempts=attempts,
            retrieval=retrieval,
        )
        results.append(record)
        inputs.append(judge_input(record, "mmdocir-adapted-qa-v1"))
        ledger_status = ledger_row.get("status") or selected.get("status")
        judge = {
            "answer_non_empty": bool(str(ledger_row.get("generated_answer") or selected.get("answer") or "").strip()),
            "answer_contains_gold": ledger_row.get("answer_contains_gold"),
            "token_f1": ledger_row.get("token_f1"),
            "retrieved_page_recall_at_k": ledger_row.get("retrieved_page_recall_at_k"),
            "source_metrics": selected.get("metrics") or {},
        }
        judgements.append({
            "id": identifier,
            "status": "valid" if ok_status(ledger_status) else "invalid",
            "judge_contract": "mmdocir-adapted-qa-v1",
            "judge": judge,
            "source": rel(qa_ledger_path),
        })
        for k in page_values:
            value = page_fraction(page_attempt, gold_pages, int(k))
            if value is not None:
                page_values[k].append(value)
        page_mrr_values.append(page_mrr(page_attempt, gold_pages))
        for k in layout_values:
            value = numeric((layout_attempt.get("recall_at_k") or {}).get(k))
            if value is not None:
                layout_values[k].append(value)
        qa_non_empty.append(bool(str(ledger_row.get("generated_answer") or selected.get("answer") or "").strip()))
        qa_contains_gold.append(ledger_row.get("answer_contains_gold"))
        qa_token_f1.append(ledger_row.get("token_f1"))
        for k in qa_page_recall:
            value = numeric((ledger_row.get("retrieved_page_recall_at_k") or {}).get(k))
            if value is not None:
                qa_page_recall[k].append(value)
    page_recomputed = {f"fraction_at_{k}": {"mean": mean(values), "valid_n": len(values)} for k, values in page_values.items()}
    layout_recomputed = {f"recall_at_{k}": {"mean": mean(values), "valid_n": len(values)} for k, values in layout_values.items()}
    qa_recomputed = {
        "questions": len(results),
        "query_ok": sum(ok_status(row.get("status")) for row in results),
        "answer_non_empty_rate": mean(qa_non_empty),
        "answer_contains_gold_rate": mean(qa_contains_gold),
        "mean_token_f1": mean(qa_token_f1),
        "mean_page_recall_at_k": {k: mean(values) for k, values in qa_page_recall.items()},
    }
    source_page_metrics = read_json(page_metrics_path)
    source_layout_metrics = read_json(layout_metrics_path)
    source_qa_summary = read_json(qa_summary_path)
    metrics = {
        "dataset": "MMDocIR",
        "score_pass": {"mode": "reaggregate_retrieval_and_existing_qa_artifacts", "judge_invocations": 0, "scored_at": now()},
        "recomputed": {
            "page_retrieval": page_recomputed,
            "page_mrr": {"mean": mean(page_mrr_values), "valid_n": len(page_mrr_values)},
            "layout_retrieval": layout_recomputed,
            "qa": qa_recomputed,
        },
        "reported_adapted_qa": {
            "answer_correctness_5": 3.91,
            "faithfulness": 0.7398,
            "source": "tables.md and results/MOI_rag_benchmark_v1.0.md; no per-question judge file was present",
        },
        "source_metrics": {
            "page": source_page_metrics,
            "layout": source_layout_metrics,
            "qa": source_qa_summary,
        },
        "validation": {
            "page_rows": len(page) == len(results),
            "layout_rows": len(layout) == len(results),
            "qa_rows": len(qa) == len(results),
            "qa_summary_attempts_match": int(source_qa_summary.get("attempts", -1)) == len(results),
            "page_fraction_at_10_recomputed": page_recomputed["fraction_at_10"],
        },
    }
    sources = [
        source_file_summary(page_path, lambda row: str(row.get("question_id") or "")),
        source_file_summary(layout_path, lambda row: str(row.get("question_id") or "")),
        source_file_summary(qa_result_path, lambda row: str((row.get("case") or {}).get("id") or "")),
        source_file_summary(qa_ledger_path, lambda row: str(row.get("question_id") or "")),
        source_file_summary(prepared_path, lambda row: str(row.get("id") or "")),
        {"path": rel(page_metrics_path), "kind": "source_metrics"},
        {"path": rel(layout_metrics_path), "kind": "source_metrics"},
        {"path": rel(qa_summary_path), "kind": "source_metrics"},
    ]
    return finish_dataset(
        out,
        dataset="mmdocir",
        results=results,
        inputs=inputs,
        judgements=judgements,
        judge_attempts=judgements,
        metrics=metrics,
        sources=sources,
        notes=[
            "Page and layout retrieval attempts are joined to the full 1,658-question QA run by question_id.",
            "The page fraction@10 value is recomputed from top-10 hits and the prepared Gold page_ids; the source page metrics file did not persist a @10 field.",
            "Answer correctness 3.91/5 and faithfulness 0.7398 are carried-forward report metrics because no per-question LLM judge file was present; deterministic QA metrics are freshly re-aggregated.",
            "This remains MMDocIR adapted QA, not an official MMDocIR QA leaderboard.",
        ],
    )


def valid_docbench_judge(row: dict[str, Any] | None) -> bool:
    if not row or row.get("status") != "ok":
        return False
    return numeric(row.get("score")) is not None


def prefer_judgement_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        identifier = str(row.get("id") or "")
        if not identifier:
            continue
        if identifier not in result or valid_docbench_judge(row):
            result[identifier] = row
    return result


def consolidate_docbench(out: Path) -> dict[str, Any]:
    initial_dir = ROOT / "runs/current-corpus-eval/20260813-232055-docbench-missing196/docbench-full-1102/datasets/docbench"
    r1_dir = ROOT / "runs/current-corpus-eval-reruns-docbench/20260817-000134.440/datasets/docbench"
    r2_dir = ROOT / "runs/current-corpus-eval-reruns-docbench/20260817-011206.565/datasets/docbench"
    r3_dir = ROOT / "runs/current-corpus-eval-reruns-docbench/20260817-021923.527/datasets/docbench"
    initial_result_path = initial_dir / "combined-results.jsonl"
    initial_judge_path = initial_dir / "judgements.jsonl"
    r1_result_path = r1_dir / "combined-results.jsonl"
    r1_judge_path = r1_dir / "judgements.jsonl"
    r2_result_path = r2_dir / "combined-results.jsonl"
    r2_judge_path = r2_dir / "judgements.jsonl"
    r3_result_path = r3_dir / "combined-results.jsonl"
    r3_judge_path = r3_dir / "judgements.jsonl"
    initial = load_map(initial_result_path, id_from_case)
    r1 = load_map(r1_result_path, id_from_case)
    r2 = load_map(r2_result_path, id_from_case)
    r3 = load_map(r3_result_path, id_from_case)
    initial_judges = prefer_judgement_rows(read_jsonl(initial_judge_path))
    r1_judges = prefer_judgement_rows(read_jsonl(r1_judge_path))
    r2_judges = prefer_judgement_rows(read_jsonl(r2_judge_path))
    r3_judges = prefer_judgement_rows(read_jsonl(r3_judge_path))
    ids = sorted(initial, key=natural_id_key)
    results: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    judgements: list[dict[str, Any]] = []
    judge_attempts: list[dict[str, Any]] = []
    type_stats: dict[str, dict[str, Any]] = {}
    recovery_selected = 0
    remaining_failure_ids: list[str] = []

    for identifier in ids:
        attempt_defs = [
            ("initial", initial.get(identifier), initial_judges.get(identifier), initial_result_path, initial_judge_path),
            ("recovery_round1", r1.get(identifier), r1_judges.get(identifier), r1_result_path, r1_judge_path),
            ("recovery_round2", r2.get(identifier), r2_judges.get(identifier), r2_result_path, r2_judge_path),
            ("recovery_round3", r3.get(identifier), r3_judges.get(identifier), r3_result_path, r3_judge_path),
        ]
        attempts: list[dict[str, Any]] = []
        for label, raw, jrow, result_path, judge_path in attempt_defs:
            if raw is None and jrow is None:
                continue
            attempts.append({
                "round": label,
                "result_source": rel(result_path) if raw is not None else None,
                "judge_source": rel(judge_path) if jrow is not None else None,
                "status": raw.get("status") if raw else None,
                "judge_status": jrow.get("status") if jrow else "missing",
                "error": (raw or {}).get("error"),
            })
        candidates = [
            ("recovery_round3", r3.get(identifier), r3_judges.get(identifier), r3_result_path),
            ("recovery_round2", r2.get(identifier), r2_judges.get(identifier), r2_result_path),
            ("recovery_round1", r1.get(identifier), r1_judges.get(identifier), r1_result_path),
            ("initial", initial.get(identifier), initial_judges.get(identifier), initial_result_path),
        ]
        selected_label: str | None = None
        selected_raw: dict[str, Any] | None = None
        selected_judge: dict[str, Any] | None = None
        selected_path = initial_result_path
        # Prefer a recovery only when it has a valid query and valid judge.  A
        # clean historical result remains the canonical result for clean cases.
        for label, raw, jrow, result_path in candidates:
            if raw is not None and ok_status(raw.get("status")) and valid_docbench_judge(jrow):
                selected_label, selected_raw, selected_judge, selected_path = label, raw, jrow, result_path
                break
        if selected_raw is None:
            # Preserve the latest failed attempt for unresolved cases, then any
            # successful-but-unjudged result as a diagnostic fallback.
            for label, raw, jrow, result_path in candidates:
                if raw is not None and not ok_status(raw.get("status")):
                    selected_label, selected_raw, selected_judge, selected_path = label, raw, jrow, result_path
                    break
            if selected_raw is None:
                for label, raw, jrow, result_path in candidates:
                    if raw is not None:
                        selected_label, selected_raw, selected_judge, selected_path = label, raw, jrow, result_path
                        break
        assert selected_raw is not None and selected_label is not None
        if selected_label != "initial":
            recovery_selected += 1
        if not ok_status(selected_raw.get("status")):
            remaining_failure_ids.append(identifier)
        case = selected_raw.get("case") or initial[identifier].get("case") or {}
        metadata = case.get("metadata") or {}
        qtype = metadata.get("question_type")
        record = common_result(
            dataset="docbench",
            identifier=identifier,
            question=str(case.get("question") or ""),
            reference_answer=metadata.get("reference_answer"),
            reference_evidence=metadata.get("reference_evidence"),
            expected_answerable=case.get("expected_answerable"),
            question_type=qtype,
            selected_raw=selected_raw,
            selected_source=selected_path,
            attempts=attempts + [{"round": "selected", "source": rel(selected_path), "label": selected_label}],
            retrieval={
                "metrics": selected_raw.get("metrics") or {},
                "latency_ms": selected_raw.get("retrieval_latency_ms"),
                "routes": selected_raw.get("routes") or [],
            },
        )
        results.append(record)
        inputs.append(judge_input(record, "docbench-evaluation-prompt-v1"))
        judge_entry = {
            "id": identifier,
            "status": "valid" if valid_docbench_judge(selected_judge) else "unavailable",
            "judge_contract": "docbench-evaluation-prompt-v1",
            "score": selected_judge.get("score") if selected_judge else None,
            "model": selected_judge.get("model") if selected_judge else None,
            "provider": selected_judge.get("provider") if selected_judge else None,
            "raw": selected_judge.get("raw") if selected_judge else None,
            "selected_round": selected_label,
            "selected_source": rel(selected_path),
        }
        judgements.append(judge_entry)
        for label, raw, jrow, result_path, judge_path in attempt_defs:
            if jrow is not None:
                judge_attempts.append({"round": label, "source": rel(judge_path), **jrow})
        qtype = str(qtype or "unknown")
        stat = type_stats.setdefault(qtype, {"total": 0, "query_ok": 0, "judge_valid": 0, "score_sum": 0})
        stat["total"] += 1
        stat["query_ok"] += int(ok_status(selected_raw.get("status")))
        if valid_docbench_judge(selected_judge):
            stat["judge_valid"] += 1
            stat["score_sum"] += int(selected_judge.get("score"))

    valid_judges = [row for row in judgements if row["status"] == "valid"]
    score_sum = sum(int(row["score"]) for row in valid_judges)
    by_type: dict[str, Any] = {}
    for key, stat in type_stats.items():
        valid_n = stat["judge_valid"]
        total = stat["total"]
        by_type[key] = {
            **stat,
            "judge_rate_available": stat["score_sum"] / valid_n if valid_n else None,
            "full_denominator_rate": stat["score_sum"] / total if total else None,
        }
    lexical_by_type = {
        key: docbench_lexical_summary([row for row in results if str(row.get("question_type") or "unknown") == key])
        for key in sorted(type_stats)
    }
    recovery_summary_path = ROOT / "runs/current-corpus-eval-reruns-docbench/failed-case-recovery-20260817/summary.json"
    metrics = {
        "dataset": "DocBench",
        "score_pass": {"mode": "reaggregate_historical_and_three_recovery_rounds", "judge_invocations": 0, "scored_at": now()},
        "questions": len(ids),
        "initial_query_failed_n": sum(not ok_status(row.get("status")) for row in initial.values()),
        "initial_judge_failed_n": sum(j is not None and not valid_docbench_judge(j) for j in initial_judges.values()),
        "failure_union_n": sum(
            not ok_status(initial.get(identifier, {}).get("status")) or not valid_docbench_judge(initial_judges.get(identifier))
            for identifier in ids
        ),
        "recovery_selected_n": recovery_selected,
        "final_query_ok_n": sum(ok_status(row.get("status")) for row in results),
        "final_query_failed_n": len(remaining_failure_ids),
        "final_judge_valid_n": len(valid_judges),
        "final_judge_unavailable_n": len(judgements) - len(valid_judges),
        "final_judge_score_sum": score_sum,
        "final_correctness_available": score_sum / len(valid_judges) if valid_judges else None,
        "final_correctness_full_denominator": score_sum / len(ids) if ids else None,
        "by_question_type": by_type,
        "lexical_diagnostics": {
            "contract": "docbench-lexical-diagnostic-v1; normalize=lowercase plus Unicode punctuation removal; token_pattern=[^\\W_]+; failed rows remain zero in the full denominator",
            "full_denominator": docbench_lexical_summary(results),
            "query_success_only": docbench_lexical_summary([row for row in results if ok_status(row.get("status"))]),
            "by_question_type": lexical_by_type,
            "interpretation": "Deterministic lexical diagnostics only; they do not replace the semantic DocBench Judge correctness score.",
        },
        "remaining_failure_ids": remaining_failure_ids,
        "source_metrics": {
            "historical": read_json(initial_dir / "metrics.json"),
            "recovery_summary": read_json(recovery_summary_path) if recovery_summary_path.is_file() else None,
        },
        "validation": {
            "historical_rows": len(initial) == 1102,
            "final_rows": len(results) == 1102,
            "valid_judge_rows_equal_query_ok": len(valid_judges) == sum(ok_status(row.get("status")) for row in results),
            "lexical_diagnostics_rows_equal_final_rows": len(results) == len(ids),
            "remaining_failures_match_third_round": set(remaining_failure_ids) == {
                "docbench-39-0000", "docbench-90-0000", "docbench-200-0002", "docbench-92-0003"
            },
        },
    }
    sources = [
        source_file_summary(initial_result_path, id_from_case),
        source_file_summary(initial_judge_path, lambda row: str(row.get("id") or "")),
        source_file_summary(r1_result_path, id_from_case),
        source_file_summary(r1_judge_path, lambda row: str(row.get("id") or "")),
        source_file_summary(r2_result_path, id_from_case),
        source_file_summary(r2_judge_path, lambda row: str(row.get("id") or "")),
        source_file_summary(r3_result_path, id_from_case),
        source_file_summary(r3_judge_path, lambda row: str(row.get("id") or "")),
        {"path": rel(recovery_summary_path), "kind": "recovery_summary"},
    ]
    return finish_dataset(
        out,
        dataset="docbench",
        results=results,
        inputs=inputs,
        judgements=judgements,
        judge_attempts=judge_attempts,
        metrics=metrics,
        sources=sources,
        notes=[
            "Canonical precedence is valid recovery round 3, then round 2, round 1, and finally a valid historical result; unresolved cases remain failed.",
            "The third retry attempted the four remaining ModelArts.81011 cases and failed 4/4; the runner's zero-success closeout error is retained as provenance, and no further retry is scheduled.",
            "The four unresolved questions remain in results.jsonl and judge-input.jsonl with unavailable final judgment and count in the full 1,102-question denominator.",
            "Contains-gold and Token F1 are freshly derived from the canonical answer/reference rows as deterministic lexical diagnostics; they are not semantic Judge scores.",
            "This is a current-corpus adapted recovery audit, not a replacement for the historical Native PDF ranking row.",
        ],
    )


def fact_coverage_fraction(judge: dict[str, Any]) -> float | None:
    values = judge.get("fact_coverage")
    if not isinstance(values, list) or not values:
        return None
    numbers = [numeric(value) for value in values]
    if any(value is None for value in numbers):
        return None
    return sum(float(value) for value in numbers if value is not None) / len(numbers)


def consolidate_enterprise(out: Path) -> dict[str, Any]:
    base = ROOT / "runs/current-corpus-eval/20260812-121828.079/datasets/enterpriserag-bench"
    initial_result_path = base / "combined-results.jsonl"
    initial_ledger_path = base / "qa-ledger.jsonl"
    initial_metrics_path = base / "metrics.json"
    recovery = base / "recovered-evaluation"
    recovered_result_path = recovery / "recovered-results.jsonl"
    recovered_ledger_path = recovery / "qa-ledger.jsonl"
    recovered_judge_path = recovery / "judgements.jsonl"
    recovered_metrics_path = recovery / "metrics.json"
    initial = load_map(initial_result_path, id_from_case)
    recovered_raw = load_map(recovered_result_path, id_from_case)
    recovered_ledger = load_map(recovered_ledger_path, lambda row: str(row.get("id") or ""))
    ids = sorted(set(initial) | set(recovered_raw) | set(recovered_ledger), key=natural_id_key)
    results: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    judgements: list[dict[str, Any]] = []
    all_judge_attempts: list[dict[str, Any]] = []
    for index, row in enumerate(read_jsonl(recovered_judge_path), start=1):
        all_judge_attempts.append({"attempt_index": index, "source": rel(recovered_judge_path), **row})
    for identifier in ids:
        ledger_row = recovered_ledger.get(identifier) or {}
        selected = recovered_raw.get(identifier) or ledger_row.get("result") or initial.get(identifier) or {"status": "failed", "case": {"id": identifier}}
        case = selected.get("case") or {}
        metadata = case.get("metadata") or {}
        initial_row = initial.get(identifier) or {}
        attempts = [
            {
                "round": "initial",
                "source": rel(initial_result_path),
                "status": initial_row.get("status"),
                "error": initial_row.get("error"),
            },
            {
                "round": "recovered-evaluation",
                "source": rel(recovered_result_path),
                "status": selected.get("status"),
                "attempts": ledger_row.get("attempts"),
            },
        ]
        record = common_result(
            dataset="enterpriserag-bench",
            identifier=identifier,
            question=str(case.get("question") or ledger_row.get("question") or ""),
            reference_answer=metadata.get("reference_answer"),
            reference_evidence=case.get("relevant_evidence") or metadata.get("reference_evidence") or [],
            expected_answerable=case.get("expected_answerable"),
            question_type=metadata.get("question_type"),
            selected_raw=selected,
            selected_source=recovered_result_path,
            attempts=attempts,
            retrieval={
                "metrics": selected.get("metrics") or {},
                "latency_ms": selected.get("retrieval_latency_ms"),
                "routes": selected.get("routes") or [],
            },
        )
        results.append(record)
        inputs.append(judge_input(record, "enterpriserag-adapted-answer-facts-v1"))
        judge = ledger_row.get("judge") or {}
        judgements.append({
            "id": identifier,
            "status": "valid" if judge.get("status") == "success" else "invalid",
            "judge_contract": "enterpriserag-adapted-answer-facts-v1",
            "judge": judge,
            "source": rel(recovered_ledger_path),
        })
    valid_judges = [row["judge"] for row in judgements if row["status"] == "valid"]
    correctness = [judge.get("correctness") for judge in valid_judges]
    completeness = [fact_coverage_fraction(judge) for judge in valid_judges]
    unsupported = [judge.get("unsupported_completion") for judge in valid_judges]
    source_metrics = read_json(recovered_metrics_path)
    recomputed = {
        "questions": len(results),
        "initial_query_ok_n": sum(ok_status(row.get("status")) for row in initial.values()),
        "recovered_query_ok_n": sum(ok_status(row.get("status")) for row in results),
        "judge_valid_n": len(valid_judges),
        "correctness": mean(correctness),
        "completeness": mean(completeness),
        "unsupported_completion_rate": mean(unsupported),
    }
    metrics = {
        "dataset": "EnterpriseRAG-Bench",
        "score_pass": {"mode": "reaggregate_recovered_results_and_existing_judgements", "judge_invocations": 0, "scored_at": now()},
        "headline": source_metrics,
        "recomputed_checks": recomputed,
        "source_initial_metrics": read_json(initial_metrics_path),
        "validation": {
            "question_count": len(results) == 500,
            "recovered_judge_count": len(valid_judges) == 500,
            "correctness_matches_source": abs((mean(correctness) or 0) - float(source_metrics.get("correctness", -1))) < 1e-12,
            "completeness_matches_source": abs((mean(completeness) or 0) - float(source_metrics.get("completeness", -1))) < 1e-12,
            "initial_availability_matches_source": sum(ok_status(row.get("status")) for row in initial.values()) == int(source_metrics.get("raw_transport_initial_success", -1)),
        },
    }
    sources = [
        source_file_summary(initial_result_path, id_from_case),
        source_file_summary(initial_ledger_path, lambda row: str(row.get("id") or "")),
        source_file_summary(recovered_result_path, id_from_case),
        source_file_summary(recovered_ledger_path, lambda row: str(row.get("id") or "")),
        source_file_summary(recovered_judge_path, lambda row: str(row.get("id") or "")),
        {"path": rel(initial_metrics_path), "kind": "source_metrics"},
        {"path": rel(recovered_metrics_path), "kind": "source_metrics"},
    ]
    return finish_dataset(
        out,
        dataset="enterpriserag-bench",
        results=results,
        inputs=inputs,
        judgements=judgements,
        judge_attempts=all_judge_attempts,
        metrics=metrics,
        sources=sources,
        notes=[
            "Recovered-evaluation is the canonical answer result because all 500 questions have a successful recovered result and valid frozen judge.",
            "Initial transport availability remains visible: 417/500 on the first pass and 83 questions recovered by retry.",
            "The score is for the current-corpus adapted 722-document slice, not the official full EnterpriseRAG-Bench corpus.",
        ],
    )


def consolidate_lenovo(out: Path) -> dict[str, Any]:
    base = ROOT / "runs/lenovo-bench/20260812-233500"
    contract_dir = base / "evaluation-fastgpt-contract"
    result_path = contract_dir / "results.jsonl"
    judge_path = contract_dir / "judgements.jsonl"
    metrics_path = contract_dir / "metrics.json"
    project_metrics_path = base / "evaluation/metrics.json"
    rows = read_jsonl(result_path)
    judge_attempt_rows = read_jsonl(judge_path)
    results: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    judgements: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: natural_id_key(str(item.get("question_id") or ""))):
        identifier = str(row.get("question_id") or "")
        case = row.get("case") or {}
        selected = row
        record = common_result(
            dataset="lenovo-bench",
            identifier=identifier,
            question=str(case.get("question") or ""),
            reference_answer=case.get("reference_answer"),
            reference_evidence=case.get("evidence_sets") or [],
            expected_answerable=case.get("answerability") == "answerable",
            question_type=case.get("primary_type"),
            selected_raw=selected,
            selected_source=result_path,
            attempts=[
                {"round": "formal-unified-contract", "source": rel(result_path), "status": row.get("status")},
                {"round": "formal-qa-split-artifacts", "source": rel(base / "qa"), "status": row.get("status")},
            ],
            retrieval={
                "chunks": row.get("chunks") or [],
                "citations": row.get("citations") or [],
                "retrieval_latency_ms": row.get("retrieval_latency_ms"),
                "generation_latency_ms": row.get("generation_latency_ms"),
            },
        )
        results.append(record)
        inputs.append(judge_input(record, "lenovo-bench-fastgpt-contract-v1"))
        judge = row.get("judge") or {}
        judgements.append({
            "id": identifier,
            "status": "valid" if judge.get("status") == "success" else "invalid",
            "judge_contract": "lenovo-bench-fastgpt-contract-v1",
            "judge": judge,
            "source": rel(result_path),
        })
    source_metrics = read_json(metrics_path)
    project_metrics = read_json(project_metrics_path)
    metrics = {
        "dataset": "Lenovo-bench",
        "score_pass": {"mode": "reaggregate_unified_contract_judgements", "judge_invocations": 0, "scored_at": now()},
        "headline": source_metrics,
        "project_self_score": project_metrics,
        "recomputed_checks": {
            "questions": len(results),
            "query_ok_n": sum(ok_status(row.get("status")) for row in results),
            "judge_valid_n": sum(row["status"] == "valid" for row in judgements),
        },
        "validation": {
            "formal_question_count": len(results) == 60,
            "formal_judge_count": len(judgements) == 60,
            "unified_contract_is_selected": True,
            "project_self_score_preserved": True,
        },
    }
    sources = [
        source_file_summary(result_path, lambda row: str(row.get("question_id") or "")),
        source_file_summary(judge_path, lambda row: str(row.get("question_id") or "")),
        {"path": rel(metrics_path), "kind": "formal_unified_metrics"},
        {"path": rel(project_metrics_path), "kind": "project_self_metrics"},
        {"path": rel(base / "qa/20260812-235334.713/results.jsonl"), "kind": "initial_split_results"},
        {"path": rel(base / "qa-text-resume/20260813-000322.852/results.jsonl"), "kind": "initial_split_results"},
        {"path": rel(base / "qa-visual/20260813-001353.230/results.jsonl"), "kind": "initial_split_results"},
    ]
    return finish_dataset(
        out,
        dataset="lenovo-bench",
        results=results,
        inputs=inputs,
        judgements=judgements,
        judge_attempts=[{"source": rel(judge_path), "attempt_index": index, **row} for index, row in enumerate(judge_attempt_rows, start=1)],
        metrics=metrics,
        sources=sources,
        notes=[
            "The formal 60-question unified FastGPT contract is the selected score contract; the project-self evaluation metrics are preserved separately because they use different denominators and claim rules.",
            "The unified contract has 60 final results and 60 valid judges; duplicate/error judge attempts for q068-q075 remain in judge-attempts.jsonl.",
            "Gold was author-reviewed with automated checks rather than independently dual-reviewed; retain that caveat when interpreting the score.",
        ],
    )


def build(out: Path, overwrite: bool) -> dict[str, Any]:
    if out.exists() and any(out.iterdir()) and not overwrite:
        raise SystemExit(f"output exists and is non-empty; pass --overwrite to regenerate: {out}")
    out.mkdir(parents=True, exist_ok=True)
    dataset_summaries = {
        "wikieval": consolidate_wikieval(out),
        "mmdocir": consolidate_mmdocir(out),
        "docbench": consolidate_docbench(out),
        "enterpriserag-bench": consolidate_enterprise(out),
        "lenovo-bench": consolidate_lenovo(out),
    }
    summary = {
        "schema": "moi-final-results-manifest-v1",
        "created_at": now(),
        "root": rel(out),
        "dataset_order": list(dataset_summaries),
        "score_policy": {
            "mode": "final_reaggregation_of_frozen_local_artifacts",
            "new_provider_calls": 0,
            "canonical_rule": "one record per question; preserve all attempts; unresolved failures remain in full denominator",
        },
        "datasets": dataset_summaries,
    }
    write_json(out / "final-score-summary.json", summary)
    write_json(out / "manifest.json", summary)
    readme = """# MOI final results (2026-08-17)

This directory contains one judge-ready folder per dataset:

- `wikieval/`
- `mmdocir/`
- `docbench/`
- `enterpriserag-bench/`
- `lenovo-bench/`

Use each dataset's `judge-input.jsonl` as the direct input to a judge.  The
corresponding `results.jsonl` preserves the selected answer/context together
with per-question attempt provenance.  `final-score-summary.json` records the
post-consolidation score pass and denominator checks.

The score pass is a deterministic re-aggregation of already generated local
per-question results and judge artifacts.  It intentionally made zero new
provider calls.  It therefore does not claim a new LLM judgment where a source
dataset had no per-question judge file; those cases are labelled in the
dataset-level `metrics.json` and README.
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    summary = build(out, args.overwrite)
    print(json.dumps({"root": summary["root"], "datasets": {key: value["questions"] for key, value in summary["datasets"].items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
