#!/usr/bin/env python3
"""Run all frozen Kleister-NDA cases through LandingAI Parse and Extract Jobs.

The script saves raw outputs without scoring. Use --run-dir to resume.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_landingai_vrdu_batch import (
    DEFAULT_EXTRACT_MODEL,
    DEFAULT_PARSE_MODEL,
    LandingAIClient,
    build_summary,
    poll_active,
    read_json,
    submit_pending,
    utc_now,
    write_json,
)


TERMINAL_STATUSES = {"completed", "failed"}

SCHEMA = {
    "type": "object",
    "properties": {
        "effective_date": {
            "type": "string",
            "format": "YYYY-MM-DD",
            "description": (
                "The date on which the nondisclosure or confidentiality agreement becomes "
                "legally effective. Distinguish it from signature dates, filing dates, "
                "document creation dates, and dates mentioned in referenced agreements."
            ),
            "x-alternativeNames": [
                "Effective Date",
                "Date of Agreement",
                "Agreement Date",
                "Dated as of",
            ],
        },
        "jurisdiction": {
            "type": "string",
            "description": (
                "The state, country, or legal jurisdiction whose laws govern the agreement. "
                "Extract the governing-law jurisdiction, not a venue, company address, "
                "incorporation state, or court location unless it is explicitly the governing law."
            ),
            "x-alternativeNames": [
                "Governing Law",
                "Applicable Law",
                "Choice of Law",
                "Jurisdiction",
            ],
        },
        "party": {
            "type": "array",
            "description": (
                "All legal entities or individuals that are parties to the agreement. "
                "Return each contracting party once. Do not include signers, representatives, "
                "affiliates, advisers, addresses, or defined third parties unless they are "
                "explicitly a contracting party."
            ),
            "x-alternativeNames": [
                "Parties",
                "Party",
                "Disclosing Party",
                "Receiving Party",
            ],
            "items": {
                "type": "string",
                "description": "The complete legal name of one contracting party.",
            },
        },
        "term": {
            "type": "string",
            "format": (
                "Normalize the confidentiality obligation duration as {number}_{unit}, "
                "using lowercase singular or plural units, for example 18_months, "
                "1_year, or 5_years."
            ),
            "description": (
                "The duration of the confidentiality or nondisclosure obligation. Infer it "
                "from the operative term clause. Do not return the negotiation period, "
                "agreement renewal period, disclosure window, or document retention period."
            ),
            "x-alternativeNames": [
                "Term",
                "Duration",
                "Confidentiality Period",
                "Survival",
            ],
        },
    },
}


def sanitize_case_id(case_id: str) -> str:
    return case_id.replace("/", "_").replace("\\", "_")


def create_state(case: dict[str, Any], pdf_path: Path) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "pdf_path": str(pdf_path),
        "source_type": "pdf",
        "source_split": case.get("split"),
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
            state = create_state(case, pdf_path)
            write_json(state_path, state)
        states[case["case_id"]] = state
    return states


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
    dataset_root = track_root / "datasets" / "Kleister-NDA"
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
        run_dir = track_root / "runs" / f"landingai-kleister-batch-{run_id}"
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
                "dataset": "Kleister-NDA",
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
    client = LandingAIClient(api_key, args.request_timeout, read_json(schema_path))

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
