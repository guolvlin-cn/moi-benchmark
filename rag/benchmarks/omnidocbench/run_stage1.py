#!/usr/bin/env python3
"""Reproducible OmniDocBench Stage 1 adapter for the local MOI parser."""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import math
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image


SCHEMA_VERSION = "moi-omnidocbench-stage1-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_rank(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def source_type(record: dict) -> str:
    return record["page_info"].get("page_attribute", {}).get("data_source", "unknown")


def proportional_quotas(records: list[dict], sample_size: int) -> dict[str, int]:
    counts = Counter(source_type(record) for record in records)
    raw = {key: sample_size * count / len(records) for key, count in counts.items()}
    quotas = {key: min(counts[key], math.floor(value)) for key, value in raw.items()}
    remaining = sample_size - sum(quotas.values())
    order = sorted(counts, key=lambda key: (-(raw[key] - quotas[key]), key))
    while remaining:
        progressed = False
        for key in order:
            if quotas[key] < counts[key]:
                quotas[key] += 1
                remaining -= 1
                progressed = True
                if remaining == 0:
                    break
        if not progressed:
            raise ValueError("could not allocate requested sample")
    return quotas


def select_records(records: list[dict], sample_size: int, seed: int) -> list[dict]:
    if sample_size <= 0 or sample_size > len(records):
        raise ValueError(f"sample size must be in [1, {len(records)}], got {sample_size}")
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[source_type(record)].append(record)
    quotas = proportional_quotas(records, sample_size)
    selected = []
    for key in sorted(groups):
        ranked = sorted(
            groups[key],
            key=lambda record: stable_rank(seed, record["page_info"]["image_path"]),
        )
        selected.extend(ranked[: quotas[key]])
    return sorted(selected, key=lambda record: record["page_info"]["image_path"])


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def image_to_pdf(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.pdf")
    with Image.open(source) as source_image:
        image = source_image if source_image.mode == "RGB" else source_image.convert("RGB")
        try:
            image.save(temporary, "PDF", resolution=200.0)
        finally:
            if image is not source_image:
                image.close()
    temporary.replace(destination)


def is_complete_pdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 4:
        return False
    with path.open("rb") as source:
        return source.read(5) == b"%PDF-"


def prepare(args: argparse.Namespace) -> None:
    ground_truth_path = Path(args.ground_truth).resolve()
    images_dir = Path(args.images).resolve()
    run_dir = Path(args.run_dir).resolve()
    records = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    selected = select_records(records, args.sample_size, args.seed)

    official_dir = run_dir / "official"
    input_dir = run_dir / "artifacts" / "inputs"
    predictions_dir = official_dir / "predictions"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    write_json(official_dir / "ground-truth.json", selected)

    manifest_lines = []
    hashes = [f"{sha256_file(ground_truth_path)}  dataset/OmniDocBench.json"]
    for record in selected:
        page_info = record["page_info"]
        image_name = page_info["image_path"]
        image_path = images_dir / image_name
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        page_id = Path(image_name).stem
        pdf_path = input_dir / f"{page_id}.pdf"
        if not is_complete_pdf(pdf_path):
            image_to_pdf(image_path, pdf_path)
        attributes = page_info.get("page_attribute", {})
        manifest_lines.append(
            json.dumps(
                {
                    "page_id": page_id,
                    "image_path": str(image_path),
                    "input_pdf": str(pdf_path),
                    "prediction": str(predictions_dir / f"{page_id}.md"),
                    "source_sha256": sha256_file(image_path),
                    "data_source": attributes.get("data_source"),
                    "language": attributes.get("language"),
                    "layout": attributes.get("layout"),
                    "special_issue": attributes.get("special_issue", []),
                },
                ensure_ascii=False,
            )
        )
        hashes.append(f"{sha256_file(image_path)}  source/{image_name}")
    manifest_path = run_dir / "artifacts" / "sample-manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    (run_dir / "artifacts" / "hashes.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    write_json(
        run_dir / "artifacts" / "manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "benchmark": "OmniDocBench",
            "sample_size": len(selected),
            "sampling": "proportional_by_data_source_deterministic_within_stratum",
            "seed": args.seed,
            "ground_truth": str(ground_truth_path),
            "source_distribution": dict(sorted(Counter(source_type(record) for record in selected).items())),
        },
    )
    print(f"prepared={len(selected)} run_dir={run_dir}")


