#!/usr/bin/env python3
"""Register and verify MaxKB's Qianfan OpenAI-compatible embedding model.

MaxKB's OpenAI embedding form exposes a small set of dimensions and can
silently add a ``dimensions`` parameter to a model credential.  Qianfan's
``qwen3-embedding-8b`` endpoint returns 4096 dimensions and must therefore be
registered with an empty ``model_params_form``.  This helper keeps that rule in
one MaxKB-local command without changing the shared evaluation runner.

The command never prints or writes provider credentials.  It only emits a
small manifest containing model identity, status, and the observed vector
dimension.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping


PLATFORM_ROOT = Path(__file__).resolve().parents[1]
ROOT = PLATFORM_ROOT.parent
if str(PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(PLATFORM_ROOT))
from env import inject_central_env  # noqa: E402

DEFAULT_MAXKB_BASE_URL = "http://127.0.0.1:8090"
DEFAULT_QIANFAN_BASE_URL = "https://qianfan.baidubce.com/v2"
DEFAULT_MODEL_NAME = "qwen3-embedding-8b"
DEFAULT_DIMENSION = 4096
MAXKB_OPENAI_PROVIDER = "model_openai_provider"
MAXKB_EMBEDDING_TYPE = "EMBEDDING"


class MaxKBQianfanError(RuntimeError):
    """A safe, user-facing configuration or contract error."""


def load_local_environment() -> None:
    """Load the repository-root .env without echoing its values."""

    inject_central_env()


def _required(value: str | None, name: str) -> str:
    value = str(value or "").strip()
    if not value or value.startswith("<"):
        raise MaxKBQianfanError(f"{name}_MISSING")
    return value


def _normalise_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _safe_model(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return only non-secret model metadata for manifests/stdout."""

    fields = (
        "id",
        "name",
        "model_name",
        "model_type",
        "provider",
        "status",
        "meta",
        "model_params_form",
        "workspace_id",
    )
    return {field: record.get(field) for field in fields if field in record}


def _list_records(payload: Any) -> list[dict[str, Any]]:
    data: Any = payload
    if isinstance(payload, Mapping):
        data = payload.get("data", payload)
    if isinstance(data, Mapping):
        data = data.get("list", data.get("results", []))
    if not isinstance(data, list):
        raise MaxKBQianfanError("MAXKB_MODEL_LIST_INVALID")
    return [dict(item) for item in data if isinstance(item, Mapping)]


def _model_params_are_empty(value: Any) -> bool:
    """Check that MaxKB will not send a dimensions override."""

    if value in (None, "", [], {}):
        return True
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return False
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, Mapping) and str(item.get("field", "")).casefold() == "dimensions":
            return False
    return True


def validate_model_record(
    record: Mapping[str, Any],
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    expected_provider: str = MAXKB_OPENAI_PROVIDER,
) -> dict[str, Any]:
    """Validate the exact MaxKB model contract used by the local runner."""

    model_id = str(record.get("id") or record.get("model_id") or "").strip()
    if not model_id:
        raise MaxKBQianfanError("MAXKB_QIANFAN_EMBEDDING_MODEL_ID_MISSING")
    actual_name = str(record.get("model_name") or "").strip()
    if actual_name.casefold() != model_name.casefold():
        raise MaxKBQianfanError(
            f"MAXKB_QIANFAN_EMBEDDING_MODEL_NAME_MISMATCH:{actual_name or 'empty'}"
        )
    actual_type = str(record.get("model_type") or "").strip().upper()
    if actual_type != MAXKB_EMBEDDING_TYPE:
        raise MaxKBQianfanError(f"MAXKB_QIANFAN_EMBEDDING_TYPE_MISMATCH:{actual_type or 'empty'}")
    provider = str(record.get("provider") or "").strip()
    if provider != expected_provider:
        raise MaxKBQianfanError(f"MAXKB_QIANFAN_EMBEDDING_PROVIDER_MISMATCH:{provider or 'empty'}")
    status = str(record.get("status") or "").strip().upper()
    if status and status not in {"SUCCESS", "READY", "AVAILABLE"}:
        raise MaxKBQianfanError(f"MAXKB_QIANFAN_EMBEDDING_STATUS:{status}")
    if not _model_params_are_empty(record.get("model_params_form")):
        raise MaxKBQianfanError("MAXKB_QIANFAN_EMBEDDING_DIMENSIONS_OVERRIDE_PRESENT")
    return _safe_model(record)


