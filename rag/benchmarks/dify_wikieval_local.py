#!/usr/bin/env python3
"""Run the local Dify app on the prepared WikiEval question set.

The local app is temporarily rebound to the run-specific Dify dataset so its
native chat path is evaluated against exactly the same 50 WikiEval documents
as MOI.  The original app dataset binding is restored in ``finally``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local-rag-platforms/dify-rag-eval/src"))

from dify_rag_eval.config import Config  # noqa: E402
from dify_rag_eval.dify import DifyClient  # noqa: E402
from dify_rag_eval.io import read_jsonl, write_jsonl  # noqa: E402
from dify_rag_eval.metrics import summarize  # noqa: E402
from dify_rag_eval.report import write_report  # noqa: E402
from dify_rag_eval.runner import run_dataset  # noqa: E402


def load_binding_module():
    path = ROOT / "local-rag-platforms/scripts/evaluation/mmdocir_competitor_eval.py"
    spec = importlib.util.spec_from_file_location("mmdocir_competitor_eval", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Dify binding module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def adapt_case(case: dict[str, object]) -> dict[str, object]:
    """Map the WikiEval adapter fields to dify-rag-eval's metric contract."""
    adapted = dict(case)
    metadata = adapted.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    adapted.setdefault("gold_document_names", adapted.get("relevant_documents") or [])
    adapted.setdefault("gold_evidence", adapted.get("relevant_evidence") or [])
    adapted.setdefault("references", [metadata.get("reference") or (adapted.get("relevant_evidence") or [""])[0]])
    adapted.setdefault("required_keywords", adapted.get("expected_answer_keywords") or [])
    return adapted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dify-dataset-id", required=True)
    parser.add_argument("--base-url", default=os.getenv("DIFY_API_BASE_URL", "http://127.0.0.1:8010/v1"))
    parser.add_argument("--api-key-env", default="DIFY_LOCAL_API_KEY")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env)
    app_id = os.getenv("DIFY_LOCAL_APP_ID")
    if not api_key:
        raise SystemExit(f"missing {args.api_key_env}")
    if not app_id:
        raise SystemExit("missing DIFY_LOCAL_APP_ID")
    if not os.getenv("DIFY_LOCAL_ADMIN_EMAIL") or not os.getenv("DIFY_LOCAL_ADMIN_PASSWORD"):
        raise SystemExit("missing DIFY_LOCAL_ADMIN_EMAIL or DIFY_LOCAL_ADMIN_PASSWORD")

    args.output.mkdir(parents=True, exist_ok=True)
    binding_module = load_binding_module()
    progress = binding_module.Progress(args.output / "binding-progress.jsonl")
    binding = binding_module.DifyNativeDatasetBinding(os.environ, app_id, progress)
    config = Config(
        base_url=args.base_url,
        app_type="chat",
        api_key_env=args.api_key_env,
        user_prefix="moi-wikieval-dify",
        timeout_seconds=180,
        max_retries=3,
        concurrency=args.concurrency,
        repeats=1,
        top_k=args.top_k,
    )
    cases = [adapt_case(case) for case in read_jsonl(args.dataset)]
    write_json(args.output / "run-config.json", {
        "protocol": "wikieval-dify-local-v1",
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "dify_dataset_id": args.dify_dataset_id,
        "dify_app_id_loaded": bool(app_id),
        "questions": len(cases),
        "concurrency": args.concurrency,
        "top_k": args.top_k,
    })
    binding.bind(args.dify_dataset_id, args.output)
    try:
        results = run_dataset(config, DifyClient(config, api_key), cases)
        write_jsonl(args.output / "results.jsonl", results)
        summary = summarize(results)
        summary["protocol"] = "wikieval-dify-local-v1"
        write_json(args.output / "summary.json", summary)
        write_report(args.output / "report.md", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        binding.restore(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