def parse_one(entry: dict, args: argparse.Namespace, page_runs: Path) -> dict:
    page_id = entry["page_id"]
    started = time.time()
    command = [
        str(Path(args.parser_bin).resolve()),
        "parse",
        "--input",
        entry["input_pdf"],
        "--pipeline",
        args.pipeline,
        "--run",
        str(page_runs),
        "--mineru-timeout",
        args.timeout,
    ]
    if args.env_file:
        command.extend(["--env-file", str(Path(args.env_file).resolve())])
    completed = subprocess.run(command, text=True, capture_output=True)
    elapsed_ms = (time.time() - started) * 1000
    attempt = {
        "page_id": page_id,
        "pipeline": args.pipeline,
        "attempt": 1,
        "status": "error",
        "latency_ms": round(elapsed_ms, 3),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }
    if completed.returncode != 0:
        attempt["error_type"] = "parser_process_error"
        return attempt
    run_line = next((line for line in completed.stdout.splitlines() if line.startswith("run_dir=")), "")
    if not run_line:
        attempt["error_type"] = "missing_parser_run_dir"
        return attempt
    parser_run = Path(run_line.split("=", 1)[1]).resolve()
    markdown_path = parser_run / "product-artifacts" / "mineru-full.md"
    if not markdown_path.is_file():
        attempt["error_type"] = "missing_markdown"
        attempt["parser_run_dir"] = str(parser_run)
        return attempt
    prediction = Path(entry["prediction"])
    prediction.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(markdown_path, prediction)
    attempt.update(
        {
            "status": "ok",
            "prediction": str(prediction),
            "prediction_sha256": sha256_file(prediction),
            "parser_run_dir": str(parser_run),
            "parser_summary": str(parser_run / "summary.json"),
        }
    )
    return attempt


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def parse(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).resolve()
    lock_path = run_dir / "moi-unified" / "parse.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        print(f"waiting_for_parse_lock={lock_path}", flush=True)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            _parse_unlocked(args)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _parse_unlocked(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "artifacts" / "sample-manifest.jsonl"
    entries = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line]
    page_runs = run_dir / "artifacts" / "parser-runs" / args.pipeline
    page_runs.mkdir(parents=True, exist_ok=True)
    attempts_path = run_dir / "moi-unified" / "attempts.jsonl"
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    attempts = []
    if attempts_path.is_file():
        attempts = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line]
    attempted_page_ids = {attempt["page_id"] for attempt in attempts}
    pending = [entry for entry in entries if entry["page_id"] not in attempted_page_ids]
    progress_path = run_dir / "moi-unified" / "progress.json"
    handoff_path = run_dir / "PRECISION-HANDOFF.md"

    def update_progress() -> None:
        successful_count = sum(attempt["status"] == "ok" for attempt in attempts)
        error_count = sum(attempt["status"] != "ok" for attempt in attempts)
        write_json(
            progress_path,
            {
                "schema_version": SCHEMA_VERSION,
                "pipeline": args.pipeline,
                "planned_pages": len(entries),
                "completed_pages": len(attempts),
                "accepted_pages": successful_count,
                "failed_pages": error_count,
                "remaining_pages": len(entries) - len(attempts),
                "updated_at_epoch": time.time(),
            },
        )

    update_progress()
    if pending and handoff_path.is_file():
        print(
            f"automatic_parse_blocked=true remaining={len(pending)} handoff={handoff_path}; "
            "wait for the externally owned Precision parse and run verify before scoring",
            flush=True,
        )
        raise SystemExit(2)
    if pending:
        with attempts_path.open("a", encoding="utf-8") as ledger:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = {executor.submit(parse_one, entry, args, page_runs): entry for entry in pending}
                for future in concurrent.futures.as_completed(futures):
                    attempt = future.result()
                    attempts.append(attempt)
                    ledger.write(json.dumps(attempt, ensure_ascii=False) + "\n")
                    ledger.flush()
                    update_progress()
                    print(
                        f"progress={len(attempts)}/{len(entries)} accepted={sum(item['status'] == 'ok' for item in attempts)} "
                        f"failed={sum(item['status'] != 'ok' for item in attempts)} page={attempt['page_id']}",
                        flush=True,
                    )
    attempts.sort(key=lambda attempt: attempt["page_id"])
    successful = [attempt for attempt in attempts if attempt["status"] == "ok"]
    latencies = [attempt["latency_ms"] for attempt in attempts]
    error_counts = Counter(attempt.get("error_type", "none") for attempt in attempts if attempt["status"] != "ok")
    write_json(
        run_dir / "moi-unified" / "metrics.json",
        {
            "schema_version": SCHEMA_VERSION,
            "planned_pages": len(attempts),
            "accepted_pages": len(successful),
            "accepted_page_rate": len(successful) / len(attempts) if attempts else 0,
            "parse_latency_mean_ms": sum(latencies) / len(latencies) if latencies else 0,
            "parse_latency_p50_ms": percentile(latencies, 0.50),
            "parse_latency_p95_ms": percentile(latencies, 0.95),
            "pipeline": args.pipeline,
        },
    )
    write_json(run_dir / "moi-unified" / "error-taxonomy.json", dict(sorted(error_counts.items())))
    write_json(
        run_dir / "official" / "protocol.json",
        {
            "benchmark": "OmniDocBench",
            "protocol_status": "ADAPTED_PROTOCOL",
            "adaptation": "benchmark page image embedded losslessly in a single-page PDF for the MOI PDF parser",
            "prediction_format": "one Markdown file per benchmark page",
            "pipeline": args.pipeline,
        },
    )
    print(f"planned={len(attempts)} accepted={len(successful)} pipeline={args.pipeline} run_dir={run_dir}")
    if len(successful) != len(attempts):
        raise SystemExit(1)