def choose_model(
    records: Iterable[Mapping[str, Any]],
    *,
    model_id: str | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, Any]:
    """Select one Qianfan OpenAI embedding record without guessing."""

    candidates = [
        dict(record)
        for record in records
        if isinstance(record, Mapping)
        and str(record.get("model_type") or "").strip().upper() == MAXKB_EMBEDDING_TYPE
        and str(record.get("provider") or "").strip() == MAXKB_OPENAI_PROVIDER
    ]
    if model_id:
        selected = next(
            (item for item in candidates if str(item.get("id") or item.get("model_id") or "") == model_id),
            None,
        )
        if selected is None:
            raise MaxKBQianfanError(f"MAXKB_QIANFAN_EMBEDDING_MODEL_ID_NOT_FOUND:{model_id}")
        return selected
    exact = [
        item
        for item in candidates
        if str(item.get("model_name") or "").strip().casefold() == model_name.casefold()
    ]
    ready = [item for item in exact if str(item.get("status") or "").strip().upper() in {"", "SUCCESS", "READY", "AVAILABLE"}]
    if len(ready) == 1:
        return ready[0]
    if len(ready) > 1:
        raise MaxKBQianfanError("MAXKB_QIANFAN_EMBEDDING_MODEL_AMBIGUOUS_SET_MODEL_ID")
    if exact:
        return exact[0]
    raise MaxKBQianfanError(f"MAXKB_QIANFAN_EMBEDDING_MODEL_NOT_REGISTERED:{model_name}")


class JsonHttpClient:
    """Tiny dependency-free JSON client used by this MaxKB-local tool."""

    def __init__(self, base_url: str, *, api_key: str | None = None, timeout: float = 60.0):
        self.base_url = _normalise_url(base_url)
        self.api_key = api_key
        self.timeout = timeout

    def request(self, method: str, path: str, *, body: Any = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            # Do not include the body: provider/API errors can echo credential
            # fields.  The status is sufficient for a safe diagnosis here.
            raise MaxKBQianfanError(f"HTTP_{exc.code}:{method.upper()}:{path}") from exc
        except urllib.error.URLError as exc:
            raise MaxKBQianfanError(f"URL_ERROR:{method.upper()}:{path}") from exc

        if status < 200 or status >= 300:
            raise MaxKBQianfanError(f"HTTP_{status}:{method.upper()}:{path}")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MaxKBQianfanError(f"JSON_INVALID:{method.upper()}:{path}") from exc
        if isinstance(payload, Mapping) and "code" in payload:
            code = payload.get("code")
            if code not in (200, "200", 0, "0", None):
                message = str(payload.get("message") or "api_error")[:180]
                raise MaxKBQianfanError(f"API_{code}:{message}")
        return payload


class QianfanClient(JsonHttpClient):
    def embed(self, *, model: str, text: str) -> dict[str, Any]:
        payload = self.request(
            "POST",
            "/embeddings",
            body={"model": model, "input": [text]},
        )
        data = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], Mapping):
            raise MaxKBQianfanError("QIANFAN_EMBEDDING_RESPONSE_INVALID")
        vector = data[0].get("embedding")
        if not isinstance(vector, list) or not vector:
            raise MaxKBQianfanError("QIANFAN_EMBEDDING_VECTOR_MISSING")
        return {
            "vector_dimension": len(vector),
            "vector_count": len(data),
            "usage_total_tokens": (payload.get("usage") or {}).get("total_tokens")
            if isinstance(payload.get("usage"), Mapping)
            else None,
        }


