#!/usr/bin/env python3
"""Run frozen Ragas diagnostic metrics over a completed MOI result ledger.

This is deliberately separate from the deterministic MOI scorer.  The judge
model and embeddings are supplied through an OpenAI-compatible TaaS endpoint,
and the exact versions/configuration are written beside the scores.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


METRIC_NAMES = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
DEFAULT_LLM_MODEL = "deepseek-v4-flash"
DEFAULT_EMBEDDING_MODEL = "bge-m3"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def result_to_sample(result: dict[str, Any]):
    from ragas import SingleTurnSample

    case = result.get("case") or {}
    chunks = result.get("chunks") or []
    if not chunks:
        # The local Dify adapter calls returned retriever passages "contexts".
        # Normalize that vendor-native shape to the same ranked-chunk contract
        # used by the MOI ledger before constructing the Ragas sample.
        chunks = [
            {
                "content": context.get("content") or "",
                "rank": context.get("position"),
                "file_name": context.get("document_name"),
            }
            for context in (result.get("contexts") or [])
        ]
    chunks = sorted(chunks, key=lambda item: item.get("rank", 10**9))
    metadata = case.get("metadata") or {}
    reference = metadata.get("reference") or (case.get("relevant_evidence") or [""])[0]
    return SingleTurnSample(
        user_input=str(case.get("question") or ""),
        retrieved_contexts=[str(chunk.get("content") or "") for chunk in chunks],
        response=str(result.get("answer") or ""),
        reference=str(reference or ""),
    )


class TaaSEmbeddings:
    """LangChain Embeddings-compatible adapter using a list-valued TaaS input."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int):
        from openai import OpenAI
        import httpx

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=2,
            http_client=httpx.Client(timeout=timeout, trust_env=False),
        )
        self.model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=list(texts),
            encoding_format="float",
        )
        return [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def make_ragas_clients(base_url: str, api_key: str, llm_model: str, embedding_model: str, timeout: int):
    import httpx
    from langchain_openai import ChatOpenAI
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper

    http_client = httpx.Client(timeout=timeout, trust_env=False)
    llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=llm_model,
            base_url=base_url,
            api_key=api_key,
            temperature=0,
            timeout=timeout,
            max_retries=2,
            http_client=http_client,
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        TaaSEmbeddings(base_url, api_key, embedding_model, timeout)
    )
    return llm, embeddings


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def summarize_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"rows": len(rows), "metrics": {}}
    for metric in METRIC_NAMES:
        values = [value for row in rows if (value := finite(row.get(metric))) is not None]
        summary["metrics"][metric] = {
            "scored_rows": len(values),
            "mean": statistics.fmean(values) if values else None,
            "p50": statistics.median(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    return summary


def evaluate_results(
    results: list[dict[str, Any]],
    *,
    base_url: str,
    api_key: str,
    llm_model: str = DEFAULT_LLM_MODEL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    timeout: int = 180,
    max_workers: int = 2,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    from ragas.run_config import RunConfig

    llm, embeddings = make_ragas_clients(base_url, api_key, llm_model, embedding_model, timeout)
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    dataset = EvaluationDataset(samples=[result_to_sample(result) for result in results])
    evaluated = evaluate(
        dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=timeout, max_retries=3, max_workers=max_workers, max_wait=60),
        raise_exceptions=False,
        show_progress=True,
        # Let Ragas schedule all jobs so RunConfig.max_workers is effective.
        # batch_size=1 would serialize the 200 metric jobs in ragas 0.2.x.
        batch_size=None,
    )
    frame = evaluated.to_pandas()
    score_rows: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        row = {"id": (result.get("case") or {}).get("id"), "status": result.get("status")}
        for metric in METRIC_NAMES:
            row[metric] = frame.iloc[index][metric] if metric in frame.columns else None
        score_rows.append(row)
    return score_rows, summarize_scores(score_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=os.getenv("TAAS_BASE_URL", "https://token.moi.matrixorigin.cn/v1"))
    parser.add_argument("--api-key-env", default="TAAS_API_KEY")
    parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-workers", type=int, default=2)
    args = parser.parse_args()
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        raise SystemExit(f"missing {args.api_key_env}")
    results = read_jsonl(args.results)
    score_rows, summary = evaluate_results(
        results,
        base_url=args.base_url,
        api_key=api_key,
        llm_model=args.llm_model,
        embedding_model=args.embedding_model,
        timeout=args.timeout,
        max_workers=args.max_workers,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "scores.jsonl", score_rows)
    write_json(args.output_dir / "summary.json", summary)
    write_json(args.output_dir / "config.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results_sha256": sha256_file(args.results),
        "ragas_version": importlib.metadata.version("ragas"),
        "llm_model": args.llm_model,
        "embedding_model": args.embedding_model,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "timeout": args.timeout,
        "max_workers": args.max_workers,
        "metrics": list(METRIC_NAMES),
        "temperature": 0,
        "raise_exceptions": False,
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
