#!/usr/bin/env python3
"""Run comparable MMDocIR document-local page retrieval on local RAG products.

The MOI reference run searches only inside the document named by each MMDocIR
question.  This runner preserves that contract by creating one product
knowledge base per original document and inserting one canonical page chunk per
prepared MMDocIR page.  It intentionally does not run generation: the MOI
reference condition uses BGE-M3 retrieval only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
PLATFORM_ROOT = HERE.parents[1]
ROOT = PLATFORM_ROOT.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mmdocir_competitor_eval import (  # noqa: E402
    ArtifactHTTP,
    EvalError,
    Progress,
    Provider,
    external_json,
    first_value,
    json_dump,
    list_items,
    parse_dotenv,
    sha256_bytes,
    utc_now,
    value_from,
)


DEFAULT_PREPARED = ROOT / "runs/stage1/mmdocir/20260806-161153-full-1658/artifacts/prepared"
DEFAULT_OUTPUT = ROOT / "runs/stage1/mmdocir-competitors"
RUNTIME_ROOT = ROOT / ".local-services/mmdocir-competitors"


@dataclass(frozen=True)
class PageChunk:
    file_id: str
    doc_name: str
    page_number: int
    page_id: str
    content: bytes


@dataclass(frozen=True)
class Question:
    question_id: str
    query_index: int
    question: str
    answer: str
    file_id: str
    doc_name: str
    page_ids: list[int]
    domain: str


def canonical_page_bytes(page: dict[str, Any]) -> bytes:
    content = str(page.get("content", ""))
    return (content if content.strip() else "\u2060").encode("utf-8")


def fastgpt_push_payload(collection_id: str, chunks: list[PageChunk]) -> dict[str, Any]:
    return {
        "collectionId": collection_id,
        "trainingType": "chunk",
        "data": [
            {"q": chunk.content.decode("utf-8"), "chunkIndex": index}
            for index, chunk in enumerate(chunks)
        ],
    }


def fastgpt_search_payload(dataset_id: str, question: str) -> dict[str, Any]:
    # FastGPT's ``limit`` is a result token budget, not the requested hit
    # count.  Ask for the endpoint maximum and apply benchmark top-k locally.
    return {
        "datasetId": dataset_id,
        "text": question,
        "limit": 20000,
        "similarity": 0,
        "searchMode": "embedding",
        "usingReRank": False,
        "datasetSearchUsingExtensionQuery": False,
    }


def maxkb_document_payload(doc_name: str, chunks: list[PageChunk]) -> list[dict[str, Any]]:
    return [{
        "name": doc_name[:128] or chunks[0].file_id,
        "paragraphs": [
            {
                "title": f"MMDocIR page {chunk.page_number}",
                "content": chunk.content.decode("utf-8"),
            }
            for chunk in chunks
        ],
    }]


def score_page_recall(
    question: Question,
    ranked_markers: list[list[tuple[str, int]]],
    cutoffs: Iterable[int],
) -> dict[str, Any]:
    gold = {(question.file_id, page) for page in question.page_ids}
    values: dict[str, float] = {}
    for cutoff in cutoffs:
        found = {marker for row in ranked_markers[:cutoff] for marker in row}
        values[str(cutoff)] = len(gold.intersection(found)) / len(gold) if gold else 0.0
    return {
        "gold_pages": sorted([list(item) for item in gold]),
        "marker_hits": ranked_markers,
        "recall_at_k": values,
    }


def unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "code" in payload:
        if int(payload.get("code", 0)) != 200:
            raise EvalError(f"PRODUCT_API_ERROR: {payload.get('message', payload)}")
        return payload.get("data")
    if isinstance(payload, dict) and payload.get("code") == 200:
        return payload.get("data")
    if isinstance(payload, dict) and "data" in payload and len(payload) <= 3:
        return payload.get("data")
    return payload


def product_id(payload: Any) -> str:
    """Return an ID from APIs that use either a scalar or object response."""
    if isinstance(payload, (str, int)):
        return str(payload)
    return str(first_value(payload, ("datasetId", "collectionId", "id", "_id")) or "")


def choose_maxkb_embedding_model(candidates: list[Any], model: str, provider_label: str) -> dict[str, Any]:
    matches = [item for item in candidates if isinstance(item, dict) and (
        str(item.get("model_name", "")).lower() == model.lower()
        or str(item.get("name", "")).lower() == model.lower()
    ) and "embed" in str(item.get("model_type", "embedding")).lower()]
    provider_matches = [item for item in matches if provider_label.lower() in str(item.get("name", "")).lower()]
    if len(provider_matches) != 1:
        raise EvalError(f"MAXKB_{model.upper().replace('-', '_')}_{provider_label.upper()}_MODEL_MATCH_COUNT_{len(provider_matches)}")
    return provider_matches[0]


def is_maxkb_busy(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and int(payload.get("code", 0) or 0) == 500
        and "任务正在执行" in str(payload.get("message", ""))
    )


def sort_maxkb_hits(hits: list[Any]) -> list[Any]:
    """Restore ranking lost by MaxKB's paragraph hydration query."""
    return sorted(
        hits,
        key=lambda item: float(
            (item.get("comprehensive_score", item.get("similarity", 0)) if isinstance(item, dict) else 0)
            or 0
        ),
        reverse=True,
    )


