#!/usr/bin/env python3
"""Prepare and audit the frozen MultiHop-RAG MatrixFlow benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUESTION_TYPES = (
    "comparison_query",
    "inference_query",
    "temporal_query",
    "null_query",
)
REFUSAL_PATTERNS = (
    r"\binsufficient\b",
    r"\bnot enough\b",
    r"\bcannot (?:be )?determine",
    r"\bcan't (?:be )?determine",
    r"\bno (?:relevant |sufficient )?(?:information|evidence)\b",
    r"\bdoes not (?:provide|contain|specify|mention)\b",
    r"\bdoes not include\b",
    r"\bnot (?:provided|available|specified|mentioned)\b",
    r"\bunable to (?:answer|determine)\b",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def doc_filename(url: str) -> str:
    return "doc_" + sha256_bytes(url.encode("utf-8"))[:20] + ".txt"


def select_questions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("question_type", ""))].append(row)
    selected: list[dict[str, Any]] = []
    for question_type in QUESTION_TYPES:
        ordered = sorted(
            grouped[question_type],
            key=lambda item: sha256_bytes(str(item["query"]).encode("utf-8")),
        )
        if len(ordered) < 5:
            raise ValueError(f"{question_type} has fewer than five questions")
        selected.extend(ordered[:5])
    return selected


def prepare(args: argparse.Namespace) -> None:
    corpus_path = Path(args.corpus).resolve()
    questions_path = Path(args.questions).resolve()
    output = Path(args.output).resolve()
    corpus_rows = json.loads(corpus_path.read_text(encoding="utf-8"))
    question_rows = json.loads(questions_path.read_text(encoding="utf-8"))
    selected = select_questions(question_rows)
    corpus_dir = output / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)

    corpus_by_url: dict[str, dict[str, Any]] = {}
    corpus_manifest: list[dict[str, Any]] = []
    for row in corpus_rows:
        url = str(row.get("url", "")).strip()
        if not url:
            raise ValueError("corpus row is missing url")
        filename = doc_filename(url)
        body = "\n".join(
            [
                f"Title: {row.get('title') or ''}",
                f"URL: {url}",
                f"Source: {row.get('source') or ''}",
                f"Published at: {row.get('published_at') or ''}",
                f"Author: {row.get('author') or ''}",
                "",
                str(row.get("body") or ""),
            ]
        ).strip() + "\n"
        destination = corpus_dir / filename
        destination.write_text(body, encoding="utf-8")
        record = {
            "filename": filename,
            "url": url,
            "title": row.get("title"),
            "source": row.get("source"),
            "published_at": row.get("published_at"),
            "body_sha256": sha256_bytes(str(row.get("body") or "").encode("utf-8")),
            "ingest_text_sha256": sha256_bytes(body.encode("utf-8")),
        }
        corpus_by_url[url] = record
        corpus_manifest.append(record)

    frozen: list[dict[str, Any]] = []
    dataset: list[dict[str, Any]] = []
    missing_urls: list[dict[str, str]] = []
    for row in selected:
        query = str(row["query"])
        query_hash = sha256_bytes(query.encode("utf-8"))
        evidence = row.get("evidence_list") or []
        relevant_documents: list[str] = []
        for item in evidence:
            url = str(item.get("url", ""))
            document = corpus_by_url.get(url)
            if document:
                relevant_documents.append(document["filename"])
            else:
                missing_urls.append({"query_sha256": query_hash, "url": url})
        relevant_documents = list(dict.fromkeys(relevant_documents))
        question_id = f"{row['question_type']}-{query_hash[:16]}"
        frozen_row = {
            "id": question_id,
            "query_sha256": query_hash,
            "question_type": row["question_type"],
            "query": query,
            "answer": row.get("answer"),
            "evidence_list": evidence,
            "relevant_documents": relevant_documents,
        }
        frozen.append(frozen_row)
        dataset.append(
            {
                "id": question_id,
                "question": query,
                "retrieval_keywords": [query],
                "relevant_documents": relevant_documents,
                "relevant_evidence": [
                    str(item.get("fact") or "") for item in evidence if item.get("fact")
                ],
                "expected_answer_keywords": answer_tokens(str(row.get("answer") or "")),
                "expected_answerable": row["question_type"] != "null_query",
            }
        )

    freeze = {
        "schema_version": "matrixflow-multihop-rag-freeze-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_rule": (
            "group by question_type; sort each group by SHA256(query) ascending; "
            "take 5 from comparison_query, inference_query, temporal_query, null_query"
        ),
        "repeats": 2,
        "question_count": len(frozen),
        "attempt_count": len(frozen) * 2,
        "question_type_counts": {
            question_type: sum(
                item["question_type"] == question_type for item in frozen
            )
            for question_type in QUESTION_TYPES
        },
        "source_inputs": {
            "corpus_path": str(corpus_path),
            "corpus_sha256": sha256_file(corpus_path),
            "questions_path": str(questions_path),
            "questions_sha256": sha256_file(questions_path),
        },
        "selected_questions": frozen,
        "selected_questions_sha256": sha256_bytes(canonical_json(frozen)),
        "missing_evidence_urls": missing_urls,
    }
    write_json(output / "freeze.json", freeze)
    write_json(output / "corpus_manifest.json", {"documents": corpus_manifest})
    write_jsonl(output / "questions.jsonl", dataset)
    write_json(
        output / "prepare_manifest.json",
        {
            "corpus_documents": len(corpus_manifest),
            "questions": len(dataset),
            "missing_evidence_urls": len(missing_urls),
            "freeze_sha256": sha256_file(output / "freeze.json"),
            "questions_jsonl_sha256": sha256_file(output / "questions.jsonl"),
            "corpus_manifest_sha256": sha256_file(output / "corpus_manifest.json"),
        },
    )


def normalize_answer(text: str) -> str:
    return "".join(character for character in text.casefold() if character.isalnum())


def answer_tokens(text: str) -> list[str]:
    return list(
        dict.fromkeys(
            token.casefold()
            for token in re.findall(r"[\w]+", text, flags=re.UNICODE)
            if len(token) > 1
            and token.casefold()
            not in {"the", "and", "for", "with", "from", "that", "this", "was", "were"}
        )
    )


def exact_or_contained_answer(expected: str, answer: str) -> bool:
    expected_normalized = normalize_answer(expected)
    answer_normalized = normalize_answer(answer)
    if not expected_normalized:
        return False
    if expected_normalized == answer_normalized:
        return True
    if len(answer_tokens(expected)) == 1:
        return expected.casefold().strip(" .") in set(answer_tokens(answer))
    return expected_normalized in answer_normalized


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def git_head(path: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def audit(args: argparse.Namespace) -> None:
    prepared = Path(args.prepared).resolve()
    product_run = Path(args.product_run).resolve()
    output = Path(args.output).resolve()
    freeze = json.loads((prepared / "freeze.json").read_text(encoding="utf-8"))
    frozen_by_id = {
        item["id"]: item for item in freeze["selected_questions"]
    }
    results = [
        json.loads(line)
        for line in (product_run / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    judgements: list[dict[str, Any]] = []
    for result in results:
        case_id = result["case"]["id"]
        gold = frozen_by_id[case_id]
        answer = str(result.get("answer") or "")
        expected = str(gold.get("answer") or "")
        tokens = answer_tokens(expected)
        answer_token_set = set(answer_tokens(answer))
        token_hits = [token for token in tokens if token in answer_token_set]
        token_coverage = len(token_hits) / len(tokens) if tokens else 0.0
        exact_or_contained = exact_or_contained_answer(expected, answer)
        null_refusal = any(
            re.search(pattern, answer, flags=re.IGNORECASE)
            for pattern in REFUSAL_PATTERNS
        )
        relevant = set(gold["relevant_documents"])
        retrieved = [chunk.get("file_name") for chunk in result.get("chunks") or []]
        retrieved_relevant = relevant.intersection(retrieved)
        source_recall = (
            len(retrieved_relevant) / len(relevant)
            if relevant
            else None
        )
        is_null = gold["question_type"] == "null_query"
        correctness_pass = null_refusal if is_null else (exact_or_contained or token_coverage >= 0.8)
        total_latency = float(result.get("retrieval_latency_ms") or 0) + float(
            result.get("generation_latency_ms") or 0
        )
        judgements.append(
            {
                "question_id": case_id,
                "question_type": gold["question_type"],
                "repeat": result["repeat"],
                "started_at": result.get("started_at"),
                "ended_at": result.get("ended_at"),
                "status": result.get("status"),
                "error": result.get("error"),
                "answer": answer,
                "gold_answer": expected,
                "normalized_exact_or_contained": exact_or_contained,
                "gold_answer_token_hits": token_hits,
                "gold_answer_token_total": len(tokens),
                "gold_answer_token_coverage": token_coverage,
                "null_refusal_success": null_refusal if is_null else None,
                "correctness_pass": correctness_pass,
                "relevant_source_total": len(relevant),
                "retrieved_relevant_sources": sorted(retrieved_relevant),
                "evidence_source_recall": source_recall,
                "retrieved_contexts": result.get("chunks") or [],
                "retrieval_routes": result.get("routes") or [],
                "retrieval_latency_ms": result.get("retrieval_latency_ms"),
                "generation_latency_ms": result.get("generation_latency_ms"),
                "total_latency_ms": total_latency,
                "structured_citations": None,
                "structured_citations_reason": "STRUCTURED_CITATIONS_UNAVAILABLE",
            }
        )

    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in judgements:
        by_question[item["question_id"]].append(item)
    exact_stable = 0
    outcome_stable = 0
    jaccards: list[float] = []
    for pairs in by_question.values():
        pairs.sort(key=lambda item: item["repeat"])
        if len(pairs) != 2:
            continue
        if normalize_answer(pairs[0]["answer"]) == normalize_answer(pairs[1]["answer"]):
            exact_stable += 1
        if pairs[0]["correctness_pass"] == pairs[1]["correctness_pass"]:
            outcome_stable += 1
        left, right = set(answer_tokens(pairs[0]["answer"])), set(answer_tokens(pairs[1]["answer"]))
        union = left | right
        jaccards.append(len(left & right) / len(union) if union else 1.0)

    successful = [item for item in judgements if item["status"] == "ok"]
    terminal = [
        item
        for item in judgements
        if item.get("started_at") and item.get("ended_at")
    ]
    answerable = [
        item for item in judgements if item["question_type"] != "null_query"
    ]
    nulls = [item for item in judgements if item["question_type"] == "null_query"]
    source_scored = [
        item for item in answerable if item["evidence_source_recall"] is not None
    ]
    latencies = [item["total_latency_ms"] for item in terminal]
    metrics = {
        "schema_version": "matrixflow-multihop-rag-metrics-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "planned_questions": 20,
        "planned_attempts": 40,
        "actual_questions": len(by_question),
        "actual_attempts": len(judgements),
        "availability": {
            "numerator": len(successful),
            "denominator": len(judgements),
            "rate": len(successful) / len(judgements) if judgements else 0.0,
            "errors": len(judgements) - len(successful),
            "error_attempts": [
                {
                    "question_id": item["question_id"],
                    "repeat": item["repeat"],
                    "error": item["error"],
                }
                for item in judgements
                if item["status"] != "ok"
            ],
        },
        "answer_correctness": {
            "pass_numerator": sum(item["correctness_pass"] for item in answerable),
            "denominator": len(answerable),
            "rate": (
                sum(item["correctness_pass"] for item in answerable) / len(answerable)
                if answerable
                else 0.0
            ),
            "normalized_exact_or_contained_numerator": sum(
                item["normalized_exact_or_contained"] for item in answerable
            ),
            "mean_gold_answer_token_coverage": (
                statistics.fmean(
                    item["gold_answer_token_coverage"] for item in answerable
                )
                if answerable
                else 0.0
            ),
            "pass_rule": "normalized exact/contained OR gold-answer token coverage >= 0.8",
        },
        "evidence_source_retrieval_recall": {
            "macro_mean": (
                statistics.fmean(item["evidence_source_recall"] for item in source_scored)
                if source_scored
                else None
            ),
            "full_recall_attempts": sum(
                item["evidence_source_recall"] == 1.0 for item in source_scored
            ),
            "denominator": len(source_scored),
            "basis": "corpus URL mapped to deterministic source filename",
        },
        "null_query_refusal": {
            "numerator": sum(bool(item["null_refusal_success"]) for item in nulls),
            "denominator": len(nulls),
            "rate": (
                sum(bool(item["null_refusal_success"]) for item in nulls) / len(nulls)
                if nulls
                else 0.0
            ),
        },
        "latency_ms": {
            "denominator": len(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "scope": "terminal attempts; retrieval plus generation",
        },
        "repeat_stability": {
            "normalized_answer_exact_match_questions": exact_stable,
            "correctness_outcome_match_questions": outcome_stable,
            "denominator": len(by_question),
            "mean_answer_token_jaccard": statistics.fmean(jaccards) if jaccards else None,
        },
        "trace": {
            "available_attempts": sum(bool(item["retrieved_contexts"]) for item in judgements),
            "denominator": len(judgements),
            "includes_rank_content_score_routes": True,
        },
        "citations": {
            "value": None,
            "reason": "STRUCTURED_CITATIONS_UNAVAILABLE",
            "note": "answers may contain filename text, but the controlled generator emits no structured citation object",
        },
    }
    write_jsonl(output / "judgements.jsonl", judgements)
    write_json(output / "metrics.json", metrics)
    benchmark_root = Path(__file__).resolve().parents[2]
    matrixflow_root = benchmark_root.parents[1] / "matrixflow"
    write_json(
        output / "run_metadata.json",
        {
            "schema_version": "matrixflow-multihop-rag-run-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_started_at": min(
                item["started_at"] for item in judgements if item.get("started_at")
            ),
            "run_ended_at": max(
                item["ended_at"] for item in judgements if item.get("ended_at")
            ),
            "pipeline_command": [
                "python3",
                "local_matrixflow_rag.py",
                "pipeline",
                "--config",
                str(Path(args.config).resolve()),
                "--source",
                str((prepared / "corpus").resolve()),
                "--dataset",
                str((prepared / "questions.jsonl").resolve()),
                "--run",
                str(product_run.parent.resolve()),
                "--max-hits",
                "10",
                "--repeats",
                "2",
                "--force",
            ],
            "matrixflow_git_commit": git_head(matrixflow_root),
            "benchmark_git_commit": git_head(benchmark_root),
            "benchmark_script_sha256": sha256_file(Path(__file__).resolve()),
            "benchmark_go_source_sha256": sha256_file(
                Path(__file__).resolve().with_name("main.go")
            ),
            "config_path": str(Path(args.config).resolve()),
            "config_sha256": sha256_file(Path(args.config).resolve()),
            "freeze_sha256": sha256_file(prepared / "freeze.json"),
            "product_run": str(product_run),
            "initial_attempt_policy": "no retry; product/API failures remain in denominator",
        },
    )
    write_report(
        output / "report.md",
        freeze,
        metrics,
        json.loads(Path(args.config).read_text(encoding="utf-8")),
        prepared,
        product_run,
    )
    artifact_hashes = {}
    for path in sorted(
        [Path(args.config).resolve()]
        + list(prepared.glob("*.json"))
        + list(prepared.glob("*.jsonl"))
        + list(product_run.glob("*.json"))
        + list(product_run.glob("*.jsonl"))
        + [
            output / "judgements.jsonl",
            output / "metrics.json",
            output / "run_metadata.json",
            output / "report.md",
        ]
    ):
        artifact_hashes[str(path)] = sha256_file(path)
    write_json(output / "artifact_hashes.json", artifact_hashes)


def format_rate(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({numerator / denominator:.1%})" if denominator else "0/0"


def write_report(
    path: Path,
    freeze: dict[str, Any],
    metrics: dict[str, Any],
    config: dict[str, Any],
    prepared: Path,
    product_run: Path,
) -> None:
    availability = metrics["availability"]
    correctness = metrics["answer_correctness"]
    source = metrics["evidence_source_retrieval_recall"]
    refusal = metrics["null_query_refusal"]
    latency = metrics["latency_ms"]
    stability = metrics["repeat_stability"]
    error_note = "；".join(
        f'{item["question_id"]} repeat {item["repeat"]}: {item["error"].splitlines()[0]}'
        for item in availability["error_attempts"]
    ) or "无"
    ingest = json.loads((product_run / "ingest-state.json").read_text(encoding="utf-8"))
    text = f"""# MatrixFlow MultiHop-RAG 本地基准报告

