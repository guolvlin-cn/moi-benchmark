#!/usr/bin/env python3
"""Run all frozen VRDU cases through LandingAI Parse Jobs and Extract Jobs.

The script does not score outputs. It saves raw API responses, Parse Markdown,
Extract results, status, timing, model versions, and credit usage per case.
Runs are resumable with --run-dir.
"""

from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://api.va.landing.ai/v1/ade"
DEFAULT_PARSE_MODEL = "dpt-2-20260410"
DEFAULT_EXTRACT_MODEL = "extract-20260314"
TERMINAL_STATUSES = {"completed", "failed"}
ACTIVE_STATUSES = {"parse_submitted", "extract_submitted"}

SCHEMA = {
    "type": "object",
    "properties": {
        "file_date": {
            "type": "string",
            "description": (
                "The filing date shown on the registration document. Do not use unrelated "
                "dates appearing in instructions or historical references."
            ),
            "x-alternativeNames": ["Date of Filing", "Filing Date", "Date"],
        },
        "foreign_principle_name": {
            "type": "string",
            "description": (
                "The name of the foreign principal represented by the registrant. "
                "Do not return the registrant name."
            ),
            "x-alternativeNames": ["Foreign Principal", "Name of Foreign Principal"],
        },
        "registrant_name": {
            "type": "string",
            "description": (
                "The official name of the registrant organization or individual. "
                "Do not return the foreign principal or signer."
            ),
            "x-alternativeNames": ["Name of Registrant", "Registrant"],
        },
        "registration_num": {
            "type": "string",
            "description": (
                "The registrant's registration number. Preserve it as text and preserve "
                "leading zeros."
            ),
            "x-alternativeNames": ["Registration No.", "Registration Number", "Reg. No."],
        },
        "signer_name": {
            "type": "string",
            "description": (
                "The name of the person who signed or executed the document. Do not return "
                "a printed name unrelated to the signature."
            ),
            "x-alternativeNames": ["Name of Signer", "Type or Print Name", "Printed Name"],
        },
        "signer_title": {
            "type": "string",
            "description": (
                "The business title or role of the signer, such as Partner, President, "
                "Director, or Executive Director. Do not return the signer name."
            ),
            "x-alternativeNames": ["Title", "Position", "Capacity"],
        },
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sanitize_case_id(case_id: str) -> str:
    return case_id.replace("/", "_").replace("\\", "_")


class LandingAIClient:
    def __init__(self, api_key: str, timeout: int, schema: dict[str, Any]) -> None:
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout
        self.schema = schema
        self.session = requests.Session()

    def _json_response(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            snippet = response.text[:500]
            raise RuntimeError(
                f"LandingAI returned non-JSON HTTP {response.status_code}: {snippet}"
            ) from exc
        if response.status_code not in (200, 202, 206):
            raise RuntimeError(
                f"LandingAI HTTP {response.status_code}: "
                f"{json.dumps(payload, ensure_ascii=False)[:1000]}"
            )
        return payload

    def submit_parse(self, pdf_path: Path, model: str) -> dict[str, Any]:
        media_type = mimetypes.guess_type(pdf_path.name)[0] or "application/octet-stream"
        with pdf_path.open("rb") as document:
            response = self.session.post(
                f"{BASE_URL}/parse/jobs",
                headers=self.headers,
                files={"document": (pdf_path.name, document, media_type)},
                data={"model": model},
                timeout=self.timeout,
            )
        return self._json_response(response)

    def get_parse_job(self, job_id: str) -> dict[str, Any]:
        response = self.session.get(
            f"{BASE_URL}/parse/jobs/{job_id}",
            headers=self.headers,
            timeout=self.timeout,
        )
        return self._json_response(response)

    def submit_extract(self, markdown_path: Path, model: str) -> dict[str, Any]:
        with markdown_path.open("rb") as markdown:
            response = self.session.post(
                f"{BASE_URL}/extract/jobs",
                headers=self.headers,
                files={"markdown": ("document.md", markdown, "text/markdown")},
                data={
                    "schema": json.dumps(self.schema, ensure_ascii=False),
                    "model": model,
                    "strict": "true",
                },
                timeout=self.timeout,
            )
        return self._json_response(response)

    def get_extract_job(self, job_id: str) -> dict[str, Any]:
        response = self.session.get(
            f"{BASE_URL}/extract/jobs/{job_id}",
            headers=self.headers,
            timeout=self.timeout,
        )
        return self._json_response(response)

    def download_output(self, url: str) -> dict[str, Any]:
        response = self.session.get(url, timeout=self.timeout)
        return self._json_response(response)


def make_case_state(case: dict[str, Any], pdf_path: Path) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "pdf_path": str(pdf_path),
        "pdf_sha256": case.get("pdf_sha256"),
        "status": "pending_parse",
        "parse_job_id": None,
        "extract_job_id": None,
        "parse_submit_attempts": 0,
        "extract_submit_attempts": 0,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "error": None,
    }


def load_or_create_states(
    cases: list[dict[str, Any]],
    dataset_root: Path,
    cases_dir: Path,
) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_dir = cases_dir / sanitize_case_id(case["case_id"])
        case_dir.mkdir(parents=True, exist_ok=True)
        state_path = case_dir / "status.json"
        if state_path.exists():
            state = read_json(state_path)
        else:
            pdf_path = dataset_root / case["pdf"]
            if not pdf_path.is_file():
                raise FileNotFoundError(pdf_path)
            state = make_case_state(case, pdf_path)
            write_json(state_path, state)
        states[case["case_id"]] = state
    return states


def save_state(cases_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    case_dir = cases_dir / sanitize_case_id(state["case_id"])
    write_json(case_dir / "status.json", state)


def append_event(events_path: Path, event: dict[str, Any]) -> None:
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), **event}, ensure_ascii=False) + "\n")


