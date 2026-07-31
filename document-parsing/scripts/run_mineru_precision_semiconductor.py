#!/usr/bin/env python3
"""Run semiconductor private files through MinerU Precision Extract API.

Only the extracted MinerU result files are retained. ZIP archives, request
metadata, polling responses, status files, and credentials are not persisted.
Completed case directories are skipped when the script is run again.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import time
import zipfile
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
    "mineru-precision-半导体场景模拟数据"
)
API_BASE_URL = "https://mineru.net/api/v4"
SUPPORTED_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}


def stable_id(path: Path, input_dir: Path) -> str:
    relative = path.relative_to(input_dir).as_posix()
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]


def safe_case_name(path: Path, case_id: str) -> str:
    readable = "".join(
        "_" if char in {"/", "\\", "\0"} or ord(char) < 32 else char
        for char in path.name
    ).strip(" .")
    return f"{readable or 'unnamed'}--{case_id}"


def api_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float,
    **kwargs: Any,
) -> dict[str, Any]:
    response = session.request(method, url, timeout=timeout, **kwargs)
    if not response.ok:
        body = response.text[:2000].replace("\n", " ")
        raise RuntimeError(
            f"{method} {url} returned HTTP {response.status_code}: {body}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {url} returned non-JSON data") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{method} {url} returned invalid JSON: {payload!r}")
    if payload.get("code") != 0:
        raise RuntimeError(
            f"MinerU API error code={payload.get('code')!r}: "
            f"{payload.get('msg') or payload}"
        )
    return payload


def request_upload_url(
    session: requests.Session,
    headers: dict[str, str],
    path: Path,
    data_id: str,
    model_version: str,
    language: str,
    request_timeout: float,
) -> tuple[str, str]:
    payload = api_json(
        session,
        "POST",
        f"{API_BASE_URL}/file-urls/batch",
        timeout=request_timeout,
        headers=headers,
        json={
            "files": [{"name": path.name, "data_id": data_id}],
            "model_version": model_version,
            "language": language,
            "enable_table": True,
            "enable_formula": True,
        },
    )
    data = payload.get("data")
    if not isinstance(data, dict) or not data.get("batch_id"):
        raise RuntimeError(f"upload request returned no batch_id: {payload!r}")
    file_urls = data.get("file_urls")
    if not isinstance(file_urls, list) or len(file_urls) != 1:
        raise RuntimeError(f"upload request returned invalid file_urls: {payload!r}")
    upload_item = file_urls[0]
    if isinstance(upload_item, dict):
        upload_url = upload_item.get("url") or upload_item.get("file_url")
    else:
        upload_url = upload_item
    if not isinstance(upload_url, str) or not upload_url:
        raise RuntimeError(f"upload request returned no upload URL: {payload!r}")
    return str(data["batch_id"]), upload_url


def upload_file(
    session: requests.Session,
    upload_url: str,
    path: Path,
    request_timeout: float,
) -> None:
    with path.open("rb") as stream:
        response = session.put(
            upload_url,
            data=stream,
            timeout=max(request_timeout, 300),
        )
    if not response.ok:
        body = response.text[:1000].replace("\n", " ")
        raise RuntimeError(
            f"PUT signed upload URL returned HTTP {response.status_code}: {body}"
        )


def wait_for_result(
    session: requests.Session,
    headers: dict[str, str],
    batch_id: str,
    poll_interval: float,
    run_timeout: float,
    request_timeout: float,
) -> str:
    deadline = time.monotonic() + run_timeout
    query_url = f"{API_BASE_URL}/extract-results/batch/{batch_id}"
    previous_state = ""

    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"MinerU batch {batch_id} exceeded timeout {run_timeout:.0f}s"
            )
        payload = api_json(
            session,
            "GET",
            query_url,
            timeout=request_timeout,
            headers=headers,
        )
        data = payload.get("data")
        results = data.get("extract_result") if isinstance(data, dict) else None
        if not isinstance(results, list) or len(results) != 1:
            raise RuntimeError(f"invalid batch query response: {payload!r}")
        result = results[0]
        if not isinstance(result, dict):
            raise RuntimeError(f"invalid extract result: {result!r}")
        state = str(result.get("state", "")).lower()
        if state != previous_state:
            print(f"    state={state or 'unknown'}", flush=True)
            previous_state = state
        if state == "failed":
            raise RuntimeError(
                f"MinerU parsing failed: {result.get('err_msg') or result}"
            )
        if state == "done":
            result_url = result.get("full_zip_url")
            if not isinstance(result_url, str) or not result_url:
                raise RuntimeError("completed MinerU result has no full_zip_url")
            return result_url
        time.sleep(poll_interval)


def download_file(
    session: requests.Session,
    url: str,
    target: Path,
    request_timeout: float,
) -> None:
    with session.get(
        url,
        stream=True,
        timeout=max(request_timeout, 300),
    ) as response:
        response.raise_for_status()
        with target.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    stream.write(chunk)


def extract_zip_safely(archive: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    resolved_output = output_dir.resolve()
    with zipfile.ZipFile(archive) as zip_file:
        for member in zip_file.infolist():
            target = (output_dir / member.filename).resolve()
            if target != resolved_output and resolved_output not in target.parents:
                raise RuntimeError(
                    f"unsafe ZIP member path rejected: {member.filename!r}"
                )
        zip_file.extractall(output_dir)


def run_case(
    session: requests.Session,
    headers: dict[str, str],
    path: Path,
    input_dir: Path,
    run_dir: Path,
    model_version: str,
    language: str,
    poll_interval: float,
    run_timeout: float,
    request_timeout: float,
) -> str:
    case_id = stable_id(path, input_dir)
    case_dir = run_dir / safe_case_name(path, case_id)
    if case_dir.is_dir():
        print(f"[skip] {path.name}", flush=True)
        return "skipped"

    print(f"[run] {path.name}", flush=True)
    batch_id, upload_url = request_upload_url(
        session,
        headers,
        path,
        case_id,
        model_version,
        language,
        request_timeout,
    )
    upload_file(session, upload_url, path, request_timeout)
    result_url = wait_for_result(
        session,
        headers,
        batch_id,
        poll_interval,
        run_timeout,
        request_timeout,
    )

    # Keep the ZIP and extraction directory only inside a temporary directory.
    # Move the extracted result into place after every operation succeeds.
    with tempfile.TemporaryDirectory(prefix=".mineru-", dir=run_dir) as temporary:
        temporary_dir = Path(temporary)
        archive = temporary_dir / "result.zip"
        extracted = temporary_dir / "extracted"
        download_file(session, result_url, archive, request_timeout)
        extract_zip_safely(archive, extracted)
        shutil.move(str(extracted), str(case_dir))

    print(f"[done] {path.name}", flush=True)
    return "completed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run semiconductor private files through MinerU Precision API."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument(
        "--model-version",
        choices=("pipeline", "vlm"),
        default="vlm",
    )
    parser.add_argument("--language", default="ch")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--run-timeout", type=float, default=7200.0)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument(
        "--max-files",
        type=int,
        help="Only process the first N files; useful for a smoke test.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get("MINERU_TOKEN", "").strip()
    if not token:
        print(
            "MINERU_TOKEN is required. Export it before running the script.",
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

    run_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    counts = {"completed": 0, "failed": 0, "skipped": 0}
    for index, path in enumerate(files, start=1):
        print(f"\n[{index}/{len(files)}] {path.name}", flush=True)
        try:
            outcome = run_case(
                session,
                headers,
                path,
                input_dir,
                run_dir,
                args.model_version,
                args.language,
                args.poll_interval,
                args.run_timeout,
                args.request_timeout,
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
