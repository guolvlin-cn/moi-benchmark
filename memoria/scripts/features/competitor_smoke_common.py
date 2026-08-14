#!/usr/bin/env python3
"""Mem0/Zep 重复记忆处理 Smoke 实验共用工具。"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


SMOKE_CASE_IDS = [
    "dmh-formal-001-exact-duplicate",
    "dmh-formal-009-exact-duplicate",
    "dmh-formal-011-semantic-equivalent",
    "dmh-formal-021-semantic-equivalent",
    "dmh-formal-035-independent-facts",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_smoke_cases(path: Path) -> list[dict[str, Any]]:
    cases = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            case = json.loads(raw)
            if case["case_id"] in SMOKE_CASE_IDS:
                cases[case["case_id"]] = case
    missing = set(SMOKE_CASE_IDS) - set(cases)
    if missing:
        raise ValueError(f"smoke cases missing from dataset: {sorted(missing)}")
    return [cases[case_id] for case_id in SMOKE_CASE_IDS]


def load_all_cases(path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]
    if len(cases) != 50 or len({case["case_id"] for case in cases}) != 50:
        raise ValueError("formal dataset must contain 50 unique cases")
    return cases


def store_operations(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [op for op in case["operations"] if op["op"] == "store_memory"]


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class JsonClient:
    def __init__(
        self,
        base_url: str,
        authorization: str,
        log_path: Path,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.authorization = authorization
        self.log_path = log_path
        self.timeout = timeout
        self.session = requests.Session()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expected: set[int] | None = None,
    ) -> tuple[int, Any, float]:
        expected = expected or {200}
        started = time.perf_counter()
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers={
                "Authorization": self.authorization,
                "Content-Type": "application/json",
            },
            json=json_body,
            params=params,
            timeout=self.timeout,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        append_jsonl(
            self.log_path,
            {
                "at": utc_now(),
                "method": method,
                "path": path,
                "params": params,
                "request_body": json_body,
                "status_code": response.status_code,
                "elapsed_ms": round(elapsed_ms, 3),
                "response_body": body,
            },
        )
        if response.status_code not in expected:
            raise RuntimeError(
                f"{method} {path} returned {response.status_code}: {str(body)[:1000]}"
            )
        return response.status_code, body, elapsed_ms