def reuse(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "artifacts" / "sample-manifest.jsonl"
    entries = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line]
    targets = {entry["page_id"]: entry for entry in entries}
    attempts_path = run_dir / "moi-unified" / "attempts.jsonl"
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if attempts_path.is_file():
        existing = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line]
    used_page_ids = {attempt["page_id"] for attempt in existing}
    reused_attempts = []
    reused_by_source = Counter(
        attempt.get("reused_from")
        for attempt in existing
        if attempt.get("reused") and attempt.get("reused_from")
    )

    for source_value in args.source_run:
        source_run = Path(source_value).resolve()
        source_attempts_path = source_run / "moi-unified" / "attempts.jsonl"
        if not source_attempts_path.is_file():
            continue
        source_attempts = [
            json.loads(line) for line in source_attempts_path.read_text(encoding="utf-8").splitlines() if line
        ]
        for attempt in source_attempts:
            page_id = attempt["page_id"]
            if attempt.get("status") != "ok" or page_id not in targets or page_id in used_page_ids:
                continue
            source_prediction = source_run / "official" / "predictions" / f"{page_id}.md"
            if not source_prediction.is_file():
                continue
            target_prediction = Path(targets[page_id]["prediction"])
            target_prediction.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_prediction, target_prediction)
            reused_attempt = dict(attempt)
            reused_attempt.update(
                {
                    "prediction": str(target_prediction),
                    "prediction_sha256": sha256_file(target_prediction),
                    "reused": True,
                    "reused_from": str(source_run),
                }
            )
            reused_attempts.append(reused_attempt)
            reused_by_source[str(source_run)] += 1
            used_page_ids.add(page_id)

    if reused_attempts:
        with attempts_path.open("a", encoding="utf-8") as ledger:
            for attempt in reused_attempts:
                ledger.write(json.dumps(attempt, ensure_ascii=False) + "\n")
    all_attempts = existing + reused_attempts
    total_reused = sum(bool(attempt.get("reused")) for attempt in all_attempts)
    write_json(
        run_dir / "moi-unified" / "reuse-summary.json",
        {
            "schema_version": SCHEMA_VERSION,
            "planned_pages": len(entries),
            "reused_pages": total_reused,
            "newly_reused_pages": len(reused_attempts),
            "reused_by_source": dict(sorted(reused_by_source.items())),
            "remaining_pages": len(entries) - len(all_attempts),
        },
    )
    write_json(
        run_dir / "moi-unified" / "progress.json",
        {
            "schema_version": SCHEMA_VERSION,
            "pipeline": "precision",
            "planned_pages": len(entries),
            "completed_pages": len(all_attempts),
            "accepted_pages": sum(attempt.get("status") == "ok" for attempt in all_attempts),
            "failed_pages": sum(attempt.get("status") != "ok" for attempt in all_attempts),
            "remaining_pages": len(entries) - len(all_attempts),
            "updated_at_epoch": time.time(),
        },
    )
    print(
        f"newly_reused={len(reused_attempts)} total_reused={total_reused} "
        f"remaining={len(entries) - len(all_attempts)} run_dir={run_dir}"
    )


