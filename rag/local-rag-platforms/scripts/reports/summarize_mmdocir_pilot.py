#!/usr/bin/env python3
"""Build a reproducible MOI-vs-Dify summary for the single 50-question pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def dify_metrics(metrics_path: Path, results_path: Path) -> dict[str, Any]:
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    rows = read_jsonl(results_path)
    retrieval_rows = [row.get("retrieval", {}) for row in rows if row.get("retrieval", {}).get("status") in {"success", "empty"}]
    native_rows = [row.get("native", {}) for row in rows if row.get("native", {}).get("status") == "success"]
    page_fraction: dict[str, float | None] = {}
    for k in (1, 3, 5, 10):
        values = []
        for row in retrieval_rows:
            field = f"page_fraction_recall_at_{k}"
            if field in row:
                values.append(float(row[field]))
                continue
            gold = {tuple(item) for item in row.get("gold_pages", [])}
            found = {
                tuple(marker)
                for hit in row.get("marker_hits", [])[:k]
                for marker in hit
            }
            values.append(len(gold.intersection(found)) / len(gold) if gold else 0.0)
        page_fraction[str(k)] = mean(values)
    return {
        "questions": len(rows),
        "retrieval_success": sum(bool(row.get("retrieval", {}).get("status") == "success") for row in rows),
        "retrieval_nonempty_rate": metrics.get("retrieval_nonempty_rate"),
        "page_fraction_recall_at_k": page_fraction,
        "native_success": sum(bool(row.get("native", {}).get("status") == "success") for row in rows),
        "native_answer_contains_gold_count": sum(bool(row.get("answer_contains_gold")) for row in native_rows),
        "native_answer_contains_gold_rate": mean([1.0 if row.get("answer_contains_gold") else 0.0 for row in native_rows]),
        "native_answer_exact_match_normalized_count": sum(bool(row.get("answer_exact_match_normalized")) for row in native_rows),
        "native_answer_exact_match_normalized_rate": mean([1.0 if row.get("answer_exact_match_normalized") else 0.0 for row in native_rows]),
        "document_recall_at_k": {
            str(k): metrics.get(f"document_recall_at_{k}")
            for k in (1, 3, 5)
        },
        "index_state": metrics.get("index_state"),
        "dataset_id": metrics.get("dataset_id"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moi-summary", type=Path, required=True)
    parser.add_argument("--moi-ledger", type=Path, required=True)
    parser.add_argument("--dify-metrics", type=Path, required=True)
    parser.add_argument("--dify-results", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    moi_summary = json.loads(args.moi_summary.read_text(encoding="utf-8"))
    moi_rows = read_jsonl(args.moi_ledger)
    dify = dify_metrics(args.dify_metrics, args.dify_results)
    report = {
        "schema": "mmdocir-moi-dify-pilot-comparison-v1",
        "scope": {
            "questions": 50,
            "documents": 9,
            "question_selection": "official MMDocIR questions with query_index 0-49",
            "condition": "page",
            "comparison_type": "adapted product-boundary comparison",
        },
        "moi": {
            "questions": moi_summary.get("attempts"),
            "retrieval_success": moi_summary.get("successful_attempts"),
            "retrieval_nonempty_rate": (moi_summary.get("successful_attempts", 0) / moi_summary["attempts"] if moi_summary.get("attempts") else None),
            "page_fraction_recall_at_k": moi_summary.get("mean_page_recall_at_k"),
            "answer_contains_gold_count": moi_summary.get("answer_contains_gold_count"),
            "answer_contains_gold_rate": moi_summary.get("answer_contains_gold_rate"),
            "answer_exact_match_normalized_count": moi_summary.get("answer_exact_match_normalized_count"),
            "answer_exact_match_normalized_rate": moi_summary.get("answer_exact_match_normalized_rate"),
            "generation_model": moi_rows[0].get("generation_model") if moi_rows else None,
            "embedding_model": moi_rows[0].get("embedding_model") if moi_rows else None,
        },
        "dify_local": dify,
        "notes": [
            "Dify native QA was temporarily bound to the run dataset and restored afterward; all 50 native responses referenced the run dataset.",
            "MOI uses the official document-local dense retrieval protocol; Dify queries the same 9-document pilot corpus through its product API.",
            "MOI generation used qwen3.6-flash; the configured Dify app used deepseek-v4-flash, so answer rates are an end-to-end pilot comparison rather than a generator-controlled ablation.",
            "FastGPT was not included because its local service was not running/configured for this pilot.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = [
        ("Page fraction recall @1", report["moi"]["page_fraction_recall_at_k"].get("1"), report["dify_local"]["page_fraction_recall_at_k"].get("1")),
        ("Page fraction recall @3", report["moi"]["page_fraction_recall_at_k"].get("3"), report["dify_local"]["page_fraction_recall_at_k"].get("3")),
        ("Page fraction recall @5", report["moi"]["page_fraction_recall_at_k"].get("5"), report["dify_local"]["page_fraction_recall_at_k"].get("5")),
        ("Page fraction recall @10", report["moi"]["page_fraction_recall_at_k"].get("10"), report["dify_local"]["page_fraction_recall_at_k"].get("10")),
        ("Answer contains gold", report["moi"]["answer_contains_gold_rate"], report["dify_local"]["native_answer_contains_gold_rate"]),
        ("Normalized exact match", report["moi"]["answer_exact_match_normalized_rate"], report["dify_local"]["native_answer_exact_match_normalized_rate"]),
    ]
    def fmt(value: Any) -> str:
        return "n/a" if value is None else f"{float(value):.4f}"
    markdown = [
        "# MMDocIR 50 题 pilot：MOI vs Dify Local",
        "",
        "- 样本：官方 MMDocIR 前 50 题，涉及 9 个文档；page condition。",
        "- 检索指标：gold page 集合在 Top-K 中被覆盖的平均比例。",
        "- 答案指标：统一标准化后，生成答案是否包含参考答案；exact match 为标准化字符串完全相等。",
        "",
        "| 指标 | MOI | Dify Local |",
        "|---|---:|---:|",
    ]
    markdown.extend(f"| {name} | {fmt(moi)} | {fmt(dify)} |" for name, moi, dify in rows)
    markdown.extend([
        "",
        "## 口径说明",
        "",
        *[f"- {note}" for note in report["notes"]],
        "",
        f"原始 MOI 汇总：`{args.moi_summary}`；原始 Dify 指标：`{args.dify_metrics}`。",
    ])
    args.output_md.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