def extract_job_data(
    client: LandingAIClient,
    job: dict[str, Any],
) -> dict[str, Any]:
    data = job.get("data")
    if isinstance(data, dict):
        return data
    output_url = job.get("output_url")
    if output_url:
        return client.download_output(output_url)
    raise RuntimeError("Completed job contains neither data nor output_url")


def submit_pending(
    client: LandingAIClient,
    states: dict[str, dict[str, Any]],
    cases_dir: Path,
    events_path: Path,
    concurrency: int,
    parse_model: str,
    extract_model: str,
    max_submit_attempts: int,
) -> None:
    active = sum(state["status"] in ACTIVE_STATUSES for state in states.values())
    available = max(0, concurrency - active)
    if available == 0:
        return

    pending = [
        state
        for state in states.values()
        if state["status"] in {"pending_parse", "pending_extract"}
    ]
    for state in pending[:available]:
        case_dir = cases_dir / sanitize_case_id(state["case_id"])
        stage = "parse" if state["status"] == "pending_parse" else "extract"
        attempt_key = f"{stage}_submit_attempts"
        if state[attempt_key] >= max_submit_attempts:
            state["status"] = "failed"
            state["error"] = f"{stage} submission exceeded {max_submit_attempts} attempts"
            save_state(cases_dir, state)
            continue

        state[attempt_key] += 1
        save_state(cases_dir, state)
        try:
            if stage == "parse":
                response = client.submit_parse(Path(state["pdf_path"]), parse_model)
                job_id = response["job_id"]
                write_json(case_dir / "parse-submit-response.json", response)
                state["parse_job_id"] = job_id
                state["parse_submitted_at"] = utc_now()
                state["status"] = "parse_submitted"
            else:
                response = client.submit_extract(case_dir / "document.md", extract_model)
                job_id = response["job_id"]
                write_json(case_dir / "extract-submit-response.json", response)
                state["extract_job_id"] = job_id
                state["extract_submitted_at"] = utc_now()
                state["status"] = "extract_submitted"
            state["error"] = None
            save_state(cases_dir, state)
            append_event(
                events_path,
                {"case_id": state["case_id"], "event": f"{stage}_submitted", "job_id": job_id},
            )
            print(f"[submit] {state['case_id']} {stage} job={job_id}", flush=True)
        except (requests.RequestException, RuntimeError, KeyError) as exc:
            state["error"] = f"{type(exc).__name__}: {exc}"
            save_state(cases_dir, state)
            append_event(
                events_path,
                {"case_id": state["case_id"], "event": f"{stage}_submit_error", "error": str(exc)},
            )
            delay = min(30.0, 2 ** state[attempt_key]) + random.random()
            print(f"[retry] {state['case_id']} {stage} submit: {exc}; wait {delay:.1f}s")
            time.sleep(delay)


