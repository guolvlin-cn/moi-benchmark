#!/usr/bin/env python3
"""Regenerate normalized scoring inputs for MinerU and PaddleOCR-VL."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


def stable_id(path: Path, source_dir: Path) -> str:
    relative = path.relative_to(source_dir).as_posix()
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    base_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-parsing-dir", type=Path, default=base_default)
    parser.add_argument(
        "--mineru-adapter",
        type=Path,
        required=True,
        help=(
            "Path to tools/parsing_benchmark/tools/mineru_content_list_to_parsed "
            "from moi-parse-bench commit 06faf76112c998835f0f9ca174a5f2d311d559f2."
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    base = args.document_parsing_dir.resolve()
    source_dir = base / "datasets" / "半导体场景模拟数据"
    mineru_run = base / "runs" / "半导体场景模拟数据-mineru-precision"
    paddle_run = base / "runs" / "半导体场景模拟数据-paddleocr-vl"
    mineru_out = args.output_dir / "mineru-precision"
    paddle_out = args.output_dir / "paddleocr-vl"
    mineru_out.mkdir(parents=True, exist_ok=True)
    paddle_out.mkdir(parents=True, exist_ok=True)

    files = sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )
    if len(files) != 50:
        parser.error(f"expected 50 source files, found {len(files)}")

    for source in files:
        case_name = f"{source.name}--{stable_id(source, source_dir)}"
        mineru_candidates = list((mineru_run / case_name).glob("*_content_list.json"))
        if len(mineru_candidates) != 1:
            raise RuntimeError(
                f"expected one non-v2 MinerU content_list for {case_name}, "
                f"found {len(mineru_candidates)}"
            )
        mineru_target = mineru_out / f"{case_name}_parse.json"
        paddle_target = paddle_out / f"{case_name}_parse.json"
        if args.force or not mineru_target.exists():
            command = [
                sys.executable,
                str(args.mineru_adapter),
                str(mineru_candidates[0]),
                str(mineru_target),
            ]
            if args.force:
                command.append("--force")
            run(command)
        if args.force or not paddle_target.exists():
            command = [
                sys.executable,
                str(Path(__file__).with_name("adapt_paddleocr_vl_to_parsed.py")),
                str(paddle_run / case_name / "result.json"),
                str(paddle_target),
            ]
            if args.force:
                command.append("--force")
            run(command)

    print(f"MinerU: {mineru_out}")
    print(f"PaddleOCR-VL: {paddle_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
