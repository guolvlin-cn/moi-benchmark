#!/usr/bin/env python3
"""Run resumable LoCoMo Top-200 retrieval and score turn-level evidence."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import statistics
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import requests


OFFICIAL_DATASET_SHA256 = (
    "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
)
MEM0_BASELINE_COMMIT = "4b61c5d31b9c668a12b4f5e78064248a02c82d2b"
CATEGORIES = (1, 2, 3, 4)
CATEGORY_NAMES = {
    1: "multi-hop",
    2: "temporal",
    3: "open-domain",
    4: "single-hop",
}
TOP_K = 200
CUTOFFS = (10, 20, 50, 200)
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
EVIDENCE_RE = re.compile(r"D(\d+):(\d+)")
MALFORMED_EVIDENCE_RE = re.compile(r"D:(\d+):(\d+)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()

    def write(self, value: dict[str, Any]) -> None:
        line = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.lock:
            self.handle.write(line + "\n")
            self.handle.flush()
            os.fsync(self.handle.fileno())

    def close(self) -> None:
        with self.lock:
            self.handle.close()


def latest_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            question_id = record.get("question_id")
            if question_id:
                records[str(question_id)] = record
    return records


def conversation_turn_ids(sample: dict[str, Any]) -> set[str]:
    conversation = sample.get("conversation")
    if not isinstance(conversation, dict):
        raise ValueError(f"invalid conversation for {sample.get('sample_id')}")
    turn_ids: set[str] = set()
    for key, turns in conversation.items():
        if not re.fullmatch(r"session_\d+", key) or not isinstance(turns, list):
            continue
        for turn in turns:
            dia_id = str(turn.get("dia_id", "")).strip()
            if not dia_id:
                raise ValueError(f"missing dia_id in {sample.get('sample_id')}/{key}")
            if dia_id in turn_ids:
                raise ValueError(f"duplicate dia_id {sample.get('sample_id')}/{dia_id}")
            turn_ids.add(dia_id)
    return turn_ids


def normalize_evidence(
    raw_evidence: Any, valid_turn_ids: set[str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Normalize known LoCoMo evidence formatting without guessing missing turns."""
    raw_values = raw_evidence if isinstance(raw_evidence, list) else []
    normalized: list[str] = []
    issues: list[dict[str, Any]] = []

    for raw_value in raw_values:
        raw = str(raw_value).strip()
        parsed: list[str] = []
        for session, turn in EVIDENCE_RE.findall(raw):
            parsed.append(f"D{int(session)}:{int(turn)}")
        for session, turn in MALFORMED_EVIDENCE_RE.findall(raw):
            candidate = f"D{int(session)}:{int(turn)}"
            if candidate not in parsed:
                parsed.append(candidate)

        valid = [candidate for candidate in parsed if candidate in valid_turn_ids]
        invalid = [candidate for candidate in parsed if candidate not in valid_turn_ids]
        for candidate in valid:
            if candidate not in normalized:
                normalized.append(candidate)

        canonical_raw = raw if len(parsed) == 1 else None
        changed = (
            len(parsed) != 1
            or not parsed
            or invalid
            or (parsed and canonical_raw != parsed[0])
        )
        if changed:
            issues.append(
                {
                    "raw": raw,
                    "parsed": parsed,
                    "accepted": valid,
                    "invalid": invalid,
                }
            )

    if not raw_values:
        issues.append(
            {
                "raw": None,
                "parsed": [],
                "accepted": [],
                "invalid": [],
                "reason": "empty evidence",
            }
        )
    return normalized, issues


