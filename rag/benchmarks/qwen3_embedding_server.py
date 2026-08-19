#!/usr/bin/env python3
"""Minimal OpenAI-compatible server for the locally cached Qwen3 embedding model."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


MODEL_PATH = os.environ.get("QWEN3_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
MODEL_ID = "qwen3-embedding-0.6b"
model: SentenceTransformer | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global model
    model = SentenceTransformer(MODEL_PATH, local_files_only=True, device=os.environ.get("QWEN3_EMBEDDING_DEVICE", "mps"))
    yield


app = FastAPI(lifespan=lifespan)


class EmbeddingRequest(BaseModel):
    model: str | None = None
    input: str | list[str]
    encoding_format: str | None = "float"


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ready" if model is not None else "loading", "model": MODEL_ID}


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "local"}]}


@app.post("/v1/embeddings")
@app.post("/embeddings")
def embeddings(body: EmbeddingRequest) -> dict[str, Any]:
    if model is None:
        raise HTTPException(status_code=503, detail="model is not loaded")
    if body.model and body.model.casefold() not in {MODEL_ID, "qwen/qwen3-embedding-0.6b"}:
        raise HTTPException(status_code=400, detail=f"unsupported model {body.model}")
    texts = [body.input] if isinstance(body.input, str) else body.input
    if not texts or any(not text.strip() for text in texts):
        raise HTTPException(status_code=400, detail="input must contain non-empty text")
    # The historical MOI ingest sent raw strings to the provider without a
    # query/document prompt. Keep the local replacement on that exact path.
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": vector.tolist()}
            for index, vector in enumerate(vectors)
        ],
        "model": MODEL_ID,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }
