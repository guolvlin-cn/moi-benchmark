#!/usr/bin/env python3
"""Controlled MMDocIR QA over frozen competitor retrieval traces.

MMDocIR is a retrieval benchmark.  This downstream QA adapter is therefore an
ADAPTED_PROTOCOL: it reconstructs the pages returned by a product's frozen
document-local retrieval run, sends the page text and images to one fixed
multimodal reader, and keeps oracle-gold evidence as a separate condition.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PREPARED = ROOT / "runs/stage1/mmdocir/20260806-161153-full-1658/artifacts/prepared"
DEFAULT_IMAGES = ROOT / "datasets/downloads/document-rag/mmdocir/data/extracted/page_images"
WORD = re.compile(r"[^\W_]+", re.UNICODE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {path.name}\n", encoding="utf-8"
    )


def normalize(value: Any) -> str:
    return "".join(WORD.findall(str(value or "").lower()))


def tokens(value: Any) -> list[str]:
    return WORD.findall(str(value or "").lower())


def token_f1(prediction: Any, reference: Any) -> float:
    predicted, expected = tokens(prediction), tokens(reference)
    if not predicted or not expected:
        return 0.0
    overlap = sum((Counter(predicted) & Counter(expected)).values())
    if not overlap:
        return 0.0
    precision, recall = overlap / len(predicted), overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


def flatten_marker_hits(marker_hits: list[Any]) -> list[tuple[str, int]]:
    pages: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for rank in marker_hits:
        for item in rank if isinstance(rank, list) else []:
            if not isinstance(item, list) or len(item) < 2:
                continue
            page = (str(item[0]), int(item[1]))
            if page not in seen:
                seen.add(page)
                pages.append(page)
    return pages


def page_image(root: Path, doc_name: str, page_number: int) -> Path:
    name = Path(doc_name).name
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return root / f"{name}_{page_number}.jpg"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))]


def latest_by_question(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest[str(row["question_id"])] = row
    return sorted(latest.values(), key=lambda row: int(row["ordinal"]))


class QianfanReader:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int, retries: int, output: Path):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.output = output
        self.lock = threading.Lock()

    def answer(self, ordinal: int, question: str, evidence: list[dict[str, Any]]) -> tuple[str, float, int]:
        text_parts = []
        content: list[dict[str, Any]] = []
        remaining_chars = 60000
        request_images = []
        for rank, page in enumerate(evidence, 1):
            page_text = str(page["content"])
            page_text = page_text[: max(0, min(remaining_chars, 12000))]
            remaining_chars -= len(page_text)
            text_parts.append(f"[rank={rank} source={page['doc_name']} page={page['page_number']}]\n{page_text}")
        content.append({"type": "text", "text": (
            "Answer only from the supplied evidence. If it is insufficient, say so. "
            "Give a concise answer and cite source page numbers in square brackets.\n\n"
            f"Question:\n{question}\n\nEvidence text:\n" + "\n\n".join(text_parts)
        )})
        for page in evidence:
            image = Path(page["image"])
            raw = image.read_bytes()
            content.append({"type": "text", "text": f"Page image: [{page['doc_name']} page={page['page_number']}]"})
            content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(raw).decode()}})
            request_images.append({"path": str(image), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "stream": False,
            "max_tokens": 1024,
        }
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            request = Request(
                self.url,
                data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    response_payload = json.loads(response.read().decode())
                choices = response_payload.get("choices") or []
                message = choices[0].get("message", {}) if choices else {}
                answer = str(message.get("content") or message.get("reasoning_content") or "").strip()
                if not answer:
                    raise RuntimeError("Qianfan returned an empty answer")
                latency = (time.perf_counter() - started) * 1000
                write_json(self.output / "http" / f"{ordinal:04d}.json", {
                    "recorded_at": utc_now(),
                    "request": {"url": self.url, "model": self.model, "question": question, "images": request_images},
                    "response": response_payload,
                    "attempts": attempt,
                    "latency_ms": latency,
                })
                return answer, latency, attempt
            except HTTPError as exc:
                body = exc.read().decode(errors="replace")[:2000]
                last_error = RuntimeError(f"HTTP {exc.code}: {body}")
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    break
            except (URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
                last_error = exc
            if attempt < self.retries:
                # Multimodal requests consume substantial TPM. Qianfan's 429
                # response currently has no Retry-After header, so use a
                # conservative cooldown instead of immediately amplifying it.
                delay = 30 * attempt if isinstance(last_error, RuntimeError) and "HTTP 429" in str(last_error) else min(20, 2 ** (attempt - 1))
                time.sleep(delay)
        raise RuntimeError(str(last_error or "Qianfan request failed"))


def build_evidence(
    retrieval: dict[str, Any], question: dict[str, Any], pages: dict[tuple[str, int], dict[str, Any]],
    images_root: Path, condition: str, top_k: int,
) -> list[dict[str, Any]]:
    if condition == "oracle":
        locators = [(str(question["file_id"]), int(page)) for page in question.get("page_ids", [])]
    else:
        locators = flatten_marker_hits(retrieval.get("marker_hits", []))[:top_k]
    evidence = []
    for file_id, number in locators:
        page = pages.get((file_id, number))
        if not page:
            continue
        doc_name = str(question.get("doc_name") or page.get("metadata", {}).get("doc_name") or "")
        image = page_image(images_root, doc_name, number)
        if not image.is_file():
            raise FileNotFoundError(image)
        evidence.append({"file_id": file_id, "doc_name": doc_name, "page_number": number, "content": page.get("content", ""), "image": str(image)})
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-id", required=True)
    parser.add_argument("--retrieval-results", type=Path, required=True)
    parser.add_argument("--prepared-root", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--images-root", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--condition", choices=("actual", "oracle"), default="actual")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--model", default="qwen3.5-35b-a3b")
    parser.add_argument("--base-url", default=os.getenv("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=4)
    args = parser.parse_args()

    api_key = os.getenv("QIANFAN_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("QIANFAN_API_KEY is required")
    questions = {str(row["id"]): row for row in read_jsonl(args.prepared_root / "questions.jsonl")}
    pages = {(str(row["file_id"]), int(row.get("page_number", row.get("page_id", 0)))): row for row in read_jsonl(args.prepared_root / "pages.jsonl")}
    retrieval_rows = read_jsonl(args.retrieval_results)
    if args.limit > 0:
        retrieval_rows = retrieval_rows[: args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    existing_path = args.output / "qa-results.jsonl"
    existing = read_jsonl(existing_path) if existing_path.exists() else []
    completed = {str(row["question_id"]) for row in existing if row.get("status") == "ok"}
    reader = QianfanReader(base_url=args.base_url, api_key=api_key, model=args.model, timeout=args.timeout, retries=args.retries, output=args.output)

    def evaluate(row: dict[str, Any]) -> dict[str, Any]:
        question = questions[str(row["question_id"])]
        evidence = build_evidence(row, question, pages, args.images_root, args.condition, args.top_k)
        started = utc_now()
        try:
            answer, latency, attempts = reader.answer(int(row["ordinal"]), str(question["question"]), evidence)
            reference = str(question.get("answer") or "")
            return {
                "ordinal": row["ordinal"], "question_id": row["question_id"], "question": question["question"],
                "reference_answer": reference, "generated_answer": answer, "status": "ok", "error": "",
                "condition": args.condition, "system_id": args.system_id, "generation_provider": "qianfan",
                "generation_model": args.model, "generation_latency_ms": latency, "provider_attempts": attempts,
                "retrieved_page_recall_at_10": row.get("recall_at_k", {}).get("10"),
                "evidence_pages": [{k: p[k] for k in ("file_id", "doc_name", "page_number", "image")} for p in evidence],
                "answer_exact_match_normalized": bool(reference) and normalize(answer) == normalize(reference),
                "answer_contains_gold": bool(reference) and normalize(reference) in normalize(answer),
                "token_f1": token_f1(answer, reference), "started_at": started, "ended_at": utc_now(),
            }
        except Exception as exc:
            return {"ordinal": row["ordinal"], "question_id": row["question_id"], "question": question["question"],
                    "reference_answer": question.get("answer"), "status": "failed", "error": str(exc),
                    "condition": args.condition, "system_id": args.system_id, "generation_provider": "qianfan",
                    "generation_model": args.model, "started_at": started, "ended_at": utc_now()}

    pending = [row for row in retrieval_rows if str(row["question_id"]) not in completed]
    with ThreadPoolExecutor(max_workers=args.workers) as pool, existing_path.open("a", encoding="utf-8") as output:
        futures = {pool.submit(evaluate, row): row for row in pending}
        done = len(completed)
        for future in as_completed(futures):
            result = future.result()
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()
            done += 1
            print(f"mmdocir_qa={done}/{len(retrieval_rows)} system={args.system_id} condition={args.condition} id={result['question_id']} status={result['status']}", flush=True)

    rows = latest_by_question(read_jsonl(existing_path))
    successful = [row for row in rows if row.get("status") == "ok"]
    latencies = [float(row["generation_latency_ms"]) for row in successful]
    metrics = {
        "schema": "mmdocir-controlled-multimodal-qa-v1", "protocol": "ADAPTED_PROTOCOL",
        "system_id": args.system_id, "condition": args.condition, "questions": len(rows),
        "successful_attempts": len(successful), "failed_attempts": len(rows) - len(successful),
        "generation_provider": "Baidu Qianfan", "generation_model": args.model,
        "embedding_provider": "Huawei MaaS", "embedding_model": "bge-m3",
        # Product/provider failures remain in the frozen question denominator.
        "answer_contains_gold_rate": sum(bool(row["answer_contains_gold"]) for row in successful) / len(rows) if rows else 0,
        "answer_exact_match_normalized_rate": sum(bool(row["answer_exact_match_normalized"]) for row in successful) / len(rows) if rows else 0,
        "mean_token_f1": sum(float(row["token_f1"]) for row in successful) / len(rows) if rows else 0,
        "mean_token_f1_success_only": statistics.fmean(float(row["token_f1"]) for row in successful) if successful else 0,
        "generation_latency_p50_ms": percentile(latencies, .5), "generation_latency_p95_ms": percentile(latencies, .95),
        "retrieval_results": str(args.retrieval_results), "top_k": args.top_k,
    }
    write_json(args.output / "metrics.json", metrics)
    write_json(args.output / "run-manifest.json", {**metrics, "prepared_root": str(args.prepared_root), "images_root": str(args.images_root), "completed_at": utc_now()})
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if len(successful) == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
