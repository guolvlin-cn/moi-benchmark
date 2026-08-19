#!/usr/bin/env python3
"""Merge the isolated Lenovo local-performance passes into one MaaS-aware report.

The four product adapters do not expose identical contracts.  This merger keeps
the database-facing retrieval track separate from the application/streaming
track and records the configured upstream model provider beside every result.
It never writes credentials; its inputs are the redacted benchmark artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping


PLATFORM_ROOT = Path(__file__).resolve().parents[2]
ROOT = PLATFORM_ROOT.parent
PLATFORM_ORDER = ("moi", "dify", "fastgpt", "maxkb")
DEFAULT_BASELINE = ROOT / "runs/lenovo-local-latency/20260817-000847-maas-baseline"

PLATFORM_METADATA: dict[str, dict[str, str]] = {
    "moi": {
        "retrieval_provider": "Huawei MaaS",
        "retrieval_model": "bge-m3 / 1024d",
        "chat_provider": "Huawei MaaS (configured; disabled)",
        "chat_model": "qwen3-30b-a3b",
        "provider_evidence": "prototypes/local-matrixflow-rag/config.lenovo-bench.latency.maas.json",
        "retrieval_contract": "native MatrixFlow SearchRAGChunks CLI -> MatrixOne",
        "application_contract": "not exposed by current local implementation",
    },
    "dify": {
        "retrieval_provider": "Huawei MaaS",
        "retrieval_model": "bge-m3 / 1024d",
        "chat_provider": "Qianfan (current resource)",
        "chat_model": "deepseek-v4-flash",
        "provider_evidence": "runs/dify-lenovo-bench-20260813/dify-local-lenovo-bench-formal-v1/preflight.json",
        "retrieval_contract": "POST /v1/datasets/{id}/retrieve",
        "application_contract": "POST /v1/chat-messages (SSE)",
    },
    "fastgpt": {
        "retrieval_provider": "MatrixOrigin TaaS",
        "retrieval_model": "bge-m3 / 1024d",
        "chat_provider": "Qianfan",
        "chat_model": "deepseek-v4-flash",
        "provider_evidence": "runs/stage1/lenovo-bench-fastgpt/20260812-fastgpt-lenovo-bench-native-v5-final/fastgpt_local/native/fastgpt-http/http/000150-native-020.json",
        "retrieval_contract": "POST /api/core/dataset/searchTest",
        "application_contract": "POST /api/v1/chat/completions (SSE)",
    },
    "maxkb": {
        "retrieval_provider": "Huawei MaaS",
        "retrieval_model": "bge-m3 / 1024d",
        "chat_provider": "Qianfan (current resource)",
        "chat_model": "deepseek-v4-flash",
        "provider_evidence": "runs/maxkb-lenovo-bench-20260813/maxkb-local-lenovo-bench-chunked-text-v1/preflight.json",
        "retrieval_contract": "admin knowledge hit_test diagnostic API",
        "application_contract": "published OpenAI-compatible JSON API",
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _number(value: Any, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _dist(summary: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = summary.get(key)
    return value if isinstance(value, Mapping) else {}


def _provider_alignment(meta: Mapping[str, str]) -> str:
    retrieval = meta.get("retrieval_provider", "")
    chat = meta.get("chat_provider", "")
    if retrieval.startswith("Huawei MaaS") and chat.startswith("Huawei MaaS"):
        return "Huawei MaaS / Huawei MaaS"
    return f"{retrieval} / {chat}"


def _load_platform_run(path: Path, platform: str) -> dict[str, Any]:
    results = _read_json(path / "results.json")
    if platform not in results:
        raise ValueError(f"{path}/results.json does not contain platform {platform!r}")
    manifest = _read_json(path / "manifest.json")
    queries = path / "selected-queries.jsonl"
    if not queries.is_file():
        raise FileNotFoundError(queries)
    result = dict(results[platform])
    result["source_run"] = str(path.resolve())
    result["source_manifest"] = manifest
    result["selected_queries_sha256"] = _sha256(queries)
    result["provider"] = PLATFORM_METADATA[platform]
    result["provider_alignment"] = _provider_alignment(PLATFORM_METADATA[platform])
    return result


def _load_baseline(path: Path) -> dict[str, Any]:
    results = _read_json(path / "results.json")
    manifest = _read_json(path / "manifest.json")
    queries = path / "selected-queries.jsonl"
    return {
        "source_run": str(path.resolve()),
        "source_manifest": manifest,
        "selected_queries_sha256": _sha256(queries),
        "results": results,
    }


def _validate_common_runs(runs: Mapping[str, Mapping[str, Any]], baseline: Mapping[str, Any]) -> dict[str, Any]:
    manifests = [run["source_manifest"] for run in runs.values()]
    manifests.append(baseline["source_manifest"])
    count = {item.get("count") for item in manifests}
    seed = {item.get("seed") for item in manifests}
    connections = {item.get("connections") for item in manifests}
    hashes = {run["selected_queries_sha256"] for run in runs.values()}
    hashes.add(baseline["selected_queries_sha256"])
    if len(count) != 1 or len(seed) != 1 or len(connections) != 1 or len(hashes) != 1:
        raise ValueError(
            "input runs are not comparable: "
            f"count={count}, seed={seed}, connections={connections}, query_hashes={hashes}"
        )
    return {
        "count": next(iter(count)),
        "seed": next(iter(seed)),
        "connections": next(iter(connections)),
        "selected_queries_sha256": next(iter(hashes)),
    }


def _retrieval_row(platform: str, result: Mapping[str, Any]) -> str:
    summary = result.get("retrieval") or {}
    dist = _dist(summary, "latency_ms")
    return (
        f"| {platform.upper()} | {_provider_alignment(result['provider'])} | "
        f"{summary.get('successes', 0)}/{summary.get('requests', 0)} | "
        f"{_number(dist.get('p50'))} / {_number(dist.get('p95'))} | "
        f"{_number(summary.get('qps'))} | {_number(summary.get('configured_connections'), 0)} / "
        f"{_number(summary.get('peak_in_flight'), 0)} | {summary.get('status', 'N/A')} |"
    )


def _application_row(platform: str, result: Mapping[str, Any]) -> str:
    summary = result.get("events") or {}
    dist = _dist(summary, "latency_ms")
    ttfe = _dist(summary, "ttfe_ms")
    status = summary.get("status", "N/A")
    if status in {"unsupported", "skipped"}:
        status_note = status
    elif status == "error":
        status_note = "; ".join(summary.get("error_types") or []) or "error"
    else:
        status_note = status
    event_rate = summary.get("event_throughput_events_per_s") if status == "ok" else None
    return (
        f"| {platform.upper()} | {result['provider'].get('chat_provider', 'N/A')} / "
        f"{result['provider'].get('chat_model', 'N/A')} | {summary.get('successes', 0)}/"
        f"{summary.get('requests', 0)} | {_number(ttfe.get('p50'))} / {_number(ttfe.get('p95'))} | "
        f"{_number(dist.get('p50'))} / {_number(dist.get('p95'))} | "
        f"{_number(event_rate)} | "
        f"{_number(summary.get('configured_connections'), 0)} / {_number(summary.get('peak_in_flight'), 0)} | "
        f"{status_note} |"
    )


def _baseline_rows(baseline: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for provider, result in baseline.get("results", {}).items():
        dist = result.get("latency_ms") or {}
        warmup = result.get("warmup") or {}
        error = warmup.get("error") or warmup.get("status_code") or result.get("reason") or ""
        qps = result.get("qps") if result.get("status") == "ok" else None
        lines.append(
            f"| {provider} | {result.get('model', 'N/A')} | {result.get('successes', 0)}/"
            f"{result.get('requests', 0)} | {_number(dist.get('p50'))} | {_number(dist.get('p95'))} | "
            f"{_number(qps)} | {', '.join(map(str, result.get('vector_dimensions', []))) or 'N/A'} | "
            f"{error or result.get('status', 'N/A')} |"
        )
    return lines


def build_report(runs: Mapping[str, Mapping[str, Any]], baseline: Mapping[str, Any], common: Mapping[str, Any], output: Path) -> str:
    lines = [
        "# Lenovo 本地 RAG + MaaS 性能横向对比报告",
        "",
        "本报告只评估本地部署的运行性能，不评价回答质量。模型推理/向量化仍通过外部 MaaS（或当前资源中已配置的兼容供应商）完成，所以上游网络和模型耗时单独标注，不能误读为纯本地数据库耗时。",
        "",
        "## 结论摘要",
        "",
        f"- 四个平台均完成检索轨道 `{common['count']}/{common['count']}` 成功；同一批 Query 的 SHA-256 为 `{common['selected_queries_sha256']}`。",
        "- 本地检索 p50：FastGPT 686.117 ms，MaxKB 691.858 ms，MOI 753.895 ms，Dify 1017.952 ms。这个排序只针对本轮固定 Query、当前本地资源和并发设置。",
        "- 应用轨道：FastGPT TTFE 最低（p50 97.341 ms），Dify 为 1649.582 ms；MaxKB 10/10 返回 500，MOI 当前实现没有流式 HTTP 应用接口。",
        "- 当前资源并非全部 Huawei MaaS：MOI、Dify、MaxKB 的 embedding 记录为 Huawei MaaS `bge-m3/1024d`，FastGPT 的 Lenovo 资源记录为 MatrixOrigin TaaS `bge-m3`；Dify、FastGPT、MaxKB 的聊天应用均绑定 Qianfan。",
        "",
        "## 1. 本地检索轨道（主指标）",
        "",
        "检索请求包含产品侧的查询向量化、HTTP/API 编排和本地向量库查询；由于产品没有统一的内部 tracing，不能把它进一步拆成纯数据库时间。",
        "",
        "| 平台 | Embedding / Chat provider | 成功数 | Retrieval p50 / p95 (ms) | Retrieval QPS | 连接数（配置 / 峰值） | 状态 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for platform in PLATFORM_ORDER:
        lines.append(_retrieval_row(platform, runs[platform]))
    lines += [
        "",
        "## 2. 应用/流式轨道（辅助指标）",
        "",
        "TTFE 是请求开始到首个 SSE/JSON 事件的时间；Event Throughput 是本轮应用请求解析到的事件数除以批次墙钟时间；总耗时包含生成和传输。",
        "",
        "| 平台 | Chat provider / model | 成功数 | TTFE p50 / p95 (ms) | 总耗时 p50 / p95 (ms) | Event Throughput (events/s) | 连接数（配置 / 峰值） | 状态/原因 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for platform in PLATFORM_ORDER:
        lines.append(_application_row(platform, runs[platform]))
    lines += [
        "",
        "Empty Workflow QPS：四个平台本轮均为 `N/A`，因为没有统一配置的“不检索、不调用模型、只返回固定文本”的空工作流；用真实 RAG 应用代替会污染这个指标。",
        "",
        "## 3. MaaS 上游 embedding 基线",
        "",
        "这个轨道直接调用外部 `/embeddings`，只用于解释本地检索端到端延迟的上游参考线，不代表本地平台性能。",
        "",
        "| Provider | Model | 成功数 | p50 (ms) | p95 (ms) | QPS | 向量维度 | 探测结果/错误 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    lines.extend(_baseline_rows(baseline))
    lines += [
        "",
        "本轮 Huawei MaaS `bge-m3` 直连基线为 10/10，p50 2167.621 ms、p95 2499.331 ms、QPS 1.650；Qianfan 直连探测返回 HTTP 403，MatrixOrigin TaaS 返回 HTTP 401，因此没有把失败结果当作 0 ms 纳入排名。",
        "",
        "## 4. 测试条件与可比性边界",
        "",
        f"- 数据集：Lenovo `moi-corpus-100q-v1`；随机抽样 `{common['count']}` 条，seed `{common['seed']}`；回答质量不评分。",
        f"- 并发：每个平台 `{common['connections']}` 个请求 worker；平台之间串行执行；单请求超时 120 秒。",
        "- MOI：当前本地实现是 MatrixFlow CLI，实际并发为 1，因此不虚构 Event Throughput、TTFE 或 HTTP Connections。",
        "- Dify：检索是 dataset retrieve API；应用轨道是 chat-messages SSE。测试前 Weaviate 完成 WAL/Schema 恢复，最终重跑结果为本报告所用数据。",
        "- FastGPT：检索是 dataset searchTest；应用轨道是 OpenAI 兼容 SSE。总耗时较长但首事件较快，说明“首包响应”和“完整生成结束”是两个不同指标。",
        "- MaxKB：检索使用 admin hit_test 诊断接口；公开应用轨道返回 HTTP 500，保留检索结果，生成指标记为失败。",
        "- 本报告没有把 `p50 - MaaS p50` 写成“纯本地 DB 延迟”：不同产品的批处理、缓存、连接复用和 embedding 调用时序不同，直接相减会产生误导。",
        "",
        "## 5. MaaS 配置核对",
        "",
        "| 平台 | Embedding | Chat | 严格同 MaaS 生成对比 | 证据 |",
        "|---|---|---|---|---|",
    ]
    for platform in PLATFORM_ORDER:
        meta = runs[platform]["provider"]
        same = "是" if meta["chat_provider"].startswith("Huawei MaaS") else "否（当前资源为混合供应商）"
        lines.append(
            f"| {platform.upper()} | {meta['retrieval_provider']} / {meta['retrieval_model']} | "
            f"{meta['chat_provider']} / {meta['chat_model']} | {same} | `{meta['provider_evidence']}` |"
        )
    lines += [
        "",
        "如果汇报需要严格的“全链路均使用 Huawei MaaS”对比，应为 FastGPT、Dify、MaxKB 各创建新的 MaaS embedding/Chat 资源并重建索引（不要覆盖当前资源），再复用本报告的同一 Query/并发配置重测；本报告是当前部署的真实本地性能结果。",
        "",
        "## 6. 机器可读产物",
        "",
        f"- 汇报版：`{(output / 'report.md').resolve()}`",
        f"- 合并结果：`{(output / 'results.json').resolve()}`",
        f"- 测试清单：`{(output / 'manifest.json').resolve()}`",
        "- 每个平台的原始请求样本、错误类型和 MOI 日志保留在各自 source run 目录；没有写入 API Key。",
    ]
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> Path:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    platform_paths = {
        "moi": args.moi,
        "dify": args.dify,
        "fastgpt": args.fastgpt,
        "maxkb": args.maxkb,
    }
    runs = {platform: _load_platform_run(path.resolve(), platform) for platform, path in platform_paths.items()}
    baseline = _load_baseline(args.maas_baseline.resolve())
    common = _validate_common_runs(runs, baseline)
    merged = {
        "schema": "lenovo-local-maas-performance-v1",
        "common": common,
        "platforms": runs,
        "maas_baseline": baseline,
    }
    (output / "results.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "schema": "lenovo-local-maas-performance-v1",
        **common,
        "platforms": list(PLATFORM_ORDER),
        "source_runs": {platform: str(path.resolve()) for platform, path in platform_paths.items()},
        "maas_baseline": str(args.maas_baseline.resolve()),
        "quality_evaluation": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_queries = next(iter(platform_paths.values())).resolve() / "selected-queries.jsonl"
    shutil.copy2(source_queries, output / "selected-queries.jsonl")
    report_path = output / "report.md"
    report_path.write_text(build_report(runs, baseline, common, output), encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    for platform in PLATFORM_ORDER:
        parser.add_argument(f"--{platform}", type=Path, required=True)
    parser.add_argument("--maas-baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args()
    print(f"report={run(args)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
