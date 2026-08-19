#!/usr/bin/env python3
"""Measure the external embedding endpoints used by the local RAG platforms."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LENOVO_DIR = Path(__file__).resolve().parents[1] / "lenovo"
if str(LENOVO_DIR) not in sys.path:
    sys.path.insert(0, str(LENOVO_DIR))

from lenovo_latency_benchmark import DATASET_DEFAULT, load_query_rows, select_queries


ROOT = Path(__file__).resolve().parents[4]


def _load_env_file(path: Path, environ: dict[str, str]) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        environ.setdefault(key.strip(), value)


def _load_env() -> dict[str, str]:
    environ = dict(os.environ)
    _load_env_file(ROOT / ".env", environ)
    return environ


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _provider_configs(environ: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "provider": "huawei-maas",
            "base_url": environ.get("MAAS_BASE_URL", "https://api.modelarts-maas.com/v1").rstrip("/"),
            "model": environ.get("MAAS_EMBEDDING_MODEL", "bge-m3"),
            "api_key": environ.get("MAAS_API_KEY", ""),
        },
        {
            "provider": "qianfan-maas",
            "base_url": environ.get("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2").rstrip("/"),
            "model": environ.get("QIANFAN_EMBEDDING_MODEL", "qwen3-embedding-8b"),
            "api_key": environ.get("QIANFAN_API_KEY", ""),
        },
        {
            "provider": "matrixorigin-taas",
            "base_url": environ.get("TAAS_BASE_URL", "https://token.moi.matrixorigin.cn/v1").rstrip("/"),
            "model": environ.get("TAAS_EMBEDDING_MODEL", "bge-m3"),
            "api_key": environ.get("TAAS_API_KEY", ""),
        },
    ]


def _measure(config: dict[str, str], query: str, timeout_s: float, index: int, warmup: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    request_id = uuid.uuid4().hex
    request = Request(
        f"{config['base_url']}/embeddings",
        data=json.dumps({"model": config["model"], "input": [query], "encoding_format": "float"}).encode(),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
            "User-Agent": "MOI-RAG-MaaS-Baseline/0.1",
        },
    )
    result: dict[str, Any] = {
        "request_id": request_id,
        "provider": config["provider"],
        "model": config["model"],
        "query_index": index,
        "warmup": warmup,
        "success": False,
        "status_code": None,
        "latency_ms": None,
        "vector_dimension": None,
        "error": None,
    }
    try:
        with urlopen(request, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
            result["status_code"] = response.status
        data = payload.get("data") if isinstance(payload, dict) else None
        vector = data[0].get("embedding") if isinstance(data, list) and data and isinstance(data[0], dict) else None
        if not isinstance(vector, list) or not vector:
            raise ValueError("embedding response missing data[0].embedding")
        result["success"] = True
        result["vector_dimension"] = len(vector)
    except HTTPError as exc:
        result["status_code"] = exc.code
        result["error"] = f"http_status={exc.code}"
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    finally:
        result["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
    return result


def _run_provider(config: dict[str, str], queries: list[dict[str, Any]], connections: int, timeout_s: float) -> dict[str, Any]:
    if not config["api_key"]:
        return {
            "provider": config["provider"],
            "base_url": config["base_url"],
            "model": config["model"],
            "status": "skipped",
            "reason": "API key is not configured",
            "warmup": None,
            "samples": [],
        }
    warmup = _measure(config, queries[0]["question"], timeout_s, 0, warmup=True)
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=connections) as executor:
        futures = {
            executor.submit(_measure, config, row["question"], timeout_s, index): index
            for index, row in enumerate(queries)
        }
        for future in as_completed(futures):
            samples.append(future.result())
    wall_s = max(time.monotonic() - started, 1e-9)
    successful = [sample for sample in samples if sample["success"]]
    latencies = [float(sample["latency_ms"]) for sample in successful]
    return {
        "provider": config["provider"],
        "base_url": config["base_url"],
        "model": config["model"],
        "status": "ok" if len(successful) == len(samples) else "partial" if successful else "error",
        "warmup": warmup,
        "requests": len(samples),
        "successes": len(successful),
        "errors": len(samples) - len(successful),
        "success_rate": len(successful) / len(samples) if samples else 0.0,
        "qps": len(successful) / wall_s if successful else 0.0,
        "latency_ms": {
            "count": len(latencies),
            "min": min(latencies) if latencies else None,
            "avg": sum(latencies) / len(latencies) if latencies else None,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
        },
        "vector_dimensions": sorted({sample["vector_dimension"] for sample in successful}),
        "connections": connections,
        "samples": samples,
    }


def run(args: argparse.Namespace) -> Path:
    rows = load_query_rows(Path(args.questions))
    queries = select_queries(rows, args.count, args.seed)
    output_dir = args.output or ROOT / "runs/lenovo-local-latency" / f"{time.strftime('%Y%m%d-%H%M%S')}-maas-baseline"
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "selected-queries.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in queries), encoding="utf-8"
    )
    results = {
        config["provider"]: _run_provider(config, queries, args.connections, args.timeout)
        for config in _provider_configs(_load_env())
    }
    (output_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps({
        "count": len(queries),
        "seed": args.seed,
        "connections": args.connections,
        "timeout_seconds": args.timeout,
        "track": "external embedding endpoint baseline",
        "quality_evaluation": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# External MaaS embedding baseline",
        "",
        f"Fixed query count: `{len(queries)}`, seed: `{args.seed}`, concurrency: `{args.connections}`.",
        "This is a reference line for interpreting local platform retrieval latency; it is not a local deployment measurement.",
        "",
        "| Provider | Model | Success | p50 (ms) | p95 (ms) | QPS | Dimensions |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for provider, result in results.items():
        latency = result.get("latency_ms") or {}
        lines.append(
            f"| {provider} | {result.get('model', 'N/A')} | {result.get('successes', 0)}/{result.get('requests', 0)} | "
            f"{latency.get('p50', 'N/A')} | {latency.get('p95', 'N/A')} | {result.get('qps', 'N/A')} | "
            f"{','.join(str(x) for x in result.get('vector_dimensions', [])) or 'N/A'} |"
        )
    report_path = output_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DATASET_DEFAULT)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--connections", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    print(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
