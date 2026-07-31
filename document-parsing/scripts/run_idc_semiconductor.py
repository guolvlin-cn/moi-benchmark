#!/usr/bin/env python3
"""Run the semiconductor private dataset through the Shanghai IDC parser.

Each input is submitted as an independent job. Only the final ZIP is retained.
Existing ZIPs are skipped, so the script can be safely run again.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_INPUT_DIR = Path(
    "/Users/wangyaqi/Documents/cursor_project/agent评估/"
    "moi-benchmark/document-parsing/datasets/半导体场景模拟数据"
)
DEFAULT_OUTPUT_DIR = Path(
    "/Users/wangyaqi/Documents/cursor_project/agent评估/"
    "moi-benchmark/document-parsing/runs/半导体场景私有数据集-idc"
)
DEFAULT_DEMO_SCRIPT = Path(
    "/Users/wangyaqi/Documents/cursor_project/parse-reorg/src/demo_onebyone.py"
)
DEFAULT_BASE_URL = "https://shanghai.idc.matrixorigin.cn:30046/"
SUPPORTED_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".wps",
    ".ofd",
    ".eml",
    ".msg",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
}

OPTIONS: dict[str, Any] = {
    "enable_parser_pipeline": True,
    "debug_enabled": True,
    "max_workers": 16,
    "pptx_normalize_before_pdf": False,
    "save_table_image_file": False,
    "cast_table_as_image": False,
    "enable_table_html_regeneration": True,
    "enable_table_embedded_image_extraction": True,
    "enable_merged_table_split": True,
    "enable_cross_page_table_merge": True,
    "unmerge_table_cells": False,
    "enable_table_inline_image_text": False,
    "enable_table_image_in_markdown": False,
    "enable_vlm_title_detection": True,
    "enable_vlm_header_footer_detection": True,
    "enable_formula_repair": True,
    "enable_list_marker_repair": True,
    "enable_indent_detection": True,
    "enable_fragment_merge": True,
    "enable_image_fragment_merge": True,
    "enable_strikethrough_detection": False,
    "ppt_title_detection_mode": "block",
    "enable_image_annotation_text": False,
    "enable_decorative_icon_detection": True,
    "flowchart_table_strategy": "table",
    "indent_spaces_per_level": 2,
    "vlm_model": None,
    "header_footer_similarity_threshold": 0.6,
    "header_footer_short_text_threshold": 0.8,
    "header_footer_min_text_threshold": 0.95,
    "header_footer_block_coverage_threshold": 0.7,
    "cross_page_merge_header_table": True,
    "cross_page_table_vlm_timeout": 120.0,
    "wps_file_type_detection_mode": None,
    "title_detection_enable_reasoning": False,
    "table_multi_table_judge_timeout": 30.0,
    "table_multi_table_judge_retries": 2,
    "table_multi_table_generate_timeout": 120.0,
    "table_multi_table_generate_retries": 1,
    "table_regenerate_timeout": 120.0,
    "table_regenerate_retries": 1,
    "l1_html_generation_timeout": 120.0,
    "l1_html_generation_retries": 1,
    "flowchart_detect_future_timeout": 60.0,
    "l1_html_generation_future_timeout": 120.0,
    "decorative_icon_ecc_threshold": 0.8,
    "decorative_icon_max_dimension": 200,
    "enable_cross_page_geometric_filter": True,
    "enable_openxml_header_footer": True,
    "enable_doc_libreoffice_openxml": False,
    "enable_doc_uno_hf": False,
    "enable_paddle_hf_geometric_filter": False,
    "enable_header_footer_as_text": False,
    "use_remote_paddle_layout": False,
    "flowchart_table_ignore_judge": True,
    "image_section_heading_level": "bold",
    "prompt_overrides": {},
    "priority": None,
    "save_ppt_page_as_image": False,
}


def stable_id(path: Path, input_dir: Path) -> str:
    relative = path.relative_to(input_dir).as_posix()
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]


def safe_name(path: Path) -> str:
    return "".join(
        "_" if char in {"/", "\\", "\0"} or ord(char) < 32 else char
        for char in path.name
    ).strip(" .") or "unnamed"


def result_path(path: Path, input_dir: Path, output_dir: Path) -> Path:
    return output_dir / f"{safe_name(path)}--{stable_id(path, input_dir)}.zip"


def load_moi_key(demo_script: Path) -> str:
    env_key = os.environ.get("IDC_MOI_KEY", "").strip()
    if env_key:
        return env_key
    if not demo_script.is_file():
        raise RuntimeError(
            "IDC_MOI_KEY is not set and demo script does not exist: "
            f"{demo_script}"
        )
    spec = importlib.util.spec_from_file_location("idc_demo_onebyone", demo_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load IDC demo script: {demo_script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    headers = getattr(module, "headers", None)
    key = headers.get("moi-key") if isinstance(headers, dict) else None
    if not isinstance(key, str) or not key.strip():
        raise RuntimeError(
            f"demo script contains no headers['moi-key']: {demo_script}"
        )
    return key.strip()


def mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".doc":
        return "application/msword"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".ppt":
        return "application/vnd.ms-powerpoint"
    if suffix == ".pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if suffix == ".xls":
        return "application/vnd.ms-excel"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".csv":
        return "text/csv"
    if suffix == ".txt":
        return "text/plain"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".bmp":
        return "image/bmp"
    if suffix in {".tif", ".tiff"}:
        return "image/tiff"
    return "application/octet-stream"


def payload_for(path: Path) -> dict[str, Any]:
    return {
        "file_names": [path.name],
        "steps": [
            {
                "node": "ParseNode",
                "parameters": {
                    "DOCXToDocument": {"convert_to_pdf": True},
                    "PPTXToDocument": {"convert_to_pdf": True},
                    "XLSXToDocument": {
                        "unmerge_cells": False,
                        "table_format": "markdown",
                    },
                    "CsvToDocument": {
                        "unmerge_cells": False,
                        "table_format": "markdown",
                    },
                },
            }
        ],
        "options": OPTIONS,
    }


def is_supported_input(path: Path, input_dir: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return False
    relative = path.relative_to(input_dir)
    if any(part.startswith(".") for part in relative.parts):
        return False
    if path.name.startswith("~$"):
        return False
    return True


def checked_json(response: requests.Response, operation: str) -> dict[str, Any]:
    if not response.ok:
        body = response.text[:2000].replace("\n", " ")
        raise RuntimeError(
            f"{operation} returned HTTP {response.status_code}: {body}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{operation} returned non-JSON data") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{operation} returned invalid JSON: {data!r}")
    if data.get("code") not in ("OK", 0, "0", None):
        raise RuntimeError(
            f"{operation} failed: code={data.get('code')!r}, "
            f"message={data.get('msg') or data}"
        )
    return data


def submit_job(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    path: Path,
    request_timeout: float,
) -> str:
    url = f"{base_url.rstrip('/')}/v1/genai/pipeline"
    with path.open("rb") as stream:
        response = session.post(
            url,
            headers=headers,
            files={
                "files": (
                    path.name,
                    stream,
                    mime_type(path),
                )
            },
            data={"payload": json.dumps(payload_for(path), ensure_ascii=False)},
            timeout=request_timeout,
        )
    data = checked_json(response, "job submission").get("data")
    job_id = data.get("job_id") if isinstance(data, dict) else None
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError("job submission returned no job_id")
    return job_id


def get_job(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    job_id: str,
    request_timeout: float,
) -> dict[str, Any]:
    response = session.get(
        f"{base_url.rstrip('/')}/v1/genai/jobs/{job_id}",
        headers=headers,
        timeout=request_timeout,
    )
    payload = checked_json(response, "job query")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"job query returned invalid data: {payload!r}")
    return data


def wait_for_file_id(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    job_id: str,
    poll_interval: float,
    run_timeout: float,
    request_timeout: float,
) -> str:
    deadline = time.monotonic() + run_timeout
    previous_status = ""
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"job {job_id} exceeded timeout {run_timeout:.0f}s"
            )
        data = get_job(session, base_url, headers, job_id, request_timeout)
        status = str(data.get("status", "")).lower()
        if status != previous_status:
            print(f"    status={status or 'unknown'}", flush=True)
            previous_status = status
        if status == "completed":
            files = data.get("files")
            if not isinstance(files, list) or len(files) != 1:
                raise RuntimeError(
                    f"completed job returned unexpected files: {files!r}"
                )
            file_data = files[0]
            if not isinstance(file_data, dict):
                raise RuntimeError(f"invalid job file result: {file_data!r}")
            file_status = str(file_data.get("file_status", "")).lower()
            if file_status != "completed":
                raise RuntimeError(
                    f"file parsing failed with status={file_status!r}: "
                    f"{file_data}"
                )
            file_id = file_data.get("file_id")
            if not isinstance(file_id, str) or not file_id:
                raise RuntimeError("completed file contains no file_id")
            return file_id
        if status in {"failed", "error", "cancelled", "canceled"}:
            raise RuntimeError(f"job ended with status={status!r}: {data}")
        if status not in {"pending", "queued", "running", "processing"}:
            raise RuntimeError(f"job returned unknown status={status!r}: {data}")
        time.sleep(poll_interval)


def download_result(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    file_id: str,
    target: Path,
    request_timeout: float,
) -> None:
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with session.get(
            f"{base_url.rstrip('/')}/v1/genai/results/file/{file_id}",
            headers=headers,
            params={
                "need_source_files": "true",
                "delete_after_download": "false",
            },
            stream=True,
            timeout=request_timeout,
        ) as response:
            response.raise_for_status()
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        stream.write(chunk)
        if temporary.stat().st_size == 0:
            raise RuntimeError("downloaded result ZIP is empty")
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def run_file(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    path: Path,
    target: Path,
    poll_interval: float,
    run_timeout: float,
    submit_timeout: float,
    request_timeout: float,
    download_timeout: float,
) -> str:
    if target.is_file() and target.stat().st_size > 0:
        print(f"[skip] {path.name}", flush=True)
        return "skipped"
    print(f"[run] {path.name}", flush=True)
    job_id = submit_job(session, base_url, headers, path, submit_timeout)
    print(f"    job_id={job_id}", flush=True)
    file_id = wait_for_file_id(
        session,
        base_url,
        headers,
        job_id,
        poll_interval,
        run_timeout,
        request_timeout,
    )
    download_result(
        session,
        base_url,
        headers,
        file_id,
        target,
        download_timeout,
    )
    print(f"[done] {path.name} -> {target.name}", flush=True)
    return "completed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run documents through the Shanghai IDC parser."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--file",
        type=Path,
        help="Process only this file; it must be located under --input-dir.",
    )
    parser.add_argument("--demo-script", type=Path, default=DEFAULT_DEMO_SCRIPT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--poll-interval", type=float, default=10.0)
    parser.add_argument("--run-timeout", type=float, default=7200.0)
    parser.add_argument("--submit-timeout", type=float, default=1200.0)
    parser.add_argument("--request-timeout", type=float, default=2400.0)
    parser.add_argument("--download-timeout", type=float, default=2400.0)
    parser.add_argument(
        "--max-files",
        type=int,
        help="Only process the first N files; useful for a smoke test.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    demo_script = args.demo_script.expanduser().resolve()
    if not input_dir.is_dir():
        print(f"input directory does not exist: {input_dir}", file=sys.stderr)
        return 2
    if args.max_files is not None and args.max_files < 1:
        print("--max-files must be at least 1", file=sys.stderr)
        return 2
    if args.file is not None and args.max_files is not None:
        print("--file and --max-files cannot be used together", file=sys.stderr)
        return 2

    if args.file is not None:
        selected_file = args.file.expanduser().resolve()
        try:
            selected_file.relative_to(input_dir)
        except ValueError:
            print(
                f"--file must be located under --input-dir: {input_dir}",
                file=sys.stderr,
            )
            return 2
        if not is_supported_input(selected_file, input_dir):
            print(
                f"--file is missing, temporary, or unsupported: {selected_file}",
                file=sys.stderr,
            )
            return 2
        files = [selected_file]
    else:
        files = sorted(
            (
                path
                for path in input_dir.rglob("*")
                if is_supported_input(path, input_dir)
            ),
            key=lambda path: path.relative_to(input_dir).as_posix(),
        )
        if args.max_files is not None:
            files = files[: args.max_files]
    if not files:
        print(f"no supported files found under {input_dir}", file=sys.stderr)
        return 2

    try:
        moi_key = load_moi_key(demo_script)
    except Exception as exc:
        print(f"credential loading failed: {exc}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    headers = {"moi-key": moi_key}
    counts = {"completed": 0, "failed": 0, "skipped": 0}
    for index, path in enumerate(files, start=1):
        print(f"\n[{index}/{len(files)}] {path.name}", flush=True)
        target = result_path(path, input_dir, output_dir)
        try:
            outcome = run_file(
                session,
                args.base_url,
                headers,
                path,
                target,
                args.poll_interval,
                args.run_timeout,
                args.submit_timeout,
                args.request_timeout,
                args.download_timeout,
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
    print(f"ZIP directory: {output_dir}", flush=True)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
