#!/usr/bin/env python3
"""Run the MMDocIR page-condition evaluation against local RAG products.

This runner deliberately keeps the product boundary visible:

* documents are uploaded through the local product API;
* retrieval and native QA are called through the product API;
* raw HTTP request/response evidence is redacted and hashed;
* Qianfan fallback creates a new provider-specific dataset instead of mixing
  embeddings with the TaaS corpus.

The first implementation covers the page condition.  Layout-condition support
can be added later without changing the attempt ledger or the marker contract.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener, urlopen


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PREPARED = ROOT / "runs/stage1/mmdocir/20260806-161153-full-1658/artifacts/prepared"
RUNTIME_ROOT = ROOT / ".local-services/mmdocir-competitors"
ACTIVE_PROGRESS = RUNTIME_ROOT / "active-progress.jsonl"
ACTIVE_STATUS = RUNTIME_ROOT / "active-status.json"
USER_AGENT = "MOI-MMDocIR-Local-Competitor-Eval/0.1"

PAGE_MARKER = re.compile(r"MMDocIR_PAGE_MARKER\s+file_id=([^\s]+)\s+page_number=(\d+)")
SOURCE_PAGE_MARKER = re.compile(r"MMDocIR_SOURCE_PAGE\s+file_id=([^\s]+)\s+page_number=(\d+)")
PAGE_FILE_MARKER = re.compile(r"MMDocIR__([A-Za-z0-9_-]+)__page_(\d+)(?:\.md)?")
DOC_MARKER = re.compile(r"MMDocIR_DOCUMENT_MARKER\s+file_id=([^\s]+)")
SECRET_KEY = re.compile(
    r"(?:authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|password|secret|cookie|set-cookie|token)$",
    re.IGNORECASE,
)
BEARER = re.compile(r"(?i)\bBearer\s+[^\s]+")
KEY_VALUE = re.compile(r"(?i)\b(?:sk|key|token)[-_][A-Za-z0-9._-]{8,}")
PROVIDER_FAILURE_MARKERS = (
    "insufficient balance",
    "insufficient quota",
    "quota exceeded",
    "rate limit",
    "too many requests",
    "credits",
    "credit balance",
    "余额不足",
    "配额",
    "限流",
    "upstream model",
    "upstream provider",
    "matrixorigin",
    "taas",
    "huawei",
    "maas",
)


class EvalError(RuntimeError):
    """Expected evaluation failure that belongs in the run artifact."""


class ProviderUnavailable(EvalError):
    pass


class ProviderFailure(EvalError):
    pass


class HTTPFailure(EvalError):
    def __init__(self, status: int, body: Any, url: str, operation: str):
        self.status = status
        self.body = body
        self.url = url
        self.operation = operation
        super().__init__(f"HTTP {status} from {operation}: {url}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact_text(value: str) -> str:
    return KEY_VALUE.sub("<redacted>", BEARER.sub("Bearer <redacted>", value))


def redact(value: Any, key: str | None = None) -> Any:
    if key and SECRET_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(redact(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_bytes(encoded)}  {path.name}\n", encoding="utf-8"
    )


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        key = key.strip()
        if not value:
            continue
        # API credentials are only accepted from the repository-root .env.
        # Legacy runtime files may still provide non-secret model settings.
        if path.resolve() != (ROOT / ".env").resolve() and (
            key.endswith(("_API_KEY", "_APP_KEY", "_TOKEN", "_SECRET"))
        ):
            continue
        values[key] = value
    return values


def value_from(env: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = env.get(name, "").strip()
        if value:
            return value
    return default


def is_provider_failure(status: int | None, body: Any) -> bool:
    text = str(body or "").lower()
    if status in {402, 429, 500, 502, 503, 504}:
        return True
    # A dataset name can legitimately contain the strings ``taas`` or
    # ``matrixorigin``.  Do not turn a local validation error into a provider
    # fallback merely because those low-signal words appear in the payload.
    low_signal = {"taas", "matrixorigin"}
    return any(marker.lower() in text for marker in PROVIDER_FAILURE_MARKERS if marker not in low_signal)


def first_value(payload: Any, names: Iterable[str]) -> Any:
    wanted = tuple(names)
    if isinstance(payload, dict):
        for name in wanted:
            if name in payload and payload[name] not in (None, ""):
                return payload[name]
        for value in payload.values():
            found = first_value(value, wanted)
            if found not in (None, ""):
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = first_value(value, wanted)
            if found not in (None, ""):
                return found
    return None


def list_items(payload: Any, preferred: tuple[str, ...] = ()) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    keys = preferred + ("records", "list", "items", "documents", "data", "result", "chunks")
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    for value in payload.values():
        found = list_items(value)
        if found:
            return found
    return []


def provider_error_from_http(exc: HTTPFailure) -> ProviderFailure | None:
    if is_provider_failure(exc.status, exc.body):
        return ProviderFailure(f"{exc.operation}: provider-like HTTP failure {exc.status}: {redact_text(str(exc.body))[:800]}")
    return None


class Progress:
    def __init__(self, path: Path = ACTIVE_PROGRESS):
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def emit(self, stage: str, message: str, **fields: Any) -> None:
        payload = {"at": utc_now(), "stage": stage, "message": message, **fields}
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(redact(payload), ensure_ascii=False) + "\n")
                handle.flush()
            print(f"[{payload['at']}] {stage}: {message}", flush=True)


class ArtifactHTTP:
    def __init__(self, base_url: str, output: Path, progress: Progress, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.output = output
        self.progress = progress
        self.timeout = timeout
        self.counter = 0
        self._save_lock = Lock()

    def root(self) -> "ArtifactHTTP":
        parts = urlsplit(self.base_url)
        path = parts.path
        if path.endswith("/v1"):
            path = path[:-3]
        return ArtifactHTTP(urlunsplit((parts.scheme, parts.netloc, path.rstrip("/"), "", "")), self.output, self.progress, self.timeout)

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}/{path.lstrip('/')}"
        if params:
            url += ("&" if "?" in url else "?") + urlencode({k: str(v) for k, v in params.items() if v is not None})
        return url

    @staticmethod
    def _parse(raw: bytes, content_type: str) -> Any:
        if not raw:
            return None
        if "json" in content_type.lower() or raw[:1] in {b"{", b"["}:
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        return raw[:200_000].decode("utf-8", errors="replace")

    def _save_http(self, operation: str, request_meta: dict[str, Any], response: Any, error: Any = None) -> None:
        with self._save_lock:
            self.counter += 1
            counter = self.counter
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", operation).strip(".") or "request"
            json_dump(
                self.output / "http" / f"{counter:06d}-{slug}.json",
                {"recorded_at": utc_now(), "operation": operation, "request": request_meta, "response": response, "error": error},
            )

    def request(
        self,
        method: str,
        path: str,
        *,
        api_key: str | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        file_path: Path | None = None,
        form: dict[str, Any] | None = None,
        operation: str = "request",
        timeout: float | None = None,
    ) -> Any:
        url = self._url(path, params)
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body: bytes | None = None
        request_meta: dict[str, Any] = {"method": method.upper(), "url": redact_text(url), "headers": headers}
        if file_path is not None:
            boundary = f"----moi-mmdocir-{uuid.uuid4().hex}"
            content = file_path.read_bytes()
            content_type = mimetypes.guess_type(file_path.name)[0] or "text/plain"
            parts: list[bytes] = []
            for name, value in (form or {}).items():
                parts += [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            parts += [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
            body = b"".join(parts)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            request_meta["multipart"] = {
                "fields": form or {},
                "file": {"name": file_path.name, "size": len(content), "sha256": sha256_bytes(content)},
            }
        elif json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            request_meta["json"] = json_body
        request = Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read()
                payload = self._parse(raw, response.headers.get("Content-Type", ""))
                self._save_http(operation, request_meta, {"status": response.status, "headers": dict(response.headers.items()), "body": payload})
                return payload
        except HTTPError as exc:
            raw = exc.read()
            payload = self._parse(raw, exc.headers.get("Content-Type", ""))
            self._save_http(operation, request_meta, {"status": exc.code}, {"type": "http", "status": exc.code, "body": payload})
            failure = HTTPFailure(exc.code, payload, url, operation)
            provider_failure = provider_error_from_http(failure)
            if provider_failure:
                raise provider_failure from exc
            raise failure from exc
        except (URLError, TimeoutError, OSError) as exc:
            self._save_http(operation, request_meta, None, {"type": "transport", "message": str(exc)})
            raise EvalError(f"{operation}: transport failure: {exc}") from exc


class DifyNativeDatasetBinding:
    """Temporarily bind the Dify native chat app to the run's dataset.

    Dify's public dataset API creates an isolated dataset per attempt, while a
    chat app keeps its dataset joins in the console configuration.  The binding
    is therefore made only after indexing and is restored in a ``finally``
    block after native QA.  Credentials are read locally and never written to
    the run artifacts.
    """

    def __init__(self, env: dict[str, str], app_id: str, progress: Progress):
        self.env = env
        self.app_id = app_id
        self.progress = progress
        api_base = value_from(env, "DIFY_API_BASE_URL", default="http://127.0.0.1:8010/v1")
        parts = urlsplit(api_base.rstrip("/"))
        path = parts.path[:-3] if parts.path.endswith("/v1") else parts.path
        self.base_url = urlunsplit((parts.scheme, parts.netloc, path.rstrip("/"), "", ""))
        self.email = value_from(env, "DIFY_LOCAL_ADMIN_EMAIL")
        self.password = value_from(env, "DIFY_LOCAL_ADMIN_PASSWORD")
        self.jar = http.cookiejar.CookieJar()
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(self.jar))
        self.old_config: dict[str, Any] | None = None
        self.info: dict[str, Any] = {"app_id": app_id, "bound_dataset_id": None, "previous_dataset_ids": [], "restored": False}

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/json"
        csrf = next((cookie.value for cookie in self.jar if cookie.name == "csrf_token"), "")
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = Request(f"{self.base_url}/{path.lstrip('/')}", data=data, headers=headers, method=method.upper())
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")[:1000]
            raise EvalError(f"DIFY_CONSOLE_HTTP_{exc.code}: {path}: {redact_text(raw)}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise EvalError(f"DIFY_CONSOLE_REQUEST_FAILED: {path}: {exc}") from exc

    def _login(self) -> None:
        if not self.email or not self.password:
            raise ProviderUnavailable("DIFY_LOCAL_ADMIN_CREDENTIALS_MISSING_FOR_NATIVE_BINDING")
        encoded_password = base64.b64encode(self.password.encode("utf-8")).decode("ascii")
        result = self._request(
            "POST",
            "/console/api/login",
            {"email": self.email, "password": encoded_password, "remember_me": True},
        )
        if not isinstance(result, dict) or result.get("result") not in {"success", None}:
            raise EvalError("DIFY_CONSOLE_LOGIN_FAILED")

    @staticmethod
    def _unwrap(payload: Any) -> dict[str, Any]:
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(data, dict):
            raise EvalError("DIFY_CONSOLE_APP_CONFIG_INVALID")
        return data

    @staticmethod
    def _dataset_ids(config: dict[str, Any]) -> list[str]:
        dataset_configs = config.get("dataset_configs") or {}
        datasets = dataset_configs.get("datasets") if isinstance(dataset_configs, dict) else None
        items = datasets.get("datasets", []) if isinstance(datasets, dict) else []
        ids: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            dataset = item.get("dataset")
            if isinstance(dataset, dict) and dataset.get("id"):
                ids.append(str(dataset["id"]))
        return ids

    def bind(self, dataset_id: str, output: Path) -> dict[str, Any]:
        self._login()
        detail = self._unwrap(self._request("GET", f"/console/api/apps/{self.app_id}"))
        old_config = detail.get("model_config")
        if not isinstance(old_config, dict):
            raise EvalError("DIFY_CONSOLE_APP_MODEL_CONFIG_MISSING")
        self.old_config = json.loads(json.dumps(old_config))
        self.info["previous_dataset_ids"] = self._dataset_ids(self.old_config)
        new_config = json.loads(json.dumps(old_config))
        dataset_configs = new_config.setdefault("dataset_configs", {})
        dataset_configs["datasets"] = {"strategy": "router", "datasets": [{"dataset": {"id": dataset_id, "enabled": True}}]}
        self._request("POST", f"/console/api/apps/{self.app_id}/model-config", new_config)
        verify = self._unwrap(self._request("GET", f"/console/api/apps/{self.app_id}"))
        if self._dataset_ids(verify.get("model_config") or {}) != [dataset_id]:
            raise EvalError("DIFY_CONSOLE_NATIVE_DATASET_BIND_VERIFY_FAILED")
        self.info["bound_dataset_id"] = dataset_id
        json_dump(output / "native-binding.json", self.info)
        self.progress.emit("native", "Dify native app bound to this dataset", app_id=self.app_id, dataset_id=dataset_id)
        return self.info

    def restore(self, output: Path) -> None:
        if self.old_config is None:
            return
        try:
            self._request("POST", f"/console/api/apps/{self.app_id}/model-config", self.old_config)
            verify = self._unwrap(self._request("GET", f"/console/api/apps/{self.app_id}"))
            restored_ids = self._dataset_ids(verify.get("model_config") or {})
            self.info["restored_dataset_ids"] = restored_ids
            self.info["restored"] = restored_ids == self.info.get("previous_dataset_ids", [])
            if not self.info["restored"]:
                raise EvalError("DIFY_CONSOLE_NATIVE_DATASET_RESTORE_VERIFY_FAILED")
            json_dump(output / "native-binding.json", self.info)
            self.progress.emit("native", "Dify native app dataset binding restored", app_id=self.app_id)
        except Exception as exc:
            self.info["restore_error"] = str(exc)
            json_dump(output / "native-binding.json", self.info)
            raise


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    llm_model: str
    embedding_model: str
    embedding_dimension: int | None = None
    reranker_model: str = ""
    embedding_provider: str = ""
    native_api_key: str = ""
    native_app_id: str = ""


def provider_dict(provider: Provider) -> dict[str, Any]:
    return {
        "name": provider.name,
        "base_url": provider.base_url,
        "llm_model": provider.llm_model,
        "embedding_model": provider.embedding_model,
        "embedding_dimension": provider.embedding_dimension,
        "reranker_model": provider.reranker_model,
        "embedding_provider": provider.embedding_provider,
        "api_key_loaded": bool(provider.api_key and not provider.api_key.startswith("<")),
        "native_api_key_loaded": bool(provider.native_api_key and not provider.native_api_key.startswith("<")),
        "native_app_id_loaded": bool(provider.native_app_id),
    }


def load_provider_profiles(system: str) -> tuple[dict[str, str], dict[str, Provider]]:
    if system == "dify_local":
        # Keep the repository-level TaaS settings as the common source of
        # truth, while allowing Dify-specific credentials/runtime values to
        # override them when present.
        platform_env = parse_dotenv(ROOT / ".env")
        taas = Provider(
            name="taas",
            base_url=value_from(platform_env, "TAAS_BASE_URL", default="https://token.moi.matrixorigin.cn/v1"),
            api_key=value_from(platform_env, "TAAS_API_KEY"),
            llm_model=value_from(platform_env, "TAAS_LLM_MODEL", default="qwen3.6-flash"),
            embedding_model=value_from(platform_env, "TAAS_EMBEDDING_MODEL", "DIFY_EMBEDDING_MODEL", default="bge-m3"),
            embedding_provider=value_from(platform_env, "DIFY_EMBEDDING_PROVIDER", default="matrixorigin/matrixorigin_taas/matrixorigin_taas"),
            native_api_key=value_from(platform_env, "DIFY_LOCAL_API_KEY"),
            native_app_id=value_from(platform_env, "DIFY_LOCAL_APP_ID"),
        )
        maas = Provider(
            name="maas",
            base_url=value_from(platform_env, "MAAS_BASE_URL", default="https://api.modelarts-maas.com/v1"),
            api_key=value_from(platform_env, "MAAS_API_KEY"),
            llm_model=value_from(platform_env, "MAAS_LLM_MODEL", default="qwen3-30b-a3b"),
            embedding_model=value_from(platform_env, "MAAS_EMBEDDING_MODEL", default="bge-m3"),
            embedding_dimension=int(value_from(platform_env, "MAAS_EMBEDDING_DIMENSION", default="1024")),
            reranker_model=value_from(platform_env, "MAAS_RERANKER_MODEL", default="bge-reranker-v2-m3"),
            embedding_provider=value_from(platform_env, "DIFY_MAAS_EMBEDDING_PROVIDER", default="matrixorigin/matrixorigin_taas/huawei_maas"),
            native_api_key=value_from(platform_env, "DIFY_MAAS_API_KEY"),
            native_app_id=value_from(platform_env, "DIFY_MAAS_APP_ID"),
        )
        qianfan_env = platform_env
        qianfan = Provider(
            name="qianfan",
            base_url=value_from(qianfan_env, "QIANFAN_BASE_URL", default="https://qianfan.baidubce.com/v2"),
            api_key=value_from(qianfan_env, "QIANFAN_API_KEY"),
            llm_model=value_from(qianfan_env, "QIANFAN_LLM_MODEL", default="deepseek-v4-flash"),
            embedding_model=value_from(qianfan_env, "QIANFAN_EMBEDDING_MODEL", default="qwen3-embedding-8b"),
            embedding_dimension=int(value_from(qianfan_env, "QIANFAN_EMBEDDING_DIMENSION", default="4096")),
            reranker_model=value_from(qianfan_env, "QIANFAN_RERANKER_MODEL"),
            embedding_provider=value_from(platform_env, "DIFY_QIANFAN_EMBEDDING_PROVIDER"),
            native_api_key=value_from(platform_env, "DIFY_QIANFAN_API_KEY", "DIFY_LOCAL_QIANFAN_API_KEY"),
            native_app_id=value_from(platform_env, "DIFY_QIANFAN_APP_ID", "DIFY_LOCAL_QIANFAN_APP_ID"),
        )
        local_env = parse_dotenv(ROOT / ".env")
        local_bge = Provider(
            name="local_bge",
            base_url=value_from(
                platform_env,
                "DIFY_LOCAL_BGE_BASE_URL",
                default="http://192.168.5.2:8081/v1",
            ),
            api_key=value_from(local_env, "TAAS_API_KEY"),
            llm_model="",
            embedding_model="bge-m3",
            embedding_dimension=1024,
            embedding_provider=value_from(
                platform_env,
                "DIFY_EMBEDDING_PROVIDER",
                default="matrixorigin/matrixorigin_taas/matrixorigin_taas",
            ),
        )
        return platform_env, {"taas": taas, "maas": maas, "qianfan": qianfan, "local_bge": local_bge}

    platform_env = parse_dotenv(ROOT / ".env")
    taas = Provider(
        name="taas",
        base_url=value_from(platform_env, "TAAS_BASE_URL", default="https://token.moi.matrixorigin.cn/v1"),
        api_key=value_from(platform_env, "TAAS_API_KEY"),
        llm_model=value_from(platform_env, "TAAS_LLM_MODEL", default="qwen3.6-flash"),
        embedding_model=value_from(platform_env, "TAAS_EMBEDDING_MODEL", default="bge-m3"),
        native_api_key=value_from(platform_env, "FASTGPT_API_KEY"),
        native_app_id=value_from(platform_env, "FASTGPT_APP_ID"),
    )
    maas = Provider(
        name="maas",
        base_url=value_from(platform_env, "MAAS_BASE_URL", default="https://api.modelarts-maas.com/v1"),
        api_key=value_from(platform_env, "MAAS_API_KEY"),
        llm_model=value_from(platform_env, "MAAS_LLM_MODEL", default="qwen3-30b-a3b"),
        embedding_model=value_from(platform_env, "MAAS_EMBEDDING_MODEL", default="bge-m3"),
        embedding_dimension=int(value_from(platform_env, "MAAS_EMBEDDING_DIMENSION", default="1024")),
        reranker_model=value_from(platform_env, "MAAS_RERANKER_MODEL", default="bge-reranker-v2-m3"),
        native_api_key=value_from(platform_env, "FASTGPT_MAAS_API_KEY", "FASTGPT_API_KEY"),
        native_app_id=value_from(platform_env, "FASTGPT_MAAS_APP_ID", "FASTGPT_APP_ID"),
    )
    qianfan_env = platform_env
    qianfan = Provider(
        name="qianfan",
        base_url=value_from(qianfan_env, "QIANFAN_BASE_URL", default="https://qianfan.baidubce.com/v2"),
        api_key=value_from(qianfan_env, "QIANFAN_API_KEY"),
        llm_model=value_from(qianfan_env, "QIANFAN_LLM_MODEL", default="deepseek-v4-flash"),
        embedding_model=value_from(qianfan_env, "QIANFAN_EMBEDDING_MODEL", default="qwen3-embedding-8b"),
        embedding_dimension=int(value_from(qianfan_env, "QIANFAN_EMBEDDING_DIMENSION", default="4096")),
        reranker_model=value_from(qianfan_env, "QIANFAN_RERANKER_MODEL"),
        native_api_key=value_from(platform_env, "FASTGPT_QIANFAN_API_KEY"),
        native_app_id=value_from(platform_env, "FASTGPT_QIANFAN_APP_ID"),
    )
    return platform_env, {"taas": taas, "maas": maas, "qianfan": qianfan}


def external_json(provider: Provider, path: str, *, body: Any = None, timeout: float = 60) -> Any:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT, "Authorization": f"Bearer {provider.api_key}"}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{provider.base_url.rstrip('/')}/{path.lstrip('/')}", data=data, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:800]
        raise ProviderFailure(f"{provider.name} {path} HTTP {exc.code}: {redact_text(body_text)}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ProviderFailure(f"{provider.name} {path} probe failed: {exc}") from exc


def probe_qianfan(provider: Provider, output: Path, progress: Progress) -> dict[str, Any]:
    result: dict[str, Any] = {"provider": provider_dict(provider), "ready": False, "rerank": "unsupported", "errors": []}
    if not provider.api_key or provider.api_key.startswith("<"):
        result["errors"].append("QIANFAN_API_KEY missing")
        json_dump(output / "providers" / "qianfan-probe.json", result)
        return result
    try:
        models = external_json(provider, "/models")
        model_ids = {str(item.get("id")) for item in models.get("data", []) if isinstance(item, dict) and item.get("id")}
        result["models"] = {
            "count": len(model_ids),
            "llm_available": provider.llm_model in model_ids,
            "embedding_available": provider.embedding_model in model_ids,
            "reranker_available": bool(provider.reranker_model and provider.reranker_model in model_ids),
        }
        if not result["models"]["llm_available"] or not result["models"]["embedding_available"]:
            raise ProviderUnavailable("QIANFAN_REQUIRED_LLM_OR_EMBEDDING_MODEL_UNAVAILABLE")
        embedding = external_json(provider, "/embeddings", body={"model": provider.embedding_model, "input": ["MOI MMDocIR provider health check"], "encoding_format": "float"})
        vector = first_value(embedding, ("embedding",))
        result["embedding_dimension"] = len(vector) if isinstance(vector, list) else None
        chat = external_json(provider, "/chat/completions", body={"model": provider.llm_model, "messages": [{"role": "user", "content": "Reply with exactly: OK"}], "stream": False, "max_tokens": 32, "temperature": 0})
        choice = list_items(chat, ("choices",))
        message = choice[0].get("message", {}) if choice and isinstance(choice[0], dict) else {}
        result["chat_content"] = bool(str(message.get("content") or message.get("reasoning_content") or "").strip())
        result["rerank"] = "available" if result["models"]["reranker_available"] else "unsupported"
        result["ready"] = bool(result["chat_content"] and result["embedding_dimension"])
    except (ProviderUnavailable, ProviderFailure) as exc:
        result["errors"].append(str(exc))
    json_dump(output / "providers" / "qianfan-probe.json", result)
    progress.emit("provider", "Qianfan probe finished", ready=result["ready"], rerank=result["rerank"])
    return result


@dataclass
class MMDocIRQuestion:
    question_id: str
    query_index: int
    question: str
    answer: str
    file_id: str
    doc_name: str
    page_ids: list[int]


class MMDocIRFixture:
    def __init__(self, prepared: Path, output: Path, documents_limit: int, questions_limit: int):
        self.prepared = prepared
        self.output = output
        self.documents_limit = documents_limit
        self.questions_limit = questions_limit
        self.pages = [json.loads(line) for line in (prepared / "pages.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.questions_raw = [json.loads(line) for line in (prepared / "questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.questions_raw.sort(key=lambda row: int(row.get("query_index", 0)))
        self.questions: list[MMDocIRQuestion] = []
        self.documents: list[str] = []
        self.files: list[Path] = []

    def select(self) -> None:
        first_question: dict[str, int] = {}
        for row in self.questions_raw:
            first_question.setdefault(str(row["file_id"]), int(row.get("query_index", 0)))
        all_docs = sorted({str(row["file_id"]) for row in self.pages}, key=lambda fid: (first_question.get(fid, 10**9), fid))
        self.documents = all_docs if self.documents_limit <= 0 else all_docs[: self.documents_limit]
        selected = [row for row in self.questions_raw if str(row["file_id"]) in set(self.documents)]
        if self.questions_limit > 0:
            selected = selected[: self.questions_limit]
        self.questions = [
            MMDocIRQuestion(
                question_id=str(row["id"]),
                query_index=int(row.get("query_index", 0)),
                question=str(row.get("question", "")),
                answer=str(row.get("answer", "")),
                file_id=str(row["file_id"]),
                doc_name=str(row.get("doc_name", "")),
                page_ids=[int(page) for page in row.get("page_ids", [])],
            )
            for row in selected
        ]

    @staticmethod
    def _safe_name(value: str) -> str:
        value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "document"
        return value[:100]

    def build(self, progress: Progress) -> dict[str, Any]:
        self.select()
        source_dir = self.output / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for page in self.pages:
            if str(page["file_id"]) in set(self.documents):
                grouped[str(page["file_id"])].append(page)
        # Upload one source file per page.  Some RAG products normalize or
        # discard marker-like text during Markdown indexing; putting the page
        # identity in the original filename leaves a stable locator in the
        # product's retrieval response and matches MMDocIR's page condition.
        file_rows: list[dict[str, Any]] = []
        file_index = 0
        for file_id in self.documents:
            pages = sorted(
                grouped[file_id],
                key=lambda row: (int(row.get("page_number", 0)), int(row.get("chunk_index", 0))),
            )
            for page in pages:
                file_index += 1
                page_number = int(page.get("page_number", 0))
                page_id = str(page.get("id", f"{file_id}_{page_number}"))
                doc_name = str(
                    page.get("metadata", {}).get("doc_name")
                    or page.get("metadata", {}).get("file_name")
                    or file_id
                )
                marker = f"MMDocIR_PAGE_MARKER file_id={file_id} page_number={page_number} page_id={page_id}"
                source_marker = f"MMDocIR_SOURCE_PAGE file_id={file_id} page_number={page_number}"
                # Collapse layout whitespace so the custom splitter does not
                # turn every layout line into a separate product chunk.
                text = re.sub(r"\s+", " ", str(page.get("content", ""))).strip() or "\u2060"
                chunks = [
                    f"# MMDocIR page {page_number} - {doc_name}\n\n"
                    f"{source_marker}\n{marker}\n\n{text}\n"
                ]
                target = source_dir / f"MMDocIR__{file_id}__page_{page_number:04d}.md"
                encoded = "".join(chunks).encode("utf-8")
                target.write_bytes(encoded)
                file_rows.append(
                    {
                        "file_id": file_id,
                        "doc_name": doc_name,
                        "page_number": page_number,
                        "page_id": page_id,
                        "path": str(target.relative_to(self.output)),
                        "pages": 1,
                        "source_chars": len(text),
                        "bytes": len(encoded),
                        "sha256": sha256_bytes(encoded),
                    }
                )
        question_rows = [
            {"question_id": q.question_id, "query_index": q.query_index, "question": q.question, "answer": q.answer, "file_id": q.file_id, "doc_name": q.doc_name, "page_ids": q.page_ids}
            for q in self.questions
        ]
        manifest = {
            "schema": "mmdocir-competitor-page-file-v2",
            "condition": "page",
            "prepared_root": str(self.prepared),
            "source_manifest": str((self.prepared / "manifest.json").relative_to(ROOT)),
            "documents": len(self.documents),
            "upload_granularity": "page",
            "files_count": len(file_rows),
            "questions": len(self.questions),
            "pages": sum(row["pages"] for row in file_rows),
            "source_chars": sum(row["source_chars"] for row in file_rows),
            "marker_repeat_chars": 1400,
            "files": file_rows,
            "questions_file": "questions.json",
        }
        json_dump(self.output / "fixture-manifest.json", manifest)
        json_dump(self.output / "questions.json", question_rows)
        progress.emit("fixture", "MMDocIR marker fixture ready", documents=len(self.documents), pages=manifest["pages"], questions=len(self.questions), bytes=sum(row["bytes"] for row in file_rows))
        return manifest


def extract_hits(payload: Any, system: str) -> list[Any]:
    if system == "dify":
        return list_items(payload, ("records", "retriever_resources"))
    return list_items(payload, ("list",))


def markers_from(value: Any) -> list[tuple[str, int]]:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    pages = [(file_id, int(page)) for file_id, page in PAGE_MARKER.findall(text)]
    if not pages:
        pages = [(file_id, int(page)) for file_id, page in SOURCE_PAGE_MARKER.findall(text)]
    if not pages:
        pages = [(file_id, int(page)) for file_id, page in PAGE_FILE_MARKER.findall(text)]
    if pages:
        return pages
    return [(file_id, -1) for file_id in DOC_MARKER.findall(text)]


def answer_from(payload: Any) -> str:
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            if isinstance(message, dict) and str(message.get("content") or "").strip():
                return str(message["content"])
        for name in ("answer", "content", "text", "response"):
            if isinstance(payload.get(name), str) and payload[name].strip():
                return payload[name]
        for value in payload.values():
            found = answer_from(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = answer_from(value)
            if found:
                return found
    return ""


def normalize(value: str) -> str:
    return re.sub(r"\W+", "", value.lower(), flags=re.UNICODE)


def score_retrieval(question: MMDocIRQuestion, hits: list[Any]) -> dict[str, Any]:
    gold_pages = {(question.file_id, int(page)) for page in question.page_ids}
    gold_doc = question.file_id
    ranked_markers: list[list[tuple[str, int]]] = [markers_from(hit) for hit in hits]
    def page_hit(k: int) -> bool:
        return bool(gold_pages.intersection({marker for row in ranked_markers[:k] for marker in row}))
    def doc_hit(k: int) -> bool:
        return gold_doc in {file_id for row in ranked_markers[:k] for file_id, _ in row}
    def page_fraction_recall(k: int) -> float:
        if not gold_pages:
            return 0.0
        found = {marker for row in ranked_markers[:k] for marker in row}
        return len(gold_pages.intersection(found)) / len(gold_pages)
    return {
        "gold_pages": sorted([list(page) for page in gold_pages]),
        "marker_hits": ranked_markers,
        "page_recall_at_1": page_hit(1),
        "page_recall_at_3": page_hit(3),
        "page_recall_at_5": page_hit(5),
        "page_recall_at_10": page_hit(10),
        "page_fraction_recall_at_1": page_fraction_recall(1),
        "page_fraction_recall_at_3": page_fraction_recall(3),
        "page_fraction_recall_at_5": page_fraction_recall(5),
        "page_fraction_recall_at_10": page_fraction_recall(10),
        "document_recall_at_1": doc_hit(1),
        "document_recall_at_3": doc_hit(3),
        "document_recall_at_5": doc_hit(5),
        "document_recall_at_10": doc_hit(10),
        "marker_observed": bool(ranked_markers),
    }


class CompetitorRun:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.system = args.system
        self.system_id = f"{args.system}"
        self.run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.root = ROOT / "runs/stage1/mmdocir-competitors" / self.run_id / args.system / args.condition / args.phase
        self.root.mkdir(parents=True, exist_ok=False)
        self.progress = Progress(Path(args.progress_path) if args.progress_path else ACTIVE_PROGRESS)
        self.platform_env, self.providers = load_provider_profiles(args.system)
        self.provider_probe: dict[str, Any] = {}
        self.current_provider = "maas"
        self.native_disabled_reason: str | None = None
        self.native_binding_enabled = bool(getattr(args, "bind_dify_native_dataset", False)) and args.system == "dify_local"
        self.attempts: list[dict[str, Any]] = []
        self.fixture = MMDocIRFixture(Path(args.prepared_root), self.root, args.documents_limit, args.questions_limit)
        self.fixture_manifest: dict[str, Any] = {}

    def status(self, **fields: Any) -> None:
        payload = {"run_id": self.run_id, "system_id": self.system_id, "root": str(self.root.relative_to(ROOT)), **fields}
        json_dump(ACTIVE_STATUS, payload)

    def setup(self) -> None:
        self.status(status="starting", phase=self.args.phase, condition=self.args.condition)
        if self.args.condition != "page":
            raise EvalError("only page condition is implemented in this initial competitor runner")
        self.fixture_manifest = self.fixture.build(self.progress)
        self.provider_probe = probe_qianfan(self.providers["qianfan"], self.root, self.progress)
        json_dump(self.root / "run-manifest.json", {
            "schema": "mmdocir-local-competitor-run-v1",
            "run_id": self.run_id,
            "system_id": self.system_id,
            "deployment_mode": "self_hosted",
            "condition": self.args.condition,
            "phase": self.args.phase,
            "platform": "linux/arm64-or-emulated",
            "model_egress": "external",
            "prepared_root": str(Path(self.args.prepared_root)),
            "fixture": self.fixture_manifest,
            "providers": {name: provider_dict(profile) for name, profile in self.providers.items()},
            "qianfan_probe": self.provider_probe,
            "fallback_policy": (
                "Huawei MaaS first; stop on provider failure; no mixed vector space"
                if self.args.provider == "auto"
                else f"fixed provider: {self.args.provider}; no automatic fallback"
            ),
            "bind_dify_native_dataset": self.native_binding_enabled,
        })

    def base_url_and_keys(self, provider: Provider) -> tuple[str, str, str, str]:
        if self.system == "dify_local":
            base = value_from(self.platform_env, "DIFY_API_BASE_URL", default="http://127.0.0.1:8010/v1")
            dataset_key = value_from(self.platform_env, "DIFY_LOCAL_DATASET_API_KEY", "DIFY_DATASET_API_KEY")
            app_key = provider.native_api_key or value_from(self.platform_env, "DIFY_LOCAL_API_KEY", "DIFY_API_KEY")
            return base, dataset_key, app_key, provider.native_app_id
        base = value_from(self.platform_env, "FASTGPT_BASE_URL", default="http://127.0.0.1:3000")
        return base, provider.native_api_key or value_from(self.platform_env, "FASTGPT_API_KEY"), provider.native_api_key, provider.native_app_id

    def discover_dify_provider(self, client: ArtifactHTTP, provider: Provider, dataset_key: str) -> None:
        if provider.name == "taas":
            return
        if provider.embedding_provider:
            return
        try:
            payload = client.request("GET", "/workspaces/current/models/model-types/text-embedding", api_key=dataset_key, operation="dify-provider-discovery")
        except EvalError as exc:
            raise ProviderUnavailable(f"DIFY_{provider.name.upper()}_PROVIDER_DISCOVERY_FAILED: {exc}") from exc
        for item in list_items(payload):
            if not isinstance(item, dict):
                continue
            model = str(item.get("model") or item.get("model_name") or item.get("name") or "")
            if model == provider.embedding_model:
                provider.embedding_provider = str(item.get("provider") or item.get("provider_name") or "")
                break
        if not provider.embedding_provider:
            raise ProviderUnavailable(
                f"DIFY_{provider.name.upper()}_EMBEDDING_NOT_REGISTERED: register {provider.embedding_model} in local Dify provider"
            )

    def ensure_provider(self, provider: Provider, client: ArtifactHTTP, dataset_key: str) -> None:
        if provider.name == "maas":
            if not provider.api_key or provider.api_key.startswith("<"):
                raise ProviderUnavailable("MAAS_API_KEY_MISSING")
            probe = external_json(provider, "/embeddings", body={"model": provider.embedding_model, "input": ["MMDocIR provider smoke"], "encoding_format": "float"})
            vectors = list_items(probe, ("data",))
            if len(vectors) != 1 or len(vectors[0].get("embedding", [])) != (provider.embedding_dimension or 1024):
                raise ProviderUnavailable("MAAS_EMBEDDING_PROBE_INVALID")
            if self.system == "dify_local":
                self.discover_dify_provider(client, provider, dataset_key)
            else:
                env = dict(os.environ)
                env.update(self.platform_env)
                command = [sys.executable, "local-rag-platforms/fastgpt_local/fastgpt_local.py", "provider", "--provider", "maas", "--execute"]
                completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
                registration = {"returncode": completed.returncode, "stdout": redact_text(completed.stdout), "stderr": redact_text(completed.stderr)}
                json_dump(self.root / "providers" / "fastgpt-maas-registration.json", registration)
                if completed.returncode:
                    raise ProviderUnavailable(f"FASTGPT_MAAS_CHANNEL_REGISTRATION_FAILED: {redact_text(completed.stderr)[:800]}")
            return
        if provider.name == "qianfan":
            if not self.provider_probe.get("ready"):
                raise ProviderUnavailable("QIANFAN_PROBE_NOT_READY")
            if self.system == "dify_local":
                self.discover_dify_provider(client, provider, dataset_key)
            else:
                env = dict(os.environ)
                env.update(self.platform_env)
                if self.provider_probe.get("rerank") != "available":
                    env["QIANFAN_RERANKER_MODEL"] = ""
                command = [sys.executable, "local-rag-platforms/fastgpt_local/fastgpt_local.py", "provider", "--provider", "qianfan", "--execute"]
                completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
                registration = {"returncode": completed.returncode, "stdout": redact_text(completed.stdout), "stderr": redact_text(completed.stderr)}
                json_dump(self.root / "providers" / "fastgpt-qianfan-registration.json", registration)
                if completed.returncode:
                    raise ProviderUnavailable(f"FASTGPT_QIANFAN_CHANNEL_REGISTRATION_FAILED: {redact_text(completed.stderr)[:800]}")

    def wait_service(self, client: ArtifactHTTP, provider: Provider) -> None:
        deadline = time.monotonic() + self.args.startup_wait
        last_error = ""
        while time.monotonic() < deadline:
            try:
                if self.system == "dify_local":
                    client.root().request("GET", "/console/api/setup", operation="health")
                else:
                    client.request("GET", "/", operation="health")
                self.progress.emit("service", "local service ready", system_id=self.system_id, provider=provider.name)
                return
            except EvalError as exc:
                last_error = str(exc)
                if int(time.monotonic()) % 10 < 2:
                    self.progress.emit("service", "waiting for local service", error=last_error[:300])
                time.sleep(2)
        raise EvalError(f"SERVICE_STARTUP_TIMEOUT: {last_error}")

    @staticmethod
    def unwrap_fastgpt(payload: Any) -> Any:
        if isinstance(payload, dict) and "code" in payload and payload.get("code") not in (None, 200):
            raise EvalError(f"FastGPT API code {payload.get('code')}: {payload.get('message')}")
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def create_dataset(self, client: ArtifactHTTP, provider: Provider, dataset_key: str) -> str:
        # Dify 1.16.1 caps dataset names at 40 characters.
        name = f"MMDocIR-{self.args.phase}-{provider.name}-{uuid.uuid4().hex[:8]}"
        if self.system == "dify_local":
            payload = {
                "name": name,
                "indexing_technique": "high_quality",
                "permission": "only_me",
                "embedding_model": provider.embedding_model,
                "embedding_model_provider": provider.embedding_provider,
            }
            created = client.request("POST", "/datasets", api_key=dataset_key, json_body=payload, operation="create-dataset")
            dataset_id = first_value(created, ("id", "dataset_id"))
        else:
            payload = {
                "parentId": None,
                "type": "dataset",
                "name": name,
                "intro": "MOI MMDocIR local competitor evaluation",
                "avatar": "",
                "vectorModel": provider.embedding_model,
                "agentModel": provider.llm_model,
            }
            created = self.unwrap_fastgpt(client.request("POST", "/api/core/dataset/create", api_key=dataset_key, json_body=payload, operation="create-dataset"))
            dataset_id = first_value(created, ("datasetId", "id"))
        if not dataset_id:
            raise EvalError("CREATE_DATASET_NO_ID")
        return str(dataset_id)

    def upload_documents(self, client: ArtifactHTTP, provider: Provider, dataset_key: str, dataset_id: str) -> list[str]:
        uploads: list[str] = []
        files = sorted((self.root / "source").glob("*.md"))
        for index, path in enumerate(files, start=1):
            if self.system == "dify_local":
                payload = {
                    "indexing_technique": "high_quality",
                    "process_rule": {
                        "mode": "custom",
                        "rules": {
                            "pre_processing_rules": [{"id": "remove_extra_spaces", "enabled": True}, {"id": "remove_urls_emails", "enabled": False}],
                            "segmentation": {"separator": "\n", "max_tokens": 512, "chunk_overlap": 64},
                        },
                    },
                }
                response = client.request("POST", f"/datasets/{dataset_id}/document/create-by-file", api_key=dataset_key, file_path=path, form={"data": json.dumps(payload)}, operation=f"upload-{index:04d}", timeout=self.args.upload_timeout)
                doc_id = first_value(response, ("document", "document_id", "id"))
            else:
                response = self.unwrap_fastgpt(client.request("POST", "/api/core/dataset/collection/create/localFile", api_key=dataset_key, file_path=path, form={"datasetId": dataset_id, "parentId": None, "trainingType": "chunk", "chunkSize": 512, "chunkSplitter": "", "qaPrompt": "", "metadata": json.dumps({"benchmark": "MMDocIR", "condition": "page"})}, operation=f"upload-{index:04d}", timeout=self.args.upload_timeout))
                doc_id = first_value(response, ("collectionId", "id"))
            if doc_id:
                uploads.append(str(doc_id))
            if index == 1 or index == len(files) or index % 5 == 0:
                self.progress.emit("ingest", "document upload progress", system_id=self.system_id, provider=provider.name, uploaded=index, total=len(files), dataset_id=dataset_id)
        if len(uploads) != len(files):
            raise EvalError(f"UPLOAD_INCOMPLETE: {len(uploads)}/{len(files)} document IDs returned")
        return uploads

    def wait_index(self, client: ArtifactHTTP, provider: Provider, dataset_key: str, dataset_id: str, expected_ids: list[str]) -> dict[str, Any]:
        deadline = time.monotonic() + self.args.index_wait
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            if self.system == "dify_local":
                page = 1
                items: list[Any] = []
                total = None
                # Full MMDocIR uses one Dify document per source page (about
                # 18.7k documents).  The former fixed 20-page cap could only
                # observe 2,000 documents, so a healthy full index could never
                # satisfy the readiness check.  Bound pagination by the number
                # of uploads plus one sentinel page instead.
                max_pages = max(1, (len(expected_ids) + 99) // 100 + 1)
                while page <= max_pages:
                    payload = client.request("GET", f"/datasets/{dataset_id}/documents", api_key=dataset_key, params={"page": page, "limit": 100}, operation=f"document-status-{page}")
                    batch = list_items(payload, ("data", "documents"))
                    items.extend(batch)
                    total = first_value(payload, ("total",))
                    if not batch or (total is not None and len(items) >= int(total)) or len(batch) < 100:
                        break
                    page += 1
                statuses = [str(first_value(item, ("indexing_status", "status", "state")) or "").lower() for item in items]
                last = {"items": len(items), "total": total, "statuses": dict(Counter(statuses))}
                failed = [item for item in items if str(first_value(item, ("indexing_status", "status", "state")) or "").lower() in {"error", "failed"}]
                if failed:
                    body = json.dumps(failed, ensure_ascii=False)
                    if provider.name in {"taas", "maas"} and is_provider_failure(None, body):
                        raise ProviderFailure(f"DIFY_INDEX_PROVIDER_FAILURE: {redact_text(body)[:800]}")
                    raise EvalError(f"DIFY_INDEX_FAILED: {redact_text(body)[:800]}")
                ready = len(items) >= len(expected_ids) and bool(items) and all(status in {"completed", "indexed", "ready", "available"} for status in statuses)
            else:
                payload = self.unwrap_fastgpt(client.request("POST", "/api/core/dataset/collection/listV2", api_key=dataset_key, json_body={"offset": 0, "pageSize": max(30, len(expected_ids) + 5), "datasetId": dataset_id, "parentId": None, "searchText": ""}, operation="collection-status"))
                items = list_items(payload, ("list",))
                statuses = [str(first_value(item, ("status", "trainingType", "state")) or "").lower() for item in items]
                last = {"items": len(items), "statuses": dict(Counter(statuses)), "training_amount": sum(int(item.get("trainingAmount", 0) or 0) for item in items if isinstance(item, dict)), "active_training_amount": sum(int(item.get("activeTrainingAmount", 0) or 0) for item in items if isinstance(item, dict))}
                failed = [item for item in items if isinstance(item, dict) and (item.get("hasError") or item.get("finalErrorAmount", 0))]
                if failed:
                    body = json.dumps(failed, ensure_ascii=False)
                    if provider.name in {"taas", "maas"} and is_provider_failure(None, body):
                        raise ProviderFailure(f"FASTGPT_INDEX_PROVIDER_FAILURE: {redact_text(body)[:800]}")
                    raise EvalError(f"FASTGPT_INDEX_FAILED: {redact_text(body)[:800]}")
                ready = len(items) >= len(expected_ids) and bool(items) and not failed and all(int(item.get("trainingAmount", 0) or 0) == 0 and int(item.get("activeTrainingAmount", 0) or 0) == 0 for item in items if isinstance(item, dict))
            self.progress.emit("ingest", "index status", provider=provider.name, dataset_id=dataset_id, ready=ready, **last)
            if ready:
                return last
            time.sleep(self.args.poll_seconds)
        raise EvalError(f"INDEX_WAIT_TIMEOUT: {json.dumps(last, ensure_ascii=False)}")

    def retrieve(self, client: ArtifactHTTP, provider: Provider, dataset_key: str, dataset_id: str, question: str, ordinal: int) -> Any:
        if self.system == "dify_local":
            return client.request("POST", f"/datasets/{dataset_id}/retrieve", api_key=dataset_key, json_body={"query": question, "retrieval_model": {"search_method": "semantic_search", "reranking_enable": False, "top_k": self.args.top_k, "score_threshold_enabled": False}}, operation=f"retrieval-{ordinal:04d}", timeout=self.args.query_timeout)
        return self.unwrap_fastgpt(client.request("POST", "/api/core/dataset/searchTest", api_key=dataset_key, json_body={"datasetId": dataset_id, "text": question, "limit": self.args.top_k, "similarity": 0, "searchMode": "embedding", "usingReRank": False, "datasetSearchUsingExtensionQuery": False}, operation=f"retrieval-{ordinal:04d}", timeout=self.args.query_timeout))

    def native(self, client: ArtifactHTTP, provider: Provider, app_key: str, app_id: str, question: str, ordinal: int) -> Any:
        if not app_key:
            raise ProviderUnavailable("NATIVE_APP_KEY_NOT_CONFIGURED_FOR_PROVIDER")
        if self.system == "dify_local":
            return client.request("POST", "/chat-messages", api_key=app_key, json_body={"inputs": {}, "query": question, "response_mode": "blocking", "conversation_id": "", "user": f"moi-mmdocir-{self.run_id}-{ordinal}-{uuid.uuid4().hex[:8]}"}, operation=f"native-{ordinal:04d}", timeout=self.args.native_timeout)
        if not app_id:
            raise ProviderUnavailable("FASTGPT_NATIVE_APP_ID_NOT_CONFIGURED_FOR_PROVIDER")
        return self.unwrap_fastgpt(client.request("POST", "/api/v1/chat/completions", api_key=app_key, json_body={"appId": app_id, "chatId": str(uuid.uuid4()), "stream": False, "detail": True, "messages": [{"role": "user", "content": question}]}, operation=f"native-{ordinal:04d}", timeout=self.args.native_timeout))

    def _evaluate_attempt(
        self,
        provider_name: str,
        provider: Provider,
        client: ArtifactHTTP,
        dataset_key: str,
        app_key: str,
        app_id: str,
        dataset_id: str,
        output: Path,
        upload_ids: list[str],
        index_state: dict[str, Any],
    ) -> dict[str, Any]:
        results_path = output / "results.jsonl"
        retrieval_count = 0
        retrieval_success = 0
        native_attempted = 0
        native_success = 0
        rows: list[dict[str, Any]] = []
        with results_path.open("w", encoding="utf-8") as results_file:
            for ordinal, question in enumerate(self.fixture.questions, start=1):
                row: dict[str, Any] = {"ordinal": ordinal, "question_id": question.question_id, "query_index": question.query_index, "question": question.question, "gold_answer": question.answer, "file_id": question.file_id, "doc_name": question.doc_name, "page_ids": question.page_ids, "provider": provider_name}
                try:
                    retrieval = self.retrieve(client, provider, dataset_key, dataset_id, question.question, ordinal)
                    hits = extract_hits(retrieval, "dify" if self.system == "dify_local" else "fastgpt")
                    row["retrieval"] = {"status": "success" if hits else "empty", "hit_count": len(hits), **score_retrieval(question, hits)}
                    retrieval_count += 1
                    retrieval_success += bool(hits)
                except ProviderFailure:
                    raise
                except EvalError as exc:
                    row["retrieval"] = {"status": "error", "error": str(exc)}
                if not self.args.skip_native and not self.native_disabled_reason:
                    native_attempted += 1
                    try:
                        native_payload = self.native(client, provider, app_key, app_id, question.question, ordinal)
                        answer = answer_from(native_payload)
                        normalized_answer = normalize(answer)
                        normalized_gold = normalize(question.answer)
                        row["native"] = {
                            "status": "success" if answer else "empty",
                            "answer": answer,
                            "answer_contains_gold": bool(normalized_gold and normalized_gold in normalized_answer),
                            "answer_exact_match_normalized": bool(normalized_gold and normalized_gold == normalized_answer),
                        }
                        native_success += bool(answer)
                    except ProviderFailure:
                        raise
                    except ProviderUnavailable as exc:
                        row["native"] = {"status": "unsupported", "error": str(exc)}
                        self.native_disabled_reason = str(exc)
                    except EvalError as exc:
                        row["native"] = {"status": "error", "error": str(exc)}
                        if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                            self.native_disabled_reason = f"disabled_after_timeout: {exc}"
                else:
                    row["native"] = {"status": "skipped", "reason": self.native_disabled_reason or "--skip-native"}
                results_file.write(json.dumps(redact(row), ensure_ascii=False) + "\n")
                results_file.flush()
                rows.append(row)
                if ordinal == 1 or ordinal == len(self.fixture.questions) or ordinal % self.args.progress_every == 0:
                    self.progress.emit("evaluation", "question progress", system_id=self.system_id, provider=provider_name, completed=ordinal, total=len(self.fixture.questions), retrieval_success=retrieval_success, native_success=native_success, native_disabled=bool(self.native_disabled_reason))
        encoded = results_path.read_bytes()
        results_path.with_suffix(".jsonl.sha256").write_text(f"{sha256_bytes(encoded)}  {results_path.name}\n", encoding="utf-8")
        metrics = self.metrics(rows, provider_name, dataset_id, index_state, retrieval_count, retrieval_success, native_attempted, native_success)
        json_dump(output / "metrics.json", metrics)
        json_dump(output / "attempt-summary.json", {"provider": provider_name, "dataset_id": dataset_id, "upload_count": len(upload_ids), "index_state": index_state, "metrics": metrics, "native_disabled_reason": self.native_disabled_reason})
        return {"provider": provider_name, "dataset_id": dataset_id, "output": str(output.relative_to(ROOT)), "metrics": metrics}

    def run_attempt(self, provider_name: str) -> dict[str, Any]:
        provider = self.providers[provider_name]
        self.current_provider = provider_name
        base_url, dataset_key, app_key, app_id = self.base_url_and_keys(provider)
        if not dataset_key:
            raise EvalError(f"{self.system.upper()}_DATASET_API_KEY_MISSING")
        output = self.root / f"attempt-{provider_name}"
        output.mkdir(parents=True, exist_ok=True)
        client = ArtifactHTTP(base_url, output, self.progress, timeout=self.args.query_timeout)
        self.status(status="running", provider=provider_name, attempt=str(output.relative_to(ROOT)))
        self.progress.emit("service", "checking local service", system_id=self.system_id, provider=provider_name)
        self.wait_service(client, provider)
        self.ensure_provider(provider, client, dataset_key)
        dataset_id = self.create_dataset(client, provider, dataset_key)
        self.progress.emit("ingest", "dataset created", system_id=self.system_id, provider=provider_name, dataset_id=dataset_id)
        upload_ids = self.upload_documents(client, provider, dataset_key, dataset_id)
        index_state = self.wait_index(client, provider, dataset_key, dataset_id, upload_ids)
        self.progress.emit("evaluation", "index ready; starting questions", system_id=self.system_id, provider=provider_name, questions=len(self.fixture.questions), dataset_id=dataset_id)
        binding: DifyNativeDatasetBinding | None = None
        try:
            if self.native_binding_enabled and provider_name == "taas" and not self.args.skip_native:
                if not app_id:
                    raise ProviderUnavailable("DIFY_NATIVE_APP_ID_MISSING_FOR_DATASET_BINDING")
                binding = DifyNativeDatasetBinding(self.platform_env, app_id, self.progress)
                binding.bind(dataset_id, output)
            return self._evaluate_attempt(provider_name, provider, client, dataset_key, app_key, app_id, dataset_id, output, upload_ids, index_state)
        finally:
            if binding is not None and binding.old_config is not None:
                binding.restore(output)

    def metrics(self, rows: list[dict[str, Any]], provider: str, dataset_id: str, index_state: dict[str, Any], retrieval_count: int, retrieval_success: int, native_attempted: int, native_success: int) -> dict[str, Any]:
        def avg(name: str) -> float | None:
            values: list[float] = []
            for row in rows:
                retrieval = row.get("retrieval", {})
                if retrieval.get("status") not in {"success", "empty"}:
                    continue
                value = retrieval.get(name)
                if name.startswith("page_fraction_recall_at_") and value is not None:
                    values.append(float(value))
                else:
                    values.append(1.0 if value else 0.0)
            return sum(values) / len(values) if values else None
        native_rows = [row.get("native", {}) for row in rows if row.get("native", {}).get("status") == "success"]
        native_contains = [1.0 if row.get("answer_contains_gold") else 0.0 for row in native_rows]
        native_exact = [1.0 if row.get("answer_exact_match_normalized") else 0.0 for row in native_rows]
        return {
            "protocol": "adapted_mmdocir_page_file_retrieval",
            "provider": provider,
            "dataset_id": dataset_id,
            "questions": len(rows),
            "retrieval_attempted": retrieval_count,
            "retrieval_nonempty": retrieval_success,
            "retrieval_nonempty_rate": retrieval_success / retrieval_count if retrieval_count else None,
            "page_recall_at_1": avg("page_recall_at_1"),
            "page_recall_at_3": avg("page_recall_at_3"),
            "page_recall_at_5": avg("page_recall_at_5"),
            "page_recall_at_10": avg("page_recall_at_10"),
            "page_fraction_recall_at_1": avg("page_fraction_recall_at_1"),
            "page_fraction_recall_at_3": avg("page_fraction_recall_at_3"),
            "page_fraction_recall_at_5": avg("page_fraction_recall_at_5"),
            "page_fraction_recall_at_10": avg("page_fraction_recall_at_10"),
            "document_recall_at_1": avg("document_recall_at_1"),
            "document_recall_at_3": avg("document_recall_at_3"),
            "document_recall_at_5": avg("document_recall_at_5"),
            "document_recall_at_10": avg("document_recall_at_10"),
            "native_attempted": native_attempted,
            "native_nonempty": native_success,
            "native_nonempty_rate": native_success / native_attempted if native_attempted else None,
            "native_answer_contains_gold_count": int(sum(native_contains)),
            "native_answer_contains_gold_rate": sum(native_contains) / len(native_contains) if native_contains else None,
            "native_answer_exact_match_normalized_count": int(sum(native_exact)),
            "native_answer_exact_match_normalized_rate": sum(native_exact) / len(native_exact) if native_exact else None,
            "index_state": index_state,
            "citation_policy": "raw vendor fields only; no citation inferred from answer text",
        }

    def run(self) -> dict[str, Any]:
        try:
            self.setup()
            initial = "maas" if self.args.provider == "auto" else self.args.provider
            try:
                attempt = self.run_attempt(initial)
                self.attempts.append(attempt)
            except ProviderFailure as exc:
                failure = {"provider": initial, "error": str(exc), "fallback_considered": True}
                json_dump(self.root / f"attempt-{initial}" / "provider-failure.json", failure)
                self.progress.emit("provider", "cloud provider-like failure detected", provider=initial, error=str(exc)[:500])
                if initial != "taas" or not self.provider_probe.get("ready"):
                    raise
                try:
                    fallback = self.run_attempt("qianfan")
                    self.attempts.append(fallback)
                    self.progress.emit("provider", "Qianfan fallback attempt finished", provider="qianfan")
                except ProviderUnavailable as fallback_exc:
                    failure["fallback_error"] = str(fallback_exc)
                    json_dump(self.root / "provider-fallback-blocked.json", failure)
                    raise EvalError(f"{exc}; Qianfan fallback blocked: {fallback_exc}") from fallback_exc
            summary = {
                "status": "success" if self.attempts and all(attempt["metrics"]["retrieval_nonempty_rate"] is not None for attempt in self.attempts) else "partial",
                "system_id": self.system_id,
                "deployment_mode": "self_hosted",
                "condition": self.args.condition,
                "phase": self.args.phase,
                "run_id": self.run_id,
                "attempts": self.attempts,
                "qianfan_probe": self.provider_probe,
                "artifacts_root": str(self.root.relative_to(ROOT)),
            }
            json_dump(self.root / "summary.json", summary)
            self.status(status=summary["status"], completed=True, attempts=len(self.attempts))
            self.progress.emit("complete", "evaluation finished", system_id=self.system_id, status=summary["status"], attempts=len(self.attempts))
            return summary
        except Exception as exc:
            summary = {"status": "error", "system_id": self.system_id, "run_id": self.run_id, "error": str(exc), "attempts": self.attempts, "artifacts_root": str(self.root.relative_to(ROOT))}
            json_dump(self.root / "summary.json", summary)
            self.status(status="error", completed=True, error=str(exc))
            self.progress.emit("error", "evaluation stopped", system_id=self.system_id, error=str(exc)[:800])
            return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=("dify_local", "fastgpt_local"), required=True)
    parser.add_argument("--prepared-root", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--condition", default="page")
    parser.add_argument("--phase", choices=("pilot", "full"), default="pilot")
    parser.add_argument("--provider", choices=("auto", "taas", "maas", "qianfan", "local_bge"), default="auto")
    parser.add_argument("--documents-limit", type=int, default=20, help="0 means all documents")
    parser.add_argument("--questions-limit", type=int, default=0, help="0 means all questions in the selected documents")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--skip-native", action="store_true")
    parser.add_argument(
        "--bind-dify-native-dataset",
        action="store_true",
        help="temporarily bind the configured Dify chat app to this run's dataset and restore it afterward",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--progress-path", type=Path, default=ACTIVE_PROGRESS)
    parser.add_argument("--startup-wait", type=int, default=300)
    parser.add_argument("--index-wait", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument("--upload-timeout", type=int, default=300)
    parser.add_argument("--query-timeout", type=int, default=120)
    parser.add_argument("--native-timeout", type=int, default=120)
    parser.add_argument("--progress-every", type=int, default=10)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.phase == "full" and args.documents_limit == 20:
        args.documents_limit = 0
    result = CompetitorRun(args).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
