#!/usr/bin/env python3
"""统一评分Enron三轮产物；MOI使用MatrixOne原生结果。"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评分一个产品的50题×3轮产物")
    parser.add_argument("--product", required=True, choices=("chat2db", "wren", "moi"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--variant",
        default="baseline_no_semantic",
        help="MOI条件名称，例如baseline_no_semantic或semantic_v2",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    predictions = run_dir / "predictions.jsonl"
    validation = run_dir / "validation.json"
    if not predictions.exists():
        raise FileNotFoundError(f"缺少预测文件：{predictions}")
    if not validation.exists():
        raise FileNotFoundError("必须先运行validate_three_rounds.py并生成validation.json")
    validation_info = json.loads(validation.read_text(encoding="utf-8"))
    if validation_info.get("validation") != "passed":
        raise ValueError("validation.json未通过，不能评分")
    if validation_info.get("product") != args.product:
        raise ValueError(
            f"validation.json产品为{validation_info.get('product')}，不是{args.product}"
        )
    if int(validation_info.get("attempts") or 0) != 150:
        raise ValueError("validation.json未确认150次完整请求")

    output = (args.output or (run_dir / "evaluation.json")).resolve()
    if args.product == "moi":
        command = [
            sys.executable,
            str(ROOT / "scoring_code/evaluate_moi_native.py"),
            "--predictions", str(predictions),
            "--run-id", run_dir.name,
            "--variant", args.variant,
            "--expected-repeats", "3",
            "--output", str(output),
        ]
    else:
        command = [
            sys.executable,
            str(ROOT / "scoring_code/evaluate_repeated_mysql.py"),
            "--predictions", str(predictions),
            "--product", args.product,
            "--run-id", run_dir.name,
            "--expected-repeats", "3",
            "--output", str(output),
        ]
    print("将评分：", shlex.join(command), flush=True)
    if args.dry_run:
        return 0
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
