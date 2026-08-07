#!/usr/bin/env python3
"""根据正式问题与 Golden SQL 生成统一 cases YAML。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN = PROJECT_ROOT / "benchmark/golden/questions_enron_50_golden.sql"
DEFAULT_QUESTIONS = PROJECT_ROOT / "benchmark/questions/user/questions_enron_50_user_mix.txt"
DEFAULT_OUTPUT = PROJECT_ROOT / "benchmark/cases/cases_enron_50.yaml"
CASE_MARKER = re.compile(r"^--\s+(e\d{2}_[A-Za-z0-9_]+|m\d{2}_[A-Za-z0-9_]+|h\d{2}_[A-Za-z0-9_]+)\s*$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建 Enron 50 题 cases YAML")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def parse_golden(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    matches = list(CASE_MARKER.finditer(text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sql = text[start:end].strip().rstrip(";").strip()
        if not sql:
            raise ValueError(f"Golden SQL 为空：{match.group(1)}")
        result[match.group(1)] = sql
    return result


def parse_questions(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise ValueError(f"问题格式错误：{path}:{line_number}")
        case_id, question = (part.strip() for part in parts)
        if case_id in result:
            raise ValueError(f"问题编号重复：{case_id}")
        result[case_id] = question
    return result


def difficulty(case_id: str) -> str:
    return {"e": "easy", "m": "medium", "h": "hard"}[case_id[0]]


def main() -> int:
    args = parse_args()
    golden = parse_golden(args.golden)
    questions = parse_questions(args.questions)
    if set(golden) != set(questions):
        missing_question = sorted(set(golden) - set(questions))
        missing_golden = sorted(set(questions) - set(golden))
        raise ValueError(f"题目与 Golden SQL 不一致：missing_question={missing_question}, missing_golden={missing_golden}")

    cases = [
        {
            "case_id": case_id,
            "difficulty": difficulty(case_id),
            "question": questions[case_id],
            "gold_sql": golden[case_id],
        }
        for case_id in sorted(golden)
    ]
    if len(cases) != 50:
        raise ValueError(f"正式评测集必须为 50 题，实际为 {len(cases)} 题")

    output = {
        "benchmark_id": "enron_golden50_v1",
        "database": "enron_eval",
        "dialect": "mysql8",
        "tables": [
            "enron_email",
            "enron_emailinfo",
            "enron_emailorig",
            "enron_emailto",
            "enron_emailxto",
            "enron_source",
        ],
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8",
    )
    print(f"已生成 {len(cases)} 题：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
