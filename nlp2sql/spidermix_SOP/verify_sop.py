#!/usr/bin/env python3
"""验证Spider Mix50统一模型正式结果与冻结清单。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pair(metrics: dict, key: str) -> list[int]:
    return [int(metrics[key]["numerator"]), int(metrics[key]["denominator"])]


def main() -> int:
    manifest = load_json(ROOT / "provenance/freeze_manifest.json")
    if manifest["model"] != "qwen3.7-plus-2026-05-26":
        raise AssertionError("模型快照不一致")
    for product, spec in manifest["runs"].items():
        directory = ROOT / spec["directory"]
        run = load_json(directory / "run.json")
        evaluation = load_json(directory / "evaluation.json")
        predictions = load_jsonl(directory / "predictions.jsonl")
        if run.get("model") != manifest["model"]:
            raise AssertionError(f"{product}模型不一致")
        if len(predictions) != 50:
            raise AssertionError(f"{product}预测不是50条")
        case_ids = {str(item.get("question_id") or item.get("case_id")) for item in predictions}
        if len(case_ids) != 50:
            raise AssertionError(f"{product}题号不完整或重复")
        metrics = evaluation["metrics"]
        if pair(metrics, "execution_accuracy") != spec["execution_accuracy"]:
            raise AssertionError(f"{product}正确率变化")
        if pair(metrics, "sql_success_rate") != spec["sql_success_rate"]:
            raise AssertionError(f"{product}SQL成功率变化")
        print(f"OK  {product}: 50题，模型与冻结指标一致")
    print("OK  Spider Mix50统一模型SOP验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
