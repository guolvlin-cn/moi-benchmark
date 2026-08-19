#!/usr/bin/env python3
"""Write a completed current-corpus MOI run into the matching TODO Results rows."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(value: Any) -> str:
    return "—" if value is None else f"{100 * float(value):.2f}%"


def num(value: Any, digits: int = 4) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"


def latency_pair(metrics: dict[str, Any]) -> str:
    latency = (metrics.get("retrieval") or {}).get("retrieval_latency_ms") or metrics.get("latency_ms") or {}
    if latency.get("p50") is None or latency.get("p95") is None:
        return "—"
    return f"{float(latency['p50']):.2f}/{float(latency['p95']):.2f} ms"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[max(0, min(len(values) - 1, math.ceil(len(values) * fraction) - 1))]


def e2e_pair(run: Path, dataset: str) -> str:
    path = run / "datasets" / dataset / "combined-results.jsonl"
    if not path.is_file():
        return "—"
    values = []
    for row in read_jsonl(path):
        if row.get("status") != "ok":
            continue
        values.append(float(row.get("retrieval_latency_ms") or 0) + float(row.get("generation_latency_ms") or 0))
    p50, p95 = percentile(values, .5), percentile(values, .95)
    return "—" if p50 is None or p95 is None else f"{p50:.2f}/{p95:.2f} ms"


def mmdocrag_text_recall_at_5(run: Path) -> tuple[float | None, int]:
    path = run / "datasets" / "mmdocrag" / "combined-results.jsonl"
    if not path.is_file():
        return None, 0
    values = []
    for row in read_jsonl(path):
        if row.get("status") != "ok":
            continue
        gold = ["".join(str(item.get("text") or "").lower().split()) for item in ((row.get("case") or {}).get("metadata") or {}).get("gold_text_quotes", []) if item.get("text")]
        if not gold:
            continue
        chunks = ["".join(str(item.get("content") or "").lower().split()) for item in (row.get("chunks") or [])[:5]]
        values.append(sum(any(quote in chunk for chunk in chunks) for quote in gold) / len(gold))
    return (sum(values) / len(values) if values else None), len(values)


def docbench_grouped_correctness(run: Path) -> dict[str, float | None]:
    results_path = run / "datasets" / "docbench" / "combined-results.jsonl"
    judge_path = run / "datasets" / "docbench" / "judgements.jsonl"
    if not results_path.is_file() or not judge_path.is_file():
        return {}
    types = {str((row.get("case") or {}).get("id")): str(((row.get("case") or {}).get("metadata") or {}).get("question_type") or "") for row in read_jsonl(results_path)}
    groups: dict[str, list[int]] = {"text-only": [], "multimodal": [], "metadata": [], "unanswerable": []}
    for row in read_jsonl(judge_path):
        if not isinstance(row.get("score"), int):
            continue
        raw_type = types.get(str(row.get("id")), "")
        if raw_type == "text-only":
            group = "text-only"
        elif raw_type in {"multimodal-t", "multimodal-f"}:
            group = "multimodal"
        elif raw_type == "meta-data":
            group = "metadata"
        elif raw_type in {"unanswerable", "una-web"}:
            group = "unanswerable"
        else:
            continue
        groups[group].append(int(row["score"]))
    return {name: (sum(values) / len(values) if values else None) for name, values in groups.items()}


def replace_moi_row(text: str, heading: str, row: str) -> str:
    start = text.find(heading)
    if start < 0:
        raise RuntimeError(f"TODO heading not found: {heading}")
    row_start = text.find("| MOI |", start)
    if row_start < 0:
        raise RuntimeError(f"MOI row not found after: {heading}")
    row_end = text.find("\n", row_start)
    return text[:row_start] + row + text[row_end:]


def update(run: Path, todo: Path) -> None:
    state = read_json(run / "state.json")
    if state.get("status") != "succeeded":
        raise RuntimeError(f"run is not complete: {state.get('status')}")
    aggregate = read_json(run / "aggregated-metrics.json")
    text = todo.read_text(encoding="utf-8")
    run_id = run.name

    mm = aggregate["mmdocrag"]
    mm_recall5, mm_recall_n = mmdocrag_text_recall_at_5(run)
    text = replace_moi_row(text, "**实验 4：MMDocRAG 多模态证据检索。**",
        f"| MOI | {pct(mm_recall5)} | — | N/A（无 image trace） | N/A（无 image trace） | — | {latency_pair(mm)} | `CURRENT_CORPUS_ADAPTED`, `TEXT_ONLY`; {mm_recall_n}/1,504 有 text Gold；run `{run_id}` |")
    answer = mm.get("answer") or {}
    quote = answer.get("quote_selection") or {}
    judge = mm.get("judge") or {}
    text = replace_moi_row(text, "**实验 5：MMDocRAG Quote Selection 与回答质量。**",
        f"| MOI | {num(quote.get('text_precision_adapted'))} | {num(quote.get('text_recall_adapted'))} | {num(quote.get('text_f1_adapted'))} | {num(quote.get('text_f1_adapted'))} | N/A（无 image trace） | {num(answer.get('bleu_1_adapted'))} | {num(answer.get('rouge_l'))} | {num(judge.get('average'))} | `CURRENT_CORPUS_ADAPTED`, `TEXT_ONLY`; run `{run_id}` |")

    doc = aggregate["docbench"]
    correctness = doc.get("correctness") or {}
    by_type = docbench_grouped_correctness(run)
    availability = (doc.get("retrieval") or {}).get("initial_availability")
    text = replace_moi_row(text, "**实验 6：DocBench 原始 PDF 端到端回答。**",
        f"| MOI | {pct(correctness.get('correctness'))} | {pct(by_type.get('text-only'))} | {pct(by_type.get('multimodal'))} | {pct(by_type.get('metadata'))} | {pct(by_type.get('unanswerable'))} | {pct(availability)} | {e2e_pair(run, 'docbench')} | `CURRENT_CORPUS_ADAPTED`, `TEXT_ONLY`; 188 文档/906 题；run `{run_id}` |")

    ent = aggregate["enterpriserag-bench"]
    slices = ent.get("question_type_slices") or {}
    text = replace_moi_row(text, "**实验 9：Enterprise-Bench 企业检索。**",
        f"| MOI | {pct(ent.get('doc_recall_at_10'))} | {pct(ent.get('complete_evidence_set_recall_at_10'))} | {num(ent.get('invalid_extra_docs'), 2)} | {pct(slices.get('semantic'))} | {pct(slices.get('conflicting_info'))} | {pct(ent.get('strict_unanswerable_success'))} | {latency_pair(ent)} | `CURRENT_CORPUS_ADAPTED`; 722 文档/500 题；run `{run_id}` |")
    text = replace_moi_row(text, "**实验 10：Enterprise-Bench 端到端企业问答。**",
        f"| MOI | — | — | — | {pct(ent.get('strict_unanswerable_success'))} | — | {pct(ent.get('availability'))} | {e2e_pair(run, 'enterpriserag-bench')} | `CURRENT_CORPUS_ADAPTED`; official correctness/completeness judge unavailable；run `{run_id}` |")

    fab = aggregate["fab-bench"]
    text = replace_moi_row(text, "**实验 11：FAB-Bench 六维质量。**",
        f"| MOI | — | — | — | — | — | — | — | {e2e_pair(run, 'fab-bench')} | `CURRENT_CORPUS_ADAPTED`; 六维 G-Eval scorer unavailable；objective accuracy={pct((fab.get('objective_accuracy') or {}).get('accuracy'))}；run `{run_id}` |")
    text = replace_moi_row(text, "**实验 12：FAB-Bench Context Scaling。**",
        f"| MOI | — | — | — | — | — | — | — | — | `N/A: NOT_RUN`; 本轮仅固定 Top-10 current-corpus 条件；run `{run_id}` |")

    todo.write_text(text, encoding="utf-8")
    (run / "todo-update.json").write_text(json.dumps({"todo": str(todo), "run_id": run_id, "updated": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--todo", type=Path, default=ROOT / "TODO.md")
    args = parser.parse_args()
    update(args.run.resolve(), args.todo.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
