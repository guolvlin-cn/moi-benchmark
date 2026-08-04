#!/usr/bin/env python3
"""Build a reproducible Hermes-current and Astra-56 comparison snapshot."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


WORK_DIR = Path(__file__).resolve().parents[3]
HERMES_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent
ASTRA_ANALYSIS_DIR = (
    WORK_DIR
    / "astra-c0-all-jobs"
    / "2026-07-29__19-36-33"
    / "analysis"
    / "v1"
)
ASTRA_CSV = ASTRA_ANALYSIS_DIR / "astra-c0-56-tasks-statistics-v1.csv"
ASTRA_SUMMARY = ASTRA_ANALYSIS_DIR / "astra-c0-56-tasks-statistics-v1-summary.json"

# Freeze the in-progress Hermes directory at the start of this analysis.
SNAPSHOT_CUTOFF = datetime.fromisoformat("2026-07-31T16:46:44+08:00")

HERMES_CSV = OUTPUT_DIR / "hermes-c0-current-64-tasks-v1.csv"
MATCHED_CSV = OUTPUT_DIR / "hermes-vs-astra-matched-46-tasks-v1.csv"
SUMMARY_JSON = OUTPUT_DIR / "hermes-vs-astra-current-summary-v1.json"

BACKGROUND_LIFECYCLE_FAILURES = {
    "configure-git-webserver",
    "kv-store-grpc",
    "pypi-server",
    "qemu-startup",
}

TASK_REQUIREMENT_FAILURES = {
    "winning-avg-corewars",
    "build-pov-ray",
    "caffe-cifar-10",
    "dna-assembly",
    "dna-insert",
    "feal-linear-cryptanalysis",
    "make-doom-for-mips",
    "make-mips-interpreter",
    "openssl-selfsigned-cert",
    "protein-assembly",
}

FAILURE_DETAILS = {
    "adaptive-rejection-sampler": (
        "Provider 连续 5 次 stale attempt 无响应，Hermes 主动终止；ars.R 等交付物未生成",
        "LLM/provider 恢复后完整重跑",
    ),
    "winning-avg-corewars": (
        "Verifier 1/3；my_warrior.red 缺失，性能测试失败",
        "保留任务零分",
    ),
    "build-pov-ray": (
        "Verifier 2/3；产物未通过 POV-Ray 2.2 正确源码真实性检查",
        "保留任务零分",
    ),
    "caffe-cifar-10": (
        "Verifier 3/6；训练模型与 training_output.txt 等交付物缺失",
        "保留任务零分",
    ),
    "compile-compcert": (
        "Hermes 超过 driver deadline；/tmp/CompCert/ccomp 未生成，Verifier 0/3",
        "若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑",
    ),
    "configure-git-webserver": (
        "Agent 内服务可用，但 gateway 收尾后 HTTP 返回 000；后台服务未持久化到 Verifier",
        "使用独立 daemon 后完整重跑",
    ),
    "dna-assembly": (
        "Verifier 0/1；primers.fasta 未满足扩增和 overhang 要求",
        "保留任务零分",
    ),
    "dna-insert": (
        "Verifier 0/1；primers.fasta 未满足插入任务要求",
        "保留任务零分",
    ),
    "extract-moves-from-video": (
        "Hermes run 超过 deadline，随后 cleanup report 缺失，Verifier 未运行",
        "完整重跑；若保留原 deadline，应将超时作为明确终态",
    ),
    "feal-linear-cryptanalysis": (
        "Verifier 0/1；线性密码分析输出未正确解密全部密文",
        "保留任务零分",
    ),
    "gcode-to-text": (
        "Hermes 超过 driver deadline；out.txt 未生成，Verifier 0/2",
        "若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑",
    ),
    "git-multibranch": (
        "Hermes run completed，但 cleanup report 缺失导致 adapter_infra_error；Verifier 未运行",
        "完整重跑以获得可评分结果",
    ),
    "gpt2-codegolf": (
        "Hermes 超过 driver deadline；gpt2.c 未生成，Verifier 0/1",
        "若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑",
    ),
    "install-windows-3.11": (
        "Hermes run completed，但 cleanup report 缺失导致 adapter_infra_error；Verifier 未运行",
        "完整重跑以获得可评分结果",
    ),
    "kv-store-grpc": (
        "Verifier 5/7；gateway 收尾后 5328 端口 Connection refused，后台 gRPC 服务未持久化",
        "使用独立 daemon 后完整重跑",
    ),
    "mailman": (
        "Hermes run completed，但 cleanup report 缺失导致 adapter_infra_error；Verifier 未运行",
        "完整重跑以获得可评分结果",
    ),
    "make-doom-for-mips": (
        "Verifier 0/3；vm.js 未成功运行且 frame.bmp 未生成",
        "保留任务零分",
    ),
    "make-mips-interpreter": (
        "Verifier 0/3；vm.js 未成功运行且 frame.bmp 未生成",
        "保留任务零分",
    ),
    "nginx-request-logging": (
        "Hermes run completed，但 cleanup report 缺失导致 adapter_infra_error；Verifier 未运行",
        "完整重跑以获得可评分结果",
    ),
    "openssl-selfsigned-cert": (
        "Verifier 5/6；check_cert.py 执行返回非零",
        "保留任务零分",
    ),
    "path-tracing": (
        "Hermes run 超过 deadline，随后 cleanup report 缺失，Verifier 未运行",
        "完整重跑；若保留原 deadline，应将超时作为明确终态",
    ),
    "protein-assembly": (
        "Verifier 0/1；gblock.txt 缺失或不满足融合蛋白要求",
        "保留任务零分",
    ),
    "prove-plus-comm": (
        "产品在 Hermes session 建立前发生 launcher/lifecycle 异常；无 session、无 Verifier",
        "修复 launcher/架构问题后完整重跑",
    ),
    "pypi-server": (
        "Verifier 安装 vectorops==0.1.0 时连接不到本地 PyPI；后台服务未持久化",
        "使用独立 daemon 后完整重跑",
    ),
    "pytorch-model-recovery": (
        "Verifier 下载依赖时 SSL_ERROR_SYSCALL，且 uvx 不存在；没有生成 CTRF",
        "优先重跑 Verifier；若原环境不可恢复则完整重跑",
    ),
    "qemu-alpine-ssh": (
        "Hermes 超过 driver deadline；SSH 端口不可用，Verifier 0/1",
        "若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑",
    ),
    "qemu-startup": (
        "QEMU 在 Agent 内已出现 login prompt，但 gateway cleanup 清理了工具托管后台进程；Verifier 时端口消失",
        "使用 QEMU -daemonize 后完整重跑",
    ),
    "query-optimize": (
        "Verifier 5/6；solution median 1.269s，未达到不慢于 golden 1.05 倍的门槛",
        "保留任务零分",
    ),
    "raman-fitting": (
        "Hermes 超过 driver deadline；Verifier 1/3，G 与 2D 峰参数未达容差",
        "若 deadline 属实验预算则保留零分；否则提高 deadline 后完整重跑",
    ),
}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def duration_s(value: dict[str, Any] | None) -> float | None:
    if not value:
        return None
    start = parse_time(value.get("started_at"))
    finish = parse_time(value.get("finished_at"))
    return (finish - start).total_seconds() if start and finish else None


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def percentile(values: list[float], p: float) -> float | None:
    clean = sorted(values)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    index = (len(clean) - 1) * p
    lo = math.floor(index)
    hi = math.ceil(index)
    if lo == hi:
        return clean[lo]
    return clean[lo] + (clean[hi] - clean[lo]) * (index - lo)


def stats(values: list[float | int | None]) -> dict[str, float | int | None]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"n": 0, "sum": None, "mean": None, "median": None, "p90": None}
    return {
        "n": len(clean),
        "sum": sum(clean),
        "mean": sum(clean) / len(clean),
        "median": percentile(clean, 0.5),
        "p90": percentile(clean, 0.9),
        "min": min(clean),
        "max": max(clean),
    }


def verifier_summary(trial_dir: Path) -> dict[str, Any]:
    ctrf = read_json(trial_dir / "verifier" / "ctrf.json")
    results = ctrf.get("results") if ctrf else None
    if not isinstance(results, dict):
        return {
            "verifier_tests": None,
            "verifier_passed": None,
            "verifier_failed": None,
            "verifier_skipped": None,
            "failed_test_names": "",
        }
    summary = results.get("summary")
    tests = results.get("tests")
    summary = summary if isinstance(summary, dict) else {}
    tests = tests if isinstance(tests, list) else []
    failed_names = [
        str(test.get("name"))
        for test in tests
        if isinstance(test, dict) and test.get("status") == "failed"
    ]
    return {
        "verifier_tests": summary.get("tests"),
        "verifier_passed": summary.get("passed"),
        "verifier_failed": summary.get("failed"),
        "verifier_skipped": summary.get("skipped"),
        "failed_test_names": "; ".join(failed_names),
    }


def classify(
    task_id: str,
    reward: int | None,
    product_status: str,
    product_rc: int | None,
    run_status: str,
) -> tuple[str, str, str]:
    if reward == 1:
        if product_status == "completed" and product_rc == 0:
            return "clean_verifier_pass", "功能通过且 Agent 正常完成", "保留结果"
        return (
            "abnormal_verifier_pass",
            "Agent 超过 deadline，但中断前产物已通过 Verifier",
            "保留功能结果；严格 E2E 统计记为未成功",
        )

    detail, action = FAILURE_DETAILS.get(
        task_id, ("尚未完成人工根因分类", "人工复核")
    )
    if reward is None:
        if task_id == "prove-plus-comm":
            return "launcher_infra_no_verifier", detail, action
        if run_status == "timed_out":
            return "deadline_adapter_no_verifier", detail, action
        return "cleanup_adapter_no_verifier", detail, action
    if task_id == "adaptive-rejection-sampler":
        return "llm_provider_unresponsive", detail, action
    if product_status == "timeout" or run_status == "timed_out":
        return "agent_deadline_zero", detail, action
    if task_id in BACKGROUND_LIFECYCLE_FAILURES:
        return "background_lifecycle_failure", detail, action
    if task_id == "pytorch-model-recovery":
        return "verifier_infra_failure", detail, action
    if task_id == "query-optimize":
        return "performance_requirement_failure", detail, action
    if task_id in TASK_REQUIREMENT_FAILURES:
        return "task_requirement_failure", detail, action
    return "other_zero", detail, action


def analyze_trial(run_dir: Path, trial_dir: Path) -> dict[str, Any] | None:
    result = read_json(trial_dir / "result.json")
    if not result:
        return None
    finish = parse_time(result.get("finished_at"))
    if not finish or finish > SNAPSHOT_CUTOFF:
        return None

    metadata = ((result.get("agent_result") or {}).get("metadata") or {})
    reward_value = (
        ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    )
    reward = int(reward_value) if reward_value is not None else None
    task_id = str(result.get("task_name") or "").removeprefix("terminal-bench/")

    run = read_json(trial_dir / "agent" / "hermes-run.json") or {}
    session_rows = read_jsonl(trial_dir / "agent" / "hermes-session.jsonl")
    session = session_rows[0] if session_rows else {}
    events = read_jsonl(trial_dir / "agent" / "hermes-run-events.jsonl")

    tool_events = [row for row in events if row.get("event") == "tool.completed"]
    tool_counts: Counter[str] = Counter(
        str(row.get("tool")) for row in tool_events if row.get("tool")
    )
    failed_tool_counts: Counter[str] = Counter(
        str(row.get("tool"))
        for row in tool_events
        if row.get("tool") and row.get("error") is True
    )

    fresh = session.get("input_tokens")
    cache = session.get("cache_read_tokens")
    output = session.get("output_tokens")
    input_tokens = (
        int(fresh or 0) + int(cache or 0)
        if fresh is not None or cache is not None
        else None
    )
    output_tokens = int(output) if output is not None else None
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )

    start = parse_time(result.get("started_at"))
    product_status = str(metadata.get("product_terminal_status") or "")
    product_rc = metadata.get("product_return_code")
    run_status = str(run.get("status") or "")
    category, reason, action = classify(
        task_id, reward, product_status, product_rc, run_status
    )

    row: dict[str, Any] = {
        "task_id": task_id,
        "run_dir": run_dir.name,
        "trial_name": result.get("trial_name") or trial_dir.name,
        "trial_path": str(trial_dir),
        "reward": reward,
        "scored": reward is not None,
        "strict_e2e_success": (
            reward == 1 and product_status == "completed" and product_rc == 0
        ),
        "exception": bool(result.get("exception_info")),
        "exception_type": (
            (result.get("exception_info") or {}).get("exception_type") or ""
        ),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "e2e_s": (finish - start).total_seconds() if start else None,
        "environment_setup_s": duration_s(result.get("environment_setup")),
        "agent_setup_s": duration_s(result.get("agent_setup")),
        "agent_execution_s": duration_s(result.get("agent_execution")),
        "verifier_s": duration_s(result.get("verifier")),
        "product_terminal_status": product_status,
        "product_return_code": product_rc,
        "product_completion_claim": metadata.get("product_completion_claim"),
        "product_error_type": metadata.get("product_error_type"),
        "product_final_status": metadata.get("product_final_status"),
        "cleanup_zero_live_proven": metadata.get(
            "product_cleanup_zero_live_proven"
        ),
        "trigger_hit": metadata.get("trigger_hit"),
        "trigger_reason": metadata.get("trigger_reason"),
        "lifecycle_gate_passed": metadata.get("lifecycle_gate_passed"),
        "formal_score_eligible": metadata.get("formal_score_eligible"),
        "run_status": run_status,
        "run_error": run.get("error"),
        "run_duration_s": run.get("duration_sec"),
        "session_present": bool(session),
        "api_calls": session.get("api_call_count"),
        "session_tool_calls": session.get("tool_call_count"),
        "tool_calls": len(tool_events),
        "tool_calls_failed": sum(failed_tool_counts.values()),
        "tool_call_failure_rate": (
            sum(failed_tool_counts.values()) / len(tool_events)
            if tool_events
            else 0.0
        ),
        "tool_duration_s": sum(float(row.get("duration") or 0) for row in tool_events),
        "tool_breakdown": json.dumps(
            tool_counts, ensure_ascii=False, sort_keys=True
        ),
        "failed_tool_breakdown": json.dumps(
            failed_tool_counts, ensure_ascii=False, sort_keys=True
        ),
        "fresh_input_tokens": int(fresh) if fresh is not None else None,
        "cache_tokens": int(cache) if cache is not None else None,
        "cache_write_tokens": (
            int(session["cache_write_tokens"])
            if session.get("cache_write_tokens") is not None
            else None
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": (
            int(session["reasoning_tokens"])
            if session.get("reasoning_tokens") is not None
            else None
        ),
        "total_tokens": total_tokens,
        "cache_share": (
            int(cache or 0) / input_tokens if input_tokens else None
        ),
        "cost_status": session.get("cost_status"),
        "actual_cost_usd": session.get("actual_cost_usd"),
        "outcome_category": category,
        "failure_reason": reason,
        "recommended_action": action,
    }
    row.update(verifier_summary(trial_dir))
    return row


def load_hermes_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(HERMES_ROOT.iterdir()):
        if not run_dir.is_dir() or run_dir.name == "analysis":
            continue
        for trial_dir in sorted(run_dir.iterdir()):
            if not trial_dir.is_dir() or not (trial_dir / "result.json").is_file():
                continue
            row = analyze_trial(run_dir, trial_dir)
            if row:
                rows.append(row)
    return sorted(rows, key=lambda row: str(row["finished_at"]))


def load_astra_rows() -> list[dict[str, Any]]:
    with ASTRA_CSV.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def as_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metric_fields = [
        "e2e_s",
        "environment_setup_s",
        "agent_setup_s",
        "agent_execution_s",
        "verifier_s",
        "fresh_input_tokens",
        "cache_tokens",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "api_calls",
        "tool_calls",
        "tool_calls_failed",
        "tool_duration_s",
    ]
    ctrf_rows = [row for row in rows if row["verifier_tests"] is not None]
    tool_counts: Counter[str] = Counter()
    failed_tool_counts: Counter[str] = Counter()
    for row in rows:
        tool_counts.update(json.loads(str(row["tool_breakdown"])))
        failed_tool_counts.update(json.loads(str(row["failed_tool_breakdown"])))

    def group_summary(group: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(group),
            "e2e_s": stats([row.get("e2e_s") for row in group]),
            "agent_execution_s": stats(
                [row.get("agent_execution_s") for row in group]
            ),
            "total_tokens": stats([row.get("total_tokens") for row in group]),
            "api_calls": stats([row.get("api_calls") for row in group]),
            "tool_calls": stats([row.get("tool_calls") for row in group]),
            "tool_calls_failed": stats(
                [row.get("tool_calls_failed") for row in group]
            ),
            "verifier": {
                "tests": sum(int(row["verifier_tests"] or 0) for row in group),
                "passed": sum(int(row["verifier_passed"] or 0) for row in group),
                "failed": sum(int(row["verifier_failed"] or 0) for row in group),
            },
        }

    reward_groups = {
        "reward1": [row for row in rows if row["reward"] == 1],
        "reward0": [row for row in rows if row["reward"] == 0],
        "unscored": [row for row in rows if row["reward"] is None],
        "strict_e2e_success": [
            row for row in rows if row["strict_e2e_success"] is True
        ],
    }
    categories = sorted({str(row["outcome_category"]) for row in rows})
    return {
        "n": len(rows),
        "counts": {
            "reward": dict(Counter(str(row["reward"]) for row in rows)),
            "outcome_category": dict(
                Counter(str(row["outcome_category"]) for row in rows)
            ),
            "product_terminal_status": dict(
                Counter(str(row["product_terminal_status"]) for row in rows)
            ),
            "product_return_code": dict(
                Counter(str(row["product_return_code"]) for row in rows)
            ),
            "trigger_reason": dict(
                Counter(str(row["trigger_reason"]) for row in rows)
            ),
            "exceptions": sum(bool(row["exception"]) for row in rows),
            "scored": sum(bool(row["scored"]) for row in rows),
            "reward1": sum(row["reward"] == 1 for row in rows),
            "reward0": sum(row["reward"] == 0 for row in rows),
            "unscored": sum(row["reward"] is None for row in rows),
            "strict_e2e_success": sum(
                bool(row["strict_e2e_success"]) for row in rows
            ),
            "formal_score_eligible_true": sum(
                row["formal_score_eligible"] is True for row in rows
            ),
            "trigger_hit_true": sum(row["trigger_hit"] is True for row in rows),
            "session_present": sum(bool(row["session_present"]) for row in rows),
        },
        "metrics": {
            field: stats([row.get(field) for row in rows])
            for field in metric_fields
        },
        "by_reward": {
            name: group_summary(group) for name, group in reward_groups.items()
        },
        "by_category": {
            category: group_summary(
                [row for row in rows if row["outcome_category"] == category]
            )
            for category in categories
        },
        "tool_call_counts": dict(tool_counts.most_common()),
        "failed_tool_call_counts": dict(failed_tool_counts.most_common()),
        "verifier": {
            "trials_with_ctrf": len(ctrf_rows),
            "trials_without_ctrf": len(rows) - len(ctrf_rows),
            "tests": sum(int(row["verifier_tests"] or 0) for row in ctrf_rows),
            "passed": sum(int(row["verifier_passed"] or 0) for row in ctrf_rows),
            "failed": sum(int(row["verifier_failed"] or 0) for row in ctrf_rows),
            "skipped": sum(int(row["verifier_skipped"] or 0) for row in ctrf_rows),
        },
    }


def matched_rows(
    hermes_rows: list[dict[str, Any]], astra_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    hermes = {str(row["task_id"]): row for row in hermes_rows}
    astra = {str(row["task_id"]): row for row in astra_rows}
    rows: list[dict[str, Any]] = []
    for task_id in sorted(hermes.keys() & astra.keys()):
        h = hermes[task_id]
        a = astra[task_id]
        a_reward = int(a["reward"])
        h_reward = h["reward"]
        if h_reward is None:
            transition = f"{a_reward}->NA"
        else:
            transition = f"{a_reward}->{h_reward}"
        a_strict = (
            a_reward == 1
            and a["product_terminal_status"] == "completed"
            and a["product_return_code"] == "0"
        )
        rows.append(
            {
                "task_id": task_id,
                "astra_reward": a_reward,
                "hermes_reward": h_reward,
                "reward_transition": transition,
                "astra_strict_e2e": a_strict,
                "hermes_strict_e2e": h["strict_e2e_success"],
                "astra_outcome_category": a["outcome_category"],
                "hermes_outcome_category": h["outcome_category"],
                "astra_product_status": a["product_terminal_status"],
                "hermes_product_status": h["product_terminal_status"],
                "astra_e2e_s": as_number(a["e2e_s"]),
                "hermes_e2e_s": h["e2e_s"],
                "astra_agent_s": as_number(a["agent_execution_s"]),
                "hermes_agent_s": h["agent_execution_s"],
                "astra_fresh_input_tokens": as_number(a["fresh_input_tokens"]),
                "hermes_fresh_input_tokens": h["fresh_input_tokens"],
                "astra_cache_tokens": as_number(a["cache_tokens"]),
                "hermes_cache_tokens": h["cache_tokens"],
                "astra_input_tokens": as_number(a["input_tokens"]),
                "hermes_input_tokens": h["input_tokens"],
                "astra_output_tokens": as_number(a["output_tokens"]),
                "hermes_output_tokens": h["output_tokens"],
                "astra_total_tokens": as_number(a["total_tokens"]),
                "hermes_total_tokens": h["total_tokens"],
                "astra_rounds": as_number(a["turns_completed"]),
                "hermes_api_calls": h["api_calls"],
                "astra_tool_calls": as_number(a["tool_calls"]),
                "hermes_tool_calls": h["tool_calls"],
                "astra_failed_tools": as_number(a["tool_calls_failed"]),
                "hermes_failed_tools": h["tool_calls_failed"],
                "astra_verifier": (
                    f'{a["verifier_passed"]}/{a["verifier_tests"]}'
                    if a["verifier_tests"]
                    else "无 CTRF"
                ),
                "hermes_verifier": (
                    f'{h["verifier_passed"]}/{h["verifier_tests"]}'
                    if h["verifier_tests"] is not None
                    else "无 CTRF"
                ),
                "hermes_failure_reason": h["failure_reason"],
                "hermes_trial_path": h["trial_path"],
                "astra_trial_path": a["trial_path"],
            }
        )
    return rows


def matched_aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metric_pairs = {
        "e2e_s": ("astra_e2e_s", "hermes_e2e_s"),
        "agent_s": ("astra_agent_s", "hermes_agent_s"),
        "fresh_input_tokens": (
            "astra_fresh_input_tokens",
            "hermes_fresh_input_tokens",
        ),
        "cache_tokens": ("astra_cache_tokens", "hermes_cache_tokens"),
        "input_tokens": ("astra_input_tokens", "hermes_input_tokens"),
        "output_tokens": ("astra_output_tokens", "hermes_output_tokens"),
        "total_tokens": ("astra_total_tokens", "hermes_total_tokens"),
        "rounds": ("astra_rounds", "hermes_api_calls"),
        "tool_calls": ("astra_tool_calls", "hermes_tool_calls"),
        "failed_tools": ("astra_failed_tools", "hermes_failed_tools"),
    }
    metrics: dict[str, Any] = {}
    for label, (astra_key, hermes_key) in metric_pairs.items():
        astra_values = [as_number(row[astra_key]) for row in rows]
        hermes_values = [as_number(row[hermes_key]) for row in rows]
        ratios = [
            h / a
            for a, h in zip(astra_values, hermes_values)
            if a not in (None, 0) and h is not None
        ]
        metrics[label] = {
            "astra": stats(astra_values),
            "hermes": stats(hermes_values),
            "hermes_over_astra_sum": (
                sum(value for value in hermes_values if value is not None)
                / sum(value for value in astra_values if value is not None)
                if sum(value for value in astra_values if value is not None)
                else None
            ),
            "paired_ratio": stats(ratios),
        }

    scored = [row for row in rows if row["hermes_reward"] is not None]
    return {
        "n": len(rows),
        "reward_transition": dict(
            Counter(str(row["reward_transition"]) for row in rows)
        ),
        "astra_reward1": sum(row["astra_reward"] == 1 for row in rows),
        "hermes_reward1": sum(row["hermes_reward"] == 1 for row in rows),
        "hermes_scored": len(scored),
        "hermes_unscored": len(rows) - len(scored),
        "astra_reward1_on_hermes_scored": sum(
            row["astra_reward"] == 1 for row in scored
        ),
        "hermes_reward1_on_scored": sum(
            row["hermes_reward"] == 1 for row in scored
        ),
        "astra_strict_e2e": sum(bool(row["astra_strict_e2e"]) for row in rows),
        "hermes_strict_e2e": sum(bool(row["hermes_strict_e2e"]) for row in rows),
        "metrics": metrics,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    hermes_rows = load_hermes_rows()
    astra_rows = load_astra_rows()
    matched = matched_rows(hermes_rows, astra_rows)
    astra_summary = read_json(ASTRA_SUMMARY) or {}

    summary = {
        "schema_version": 1,
        "snapshot_cutoff": SNAPSHOT_CUTOFF.isoformat(),
        "scope": {
            "hermes_terminal_trials": len(hermes_rows),
            "astra_v1_trials": len(astra_rows),
            "matched_tasks": len(matched),
            "hermes_only_vs_astra56": sorted(
                {str(row["task_id"]) for row in hermes_rows}
                - {str(row["task_id"]) for row in astra_rows}
            ),
            "astra56_not_yet_terminal_in_hermes": sorted(
                {str(row["task_id"]) for row in astra_rows}
                - {str(row["task_id"]) for row in hermes_rows}
            ),
        },
        "hermes_current": aggregate(hermes_rows),
        "astra_v1": astra_summary,
        "matched": matched_aggregate(matched),
        "limitations": [
            "Astra 56 是排除 33 个必须完整重跑任务后的条件样本；Hermes 64 是进行中批次的时间截面。",
            "主对比使用 46 个同任务交集；64 对 56 的全样本数字只用于各自快照描述。",
            "Hermes 使用 zai/glm-5.2、max_turns=90；Astra 模型标识不透明、max_turns=50，不能把差异单独归因于 runner。",
            "Astra rounds 与 Hermes api_call_count、Astra ToolCallFailed 与 Hermes tool.completed.error 是近似映射，不是完全相同的埋点。",
            "Astra 的 23 个 journal token 是可观测下界；Hermes 1 个 launcher 失败没有 session/token。",
            "两边全部 formal_score_eligible=false，结果均为探索性而非正式 C0 分数。",
            "CPU、RAM、GPU、磁盘、网络字节和实际美元成本不可比较。",
        ],
    }

    write_csv(HERMES_CSV, hermes_rows)
    write_csv(MATCHED_CSV, matched)
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "hermes_rows": len(hermes_rows),
                "matched_rows": len(matched),
                "hermes_csv": str(HERMES_CSV),
                "matched_csv": str(MATCHED_CSV),
                "summary_json": str(SUMMARY_JSON),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
