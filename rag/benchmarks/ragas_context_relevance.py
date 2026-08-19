#!/usr/bin/env python3
"""Run the legacy Ragas ContextRelevance diagnostic on a result ledger.

Ragas 0.2.15 still exposes the paper-era metric as ``nv_context_relevance``.
It is kept in a separate runner so the modern four-metric result files remain
unchanged and the different metric name/denominator are explicit.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ragas_wikieval_judge import (
    make_ragas_clients,
    read_jsonl,
    result_to_sample,
    sha256_file,
    write_json,
    write_jsonl,
)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def evaluate_results(
    results: list[dict[str, Any]],
    *,
    base_url: str,
    api_key: str,
    llm_model: str,
    embedding_model: str,
    timeout: int,
    max_workers: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import ContextRelevance
    from ragas.run_config import RunConfig

    llm, embeddings = make_ragas_clients(base_url, api_key, llm_model, embedding_model, timeout)
    dataset = EvaluationDataset(samples=[result_to_sample(result) for result in results])
    evaluated = evaluate(
        dataset,
        metrics=[ContextRelevance()],
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=timeout, max_retries=3, max_workers=max_workers, max_wait=60),
        raise_exceptions=False,
        show_progress=True,
        batch_size=None,
    )
    frame = evaluated.to_pandas()
    metric_name = "nv_context_relevance"
    rows: list[dict[str, Any]] = []
    values: list[float] = []
    for index, result in enumerate(results):
        value = frame.iloc[index][metric_name] if metric_name in frame.columns else None
        value = finite(value)
        if value is not None:
            values.append(value)
        rows.append({
            "id": (result.get("case") or {}).get("id"),
            "status": result.get("status"),
            metric_name: value,
        })
    summary = {
        "rows": len(rows),
        "metric": metric_name,
        "scored_rows": len(values),
        "mean": statistics.fmean(values) if values else None,
        "p50": statistics.median(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=os.getenv("TAAS_BASE_URL", "https://token.moi.matrixorigin.cn/v1"))
    parser.add_argument("--api-key-env", default="TAAS_API_KEY")
    parser.add_argument("--llm-model", default="deepseek-v4-flash")
    parser.add_argument("--embedding-model", default="bge-m3")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        raise SystemExit(f"missing {args.api_key_env}")
    rows, summary = evaluate_results(
        read_jsonl(args.results),
        base_url=args.base_url,
        api_key=api_key,
        llm_model=args.llm_model,
        embedding_model=args.embedding_model,
        timeout=args.timeout,
        max_workers=args.max_workers,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "scores.jsonl", rows)
    write_json(args.output_dir / "summary.json", summary)
    write_json(args.output_dir / "config.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results_sha256": sha256_file(args.results),
        "ragas_version": importlib.metadata.version("ragas"),
        "metric": "nv_context_relevance",
        "metric_class": "ContextRelevance",
        "llm_model": args.llm_model,
        "embedding_model": args.embedding_model,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "timeout": args.timeout,
        "max_workers": args.max_workers,
        "temperature": 0.1,
        "raise_exceptions": False,
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
