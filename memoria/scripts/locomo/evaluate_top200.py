#!/usr/bin/env python3
"""Run Mem0-compatible GPT-5 Reader + GPT-5 Judge on frozen Top-200 results."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import statistics
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import openai

from mem0_prompts import (
    ANSWERER_MEMORY_LIMIT,
    ANSWER_GENERATION_PROMPT,
    CATEGORY_NAMES,
    JUDGE_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    get_answer_generation_prompt,
    get_judge_prompt,
    preprocess_answer,
)


OFFICIAL_DATASET_SHA256 = (
    "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
)
MEM0_BASELINE_COMMIT = "4b61c5d31b9c668a12b4f5e78064248a02c82d2b"
EXPECTED_PROMPT_HASHES = {
    "answer_generation_prompt": "79c9f09bcc8d5e9e8b7e9786af587b02a67d366ab79285fc148b73fd20f6297b",
    "judge_system_prompt": "36c007917faf1ab84516cdca577fb523711a9b993706fbae8ae37806e6f9adcc",
    "judge_prompt_without_evidence": "d248e056d993725e28fba8d16ca7081f0b59deae272ef294f3c6b00d48eac02b",
}
CATEGORIES = (1, 2, 3, 4)
TOP_K = 200
DEFAULT_MAX_TOKENS = 4096
DATE_FORMATS = ("%I:%M %p on %d %B, %Y", "%I:%M %p on %d %b, %Y")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", buffering=1) as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def latest_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.is_file():
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


def successful_records(path: Path) -> dict[str, dict[str, Any]]:
    return {
        qid: record
        for qid, record in latest_records(path).items()
        if record.get("status") == "success"
    }


def parse_locomo_date(value: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except (TypeError, ValueError):
            continue
    raise ValueError(f"cannot parse LoCoMo date: {value!r}")


def source_time_index(sample: dict[str, Any]) -> tuple[dict[str, str], str]:
    conversation = sample["conversation"]
    sessions: list[tuple[datetime, str, str]] = []
    dia_dates: dict[str, str] = {}
    for key, turns in conversation.items():
        match = re.fullmatch(r"session_(\d+)", key)
        if not match or not isinstance(turns, list):
            continue
        raw_date = str(conversation[f"{key}_date_time"])
        parsed = parse_locomo_date(raw_date)
        iso_date = parsed.isoformat()
        sessions.append((parsed, key, raw_date))
        for turn in turns:
            dia_id = str(turn.get("dia_id", ""))
            if not dia_id:
                raise ValueError(f"missing dia_id in {sample.get('sample_id')}/{key}")
            dia_dates[dia_id] = iso_date
    if not sessions:
        raise ValueError(f"sample {sample.get('sample_id')} has no sessions")
    sessions.sort()
    return dia_dates, sessions[-1][2]


def load_dataset_questions(dataset_path: Path) -> tuple[list[dict[str, Any]], dict[int, dict[str, str]], dict[int, str]]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(dataset, list) or len(dataset) != 10:
        raise ValueError("LoCoMo dataset must contain exactly 10 samples")
    questions: list[dict[str, Any]] = []
    dates_by_conversation: dict[int, dict[str, str]] = {}
    reference_dates: dict[int, str] = {}
    for conversation_idx, sample in enumerate(dataset):
        dates_by_conversation[conversation_idx], reference_dates[conversation_idx] = source_time_index(sample)
        for qa_idx, qa in enumerate(sample.get("qa", [])):
            category = int(qa.get("category", 0))
            if category not in CATEGORIES:
                continue
            questions.append(
                {
                    "question_id": f"conv{conversation_idx}_q{qa_idx}",
                    "conversation_idx": conversation_idx,
                    "qa_idx": qa_idx,
                    "sample_id": str(sample["sample_id"]),
                    "category": category,
                    "category_name": CATEGORY_NAMES[category],
                    "question": str(qa["question"]),
                    "answer": str(qa["answer"]),
                    "gold_evidence": [str(value) for value in qa.get("evidence", [])],
                }
            )
    counts = Counter(row["category"] for row in questions)
    if len(questions) != 1540 or counts != Counter({1: 282, 2: 321, 3: 96, 4: 841}):
        raise ValueError(f"unexpected Category 1-4 distribution: {dict(counts)}")
    return questions, dates_by_conversation, reference_dates


def validate_prompt_hashes() -> dict[str, str]:
    actual = {
        "answer_generation_prompt": sha256_text(ANSWER_GENERATION_PROMPT),
        "judge_system_prompt": sha256_text(JUDGE_SYSTEM_PROMPT),
        "judge_prompt_without_evidence": sha256_text(JUDGE_PROMPT),
    }
    if actual != EXPECTED_PROMPT_HASHES:
        raise ValueError(f"vendored Mem0 prompt drift: {actual}")
    return actual


def load_retrieval_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    records = latest_records(path)
    valid: dict[str, dict[str, Any]] = {}
    for qid, record in records.items():
        results = record.get("results")
        if (
            record.get("status") != "success"
            or record.get("validation_ok") is not True
            or not isinstance(results, list)
            or len(results) != TOP_K
        ):
            raise ValueError(f"invalid Top-200 retrieval record: {qid}")
        valid[qid] = record
    return valid


def select_questions(
    questions: list[dict[str, Any]], limit: int | None, question_ids: Sequence[str]
) -> list[dict[str, Any]]:
    if question_ids:
        wanted = set(question_ids)
        selected = [row for row in questions if row["question_id"] in wanted]
        missing = wanted - {row["question_id"] for row in selected}
        if missing:
            raise ValueError(f"unknown question ids: {sorted(missing)}")
        return selected
    return questions if limit is None else questions[:limit]


def build_reader_input(
    question: dict[str, Any],
    retrieval: dict[str, Any],
    source_dates: dict[str, str],
    reference_date: str,
) -> tuple[str, list[str]]:
    search_results: list[dict[str, str]] = []
    ranked_ids: list[str] = []
    for result in retrieval["results"][:TOP_K]:
        dia_id = str(result.get("dia_id", ""))
        if dia_id not in source_dates:
            raise ValueError(f"{question['question_id']} has unknown dia_id {dia_id!r}")
        ranked_ids.append(str(result["memory_id"]))
        search_results.append(
            {
                "memory": str(result["content"]),
                "created_at": source_dates[dia_id],
                "memory_id": str(result["memory_id"]),
            }
        )
    prompt = get_answer_generation_prompt(
        question["question"], search_results, reference_date=reference_date
    )
    chronological_ids = [
        row["memory_id"]
        for row in sorted(search_results, key=lambda row: row["created_at"])
    ]
    return prompt, chronological_ids


def extract_answer(raw_response: str) -> str:
    if "ANSWER:" in raw_response:
        return raw_response.rsplit("ANSWER:", 1)[-1].strip()
    return raw_response.strip()


class SlidingWindowLimiter:
    """Small dependency-free approximation of Mem0's per-client RPM limiter."""

    def __init__(self, rpm: int) -> None:
        if rpm < 1:
            raise ValueError("rpm must be positive")
        self.rpm = rpm
        self.timestamps: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self.lock:
                now = time.monotonic()
                while self.timestamps and now - self.timestamps[0] >= 60:
                    self.timestamps.popleft()
                if len(self.timestamps) < self.rpm:
                    self.timestamps.append(now)
                    return
                delay = max(0.01, 60 - (now - self.timestamps[0]))
            await asyncio.sleep(delay)


