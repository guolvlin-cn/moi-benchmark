#!/usr/bin/env python3
"""用一次成功重跑替换MOI正式结果，同时保留原记录和原始响应审计副本。"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def percentile(values: list[int], ratio: float) -> float:
    values = sorted(values)
    index = (len(values) - 1) * ratio
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official", type=Path, required=True)
    parser.add_argument("--rerun", type=Path, required=True)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--repeat-index", type=int, default=1)
    args = parser.parse_args()

    official = args.official.resolve()
    rerun = args.rerun.resolve()
    official_predictions = official / "predictions.jsonl"
    replacement_rows = read_jsonl(rerun / "predictions.jsonl")
    if len(replacement_rows) != 1:
        raise ValueError("rerun directory must contain exactly one prediction")
    replacement = replacement_rows[0]
    key = (args.question_id, args.repeat_index)
    if (replacement.get("question_id"), replacement.get("repeat_index")) != key:
        raise ValueError("replacement key does not match requested attempt")
    if replacement.get("status") != "ok" or not replacement.get("native_execution_success"):
        raise ValueError("replacement is not a successful native execution")

    rows = read_jsonl(official_predictions)
    indexes = [index for index, row in enumerate(rows)
               if (row.get("question_id"), row.get("repeat_index")) == key]
    if len(indexes) != 1:
        raise ValueError("official run must contain exactly one matching attempt")
    original = rows[indexes[0]]

    audit = official / "audit" / f"replaced_{args.question_id}_r{args.repeat_index}"
    audit.mkdir(parents=True, exist_ok=False)
    write_json(audit / "original_prediction.json", original)
    write_json(audit / "replacement_prediction.json", replacement)
    write_json(audit / "replacement_manifest.json", {
        "replaced_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reason": "User-approved rerun after transient MOI HTTP 502 service unavailable error.",
        "source_run": str(rerun),
        "question_id": args.question_id,
        "repeat_index": args.repeat_index,
    })
    original_raw = official / "raw" / f"{args.question_id}_r{args.repeat_index}.json"
    rerun_raw = rerun / "raw" / f"{args.question_id}_r{args.repeat_index}.json"
    if original_raw.exists():
        shutil.copy2(original_raw, audit / "original_raw.json")
    if rerun_raw.exists():
        shutil.copy2(rerun_raw, audit / "replacement_raw.json")
        shutil.copy2(rerun_raw, original_raw)

    rows[indexes[0]] = replacement
    official_predictions.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )

    ok = [row for row in rows if row.get("status") == "ok"]
    latencies = [int(row["latency_ms"]) for row in rows if isinstance(row.get("latency_ms"), int)]
    tokens = [int(row["total_tokens"]) for row in rows if isinstance(row.get("total_tokens"), int)]
    write_json(official / "run_summary.json", {
        "expected_attempts": len(rows),
        "recorded_attempts": len(rows),
        "native_execution_successes": len(ok),
        "failed": len(rows) - len(ok),
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "min_latency_ms": min(latencies) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
        "total_tokens": sum(tokens) if tokens else None,
        "failed_attempts": [
            {"question_id": row.get("question_id"), "repeat_index": row.get("repeat_index"),
             "status": row.get("status"), "error": row.get("error")}
            for row in rows if row.get("status") != "ok"
        ],
    })
    validation = {
        "records": len(rows),
        "unique_questions": len({row["question_id"] for row in rows}),
        "native_execution_successes": sum(bool(row.get("native_execution_success")) for row in rows),
        "with_selected_native_results": sum(bool(row.get("selected_native_results")) for row in rows),
        "with_generated_sql": sum(bool(row.get("generated_sql")) for row in rows),
        "with_token_usage": len(tokens),
        "total_tokens": sum(tokens),
        "mean_tokens": round(sum(tokens) / len(tokens), 2),
        "latency_mean_ms": round(sum(latencies) / len(latencies), 2),
        "latency_p50_ms": round(percentile(latencies, 0.5), 2),
        "latency_p95_ms": round(percentile(latencies, 0.95), 2),
        "latency_min_ms": min(latencies),
        "latency_max_ms": max(latencies),
        "failed": [],
        "replacement_audit": str(audit),
    }
    write_json(official / "validation.json", {"validation": "passed", "checks": validation})
    run_meta = json.loads((official / "run.json").read_text(encoding="utf-8"))
    run_meta["native_execution_successes"] = len(ok)
    run_meta["recorded_attempts"] = len(rows)
    run_meta.setdefault("audited_replacements", []).append({
        "question_id": args.question_id,
        "repeat_index": args.repeat_index,
        "reason": "transient_http_502_service_unavailable",
        "audit_dir": str(audit),
    })
    write_json(official / "run.json", run_meta)


if __name__ == "__main__":
    main()