def verify(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).resolve()
    lock_path = run_dir / "moi-unified" / "parse.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        print(f"waiting_for_parse_lock={lock_path}", flush=True)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        _verify_unlocked(run_dir, args.pipeline, args.allow_empty_predictions)


def _verify_unlocked(run_dir: Path, pipeline: str, allow_empty_predictions: bool = False) -> None:
    manifest_path = run_dir / "artifacts" / "sample-manifest.jsonl"
    attempts_path = run_dir / "moi-unified" / "attempts.jsonl"
    progress_path = run_dir / "moi-unified" / "progress.json"
    metrics_path = run_dir / "moi-unified" / "metrics.json"
    verification_path = run_dir / "moi-unified" / "verification.json"
    issues = []

    entries = []
    attempts = []
    if not manifest_path.is_file():
        issues.append("missing sample manifest")
    else:
        entries = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line]
    if not attempts_path.is_file():
        issues.append("missing attempts ledger")
    else:
        attempts = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line]

    manifest_ids = [entry["page_id"] for entry in entries]
    attempt_ids = [attempt["page_id"] for attempt in attempts]
    duplicate_manifest_ids = sorted(page_id for page_id, count in Counter(manifest_ids).items() if count > 1)
    duplicate_attempt_ids = sorted(page_id for page_id, count in Counter(attempt_ids).items() if count > 1)
    missing_attempt_ids = sorted(set(manifest_ids) - set(attempt_ids))
    unexpected_attempt_ids = sorted(set(attempt_ids) - set(manifest_ids))
    failed_attempt_ids = sorted(attempt["page_id"] for attempt in attempts if attempt.get("status") != "ok")
    if duplicate_manifest_ids:
        issues.append(f"duplicate manifest page IDs: {len(duplicate_manifest_ids)}")
    if duplicate_attempt_ids:
        issues.append(f"duplicate attempt page IDs: {len(duplicate_attempt_ids)}")
    if missing_attempt_ids:
        issues.append(f"missing attempts: {len(missing_attempt_ids)}")
    if unexpected_attempt_ids:
        issues.append(f"unexpected attempts: {len(unexpected_attempt_ids)}")
    if failed_attempt_ids:
        issues.append(f"failed attempts: {len(failed_attempt_ids)}")

    attempts_by_id = {attempt["page_id"]: attempt for attempt in attempts}
    missing_predictions = []
    empty_predictions = []
    hash_mismatches = []
    expected_prediction_paths = set()
    for entry in entries:
        page_id = entry["page_id"]
        prediction = Path(entry["prediction"]).resolve()
        expected_prediction_paths.add(prediction)
        if not prediction.is_file():
            missing_predictions.append(page_id)
            continue
        if prediction.stat().st_size == 0:
            empty_predictions.append(page_id)
        expected_hash = attempts_by_id.get(page_id, {}).get("prediction_sha256")
        if expected_hash and sha256_file(prediction) != expected_hash:
            hash_mismatches.append(page_id)
    prediction_dir = run_dir / "official" / "predictions"
    actual_prediction_paths = {path.resolve() for path in prediction_dir.glob("*.md")} if prediction_dir.is_dir() else set()
    unexpected_predictions = sorted(str(path) for path in actual_prediction_paths - expected_prediction_paths)
    if missing_predictions:
        issues.append(f"missing predictions: {len(missing_predictions)}")
    if empty_predictions and not allow_empty_predictions:
        issues.append(f"empty predictions: {len(empty_predictions)}")
    if hash_mismatches:
        issues.append(f"prediction hash mismatches: {len(hash_mismatches)}")
    if unexpected_predictions:
        issues.append(f"unexpected predictions: {len(unexpected_predictions)}")
    if not progress_path.is_file():
        issues.append("missing progress.json")
        progress = {}
    else:
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        expected_progress = {
            "planned_pages": len(entries),
            "completed_pages": len(attempts),
            "accepted_pages": sum(attempt.get("status") == "ok" for attempt in attempts),
            "failed_pages": sum(attempt.get("status") != "ok" for attempt in attempts),
            "remaining_pages": len(entries) - len(attempts),
        }
        for key, expected in expected_progress.items():
            if progress.get(key) != expected:
                issues.append(f"progress {key}={progress.get(key)!r}, expected {expected}")
    if not metrics_path.is_file():
        issues.append("missing metrics.json")

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_dir": str(run_dir),
        "pipeline": pipeline,
        "complete": not issues,
        "planned_pages": len(entries),
        "attempted_pages": len(attempts),
        "accepted_pages": sum(attempt.get("status") == "ok" for attempt in attempts),
        "prediction_files": len(actual_prediction_paths),
        "reused_pages": sum(bool(attempt.get("reused")) for attempt in attempts),
        "missing_attempt_page_ids": missing_attempt_ids,
        "failed_attempt_page_ids": failed_attempt_ids,
        "missing_prediction_page_ids": missing_predictions,
        "empty_prediction_page_ids": empty_predictions,
        "empty_predictions_allowed": allow_empty_predictions,
        "prediction_hash_mismatch_page_ids": hash_mismatches,
        "unexpected_predictions": unexpected_predictions,
        "issues": issues,
        "verified_at_epoch": time.time(),
    }
    write_json(verification_path, report)
    print(
        f"complete={str(not issues).lower()} planned={len(entries)} attempted={len(attempts)} "
        f"accepted={report['accepted_pages']} predictions={len(actual_prediction_paths)} "
        f"run_dir={run_dir}"
    )
    if issues:
        for issue in issues:
            print(f"verification_issue={issue}")
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare", help="create a deterministic stratified evaluation subset")
    prepare_parser.add_argument("--ground-truth", required=True)
    prepare_parser.add_argument("--images", required=True)
    prepare_parser.add_argument("--run-dir", required=True)
    prepare_parser.add_argument("--sample-size", type=int, required=True)
    prepare_parser.add_argument("--seed", type=int, default=20260803)
    prepare_parser.set_defaults(handler=prepare)
    parse_parser = subparsers.add_parser("parse", help="parse a prepared subset with the MOI parser")
    parse_parser.add_argument("--run-dir", required=True)
    parse_parser.add_argument("--parser-bin", required=True)
    parse_parser.add_argument("--pipeline", choices=("precision", "agent"), required=True)
    parse_parser.add_argument("--env-file")
    parse_parser.add_argument("--workers", type=int, default=4)
    parse_parser.add_argument("--timeout", default="15m")
    parse_parser.set_defaults(handler=parse)
    reuse_parser = subparsers.add_parser("reuse", help="reuse successful overlapping predictions from earlier runs")
    reuse_parser.add_argument("--run-dir", required=True)
    reuse_parser.add_argument("--source-run", action="append", required=True)
    reuse_parser.set_defaults(handler=reuse)
    verify_parser = subparsers.add_parser("verify", help="verify a completed parse before official scoring")
    verify_parser.add_argument("--run-dir", required=True)
    verify_parser.add_argument("--pipeline", choices=("precision", "agent"), required=True)
    verify_parser.add_argument(
        "--allow-empty-predictions",
        action="store_true",
        help="allow successful empty Markdown predictions to remain in the official scoring denominator",
    )
    verify_parser.set_defaults(handler=verify)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
