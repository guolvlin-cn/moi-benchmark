from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import load_config
from .dify import DifyClient
from .io import read_jsonl, read_result_jsonl, write_jsonl
from .knowledge import KnowledgeClient, ingest_directory, validate_chunk_options
from .api_benchmark import add_api_benchmark_parser, run_api_benchmark_command
from .local_smoke import SmokeContext, run_local_smoke
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

    local_smoke = subparsers.add_parser(
        "local-smoke", help="run the initial self-hosted competitor API smoke"
    )
    local_smoke.add_argument(
        "--system",
        required=True,
        choices=("dify_local", "fastgpt_local", "ragflow_local", "maxkb_local"),
    )
    local_smoke.add_argument("--base-url")
    local_smoke.add_argument("--output", required=True, type=Path)
    local_smoke.add_argument(
        "--source",
        type=Path,
        default=Path("local-rag-platforms/fixtures/smoke"),
    )
    local_smoke.add_argument("--api-key-env", default="LOCAL_RAG_API_KEY")
    local_smoke.add_argument("--dataset-api-key-env", default="DIFY_LOCAL_DATASET_API_KEY")
    local_smoke.add_argument(
        "--dataset-id-env",
        default="DIFY_LOCAL_DATASET_ID",
        help="reuse an existing Dify dataset so the native app and retrieval smoke share one corpus",
    )
    local_smoke.add_argument("--app-api-key-env", default="DIFY_LOCAL_API_KEY")
    local_smoke.add_argument("--app-id-env", default="FASTGPT_APP_ID")
    local_smoke.add_argument("--question", default="Where must the RAG service under test run, and what external dependency is allowed?")
    local_smoke.add_argument("--retrieval-probe", default="Colima machine")
    local_smoke.add_argument("--wait-seconds", type=int, default=120)
    local_smoke.add_argument("--platform", default="linux/arm64")
    local_smoke.add_argument(
        "--blocked-reason",
        choices=(
            "BLOCKED_LOCAL_ARCH",
            "BLOCKED_LOCAL_RESOURCES",
            "BLOCKED_LOCAL_DEPENDENCY",
        ),
        help="override the deployment gate reason while preserving the failed smoke calls",
    )
    local_smoke.add_argument("--embedding-model", default=os.getenv("DIFY_EMBEDDING_MODEL"))
    local_smoke.add_argument("--embedding-provider", default=os.getenv("DIFY_EMBEDDING_PROVIDER"))
    local_smoke.add_argument("--vector-model", default=os.getenv("FASTGPT_VECTOR_MODEL"))
    local_smoke.add_argument("--agent-model", default=os.getenv("FASTGPT_AGENT_MODEL"))
    local_smoke.add_argument("--chat-id", default=os.getenv("RAGFLOW_CHAT_ID"))
    local_smoke.add_argument("--native-base-url", default=os.getenv("MAXKB_OPENAI_BASE_URL"))
    local_smoke.add_argument("--native-path", default=os.getenv("MAXKB_OPENAI_PATH"))
    local_smoke.add_argument("--model", default=os.getenv("MAXKB_MODEL", "default"))
    add_api_benchmark_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    # The repository-root .env is the single local credential entry point.
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
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

    if args.command == "local-smoke":
        base_urls = {
            "dify_local": "http://127.0.0.1:8010/v1",
            "fastgpt_local": "http://127.0.0.1:3000",
            "ragflow_local": "http://127.0.0.1:9380",
            "maxkb_local": "http://127.0.0.1:8090",
        }
        api_key = os.getenv(args.api_key_env)
        dataset_api_key = os.getenv(args.dataset_api_key_env)
        dataset_id = os.getenv(args.dataset_id_env)
        app_api_key = os.getenv(args.app_api_key_env)
        app_id = os.getenv(args.app_id_env)
        context = SmokeContext(
            system_id=args.system,
            base_url=args.base_url or base_urls[args.system],
            output=args.output,
            api_key=api_key,
            dataset_api_key=dataset_api_key,
            app_api_key=app_api_key,
            app_id=app_id,
            source_dir=args.source,
            question=args.question,
            retrieval_probe=args.retrieval_probe,
            wait_seconds=args.wait_seconds,
            platform=args.platform,
            options={
                "embedding_model": args.embedding_model,
                "embedding_provider": args.embedding_provider,
                "dataset_id": dataset_id,
                "vector_model": args.vector_model,
                "agent_model": args.agent_model,
                "chat_id": args.chat_id,
                "native_base_url": args.native_base_url,
                "native_path": args.native_path,
                "model": args.model,
                "blocked_reason": args.blocked_reason,
            },
        )
        result = run_local_smoke(context)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "api-benchmark":
        try:
            return run_api_benchmark_command(args)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

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
