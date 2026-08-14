#!/usr/bin/env python3
"""Evaluate frozen Memoria Top-20 retrieval with Mem0's Reader/Judge prompts.

Retrieval is never performed by this program. Reader and Judge are resumable
stages over the immutable 500-question Memoria retrieval snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mem0_prompts import (
    ANSWER_GENERATION_PROMPT,
    JUDGE_PROMPT,
    get_answer_generation_prompt,
    get_judge_prompt,
)
from snapshot_common import CATEGORIES, load_jsonl, validate_and_select


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = PROJECT_ROOT / (
    "memoria/datasets/downloads/public-benchmarks/longmemeval/"
    "longmemeval_oracle.json"
)
DEFAULT_SNAPSHOT = PROJECT_ROOT / (
    "memoria/runs/longmemeval-s-bge-m3-relative-shift-v1/retrieval/"
    "top20-full500-v1/retrieval.jsonl"
)
DEFAULT_RUN_DIR = PROJECT_ROOT / (
    "memoria/runs/longmemeval-s-mem0-protocol-gpt5-top20-full500-v1"
)
MEM0_COMMIT = "4b61c5d31b9c668a12b4f5e78064248a02c82d2b"
MEM0_PROMPT_SOURCE = (
    "https://github.com/mem0ai/memory-benchmarks/blob/"
    f"{MEM0_COMMIT}/benchmarks/longmemeval/prompts.py"
)
EXPECTED_SNAPSHOT_SHA256 = (
    "fe6f179d8cd21cf71a204ebfaf4c62fff7db5ae434a61b69a3c9fdff334a1434"
)
EXPECTED_PROMPT_HASHES = {
    "answer_generation_prompt": (
        "59f155c1c77e3000c6c75494232f669357f77a352d5ac5042decbacea230eebf"
    ),
    "judge_prompt": (
        "c4dc2f6e34e92f9958b62222a0ed520b3ce80dede68bba164dc7961c27dae515"
    ),
}
TOP_K = 20
MAX_COMPLETION_TOKENS = 4096
DEFAULT_EXPERIMENT_NAME = "LongMemEval-S Memoria Top-20 under Mem0 GPT-5 protocol"
DEFAULT_PROTOCOL_NAME = "mem0-longmemeval-reader-judge-v1"


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
    temporary.replace(path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", buffering=1) as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def latest_successful(path: Path, key_field: str = "question_id") -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return latest
    for row in load_jsonl(path):
        key = row.get(key_field)
        if key and row.get("status") == "success":
            latest[str(key)] = row
    return latest


def load_question_ids(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("selected_question_ids")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("question IDs must be a JSON list of strings")
    return value


def parse_longmemeval_date(value: str) -> datetime:
    cleaned = re.sub(r"\s*\([A-Za-z]+\)\s*", " ", value).strip()
    return datetime.strptime(cleaned, "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)


def human_question_date(value: str) -> str:
    return parse_longmemeval_date(value).strftime("%A, %B %d, %Y")


def source_session_date(result: dict[str, Any]) -> str:
    metadata = result.get("extra_metadata") or {}
    source = metadata.get("source_session_date")
    if not source:
        raise ValueError(f"memory {result.get('memory_id')} lacks source_session_date")
    return parse_longmemeval_date(str(source)).isoformat()


def build_reader_prompt(row: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    ranked = row["results"][:TOP_K]
    search_results = [
        {
            "memory": str(result.get("content", "")),
            "score": result.get("retrieval_score"),
            "created_at": source_session_date(result),
            "memory_id": str(result.get("memory_id", "")),
        }
        for result in ranked
    ]
    chronological = sorted(search_results, key=lambda item: item["created_at"])
    prompt = get_answer_generation_prompt(
        question=row["question"],
        search_results=chronological,
        question_date=human_question_date(row["question_date"]),
        user_profile=None,
    )
    return (
        prompt,
        [item["memory_id"] for item in ranked],
        [item["memory_id"] for item in chronological],
    )


def extract_answer(raw: str) -> str:
    cleaned = re.sub(
        r"[<\[]mem_thinking[>\]].*?[<\[]/mem_thinking[>\]]",
        "",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    if "ANSWER:" in cleaned:
        cleaned = cleaned.rsplit("ANSWER:", 1)[-1].strip()
    if not cleaned:
        raise ValueError("Reader response is empty after Mem0 output cleanup")
    return cleaned


def parse_judge(raw: str) -> bool:
    cleaned = re.sub(
        r"[<\[]judge_thinking[>\]].*?[<\[]/judge_thinking[>\]]",
        "",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    labels = re.findall(r"\b(yes|no)\b", cleaned, flags=re.IGNORECASE)
    if not labels:
        raise ValueError(f"Judge response has no final yes/no verdict: {raw!r}")
    return labels[-1].lower() == "yes"


def prompt_hashes() -> dict[str, str]:
    actual = {
        "answer_generation_prompt": sha256_text(ANSWER_GENERATION_PROMPT),
        "judge_prompt": sha256_text(JUDGE_PROMPT),
    }
    if actual != EXPECTED_PROMPT_HASHES:
        raise ValueError(f"vendored Mem0 prompt drift: {actual}")
    return actual


def load_selected(args: argparse.Namespace) -> list[dict[str, Any]]:
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    snapshot = load_jsonl(args.snapshot)
    if len(dataset) != 500 or len(snapshot) != 500:
        raise ValueError(
            f"expected 500 dataset/snapshot rows, got {len(dataset)}/{len(snapshot)}"
        )
    snapshot_hash = sha256_file(args.snapshot)
    if snapshot_hash != EXPECTED_SNAPSHOT_SHA256:
        raise ValueError(f"frozen retrieval SHA-256 mismatch: {snapshot_hash}")
    return validate_and_select(
        dataset,
        snapshot,
        load_question_ids(args.question_ids_file),
        args.limit,
        TOP_K,
    )


def frozen_manifest(args: argparse.Namespace, selected: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = {
        "protocol": args.protocol_name,
        "mem0_baseline_commit": MEM0_COMMIT,
        "mem0_prompt_source": MEM0_PROMPT_SOURCE,
        "prompt_hashes": prompt_hashes(),
        "prompt_module_sha256": sha256_file(Path(__file__).with_name("mem0_prompts.py")),
        "dataset_path": str(args.dataset.resolve()),
        "dataset_sha256": sha256_file(args.dataset),
        "retrieval_snapshot_path": str(args.snapshot.resolve()),
        "retrieval_snapshot_sha256": sha256_file(args.snapshot),
        "retrieval_top_k": TOP_K,
        "retrieval_policy": "ranked_top20_first_then_chronological_ascending_for_reader",
        "memory_date_source": "results[].extra_metadata.source_session_date",
        "question_date_source": "frozen retrieval snapshot question_date",
        "user_profile": False,
        "selected_question_ids": [row["question_id"] for row in selected],
        "answerer_model": args.answerer_model,
        "judge_model": args.judge_model,
        "provider": f"openai_compatible_{args.api_style}",
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "system_prompt": "omitted",
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "temperature": "provider_default_parameter_omitted",
        "failure_policy": "missing Reader/Judge verdicts remain incorrect in the 500-question denominator",
    }
    # Preserve resumability of runs created before the configurable experiment
    # metadata and Responses API support were added.
    if args.protocol_name != DEFAULT_PROTOCOL_NAME:
        manifest["experiment_name"] = args.experiment_name
        manifest["scope_note"] = args.scope_note
    if args.api_style == "responses":
        manifest["api_style"] = args.api_style
        manifest["reasoning_effort"] = args.reasoning_effort
    return manifest


def prepare(args: argparse.Namespace, selected: list[dict[str, Any]]) -> dict[str, Any]:
    args.run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.run_dir / "manifest.json"
    frozen = frozen_manifest(args, selected)
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if {key: existing.get(key) for key in frozen} != frozen:
            raise ValueError("run directory manifest differs; use a new run directory")
        manifest = existing
    else:
        manifest = {"created_at": utc_now(), **frozen}
        atomic_json(manifest_path, manifest)
        sample: list[dict[str, Any]] = []
        prompt_rows: list[dict[str, Any]] = []
        for row in selected:
            prompt, ranked_ids, chronological_ids = build_reader_prompt(row)
            sample.append(
                {
                    "question_id": row["question_id"],
                    "question_type": row["question_type"],
                    "is_abstention": row["question_id"].endswith("_abs"),
                    "ranked_memory_ids": ranked_ids,
                    "chronological_memory_ids": chronological_ids,
                }
            )
            prompt_rows.append(
                {
                    "question_id": row["question_id"],
                    "prompt": prompt,
                    "prompt_sha256": sha256_text(prompt),
                }
            )
        atomic_json(args.run_dir / "sample.json", sample)
        for record in prompt_rows:
            append_jsonl(args.run_dir / "reader_prompts.jsonl", record)
        (args.run_dir / "errors.jsonl").touch()
    validate_prepared(args, selected)
    write_checkpoint(args, selected)
    print(
        f"Prepared {len(selected)} questions; frozen retrieval={EXPECTED_SNAPSHOT_SHA256}; Top-{TOP_K}",
        flush=True,
    )
    return manifest


def validate_prepared(args: argparse.Namespace, selected: list[dict[str, Any]]) -> None:
    samples = json.loads((args.run_dir / "sample.json").read_text(encoding="utf-8"))
    prompts = load_jsonl(args.run_dir / "reader_prompts.jsonl")
    expected = [row["question_id"] for row in selected]
    if [row["question_id"] for row in samples] != expected:
        raise ValueError("sample IDs/order differ from selection")
    if [row["question_id"] for row in prompts] != expected:
        raise ValueError("Reader prompt IDs/order differ from selection")
    for row, sample, saved in zip(selected, samples, prompts):
        prompt, ranked_ids, chronological_ids = build_reader_prompt(row)
        if saved["prompt"] != prompt or saved["prompt_sha256"] != sha256_text(prompt):
            raise ValueError(f"Reader prompt drift: {row['question_id']}")
        if sample["ranked_memory_ids"] != ranked_ids:
            raise ValueError(f"ranked Top-20 drift: {row['question_id']}")
        if sample["chronological_memory_ids"] != chronological_ids:
            raise ValueError(f"chronological Top-20 drift: {row['question_id']}")


def get_client(args: argparse.Namespace) -> OpenAI:
    key = os.getenv(args.api_key_env)
    if not key:
        raise RuntimeError(f"environment variable {args.api_key_env} is not set")
    return OpenAI(api_key=key, base_url=args.base_url, timeout=args.timeout)


def call_model(
    client: OpenAI,
    model: str,
    prompt: str,
    max_retries: int,
    api_style: str,
    reasoning_effort: str,
) -> tuple[Any, str, float, int]:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        started = time.perf_counter()
        try:
            if api_style == "responses":
                response = client.responses.create(
                    model=model,
                    input=prompt,
                    reasoning={"effort": reasoning_effort},
                    max_output_tokens=MAX_COMPLETION_TOKENS,
                )
                content = response.output_text
                if not content:
                    raise ValueError(
                        f"empty response; status={getattr(response, 'status', None)}"
                    )
            else:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=MAX_COMPLETION_TOKENS,
                    stream=False,
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError(
                        "empty response; "
                        f"finish_reason={response.choices[0].finish_reason}"
                    )
            return response, content.strip(), (time.perf_counter() - started) * 1000, attempt
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"LLM failed after {max_retries} attempts: {last_error}")


def usage(response: Any) -> dict[str, int | None]:
    value = getattr(response, "usage", None)
    if hasattr(value, "input_tokens"):
        output_details = getattr(value, "output_tokens_details", None)
        return {
            "prompt_tokens": getattr(value, "input_tokens", None),
            "completion_tokens": getattr(value, "output_tokens", None),
            "reasoning_tokens": getattr(output_details, "reasoning_tokens", None),
            "total_tokens": getattr(value, "total_tokens", None),
        }
    return {
        "prompt_tokens": getattr(value, "prompt_tokens", None),
        "completion_tokens": getattr(value, "completion_tokens", None),
        "reasoning_tokens": None,
        "total_tokens": getattr(value, "total_tokens", None),
    }


def response_metadata(response: Any) -> dict[str, Any]:
    choices = getattr(response, "choices", None)
    return {
        "response_id": getattr(response, "id", None),
        "response_model": getattr(response, "model", None),
        "finish_reason": (
            getattr(choices[0], "finish_reason", None) if choices else None
        ),
        "response_status": getattr(response, "status", None),
        "usage": usage(response),
    }


def run_readers(args: argparse.Namespace, selected: list[dict[str, Any]], client: OpenAI) -> None:
    path = args.run_dir / "answers.jsonl"
    done = latest_successful(path)
    for index, row in enumerate(selected, 1):
        qid = row["question_id"]
        if qid in done:
            continue
        prompt, ranked_ids, chronological_ids = build_reader_prompt(row)
        print(f"[Reader {index}/{len(selected)}] {qid}", flush=True)
        try:
            response, raw, latency_ms, attempts = call_model(
                client,
                args.answerer_model,
                prompt,
                args.max_retries,
                args.api_style,
                args.reasoning_effort,
            )
            record = {
                "at": utc_now(),
                "status": "success",
                "question_id": qid,
                "question_type": row["question_type"],
                "is_abstention": qid.endswith("_abs"),
                "requested_model": args.answerer_model,
                "memories_evaluated": TOP_K,
                "ranked_memory_ids": ranked_ids,
                "chronological_memory_ids": chronological_ids,
                "prompt_sha256": sha256_text(prompt),
                "raw_response": raw,
                "generated_answer": extract_answer(raw),
                "latency_ms": round(latency_ms, 3),
                "attempts": attempts,
                **response_metadata(response),
            }
            append_jsonl(path, record)
            done[qid] = record
        except Exception as exc:
            error = {
                "at": utc_now(),
                "stage": "reader",
                "status": "failed",
                "question_id": qid,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            append_jsonl(path, error)
            append_jsonl(args.run_dir / "errors.jsonl", error)
            print(f"Reader failed {qid}: {exc}", file=sys.stderr, flush=True)
        write_checkpoint(args, selected)


def run_judge(args: argparse.Namespace, selected: list[dict[str, Any]], client: OpenAI) -> None:
    answers = latest_successful(args.run_dir / "answers.jsonl")
    path = args.run_dir / "judgments.jsonl"
    done = latest_successful(path)
    for index, row in enumerate(selected, 1):
        qid = row["question_id"]
        if qid in done or qid not in answers:
            continue
        prompt = get_judge_prompt(
            question_type=row["question_type"],
            question_id=qid,
            question=row["question"],
            answer=str(row["answer"]),
            response=answers[qid]["generated_answer"],
            question_date=human_question_date(row["question_date"]),
        )
        print(f"[Judge {index}/{len(selected)}] {qid}", flush=True)
        try:
            response, raw, latency_ms, attempts = call_model(
                client,
                args.judge_model,
                prompt,
                args.max_retries,
                args.api_style,
                args.reasoning_effort,
            )
            correct = parse_judge(raw)
            record = {
                "at": utc_now(),
                "status": "success",
                "question_id": qid,
                "question_type": row["question_type"],
                "is_abstention": qid.endswith("_abs"),
                "requested_model": args.judge_model,
                "generated_answer": answers[qid]["generated_answer"],
                "prompt_sha256": sha256_text(prompt),
                "raw_response": raw,
                "label": correct,
                "score": 1 if correct else 0,
                "latency_ms": round(latency_ms, 3),
                "attempts": attempts,
                **response_metadata(response),
            }
            append_jsonl(path, record)
            done[qid] = record
        except Exception as exc:
            error = {
                "at": utc_now(),
                "stage": "judge",
                "status": "failed",
                "question_id": qid,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            append_jsonl(path, error)
            append_jsonl(args.run_dir / "errors.jsonl", error)
            print(f"Judge failed {qid}: {exc}", file=sys.stderr, flush=True)
        write_checkpoint(args, selected)


def summarize(correct_values: Iterable[bool]) -> dict[str, Any]:
    values = list(correct_values)
    correct = sum(values)
    return {
        "correct": correct,
        "total": len(values),
        "accuracy": round(correct / len(values), 6) if values else None,
    }


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def operation_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"calls": len(records)}
    for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens"):
        values = [row.get("usage", {}).get(key) for row in records]
        result[key] = sum(value for value in values if isinstance(value, int))
    latencies = [float(row["latency_ms"]) for row in records if row.get("latency_ms") is not None]
    result["latency_ms"] = {
        "p50": round(float(median(latencies)), 3) if latencies else None,
        "p95": round(float(percentile(latencies, 0.95)), 3) if latencies else None,
    }
    return result


def build_metrics(args: argparse.Namespace, selected: list[dict[str, Any]]) -> dict[str, Any]:
    answers = latest_successful(args.run_dir / "answers.jsonl")
    judgments = latest_successful(args.run_dir / "judgments.jsonl")
    by_type: dict[str, list[bool]] = defaultdict(list)
    abstention: list[bool] = []
    non_abstention: list[bool] = []
    all_scores: list[bool] = []
    for row in selected:
        qid = row["question_id"]
        correct = bool(judgments.get(qid, {}).get("label", False))
        all_scores.append(correct)
        if qid.endswith("_abs"):
            abstention.append(correct)
        else:
            non_abstention.append(correct)
            by_type[row["question_type"]].append(correct)
    answer_rows = [answers[q["question_id"]] for q in selected if q["question_id"] in answers]
    judge_rows = [judgments[q["question_id"]] for q in selected if q["question_id"] in judgments]
    return {
        "generated_at": utc_now(),
        "complete": len(answer_rows) == len(selected) and len(judge_rows) == len(selected),
        "overall": summarize(all_scores),
        "non_abstention": summarize(non_abstention),
        "abstention": summarize(abstention),
        "by_question_type": {category: summarize(by_type[category]) for category in CATEGORIES},
        "operations": {
            "selected_questions": len(selected),
            "successful_answers": len(answer_rows),
            "successful_judgments": len(judge_rows),
            "missing_or_failed_answers": len(selected) - len(answer_rows),
            "missing_or_failed_judgments": len(selected) - len(judge_rows),
            "reader": operation_metrics(answer_rows),
            "judge": operation_metrics(judge_rows),
        },
    }


def write_checkpoint(args: argparse.Namespace, selected: list[dict[str, Any]]) -> None:
    answers = latest_successful(args.run_dir / "answers.jsonl")
    judgments = latest_successful(args.run_dir / "judgments.jsonl")
    atomic_json(
        args.run_dir / "checkpoint.json",
        {
            "updated_at": utc_now(),
            "expected": len(selected),
            "reader_success": len(answers),
            "judge_success": len(judgments),
            "reader_missing_question_ids": [
                row["question_id"] for row in selected if row["question_id"] not in answers
            ],
            "judge_missing_question_ids": [
                row["question_id"] for row in selected if row["question_id"] not in judgments
            ],
        },
    )


def write_report(args: argparse.Namespace, selected: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = build_metrics(args, selected)
    atomic_json(args.run_dir / "metrics.json", metrics)
    overall = metrics["overall"]
    ops = metrics["operations"]
    lines = [
        f"# {args.experiment_name}",
        "",
        f"- Status: **{'COMPLETE' if metrics['complete'] else 'INCOMPLETE'}**",
        f"- Accuracy: **{overall['accuracy']:.2%}** ({overall['correct']}/{overall['total']})",
        f"- Reader / Judge: `{args.answerer_model}` / `{args.judge_model}`",
        f"- API / reasoning: `{args.api_style}` / `{args.reasoning_effort if args.api_style == 'responses' else 'N/A'}`",
        "- Reader/Judge prompts: pinned Mem0 LongMemEval prompts",
        f"- Mem0 protocol commit: `{MEM0_COMMIT}`",
        f"- Frozen retrieval SHA256: `{EXPECTED_SNAPSHOT_SHA256}`",
        "- Missing Reader/Judge results remain incorrect in the full denominator.",
        "",
        "| Category | Correct | Total | Accuracy |",
        "| --- | ---: | ---: | ---: |",
    ]
    for category in CATEGORIES:
        row = metrics["by_question_type"][category]
        accuracy = f"{row['accuracy']:.2%}" if row["accuracy"] is not None else "N/A"
        lines.append(f"| {category} | {row['correct']} | {row['total']} | {accuracy} |")
    for label, key in (("Abstention", "abstention"), ("Non-abstention", "non_abstention")):
        row = metrics[key]
        lines.append(f"| {label} | {row['correct']} | {row['total']} | {row['accuracy']:.2%} |")
    lines.extend(
        [
            "",
            "## Operations",
            "",
            f"- Reader: {ops['successful_answers']}/{ops['selected_questions']}",
            f"- Judge: {ops['successful_judgments']}/{ops['selected_questions']}",
            f"- Reader usage: `{json.dumps(ops['reader'], ensure_ascii=False)}`",
            f"- Judge usage: `{json.dumps(ops['judge'], ensure_ascii=False)}`",
            "",
        ]
    )
    (args.run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    write_checkpoint(args, selected)
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "readers", "judge", "report", "all"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--question-ids-file", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--answerer-model", default="gpt-5")
    parser.add_argument("--judge-model", default="gpt-5")
    parser.add_argument(
        "--api-style", choices=("chat_completions", "responses"), default="chat_completions"
    )
    parser.add_argument(
        "--reasoning-effort", choices=("low", "medium", "high"), default="medium"
    )
    parser.add_argument("--experiment-name", default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--protocol-name", default=DEFAULT_PROTOCOL_NAME)
    parser.add_argument("--scope-note", default="")
    parser.add_argument("--base-url", default="https://aihubmix.com/v1")
    parser.add_argument("--api-key-env", default="AIHUBMIX_API_KEY")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-retries", type=int, default=5)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        raise ValueError("limit must be positive")
    if args.limit is not None and args.question_ids_file:
        raise ValueError("--limit and --question-ids-file cannot be combined")
    return args


def main() -> int:
    args = parse_args()
    args.dataset = args.dataset.resolve()
    args.snapshot = args.snapshot.resolve()
    args.run_dir = args.run_dir.resolve()
    if args.question_ids_file:
        args.question_ids_file = args.question_ids_file.resolve()
    selected = load_selected(args)
    prepare(args, selected)
    if args.command == "prepare":
        return 0
    if args.command in {"readers", "all"}:
        run_readers(args, selected, get_client(args))
    if args.command in {"judge", "all"}:
        run_judge(args, selected, get_client(args))
    if args.command in {"report", "all"}:
        metrics = write_report(args, selected)
        return 0 if metrics["complete"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