@dataclass
class Completion:
    content: str
    response_id: str | None
    response_model: str | None
    finish_reason: str | None
    usage: dict[str, int | None]
    latency_ms: float
    attempts: int


class Mem0CompatibleLLM:
    def __init__(
        self,
        *,
        model: str,
        provider: str,
        rpm: int,
        timeout: float,
        max_retries: int,
        base_url: str | None,
        azure_endpoint: str | None,
        azure_api_version: str,
    ) -> None:
        self.model = model
        self.provider = provider
        self.timeout = timeout
        self.max_retries = max_retries
        self.limiter = SlidingWindowLimiter(rpm)
        client_timeout = openai.Timeout(timeout, connect=10.0)
        if provider == "azure":
            self.client = openai.AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", ""),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=azure_api_version,
                timeout=client_timeout,
            )
        else:
            self.client = openai.AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=base_url or os.getenv("OPENAI_BASE_URL") or None,
                timeout=client_timeout,
            )

    async def generate(self, *, system: str, user: str, structured: bool) -> Completion:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            try:
                await self.limiter.acquire()
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "max_completion_tokens": DEFAULT_MAX_TOKENS,
                }
                if structured:
                    kwargs["response_format"] = {"type": "json_object"}
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(**kwargs), timeout=self.timeout
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError(
                        f"empty completion, finish_reason={response.choices[0].finish_reason}"
                    )
                if structured:
                    # Mem0 retries structured-output parse failures inside the LLM client.
                    validate_judgment(content)
                usage = response.usage
                return Completion(
                    content=content.strip(),
                    response_id=getattr(response, "id", None),
                    response_model=getattr(response, "model", None),
                    finish_reason=response.choices[0].finish_reason,
                    usage={
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    },
                    latency_ms=round((time.perf_counter() - started) * 1000, 3),
                    attempts=attempt,
                )
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(2 * attempt)
        raise RuntimeError(f"LLM failed after {self.max_retries} attempts: {last_error}")


