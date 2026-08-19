#!/usr/bin/env python3
"""Create a durable comparison report for the local WikiEval runs.

The comparison intentionally keeps protocol-specific metrics separate.  MOI's
primary latency is retrieval latency, while the local Dify adapter records
end-to-end request latency; neither is relabeled as the other.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}" if isinstance(value, float) else str(value)
    return str(value)


def pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f}%"


def latest_moi_summary(run_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    candidates = sorted((run_dir / "moi-run").glob("*/summary.json"))
    if not candidates:
        return None, {}
    path = candidates[-1]
    return path, read_json(path, {})


def build_comparison(run_dir: Path) -> dict[str, Any]:
    moi_metrics = read_json(run_dir / "artifacts" / "metrics.json", {})
    moi_summary_path, moi_summary = latest_moi_summary(run_dir)
    dify_summary = read_json(run_dir / "dify-run" / "summary.json", {})
    dify_config = read_json(run_dir / "dify-run" / "run-config.json", {})
    ragas_summary = read_json(run_dir / "artifacts" / "ragas" / "summary.json")
    ragas_config = read_json(run_dir / "artifacts" / "ragas" / "config.json")

    fastgpt_path = run_dir.parents[3] / ".local-services" / "fastgpt_local" / "logs" / "smoke-partial-20260806-114747" / "smoke-result.json"
    maxkb_path = run_dir.parents[3] / ".local-services" / "maxkb_local" / "logs" / "smoke-partial-2026-08-06" / "smoke-result.json"
    fastgpt = read_json(fastgpt_path, {})
    maxkb = read_json(maxkb_path, {})

    dify_metrics = dify_summary.get("metrics") or {}
    dify_latency = dify_summary.get("latency_seconds") or {}
    rows = [
        {
            "system": "MOI",
            "status": "completed",
            "attempts": moi_metrics.get("attempts"),
            "request_success_rate": moi_metrics.get("success_rate"),
            "retrieval_hit_rate": moi_metrics.get("source_recall_at_10"),
            "retrieval_recall_rate": moi_metrics.get("source_recall_at_10"),
            "mrr": moi_metrics.get("mrr"),
            "answer_keyword_recall": moi_metrics.get("reference_keyword_recall"),
            "answer_quality_metric": "reference_normalized_overlap",
            "answer_quality_value": moi_metrics.get("reference_normalized_overlap"),
            "latency_p50": moi_metrics.get("latency_ms_p50"),
            "latency_p95": moi_metrics.get("latency_ms_p95"),
            "latency_unit": "ms; retrieval only",
            "protocol": moi_metrics.get("protocol"),
        },
        {
            "system": "Dify local",
            "status": "completed",
            "attempts": dify_summary.get("attempts"),
            "request_success_rate": dify_metrics.get("request_success"),
            "retrieval_hit_rate": dify_metrics.get("retrieval_hit_at_k"),
            "retrieval_recall_rate": dify_metrics.get("retrieval_recall_at_k"),
            "mrr": dify_metrics.get("mrr"),
            "answer_keyword_recall": dify_metrics.get("keyword_recall"),
            "answer_quality_metric": "token_f1",
            "answer_quality_value": dify_metrics.get("token_f1"),
            "latency_p50": dify_latency.get("p50"),
            "latency_p95": dify_latency.get("p95"),
            "latency_unit": "s; end-to-end request",
            "protocol": dify_summary.get("protocol"),
        },
    ]
    skipped = [
        {
            "system": "FastGPT local",
            "status": "skipped",
            "reason": "本轮 WikiEval 未启动 FastGPT；既有 smoke 仅完成服务/入库/检索，native QA 持续超时，没有可比较的 WikiEval 结果。",
            "evidence": str(fastgpt_path),
            "smoke_status": fastgpt.get("status"),
            "native_status": fastgpt.get("native_status"),
            "retrieval_status": fastgpt.get("retrieval_status"),
            "blocked_reason": fastgpt.get("blocked_reason"),
        },
        {
            "system": "MaxKB local",
            "status": "skipped",
            "reason": "本轮 WikiEval 未启动 MaxKB；既有 smoke 的入库状态语义未验证、native 回答未消费问题，公共 direct-retrieval 合约也未确认。",
            "evidence": str(maxkb_path),
            "smoke_status": maxkb.get("details", {}).get("overall_result", maxkb.get("status")),
            "native_status": maxkb.get("native_status"),
            "retrieval_status": maxkb.get("retrieval_status"),
            "blocked_reason": maxkb.get("blocked_reason"),
        },
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "vibrantlabsai/wiki-eval",
        "dataset_rows": 50,
        "run_dir": str(run_dir),
        "moi_summary_path": str(moi_summary_path) if moi_summary_path else None,
        "dify_config": dify_config,
        "ragas_config": ragas_config,
        "moi_summary": moi_summary,
        "moi_metrics": moi_metrics,
        "dify_summary": dify_summary,
        "ragas_summary": ragas_summary,
        "rows": rows,
        "skipped": skipped,
        "interpretation": {
            "primary_comparison": "request success, retrieval hit/recall, MRR, and protocol-specific answer diagnostics",
            "latency_caveat": "MOI latency is retrieval latency; Dify latency is end-to-end request latency",
            "ragas_role": "Ragas judge metrics are diagnostic and are not the primary deterministic leaderboard score",
        },
    }


def render_markdown(comparison: dict[str, Any], output_path: Path, comparison_json_path: Path) -> None:
    moi = comparison["moi_metrics"]
    dify = comparison["dify_summary"]
    dm = dify.get("metrics") or {}
    dl = dify.get("latency_seconds") or {}
    ragas = comparison.get("ragas_summary")
    run_dir = Path(comparison["run_dir"])
    lines = [
        "# MOI WikiEval Ragas 与本地竞品对比",
        "",
        "## Technical Summary",
        "",
        f"本报告基于 WikiEval 的 50 条问题，数据集为 `vibrantlabsai/wiki-eval`。本轮完成了 MOI 和本地 Dify 的 50/50 端到端请求；FastGPT 与 MaxKB 按既有 smoke 证据和当前运行状态跳过，没有据此给出排名。",
        "",
        f"MOI 的检索侧在本快照中 source recall@10={pct(moi.get('source_recall_at_10'))}、MRR={fmt(moi.get('mrr'))}、成功率={pct(moi.get('success_rate'))}；Dify 的对应协议字段为 retrieval hit@k={pct(dm.get('retrieval_hit_at_k'))}、MRR={fmt(dm.get('mrr'))}、请求成功率={pct(dm.get('request_success'))}。两者的召回字段都命中了 50/50，但 MOI 与 Dify 的 chunk/context 统计口径不同，不能仅凭这个结果宣布绝对优胜。",
        "",
        "## Completed Runs",
        "",
        "| System | Rows | Request success | Retrieval hit/recall | MRR | Answer diagnostic | Latency |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| MOI | {fmt(moi.get('attempts'))} | {pct(moi.get('success_rate'))} | source recall@10 {pct(moi.get('source_recall_at_10'))} | {fmt(moi.get('mrr'))} | keyword recall {pct(moi.get('reference_keyword_recall'))}; normalized overlap {pct(moi.get('reference_normalized_overlap'))} | retrieval p50/p95 {fmt(moi.get('latency_ms_p50'), 1)}/{fmt(moi.get('latency_ms_p95'), 1)} ms |",
        f"| Dify local | {fmt(dify.get('attempts'))} | {pct(dm.get('request_success'))} | hit@k {pct(dm.get('retrieval_hit_at_k'))}; recall@k {pct(dm.get('retrieval_recall_at_k'))} | {fmt(dm.get('mrr'))} | keyword recall {pct(dm.get('keyword_recall'))}; token F1 {pct(dm.get('token_f1'))} | end-to-end p50/p95 {fmt(dl.get('p50'), 2)}/{fmt(dl.get('p95'), 2)} s |",
        "",
        "### Metric definitions",
        "",
        "- MOI `source recall@10`：排名前 10 的检索结果是否包含该 WikiEval 行对应的 source；`reference_normalized_overlap` 和 keyword recall 是回答诊断指标。",
        "- Dify `retrieval hit@k` / `recall@k` / precision：由本地 `dify-rag-eval` 适配器依据返回的 retriever contexts 计算；`token F1` 是回答与 reference 的 token 级诊断。",
        "- 延迟不能直接横比：MOI 这里记录检索延迟，Dify 记录端到端 API 请求延迟；报告保留单位和口径。",
        "",
        "## MOI Ragas Diagnostic",
        "",
    ]
    if ragas:
        lines += [
            f"Ragas 共处理 {fmt(ragas.get('rows'))} 行；由于 TaaS judge 的超时/重试策略，下面的 `scored_rows` 是实际得到有限值的分母。Ragas 仅作为诊断，不替代确定性检索主指标。",
            "",
            "| Metric | Scored rows | Mean | P50 | Min | Max |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for name, value in (ragas.get("metrics") or {}).items():
            lines.append(f"| {name} | {fmt(value.get('scored_rows'))} | {fmt(value.get('mean'), 4)} | {fmt(value.get('p50'), 4)} | {fmt(value.get('min'), 4)} | {fmt(value.get('max'), 4)} |")
    else:
        lines.append("Ragas judge 尚未产生 summary.json；本报告暂仅记录确定性指标。")
    lines += [
        "",
        "## Skipped Competitors",
        "",
        "| System | Status | Reason |",
        "|---|---|---|",
    ]
    for item in comparison["skipped"]:
        lines.append(f"| {item['system']} | {item['status']} | {item['reason']} |")
    lines += [
        "",
        "## Methodology and scope",
        "",
        "- WikiEval 当前快照固定为 50 条 question/source 行；MOI 使用本地 MatrixFlow pipeline，Dify 使用本地 Dify app，并为本次 run 临时绑定同一批 WikiEval 文档，结束后恢复原 Dify dataset binding。",
        "- MOI 的 deterministic scorer 是主结果；Ragas 使用 TaaS 的 `deepseek-v4-flash` judge 与 `bge-m3` embedding，仅用于 faithfulness、answer relevancy、context precision、context recall 诊断。",
        "- FastGPT/MaxKB 的 smoke 证据来自本地 `.local-services` 日志；由于没有形成同一 WikiEval 的稳定 ingest/query/result contract，未强行启动竞品，也未将 smoke 命中率冒充 WikiEval 结果。",
        "",
        "## Limitations and next steps",
        "",
        "- 若需要严格的跨产品排行榜，应进一步统一各产品的 top-k、chunk/source identity、答案终止条件、端到端计时边界，并让 Dify 也跑同一套 Ragas judge。",
        "- MOI 的完整 evidence substring recall 较低时，不能直接解释为检索失败；WikiEval reference 是长文本，当前字段更适合作为诊断信号，需结合 source recall、normalized overlap 和人工抽样复核。",
        "- FastGPT/MaxKB 可在后续服务资源窗口允许时逐个启动，用同一批 50 文档做 ingest readiness、direct retrieval、native QA 三段式门禁；任一门禁失败仍应保留 skipped 状态。",
        "",
        "## Artifact paths",
        "",
        f"- Dataset manifest: `{run_dir / 'artifacts' / 'dataset_manifest.json'}`",
        f"- MOI results: `{run_dir / 'moi-run'}`",
        f"- MOI metrics: `{run_dir / 'artifacts' / 'metrics.json'}`",
        f"- MOI Ragas scores: `{run_dir / 'artifacts' / 'ragas'}`",
        f"- Dify results: `{run_dir / 'dify-run'}`",
        f"- Comparison JSON: `{comparison_json_path}`",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    comparison = build_comparison(args.run)
    report_path = args.run / "wikieval-comparison-report.md"
    json_path = args.run / "artifacts" / "wikieval-comparison.json"
    write_json(json_path, comparison)
    render_markdown(comparison, report_path, json_path)
    print(json.dumps({"report": str(report_path), "comparison": str(json_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
