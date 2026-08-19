#!/usr/bin/env python3
"""Run MultiHop-RAG Gold-evidence generation through a retrieval-free FastGPT app.

This condition keeps FastGPT's configured chat model and system prompt, removes
the dataset-search node, and supplies each frozen Gold evidence set directly in
the user message.  It is an oracle generation condition, not a retrieval run.
The JSONL ledger is append-only and safe to resume by question_id.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_hash_sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def request_json(base_url: str, api_key: str, method: str, path: str, body: Mapping[str, Any], timeout: float) -> Any:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method=method,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def unwrap(payload: Any) -> Any:
    if isinstance(payload, Mapping) and "code" in payload:
        code = int(payload.get("code", 500) or 500)
        if code not in (0, 200):
            raise RuntimeError(f"FASTGPT_API_ERROR:{code}:{payload.get('message', '')}")
        return payload.get("data", payload)
    return payload


def create_app(base_url: str, api_key: str, model: str, name: str, timeout: float) -> str:
    start = {
        "flowNodeType": "workflowStart",
        "inputs": [{"key": "userChatInput", "label": "", "renderTypeList": ["textarea"], "value": None, "valueType": "string"}],
        "name": "Workflow start",
        "nodeId": "workflowStartNodeId",
        "outputs": [
            {"id": "userChatInput", "key": "userChatInput", "type": "static", "valueType": "string"},
            {"id": "userFiles", "key": "userFiles", "type": "static", "valueType": "arrayString"},
        ],
    }
    chat = {
        "flowNodeType": "chatNode",
        "inputs": [
            {"key": "model", "label": "", "renderTypeList": ["settingLLMModel"], "value": model, "valueType": "string"},
            {"key": "isResponseAnswerText", "label": "", "renderTypeList": ["hidden"], "value": True, "valueType": "boolean"},
            {"key": "systemPrompt", "label": "", "renderTypeList": ["textarea"], "value": "Answer using the supplied knowledge. If it is insufficient, say so.", "valueType": "string"},
            {"key": "maxContext", "label": "", "renderTypeList": ["numberInput"], "value": 6, "valueType": "chatHistory"},
            {"key": "userChatInput", "label": "", "renderTypeList": ["reference"], "value": ["workflowStartNodeId", "userChatInput"], "valueType": "string"},
        ],
        "name": "AI chat",
        "nodeId": "goldOracleAiChat",
        "outputs": [
            {"id": "history", "key": "history", "type": "static", "valueType": "chatHistory"},
            {"id": "answerText", "key": "answerText", "type": "static", "valueType": "string"},
        ],
        "showStatus": True,
        "version": "4.9.7",
    }
    payload = {
        "name": name[:100],
        "intro": "MultiHop-RAG frozen Gold-evidence oracle generation",
        "type": "simple",
        "chatConfig": {},
        "modules": [
            {"flowNodeType": "userGuide", "inputs": [], "name": "System configuration", "nodeId": "userGuide", "outputs": []},
            start,
            chat,
        ],
        "edges": [{
            "source": "workflowStartNodeId",
            "sourceHandle": "workflowStartNodeId-source-right",
            "target": "goldOracleAiChat",
            "targetHandle": "goldOracleAiChat-target-left",
        }],
    }
    value = unwrap(request_json(base_url, api_key, "POST", "/api/core/app/create", payload, timeout))
    app_id = str(value.get("appId") or value.get("id") or value.get("_id") or "") if isinstance(value, Mapping) else str(value or "")
    if not app_id:
        raise RuntimeError("FASTGPT_CREATE_GOLD_ORACLE_APP_NO_ID")
    return app_id


def prompt_for(question: Mapping[str, Any]) -> str:
    sources = question.get("metadata", {}).get("evidence_sources", []) if isinstance(question.get("metadata"), Mapping) else []
    facts = question.get("gold_evidence", []) if isinstance(question.get("gold_evidence"), list) else []
    blocks: list[str] = []
    for index, fact in enumerate(facts, 1):
        source = sources[index - 1] if index - 1 < len(sources) and isinstance(sources[index - 1], Mapping) else {}
        metadata = "\n".join(
            f"{label}: {source[key]}"
            for label, key in (("Title", "title"), ("Source", "source"), ("Published at", "published_at"), ("Author", "author"), ("Category", "category"))
            if source.get(key) not in (None, "")
        )
        blocks.append(f"[Evidence {index}]\n{metadata}\nFact: {fact}".strip())
    evidence = "\n\n".join(blocks) if blocks else "(No supporting evidence is available.)"
    return f"Frozen Gold evidence:\n{evidence}\n\nQuestion: {question.get('question', '')}"


def answer_from(payload: Any) -> str:
    if isinstance(payload, Mapping):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message")
            if isinstance(message, Mapping) and isinstance(message.get("content"), str):
                return str(message["content"])
        for key in ("answer", "content", "text", "output"):
            if isinstance(payload.get(key), str):
                return str(payload[key])
    return ""


def run_one(base_url: str, api_key: str, app_id: str, question: Mapping[str, Any], timeout: float, retries: int) -> dict[str, Any]:
    qid = str(question["question_id"])
    body = {
        "appId": app_id,
        "chatId": str(uuid.uuid4()),
        "stream": False,
        "detail": False,
        "messages": [{"role": "user", "content": prompt_for(question)}],
    }
    started = time.monotonic()
    last_error = ""
    for attempt in range(retries + 1):
        try:
            payload = unwrap(request_json(base_url, api_key, "POST", "/api/v1/chat/completions", body, timeout))
            answer = answer_from(payload)
            return {
                "schema": "fastgpt-multihop-gold-oracle-ledger-v1",
                "question_id": qid,
                "question_type": question.get("question_type"),
                "answerable": bool(question.get("answerable", True)),
                "reference_answer": question.get("reference_answer"),
                "answer": answer,
                "status": "SUCCESS" if answer.strip() else "EMPTY",
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "attempts": attempt + 1,
                "recorded_at": utc_now(),
            }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = str(exc)[:1000]
            retryable = "429" in last_error or any(code in last_error for code in ("500", "502", "503", "504"))
            if attempt >= retries or not retryable or "sensitive information" in last_error.casefold():
                break
            time.sleep(min(20.0, (2 ** attempt) + random.random()))
    return {
        "schema": "fastgpt-multihop-gold-oracle-ledger-v1",
        "question_id": qid,
        "question_type": question.get("question_type"),
        "answerable": bool(question.get("answerable", True)),
        "reference_answer": question.get("reference_answer"),
        "answer": "",
        "status": "FAILED",
        "error": last_error,
        "latency_ms": round((time.monotonic() - started) * 1000, 3),
        "attempts": retries + 1,
        "recorded_at": utc_now(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--create-only", action="store_true")
    args = parser.parse_args()
    base_url = os.environ.get("FASTGPT_BASE_URL", "").strip()
    api_key = os.environ.get("FASTGPT_API_KEY", "").strip()
    model = os.environ.get("QIANFAN_LLM_MODEL", "deepseek-v4-flash").strip()
    if not base_url or not api_key:
        raise SystemExit("FASTGPT_BASE_URL and FASTGPT_API_KEY are required")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "manifest.json"
    ledger_path = args.output / "terminal-ledger.jsonl"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        app_id = str(manifest["app_id"])
    else:
        app_id = create_app(base_url, api_key, model, f"MultiHop-Gold-Oracle-{args.output.name}", args.timeout)
        manifest = {
            "schema": "fastgpt-multihop-gold-oracle-manifest-v1",
            "condition": "frozen_gold_evidence_retrieval_free",
            "app_id": app_id,
            "model": model,
            "system_prompt": "Answer using the supplied knowledge. If it is insufficient, say so.",
            "questions_sha256": sha256_file(args.package / "questions.jsonl"),
            "gold_sha256": sha256_file(args.package / "gold.jsonl"),
            "planned_n": len(read_jsonl(args.package / "questions.jsonl")),
            "created_at": utc_now(),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"app_id": app_id, "manifest": str(manifest_path)}, ensure_ascii=False), flush=True)
    if args.create_only:
        return
    questions = read_jsonl(args.package / "questions.jsonl")
    completed = {str(row.get("question_id")) for row in read_jsonl(ledger_path)}
    pending = [question for question in questions if str(question.get("question_id")) not in completed]
    lock = threading.Lock()
    statuses: Counter[str] = Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [executor.submit(run_one, base_url, api_key, app_id, question, args.timeout, args.retries) for question in pending]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            statuses[str(row["status"])] += 1
            with lock, ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            if index % 50 == 0 or index == len(futures):
                print(json.dumps({"completed_this_run": index, "pending_at_start": len(futures), "statuses": dict(statuses)}, ensure_ascii=False), flush=True)
    all_rows = read_jsonl(ledger_path)
    all_statuses = Counter(str(row.get("status", "UNKNOWN")) for row in all_rows)
    summary = {
        "schema": "fastgpt-multihop-gold-oracle-summary-v1",
        "planned_n": len(questions),
        "terminal_n": len({str(row.get("question_id")) for row in all_rows}),
        "status_counts": dict(all_statuses),
        "complete": len({str(row.get("question_id")) for row in all_rows}) == len(questions),
        "completed_at": utc_now(),
    }
    summary_path = args.output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in (manifest_path, ledger_path, summary_path):
        write_hash_sidecar(path)


if __name__ == "__main__":
    main()
