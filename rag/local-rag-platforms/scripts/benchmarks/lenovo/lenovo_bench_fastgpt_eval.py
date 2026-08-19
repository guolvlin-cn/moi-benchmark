#!/usr/bin/env python3
"""Run Lenovo Bench native RAG evaluation on the local FastGPT service."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from pypdf import PdfReader


HERE = Path(__file__).resolve().parent
PLATFORM_ROOT = HERE.parents[2]
ROOT = PLATFORM_ROOT.parent
EVALUATION_DIR = PLATFORM_ROOT / "scripts/evaluation"
for import_root in (HERE, PLATFORM_ROOT, EVALUATION_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from fastgpt_local.fastgpt_local import build_isolated_app_payload  # noqa: E402
from mmdocir_competitor_eval import (  # noqa: E402
    ArtifactHTTP,
    EvalError,
    Progress,
    first_value,
    json_dump,
    list_items,
    parse_dotenv,
    sha256_bytes,
    value_from,
)


DEFAULT_DATASET = ROOT / "datasets/lenovo-bench"
DEFAULT_MINERU = ROOT / "runs/stage1/lenovo-bench-parsing/mineru-precision/20260812-233036.403/documents.jsonl"
DEFAULT_OUTPUT = ROOT / "runs/stage1/lenovo-bench-fastgpt"
CITATION_RE = re.compile(r"\[([^\[\]\n]+?\.pdf)\s+(?:p\.?|page\s*)(\d+)\]", re.IGNORECASE)


def unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "code" in payload:
        if int(payload.get("code", 0) or 0) != 200:
            raise EvalError(f"PRODUCT_API_ERROR: {payload.get('message', payload)}")
        return payload.get("data")
    return payload


def answer_text(payload: Any) -> str:
    choices = payload.get("choices", []) if isinstance(payload, dict) else []
    if choices and isinstance(choices[0], dict):
        return str(choices[0].get("message", {}).get("content", ""))
    return str(first_value(payload, ("answer", "answer_text", "content", "text")) or "")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def parse_json_object(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise EvalError("JUDGE_RESPONSE_NO_JSON_OBJECT")
    result = json.loads(value[start:end + 1])
    if not isinstance(result, dict):
        raise EvalError("JUDGE_RESPONSE_NOT_OBJECT")
    return result


class LenovoFixture:
    def __init__(self, root: Path, mineru_documents: Path):
        self.root = root
        self.gold_root = root / "moi-corpus-100q-v1"
        self.corpus_root = root / "corpus"
        self.manifest = [json.loads(line) for line in (self.gold_root / "corpus_manifest.jsonl").open() if line.strip()]
        self.questions = [json.loads(line) for line in (self.gold_root / "questions.all.jsonl").open() if line.strip()]
        if len(self.manifest) != 46 or len(self.questions) != 100:
            raise EvalError(f"LENOVO_FIXTURE_SIZE: documents={len(self.manifest)} questions={len(self.questions)}")
        if len({row["question_id"] for row in self.questions}) != len(self.questions):
            raise EvalError("LENOVO_DUPLICATE_QUESTION_ID")
        self.by_file = {row["source_file"]: row for row in self.manifest}
        missing = [name for name in self.by_file if not (self.corpus_root / name).is_file()]
        if missing:
            raise EvalError(f"LENOVO_MISSING_PDF: {missing[:3]}")
        self.mineru_documents = mineru_documents

    def _mineru_pages(self, file_name: str) -> dict[int, str]:
        pages: dict[int, list[str]] = {}
        with self.mineru_documents.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                metadata = row.get("metadata", {})
                if metadata.get("file_name") != file_name:
                    continue
                page = int(metadata.get("page_num", 0) or 0)
                content = str(row.get("content", "")).strip()
                if page > 0 and content:
                    pages.setdefault(page, []).append(content)
        return {page: "\n\n".join(parts) for page, parts in pages.items()}

    def pages(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        mineru_file = "Anti-Slavery_and_Human_Trafficking_Statement.pdf"
        mineru_pages = self._mineru_pages(mineru_file)
        rows: list[dict[str, Any]] = []
        empty_pages: list[dict[str, Any]] = []
        for item in self.manifest:
            path = self.corpus_root / item["source_file"]
            reader = PdfReader(str(path))
            if len(reader.pages) != int(item["pdf_pages"]):
                raise EvalError(f"LENOVO_PAGE_COUNT_MISMATCH: {path.name}")
            for page_number, page in enumerate(reader.pages, start=1):
                if path.name == mineru_file:
                    content = mineru_pages.get(page_number, "")
                    parser = "mineru-official-precision-v4"
                else:
                    content = (page.extract_text() or "").strip()
                    parser = "pypdf-6.14.2"
                if not content:
                    empty_pages.append({"source_file": path.name, "pdf_page": page_number})
                    content = "[This PDF page contains no extractable text.]"
                rows.append({
                    "doc_id": item["doc_id"], "source_file": path.name, "sha256": item["sha256"],
                    "pdf_page": page_number, "content": content, "parser": parser,
                })
        profile = {
            "documents": len(self.manifest), "pages": len(rows), "questions": len(self.questions),
            "empty_page_placeholders": len(empty_pages), "empty_pages": empty_pages,
            "mineru_source": str(self.mineru_documents),
            "mineru_source_sha256": sha256_bytes(self.mineru_documents.read_bytes()),
            "corpus_combined_sha256": "3a7b98c5b57c2ab4057339fa8c59df1933dc67441072ce0249e608e3097430bb",
        }
        return rows, profile


def chunk_text(page: dict[str, Any]) -> str:
    return (
        f"[SOURCE_FILE: {page['source_file']}]\n"
        f"[PDF_PAGE: {page['pdf_page']}]\n"
        f"[SHA256: {page['sha256']}]\n"
        f"[DOC_ID: {page['doc_id']}]\n\n{page['content']}"
    )


def split_page_content(content: str, max_chars: int = 6_000, overlap_chars: int = 300) -> list[str]:
    """Bound embedding inputs while retaining the original PDF page locator."""
    if len(content) <= max_chars:
        return [content]
    parts: list[str] = []
    start = 0
    while start < len(content):
        end = min(len(content), start + max_chars)
        if end < len(content):
            boundary = max(content.rfind("\n", start + max_chars // 2, end), content.rfind(". ", start + max_chars // 2, end))
            if boundary > start:
                end = boundary + 1
        parts.append(content[start:end])
        if end >= len(content):
            break
        start = max(start + 1, end - overlap_chars)
    return parts


def hit_locator(hit: dict[str, Any]) -> tuple[str, int]:
    content = str(hit.get("q", ""))
    file_match = re.search(r"\[SOURCE_FILE:\s*(.+?)\]", content)
    page_match = re.search(r"\[PDF_PAGE:\s*(\d+)\]", content)
    return (file_match.group(1).strip() if file_match else str(hit.get("sourceName", "")), int(page_match.group(1)) if page_match else 0)


class FastGPTRun:
    def __init__(self, args: argparse.Namespace, fixture: LenovoFixture, output: Path, progress: Progress):
        env = parse_dotenv(ROOT / ".env")
        os.environ.update({key: value for key, value in env.items() if value})
        self.key = value_from(env, "FASTGPT_API_KEY")
        if not self.key:
            raise EvalError("FASTGPT_API_KEY_MISSING")
        self.client = ArtifactHTTP(value_from(env, "FASTGPT_BASE_URL", default="http://127.0.0.1:3000"), output / "fastgpt-http", progress)
        self.judge = ArtifactHTTP(value_from(env, "QIANFAN_BASE_URL", default="https://qianfan.baidubce.com/v2"), output / "judge-http", progress)
        qianfan = env
        self.judge_key = value_from(qianfan, "QIANFAN_API_KEY")
        self.judge_model = value_from(qianfan, "QIANFAN_LLM_MODEL", default="deepseek-v4-flash")
        self.args, self.fixture, self.output, self.progress = args, fixture, output, progress
        self.dataset_id = ""
        self.app_id = ""

    def setup(self, pages: list[dict[str, Any]]) -> dict[str, Any]:
        name = f"LenovoBench-{self.args.run_id}"
        by_file: dict[str, list[dict[str, Any]]] = {}
        for page in pages:
            by_file.setdefault(page["source_file"], []).append(page)
        collections: dict[str, dict[str, Any]] = {}
        if self.args.resume_dataset_id:
            self.dataset_id = self.args.resume_dataset_id
            for item in self.fixture.manifest:
                file_pages = by_file[item["source_file"]]
                collections[item["source_file"]] = {
                    "collection_id": "",
                    "pages": len(file_pages),
                    "chunks": sum(len(split_page_content(page["content"])) for page in file_pages),
                }
            self.progress.emit("ingest", "Resuming existing FastGPT Lenovo dataset", dataset_id=self.dataset_id)
        else:
            created = unwrap(self.client.request("POST", "/api/core/dataset/create", api_key=self.key, json_body={
                "parentId": None, "type": "dataset", "name": name, "intro": "Lenovo Bench 46-PDF native corpus",
                "avatar": "", "vectorModel": self.args.embedding_model, "agentModel": self.args.chat_model,
            }, operation="create-dataset"))
            self.dataset_id = str(created if isinstance(created, (str, int)) else first_value(created, ("datasetId", "id", "_id")) or "")
            if not self.dataset_id:
                raise EvalError("FASTGPT_CREATE_DATASET_NO_ID")
            for ordinal, item in enumerate(self.fixture.manifest, start=1):
                file_pages = by_file[item["source_file"]]
                created_collection = unwrap(self.client.request("POST", "/api/core/dataset/collection/create", api_key=self.key, json_body={
                    "datasetId": self.dataset_id, "parentId": None, "name": item["source_file"], "type": "virtual",
                }, operation=f"create-collection-{ordinal:03d}"))
                collection_id = str(created_collection if isinstance(created_collection, (str, int)) else first_value(created_collection, ("collectionId", "id", "_id")) or "")
                if not collection_id:
                    raise EvalError(f"FASTGPT_CREATE_COLLECTION_NO_ID: {item['source_file']}")
                chunks: list[dict[str, Any]] = []
                for page in file_pages:
                    parts = split_page_content(page["content"])
                    for part_number, part in enumerate(parts, start=1):
                        part_page = dict(page, content=part)
                        text = chunk_text(part_page)
                        if len(parts) > 1:
                            text = text.replace("\n\n", f"\n[PAGE_PART: {part_number}/{len(parts)}]\n\n", 1)
                        chunks.append({"q": text, "chunkIndex": len(chunks)})
                for batch_number, offset in enumerate(range(0, len(chunks), 200), start=1):
                    self.client.request("POST", "/api/core/dataset/data/pushData", api_key=self.key, json_body={
                        "collectionId": collection_id, "trainingType": "chunk",
                        "data": chunks[offset:offset + 200],
                    }, operation=f"push-document-{ordinal:03d}-batch-{batch_number:03d}", timeout=self.args.upload_timeout)
                collections[item["source_file"]] = {"collection_id": collection_id, "pages": len(file_pages), "chunks": len(chunks)}
                self.progress.emit("ingest", "FastGPT Lenovo document submitted", completed=ordinal, total=len(self.fixture.manifest), pages=len(file_pages), chunks=len(chunks))
        deadline = time.monotonic() + self.args.index_wait
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            listing = unwrap(self.client.request("POST", "/api/core/dataset/collection/listV2", api_key=self.key, json_body={
                "offset": 0, "pageSize": 100, "datasetId": self.dataset_id, "parentId": None, "searchText": "",
            }, operation="index-status", timeout=600))
            items = list_items(listing, ("list",))
            for item in items:
                source_file = str(item.get("name", "")) if isinstance(item, dict) else ""
                if source_file in collections:
                    collections[source_file]["collection_id"] = str(first_value(item, ("collectionId", "id", "_id")) or "")
            last = {
                "collections": len(items),
                "training": sum(int(x.get("trainingAmount", 0) or 0) for x in items if isinstance(x, dict)),
                "active_training": sum(int(x.get("activeTrainingAmount", 0) or 0) for x in items if isinstance(x, dict)),
                "errors": sum(int(x.get("finalErrorAmount", 0) or 0) for x in items if isinstance(x, dict)),
            }
            if last["errors"]:
                raise EvalError(f"FASTGPT_INDEX_FAILED: {last}")
            if len(items) == len(collections) and last["training"] == 0 and last["active_training"] == 0:
                break
            self.progress.emit("ingest", "FastGPT Lenovo index pending", **last)
            time.sleep(self.args.poll_seconds)
        else:
            raise EvalError(f"FASTGPT_INDEX_TIMEOUT: {last}")
        payload = build_isolated_app_payload(provider_name="maas", dataset_id=self.dataset_id, dataset_name=name)
        for module in payload["modules"]:
            for item in module.get("inputs", []):
                if item.get("key") == "model":
                    item["value"] = self.args.chat_model
                elif item.get("key") == "systemPrompt":
                    item["value"] = (
                        "Answer only from the supplied Lenovo Bench knowledge. Answer in the question's language. "
                        "For every factual statement cite the source exactly as [source_file.pdf p.N]. "
                        "Use the SOURCE_FILE and PDF_PAGE markers in the knowledge. If the corpus is insufficient, "
                        "explicitly refuse and do not guess. Preserve model, version, date, units and conditions."
                    )
                elif item.get("key") == "datasets":
                    item["value"][0]["vectorModel"] = {"model": self.args.embedding_model}
                elif item.get("key") == "limit":
                    item["value"] = self.args.top_k
        app = unwrap(self.client.request("POST", "/api/core/app/create", api_key=self.key, json_body=payload, operation="create-app"))
        self.app_id = str(app if isinstance(app, (str, int)) else first_value(app, ("appId", "id", "_id")) or "")
        if not self.app_id:
            raise EvalError("FASTGPT_CREATE_APP_NO_ID")
        return {"dataset_id": self.dataset_id, "app_id": self.app_id, "collections": collections, "index": last}

    def run_question(self, question: dict[str, Any], ordinal: int) -> dict[str, Any]:
        row: dict[str, Any] = {"ordinal": ordinal, "question_id": question["question_id"], "case": question}
        try:
            started = time.monotonic()
            retrieval = unwrap(self.client.request("POST", "/api/core/dataset/searchTest", api_key=self.key, json_body={
                "datasetId": self.dataset_id, "text": question["question"], "limit": 20000, "similarity": 0,
                "searchMode": "embedding", "usingReRank": False, "datasetSearchUsingExtensionQuery": False,
            }, operation=f"retrieval-{ordinal:03d}", timeout=self.args.query_timeout))
            row["retrieval_latency_ms"] = (time.monotonic() - started) * 1000
            hits = list_items(retrieval, ("list",))[:self.args.top_k]
            row["chunks"] = [
                {"rank": rank, "source_file": hit_locator(hit)[0], "pdf_page": hit_locator(hit)[1], "content": str(hit.get("q", ""))}
                for rank, hit in enumerate(hits, start=1) if isinstance(hit, dict)
            ]
            started = time.monotonic()
            native = self.client.request("POST", "/api/v1/chat/completions", api_key=self.key, json_body={
                "appId": self.app_id, "chatId": str(uuid.uuid4()), "stream": False, "detail": True,
                "messages": [{"role": "user", "content": question["question"]}],
            }, operation=f"native-{ordinal:03d}", timeout=self.args.native_timeout)
            row["generation_latency_ms"] = (time.monotonic() - started) * 1000
            row["answer"] = answer_text(native)
            row["citations"] = [{"source_file": name, "pdf_page": int(page)} for name, page in CITATION_RE.findall(row["answer"])]
            row["status"] = "success"
        except Exception as exc:
            row.update({"status": "error", "error": str(exc), "chunks": row.get("chunks", []), "answer": row.get("answer", ""), "citations": []})
        return row

    def judge_question(self, row: dict[str, Any]) -> dict[str, Any]:
        if row.get("status") != "success":
            return {"status": "not_scored", "error": "generation_failed"}
        case = row["case"]
        contexts = [chunk["content"] for chunk in row.get("chunks", [])]
        prompt = {
            "task": "Evaluate one RAG answer against atomic Gold claims and the actually retrieved context.",
            "rules": [
                "Use only the supplied Gold/reference and retrieved context.",
                "gold_claim_coverage must contain one 0/1 entry per Gold claim in order.",
                "A material answer claim is supported only if entailed by retrieved_context.",
                "For unanswerable items, refusal_correct=1 only for a clear refusal without factual guessing.",
                "Return strict JSON only; scores are binary 0 or 1 except counts and null where not applicable.",
            ],
            "question": case["question"], "answerability": case["answerability"],
            "reference_answer": case["reference_answer"], "accepted_answers": case.get("accepted_answers", []),
            "gold_claims": [claim["text"] for claim in case.get("claims", [])],
            "answer": row["answer"], "retrieved_context": contexts,
            "output_schema": {
                "gold_claim_coverage": "array of 0/1", "material_answer_claim_count": "integer",
                "supported_material_answer_claim_count": "integer", "answer_correct": "0/1",
                "answer_complete": "0/1", "numeric_unit_correct": "0/1/null",
                "scope_version_correct": "0/1/null", "faithfulness": "0/1",
                "answer_relevance": "0/1", "refusal_correct": "0/1/null",
                "unsupported_completion": "0/1", "rationale": "short string",
            },
        }
        last_error = ""
        for attempt in range(1, 4):
            try:
                payload = self.judge.request("POST", "/chat/completions", api_key=self.judge_key, json_body={
                    "model": self.judge_model, "temperature": 0,
                    "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
                }, operation=f"judge-{row['ordinal']:03d}-attempt-{attempt}", timeout=self.args.judge_timeout)
                result = parse_json_object(answer_text(payload))
                coverage = result.get("gold_claim_coverage", [])
                if not isinstance(coverage, list) or len(coverage) != len(case.get("claims", [])):
                    raise EvalError("JUDGE_CLAIM_COVERAGE_LENGTH")
                result["status"] = "success"
                return result
            except Exception as exc:
                last_error = str(exc)
        return {"status": "error", "error": last_error}


def gold_evidence_sets(case: dict[str, Any]) -> list[set[tuple[str, int]]]:
    return [
        {(str(item["source_file"]), int(item["pdf_page"])) for item in evidence.get("items", [])}
        for evidence in case.get("evidence_sets", [])
    ]


def score_rows(rows: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> dict[str, Any]:
    page_limits = {row["source_file"]: int(row["pdf_pages"]) for row in manifest}
    successful = [row for row in rows if row.get("status") == "success"]
    answerable = [row for row in successful if row["case"]["answerability"] == "answerable"]
    judged = [row for row in successful if row.get("judge", {}).get("status") == "success"]
    judged_answerable = [row for row in judged if row["case"]["answerability"] == "answerable"]
    judged_unanswerable = [row for row in judged if row["case"]["answerability"] == "unanswerable"]
    retrieval_latency = [float(row["retrieval_latency_ms"]) for row in successful]
    generation_latency = [float(row["generation_latency_ms"]) for row in successful]
    e2e_latency = [
        float(row["retrieval_latency_ms"]) + float(row["generation_latency_ms"])
        for row in successful
    ]
    metrics: dict[str, Any] = {
        "questions": len(rows), "successful_questions": len(successful),
        "answerable_questions": len(answerable),
        "unanswerable_questions": len([row for row in successful if row["case"]["answerability"] == "unanswerable"]),
        "success_rate": len(successful) / len(rows) if rows else None,
        "judge_valid_n": len(judged), "judge_valid_rate": len(judged) / len(successful) if successful else None,
        "retrieval_latency_p50_ms": median(retrieval_latency) if retrieval_latency else None,
        "retrieval_latency_p95_ms": percentile(retrieval_latency, 0.95),
        "generation_latency_p50_ms": median(generation_latency) if generation_latency else None,
        "generation_latency_p95_ms": percentile(generation_latency, 0.95),
        "e2e_latency_p50_ms": median(e2e_latency) if e2e_latency else None,
        "e2e_latency_p95_ms": percentile(e2e_latency, 0.95),
    }
    for cutoff in (1, 3, 5, 10):
        any_doc = all_doc = any_evidence = complete_set = 0.0
        evidence_fraction = context_precision = reciprocal = 0.0
        for row in answerable:
            ranked = [(chunk["source_file"], int(chunk["pdf_page"])) for chunk in row.get("chunks", [])[:cutoff]]
            ranked_docs = {name for name, _ in ranked}
            required_docs = set(row["case"].get("source_documents", []))
            doc_ids = {m["doc_id"]: m["source_file"] for m in manifest}
            required_files = {doc_ids.get(doc_id, doc_id) for doc_id in required_docs}
            sets = gold_evidence_sets(row["case"])
            union = set().union(*sets) if sets else set()
            any_doc += float(bool(required_files.intersection(ranked_docs)))
            all_doc += float(bool(required_files) and required_files.issubset(ranked_docs))
            any_evidence += float(bool(union.intersection(ranked)))
            fractions = [len(evidence.intersection(ranked)) / len(evidence) for evidence in sets if evidence]
            evidence_fraction += max(fractions, default=0.0)
            complete_set += float(any(evidence and evidence.issubset(ranked) for evidence in sets))
            context_precision += sum(locator in union for locator in ranked) / len(ranked) if ranked else 0.0
            ranks = [index for index, locator in enumerate(ranked, 1) if locator in union]
            reciprocal += 1 / min(ranks) if ranks else 0.0
        denominator = len(answerable)
        metrics.update({
            f"doc_any_recall_at_{cutoff}": any_doc / denominator if denominator else None,
            f"doc_complete_recall_at_{cutoff}": all_doc / denominator if denominator else None,
            f"evidence_any_recall_at_{cutoff}": any_evidence / denominator if denominator else None,
            f"evidence_fraction_recall_at_{cutoff}": evidence_fraction / denominator if denominator else None,
            f"complete_evidence_set_recall_at_{cutoff}": complete_set / denominator if denominator else None,
            f"context_precision_at_{cutoff}": context_precision / denominator if denominator else None,
            f"evidence_mrr_at_{cutoff}": reciprocal / denominator if denominator else None,
        })
    all_citations = [citation for row in successful for citation in row.get("citations", [])]
    valid_citations = [citation for citation in all_citations if citation["source_file"] in page_limits and 1 <= citation["pdf_page"] <= page_limits[citation["source_file"]]]
    metrics["answers_with_citation_rate"] = sum(bool(row.get("citations")) for row in successful) / len(successful) if successful else None
    metrics["citation_locator_valid_rate"] = len(valid_citations) / len(all_citations) if all_citations else None
    metrics["citation_fabricated_or_out_of_range_rate"] = 1 - metrics["citation_locator_valid_rate"] if metrics["citation_locator_valid_rate"] is not None else None
    citation_precision_sum = citation_recall_sum = citation_complete = 0.0
    for row in answerable:
        citations = {(x["source_file"], int(x["pdf_page"])) for x in row.get("citations", [])}
        sets = gold_evidence_sets(row["case"])
        union = set().union(*sets) if sets else set()
        citation_precision_sum += len(citations.intersection(union)) / len(citations) if citations else 0.0
        citation_recall_sum += max((len(citations.intersection(s)) / len(s) for s in sets if s), default=0.0)
        citation_complete += float(any(s and s.issubset(citations) for s in sets))
    metrics["gold_citation_precision"] = citation_precision_sum / len(answerable) if answerable else None
    metrics["gold_citation_evidence_recall"] = citation_recall_sum / len(answerable) if answerable else None
    metrics["complete_citation_set_rate"] = citation_complete / len(answerable) if answerable else None
    claim_total = sum(len(row["case"].get("claims", [])) for row in judged_answerable)
    claim_covered = sum(sum(int(bool(x)) for x in row["judge"].get("gold_claim_coverage", [])) for row in judged_answerable)
    material_total = sum(max(0, int(row["judge"].get("material_answer_claim_count", 0) or 0)) for row in judged_answerable)
    material_supported = sum(max(0, int(row["judge"].get("supported_material_answer_claim_count", 0) or 0)) for row in judged_answerable)
    metrics["atomic_claim_recall"] = claim_covered / claim_total if claim_total else None
    metrics["atomic_claim_precision"] = material_supported / material_total if material_total else None
    metrics["reference_claims_total"] = claim_total
    metrics["reference_claims_covered"] = claim_covered
    metrics["response_claims_total"] = material_total
    metrics["response_claims_supported"] = material_supported
    for key in ("answer_correct", "answer_complete", "faithfulness", "answer_relevance"):
        metrics[key] = sum(int(bool(row["judge"].get(key))) for row in judged_answerable) / len(judged_answerable) if judged_answerable else None
    numeric = [row for row in judged_answerable if row["judge"].get("numeric_unit_correct") is not None]
    scope = [row for row in judged_answerable if row["judge"].get("scope_version_correct") is not None]
    metrics["numeric_unit_accuracy"] = sum(int(bool(row["judge"]["numeric_unit_correct"])) for row in numeric) / len(numeric) if numeric else None
    metrics["scope_version_accuracy"] = sum(int(bool(row["judge"]["scope_version_correct"])) for row in scope) / len(scope) if scope else None
    strict_unanswerable_pass = sum(int(bool(row["judge"].get("refusal_correct"))) for row in judged_unanswerable)
    metrics["strict_unanswerable_pass"] = strict_unanswerable_pass
    metrics["strict_unanswerable_total"] = len(judged_unanswerable)
    metrics["unanswerable_success"] = strict_unanswerable_pass / len(judged_unanswerable) if judged_unanswerable else None
    metrics["unsupported_completion_rate"] = sum(int(bool(row["judge"].get("unsupported_completion"))) for row in judged) / len(judged) if judged else None
    trusted = 0
    trusted_answerable = 0
    for row in judged:
        judge = row["judge"]
        if row["case"]["answerability"] == "unanswerable":
            trusted += int(bool(judge.get("refusal_correct")) and not bool(judge.get("unsupported_completion")))
        else:
            citations = {(x["source_file"], int(x["pdf_page"])) for x in row.get("citations", [])}
            complete_citation = any(s and s.issubset(citations) for s in gold_evidence_sets(row["case"]))
            claims_complete = all(bool(x) for x in judge.get("gold_claim_coverage", []))
            answerable_pass = int(bool(judge.get("answer_correct")) and bool(judge.get("answer_complete")) and bool(judge.get("faithfulness")) and claims_complete and complete_citation)
            trusted += answerable_pass
            trusted_answerable += answerable_pass
    metrics["trusted_answer_rate"] = trusted / len(judged) if judged else None
    metrics["tdas_answerable_pass"] = trusted_answerable
    metrics["tdas_answerable_total"] = len(judged_answerable)
    metrics["tdas_answerable"] = trusted_answerable / len(judged_answerable) if judged_answerable else None
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--mineru-documents", type=Path, default=DEFAULT_MINERU)
    parser.add_argument("--prepared-pages", type=Path, help="reuse a validated prepared-pages.jsonl from an earlier attempt")
    parser.add_argument("--resume-dataset-id", help="resume indexing and evaluation from an existing FastGPT dataset")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--embedding-model", default="bge-m3")
    parser.add_argument("--chat-model", default="qwen3-30b-a3b")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--query-workers", type=int, default=4)
    parser.add_argument("--judge-workers", type=int, default=4)
    parser.add_argument("--upload-timeout", type=int, default=600)
    parser.add_argument("--query-timeout", type=int, default=180)
    parser.add_argument("--native-timeout", type=int, default=600)
    parser.add_argument("--judge-timeout", type=int, default=300)
    parser.add_argument("--index-wait", type=int, default=7200)
    parser.add_argument("--poll-seconds", type=float, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = args.output_root / args.run_id / "fastgpt_local" / "native"
    output.mkdir(parents=True, exist_ok=False)
    progress = Progress(output / "progress.jsonl")
    try:
        fixture = LenovoFixture(args.dataset_root, args.mineru_documents)
        if args.prepared_pages:
            pages = [json.loads(line) for line in args.prepared_pages.open() if line.strip()]
            if len(pages) != 1104:
                raise EvalError(f"PREPARED_PAGE_COUNT_{len(pages)}")
            profile = {
                "documents": 46, "pages": len(pages), "questions": 100,
                "reused_from": str(args.prepared_pages), "reused_sha256": sha256_bytes(args.prepared_pages.read_bytes()),
            }
        else:
            pages, profile = fixture.pages()
        with (output / "prepared-pages.jsonl").open("w", encoding="utf-8") as handle:
            for row in pages:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        json_dump(output / "corpus-profile.json", profile)
        json_dump(output / "run-manifest.json", {
            "schema": "lenovo-bench-fastgpt-native-v1", "run_id": args.run_id, "system": "fastgpt_local",
            "mode": "native", "questions": 100, "documents": 46, "pages": 1104,
            "official_headline_split": "formal", "embedding_model": args.embedding_model,
            "chat_model": args.chat_model, "retrieval_top_k": args.top_k,
            "query_workers": args.query_workers, "judge_workers": args.judge_workers,
            "gold_candidate_limitation": "independent second reviewer and arbitration remain pending",
        })
        runner = FastGPTRun(args, fixture, output, progress)
        resources = runner.setup(pages)
        json_dump(output / "resources.json", resources)
        rows: list[dict[str, Any] | None] = [None] * len(fixture.questions)
        with ThreadPoolExecutor(max_workers=args.query_workers) as pool:
            futures = {pool.submit(runner.run_question, case, ordinal): ordinal for ordinal, case in enumerate(fixture.questions, 1)}
            for future in as_completed(futures):
                ordinal = futures[future]
                rows[ordinal - 1] = future.result()
                progress.emit("qa", "FastGPT Lenovo question complete", completed=sum(row is not None for row in rows), total=len(rows))
        completed_rows = [row for row in rows if row is not None]
        with ThreadPoolExecutor(max_workers=args.judge_workers) as pool:
            futures = {pool.submit(runner.judge_question, row): row for row in completed_rows}
            completed = 0
            for future in as_completed(futures):
                row = futures[future]
                row["judge"] = future.result()
                completed += 1
                progress.emit("judge", "Lenovo answer judged", completed=completed, total=len(completed_rows))
        with (output / "results.jsonl").open("w", encoding="utf-8") as handle:
            for row in completed_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        all_metrics = score_rows(completed_rows, fixture.manifest)
        by_split = {
            split: score_rows([row for row in completed_rows if row["case"]["split"] == split], fixture.manifest)
            for split in ("dev", "pilot", "formal")
        }
        by_type = {
            kind: score_rows([row for row in completed_rows if row["case"]["primary_type"] == kind], fixture.manifest)
            for kind in sorted({row["case"]["primary_type"] for row in completed_rows})
        }
        metrics = {"protocol": "Lenovo Bench native FastGPT v1", "all": all_metrics, "by_split": by_split, "by_primary_type": by_type}
        json_dump(output / "metrics.json", metrics)
        summary = {"status": "success", "run_id": args.run_id, "output": str(output), "headline_formal": by_split["formal"]}
        json_dump(output / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        failure = {"status": "error", "run_id": args.run_id, "output": str(output), "type": type(exc).__name__, "error": str(exc)}
        json_dump(output / "failure.json", failure)
        print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
