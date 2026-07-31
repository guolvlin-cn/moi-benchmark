#!/usr/bin/env python3
"""Batch-run the semiconductor dataset through local Matrixflow 4.1.14 V2.

Each input file is submitted as an independent pipeline. Processing is
sequential, failures are isolated, and only verified result ZIPs are retained.
Existing valid ZIPs are skipped, so rerunning the script resumes the batch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import requests


DEFAULT_INPUT_DIR = Path(
    "/Users/wangyaqi/Documents/cursor_project/agent评估/"
    "moi-benchmark/document-parsing/datasets/半导体场景模拟数据"
)
DEFAULT_OUTPUT_DIR = Path(
    "/Users/wangyaqi/Documents/cursor_project/agent评估/"
    "moi-benchmark/document-parsing/runs/半导体场景私有数据集-idc-4.1.14"
)
DEFAULT_CATALOG_URL = "http://127.0.0.1:8920"
DEFAULT_WORKFLOW_BE_URL = "http://127.0.0.1:8910"
DEFAULT_GUARD_SCRIPT = Path(__file__).resolve().with_name("matrixflow_local_guard.py")
DEFAULT_ACCOUNT_NAME = "local-moi-account"
DEFAULT_USER_NAME = "admin"
DEFAULT_LOCAL_UID = (
    "00000000-0000-0000-0000-0000-" "local-moi-account:admin:accountadmin"
)

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

PARSER_OPTIONS: dict[str, bool | str] = {
    "vlm_model": "qwen3.5-27b",
    "enable_parser_pipeline": True,
    "debug_enabled": True,
    "pptx_normalize_before_pdf": False,
    "save_ppt_page_as_image": False,
    "use_remote_paddle_layout": False,
    "save_table_image_file": True,
    "cast_table_as_image": False,
    "enable_table_html_regeneration": True,
    "enable_table_embedded_image_extraction": True,
    "enable_merged_table_split": True,
    "unmerge_table_cells": False,
    "enable_table_inline_image_text": False,
    "enable_table_image_in_markdown": False,
    "enable_cross_page_table_merge": True,
    "cross_page_merge_header_table": True,
    "enable_cross_page_geometric_filter": True,
    "enable_vlm_title_detection": True,
    "title_detection_enable_reasoning": True,
    "enable_vlm_header_footer_detection": True,
    "enable_openxml_header_footer": True,
    "enable_doc_libreoffice_openxml": True,
    "enable_doc_uno_hf": False,
    "enable_paddle_hf_geometric_filter": False,
    "enable_header_footer_as_text": False,
    "enable_formula_repair": True,
    "enable_list_marker_repair": True,
    "enable_indent_detection": True,
    "enable_fragment_merge": False,
    "enable_image_fragment_merge": False,
    "enable_strikethrough_detection": False,
    "enable_image_annotation_text": False,
    "enable_decorative_icon_detection": True,
    "flowchart_table_ignore_judge": True,
}

WORKFLOW_STEPS: list[dict[str, Any]] = [
    {
        "node": "ParseNode",
        "parameters": {
            "DOCXToDocument": {"convert_to_pdf": True},
            "PPTXToDocument": {
                "convert_to_pdf": True,
                "convert_pptx_to_image": False,
            },
        },
    }
]

JOB_STATUSES = {
    0: "pending",
    1: "running",
    2: "completed",
    3: "failed",
}
FILE_STATUSES = {
    0: "pending",
    1: "processing",
    2: "completed",
    3: "failed",
    4: "stopped",
    5: "retrying",
}
INFRA_ERROR_MARKERS = (
    "invalid connection",
    "lost connection to mysql",
    "can't connect to mysql",
    "connection refused",
    "connection aborted",
    "connection reset",
    "remote end closed connection",
    "read timed out",
    "workflow api error: status=500",
    "pendingrollbackerror",
    "can't reconnect until invalid transaction",
    "初始化 nodefactory 失败",
    "node type documentcleanernode not found",
)


class InfrastructureError(RuntimeError):
    """A shared-service failure that should not count as a bad document."""


class WorkflowFailedError(RuntimeError):
    """A workflow reached its terminal failed state."""


def is_infrastructure_error(error: BaseException | str) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in INFRA_ERROR_MARKERS)


def ensure_infrastructure(args: argparse.Namespace, reason: str) -> None:
    if args.no_guard:
        return
    guard_script = args.guard_script.expanduser().resolve()
    if not guard_script.is_file():
        raise InfrastructureError(f"guard script not found: {guard_script}")
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(guard_script),
                "--ensure",
                "--workflow-be-url",
                args.workflow_be_url,
                "--max-recovery-attempts",
                str(args.guard_recovery_attempts),
            ],
            timeout=args.guard_timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InfrastructureError(f"health guard failed to run: {exc}") from exc
    if result.returncode != 0:
        raise InfrastructureError(
            "health guard could not recover infrastructure "
            f"during {reason}: exit={result.returncode}"
        )


def stable_id(path: Path, input_dir: Path) -> str:
    relative = path.relative_to(input_dir).as_posix()
    return hashlib.sha256(relative.encode()).hexdigest()[:12]


def safe_name(path: Path) -> str:
    name = "".join(
        "_" if char in {"/", "\\", "\0"} or ord(char) < 32 else char
        for char in path.name
    ).strip(" .")
    return name or "unnamed"


def result_path(path: Path, input_dir: Path, output_dir: Path) -> Path:
    return output_dir / f"{safe_name(path)}--{stable_id(path, input_dir)}.zip"


def checkpoint_path(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".workflow.json")


def payload_digest(path: Path) -> str:
    serialized = json.dumps(
        payload_for(path),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def load_checkpoint(path: Path, expected_digest: str) -> dict[str, str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("payload_digest") != expected_digest:
        return {}
    return {
        key: value
        for key in ("workflow_id", "file_id")
        if isinstance((value := data.get(key)), str) and value
    }


def save_checkpoint(
    path: Path,
    digest: str,
    *,
    workflow_id: str,
    file_id: str | None = None,
) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    data = {
        "payload_digest": digest,
        "workflow_id": workflow_id,
        "file_id": file_id,
    }
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def is_valid_zip(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            return archive.testzip() is None
    except (OSError, zipfile.BadZipFile):
        return False


def is_supported_input(path: Path, input_dir: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return False
    relative = path.relative_to(input_dir)
    if any(part.startswith(".") for part in relative.parts):
        return False
    return not path.name.startswith(("~$", ".~"))


def payload_for(path: Path) -> dict[str, Any]:
    return {
        "file_names": [path.name],
        "steps": WORKFLOW_STEPS,
        "options": PARSER_OPTIONS,
    }


def response_data(response: requests.Response, operation: str) -> dict[str, Any]:
    if not response.ok:
        body = response.text[:2000].replace("\n", " ")
        message = f"{operation} returned HTTP {response.status_code}: {body}"
        if response.status_code >= 500 or is_infrastructure_error(message):
            raise InfrastructureError(message)
        raise RuntimeError(message)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{operation} returned non-JSON data") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation} returned invalid JSON: {payload!r}")
    if payload.get("code") not in (None, 0, "0", "OK", "ok"):
        message = (
            f"{operation} failed: code={payload.get('code')!r}, "
            f"message={payload.get('msg') or payload.get('message') or payload}"
        )
        if is_infrastructure_error(message):
            raise InfrastructureError(message)
        raise RuntimeError(message)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{operation} returned no data object: {payload!r}")
    return data


def catalog_headers(args: argparse.Namespace) -> dict[str, str]:
    return {
        "uid": args.uid,
        "user_id": args.account_name,
        "user_name": args.user_name,
    }


def workflow_headers(args: argparse.Namespace) -> dict[str, str]:
    return {
        "user-id": args.account_name,
        "user-name": args.user_name,
    }


def submit_pipeline_once(
    session: requests.Session,
    args: argparse.Namespace,
    path: Path,
) -> str:
    mime_type = mimetypes.guess_type(path.name)[0]
    with path.open("rb") as stream:
        response = session.post(
            f"{args.catalog_url.rstrip('/')}/v1/genai/pipeline",
            headers=catalog_headers(args),
            files={
                "files": (
                    path.name,
                    stream,
                    mime_type or "application/octet-stream",
                )
            },
            data={"payload": json.dumps(payload_for(path), ensure_ascii=False)},
            timeout=args.submit_timeout,
        )
    data = response_data(response, "pipeline submission")
    workflow_id = data.get("job_id")
    if not isinstance(workflow_id, str) or not workflow_id:
        raise RuntimeError(f"pipeline submission returned no job_id: {data!r}")
    return workflow_id


def submit_pipeline(
    session: requests.Session,
    args: argparse.Namespace,
    path: Path,
) -> str:
    for attempt in range(args.infra_retries + 1):
        try:
            return submit_pipeline_once(session, args, path)
        except (InfrastructureError, requests.RequestException) as exc:
            if attempt >= args.infra_retries:
                if isinstance(exc, InfrastructureError):
                    raise
                raise InfrastructureError(
                    f"pipeline submission request failed: {exc}"
                ) from exc
            ensure_infrastructure(args, "submission failed")
            delay = args.infra_retry_delay * (attempt + 1)
            print(
                "    infrastructure error during submission; "
                f"retry={attempt + 1}/{args.infra_retries} "
                f"sleep={delay:.0f}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def list_workflow_jobs(
    session: requests.Session,
    args: argparse.Namespace,
    workflow_id: str,
) -> list[dict[str, Any]]:
    response = session.get(
        f"{args.workflow_be_url.rstrip('/')}/byoa/api/v1/workflow_job",
        headers=workflow_headers(args),
        params={
            "workflow_id": workflow_id,
            "page_num": 1,
            "page_size": 10,
        },
        timeout=args.request_timeout,
    )
    data = response_data(response, "workflow job list")
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        raise RuntimeError(f"workflow job list is invalid: {data!r}")
    return jobs


def list_job_files(
    session: requests.Session,
    args: argparse.Namespace,
    job_id: str,
) -> list[dict[str, Any]]:
    response = session.get(
        (
            f"{args.workflow_be_url.rstrip('/')}/byoa/api/v1/"
            f"workflow_job/{job_id}/files"
        ),
        headers=workflow_headers(args),
        params={"page_num": 1, "page_size": 100_000},
        timeout=args.request_timeout,
    )
    data = response_data(response, "workflow job files")
    files = data.get("files")
    if not isinstance(files, list):
        raise RuntimeError(f"workflow job files are invalid: {data!r}")
    return files


def wait_for_file_id(
    session: requests.Session,
    args: argparse.Namespace,
    workflow_id: str,
) -> str:
    deadline = time.monotonic() + args.run_timeout
    last_status = ""
    infra_attempt = 0
    last_guard_at = time.monotonic()
    while time.monotonic() < deadline:
        if (
            not args.no_guard
            and time.monotonic() - last_guard_at >= args.guard_interval
        ):
            ensure_infrastructure(args, f"workflow {workflow_id} is active")
            last_guard_at = time.monotonic()
        try:
            jobs = list_workflow_jobs(session, args, workflow_id)
        except (InfrastructureError, requests.RequestException) as exc:
            if infra_attempt >= args.infra_retries:
                if isinstance(exc, InfrastructureError):
                    raise
                raise InfrastructureError(
                    f"workflow status request failed: {exc}"
                ) from exc
            infra_attempt += 1
            ensure_infrastructure(args, "status polling failed")
            delay = args.infra_retry_delay * infra_attempt
            print(
                "    infrastructure error during status polling; "
                f"retry={infra_attempt}/{args.infra_retries} "
                f"sleep={delay:.0f}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
            continue
        infra_attempt = 0
        if not jobs:
            status = "pending"
        else:
            job = jobs[0]
            status = JOB_STATUSES.get(job.get("status"), "unknown")

        if status != last_status:
            print(f"    status={status}", flush=True)
            last_status = status

        if status == "completed":
            job_id = jobs[0].get("id")
            if not isinstance(job_id, str) or not job_id:
                raise RuntimeError(f"completed job has no id: {jobs[0]!r}")
            try:
                files = list_job_files(session, args, job_id)
            except (InfrastructureError, requests.RequestException) as exc:
                if infra_attempt >= args.infra_retries:
                    if isinstance(exc, InfrastructureError):
                        raise
                    raise InfrastructureError(
                        f"workflow file request failed: {exc}"
                    ) from exc
                infra_attempt += 1
                ensure_infrastructure(args, "result lookup failed")
                delay = args.infra_retry_delay * infra_attempt
                print(
                    "    infrastructure error while locating result; "
                    f"retry={infra_attempt}/{args.infra_retries} "
                    f"sleep={delay:.0f}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay)
                continue
            if len(files) != 1:
                raise RuntimeError(
                    f"completed job returned {len(files)} files, expected 1"
                )
            file_info = files[0]
            file_status = FILE_STATUSES.get(file_info.get("file_status"), "unknown")
            if file_status != "completed":
                raise RuntimeError(
                    f"file ended with status={file_status}: {file_info!r}"
                )
            file_id = file_info.get("id")
            if not isinstance(file_id, str) or not file_id:
                raise RuntimeError(f"completed file returned no id: {file_info!r}")
            return file_id

        if status == "failed":
            raise WorkflowFailedError(f"workflow failed: {jobs[0]!r}")
        if status == "unknown":
            raise RuntimeError(f"unknown workflow status: {jobs[0]!r}")
        time.sleep(args.poll_interval)

    raise TimeoutError(f"workflow {workflow_id} exceeded {args.run_timeout:.0f}s")


def download_result(
    session: requests.Session,
    args: argparse.Namespace,
    file_id: str,
    target: Path,
) -> None:
    temporary = target.with_suffix(target.suffix + ".part")
    for attempt in range(args.infra_retries + 1):
        temporary.unlink(missing_ok=True)
        try:
            with session.get(
                (
                    f"{args.workflow_be_url.rstrip('/')}/byoa/api/v1/"
                    f"explore/volumes/any/files/{file_id}/raws"
                ),
                headers=workflow_headers(args),
                params={"need_source_files": "false"},
                stream=True,
                timeout=args.download_timeout,
            ) as response:
                if not response.ok:
                    body = response.text[:2000].replace("\n", " ")
                    message = (
                        "result download returned HTTP "
                        f"{response.status_code}: {body}"
                    )
                    if response.status_code >= 500:
                        raise InfrastructureError(message)
                    raise RuntimeError(message)
                with temporary.open("wb") as stream:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            stream.write(chunk)

            if not is_valid_zip(temporary):
                raise RuntimeError("downloaded result is not a valid ZIP")
            temporary.replace(target)
            return
        except (InfrastructureError, requests.RequestException) as exc:
            temporary.unlink(missing_ok=True)
            if attempt >= args.infra_retries:
                if isinstance(exc, InfrastructureError):
                    raise
                raise InfrastructureError(
                    f"result download request failed: {exc}"
                ) from exc
            ensure_infrastructure(args, "result download failed")
            delay = args.infra_retry_delay * (attempt + 1)
            print(
                "    infrastructure error during result download; "
                f"retry={attempt + 1}/{args.infra_retries} "
                f"sleep={delay:.0f}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    raise AssertionError("unreachable")


def run_file(
    session: requests.Session,
    args: argparse.Namespace,
    path: Path,
    target: Path,
) -> str:
    checkpoint = checkpoint_path(target)
    digest = payload_digest(path)
    saved = load_checkpoint(checkpoint, digest)

    if not args.force and is_valid_zip(target) and not saved:
        print(f"[skip] {path.name}", flush=True)
        return "skipped"

    ensure_infrastructure(args, f"before {path.name}")
    print(f"[run] {path.name}", flush=True)
    workflow_id = saved.get("workflow_id")
    resumed_workflow = bool(workflow_id)
    if resumed_workflow:
        print(f"    resume_workflow_id={workflow_id}", flush=True)
    else:
        workflow_id = submit_pipeline(session, args, path)
        save_checkpoint(checkpoint, digest, workflow_id=workflow_id)
        print(f"    workflow_id={workflow_id}", flush=True)

    file_id = saved.get("file_id")
    if file_id:
        print(f"    resume_file_id={file_id}", flush=True)
    else:
        try:
            file_id = wait_for_file_id(session, args, workflow_id)
        except WorkflowFailedError:
            checkpoint.unlink(missing_ok=True)
            if not resumed_workflow:
                raise
            print(
                "    resumed workflow already failed; submitting a new workflow",
                file=sys.stderr,
                flush=True,
            )
            workflow_id = submit_pipeline(session, args, path)
            save_checkpoint(checkpoint, digest, workflow_id=workflow_id)
            print(f"    workflow_id={workflow_id}", flush=True)
            try:
                file_id = wait_for_file_id(session, args, workflow_id)
            except WorkflowFailedError:
                checkpoint.unlink(missing_ok=True)
                raise
        save_checkpoint(
            checkpoint,
            digest,
            workflow_id=workflow_id,
            file_id=file_id,
        )
    ensure_infrastructure(args, f"before downloading {path.name}")
    download_result(session, args, file_id, target)
    checkpoint.unlink(missing_ok=True)
    print(f"[done] {path.name} -> {target.name}", flush=True)
    return "completed"


def select_files(args: argparse.Namespace, input_dir: Path) -> list[Path]:
    if args.file is not None:
        selected = args.file.expanduser().resolve()
        try:
            selected.relative_to(input_dir)
        except ValueError as exc:
            raise ValueError(
                f"--file must be located under --input-dir: {input_dir}"
            ) from exc
        if not is_supported_input(selected, input_dir):
            raise ValueError(
                f"--file is missing, temporary, or unsupported: {selected}"
            )
        return [selected]

    files = sorted(
        (path for path in input_dir.rglob("*") if is_supported_input(path, input_dir)),
        key=lambda path: path.relative_to(input_dir).as_posix(),
    )
    if args.max_files is not None:
        files = files[: args.max_files]
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batch-run semiconductor documents through local Matrixflow " "4.1.14 V2."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--file",
        type=Path,
        help="Process only one file located under --input-dir.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        help="Process only the first N files; useful for smoke tests.",
    )
    parser.add_argument(
        "--catalog-url",
        default=os.getenv("MATRIXFLOW_CATALOG_URL", DEFAULT_CATALOG_URL),
    )
    parser.add_argument(
        "--workflow-be-url",
        default=os.getenv("MATRIXFLOW_WORKFLOW_BE_URL", DEFAULT_WORKFLOW_BE_URL),
    )
    parser.add_argument(
        "--uid",
        default=os.getenv("MATRIXFLOW_UID", DEFAULT_LOCAL_UID),
        help=(
            "Local catalog-service UID; defaults to MATRIXFLOW_UID or the "
            "standard local-moi-account admin identity."
        ),
    )
    parser.add_argument(
        "--account-name",
        default=os.getenv("MATRIXFLOW_ACCOUNT_NAME", DEFAULT_ACCOUNT_NAME),
    )
    parser.add_argument(
        "--user-name",
        default=os.getenv("MATRIXFLOW_USER_NAME", DEFAULT_USER_NAME),
    )
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--run-timeout", type=float, default=7200.0)
    parser.add_argument("--submit-timeout", type=float, default=1200.0)
    parser.add_argument("--request-timeout", type=float, default=1200.0)
    parser.add_argument("--download-timeout", type=float, default=1200.0)
    parser.add_argument(
        "--guard-script",
        type=Path,
        default=DEFAULT_GUARD_SCRIPT,
        help="Local health guard used for checks and automatic recovery.",
    )
    parser.add_argument(
        "--guard-interval",
        type=float,
        default=30.0,
        help="Seconds between health checks while a workflow is active.",
    )
    parser.add_argument(
        "--guard-timeout",
        type=float,
        default=900.0,
        help="Maximum seconds for one health-check/recovery cycle.",
    )
    parser.add_argument(
        "--guard-recovery-attempts",
        type=int,
        default=3,
        help="Automatic recovery attempts for one unhealthy check.",
    )
    parser.add_argument(
        "--no-guard",
        action="store_true",
        help="Disable preflight checks and automatic infrastructure recovery.",
    )
    parser.add_argument(
        "--infra-retries",
        type=int,
        default=3,
        help="Retries for explicit infrastructure errors during submission.",
    )
    parser.add_argument(
        "--infra-retry-delay",
        type=float,
        default=10.0,
        help="Base delay in seconds for infrastructure retries.",
    )
    parser.add_argument(
        "--max-consecutive-infra-failures",
        type=int,
        default=3,
        help=("Stop the batch after this many consecutive infrastructure " "failures."),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rerun files even when a valid result ZIP already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List selected files and print the payload without API calls.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    if not input_dir.is_dir():
        print(f"input directory does not exist: {input_dir}", file=sys.stderr)
        return 2
    if args.file is not None and args.max_files is not None:
        print("--file and --max-files cannot be combined", file=sys.stderr)
        return 2
    if args.max_files is not None and args.max_files < 1:
        print("--max-files must be at least 1", file=sys.stderr)
        return 2
    if args.infra_retries < 0:
        print("--infra-retries cannot be negative", file=sys.stderr)
        return 2
    if args.max_consecutive_infra_failures < 1:
        print(
            "--max-consecutive-infra-failures must be at least 1",
            file=sys.stderr,
        )
        return 2
    if args.guard_recovery_attempts < 1:
        print("--guard-recovery-attempts must be at least 1", file=sys.stderr)
        return 2
    for name in (
        "poll_interval",
        "run_timeout",
        "submit_timeout",
        "request_timeout",
        "download_timeout",
        "infra_retry_delay",
        "guard_interval",
        "guard_timeout",
    ):
        if getattr(args, name) <= 0:
            print(f"--{name.replace('_', '-')} must be positive", file=sys.stderr)
            return 2

    try:
        files = select_files(args, input_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not files:
        print(f"no supported files found under {input_dir}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(
            json.dumps(
                {
                    "input_dir": str(input_dir),
                    "output_dir": str(output_dir),
                    "file_count": len(files),
                    "files": [str(path.relative_to(input_dir)) for path in files],
                    "sample_payload": payload_for(files[0]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not args.uid:
        print(
            "MATRIXFLOW_UID is not set; export it or pass --uid",
            file=sys.stderr,
        )
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    try:
        ensure_infrastructure(args, "batch preflight")
    except InfrastructureError as exc:
        print(f"[stop] batch preflight failed: {exc}", file=sys.stderr, flush=True)
        return 1
    counts = {"completed": 0, "failed": 0, "skipped": 0}
    consecutive_infra_failures = 0
    stopped_for_infrastructure = False

    for index, path in enumerate(files, start=1):
        print(f"\n[{index}/{len(files)}] {path.name}", flush=True)
        target = result_path(path, input_dir, output_dir)
        try:
            outcome = run_file(session, args, path, target)
            if outcome == "completed":
                consecutive_infra_failures = 0
        except Exception as exc:
            if is_infrastructure_error(exc):
                consecutive_infra_failures += 1
            else:
                consecutive_infra_failures = 0
            print(
                f"[failed] {path.name}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            outcome = "failed"
        counts[outcome] += 1
        if consecutive_infra_failures >= args.max_consecutive_infra_failures:
            stopped_for_infrastructure = True
            print(
                "[stop] infrastructure circuit breaker opened after "
                f"{consecutive_infra_failures} consecutive failures; "
                "fix the local services and rerun the same command",
                file=sys.stderr,
                flush=True,
            )
            break

    processed = sum(counts.values())
    print(
        "\nSummary: "
        f"selected={len(files)} processed={processed} "
        f"remaining={len(files) - processed} "
        f"completed={counts['completed']} skipped={counts['skipped']} "
        f"failed={counts['failed']} "
        f"stopped_for_infrastructure={stopped_for_infrastructure}",
        flush=True,
    )
    print(f"ZIP directory: {output_dir}", flush=True)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