def fastgpt_hit_markers(file_id: str, chunks: list[PageChunk], hit: Any) -> list[tuple[str, int]]:
    if not isinstance(hit, dict):
        return []
    try:
        index = int(hit.get("chunkIndex"))
    except (TypeError, ValueError):
        return []
    if index < 0 or index >= len(chunks):
        return []
    return [(file_id, chunks[index].page_number)]


def maxkb_hit_markers(file_id: str, hit: Any) -> list[tuple[str, int]]:
    if not isinstance(hit, dict):
        return []
    match = re.fullmatch(r"MMDocIR page (\d+)", str(hit.get("title", "")).strip())
    return [(file_id, int(match.group(1)))] if match else []


class Corpus:
    def __init__(self, prepared: Path, documents_limit: int, questions_limit: int):
        self.prepared = prepared
        pages = [json.loads(line) for line in (prepared / "pages.jsonl").open() if line.strip()]
        questions = [json.loads(line) for line in (prepared / "questions.jsonl").open() if line.strip()]
        questions.sort(key=lambda row: int(row.get("query_index", 0)))
        first_question: dict[str, int] = {}
        for row in questions:
            first_question.setdefault(str(row["file_id"]), int(row.get("query_index", 0)))
        document_ids = sorted(
            {str(row["file_id"]) for row in pages},
            key=lambda file_id: (first_question.get(file_id, 10**9), file_id),
        )
        self.document_ids = document_ids if documents_limit <= 0 else document_ids[:documents_limit]
        selected_ids = set(self.document_ids)
        selected_questions = [row for row in questions if str(row["file_id"]) in selected_ids]
        if questions_limit > 0:
            selected_questions = selected_questions[:questions_limit]
        self.questions = [
            Question(
                question_id=str(row["id"]),
                query_index=int(row.get("query_index", 0)),
                question=str(row.get("question", "")),
                answer=str(row.get("answer", "")),
                file_id=str(row["file_id"]),
                doc_name=str(row.get("doc_name", "")),
                page_ids=[int(value) for value in row.get("page_ids", [])],
                domain=str(row.get("domain", "unknown")),
            )
            for row in selected_questions
        ]
        grouped: dict[str, list[PageChunk]] = defaultdict(list)
        for page in pages:
            file_id = str(page["file_id"])
            if file_id not in selected_ids:
                continue
            metadata = page.get("metadata") if isinstance(page.get("metadata"), dict) else {}
            grouped[file_id].append(PageChunk(
                file_id=file_id,
                doc_name=str(metadata.get("doc_name") or metadata.get("file_name") or file_id),
                page_number=int(page.get("page_number", 0)),
                page_id=str(page.get("id", "")),
                content=canonical_page_bytes(page),
            ))
        self.pages_by_document = {
            file_id: sorted(grouped[file_id], key=lambda chunk: chunk.page_number)
            for file_id in self.document_ids
        }

    def write_manifest(self, output: Path) -> dict[str, Any]:
        source = output / "canonical-source"
        source.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        for file_id in self.document_ids:
            for chunk in self.pages_by_document[file_id]:
                path = source / f"MMDocIR__{file_id}__page_{chunk.page_number:04d}.md"
                path.write_bytes(chunk.content)
                rows.append({
                    "file_id": file_id,
                    "doc_name": chunk.doc_name,
                    "page_number": chunk.page_number,
                    "page_id": chunk.page_id,
                    "path": str(path.relative_to(output)),
                    "bytes": len(chunk.content),
                    "sha256": sha256_bytes(chunk.content),
                })
        prepared_manifest = json.loads((self.prepared / "manifest.json").read_text())
        manifest = {
            "schema": "mmdocir-canonical-page-chunks-v1",
            "prepared_root": str(self.prepared),
            "prepared_manifest_sha256": sha256_bytes((self.prepared / "manifest.json").read_bytes()),
            "page_text_condition": prepared_manifest.get("page_text_condition"),
            "documents": len(self.document_ids),
            "pages": len(rows),
            "questions": len(self.questions),
            "one_page_per_vector_chunk": True,
            "embedding_input_contract": "prepared pages.jsonl content verbatim; whitespace-only content becomes U+2060",
            "locator_policy": "page identity is carried outside embedding text by product structured fields",
            "files": rows,
        }
        json_dump(output / "canonical-source-manifest.json", manifest)
        return manifest


