from __future__ import annotations

import json
import hashlib
import mimetypes
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EmbeddingModel:
    provider: str
    model: str


class KnowledgeClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 120,
        max_retries: int = 4,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def available_embedding_models(self) -> list[EmbeddingModel]:
        raw = self._request_json(
            "GET", "/workspaces/current/models/model-types/text-embedding"
        )
        found: list[EmbeddingModel] = []
        for provider in _walk_dicts(raw):
            provider_name = provider.get("provider")
            models = provider.get("models")
            if not provider_name or not isinstance(models, list):
                continue
            for model in models:
                if (
                    isinstance(model, dict)
                    and model.get("model")
                    and model.get("status") == "active"
                ):
                    found.append(
                        EmbeddingModel(
                            provider=str(provider_name),
                            model=str(model["model"]),
                        )
                    )
        unique = {(item.provider, item.model): item for item in found}
        return list(unique.values())

    def list_knowledge_bases(self, keyword: str | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"page": 1, "limit": 100}
        if keyword:
            query["keyword"] = keyword
        raw = self._request_json(
            "GET", "/datasets?" + urllib.parse.urlencode(query)
        )
        return list(raw.get("data") or [])

    def create_knowledge_base(
        self,
        name: str,
        embedding: EmbeddingModel,
        *,
        top_k: int,
        search_method: str,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/datasets",
            {
                "name": name,
                "description": "Created by dify-rag-eval ingest pipeline",
                "indexing_technique": "high_quality",
                "permission": "only_me",
                "embedding_model": embedding.model,
                "embedding_model_provider": embedding.provider,
                "retrieval_model": {
                    "search_method": search_method,
                    "reranking_enable": False,
                    "top_k": top_k,
                    "score_threshold_enabled": False,
                },
            },
        )

    def list_documents(self, dataset_id: str) -> list[dict[str, Any]]:
        page = 1
        documents: list[dict[str, Any]] = []
        while True:
            raw = self._request_json(
                "GET",
                f"/datasets/{dataset_id}/documents?"
                + urllib.parse.urlencode({"page": page, "limit": 100}),
            )
            documents.extend(raw.get("data") or [])
            if not raw.get("has_more"):
                return documents
            page += 1

    def upload_document(self, dataset_id: str, path: Path) -> dict[str, Any]:
        data = {
            "indexing_technique": "high_quality",
            "doc_form": "text_model",
            "doc_language": "English",
            "process_rule": {"mode": "automatic"},
        }
        body, content_type = _multipart_body(path, data)
        return self._request_json(
            "POST",
            f"/datasets/{dataset_id}/document/create-by-file",
            raw_body=body,
            content_type=content_type,
        )

    def retrieve(
        self,
        dataset_id: str,
        query: str,
        *,
        top_k: int,
        search_method: str,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/datasets/{dataset_id}/retrieve",
            {
                "query": query,
                "retrieval_model": {
                    "search_method": search_method,
                    "reranking_enable": False,
                    "top_k": top_k,
                    "score_threshold_enabled": False,
                },
            },
        )

    def _request_json(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        *,
        raw_body: bytes | None = None,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        if raw_body is not None and payload is not None:
            raise ValueError("provide payload or raw_body, not both")
        body = (
            raw_body
            if raw_body is not None
            else (
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None
                else None
            )
        )
        request = urllib.request.Request(
            self.base_url + endpoint,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": content_type,
                "Accept": "application/json",
                "User-Agent": "Dify-RAG-Eval/0.1",
            },
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    value = json.loads(response.read().decode("utf-8"))
                    if not isinstance(value, dict):
                        raise RuntimeError("Dify returned a non-object JSON response")
                    return value
            except urllib.error.HTTPError as exc:
                message = exc.read().decode("utf-8", errors="replace")
                rate_limited = exc.code in {403, 429} and "rate limit" in message.lower()
                retryable = rate_limited or 500 <= exc.code < 600
                if not retryable or attempt >= self.max_retries:
                    raise RuntimeError(f"Dify HTTP {exc.code}: {message}") from exc
                delay = 30.0 if rate_limited else min(8.0, 0.5 * (2**attempt))
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Dify request failed: {exc}") from exc
                delay = min(8.0, 0.5 * (2**attempt))
            time.sleep(delay + random.uniform(0, 0.25))
        raise AssertionError("unreachable")


def choose_embedding_model(
    models: list[EmbeddingModel],
    *,
    requested_model: str | None = None,
    requested_provider: str | None = None,
) -> EmbeddingModel:
    candidates = [
        item
        for item in models
        if (not requested_model or item.model == requested_model)
        and (not requested_provider or item.provider == requested_provider)
    ]
    if not candidates:
        raise ValueError("no active embedding model matches the requested selection")
    preferences = (
        "BAAI/bge-large-en-v1.5",
        "Qwen/Qwen3-Embedding-0.6B",
        "text-embedding-3-small",
    )
    for preferred in preferences:
        for item in candidates:
            if item.model == preferred:
                return item
    return candidates[0]


def ingest_directory(
    client: KnowledgeClient,
    *,
    source: Path,
    knowledge_name: str,
    output: Path,
    embedding_model: str | None,
    embedding_provider: str | None,
    top_k: int,
    search_method: str,
    upload_interval_seconds: float,
    wait: bool,
    probe: str | None,
    local_chunks: bool = False,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
) -> dict[str, Any]:
    source_files = sorted(
        path
        for path in source.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )
    if not source_files:
        raise ValueError(f"no uploadable files found under {source}")
    validate_chunk_options(chunk_size, chunk_overlap)
    output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    if local_chunks:
        files, manifest = _materialize_chunks(
            source_files, output / "chunks", chunk_size, chunk_overlap
        )
        (output / "chunk-manifest.json").write_text(
            json.dumps(
                {"chunk_size": chunk_size, "chunk_overlap": chunk_overlap, "chunks": manifest},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        files = source_files
    state_path = output / "ingest-state.json"
    state = _load_state(state_path)
    resolved_source = str(source.resolve())
    if state.get("knowledge_name") not in {None, knowledge_name}:
        raise ValueError(
            f"state belongs to knowledge base {state['knowledge_name']!r}, "
            f"not {knowledge_name!r}"
        )
    if state.get("source") not in {None, resolved_source}:
        raise ValueError(
            f"state belongs to source {state['source']!r}, not {resolved_source!r}"
        )

    dataset_id = state.get("dataset_id")
    if not dataset_id:
        matches = [
            item
            for item in client.list_knowledge_bases(knowledge_name)
            if item.get("name") == knowledge_name
        ]
        if matches:
            dataset = matches[0]
            print(f"reusing knowledge base {knowledge_name!r}", flush=True)
        else:
            embedding = choose_embedding_model(
                client.available_embedding_models(),
                requested_model=embedding_model,
                requested_provider=embedding_provider,
            )
            print(
                f"creating knowledge base {knowledge_name!r} with "
                f"{embedding.provider}/{embedding.model}",
                flush=True,
            )
            dataset = client.create_knowledge_base(
                knowledge_name,
                embedding,
                top_k=top_k,
                search_method=search_method,
            )
            state["embedding"] = {
                "provider": embedding.provider,
                "model": embedding.model,
            }
        dataset_id = str(dataset["id"])
        state.update(
            {
                "dataset_id": dataset_id,
                "knowledge_name": knowledge_name,
                "source": resolved_source,
                "files": state.get("files") or {},
            }
        )
        _save_state(state_path, state)

    existing = {
        str(item.get("name")): item for item in client.list_documents(dataset_id)
    }
    uploaded = 0
    for index, path in enumerate(files, 1):
        if path.name in existing:
            state.setdefault("files", {}).setdefault(
                path.name,
                {
                    "document_id": existing[path.name].get("id"),
                    "status": existing[path.name].get("indexing_status"),
                    "action": "reused",
                },
            )
            print(
                f"[{index}/{len(files)}] {path.name}: already present",
                flush=True,
            )
            continue
        print(f"[{index}/{len(files)}] {path.name}: uploading", flush=True)
        response = client.upload_document(dataset_id, path)
        document = response.get("document") or {}
        state.setdefault("files", {})[path.name] = {
            "document_id": document.get("id"),
            "batch": response.get("batch"),
            "status": document.get("indexing_status"),
            "action": "uploaded",
        }
        _save_state(state_path, state)
        uploaded += 1
        if upload_interval_seconds > 0 and index < len(files):
            time.sleep(upload_interval_seconds)

    if wait:
        _wait_for_documents(client, dataset_id, state, state_path)

    retrieval = None
    if probe:
        retrieval = client.retrieve(
            dataset_id, probe, top_k=top_k, search_method=search_method
        )
        (output / "retrieval-probe.json").write_text(
            json.dumps(retrieval, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"retrieval probe returned {len(retrieval.get('records') or [])} records",
            flush=True,
        )

    state["summary"] = {
        "source_files": len(source_files),
        "documents": len(files),
        "local_chunks": local_chunks,
        "uploaded_this_run": uploaded,
        "tracked_files": len(state.get("files") or {}),
        "retrieval_records": (
            len(retrieval.get("records") or []) if retrieval is not None else None
        ),
    }
    _save_state(state_path, state)
    return state


def validate_chunk_options(chunk_size: int, chunk_overlap: int) -> None:
    """Validate deterministic local chunking parameters."""
    if chunk_size <= 0:
        raise ValueError("chunk size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk overlap must be >= 0 and < chunk size")


def chunk_text(text: str, chunk_size: int = 2000, chunk_overlap: int = 200) -> list[tuple[int, int, str]]:
    """Return (start, end, text) character chunks with deterministic overlap."""
    validate_chunk_options(chunk_size, chunk_overlap)
    if not text:
        return [(0, 0, "")]
    step = chunk_size - chunk_overlap
    return [(start, min(start + chunk_size, len(text)), text[start:min(start + chunk_size, len(text))])
            for start in range(0, len(text), step)]


def _materialize_chunks(
    source_files: list[Path], output_dir: Path, chunk_size: int, chunk_overlap: int
) -> tuple[list[Path], list[dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    manifest: list[dict[str, Any]] = []
    for source_path in source_files:
        text = source_path.read_text(encoding="utf-8")
        for index, (start, end, content) in enumerate(
            chunk_text(text, chunk_size, chunk_overlap)
        ):
            digest = hashlib.sha256(
                (source_path.name + "\0" + content + "\0" + str(index)).encode("utf-8")
            ).hexdigest()
            suffix = source_path.suffix if source_path.suffix.lower() in {".md", ".txt"} else ".txt"
            filename = f"{source_path.stem}--chunk-{index:05d}-{digest[:12]}{suffix}"
            path = output_dir / filename
            path.write_text(content, encoding="utf-8")
            files.append(path)
            manifest.append(
                {
                    "id": digest,
                    "path": str(path),
                    "source_file": source_path.name,
                    "chunk_index": index,
                    "start_offset": start,
                    "end_offset": end,
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                }
            )
    return files, manifest


def _wait_for_documents(
    client: KnowledgeClient,
    dataset_id: str,
    state: dict[str, Any],
    state_path: Path,
) -> None:
    while True:
        documents = client.list_documents(dataset_id)
        by_name = {str(item.get("name")): item for item in documents}
        pending = 0
        errors = 0
        for name, item in state.get("files", {}).items():
            document = by_name.get(name)
            if not document:
                pending += 1
                continue
            status = str(document.get("indexing_status") or "unknown")
            item["status"] = status
            item["error"] = document.get("error")
            if status == "error":
                errors += 1
            elif status != "completed":
                pending += 1
        _save_state(state_path, state)
        print(
            f"indexing status: completed={len(state.get('files', {})) - pending - errors} "
            f"pending={pending} errors={errors}",
            flush=True,
        )
        if errors:
            raise RuntimeError(f"{errors} document(s) failed indexing")
        if pending == 0:
            return
        time.sleep(10)


def _multipart_body(path: Path, data: dict[str, Any]) -> tuple[bytes, str]:
    boundary = f"dify-rag-eval-{uuid.uuid4().hex}"
    file_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    chunks = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {file_type}\r\n\r\n"
        ).encode(),
        path.read_bytes(),
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="data"\r\n',
        b"Content-Type: application/json\r\n\r\n",
        json.dumps(data, ensure_ascii=False).encode(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
