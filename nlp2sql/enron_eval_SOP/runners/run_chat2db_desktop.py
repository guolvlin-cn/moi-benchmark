#!/usr/bin/env python3
"""通过真实 Chat2DB Pro 桌面界面运行 Enron 问题，并从日志采集指标。"""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS = PROJECT_ROOT / "benchmark/questions/user/questions_enron_50_user_mix.txt"
DEFAULT_LOG = Path.home() / ".chat2db/chat2db-enterprise/logs/application.log"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "products/chat2db/results/automated"
DEFAULT_MODEL = "qwen3.7-plus-2026-05-26"
TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")
CHAT_START = "/api/v3/ai/chat/stream"
CHAT_COMPLETE = "v3 ai_complete via JCEF IPC"
FENCED_SQL = re.compile(r"```sql\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="在 Chat2DB Pro 中逐题新建对话并采集 SQL、耗时和 Token"
    )
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--repeat-start",
        type=int,
        default=1,
        help="本批次起始轮次编号；分批运行时依次使用1、2、3",
    )
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument(
        "--force-case",
        action="append",
        default=[],
        help="强制重跑指定题号；旧记录移入replaced_predictions.jsonl后原位替换",
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--cooldown", type=float, default=1.0)
    parser.add_argument("--new-chat-delay", type=float, default=1.0)
    parser.add_argument("--database", default="enron_eval")
    parser.add_argument(
        "--expected-model",
        default=DEFAULT_MODEL,
        help="日志中必须出现的实际模型；不一致时立即停止，避免污染评测批次",
    )
    parser.add_argument("--app-name", default="Chat2DB Pro")
    parser.add_argument("--new-chat-x-ratio", type=float, default=0.113)
    parser.add_argument("--new-chat-y-ratio", type=float, default=0.063)
    parser.add_argument("--input-x-ratio", type=float, default=0.58)
    parser.add_argument("--input-y-ratio", type=float, default=0.575)
    parser.add_argument(
        "--stop-on-product-error",
        action="store_true",
        help="模型未生成可执行SQL时停止；默认记录失败并继续下一题",
    )
    parser.add_argument(
        "--inspect-latest",
        action="store_true",
        help="不操作界面，只解析日志中最近一次完整提问",
    )
    return parser.parse_args()


def load_questions(path: Path) -> list[tuple[str, str]]:
    questions: list[tuple[str, str]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split("\t", 1)
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise ValueError(f"问题文件第 {line_number} 行格式错误")
        questions.append((parts[0].strip(), parts[1].strip()))
    return questions


def parse_json_after(line: str, marker: str) -> dict[str, Any] | None:
    if marker not in line:
        return None
    candidate = line.split(marker, 1)[1].strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def normalize_tool_content(value: Any) -> str:
    text = str(value or "")
    if text.startswith('"'):
        try:
            decoded = json.loads(text)
            if isinstance(decoded, str):
                return decoded
        except json.JSONDecodeError:
            pass
    return text


def stream_events(segment: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in segment.splitlines():
        marker_at = line.find("data: ")
        if marker_at < 0:
            continue
        payload = line[marker_at + len("data: ") :].strip()
        if payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def parse_capture(segment: str) -> dict[str, Any]:
    lines = segment.splitlines()
    start_match = TIMESTAMP.match(lines[0]) if lines else None
    end_line = next((line for line in reversed(lines) if CHAT_COMPLETE in line), "")
    end_match = TIMESTAMP.match(end_line)
    if not start_match or not end_match:
        raise ValueError("日志片段缺少开始或完成时间")
    started = datetime.strptime(start_match.group(1), "%Y-%m-%d %H:%M:%S.%f")
    completed = datetime.strptime(end_match.group(1), "%Y-%m-%d %H:%M:%S.%f")

    request_payload: dict[str, Any] = {}
    execute_results: list[str] = []
    for line in lines:
        payload = parse_json_after(line, "ai upstream request payload:")
        if payload and not request_payload:
            request_payload = payload
        body = parse_json_after(line, "Original Request Body:")
        if not body:
            continue
        for message in body.get("messages") or []:
            if message.get("role") == "tool" and message.get("name") == "execute_sql":
                execute_results.append(normalize_tool_content(message.get("content")))

    streams: dict[str, dict[str, Any]] = {}
    stream_order: list[str] = []
    for event in stream_events(segment):
        stream_id = str(event.get("id") or "")
        if not stream_id:
            continue
        if stream_id not in streams:
            streams[stream_id] = {
                "model": event.get("model"),
                "content": [],
                "tool_calls": {},
                "usage": None,
                "finished": None,
            }
            stream_order.append(stream_id)
        stream = streams[stream_id]
        if event.get("usage"):
            stream["usage"] = event["usage"]
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                stream["content"].append(delta["content"])
            for tool_delta in delta.get("tool_calls") or []:
                index = int(tool_delta.get("index", 0))
                call = stream["tool_calls"].setdefault(
                    index, {"id": "", "name": "", "arguments": ""}
                )
                if tool_delta.get("id"):
                    call["id"] = tool_delta["id"]
                function = tool_delta.get("function") or {}
                if function.get("name"):
                    call["name"] = function["name"]
                if function.get("arguments"):
                    call["arguments"] += function["arguments"]
            if choice.get("finish_reason"):
                stream["finished"] = choice["finish_reason"]

    sql_attempts: list[dict[str, Any]] = []
    for stream_id in stream_order:
        for call in streams[stream_id]["tool_calls"].values():
            if call["name"] != "execute_sql":
                continue
            try:
                arguments = json.loads(call["arguments"])
            except json.JSONDecodeError:
                arguments = {}
            sql_attempts.append(
                {
                    "stream_id": stream_id,
                    "tool_call_id": call["id"],
                    "sql": arguments.get("sql"),
                    "database": arguments.get("databaseName"),
                }
            )

    final_answer = ""
    for stream_id in reversed(stream_order):
        content = "".join(streams[stream_id]["content"]).strip()
        if content:
            final_answer = content
            break

    generated_sql = sql_attempts[-1].get("sql") if sql_attempts else None
    if not generated_sql and final_answer:
        match = FENCED_SQL.search(final_answer)
        generated_sql = match.group(1).strip() if match else None

    prompt_tokens = completion_tokens = cached_tokens = 0
    for stream in streams.values():
        usage = stream.get("usage") or {}
        prompt_tokens += int(usage.get("prompt_tokens") or 0)
        completion_tokens += int(usage.get("completion_tokens") or 0)
        cached_tokens += int(
            (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        )

    result_text = execute_results[-1] if execute_results else ""
    success_match = re.search(r"\bsuccess:\s*(true|false)", result_text, re.I)
    duration_match = re.search(r"\bdurationMs:\s*([0-9.]+)", result_text)
    rows_match = re.search(r"\brows:\s*(\d+)", result_text)
    sql_success = success_match.group(1).lower() == "true" if success_match else None

    question = None
    messages = request_payload.get("messages") or []
    if messages:
        question = messages[-1].get("textPreview")
    metadata = {
        "session_id": request_payload.get("sessionId"),
        "history_size": request_payload.get("historySize"),
        "database": (request_payload.get("toolContext") or {}).get("databaseName"),
        "data_source_id": (request_payload.get("toolContext") or {}).get("dataSourceId"),
        "model": request_payload.get("model")
        or next((streams[item]["model"] for item in stream_order if streams[item]["model"]), None),
        "model_call_count": len(streams),
        "cached_tokens": cached_tokens,
        "sql_attempts": sql_attempts,
        "sql_result_rows": int(rows_match.group(1)) if rows_match else None,
    }
    status = "ok" if generated_sql and sql_success is True else "generation_error"
    if not generated_sql:
        status = "empty_sql"
    elif sql_success is False:
        status = "execution_error"

    return {
        "question": question,
        "generated_sql": generated_sql,
        "status": status,
        "latency_ms": round((completed - started).total_seconds() * 1000, 3),
        "sql_execution_ms": float(duration_match.group(1)) if duration_match else None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "raw_answer": final_answer or None,
        "error": None if status == "ok" else result_text or "未获得成功的 SQL 执行结果",
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "metadata": metadata,
    }


def latest_complete_segment(log_path: Path) -> str:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    complete_at = text.rfind(CHAT_COMPLETE)
    if complete_at < 0:
        raise ValueError("日志中没有完整的 AI 对话")
    start_at = text.rfind("\n", 0, text.rfind(CHAT_START, 0, complete_at))
    end_at = text.find("\n", complete_at)
    return text[start_at + 1 : end_at if end_at >= 0 else None]


def wait_for_capture(log_path: Path, offset: int, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    start_at: int | None = None
    while time.monotonic() < deadline:
        with log_path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read().decode("utf-8", errors="replace")
        if start_at is None:
            marker = chunk.find(CHAT_START)
            if marker >= 0:
                start_at = chunk.rfind("\n", 0, marker) + 1
        if start_at is not None:
            complete = chunk.find(CHAT_COMPLETE, start_at)
            if complete >= 0:
                end_at = chunk.find("\n", complete)
                return chunk[start_at : end_at if end_at >= 0 else None]
        time.sleep(0.25)
    raise TimeoutError(f"等待 Chat2DB 完成响应超时（{timeout:g} 秒）")


APPLE_SCRIPT = r'''
on run argv
    set appName to item 1 of argv
    tell application appName to activate
    delay 0.4
    tell application "System Events"
        tell process appName
            if (count of windows) is 0 then error "Chat2DB 没有可用窗口"
            set targetWindow to front window
            set value of attribute "AXMinimized" of targetWindow to false
            set frontmost to true
            set {windowX, windowY} to position of targetWindow
            set {windowWidth, windowHeight} to size of targetWindow
            return (windowX as string) & "," & (windowY as string) & "," & (windowWidth as string) & "," & (windowHeight as string)
        end tell
    end tell
end run
'''


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


def native_click(x: float, y: float) -> None:
    core_graphics = ctypes.CDLL(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    core_foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    core_graphics.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    core_graphics.CGEventCreateMouseEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        CGPoint,
        ctypes.c_uint32,
    ]
    core_graphics.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
    point = CGPoint(float(x), float(y))
    for event_type, delay in ((5, 0.08), (1, 0.05), (2, 0.0)):
        event = core_graphics.CGEventCreateMouseEvent(None, event_type, point, 0)
        if not event:
            raise RuntimeError("无法创建 macOS 鼠标事件")
        core_graphics.CGEventPost(0, event)
        core_foundation.CFRelease(event)
        if delay:
            time.sleep(delay)


def submit_question(args: argparse.Namespace, question: str) -> None:
    command = [
        "osascript",
        "-e",
        APPLE_SCRIPT,
        args.app_name,
    ]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=30)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "Chat2DB 界面操作失败")
    try:
        window_x, window_y, window_width, window_height = [
            float(value.strip()) for value in completed.stdout.strip().split(",")
        ]
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"无法读取 Chat2DB 窗口位置：{completed.stdout!r}") from exc

    native_click(
        window_x + window_width * args.new_chat_x_ratio,
        window_y + window_height * args.new_chat_y_ratio,
    )
    time.sleep(args.new_chat_delay)
    native_click(
        window_x + window_width * args.input_x_ratio,
        window_y + window_height * args.input_y_ratio,
    )
    subprocess.run(["pbcopy"], input=question, text=True, check=True, timeout=10)
    keypress = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "v" using {command down}',
            "-e",
            'delay 0.2',
            "-e",
            'tell application "System Events" to key code 36',
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    if keypress.returncode:
        raise RuntimeError(keypress.stderr.strip() or "无法粘贴并提交问题")


def load_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def main() -> int:
    args = parse_args()
    if args.inspect_latest:
        print(json.dumps(parse_capture(latest_complete_segment(args.log)), ensure_ascii=False, indent=2))
        return 0
    if sys.platform != "darwin":
        raise RuntimeError("Chat2DB 桌面自动化脚本目前仅支持 macOS")
    if not args.log.exists():
        raise FileNotFoundError(f"找不到 Chat2DB 日志：{args.log}")

    questions = load_questions(args.questions)
    if len(questions) != 50:
        raise ValueError(f"问题文件必须包含50题，实际为{len(questions)}题")
    if args.case:
        selected = set(args.case)
        questions = [item for item in questions if item[0] in selected]
        missing = selected - {item[0] for item in questions}
        if missing:
            raise ValueError(f"不存在的题号：{', '.join(sorted(missing))}")

    run_dir = args.output_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = run_dir / "predictions.jsonl"
    replaced_path = run_dir / "replaced_predictions.jsonl"
    run_path = run_dir / "run.json"
    existing = load_existing(predictions_path)
    invalid_collection = [
        item
        for item in existing
        if item.get("status") in {"collector_error", "context_error"}
    ]
    if invalid_collection:
        recovered_at = datetime.now().astimezone().isoformat()
        collection_errors_path = run_dir / "collection_errors.jsonl"
        for item in invalid_collection:
            archived = dict(item)
            archived["archived_at"] = recovered_at
            archived["archive_reason"] = "invalid_collection_must_be_recollected"
            append_jsonl(collection_errors_path, archived)
        existing = [item for item in existing if item not in invalid_collection]
        predictions_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in existing),
            encoding="utf-8",
        )
    force_cases = set(args.force_case)
    unknown_force_cases = force_cases - {item[0] for item in load_questions(args.questions)}
    if unknown_force_cases:
        raise ValueError(f"不存在的强制重跑题号：{', '.join(sorted(unknown_force_cases))}")
    if force_cases:
        repeat_indexes = set(range(args.repeat_start, args.repeat_start + args.repeats))
        replaced = [
            item
            for item in existing
            if str(item["question_id"]) in force_cases
            and int(item.get("repeat_index") or 1) in repeat_indexes
        ]
        if replaced:
            replaced_at = datetime.now().astimezone().isoformat()
            for item in replaced:
                archived = dict(item)
                archived["replaced_at"] = replaced_at
                archived["replacement_reason"] = "forced_rerun"
                append_jsonl(replaced_path, archived)
            existing = [item for item in existing if item not in replaced]
            predictions_path.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in existing),
                encoding="utf-8",
            )
    completed_keys = {
        (str(item["question_id"]), int(item.get("repeat_index") or 1))
        for item in existing
    }
    if run_path.exists():
        run_info = json.loads(run_path.read_text(encoding="utf-8"))
        if (
            run_info.get("database") != args.database
            or int(run_info.get("repeats") or 0) != args.repeats
            or int(run_info.get("repeat_start") or 1) != args.repeat_start
            or run_info.get("expected_model", args.expected_model) != args.expected_model
        ):
            raise ValueError(
                "续跑时的数据库、repeats和repeat-start必须与原run.json一致"
            )
        run_info.pop("completed_at", None)
        run_info["resumed_at"] = datetime.now().astimezone().isoformat()
    else:
        run_info = {
            "run_id": args.run_id,
            "product": "chat2db",
            "product_version": "5.3.0",
            "benchmark_id": "enron_golden50_v1",
            "database": args.database,
            "expected_model": args.expected_model,
            "repeats": args.repeats,
            "repeat_start": args.repeat_start,
            "repeat_end": args.repeat_start + args.repeats - 1,
            "collection_mode": "macos_ui_plus_application_log",
            "started_at": datetime.now().astimezone().isoformat(),
            "predictions_file": str(predictions_path.relative_to(PROJECT_ROOT)),
        }
    run_info["record_count"] = len(existing)
    run_path.write_text(json.dumps(run_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total = len(questions) * args.repeats
    sequence = 0
    for repeat_index in range(args.repeat_start, args.repeat_start + args.repeats):
        for question_id, question in questions:
            sequence += 1
            key = (question_id, repeat_index)
            if key in completed_keys:
                print(f"[{sequence:03d}/{total}] {question_id} R{repeat_index} SKIP", flush=True)
                continue
            offset = args.log.stat().st_size
            try:
                submit_question(args, question)
                capture = wait_for_capture(args.log, offset, args.timeout)
                result = parse_capture(capture)
                metadata = result.setdefault("metadata", {})
                metadata["collector"] = "chat2db_desktop_log_v1"
                if metadata.get("model") and not run_info.get("model"):
                    run_info["model"] = metadata["model"]
                if metadata.get("data_source_id") and not run_info.get("data_source_id"):
                    run_info["data_source_id"] = metadata["data_source_id"]
                context_error = None
                if metadata.get("history_size") != 0:
                    context_error = f"新对话历史应为0，实际为{metadata.get('history_size')}"
                elif metadata.get("database") != args.database:
                    context_error = (
                        f"数据库上下文应为{args.database}，实际为{metadata.get('database')}"
                    )
                elif metadata.get("model") != args.expected_model:
                    context_error = (
                        f"运行模型应为{args.expected_model}，实际为{metadata.get('model')}"
                    )
                record = {
                    "question_id": question_id,
                    "question": question,
                    "repeat_index": repeat_index,
                    **result,
                }
                if context_error:
                    record["status"] = "context_error"
                    record["error"] = context_error
                append_jsonl(predictions_path, record)
                completed_keys.add(key)
                run_info["record_count"] = len(load_existing(predictions_path))
                run_info["last_updated_at"] = datetime.now().astimezone().isoformat()
                run_path.write_text(
                    json.dumps(run_info, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(
                    f"[{sequence:03d}/{total}] {question_id} R{repeat_index} "
                    f"{record['status']} {record['latency_ms'] / 1000:.3f}s "
                    f"tokens={record['total_tokens']}",
                    flush=True,
                )
                if context_error:
                    raise RuntimeError(context_error)
                if record["status"] != "ok" and args.stop_on_product_error:
                    raise RuntimeError(record["error"] or record["status"])
            except Exception as exc:
                if key not in completed_keys:
                    append_jsonl(
                        predictions_path,
                        {
                            "question_id": question_id,
                            "question": question,
                            "repeat_index": repeat_index,
                            "generated_sql": None,
                            "status": "collector_error",
                            "latency_ms": None,
                            "sql_execution_ms": None,
                            "prompt_tokens": None,
                            "completion_tokens": None,
                            "total_tokens": None,
                            "raw_answer": None,
                            "error": str(exc),
                            "completed_at": datetime.now().astimezone().isoformat(),
                            "metadata": {"collector": "chat2db_desktop_log_v1"},
                        },
                    )
                print(f"停止：{question_id} R{repeat_index}: {exc}", file=sys.stderr)
                return 2
            time.sleep(args.cooldown)

    run_info["completed_at"] = datetime.now().astimezone().isoformat()
    run_info["record_count"] = len(load_existing(predictions_path))
    run_path.write_text(json.dumps(run_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"完成：{predictions_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
