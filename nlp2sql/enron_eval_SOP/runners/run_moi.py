#!/usr/bin/env python3
"""Batch-run Enron NL2SQL questions against a local MOI knowledge base.

Credentials come from MOI_EMAIL and MOI_PASSWORD and are never stored in run
artifacts. Each attempt gets an isolated fixed-knowledge session. Besides SQL,
the runner captures MOI's native MatrixOne query results and LLM usage events.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlencode, urlparse

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*")
import requests

DEFAULT_WORKSPACE_ID = "405e1cb4-6097-4cbd-770f-9fd14ad58184"
DEFAULT_BASE_URL = "http://localhost:18002"
DEFAULT_UC_URL = "http://127.0.0.1:19080"
DEFAULT_KNOWLEDGE_NAME = "邮件问答-baseline-qwen37"
DEFAULT_MODEL = "qwen3.7-plus-2026-05-26"
DEFAULT_QUESTIONS = Path("benchmark/questions/user/questions_enron_50_user_mix.txt")


class MoiError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def compact_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def unwrap(body: Any, operation: str) -> Any:
    if not isinstance(body, dict):
        raise MoiError(f"{operation}: malformed response")
    code = body.get("code")
    if code and code not in {"OK", "Success", "success"}:
        raise MoiError(f"{operation}: {body.get('message') or body.get('msg') or code}")
    return body.get("data", body)


class MoiClient:
    def __init__(self, base_url: str, uc_url: str, workspace_id: str, timeout: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.uc_url = uc_url.rstrip("/")
        self.workspace_id = workspace_id
        self.timeout = timeout
        self.session = requests.Session()
        # Local MOI traffic must not be sent through a shell-configured HTTP proxy.
        self.session.trust_env = False
        self.csrf_token = ""

    def _request(self, method: str, url: str, body: Any = None, *, workspace: bool = False,
                 csrf: bool = False, accept: str = "application/json"):
        headers = {"Accept": accept, "User-Agent": "enron-eval-moi-runner/1.0"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if workspace:
            headers["X-Workspace-ID"] = self.workspace_id
        if csrf:
            if not self.csrf_token:
                raise MoiError("CSRF token is unavailable")
            headers["X-CSRF-Token"] = self.csrf_token
        try:
            response = self.session.request(method, url, data=compact_json(body) if body is not None else None,
                                            headers=headers, timeout=self.timeout, stream=accept == "text/event-stream")
        except requests.RequestException as exc:
            raise MoiError(f"Cannot reach {url}: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text[:1000]
            response.close()
            raise MoiError(f"HTTP {response.status_code} {url}: {detail}")
        return response

    def json_request(self, method: str, path_or_url: str, body: Any = None, *,
                     workspace: bool = False, csrf: bool = False) -> Any:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}/newmoi{path_or_url}"
        with self._request(method, url, body, workspace=workspace, csrf=csrf) as response:
            raw = response.text
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MoiError(f"Expected JSON from {url}, got: {raw[:300]}") from exc

    def _uc_login(self, email: str, password: str, challenge: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "email": email, "password": password, "app": "ai", "remember": True,
            "return_to": f"/{self.workspace_id}/knowledge",
        }
        if challenge:
            payload["login_challenge"] = challenge
        data = unwrap(self.json_request("POST", f"{self.uc_url}/api/v1/uc/sessions/login", payload), "UC login")
        if not isinstance(data, dict) or not data.get("redirect_url"):
            raise MoiError("UC login did not return redirect_url")
        return data

    def _follow(self, url: str) -> str:
        with self._request("GET", url, accept="text/html,*/*") as response:
            _ = response.content
            return response.url

    def login(self, email: str, password: str) -> dict[str, Any]:
        first = self._uc_login(email, password)
        challenge_url = self._follow(str(first["redirect_url"]))
        challenge = parse_qs(urlparse(challenge_url).query).get("login_challenge", [""])[0]
        if challenge:
            second = self._uc_login(email, password, challenge)
            self._follow(str(second["redirect_url"]))
        me = unwrap(self.json_request("GET", "/auth/me"), "MOI auth/me")
        if not isinstance(me, dict) or not me.get("csrf_token"):
            raise MoiError("MOI product session did not provide a CSRF token")
        self.csrf_token = str(me["csrf_token"])
        return me

    def list_knowledge(self, search: str) -> list[dict[str, Any]]:
        query = urlencode({"page_size": 100, "search": search})
        data = unwrap(self.json_request("GET", f"/semantic-models?{query}", workspace=True), "list semantic models")
        return list(data.get("items") or []) if isinstance(data, dict) else []

    def list_models(self) -> list[dict[str, Any]]:
        data = unwrap(self.json_request("GET", "/models", workspace=True), "list models")
        return list(data.get("models") or []) if isinstance(data, dict) else []

    def create_session(self, question_id: str, repeat_index: int, knowledge_id: int,
                       model: dict[str, Any]) -> dict[str, Any]:
        config_data: dict[str, Any] = {
            "type": "fixed", "semantic_models": [{"semantic_model_id": knowledge_id}],
            "model": str(model["model"]),
            "llm": {"model": str(model["model"]), "backend_id": model.get("backend_id")},
        }
        config = json.dumps(config_data, ensure_ascii=False, separators=(",", ":"))
        body = {"title": f"[enron-eval] {question_id} r{repeat_index}", "source": "moi", "config": config}
        data = unwrap(self.json_request("POST", "/sessions", body, workspace=True, csrf=True), "create session")
        if not isinstance(data, dict) or not data.get("id"):
            raise MoiError("create session returned no id")
        return data

    def stream_question(self, session_id: int, question: str, knowledge: dict[str, Any],
                        model: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        deadline = time.monotonic() + self.timeout
        stamp, suffix = int(time.time() * 1000), uuid.uuid4().hex[:6]
        task_id = f"explore_{session_id}_{stamp}_{suffix}"
        context_id = f"explore_session_{session_id}"
        tables = sorted({name.strip() for item in (knowledge.get("tables") or [])
                         for name in (item.get("table_names") or []) if isinstance(name, str) and name.strip()})
        databases = sorted({str(item.get("db_name", "")).strip() for item in (knowledge.get("tables") or [])
                            if str(item.get("db_name", "")).strip()})
        knowledge_id = int(knowledge["id"])
        scope_metadata = {"semantic_model_ids": str(knowledge_id),
                          "semantic_model_names": str(knowledge.get("name") or "")}
        scope: dict[str, Any] = {"workspace_id": self.workspace_id, "session_id": str(session_id),
                                 "scope_metadata": scope_metadata}
        if tables:
            scope["tables"] = tables
        if len(databases) == 1:
            scope["database"] = databases[0]
        metadata: dict[str, Any] = {
            "matrixflow_client": "moi-frontend", "workspace_id": self.workspace_id,
            "session_id": str(session_id), "scope": scope, "scope_metadata": scope_metadata,
            "semantic_model_ids": [knowledge_id],
        }
        if tables:
            metadata["tables"] = tables
        if len(databases) == 1:
            metadata["database"] = databases[0]
        params: dict[str, Any] = {
            "message": {"kind": "message", "role": "user", "messageId": f"msg_user_{stamp}_{suffix}",
                        "taskId": task_id, "contextId": context_id,
                        "parts": [{"kind": "text", "text": question.strip()}], "metadata": metadata},
            "model": str(model["model"]), "metadata": metadata,
        }
        backend_id = model.get("backend_id")
        if isinstance(backend_id, int) and backend_id != 0:
            request_metadata = {**metadata, "llm_backend_id": backend_id}
            params.update({"llm_backend_id": backend_id, "metadata": request_metadata})
            params["message"]["metadata"] = request_metadata
        payload = {"agent_code": "explore", "jsonrpc": "2.0", "id": f"req_{task_id}",
                   "method": "message/stream", "params": params}
        response = self._request("POST", f"{self.base_url}/newmoi/agents/a2a", payload,
                                 workspace=True, csrf=True, accept="text/event-stream")
        response.encoding = "utf-8"
        events: list[dict[str, Any]] = []
        raw_lines: list[str] = []
        data_lines: list[str] = []
        try:
            for raw in response.iter_lines(decode_unicode=True):
                if time.monotonic() >= deadline:
                    raise MoiError(
                        f"MOI attempt exceeded the {self.timeout}-second total time limit"
                    )
                line = raw.rstrip("\r\n")
                raw_lines.append(line)
                if not line:
                    if data_lines:
                        self._append_sse_event(events, "\n".join(data_lines))
                        data_lines = []
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                self._append_sse_event(events, "\n".join(data_lines))
        finally:
            response.close()
        raw = {"request": payload, "events": events, "sse_lines": raw_lines,
               "task_id": task_id, "context_id": context_id}
        return events, raw

    @staticmethod
    def _append_sse_event(events: list[dict[str, Any]], text: str) -> None:
        if text == "[DONE]":
            return
        try:
            parsed = json.loads(text)
            events.append(parsed if isinstance(parsed, dict) else {"_data": parsed})
        except json.JSONDecodeError:
            events.append({"_unparsed_data": text})


def read_questions(path: Path) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" not in line:
            raise MoiError(f"{path}:{number}: expected question_id<TAB>question")
        question_id, question = (part.strip() for part in line.split("\t", 1))
        if not question_id or not question or question_id in seen:
            raise MoiError(f"{path}:{number}: invalid or duplicate question")
        seen.add(question_id)
        result.append((question_id, question))
    return result


def choose_model(models: list[dict[str, Any]], requested: str = "") -> dict[str, Any]:
    compatible = [item for item in models
                  if str(item.get("model_type") or "chat").lower() in {"chat", "vision", "reasoning"}
                  and str(item.get("model") or "").strip()]
    if requested:
        compatible = [item for item in compatible if str(item.get("model")) == requested]
    compatible.sort(key=lambda item: (0 if item.get("system_default") else 1, str(item.get("model"))))
    if not compatible:
        raise MoiError(f"No compatible MOI model is configured{f': {requested}' if requested else ''}")
    return compatible[0]


def walk(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + (str(index),))


def iter_dicts(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def duration_ms(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(ms|s)?\s*", value, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    return amount * 1000 if (match.group(2) or "ms").lower() == "s" else amount


def extract_query_results(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(output: dict[str, Any], elapsed: Any = None) -> None:
        sql = output.get("sql")
        rows = output.get("rows")
        if not isinstance(sql, str) or not re.match(r"^\s*(?:SELECT|WITH)\b", sql, re.I):
            return
        if not isinstance(rows, list):
            return
        artifact_id = str(output.get("artifact_id") or "")
        identity = artifact_id or json.dumps(
            [sql, output.get("sql_idx"), output.get("columns"), rows],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if identity in seen:
            return
        seen.add(identity)
        results.append({
            "artifact_id": artifact_id or None,
            "sql": sql.strip(),
            "columns": output.get("columns") if isinstance(output.get("columns"), list) else [],
            "rows": rows,
            "row_count": output.get("row_count"),
            "total_count": output.get("total_count"),
            "max_rows": output.get("max_rows"),
            "database": output.get("db_name"),
            "tables": output.get("table_names") if isinstance(output.get("table_names"), list) else [],
            "execution_ms": duration_ms(elapsed),
        })

    for event in events:
        for item in iter_dicts(event):
            output = item.get("output")
            if isinstance(output, dict) and (
                item.get("toolId") == "query_sql"
                or item.get("tool_id") == "query_sql"
                or output.get("kind") == "query_sql"
                or output.get("tool_id") == "query_sql"
            ):
                add(output, item.get("duration"))
            if item.get("kind") == "query_sql" or item.get("tool_id") == "query_sql":
                add(item)
    return results


def extract_selected_source_ids(events: list[dict[str, Any]]) -> list[str]:
    selections: list[list[str]] = []
    for event in events:
        for item in iter_dicts(event):
            if item.get("selected") is not True and item.get("data_type") != "answer":
                continue
            refs = item.get("source_refs") or item.get("sources")
            if not isinstance(refs, list):
                continue
            ids = [str(ref.get("artifact_id")) for ref in refs
                   if isinstance(ref, dict) and ref.get("artifact_id")]
            if ids:
                selections.append(ids)
    return selections[-1] if selections else []


def extract_llm_usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    calls_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        for item in iter_dicts(event):
            call_type = str(item.get("type") or "").lower()
            if "llm_call" not in call_type:
                continue
            call_id = str(item.get("call_id") or "")
            if not call_id:
                continue
            candidate = {
                "call_id": call_id,
                "model": item.get("model"),
                "status": item.get("status"),
                "input_tokens": int(item.get("input_tokens") or 0),
                "output_tokens": int(item.get("output_tokens") or 0),
                "cached_tokens": int(item.get("cached_tokens") or 0),
                "reasoning_tokens": int(item.get("reasoning_tokens") or 0),
                "duration_ms": item.get("duration_ms"),
                "ttft_ms": item.get("ttft_ms"),
            }
            previous = calls_by_id.get(call_id)
            candidate_score = (candidate["input_tokens"] + candidate["output_tokens"],
                               candidate["status"] == "completed")
            previous_score = ((previous["input_tokens"] + previous["output_tokens"],
                               previous["status"] == "completed") if previous else (-1, False))
            if candidate_score > previous_score:
                calls_by_id[call_id] = candidate
    calls = list(calls_by_id.values())
    prompt_tokens = sum(call["input_tokens"] for call in calls)
    completion_tokens = sum(call["output_tokens"] for call in calls)
    return {
        "prompt_tokens": prompt_tokens if calls else None,
        "completion_tokens": completion_tokens if calls else None,
        "total_tokens": prompt_tokens + completion_tokens if calls else None,
        "cached_tokens": sum(call["cached_tokens"] for call in calls) if calls else None,
        "reasoning_tokens": sum(call["reasoning_tokens"] for call in calls) if calls else None,
        "llm_call_count": len(calls),
        "calls": calls,
    }


def extract_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[tuple[int, int, str]] = []
    answers: list[str] = []
    answer_chunks: list[str] = []
    states: list[str] = []
    errors: list[str] = []
    order = 0
    for event in events:
        for path, value in walk(event):
            order += 1
            key = path[-1].lower() if path else ""
            if key == "state" and isinstance(value, str):
                states.append(value.lower())
            if key in {"error", "error_message"} and isinstance(value, str) and value.strip():
                errors.append(value.strip())
            if (isinstance(value, str) and key in {"executed_sql", "generated_sql", "sql"}
                    and re.match(r"^\s*(?:SELECT|WITH)\b", value, re.I)):
                priority = 100 if key == "executed_sql" else 90 if key == "generated_sql" else 80
                candidates.append((priority, order, value.strip()))
        result = event.get("result")
        if not isinstance(result, dict):
            continue
        status_message = (result.get("status") or {}).get("message")
        if isinstance(status_message, dict) and status_message.get("role") == "agent":
            answer_chunks.extend(part["text"] for part in (status_message.get("parts") or [])
                                 if isinstance(part, dict) and isinstance(part.get("text"), str))
        artifacts: list[dict[str, Any]] = []
        if result.get("kind") == "artifact-update" and isinstance(result.get("artifact"), dict):
            artifacts.append(result["artifact"])
        artifacts.extend(item for item in (result.get("artifacts") or []) if isinstance(item, dict))
        for artifact in artifacts:
            metadata = artifact.get("metadata") or {}
            kind = " ".join((str(artifact.get("name") or ""), str(metadata.get("matrixflow_type") or ""),
                             str(metadata.get("data_type") or ""))).lower()
            if ("final_answer" in kind or "final answer" in kind
                    or "knowledge.answer" in kind or metadata.get("data_type") == "answer"):
                answers.extend(part["text"].strip() for part in (artifact.get("parts") or [])
                               if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip())
    query_results = extract_query_results(events)
    selected_source_ids = extract_selected_source_ids(events)
    selected_results = [item for item in query_results if item.get("artifact_id") in selected_source_ids]
    if not selected_results and query_results:
        selected_results = [query_results[-1]]
    selected_sql = selected_results[-1]["sql"] if selected_results else ""
    generated_sql = selected_sql or (max(candidates, key=lambda item: (item[0], item[1]))[2]
                                     if candidates else "")
    failure = next((state for state in reversed(states) if state in {"failed", "rejected", "canceled"}), None)
    error = errors[-1] if errors else (f"MOI task state: {failure}" if failure else None)
    raw_answer = answers[-1] if answers else ("".join(answer_chunks).strip() or None)
    usage = extract_llm_usage(events)
    execution_times = [item["execution_ms"] for item in selected_results
                       if isinstance(item.get("execution_ms"), (int, float))]
    return {
        "generated_sql": generated_sql,
        "raw_answer": raw_answer,
        "error": error,
        "task_failure_state": failure,
        "native_execution_success": bool(selected_results),
        "native_query_results": query_results,
        "selected_source_ids": selected_source_ids,
        "selected_native_results": selected_results,
        "sql_execution_ms": round(sum(execution_times), 3) if execution_times else None,
        **usage,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Enron questions against local MOI")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--uc-url", default=DEFAULT_UC_URL)
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    parser.add_argument("--knowledge-name", default=DEFAULT_KNOWLEDGE_NAME)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-backend-id", type=int)
    parser.add_argument("--semantic-rules", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--attempt-retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=10.0)
    parser.add_argument("--max-consecutive-infrastructure-errors", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    email, password = os.environ.get("MOI_EMAIL", "").strip(), os.environ.get("MOI_PASSWORD", "")
    if not email or not password:
        raise MoiError("Set MOI_EMAIL and MOI_PASSWORD before running")
    root = args.project_root.resolve()
    questions_path = (args.questions or root / DEFAULT_QUESTIONS).resolve()
    output_root = (args.output_root or root / "runs/moi").resolve()
    questions = read_questions(questions_path)
    if args.limit > 0:
        questions = questions[:args.limit]
    if args.repeats < 1:
        raise MoiError("--repeats must be at least 1")
    if args.attempt_retries < 0:
        raise MoiError("--attempt-retries cannot be negative")
    run_id = args.run_id or datetime.now().astimezone().strftime("%Y-%m-%d_moi_no_semantic_%H%M%S")
    run_dir, raw_dir = output_root / run_id, output_root / run_id / "raw"
    raw_dir.mkdir(parents=True, exist_ok=args.resume)
    predictions_path = run_dir / "predictions.jsonl"
    completed: set[tuple[str, int]] = set()
    if args.resume and predictions_path.exists():
        for line in predictions_path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                completed.add((str(record.get("question_id") or ""),
                               int(record.get("repeat_index") or record.get("attempt") or 1)))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    client = MoiClient(args.base_url, args.uc_url, args.workspace_id, args.timeout)
    print("Authenticating with local MOI...", flush=True)
    client.login(email, password)
    matches = [item for item in client.list_knowledge(args.knowledge_name) if item.get("name") == args.knowledge_name]
    if len(matches) != 1:
        raise MoiError(f"Expected exactly one knowledge base named {args.knowledge_name!r}")
    knowledge = matches[0]
    if args.model_backend_id is not None:
        model = {"model": args.model, "backend_id": args.model_backend_id,
                 "system_default": args.model_backend_id < 0}
    else:
        model = choose_model(client.list_models(), args.model)
    started_at = now_iso()
    meta = {
        "run_id": run_id, "product": "moi", "product_version": "local", "model": model.get("model"),
        "model_backend_id": model.get("backend_id"), "benchmark_id": "enron_golden50_v1",
        "database_snapshot": "expected_counts_v1", "semantic_rules": args.semantic_rules or None,
        "knowledge_base": {"id": knowledge.get("id"), "name": knowledge.get("name")},
        "workspace_id": args.workspace_id, "questions_file": str(questions_path), "started_at": started_at,
        "finished_at": None, "question_count": len(questions), "repeats": args.repeats,
        "expected_attempts": len(questions) * args.repeats,
        "native_execution_engine": "matrixone",
        "protocol": "one isolated fixed-knowledge MOI session per question and repeat",
        "notes": ("Run with configured semantic information."
                  if args.semantic_rules else "Baseline run without configured semantic information."),
    }
    write_json(run_dir / "run.json", meta)
    attempts = [(repeat_index, question_id, question)
                for repeat_index in range(1, args.repeats + 1)
                for question_id, question in questions]
    consecutive_infrastructure_errors = 0
    for index, (repeat_index, question_id, question) in enumerate(attempts, 1):
        if (question_id, repeat_index) in completed:
            print(f"[{index:03d}/{len(attempts):03d}] {question_id} r{repeat_index}: skipped (resume)", flush=True)
            continue
        started, session_id, raw = time.perf_counter(), None, {}
        extracted: dict[str, Any] = {}
        status, infrastructure_error = "generation_error", False
        for retry_index in range(args.attempt_retries + 1):
            extracted = {
                "generated_sql": "", "raw_answer": None, "error": None,
                "native_execution_success": False, "native_query_results": [],
                "selected_source_ids": [], "selected_native_results": [], "sql_execution_ms": None,
                "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
                "cached_tokens": None, "reasoning_tokens": None, "llm_call_count": 0, "calls": [],
            }
            try:
                session_id = int(client.create_session(
                    question_id, repeat_index, int(knowledge["id"]), model
                )["id"])
                events, raw = client.stream_question(session_id, question, knowledge, model)
                extracted = extract_result(events)
                if extracted["native_execution_success"] and extracted["generated_sql"]:
                    status = "ok"
                elif extracted["error"]:
                    status = "generation_error"
                elif extracted["generated_sql"]:
                    status = "native_execution_error"
                else:
                    status = "empty_sql"
                infrastructure_error = False
                break
            except Exception as exc:
                message = str(exc)
                status, extracted["error"] = "generation_error", message
                raw = {"exception": message, "retry_index": retry_index}
                infrastructure_error = any(marker in message.lower() for marker in (
                    "service unavailable", "connection reset", "cannot reach",
                    "connection refused", "timed out", "time limit",
                ))
                if infrastructure_error and retry_index < args.attempt_retries:
                    print(
                        f"[{index:03d}/{len(attempts):03d}] {question_id} r{repeat_index}: "
                        f"infrastructure error, retry {retry_index + 1}/{args.attempt_retries}",
                        flush=True,
                    )
                    time.sleep(args.retry_delay)
                    continue
                break
        latency_ms = round((time.perf_counter() - started) * 1000)
        raw.update({"question_id": question_id, "question": question,
                    "repeat_index": repeat_index, "session_id": session_id})
        write_json(raw_dir / f"{question_id}_r{repeat_index}.json", raw)
        append_jsonl(predictions_path, {
            "question_id": question_id,
            "question": question,
            "repeat_index": repeat_index,
            "generated_sql": extracted["generated_sql"],
            "status": status,
            "native_execution_engine": "matrixone",
            "native_execution_success": extracted["native_execution_success"],
            "native_query_results": extracted["native_query_results"],
            "selected_source_ids": extracted["selected_source_ids"],
            "selected_native_results": extracted["selected_native_results"],
            "latency_ms": latency_ms,
            "sql_execution_ms": extracted["sql_execution_ms"],
            "prompt_tokens": extracted["prompt_tokens"],
            "completion_tokens": extracted["completion_tokens"],
            "total_tokens": extracted["total_tokens"],
            "cached_tokens": extracted["cached_tokens"],
            "reasoning_tokens": extracted["reasoning_tokens"],
            "llm_call_count": extracted["llm_call_count"],
            "error": extracted["error"],
            "raw_answer": extracted["raw_answer"],
            "metadata": {
                "session_id": session_id,
                "task_id": raw.get("task_id"),
                "context_id": raw.get("context_id"),
                "knowledge_id": knowledge.get("id"),
                "model": model.get("model"),
                "model_backend_id": model.get("backend_id"),
                "new_session": True,
                "llm_calls": extracted["calls"],
            },
            "completed_at": now_iso(),
        })
        completed.add((question_id, repeat_index))
        meta["recorded_attempts"] = len(completed)
        write_json(run_dir / "run.json", meta)
        print(f"[{index:03d}/{len(attempts):03d}] {question_id} r{repeat_index}: "
              f"{status}, {latency_ms} ms", flush=True)
        if infrastructure_error:
            consecutive_infrastructure_errors += 1
        else:
            consecutive_infrastructure_errors = 0
        if consecutive_infrastructure_errors >= args.max_consecutive_infrastructure_errors:
            raise MoiError(
                "Stopped after consecutive infrastructure errors; restart MOI and resume this run"
            )

    records = [json.loads(line) for line in predictions_path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    ok_records = [item for item in records if item.get("status") == "ok"]
    latencies = [int(item["latency_ms"]) for item in records if isinstance(item.get("latency_ms"), int)]
    token_values = [int(item["total_tokens"]) for item in records if isinstance(item.get("total_tokens"), int)]
    summary = {
        "expected_attempts": len(attempts),
        "recorded_attempts": len(records),
        "native_execution_successes": len(ok_records),
        "failed": len(records) - len(ok_records),
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "min_latency_ms": min(latencies) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
        "total_tokens": sum(token_values) if token_values else None,
        "failed_attempts": [
            {"question_id": item.get("question_id"), "repeat_index": item.get("repeat_index"),
             "status": item.get("status"), "error": item.get("error")}
            for item in records if item.get("status") != "ok"
        ],
    }
    write_json(run_dir / "run_summary.json", summary)
    meta.update({"finished_at": now_iso(), "recorded_attempts": len(records),
                 "native_execution_successes": len(ok_records)})
    write_json(run_dir / "run.json", meta)
    print(f"Run artifacts: {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except MoiError as exc:
        print(f"MOI runner error: {exc}", file=sys.stderr)
        raise SystemExit(1)
