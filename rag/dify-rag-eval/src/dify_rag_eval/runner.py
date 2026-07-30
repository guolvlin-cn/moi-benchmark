from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .config import Config
from .dify import DifyClient
from .metrics import score_result


def run_dataset(
    config: Config, client: DifyClient, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    work = [
        (case, repeat)
        for case in cases
        for repeat in range(1, config.repeats + 1)
    ]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = {
            executor.submit(_run_one, client, case, repeat): (case["id"], repeat)
            for case, repeat in work
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(score_result(result, config.top_k))
            status = "ok" if not result.get("error") else "failed"
            print(
                f"[{len(results)}/{len(work)}] {result['case']['id']} "
                f"repeat={result['repeat']} {status}"
            )
    return sorted(results, key=lambda item: (item["case"]["id"], item["repeat"]))


def _run_one(
    client: DifyClient, case: dict[str, Any], repeat: int
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.query(
            case["question"],
            case_id=case["id"],
            repeat=repeat,
            case_inputs=case.get("inputs") or {},
        )
        return {
            "case": case,
            "repeat": repeat,
            "answer": response.answer,
            "contexts": response.contexts,
            "usage": response.usage,
            "ids": response.ids,
            "raw_response": response.raw,
            "latency_seconds": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:  # Keep failed attempts in the benchmark denominator.
        return {
            "case": case,
            "repeat": repeat,
            "answer": "",
            "contexts": [],
            "usage": {},
            "ids": {},
            "raw_response": None,
            "latency_seconds": time.perf_counter() - started,
            "error": f"{type(exc).__name__}: {exc}",
        }

