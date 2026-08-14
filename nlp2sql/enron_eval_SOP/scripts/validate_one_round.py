#!/usr/bin/env python3
"""验证一轮采集是否完整，不把产品失败误当作采集缺失。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "benchmark/questions/user/questions_enron_50_user_mix.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证一个产品的一轮50题产物")
    parser.add_argument("--product", required=True, choices=("chat2db", "wren", "moi"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-model", default="qwen3.7-plus-2026-05-26")
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--wren-config", type=Path)
    parser.add_argument(
        "--repeat-index",
        type=int,
        default=1,
        help="验证多轮历史文件中的指定轮次；正式单轮产物使用默认值1",
    )
    return parser.parse_args()


def read_questions(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        question_id, question = raw.split("\t", 1)
        result[question_id.strip()] = question.strip()
    if len(result) != 50:
        raise AssertionError(f"正式问题集应为50题，实际为{len(result)}题")
    return result


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percent": round(numerator * 100 / denominator, 2) if denominator else 0,
    }


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    predictions_path = run_dir / "predictions.jsonl"
    run_path = run_dir / "run.json"
    if not predictions_path.exists() or not run_path.exists():
        raise FileNotFoundError("运行目录必须同时包含predictions.jsonl和run.json")

    questions = read_questions(args.questions)
    records = read_jsonl(predictions_path)
    records = [
        item
        for item in records
        if int(item.get("repeat_index") or 0) == args.repeat_index
    ]
    if len(records) != 50:
        raise AssertionError(
            f"指定轮次必须有50条记录，实际为{len(records)}条"
        )

    keys = [(str(item.get("question_id")), int(item.get("repeat_index") or 0)) for item in records]
    if len(set(keys)) != 50:
        raise AssertionError("题号和轮次存在重复")
    if set(keys) != {(question_id, args.repeat_index) for question_id in questions}:
        raise AssertionError("记录未完整覆盖指定轮次的50题")

    model_mismatches: list[str] = []
    for record in records:
        question_id = str(record["question_id"])
        if record.get("question") != questions[question_id]:
            raise AssertionError(f"{question_id}的问题文本与冻结题集不一致")
        if "status" not in record or "generated_sql" not in record:
            raise AssertionError(f"{question_id}缺少status或generated_sql")
        latency = record.get("latency_ms")
        if latency is not None and (not isinstance(latency, (int, float)) or latency < 0):
            raise AssertionError(f"{question_id}的latency_ms无效")
        metadata = record.get("metadata") or {}
        observed_model = metadata.get("model")
        if observed_model and observed_model != args.expected_model:
            model_mismatches.append(f"{question_id}:{observed_model}")
        if args.product == "moi":
            for field in ("native_execution_success", "native_query_results", "selected_native_results"):
                if field not in record:
                    raise AssertionError(f"{question_id}缺少MOI原生字段{field}")
    if model_mismatches:
        raise AssertionError(f"发现非统一模型记录：{model_mismatches[:5]}")

    run_info = json.loads(run_path.read_text(encoding="utf-8"))
    declared_model = run_info.get("model") or run_info.get("expected_model")
    if declared_model != args.expected_model:
        raise AssertionError(f"run.json模型为{declared_model}，应为{args.expected_model}")
    if args.product == "wren":
        if not args.wren_config:
            raise AssertionError("Wren验证必须提供实际使用的--wren-config")
        required = f"model: openai/{args.expected_model}"
        if required not in args.wren_config.read_text(encoding="utf-8"):
            raise AssertionError(f"Wren配置未包含统一模型：{required}")

    status_counts = Counter(str(item.get("status") or "unknown") for item in records)
    invalid_collection_statuses = {"collector_error", "context_error"}
    if invalid_collection_statuses & set(status_counts):
        raise AssertionError(
            "本轮包含采集器或上下文错误，必须修复后重新采集对应题目"
        )
    sql_generated = sum(bool(str(item.get("generated_sql") or "").strip()) for item in records)
    native_success = (
        sum(item.get("native_execution_success") is True for item in records)
        if args.product == "moi"
        else None
    )
    tokens_available = sum(isinstance(item.get("total_tokens"), int) for item in records)
    report = {
        "validation": "passed",
        "validated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "product": args.product,
        "run_id": run_info.get("run_id"),
        "benchmark_id": "enron_golden50_v1",
        "expected_model": args.expected_model,
        "attempts": 50,
        "repeat_index": args.repeat_index,
        "question_coverage": rate(50, 50),
        "sql_generated": rate(sql_generated, 50),
        "native_execution_success": rate(native_success, 50) if native_success is not None else None,
        "token_records_available": rate(tokens_available, 50),
        "status_counts": dict(sorted(status_counts.items())),
        "model_evidence": (
            "application_log" if args.product == "chat2db"
            else "moi_llm_events_and_session" if args.product == "moi"
            else "runner_declaration_plus_required_wren_private_config_check"
        ),
        "note": "产品生成失败可以保留；缺题、重复题、上下文污染或模型不一致不能通过。",
    }
    output = run_dir / "validation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"验证通过：{args.product} 一轮50题，生成SQL {sql_generated}/50")
    print(f"验证报告：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
