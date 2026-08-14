#!/usr/bin/env python3
"""Combine automatic passes with human verdicts and publish adjusted scores."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS_PATH = PROJECT_ROOT / "results/human_review/annotations.json"
JSON_OUTPUT = PROJECT_ROOT / "results/human_review/product_scores.json"
MARKDOWN_OUTPUT = PROJECT_ROOT / "results/human_review/product_scores.md"
EVALUATIONS = {
    "moi": PROJECT_ROOT
    / "products/moi/results/automated/moi_qwen37_no_semantic_20260811_r3/evaluation_native.json",
    "wren": PROJECT_ROOT
    / "products/wren/results/automated/wren_qwen37_20260810_r3/evaluation.json",
}
CASE_PREFIX = re.compile(r"^(e\d{2}|m\d{2}|h\d{2})")
VERDICT_SCORE = {"full": 1.0, "partial": 0.5, "incorrect": 0.0}
VERIFIED_SQL_SUCCESS = {"wren:m14:r1"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ratio(numerator: float, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percent": round(numerator / denominator * 100, 2) if denominator else None,
    }


def case_key(case_id: str) -> str:
    match = CASE_PREFIX.match(case_id)
    if not match:
        raise ValueError(f"无法识别题号：{case_id}")
    return match.group(1)


def calculate_product(
    product: str,
    report: dict[str, Any],
    annotations: dict[str, Any],
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    missing: list[str] = []

    for record in report["records"]:
        short_id = case_key(record["case_id"])
        annotation_key = f"{product}:{short_id}:r{record['repeat_index']}"
        if record.get("execution_correct"):
            verdict = "automatic_full"
            score = 1.0
        else:
            annotation = annotations.get(annotation_key)
            if not annotation or annotation.get("verdict") not in VERDICT_SCORE:
                missing.append(annotation_key)
                continue
            verdict = annotation["verdict"]
            score = VERDICT_SCORE[verdict]
        scored.append(
            {
                "case_id": short_id,
                "repeat_index": int(record["repeat_index"]),
                "difficulty": record["difficulty"],
                "verdict": verdict,
                "score": score,
            }
        )

    if missing:
        raise ValueError(f"{product} 仍有未审核题次：{', '.join(missing)}")

    total = len(scored)
    weighted = sum(item["score"] for item in scored)
    strict = sum(item["score"] == 1 for item in scored)
    verdict_counts = {
        verdict: sum(item["verdict"] == verdict for item in scored)
        for verdict in ("automatic_full", "full", "partial", "incorrect")
    }

    by_round: dict[str, Any] = {}
    for repeat_index in (1, 2, 3):
        selected = [item for item in scored if item["repeat_index"] == repeat_index]
        by_round[str(repeat_index)] = {
            "weighted_correctness": ratio(sum(item["score"] for item in selected), len(selected)),
            "strict_correctness": ratio(sum(item["score"] == 1 for item in selected), len(selected)),
        }

    by_difficulty: dict[str, Any] = {}
    for difficulty in ("easy", "medium", "hard"):
        selected = [item for item in scored if item["difficulty"] == difficulty]
        by_difficulty[difficulty] = {
            "weighted_correctness": ratio(sum(item["score"] for item in selected), len(selected)),
            "strict_correctness": ratio(sum(item["score"] == 1 for item in selected), len(selected)),
        }

    questions = sorted({item["case_id"] for item in scored})
    repeat_full = sum(
        all(item["score"] == 1 for item in scored if item["case_id"] == question)
        for question in questions
    )

    automatic_metrics = report.get("metrics") or {}
    original_sql_success = automatic_metrics.get("sql_success_rate") or {}
    verified_sql_success = int(original_sql_success.get("numerator") or 0) + sum(
        1
        for key in VERIFIED_SQL_SUCCESS
        if key.startswith(f"{product}:")
    )
    return {
        "run_id": report.get("run_id"),
        "attempts": total,
        "questions": len(questions),
        "verdict_counts": verdict_counts,
        "automatic_execution_accuracy": automatic_metrics.get("execution_accuracy"),
        "human_adjusted_weighted_correctness": ratio(weighted, total),
        "human_adjusted_strict_correctness": ratio(strict, total),
        "human_adjusted_repeat_correct_rate": ratio(repeat_full, len(questions)),
        "human_verified_sql_success_rate": ratio(verified_sql_success, total),
        "by_round": by_round,
        "by_difficulty": by_difficulty,
        "operational_metrics_unchanged": {
            "sql_success_rate": automatic_metrics.get("sql_success_rate"),
            "end_to_end_latency_ms": automatic_metrics.get("end_to_end_latency_ms"),
            "token_usage": automatic_metrics.get("token_usage"),
        },
    }


def markdown(report: dict[str, Any]) -> str:
    rows = []
    for product, item in report["products"].items():
        auto = item["automatic_execution_accuracy"]
        weighted = item["human_adjusted_weighted_correctness"]
        strict = item["human_adjusted_strict_correctness"]
        repeat = item["human_adjusted_repeat_correct_rate"]
        sql_success = item["operational_metrics_unchanged"]["sql_success_rate"]
        verified_sql_success = item["human_verified_sql_success_rate"]
        rows.append(
            f"| {product.upper()} | {auto['numerator']}/{auto['denominator']} "
            f"({auto['percent']:.2f}%) | {weighted['numerator']:g}/{weighted['denominator']} "
            f"({weighted['percent']:.2f}%) | {strict['numerator']}/{strict['denominator']} "
            f"({strict['percent']:.2f}%) | {repeat['numerator']}/{repeat['denominator']} "
            f"({repeat['percent']:.2f}%) | {sql_success['numerator']}/{sql_success['denominator']} "
            f"({sql_success['percent']:.2f}%) | {verified_sql_success['numerator']}/"
            f"{verified_sql_success['denominator']} ({verified_sql_success['percent']:.2f}%) |"
        )

    details = []
    for product, item in report["products"].items():
        counts = item["verdict_counts"]
        difficulty = item["by_difficulty"]
        rounds = item["by_round"]
        details.extend(
            [
                f"## {product.upper()}",
                "",
                f"- 自动正确：{counts['automatic_full']}题次",
                f"- 自动判错后人工改判完全正确：{counts['full']}题次",
                f"- 部分正确：{counts['partial']}题次",
                f"- 错误：{counts['incorrect']}题次",
                "- 三轮加权正确率："
                + "，".join(
                    f"第{round_id}轮 {value['weighted_correctness']['percent']:.2f}%"
                    for round_id, value in rounds.items()
                ),
                "- 难度加权正确率："
                + "，".join(
                    f"{name} {value['weighted_correctness']['percent']:.2f}%"
                    for name, value in difficulty.items()
                ),
                "",
            ]
        )

    return "\n".join(
        [
            "# Enron NL2SQL 人工审核后产品得分",
            "",
            f"> 标注更新时间：{report['annotations_updated_at']}",
            "",
            "计分：完全正确1分，部分正确0.5分，错误0分；自动判定正确且未进入人工审核的题次按1分计。",
            "",
            "| 产品 | 原始自动准确率 | 人工加权正确率 | 人工严格正确率 | 三轮全部正确率 | 原始SQL成功率 | 核验后SQL成功率 |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *rows,
            "",
            "说明：人工审核只调整答案正确性。核验后SQL成功率仅修正已在MySQL直接验证可执行、但被安全规则误拦截的Wren m14第一轮；时延和Token仍采用原始运行记录。",
            "",
            *details,
        ]
    )


def main() -> None:
    annotations_document = read_json(ANNOTATIONS_PATH)
    annotations = annotations_document.get("annotations") or {}
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "annotations_updated_at": annotations_document.get("updated_at"),
        "scoring": {"full": 1, "partial": 0.5, "incorrect": 0},
        "products": {
            product: calculate_product(product, read_json(path), annotations)
            for product, path in EVALUATIONS.items()
        },
    }
    JSON_OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MARKDOWN_OUTPUT.write_text(markdown(result) + "\n", encoding="utf-8")
    print(MARKDOWN_OUTPUT)


if __name__ == "__main__":
    main()
