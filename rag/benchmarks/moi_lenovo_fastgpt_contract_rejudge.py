#!/usr/bin/env python3
"""Rejudge MOI Lenovo-Bench results with the exact FastGPT judge contract."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local-rag-platforms/scripts/benchmarks/lenovo"))

from benchmarks import moi_rag_benchmark as legacy  # noqa: E402
from lenovo_bench_fastgpt_eval import parse_json_object, score_rows  # noqa: E402

CITATION_RE = re.compile(r"\[([^\[\]\n]+?\.pdf)\s+(?:p\.?|page\s*)(\d+)\]", re.IGNORECASE)
GOLD_ROOT = ROOT / "datasets/lenovo-bench/moi-corpus-100q-v1"


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


def load_environment() -> dict[str, str]:
    environment = os.environ.copy()
    legacy.load_dotenv(ROOT / ".env", environment)
    legacy.load_dotenv(ROOT / ".local-services/providers/qianfan.env", environment)
    return environment


def convert_results(paths: list[Path]) -> list[dict[str, Any]]:
    gold = {row["question_id"]: row for row in read_jsonl(GOLD_ROOT / "questions.formal.jsonl")}
    by_id: dict[str, dict[str, Any]] = {}
    for path in paths:
        for raw in read_jsonl(path):
            qid = str((raw.get("case") or {}).get("id"))
            if not qid or raw.get("status") != "ok":
                continue
            answer = str(raw.get("answer") or "")
            by_id[qid] = {
                "ordinal": 0,
                "question_id": qid,
                "case": gold[qid],
                "status": "success",
                "answer": answer,
                "retrieval_latency_ms": float(raw.get("retrieval_latency_ms") or 0),
                "generation_latency_ms": float(raw.get("generation_latency_ms") or 0),
                "chunks": [
                    {
                        "rank": index,
                        "source_file": Path(str(chunk.get("file_name") or "")).name,
                        "pdf_page": int(chunk.get("page_number") or 0),
                        "content": str(chunk.get("content") or ""),
                    }
                    for index, chunk in enumerate(raw.get("chunks") or [], 1)
                ],
                "citations": [
                    {"source_file": name, "pdf_page": int(page)}
                    for name, page in CITATION_RE.findall(answer)
                ],
            }
    ordered = []
    for ordinal, qid in enumerate(gold, 1):
        if qid in by_id:
            by_id[qid]["ordinal"] = ordinal
            ordered.append(by_id[qid])
    if len(ordered) != 60:
        raise RuntimeError(f"expected 60 successful MOI results, found {len(ordered)}")
    return ordered


def judge_row(row: dict[str, Any], environment: dict[str, str]) -> dict[str, Any]:
    case = row["case"]
    prompt = {
        "task": "Evaluate one RAG answer against atomic Gold claims and the actually retrieved context.",
        "rules": [
            "Use only the supplied Gold/reference and retrieved context.",
            "gold_claim_coverage must contain one 0/1 entry per Gold claim in order.",
            "A material answer claim is supported only if entailed by retrieved_context.",
            "For unanswerable items, refusal_correct=1 only for a clear refusal without factual guessing.",
            "Return strict JSON only; scores are binary 0 or 1 except counts and null where not applicable.",
        ],
        "question": case["question"],
        "answerability": case["answerability"],
        "reference_answer": case["reference_answer"],
        "accepted_answers": case.get("accepted_answers", []),
        "gold_claims": [claim["text"] for claim in case.get("claims", [])],
        "answer": row["answer"],
        "retrieved_context": [chunk["content"] for chunk in row.get("chunks", [])],
        "output_schema": {
            "gold_claim_coverage": "array of 0/1",
            "material_answer_claim_count": "integer",
            "supported_material_answer_claim_count": "integer",
            "answer_correct": "0/1",
            "answer_complete": "0/1",
            "numeric_unit_correct": "0/1/null",
            "scope_version_correct": "0/1/null",
            "faithfulness": "0/1",
            "answer_relevance": "0/1",
            "refusal_correct": "0/1/null",
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
            result = parse_json_object(raw)
            coverage = result.get("gold_claim_coverage", [])
            if not isinstance(coverage, list) or len(coverage) != len(case.get("claims", [])):
                raise RuntimeError("JUDGE_CLAIM_COVERAGE_LENGTH")
            result.update({"status": "success", "raw": raw})
            return result
        except Exception as exc:
            last_error = str(exc)
            if "429" in last_error and attempt < 2:
                time.sleep(15 * (attempt + 1))
    return {"status": "error", "error": last_error}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    output = args.output.resolve()
    rows = convert_results([path.resolve() for path in args.results])
    environment = load_environment()
    judge_path = output / "judgements.jsonl"
    existing = {row["question_id"]: row for row in read_jsonl(judge_path)} if judge_path.exists() else {}
    pending = [row for row in rows if existing.get(row["question_id"], {}).get("judge", {}).get("status") != "success"]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(judge_row, row, environment): row for row in pending}
        for index, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            record = {"question_id": row["question_id"], "judge": future.result()}
            append_jsonl(judge_path, record)
            existing[row["question_id"]] = record
            print(f"judge {index}/{len(pending)} id={row['question_id']} status={record['judge']['status']}", flush=True)
    for row in rows:
        row["judge"] = existing.get(row["question_id"], {}).get("judge", {"status": "error", "error": "missing"})
    manifest = read_jsonl(GOLD_ROOT / "corpus_manifest.jsonl")
    metrics = score_rows(rows, manifest)
    metrics["judge_contract"] = "lenovo_bench_fastgpt_eval.py exact prompt/schema and score_rows"
    metrics["judge_provider"] = "qianfan"
    metrics["judge_model"] = environment.get("QIANFAN_LLM_MODEL", "deepseek-v4-flash")
    write_jsonl(output / "results.jsonl", rows)
    write_json(output / "metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
