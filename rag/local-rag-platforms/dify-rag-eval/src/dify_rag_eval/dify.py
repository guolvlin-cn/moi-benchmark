from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Config


@dataclass
class DifyResponse:
    answer: str
    contexts: list[dict[str, Any]]
    usage: dict[str, Any]
    ids: dict[str, Any]
    raw: dict[str, Any]


def get_path(value: Any, path: str, default: Any = None) -> Any:
    current = value
    for part in path.split("."):
        if not part:
            continue
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def normalize_contexts(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        return [{"content": value}]
    if isinstance(value, dict):
        value = value.get("result") or value.get("records") or [value]
    if not isinstance(value, list):
        return [{"content": str(value)}]
    contexts: list[dict[str, Any]] = []
    for position, item in enumerate(value, 1):
        if isinstance(item, str):
            contexts.append({"position": position, "content": item})
        elif isinstance(item, dict):
            normalized = dict(item)
            normalized.setdefault("position", position)
            normalized.setdefault(
                "content",
                item.get("text") or item.get("page_content") or item.get("content") or "",
            )
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                for key in ("document_id", "document_name", "dataset_id", "score"):
                    normalized.setdefault(key, metadata.get(key))
            contexts.append(normalized)
        else:
            contexts.append({"position": position, "content": str(item)})
    return contexts


class DifyClient:
    def __init__(self, config: Config, api_key: str):
        self.config = config
        self.api_key = api_key

    def query(
        self, question: str, *, case_id: str, repeat: int, case_inputs: dict[str, Any]
    ) -> DifyResponse:
        inputs = {**self.config.inputs, **case_inputs}
        user = f"{self.config.user_prefix}-{case_id}-r{repeat}"
        if self.config.app_type == "chat":
            endpoint = "/chat-messages"
            payload = {
                "inputs": inputs,
                "query": question,
                "response_mode": "blocking",
                "conversation_id": "",
                "user": user,
            }
        else:
            endpoint = "/workflows/run"
            inputs[self.config.workflow.query_input] = question
            payload = {"inputs": inputs, "response_mode": "blocking", "user": user}

        raw = self._post(endpoint, payload)
        if self.config.app_type == "chat":
            metadata = raw.get("metadata") or {}
            return DifyResponse(
                answer=str(raw.get("answer") or ""),
                contexts=normalize_contexts(metadata.get("retriever_resources")),
                usage=metadata.get("usage") or {},
                ids={
                    "task_id": raw.get("task_id"),
                    "message_id": raw.get("message_id"),
                    "conversation_id": raw.get("conversation_id"),
                },
                raw=raw,
            )

        data = raw.get("data") or {}
        status = data.get("status")
        if status and status != "succeeded":
            raise RuntimeError(
                f"Dify workflow ended with status={status}: {data.get('error') or 'no error detail'}"
            )
        answer = get_path(raw, self.config.workflow.answer_path, "")
        contexts = get_path(raw, self.config.workflow.contexts_path, [])
        return DifyResponse(
            answer=str(answer or ""),
            contexts=normalize_contexts(contexts),
            usage={
                "total_tokens": data.get("total_tokens"),
                "elapsed_time": data.get("elapsed_time"),
            },
            ids={
                "task_id": raw.get("task_id"),
                "workflow_run_id": raw.get("workflow_run_id") or data.get("id"),
            },
            raw=raw,
        )

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/") + endpoint
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Dify-RAG-Eval/0.1",
            },
        )
        for attempt in range(self.config.max_retries + 1):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.config.timeout_seconds
                ) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                message = exc.read().decode("utf-8", errors="replace")
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt >= self.config.max_retries:
                    raise RuntimeError(f"Dify HTTP {exc.code}: {message}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.config.max_retries:
                    raise RuntimeError(f"Dify request failed: {exc}") from exc
            delay = min(8.0, 0.5 * (2**attempt)) + random.uniform(0, 0.25)
            time.sleep(delay)
        raise AssertionError("unreachable")