## 范围与冻结

- 语料：MultiHop-RAG `corpus.json` 的 609 篇正文，直接写入文本并摄取，未经过文档解析。
- 题目：按 `question_type` 分组、组内按 `SHA256(query)` 升序，各取 5 题；共 20 题，冻结后未改题。
- 运行：每题 2 次，共 40 次；MatrixFlow `SearchRAGChunks` + 检索上下文受控生成。
- 配置：embedding `{config["embedding"]["model"]}`（{config["embedding"]["dimension"]} 维），generation `{config["generation"]["model"]}`，chunk {config["chunk_size"]}/overlap {config["chunk_overlap"]}，max hits 10。
- 建库：{len(ingest["documents"])} documents / {len(ingest["chunks"])} chunks；专用向量表 `{ingest["vector_table"]}`。
- 冻结哈希：`{freeze["selected_questions_sha256"]}`。

## 核心指标

- 可用性：{format_rate(availability["numerator"], availability["denominator"])}；错误 {availability["errors"]}（{error_note}）。
- 回答正确性：{format_rate(correctness["pass_numerator"], correctness["denominator"])}；判定为规范化答案完整包含，或 Gold 答案 token 覆盖率 ≥ 0.8；平均 token 覆盖率 {correctness["mean_gold_answer_token_coverage"]:.3f}。
- Evidence-source retrieval recall：宏平均 {source["macro_mean"] if source["macro_mean"] is not None else "N/A"}；完整召回 {source["full_recall_attempts"]}/{source["denominator"]}。来源按 evidence URL 映射到确定性语料文件名。
- `null_query` 拒答成功：{format_rate(refusal["numerator"], refusal["denominator"])}。
- 端到端延迟（检索+生成，terminal attempts）：P50 {latency["p50"]:.2f} ms，P95 {latency["p95"]:.2f} ms。
- 重复稳定性：规范化答案完全一致 {stability["normalized_answer_exact_match_questions"]}/{stability["denominator"]}；正确性结果一致 {stability["correctness_outcome_match_questions"]}/{stability["denominator"]}；答案 token Jaccard 均值 {stability["mean_answer_token_jaccard"]:.3f}。

## 可审计性与限制

- 每次尝试保存开始/结束时间、状态、错误、原始答案、检索 routes、上下文、rank、score 和 chunk ID。
- 结构化 citations：N/A（`STRUCTURED_CITATIONS_UNAVAILABLE`）；生成文本中的文件名不冒充结构化 citation。
- 本报告是固定 20 题、两次重复的描述性本地基准，不做显著性或产品级泛化结论。
- 输入、输出及配置哈希见 `artifact_hashes.json`；冻结输入见 `{prepared}`；原始运行见 `{product_run}`。
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--corpus", required=True)
    prepare_parser.add_argument("--questions", required=True)
    prepare_parser.add_argument("--output", required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--prepared", required=True)
    audit_parser.add_argument("--product-run", required=True)
    audit_parser.add_argument("--output", required=True)
    audit_parser.add_argument("--config", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        audit(args)


if __name__ == "__main__":
    main()
