#!/usr/bin/env python3
"""Re-score frozen WikiEval QA traces with one shared RAGAS configuration.

This script deliberately does not call any RAG platform.  It loads the
already-recorded QA traces for MOI, Dify, FastGPT, and MaxKB, validates that
they use the same 50-question frozen benchmark, maps them to the RAGAS
0.2.15 schema, and evaluates the four standard RAGAS metrics with one shared
LLM and embedding endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
import sys
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = (
    REPO_ROOT
    / "runs/stage1/ragas-wikieval-moi/20260807-160000-wikieval/artifacts/questions.jsonl"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "runs/stage1/ragas-wikieval-calibrated/20260812-ragas-0215-maas-unified"
)

SYSTEMS: "OrderedDict[str, dict[str, str]]" = OrderedDict(
    [
        (
            "moi",
            {
                "raw_path": "runs/stage1/ragas-wikieval-moi/20260807-160000-wikieval/moi-run/20260807-161313.375/results.jsonl",
                "contexts_key": "chunks",
                "context_content_key": "content",
            },
        ),
        (
            "dify",
            {
                "raw_path": "runs/stage1/ragas-wikieval-moi/20260807-160000-wikieval/dify-run/results.jsonl",
                "contexts_key": "contexts",
                "context_content_key": "content",
            },
        ),
        (
            "fastgpt",
            {
                "raw_path": "runs/stage1/wikieval-competitors/20260810-fastgpt-wikieval-round1-english/fastgpt_local/results.jsonl",
                "contexts_key": "chunks",
                "context_content_key": "content",
            },
        ),
        (
            "maxkb",
            {
                "raw_path": "runs/stage1/wikieval-competitors/20260810-maxkb-wikieval-round1-stable/maxkb_local/results.jsonl",
                "contexts_key": "chunks",
                "context_content_key": "content",
            },
        ),
    ]
)

METRIC_NAMES = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected an object at {path}:{line_number}")
            rows.append(value)
    return rows


def json_dump(path: Path, value: Any) -> None:
    temporary_path = path.with_name(path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def jsonl_dump(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary_path = path.with_name(path.name + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, allow_nan=False, sort_keys=True)
                + "\n"
            )
    os.replace(temporary_path, path)


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def load_benchmark(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = load_jsonl(path)
    if not rows:
        raise ValueError(f"Benchmark is empty: {path}")
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = require_string(row.get("id"), f"benchmark id in {path}")
        if row_id in by_id:
            raise ValueError(f"Duplicate benchmark id: {row_id}")
        require_string(row.get("question"), f"benchmark question {row_id}")
        by_id[row_id] = row
    return rows, by_id


def extract_reference(case: dict[str, Any], row_id: str) -> str:
    evidence = case.get("relevant_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"{row_id}: missing case.relevant_evidence[0]")
    return require_string(evidence[0], f"reference {row_id}")


def normalize_rows(
    system: str,
    spec: dict[str, str],
    raw_path: Path,
    benchmark_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_rows = load_jsonl(raw_path)
    by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_rows:
        case = raw.get("case")
        if not isinstance(case, dict):
            raise ValueError(f"{system}: raw row has no object case")
        row_id = require_string(case.get("id"), f"{system} case.id")
        if row_id in by_id:
            raise ValueError(f"{system}: duplicate case.id {row_id}")
        if row_id not in benchmark_by_id:
            raise ValueError(f"{system}: case.id not in frozen benchmark: {row_id}")

        question = require_string(case.get("question"), f"{system} question {row_id}")
        benchmark_question = require_string(
            benchmark_by_id[row_id].get("question"), f"benchmark question {row_id}"
        )
        if question != benchmark_question:
            raise ValueError(f"{system}: question mismatch for {row_id}")

        reference = extract_reference(case, row_id)
        answer = require_string(raw.get("answer"), f"{system} answer {row_id}")
        contexts = raw.get(spec["contexts_key"])
        if not isinstance(contexts, list) or not contexts:
            raise ValueError(f"{system}: empty {spec['contexts_key']} for {row_id}")
        context_texts: list[str] = []
        for index, context in enumerate(contexts):
            if not isinstance(context, dict):
                raise ValueError(f"{system}: context {row_id}[{index}] is not an object")
            context_texts.append(
                require_string(
                    context.get(spec["context_content_key"]),
                    f"{system} context {row_id}[{index}]",
                )
            )

        by_id[row_id] = {
            "id": row_id,
            "user_input": question,
            "response": answer,
            "retrieved_contexts": context_texts,
            "reference": reference,
            "qa_status": raw.get("status"),
            "context_count": len(context_texts),
        }

    expected_ids = list(benchmark_by_id)
    actual_ids = set(by_id)
    if actual_ids != set(expected_ids):
        missing = sorted(set(expected_ids) - actual_ids)
        extra = sorted(actual_ids - set(expected_ids))
        raise ValueError(f"{system}: benchmark id mismatch; missing={missing}, extra={extra}")

    ordered = [by_id[row_id] for row_id in expected_ids]
    input_hash = canonical_sha256(
        [
            {
                "id": row["id"],
                "user_input": row["user_input"],
                "response": row["response"],
                "retrieved_contexts": row["retrieved_contexts"],
                "reference": row["reference"],
            }
            for row in ordered
        ]
    )
    return ordered, {
        "rows": len(ordered),
        "input_sha256": input_hash,
        "context_counts": {
            "min": min(row["context_count"] for row in ordered),
            "median": median(row["context_count"] for row in ordered),
            "max": max(row["context_count"] for row in ordered),
        },
    }


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def summarize_scores(rows: list[dict[str, Any]], metric_names: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {"rows": len(rows), "metrics": {}}
    for metric_name in metric_names:
        values = [finite_float(row.get(metric_name)) for row in rows]
        valid = [value for value in values if value is not None]
        invalid_ids = [
            row["id"] for row, value in zip(rows, values, strict=True) if value is None
        ]
        summary["metrics"][metric_name] = {
            "scored_rows": len(valid),
            "mean": (sum(valid) / len(valid)) if valid else None,
            "p50": median(valid) if valid else None,
            "min": min(valid) if valid else None,
            "max": max(valid) if valid else None,
            "invalid_ids": invalid_ids,
        }
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--llm-model",
        default=os.environ.get("CALIBRATED_LLM_MODEL", "qwen3-32b"),
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("CALIBRATED_EMBEDDING_MODEL", "bge-m3"),
    )
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2"),
    )
    parser.add_argument(
        "--embedding-base-url",
        default=os.environ.get("MAAS_BASE_URL", "https://api.modelarts-maas.com/v1"),
    )
    parser.add_argument("--llm-api-key-env", default="QIANFAN_API_KEY")
    parser.add_argument("--embedding-api-key-env", default="MAAS_API_KEY")
    parser.add_argument("--llm-provider", default="Baidu Qianfan")
    parser.add_argument("--embedding-provider", default="Huawei MaaS")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument(
        "--context-max-tokens",
        type=int,
        default=1024,
        help="short response budget for context_precision verdicts",
    )
    parser.add_argument(
        "--context-k",
        type=int,
        default=10,
        help="number of top-ranked native contexts used for context_precision",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="ignore existing per-system checkpoints and start each system over",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="remove previously failed metric rows from checkpoints so they are retried",
    )
    parser.add_argument(
        "--reset-context-precision",
        action="store_true",
        help="discard context_precision scores and recompute them with --context-k",
    )
    parser.add_argument(
        "--systems",
        nargs="+",
        choices=list(SYSTEMS),
        default=list(SYSTEMS),
        help="systems to score in this invocation",
    )
    return parser


def _initial_score_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "status": "pending",
            "qa_status": row["qa_status"],
            "context_count": row["context_count"],
        }
        for row in rows
    ]


def _validate_score_rows(
    score_rows: list[dict[str, Any]], rows: list[dict[str, Any]], system: str
) -> None:
    expected_ids = [row["id"] for row in rows]
    actual_ids = [row.get("id") for row in score_rows]
    if actual_ids != expected_ids:
        raise ValueError(
            f"{system}: checkpoint score ids do not match frozen benchmark order"
        )


def _load_system_checkpoint(
    system_output_dir: Path,
    rows: list[dict[str, Any]],
    input_sha256: str,
    *,
    reset: bool,
    retry_errors: bool,
    reset_context_precision: bool,
    context_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, set[str]]]:
    checkpoint_path = system_output_dir / "checkpoint.json"
    score_path = system_output_dir / "scores.jsonl"
    score_rows = _initial_score_rows(rows)
    completed_ids: dict[str, set[str]] = {metric: set() for metric in METRIC_NAMES}
    checkpoint: dict[str, Any] = {
        "input_sha256": input_sha256,
        "metric_names": METRIC_NAMES,
        "completed_metrics": [],
        "metric_row_ids": {metric: [] for metric in METRIC_NAMES},
        "last_metric": None,
        "last_row_id": None,
        "context_precision_context_k": context_k,
    }

    def reset_context_precision_state() -> None:
        if not reset_context_precision:
            return
        for row in score_rows:
            row.pop("context_precision", None)
            errors = row.get("errors")
            if isinstance(errors, dict):
                errors.pop("context_precision", None)
                if not errors:
                    row.pop("errors", None)
        completed_ids["context_precision"].clear()
        checkpoint["metric_row_ids"]["context_precision"] = []
        checkpoint["context_precision_context_k"] = context_k

    if reset:
        reset_context_precision_state()
        return score_rows, checkpoint, completed_ids

    def retry_failed_rows() -> None:
        if not retry_errors:
            return
        for row in score_rows:
            errors = row.get("errors", {})
            if not isinstance(errors, dict):
                continue
            for metric in list(errors):
                if metric in METRIC_NAMES:
                    row.pop(metric, None)
                    completed_ids[metric].discard(row["id"])
                    errors.pop(metric, None)
            if not errors:
                row.pop("errors", None)

    if checkpoint_path.exists():
        stored_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if stored_checkpoint.get("input_sha256") != input_sha256:
            raise ValueError(
                f"{system_output_dir.name}: checkpoint input hash does not match raw QA"
            )
        if stored_checkpoint.get("metric_names") != METRIC_NAMES:
            raise ValueError(
                f"{system_output_dir.name}: checkpoint metric set does not match"
            )
        stored_context_k = stored_checkpoint.get("context_precision_context_k")
        if (
            not reset_context_precision
            and stored_context_k != context_k
            and stored_checkpoint.get("metric_row_ids", {}).get("context_precision")
        ):
            raise ValueError(
                f"{system_output_dir.name}: context_precision checkpoint uses "
                f"context_k={stored_context_k}; rerun with --reset-context-precision "
                f"for context_k={context_k}"
            )
        checkpoint = stored_checkpoint
        if score_path.exists():
            score_rows = load_jsonl(score_path)
            _validate_score_rows(score_rows, rows, system_output_dir.name)
        else:
            raise ValueError(
                f"{system_output_dir.name}: checkpoint exists but scores.jsonl is missing"
            )
        for metric in METRIC_NAMES:
            completed_ids[metric] = set(
                checkpoint.get("metric_row_ids", {}).get(metric, [])
            )
        retry_failed_rows()
        reset_context_precision_state()
        return score_rows, checkpoint, completed_ids

    # A score file without a checkpoint is accepted only when it is complete
    # for a metric. This makes the handoff conservative after an older run.
    if score_path.exists():
        score_rows = load_jsonl(score_path)
        _validate_score_rows(score_rows, rows, system_output_dir.name)
        for metric in METRIC_NAMES:
            if all(metric in row for row in score_rows):
                completed_ids[metric] = {row["id"] for row in score_rows}
        checkpoint["completed_metrics"] = [
            metric for metric in METRIC_NAMES if len(completed_ids[metric]) == len(rows)
        ]
        for metric in METRIC_NAMES:
            checkpoint["metric_row_ids"][metric] = [
                row["id"] for row in score_rows if row["id"] in completed_ids[metric]
            ]
        retry_failed_rows()
        reset_context_precision_state()
    return score_rows, checkpoint, completed_ids


def _update_score_statuses(
    score_rows: list[dict[str, Any]], metric_names: list[str]
) -> None:
    for row in score_rows:
        present = [metric for metric in metric_names if metric in row]
        invalid = any(finite_float(row.get(metric)) is None for metric in present)
        if len(present) == len(metric_names) and not invalid:
            row["status"] = "ok"
        elif present:
            row["status"] = "partial"
        else:
            row["status"] = "pending"


def _save_system_checkpoint(
    system_output_dir: Path,
    score_rows: list[dict[str, Any]],
    checkpoint: dict[str, Any],
    completed_ids: dict[str, set[str]],
    rows: list[dict[str, Any]],
) -> None:
    _update_score_statuses(score_rows, METRIC_NAMES)
    for metric in METRIC_NAMES:
        checkpoint["metric_row_ids"][metric] = [
            row["id"] for row in rows if row["id"] in completed_ids[metric]
        ]
    checkpoint["completed_metrics"] = [
        metric
        for metric in METRIC_NAMES
        if len(completed_ids[metric]) == len(rows)
    ]
    jsonl_dump(system_output_dir / "scores.jsonl", score_rows)
    summary = summarize_scores(score_rows, METRIC_NAMES)
    summary["completed_metrics"] = checkpoint["completed_metrics"]
    summary["checkpoint"] = {
        "last_metric": checkpoint.get("last_metric"),
        "last_row_id": checkpoint.get("last_row_id"),
    }
    json_dump(system_output_dir / "summary.json", summary)
    json_dump(system_output_dir / "checkpoint.json", checkpoint)


async def _score_pending_rows(
    metric: Any,
    samples: list[Any],
    pending_indices: list[int],
    *,
    metric_name: str,
    timeout: int,
    max_workers: int,
    on_result: Any,
) -> None:
    semaphore = asyncio.Semaphore(max_workers)

    async def score_one(index: int) -> tuple[int, float | None, str | None]:
        async with semaphore:
            try:
                value = await asyncio.wait_for(
                    metric.single_turn_ascore(samples[index], callbacks=[]),
                    timeout=timeout,
                )
                return index, finite_float(value), None
            except Exception as exc:  # RAGAS uses NaN for failed rows in this mode.
                return index, None, f"{type(exc).__name__}: {str(exc)[:300]}"

    tasks = [asyncio.create_task(score_one(index)) for index in pending_indices]
    try:
        for task in asyncio.as_completed(tasks):
            index, value, error = await task
            await on_result(index, value, error)
    finally:
        unfinished = [task for task in tasks if not task.done()]
        for task in unfinished:
            task.cancel()
        if unfinished:
            await asyncio.gather(*unfinished, return_exceptions=True)


def evaluate_system(
    rows: list[dict[str, Any]],
    system_output_dir: Path,
    *,
    input_sha256: str,
    llm_model: str,
    embedding_model: str,
    llm_base_url: str,
    llm_api_key: str,
    embedding_base_url: str,
    embedding_api_key: str,
    temperature: float,
    max_tokens: int,
    context_max_tokens: int,
    timeout: int,
    max_workers: int,
    reset: bool,
    retry_errors: bool,
    reset_context_precision: bool,
    context_k: int,
) -> dict[str, Any]:
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas.dataset_schema import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        ContextPrecision,
        answer_relevancy,
        context_recall,
        faithfulness,
    )
    from ragas.metrics._context_precision import QAC, Verification
    from ragas.metrics.base import ensembler
    from ragas.run_config import RunConfig

    run_config = RunConfig(timeout=timeout, max_retries=2, max_workers=max_workers)
    chat_model = ChatOpenAI(
        model=llm_model,
        api_key=llm_api_key,
        base_url=llm_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=2,
    )
    embedding_model_client = OpenAIEmbeddings(
        model=embedding_model,
        api_key=embedding_api_key,
        base_url=embedding_base_url,
        request_timeout=timeout,
        max_retries=2,
        chunk_size=16,
    )
    llm = LangchainLLMWrapper(chat_model, run_config=run_config)
    context_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=llm_model,
            api_key=llm_api_key,
            base_url=llm_base_url,
            temperature=temperature,
            max_tokens=context_max_tokens,
            timeout=timeout,
            max_retries=2,
        ),
        run_config=run_config,
    )
    embeddings = LangchainEmbeddingsWrapper(
        embedding_model_client, run_config=run_config
    )

    class ParallelContextPrecision(ContextPrecision):
        """Run the stock RAGAS context verdicts concurrently per row.

        The prompt, verdict aggregation, and average-precision formula are
        unchanged from RAGAS 0.2.15; only the independent context calls are
        scheduled concurrently so large raw context lists do not serialize
        the whole calibration run.
        """

        def __init__(self, *, context_max_workers: int):
            super().__init__()
            self.context_max_workers = context_max_workers

        async def _ascore(self, row: dict[str, Any], callbacks: Any) -> float:
            assert self.llm is not None, "LLM is not set"
            user_input, retrieved_contexts, reference = self._get_row_attributes(row)
            semaphore = asyncio.Semaphore(self.context_max_workers)

            async def score_context(context: str) -> list[dict[str, Any]]:
                async with semaphore:
                    verdicts = await self.context_precision_prompt.generate_multiple(
                        data=QAC(
                            question=user_input,
                            context=context,
                            answer=reference,
                        ),
                        llm=self.llm,
                        callbacks=callbacks,
                    )
                    return [result.model_dump() for result in verdicts]

            responses = await asyncio.gather(
                *(score_context(context) for context in retrieved_contexts)
            )
            answers = [
                Verification(**ensembler.from_discrete([response], "verdict")[0])
                for response in responses
            ]
            return self._calculate_average_precision(answers)

    metric_templates = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": ParallelContextPrecision(
            context_max_workers=max_workers
        ),
        "context_recall": context_recall,
    }
    samples = [
        SingleTurnSample(
            user_input=row["user_input"],
            response=row["response"],
            retrieved_contexts=row["retrieved_contexts"],
            reference=row["reference"],
        )
        for row in rows
    ]
    context_precision_samples = [
        SingleTurnSample(
            user_input=row["user_input"],
            response=row["response"],
            retrieved_contexts=row["retrieved_contexts"][:context_k],
            reference=row["reference"],
        )
        for row in rows
    ]

    score_rows, checkpoint, completed_ids = _load_system_checkpoint(
        system_output_dir,
        rows,
        input_sha256,
        reset=reset,
        retry_errors=retry_errors,
        reset_context_precision=reset_context_precision,
        context_k=context_k,
    )
    _save_system_checkpoint(
        system_output_dir, score_rows, checkpoint, completed_ids, rows
    )
    for metric_name in METRIC_NAMES:
        if len(completed_ids[metric_name]) == len(rows):
            print(
                f"resuming {system_output_dir.name}/{metric_name}: already complete",
                flush=True,
            )
            continue

        metric = deepcopy(metric_templates[metric_name])
        metric.llm = context_llm if metric_name == "context_precision" else llm
        metric.embeddings = embeddings
        metric.init(run_config)
        pending_indices = [
            index
            for index, row in enumerate(rows)
            if row["id"] not in completed_ids[metric_name]
        ]
        print(
            f"scoring {system_output_dir.name}/{metric_name}: "
            f"pending_rows={len(pending_indices)} workers={max_workers}",
            flush=True,
        )

        async def on_result(
            index: int, value: float | None, error: str | None
        ) -> None:
            row_id = rows[index]["id"]
            score_rows[index][metric_name] = value
            if error:
                errors = score_rows[index].setdefault("errors", {})
                errors[metric_name] = error
            completed_ids[metric_name].add(row_id)
            checkpoint["last_metric"] = metric_name
            checkpoint["last_row_id"] = row_id
            _save_system_checkpoint(
                system_output_dir, score_rows, checkpoint, completed_ids, rows
            )
            print(
                f"checkpoint {system_output_dir.name}/{metric_name} "
                f"{len(completed_ids[metric_name])}/{len(rows)}",
                flush=True,
            )

        asyncio.run(
            _score_pending_rows(
                metric,
                context_precision_samples
                if metric_name == "context_precision"
                else samples,
                pending_indices,
                metric_name=metric_name,
                timeout=timeout,
                max_workers=max_workers,
                on_result=on_result,
            )
        )
        if len(completed_ids[metric_name]) != len(rows):
            raise RuntimeError(
                f"{system_output_dir.name}/{metric_name} stopped before all rows completed"
            )

    _save_system_checkpoint(system_output_dir, score_rows, checkpoint, completed_ids, rows)
    return {
        "metric_names": METRIC_NAMES,
        "summary": summarize_scores(score_rows, METRIC_NAMES),
    }


def main() -> int:
    args = build_parser().parse_args()
    benchmark_path = args.benchmark.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    llm_api_key = os.environ.get(args.llm_api_key_env)
    embedding_api_key = os.environ.get(args.embedding_api_key_env)
    if not llm_api_key:
        raise SystemExit(f"{args.llm_api_key_env} is required")
    if not embedding_api_key:
        raise SystemExit(f"{args.embedding_api_key_env} is required")
    if args.context_k < 1:
        raise SystemExit("--context-k must be at least 1")

    benchmark_rows, benchmark_by_id = load_benchmark(benchmark_path)
    benchmark_id_hash = canonical_sha256([row["id"] for row in benchmark_rows])
    benchmark_question_hash = canonical_sha256(
        [{"id": row["id"], "question": row["question"]} for row in benchmark_rows]
    )

    normalized: dict[str, list[dict[str, Any]]] = {}
    source_info: dict[str, Any] = {}
    for system, spec in SYSTEMS.items():
        raw_path = (REPO_ROOT / spec["raw_path"]).resolve()
        if not raw_path.exists():
            raise SystemExit(f"Missing raw QA source for {system}: {raw_path}")
        rows, info = normalize_rows(system, spec, raw_path, benchmark_by_id)
        normalized[system] = rows
        source_info[system] = {
            "raw_path": str(raw_path.relative_to(REPO_ROOT)),
            "raw_sha256": sha256_file(raw_path),
            "contexts_key": spec["contexts_key"],
            "context_content_key": spec["context_content_key"],
            **info,
        }

    print(
        f"validated benchmark rows={len(benchmark_rows)} "
        f"id_sha256={benchmark_id_hash[:12]} question_sha256={benchmark_question_hash[:12]}",
        flush=True,
    )
    print("validated raw QA sources: " + ", ".join(normalized), flush=True)

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": {
            "name": "WikiEval",
            "rows": len(benchmark_rows),
            "source_path": str(benchmark_path.relative_to(REPO_ROOT)),
            "source_sha256": sha256_file(benchmark_path),
            "id_sha256": benchmark_id_hash,
            "question_sha256": benchmark_question_hash,
        },
        "evaluation": {
            "ragas_version": importlib.metadata.version("ragas"),
            "metrics": METRIC_NAMES,
            "judge": {
                "provider": args.llm_provider,
                "model": args.llm_model,
                "base_url": args.llm_base_url,
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
                "context_max_tokens": args.context_max_tokens,
            },
            "embedding": {
                "provider": args.embedding_provider,
                "model": args.embedding_model,
                "base_url": args.embedding_base_url,
            },
            "run_config": {
                "timeout": args.timeout,
                "max_workers": args.max_workers,
                "max_retries": 2,
                "raise_exceptions": False,
            },
            "field_mapping": {
                "question": "case.question",
                "answer": "raw.answer",
                "reference": "case.relevant_evidence[0]",
                "contexts": "platform-native raw context content list",
                "context_precision_contexts": (
                    f"first {args.context_k} contexts in native raw ranking"
                ),
            },
            "context_precision_context_k": args.context_k,
            "qa_reuse": True,
            "qa_evaluation_performed": False,
            "execution_mode": "RAGAS single_turn_ascore with per-row checkpoints; context verdicts parallelized",
            "checkpoint_granularity": "one completed metric-row score",
        },
        "systems": source_info,
    }
    json_dump(output_dir / "manifest.json", metadata)

    comparison: dict[str, Any] = {
        "benchmark": metadata["benchmark"],
        "evaluation": metadata["evaluation"],
        "systems": {},
    }
    for system in args.systems:
        rows = normalized[system]
        system_dir = output_dir / system
        system_dir.mkdir(parents=True, exist_ok=True)
        print(f"scoring {system}: rows={len(rows)}", flush=True)
        result_info = evaluate_system(
            rows,
            system_dir,
            input_sha256=source_info[system]["input_sha256"],
            llm_model=args.llm_model,
            embedding_model=args.embedding_model,
            llm_base_url=args.llm_base_url,
            llm_api_key=llm_api_key,
            embedding_base_url=args.embedding_base_url,
            embedding_api_key=embedding_api_key,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            context_max_tokens=args.context_max_tokens,
            timeout=args.timeout,
            max_workers=args.max_workers,
            reset=args.overwrite,
            retry_errors=args.retry_errors,
            reset_context_precision=args.reset_context_precision,
            context_k=args.context_k,
        )
        comparison["systems"][system] = {
            "source": source_info[system],
            **result_info["summary"],
        }
        print(f"completed {system}: {result_info['summary']['metrics']}", flush=True)

    json_dump(output_dir / "comparison.json", comparison)
    print(f"completed unified evaluation: {output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
