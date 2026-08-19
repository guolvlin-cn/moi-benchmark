#!/usr/bin/env python3
"""Run the frozen 50-row WikiEval fixture on local FastGPT or MaxKB.

The benchmark keeps product retrieval and native QA as separate observable
steps.  Retrieval is scored by the frozen source filename; answer quality uses
the deterministic reference-keyword diagnostic already used by the MOI/Dify
WikiEval run.  Raw HTTP artifacts are redacted by ``ArtifactHTTP``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
PLATFORM_ROOT = HERE.parents[1]
ROOT = PLATFORM_ROOT.parent

import sys

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

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
from fastgpt_local.fastgpt_local import build_isolated_app_payload  # noqa: E402


DEFAULT_FIXTURE = ROOT / "runs/stage1/ragas-wikieval-moi/20260807-160000-wikieval/artifacts"
DEFAULT_OUTPUT = ROOT / "runs/stage1/wikieval-competitors"


class Fixture:
    def __init__(self, cases: list[dict[str, Any]], documents: list[Path], manifest: dict[str, Any]):
        self.cases = cases
        self.documents = documents
        self.manifest = manifest


def load_fixture(questions: Path, documents: Path) -> Fixture:
    cases = [json.loads(line) for line in questions.open(encoding="utf-8") if line.strip()]
    files = sorted(path for path in documents.iterdir() if path.is_file() and not path.name.startswith("."))
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    return Fixture(cases, files, {
        "schema": "wikieval-frozen-local-competitor-v1",
        "questions": len(cases),
        "documents": len(files),
        "questions_sha256": hashlib.sha256(questions.read_bytes()).hexdigest(),
        "document_sha256": hashes,
    })


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _normal(value: str) -> str:
    return " ".join(str(value).casefold().split())


def _keyword_recall(answer: str, keywords: list[Any]) -> float:
    normalized = _normal(answer)
    selected = [_normal(str(value)) for value in keywords if str(value).strip()]
    return sum(value in normalized for value in selected) / len(selected) if selected else 0.0


def score_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = len(rows)
    successful = [row for row in rows if row.get("status") == "success"]
    source_at: dict[int, float] = {}
    reciprocal: list[float] = []
    for row in rows:
        relevant = set(row.get("case", {}).get("relevant_documents", []))
        ranked = [str(chunk.get("source_name", "")) for chunk in row.get("chunks", [])]
        ranks = [index for index, name in enumerate(ranked, start=1) if name in relevant]
        reciprocal.append(1.0 / min(ranks) if ranks else 0.0)
        for cutoff in (1, 3, 5, 10):
            source_at[cutoff] = source_at.get(cutoff, 0.0) + float(bool(relevant.intersection(ranked[:cutoff])))
    retrieval = [float(row["retrieval_latency_ms"]) for row in successful if row.get("retrieval_latency_ms") is not None]
    generation = [float(row["generation_latency_ms"]) for row in successful if row.get("generation_latency_ms") is not None]
    keyword_scores = [
        _keyword_recall(str(row.get("answer", "")), row.get("case", {}).get("expected_answer_keywords", []))
        for row in successful
    ]
    metrics: dict[str, Any] = {
        "attempts": attempts,
        "successful_attempts": len(successful),
        "success_rate": len(successful) / attempts if attempts else 0.0,
        "first_pass_success_rate": sum(not row.get("recovery", {}).get("first_pass_error") for row in rows) / attempts if attempts else 0.0,
        "recovered_attempts": sum(bool(row.get("recovery", {}).get("first_pass_error")) and row.get("status") == "success" for row in rows),
        "mrr": sum(reciprocal) / attempts if attempts else 0.0,
        "answer_non_empty_rate": sum(bool(str(row.get("answer", "")).strip()) for row in rows) / attempts if attempts else 0.0,
        "reference_keyword_recall": sum(keyword_scores) / len(keyword_scores) if keyword_scores else 0.0,
        "retrieval_latency_ms_p50": median(retrieval) if retrieval else None,
        "retrieval_latency_ms_p95": percentile(retrieval, 0.95),
        "generation_latency_ms_p50": median(generation) if generation else None,
        "generation_latency_ms_p95": percentile(generation, 0.95),
    }
    for cutoff in (1, 3, 5, 10):
        metrics[f"source_recall_at_{cutoff}"] = source_at.get(cutoff, 0.0) / attempts if attempts else 0.0
    return metrics


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "code" in payload:
        if int(payload.get("code", 0) or 0) != 200:
            raise EvalError(f"PRODUCT_API_ERROR: {payload.get('message', payload)}")
        return payload.get("data")
    return payload


def _answer(payload: Any) -> str:
    choices = payload.get("choices", []) if isinstance(payload, dict) else []
    if choices and isinstance(choices[0], dict):
        return str(choices[0].get("message", {}).get("content", ""))
    return str(first_value(payload, ("answer", "answer_text", "content", "text")) or "")


class FastGPT:
    system_id = "fastgpt_local"

    def __init__(self, args: argparse.Namespace, fixture: Fixture, output: Path, progress: Progress):
        env = parse_dotenv(ROOT / ".env")
        self.key = value_from(env, "FASTGPT_API_KEY")
        if not self.key:
            raise EvalError("FASTGPT_API_KEY_MISSING")
        self.client = ArtifactHTTP(value_from(env, "FASTGPT_BASE_URL", default="http://127.0.0.1:3000"), output, progress)
        self.args, self.fixture, self.output, self.progress = args, fixture, output, progress
        self.dataset_id = ""
        self.app_id = ""

    def setup(self) -> dict[str, Any]:
        name = f"WikiEval-{self.args.run_id}"
        created = _unwrap(self.client.request("POST", "/api/core/dataset/create", api_key=self.key, json_body={
            "parentId": None, "type": "dataset", "name": name, "intro": "Frozen WikiEval local benchmark", "avatar": "",
            "vectorModel": self.args.embedding_model, "agentModel": self.args.chat_model,
        }, operation="create-dataset"))
        self.dataset_id = str(created if isinstance(created, (str, int)) else first_value(created, ("datasetId", "id", "_id")) or "")
        if not self.dataset_id:
            raise EvalError("FASTGPT_CREATE_DATASET_NO_ID")
        collections: dict[str, str] = {}
        for ordinal, path in enumerate(self.fixture.documents, start=1):
            created_collection = _unwrap(self.client.request("POST", "/api/core/dataset/collection/create", api_key=self.key, json_body={
                "datasetId": self.dataset_id, "parentId": None, "name": path.name, "type": "virtual",
            }, operation=f"create-collection-{ordinal:03d}"))
            collection_id = str(created_collection if isinstance(created_collection, (str, int)) else first_value(created_collection, ("collectionId", "id", "_id")) or "")
            if not collection_id:
                raise EvalError(f"FASTGPT_CREATE_COLLECTION_NO_ID: {path.name}")
            self.client.request("POST", "/api/core/dataset/data/pushData", api_key=self.key, json_body={
                "collectionId": collection_id, "trainingType": "chunk", "data": [{"q": path.read_text(encoding="utf-8"), "chunkIndex": 0}],
            }, operation=f"push-document-{ordinal:03d}", timeout=self.args.upload_timeout)
            collections[collection_id] = path.name
            if ordinal == 1 or ordinal % 10 == 0 or ordinal == len(self.fixture.documents):
                self.progress.emit("ingest", "FastGPT WikiEval documents submitted", completed=ordinal, total=len(self.fixture.documents))
        deadline = time.monotonic() + self.args.index_wait
        while time.monotonic() < deadline:
            listing = _unwrap(self.client.request("POST", "/api/core/dataset/collection/listV2", api_key=self.key, json_body={
                "offset": 0, "pageSize": 100, "datasetId": self.dataset_id, "parentId": None, "searchText": "",
            }, operation="index-status"))
            items = list_items(listing, ("list",))
            if any(item.get("hasError") or item.get("finalErrorAmount", 0) for item in items if isinstance(item, dict)):
                raise EvalError("FASTGPT_INDEX_FAILED")
            if len(items) >= len(collections) and all(
                int(item.get("trainingAmount", 0) or 0) == 0 and int(item.get("activeTrainingAmount", 0) or 0) == 0
                for item in items if isinstance(item, dict)
            ):
                break
            time.sleep(self.args.poll_seconds)
        else:
            raise EvalError("FASTGPT_INDEX_TIMEOUT")
        payload = build_isolated_app_payload(provider_name="qianfan", dataset_id=self.dataset_id, dataset_name=name)
        for module in payload["modules"]:
            for item in module.get("inputs", []):
                if item.get("key") == "model":
                    item["value"] = self.args.chat_model
                elif item.get("key") == "systemPrompt":
                    item["value"] = (
                        "Answer only from the supplied knowledge. Answer in the same language as the question; "
                        "for WikiEval's English questions, answer in English. If knowledge is insufficient, say so."
                    )
                elif item.get("key") == "datasets":
                    item["value"][0]["vectorModel"] = {"model": self.args.embedding_model}
        app = _unwrap(self.client.request("POST", "/api/core/app/create", api_key=self.key, json_body=payload, operation="create-app"))
        self.app_id = str(app if isinstance(app, (str, int)) else first_value(app, ("appId", "id", "_id")) or "")
        if not self.app_id:
            raise EvalError("FASTGPT_CREATE_APP_NO_ID")
        return {"dataset_id": self.dataset_id, "app_id": self.app_id, "collections": collections}

    def run_case(self, case: dict[str, Any], ordinal: int) -> tuple[list[dict[str, Any]], str, float, float, Any]:
        started = time.monotonic()
        retrieval = _unwrap(self.client.request("POST", "/api/core/dataset/searchTest", api_key=self.key, json_body={
            "datasetId": self.dataset_id, "text": case["question"], "limit": 20000, "similarity": 0,
            "searchMode": "embedding", "usingReRank": False, "datasetSearchUsingExtensionQuery": False,
        }, operation=f"retrieval-{ordinal:03d}", timeout=self.args.query_timeout))
        retrieval_ms = (time.monotonic() - started) * 1000
        hits = list_items(retrieval, ("list",))[:self.args.top_k]
        chunks = [{"rank": rank, "source_name": str(hit.get("sourceName", "")), "content": str(hit.get("q", ""))}
                  for rank, hit in enumerate(hits, start=1) if isinstance(hit, dict)]
        started = time.monotonic()
        native = self.client.request("POST", "/api/v1/chat/completions", api_key=self.key, json_body={
            "appId": self.app_id, "chatId": str(uuid.uuid4()), "stream": False, "detail": True,
            "messages": [{"role": "user", "content": case["question"]}],
        }, operation=f"native-{ordinal:03d}", timeout=self.args.native_timeout)
        generation_ms = (time.monotonic() - started) * 1000
        return chunks, _answer(native), retrieval_ms, generation_ms, native, {}


class MaxKB:
    system_id = "maxkb_local"

    def __init__(self, args: argparse.Namespace, fixture: Fixture, output: Path, progress: Progress):
        token = ROOT / ".local-services/maxkb_local/secrets/admin.token"
        if not token.exists():
            raise EvalError("MAXKB_ADMIN_TOKEN_MISSING")
        self.admin_key = token.read_text().strip()
        self.client = ArtifactHTTP("http://127.0.0.1:8090/admin/api", output, progress)
        self.args, self.fixture, self.output, self.progress = args, fixture, output, progress
        self.knowledge_id = self.app_id = self.app_key = ""

    def request(self, method: str, path: str, body: Any = None, operation: str = "request", timeout: int | None = None) -> Any:
        return _unwrap(self.client.request(method, path, api_key=self.admin_key, json_body=body, operation=operation, timeout=timeout))

    def _models(self) -> tuple[str, str]:
        models = list_items(self.request("GET", "/workspace/default/model", operation="discover-models"))
        embeddings = [item for item in models if isinstance(item, dict) and str(item.get("model_name", "")).casefold() == self.args.embedding_model.casefold()
                      and "maas" in str(item.get("name", "")).casefold()]
        chats = [item for item in models if isinstance(item, dict) and str(item.get("model_name", "")).casefold() == self.args.chat_model.casefold()
                 and "qianfan" in str(item.get("name", "")).casefold()]
        if len(embeddings) != 1 or len(chats) != 1:
            raise EvalError(f"MAXKB_MODEL_MATCH: embedding={len(embeddings)} chat={len(chats)}")
        return str(embeddings[0]["id"]), str(chats[0]["id"])

    def _create_app_key(self) -> str:
        url = f"http://127.0.0.1:8090/admin/api/workspace/default/application/{self.app_id}/application_key"
        request = Request(url, headers={"Authorization": f"Bearer {self.admin_key}", "Accept": "application/json"}, method="POST")
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        secret = str(first_value(payload, ("secret_key",)) or "")
        if not secret:
            raise EvalError("MAXKB_CREATE_APP_KEY_FAILED")
        json_dump(self.output / "application-key-redacted.json", {"created": True, "application_id": self.app_id})
        return secret

    def setup(self) -> dict[str, Any]:
        embedding_id, chat_id = self._models()
        if self.args.reuse_resources:
            reused = json.loads(self.args.reuse_resources.read_text(encoding="utf-8"))
            # Accept either the runner's resources.json or the redacted
            # ArtifactHTTP response from a setup attempt interrupted after
            # batch_create.  This keeps successful embeddings instead of
            # rebuilding the vector space after one transient paragraph error.
            if "response" in reused:
                created_rows = reused.get("response", {}).get("body", {}).get("data", [])
                self.knowledge_id = str(first_value(created_rows, ("knowledge_id",)) or "")
                ids = [str(item.get("id")) for item in created_rows if isinstance(item, dict) and item.get("id")]
            else:
                self.knowledge_id = str(reused.get("knowledge_id", ""))
                ids = [str(value) for value in reused.get("documents", [])]
            if not self.knowledge_id or len(ids) != len(self.fixture.documents):
                raise EvalError("MAXKB_REUSE_RESOURCES_INVALID")
        else:
            knowledge = self.request("POST", "/workspace/default/knowledge/base", {
                "name": f"WikiEval-{self.args.run_id}", "folder_id": "default", "desc": "Frozen WikiEval local benchmark",
                "embedding_model_id": embedding_id,
            }, "create-knowledge")
            self.knowledge_id = str(first_value(knowledge, ("id",)) or "")
            if not self.knowledge_id:
                raise EvalError("MAXKB_CREATE_KNOWLEDGE_NO_ID")
            body = [{"name": path.name, "paragraphs": [{"title": path.name, "content": path.read_text(encoding="utf-8")}]} for path in self.fixture.documents]
            created = self.request("PUT", f"/workspace/default/knowledge/{self.knowledge_id}/document/batch_create", body,
                                   "create-documents", self.args.upload_timeout)
            documents = list_items(created)
            ids = [str(item.get("id")) for item in documents if isinstance(item, dict) and item.get("id")]
            if len(ids) != len(self.fixture.documents):
                raise EvalError(f"MAXKB_DOCUMENT_COUNT_{len(ids)}")
        deadline = time.monotonic() + self.args.index_wait
        refreshes: dict[str, int] = {}
        while time.monotonic() < deadline:
            statuses: list[tuple[str, str]] = []
            for index, document_id in enumerate(ids, start=1):
                item = self.request("GET", f"/workspace/default/knowledge/{self.knowledge_id}/document/{document_id}", operation=f"index-{index:03d}")
                statuses.append((document_id, str(item.get("status", "")) if isinstance(item, dict) else ""))
            failed = [document_id for document_id, status in statuses if status.endswith("3")]
            for document_id in failed:
                refreshes[document_id] = refreshes.get(document_id, 0) + 1
                if refreshes[document_id] > 3:
                    raise EvalError(f"MAXKB_INDEX_FAILED_AFTER_REFRESH: {document_id}")
                self.progress.emit("ingest", "MaxKB retrying failed WikiEval paragraph", document_id=document_id,
                                   refresh=refreshes[document_id])
                self.request("PUT", f"/workspace/default/knowledge/{self.knowledge_id}/document/{document_id}/refresh",
                             {"state_list": ["3"]}, f"refresh-{document_id}-{refreshes[document_id]}")
            if statuses and all(status.endswith("2") for _, status in statuses):
                break
            self.progress.emit("ingest", "MaxKB WikiEval indexing", ready=sum(status.endswith("2") for _, status in statuses), total=len(statuses))
            time.sleep(self.args.poll_seconds)
        else:
            raise EvalError("MAXKB_INDEX_TIMEOUT")
        app = self.request("POST", "/workspace/default/application", {
            "name": f"WikiEval-{self.args.run_id}", "desc": "Frozen WikiEval generative RAG", "folder_id": "default",
            "model_id": chat_id, "dialogue_number": 3, "prologue": "", "knowledge_id_list": [self.knowledge_id],
            # MaxKB v2.10.4 hydrates paragraph rows without preserving vector
            # rank.  WikiEval has exactly one gold source per question, so the
            # native app requests one product-ranked paragraph and avoids
            # arbitrary database order consuming the context budget.
            "knowledge_setting": {"top_n": 1, "similarity": 0.0, "max_paragraph_char_number": 20000, "search_mode": "embedding",
                                  "no_references_setting": {"status": "designated_answer", "value": "No matching knowledge."}},
            "model_setting": {"prompt": "Use only the following retrieved knowledge:\n{data}\n\nQuestion: {question}\n\nAnswer in English.",
                              "system": "Grounded RAG assistant. Answer in the same language as the question; WikiEval questions are English.",
                              "no_references_prompt": "No relevant knowledge was retrieved."},
            "problem_optimization": False, "type": "SIMPLE", "model_params_setting": {"temperature": 0.1, "max_tokens": 1024},
        }, "create-app")
        self.app_id = str(first_value(app, ("id",)) or "")
        if not self.app_id:
            raise EvalError("MAXKB_CREATE_APP_NO_ID")
        self.request("PUT", f"/workspace/default/application/{self.app_id}/publish", {}, "publish-app")
        self.app_key = self._create_app_key()
        return {"knowledge_id": self.knowledge_id, "application_id": self.app_id, "documents": ids,
                "embedding_model_id": embedding_id, "chat_model_id": chat_id}

    def run_case(self, case: dict[str, Any], ordinal: int) -> tuple[list[dict[str, Any]], str, float, float, Any]:
        recovery: dict[str, Any] = {"retrieval_attempts": 0, "native_attempts": 0, "first_pass_error": None}
        retrieval_started = time.monotonic()
        hits = None
        for attempt in range(1, 4):
            recovery["retrieval_attempts"] = attempt
            try:
                hits = self.request("POST", f"/workspace/default/knowledge/{self.knowledge_id}/hit_test", {
                    "query_text": case["question"], "top_number": self.args.top_k, "similarity": 0.0, "search_mode": "embedding",
                }, f"retrieval-{ordinal:03d}-try-{attempt}", self.args.query_timeout)
                break
            except EvalError as exc:
                if attempt == 1:
                    recovery["first_pass_error"] = f"retrieval: {exc}"
                if attempt >= 3 or not any(marker in str(exc).casefold() for marker in ("connection error", "transport failure", "timed out", "timeout")):
                    raise
                time.sleep(2 ** attempt)
        retrieval_ms = (time.monotonic() - retrieval_started) * 1000
        hits = sorted(list_items(hits), key=lambda item: float(item.get("comprehensive_score", item.get("similarity", 0)) or 0), reverse=True)
        chunks = [{"rank": rank, "source_name": str(hit.get("document_name", "")), "content": str(hit.get("content", ""))}
                  for rank, hit in enumerate(hits[:self.args.top_k], start=1) if isinstance(hit, dict)]
        generation_started = time.monotonic()
        public = ArtifactHTTP("http://127.0.0.1:8090/chat/api", self.output, self.progress)
        native = None
        for attempt in range(1, 4):
            recovery["native_attempts"] = attempt
            try:
                opened = _unwrap(public.request("GET", "/open", api_key=self.app_key,
                                                operation=f"open-session-{ordinal:03d}-try-{attempt}", timeout=self.args.native_timeout))
                chat_id = str(opened if isinstance(opened, (str, int)) else first_value(opened, ("chat_id", "id")) or "")
                if not chat_id:
                    raise EvalError("MAXKB_OPEN_SESSION_NO_CHAT_ID")
                native = _unwrap(public.request("POST", f"/chat_message/{chat_id}", api_key=self.app_key, json_body={
                    "message": case["question"], "stream": False, "re_chat": False,
                }, operation=f"native-{ordinal:03d}-try-{attempt}", timeout=self.args.native_timeout))
                break
            except EvalError as exc:
                if attempt == 1 and not recovery["first_pass_error"]:
                    recovery["first_pass_error"] = f"native: {exc}"
                if attempt >= 3 or not any(marker in str(exc).casefold() for marker in ("connection error", "transport failure", "timed out", "timeout")):
                    raise
                time.sleep(2 ** attempt)
        generation_ms = (time.monotonic() - generation_started) * 1000
        return chunks, _answer(native), retrieval_ms, generation_ms, native, recovery


def run(args: argparse.Namespace) -> Path:
    fixture = load_fixture(args.fixture / "questions.jsonl", args.fixture / "documents")
    if args.questions_limit > 0:
        fixture.cases = fixture.cases[:args.questions_limit]
        fixture.manifest = {**fixture.manifest, "questions_selected": len(fixture.cases)}
    output = args.output_root / args.run_id / args.system
    output.mkdir(parents=True, exist_ok=False)
    progress = Progress(output / "progress.jsonl")
    json_dump(output / "fixture-manifest.json", fixture.manifest)
    adapter = FastGPT(args, fixture, output / "http-artifacts", progress) if args.system == "fastgpt_local" else MaxKB(args, fixture, output / "http-artifacts", progress)
    resources = adapter.setup()
    json_dump(output / "resources.json", resources)
    rows: list[dict[str, Any]] = []
    results = output / "results.jsonl"
    with results.open("w", encoding="utf-8") as handle:
        for ordinal, case in enumerate(fixture.cases, start=1):
            row: dict[str, Any] = {"ordinal": ordinal, "case": case, "status": "error", "answer": "", "chunks": []}
            try:
                chunks, answer, retrieval_ms, generation_ms, native, recovery = adapter.run_case(case, ordinal)
                row.update({"status": "success", "answer": answer, "chunks": chunks,
                            "retrieval_latency_ms": round(retrieval_ms, 3), "generation_latency_ms": round(generation_ms, 3),
                            "usage": native.get("usage") if isinstance(native, dict) else None, "recovery": recovery})
                if not answer.strip():
                    row["status"] = "error"
                    row["error"] = "EMPTY_NATIVE_ANSWER"
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            rows.append(row)
            if ordinal == 1 or ordinal % 5 == 0 or ordinal == len(fixture.cases):
                progress.emit("evaluation", "WikiEval question progress", completed=ordinal, total=len(fixture.cases), successes=sum(r["status"] == "success" for r in rows))
            if args.query_interval:
                time.sleep(args.query_interval)
    results.with_suffix(".jsonl.sha256").write_text(f"{sha256_bytes(results.read_bytes())}  {results.name}\n")
    metrics = score_results(rows)
    metrics.update({"protocol": "wikieval-local-competitor-v1", "system_id": args.system,
                    "embedding_provider": "Huawei MaaS", "embedding_model": args.embedding_model,
                    "chat_provider": "Baidu Qianfan", "chat_model": args.chat_model})
    json_dump(output / "metrics.json", metrics)
    json_dump(output / "run-manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "system_id": args.system, "deployment_mode": "self_hosted",
        "model_egress": "external", "embedding": {"provider": "Huawei MaaS", "model": args.embedding_model},
        "chat": {"provider": "Baidu Qianfan", "model": args.chat_model}, "top_k": args.top_k,
        "fixture": fixture.manifest, "resources": resources,
    })
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=("fastgpt_local", "maxkb_local"), required=True)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--embedding-model", default="bge-m3")
    parser.add_argument("--chat-model", default="deepseek-v4-flash")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--index-wait", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=3)
    parser.add_argument("--upload-timeout", type=int, default=600)
    parser.add_argument("--query-timeout", type=int, default=120)
    parser.add_argument("--native-timeout", type=int, default=180)
    parser.add_argument("--query-interval", type=float, default=0.1)
    parser.add_argument("--questions-limit", type=int, default=0, help="0 runs all frozen questions")
    parser.add_argument("--reuse-resources", type=Path, help="reuse a compatible MaxKB knowledge/documents mapping")
    return parser


def main() -> int:
    output = run(build_parser().parse_args())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
