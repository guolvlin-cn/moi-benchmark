#!/usr/bin/env python3
"""Render the Hermes-current versus Astra-56 comparison as Markdown."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path(__file__).resolve().parent
SUMMARY_PATH = OUTPUT_DIR / "hermes-vs-astra-current-summary-v1.json"
HERMES_CSV = OUTPUT_DIR / "hermes-c0-current-64-tasks-v1.csv"
MATCHED_CSV = OUTPUT_DIR / "hermes-vs-astra-matched-46-tasks-v1.csv"
REPORT_PATH = OUTPUT_DIR / "hermes-current-vs-astra56-comparison-v1.md"
ASTRA_REPORT = (
    Path(__file__).resolve().parents[3]
    / "astra-c0-all-jobs"
    / "2026-07-29__19-36-33"
    / "analysis"
    / "v1"
    / "astra-c0-56-tasks-statistics-v1.md"
)

CATEGORY_LABELS = {
    "clean_verifier_pass": "正常完成且通过",
    "abnormal_verifier_pass": "超时终止但通过",
    "llm_provider_unresponsive": "LLM/Provider 明确无响应",
    "agent_deadline_zero": "Driver deadline，任务未完成",
    "task_requirement_failure": "任务交付或产物错误",
    "performance_requirement_failure": "性能门槛未满足",
    "background_lifecycle_failure": "后台服务被 gateway cleanup 清理",
    "verifier_infra_failure": "Verifier 基础设施失败",
    "deadline_adapter_no_verifier": "Deadline 后 adapter 异常，无 Verifier",
    "cleanup_adapter_no_verifier": "Cleanup/adapter 异常，无 Verifier",
    "launcher_infra_no_verifier": "Launcher/环境异常，无 Verifier",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def pct(value: float, denominator: float) -> str:
    return f"{value / denominator * 100:.2f}%" if denominator else "—"


def integer(value: Any) -> str:
    if value in (None, ""):
        return "—"
    return f"{float(value):,.0f}"


def decimal(value: Any, digits: int = 2) -> str:
    if value in (None, ""):
        return "—"
    return f"{float(value):,.{digits}f}"


def minutes(seconds: Any) -> str:
    if seconds in (None, ""):
        return "—"
    return f"{float(seconds) / 60:.2f}"


def hours(seconds: Any) -> str:
    if seconds in (None, ""):
        return "—"
    return f"{float(seconds) / 3600:.3f}"


def reward(value: str) -> str:
    return value if value else "—"


def result_link(row: dict[str, str], label: str = "result") -> str:
    return f'[{label}](<{row["trial_path"]}/result.json>)'


def task_link(row: dict[str, str]) -> str:
    return f'[{row["task_id"]}](<{row["trial_path"]}/result.json>)'


def matched_task_link(row: dict[str, str]) -> str:
    return f'[{row["task_id"]}](<{row["hermes_trial_path"]}/result.json>)'


def task_list(rows: list[dict[str, str]], transition: str) -> str:
    selected = [
        matched_task_link(row)
        for row in rows
        if row["reward_transition"] == transition
    ]
    return "、".join(selected) if selected else "—"


def top_rows(
    rows: list[dict[str, str]], field: str, limit: int = 8
) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: float(row[field] or -1),
        reverse=True,
    )[:limit]


def main() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    hermes_rows = read_csv(HERMES_CSV)
    matched_rows = read_csv(MATCHED_CSV)

    hermes = summary["hermes_current"]
    h_counts = hermes["counts"]
    h_metrics = hermes["metrics"]
    h_reward = hermes["by_reward"]
    matched = summary["matched"]
    astra = summary["astra_v1"]
    astra_counts = astra["counts"]
    astra_metrics = astra["overall_stats"]
    astra_verifier = astra["verifier_aggregate"]

    lines: list[str] = []
    add = lines.append

    add("# Hermes C0 当前已完成任务与 Astra 56 项交叉统计（V1）")
    add("")
    add(f"- Hermes 根目录：`{Path(__file__).resolve().parents[2]}`")
    add(f"- Hermes 快照截止：`{summary['snapshot_cutoff']}`")
    add("- Hermes 已终态：64；另有 `regex-chess` 在快照时仍运行，未纳入")
    add(f"- Astra 对照：[Astra C0 56 项 V1](<{ASTRA_REPORT}>)")
    add("- 主比较样本：Hermes 64 与 Astra 56 的 46 个同任务交集")
    add("- 数据来源：trial `result.json`、Hermes session/run/events、controller、CTRF，以及 Astra V1 CSV/JSON")
    add("")

    add("## 1. 执行摘要")
    add("")
    add(
        f"- Hermes 当前 64 个终态任务中，`reward=1` 为 **35/64（{pct(35, 64)}）**；"
        f"在 57 个已有 reward 的任务中为 **35/57（{pct(35, 57)}）**。"
    )
    add(
        f"- Hermes 严格端到端成功为 **33/64（{pct(33, 64)}）**；"
        f"Agent 正常终态为 **49/64（{pct(49, 64)}）**。"
    )
    add(
        "- Hermes 有 22 个零分和 7 个无 reward 异常。22 个零分中只有 "
        "**1 个**具有明确 LLM/provider 无响应证据；失败主因已从 Astra 的传输中断转为"
        "任务未完成、deadline、后台进程生命周期和评估基础设施问题。"
    )
    add(
        f"- 在 46 个同任务交集上，Astra 通过 **26/46（{pct(26, 46)}）**，"
        f"Hermes 通过 **31/46（{pct(31, 46)}）**，但 Hermes 有 6 项未评分。"
        f"若只看双方都有 Hermes reward 的 40 项，Astra 为 **24/40（{pct(24, 40)}）**，"
        f"Hermes 为 **31/40（{pct(31, 40)}）**。"
    )
    add(
        f"- 同任务交集的严格 E2E 成功：Astra **20/46（{pct(20, 46)}）**，"
        f"Hermes **30/46（{pct(30, 46)}）**。"
    )
    add(
        "- 同任务交集上，Hermes 累计 E2E 时间比 Astra 少 **31.72%**，"
        "但总 token 为 Astra 的 **2.97 倍**；fresh input 基本持平，"
        "增量主要来自 Hermes 的 cache-read（3.64 倍）。"
    )
    add(
        "- 两边所有纳入项均为 `formal_score_eligible=false`。"
        "本文只能解释探索性运行结果，不能作为正式 C0 主结果。"
    )
    add("")

    add("## 2. 范围与可比口径")
    add("")
    add("### 2.1 三个样本集合")
    add("")
    add("| 集合 | 任务数 | 用途 | 主要偏差 |")
    add("| --- | ---: | --- | --- |")
    add("| Hermes 当前终态快照 | 64 | 研究 Hermes 当前完成情况 | 进行中批次的时间截面，非随机样本 |")
    add("| Astra V1 非重跑样本 | 56 | 复用既有基线 | 从 89 项排除 33 个必须完整重跑任务后的条件样本 |")
    add("| 同任务交集 | 46 | 主交叉比较 | 控制任务组成，但模型、turn budget、timeout 和 runner 仍不同 |")
    add("")
    add(
        "Hermes 当前 64 项中，有 18 项属于 Astra V1 排除的“必须从头重跑”集合；"
        "Astra 56 项中还有 10 项在 Hermes 快照时尚未终态。因此 64 对 56 的全样本通过率"
        "只能描述各自快照，不能直接解释为 Agent 优劣。"
    )
    add("")
    add("- Hermes 已完成、但不在 Astra 56 中的 18 项：`" + "`, `".join(summary["scope"]["hermes_only_vs_astra56"]) + "`。")
    add("- Astra 56 中尚未进入 Hermes 终态的 10 项：`" + "`, `".join(summary["scope"]["astra56_not_yet_terminal_in_hermes"]) + "`。")
    add("")

    add("### 2.2 指标定义")
    add("")
    add("| 指标 | 统一判定 |")
    add("| --- | --- |")
    add("| Verifier 功能通过 | `reward=1`，不要求 Agent 正常退出 |")
    add("| Agent 正常终态 | `product_terminal_status=completed && rc=0` |")
    add("| 严格端到端成功 | Agent 正常终态且 `reward=1` |")
    add("| Input token | `fresh_input + cache_read` |")
    add("| Total token | `input + output`；reasoning 是 output 的补充分拆，不重复相加 |")
    add("| 工具调用 | Astra 为完成/失败 step event；Hermes 为 `tool.completed` |")
    add("| 失败工具返回 | Astra `ToolCallFailed`；Hermes `tool.completed.error=true` |")
    add("| 时间 | 每任务阶段时间累计；不是并发批次 wall-clock |")
    add("")
    add(
        "轮次与工具失败是近似对齐而非同源埋点：Astra 使用 `StepStarted`/中断记录，"
        "Hermes 使用 session `api_call_count`；Astra 的 bash 非零返回可能不记 `ToolCallFailed`，"
        "Hermes 的 event error 也不等价于所有非零子进程状态。"
    )
    add("")

    add("## 3. Hermes 当前 64 项结果")
    add("")
    add("### 3.1 完成与评分")
    add("")
    add("| 口径 | 数量 | 比例 |")
    add("| --- | ---: | ---: |")
    add(f"| Reward=1 / 全部终态 | 35/64 | {pct(35, 64)} |")
    add(f"| Reward=1 / 已评分 | 35/57 | {pct(35, 57)} |")
    add(f"| Reward=0 | 22/64 | {pct(22, 64)} |")
    add(f"| Reward 缺失 | 7/64 | {pct(7, 64)} |")
    add(f"| Agent completed/rc0 | 49/64 | {pct(49, 64)} |")
    add(f"| 严格 E2E 成功 | 33/64 | {pct(33, 64)} |")
    add(f"| 异常终止但通过 | 2/64 | {pct(2, 64)} |")
    add("| 正式 C0 合格 | 0/64 | 0.00% |")
    add("")
    add("| Product 终态 | 总数 | Reward=1 | Reward=0 | 无 Reward |")
    add("| --- | ---: | ---: | ---: | ---: |")
    add("| `completed/rc0` | 49 | 33 | 16 | 0 |")
    add("| `timeout/rc124` | 7 | 2 | 5 | 0 |")
    add("| `failed/rc2` | 1 | 0 | 1 | 0 |")
    add("| `adapter_infra_error/rc null` | 7 | 0 | 0 | 7 |")
    add("")
    add(
        "两个“异常终止但通过”是 `model-extraction-relu-logits` 和 "
        "`path-tracing-reverse`：都达到 driver deadline，但 timeout 前留下的 artifact "
        "通过了 Verifier。功能 reward 可以保留，严格 E2E 不计成功。"
    )
    add("")

    add("### 3.2 Verifier")
    add("")
    add(
        f"- 56/64 生成 CTRF；合计 **{hermes['verifier']['tests']} tests，"
        f"{hermes['verifier']['passed']} pass、{hermes['verifier']['failed']} fail**。"
    )
    add("- Reward=1：130/130 tests。")
    add("- Reward=0 且有 CTRF：22/63 tests。")
    add(
        "- 8 项无 CTRF：7 个无 reward 异常，以及 `pytorch-model-recovery`；"
        "后者在 Verifier 下载依赖时出现网络/SSL 故障。"
    )
    add("")

    add("### 3.3 时间")
    add("")
    add("| 阶段 | 覆盖 | 累计小时 | 均值分钟 | 中位数分钟 | P90 分钟 | 最大分钟 |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for label, key in [
        ("端到端", "e2e_s"),
        ("环境初始化", "environment_setup_s"),
        ("Agent 初始化", "agent_setup_s"),
        ("Agent 执行", "agent_execution_s"),
        ("Verifier", "verifier_s"),
    ]:
        metric = h_metrics[key]
        add(
            f"| {label} | {metric['n']}/64 | {hours(metric['sum'])} | "
            f"{minutes(metric['mean'])} | {minutes(metric['median'])} | "
            f"{minutes(metric['p90'])} | {minutes(metric['max'])} |"
        )
    add("")
    add("端到端累计为 **21.842 task-hours**；Agent 执行累计 **20.289 agent-hours**。")
    add("")

    add("E2E 时间最高的任务：")
    add("")
    add("| 任务 | Reward | Product | E2E 分钟 | Agent 分钟 | 类别 |")
    add("| --- | ---: | --- | ---: | ---: | --- |")
    for row in top_rows(hermes_rows, "e2e_s", 8):
        add(
            f"| {task_link(row)} | {reward(row['reward'])} | "
            f"`{row['product_terminal_status']}/rc{row['product_return_code'] or 'null'}` | "
            f"{minutes(row['e2e_s'])} | {minutes(row['agent_execution_s'])} | "
            f"{CATEGORY_LABELS.get(row['outcome_category'], row['outcome_category'])} |"
        )
    add("")

    add("### 3.4 Token、轮次与工具")
    add("")
    add("| 指标 | 覆盖 | 累计 | 均值 | 中位数 | P90 |")
    add("| --- | ---: | ---: | ---: | ---: | ---: |")
    for label, key in [
        ("Fresh input", "fresh_input_tokens"),
        ("Cache-read", "cache_tokens"),
        ("Input（含 cache）", "input_tokens"),
        ("Output", "output_tokens"),
        ("总 token", "total_tokens"),
        ("API/Agentic 轮次", "api_calls"),
        ("工具完成返回", "tool_calls"),
        ("失败工具返回", "tool_calls_failed"),
    ]:
        metric = h_metrics[key]
        add(
            f"| {label} | {metric['n']}/64 | {integer(metric['sum'])} | "
            f"{integer(metric['mean'])} | {integer(metric['median'])} | "
            f"{decimal(metric['p90'], 1)} |"
        )
    add("")
    add(
        f"- Cache-read 占 input 的 **{pct(h_metrics['cache_tokens']['sum'], h_metrics['input_tokens']['sum'])}**。"
    )
    add(
        f"- Reasoning token 共 {integer(h_metrics['reasoning_tokens']['sum'])}；"
        "它已包含在 output 口径内，不再加入 total。"
    )
    add(
        f"- 工具事件失败率为 **219/2,233（{pct(219, 2233)}）**；"
        f"工具累计执行时间约 **{hours(h_metrics['tool_duration_s']['sum'])} 小时**。"
    )
    add(
        "- 63/64 有 session/token；`prove-plus-comm` 在 session 建立前失败。"
        "美元成本没有可靠记录，`estimated_cost_usd=0` 不能解释为实际成本为零。"
    )
    add("")
    add("| 工具 | 完成返回 | 失败返回 | 事件失败率 |")
    add("| --- | ---: | ---: | ---: |")
    tool_counts = hermes["tool_call_counts"]
    failed_counts = hermes["failed_tool_call_counts"]
    for name, count in list(tool_counts.items())[:10]:
        failed = int(failed_counts.get(name, 0))
        add(f"| `{name}` | {count:,} | {failed:,} | {pct(failed, count)} |")
    add("")

    add("按 Reward 分组的资源投入：")
    add("")
    add("| 分组 | 任务 | E2E 小时 | Agent 小时 | 总 token | API 轮次 | 工具 | 失败工具 | Tests |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for label, key in [
        ("Reward=1", "reward1"),
        ("Reward=0", "reward0"),
        ("Reward 缺失", "unscored"),
        ("严格 E2E 成功", "strict_e2e_success"),
    ]:
        group = h_reward[key]
        v = group["verifier"]
        add(
            f"| {label} | {group['n']} | {hours(group['e2e_s']['sum'])} | "
            f"{hours(group['agent_execution_s']['sum'])} | {integer(group['total_tokens']['sum'])} | "
            f"{integer(group['api_calls']['sum'])} | {integer(group['tool_calls']['sum'])} | "
            f"{integer(group['tool_calls_failed']['sum'])} | {v['passed']}/{v['tests']} |"
        )
    add("")
    add(
        "31 个非严格成功任务消耗约 **53.34M token，占可观测总 token 的 67.99%**。"
        "因此不能把零分或未评分任务当作“零资源失败”。"
    )
    add("")

    add("总 token 最高的任务：")
    add("")
    add("| 任务 | Reward | 总 token | Fresh | Cache | Output | API 轮次 | 工具 |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in top_rows(hermes_rows, "total_tokens", 10):
        add(
            f"| {task_link(row)} | {reward(row['reward'])} | {integer(row['total_tokens'])} | "
            f"{integer(row['fresh_input_tokens'])} | {integer(row['cache_tokens'])} | "
            f"{integer(row['output_tokens'])} | {integer(row['api_calls'])} | "
            f"{integer(row['tool_calls'])} |"
        )
    add("")

    add("## 4. Hermes 失败与异常根因")
    add("")
    add("### 4.1 分类总表")
    add("")
    add("| 类别 | 数量 | 是否计分 | 是否明确 LLM 连接问题 | 建议 |")
    add("| --- | ---: | --- | --- | --- |")
    category_rows = [
        ("clean_verifier_pass", 33, "Reward=1", "否", "保留"),
        ("abnormal_verifier_pass", 2, "Reward=1", "否", "保留功能结果；严格 E2E 可重跑"),
        ("llm_provider_unresponsive", 1, "Reward=0", "是", "Provider 恢复后完整重跑"),
        ("agent_deadline_zero", 5, "Reward=0", "无明确证据", "若 deadline 是协议预算则保留；否则统一配置后重跑"),
        ("task_requirement_failure", 10, "Reward=0", "否", "保留真实零分"),
        ("performance_requirement_failure", 1, "Reward=0", "否", "保留真实零分"),
        ("background_lifecycle_failure", 4, "Reward=0", "否", "改为独立 daemon 后完整重跑"),
        ("verifier_infra_failure", 1, "Reward=0", "否", "优先重跑 Verifier"),
        ("deadline_adapter_no_verifier", 2, "无 Reward", "否", "完整重跑并保留明确 timeout 终态"),
        ("cleanup_adapter_no_verifier", 4, "无 Reward", "否", "完整重跑取得评分"),
        ("launcher_infra_no_verifier", 1, "无 Reward", "否", "修复 launcher 后完整重跑"),
    ]
    for key, count, scored, llm, action in category_rows:
        add(f"| {CATEGORY_LABELS[key]} | {count} | {scored} | {llm} | {action} |")
    add("")

    add("### 4.2 明确的 LLM/provider 无响应只有 1 项")
    add("")
    add(
        "`adaptive-rejection-sampler` 的 driver 明确记录 "
        "`Provider has been unresponsive ... for 5 consecutive stale attempts`，"
        "这是当前唯一可以严格计为 LLM/provider 无返回的失败。"
        "它运行约 93 分钟后失败，未生成 `ars.R`。"
        f" [driver](<{Path(__file__).resolve().parents[2]}/2026-07-30__12-02-21/"
        "adaptive-rejection-sampler__RUDgwZK/agent/hermes-driver.stdout.txt:1>)"
    )
    add("")
    add(
        "`gpt2-codegolf` 在最后工具完成后出现长时间无事件，可能与等待下一次模型返回有关，"
        "但日志只记录 `ProductDeadlineExpired`，没有 transport/provider 错误，因此不计入"
        "“明确 LLM 连接失败”。`feal-linear-cryptanalysis` 是回复多次截断后以"
        "`run.completed/output=null` 结束，也不能归为连接失败。"
    )
    add("")

    add("### 4.3 四个后台服务被 gateway cleanup 清理")
    add("")
    add(
        "`configure-git-webserver`、`kv-store-grpc`、`pypi-server`、`qemu-startup`"
        "均在 Agent 内启动过服务，但使用 Hermes 工具托管的 background。"
        "`run.completed` 后 gateway 正常 shutdown 会清理这些进程，Verifier 随后连接失败。"
        "这类零分是可重复的生命周期集成问题，不是 LLM 无返回。"
    )
    add("")
    add("- [configure-git-webserver：run.completed → cleanup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-30-38/configure-git-webserver__VuHrDDN/agent/hermes-run-events.jsonl:419>)；[Verifier HTTP 000](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__20-30-38/configure-git-webserver__VuHrDDN/verifier/test-stdout.txt:30>)")
    add("- [kv-store-grpc：run.completed → cleanup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-25-39/kv-store-grpc__Ef67kGg/agent/hermes-run-events.jsonl:515>)；[Verifier 5328 connection refused](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__06-25-39/kv-store-grpc__Ef67kGg/verifier/test-stdout.txt:125>)")
    add("- [pypi-server：run.completed → cleanup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-05-34/pypi-server__SzFsDEH/agent/hermes-run-events.jsonl:1329>)；[Verifier 无法安装包](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__14-05-34/pypi-server__SzFsDEH/verifier/test-stdout.txt:67>)")
    add("- [qemu-startup：run.completed → cleanup](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-09-06/qemu-startup__4pKPFNL/agent/hermes-run-events.jsonl:282>)；[Verifier telnet 失败](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-09-06/qemu-startup__4pKPFNL/verifier/test-stdout.txt:99>)")
    add("")

    add("### 4.4 七个 Exception/no-reward")
    add("")
    add(
        "七项都表现为 `ExceptionGroup + adapter_infra_error`，表层共同错误为 "
        "`LifecycleControllerError: process cleanup report is unavailable`："
    )
    add("")
    add("- Deadline 后再被 adapter 异常覆盖：`extract-moves-from-video`、`path-tracing`。")
    add("- Hermes 已 `run.completed`，但 cleanup report 缺失、Verifier 被跳过：`git-multibranch`、`install-windows-3.11`、`mailman`、`nginx-request-logging`。")
    add("- Agent/session 未成功建立：`prove-plus-comm`。")
    add("")
    add(
        "这些任务都不是明确 LLM 连接失败；因为原环境已经结束，现有 session 不能直接恢复"
        "成可验证的现场。共同异常示例见 "
        "[git-multibranch result](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__04-45-22/git-multibranch__annFNdb/result.json:197>)。"
    )
    add("")

    add("### 4.5 真实任务/产物失败")
    add("")
    add(
        "11 项属于任务交付、产物正确性或性能门槛失败，不应误归入 LLM/runner 可靠性："
        "`winning-avg-corewars`、`build-pov-ray`、`caffe-cifar-10`、`dna-assembly`、"
        "`dna-insert`、`feal-linear-cryptanalysis`、`make-doom-for-mips`、"
        "`make-mips-interpreter`、`openssl-selfsigned-cert`、`protein-assembly`、"
        "`query-optimize`。"
    )
    add("")
    add(
        "其中 `query-optimize` 的结果正确，但 solution median 1.269s，超过 "
        "golden 0.966s 的 1.05 倍性能门槛；这是有效的性能零分。"
        " [Verifier](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-31__15-29-40/query-optimize__GxjCVic/verifier/test-stdout.txt:110>)"
    )
    add("")

    add("## 5. 与 Astra V1 的交叉对比")
    add("")
    add("### 5.1 全样本快照：只能描述，不能直接排名")
    add("")
    add("| 指标 | Astra V1 56 | Hermes 当前 64 |")
    add("| --- | ---: | ---: |")
    add(f"| Reward=1 | 31/56（{pct(31, 56)}） | 35/64（{pct(35, 64)}）；已评分口径 35/57（{pct(35, 57)}） |")
    add(f"| 严格 E2E 成功 | 25/56（{pct(25, 56)}） | 33/64（{pct(33, 64)}） |")
    add(f"| Agent completed/rc0 | 27/56（{pct(27, 56)}） | 49/64（{pct(49, 64)}） |")
    add("| 无 Reward | 0 | 7 |")
    add(f"| E2E 累计 task-hours | {hours(astra_metrics['e2e_s']['sum'])} | {hours(h_metrics['e2e_s']['sum'])} |")
    add(f"| Agent 累计 hours | {hours(astra_metrics['agent_execution_s']['sum'])} | {hours(h_metrics['agent_execution_s']['sum'])} |")
    add(f"| Fresh input | {integer(astra_metrics['fresh_input_tokens']['sum'])} | {integer(h_metrics['fresh_input_tokens']['sum'])} |")
    add(f"| Cache-read | {integer(astra_metrics['cache_tokens']['sum'])} | {integer(h_metrics['cache_tokens']['sum'])} |")
    add(f"| 总 token | {integer(astra_metrics['total_tokens']['sum'])} | {integer(h_metrics['total_tokens']['sum'])} |")
    add(f"| 轮次/API 调用 | {integer(astra_metrics['turns_completed']['sum'])} | {integer(h_metrics['api_calls']['sum'])} |")
    add(f"| 工具返回 | {integer(astra_metrics['tool_calls']['sum'])} | {integer(h_metrics['tool_calls']['sum'])} |")
    add(f"| 失败工具返回 | {integer(astra_metrics['tool_calls_failed']['sum'])} | {integer(h_metrics['tool_calls_failed']['sum'])} |")
    add(f"| CTRF tests | {astra_verifier['passed']}/{astra_verifier['tests']} | {hermes['verifier']['passed']}/{hermes['verifier']['tests']} |")
    add("| 正式 C0 合格 | 0 | 0 |")
    add("")

    add("### 5.2 46 个同任务的结果变化")
    add("")
    add("| 转移 | 数量 | 含义 | 任务 |")
    add("| --- | ---: | --- | --- |")
    add(f"| 1→1 | 19 | 两边都通过 | {task_list(matched_rows, '1->1')} |")
    add(f"| 0→1 | 12 | Hermes 改善 | {task_list(matched_rows, '0->1')} |")
    add(f"| 1→0 | 5 | Hermes 回退 | {task_list(matched_rows, '1->0')} |")
    add(f"| 0→0 | 4 | 两边都零分 | {task_list(matched_rows, '0->0')} |")
    add(f"| 0→NA | 4 | Astra 零分，Hermes 未评分 | {task_list(matched_rows, '0->NA')} |")
    add(f"| 1→NA | 2 | Astra 通过，Hermes 未评分 | {task_list(matched_rows, '1->NA')} |")
    add("")
    add(
        "Astra 在这 46 项中的 17 个 `stream_transport` 零分，在 Hermes 中变为："
        "**10 个通过、4 个零分、3 个未评分**。这表明 Hermes 当前显著减少了"
        "Astra 批次中的 stream/fallback 回传故障表现，但并没有把所有原 stream 零分都转化为成功。"
    )
    add("")
    add(
        "5 个 1→0 回退分别是：`caffe-cifar-10`（训练未完成）、"
        "`compile-compcert`（deadline）、`configure-git-webserver` 和 `pypi-server`"
        "（后台服务被 cleanup）、`openssl-selfsigned-cert`（交付脚本依赖未随任务环境提供）。"
    )
    add("")

    add("### 5.3 同任务时间与资源")
    add("")
    add("| 指标 | Astra 46 | Hermes 46 | Hermes/Astra 累计比 | 配对中位比 |")
    add("| --- | ---: | ---: | ---: | ---: |")
    matched_metrics = matched["metrics"]
    metric_specs = [
        ("E2E 累计小时", "e2e_s", "hours"),
        ("Agent 累计小时", "agent_s", "hours"),
        ("Fresh input", "fresh_input_tokens", "integer"),
        ("Cache-read", "cache_tokens", "integer"),
        ("Input（含 cache）", "input_tokens", "integer"),
        ("Output", "output_tokens", "integer"),
        ("总 token", "total_tokens", "integer"),
        ("轮次/API 调用", "rounds", "integer"),
        ("工具返回", "tool_calls", "integer"),
        ("失败工具返回", "failed_tools", "integer"),
    ]
    for label, key, kind in metric_specs:
        metric = matched_metrics[key]
        formatter = hours if kind == "hours" else integer
        add(
            f"| {label} | {formatter(metric['astra']['sum'])} | "
            f"{formatter(metric['hermes']['sum'])} | "
            f"{decimal(metric['hermes_over_astra_sum'], 3)}× | "
            f"{decimal(metric['paired_ratio']['median'], 3)}× |"
        )
    add("")
    astra_cache_share = (
        matched_metrics["cache_tokens"]["astra"]["sum"]
        / matched_metrics["input_tokens"]["astra"]["sum"]
    )
    hermes_cache_share = (
        matched_metrics["cache_tokens"]["hermes"]["sum"]
        / matched_metrics["input_tokens"]["hermes"]["sum"]
    )
    astra_tool_failure = (
        matched_metrics["failed_tools"]["astra"]["sum"]
        / matched_metrics["tool_calls"]["astra"]["sum"]
    )
    hermes_tool_failure = (
        matched_metrics["failed_tools"]["hermes"]["sum"]
        / matched_metrics["tool_calls"]["hermes"]["sum"]
    )
    add(
        f"- E2E：Astra **{hours(matched_metrics['e2e_s']['astra']['sum'])}h**，"
        f"Hermes **{hours(matched_metrics['e2e_s']['hermes']['sum'])}h**；"
        "Hermes 累计少 31.72%，典型任务的配对中位比为 0.767。"
    )
    add(
        f"- 总 token：Astra **{integer(matched_metrics['total_tokens']['astra']['sum'])}**，"
        f"Hermes **{integer(matched_metrics['total_tokens']['hermes']['sum'])}**，"
        "Hermes 为 2.97 倍。"
    )
    add(
        f"- Fresh input 几乎持平（1.009 倍），但 cache-read 为 3.64 倍；"
        f"cache 占 input 从 Astra 的 **{astra_cache_share * 100:.2f}%** "
        f"升至 Hermes 的 **{hermes_cache_share * 100:.2f}%**。"
    )
    add(
        "- Hermes output 只有 Astra 的 0.668 倍，但 API 轮次为 1.694 倍、"
        "工具返回为 1.381 倍：表现为更多轮、更短输出、更高上下文复用。"
    )
    add(
        f"- 工具事件失败率：Astra 约 **{astra_tool_failure * 100:.2f}%**，"
        f"Hermes 约 **{hermes_tool_failure * 100:.2f}%**；"
        "两者事件定义不同，只能作为诊断指标。"
    )
    add("")

    add("### 5.4 失败模式发生了什么变化")
    add("")
    add("| 维度 | Astra V1 56 | Hermes 当前 64 |")
    add("| --- | --- | --- |")
    add("| 明确 LLM/传输失败 | 22 个 `stream_transport` 零分，占零分 88.00% | 1 个 provider 明确无响应，占零分 4.55% |")
    add("| 异常但 reward 可得 | 6 个异常通过，Verifier 仍运行 | 2 个 timeout 通过；另有 7 个 adapter 异常完全无 reward |")
    add("| 后台服务生命周期 | 未形成主要零分类别 | 4 个服务在 gateway cleanup 后消失 |")
    add("| Deadline | 1 个预算耗尽异常通过，另有个别 verifier timeout | 7 个 product timeout：2 pass、5 zero；另有 2 个 timeout 被 adapter 异常覆盖 |")
    add("| 真实任务/性能失败 | 1 个明确任务失败 | 11 个任务交付、产物或性能失败 |")
    add("| Verifier infra | 1 个无 CTRF，1 个固定超时 | 1 个网络/uvx 故障无 CTRF |")
    add("")
    add(
        "本次观测的主要差异是 Hermes 批次很少出现 Astra 最突出的 stream/fallback 连接问题；"
        "同时暴露出新的系统边界：gateway 对工具后台进程的清理语义、cleanup report "
        "缺失导致 Verifier 被跳过、以及更短或不同的 product deadline。"
    )
    add("")

    add("## 6. 重跑与处置建议")
    add("")
    add("### 6.1 若目标是得到可信的探索性 reward")
    add("")
    add("| 集合 | 数量 | 处置 |")
    add("| --- | ---: | --- |")
    add("| 已正常通过 | 33 | 保留 |")
    add("| Timeout 但通过 | 2 | 功能 reward 保留；严格 E2E 需要重跑 |")
    add("| 真实任务/性能失败 | 11 | 保留零分，不进入可靠性重跑队列 |")
    add("| Deadline 零分 | 5 | 若 deadline 是预先定义预算则保留；若配置不一致，统一后重跑 |")
    add("| 明确 provider 无响应 | 1 | 完整重跑；现有环境已结束，不能只恢复 LLM session |")
    add("| 后台服务被 cleanup | 4 | 修正 daemon 化方式后完整重跑 |")
    add("| Verifier infra | 1 | 优先重跑 Verifier；环境不可恢复时完整重跑 |")
    add("| 无 reward adapter/launcher 异常 | 7 | 完整重跑取得评分 |")
    add("")
    add(
        "因此，按与 Astra V1 相同的“只重跑可靠性或评估无效项”口径，"
        "**最低优先队列为 13 项**：1 个 provider 无响应、4 个后台生命周期失败、"
        "1 个 Verifier infra、7 个无 reward。5 个 deadline 零分是否重跑取决于"
        "deadline 是否属于预先冻结的实验预算。"
    )
    add("")
    add(
        "如果采用更保守的“所有零分和无 reward 都重跑”策略，则为 **29 项**；"
        "若还要求两个 timeout-pass 具有干净终态，则为 **31 项**。"
    )
    add("")

    add("### 6.2 若目标是正式 C0")
    add("")
    add(
        "64/64 都是 `trigger_hit=false`、`lifecycle_gate_passed=false`、"
        "`formal_score_eligible=false`。Hermes controller 登记的是短生命周期的 "
        "`/run/rosetta/rosetta` wrapper；no-hit 分布为："
        "`product_exited_before_noop=55`、`product_exited=2`、"
        "`controller_incomplete=7`。"
    )
    add("")
    add(
        "如果目标是正式有效 C0，必须先修正 lifecycle process tracking，再重跑全部 64 项；"
        "当前 reward 只能保留为探索性诊断结果。典型证据："
        "[controller 注册 wrapper](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/agent/controller.jsonl:6>)、"
        "[trigger no-hit](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/agent/controller.jsonl:7>)、"
        "[gate false](</Users/chenyuwei/Documents/MOI benchmark/work/hermes-c0-all-jobs/2026-07-30__14-15-09/bn-fit-modify__6YxAGqr/agent/controller.jsonl:10>)。"
    )
    add("")

    add("## 7. 解释限制")
    add("")
    add("1. Astra 56 与 Hermes 64 都不是随机、完整的 89 项样本；Agent 能力比较必须以 46 项交集为主。")
    add("2. Hermes 明确使用 `zai/glm-5.2`、`max_turns=90`；Astra 的模型只保存为不透明 UUID，`max_turns=50`。更高的 Hermes 成功数不能单独归因于 runner。")
    add("3. 两边 product deadline 配置不同；Hermes 的部分回退直接来自 1,800/3,600/4,800 秒 deadline。")
    add("4. Astra 23 个 journal token 项是已落盘 usage 的可观测下界；Hermes 有 1 项没有 session/token。")
    add("5. API 轮次、工具失败是近似映射；不能做精确埋点级显著性结论。")
    add("6. CPU、RAM、GPU、磁盘 I/O、网络字节和实际美元成本均不可比较。")
    add("7. 46 项中 Hermes 有 6 项未评分；将它们算零分、排除或重跑会产生不同通过率，报告已分别列出。")
    add("8. 所有结果均不具正式 C0 资格，不能用于正式主榜或最终模型结论。")
    add("")

    add("## 附录 A：Hermes 64 项明细")
    add("")
    add("时间单位为分钟；Token 为 `fresh + cache + output`。")
    add("")
    add("| # | 任务 | R | Product | 类别 | E2E | Agent | 总 token | API | 工具/失败 | Verifier | 建议 |")
    add("| ---: | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for index, row in enumerate(hermes_rows, 1):
        verifier = (
            f"{row['verifier_passed']}/{row['verifier_tests']}"
            if row["verifier_tests"]
            else "无 CTRF"
        )
        add(
            f"| {index} | {task_link(row)} | {reward(row['reward'])} | "
            f"`{row['product_terminal_status']}/rc{row['product_return_code'] or 'null'}` | "
            f"{CATEGORY_LABELS.get(row['outcome_category'], row['outcome_category'])} | "
            f"{minutes(row['e2e_s'])} | {minutes(row['agent_execution_s'])} | "
            f"{integer(row['total_tokens'])} | {integer(row['api_calls'])} | "
            f"{integer(row['tool_calls'])}/{integer(row['tool_calls_failed'])} | "
            f"{verifier} | {row['recommended_action']} |"
        )
    add("")

    add("## 附录 B：46 个同任务配对明细")
    add("")
    add("| # | 任务 | Astra R | Hermes R | 转移 | Astra E2E | Hermes E2E | Astra token | Hermes token | Astra 工具 | Hermes 工具 |")
    add("| ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for index, row in enumerate(matched_rows, 1):
        add(
            f"| {index} | {matched_task_link(row)} | {row['astra_reward']} | "
            f"{reward(row['hermes_reward'])} | `{row['reward_transition']}` | "
            f"{minutes(row['astra_e2e_s'])} | {minutes(row['hermes_e2e_s'])} | "
            f"{integer(row['astra_total_tokens'])} | {integer(row['hermes_total_tokens'])} | "
            f"{integer(row['astra_tool_calls'])} | {integer(row['hermes_tool_calls'])} |"
        )
    add("")

    add("## 附录 C：机器可读数据")
    add("")
    add(f"- Hermes 64 项 CSV：[hermes-c0-current-64-tasks-v1.csv](<{HERMES_CSV}>)")
    add(f"- 46 项配对 CSV：[hermes-vs-astra-matched-46-tasks-v1.csv](<{MATCHED_CSV}>)")
    add(f"- 聚合 JSON：[hermes-vs-astra-current-summary-v1.json](<{SUMMARY_PATH}>)")
    add(f"- 可复现分析脚本：[analyze_hermes_astra_current.py](<{OUTPUT_DIR / 'analyze_hermes_astra_current.py'}>)")
    add("")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
