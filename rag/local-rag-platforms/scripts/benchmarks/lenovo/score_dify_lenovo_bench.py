#!/usr/bin/env python3
"""Score a completed generic-Dify Lenovo-Bench formal run.

The generic runner owns ingestion, retrieval, QA, and its durable ledgers. This
post-processor adds the Lenovo-Bench contract: page/document evidence recall,
evidence-set completion, citations, answerability, and Qianfan-judged claims.
It is resumable through a judge ledger and never changes the runner ledger.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lenovo_bench_fastgpt_eval import score_rows  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "item"


def normalize_text(value: Any) -> str:
    text = str(value or "").casefold()
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)


def extract_answer(body: Any) -> str:
    if isinstance(body, dict):
        if body.get("answer"):
            return str(body["answer"])
        choices = body.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            return str(message.get("content") or message.get("reasoning_content") or "")
        for key in ("content", "text", "answer_text"):
            if body.get(key):
                return str(body[key])
    return ""


def artifact_response(path: Path) -> Any:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return (record.get("response") or {}).get("body") if isinstance(record, dict) else None


def latest_artifact(http_root: Path, operation: str, question_id: str) -> Path | None:
    matches = sorted(http_root.glob(f"*-{operation}-{safe_name(question_id)}.json"))
    return matches[-1] if matches else None


def source_name(value: Any) -> str:
    name = str(value or "")
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name


def hit_content(hit: Any) -> str:
    if not isinstance(hit, dict):
        return str(hit or "")
    segment = hit.get("segment") if isinstance(hit.get("segment"), dict) else hit
    return str(segment.get("content") or segment.get("q") or hit.get("content") or "")


def hit_source_file(hit: Any) -> str:
    if not isinstance(hit, dict):
        return ""
    segment = hit.get("segment") if isinstance(hit.get("segment"), dict) else hit
    document = segment.get("document") if isinstance(segment.get("document"), dict) else {}
    return source_name(document.get("name") or segment.get("source_file") or segment.get("file_name") or hit.get("sourceName"))


def infer_page(content: str, file_name: str, pages_by_file: dict[str, list[dict[str, Any]]]) -> int:
    candidates = pages_by_file.get(file_name, []) or [page for rows in pages_by_file.values() for page in rows]
    if not candidates or not content.strip():
        return 0
    normalized_content = normalize_text(content)
    probes = [normalized_content[:size] for size in (180, 120, 80, 50) if len(normalized_content) >= size]
    for probe in probes:
        if not probe:
            continue
        for page in candidates:
            if probe in normalize_text(page.get("content")):
                return int(page.get("pdf_page", 0) or 0)
    tokens = [token for token in re.findall(r"[\w]{4,}", str(content).casefold())[:80]]
    if not tokens:
        return 0
    best_page, best_score = 0, 0
    for page in candidates:
        page_text = str(page.get("content", "")).casefold()
        score = sum(page_text.count(token) for token in tokens)
        if score > best_score:
            best_page, best_score = int(page.get("pdf_page", 0) or 0), score
    return best_page


def retrieval_chunks(body: Any, pages_by_file: dict[str, list[dict[str, Any]]], top_k: int) -> list[dict[str, Any]]:
    records = body.get("records", []) if isinstance(body, dict) else []
    chunks: list[dict[str, Any]] = []
    for rank, hit in enumerate(records[:top_k], start=1):
        file_name = hit_source_file(hit)
        content = hit_content(hit)
        chunks.append(
            {
                "rank": rank,
                "source_file": file_name,
                "pdf_page": infer_page(content, file_name, pages_by_file),
                "content": content,
                "score": (hit.get("score") if isinstance(hit, dict) else None),
                "raw_locator": {
                    "document_id": ((hit.get("segment") or {}).get("document_id") if isinstance(hit, dict) and isinstance(hit.get("segment"), dict) else None),
                },
            }
        )
    return chunks


CITATION_RE = re.compile(r"\[([^\[\]\n]+?\.pdf)\s+(?:p\.?|page\s*)(\d+)\]", re.IGNORECASE)


def citations_from_answer(answer: str) -> list[dict[str, Any]]:
    return [{"source_file": source_name(name), "pdf_page": int(page)} for name, page in CITATION_RE.findall(answer)]


def parse_json_object(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("JUDGE_RESPONSE_NO_JSON_OBJECT")
    result = json.loads(value[start : end + 1])
    if not isinstance(result, dict):
        raise ValueError("JUDGE_RESPONSE_NOT_OBJECT")
    return result


class QianfanJudge:
    def __init__(self, run_root: Path, env: dict[str, str], model_override: str = ""):
        self.run_root = run_root
        self.key = env.get("QIANFAN_API_KEY", "")
        self.base_url = (env.get("QIANFAN_BASE_URL") or "https://qianfan.baidubce.com/v2").rstrip("/")
        self.model = model_override or env.get("QIANFAN_LLM_MODEL", "deepseek-v4-flash")
        self.artifact_root = run_root / "judge-http"

    def judge(self, case: dict[str, Any], answer: str, contexts: list[str], question_id: str) -> dict[str, Any]:
        if not self.key:
            return {"status": "unsupported", "error": "QIANFAN_API_KEY_MISSING"}
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
            "answer": answer,
            "retrieved_context": contexts,
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
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
        }
        last_error = ""
        for attempt in range(1, 4):
            request = Request(
                self.base_url + "/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=240) as response:
                    body = json.loads(response.read().decode("utf-8", errors="replace"))
                self.artifact_root.mkdir(parents=True, exist_ok=True)
                write_json(self.artifact_root / f"{safe_name(question_id)}.json", {"question_id": question_id, "model": self.model, "attempt": attempt, "response": body})
                choices = body.get("choices", []) if isinstance(body, dict) else []
                content = ""
                if choices and isinstance(choices[0], dict):
                    message = choices[0].get("message") or {}
                    content = str(message.get("content") or message.get("reasoning_content") or "")
                result = parse_json_object(content)
                coverage = result.get("gold_claim_coverage", [])
                if not isinstance(coverage, list) or len(coverage) != len(case.get("claims", [])):
                    raise ValueError("JUDGE_CLAIM_COVERAGE_LENGTH")
                result["status"] = "success"
                return result
            except HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:1000]
                last_error = f"HTTP_{exc.code}:{detail}"
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    break
            except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
            if attempt < 3:
                time.sleep(10 * attempt if "429" in last_error else 2**attempt)
        return {"status": "error", "error": last_error}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--audit-pages", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--judge-model", default="")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    package = args.package.expanduser().resolve()
    pages_path = args.audit_pages.expanduser().resolve()
    questions = {str(row["question_id"]): row for row in read_jsonl(package / "questions.jsonl")}
    raw_manifest = read_jsonl(package / "corpus.jsonl")
    manifest: list[dict[str, Any]] = []
    for row in raw_manifest:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        source_file = source_name(
            row.get("source_file") or metadata.get("source_file") or row.get("path")
        )
        pdf_pages = row.get("pdf_pages") or row.get("pages") or metadata.get("pages") or 0
        manifest.append(
            {
                **row,
                "doc_id": row.get("doc_id") or row.get("id"),
                "source_file": source_file,
                "pdf_pages": int(pdf_pages),
            }
        )
    pages_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in read_jsonl(pages_path):
        pages_by_file[str(page.get("source_file", ""))].append(page)
    http_root = run_root / "http"
    retrieval_ledger = [row for row in read_jsonl(run_root / "terminal-ledger.jsonl") if row.get("stage") == "retrieval"]
    qa_ledger = [row for row in read_jsonl(run_root / "terminal-ledger.jsonl") if row.get("stage") == "qa"]
    qa_by_id = {str(row.get("question_id")): row for row in qa_ledger}
    rows: list[dict[str, Any]] = []
    for question_id, case in questions.items():
        qa = qa_by_id.get(question_id, {})
        answer = str(qa.get("answer", ""))
        retrieval_artifact = latest_artifact(http_root, "dify-retrieval", question_id)
        retrieval_body = artifact_response(retrieval_artifact) if retrieval_artifact else None
        qa_artifact = latest_artifact(http_root, "dify-qa", question_id)
        qa_body = artifact_response(qa_artifact) if qa_artifact else None
        if not answer and qa_body is not None:
            answer = extract_answer(qa_body)
        chunks = retrieval_chunks(retrieval_body, pages_by_file, args.top_k) if retrieval_body is not None else []
        rows.append(
            {
                "question_id": question_id,
                "case": case,
                "answer": answer,
                "status": "success" if qa.get("status") in {"SUCCESS", "EMPTY"} and answer else str(qa.get("status", "not_recorded")).lower(),
                "chunks": chunks,
                "citations": citations_from_answer(answer),
                "retrieval_latency_ms": next((x.get("latency_ms") for x in retrieval_ledger if x.get("question_id") == question_id), None),
                "generation_latency_ms": qa.get("latency_ms"),
                "qa_artifact": str(qa_artifact.relative_to(run_root)) if qa_artifact else None,
                "retrieval_artifact": str(retrieval_artifact.relative_to(run_root)) if retrieval_artifact else None,
            }
        )

    judge_ledger_path = run_root / "lenovo-judge-ledger.jsonl"
    judged_by_id = {str(row.get("question_id")): row for row in read_jsonl(judge_ledger_path)}
    if not args.skip_judge:
        env = parse_env(ROOT / ".env")
        env.update({key: value for key, value in os.environ.items() if key.startswith("QIANFAN_") and value})
        judge = QianfanJudge(run_root, env, args.judge_model)
        for row in rows:
            question_id = row["question_id"]
            if row["status"] != "success":
                continue
            prior = judged_by_id.get(question_id)
            if isinstance(prior, dict) and prior.get("judge", {}).get("status") == "success":
                row["judge"] = prior["judge"]
                continue
            row["judge"] = judge.judge(row["case"], row["answer"], [chunk["content"] for chunk in row["chunks"]], question_id)
            judged_by_id[question_id] = {"question_id": question_id, "judge": row["judge"]}
            write_jsonl(judge_ledger_path, list(judged_by_id.values()))

    completed_rows = [row for row in rows if row["status"] == "success"]
    metrics = score_rows(completed_rows, manifest)
    metrics.update(
        {
            "schema": "lenovo-bench-dify-posthoc-metrics-v1",
            "dataset": "lenovo-bench",
            "split": "formal",
            "system": "dify_local",
            "run_root": str(run_root),
            "planned_questions": len(questions),
            "successful_questions": len(completed_rows),
            "failed_or_missing_questions": len(questions) - len(completed_rows),
            "success_rate": len(completed_rows) / len(questions) if questions else None,
            "judge_skipped": bool(args.skip_judge),
            "judge_success_n": sum(row.get("judge", {}).get("status") == "success" for row in completed_rows),
            "retrieval_artifact_coverage": sum(bool(row.get("retrieval_artifact")) for row in rows) / len(rows) if rows else None,
            "qa_artifact_coverage": sum(bool(row.get("qa_artifact")) for row in rows) / len(rows) if rows else None,
            "citation_metric_note": "Only explicit [source_file.pdf p.N] citations in the answer are scored; retrieved resources are not treated as answer citations.",
        }
    )
    write_jsonl(run_root / "lenovo-scored-rows.jsonl", rows)
    write_json(run_root / "lenovo-metrics.json", metrics)
    print(json.dumps({key: metrics.get(key) for key in ("planned_questions", "successful_questions", "failed_or_missing_questions", "evidence_any_recall_at_1", "evidence_any_recall_at_5", "complete_evidence_set_recall_at_10", "answers_with_citation_rate", "atomic_claim_recall", "answer_correct", "unanswerable_success", "retrieval_latency_p50_ms", "generation_latency_p50_ms", "judge_success_n")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
