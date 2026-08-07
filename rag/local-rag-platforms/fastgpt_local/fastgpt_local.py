#!/usr/bin/env python3
"""Read-only deployment checks and opt-in FastGPT API smoke for the local stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".local-services/fastgpt_local"
COMPOSE = RUNTIME / "compose/docker-compose.pg.yml"
SOURCE_LOCK = RUNTIME / "compose/source-lock.json"
CONTRACTS = Path(__file__).with_name("contracts.json")
EXPECTED_TAG = "v4.15.6"
EXPECTED_COMMIT = "3db33e93b78e75b37c93f7a6e3d0fafeafbfd256"

PROVIDER_PROFILES = {
    "taas": {
        "env_prefix": "TAAS",
        "channel_name": "MatrixOrigin TaaS",
        "base_url": "https://api-taas.moi.matrixorigin.cn/v1",
        "llm_model": "qwen3.6-flash",
        "embedding_model": "bge-m3",
    },
    "qianfan": {
        "env_prefix": "QIANFAN",
        "channel_name": "Baidu Qianfan V2",
        "base_url": "https://qianfan.baidubce.com/v2",
        "llm_model": "deepseek-v4-flash",
        "embedding_model": "qwen3-embedding-8b",
        "reranker_model": "qwen3-reranker-8b",
    },
}


class ContractError(RuntimeError):
    pass


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def preflight() -> int:
    failures: list[str] = []
    warnings: list[str] = []
    lock = load_json(SOURCE_LOCK)
    if lock.get("resolved_tag") != EXPECTED_TAG:
        failures.append(f"source tag is {lock.get('resolved_tag')!r}, expected {EXPECTED_TAG}")
    if lock.get("commit") != EXPECTED_COMMIT:
        failures.append("source commit does not match the pinned v4.15.6 commit")

    source = ROOT / lock["source"]
    head = run(["git", "-C", str(source), "rev-parse", "HEAD"])
    if head.returncode or head.stdout.strip() != EXPECTED_COMMIT:
        failures.append("prepared source checkout HEAD does not match source-lock.json")

    config = run(["docker", "compose", "-p", "moi_fastgpt_local", "-f", str(COMPOSE), "config", "--quiet"])
    if config.returncode:
        failures.append(f"docker compose config failed: {config.stderr.strip()}")
    images_result = run(["docker", "compose", "-p", "moi_fastgpt_local", "-f", str(COMPOSE), "config", "--images"])
    images = sorted(set(images_result.stdout.splitlines())) if images_result.returncode == 0 else []
    if "ghcr.io/labring/fastgpt:v4.15.4" not in images:
        failures.append("runtime compose no longer resolves the checked-in v4.15.4 FastGPT image")

    manifests: list[dict[str, Any]] = []
    for path in sorted((RUNTIME / "logs").glob("image-manifest-*.json")):
        data = load_json(path)
        platforms = data.get("platforms", [])
        native_arm64 = any(x.get("os") == "linux" and x.get("architecture") == "arm64" for x in platforms)
        manifests.append({"image": data.get("image"), "linux_arm64": native_arm64})
        if not native_arm64:
            failures.append(f"no linux/arm64 manifest recorded for {data.get('image')}")

    running = run(["docker", "ps", "--format", "{{.Names}}"])
    running_names = running.stdout.splitlines() if running.returncode == 0 else []
    fastgpt_running = sorted(name for name in running_names if "fastgpt" in name.lower())
    if fastgpt_running:
        failures.append("FastGPT containers are running during the no-start preparation phase")
    expected_existing = {
        "moi-openxml-parser": any(name == "moi-openxml-parser" for name in running_names),
        "matrixone": any(name == "matrixone" for name in running_names),
        "dify": any(name.startswith("moi_dify_local-") for name in running_names),
    }
    for service, present in expected_existing.items():
        if service == "dify":
            continue
        if not present:
            warnings.append(f"expected existing {service} service is not running")

    env = {
        "TAAS_API_KEY": bool(os.getenv("TAAS_API_KEY")),
        "FASTGPT_API_KEY": bool(os.getenv("FASTGPT_API_KEY")),
        "FASTGPT_APP_ID": bool(os.getenv("FASTGPT_APP_ID")),
    }
    if not env["TAAS_API_KEY"]:
        warnings.append("TAAS_API_KEY is not loaded; configure the AI Proxy channel later in the local UI")
    if not env["FASTGPT_API_KEY"] or not env["FASTGPT_APP_ID"]:
        warnings.append("FastGPT local API key/app id are not loaded; API smoke remains blocked")

    report = {
        "status": "ready" if not failures else "blocked",
        "mutated_runtime": False,
        "source": {"tag": lock.get("resolved_tag"), "commit": lock.get("commit")},
        "compose": {"file": str(COMPOSE.relative_to(ROOT)), "valid": config.returncode == 0, "images": images},
        "image_platforms": manifests,
        "running": {"fastgpt": fastgpt_running, "existing_services": expected_existing},
        "taas": {
            "base_url": os.getenv("TAAS_BASE_URL", "https://api-taas.moi.matrixorigin.cn/v1"),
            "llm_model": os.getenv("TAAS_LLM_MODEL", "qwen3.6-flash"),
            "embedding_model": os.getenv("TAAS_EMBEDDING_MODEL", "bge-m3"),
            "api_key_loaded": env["TAAS_API_KEY"],
            "model_egress": "external",
        },
        "local_credentials": {"api_key_loaded": env["FASTGPT_API_KEY"], "app_id_loaded": env["FASTGPT_APP_ID"]},
        "warnings": warnings,
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def api_request(base_url: str, path: str, api_key: str, *, body: Any = None, multipart: tuple[Path, dict[str, Any]] | None = None) -> Any:
    headers = {"Authorization": f"Bearer {api_key}"}
    payload: bytes | None = None
    if multipart:
        file_path, data = multipart
        boundary = f"----moi-fastgpt-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"data\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(data)}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_path.name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        payload = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url.rstrip('/')}{path}", data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise ContractError(f"{path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ContractError(f"{path} is unreachable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ContractError(f"{path} timed out after 60s") from exc
    if isinstance(result, dict) and result.get("code") not in (None, 200):
        raise ContractError(f"{path} returned API code {result.get('code')}: {result.get('message')}")
    return result.get("data", result) if isinstance(result, dict) else result


def validate_local_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ContractError("FASTGPT_BASE_URL must target localhost; cloud endpoints are refused")
    return value.rstrip("/")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.lower() in {"key", "api_key", "authorization"} else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def write_smoke_result(output_dir: Path, result: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=False)
    output = output_dir / "smoke-result.json"
    encoded = json.dumps(redact(result), ensure_ascii=False, indent=2).encode()
    output.write_bytes(encoded)
    output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(encoded).hexdigest() + "  smoke-result.json\n",
        encoding="utf-8",
    )
    return output


def provider(args: argparse.Namespace) -> int:
    contract = load_json(CONTRACTS)["provider_channel_api"]
    profile = PROVIDER_PROFILES[args.provider]
    if not args.execute:
        print(json.dumps({"selected_provider": args.provider, "profile": profile, "contract": contract}, ensure_ascii=False, indent=2))
        print("Dry run only. Pass --execute after MaxKB is stopped and FastGPT is started.", file=sys.stderr)
        return 0

    running = run(["docker", "ps", "--format", "{{.Names}}"])
    if running.returncode:
        raise ContractError(f"cannot inspect Docker: {running.stderr.strip()}")
    names = running.stdout.splitlines()
    if any("maxkb" in name.lower() for name in names):
        raise ContractError("MaxKB is still running; refusing to consume the serial competitor window")
    for required in ("fastgpt-app", "fastgpt-aiproxy"):
        if required not in names:
            raise ContractError(f"required container is not running: {required}")

    prefix = profile["env_prefix"]
    provider_key = os.getenv(f"{prefix}_API_KEY", "").strip()
    if not provider_key or provider_key.startswith("<"):
        raise ContractError(f"{prefix}_API_KEY must be loaded before provider --execute")

    inspect = run([
        "docker", "inspect", "fastgpt-aiproxy", "--format", "{{json .Config.Env}}"
    ])
    if inspect.returncode:
        raise ContractError(f"cannot inspect fastgpt-aiproxy: {inspect.stderr.strip()}")
    container_env = json.loads(inspect.stdout)
    admin_key = next((item.split("=", 1)[1] for item in container_env if item.startswith("ADMIN_KEY=")), "")
    if not admin_key:
        raise ContractError("fastgpt-aiproxy has no ADMIN_KEY")

    create = dict(contract["create"]["payload"])
    reranker_model = os.getenv(f"{prefix}_RERANKER_MODEL", profile.get("reranker_model", "")).strip()
    models = [
        os.getenv(f"{prefix}_LLM_MODEL", profile["llm_model"]),
        os.getenv(f"{prefix}_EMBEDDING_MODEL", profile["embedding_model"]),
    ]
    if reranker_model:
        models.append(reranker_model)
    create.update({
        "name": os.getenv(f"{prefix}_CHANNEL_NAME", profile["channel_name"]),
        "base_url": os.getenv(f"{prefix}_BASE_URL", profile["base_url"]).rstrip("/"),
        "models": models,
        "key": provider_key,
    })
    request_input = json.dumps({"adminKey": admin_key, "channel": create})
    node_program = r"""
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const base = 'http://fastgpt-aiproxy:3000';
async function request(path, options = {}) {
  const response = await fetch(base + path, {
    ...options,
    headers: {
      Authorization: `Bearer ${input.adminKey}`,
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  });
  const text = await response.text();
  let payload;
  try { payload = JSON.parse(text); } catch { payload = { message: text }; }
  if (!response.ok || payload.success === false) {
    throw new Error(`${options.method || 'GET'} ${path}: HTTP ${response.status} ${payload.message || text}`);
  }
  return payload.data;
}
(async () => {
  let channels = await request('/api/channels/all');
  let matches = channels.filter((item) => item.name === input.channel.name);
  if (matches.length > 1) throw new Error(`duplicate channels named ${input.channel.name}`);
  let created = false;
  if (matches.length === 0) {
    await request('/api/channel/', { method: 'POST', body: JSON.stringify(input.channel) });
    created = true;
    channels = await request('/api/channels/all');
    matches = channels.filter((item) => item.name === input.channel.name);
  }
  if (matches.length !== 1) throw new Error('created channel was not returned by /api/channels/all');
  const channel = matches[0];
  const expectedModels = [...input.channel.models].sort().join(',');
  const actualModels = [...(channel.models || [])].sort().join(',');
  if (Number(channel.type) !== Number(input.channel.type) ||
      String(channel.base_url || '').replace(/\/$/, '') !== input.channel.base_url.replace(/\/$/, '') ||
      actualModels !== expectedModels) {
    throw new Error('existing channel differs from requested type/base_url/models; refusing to overwrite it');
  }
  const test = await request(`/api/channel/${channel.id}/test?return_success=true&success_body=false&stream=false`);
  process.stdout.write(JSON.stringify({
    created,
    channel: { id: channel.id, name: channel.name, type: channel.type, base_url: channel.base_url, models: channel.models },
    test
  }));
})().catch((error) => { process.stderr.write(error.message); process.exit(1); });
"""
    result = subprocess.run(
        ["docker", "exec", "-i", "fastgpt-app", "node", "-e", node_program],
        cwd=ROOT,
        text=True,
        input=request_input,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ContractError(f"provider create/list/test failed: {result.stderr.strip()[:1500]}")
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("provider verifier returned invalid JSON") from exc
    print(json.dumps(redact(output), ensure_ascii=False, indent=2))
    return 0


def smoke(args: argparse.Namespace) -> int:
    if not args.execute:
        print(json.dumps(load_json(CONTRACTS), ensure_ascii=False, indent=2))
        print("Dry run only. Pass --execute after FastGPT is started and local credentials are loaded.", file=sys.stderr)
        return 0

    base_url = validate_local_url(os.getenv("FASTGPT_BASE_URL", "http://127.0.0.1:3000"))
    api_key = os.getenv("FASTGPT_API_KEY", "").strip()
    app_id = os.getenv("FASTGPT_APP_ID", "").strip()
    if not api_key or not app_id:
        raise ContractError("FASTGPT_API_KEY and FASTGPT_APP_ID are required for --execute")
    source_dir = (ROOT / os.getenv("FASTGPT_SMOKE_SOURCE_DIR", "local-rag-platforms/fixtures/smoke")).resolve()
    if not source_dir.is_dir():
        raise ContractError(f"smoke source directory does not exist: {source_dir}")

    output_dir = RUNTIME / "logs" / f"smoke-contract-{time.strftime('%Y%m%d-%H%M%S')}"
    result: dict[str, Any] = {
        "system_id": "fastgpt_local",
        "deployment_mode": "self_hosted",
        "platform": "linux/arm64",
        "version": "v4.15.6",
        "image_digest": None,
        "model_egress": "external",
        "service_status": "error",
        "ingest_status": "error",
        "native_status": "error",
        "retrieval_status": "error",
        "blocked_reason": None,
        "artifacts": [str((output_dir / "smoke-result.json").relative_to(ROOT))],
        "details": {"runtime_image": "ghcr.io/labring/fastgpt:v4.15.4"},
    }
    stage = "service"
    dataset_id: str | None = None
    try:
        dataset = api_request(base_url, "/api/core/dataset/create", api_key, body={
            "parentId": None,
            "type": "dataset",
            "name": f"moi-fastgpt-smoke-{time.strftime('%Y%m%d-%H%M%S')}",
            "intro": "MOI local RAG FastGPT smoke",
            "avatar": "",
            "vectorModel": os.getenv("TAAS_EMBEDDING_MODEL", "bge-m3"),
            "agentModel": os.getenv("TAAS_LLM_MODEL", "qwen3.6-flash"),
        })
        dataset_id = dataset if isinstance(dataset, str) else dataset.get("datasetId") or dataset.get("id")
        if not dataset_id:
            raise ContractError("create dataset response did not contain a dataset id")
        result["service_status"] = "ready"
        result["details"]["dataset_id"] = dataset_id

        stage = "ingest"
        uploads = []
        for path in sorted(source_dir.iterdir()):
            if not path.is_file() or path.name.startswith(".") or path.suffix.lower() in {".json", ".jsonl"}:
                continue
            response = api_request(base_url, "/api/core/dataset/collection/create/localFile", api_key, multipart=(path, {
                "datasetId": dataset_id,
                "parentId": None,
                "trainingType": "chunk",
                "chunkSize": 512,
                "chunkSplitter": "",
                "qaPrompt": "",
                "metadata": {"benchmark": "moi-local-rag"},
            }))
            uploads.append({"file": path.name, "collectionId": response.get("collectionId") if isinstance(response, dict) else None})
        if not uploads:
            raise ContractError("no supported smoke documents were found")

        wait_seconds = int(os.getenv("FASTGPT_SMOKE_WAIT_SECONDS", "300"))
        deadline = time.monotonic() + wait_seconds
        collections: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            listing = api_request(base_url, "/api/core/dataset/collection/listV2", api_key, body={
                "offset": 0, "pageSize": 30, "datasetId": dataset_id, "parentId": None, "searchText": ""
            })
            collections = listing.get("list", []) if isinstance(listing, dict) else []
            if collections and all(
                item.get("trainingAmount", 0) == 0
                and item.get("activeTrainingAmount", 0) == 0
                and item.get("finalErrorAmount", 0) == 0
                and not item.get("hasError", False)
                for item in collections
            ):
                break
            if any(item.get("hasError", False) or item.get("finalErrorAmount", 0) for item in collections):
                raise ContractError("one or more FastGPT collections failed indexing")
            time.sleep(2)
        else:
            raise ContractError(f"collection indexing did not finish within {wait_seconds}s")
        result["ingest_status"] = "ready"
        result["details"].update({"uploads": uploads, "collection_count": len(collections)})

        stage = "retrieval"
        query = os.getenv("FASTGPT_SMOKE_RETRIEVAL_QUERY", "local RAG smoke")
        retrieval = api_request(base_url, "/api/core/dataset/searchTest", api_key, body={
            "datasetId": dataset_id,
            "text": query,
            "limit": 5000,
            "similarity": 0,
            "searchMode": "embedding",
            "usingReRank": False,
            "datasetSearchUsingExtensionQuery": False,
        })
        hits = retrieval.get("list", []) if isinstance(retrieval, dict) else []
        if not hits:
            raise ContractError("direct retrieval returned no hits")
        result["retrieval_status"] = "success"
        result["details"].update({"retrieval_hit_count": len(hits), "retrieval": retrieval})

        stage = "native"
        question = os.getenv("FASTGPT_SMOKE_QUESTION", "What facts are stated in the local smoke documents?")
        native = api_request(base_url, "/api/v1/chat/completions", api_key, body={
            "appId": app_id,
            "chatId": str(uuid.uuid4()),
            "stream": False,
            "detail": True,
            "messages": [{"role": "user", "content": question}],
        })
        choices = native.get("choices", []) if isinstance(native, dict) else []
        answer = choices[0].get("message", {}).get("content", "") if choices else ""
        if not answer.strip():
            raise ContractError("native QA returned no answer")
        result["native_status"] = "success"
        result["details"]["native"] = native
    except ContractError as exc:
        failure_kind = "timeout" if "timed out" in str(exc).lower() else "request_error"
        result["blocked_reason"] = f"{stage.upper()}_SMOKE_{failure_kind.upper()}"
        result["details"]["failed_stage"] = stage
        result["details"]["failure_kind"] = failure_kind

    output = write_smoke_result(output_dir, result)
    success = all(result[key] in {"ready", "success"} for key in (
        "service_status", "ingest_status", "retrieval_status", "native_status"
    ))
    print(json.dumps({
        "status": "success" if success else "error",
        "artifact": str(output.relative_to(ROOT)),
        "dataset_id": dataset_id,
        "blocked_reason": result["blocked_reason"],
    }, indent=2))
    return 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="read-only source/compose/ARM64/runtime check")
    smoke_parser = subparsers.add_parser("smoke", help="print the contract, or execute it explicitly")
    smoke_parser.add_argument("--execute", action="store_true", help="create a local dataset and run smoke APIs")
    provider_parser = subparsers.add_parser("provider", help="print or execute AIProxy channel create/list/test")
    provider_parser.add_argument("--provider", choices=sorted(PROVIDER_PROFILES), default="taas")
    provider_parser.add_argument("--execute", action="store_true", help="create or validate the selected provider channel")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            return preflight()
        if args.command == "provider":
            return provider(args)
        return smoke(args)
    except (ContractError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
