#!/usr/bin/env python3
"""Run all semiconductor private files through Baidu PaddleOCR-VL.

Credentials are read from BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY.
For each successful input, only the final Markdown and JSON results are kept.
Completed cases are skipped when the script is run again.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_INPUT_DIR = Path(
    "/Users/wangyaqi/Documents/cursor_project/agent评估/"
    "moi-benchmark/document-parsing/datasets/半导体场景模拟数据"
)
DEFAULT_RUN_DIR = Path(
    "/Users/wangyaqi/Documents/cursor_project/agent评估/"
    "moi-benchmark/document-parsing/runs/"
    "paddleocr-vl-半导体场景模拟数据"
)
TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
TASK_URL = (
    "https://aip.baidubce.com/rest/2.0/brain/online/v2/"
    "paddle-vl-parser/task"
)
QUERY_URL = f"{TASK_URL}/query"
SUPPORTED_SUFFIXES = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".ofd",
    ".doc",
    ".docx",
    ".txt",
    ".wps",
    ".ppt",
    ".pptx",
}


def stable_id(path: Path, input_dir: Path) -> str:
    relative = path.relative_to(input_dir).as_posix()
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]


def safe_case_name(path: Path, case_id: str) -> str:
    readable = "".join(
        "_" if char in {"/", "\\", "\0"} or ord(char) < 32 else char
        for char in path.name
    ).strip(" .")
    return f"{readable or 'unnamed'}--{case_id}"


def response_json(response: requests.Response, operation: str) -> dict[str, Any]:
    if not response.ok:
        body = response.text[:2000].replace("\n", " ")
        raise RuntimeError(
            f"{operation} returned HTTP {response.status_code}: {body}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{operation} returned non-JSON data") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation} returned invalid JSON: {payload!r}")
    error_code = payload.get("error_code", 0)
    if error_code not in (0, "0", None):
        raise RuntimeError(
            f"{operation} failed with error_code={error_code!r}: "
            f"{payload.get('error_msg') or payload}"
        )
    return payload


def get_access_token(
    session: requests.Session,
    api_key: str,
    secret_key: str,
    request_timeout: float,
) -> str:
    response = session.post(
        TOKEN_URL,
        params={
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": secret_key,
        },
        timeout=request_timeout,
    )
    payload = response_json(response, "access-token request")
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(
            f"access-token response contains no access_token: {payload!r}"
        )
    return token


def submit_task(
    session: requests.Session,
    access_token: str,
    path: Path,
    request_timeout: float,
) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    response = session.post(
        TASK_URL,
        params={"access_token": access_token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "file_data": encoded,
            "file_name": path.name,
            "analysis_chart": "true",
            "merge_tables": "true",
            "relevel_titles": "true",
            "recognize_seal": "true",
            "return_span_boxes": "true",
        },
        timeout=max(request_timeout, 300),
    )
    payload = response_json(response, "task submission")
    result = payload.get("result")
    task_id = result.get("task_id") if isinstance(result, dict) else None
    if not isinstance(task_id, str) or not task_id:
        raise RuntimeError(f"task submission returned no task_id: {payload!r}")
    return task_id


def wait_for_result(
    session: requests.Session,
    access_token: str,
    task_id: str,
    poll_interval: float,
    run_timeout: float,
    request_timeout: float,
) -> tuple[str, str]:
    deadline = time.monotonic() + run_timeout
    previous_status = ""

    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"PaddleOCR-VL task {task_id} exceeded timeout "
                f"{run_timeout:.0f}s"
            )
        response = session.post(
            QUERY_URL,
            params={"access_token": access_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"task_id": task_id},
            timeout=request_timeout,
        )
        payload = response_json(response, "task query")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"task query returned invalid result: {payload!r}")

        status = str(result.get("status", "")).lower()
        if status != previous_status:
            print(f"    status={status or 'unknown'}", flush=True)
            previous_status = status

        if status == "failed":
            raise RuntimeError(
                f"PaddleOCR-VL parsing failed: "
                f"{result.get('task_error') or result}"
            )
        if status == "success":
            markdown_url = result.get("markdown_url")
            parse_result_url = result.get("parse_result_url")
            if not isinstance(markdown_url, str) or not markdown_url:
                raise RuntimeError("successful task has no markdown_url")
            if not isinstance(parse_result_url, str) or not parse_result_url:
                raise RuntimeError("successful task has no parse_result_url")
            return markdown_url, parse_result_url
        if status not in {"pending", "processing", "running"}:
            raise RuntimeError(f"task query returned unknown status: {result!r}")

        time.sleep(poll_interval)


def download_bytes(
    session: requests.Session,
    url: str,
    request_timeout: float,
) -> bytes:
    response = session.get(url, timeout=max(request_timeout, 300))
    response.raise_for_status()
    return response.content


def run_case(
    session: requests.Session,
    access_token: str,
    path: Path,
    input_dir: Path,
    run_dir: Path,
    poll_interval: float,
    run_timeout: float,
    request_timeout: float,
    resume_task_id: str | None = None,
) -> str:
    case_id = stable_id(path, input_dir)
    case_dir = run_dir / safe_case_name(path, case_id)
    if (case_dir / "result.md").is_file() and (
        case_dir / "result.json"
    ).is_file():
        print(f"[skip] {path.name}", flush=True)
        return "skipped"

    if resume_task_id:
        print(f"[resume] {path.name} task_id={resume_task_id}", flush=True)
        task_id = resume_task_id
    else:
        print(f"[run] {path.name}", flush=True)
        task_id = submit_task(session, access_token, path, request_timeout)
    markdown_url, parse_result_url = wait_for_result(
        session,
        access_token,
        task_id,
        poll_interval,
        run_timeout,
        request_timeout,
    )
    markdown = download_bytes(session, markdown_url, request_timeout)
    result_bytes = download_bytes(session, parse_result_url, request_timeout)

    try:
        parsed_result = json.loads(result_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("downloaded parse result is not valid JSON") from exc

    with tempfile.TemporaryDirectory(prefix=".paddleocr-vl-", dir=run_dir) as temp:
        temp_dir = Path(temp)
        (temp_dir / "result.md").write_bytes(markdown)
        (temp_dir / "result.json").write_text(
            json.dumps(parsed_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if case_dir.exists():
            shutil.rmtree(case_dir)
        shutil.move(str(temp_dir), str(case_dir))

    print(f"[done] {path.name}", flush=True)
    return "completed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run semiconductor files through Baidu PaddleOCR-VL."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--run-timeout", type=float, default=7200.0)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument(
        "--max-files",
        type=int,
        help="Only process the first N files; useful for a smoke test.",
    )
    parser.add_argument(
        "--resume-task-id",
        help=(
            "Resume an already-submitted task instead of submitting the "
            "selected input again; requires exactly one selected input file."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("BAIDU_OCR_API_KEY", "").strip()
    secret_key = os.environ.get("BAIDU_OCR_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        print(
            "BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY are required.",
            file=sys.stderr,
        )
        return 2

    input_dir = args.input_dir.expanduser().resolve()
    run_dir = args.run_dir.expanduser().resolve()
    if not input_dir.is_dir():
        print(f"input directory does not exist: {input_dir}", file=sys.stderr)
        return 2

    files = sorted(
        (
            path
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: path.relative_to(input_dir).as_posix(),
    )
    if args.max_files is not None:
        if args.max_files < 1:
            print("--max-files must be at least 1", file=sys.stderr)
            return 2
        files = files[: args.max_files]
    if not files:
        print(f"no supported input files found under {input_dir}", file=sys.stderr)
        return 2
    if args.resume_task_id and len(files) != 1:
        print(
            "--resume-task-id requires exactly one selected input file.",
            file=sys.stderr,
        )
        return 2

    run_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    try:
        access_token = get_access_token(
            session,
            api_key,
            secret_key,
            args.request_timeout,
        )
    except Exception as exc:
        print(f"authentication failed: {exc}", file=sys.stderr)
        return 2

    counts = {"completed": 0, "failed": 0, "skipped": 0}
    for index, path in enumerate(files, start=1):
        print(f"\n[{index}/{len(files)}] {path.name}", flush=True)
        try:
            outcome = run_case(
                session,
                access_token,
                path,
                input_dir,
                run_dir,
                args.poll_interval,
                args.run_timeout,
                args.request_timeout,
                args.resume_task_id if index == 1 else None,
            )
        except Exception as exc:
            print(f"[failed] {path.name}: {exc}", file=sys.stderr, flush=True)
            outcome = "failed"
        counts[outcome] += 1

    print(
        "\nSummary: "
        f"total={len(files)} completed={counts['completed']} "
        f"skipped={counts['skipped']} failed={counts['failed']}",
        flush=True,
    )
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
