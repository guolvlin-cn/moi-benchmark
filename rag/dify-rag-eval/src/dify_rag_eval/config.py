from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowConfig:
    query_input: str = "query"
    answer_path: str = "data.outputs.answer"
    contexts_path: str = "data.outputs.contexts"


@dataclass(frozen=True)
class Config:
    base_url: str
    app_type: str = "chat"
    api_key_env: str = "DIFY_API_KEY"
    user_prefix: str = "dify-rag-eval"
    timeout_seconds: float = 120.0
    max_retries: int = 3
    concurrency: int = 2
    repeats: int = 1
    top_k: int = 5
    inputs: dict[str, Any] = field(default_factory=dict)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)


def load_config(path: str | Path) -> Config:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    workflow = WorkflowConfig(**raw.pop("workflow", {}))
    config = Config(workflow=workflow, **raw)
    if config.app_type not in {"chat", "workflow"}:
        raise ValueError("app_type must be 'chat' or 'workflow'")
    if config.concurrency < 1 or config.repeats < 1 or config.top_k < 1:
        raise ValueError("concurrency, repeats, and top_k must be positive")
    return config

