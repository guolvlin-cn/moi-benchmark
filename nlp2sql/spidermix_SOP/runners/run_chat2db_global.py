#!/usr/bin/env python3
"""Run Spider Mix50 through Chat2DB's real global desktop chat panel."""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ENRON_RUNNER = (
    Path(__file__).resolve().parents[2]
    / "enron_eval_SOP/runners/run_chat2db_desktop.py"
)
DEFAULT_QUESTIONS = ROOT / "benchmark/questions/questions_mix50.tsv"
DEFAULT_DATABASES = ROOT / "benchmark/questions/case_databases.tsv"
DEFAULT_LOG = Path.home() / ".chat2db/chat2db-enterprise/logs/application.log"
DEFAULT_MODEL = "qwen3.7-plus-2026-05-26"


def load_base_module():
    spec = importlib.util.spec_from_file_location("chat2db_enron_runner", ENRON_RUNNER)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load Chat2DB collector: {ENRON_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_base_module()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--databases", type=Path, default=DEFAULT_DATABASES)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs/chat2db")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument(
        "--database-only",
        choices=("pets_1", "concert_singer", "car_1"),
        help="只运行属于指定数据库的题目；用于人工切库后的三批正式采集",
    )
    parser.add_argument("--expected-model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--fixed-database",
        default="",
        help="已在Chat2DB界面人工绑定的数据库；填写后逐题校验日志中的database上下文",
    )
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--cooldown", type=float, default=1)
    parser.add_argument("--new-chat-delay", type=float, default=1)
    parser.add_argument("--focus-x", type=float, default=700)
    parser.add_argument("--focus-y", type=float, default=100)
    parser.add_argument("--input-x", type=float, default=900)
    parser.add_argument("--input-y", type=float, default=535)
    parser.add_argument("--new-chat-x", type=float, default=250)
    parser.add_argument("--new-chat-y", type=float, default=86)
    parser.add_argument(
        "--new-chat-shortcut",
        action="store_true",
        help="使用Chat2DB内置Cmd+L新建对话；新对话会保留当前数据库选择",
    )
    parser.add_argument(
        "--skip-new-chat-first",
        action="store_true",
        help="Use only for a smoke test when the visible panel is already an empty new chat",
    )
    return parser.parse_args()


