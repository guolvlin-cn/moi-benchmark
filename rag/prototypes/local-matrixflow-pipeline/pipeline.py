#!/usr/bin/env python3
"""PROTOTYPE: local MatrixFlow parse -> index -> Explore QA orchestration."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARSER = ROOT / "local-matrixflow-parser"
RAG = ROOT / "local-matrixflow-rag"


def allocate_run(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:-3]
    for sequence in range(100):
        name = stamp if sequence == 0 else f"{stamp}-{sequence:02d}"
        candidate = root / name
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("could not allocate a unique run directory")


def run_command(command: list[str], cwd: Path, log_path: Path) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "$ " + " ".join(command) + "\n\nSTDOUT\n" + completed.stdout
        + "\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}); see {log_path}")
    return completed.stdout


def emitted_run_dir(output: str) -> Path:
    for line in output.splitlines():
        if line.startswith("run_dir="):
            return Path(line.removeprefix("run_dir=").strip()).resolve()
    raise RuntimeError("child command did not emit run_dir")


def input_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path.resolve()]
    if not path.is_dir():
        raise FileNotFoundError(path)
    return sorted(item.resolve() for item in path.rglob("*") if item.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MatrixFlow parser, product ingestion, and Explore QA as one local pipeline."
    )
    parser.add_argument("--input", required=True, help="document file or directory")
    parser.add_argument("--config", required=True, help="local-matrixflow-rag config JSON")
    parser.add_argument("--question", help="single interactive knowledge question")
    parser.add_argument("--dataset", help="optional benchmark questions JSONL")
    parser.add_argument("--parser-profile", default="web-default", choices=["web-default", "v3-native"])
    parser.add_argument("--run", default="runs/end-to-end", help="artifact root")
    parser.add_argument("--max-hits", type=int, default=10)
    args = parser.parse_args()

    run_dir = allocate_run(Path(args.run).resolve())
    print(f"run_dir={run_dir}")
    combined = run_dir / "parsed-documents.jsonl"
    manifest: dict[str, object] = {
        "schema_version": "matrixflow-local-e2e-v1",
        "parser_profile": args.parser_profile,
        "inputs": [],
        "status": "running",
    }
    try:
        with combined.open("w", encoding="utf-8") as destination:
            for index, source in enumerate(input_files(Path(args.input))):
                child_root = run_dir / "parse" / f"{index:04d}-{source.stem}"
                output = run_command(
                    [
                        "go", "run", "./cmd/local-matrixflow-parser", "parse",
                        "--input", str(source),
                        "--profile", args.parser_profile,
                        "--run", str(child_root),
                    ],
                    PARSER,
                    run_dir / "logs" / f"parse-{index:04d}.log",
                )
                child = emitted_run_dir(output)
                documents = child / "documents.jsonl"
                destination.write(documents.read_text(encoding="utf-8"))
                summary = json.loads((child / "summary.json").read_text(encoding="utf-8"))
                manifest["inputs"].append(
                    {"source": str(source), "run_dir": str(child), "summary": summary}
                )

        ingest_output = run_command(
            [
                "go", "run", ".", "ingest",
                "--config", str(Path(args.config).resolve()),
                "--documents", str(combined),
                "--run", str(run_dir / "rag-ingest"),
                "--force",
            ],
            RAG,
            run_dir / "logs" / "rag-ingest.log",
        )
        manifest["rag_ingest_run"] = str(emitted_run_dir(ingest_output))

        if args.question:
            ask_output = run_command(
                [
                    "go", "run", ".", "ask",
                    "--config", str(Path(args.config).resolve()),
                    "--question", args.question,
                    "--run", str(run_dir / "qa"),
                ],
                RAG,
                run_dir / "logs" / "qa.log",
            )
            qa_run = emitted_run_dir(ask_output)
            manifest["qa_run"] = str(qa_run)
            print((qa_run / "answer.json").read_text(encoding="utf-8"))

        if args.dataset:
            benchmark_output = run_command(
                [
                    "go", "run", ".", "run",
                    "--config", str(Path(args.config).resolve()),
                    "--dataset", str(Path(args.dataset).resolve()),
                    "--run", str(run_dir / "benchmark"),
                    "--max-hits", str(args.max_hits),
                ],
                RAG,
                run_dir / "logs" / "benchmark.log",
            )
            manifest["benchmark_run"] = str(emitted_run_dir(benchmark_output))
        manifest["status"] = "succeeded"
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        (run_dir / "pipeline-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
