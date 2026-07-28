#!/usr/bin/env python3
"""Run the configured local Matrixflow extraction workflow over SROIE PDFs.

The workflow's stored default_values remain authoritative. For each PDF this
runner uploads one file and overrides only the source_ref form field.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_INPUT_DIR = Path(
    "/Users/wangyaqi/Documents/cursor_project/agent评估/"
    "moi-benchmark/document-extracting/datasets/SROIE2019/train/pdf"
)
DEFAULT_RUN_DIR = Path(
    "/Users/wangyaqi/Documents/cursor_project/agent评估/"
    "moi-benchmark/document-extracting/runs/"
    "matrixflow-sroie2019-workflow-2b084712"
)
DEFAULT_BACKEND_URL = "http://127.0.0.1:18000"
DEFAULT_CATALOG_URL = "http://127.0.0.1:18081"
DEFAULT_WORKSPACE_ID = "abe9f340-ab88-0d9c-5773-837e70c25c48"
DEFAULT_WORKFLOW_ID = "2b084712-3ed2-4034-965b-8e2657693359"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class APIHTTPError(RuntimeError):
    def __init__(self, method: str, url: str, status_code: int, body: str) -> None:
        self.status_code = status_code
        super().__init__(
            f"{method} {url} returned HTTP {status_code}: {body}"
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def unwrap(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    code = payload.get("code")
    if code not in (None, 0, "0", "OK"):
        message = payload.get("message") or payload.get("msg") or payload
        raise RuntimeError(f"API error code={code!r}: {message}")
    return payload.get("data", payload)


def api_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float,
    **kwargs: Any,
) -> Any:
    response = session.request(method, url, timeout=timeout, **kwargs)
    if not response.ok:
        body = response.text[:2000].replace("\n", " ")
        raise APIHTTPError(method, url, response.status_code, body)
    try:
        return unwrap(response.json())
    except ValueError as exc:
        raise RuntimeError(f"{method} {url} returned non-JSON data") from exc


def authenticate(
    backend: requests.Session,
    catalog: requests.Session,
    backend_url: str,
    workspace_id: str,
    timeout: float,
    *,
    force_login: bool = False,
) -> None:
    access_token = (
        "" if force_login else os.environ.get("MOI_ACCESS_TOKEN", "").strip()
    )
    api_key = os.environ.get("MOI_API_KEY", "").strip()
    if force_login or not access_token or not api_key:
        if force_login:
            backend.headers.pop("Authorization", None)
        mobile = os.environ.get("MOI_LOGIN_MOBILE", "13800000000")
        password = os.environ.get("MOI_LOGIN_PASSWORD", "admin")
        login_data = api_json(
            backend,
            "POST",
            f"{backend_url}/newmoi/login",
            timeout=timeout,
            json={
                "mobile_number": mobile,
                "password": password,
                "agreed_to_policy": True,
            },
        )
        if not isinstance(login_data, dict):
            raise RuntimeError("local login returned an invalid response")
        access_token = str(login_data.get("access_token", "")).strip()
        api_key = api_key or str(login_data.get("api_key", "")).strip()
    if not access_token:
        raise RuntimeError("no access token; set MOI_ACCESS_TOKEN or login variables")
    if not api_key:
        raise RuntimeError("no API key; set MOI_API_KEY or login variables")
    backend.headers.update(
        {
            "Authorization": f"Bearer {access_token}",
            "X-Workspace-ID": workspace_id,
        }
    )
    catalog.headers.update({"X-API-Key": api_key})


def backend_api_json(
    backend: requests.Session,
    catalog: requests.Session,
    args: argparse.Namespace,
    method: str,
    url: str,
    *,
    timeout: float,
    **kwargs: Any,
) -> Any:
    try:
        return api_json(
            backend, method, url, timeout=timeout, **kwargs
        )
    except APIHTTPError as exc:
        if exc.status_code != 401:
            raise
        print("    backend token expired; logging in again and retrying", flush=True)
        authenticate(
            backend,
            catalog,
            args.backend_url,
            args.workspace_id,
            args.request_timeout,
            force_login=True,
        )
        return api_json(
            backend, method, url, timeout=timeout, **kwargs
        )


def workflow_url(args: argparse.Namespace) -> str:
    return (
        f"{args.backend_url}/newmoi/workflow/v2/workflow-apps/"
        f"{args.workflow_id}"
    )


def load_workflow(
    backend: requests.Session,
    catalog: requests.Session,
    args: argparse.Namespace,
) -> dict[str, Any]:
    data = backend_api_json(
        backend,
        catalog,
        args,
        "GET",
        workflow_url(args),
        timeout=args.request_timeout,
    )
    workflow = data.get("workflow", data) if isinstance(data, dict) else data
    if not isinstance(workflow, dict) or not workflow.get("id"):
        raise RuntimeError(f"workflow lookup returned invalid data: {data!r}")
    if str(workflow.get("status", "")).lower() == "disabled":
        raise RuntimeError("workflow is disabled")
    return workflow


def form_fields(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    runtime_fields = workflow.get("runtime_fields") or {}
    if isinstance(runtime_fields, str):
        runtime_fields = json.loads(runtime_fields)
    fields = runtime_fields.get("fields", []) if isinstance(runtime_fields, dict) else []
    return [field for field in fields if isinstance(field, dict)]


def parse_values_json(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    stripped = raw.strip()
    if stripped.startswith("{"):
        value = json.loads(stripped)
    else:
        candidate = Path(raw).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(
                f"--values-json is neither a JSON object nor a file: {candidate}"
            )
        value = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("--values-json must contain a JSON object")
    return value


def validate_workflow_defaults(
    workflow: dict[str, Any], overrides: dict[str, Any]
) -> None:
    defaults = workflow.get("default_values") or {}
    if isinstance(defaults, str):
        defaults = json.loads(defaults)
    defaults = defaults if isinstance(defaults, dict) else {}
    supplied = {**defaults, **overrides}
    missing = []
    for field in form_fields(workflow):
        field_id = str(field.get("field_id", "")).strip()
        if (
            field.get("required")
            and field_id
            and field_id != "source_ref"
            and supplied.get(field_id) in (None, "", [], {})
        ):
            missing.append(field_id)
    if missing:
        joined = ", ".join(sorted(missing))
        raise RuntimeError(
            "workflow has required fields without stored defaults: "
            f"{joined}. Supply them with --values-json."
        )


def upload_file(
    catalog: requests.Session, args: argparse.Namespace, path: Path
) -> dict[str, Any]:
    mime = mimetypes.guess_type(path.name)[0] or "application/pdf"
    url = (
        f"{args.catalog_url}/api/v1/workspaces/{args.workspace_id}/files"
    )
    with path.open("rb") as stream:
        data = api_json(
            catalog,
            "POST",
            url,
            timeout=args.upload_timeout,
            files={"file": (path.name, stream, mime)},
        )
    if not isinstance(data, dict) or not data.get("file_id"):
        raise RuntimeError(f"upload returned no file_id: {data!r}")
    return data


def source_ref(path: Path, file_id: str) -> dict[str, Any]:
    return {
        "display_location": path.name,
        "file_id": file_id,
        "file_name": path.name,
        "ids": [file_id],
        "kind": "file",
        "location": path.name,
        "resource_type": "file",
    }


def create_execution(
    backend: requests.Session,
    catalog: requests.Session,
    args: argparse.Namespace,
    values: dict[str, Any],
) -> dict[str, Any]:
    data = backend_api_json(
        backend,
        catalog,
        args,
        "POST",
        f"{workflow_url(args)}/executions",
        timeout=args.request_timeout,
        json={"values": values, "trigger_now": True},
    )
    run = data.get("workflow_run", data) if isinstance(data, dict) else data
    if not isinstance(run, dict) or not run.get("execution_id"):
        raise RuntimeError(f"execution creation returned no execution_id: {data!r}")
    return run


def wait_execution(
    backend: requests.Session,
    catalog: requests.Session,
    args: argparse.Namespace,
    execution_id: str,
    case_dir: Path,
) -> dict[str, Any]:
    url = f"{workflow_url(args)}/executions/{execution_id}/result"
    deadline = time.monotonic() + args.run_timeout
    previous = ""
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"execution {execution_id} exceeded {args.run_timeout:.0f}s"
            )
        data = backend_api_json(
            backend,
            catalog,
            args,
            "GET",
            url,
            timeout=args.request_timeout,
        )
        result = data.get("result", data) if isinstance(data, dict) else data
        if not isinstance(result, dict):
            raise RuntimeError(f"execution result is invalid: {data!r}")
        write_json(case_dir / "execution_result.json", result)
        status = str(result.get("status", "")).lower()
        if status != previous:
            print(f"    execution={execution_id} status={status or 'unknown'}")
            previous = status
        if status in TERMINAL_STATUSES:
            return result
        time.sleep(args.poll_interval)


def parse_case_result(result: dict[str, Any]) -> Any:
    value = result.get("case_result")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def result_file_refs(value: Any) -> list[tuple[str, str]]:
    """Return unique (file_id, file_name) pairs from common sink result shapes."""
    refs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(file_id: Any, file_name: Any = "") -> None:
        file_id_text = str(file_id or "").strip()
        if file_id_text and file_id_text not in seen:
            seen.add(file_id_text)
            refs.append((file_id_text, str(file_name or "").strip()))

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            add(node.get("file_id"), node.get("file_name"))
            ids = node.get("file_ids")
            names = node.get("file_names")
            if isinstance(ids, list):
                for index, file_id in enumerate(ids):
                    name = names[index] if isinstance(names, list) and index < len(names) else ""
                    add(file_id, name)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return refs


def safe_output_name(name: str, fallback: str) -> str:
    candidate = Path(name).name.strip()
    if candidate in {"", ".", ".."}:
        candidate = fallback
    return candidate


def download_result(
    catalog: requests.Session,
    args: argparse.Namespace,
    file_id: str,
    target: Path,
) -> None:
    url = (
        f"{args.catalog_url}/api/v1/workspaces/{args.workspace_id}/files/"
        f"{file_id}/download"
    )
    with catalog.get(url, timeout=args.download_timeout, stream=True) as response:
        if not response.ok:
            body = response.text[:2000].replace("\n", " ")
            raise RuntimeError(
                f"GET {url} returned HTTP {response.status_code}: {body}"
            )
        tmp = target.with_name(f".{target.name}.tmp")
        with tmp.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    stream.write(chunk)
        tmp.replace(target)


def case_name(path: Path) -> str:
    return "".join(
        "_" if char in {"/", "\\", "\0"} or ord(char) < 32 else char
        for char in path.stem
    ).strip(" .") or "unnamed"


def run_case(
    backend: requests.Session,
    catalog: requests.Session,
    args: argparse.Namespace,
    path: Path,
    overrides: dict[str, Any],
    index: int,
    total: int,
) -> dict[str, Any]:
    case_dir = args.run_dir / "cases" / case_name(path)
    status_path = case_dir / "status.json"
    if not args.force and status_path.is_file():
        previous = json.loads(status_path.read_text(encoding="utf-8"))
        if previous.get("status") == "completed":
            print(f"[{index}/{total}] SKIP {path.name}")
            return previous

    case_dir.mkdir(parents=True, exist_ok=True)
    status: dict[str, Any] = {
        "file_name": path.name,
        "source_path": str(path),
        "status": "running",
        "started_at": now_iso(),
    }
    write_json(status_path, status)
    print(f"[{index}/{total}] RUN  {path.name}", flush=True)
    try:
        uploaded = upload_file(catalog, args, path)
        default_source_ref = getattr(args, "default_source_ref", {})
        if not isinstance(default_source_ref, dict):
            default_source_ref = {}
        source_value = {
            **default_source_ref,
            **source_ref(path, uploaded["file_id"]),
        }
        values = {**overrides, "source_ref": source_value}
        write_json(
            case_dir / "request.json",
            {
                "workflow_id": args.workflow_id,
                "uploaded_file": uploaded,
                "values": values,
                "note": "workflow default_values are merged by the backend",
            },
        )
        run = create_execution(backend, catalog, args, values)
        write_json(case_dir / "execution_created.json", run)
        result = wait_execution(
            backend, catalog, args, str(run["execution_id"]), case_dir
        )
        terminal_status = str(result.get("status", "")).lower()
        if terminal_status != "completed":
            failure = (
                result.get("failure")
                or result.get("case_error")
                or f"execution ended with {terminal_status}"
            )
            raise RuntimeError(str(failure))

        extracted = parse_case_result(result)
        write_json(case_dir / "case_result.json", extracted)
        downloads = []
        for number, (file_id, file_name) in enumerate(
            result_file_refs(extracted), 1
        ):
            fallback = f"{path.stem}.result-{number}.json"
            output_name = safe_output_name(file_name, fallback)
            target = case_dir / output_name
            download_result(catalog, args, file_id, target)
            downloads.append(
                {"file_id": file_id, "file_name": output_name, "path": str(target)}
            )

        status.update(
            {
                "status": "completed",
                "completed_at": now_iso(),
                "execution_id": run["execution_id"],
                "uploaded_file_id": uploaded["file_id"],
                "downloads": downloads,
            }
        )
        write_json(status_path, status)
        print(f"[{index}/{total}] OK   {path.name}", flush=True)
        return status
    except Exception as exc:
        status.update(
            {
                "status": "failed",
                "completed_at": now_iso(),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        write_json(status_path, status)
        print(f"[{index}/{total}] FAIL {path.name}: {exc}", file=sys.stderr, flush=True)
        return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the configured Matrixflow extraction workflow on SROIE PDFs."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--catalog-url", default=DEFAULT_CATALOG_URL)
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    parser.add_argument("--workflow-id", default=DEFAULT_WORKFLOW_ID)
    parser.add_argument(
        "--values-json",
        default="",
        help="JSON object or JSON file with extra form-field overrides",
    )
    parser.add_argument("--limit", type=int, default=0, help="0 means all PDFs")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--continue-on-error", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument("--upload-timeout", type=float, default=300.0)
    parser.add_argument("--download-timeout", type=float, default=300.0)
    parser.add_argument("--run-timeout", type=float, default=3600.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.backend_url = args.backend_url.rstrip("/")
    args.catalog_url = args.catalog_url.rstrip("/")
    args.input_dir = args.input_dir.expanduser().resolve()
    args.run_dir = args.run_dir.expanduser().resolve()
    if not args.input_dir.is_dir():
        raise SystemExit(f"input directory does not exist: {args.input_dir}")

    files = sorted(args.input_dir.glob("*.pdf"), key=lambda path: path.name)
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"no PDF files found in {args.input_dir}")
    overrides = parse_values_json(args.values_json)

    config = {
        "created_at": now_iso(),
        "input_dir": str(args.input_dir),
        "run_dir": str(args.run_dir),
        "backend_url": args.backend_url,
        "catalog_url": args.catalog_url,
        "workspace_id": args.workspace_id,
        "workflow_id": args.workflow_id,
        "file_count": len(files),
        "files": [path.name for path in files],
        "explicit_value_overrides": overrides,
    }
    if args.dry_run:
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0

    args.run_dir.mkdir(parents=True, exist_ok=True)
    backend = requests.Session()
    catalog = requests.Session()
    backend.trust_env = False
    catalog.trust_env = False
    authenticate(
        backend,
        catalog,
        args.backend_url,
        args.workspace_id,
        args.request_timeout,
    )
    workflow = load_workflow(backend, catalog, args)
    validate_workflow_defaults(workflow, overrides)
    default_values = workflow.get("default_values") or {}
    if isinstance(default_values, str):
        default_values = json.loads(default_values)
    args.default_source_ref = (
        default_values.get("source_ref", {})
        if isinstance(default_values, dict)
        else {}
    )
    config["workflow"] = {
        "id": workflow.get("id"),
        "name": workflow.get("name"),
        "status": workflow.get("status"),
        "runtime_field_ids": [
            field.get("field_id") for field in form_fields(workflow)
        ],
        "default_value_field_ids": sorted(
            (workflow.get("default_values") or {}).keys()
        )
        if isinstance(workflow.get("default_values"), dict)
        else [],
    }
    write_json(args.run_dir / "config.json", config)

    results = []
    for index, path in enumerate(files, 1):
        result = run_case(
            backend, catalog, args, path, overrides, index, len(files)
        )
        results.append(result)
        append_jsonl(args.run_dir / "events.jsonl", {"at": now_iso(), **result})
        summary = {
            "updated_at": now_iso(),
            "total_selected": len(files),
            "processed": len(results),
            "completed": sum(item["status"] == "completed" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
            "pending": len(files) - len(results),
            "cases": results,
        }
        write_json(args.run_dir / "summary.json", summary)
        if result["status"] == "failed" and not args.continue_on_error:
            break

    failed = sum(item["status"] == "failed" for item in results)
    print(
        f"Done: completed={len(results) - failed}, failed={failed}, "
        f"run_dir={args.run_dir}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