class BaseAdapter:
    def __init__(self, args: argparse.Namespace, output: Path, corpus: Corpus, progress: Progress):
        self.args = args
        self.output = output
        self.corpus = corpus
        self.progress = progress
        self.resources: dict[str, dict[str, Any]] = {}

    def ingest(self) -> None:
        raise NotImplementedError

    def retrieve(self, question: Question, ordinal: int) -> list[Any]:
        raise NotImplementedError

    def hit_markers(self, question: Question, hit: Any) -> list[tuple[str, int]]:
        raise NotImplementedError


class FastGPTAdapter(BaseAdapter):
    def __init__(self, args: argparse.Namespace, output: Path, corpus: Corpus, progress: Progress):
        super().__init__(args, output, corpus, progress)
        env = parse_dotenv(ROOT / ".env")
        self.api_key = value_from(env, "FASTGPT_API_KEY")
        if not self.api_key:
            raise EvalError("FASTGPT_API_KEY_MISSING")
        self.client = ArtifactHTTP(value_from(env, "FASTGPT_BASE_URL", default="http://127.0.0.1:3000"), output, progress)
        self.agent_model = value_from(env, "MAAS_LLM_MODEL", default="qwen3-30b-a3b")

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        if isinstance(payload, dict) and payload.get("code") == 200 and "data" in payload:
            return payload["data"]
        return payload

    def _wait_dataset(self, dataset_id: str, expected: int) -> dict[str, Any]:
        deadline = time.monotonic() + self.args.index_wait
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            try:
                payload = self._unwrap(self.client.request(
                    "POST", "/api/core/dataset/collection/listV2", api_key=self.api_key,
                    json_body={"offset": 0, "pageSize": 10, "datasetId": dataset_id, "parentId": None, "searchText": ""},
                    operation=f"index-{dataset_id}",
                    timeout=max(float(self.args.upload_timeout), float(self.args.query_timeout), 600.0),
                ))
            except EvalError as exc:
                # A local Mongo/Redis pause can make the readiness endpoint miss a
                # single HTTP deadline even while the vector queue keeps working.
                # Retry only transport timeouts; API errors still fail fast.
                if "transport failure: timed out" not in str(exc):
                    raise
                self.progress.emit(
                    "ingest",
                    "FastGPT readiness poll timed out; retrying",
                    dataset_id=dataset_id,
                )
                time.sleep(self.args.poll_seconds)
                continue
            items = list_items(payload, ("list",))
            last = {
                "collections": len(items),
                "training": sum(int(item.get("trainingAmount", 0) or 0) for item in items if isinstance(item, dict)),
                "active_training": sum(int(item.get("activeTrainingAmount", 0) or 0) for item in items if isinstance(item, dict)),
                "errors": sum(int(item.get("finalErrorAmount", 0) or 0) for item in items if isinstance(item, dict)),
            }
            if last["errors"]:
                raise EvalError(f"FASTGPT_INDEX_FAILED: {last}")
            if len(items) == 1 and last["training"] == 0 and last["active_training"] == 0:
                return last
            time.sleep(self.args.poll_seconds)
        raise EvalError(f"FASTGPT_INDEX_TIMEOUT: expected={expected} last={last}")

    def ingest(self) -> None:
        total = len(self.corpus.document_ids)
        for ordinal, file_id in enumerate(self.corpus.document_ids, start=1):
            if file_id in self.resources:
                self.progress.emit("ingest", "FastGPT document reused", completed=ordinal, total=total)
                continue
            chunks = self.corpus.pages_by_document[file_id]
            created = self._unwrap(self.client.request(
                "POST", "/api/core/dataset/create", api_key=self.api_key,
                json_body={
                    "parentId": None, "type": "dataset",
                    "name": f"MMDocIR-{self.args.run_id}-{ordinal:03d}",
                    "intro": f"document-local {file_id}", "avatar": "",
                    "vectorModel": self.args.embedding_model, "agentModel": self.agent_model,
                }, operation=f"create-dataset-{ordinal:03d}",
            ))
            dataset_id = product_id(created)
            if not dataset_id:
                raise EvalError(f"FASTGPT_CREATE_DATASET_NO_ID: {file_id}")
            collection = self._unwrap(self.client.request(
                "POST", "/api/core/dataset/collection/create", api_key=self.api_key,
                json_body={"datasetId": dataset_id, "parentId": None, "name": chunks[0].doc_name, "type": "virtual"},
                operation=f"create-collection-{ordinal:03d}",
            ))
            collection_id = product_id(collection)
            if not collection_id:
                raise EvalError(f"FASTGPT_CREATE_COLLECTION_NO_ID: {file_id}")
            for batch_index in range(0, len(chunks), 200):
                batch = chunks[batch_index:batch_index + 200]
                payload = fastgpt_push_payload(collection_id, batch)
                for offset, item in enumerate(payload["data"], start=batch_index):
                    item["chunkIndex"] = offset
                self.client.request(
                    "POST", "/api/core/dataset/data/pushData", api_key=self.api_key,
                    json_body=payload, operation=f"push-{ordinal:03d}-{batch_index // 200 + 1:03d}",
                    timeout=self.args.upload_timeout,
                )
            index_state = self._wait_dataset(dataset_id, len(chunks))
            self.resources[file_id] = {"dataset_id": dataset_id, "collection_id": collection_id, "pages": len(chunks), "index": index_state}
            json_dump(self.output.parent / "resource-map.partial.json", self.resources)
            self.progress.emit("ingest", "FastGPT document ready", completed=ordinal, total=total, pages=len(chunks))

    def retrieve(self, question: Question, ordinal: int) -> list[Any]:
        dataset_id = self.resources[question.file_id]["dataset_id"]
        payload = self._unwrap(self.client.request(
            "POST", "/api/core/dataset/searchTest", api_key=self.api_key,
            json_body=fastgpt_search_payload(dataset_id, question.question),
            operation=f"retrieval-{ordinal:04d}", timeout=self.args.query_timeout,
        ))
        return list_items(payload, ("list",))[:self.args.top_k]

    def hit_markers(self, question: Question, hit: Any) -> list[tuple[str, int]]:
        return fastgpt_hit_markers(question.file_id, self.corpus.pages_by_document[question.file_id], hit)