def load_tsv(path: Path) -> list[tuple[str, str]]:
    rows = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split("\t", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid TSV line {line_number}: {raw}")
        rows.append((parts[0].strip(), parts[1].strip()))
    return rows


def native_key(keycode: int, flags: int = 0) -> None:
    core_graphics = ctypes.CDLL(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    core_foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    core_graphics.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    core_graphics.CGEventCreateKeyboardEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint16,
        ctypes.c_bool,
    ]
    core_graphics.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    core_graphics.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
    for is_down in (True, False):
        event = core_graphics.CGEventCreateKeyboardEvent(None, keycode, is_down)
        if flags:
            core_graphics.CGEventSetFlags(event, flags)
        core_graphics.CGEventPost(0, event)
        core_foundation.CFRelease(event)
        time.sleep(0.05)


def submit(args: argparse.Namespace, question: str, create_chat: bool) -> None:
    BASE.native_click(args.focus_x, args.focus_y)
    time.sleep(0.25)
    if create_chat:
        if args.new_chat_shortcut:
            native_key(37, 1 << 20)  # Command+L: Chat2DB内置“新AI对话”
        else:
            if not args.new_chat_x or not args.new_chat_y:
                raise ValueError("New-chat coordinates are required for independent attempts")
            BASE.native_click(args.new_chat_x, args.new_chat_y)
        time.sleep(args.new_chat_delay)
    # Cmd+L creates a new chat but does not focus the JCEF editor.  Always click
    # the composer before pasting; coordinates are macOS logical points.
    BASE.native_click(args.input_x, args.input_y)
    time.sleep(0.2)
    subprocess.run(["pbcopy"], input=question, text=True, check=True, timeout=10)
    native_key(9, 1 << 20)  # Command+V
    time.sleep(0.2)
    native_key(36)  # Return


def load_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    args = parse_args()
    if sys.platform != "darwin":
        raise RuntimeError("Chat2DB desktop automation requires macOS")
    questions = load_tsv(args.questions)
    database_map = dict(load_tsv(args.databases))
    if len(questions) != 50 or len(database_map) != 50:
        raise ValueError("Spider Mix50 must contain exactly 50 questions and mappings")
    if args.case:
        selected = set(args.case)
        questions = [item for item in questions if item[0] in selected]
        missing = selected - {item[0] for item in questions}
        if missing:
            raise ValueError(f"Unknown cases: {sorted(missing)}")
    if args.database_only:
        if args.fixed_database and args.fixed_database != args.database_only:
            raise ValueError("--fixed-database必须与--database-only一致")
        questions = [
            item for item in questions if database_map[item[0]] == args.database_only
        ]
        if not questions:
            raise ValueError(f"No questions for database: {args.database_only}")

    run_dir = args.output_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = run_dir / "predictions.jsonl"
    run_path = run_dir / "run.json"
    existing = load_existing(predictions_path)
    completed = {
        (str(item["question_id"]), int(item.get("repeat_index") or 1)) for item in existing
    }
    if not run_path.exists():
        run_path.write_text(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "product": "chat2db",
                    "benchmark_id": "spider_mix50",
                    "database_context": args.fixed_database or "global",
                    "expected_model": args.expected_model,
                    "repeats": args.repeats,
                    "collection_mode": "macos_ui_plus_application_log",
                    "started_at": datetime.now().astimezone().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    total = len(questions) * args.repeats
    sequence = 0
    for repeat_index in range(1, args.repeats + 1):
        for question_id, question in questions:
            sequence += 1
            key = (question_id, repeat_index)
            if key in completed:
                print(f"[{sequence:03d}/{total}] {question_id} r{repeat_index} SKIP", flush=True)
                continue
            offset = args.log.stat().st_size
            first_attempt = not existing and sequence == 1
            create_chat = not (first_attempt and args.skip_new_chat_first)
            try:
                submit(args, question, create_chat)
                capture = BASE.wait_for_capture(args.log, offset, args.timeout)
                result = BASE.parse_capture(capture)
                metadata = result.setdefault("metadata", {})
                metadata["collector"] = (
                    "chat2db_fixed_database_desktop_log_v1"
                    if args.fixed_database
                    else "chat2db_global_desktop_log_v1"
                )
                metadata["target_database"] = database_map[question_id]
                context_error = None
                if metadata.get("history_size") != 0:
                    context_error = f"Expected a new chat with historySize=0, got {metadata.get('history_size')}"
                elif args.fixed_database and database_map[question_id] != args.fixed_database:
                    context_error = (
                        f"Question {question_id} targets {database_map[question_id]}, "
                        f"but the fixed database is {args.fixed_database}"
                    )
                elif args.fixed_database and metadata.get("database") != args.fixed_database:
                    context_error = (
                        f"Expected database {args.fixed_database}, got {metadata.get('database')}"
                    )
                elif not args.fixed_database and metadata.get("database") is not None:
                    context_error = f"Expected global database context, got {metadata.get('database')}"
                elif metadata.get("model") != args.expected_model:
                    context_error = f"Expected model {args.expected_model}, got {metadata.get('model')}"
                record = {
                    "question_id": question_id,
                    "question": question,
                    "repeat_index": repeat_index,
                    **result,
                }
                if context_error:
                    record["status"] = "context_error"
                    record["error"] = context_error
                BASE.append_jsonl(predictions_path, record)
                existing.append(record)
                completed.add(key)
                print(
                    f"[{sequence:03d}/{total}] {question_id} r{repeat_index} "
                    f"{record['status']} {record['latency_ms'] / 1000:.3f}s "
                    f"tokens={record['total_tokens']}",
                    flush=True,
                )
                if context_error:
                    return 2
            except Exception as exc:
                print(f"Stopped at {question_id}: {exc}", file=sys.stderr, flush=True)
                return 2
            time.sleep(args.cooldown)

    run_info = json.loads(run_path.read_text(encoding="utf-8"))
    run_info["completed_at"] = datetime.now().astimezone().isoformat()
    run_info["record_count"] = len(load_existing(predictions_path))
    run_path.write_text(json.dumps(run_info, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
