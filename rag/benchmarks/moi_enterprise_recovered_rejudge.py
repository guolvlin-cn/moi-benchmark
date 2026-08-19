#!/usr/bin/env python3
"""Aggregate recovered EnterpriseRAG-Bench answers and run an adapted fact judge."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import moi_rag_benchmark as legacy  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    os.replace(temporary, path)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))]


def load_history(run: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    questions = read_jsonl(run / "questions.jsonl")
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted((run / "results").rglob("results.jsonl")):
        for row in read_jsonl(path):
            qid = str((row.get("case") or {}).get("id") or "")
            if qid:
                history[qid].append(row)
    initial = [history[str(question["id"])][0] for question in questions]
    recovered = []
    attempts = {}
    for question in questions:
        qid = str(question["id"])
        attempts[qid] = len(history[qid])
        success = next((row for row in history[qid] if row.get("status") == "ok"), None)
        if success is None:
            raise RuntimeError(f"no successful recovered result for {qid}")
        recovered.append(success)
    return initial, recovered, attempts


def parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.S)
    value = json.loads(match.group(0) if match else text)
    if not isinstance(value, dict):
        raise ValueError("judge response is not an object")
    return value


def load_environment() -> dict[str, str]:
    environment = os.environ.copy()
    legacy.load_dotenv(ROOT / ".env", environment)
    legacy.load_dotenv(ROOT / ".local-services/providers/qianfan.env", environment)
    return environment


def judge_row(row: dict[str, Any], environment: dict[str, str]) -> dict[str, Any]:
    case = row.get("case") or {}
    metadata = case.get("metadata") or {}
    facts = [str(item) for item in metadata.get("answer_facts") or []]
    prompt = {
        "task": "Evaluate one EnterpriseRAG-Bench answer against the reference and atomic answer facts. Return strict JSON only.",
        "rules": [
            "fact_coverage must contain one binary 0/1 entry per answer_fact in order.",
            "correctness is 1 only if the answer satisfies the reference answer without a material contradiction or swapped version/value.",
            "For info_not_found questions, info_not_found_correct is 1 only when the answer clearly says the documents cannot fully answer the query and does not guess the missing information.",
            "unsupported_completion is 1 if the answer adds a material factual assertion unsupported by the reference/facts; otherwise 0.",
        ],
        "question": case.get("question"),
        "question_type": metadata.get("question_type"),
        "reference_answer": metadata.get("reference_answer"),
        "answer_facts": facts,
        "candidate_answer": row.get("answer"),
        "output_schema": {
            "fact_coverage": "array of 0/1",
            "correctness": "0/1",
            "info_not_found_correct": "0/1/null",
            "unsupported_completion": "0/1",
            "rationale": "short string",
        },
    }
    last_error = ""
    for attempt in range(3):
        try:
            raw = legacy.openai_chat(
                environment,
                environment.get("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2"),
                environment.get("QIANFAN_LLM_MODEL", "deepseek-v4-flash"),
                [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
                timeout=300,
                api_key_env="QIANFAN_API_KEY",
            )
            result = parse_json(raw)
            coverage = result.get("fact_coverage")
            if not isinstance(coverage, list) or len(coverage) != len(facts):
                raise ValueError("JUDGE_FACT_COVERAGE_LENGTH")
            result.update({"status": "success", "raw": raw})
            return result
        except Exception as exc:
            last_error = str(exc)
            if "429" in last_error and attempt < 2:
                time.sleep(15 * (attempt + 1))
    # A handful of completeness questions contain several dozen atomic facts.
    # Some judge responses truncate the coverage array even when the HTTP call
    # succeeds. Preserve the same binary contract while batching only the fact
    # list; combine coverage in original order and use strict conjunction for
    # overall correctness.
    if facts and "JUDGE_FACT_COVERAGE_LENGTH" in last_error:
        parts: list[dict[str, Any]] = []
        combined: list[int] = []
        try:
            for start in range(0, len(facts), 10):
                batched = dict(prompt)
                batched["answer_facts"] = facts[start:start + 10]
                batched["batch"] = {"start_index": start, "total_facts": len(facts)}
                raw = legacy.openai_chat(
                    environment,
                    environment.get("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2"),
                    environment.get("QIANFAN_LLM_MODEL", "deepseek-v4-flash"),
                    [{"role": "user", "content": json.dumps(batched, ensure_ascii=False)}],
                    timeout=300,
                    api_key_env="QIANFAN_API_KEY",
                )
                result = parse_json(raw)
                coverage = result.get("fact_coverage")
                expected = len(facts[start:start + 10])
                if not isinstance(coverage, list) or len(coverage) != expected:
                    raise ValueError("JUDGE_BATCHED_FACT_COVERAGE_LENGTH")
                combined.extend(int(bool(value)) for value in coverage)
                parts.append(result)
            return {
                "status": "success",
                "fact_coverage": combined,
                "correctness": int(all(bool(part.get("correctness")) for part in parts)),
                "info_not_found_correct": None,
                "unsupported_completion": int(any(bool(part.get("unsupported_completion")) for part in parts)),
                "rationale": " | ".join(str(part.get("rationale") or "") for part in parts),
                "batched_fact_judge": True,
            }
        except Exception as exc:
            last_error = str(exc)
    return {"status": "error", "error": last_error}


def retrieval_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, list[float]] = defaultdict(list)
    recalls = []; complete = []; extras = []
    for row in rows:
        metadata = (row.get("case") or {}).get("metadata") or {}
        gold = set(str(value) for value in metadata.get("gold_file_ids") or [])
        got = [str(chunk.get("file_id") or "") for chunk in (row.get("chunks") or [])[:10]]
        got_set = {value for value in got if value}
        if gold:
            recall = len(gold & got_set) / len(gold)
            recalls.append(recall)
            complete.append(float(gold <= got_set))
            extras.append(float(len(got_set - gold)))
            by_type[str(metadata.get("question_type") or "unknown")].append(recall)
    latency = [float(row.get("retrieval_latency_ms") or 0) for row in rows]
    e2e = [float(row.get("retrieval_latency_ms") or 0) + float(row.get("generation_latency_ms") or 0) for row in rows]
    return {
        "doc_recall_at_10": sum(recalls) / len(recalls),
        "doc_recall_valid_n": len(recalls),
        "complete_evidence_set_recall_at_10": sum(complete) / len(complete),
        "invalid_extra_docs_mean": sum(extras) / len(extras),
        "retrieval_latency_ms": {"p50": percentile(latency, .5), "p95": percentile(latency, .95)},
        "e2e_latency_ms": {"p50": percentile(e2e, .5), "p95": percentile(e2e, .95)},
        "doc_recall_at_10_by_type": {key: sum(values)/len(values) for key, values in by_type.items()},
    }


def infrastructure_failure_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("status") == "ok":
            continue
        error = str(row.get("error") or "")
        if "ModelArts.81006" in error:
            category = "provider_resource_frozen"
        elif "context deadline exceeded" in error:
            category = "timeout"
        elif "bad connection" in error or "invalid connection" in error:
            category = "database_connection"
        elif "context canceled" in error:
            category = "request_context_canceled"
        else:
            category = "other_infrastructure_error"
        counts[category] += 1
    return dict(counts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run = args.run.resolve(); output = args.output.resolve()
    initial, recovered, attempts = load_history(run)
    environment = load_environment()
    judge_path = output / "judgements.jsonl"
    existing = {row["id"]: row for row in read_jsonl(judge_path)} if judge_path.exists() else {}
    pending = [row for row in recovered if existing.get(str((row.get("case") or {}).get("id")), {}).get("judge", {}).get("status") != "success"]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(judge_row, row, environment): row for row in pending}
        for index, future in enumerate(as_completed(futures), 1):
            row = futures[future]; qid = str((row.get("case") or {}).get("id"))
            record = {"id": qid, "judge": future.result()}
            append_jsonl(judge_path, record); existing[qid] = record
            print(f"judge {index}/{len(pending)} id={qid} status={record['judge']['status']}", flush=True)
    ledgers = []
    for row in recovered:
        qid = str((row.get("case") or {}).get("id"))
        ledgers.append({"id": qid, "result": row, "judge": existing.get(qid, {}).get("judge", {"status": "error", "error": "missing"}), "attempts": attempts[qid]})
    valid = [item for item in ledgers if item["judge"].get("status") == "success"]
    correctness = [int(bool(item["judge"].get("correctness"))) for item in valid]
    completeness = []
    aggregate = []
    for item in valid:
        coverage = [int(bool(value)) for value in item["judge"].get("fact_coverage") or []]
        value = sum(coverage) / len(coverage) if coverage else 0.0
        completeness.append(value)
        aggregate.append(value * int(bool(item["judge"].get("correctness"))))
    info = [item for item in valid if str(((item["result"].get("case") or {}).get("metadata") or {}).get("question_type")) == "info_not_found"]
    strict_info = [item for item in info if bool(item["judge"].get("info_not_found_correct")) and not bool(item["judge"].get("unsupported_completion"))]
    raw_initial_success = sum(row.get("status") == "ok" for row in initial)
    infrastructure_failures = infrastructure_failure_breakdown(initial)
    api_retry_merged_n = len(recovered) - raw_initial_success
    metrics = {
        "scope": "CURRENT_CORPUS_ADAPTED representative 722-document slice; not the official ~511,962-document corpus",
        "questions": len(recovered),
        "availability_policy": "API/infrastructure retries are merged into the original question result and are not counted as MOI failures",
        "initial_success": len(recovered),
        "initial_availability": 1.0,
        "raw_transport_initial_success": raw_initial_success,
        "raw_transport_initial_availability": raw_initial_success / len(initial),
        "api_retry_merged_n": api_retry_merged_n,
        "api_retry_failure_breakdown": infrastructure_failures,
        "recovered_success": len(recovered),
        "recovered_availability": 1.0,
        "retry_recovered_n": api_retry_merged_n,
        "judge_valid_n": len(valid),
        "judge_failed_n": len(ledgers) - len(valid),
        "correctness": sum(correctness)/len(correctness) if correctness else None,
        "completeness": sum(completeness)/len(completeness) if completeness else None,
        "dataset_aggregate_adapted": sum(aggregate)/len(aggregate) if aggregate else None,
        "strict_info_not_found_success": len(strict_info)/len(info) if info else None,
        "strict_info_not_found_pass": len(strict_info),
        "strict_info_not_found_total": len(info),
        "unsupported_completion_rate": sum(bool(item["judge"].get("unsupported_completion")) for item in valid)/len(valid) if valid else None,
        "tdas": None,
        "tdas_reason": "N/A: required claim-to-citation binding was not scored",
        "retrieval": retrieval_metrics(recovered),
        "judge_contract": "project-adapted EnterpriseRAG answer_facts binary coverage; Qianfan deepseek-v4-flash",
    }
    write_jsonl(output / "recovered-results.jsonl", recovered)
    write_jsonl(output / "qa-ledger.jsonl", ledgers)
    write_json(output / "metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
