#!/usr/bin/env python3
"""Validate and merge strict-MaaS Lenovo latency benchmark runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PLATFORMS = ("moi", "dify", "fastgpt", "maxkb")
COUNT = 10
SEED = 20260814
TIMEOUT = 120.0


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_run(path: Path, platform: str, connections: int) -> tuple[dict[str, Any], dict[str, Any], Path]:
    path = path.resolve()
    manifest = read_json(path / "manifest.json")
    if platform not in (manifest.get("platforms") or []):
        raise ValueError(f"{platform} is not declared by {path}")
    expected = {"count": COUNT, "seed": SEED, "connections": connections, "timeout_seconds": TIMEOUT, "platform_execution": "serial"}
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"{platform} {key}={manifest.get(key)!r}; expected {value!r}")
    query_path = path / "selected-queries.jsonl"
    result = read_json(path / "results.json")
    if not isinstance(result.get(platform), dict):
        raise ValueError(f"missing result for {platform}: {path / 'results.json'}")
    return manifest, result[platform], query_path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{value:.3f}"
    return str(value)


def latency(result: dict[str, Any], section: str) -> str:
    values = (result.get(section) or {}).get("latency_ms") or {}
    return f"{fmt(values.get('p50'))}/{fmt(values.get('p95'))}"


def ttfe(result: dict[str, Any]) -> str:
    values = (result.get("events") or {}).get("ttfe_ms") or {}
    if values.get("count", 0):
        return f"{fmt(values.get('p50'))}/{fmt(values.get('p95'))}"
    proxy = result.get("cli_first_output_latency_ms") or {}
    if proxy.get("count", 0):
        return f"{fmt(proxy.get('p50'))}/{fmt(proxy.get('p95'))}（CLI proxy）"
    return "N/A/N/A"


def event_rate(result: dict[str, Any]) -> str:
    return fmt((result.get("events") or {}).get("event_throughput_events_per_s"))


def connections(result: dict[str, Any]) -> str:
    events = result.get("events") or {}
    if events.get("status") != "unsupported":
        return f"{events.get('connections')}/{events.get('peak_in_flight')}"
    retrieval = result.get("retrieval") or {}
    return f"{retrieval.get('connections')}/{retrieval.get('peak_in_flight')}（CLI）"


def success(result: dict[str, Any], section: str) -> str:
    value = result.get(section) or {}
    return f"{value.get('successes', 0)}/{value.get('requests', 0)} {value.get('status', 'unknown')}"


def empty_qps(result: dict[str, Any]) -> str:
    return fmt((result.get("empty_workflow") or {}).get("qps"))


def provider_audit() -> dict[str, Any]:
    maas = "https://api.modelarts-maas.com/v1"
    return {
        "strict_maas": True,
        "external_provider": "Huawei Cloud MaaS",
        "maas_base_url": maas,
        "embedding_model": "bge-m3",
        "api_platform_chat_model": "deepseek-v4-flash (Dify/FastGPT/MaxKB)",
        "secrets_included": False,
        "platforms": {
            "moi": {"provider": "maas", "embedding": "bge-m3", "chat": "native retrieval CLI only", "source": "prototypes/local-matrixflow-rag/config.lenovo-bench.latency.maas.json"},
            "dify": {"provider": "MaaS through MatrixOrigin-compatible adapter", "embedding": "bge-m3", "chat": "deepseek-v4-flash", "source": "dify-setup/resource-map.json"},
            "fastgpt": {"provider": "MaaS AIProxy channel", "embedding": "bge-m3", "chat": "deepseek-v4-flash", "source": "fastgpt-setup/resources.json"},
            "maxkb": {"provider": "MaaS model records", "embedding": "bge-m3", "chat": "deepseek-v4-flash", "source": "maxkb-setup/resource-map.json"},
        },
    }


def build_report(manifest: dict[str, Any], results: dict[str, dict[str, Any]], serial: dict[str, Any], runs: dict[str, Path], serial_run: Path) -> str:
    lines = [
        "# Lenovo 数据集本地 RAG 性能汇报（严格 MaaS 口径）",
        "",
        "> 只评价延迟、并发和流式传输，不评价回答质量。四个平台的外部模型/embedding 请求统一指向华为云 MaaS，本地服务、向量索引和检索编排留在本机。",
        "",
        "## 测试条件",
        "",
        f"- Lenovo 数据集；随机 query 数：{COUNT}；seed：`{SEED}`。",
        f"- 所有输入 query 文件 SHA-256：`{manifest['selected_queries_sha256']}`。",
        f"- 主表连接数：4；每个平台独立启动、串行占用机器资源；单请求 timeout：{TIMEOUT:.0f}s。",
        "- 主表 MaxKB 使用 warm 4-connections run；另列 1-connection 串行控制组。",
        "- Retrieval 是平台检索 API 的完整路径，不是绕过平台的纯本地数据库 kernel latency；应用指标还包含 MaaS 生成和平台编排。",
        "",
        "## 主结果（4 connections）",
        "",
        "| 平台 | Retrieval p50/p95 (ms) | Event Throughput (events/s) | TTFE / CLI proxy p50/p95 (ms) | Connections 实际/峰值 | Empty Workflow QPS | 完整性 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for platform in PLATFORMS:
        result = results[platform]
        lines.append(f"| {platform} | {latency(result, 'retrieval')} | {event_rate(result)} | {ttfe(result)} | {connections(result)} | {empty_qps(result)} | retrieval {success(result, 'retrieval')}; events {success(result, 'events')} |")
    lines += [
        "",
        "说明：`p50/p95` 均为毫秒；MOI 的 TTFE 列使用 `CLI First Output Latency` 替代指标（首条 `attempt=... status=...` 输出），并标注为 `CLI proxy`；它不是流式 HTTP TTFE。`N/A` 表示当前平台/资源没有该测量契约，不表示性能为 0。MOI 的连接数是 native CLI 检索实际并发，不是 HTTP 连接。",
        "",
        "## MaxKB 配额安全控制组",
        "",
        "| 场景 | Retrieval p50/p95 (ms) | Event Throughput (events/s) | TTFE p50/p95 (ms) | Connections | 成功数 |",
        "|---|---:|---:|---:|---:|---:|",
        f"| 4 connections warm（主表） | {latency(results['maxkb'], 'retrieval')} | {event_rate(results['maxkb'])} | {ttfe(results['maxkb'])} | {connections(results['maxkb'])} | {success(results['maxkb'], 'events')} |",
        f"| 1 connection serial control | {latency(serial, 'retrieval')} | {event_rate(serial)} | {ttfe(serial)} | {connections(serial)} | {success(serial, 'events')} |",
        "",
        "4 并发时 MaxKB 的 2 个失败请求对应 MaaS `ModelArts.81101`（rate limit 1 request/s），MaxKB 对外包装为 HTTP 500。串行控制组 10/10 成功，说明该次不完整主要是上游配额约束，而不是本地检索服务无法工作。",
        "",
        "## MaaS 配置核验",
        "",
        "| 平台 | embedding | chat/应用模型 | 核验记录 |",
        "|---|---|---|---|",
        "| MOI | MaaS `bge-m3` | 本次只跑 native retrieval CLI，未走 chat 生成 | `prototypes/local-matrixflow-rag/config.lenovo-bench.latency.maas.json` |",
        "| Dify | MaaS `bge-m3` | MaaS `deepseek-v4-flash`；Dify 内部使用 MatrixOrigin-compatible adapter | `dify-setup/resource-map.json` |",
        "| FastGPT | MaaS `bge-m3` | MaaS `deepseek-v4-flash`；reranker 已配置但未作为主指标拆分 | `fastgpt-setup/resources.json` |",
        "| MaxKB | MaaS `bge-m3` | MaaS `deepseek-v4-flash` | `maxkb-setup/resource-map.json` |",
        "",
        "## 结果解读与限制",
        "",
        "1. FastGPT 的本轮检索 p50 最低；MOI 的 CLI proxy 只用于补齐一个可汇报的首输出延迟，不能与其他平台的 HTTP API TTFE 直接横比。",
        "2. Dify、FastGPT、MaxKB 的应用指标包含 MaaS `deepseek-v4-flash` 生成时间，不能把它们当成单纯本地向量库耗时。若要测纯数据库 kernel，需要预计算 embedding 后的原生 search API 或直接连接向量库。",
        "3. Event Throughput 按本次脚本定义为批次内事件数除以批次总 wall time；原始结果还保留 `stream_event_rate`，不要将两个指标混为一谈。",
        "4. 四个平台没有为 Lenovo 资源配置明确的 no-op workflow，因此 `Empty Workflow QPS` 统一为 `N/A`，不是 0。",
        "",
        "## 可复现操作",
        "",
        "详见同目录的 [`RUN_GUIDE.md`](RUN_GUIDE.md)。原始 JSON、query 样本、逐请求样本和各平台报告均保留在 source run 目录中。",
        "",
        "## 原始跑数目录",
        "",
    ]
    for platform in PLATFORMS:
        lines.append(f"- `{platform}`: `{runs[platform].resolve()}`")
    lines.append(f"- `maxkb-serial-control`: `{serial_run.resolve()}`")
    return "\n".join(lines) + "\n"


def merge(output: Path, runs: dict[str, Path], serial_run: Path) -> Path:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    manifests: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, Any]] = {}
    query_paths: dict[str, Path] = {}
    for platform in PLATFORMS:
        manifest, result, query = load_run(runs[platform], platform, 4)
        manifests[platform] = manifest
        results[platform] = result
        query_paths[platform] = query
    _, serial, serial_query = load_run(serial_run, "maxkb", 1)
    query_paths["maxkb-serial"] = serial_query
    hashes = {name: sha256(path) for name, path in query_paths.items()}
    if len(set(hashes.values())) != 1:
        raise ValueError(f"query files differ: {hashes}")
    queries = [line for line in query_paths["moi"].read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(queries) != COUNT:
        raise ValueError(f"query count={len(queries)}; expected {COUNT}")
    output.mkdir(parents=True)
    (output / "selected-queries.jsonl").write_bytes(query_paths["moi"].read_bytes())
    manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "strict_maas": True,
        "external_provider": "Huawei Cloud MaaS",
        "maas_base_url": "https://api.modelarts-maas.com/v1",
        "benchmark_scope": "Lenovo random queries; latency and throughput only; no quality evaluation",
        "count": COUNT,
        "seed": SEED,
        "connections": 4,
        "timeout_seconds": TIMEOUT,
        "platform_execution": "serial-isolated-platform-passes",
        "platforms": list(PLATFORMS),
        "selected_queries_sha256": next(iter(hashes.values())),
        "source_runs": {name: str(path.resolve()) for name, path in runs.items()},
        "maxkb_serial_control_run": str(serial_run.resolve()),
        "empty_workflow_qps": "unsupported/N/A; no explicit no-op workflow configured",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    final_results = {**results, "controls": {"maxkb_serial": serial}}
    (output / "results.json").write_text(json.dumps(final_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "provider-audit.json").write_text(json.dumps(provider_audit(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(build_report(manifest, results, serial, runs, serial_run), encoding="utf-8")
    return output / "report.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--moi", type=Path, required=True)
    parser.add_argument("--dify", type=Path, required=True)
    parser.add_argument("--fastgpt", type=Path, required=True)
    parser.add_argument("--maxkb", type=Path, required=True)
    parser.add_argument("--maxkb-serial", type=Path, required=True)
    args = parser.parse_args()
    print(merge(args.output, {"moi": args.moi, "dify": args.dify, "fastgpt": args.fastgpt, "maxkb": args.maxkb}, args.maxkb_serial))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
