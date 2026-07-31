from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import load_config
from .dify import DifyClient
from .io import read_jsonl, read_result_jsonl, write_jsonl
from .knowledge import KnowledgeClient, ingest_directory, validate_chunk_options
from .metrics import score_result, summarize
from .report import write_report
from .runner import run_dataset


def load_dotenv(path: Path, environ: dict[str, str] | None = None) -> None:
    """Load simple KEY=VALUE entries without overriding explicit environment values."""
    target = os.environ if environ is None else environ
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        target.setdefault(key, value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dify-rag-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a JSONL dataset")
    validate.add_argument("--dataset", required=True)

    run = subparsers.add_parser("run", help="query Dify and score every attempt")
    run.add_argument("--config", required=True)
    run.add_argument("--dataset", required=True)
    run.add_argument("--output", default="runs/latest")

    score = subparsers.add_parser("score", help="re-score a saved results JSONL")
    score.add_argument("--results", required=True)
    score.add_argument("--output", default="runs/rescored")
    score.add_argument("--top-k", type=int, default=5)

    ingest = subparsers.add_parser(
        "ingest", help="create/reuse a Dify knowledge base and upload a directory"
    )
    ingest.add_argument("--source", required=True, type=Path)
    ingest.add_argument("--knowledge-name", required=True)
    ingest.add_argument("--output", default="runs/ingest", type=Path)
    ingest.add_argument(
        "--base-url",
        default=os.getenv("DIFY_API_BASE_URL", "https://api.dify.ai/v1"),
    )
    ingest.add_argument("--api-key-env", default="DIFY_DATASET_API_KEY")
    ingest.add_argument("--embedding-model")
    ingest.add_argument("--embedding-provider")
    ingest.add_argument("--search-method", default="semantic_search")
    ingest.add_argument("--top-k", type=int, default=5)
    ingest.add_argument("--upload-interval", type=float, default=6.5)
    ingest.add_argument("--wait", action="store_true")
    ingest.add_argument("--probe")
    ingest.add_argument(
        "--local-chunks",
        action="store_true",
        help="deterministically split local Markdown/plain-text files before upload",
    )
    ingest.add_argument("--chunk-size", type=int, default=2000)
    ingest.add_argument("--chunk-overlap", type=int, default=200)
    ingest.add_argument(
        "--segment-max-tokens",
        type=int,
        help="use Dify custom segmentation with this maximum token count",
    )
    ingest.add_argument(
        "--indexing-technique",
        choices=("high_quality", "economy"),
        default="high_quality",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        rows = read_jsonl(args.dataset)
        print(f"valid: {len(rows)} cases")
        return 0

    if args.command == "ingest":
        try:
            validate_chunk_options(args.chunk_size, args.chunk_overlap)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        api_key = os.getenv(args.api_key_env)
        if not api_key:
            raise SystemExit(
                f"missing API key: set environment variable {args.api_key_env}"
            )
        if not args.source.is_dir():
            raise SystemExit(f"source is not a directory: {args.source}")
        ingest_directory(
            KnowledgeClient(
                args.base_url,
                api_key,
                segment_max_tokens=args.segment_max_tokens,
                indexing_technique=args.indexing_technique,
            ),
            source=args.source,
            knowledge_name=args.knowledge_name,
            output=args.output,
            embedding_model=args.embedding_model,
            embedding_provider=args.embedding_provider,
            top_k=args.top_k,
            search_method=args.search_method,
            upload_interval_seconds=args.upload_interval,
            wait=args.wait,
            probe=args.probe,
            local_chunks=args.local_chunks,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
        print(f"ingest artifacts: {args.output.resolve()}")
        return 0

    if args.command == "run":
        config = load_config(args.config)
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise SystemExit(
                f"missing API key: set environment variable {config.api_key_env}"
            )
        cases = read_jsonl(args.dataset)
        results = run_dataset(config, DifyClient(config, api_key), cases)
    else:
        raw_results = read_result_jsonl(args.results)
        results = [score_result(result, args.top_k) for result in raw_results]

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "results.jsonl", results)
    summary = summarize(results)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(output / "report.md", summary)
    print(f"results: {output.resolve()}")
    return 0
