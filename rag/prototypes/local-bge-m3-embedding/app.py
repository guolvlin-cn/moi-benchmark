"""OpenAI-compatible local BGE-M3 embedding service.

Run with::

    uv run uvicorn app:app --host 127.0.0.1 --port 8081

The service intentionally exposes only dense BGE-M3 vectors because the
current MatrixFlow/MOI vector writer stores one VECF64 embedding per chunk.
"""

from __future__ import annotations

import hmac
import logging
import time
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from engine import (
    EmbeddingEngine,
    EmbeddingInputError,
    EmbeddingOutputError,
    ModelUnavailableError,
    Settings,
    estimate_prompt_tokens,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("local-bge-m3")

settings = Settings.from_env()
engine = EmbeddingEngine(settings)
app = FastAPI(
    title="Local BGE-M3 Embedding Service",
    version="0.1.0",
    description="OpenAI-compatible dense embeddings backed by FlagEmbedding's BGE-M3 model.",
)


class EmbeddingRequest(BaseModel):
    model: Optional[str] = Field(default=None)
    input: Union[str, List[str]]
    encoding_format: Optional[str] = Field(default="float")


def _error(message: str, status_code: int, error_type: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type}},
    )


def _authorized(request: Request) -> bool:
    expected = settings.api_key
    if not expected:
        return True
    header = request.headers.get("authorization", "")
    scheme, separator, token = header.partition(" ")
    return bool(separator) and scheme.lower() == "bearer" and hmac.compare_digest(
        token.strip(), expected
    )


def _model_matches(requested: Optional[str]) -> bool:
    if not requested or not requested.strip():
        return True
    normalized = requested.strip().lower()
    aliases = {
        settings.model_id.lower(),
        settings.model_source.lower(),
        "bge-m3",
        "baai/bge-m3",
    }
    return normalized in aliases


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "local-bge-m3-embedding",
        "protocol": "openai-embeddings",
        "embedding_path": "/v1/embeddings",
        "health_path": "/healthz",
        "model": settings.model_id,
    }


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    """Liveness endpoint; lazy mode does not download model weights here."""

    return engine.status()


@app.get("/readyz", response_model=None)
def readyz() -> Union[Dict[str, Any], JSONResponse]:
    if not engine.loaded:
        return JSONResponse(status_code=503, content=engine.status())
    return engine.status()


@app.get("/v1/models", response_model=None)
@app.get("/models", response_model=None)
def models(request: Request) -> Union[Dict[str, Any], JSONResponse]:
    if not _authorized(request):
        return _error("invalid or missing bearer token", 401, "authentication_error")
    return {
        "object": "list",
        "data": [
            {
                "id": settings.model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local",
            }
        ],
    }


def embeddings(request: Request, body: EmbeddingRequest) -> Union[Dict[str, Any], JSONResponse]:
    if not _authorized(request):
        return _error("invalid or missing bearer token", 401, "authentication_error")
    if not _model_matches(body.model):
        return _error(
            f"model {body.model!r} is not served; use {settings.model_id!r}",
            400,
        )
    if body.encoding_format not in (None, "float"):
        return _error("only encoding_format='float' is supported", 400)

    try:
        vectors = engine.embed(body.input)
    except EmbeddingInputError as exc:
        return _error(str(exc), 400)
    except (ModelUnavailableError, EmbeddingOutputError) as exc:
        LOGGER.error("embedding request failed: %s", exc)
        return _error(str(exc), 503, "server_error")

    if isinstance(body.input, str):
        texts = [body.input]
    else:
        texts = body.input
    prompt_tokens = estimate_prompt_tokens(texts)
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "embedding": vector,
                "index": index,
            }
            for index, vector in enumerate(vectors)
        ],
        "model": settings.model_id,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "total_tokens": prompt_tokens,
        },
    }


# Keep both routes: the RAG client uses base_url + /embeddings, while /v1 is
# the conventional OpenAI base URL used by curl and other clients.
app.add_api_route("/v1/embeddings", embeddings, methods=["POST"], response_model=None)
app.add_api_route("/embeddings", embeddings, methods=["POST"], response_model=None)


@app.on_event("startup")
def eager_load_model() -> None:
    if settings.lazy_load:
        LOGGER.info(
            "BGE-M3 service started in lazy-load mode model=%s device=%s",
            settings.model_id,
            settings.device,
        )
        return
    LOGGER.info("loading BGE-M3 model at startup: %s", settings.model_source)
    engine.load()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
