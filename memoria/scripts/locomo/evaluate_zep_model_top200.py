#!/usr/bin/env python3
"""Evaluate Memoria with Zep's published GPT-5.4 model setup and Mem0 prompts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import openai

import evaluate_top200 as common


ZEP_RESEARCH_URL = "https://www.getzep.com/research/"
REASONING_EFFORT = "medium"
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_MAX_OUTPUT_TOKENS = 4096


class SlidingWindowLimiter:
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
    status: str | None
    usage: dict[str, int | None]
    latency_ms: float
    attempts: int


class ResponsesLLM:
    """GPT-5.4 Responses client with medium reasoning and resumable-call metadata."""

    def __init__(
        self,
        *,
        model: str,
        rpm: int,
        timeout: float,
        max_retries: int,
        base_url: str | None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.limiter = SlidingWindowLimiter(rpm)
        self.client = openai.AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL") or None,
            timeout=openai.Timeout(timeout, connect=10.0),
        )

    async def generate(self, *, system: str, user: str, structured: bool) -> Completion:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            try:
                await self.limiter.acquire()
                request: dict[str, Any] = {
                    "model": self.model,
                    "input": user,
                    "reasoning": {"effort": REASONING_EFFORT},
                    "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
                }
                if system:
                    request["instructions"] = system
                response = await asyncio.wait_for(
                    self.client.responses.create(**request), timeout=self.timeout
                )
                content = response.output_text
                if not content:
                    raise ValueError(
                        f"empty response, status={getattr(response, 'status', None)}"
                    )
                content = content.strip()
                if structured:
                    # Match the Mem0 protocol: only valid CORRECT/WRONG JSON is accepted.
                    common.validate_judgment(content)
                usage = getattr(response, "usage", None)
                output_details = getattr(usage, "output_tokens_details", None)
                return Completion(
                    content=content,
                    response_id=getattr(response, "id", None),
                    response_model=getattr(response, "model", None),
                    status=getattr(response, "status", None),
                    usage={
                        "prompt_tokens": getattr(usage, "input_tokens", None),
                        "completion_tokens": getattr(usage, "output_tokens", None),
                        "reasoning_tokens": getattr(output_details, "reasoning_tokens", None),
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


def aggregate_usage(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {"calls": len(records)}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "total_tokens",
    ):
        values = [row.get("usage", {}).get(key) for row in records]
        output[key] = sum(value for value in values if isinstance(value, int))
    latencies = [
        float(row["latency_ms"])
        for row in records
        if row.get("latency_ms") is not None
    ]
    output["latency_ms"] = {
        "p50": round(common.percentile(latencies, 0.5) or 0.0, 3),
        "p95": round(common.percentile(latencies, 0.95) or 0.0, 3),
        "max": round(max(latencies), 3) if latencies else None,
    }
    return output


def build_metrics(
    selected: Sequence[dict[str, Any]],
    retrievals: dict[str, dict[str, Any]],
    answers: dict[str, dict[str, Any]],
    judgments: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metrics = common.build_metrics(selected, retrievals, answers, judgments)
    answer_rows = [
        answers[q["question_id"]]
        for q in selected
        if q["question_id"] in answers
    ]
    judge_rows = [
        judgments[q["question_id"]]
        for q in selected
        if q["question_id"] in judgments
    ]
    metrics["operations"]["answerer"] = aggregate_usage(answer_rows)
    metrics["operations"]["judge"] = aggregate_usage(judge_rows)
    return metrics


def build_report(metrics: dict[str, Any]) -> str:
    overall = metrics["overall"]
    lines = [
        "# LoCoMo Memoria Top-200 对标 Zep 模型实验",
        "",
        f"- Status: **{'COMPLETE' if metrics['complete'] else 'INCOMPLETE'}**",
        f"- Accuracy: **{overall['accuracy']:.2%}** ({overall['correct']}/{overall['total']})",
        "- Reader/Judge: GPT-5.4, reasoning=medium, Responses API",
        "- Reader/Judge Prompt and scoring protocol: pinned public Mem0 LoCoMo prompts",
        "- Retrieval/context: frozen Memoria Raw-Turn Top-200, chronological presentation",
        "- Alignment boundary: Zep published its model setup but not the prompts or detailed scoring rules used for the 94.7% run.",
        "- This is a Zep model-aligned proxy under the Mem0 prompt protocol, not a reproduction of Zep's full pipeline.",
        "- Failed or missing judgments remain in the strict denominator as wrong.",
        "",
        "## By category",
        "",
        "| Category | Correct | Total | Accuracy |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, row in metrics["by_category"].items():
        lines.append(
            f"| {name} | {row['correct']} | {row['total']} | {row['accuracy']:.2%} |"
        )
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
        lines.append(
            f"| {name} | {row['correct']} | {row['total']} | {row['accuracy']:.2%} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[3]
    default_base = (
        project_root
        / "memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root
        / "memoria/datasets/downloads/public-benchmarks/locomo/locomo10.json",
    )
    parser.add_argument(
        "--retrieval-run-dir",
        type=Path,
        default=default_base / "mem0-compatible-retrieval-top200-full1540-v1",
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL"))
    parser.add_argument("--answerer-model", default=DEFAULT_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--rpm", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=180.0)
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

    dataset_sha = common.sha256_file(args.dataset)
    if dataset_sha != common.OFFICIAL_DATASET_SHA256:
        raise ValueError(f"dataset SHA-256 mismatch: {dataset_sha}")
    prompt_hashes = common.validate_prompt_hashes()
    questions, dates_by_conversation, reference_dates = common.load_dataset_questions(
        args.dataset
    )
    selected = common.select_questions(questions, args.limit, args.question_id)

    retrieval_path = args.retrieval_run_dir / "retrieval.jsonl"
    retrieval_manifest_path = args.retrieval_run_dir / "manifest.json"
    retrievals = common.load_retrieval_snapshot(retrieval_path)
    missing = [q["question_id"] for q in selected if q["question_id"] not in retrievals]
    if missing:
        raise ValueError(
            f"retrieval snapshot is missing {len(missing)} selected questions"
        )
    retrieval_manifest = json.loads(
        retrieval_manifest_path.read_text(encoding="utf-8")
    )
    if retrieval_manifest.get("dataset_sha256") != dataset_sha:
        raise ValueError("retrieval manifest dataset SHA-256 mismatch")
    if retrieval_manifest.get("top_k") != common.TOP_K:
        raise ValueError("retrieval manifest is not Top-200")

    frozen_manifest = {
        "protocol": "zep-model-aligned-gpt54-medium-mem0-prompt-locomo-v1",
        "scope_note": "Zep-published GPT-5.4 model setup under the fully public Mem0 Reader/Judge prompt protocol; not a Zep 94.7% pipeline reproduction",
        "zep_research_url": ZEP_RESEARCH_URL,
        "zep_disclosed_reader": "gpt-5.4 reasoning=medium",
        "zep_disclosed_judge": "gpt-5.4 chain-of-thought grading",
        "zep_prompt_disclosure": "not published for the 94.7% run",
        "zep_scoring_rules_disclosure": "not published for the 94.7% run",
        "mem0_baseline_commit": common.MEM0_BASELINE_COMMIT,
        "categories": list(common.CATEGORIES),
        "top_k": common.TOP_K,
        "with_judge_evidence": False,
        "user_profile": False,
        "dataset_path": str(args.dataset.resolve()),
        "dataset_sha256": dataset_sha,
        "retrieval_run_dir": str(args.retrieval_run_dir.resolve()),
        "retrieval_snapshot_sha256": common.sha256_file(retrieval_path),
        "retrieval_manifest_sha256": common.sha256_file(retrieval_manifest_path),
        "embedding_model": retrieval_manifest.get("embedding_model"),
        "embedding_dimension": retrieval_manifest.get("embedding_dimension"),
        "selected_question_ids": [q["question_id"] for q in selected],
        "answerer_model": args.answerer_model,
        "judge_model": args.judge_model,
        "provider": "openai-compatible",
        "openai_compatible_base_url": args.base_url,
        "api_style": "responses",
        "reasoning_effort": REASONING_EFFORT,
        "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "temperature": "omitted",
        "rpm_per_client": args.rpm,
        "workers": args.workers,
        "timeout_seconds": args.timeout,
        "max_retries": args.max_retries,
        "prompt_hashes": prompt_hashes,
        "prompt_module_sha256": common.sha256_file(
            Path(__file__).with_name("mem0_prompts.py")
        ),
        "runner_sha256": common.sha256_file(Path(__file__)),
        "reader_prompt_alignment": "exact pinned public Mem0 ANSWER_GENERATION_PROMPT",
        "judge_prompt_alignment": "exact pinned public Mem0 Judge system and no-evidence user prompts",
        "reader_memory_order": "top200_then_original_session_time_ascending",
        "reference_date": "latest_original_session_date_per_sample",
        "judge_gold_preprocessing": "Mem0 Category 3 semicolon-first-part rule",
    }
    manifest_path = args.run_dir / "manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if {key: old.get(key) for key in frozen_manifest} != frozen_manifest:
            raise ValueError("run manifest does not match requested frozen configuration")
    else:
        common.atomic_json(
            manifest_path, {"created_at": common.utc_now(), **frozen_manifest}
        )

    answers_path = args.run_dir / "answers.jsonl"
    judgments_path = args.run_dir / "judgments.jsonl"
    errors_path = args.run_dir / "errors.jsonl"
    answers = common.successful_records(answers_path)
    judgments = common.successful_records(judgments_path)

    answerer = ResponsesLLM(
        model=args.answerer_model,
        rpm=args.rpm,
        timeout=args.timeout,
        max_retries=args.max_retries,
        base_url=args.base_url,
    )
    judge = ResponsesLLM(
        model=args.judge_model,
        rpm=args.rpm,
        timeout=args.timeout,
        max_retries=args.max_retries,
        base_url=args.base_url,
    )

    write_lock = asyncio.Lock()
    progress_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(args.workers)
    progress = 0

    async def write(path: Path, record: dict[str, Any]) -> None:
        async with write_lock:
            common.append_jsonl(path, record)

    async def process(question: dict[str, Any]) -> None:
        nonlocal progress
        qid = question["question_id"]
        retrieval = retrievals[qid]
        answer_record = answers.get(qid)
        if answer_record is None:
            try:
                reader_prompt, chronological_ids = common.build_reader_input(
                    question,
                    retrieval,
                    dates_by_conversation[question["conversation_idx"]],
                    reference_dates[question["conversation_idx"]],
                )
                async with semaphore:
                    completion = await answerer.generate(
                        system="", user=reader_prompt, structured=False
                    )
                answer_record = {
                    "at": common.utc_now(),
                    "status": "success",
                    **question,
                    "reference_date": reference_dates[question["conversation_idx"]],
                    "memories_evaluated": common.TOP_K,
                    "ranked_memory_ids": [
                        str(row["memory_id"]) for row in retrieval["results"]
                    ],
                    "chronological_memory_ids": chronological_ids,
                    "prompt_sha256": common.sha256_text(reader_prompt),
                    "raw_response": completion.content,
                    "generated_answer": common.extract_answer(completion.content),
                    "provider": "openai-compatible",
                    "requested_model": args.answerer_model,
                    "response_model": completion.response_model,
                    "response_id": completion.response_id,
                    "response_status": completion.status,
                    "reasoning_effort": REASONING_EFFORT,
                    "usage": completion.usage,
                    "latency_ms": completion.latency_ms,
                    "attempts": completion.attempts,
                }
                await write(answers_path, answer_record)
                answers[qid] = answer_record
            except Exception as exc:
                failure = {
                    "at": common.utc_now(),
                    "stage": "answerer",
                    "status": "failed",
                    **question,
                    "error": str(exc),
                }
                await write(answers_path, failure)
                await write(errors_path, failure)
                answer_record = None

        judgment = judgments.get(qid)
        if answer_record is not None and judgment is None:
            try:
                gold = common.preprocess_answer(
                    question["category"], question["answer"]
                )
                judge_prompt = common.get_judge_prompt(
                    question["category"],
                    question["question"],
                    gold,
                    answer_record["generated_answer"],
                )
                async with semaphore:
                    completion = await judge.generate(
                        system=common.JUDGE_SYSTEM_PROMPT,
                        user=judge_prompt,
                        structured=True,
                    )
                parsed, label = common.validate_judgment(completion.content)
                judgment = {
                    "at": common.utc_now(),
                    "status": "success",
                    **question,
                    "processed_gold_answer": gold,
                    "generated_answer": answer_record["generated_answer"],
                    "prompt_sha256": common.sha256_text(judge_prompt),
                    "raw_response": completion.content,
                    "reasoning": str(parsed.get("reasoning", "")),
                    "label": label,
                    "score": 1 if label == "CORRECT" else 0,
                    "provider": "openai-compatible",
                    "requested_model": args.judge_model,
                    "response_model": completion.response_model,
                    "response_id": completion.response_id,
                    "response_status": completion.status,
                    "reasoning_effort": REASONING_EFFORT,
                    "usage": completion.usage,
                    "latency_ms": completion.latency_ms,
                    "attempts": completion.attempts,
                }
                await write(judgments_path, judgment)
                judgments[qid] = judgment
            except Exception as exc:
                failure = {
                    "at": common.utc_now(),
                    "stage": "judge",
                    "status": "failed",
                    **question,
                    "error": str(exc),
                }
                await write(judgments_path, failure)
                await write(errors_path, failure)

        async with progress_lock:
            progress += 1
            state = judgments.get(qid, {}).get("label", "FAILED")
            print(
                f"[{progress}/{len(selected)}] question={qid} "
                f"sample={question['sample_id']} "
                f"answer={'ok' if qid in answers else 'failed'} judge={state}",
                flush=True,
            )

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for question in selected:
        grouped[question["conversation_idx"]].append(question)

    async def process_conversation(rows: Sequence[dict[str, Any]]) -> None:
        for row in rows:
            await process(row)

    await asyncio.gather(
        *(process_conversation(rows) for _, rows in sorted(grouped.items()))
    )

    metrics = build_metrics(selected, retrievals, answers, judgments)
    common.atomic_json(args.run_dir / "metrics.json", metrics)
    (args.run_dir / "report.md").write_text(
        build_report(metrics), encoding="utf-8"
    )
    summary = {
        "finished_at": common.utc_now(),
        "selected_questions": len(selected),
        "successful_answers": metrics["operations"]["successful_answers"],
        "successful_judgments": metrics["operations"]["successful_judgments"],
        "correct": metrics["overall"]["correct"],
        "accuracy": metrics["overall"]["accuracy"],
        "complete": metrics["complete"],
    }
    common.atomic_json(args.run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if metrics["complete"] else 2


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
