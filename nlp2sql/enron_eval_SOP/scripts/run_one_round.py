#!/usr/bin/env python3
"""统一启动Chat2DB、Wren或MOI的一轮Enron 50题采集。"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.7-plus-2026-05-26"
QUESTIONS = ROOT / "benchmark/questions/user/questions_enron_50_user_mix.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行一个产品的一轮50题；每题使用独立新会话"
    )
    parser.add_argument("--product", required=True, choices=("chat2db", "wren", "moi"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default=os.getenv("ENRON_EVAL_MODEL", MODEL))
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")

    parser.add_argument("--chat2db-log", type=Path)
    parser.add_argument("--chat2db-app-name", default="Chat2DB Pro")

    parser.add_argument(
        "--wren-url", default="http://localhost:3000/api/v1/generate_sql"
    )
    parser.add_argument(
        "--wren-config",
        type=Path,
        help="实际挂载到Wren AI Service的私有config.yaml；用于核验模型",
    )

    parser.add_argument("--knowledge-name", help="MOI知识库名称；运行MOI时必填")
    parser.add_argument("--semantic-rules", default="")
    parser.add_argument("--moi-base-url", default=os.getenv("MOI_BASE_URL", "http://localhost:18002"))
    parser.add_argument("--moi-uc-url", default=os.getenv("MOI_UC_URL", "http://127.0.0.1:19080"))
    parser.add_argument("--moi-workspace-id", default=os.getenv("MOI_WORKSPACE_ID", ""))
    return parser.parse_args()


def ensure_questions(path: Path) -> None:
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 50:
        raise ValueError(f"一轮必须正好包含50题，当前问题文件有{len(rows)}题")


def build_command(args: argparse.Namespace) -> tuple[list[str], Path]:
    common = ["--questions", str(args.questions.resolve()), "--repeats", "1"]
    if args.product == "chat2db":
        run_dir = ROOT / "runs/chat2db" / args.run_id
        command = [
            sys.executable,
            str(ROOT / "runners/run_chat2db_desktop.py"),
            *common,
            "--repeat-start", "1",
            "--run-id", args.run_id,
            "--output-root", str(ROOT / "runs/chat2db"),
            "--database", "enron_eval",
            "--expected-model", args.model,
            "--app-name", args.chat2db_app_name,
            "--timeout", str(args.timeout),
        ]
        if args.chat2db_log:
            command += ["--log", str(args.chat2db_log)]
        return command, run_dir

    if args.product == "wren":
        if not args.wren_config:
            raise ValueError("运行Wren时必须提供--wren-config核验实际模型")
        config_text = args.wren_config.read_text(encoding="utf-8")
        required = f"model: openai/{args.model}"
        if required not in config_text:
            raise ValueError(f"Wren配置未包含统一模型：{required}")
        run_dir = ROOT / "runs/wren" / args.run_id
        return [
            sys.executable,
            str(ROOT / "runners/run_wren.py"),
            *common,
            "--run-id", args.run_id,
            "--model", args.model,
            "--url", args.wren_url,
            "--timeout", str(args.timeout),
            "--output", str(run_dir / "predictions.jsonl"),
        ], run_dir

    if not args.knowledge_name:
        raise ValueError("运行MOI时必须提供--knowledge-name")
    if not args.moi_workspace_id:
        raise ValueError("运行MOI时必须设置MOI_WORKSPACE_ID或提供--moi-workspace-id")
    run_dir = ROOT / "runs/moi" / args.run_id
    command = [
        sys.executable,
        str(ROOT / "runners/run_moi.py"),
        *common,
        "--project-root", str(ROOT),
        "--run-id", args.run_id,
        "--output-root", str(ROOT / "runs/moi"),
        "--model", args.model,
        "--knowledge-name", args.knowledge_name,
        "--base-url", args.moi_base_url,
        "--uc-url", args.moi_uc_url,
        "--workspace-id", args.moi_workspace_id,
        "--timeout", str(int(args.timeout)),
    ]
    if args.semantic_rules:
        command += ["--semantic-rules", args.semantic_rules]
    if args.resume:
        command.append("--resume")
    return command, run_dir


def main() -> int:
    args = parse_args()
    ensure_questions(args.questions)
    if args.model != MODEL:
        raise ValueError(f"正式SOP固定模型为{MODEL}，当前传入{args.model}")
    command, run_dir = build_command(args)
    print("将运行：", shlex.join(command), flush=True)
    print("输出目录：", run_dir, flush=True)
    if args.dry_run:
        return 0
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode:
        return completed.returncode
    validator = [
        sys.executable,
        str(ROOT / "scripts/validate_one_round.py"),
        "--product", args.product,
        "--run-dir", str(run_dir),
        "--expected-model", args.model,
    ]
    if args.product == "wren" and args.wren_config:
        validator += ["--wren-config", str(args.wren_config.resolve())]
    return subprocess.run(validator, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