class MaxKBAdapter(BaseAdapter):
    def __init__(self, args: argparse.Namespace, output: Path, corpus: Corpus, progress: Progress):
        super().__init__(args, output, corpus, progress)
        token_path = ROOT / ".local-services/maxkb_local/secrets/admin.token"
        if not token_path.exists():
            raise EvalError("MAXKB_ADMIN_TOKEN_MISSING")
        self.api_key = token_path.read_text().strip()
        self.client = ArtifactHTTP("http://127.0.0.1:8090/admin/api", output, progress)
        self.embedding_model_id = self._discover_embedding_model()

    def _request(self, method: str, path: str, *, body: Any = None, operation: str, timeout: int | None = None) -> Any:
        for attempt in range(1, 61):
            payload = self.client.request(
                method, path, api_key=self.api_key, json_body=body,
                operation=f"{operation}-try-{attempt:02d}" if attempt > 1 else operation,
                timeout=timeout,
            )
            if not is_maxkb_busy(payload):
                return unwrap(payload)
            self.progress.emit("ingest", "MaxKB task queue busy; bounded retry", operation=operation, attempt=attempt)
            time.sleep(5)
        raise EvalError(f"MAXKB_TASK_BUSY_TIMEOUT: {operation}")

    def _discover_embedding_model(self) -> str:
        payload = self._request("GET", "/workspace/default/model", operation="discover-embedding-model")
        candidates = list_items(payload)
        selected = choose_maxkb_embedding_model(candidates, self.args.embedding_model, "maas")
        model_id = str(selected.get("id") or "")
        if not model_id:
            raise EvalError("MAXKB_BGE_M3_MODEL_ID_MISSING")
        json_dump(self.output / "embedding-model.json", {
            "id": model_id,
            "name": selected.get("name"),
            "model_name": selected.get("model_name"),
            "model_type": selected.get("model_type"),
        })
        return model_id

    def _wait_document(self, knowledge_id: str, document_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.args.index_wait
        last: dict[str, Any] = {}
        refreshes = 0
        while time.monotonic() < deadline:
            payload = self._request(
                "GET", f"/workspace/default/knowledge/{knowledge_id}/document/{document_id}",
                operation=f"index-{document_id}",
            )
            last = payload if isinstance(payload, dict) else {"payload": payload}
            status = str(last.get("status", ""))
            if status.endswith("3"):
                if refreshes >= 3:
                    raise EvalError(f"MAXKB_INDEX_FAILED_AFTER_REFRESH: {status}")
                refreshes += 1
                self.progress.emit("ingest", "MaxKB retrying failed embedding paragraphs", document_id=document_id, refresh=refreshes)
                self._request(
                    "PUT", f"/workspace/default/knowledge/{knowledge_id}/document/{document_id}/refresh",
                    body={"state_list": ["3"]}, operation=f"refresh-failed-{document_id}-{refreshes}",
                )
                time.sleep(self.args.poll_seconds)
                continue
            if status.endswith("2"):
                return {"status": status, "failed_embedding_refreshes": refreshes}
            time.sleep(self.args.poll_seconds)
        raise EvalError(f"MAXKB_INDEX_TIMEOUT: {last}")

    def ingest(self) -> None:
        total = len(self.corpus.document_ids)
        for ordinal, file_id in enumerate(self.corpus.document_ids, start=1):
            if file_id in self.resources:
                self.progress.emit("ingest", "MaxKB document reused", completed=ordinal, total=total)
                continue
            chunks = self.corpus.pages_by_document[file_id]
            knowledge = self._request(
                "POST", "/workspace/default/knowledge/base",
                body={
                    "name": f"MMDocIR-{self.args.run_id}-{ordinal:03d}", "folder_id": "default",
                    "desc": f"document-local {file_id}", "embedding_model_id": self.embedding_model_id,
                }, operation=f"create-knowledge-{ordinal:03d}",
            )
            knowledge_id = str(first_value(knowledge, ("id",)) or "")
            if not knowledge_id:
                raise EvalError(f"MAXKB_CREATE_KNOWLEDGE_NO_ID: {file_id}")
            documents = self._request(
                "PUT", f"/workspace/default/knowledge/{knowledge_id}/document/batch_create",
                body=maxkb_document_payload(chunks[0].doc_name, chunks),
                operation=f"create-document-{ordinal:03d}", timeout=self.args.upload_timeout,
            )
            document_id = str(first_value(documents, ("id",)) or "")
            if not document_id:
                raise EvalError(f"MAXKB_CREATE_DOCUMENT_NO_ID: {file_id}")
            index_state = self._wait_document(knowledge_id, document_id)
            self.resources[file_id] = {"knowledge_id": knowledge_id, "document_id": document_id, "pages": len(chunks), "index": index_state}
            json_dump(self.output.parent / "resource-map.partial.json", self.resources)
            self.progress.emit("ingest", "MaxKB document ready", completed=ordinal, total=total, pages=len(chunks))

    def retrieve(self, question: Question, ordinal: int) -> list[Any]:
        knowledge_id = self.resources[question.file_id]["knowledge_id"]
        payload = self._request(
            "POST", f"/workspace/default/knowledge/{knowledge_id}/hit_test",
            body={"query_text": question.question, "top_number": self.args.top_k, "similarity": 0.0, "search_mode": "embedding"},
            operation=f"retrieval-{ordinal:04d}", timeout=self.args.query_timeout,
        )
        return sort_maxkb_hits(list_items(payload))[:self.args.top_k]

    def hit_markers(self, question: Question, hit: Any) -> list[tuple[str, int]]:
        return maxkb_hit_markers(question.file_id, hit)


def probe_maas(args: argparse.Namespace, output: Path) -> dict[str, Any]:
    env = parse_dotenv(ROOT / ".env")
    provider = Provider(
        name="maas",
        base_url=value_from(env, "MAAS_BASE_URL", default="https://api.modelarts-maas.com/v1"),
        api_key=value_from(env, "MAAS_API_KEY"),
        llm_model="",
        embedding_model=args.embedding_model,
        embedding_dimension=1024,
    )
    if not provider.api_key:
        raise EvalError("MAAS_API_KEY_MISSING")
    payload = external_json(provider, "/embeddings", body={
        "model": args.embedding_model,
        "input": ["MMDocIR bge-m3 parity probe"],
        "encoding_format": "float",
    })
    vectors = list_items(payload, ("data",))
    dimension = len(vectors[0].get("embedding", [])) if vectors and isinstance(vectors[0], dict) else 0
    if dimension != 1024:
        raise EvalError(f"MAAS_BGE_M3_DIMENSION_{dimension}")
    result = {"provider": "Huawei MaaS", "model": args.embedding_model, "dimension": dimension, "ready": True}
    json_dump(output / "provider-probe.json", result)
    return result


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def load_reused_results(path: Path, corpus: Corpus) -> dict[str, dict[str, Any]]:
    """Load compatible per-question rows from an earlier run.

    The full MMDocIR run can reuse a completed pilot for the exact same
    document-local resources.  Validate the question-level contract before
    skipping live retrieval so a stale or differently ordered pilot cannot be
    silently mixed into the full denominator.
    """

    if not path.is_file():
        raise EvalError(f"REUSE_RESULTS_MISSING: {path}")
    expected = {question.question_id: question for question in corpus.questions}
    reused: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvalError(f"REUSE_RESULTS_INVALID_JSON:{path}:{line_number}") from exc
            if not isinstance(row, dict):
                raise EvalError(f"REUSE_RESULTS_ROW_NOT_OBJECT:{path}:{line_number}")
            question_id = str(row.get("question_id", ""))
            question = expected.get(question_id)
            if question is None:
                raise EvalError(f"REUSE_RESULTS_UNKNOWN_QUESTION:{question_id}")
            if question_id in reused:
                raise EvalError(f"REUSE_RESULTS_DUPLICATE_QUESTION:{question_id}")
            checks = {
                "query_index": question.query_index,
                "question": question.question,
                "file_id": question.file_id,
                "doc_name": question.doc_name,
                "page_ids": question.page_ids,
                "domain": question.domain,
            }
            for field, expected_value in checks.items():
                if row.get(field) != expected_value:
                    raise EvalError(f"REUSE_RESULTS_METADATA_MISMATCH:{question_id}:{field}")
            if row.get("status") not in {"ok", "error"}:
                raise EvalError(f"REUSE_RESULTS_STATUS_INVALID:{question_id}:{row.get('status')}")
            if row.get("status") == "ok":
                recall_at_k = row.get("recall_at_k")
                if not isinstance(recall_at_k, dict) or any(str(k) not in recall_at_k for k in (1, 3, 5, 10)):
                    raise EvalError(f"REUSE_RESULTS_RECALL_MISSING:{question_id}")
                try:
                    float(row["latency_ms"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise EvalError(f"REUSE_RESULTS_LATENCY_MISSING:{question_id}") from exc
            reused[question_id] = dict(row)
    if not reused:
        raise EvalError(f"REUSE_RESULTS_EMPTY: {path}")
    return reused


def evaluate(
    adapter: BaseAdapter,
    corpus: Corpus,
    args: argparse.Namespace,
    output: Path,
    progress: Progress,
    reused_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    cutoffs = (1, 3, 5, 10)
    reused_results = reused_results or {}
    reused_count = 0
    live_count = sum(1 for question in corpus.questions if question.question_id not in reused_results)

    def retrieve_live(ordinal: int, question: Question) -> dict[str, Any]:
        started = time.monotonic()
        row = {
            "ordinal": ordinal, "question_id": question.question_id, "query_index": question.query_index,
            "question": question.question, "file_id": question.file_id, "doc_name": question.doc_name,
            "page_ids": question.page_ids, "domain": question.domain, "result_source": "live",
        }
        try:
            hits = adapter.retrieve(question, ordinal)
            latency_ms = round((time.monotonic() - started) * 1000, 3)
            ranked = [adapter.hit_markers(question, hit) for hit in hits]
            row.update({"status": "ok", "latency_ms": latency_ms, "hit_count": len(hits)})
            row.update(score_page_recall(question, ranked, cutoffs))
        except EvalError as exc:
            row.update({"status": "error", "error": str(exc)})
        return row

    results_path = output / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=args.query_workers) as executor:
            futures = {
                ordinal: executor.submit(retrieve_live, ordinal, question)
                for ordinal, question in enumerate(corpus.questions, start=1)
                if question.question_id not in reused_results
            }
            for ordinal, question in enumerate(corpus.questions, start=1):
                if question.question_id in reused_results:
                    row = dict(reused_results[question.question_id])
                    row["ordinal"] = ordinal
                    row["result_source"] = "reused"
                    reused_count += 1
                    if row.get("status") == "ok":
                        latencies.append(float(row["latency_ms"]))
                else:
                    row = futures[ordinal].result()
                    if row.get("status") == "ok":
                        latencies.append(float(row["latency_ms"]))
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                rows.append(row)
                if ordinal == 1 or ordinal == len(corpus.questions) or ordinal % args.progress_every == 0:
                    progress.emit("evaluation", "question progress", completed=ordinal, total=len(corpus.questions))
                if args.query_interval and row.get("result_source") == "live":
                    time.sleep(args.query_interval)
    results_path.with_suffix(".jsonl.sha256").write_text(f"{sha256_bytes(results_path.read_bytes())}  {results_path.name}\n")
    successful = [row for row in rows if row.get("status") == "ok"]
    recall = {
        str(k): sum(float(row["recall_at_k"][str(k)]) for row in successful) / len(successful) if successful else None
        for k in cutoffs
    }
    domains: dict[str, dict[str, float]] = {}
    for domain in sorted({row["domain"] for row in successful}):
        subset = [row for row in successful if row["domain"] == domain]
        domains[domain] = {
            str(k): sum(float(row["recall_at_k"][str(k)]) for row in subset) / len(subset)
            for k in cutoffs
        }
    metrics = {
        "protocol": "MMDocIR document-local dense retrieval (local competitor/BGE-M3)",
        "granularity": "page", "embedding_model": args.embedding_model,
        "embedding_provider": "Huawei MaaS", "native_qa": "not_applicable_reference_is_retrieval_only",
        "attempts": len(rows), "successful_attempts": len(successful), "failed_attempts": len(rows) - len(successful),
        "reused_attempts": reused_count, "live_attempts": live_count,
        "result_source": "mixed_reused_and_live" if reused_count and live_count else ("reused" if reused_count else "live"),
        "recall_at_k": recall, "by_domain_recall_at_k": domains,
        "latency_p50_ms": median(latencies) if latencies else None,
        "latency_p95_ms": percentile(latencies, 0.95),
    }
    json_dump(output / "metrics.json", metrics)
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=("fastgpt_local", "maxkb_local"), required=True)
    parser.add_argument("--prepared-root", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--phase", choices=("pilot", "full"), default="pilot")
    parser.add_argument("--protocol", choices=("document_local",), default="document_local")
    parser.add_argument("--embedding-model", default="bge-m3")
    parser.add_argument("--documents-limit", type=int, default=20, help="0 means all 313 documents")
    parser.add_argument("--questions-limit", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--index-wait", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=3)
    parser.add_argument("--upload-timeout", type=int, default=600)
    parser.add_argument("--query-timeout", type=int, default=120)
    parser.add_argument("--query-interval", type=float, default=0.08)
    parser.add_argument("--query-workers", type=int, default=1, help="concurrent retrieval workers; 1 preserves serial evaluation")
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--reuse-resource-map", type=Path, help="reuse a completed compatible ingest resource-map.json")
    parser.add_argument("--resume-resource-map", type=Path, help="resume ingest from an incremental resource-map.partial.json")
    parser.add_argument("--resume-resource-entries", type=Path, help="merge additional completed resource entries into the resume map")
    parser.add_argument("--reuse-results", type=Path, help="reuse compatible per-question retrieval rows from an earlier run")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.phase == "full" and args.documents_limit == 20:
        args.documents_limit = 0
    if args.embedding_model != "bge-m3":
        raise SystemExit("model parity guard: the MOI reference run uses bge-m3")
    if args.query_workers < 1:
        raise SystemExit("--query-workers must be >= 1")
    output = args.output_root / args.run_id / args.system / "page" / args.phase
    output.mkdir(parents=True, exist_ok=False)
    progress = Progress(RUNTIME_ROOT / f"{args.system}-document-local-progress.jsonl")
    status_path = RUNTIME_ROOT / f"{args.system}-document-local-status.json"
    try:
        corpus = Corpus(args.prepared_root, args.documents_limit, args.questions_limit)
        source_manifest = corpus.write_manifest(output)
        reused_results = load_reused_results(args.reuse_results, corpus) if args.reuse_results else {}
        if args.reuse_results:
            json_dump(output / "result-reuse.json", {
                "source": str(args.reuse_results),
                "sha256": sha256_bytes(args.reuse_results.read_bytes()),
                "questions": len(reused_results),
                "question_ids": sorted(reused_results),
            })
        provider = probe_maas(args, output)
        json_dump(output / "run-manifest.json", {
            "schema": "mmdocir-document-local-competitor-v1", "run_id": args.run_id,
            "system_id": args.system, "deployment_mode": "self_hosted", "condition": "page",
            "protocol": args.protocol, "prepared_root": str(args.prepared_root),
            "embedding_model": args.embedding_model, "embedding_provider": provider,
            "model_egress": "external", "native_qa": "skipped_to_match_moi_reference",
            "reused_results": {
                "source": str(args.reuse_results),
                "questions": len(reused_results),
            } if args.reuse_results else None,
            "canonical_source": source_manifest,
        })
        json_dump(status_path, {"status": "ingesting", "run_id": args.run_id, "system_id": args.system, "output": str(output)})
        adapter: BaseAdapter = FastGPTAdapter(args, output / "http-artifacts", corpus, progress) if args.system == "fastgpt_local" else MaxKBAdapter(args, output / "http-artifacts", corpus, progress)
        if args.reuse_resource_map:
            adapter.resources = json.loads(args.reuse_resource_map.read_text())
            missing = sorted(set(corpus.document_ids).difference(adapter.resources))
            if missing:
                raise EvalError(f"REUSE_RESOURCE_MAP_MISSING_DOCUMENTS: {missing[:3]}")
            json_dump(output / "resource-reuse.json", {
                "source": str(args.reuse_resource_map),
                "sha256": sha256_bytes(args.reuse_resource_map.read_bytes()),
                "documents": len(adapter.resources),
            })
        elif args.resume_resource_map:
            adapter.resources = json.loads(args.resume_resource_map.read_text())
            if args.resume_resource_entries:
                extra_resources = json.loads(args.resume_resource_entries.read_text())
                overlap = sorted(set(adapter.resources).intersection(extra_resources))
                if overlap:
                    raise EvalError(f"RESUME_RESOURCE_ENTRY_ALREADY_PRESENT: {overlap[:3]}")
                adapter.resources.update(extra_resources)
            unknown = sorted(set(adapter.resources).difference(corpus.document_ids))
            if unknown:
                raise EvalError(f"RESUME_RESOURCE_MAP_UNKNOWN_DOCUMENTS: {unknown[:3]}")
            adapter.ingest()
            json_dump(output / "resource-resume.json", {
                "source": str(args.resume_resource_map),
                "sha256": sha256_bytes(args.resume_resource_map.read_bytes()),
                "additional_source": str(args.resume_resource_entries) if args.resume_resource_entries else None,
                "additional_sha256": sha256_bytes(args.resume_resource_entries.read_bytes()) if args.resume_resource_entries else None,
                "documents_reused": len(adapter.resources),
            })
        else:
            adapter.ingest()
        json_dump(output / "resource-map.json", adapter.resources)
        json_dump(status_path, {"status": "evaluating", "run_id": args.run_id, "system_id": args.system, "output": str(output)})
        metrics = evaluate(adapter, corpus, args, output, progress, reused_results)
        summary = {"status": "success", "run_id": args.run_id, "system_id": args.system, "output": str(output), "metrics": metrics}
        json_dump(output / "summary.json", summary)
        json_dump(status_path, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        failure = {"status": "error", "run_id": args.run_id, "system_id": args.system, "output": str(output), "error": str(exc), "type": type(exc).__name__}
        json_dump(output / "failure.json", failure)
        json_dump(status_path, failure)
        print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
