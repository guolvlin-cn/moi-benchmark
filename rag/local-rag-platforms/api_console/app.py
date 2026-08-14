#!/usr/bin/env python3
"""Loopback-only control plane for local RAG platform APIs and services."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".local-services/api-console"
INDEX = Path(__file__).with_name("index.html")
CONSOLE_TOKEN = secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    secret: bool = False
    default: str = ""
    hint: str = ""


@dataclass(frozen=True)
class Platform:
    system_id: str
    name: str
    accent: str
    base_url: str
    health_url: str
    config_file: Path
    fields: tuple[Field, ...]
    container_markers: tuple[str, ...]
    readiness: str
    readiness_note: str
    start_command: tuple[str, ...] | None
    start_cwd: Path
    stop_command: tuple[str, ...] | None
    stop_cwd: Path
    start_blocked_reason: str | None = None
    serial_exempt: bool = False
    require_all_markers: bool = False


PLATFORMS: dict[str, Platform] = {
    "moi_local": Platform(
        system_id="moi_local",
        name="MOI Local",
        accent="#cf525c",
        base_url="http://127.0.0.1:8080",
        health_url="http://127.0.0.1:8080/healthz",
        config_file=ROOT / "prototypes/local-matrixflow-rag/.env",
        fields=(
            Field(
                "TAAS_API_KEY",
                "MatrixOrigin TaaS API Key",
                secret=True,
                hint="用于 MatrixFlow embedding 与可选生成；模型与 Base URL 固定在 benchmark JSON 配置中。",
            ),
            Field("QIANFAN_BASE_URL", "Qianfan Base URL", default="https://qianfan.baidubce.com/v2"),
            Field("QIANFAN_API_KEY", "Qianfan API Key", secret=True),
            Field("QIANFAN_LLM_MODEL", "Qianfan LLM", default="deepseek-v4-flash"),
            Field("QIANFAN_EMBEDDING_MODEL", "Qianfan Embedding", default="qwen3-embedding-8b", hint="4096 维；切换后必须使用独立向量表重新索引。"),
            Field("QIANFAN_RERANKER_MODEL", "Qianfan Reranker", default="qwen3-reranker-8b", hint="MOI 当前 pipeline 尚无 reranker 执行节点。"),
            Field("QIANFAN_APPID", "Qianfan AppID", hint="可选：按应用计量或 Key 绑定特定 AppID 时填写。"),
        ),
        container_markers=("matrixone", "moi-openxml-parser"),
        readiness="near_ready",
        readiness_note="MMDocIR 311,644 条索引已 committed；QA 评估及其他数据集尚未执行。",
        start_command=("docker", "start", "matrixone", "moi-openxml-parser"),
        start_cwd=ROOT,
        stop_command=("docker", "stop", "moi-openxml-parser", "matrixone"),
        stop_cwd=ROOT,
        serial_exempt=True,
        require_all_markers=True,
    ),
    "dify_local": Platform(
        system_id="dify_local",
        name="Dify",
        accent="#3f7cff",
        base_url="http://127.0.0.1:8010/v1",
        health_url="http://127.0.0.1:8010/console/api/setup",
        config_file=ROOT / ".local-services/dify_local/credentials.env",
        fields=(
            Field("DIFY_API_BASE_URL", "API Base URL", default="http://127.0.0.1:8010/v1"),
            Field("DIFY_LOCAL_DATASET_API_KEY", "Dataset API Key", secret=True),
            Field("DIFY_LOCAL_API_KEY", "App API Key", secret=True),
            Field("DIFY_LOCAL_APP_ID", "App ID"),
            Field("DIFY_LOCAL_DATASET_ID", "Dataset ID", hint="正式评估时必须与 App 使用同一 44 文档 corpus"),
            Field("QIANFAN_BASE_URL", "Qianfan Base URL", default="https://qianfan.baidubce.com/v2"),
            Field("QIANFAN_API_KEY", "Qianfan API Key", secret=True, hint="保存后仍需在本地 Dify OpenAI-compatible provider 中注册模型。"),
            Field("QIANFAN_LLM_MODEL", "Qianfan LLM", default="deepseek-v4-flash"),
            Field("QIANFAN_EMBEDDING_MODEL", "Qianfan Embedding", default="qwen3-embedding-8b"),
            Field("QIANFAN_RERANKER_MODEL", "Qianfan Reranker", default="qwen3-reranker-8b"),
            Field("QIANFAN_APPID", "Qianfan AppID", hint="可选：按应用计量或权限绑定。"),
        ),
        container_markers=("moi_dify_local-",),
        readiness="near_ready",
        readiness_note="3 文档 smoke 与 44 文档 readiness 已通过；仍需对齐 App 与 44 文档 Dataset。",
        start_command=("docker", "compose", "-p", "moi_dify_local", "up", "-d"),
        start_cwd=ROOT / ".local-services/dify_local/source/dify/docker",
        stop_command=("docker", "compose", "-p", "moi_dify_local", "down"),
        stop_cwd=ROOT / ".local-services/dify_local/source/dify/docker",
    ),
    "fastgpt_local": Platform(
        system_id="fastgpt_local",
        name="FastGPT",
        accent="#e27a3f",
        base_url="http://127.0.0.1:3000",
        health_url="http://127.0.0.1:3000",
        config_file=ROOT / ".local-services/fastgpt_local/fastgpt.env",
        fields=(
            Field("FASTGPT_BASE_URL", "API Base URL", default="http://127.0.0.1:3000"),
            Field("FASTGPT_API_KEY", "API Key", secret=True),
            Field("FASTGPT_APP_ID", "App ID"),
            Field("TAAS_BASE_URL", "TaaS Base URL"),
            Field("TAAS_API_KEY", "TaaS API Key", secret=True),
            Field("TAAS_LLM_MODEL", "LLM Model", default="deepseek-v4-flash"),
            Field("TAAS_EMBEDDING_MODEL", "Embedding Model", default="bge-m3"),
            Field("QIANFAN_BASE_URL", "Qianfan Base URL", default="https://qianfan.baidubce.com/v2"),
            Field("QIANFAN_API_KEY", "Qianfan API Key", secret=True),
            Field("QIANFAN_LLM_MODEL", "Qianfan LLM", default="deepseek-v4-flash"),
            Field("QIANFAN_EMBEDDING_MODEL", "Qianfan Embedding", default="qwen3-embedding-8b"),
            Field("QIANFAN_RERANKER_MODEL", "Qianfan Reranker", default="qwen3-reranker-8b"),
            Field("QIANFAN_APPID", "Qianfan AppID", hint="可选：按应用计量或权限绑定。"),
        ),
        container_markers=("fastgpt-",),
        readiness="partial",
        readiness_note="3 文档 ingest/retrieval 成功；Native QA timeout，尚未完成 44 文档。",
        start_command=(
            "docker", "compose", "-p", "moi_fastgpt_local", "-f",
            str(ROOT / ".local-services/fastgpt_local/compose/docker-compose.pg.yml"), "up", "-d",
        ),
        start_cwd=ROOT,
        stop_command=(
            "docker", "compose", "-p", "moi_fastgpt_local", "-f",
            str(ROOT / ".local-services/fastgpt_local/compose/docker-compose.pg.yml"), "down",
        ),
        stop_cwd=ROOT,
    ),
    "maxkb_local": Platform(
        system_id="maxkb_local",
        name="MaxKB",
        accent="#a765d5",
        base_url="http://127.0.0.1:8090",
        health_url="http://127.0.0.1:8090/admin/",
        config_file=ROOT / ".local-services/maxkb_local/runtime.env",
        fields=(
            Field("MAXKB_BASE_URL", "Admin Base URL", default="http://127.0.0.1:8090"),
            Field("MAXKB_APP_ID", "Application ID"),
            Field("MAXKB_API_KEY", "Application API Key", secret=True),
            Field("MAXKB_OPENAI_BASE_URL", "OpenAI-compatible Base URL"),
            Field("MAXKB_OPENAI_PATH", "Chat Path", default="/chat/completions"),
            Field("MAXKB_MODEL", "Model", default="default"),
            Field("QIANFAN_BASE_URL", "Qianfan Base URL", default="https://qianfan.baidubce.com/v2"),
            Field("QIANFAN_API_KEY", "Qianfan API Key", secret=True),
            Field("QIANFAN_CHAT_MODEL", "Qianfan LLM", default="deepseek-v4-flash"),
            Field("QIANFAN_EMBEDDING_MODEL", "Qianfan Embedding", default="qwen3-embedding-8b"),
            Field("QIANFAN_RERANKER_MODEL", "Qianfan Reranker", default="qwen3-reranker-8b"),
            Field("QIANFAN_APPID", "Qianfan AppID", hint="可选：按应用计量或权限绑定。"),
        ),
        container_markers=("moi-maxkb-local",),
        readiness="partial",
        readiness_note="服务与 provider 已配置；Native 请求异常，Direct Retrieval 为 unsupported。",
        start_command=(str(ROOT / "local-rag-platforms/maxkb_local/maxkb-local.sh"), "resume"),
        start_cwd=ROOT,
        stop_command=(str(ROOT / "local-rag-platforms/maxkb_local/maxkb-local.sh"), "stop"),
        stop_cwd=ROOT,
    ),
    "ragflow_local": Platform(
        system_id="ragflow_local",
        name="RAGFlow",
        accent="#2b9f86",
        base_url="http://127.0.0.1:9380",
        health_url="http://127.0.0.1:9380",
        config_file=ROOT / ".local-services/ragflow_local/credentials.env",
        fields=(
            Field("RAGFLOW_API_BASE_URL", "API Base URL", default="http://127.0.0.1:9380"),
            Field("RAGFLOW_API_KEY", "API Key", secret=True),
            Field("RAGFLOW_CHAT_ID", "Chat ID"),
            Field("TAAS_BASE_URL", "TaaS Base URL"),
            Field("TAAS_API_KEY", "TaaS API Key", secret=True),
            Field("TAAS_LLM_MODEL", "LLM Model", default="deepseek-v4-flash"),
            Field("TAAS_EMBEDDING_MODEL", "Embedding Model", default="bge-m3"),
            Field("QIANFAN_BASE_URL", "Qianfan Base URL", default="https://qianfan.baidubce.com/v2"),
            Field("QIANFAN_API_KEY", "Qianfan API Key", secret=True),
            Field("QIANFAN_CHAT_MODEL", "Qianfan LLM", default="deepseek-v4-flash"),
            Field("QIANFAN_EMBEDDING_MODEL", "Qianfan Embedding", default="qwen3-embedding-8b"),
            Field("QIANFAN_RERANKER_MODEL", "Qianfan Reranker", default="qwen3-reranker-8b"),
            Field("QIANFAN_APPID", "Qianfan AppID", hint="可选：按应用计量或权限绑定。"),
        ),
        container_markers=("moi_ragflow_local", "ragflow"),
        readiness="blocked",
        readiness_note="当前 Colima 2 CPU / 12 GiB / 约 12 GiB free，低于官方资源门槛。",
        start_command=None,
        start_cwd=ROOT,
        stop_command=None,
        stop_cwd=ROOT,
        start_blocked_reason="BLOCKED_LOCAL_RESOURCES",
    ),
}


class ConfigUpdate(BaseModel):
    values: dict[str, str]


class ActionRequest(BaseModel):
    action: str


def parse_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return lines, values


def write_env(path: Path, updates: dict[str, str], allowed: set[str]) -> None:
    unknown = sorted(set(updates) - allowed)
    if unknown:
        raise HTTPException(400, f"unsupported configuration keys: {', '.join(unknown)}")
    lines, existing = parse_env(path)
    merged = dict(existing)
    for key, value in updates.items():
        value = value.strip()
        if value:
            if "\n" in value or "\r" in value or "\x00" in value:
                raise HTTPException(400, f"invalid value for {key}")
            merged[key] = value

    managed_seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in allowed:
                if key in merged:
                    output.append(f"{key}={json.dumps(merged[key])}")
                managed_seen.add(key)
                continue
        output.append(line)
    for key in sorted(allowed - managed_seen):
        if key in merged:
            output.append(f"{key}={json.dumps(merged[key])}")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output).rstrip() + "\n")
        os.replace(temp_name, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def docker_rows() -> list[dict[str, str]]:
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{json .}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=8,
    )
    if result.returncode:
        return []
    rows = []
    for line in result.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def containers_for(platform: Platform, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row for row in rows
        if any(marker.lower() in row.get("Names", "").lower() for marker in platform.container_markers)
    ]


def is_running(platform: Platform, rows: list[dict[str, str]]) -> bool:
    if platform.require_all_markers:
        return all(
            any(
                marker.lower() in row.get("Names", "").lower()
                and row.get("State", "").lower() == "running"
                for row in rows
            )
            for marker in platform.container_markers
        )
    return any(row.get("State", "").lower() == "running" for row in containers_for(platform, rows))


def probe(url: str) -> dict[str, Any]:
    started = time.monotonic()
    request = Request(url, method="GET", headers={"User-Agent": "MOI-RAG-API-Console/0.1"})
    try:
        with urlopen(request, timeout=2) as response:
            return {"reachable": True, "status": response.status, "latency_ms": round((time.monotonic() - started) * 1000)}
    except HTTPError as exc:
        return {"reachable": True, "status": exc.code, "latency_ms": round((time.monotonic() - started) * 1000)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"reachable": False, "status": None, "error": type(exc).__name__}


def require_token(token: str | None) -> None:
    if not token or not secrets.compare_digest(token, CONSOLE_TOKEN):
        raise HTTPException(403, "invalid console token")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def platform_payload(platform: Platform, rows: list[dict[str, str]], include_probe: bool = False) -> dict[str, Any]:
    _, values = parse_env(platform.config_file)
    fields = []
    for field in platform.fields:
        value = values.get(field.key, "")
        fields.append({
            "key": field.key,
            "label": field.label,
            "secret": field.secret,
            "configured": bool(value and not value.startswith("<")),
            "value": "" if field.secret else value,
            "default": field.default,
            "hint": field.hint,
        })
    containers = containers_for(platform, rows)
    payload: dict[str, Any] = {
        "system_id": platform.system_id,
        "name": platform.name,
        "accent": platform.accent,
        "base_url": platform.base_url,
        "running": is_running(platform, rows),
        "containers": [{"name": row.get("Names"), "state": row.get("State"), "status": row.get("Status")} for row in containers],
        "config_file": display_path(platform.config_file),
        "configured_count": sum(1 for field in fields if field["configured"]),
        "field_count": len(fields),
        "fields": fields,
        "readiness": platform.readiness,
        "readiness_note": platform.readiness_note,
        "start_allowed": platform.start_command is not None,
        "start_blocked_reason": platform.start_blocked_reason,
        "serial_exempt": platform.serial_exempt,
    }
    if include_probe:
        payload["probe"] = probe(platform.health_url)
    return payload


app = FastAPI(title="MOI RAG API Console", docs_url="/docs", redoc_url=None)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html = INDEX.read_text(encoding="utf-8")
    return html.replace("__CONSOLE_TOKEN__", CONSOLE_TOKEN)


@app.get("/api/status")
def status(probe_services: bool = False) -> dict[str, Any]:
    rows = docker_rows()
    platforms = [platform_payload(platform, rows, include_probe=probe_services) for platform in PLATFORMS.values()]
    active = [item["system_id"] for item in platforms if item["running"] and not item["serial_exempt"]]
    return {
        "console": {"bind": "127.0.0.1", "serial_policy_ok": len(active) <= 1, "active_competitors": active},
        "platforms": platforms,
    }


@app.put("/api/config/{system_id}")
def update_config(system_id: str, update: ConfigUpdate, x_console_token: Optional[str] = Header(default=None)) -> dict[str, Any]:
    require_token(x_console_token)
    platform = PLATFORMS.get(system_id)
    if not platform:
        raise HTTPException(404, "unknown platform")
    allowed = {field.key for field in platform.fields}
    write_env(platform.config_file, update.values, allowed)
    return {"saved": True, "system_id": system_id, "config_file": display_path(platform.config_file)}


@app.post("/api/service/{system_id}")
def service_action(system_id: str, request: ActionRequest, x_console_token: Optional[str] = Header(default=None)) -> dict[str, Any]:
    require_token(x_console_token)
    platform = PLATFORMS.get(system_id)
    if not platform:
        raise HTTPException(404, "unknown platform")
    if request.action not in {"start", "stop"}:
        raise HTTPException(400, "action must be start or stop")

    rows = docker_rows()
    if request.action == "start":
        if platform.start_command is None:
            raise HTTPException(409, platform.start_blocked_reason or "start is disabled")
        active_other = [
            item.system_id for item in PLATFORMS.values()
            if not item.serial_exempt and item.system_id != system_id and is_running(item, rows)
        ]
        if active_other:
            raise HTTPException(409, f"serial policy: stop {', '.join(active_other)} first")
        command, cwd = platform.start_command, platform.start_cwd
    else:
        if platform.stop_command is None:
            raise HTTPException(409, "stop is unavailable")
        command, cwd = platform.stop_command, platform.stop_cwd

    if not cwd.exists():
        raise HTTPException(409, f"runtime directory is missing: {display_path(cwd)}")
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False, timeout=180)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log = RUNTIME / "actions.jsonl"
    record = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system_id": system_id,
        "action": request.action,
        "exit_code": result.returncode,
        "output": (result.stdout + result.stderr)[-4000:],
    }
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.chmod(0o600)
    if result.returncode:
        raise HTTPException(500, f"{request.action} failed; inspect .local-services/api-console/actions.jsonl")
    return {"ok": True, "system_id": system_id, "action": request.action}


@app.get("/api/actions")
def actions() -> dict[str, Any]:
    log = RUNTIME / "actions.jsonl"
    records = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines()[-20:]:
            try:
                item = json.loads(line)
                item.pop("output", None)
                records.append(item)
            except json.JSONDecodeError:
                continue
    return {"actions": records}