def poll_active(
    client: LandingAIClient,
    states: dict[str, dict[str, Any]],
    cases_dir: Path,
    events_path: Path,
) -> None:
    for state in states.values():
        if state["status"] not in ACTIVE_STATUSES:
            continue
        case_dir = cases_dir / sanitize_case_id(state["case_id"])
        stage = "parse" if state["status"] == "parse_submitted" else "extract"
        job_id = state[f"{stage}_job_id"]
        try:
            job = (
                client.get_parse_job(job_id)
                if stage == "parse"
                else client.get_extract_job(job_id)
            )
        except (requests.RequestException, RuntimeError) as exc:
            append_event(
                events_path,
                {"case_id": state["case_id"], "event": f"{stage}_poll_error", "error": str(exc)},
            )
            print(f"[poll] {state['case_id']} {stage}: {exc}", flush=True)
            continue

        write_json(case_dir / f"{stage}-job-latest.json", job)
        remote_status = job.get("status")
        state[f"{stage}_remote_status"] = remote_status
        state[f"{stage}_progress"] = job.get("progress")
        save_state(cases_dir, state)
        if remote_status in {"pending", "processing"}:
            continue

        if remote_status != "completed":
            state["status"] = "failed"
            state["error"] = (
                f"{stage} job ended with status={remote_status}: "
                f"{job.get('failure_reason')}"
            )
            write_json(case_dir / f"{stage}-job-final.json", job)
            save_state(cases_dir, state)
            append_event(
                events_path,
                {
                    "case_id": state["case_id"],
                    "event": f"{stage}_failed",
                    "job_id": job_id,
                    "remote_status": remote_status,
                    "failure_reason": job.get("failure_reason"),
                },
            )
            print(f"[failed] {state['case_id']} {stage}: {state['error']}", flush=True)
            continue

        try:
            data = extract_job_data(client, job)
        except (requests.RequestException, RuntimeError) as exc:
            state["error"] = f"Could not retrieve completed {stage} output: {exc}"
            save_state(cases_dir, state)
            print(f"[output] {state['case_id']} {stage}: {exc}", flush=True)
            continue

        write_json(case_dir / f"{stage}-job-final.json", job)
        write_json(case_dir / f"{stage}-response.json", data)
        if stage == "parse":
            markdown = data.get("markdown")
            if not isinstance(markdown, str) or not markdown:
                state["status"] = "failed"
                state["error"] = "Parse completed without non-empty Markdown"
            else:
                (case_dir / "document.md").write_text(markdown, encoding="utf-8")
                state["status"] = "pending_extract"
                state["parse_completed_at"] = utc_now()
                state["parse_metadata"] = data.get("metadata") or job.get("metadata")
                state["error"] = None
        else:
            state["status"] = "completed"
            state["extract_completed_at"] = utc_now()
            state["extract_metadata"] = data.get("metadata") or job.get("metadata")
            state["extraction"] = data.get("extraction")
            state["error"] = None
        save_state(cases_dir, state)
        append_event(
            events_path,
            {"case_id": state["case_id"], "event": f"{stage}_completed", "job_id": job_id},
        )
        print(f"[done] {state['case_id']} {stage}", flush=True)


