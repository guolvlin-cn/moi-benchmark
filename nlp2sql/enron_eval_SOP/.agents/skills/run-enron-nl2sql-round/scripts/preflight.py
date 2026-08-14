#!/usr/bin/env python3
"""Read-only environment preflight for one Enron NL2SQL product round."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SOP_ROOT = SKILL_ROOT.parents[2]
MODEL = "qwen3.7-plus-2026-05-26"
QUESTIONS = SOP_ROOT / "benchmark/questions/user/questions_enron_50_user_mix.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读检查单轮评测环境")
    parser.add_argument("--product", required=True, choices=("chat2db", "wren", "moi"))
    parser.add_argument("--wren-config", type=Path)
    parser.add_argument("--knowledge-name")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def tcp_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def result(name: str, ok: bool, detail: str, blocking: bool = True) -> dict[str, Any]:
    return {"name": name, "ok": ok, "blocking": blocking, "detail": detail}


def common_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    required = [
        QUESTIONS,
        SOP_ROOT / "scripts/run_one_round.py",
        SOP_ROOT / "scripts/validate_one_round.py",
        SOP_ROOT / "scripts/verify_csv_files.py",
    ]
    missing = [str(path) for path in required if not path.exists()]
    checks.append(result("sop_files", not missing, "齐全" if not missing else f"缺少：{missing}"))

    try:
        rows = [line for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
        ids = [line.split("\t", 1)[0] for line in rows if "\t" in line]
        questions_ok = len(rows) == 50 and len(ids) == 50 and len(set(ids)) == 50
        detail = f"{len(rows)}题，{len(set(ids))}个唯一题号"
    except OSError as exc:
        questions_ok, detail = False, str(exc)
    checks.append(result("frozen_questions", questions_ok, detail))

    configured_model = os.getenv("ENRON_EVAL_MODEL", MODEL)
    checks.append(
        result(
            "fixed_model",
            configured_model == MODEL,
            MODEL if configured_model == MODEL else f"环境变量设置为{configured_model}",
        )
    )
    missing_modules = [name for name in ("requests", "pymysql", "yaml") if importlib.util.find_spec(name) is None]
    checks.append(
        result(
            "python_dependencies",
            not missing_modules,
            "齐全" if not missing_modules else f"缺少：{', '.join(missing_modules)}",
        )
    )
    return checks


def chat2db_checks() -> list[dict[str, Any]]:
    checks = [result("macos", sys.platform == "darwin", sys.platform)]
    log_path = Path.home() / ".chat2db/chat2db-enterprise/logs/application.log"
    checks.append(result("chat2db_log", log_path.exists(), str(log_path)))
    process_ok = False
    if shutil.which("pgrep"):
        completed = subprocess.run(
            ["pgrep", "-f", "Chat2DB"], capture_output=True, text=True, check=False
        )
        process_ok = completed.returncode == 0
    checks.append(result("chat2db_process", process_ok, "运行中" if process_ok else "未检测到"))
    checks.append(result("osascript", shutil.which("osascript") is not None, "可用" if shutil.which("osascript") else "缺失"))
    return checks


def wren_checks(config: Path | None) -> list[dict[str, Any]]:
    checks = [
        result(
            "wren_endpoint",
            tcp_open("127.0.0.1", 3000),
            "127.0.0.1:3000可连接" if tcp_open("127.0.0.1", 3000) else "127.0.0.1:3000不可连接",
        )
    ]
    if not config:
        checks.append(result("wren_private_config", False, "必须提供--wren-config"))
        return checks
    config = config.expanduser().resolve()
    if not config.exists():
        checks.append(result("wren_private_config", False, f"文件不存在：{config}"))
        return checks
    text = config.read_text(encoding="utf-8")
    model_ok = re.search(rf"(?m)^\s*model:\s*openai/{re.escape(MODEL)}\s*$", text) is not None
    checks.append(result("wren_private_config", model_ok, str(config)))
    checks.append(result("wren_temperature_zero", re.search(r"(?m)^\s*temperature:\s*0(?:\.0)?\s*$", text) is not None, "temperature=0"))
    checks.append(result("wren_max_tokens", re.search(r"(?m)^\s*max_tokens:\s*4096\s*$", text) is not None, "max_tokens=4096"))
    bridge = tcp_open("127.0.0.1", 13306)
    checks.append(
        result(
            "mysql_ipv4_bridge",
            bridge,
            "127.0.0.1:13306可连接" if bridge else "未检测到；仅当Wren使用13306桥接时才需要",
            blocking=False,
        )
    )
    return checks


def moi_checks(knowledge_name: str | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for variable in ("MOI_EMAIL", "MOI_PASSWORD", "MOI_WORKSPACE_ID"):
        present = bool(os.getenv(variable, "").strip())
        checks.append(result(variable.lower(), present, "已设置" if present else "未设置"))
    checks.append(result("knowledge_name", bool((knowledge_name or "").strip()), "已提供" if knowledge_name else "必须提供--knowledge-name"))
    base_url = os.getenv("MOI_BASE_URL", "http://localhost:18002")
    uc_url = os.getenv("MOI_UC_URL", "http://127.0.0.1:19080")
    for name, url, default_port in (("moi_frontend", base_url, 18002), ("moi_uc", uc_url, 19080)):
        match = re.match(r"^https?://(\[[^]]+\]|[^:/]+)(?::(\d+))?", url)
        host = match.group(1).strip("[]") if match else "127.0.0.1"
        port = int(match.group(2)) if match and match.group(2) else default_port
        opened = tcp_open(host, port)
        checks.append(result(name, opened, f"{host}:{port}" + ("可连接" if opened else "不可连接")))
    return checks


def main() -> int:
    args = parse_args()
    checks = common_checks()
    if args.product == "chat2db":
        checks.extend(chat2db_checks())
    elif args.product == "wren":
        checks.extend(wren_checks(args.wren_config))
    else:
        checks.extend(moi_checks(args.knowledge_name))

    failed = [item for item in checks if item["blocking"] and not item["ok"]]
    report = {
        "product": args.product,
        "model": MODEL,
        "sop_root": str(SOP_ROOT),
        "ready": not failed,
        "checks": checks,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            label = "OK" if item["ok"] else ("WARN" if not item["blocking"] else "FAIL")
            print(f"{label:4} {item['name']}: {item['detail']}")
        print("READY" if not failed else f"BLOCKED：{len(failed)}项必须修复")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