def _admin_client() -> JsonHttpClient:
    base = os.getenv("MAXKB_ADMIN_BASE_URL", "").strip()
    if not base:
        base = f"{_normalise_url(os.getenv('MAXKB_BASE_URL', DEFAULT_MAXKB_BASE_URL))}/admin/api"
    token = os.getenv("MAXKB_ADMIN_TOKEN", "").strip()
    if not token:
        token_file = Path(
            os.getenv(
                "MAXKB_ADMIN_TOKEN_FILE",
                str(ROOT / ".local-services/maxkb_local/secrets/admin.token"),
            )
        )
        if not token_file.is_file():
            raise MaxKBQianfanError("MAXKB_ADMIN_TOKEN_MISSING")
        token = token_file.read_text(encoding="utf-8", errors="replace").strip()
    token = _required(token, "MAXKB_ADMIN_TOKEN")
    return JsonHttpClient(base, api_key=token)


def _qianfan_client() -> QianfanClient:
    base = _normalise_url(os.getenv("QIANFAN_BASE_URL", DEFAULT_QIANFAN_BASE_URL))
    key = _required(os.getenv("QIANFAN_API_KEY"), "QIANFAN_API_KEY")
    return QianfanClient(base, api_key=key)


def qianfan_probe(
    client: QianfanClient,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    expected_dimension: int = DEFAULT_DIMENSION,
) -> dict[str, Any]:
    result = client.embed(
        model=model_name,
        text="MaxKB local embedding contract probe. Return one dense vector.",
    )
    actual = int(result["vector_dimension"])
    if actual != expected_dimension:
        raise MaxKBQianfanError(
            f"QIANFAN_EMBEDDING_DIMENSION_MISMATCH:expected={expected_dimension}:actual={actual}"
        )
    return {
        "provider": "qianfan",
        "model": model_name,
        "expected_dimension": expected_dimension,
        "observed_dimension": actual,
        "request_dimensions": "omitted",
        "vector_count": result["vector_count"],
        "usage_total_tokens": result.get("usage_total_tokens"),
        "status": "ready",
    }


def _model_list(client: JsonHttpClient) -> list[dict[str, Any]]:
    return _list_records(client.request("GET", "/workspace/default/model"))


def verify_registration(
    admin: JsonHttpClient,
    qianfan: QianfanClient | None = None,
    *,
    model_id: str | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    expected_dimension: int = DEFAULT_DIMENSION,
    probe_provider: bool = True,
) -> dict[str, Any]:
    records = _model_list(admin)
    selected = choose_model(records, model_id=model_id, model_name=model_name)
    safe = validate_model_record(selected, model_name=model_name)
    result: dict[str, Any] = {
        "status": "ready",
        "maxkb_model": safe,
        "maxkb_model_id": safe["id"],
        "model_name": model_name,
        "expected_dimension": expected_dimension,
        "maxkb_model_params_form": "empty",
        "dataset_create_embedding_model_id": safe["id"],
        "provider": "qianfan",
    }
    if probe_provider:
        if qianfan is None:
            qianfan = _qianfan_client()
        result["provider_probe"] = qianfan_probe(
            qianfan,
            model_name=model_name,
            expected_dimension=expected_dimension,
        )
    else:
        result["provider_probe"] = {"status": "skipped"}
    return result


def _registration_payload(
    *,
    model_name: str,
    model_label: str,
    qianfan_base_url: str,
    qianfan_api_key: str,
) -> dict[str, Any]:
    # Deliberately empty: MaxKB's generic OpenAI form does not offer 4096 in
    # this release and any dimensions field would override Qianfan's native
    # 4096-dimensional response.
    return {
        "name": model_label,
        "model_type": MAXKB_EMBEDDING_TYPE,
        "model_name": model_name,
        "model_params_form": [],
        "credential": {"api_base": _normalise_url(qianfan_base_url), "api_key": qianfan_api_key},
        "provider": MAXKB_OPENAI_PROVIDER,
    }