def build_summary(states: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    parse_credits = 0.0
    extract_credits = 0.0
    for state in states.values():
        counts[state["status"]] = counts.get(state["status"], 0) + 1
        parse_credits += float((state.get("parse_metadata") or {}).get("credit_usage") or 0)
        extract_credits += float((state.get("extract_metadata") or {}).get("credit_usage") or 0)
    return {
        "updated_at": utc_now(),
        "case_count": len(states),
        "status_counts": counts,
        "parse_credits": round(parse_credits, 4),
        "extract_credits": round(extract_credits, 4),
        "total_credits": round(parse_credits + extract_credits, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, help="Resume an existing run directory")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--max-submit-attempts", type=int, default=5)
    parser.add_argument("--case-limit", type=int, help="Run only the first N manifest cases")
    parser.add_argument("--parse-model", default=DEFAULT_PARSE_MODEL)
    parser.add_argument("--extract-model", default=DEFAULT_EXTRACT_MODEL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.case_limit is not None and args.case_limit < 1:
        parser.error("--case-limit must be at least 1")

    track_root = Path(__file__).resolve().parents[1]
    dataset_root = track_root / "datasets" / "VRDU"
    manifest_path = dataset_root / "selection_manifest.json"
    manifest = read_json(manifest_path)
    cases = manifest["cases"]
    if args.case_limit:
        cases = cases[: args.case_limit]

    if args.run_dir:
        run_dir = args.run_dir.expanduser().resolve()
        if not run_dir.exists():
            parser.error(f"--run-dir does not exist: {run_dir}")
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = track_root / "runs" / f"landingai-vrdu-batch-{run_id}"
        run_dir.mkdir(parents=True)

    cases_dir = run_dir / "cases"
    cases_dir.mkdir(exist_ok=True)
    events_path = run_dir / "events.jsonl"
    config_path = run_dir / "config.json"
    schema_path = run_dir / "schema.json"
    summary_path = run_dir / "summary.json"

    if not config_path.exists():
        write_json(
            config_path,
            {
                "created_at": utc_now(),
                "manifest": str(manifest_path),
                "manifest_case_count": len(cases),
                "parse_model": args.parse_model,
                "extract_model": args.extract_model,
                "concurrency": args.concurrency,
                "poll_interval": args.poll_interval,
                "request_timeout": args.request_timeout,
            },
        )
        write_json(schema_path, SCHEMA)
    else:
        config = read_json(config_path)
        if config["parse_model"] != args.parse_model:
            parser.error("Resume parse model differs from the model frozen in config.json")
        if config["extract_model"] != args.extract_model:
            parser.error("Resume extract model differs from the model frozen in config.json")

    states = load_or_create_states(cases, dataset_root, cases_dir)
    write_json(summary_path, build_summary(states))
    print(f"run_dir={run_dir}")
    print(f"cases={len(states)} parse_model={args.parse_model} extract_model={args.extract_model}")
    if args.dry_run:
        print("dry-run complete: no LandingAI API requests were made")
        return

    api_key = os.environ.get("LANDINGAI_API_KEY") or getpass.getpass("LandingAI API key: ")
    if not api_key:
        raise RuntimeError("LandingAI API key is empty")
    frozen_schema = read_json(schema_path)
    client = LandingAIClient(api_key, args.request_timeout, frozen_schema)

    try:
        while True:
            if all(state["status"] in TERMINAL_STATUSES for state in states.values()):
                break
            poll_active(client, states, cases_dir, events_path)
            submit_pending(
                client,
                states,
                cases_dir,
                events_path,
                args.concurrency,
                args.parse_model,
                args.extract_model,
                args.max_submit_attempts,
            )
            summary = build_summary(states)
            write_json(summary_path, summary)
            print(
                f"[progress] {summary['status_counts']} "
                f"credits={summary['total_credits']}",
                flush=True,
            )
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\nInterrupted. Resume with --run-dir shown above.", flush=True)
    finally:
        summary = build_summary(states)
        write_json(summary_path, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