def load_questions(dataset_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(dataset, list) or len(dataset) != 10:
        raise ValueError("LoCoMo dataset must contain exactly 10 samples")

    questions: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    sample_turn_counts: dict[str, int] = {}
    for conversation_idx, sample in enumerate(dataset):
        sample_id = str(sample.get("sample_id", "")).strip()
        if not sample_id:
            raise ValueError(f"sample {conversation_idx} has no sample_id")
        turn_ids = conversation_turn_ids(sample)
        sample_turn_counts[sample_id] = len(turn_ids)
        qa_rows = sample.get("qa")
        if not isinstance(qa_rows, list):
            raise ValueError(f"{sample_id} qa must be a list")
        for qa_idx, qa in enumerate(qa_rows):
            category = int(qa.get("category", 0))
            if category not in CATEGORIES:
                continue
            question_id = f"conv{conversation_idx}_q{qa_idx}"
            evidence, issues = normalize_evidence(qa.get("evidence"), turn_ids)
            questions.append(
                {
                    "question_id": question_id,
                    "conversation_idx": conversation_idx,
                    "qa_idx": qa_idx,
                    "sample_id": sample_id,
                    "category": category,
                    "category_name": CATEGORY_NAMES[category],
                    "question": str(qa.get("question", "")),
                    "answer": qa.get("answer"),
                    "raw_evidence": qa.get("evidence", []),
                    "gold_evidence": evidence,
                    "evidence_issues": issues,
                    "sample_turn_count": len(turn_ids),
                }
            )
            if issues:
                audit_rows.append(
                    {
                        "question_id": question_id,
                        "sample_id": sample_id,
                        "qa_idx": qa_idx,
                        "category": category,
                        "raw_evidence": qa.get("evidence", []),
                        "normalized_evidence": evidence,
                        "issues": issues,
                    }
                )

    category_counts = Counter(question["category"] for question in questions)
    expected_category_counts = {1: 282, 2: 321, 3: 96, 4: 841}
    if len(questions) != 1540 or dict(category_counts) != expected_category_counts:
        raise ValueError(
            f"unexpected Category 1-4 distribution: total={len(questions)} "
            f"categories={dict(category_counts)}"
        )
    evidence_questions = sum(bool(question["gold_evidence"]) for question in questions)
    if evidence_questions != 1536:
        raise ValueError(f"expected 1536 evidence questions, found {evidence_questions}")

    audit = {
        "dataset_path": str(dataset_path.resolve()),
        "dataset_sha256": sha256_file(dataset_path),
        "questions": len(questions),
        "questions_with_normalized_evidence": evidence_questions,
        "questions_without_evidence": len(questions) - evidence_questions,
        "sample_turn_counts": sample_turn_counts,
        "rows_with_normalization_notes": audit_rows,
    }
    return questions, audit


def smoke_questions(questions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select one deterministic question per sample while covering all categories."""
    targets = (1, 2, 3, 4, 1, 2, 3, 4, 1, 2)
    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sample_order: list[str] = []
    for question in questions:
        sample_id = str(question["sample_id"])
        if sample_id not in by_sample:
            sample_order.append(sample_id)
        by_sample[sample_id].append(question)

    selected: list[dict[str, Any]] = []
    for sample_id, target in zip(sample_order, targets, strict=True):
        candidates = by_sample[sample_id]
        question = next(
            (
                row
                for row in candidates
                if row["category"] == target and row["gold_evidence"]
            ),
            None,
        )
        if question is None:
            question = next(row for row in candidates if row["gold_evidence"])
        selected.append(question)
    return selected


def select_questions(
    questions: list[dict[str, Any]], args: argparse.Namespace
) -> list[dict[str, Any]]:
    if args.smoke:
        if args.question_id or args.limit is not None:
            raise ValueError("--smoke cannot be combined with --question-id or --limit")
        return smoke_questions(questions)
    if args.question_id:
        wanted = set(args.question_id)
        selected = [q for q in questions if q["question_id"] in wanted]
        missing = wanted - {q["question_id"] for q in selected}
        if missing:
            raise ValueError(f"unknown question ids: {sorted(missing)}")
        return selected
    return questions if args.limit is None else questions[: args.limit]


def normalize_result(item: dict[str, Any], rank: int) -> dict[str, Any]:
    metadata = item.get("extra_metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "rank": rank,
        "memory_id": item.get("memory_id"),
        "user_id": item.get("user_id"),
        "session_id": item.get("session_id"),
        "sample_id": metadata.get("sample_id"),
        "original_session_id": metadata.get("original_session_id"),
        "dia_id": metadata.get("dia_id") or item.get("subject_id"),
        "subject_id": item.get("subject_id"),
        "speaker": metadata.get("speaker"),
        "observed_at": item.get("observed_at"),
        "retrieval_score": item.get("retrieval_score"),
        "ingest_key": metadata.get("ingest_key"),
        "content": item.get("content") or item.get("memory"),
    }


class Retriever:
    def __init__(
        self,
        *,
        api_url: str,
        master_key: str,
        user_prefix: str,
        explain: str,
        timeout: float,
        max_retries: int,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.master_key = master_key
        self.user_prefix = user_prefix
        self.explain = explain
        self.timeout = timeout
        self.max_retries = max_retries
        self.local = threading.local()

    def session(self) -> requests.Session:
        session = getattr(self.local, "session", None)
        if session is None:
            session = requests.Session()
            self.local.session = session
        return session

    def retrieve(self, question: dict[str, Any]) -> dict[str, Any]:
        user_id = f"{self.user_prefix}{question['sample_id']}"
        request_body = {
            "query": question["question"],
            "top_k": TOP_K,
            "explain": self.explain,
        }
        attempts: list[dict[str, Any]] = []
        response_body: Any = None
        final_error: str | None = None
        started = time.perf_counter()

        for attempt_number in range(1, self.max_retries + 2):
            attempt_started = time.perf_counter()
            try:
                response = self.session().post(
                    f"{self.api_url}/v1/memories/retrieve",
                    headers={
                        "Authorization": f"Bearer {self.master_key}",
                        "X-Impersonate-User": user_id,
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                    timeout=self.timeout,
                )
                attempt = {
                    "attempt": attempt_number,
                    "status_code": response.status_code,
                    "elapsed_ms": round(
                        (time.perf_counter() - attempt_started) * 1000, 3
                    ),
                }
                attempts.append(attempt)
                if response.status_code == 200:
                    response_body = response.json()
                    break
                final_error = f"HTTP {response.status_code}: {response.text[:1000]}"
                attempt["error"] = final_error
                if response.status_code not in TRANSIENT_STATUS:
                    break
            except (requests.RequestException, ValueError) as exc:
                final_error = str(exc)
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "status_code": None,
                        "elapsed_ms": round(
                            (time.perf_counter() - attempt_started) * 1000, 3
                        ),
                        "error": final_error,
                    }
                )
            if attempt_number <= self.max_retries:
                time.sleep(min(2 ** (attempt_number - 1), 8))

        total_ms = round((time.perf_counter() - started) * 1000, 3)
        base = {
            "at": utc_now(),
            "question_id": question["question_id"],
            "conversation_idx": question["conversation_idx"],
            "qa_idx": question["qa_idx"],
            "sample_id": question["sample_id"],
            "category": question["category"],
            "category_name": question["category_name"],
            "question": question["question"],
            "answer": question["answer"],
            "raw_evidence": question["raw_evidence"],
            "gold_evidence": question["gold_evidence"],
            "evidence_issues": question["evidence_issues"],
            "user_id": user_id,
            "request": request_body,
            "attempts": attempts,
            "first_pass_success": len(attempts) == 1 and response_body is not None,
            "client_total_ms": total_ms,
        }
        if response_body is None:
            return {
                **base,
                "status": "failed",
                "error": final_error or "empty response",
                "results": [],
                "explain": {},
                "validation_errors": [],
                "validation_ok": False,
            }

        if isinstance(response_body, dict):
            items = response_body.get("results", [])
            explain = response_body.get("explain", {})
        else:
            items = response_body
            explain = {}
        if not isinstance(items, list):
            items = []
        normalized = [
            normalize_result(item, rank)
            for rank, item in enumerate(items, start=1)
            if isinstance(item, dict)
        ]

        expected_results = min(TOP_K, int(question["sample_turn_count"]))
        validation_errors: list[str] = []
        if len(normalized) != expected_results:
            validation_errors.append(
                f"expected {expected_results} results, received {len(normalized)}; "
                "the current Memoria API clamps top_k to 100 unless its server limit is raised"
            )
        memory_ids: set[str] = set()
        dia_ids: set[str] = set()
        for item in normalized:
            memory_id = str(item.get("memory_id") or "")
            dia_id = str(item.get("dia_id") or "")
            if item.get("user_id") != user_id:
                validation_errors.append(
                    f"cross-user memory {memory_id}: {item.get('user_id')}"
                )
            if item.get("sample_id") != question["sample_id"]:
                validation_errors.append(
                    f"cross-sample memory {memory_id}: {item.get('sample_id')}"
                )
            if not dia_id:
                validation_errors.append(f"missing dia_id: {memory_id}")
            if not item.get("ingest_key"):
                validation_errors.append(f"missing ingest_key: {memory_id}")
            if not item.get("content"):
                validation_errors.append(f"missing content: {memory_id}")
            if memory_id in memory_ids:
                validation_errors.append(f"duplicate memory_id: {memory_id}")
            if dia_id in dia_ids:
                validation_errors.append(f"duplicate dia_id: {dia_id}")
            memory_ids.add(memory_id)
            dia_ids.add(dia_id)

        return {
            **base,
            "status": "success",
            "results": normalized,
            "explain": explain if isinstance(explain, dict) else {},
            "validation_errors": validation_errors,
            "validation_ok": not validation_errors,
        }


def percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def score_record(record: dict[str, Any]) -> dict[str, float]:
    gold = set(str(value) for value in record.get("gold_evidence", []))
    results = record.get("results", []) if record.get("validation_ok") else []
    ranked = [str(item.get("dia_id")) for item in results if item.get("dia_id")]
    metrics: dict[str, float] = {}
    first_rank = next((rank for rank, dia_id in enumerate(ranked, 1) if dia_id in gold), None)
    metrics["mrr"] = 1.0 / first_rank if first_rank else 0.0
    for cutoff in CUTOFFS:
        retrieved = set(ranked[:cutoff])
        hits = gold & retrieved
        metrics[f"hit@{cutoff}"] = float(bool(hits))
        metrics[f"recall@{cutoff}"] = len(hits) / len(gold) if gold else 0.0
        metrics[f"complete_recall@{cutoff}"] = float(bool(gold) and gold <= retrieved)
    return metrics


def aggregate_rows(rows: Sequence[dict[str, float]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0}
    output: dict[str, Any] = {"count": len(rows)}
    for key in rows[0]:
        values = [row[key] for row in rows]
        output[key] = round(statistics.fmean(values), 6)
        if key.startswith(("hit@", "complete_recall@")):
            output[f"{key}_count"] = int(sum(values))
    return output


def build_metrics(
    selected: Sequence[dict[str, Any]], records_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    selected_ids = [str(question["question_id"]) for question in selected]
    records = [records_by_id[qid] for qid in selected_ids if qid in records_by_id]
    valid_records = [
        record
        for record in records
        if record.get("status") == "success" and record.get("validation_ok") is True
    ]
    valid_by_id = {str(record["question_id"]): record for record in valid_records}
    evidence_questions = [question for question in selected if question["gold_evidence"]]

    strict_rows: list[dict[str, float]] = []
    strict_by_category: dict[str, list[dict[str, float]]] = defaultdict(list)
    successful_rows: list[dict[str, float]] = []
    for question in evidence_questions:
        record = valid_by_id.get(str(question["question_id"]))
        if record is None:
            row = score_record(
                {"gold_evidence": question["gold_evidence"], "results": [], "validation_ok": False}
            )
        else:
            row = score_record(record)
            successful_rows.append(row)
        strict_rows.append(row)
        strict_by_category[question["category_name"]].append(row)

    latencies = [float(record.get("client_total_ms", 0.0)) for record in valid_records]
    paths = Counter(str(record.get("explain", {}).get("path", "missing")) for record in valid_records)
    first_pass = sum(record.get("first_pass_success") is True for record in valid_records)
    validation_error_records = [
        record for record in records if record.get("validation_ok") is not True
    ]
    return {
        "generated_at": utc_now(),
        "operational": {
            "selected_questions": len(selected),
            "questions_with_evidence": len(evidence_questions),
            "questions_without_evidence": len(selected) - len(evidence_questions),
            "snapshot_records": len(records),
            "valid_retrievals": len(valid_records),
            "failed_or_invalid_retrievals": len(selected) - len(valid_records),
            "first_pass_successes": first_pass,
            "first_pass_success_rate": round(first_pass / len(selected), 6)
            if selected
            else 0.0,
            "client_latency_ms": {
                "p50": round(percentile(latencies, 0.50) or 0.0, 3),
                "p95": round(percentile(latencies, 0.95) or 0.0, 3),
                "max": round(max(latencies), 3) if latencies else None,
            },
            "retrieval_paths": dict(sorted(paths.items())),
            "validation_error_examples": [
                {
                    "question_id": record.get("question_id"),
                    "errors": record.get("validation_errors", []),
                    "error": record.get("error"),
                }
                for record in validation_error_records[:20]
            ],
        },
        "evidence_metrics": {
            "denominator_note": (
                "strict metrics include every selected question with normalized evidence; "
                "failed or invalid retrievals score zero"
            ),
            "overall_strict": aggregate_rows(strict_rows),
            "by_category_strict": {
                category: aggregate_rows(rows)
                for category, rows in sorted(strict_by_category.items())
            },
            "successful_only_diagnostic": aggregate_rows(successful_rows),
        },
        "complete": len(valid_records) == len(selected),
    }


def build_report(metrics: dict[str, Any]) -> str:
    operational = metrics["operational"]
    overall = metrics["evidence_metrics"]["overall_strict"]
    lines = [
        "# LoCoMo Memoria Retrieval-only report",
        "",
        f"- Status: **{'COMPLETE' if metrics['complete'] else 'INCOMPLETE'}**",
        f"- Selected questions: {operational['selected_questions']}",
        f"- Evidence-evaluable questions: {operational['questions_with_evidence']}",
        f"- Valid retrievals: {operational['valid_retrievals']}/{operational['selected_questions']}",
        f"- Client latency P50/P95: {operational['client_latency_ms']['p50']:.1f} / "
        f"{operational['client_latency_ms']['p95']:.1f} ms",
        "",
        "## Strict evidence metrics",
        "",
        "Failed or invalid retrievals are retained in the denominator and score zero.",
        "",
        "| Metric | @10 | @20 | @50 | @200 |",
        "| --- | ---: | ---: | ---: | ---: |",
        "| Hit accuracy | "
        + " | ".join(
            f"{overall.get(f'hit@{cutoff}', 0.0):.2%} "
            f"({overall.get(f'hit@{cutoff}_count', 0)}/{overall.get('count', 0)})"
            for cutoff in CUTOFFS
        )
        + " |",
        "| Mean evidence recall | "
        + " | ".join(
            f"{overall.get(f'recall@{cutoff}', 0.0):.2%}" for cutoff in CUTOFFS
        )
        + " |",
        "| Complete recall | "
        + " | ".join(
            f"{overall.get(f'complete_recall@{cutoff}', 0.0):.2%} "
            f"({overall.get(f'complete_recall@{cutoff}_count', 0)}/{overall.get('count', 0)})"
            for cutoff in CUTOFFS
        )
        + " |",
        "",
        f"MRR@200: {overall.get('mrr', 0.0):.4f}",
        "",
        "## By category",
        "",
        "| Category | N | Hit@10 | Hit@20 | Hit@50 | Hit@200 | Complete@200 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, row in metrics["evidence_metrics"]["by_category_strict"].items():
        lines.append(
            f"| {category} | {row.get('count', 0)} | "
            f"{row.get('hit@10', 0.0):.2%} | {row.get('hit@20', 0.0):.2%} | "
            f"{row.get('hit@50', 0.0):.2%} | {row.get('hit@200', 0.0):.2%} | "
            f"{row.get('complete_recall@200', 0.0):.2%} |"
        )
    lines.extend(["", "## Retrieval paths", ""])
    if operational["retrieval_paths"]:
        for path, count in operational["retrieval_paths"].items():
            lines.append(f"- {path}: {count}")
    else:
        lines.append("- No valid retrieval path recorded.")
    if operational["validation_error_examples"]:
        lines.extend(["", "## Validation errors", ""])
        for row in operational["validation_error_examples"]:
            detail = row["errors"] or [row.get("error") or "unknown error"]
            lines.append(f"- `{row['question_id']}`: {'; '.join(detail)}")
    return "\n".join(lines) + "\n"


def validate_ingest_run(
    ingest_run_dir: Path, dataset_sha256: str, user_prefix: str
) -> dict[str, Any]:
    manifest_path = ingest_run_dir / "manifest.json"
    summary_path = ingest_run_dir / "summary.json"
    if not manifest_path.is_file() or not summary_path.is_file():
        raise FileNotFoundError(f"missing ingest manifest/summary under {ingest_run_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if manifest.get("dataset_sha256") != dataset_sha256:
        failures.append("ingest dataset SHA-256 mismatch")
    if manifest.get("user_prefix") != user_prefix:
        failures.append("ingest user prefix mismatch")
    expected_summary = {
        "selected_samples": 10,
        "completed_samples": 10,
        "sessions": 272,
        "expected_memories": 5882,
        "accepted_memories": 5882,
        "failed_memories": 0,
        "missing_ingest_keys": 0,
        "extra_ingest_keys": 0,
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            failures.append(f"ingest summary {key}={summary.get(key)!r}, expected {expected!r}")
    if failures:
        raise ValueError("; ".join(failures))
    return {
        "ingest_run_dir": str(ingest_run_dir.resolve()),
        "ingest_manifest_sha256": sha256_file(manifest_path),
        "ingest_summary_sha256": sha256_file(summary_path),
        "memoria_commit": manifest.get("memoria_commit"),
        "memoria_patch_sha256": manifest.get("memoria_patch_sha256"),
        "embedding_model": manifest.get("embedding_model"),
        "embedding_dimension": manifest.get("embedding_dimension"),
        "time_mapping": manifest.get("time_mapping"),
        "ingest_mapping": manifest.get("ingest_mapping"),
    }


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[3]
    workspace_root = project_root.parent
    default_ingest_run = (
        project_root / "memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root
        / "memoria/datasets/downloads/public-benchmarks/locomo/locomo10.json",
    )
    parser.add_argument("--ingest-run-dir", type=Path, default=default_ingest_run)
    parser.add_argument(
        "--runtime-env", type=Path, default=workspace_root / "memoria_runtime/.env"
    )
    parser.add_argument(
        "--runtime-api-route",
        type=Path,
        default=workspace_root
        / "memoria_runtime/source/Memoria/memoria/crates/memoria-api/src/routes/memory.rs",
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--user-prefix", default="locomo-qwen-v4-")
    parser.add_argument("--explain", default="verbose")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--question-id", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if args.limit is not None and args.limit < 1:
        raise ValueError("limit must be positive")
    if not args.dataset.is_file():
        raise FileNotFoundError(args.dataset)
    if not args.runtime_api_route.is_file():
        raise FileNotFoundError(args.runtime_api_route)
    dataset_sha256 = sha256_file(args.dataset)
    if dataset_sha256 != OFFICIAL_DATASET_SHA256:
        raise ValueError(
            f"dataset SHA-256 mismatch: {dataset_sha256}; expected {OFFICIAL_DATASET_SHA256}"
        )

    questions, evidence_audit = load_questions(args.dataset)
    selected = select_questions(questions, args)
    selected_ids = [str(question["question_id"]) for question in selected]
    ingest_config = validate_ingest_run(
        args.ingest_run_dir, dataset_sha256, args.user_prefix
    )
    env = read_env(args.runtime_env)
    master_key = os.getenv("MEMORIA_MASTER_KEY") or env.get("MEMORIA_MASTER_KEY", "")
    if not master_key:
        raise ValueError(
            "MEMORIA_MASTER_KEY is missing; export it or configure the runtime .env"
        )

    args.run_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = args.run_dir / "retrieval.jsonl"
    manifest_path = args.run_dir / "manifest.json"
    frozen_manifest = {
        "dataset_path": str(args.dataset.resolve()),
        "dataset_sha256": dataset_sha256,
        "categories": list(CATEGORIES),
        "selected_question_ids": selected_ids,
        "selection": "stratified-smoke10" if args.smoke else "explicit-or-full",
        "api_url": args.api_url.rstrip("/"),
        "endpoint": "/v1/memories/retrieve",
        "query_template": "raw_question",
        "top_k": TOP_K,
        "cutoffs": list(CUTOFFS),
        "explain": args.explain,
        "user_prefix": args.user_prefix,
        "workers": args.workers,
        "timeout_seconds": args.timeout,
        "max_retries": args.max_retries,
        "runner_sha256": sha256_file(Path(__file__)),
        "retrieval_api_route_path": str(args.runtime_api_route.resolve()),
        "retrieval_api_route_sha256": sha256_file(args.runtime_api_route),
        "mem0_baseline_commit": MEM0_BASELINE_COMMIT,
        **ingest_config,
    }
    if manifest_path.exists():
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
        current_frozen = {key: current.get(key) for key in frozen_manifest}
        if current_frozen != frozen_manifest:
            raise ValueError("run manifest does not match requested frozen configuration")
    else:
        atomic_json(manifest_path, {"created_at": utc_now(), **frozen_manifest})
    atomic_json(args.run_dir / "evidence_normalization.json", evidence_audit)

    previous = latest_records(snapshot_path)
    completed_ids = {
        question_id
        for question_id, record in previous.items()
        if record.get("status") == "success" and record.get("validation_ok") is True
    }
    pending = [q for q in selected if q["question_id"] not in completed_ids]
    snapshot = JsonlWriter(snapshot_path)
    checkpoint = JsonlWriter(args.run_dir / "checkpoint.jsonl")
    errors = JsonlWriter(args.run_dir / "errors.jsonl")
    retriever = Retriever(
        api_url=args.api_url,
        master_key=master_key,
        user_prefix=args.user_prefix,
        explain=args.explain,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )

    started = time.monotonic()
    processed = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_map = {
                pool.submit(retriever.retrieve, question): question["question_id"]
                for question in pending
            }
            for future in concurrent.futures.as_completed(future_map):
                record = future.result()
                snapshot.write(record)
                checkpoint.write(
                    {
                        "at": record["at"],
                        "question_id": record["question_id"],
                        "status": record["status"],
                        "validation_ok": record["validation_ok"],
                    }
                )
                if record["status"] != "success" or not record["validation_ok"]:
                    errors.write(record)
                processed += 1
                print(
                    f"[{processed}/{len(pending)}] question={record['question_id']} "
                    f"sample={record['sample_id']} status={record['status']} "
                    f"valid={record['validation_ok']} results={len(record['results'])} "
                    f"latency_ms={record['client_total_ms']:.1f}",
                    flush=True,
                )
    finally:
        snapshot.close()
        checkpoint.close()
        errors.close()

    records_by_id = latest_records(snapshot_path)
    metrics = build_metrics(selected, records_by_id)
    atomic_json(args.run_dir / "metrics.json", metrics)
    (args.run_dir / "report.md").write_text(build_report(metrics), encoding="utf-8")
    summary = {
        "finished_at": utc_now(),
        "selected_questions": len(selected),
        "snapshot_records": metrics["operational"]["snapshot_records"],
        "valid_retrievals": metrics["operational"]["valid_retrievals"],
        "failed_or_invalid_retrievals": metrics["operational"][
            "failed_or_invalid_retrievals"
        ],
        "processed_this_invocation": processed,
        "resumed_existing": len(selected) - len(pending),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "complete": metrics["complete"],
    }
    atomic_json(args.run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if metrics["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
