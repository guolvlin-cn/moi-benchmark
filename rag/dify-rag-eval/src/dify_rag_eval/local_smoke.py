"""Small, dependency-free smoke adapters for self-hosted RAG products.

The adapters deliberately stop at the vendor HTTP contracts.  They do not
try to infer citations from answer text and they never persist credentials or
uploaded file contents in the artifact directory.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


USER_AGENT = "MOI-RAG-Local-Smoke/0.1"
_SECRET_KEY = re.compile(
    r"(?:authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|password|secret|cookie|set-cookie|token)$",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s]+")
_KEY_VALUE = re.compile(r"(?i)\b(?:sk|key|token)[-_][A-Za-z0-9._-]{8,}")


class SmokeError(RuntimeError):
    """An expected API or transport failure that belongs in the smoke record."""


class UnsupportedSmoke(SmokeError):
    """The current product/version does not expose the requested contract."""


class HttpSmokeError(SmokeError):
    def __init__(self, status: int, body: Any, url: str):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status} from {url}")


def _redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer <redacted>", value)
    return _KEY_VALUE.sub("<redacted>", value)


def redact(value: Any, key: str | None = None) -> Any:
    """Recursively redact credential-shaped fields and bearer strings."""

    if key and _SECRET_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


@dataclass
class ArtifactStore:
    root: Path
    artifacts: list[str] = field(default_factory=list)
    _counter: int = 0

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def write_json(self, stem: str, payload: Any) -> str:
        self._counter += 1
        safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip(".") or "artifact"
        relative = "smoke-result.json" if safe_stem == "smoke-result" else f"{self._counter:03d}-{safe_stem}.json"
        path = self.root / relative
        encoded = json.dumps(redact(_jsonable(payload)), ensure_ascii=False, indent=2, sort_keys=True)
        data = (encoded + "\n").encode("utf-8")
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        digest_path = path.with_suffix(path.suffix + ".sha256")
        digest_path.write_text(digest + "\n", encoding="utf-8")
        self.artifacts.extend([relative, digest_path.name])
        return relative

    def record(
        self,
        operation: str,
        request: Any,
        response: Any = None,
        error: Any = None,
    ) -> str:
        payload = {
            "operation": operation,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request": request,
            "response": response,
            "error": error,
        }
        return self.write_json(operation, payload)


def _body_preview(data: bytes, content_type: str = "") -> Any:
    if not data:
        return None
    if "json" in content_type.lower() or data[:1] in (b"{", b"["):
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    text = data[:200_000].decode("utf-8", errors="replace")
    if len(data) > 200_000:
        text += "\n<response truncated>"
    return text


class HttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        store: ArtifactStore,
        timeout: float = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.store = store
        self.timeout = timeout

    def url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            separator = "&" if "?" in url else "?"
            url += separator + urlencode({k: str(v) for k, v in params.items() if v is not None})
        return url

    def root_client(self) -> "HttpClient":
        parts = urlsplit(self.base_url)
        path = parts.path
        if path.endswith("/v1"):
            path = path[:-3]
        root = urlunsplit((parts.scheme, parts.netloc, path.rstrip("/"), "", ""))
        return HttpClient(root, self.api_key, self.store, self.timeout)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        form: dict[str, Any] | None = None,
        api_key: str | None = None,
        operation: str | None = None,
    ) -> Any:
        url = self.url(path, params)
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        credential = self.api_key if api_key is None else api_key
        if credential:
            headers["Authorization"] = f"Bearer {credential}"

        request_meta: dict[str, Any] = {
            "method": method.upper(),
            "url": _redact_text(url),
            "headers": headers,
        }
        body: bytes | None = None
        if files is not None:
            boundary = f"----moi-smoke-{uuid.uuid4().hex}"
            chunks: list[bytes] = []
            for name, value in (form or {}).items():
                chunks.extend(
                    [
                        f"--{boundary}\r\n".encode(),
                        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                        str(value).encode(),
                        b"\r\n",
                    ]
                )
            file_meta = {}
            for name, (filename, content, content_type) in files.items():
                file_meta[name] = {
                    "filename": filename,
                    "content_type": content_type,
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
                chunks.extend(
                    [
                        f"--{boundary}\r\n".encode(),
                        (
                            f'Content-Disposition: form-data; name="{name}"; '
                            f'filename="{filename}"\r\n'
                        ).encode(),
                        f"Content-Type: {content_type}\r\n\r\n".encode(),
                        content,
                        b"\r\n",
                    ]
                )
            chunks.append(f"--{boundary}--\r\n".encode())
            body = b"".join(chunks)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            request_meta["multipart"] = {"fields": form or {}, "files": file_meta}
        elif json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            request_meta["json"] = json_body
        elif form is not None:
            body = urlencode({k: str(v) for k, v in form.items()}).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            request_meta["form"] = form

        request = Request(url, data=body, headers=headers, method=method.upper())
        op = operation or f"{method.lower()}-{path.strip('/').replace('/', '-') or 'root'}"
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                response_meta = {
                    "status": response.status,
                    "headers": dict(response.headers.items()),
                    "body": _body_preview(raw, response.headers.get("Content-Type", "")),
                }
                self.store.record(op, request_meta, response_meta)
                return _body_preview(raw, response.headers.get("Content-Type", ""))
        except HTTPError as exc:
            raw = exc.read()
            body_value = _body_preview(raw, exc.headers.get("Content-Type", ""))
            error = {"type": "http", "status": exc.code, "body": body_value}
            self.store.record(op, request_meta, {"status": exc.code}, error)
            raise HttpSmokeError(exc.code, body_value, url) from exc
        except (URLError, TimeoutError, OSError) as exc:
            error = {"type": "transport", "message": str(exc)}
            self.store.record(op, request_meta, None, error)
            raise SmokeError(str(exc)) from exc


def _first_value(payload: Any, names: tuple[str, ...]) -> Any:
    if isinstance(payload, dict):
        for name in names:
            if name in payload and payload[name] not in (None, ""):
                return payload[name]
        for value in payload.values():
            found = _first_value(value, names)
            if found not in (None, ""):
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _first_value(value, names)
            if found not in (None, ""):
                return found
    return None


def _list_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "list", "items", "documents", "chunks", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            nested = _list_items(value)
            if nested:
                return nested
    return []


def _answer(payload: Any) -> str:
    value = _first_value(payload, ("answer", "content", "text", "response"))
    return value if isinstance(value, str) else ""


@dataclass
class SmokeContext:
    system_id: str
    base_url: str
    output: Path
    api_key: str | None = None
    dataset_api_key: str | None = None
    app_api_key: str | None = None
    app_id: str | None = None
    source_dir: Path | None = None
    question: str = "Where must the RAG service under test run, and what external dependency is allowed?"
    retrieval_probe: str = "Colima machine"
    wait_seconds: int = 120
    platform: str = "linux/arm64"
    options: dict[str, Any] = field(default_factory=dict)


class BaseAdapter:
    def __init__(self, context: SmokeContext):
        self.context = context
        self.store = ArtifactStore(context.output)
        self.client = HttpClient(
            context.base_url,
            context.api_key,
            self.store,
            timeout=float(context.options.get("timeout", 60)),
        )
        self.result: dict[str, Any] = {
            "system_id": context.system_id,
            "deployment_mode": "self_hosted",
            "platform": context.platform,
            "version": None,
            "image_digest": None,
            "model_egress": "external",
            "service_status": "blocked",
            "ingest_status": "unsupported",
            "native_status": "unsupported",
            "retrieval_status": "unsupported",
            "blocked_reason": context.options.get("blocked_reason"),
            "artifacts": [],
            "errors": [],
            "details": {},
        }

    def _error(self, stage: str, exc: Exception, *, blocked: str | None = None) -> None:
        item: dict[str, Any] = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        if isinstance(exc, HttpSmokeError):
            item["status"] = exc.status
            item["body"] = redact(exc.body)
        self.result["errors"].append(item)
        if blocked and not self.result["blocked_reason"]:
            self.result["blocked_reason"] = blocked

    def _step(self, stage: str, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except UnsupportedSmoke as exc:
            self._error(stage, exc, blocked="UNSUPPORTED_API")
            return None
        except Exception as exc:  # smoke output must survive one failed stage
            self._error(stage, exc)
            return None

    def _finish(self) -> dict[str, Any]:
        self.result["artifacts"] = list(self.store.artifacts)
        self.store.write_json("smoke-result", self.result)
        self.result["artifacts"] = list(self.store.artifacts)
        return self.result

    def run(self) -> dict[str, Any]:
        raise NotImplementedError

    def _require_key(self, value: str | None, name: str) -> str:
        if not value:
            raise SmokeError(f"missing credential: {name}")
        return value


class DifyLocalAdapter(BaseAdapter):
    def __init__(self, context: SmokeContext):
        context.api_key = context.app_api_key or context.api_key
        super().__init__(context)
        self.dataset_client = HttpClient(
            context.base_url,
            context.dataset_api_key,
            self.store,
            timeout=float(context.options.get("timeout", 60)),
        )
        self.dataset_id: str | None = None

    def _health(self) -> Any:
        attempts = [
            (self.client.root_client(), "/console/api/setup"),
            (self.client.root_client(), "/console/api/init"),
            (self.client.root_client(), "/health"),
            (self.client, "/datasets"),
        ]
        for client, path in attempts:
            try:
                return client.request("GET", path, params={"page": 1, "limit": 1}, operation="health")
            except HttpSmokeError as exc:
                if exc.status not in (401, 403, 404):
                    raise
        raise SmokeError("Dify health/API probe failed")

    def run(self) -> dict[str, Any]:
        health = self._step("service", self._health)
        if health is None:
            self.result["blocked_reason"] = self.result["blocked_reason"] or "SERVICE_UNREACHABLE"
            return self._finish()
        self.result["service_status"] = "ready"
        version = self._step(
            "version",
            lambda: self.client.root_client().request(
                "GET",
                "/console/api/version",
                params={"current_version": self.context.options.get("current_version", "1.16.1")},
                operation="version",
            ),
        )
        self.result["version"] = _first_value(version, ("version", "current_version", "release")) if version else None
        self._step(
            "embedding-provider",
            lambda: self.dataset_client.request(
                "GET",
                "/workspaces/current/models/model-types/text-embedding",
                operation="embedding-provider",
            ),
        )
        dataset_key = self._step("dataset-credential", lambda: self._require_key(self.context.dataset_api_key, "DIFY_LOCAL_DATASET_API_KEY"))
        if dataset_key:
            self.dataset_id = self.context.options.get("dataset_id")
            if self.dataset_id:
                self.store.record(
                    "reuse-dataset",
                    {"dataset_id": self.dataset_id},
                    {"reused": True},
                )
            else:
                created = self._step("create-dataset", lambda: self.dataset_client.request(
                    "POST",
                    "/datasets",
                    json_body=self._dataset_payload(),
                    api_key=dataset_key,
                    operation="create-dataset",
                ))
                self.dataset_id = _first_value(created, ("id", "dataset_id")) if created else None
            if self.dataset_id and self.context.source_dir:
                uploaded = True
                for path in sorted(self.context.source_dir.iterdir()):
                    if not path.is_file() or path.name.startswith(".") or path.suffix.lower() in {".json", ".jsonl"}:
                        continue
                    response = self._step(
                        f"upload-{path.stem}",
                        lambda path=path: self.dataset_client.request(
                            "POST",
                            f"/datasets/{self.dataset_id}/document/create-by-file",
                            files={"file": (path.name, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "text/plain")},
                            form={"data": json.dumps(self._upload_payload())},
                            api_key=dataset_key,
                            operation=f"upload-{path.stem}",
                        ),
                    )
                    uploaded = uploaded and response is not None
                if uploaded:
                    ready = self._wait_dify_documents(dataset_key)
                    self.result["ingest_status"] = "ready" if ready else "error"
            else:
                self.result["ingest_status"] = "error"

            retrieval = self._step(
                "direct-retrieval",
                lambda: self.dataset_client.request(
                    "POST",
                    f"/datasets/{self.dataset_id}/retrieve" if self.dataset_id else "/datasets/unknown/retrieve",
                    json_body={
                        "query": self.context.retrieval_probe,
                        "retrieval_model": {
                            "search_method": "semantic_search",
                            "reranking_enable": False,
                            "top_k": 5,
                            "score_threshold_enabled": False,
                        },
                    },
                    api_key=dataset_key,
                    operation="direct-retrieval",
                ),
            ) if self.dataset_id else None
            if retrieval is not None:
                self.result["retrieval_status"] = "success" if _list_items(retrieval) else "error"
                self.result["details"]["retrieval_context_count"] = len(_list_items(retrieval))
        elif not self.result["blocked_reason"]:
            self.result["blocked_reason"] = "MISSING_DATASET_KEY"

        app_key = self._step("app-credential", lambda: self._require_key(self.context.app_api_key or self.context.api_key, "DIFY_LOCAL_API_KEY"))
        if app_key:
            native = self._step(
                "native-qa",
                lambda: self.client.request(
                    "POST",
                    "/chat-messages",
                    json_body={
                        "inputs": {},
                        "query": self.context.question,
                        "response_mode": "blocking",
                        "conversation_id": "",
                        "user": f"moi-local-smoke-{uuid.uuid4().hex[:12]}",
                    },
                    api_key=app_key,
                    operation="native-qa",
                ),
            )
            if native is not None:
                self.result["native_status"] = "success" if _answer(native).strip() else "error"
                self.result["details"]["native_answer"] = _answer(native)
        elif not self.result["blocked_reason"]:
            self.result["blocked_reason"] = "MISSING_APP_KEY"
        return self._finish()

    def _dataset_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": f"moi-local-smoke-{int(time.time())}",
            "indexing_technique": "high_quality",
            "permission": "only_me",
        }
        embedding_model = self.context.options.get("embedding_model")
        embedding_provider = self.context.options.get("embedding_provider")
        if embedding_model:
            payload["embedding_model"] = embedding_model
        if embedding_provider:
            payload["embedding_model_provider"] = embedding_provider
        return payload

    def _upload_payload(self) -> dict[str, Any]:
        return {
            "indexing_technique": "high_quality",
            "process_rule": {
                "mode": "custom",
                "rules": {
                    "pre_processing_rules": [
                        {"id": "remove_extra_spaces", "enabled": True},
                        {"id": "remove_urls_emails", "enabled": False},
                    ],
                    "segmentation": {"separator": "\n", "max_tokens": 512, "chunk_overlap": 64},
                },
            },
        }

    def _wait_dify_documents(self, dataset_key: str) -> bool:
        deadline = time.monotonic() + self.context.wait_seconds
        while time.monotonic() < deadline:
            response = self._step(
                "document-status",
                lambda: self.dataset_client.request(
                    "GET",
                    f"/datasets/{self.dataset_id}/documents",
                    params={"page": 1, "limit": 100},
                    api_key=dataset_key,
                    operation="document-status",
                ),
            )
            statuses = [str(_first_value(item, ("indexing_status", "status"))).lower() for item in _list_items(response)]
            if statuses and all(status in {"completed", "indexed", "ready", "available"} for status in statuses):
                return True
            if any(status in {"error", "failed"} for status in statuses):
                return False
            time.sleep(2)
        return False


class FastGPTLocalAdapter(BaseAdapter):
    def __init__(self, context: SmokeContext):
        super().__init__(context)
        self.dataset_id: str | None = None

    def _health(self) -> Any:
        last_error: HttpSmokeError | None = None
        for path in ("/api/system/getInitData", "/api/core/app/list"):
            try:
                return self.client.request("GET", path, operation="health")
            except HttpSmokeError as exc:
                last_error = exc
                if exc.status not in (401, 403, 404):
                    if exc.status != 400:
                        raise
        if last_error is not None:
            # A reachable FastGPT instance can return 400 here because these
            # contracts require a JSON body or a local auth context.  Keep the
            # raw response as evidence and reserve service failure for a
            # transport error.
            return {"health_probe": "http-reachable", "last_http_status": last_error.status}
        raise SmokeError("FastGPT health/API probe failed")

    def run(self) -> dict[str, Any]:
        health = self._step("service", self._health)
        if health is None:
            self.result["blocked_reason"] = self.result["blocked_reason"] or "SERVICE_UNREACHABLE"
            return self._finish()
        self.result["service_status"] = "ready"
        self.result["version"] = _first_value(health, ("version", "currentVersion", "release"))
        key = self._step("api-credential", lambda: self._require_key(self.context.api_key, "FASTGPT_API_KEY"))
        if key:
            created = self._step(
                "create-dataset",
                lambda: self.client.request(
                    "POST",
                    "/api/core/dataset/create",
                    json_body={
                        "parentId": None,
                        "name": f"moi-local-smoke-{int(time.time())}",
                        "intro": "MOI local RAG smoke fixture",
                        "vectorModel": self.context.options.get("vector_model"),
                        "agentModel": self.context.options.get("agent_model"),
                    },
                    api_key=key,
                    operation="create-dataset",
                ),
            )
            self.dataset_id = _first_value(created, ("id", "datasetId", "dataset_id")) if created else None
            if self.dataset_id and self.context.source_dir:
                uploaded = True
                for path in sorted(self.context.source_dir.iterdir()):
                    if not path.is_file() or path.name.startswith(".") or path.suffix.lower() in {".json", ".jsonl"}:
                        continue
                    response = self._step(
                        f"upload-{path.stem}",
                        lambda path=path: self.client.request(
                            "POST",
                            "/api/core/dataset/collection/create/localFile",
                            files={"file": (path.name, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "text/plain")},
                            form={"datasetId": self.dataset_id, "parentId": ""},
                            api_key=key,
                            operation=f"upload-{path.stem}",
                        ),
                    )
                    uploaded = uploaded and response is not None
                ready = self._wait_fastgpt_collection(key) if uploaded else False
                self.result["ingest_status"] = "ready" if ready else "error"
            else:
                self.result["ingest_status"] = "error"
            retrieval = self._step(
                "direct-retrieval",
                lambda: self.client.request(
                    "POST",
                    "/api/core/dataset/searchTest",
                    json_body={"datasetId": self.dataset_id, "search": self.context.retrieval_probe},
                    api_key=key,
                    operation="direct-retrieval",
                ) if self.dataset_id else None,
            ) if self.dataset_id else None
            if retrieval is not None:
                self.result["retrieval_status"] = "success" if _list_items(retrieval) else "error"
                self.result["details"]["retrieval_context_count"] = len(_list_items(retrieval))

        app_id = self.context.app_id or self.context.options.get("app_id")
        if key and app_id:
            native = self._step(
                "native-qa",
                lambda: self.client.request(
                    "POST",
                    "/api/v1/chat/completions",
                    json_body={
                        "appId": app_id,
                        "chatId": str(uuid.uuid4()),
                        "stream": False,
                        "detail": True,
                        "messages": [{"role": "user", "content": self.context.question}],
                    },
                    api_key=key,
                    operation="native-qa",
                ),
            )
            if native is not None:
                self.result["native_status"] = "success" if _answer(native).strip() else "error"
                self.result["details"]["native_answer"] = _answer(native)
        elif not app_id:
            self.result["blocked_reason"] = self.result["blocked_reason"] or "MISSING_APP_ID"
        if not key and not self.result["blocked_reason"]:
            self.result["blocked_reason"] = "MISSING_API_KEY"
        return self._finish()

    def _wait_fastgpt_collection(self, key: str) -> bool:
        deadline = time.monotonic() + self.context.wait_seconds
        while time.monotonic() < deadline:
            response = self._step(
                "collection-status",
                lambda: self.client.request(
                    "POST",
                    "/api/core/dataset/collection/list",
                    json_body={"datasetId": self.dataset_id},
                    api_key=key,
                    operation="collection-status",
                ),
            )
            if response is None:
                return False
            items = _list_items(response)
            statuses = [str(_first_value(item, ("status", "trainingType", "state"))).lower() for item in items]
            self.result["details"]["collection_statuses"] = statuses
            if statuses and all(status in {"success", "completed", "finish", "finished", "ready", "2"} for status in statuses):
                return True
            if any(status in {"error", "failed", "fail", "-1"} for status in statuses):
                return False
            time.sleep(2)
        return False


class RAGFlowLocalAdapter(BaseAdapter):
    def __init__(self, context: SmokeContext):
        super().__init__(context)
        self.dataset_id: str | None = None
        self.chat_id: str | None = context.options.get("chat_id")

    def _health(self) -> Any:
        for path in ("/api/v1/user/info", "/api/v1/system/status"):
            try:
                return self.client.request("GET", path, operation="health")
            except HttpSmokeError as exc:
                if exc.status not in (401, 403, 404):
                    raise
        raise SmokeError("RAGFlow health/API probe failed")

    def run(self) -> dict[str, Any]:
        health = self._step("service", self._health)
        if health is None:
            self.result["blocked_reason"] = self.result["blocked_reason"] or "SERVICE_UNREACHABLE"
            return self._finish()
        self.result["service_status"] = "ready"
        self.result["version"] = _first_value(health, ("version", "current_version", "release"))
        key = self._step("api-credential", lambda: self._require_key(self.context.api_key, "RAGFLOW_API_KEY"))
        if key:
            created = self._step(
                "create-dataset",
                lambda: self.client.request(
                    "POST",
                    "/api/v1/datasets",
                    json_body={
                        "name": f"moi-local-smoke-{int(time.time())}",
                        "chunk_method": "naive",
                        "parser_config": {"chunk_token_num": 512, "delimiter": "\\n"},
                    },
                    api_key=key,
                    operation="create-dataset",
                ),
            )
            self.dataset_id = _first_value(created, ("id", "dataset_id")) if created else None
            if self.dataset_id and self.context.source_dir:
                uploaded_ids: list[str] = []
                for path in sorted(self.context.source_dir.iterdir()):
                    if not path.is_file() or path.name.startswith(".") or path.suffix.lower() in {".json", ".jsonl"}:
                        continue
                    uploaded = self._step(
                        f"upload-{path.stem}",
                        lambda path=path: self.client.request(
                            "POST",
                            f"/api/v1/datasets/{self.dataset_id}/documents",
                            files={"file": (path.name, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "text/plain")},
                            api_key=key,
                            operation=f"upload-{path.stem}",
                        ),
                    )
                    document_id = _first_value(uploaded, ("id", "document_id")) if uploaded else None
                    if document_id:
                        uploaded_ids.append(str(document_id))
                if uploaded_ids:
                    self._step(
                        "parse",
                        lambda: self.client.request(
                            "POST",
                            f"/api/v1/datasets/{self.dataset_id}/chunks",
                            json_body={"document_ids": uploaded_ids, "run": 1},
                            api_key=key,
                            operation="parse",
                        ),
                    )
                ready = self._wait_ragflow_documents(key)
                self.result["ingest_status"] = "ready" if ready else "error"
            else:
                self.result["ingest_status"] = "error"
            retrieval = self._step(
                "direct-retrieval",
                lambda: self.client.request(
                    "POST",
                    "/api/v1/retrieval",
                    json_body={
                        "question": self.context.retrieval_probe,
                        "dataset_ids": [self.dataset_id],
                        "page": 1,
                        "page_size": 5,
                        "top_k": 5,
                    },
                    api_key=key,
                    operation="direct-retrieval",
                ) if self.dataset_id else None,
            ) if self.dataset_id else None
            if retrieval is not None:
                self.result["retrieval_status"] = "success" if _list_items(retrieval) else "error"
                self.result["details"]["retrieval_context_count"] = len(_list_items(retrieval))

        if key and self.chat_id:
            native = self._step(
                "native-qa",
                lambda: self.client.request(
                    "POST",
                    f"/api/v1/openai/{self.chat_id}/chat/completions",
                    json_body={
                        "model": "model",
                        "stream": False,
                        "messages": [{"role": "user", "content": self.context.question}],
                        "extra_body": {"reference": True, "reference_metadata": True},
                    },
                    api_key=key,
                    operation="native-qa",
                ),
            )
            if native is not None:
                self.result["native_status"] = "success" if _answer(native).strip() else "error"
                self.result["details"]["native_answer"] = _answer(native)
        elif not self.chat_id:
            self.result["blocked_reason"] = self.result["blocked_reason"] or "MISSING_CHAT_ID"
        if not key and not self.result["blocked_reason"]:
            self.result["blocked_reason"] = "MISSING_API_KEY"
        return self._finish()

    def _wait_ragflow_documents(self, key: str) -> bool:
        deadline = time.monotonic() + self.context.wait_seconds
        while time.monotonic() < deadline:
            response = self._step(
                "document-status",
                lambda: self.client.request(
                    "GET",
                    f"/api/v1/datasets/{self.dataset_id}/documents",
                    api_key=key,
                    operation="document-status",
                ),
            )
            items = _list_items(response)
            statuses = [str(_first_value(item, ("run", "status"))).lower() for item in items]
            if statuses and all(status in {"1", "success", "done", "ready", "available"} for status in statuses):
                return True
            if any(status in {"-1", "fail", "failed", "error"} for status in statuses):
                return False
            time.sleep(2)
        return False


class MaxKBLocalAdapter(BaseAdapter):
    """MaxKB uses an instance-generated API surface; discover it before calls."""

    def __init__(self, context: SmokeContext):
        super().__init__(context)
        self.discovery: Any = None

    def _health(self) -> Any:
        for path in ("/", "/api/health", "/api/system/health"):
            try:
                return self.client.request("GET", path, operation="health")
            except HttpSmokeError as exc:
                if exc.status not in (401, 403, 404):
                    raise
        raise SmokeError("MaxKB health/API probe failed")

    def run(self) -> dict[str, Any]:
        health = self._step("service", self._health)
        if health is None:
            self.result["blocked_reason"] = self.result["blocked_reason"] or "SERVICE_UNREACHABLE"
            return self._finish()
        self.result["service_status"] = "ready"
        self.result["version"] = _first_value(health, ("version", "current_version", "release"))
        self.discovery = self._discover()
        self.result["details"]["api_discovery"] = self.discovery
        native_base = self.context.options.get("native_base_url") or os.getenv("MAXKB_OPENAI_BASE_URL")
        native_path = self.context.options.get("native_path") or os.getenv("MAXKB_OPENAI_PATH")
        if native_base and self.context.api_key:
            native_client = HttpClient(native_base, self.context.api_key, self.store, timeout=self.client.timeout)
            native = self._step(
                "native-qa",
                lambda: native_client.request(
                    "POST",
                    native_path or "/chat/completions",
                    json_body={
                        "model": self.context.options.get("model", "default"),
                        "stream": False,
                        "messages": [{"role": "user", "content": self.context.question}],
                    },
                    operation="native-qa",
                ),
            )
            if native is not None:
                self.result["native_status"] = "success" if _answer(native).strip() else "error"
                self.result["details"]["native_answer"] = _answer(native)
        else:
            self.result["blocked_reason"] = self.result["blocked_reason"] or "MISSING_MAXKB_OPENAI_ENDPOINT"
        self.result["ingest_status"] = "unsupported"
        self.result["retrieval_status"] = "unsupported"
        self.result["details"]["direct_retrieval_note"] = (
            "No stable public direct-retrieval contract was assumed; use the instance OpenAPI discovery result."
        )
        return self._finish()

    def _discover(self) -> dict[str, Any]:
        found: list[dict[str, Any]] = []
        for path in ("/openapi.json", "/api/openapi.json", "/swagger.json", "/docs", "/api/docs"):
            try:
                response = self.client.request("GET", path, operation=f"discover-{path.strip('/').replace('/', '-')}")
                found.append({"path": path, "ok": True, "keys": list(response)[:20] if isinstance(response, dict) else None})
            except Exception as exc:
                found.append({"path": path, "ok": False, "error": type(exc).__name__})
        return {"paths": found}


def build_adapter(context: SmokeContext) -> BaseAdapter:
    adapters = {
        "dify_local": DifyLocalAdapter,
        "fastgpt_local": FastGPTLocalAdapter,
        "ragflow_local": RAGFlowLocalAdapter,
        "maxkb_local": MaxKBLocalAdapter,
    }
    try:
        return adapters[context.system_id](context)
    except KeyError as exc:
        raise ValueError(f"unsupported local system: {context.system_id}") from exc


def run_local_smoke(context: SmokeContext) -> dict[str, Any]:
    return build_adapter(context).run()