def register_embedding(
    admin: JsonHttpClient,
    qianfan: QianfanClient | None = None,
    *,
    model_id: str | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    expected_dimension: int = DEFAULT_DIMENSION,
    model_label: str | None = None,
    execute: bool = False,
    probe_provider: bool = True,
) -> dict[str, Any]:
    if not execute:
        raise MaxKBQianfanError("REGISTER_REQUIRES_EXECUTE")
    if qianfan is None:
        qianfan = _qianfan_client()
    provider_probe = (
        qianfan_probe(qianfan, model_name=model_name, expected_dimension=expected_dimension)
        if probe_provider
        else {"status": "skipped"}
    )
    records = _model_list(admin)
    try:
        existing = choose_model(records, model_id=model_id, model_name=model_name)
    except MaxKBQianfanError as exc:
        if not str(exc).startswith("MAXKB_QIANFAN_EMBEDDING_MODEL_NOT_REGISTERED:") or model_id:
            raise
        existing = None
    if existing is not None:
        verified = validate_model_record(existing, model_name=model_name)
        return {
            "status": "already_registered",
            "maxkb_model": verified,
            "maxkb_model_id": verified["id"],
            "provider_probe": provider_probe,
            "dataset_create_embedding_model_id": verified["id"],
            "registration_payload": {"model_params_form": [], "provider": MAXKB_OPENAI_PROVIDER},
        }

    api_key = _required(os.getenv("QIANFAN_API_KEY"), "QIANFAN_API_KEY")
    base_url = _normalise_url(os.getenv("QIANFAN_BASE_URL", DEFAULT_QIANFAN_BASE_URL))
    payload = _registration_payload(
        model_name=model_name,
        model_label=model_label or f"Qianfan {model_name} ({expected_dimension}d)",
        qianfan_base_url=base_url,
        qianfan_api_key=api_key,
    )
    created_payload = admin.request("POST", "/workspace/default/model", body=payload)
    created_records = _list_records(created_payload.get("data") if isinstance(created_payload, Mapping) else created_payload)
    created = created_records[0] if created_records else (created_payload.get("data") if isinstance(created_payload, Mapping) else None)
    if not isinstance(created, Mapping):
        raise MaxKBQianfanError("MAXKB_QIANFAN_EMBEDDING_CREATE_RESPONSE_INVALID")
    verified = validate_model_record(created, model_name=model_name)
    return {
        "status": "registered",
        "maxkb_model": verified,
        "maxkb_model_id": verified["id"],
        "provider_probe": provider_probe,
        "dataset_create_embedding_model_id": verified["id"],
        "registration_payload": {"model_params_form": [], "provider": MAXKB_OPENAI_PROVIDER},
    }


def _write_output(value: Mapping[str, Any], path: str | None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        try:
            output.chmod(0o600)
        except OSError:
            pass
    print(text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "register", "list"))
    parser.add_argument("--model-id", default=os.getenv("MAXKB_EMBEDDING_MODEL_ID", ""))
    parser.add_argument(
        "--model-name",
        default=os.getenv(
            "MAXKB_EMBEDDING_MODEL_NAME",
            os.getenv("QIANFAN_EMBEDDING_MODEL", DEFAULT_MODEL_NAME),
        ),
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=int(
            os.getenv(
                "MAXKB_EMBEDDING_DIMENSION",
                os.getenv("QIANFAN_EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION)),
            )
        ),
    )
    parser.add_argument("--model-label", default=os.getenv("MAXKB_EMBEDDING_REGISTER_NAME", ""))
    parser.add_argument("--skip-provider-probe", action="store_true")
    parser.add_argument("--execute", action="store_true", help="required for register; performs a MaxKB write")
    parser.add_argument("--output", help="optional safe JSON manifest path")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_local_environment()
    args = _parser().parse_args(argv)
    try:
        admin = _admin_client()
        if args.command == "list":
            records = _model_list(admin)
            _write_output(
                {
                    "status": "ready",
                    "embedding_models": [
                        _safe_model(item)
                        for item in records
                        if str(item.get("model_type") or "").upper() == MAXKB_EMBEDDING_TYPE
                    ],
                },
                args.output,
            )
            return 0
        qianfan = None if args.skip_provider_probe else _qianfan_client()
        if args.command == "verify":
            result = verify_registration(
                admin,
                qianfan,
                model_id=args.model_id or None,
                model_name=args.model_name,
                expected_dimension=args.dimension,
                probe_provider=not args.skip_provider_probe,
            )
        else:
            result = register_embedding(
                admin,
                qianfan,
                model_id=args.model_id or None,
                model_name=args.model_name,
                expected_dimension=args.dimension,
                model_label=args.model_label or None,
                execute=args.execute,
                probe_provider=not args.skip_provider_probe,
            )
        _write_output(result, args.output)
        return 0
    except MaxKBQianfanError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
