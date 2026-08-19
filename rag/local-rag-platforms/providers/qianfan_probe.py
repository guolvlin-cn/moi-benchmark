#!/usr/bin/env python3
"""Credential-safe smoke probe for Qianfan's OpenAI-compatible V2 API."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PLATFORM_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLATFORM_ROOT.parent
if str(PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(PLATFORM_ROOT))
from env import inject_central_env  # noqa: E402


DEFAULT_BASE_URL = "https://qianfan.baidubce.com/v2"
DEFAULT_LLM = "deepseek-v4-flash"
DEFAULT_EMBEDDING = "qwen3-embedding-8b"
DEFAULT_RERANKER = "qwen3-reranker-8b"


class ProbeError(RuntimeError):
    pass


def request_json(
    base_url: str,
    path: str,
    api_key: str,
    timeout: float,
    *,
    body: dict[str, Any] | None = None,
    appid: str = "",
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MOI-RAG-Qianfan-Probe/0.1",
    }
    if appid:
        headers["appid"] = appid
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
        method="POST" if body is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise ProbeError(f"{path} returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise ProbeError(f"{path} is unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProbeError(f"{path} returned invalid JSON") from exc
    return payload


def validate_embedding(payload: dict[str, Any], expected_dimension: int) -> int:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ProbeError("embedding response has no data")
    vector = data[0].get("embedding") if isinstance(data[0], dict) else None
    if not isinstance(vector, list) or not vector:
        raise ProbeError("embedding response has no vector")
    if expected_dimension and len(vector) != expected_dimension:
        raise ProbeError(f"embedding dimension is {len(vector)}, expected {expected_dimension}")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
        raise ProbeError("embedding contains a non-finite or non-numeric value")
    return len(vector)


def validate_chat(payload: dict[str, Any]) -> bool:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProbeError("chat response has no choices")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    if not str(message.get("content") or "").strip():
        raise ProbeError("chat response has no content")
    return True


def validate_models(payload: dict[str, Any], llm: str, embedding: str, reranker: str) -> dict[str, str]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ProbeError("models response has no data list")
    by_id = {str(item.get("id")): item for item in data if isinstance(item, dict) and item.get("id")}
    missing = [model for model in (llm, embedding, reranker) if model not in by_id]
    if missing:
        raise ProbeError(f"models are not available to this key: {', '.join(missing)}")
    return {model: str(by_id[model].get("type") or "unknown") for model in (llm, embedding, reranker)}


def validate_rerank(payload: dict[str, Any]) -> int:
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise ProbeError("rerank response has no results")
    return len(results)


def main() -> int:
    inject_central_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="send one embedding and one chat request")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()

    base_url = os.getenv("QIANFAN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    llm = os.getenv("QIANFAN_LLM_MODEL", DEFAULT_LLM)
    embedding = os.getenv("QIANFAN_EMBEDDING_MODEL", DEFAULT_EMBEDDING)
    reranker = os.getenv("QIANFAN_RERANKER_MODEL", DEFAULT_RERANKER)
    dimension = int(os.getenv("QIANFAN_EMBEDDING_DIMENSION", "4096"))
    appid = os.getenv("QIANFAN_APPID", "").strip()
    key = os.getenv("QIANFAN_API_KEY", "").strip()
    summary: dict[str, Any] = {
        "provider": "baidu_qianfan_v2",
        "protocol": "openai_compatible",
        "base_url": base_url,
        "llm_model": llm,
        "embedding_model": embedding,
        "reranker_model": reranker,
        "expected_embedding_dimension": dimension,
        "api_key_loaded": bool(key and not key.startswith("<")),
        "executed": args.execute,
    }
    if not args.execute:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if not summary["api_key_loaded"]:
        raise ProbeError("QIANFAN_API_KEY is required for --execute")

    models_response = request_json(base_url, "/models", key, args.timeout, appid=appid)
    embedding_response = request_json(
        base_url,
        "/embeddings",
        key,
        args.timeout,
        body={"model": embedding, "input": ["MOI RAG provider health check"], "encoding_format": "float"},
        appid=appid,
    )
    chat_response = request_json(
        base_url,
        "/chat/completions",
        key,
        args.timeout,
        body={
            "model": llm,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "stream": False,
            "max_tokens": 8,
            "temperature": 0,
        },
        appid=appid,
    )
    rerank_response = request_json(
        base_url,
        "/rerank",
        key,
        args.timeout,
        body={
            "model": reranker,
            "query": "local RAG provider health check",
            "documents": ["provider health check", "unrelated text"],
            "top_n": 2,
        },
        appid=appid,
    )
    summary.update({
        "models": {"status": "success", "types": validate_models(models_response, llm, embedding, reranker)},
        "embedding": {"status": "success", "dimension": validate_embedding(embedding_response, dimension)},
        "chat": {"status": "success" if validate_chat(chat_response) else "error"},
        "rerank": {"status": "success", "result_count": validate_rerank(rerank_response)},
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProbeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
