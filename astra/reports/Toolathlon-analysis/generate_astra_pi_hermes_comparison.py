#!/usr/bin/env python3
"""Build the final Pi summary and Astra/Hermes/Pi Toolathlon comparison."""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any


OUT_DIR = Path(__file__).resolve().parent
ROOT = OUT_DIR.parents[2]
RESULTS = ROOT / "astra/results"
PI_BASE = RESULTS / "toolathlon-pi-108-v1"
PI_ISOLATED = RESULTS / "toolathlon-pi-isolated-rerun-v1"
PI_FINAL = RESULTS / "toolathlon-pi-service-and-audit-8-v3"

sys.path.insert(0, str(OUT_DIR))
from generate_astra_hermes_comparison import build_row, percentile  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def resolve_run_directory(value: str) -> Path:
    marker = "/astra/results/"
    if marker in value:
        return RESULTS / value.split(marker, 1)[1]
    return Path(value)


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def descriptive(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "sum": sum(values),
        "mean": mean(values) if values else None,
        "median": median(values) if values else None,
        "p90": percentile(values, 0.9),
    }


def values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [value for row in rows if (value := number(row.get(key))) is not None]


def truthy(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def top_terminal_tools(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for row in rows:
        run_directory = row.get("run_directory")
        if not run_directory:
            continue
        path = resolve_run_directory(str(run_directory)) / "tool-calls.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("state") not in {"succeeded", "failed"}:
                    continue
                name = event.get("canonical_tool_name") or event.get("visible_tool_name") or "unknown"
                counts[str(name)] += 1
    return counts.most_common(10)


def cache_read_tokens(run_dir: Path) -> int | None:
    path = run_dir / "model-usage.jsonl"
    if not path.exists():
        return None
    total = 0
    observed = False
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("event") != "model_request.completed":
                continue
            field = (row.get("token_usage") or {}).get("cache_read_tokens")
            if isinstance(field, dict) and isinstance(field.get("value"), (int, float)):
                total += int(field["value"])
                observed = True
    return total if observed else None


def pi_rows() -> list[dict[str, Any]]:
    base = load_json(PI_BASE / "pi-108-summary.json")
    isolated = load_json(PI_ISOLATED / "pi-selected-rerun-summary.json")
    final = load_json(PI_FINAL / "pi-selected-rerun-summary.json")

    selected: dict[int, tuple[dict[str, Any], str]] = {
        int(item["position"]): (item, "pi_base_108_v1") for item in base["tasks"]
    }
    for item in isolated["tasks"]:
        if item.get("state") == "complete":
            selected[int(item["position"])] = (item, "pi_isolated_rerun_v1")
    for item in final["tasks"]:
        if item.get("state") == "complete":
            selected[int(item["position"])] = (item, "pi_service_and_audit_8_v3")

    rows = []
    for position in range(1, 109):
        item, source = selected[position]
        task_id = str(item["task_id"])
        if item.get("state") != "complete" or not item.get("run_directory"):
            rows.append(
                {
                    "position": position,
                    "task_id": task_id,
                    "system": "pi",
                    "state": "incomplete",
                    "verify_status": "missing",
                    "run_validity": "missing",
                    "terminal_status": "missing",
                    "failure_category": "infra_incomplete",
                    "source": source,
                    "run_id": "",
                    "run_directory": "",
                }
            )
            continue
        run_dir = resolve_run_directory(str(item["run_directory"]))
        if not (run_dir / "run.json").exists():
            raise FileNotFoundError(run_dir / "run.json")
        row = build_row(position, task_id, "pi", run_dir, source)
        row["state"] = "complete"
        row["cache_read_tokens"] = cache_read_tokens(run_dir)
        rows.append(row)

    if len(rows) != 108 or len({row["position"] for row in rows}) != 108:
        raise AssertionError("Pi result projection must contain positions 1..108 exactly once")
    return rows


def summarize_system(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [row for row in rows if row.get("verify_status") in {"pass", "no_pass"}]
    executed = [row for row in rows if row.get("run_id")]
    passed = [row for row in rows if row.get("verify_status") == "pass"]
    failed = [row for row in rows if row.get("verify_status") == "no_pass"]
    reliable = [row for row in executed if truthy(row.get("token_reliable"))]
    reliable_passed = [row for row in passed if truthy(row.get("token_reliable"))]
    return {
        "tasks": len(rows),
        "executed": len(executed),
        "evaluated": len(evaluated),
        "verify": dict(Counter(str(row.get("verify_status")) for row in rows)),
        "pass_rate_all_108": len(passed) / 108,
        "pass_rate_evaluated": len(passed) / len(evaluated) if evaluated else None,
        "failure_categories": dict(
            Counter(str(row.get("failure_category")) for row in failed)
        ),
        "time": {
            key: descriptive(values(executed, key))
            for key in ("e2e_seconds", "agent_seconds", "evaluator_seconds", "orchestration_seconds")
        },
        "tools": {
            "calls": descriptive(values(executed, "tool_calls")),
            "failures": descriptive(values(executed, "tool_failures")),
            "top_terminal_tools": top_terminal_tools(executed),
        },
        "requests": {
            key: descriptive(values(executed, key))
            for key in (
                "model_requests_started", "model_requests_completed", "model_requests_failed",
                "stream_requests", "non_stream_requests",
            )
        },
        "tokens": {
            "reliable_records": len(reliable),
            "reliable_input": descriptive(values(reliable, "token_input")),
            "reliable_output": descriptive(values(reliable, "token_output")),
            "reliable_total": descriptive(values(reliable, "token_total")),
            "input_visible": descriptive(values(executed, "token_input")),
            "output_visible": descriptive(values(executed, "token_output")),
            "total_visible": descriptive(values(executed, "token_total")),
            "cache_read_visible": descriptive(values(executed, "cache_read_tokens")),
            "reported_completed_requests": sum(
                int(number(row.get("token_usage_reported_completed")) or 0) for row in executed
            ),
            "missing_usage_completed_requests": sum(
                int(number(row.get("token_usage_missing_completed")) or 0) for row in executed
            ),
            "pass_reliable_records": len(reliable_passed),
            "pass_reliable_total": descriptive(values(reliable_passed, "token_total")),
        },
        "request_limit_reached": sum(
            number(row.get("model_request_limit")) is not None
            and number(row.get("model_requests_started"))
            >= number(row.get("model_request_limit"))
            for row in executed
        ),
    }


def load_astra_hermes_rows() -> list[dict[str, Any]]:
    path = OUT_DIR / "astra-hermes-toolathlon-108-task-results.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def outcome_groups(all_rows: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_key = {(int(row["position"]), str(row["system"])): row for row in all_rows}
    groups: dict[str, list[dict[str, Any]]] = {}
    task_rows = []
    for position in range(1, 109):
        current = {system: by_key[(position, system)] for system in ("astra", "hermes", "pi")}
        statuses = {system: str(row.get("verify_status")) for system, row in current.items()}
        if statuses["pi"] not in {"pass", "no_pass"}:
            group = "pi_incomplete"
        else:
            group = "".join("P" if statuses[system] == "pass" else "F" for system in ("astra", "hermes", "pi"))
        task = {
            "position": position,
            "task_id": current["astra"]["task_id"],
            "astra": statuses["astra"],
            "hermes": statuses["hermes"],
            "pi": statuses["pi"],
        }
        groups.setdefault(group, []).append(task)
        task_rows.append(task)
    return groups, task_rows


def pairwise(task_rows: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    eligible = [row for row in task_rows if row[left] in {"pass", "no_pass"} and row[right] in {"pass", "no_pass"}]
    result = Counter()
    tasks = {"both_pass": [], f"{left}_only": [], f"{right}_only": [], "neither": []}
    for row in eligible:
        lp, rp = row[left] == "pass", row[right] == "pass"
        group = "both_pass" if lp and rp else f"{left}_only" if lp else f"{right}_only" if rp else "neither"
        result[group] += 1
        tasks[group].append({"position": row["position"], "task_id": row["task_id"]})
    return {"eligible_tasks": len(eligible), "counts": dict(result), "tasks": tasks}


def format_number(value: Any, digits: int = 2) -> str:
    numeric = number(value)
    if numeric is None:
        return "—"
    if numeric.is_integer():
        return f"{int(numeric):,}"
    return f"{numeric:,.{digits}f}"


def format_compact(value: Any, digits: int = 2) -> str:
    numeric = number(value)
    if numeric is None:
        return "—"
    return f"{numeric:,.{digits}f}".rstrip("0").rstrip(".")


def format_fixed(value: Any, digits: int) -> str:
    numeric = number(value)
    return "—" if numeric is None else f"{numeric:,.{digits}f}"


def format_whole(value: Any) -> str:
    numeric = number(value)
    if numeric is None:
        return "—"
    return f"{int(numeric + 0.5):,}"


def format_hours(value: Any) -> str:
    numeric = number(value)
    return "—" if numeric is None else f"{numeric / 3600:,.2f} h"


def format_minutes(value: Any) -> str:
    numeric = number(value)
    return "—" if numeric is None else f"{numeric / 60:,.2f} min"


def format_seconds(value: Any) -> str:
    numeric = number(value)
    return "—" if numeric is None else f"{numeric:,.2f} s"


def format_total_duration(value: Any) -> str:
    numeric = number(value)
    if numeric is None:
        return "—"
    return format_minutes(numeric) if numeric < 3600 else format_hours(numeric)


def format_count_share(value: Any, total: Any) -> str:
    count = number(value)
    denominator = number(total)
    if count is None or not denominator:
        return "—"
    percentage = f"{count / denominator:.2%}".replace(".00%", "%")
    return f"{int(count):,}（{percentage}）"


def format_percent_floor(value: Any, total: Any) -> str:
    numerator = number(value)
    denominator = number(total)
    if numerator is None or not denominator:
        return "—"
    return f"{math.floor(numerator / denominator * 10000) / 100:.2f}%"


def format_tools(items: list[list[Any]] | list[tuple[str, int]], limit: int = 5) -> str:
    return "、".join(f"`{name}` {count:,}" for name, count in items[:limit])


def task_names(tasks: list[dict[str, Any]]) -> str:
    return "、".join(f"`{item['task_id']}`（{item['position']}）" for item in tasks) or "无"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    preferred = ["position", "task_id", "system", "state", "verify_status", "run_validity", "terminal_status", "failure_category", "run_id", "source"]
    fields = preferred + [field for field in fields if field not in preferred]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def pi_markdown(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    system = summary["system"]
    passed = [row for row in rows if row["verify_status"] == "pass"]
    failed = [row for row in rows if row["verify_status"] == "no_pass"]
    unavailable = [row for row in rows if row["verify_status"] == "unavailable"]
    incomplete = [row for row in rows if row["verify_status"] == "missing"]
    sources = Counter(row["source"] for row in rows)
    failures = Counter(row["failure_category"] for row in failed)
    return f"""# Pi 0.73.1：Toolathlon 108 题结果汇总

生成日期：2026-08-14  
范围：Toolathlon 第 1–108 题，Pi 0.73.1。

## 结果口径

- 最终结果按优先级覆盖：`toolathlon-pi-108-v1` → `toolathlon-pi-isolated-rerun-v1` → `toolathlon-pi-service-and-audit-8-v3`。后一层只覆盖该层实际完成并通过 artifact gate 的题目。
- `pass`/`no_pass` 以 evaluator 为准；达到模型请求上限不自动等于失败。
- 隔离重跑用于替换基础批次中可能访问宿主机路径的审计题及原未完成题；最终 8 题重跑用于替换 Canvas/WooCommerce 服务异常及扩展审计题。
- 第 53、55、72 题的 evaluator wrapper 虽已运行，但返回 `pass: null`，所以保持 `unavailable`；第 38 题没有 Pi `run.json` 或 evaluator 结果，保持 `incomplete`。四题都不计作 `no_pass`。

## 汇总

| 指标 | Pi |
| --- | ---: |
| 基准题目 | 108 |
| 有完整运行 artifact | {system['executed']} |
| 明确 pass/no-pass 的 evaluator 结果 | {system['evaluated']} |
| pass | {system['verify'].get('pass', 0)} |
| no-pass | {system['verify'].get('no_pass', 0)} |
| unavailable | {system['verify'].get('unavailable', 0)} |
| incomplete | {system['verify'].get('missing', 0)} |
| pass rate（按全部 108 题） | {system['pass_rate_all_108']:.2%} |
| pass rate（按 {system['evaluated']} 个有明确判定的题） | {system['pass_rate_evaluated']:.2%} |

最终来源分布：基础批次 {sources['pi_base_108_v1']} 题、隔离重跑 {sources['pi_isolated_rerun_v1']} 题、最终服务/审计重跑 {sources['pi_service_and_audit_8_v3']} 题。

## 任务清单

通过（{len(passed)}）：{task_names(passed)}。

未通过（{len(failed)}）：{task_names(failed)}。

Evaluator unavailable（{len(unavailable)}）：{task_names(unavailable)}。

基础设施未完成（{len(incomplete)}）：{task_names(incomplete)}。

## No-pass 终态原因

| 原因 | 题数 |
| --- | ---: |
| 完成运行但 evaluator 未通过 | {failures.get('completed_but_no_pass', 0)} |
| 达到 100 次模型请求预算 | {failures.get('model_request_budget', 0)} |
| 产品执行错误 | {failures.get('product_error', 0)} |
| 其他 | {sum(value for key, value in failures.items() if key not in {'completed_but_no_pass', 'model_request_budget', 'product_error'})} |

## 运行消耗（{system['executed']} 个有完整 artifact 的运行）

| 指标 | 总计 | 平均 | 中位数 | P90 |
| --- | ---: | ---: | ---: | ---: |
| Agent 时间（秒） | {format_number(system['time']['agent_seconds']['sum'])} | {format_number(system['time']['agent_seconds']['mean'])} | {format_number(system['time']['agent_seconds']['median'])} | {format_number(system['time']['agent_seconds']['p90'])} |
| Evaluator 时间（秒） | {format_number(system['time']['evaluator_seconds']['sum'])} | {format_number(system['time']['evaluator_seconds']['mean'])} | {format_number(system['time']['evaluator_seconds']['median'])} | {format_number(system['time']['evaluator_seconds']['p90'])} |
| 工具调用 | {format_number(system['tools']['calls']['sum'])} | {format_number(system['tools']['calls']['mean'])} | {format_number(system['tools']['calls']['median'])} | {format_number(system['tools']['calls']['p90'])} |
| 模型请求 started | {format_number(system['requests']['model_requests_started']['sum'])} | {format_number(system['requests']['model_requests_started']['mean'])} | {format_number(system['requests']['model_requests_started']['median'])} | {format_number(system['requests']['model_requests_started']['p90'])} |

触及 100 次请求上限的任务有 {system['request_limit_reached']} 题。工具失败事件是 adapter 的结构化终态计数，不等同于任务失败数。

## Token

| 指标 | 数值 |
| --- | ---: |
| 有完整 provider usage 的题目 | {system['tokens']['reliable_records']} / {system['executed']} |
| 输入 token 可见总量 | {format_number(system['tokens']['input_visible']['sum'])} |
| 输出 token 可见总量 | {format_number(system['tokens']['output_visible']['sum'])} |
| total token 可见总量 | {format_number(system['tokens']['total_visible']['sum'])} |
| cache-read token（input 子集） | {format_number(system['tokens']['cache_read_visible']['sum'])} |
| 单题 total 中位数 | {format_number(system['tokens']['total_visible']['median'])} |

Pi 的 `cache_read_tokens` 已包含在 provider input token 中，不能再次相加。Token 反映 Pi 主循环、工具 schema、累积上下文和缓存策略的整体足迹，不应直接解释为底层模型的单位推理效率。

## 附件

- 逐题数据：[`pi-toolathlon-108-task-results.csv`](pi-toolathlon-108-task-results.csv)
- 机器可读汇总：[`pi-toolathlon-108-task-summary.json`](pi-toolathlon-108-task-summary.json)
- 生成脚本：[`generate_astra_pi_hermes_comparison.py`](generate_astra_pi_hermes_comparison.py)
"""


def comparison_markdown(summary: dict[str, Any]) -> str:
    systems = summary["systems"]
    groups = summary["three_way_outcomes"]
    labels = {
        "PPP": "三者均通过", "PPF": "Astra、Hermes 通过，Pi 未通过",
        "PFP": "Astra、Pi 通过", "PFF": "仅 Astra 通过",
        "FPP": "Hermes、Pi 通过", "FPF": "仅 Hermes 通过",
        "FFP": "仅 Pi 通过", "FFF": "三者均未通过", "pi_incomplete": "Pi 无明确 evaluator 判定",
    }
    group_rows = "\n".join(
        f"| {labels[key]} | {len(groups.get(key, []))} | {task_names(groups.get(key, []))} |"
        for key in ("PPP", "PPF", "PFP", "PFF", "FPP", "FPF", "FFP", "FFF", "pi_incomplete")
    )
    failure_rows = "\n".join(
        f"| {name} | {systems[name]['failure_categories'].get('completed_but_no_pass', 0)} | {systems[name]['failure_categories'].get('model_request_budget', 0)} | {systems[name]['failure_categories'].get('product_error', 0)} |"
        for name in ("astra", "hermes", "pi")
    )
    display_names = {"astra": "Astra", "hermes": "Hermes", "pi": "Pi"}
    time_rows = []
    for key, label, total_formatter, value_formatter in (
        ("e2e_seconds", "端到端", format_hours, format_minutes),
        ("agent_seconds", "Agent 执行", format_hours, format_minutes),
        ("evaluator_seconds", "Evaluator", format_minutes, format_seconds),
        ("orchestration_seconds", "Orchestration/收尾", format_total_duration, format_seconds),
    ):
        for name in ("astra", "hermes", "pi"):
            item = systems[name]["time"][key]
            time_rows.append(
                f"| {label} | {display_names[name]} | {item['n']} | {total_formatter(item['sum'])} | {value_formatter(item['mean'])} | {value_formatter(item['median'])} | {value_formatter(item['p90'])} |"
            )
    visible_token_rows = "\n".join(
        f"| {display_names[name]} | {systems[name]['tokens']['total_visible']['n']} | {systems[name]['tokens']['reported_completed_requests']:,} / {systems[name]['tokens']['missing_usage_completed_requests']:,} | {format_whole(systems[name]['tokens']['input_visible']['sum'])} | {format_whole(systems[name]['tokens']['output_visible']['sum'])} | {format_whole(systems[name]['tokens']['total_visible']['sum'])} | {format_whole(systems[name]['tokens']['total_visible']['median'])} |"
        for name in ("astra", "hermes", "pi")
    )
    pass_token_rows = "\n".join(
        f"| {display_names[name]} | {systems[name]['tokens']['pass_reliable_records']} / {systems[name]['verify'].get('pass', 0)} | {format_whole(systems[name]['tokens']['pass_reliable_total']['sum'])} | {format_whole(systems[name]['tokens']['pass_reliable_total']['mean'])} | {format_whole(systems[name]['tokens']['pass_reliable_total']['median'])} |"
        for name in ("astra", "hermes", "pi")
    )
    pair_rows = []
    for key in ("astra_vs_hermes", "astra_vs_pi", "hermes_vs_pi"):
        pair = summary["pairwise"][key]
        left, _, right = key.partition("_vs_")
        counts = pair["counts"]
        pair_rows.append(
            f"| {left} vs {right} | {pair['eligible_tasks']} | {counts.get('both_pass', 0)} | {counts.get(left + '_only', 0)} | {counts.get(right + '_only', 0)} | {counts.get('neither', 0)} |"
        )
    pi_only = groups.get("FFP", [])
    pi_loses = groups.get("PPF", [])
    return f"""# Astra、Hermes 与 Pi：Toolathlon 108 题对比分析

生成日期：2026-08-14

## 口径

- Astra/Hermes 沿用既有 108 题正式投影；Pi 使用隔离与服务修复后的最终覆盖结果。
- Astra、Hermes 均有 108 个明确 evaluator 结果；Pi 有 104 个明确结果，另有 3 个 `unavailable` 和 1 个 `incomplete`。三方组合不会把这四题算作 Pi 失败。
- 通过与否只以 evaluator 为准。时间、工具调用、模型请求和 token 都是产品整体运行时口径，不是同构 agent loop，效率指标只能描述观测足迹。
- Pi 最终结果不是单一运行批次：Pi 的 effective result 按“基础批次 → 隔离重跑 → 最终服务/审计重跑”的顺序覆盖，同一题以后层完成且 artifact gate 通过的结果为准：

| 最终来源 | 采用题数 | 说明 |
| --- | ---: | --- |
| `toolathlon-pi-108-v1` | 75 | 初始 108 题批次中未被后续有效结果替换的 slot |
| `toolathlon-pi-isolated-rerun-v1` | 25 | 路径访问审计命中题及原基础设施未完成题的隔离重跑 |
| `toolathlon-pi-service-and-audit-8-v3` | 8 | Canvas/WooCommerce 服务修复后的正式重跑，以及 NHL/VLM 扩展审计重跑 |

初始批次使用 `isolated_bind_mount` 映射任务 workspace，但不是空根文件系统容器。后两批使用 Docker sidecar：根文件系统只读，仅任务 workspace 可写，不暴露宿主机 home、宿主机 `/tmp` 或 Docker socket，并启用 `no-new-privileges`。因此，不能把 Pi 的全部 108 个 slot 描述为在完全相同的容器隔离模式下运行；准确口径是审计命中的任务已用增强隔离结果替换，其余初始结果继续保留。

四个没有明确 Pi evaluator 判定的 slot 仍保留原状态：第 38 题无完整 `run.json`；第 53、55、72 题 evaluator 返回 `pass: null`。它们不进入 104 题三方胜负配对，也不被补记为 `no_pass`。

## 实验产品与配置

| 项目 | Astra | Hermes | Pi |
| --- | --- | --- | --- |
| 产品版本 | Linux/AMD64 release build；源码`v0.0.5-4-g844473c68`，commit `844473c68649d8ea43e10b616dc4fbf98e2321e8`；CLI 输出 `astra 0.1.0` | release descriptor`v2026.7.20-63-gf4df260f2`，commit `f4df260f26c93f15694698869f3ea8e965eea301`，project version `0.19.0` | `0.73.1` Linux x64 binary； |
| API 模型 ID | `deepseek-v4-flash` | `deepseek-v4-flash` | `deepseek-v4-flash` |
| 模型版本口径 | DeepSeek-V4-Flash-0731 | DeepSeek-V4-Flash-0731 | DeepSeek-V4-Flash-0731 |
| 模型提供方 | DeepSeek 官方 API，经每次运行独立的本地代理 | 同左 | 同左 |
| 推理配置 | Thinking enabled；`reasoning_effort=max` | 同左 | 同左 |
| Temperature | 发送`temperature=0`；DeepSeek Thinking 模式下该参数不生效 | 同左 | 同左 |
| 产品原生 max turns | Astra 冻结默认值`300` | Hermes 冻结默认值`90` | 未显式设置 |
| 外部统一请求预算 | 每题最多 100 次 product model request；允许第 100 次，拒绝第 101 次 | 同左 | 同左 |
| 实际最高模型请求数 | 100 | 100 | 100 |
| Agent deadline | 按任务采用 R1/R2/R3/R4：1800/2700/3600/5400 秒 | 同左 | 同左 |
| Prompt 口径 | 保留 Astra 原生 system prompt，并输入 Toolathlon 公共 system/task 指令 | 保留 Hermes 原生 system prompt，并输入相同公共指令 | 保留 Pi 原生 system prompt，通过 append 方式输入相同公共指令 |
| 工具范围 | 保留产品内置工具；提供当前任务 的 MCP 工具 | 保留产品内置工具；提供当前任务 的 MCP 工具 | 保留产品内置工具；提供当前任务 的 MCP 工具 |

三种产品的“turn”不是同构指标：Astra 会产生内部规划、反思和非流式请求，Hermes 主要使用携带工具 schema 的流式主循环，Pi 还包含其原生压缩与生命周期行为。因此，本实验以运行代理观测到的 `model_request.started` 作为统一请求预算和 step 统计，不把产品原生 max turns 或模型请求数直接解释为用户可见对话回合。

## 基础运行环境

| 环境项 | 配置 |
| --- | --- |
| 数据集 | Toolathlon，固定 108 题；严格三方比较采用 Pi 也有明确 evaluator 判定的 104 题 |
| Host OS | Ubuntu 22.04.5 LTS，Linux`5.15.0-186-generic`，UTC |
| CPU | Intel Xeon Platinum 8255C @ 2.50 GHz，x86_64，8 vCPU |
| 内存与 Swap | Linux MemTotal 7.75 GiB（名义配置 8 GiB）；8 GiB swap，swappiness 10，关闭 zram |
| 虚拟化 | Oracle/Vagrant 虚拟机 |
| 容器运行时 | rootful Docker Engine 29.1.3，cgroup v2，systemd cgroup driver，overlayfs |
| 任务镜像 | `lockon0927/toolathlon-task-image@sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f` |
| 单任务资源上限 | 8 CPU、8 GiB RAM、8 GiB swap |
| Kubernetes 工具 | Kind v0.20.0；kubectl v1.34.1 |
| 外部应用状态 | 由任务 preprocess 恢复；Canvas、WooCommerce、Poste、MatrixOne 和 Kind 等使用共享部署，并非每题重新部署整套服务 |
| 网络边界 | 未统一关闭公开互联网出口；任务级 MCP 限于当前任务，但终端、fetch、浏览器或产品内置工具仍可能访问公开网络 |
| Evaluator | 使用 Toolathlon 每题原生 evaluator，在 Agent 终止后独立执行 |

这里记录的是实验冻结时的环境；实验结束后宿主机内核或服务状态的变化不追溯修改历史运行口径。三种产品的内部 turn 定义不同，因此报告统一使用代理观测到的 `model_request.started`，不把它重述为可直接比较的 Agent 回合数

## 任务完成结果

| 产品 | pass | no-pass | 未完成 | 按 108 题通过率 | 已测评题通过率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Astra | {systems['astra']['verify'].get('pass', 0)} | {systems['astra']['verify'].get('no_pass', 0)} | 0 | {systems['astra']['pass_rate_all_108']:.2%} | {systems['astra']['pass_rate_evaluated']:.2%} |
| Hermes | {systems['hermes']['verify'].get('pass', 0)} | {systems['hermes']['verify'].get('no_pass', 0)} | 0 | {systems['hermes']['pass_rate_all_108']:.2%} | {systems['hermes']['pass_rate_evaluated']:.2%} |
| Pi 0.73.1 | {systems['pi']['verify'].get('pass', 0)} | {systems['pi']['verify'].get('no_pass', 0)} | {systems['pi']['verify'].get('missing', 0) + systems['pi']['verify'].get('unavailable', 0)} | {systems['pi']['pass_rate_all_108']:.2%} | {systems['pi']['pass_rate_evaluated']:.2%} |

### 三方逐题组合

`P/F` 顺序固定为 Astra/Hermes/Pi。

| 结果组 | 题数 | 任务 |
| --- | ---: | --- |
{group_rows}

最有区分度的是仅单一产品通过的任务。Pi 在 Astra 和 Hermes 都失败时通过 {len(pi_only)} 题：{task_names(pi_only)}。反向地，Astra 和 Hermes 都通过但 Pi 未通过 {len(pi_loses)} 题：{task_names(pi_loses)}。

### 两两配对

| 配对 | 可比较题数 | 双方通过 | 仅左侧通过 | 仅右侧通过 | 双方未通过 |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(pair_rows)}

Pi 与另外两者的配对只覆盖 104 个有明确 Pi evaluator 判定的题；因此不能把第 38、53、55、72 题加入任何单方胜负。

在共同可比较的 104 题上，Pi 相对 Astra 是 20 个 Pi-only 对 4 个 Astra-only，净胜 16 题；相对 Hermes 是 17 个 Pi-only 对 9 个 Hermes-only，净胜 8 题。这是固定 benchmark 上的逐题描述，不是从更大总体抽样得到的显著性结论。

## No-pass 原因

| 产品 | 完成但 evaluator 未通过 | 模型请求预算 | 产品执行错误 |
| --- | ---: | ---: | ---: |
{failure_rows}

Astra 的预算终止占失败的重要部分；Hermes 的失败主要发生在正常结束后未满足 evaluator。Pi 同时存在完成后精确性/完整性失败与预算耗尽，另有最终审计重跑记录到的产品执行错误。这里是直接终态分类，不推断模型内部原因。

## 时间消耗

Astra、Hermes 均统计 108 个正式结果；Pi 统计 107 个有完整 `run.json` 的 effective run，其中包括 3 个 evaluator `unavailable` 的运行，但不包括第 38 题的基础设施未完成 attempt。

| 阶段 | 产品 | 样本数 | 总计 | 平均 | 中位数 | P90 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(time_rows)}

Pi 的端到端和 Agent 时间中位数最低，分别为 4.83 和 4.07 分钟；Hermes 分别为 7.10 和 5.21 分钟，Astra 为 10.16 和 9.10 分钟。但 Pi 的 P90 端到端时间高于 Hermes，说明 Pi 的长尾任务仍然明显。上述时间包含通过与未通过任务，不能解释为“完成同样成功结果所需时间”。`orchestration` 是端到端减去 Agent 和 evaluator 后的剩余时间，包含准备、adapter 收尾及 post-terminal model drain，并非纯环境准备时间。

## 工具调用

| 指标 | Astra | Hermes | Pi |
| --- | ---: | ---: | ---: |
| 有工具计数的运行 | {systems['astra']['tools']['calls']['n']} | {systems['hermes']['tools']['calls']['n']} | {systems['pi']['tools']['calls']['n']} |
| 工具调用总数 | {format_compact(systems['astra']['tools']['calls']['sum'])} | {format_compact(systems['hermes']['tools']['calls']['sum'])} | {format_compact(systems['pi']['tools']['calls']['sum'])} |
| 单运行平均 | {format_compact(systems['astra']['tools']['calls']['mean'])} | {format_compact(systems['hermes']['tools']['calls']['mean'])} | {format_compact(systems['pi']['tools']['calls']['mean'])} |
| 单运行中位数 | {format_compact(systems['astra']['tools']['calls']['median'])} | {format_compact(systems['hermes']['tools']['calls']['median'])} | {format_compact(systems['pi']['tools']['calls']['median'])} |
| 单运行 P90 | {format_fixed(systems['astra']['tools']['calls']['p90'], 1)} | {format_fixed(systems['hermes']['tools']['calls']['p90'], 1)} | {format_fixed(systems['pi']['tools']['calls']['p90'], 1)} |
| 失败工具事件总数 | {format_compact(systems['astra']['tools']['failures']['sum'])} | {format_compact(systems['hermes']['tools']['failures']['sum'])} | {format_compact(systems['pi']['tools']['failures']['sum'])} |

常见终态工具：

- Astra：{format_tools(systems['astra']['tools']['top_terminal_tools'])}。
- Hermes：{format_tools(systems['hermes']['tools']['top_terminal_tools'])}。
- Pi：{format_tools(systems['pi']['tools']['top_terminal_tools'])}。

三者的工具工作负担中位数接近，但工具名称和封装并不等价。Hermes 的 `terminal`、Pi 的 `bash`、任务 MCP 的 `terminal-run_command` 是不同传输层；Hermes adapter 没有把本批 effective run 的工具终态归类为 `failed`，因此失败事件 0 不表示所有工具在语义上成功。Pi 的 247 个失败事件也可能包含重试后恢复的调用，不能直接等同于任务失败。

## 模型请求

| 指标 | Astra | Hermes | Pi |
| --- | ---: | ---: | ---: |
| 统计运行数 | {systems['astra']['executed']} | {systems['hermes']['executed']} | {systems['pi']['executed']} |
| 模型请求 started | {format_compact(systems['astra']['requests']['model_requests_started']['sum'])} | {format_compact(systems['hermes']['requests']['model_requests_started']['sum'])} | {format_compact(systems['pi']['requests']['model_requests_started']['sum'])} |
| 模型请求 completed event | {format_compact(systems['astra']['requests']['model_requests_completed']['sum'])} | {format_compact(systems['hermes']['requests']['model_requests_completed']['sum'])} | {format_compact(systems['pi']['requests']['model_requests_completed']['sum'])} |
| provider 失败请求 | {format_compact(systems['astra']['requests']['model_requests_failed']['sum'])} | {format_compact(systems['hermes']['requests']['model_requests_failed']['sum'])} | {format_compact(systems['pi']['requests']['model_requests_failed']['sum'])} |
| 单运行 started 平均 | {format_compact(systems['astra']['requests']['model_requests_started']['mean'])} | {format_compact(systems['hermes']['requests']['model_requests_started']['mean'])} | {format_compact(systems['pi']['requests']['model_requests_started']['mean'])} |
| 单运行 started 中位数 | {format_compact(systems['astra']['requests']['model_requests_started']['median'])} | {format_compact(systems['hermes']['requests']['model_requests_started']['median'])} | {format_compact(systems['pi']['requests']['model_requests_started']['median'])} |
| 单运行 started P90 | {format_compact(systems['astra']['requests']['model_requests_started']['p90'])} | {format_compact(systems['hermes']['requests']['model_requests_started']['p90'])} | {format_compact(systems['pi']['requests']['model_requests_started']['p90'])} |
| 触及 100 请求上限 | {systems['astra']['request_limit_reached']} | {systems['hermes']['request_limit_reached']} | {systems['pi']['request_limit_reached']} |
| 因请求预算 no-pass | {systems['astra']['failure_categories'].get('model_request_budget', 0)} | {systems['hermes']['failure_categories'].get('model_request_budget', 0)} | {systems['pi']['failure_categories'].get('model_request_budget', 0)} |
| 流式请求 | {format_count_share(systems['astra']['requests']['stream_requests']['sum'], systems['astra']['requests']['model_requests_started']['sum'])} | {format_count_share(systems['hermes']['requests']['stream_requests']['sum'], systems['hermes']['requests']['model_requests_started']['sum'])} | {format_count_share(systems['pi']['requests']['stream_requests']['sum'], systems['pi']['requests']['model_requests_started']['sum'])} |
| 非流式请求 | {format_count_share(systems['astra']['requests']['non_stream_requests']['sum'], systems['astra']['requests']['model_requests_started']['sum'])} | {format_count_share(systems['hermes']['requests']['non_stream_requests']['sum'], systems['hermes']['requests']['model_requests_started']['sum'])} | {format_count_share(systems['pi']['requests']['non_stream_requests']['sum'], systems['pi']['requests']['model_requests_started']['sum'])} |

Pi 的模型请求总量和中位数最低；Astra 总请求数分别比 Hermes 和 Pi 高 59.08% 和 101.50%。但请求数不是用户可见 turn：Astra 的统计包含大量内部无工具非流式请求，Hermes 和 Pi 更接近携带工具 schema 的流式主循环。Pi 触及上限的 4 个运行中，2 个形成 `no_pass`，另有第 55、72 题的 evaluator 返回 `pass: null`；因此“触及上限”和“因预算 no-pass”不是同一计数。

## Token 数据

### 保守可靠记录

若一个 effective run 的 completed response 存在缺失 usage，该运行不进入本表：

| 指标 | Astra | Hermes | Pi |
| --- | ---: | ---: | ---: |
| 有完整 provider usage 的运行 | {systems['astra']['tokens']['reliable_records']} / {systems['astra']['executed']} | {systems['hermes']['tokens']['reliable_records']} / {systems['hermes']['executed']} | {systems['pi']['tokens']['reliable_records']} / {systems['pi']['executed']} |
| 输入 token 总量 | {format_whole(systems['astra']['tokens']['reliable_input']['sum'])} | {format_whole(systems['hermes']['tokens']['reliable_input']['sum'])} | {format_whole(systems['pi']['tokens']['reliable_input']['sum'])} |
| 输出 token 总量 | {format_whole(systems['astra']['tokens']['reliable_output']['sum'])} | {format_whole(systems['hermes']['tokens']['reliable_output']['sum'])} | {format_whole(systems['pi']['tokens']['reliable_output']['sum'])} |
| total token 总量 | {format_whole(systems['astra']['tokens']['reliable_total']['sum'])} | {format_whole(systems['hermes']['tokens']['reliable_total']['sum'])} | {format_whole(systems['pi']['tokens']['reliable_total']['sum'])} |
| 单运行 total 中位数 | {format_whole(systems['astra']['tokens']['reliable_total']['median'])} | {format_whole(systems['hermes']['tokens']['reliable_total']['median'])} | {format_whole(systems['pi']['tokens']['reliable_total']['median'])} |

总量覆盖的运行数不同，不能把总量差直接解释为成本或效率差异。Pi 的可靠覆盖率最高，但其 input 中包含 provider 单独报告的 cache-read token；Astra 和 Hermes 的产品请求结构及缓存计量边界也不同。

### 全部可见 token 下界

下界口径保留每个完整运行中已经明确上报的 usage；缺失 usage 的 completed request 保持未知，不补零：

| 产品 | 运行数 | 已上报 / 缺 usage 的 completed 请求 | 输入 token 下界 | 输出 token 下界 | total token 下界 | 单运行 total 中位数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{visible_token_rows}

Pi 可见 cache-read token 为 {format_whole(systems['pi']['tokens']['cache_read_visible']['sum'])}，占其可见 input 的 {format_percent_floor(systems['pi']['tokens']['cache_read_visible']['sum'], systems['pi']['tokens']['input_visible']['sum'])}，且已经包含在 input/total 中，不能再次相加。Astra 完整架构包含内部非流式请求；双产品报告另提供“排除 Astra `stream=false && request_tool_count=0` 请求”的辅助口径。本三产品表保留各产品完整代理可见足迹，不使用不对称过滤结果给产品排序。

### Pass 任务的可靠 Token

| 产品 | 有可靠 token 的 pass 任务 | total token 总量 | 单任务平均 | 单任务中位数 |
| --- | ---: | ---: | ---: | ---: |
{pass_token_rows}

该表中三者通过的任务集合不同，不能据此计算单位成功成本。严格 token 对比还需要限制到三者共同 pass、三侧 usage 都完整的同一任务集合，并同时处理工具 schema、缓存和内部请求边界差异。

## 综合结论

1. **结果质量：Pi 当前已确认通过数最高，但覆盖尚不完整。** Pi 已确认 77 pass，高于 Hermes 的 72 和 Astra 的 61；按全部 108 题是 71.30%，按 104 个明确结果是 74.04%。第 38、53、55、72 题没有明确 Pi evaluator 判定，不能把当前结果表述为完整的 108 题最终排名。
2. **逐题结果不是包含关系。** 在104个三方可比较任务中，Pi 相对 Astra 净胜16题、相对 Hermes 净胜8题；Pi 独过9题，但也有2题由 Astra/Hermes 共同通过而 Pi 未通过。产品主循环、自检和工具执行策略都会改变结果。
3. **Astra 的请求预算消耗最突出。** Astra 有23题触及100请求上限，其中20题因预算 no-pass；Hermes分别为3和3，Pi为4和2。Astra模型请求中位数33.5，也高于Hermes的20和Pi的16。
4. **Pi 的典型运行更短，但存在长尾。** Pi Agent 时间中位数4.07分钟，为三者最低；其端到端 P90 为22.39分钟，高于Hermes的19.63分钟。不能仅用中位数概括所有任务。
5. **工具调用总量接近。** 三者单运行工具调用中位数为31.5、32.5和29。失败工具事件的采集和分类方式不同，不能直接作为产品可靠性排名。
6. **Token 只能描述架构足迹。** Pi和Astra的可靠记录 total 中位数接近，Hermes更高；但三者的工具 schema、缓存计量、上下文组织和内部请求不同，不能将差异直接表述为模型 token 效率或成本优势。
7. **Pi 的 effective result 混合了三个批次。** 路径审计命中题已由增强隔离重跑替换，服务异常题采用最终服务重跑；其余初始结果继续保留。环境修复和权限边界必须作为解释结果的一部分。
8. **能力归因必须以可观察证据为限。** Pi 的优势案例可归因到 evaluator 验证的产物完整性、步骤执行和终态自检，但不能从轨迹结果直接推断未观测的“推理能力”。

## 附件

- Pi 独立汇总：[`pi-toolathlon-108-task-comparison.md`](pi-toolathlon-108-task-comparison.md)
- 三产品逐 slot 数据：[`astra-hermes-pi-toolathlon-108-task-results.csv`](astra-hermes-pi-toolathlon-108-task-results.csv)
- 三产品机器可读汇总：[`astra-hermes-pi-toolathlon-108-task-summary.json`](astra-hermes-pi-toolathlon-108-task-summary.json)
- 原 Astra/Hermes 逐题原因：[`astra-hermes-paired-outcome-cause-analysis.md`](astra-hermes-paired-outcome-cause-analysis.md)
- 生成脚本：[`generate_astra_pi_hermes_comparison.py`](generate_astra_pi_hermes_comparison.py)
"""


def main() -> None:
    pi = pi_rows()
    ah = load_astra_hermes_rows()
    system_order = {"astra": 0, "hermes": 1, "pi": 2}
    all_rows = sorted(
        ah + pi,
        key=lambda row: (int(row["position"]), system_order[str(row["system"])]),
    )
    groups, task_rows = outcome_groups(all_rows)

    systems = {}
    for system in ("astra", "hermes", "pi"):
        selected = [row for row in all_rows if row["system"] == system]
        systems[system] = summarize_system(selected)

    summary = {
        "scope": {
            "tasks": 108,
            "systems": 3,
            "slots": 324,
            "evaluated_slots": sum(item["evaluated"] for item in systems.values()),
            "pi_unresolved_positions": [38, 53, 55, 72],
        },
        "effective_run_precedence": [
            "toolathlon-pi-108-v1",
            "toolathlon-pi-isolated-rerun-v1",
            "toolathlon-pi-service-and-audit-8-v3",
        ],
        "systems": systems,
        "three_way_outcomes": groups,
        "pairwise": {
            "astra_vs_hermes": pairwise(task_rows, "astra", "hermes"),
            "astra_vs_pi": pairwise(task_rows, "astra", "pi"),
            "hermes_vs_pi": pairwise(task_rows, "hermes", "pi"),
        },
    }
    pi_summary = {
        "scope": summary["scope"],
        "effective_run_precedence": summary["effective_run_precedence"],
        "system": systems["pi"],
        "tasks": [
            {
                key: row.get(key)
                for key in (
                    "position", "task_id", "state", "verify_status", "run_validity",
                    "terminal_status", "failure_category", "run_id", "source", "run_directory",
                )
            }
            for row in pi
        ],
    }

    write_csv(OUT_DIR / "pi-toolathlon-108-task-results.csv", pi)
    write_csv(OUT_DIR / "astra-hermes-pi-toolathlon-108-task-results.csv", all_rows)
    with (OUT_DIR / "pi-toolathlon-108-task-summary.json").open("w", encoding="utf-8") as handle:
        json.dump(pi_summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with (OUT_DIR / "astra-hermes-pi-toolathlon-108-task-summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    (OUT_DIR / "pi-toolathlon-108-task-comparison.md").write_text(
        pi_markdown(pi, pi_summary), encoding="utf-8"
    )
    (OUT_DIR / "astra-hermes-pi-toolathlon-108-task-comparison.md").write_text(
        comparison_markdown(summary), encoding="utf-8"
    )
    print(json.dumps({"pi": systems["pi"], "three_way_counts": {key: len(value) for key, value in groups.items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
