#!/usr/bin/env python3
"""验证Qwen3.7四组冻结结果的结构、指标和文件哈希。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL = "qwen3.7-plus-2026-05-26"
QUESTIONS = ROOT / "benchmark/questions/user/questions_enron_50_user_mix.txt"
SETS = {
    "chat2db": {
        "dir": ROOT / "reference_results/qwen37/chat2db",
        "evaluation": "evaluation.json",
        "accuracy": (77, 150),
        "sql_success": (150, 150),
        "repeat_correct": (21, 50),
    },
    "wren_rerun": {
        "dir": ROOT / "reference_results/qwen37/wren",
        "evaluation": "evaluation.json",
        "accuracy": (49, 150),
        "sql_success": (114, 150),
        "repeat_correct": (12, 50),
    },
    "moi_no_semantic": {
        "dir": ROOT / "reference_results/qwen37/moi_no_semantic",
        "evaluation": "evaluation_native.json",
        "accuracy": (85, 150),
        "sql_success": (150, 150),
        "repeat_correct": (26, 50),
    },
    "moi_with_semantic": {
        "dir": ROOT / "reference_results/qwen37/moi_with_semantic",
        "evaluation": "evaluation_native.json",
        "accuracy": (99, 150),
        "sql_success": (146, 150),
        "repeat_correct": (29, 50),
    },
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def metric_pair(metrics: dict, key: str) -> tuple[int, int]:
    metric = metrics[key]
    return int(metric["numerator"]), int(metric["denominator"])


def verify_hashes() -> None:
    checksum_file = ROOT / "provenance/CHECKSUMS.sha256"
    frozen_prefixes = (
        "benchmark/",
        "data/",
        "database/",
        "reference_results/",
        "scoring_code/",
        "semantic/",
    )
    frozen_files = {"provenance/freeze_manifest.json"}
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(None, 1)
        relative = relative.lstrip("*")
        if relative not in frozen_files and not relative.startswith(frozen_prefixes):
            continue
        path = ROOT / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"文件哈希变化：{relative}"


def main() -> int:
    question_map = {
        line.split("\t", 1)[0]: line.split("\t", 1)[1]
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert len(question_map) == 50, "问题文件不是50题"

    for name, spec in SETS.items():
        run_info = json.loads((spec["dir"] / "run.json").read_text(encoding="utf-8"))
        assert run_info.get("model") == MODEL, f"{name}运行配置中的模型不一致"
        records = load_jsonl(spec["dir"] / "predictions.jsonl")
        assert len(records) == 150, f"{name}不是150条"
        keys = Counter(
            (str(item.get("question_id") or item.get("case_id")), int(item["repeat_index"]))
            for item in records
        )
        assert len(keys) == 150 and all(count == 1 for count in keys.values()), f"{name}存在重复题轮"
        assert set(key[0] for key in keys) == set(question_map), f"{name}题号覆盖不完整"
        assert set(key[1] for key in keys) == {1, 2, 3}, f"{name}轮次不完整"
        for item in records:
            question_id = str(item.get("question_id") or item.get("case_id"))
            assert item.get("question") == question_map[question_id], f"{name}/{question_id}问题文本不一致"
            record_model = (item.get("metadata") or {}).get("model")
            if record_model is not None:
                assert record_model == MODEL, f"{name}/{question_id}模型不一致"

        evaluation = json.loads((spec["dir"] / spec["evaluation"]).read_text(encoding="utf-8"))
        metrics = evaluation["metrics"]
        assert metric_pair(metrics, "execution_accuracy") == spec["accuracy"], f"{name}准确率变化"
        assert metric_pair(metrics, "sql_success_rate") == spec["sql_success"], f"{name}SQL成功率变化"
        assert metric_pair(metrics, "repeat_correct_rate") == spec["repeat_correct"], f"{name}稳定率变化"
        print(f"OK  {name}: 150条，50题×3轮，指标一致")

    verify_hashes()
    print("OK  冻结文件SHA256全部一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