def validate_judgment(raw: str) -> tuple[dict[str, Any], str]:
    parsed = json.loads(raw)
    if set(parsed) == {"final"}:
        parsed = json.loads(parsed["final"]) if isinstance(parsed["final"], str) else parsed["final"]
    if not isinstance(parsed, dict):
        raise ValueError("judge output is not a JSON object")
    label = str(parsed.get("label", "")).upper()
    if label not in {"CORRECT", "WRONG"}:
        raise ValueError(f"invalid judge label: {label!r}")
    return parsed, label


def evidence_state(question: dict[str, Any], retrieval: dict[str, Any]) -> str:
    # Retrieval.py already normalized evidence; use its frozen form, including four empty rows.
    gold = set(str(value) for value in retrieval.get("gold_evidence", []))
    if not gold:
        return "no_evidence"
    found = gold & {str(row.get("dia_id")) for row in retrieval["results"][:TOP_K]}
    if not found:
        return "missing"
    return "complete" if found == gold else "partial"


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def aggregate_usage(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {"calls": len(records)}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [row.get("usage", {}).get(key) for row in records]
        output[key] = sum(value for value in values if isinstance(value, int))
    latencies = [float(row["latency_ms"]) for row in records if row.get("latency_ms") is not None]
    output["latency_ms"] = {
        "p50": round(percentile(latencies, 0.5) or 0.0, 3),
        "p95": round(percentile(latencies, 0.95) or 0.0, 3),
        "max": round(max(latencies), 3) if latencies else None,
    }
    return output


def build_metrics(
    selected: Sequence[dict[str, Any]],
    retrievals: dict[str, dict[str, Any]],
    answers: dict[str, dict[str, Any]],
    judgments: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_category: dict[str, list[bool]] = defaultdict(list)
    by_evidence: dict[str, list[bool]] = defaultdict(list)
    scores: list[bool] = []
    for question in selected:
        qid = question["question_id"]
        correct = judgments.get(qid, {}).get("label") == "CORRECT"
        scores.append(correct)
        by_category[question["category_name"]].append(correct)
        by_evidence[evidence_state(question, retrievals[qid])].append(correct)

    def summarize(values: Sequence[bool]) -> dict[str, Any]:
        correct = sum(values)
        return {
            "total": len(values),
            "correct": correct,
            "wrong_or_missing": len(values) - correct,
            "accuracy": round(correct / len(values), 6) if values else 0.0,
        }

    answer_rows = [answers[q["question_id"]] for q in selected if q["question_id"] in answers]
    judge_rows = [judgments[q["question_id"]] for q in selected if q["question_id"] in judgments]
    return {
        "generated_at": utc_now(),
        "overall": summarize(scores),
        "by_category": {key: summarize(value) for key, value in sorted(by_category.items())},
        "by_top200_evidence_state": {
            key: summarize(value) for key, value in sorted(by_evidence.items())
        },
        "operations": {
            "selected_questions": len(selected),
            "successful_answers": len(answer_rows),
            "successful_judgments": len(judge_rows),
            "failed_or_pending_answers": len(selected) - len(answer_rows),
            "failed_or_pending_judgments": len(selected) - len(judge_rows),
            "answerer": aggregate_usage(answer_rows),
            "judge": aggregate_usage(judge_rows),
        },
        "complete": len(answer_rows) == len(selected) and len(judge_rows) == len(selected),
    }


def build_report(metrics: dict[str, Any]) -> str:
    overall = metrics["overall"]
    lines = [
        "# LoCoMo Memoria Top-200 Reader + Judge",
        "",
        f"- Status: **{'COMPLETE' if metrics['complete'] else 'INCOMPLETE'}**",
        f"- Accuracy: **{overall['accuracy']:.2%}** ({overall['correct']}/{overall['total']})",
        "- Reader/Judge protocol: Mem0 prompts, GPT-5, no judge evidence",
        "- Failed or missing judgments remain in the strict denominator as wrong.",
        "",
        "## By category",
        "",
        "| Category | Correct | Total | Accuracy |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, row in metrics["by_category"].items():
        lines.append(f"| {name} | {row['correct']} | {row['total']} | {row['accuracy']:.2%} |")
    lines.extend(
        [
            "",
            "## By Top-200 evidence state",
            "",
            "| Evidence state | Correct | Total | Accuracy |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name, row in metrics["by_top200_evidence_state"].items():
        lines.append(f"| {name} | {row['correct']} | {row['total']} | {row['accuracy']:.2%} |")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[3]
    default_base = project_root / "memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root / "memoria/datasets/downloads/public-benchmarks/locomo/locomo10.json",
    )
    parser.add_argument(
        "--retrieval-run-dir",
        type=Path,
        default=default_base / "mem0-compatible-retrieval-top200-full1540-v1",
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--provider", choices=("openai", "azure"), default="openai")
    parser.add_argument("--judge-provider", choices=("openai", "azure"))
    parser.add_argument("--answerer-model", default="gpt-5")
    parser.add_argument("--judge-model", default="gpt-5")
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL"),
        help="OpenAI-compatible API base URL, for example https://aihubmix.com/v1",
    )
    parser.add_argument("--azure-endpoint")
    parser.add_argument("--azure-api-version", default="2024-12-01-preview")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--rpm", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--question-id", action="append", default=[])
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    if args.workers < 1 or args.rpm < 1 or args.max_retries < 1:
        raise ValueError("workers, rpm, and max-retries must be positive")
    if args.limit is not None and args.limit < 1:
        raise ValueError("limit must be positive")
    if args.limit is not None and args.question_id:
        raise ValueError("--limit and --question-id cannot be combined")

    dataset_sha = sha256_file(args.dataset)
    if dataset_sha != OFFICIAL_DATASET_SHA256:
        raise ValueError(f"dataset SHA-256 mismatch: {dataset_sha}")
    prompt_hashes = validate_prompt_hashes()
    questions, dates_by_conversation, reference_dates = load_dataset_questions(args.dataset)
    selected = select_questions(questions, args.limit, args.question_id)
    retrieval_path = args.retrieval_run_dir / "retrieval.jsonl"
    retrieval_manifest_path = args.retrieval_run_dir / "manifest.json"
    retrievals = load_retrieval_snapshot(retrieval_path)
    missing = [q["question_id"] for q in selected if q["question_id"] not in retrievals]
    if missing:
        raise ValueError(f"retrieval snapshot is missing {len(missing)} selected questions")
    retrieval_manifest = json.loads(retrieval_manifest_path.read_text(encoding="utf-8"))
    if retrieval_manifest.get("dataset_sha256") != dataset_sha:
        raise ValueError("retrieval manifest dataset SHA-256 mismatch")
    if retrieval_manifest.get("top_k") != TOP_K:
        raise ValueError("retrieval manifest is not Top-200")

    judge_provider = args.judge_provider or args.provider
    frozen_manifest = {
        "protocol": "mem0-compatible-locomo-reader-judge-v1",
        "mem0_baseline_commit": MEM0_BASELINE_COMMIT,
        "categories": list(CATEGORIES),
        "top_k": TOP_K,
        "with_judge_evidence": False,
        "user_profile": False,
        "dataset_path": str(args.dataset.resolve()),
        "dataset_sha256": dataset_sha,
        "retrieval_run_dir": str(args.retrieval_run_dir.resolve()),
        "retrieval_snapshot_sha256": sha256_file(retrieval_path),
        "retrieval_manifest_sha256": sha256_file(retrieval_manifest_path),
        "embedding_model": retrieval_manifest.get("embedding_model"),
        "embedding_dimension": retrieval_manifest.get("embedding_dimension"),
        "selected_question_ids": [q["question_id"] for q in selected],
        "answerer_model": args.answerer_model,
        "answerer_provider": args.provider,
        "openai_compatible_base_url": args.base_url if args.provider == "openai" else None,
        "judge_model": args.judge_model,
        "judge_provider": judge_provider,
        "api_style": "chat.completions",
        "max_completion_tokens": DEFAULT_MAX_TOKENS,
        "temperature": "provider_default_for_gpt5_parameter_omitted",
        "rpm_per_client": args.rpm,
        "workers": args.workers,
        "timeout_seconds": args.timeout,
        "max_retries": args.max_retries,
        "prompt_hashes": prompt_hashes,
        "prompt_module_sha256": sha256_file(Path(__file__).with_name("mem0_prompts.py")),
        "runner_sha256": sha256_file(Path(__file__)),
        "reader_memory_order": "top200_then_original_session_time_ascending",
        "reference_date": "latest_original_session_date_per_sample",
    }
    manifest_path = args.run_dir / "manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        old_frozen = {key: old.get(key) for key in frozen_manifest}
        if old_frozen != frozen_manifest:
            raise ValueError("run manifest does not match requested frozen configuration")
    else:
        atomic_json(manifest_path, {"created_at": utc_now(), **frozen_manifest})

    answers_path = args.run_dir / "answers.jsonl"
    judgments_path = args.run_dir / "judgments.jsonl"
    errors_path = args.run_dir / "errors.jsonl"
    answers = successful_records(answers_path)
    judgments = successful_records(judgments_path)

    answerer = Mem0CompatibleLLM(
        model=args.answerer_model,
        provider=args.provider,
        rpm=args.rpm,
        timeout=args.timeout,
        max_retries=args.max_retries,
        base_url=args.base_url,
        azure_endpoint=args.azure_endpoint,
        azure_api_version=args.azure_api_version,
    )
    judge = Mem0CompatibleLLM(
        model=args.judge_model,
        provider=judge_provider,
        rpm=args.rpm,
        timeout=args.timeout,
        max_retries=args.max_retries,
        base_url=args.base_url,
        azure_endpoint=args.azure_endpoint,
        azure_api_version=args.azure_api_version,
    )

    write_lock = asyncio.Lock()
    progress_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(args.workers)
    progress = 0

    async def write(path: Path, record: dict[str, Any]) -> None:
        async with write_lock:
            append_jsonl(path, record)

    async def process(question: dict[str, Any]) -> None:
        nonlocal progress
        qid = question["question_id"]
        retrieval = retrievals[qid]
        answer_record = answers.get(qid)
        if answer_record is None:
            try:
                reader_prompt, chronological_ids = build_reader_input(
                    question,
                    retrieval,
                    dates_by_conversation[question["conversation_idx"]],
                    reference_dates[question["conversation_idx"]],
                )
                async with semaphore:
                    completion = await answerer.generate(system="", user=reader_prompt, structured=False)
                answer_record = {
                    "at": utc_now(),
                    "status": "success",
                    **question,
                    "reference_date": reference_dates[question["conversation_idx"]],
                    "memories_evaluated": TOP_K,
                    "ranked_memory_ids": [str(row["memory_id"]) for row in retrieval["results"]],
                    "chronological_memory_ids": chronological_ids,
                    "prompt_sha256": sha256_text(reader_prompt),
                    "raw_response": completion.content,
                    "generated_answer": extract_answer(completion.content),
                    "provider": args.provider,
                    "requested_model": args.answerer_model,
                    "response_model": completion.response_model,
                    "response_id": completion.response_id,
                    "finish_reason": completion.finish_reason,
                    "usage": completion.usage,
                    "latency_ms": completion.latency_ms,
                    "attempts": completion.attempts,
                }
                await write(answers_path, answer_record)
                answers[qid] = answer_record
            except Exception as exc:
                failure = {
                    "at": utc_now(), "stage": "answerer", "status": "failed",
                    **question, "error": str(exc),
                }
                await write(answers_path, failure)
                await write(errors_path, failure)
                answer_record = None

        judgment = judgments.get(qid)
        if answer_record is not None and judgment is None:
            try:
                gold = preprocess_answer(question["category"], question["answer"])
                judge_prompt = get_judge_prompt(
                    question["category"], question["question"], gold,
                    answer_record["generated_answer"],
                )
                async with semaphore:
                    completion = await judge.generate(
                        system=JUDGE_SYSTEM_PROMPT, user=judge_prompt, structured=True
                    )
                parsed, label = validate_judgment(completion.content)
                judgment = {
                    "at": utc_now(),
                    "status": "success",
                    **question,
                    "processed_gold_answer": gold,
                    "generated_answer": answer_record["generated_answer"],
                    "prompt_sha256": sha256_text(judge_prompt),
                    "raw_response": completion.content,
                    "reasoning": str(parsed.get("reasoning", "")),
                    "label": label,
                    "score": 1 if label == "CORRECT" else 0,
                    "provider": judge_provider,
                    "requested_model": args.judge_model,
                    "response_model": completion.response_model,
                    "response_id": completion.response_id,
                    "finish_reason": completion.finish_reason,
                    "usage": completion.usage,
                    "latency_ms": completion.latency_ms,
                    "attempts": completion.attempts,
                }
                await write(judgments_path, judgment)
                judgments[qid] = judgment
            except Exception as exc:
                failure = {
                    "at": utc_now(), "stage": "judge", "status": "failed",
                    **question, "error": str(exc),
                }
                await write(judgments_path, failure)
                await write(errors_path, failure)

        async with progress_lock:
            progress += 1
            state = judgments.get(qid, {}).get("label", "FAILED")
            print(
                f"[{progress}/{len(selected)}] question={qid} sample={question['sample_id']} "
                f"answer={'ok' if qid in answers else 'failed'} judge={state}",
                flush=True,
            )

    # Match Mem0's shape: ten conversations progress concurrently, questions remain ordered per conversation.
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for question in selected:
        grouped[question["conversation_idx"]].append(question)

    async def process_conversation(rows: Sequence[dict[str, Any]]) -> None:
        for row in rows:
            await process(row)

    await asyncio.gather(*(process_conversation(rows) for _, rows in sorted(grouped.items())))

    metrics = build_metrics(selected, retrievals, answers, judgments)
    atomic_json(args.run_dir / "metrics.json", metrics)
    (args.run_dir / "report.md").write_text(build_report(metrics), encoding="utf-8")
    summary = {
        "finished_at": utc_now(),
        "selected_questions": len(selected),
        "successful_answers": metrics["operations"]["successful_answers"],
        "successful_judgments": metrics["operations"]["successful_judgments"],
        "correct": metrics["overall"]["correct"],
        "accuracy": metrics["overall"]["accuracy"],
        "complete": metrics["complete"],
    }
    atomic_json(args.run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if metrics["complete"] else 2


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
