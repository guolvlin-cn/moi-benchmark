#!/usr/bin/env python3
"""Generate multidimensional tables and a Markdown report from evaluation details."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EVALUATION_DIR = SCRIPT_DIR.parent / "evaluation" / "latest"
DATASETS = ("sroie", "vrdu", "kleister")
SYSTEMS = ("moi", "landingai")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def percent(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value) * 100:.2f}%"


def seconds(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value) / 1000:.2f}s"


def number(value: Any, digits: int = 2) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.{digits}f}"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    rendered = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    rendered.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(rendered)


def build_empty_value_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for dataset in DATASETS:
        for system in SYSTEMS:
            current = [
                row
                for row in details
                if row["dataset"] == dataset and row["system"] == system
            ]
            gold_empty = [row for row in current if not row["gold"]]
            gold_nonempty = [row for row in current if row["gold"]]
            empty_correct = sum(row["normalized_correct"] for row in gold_empty)
            hallucinations = sum(bool(row["prediction"]) for row in gold_empty)
            nonempty_correct = sum(row["normalized_correct"] for row in gold_nonempty)
            missing = sum(not row["prediction"] for row in gold_nonempty)
            wrong = sum(
                bool(row["prediction"]) and not row["normalized_correct"]
                for row in gold_nonempty
            )
            rows.append(
                {
                    "dataset": dataset,
                    "system": system,
                    "gold_empty_count": len(gold_empty),
                    "empty_correct_count": empty_correct,
                    "empty_correct_rate": ratio(empty_correct, len(gold_empty)),
                    "hallucination_count": hallucinations,
                    "hallucination_rate": ratio(hallucinations, len(gold_empty)),
                    "gold_nonempty_count": len(gold_nonempty),
                    "nonempty_correct_count": nonempty_correct,
                    "nonempty_correct_rate": ratio(nonempty_correct, len(gold_nonempty)),
                    "missing_count": missing,
                    "missing_rate": ratio(missing, len(gold_nonempty)),
                    "wrong_value_count": wrong,
                    "wrong_value_rate": ratio(wrong, len(gold_nonempty)),
                }
            )
    return rows


def document_correctness(details: list[dict[str, Any]]) -> dict[tuple[str, str, str], bool]:
    grouped: dict[tuple[str, str, str], list[bool]] = defaultdict(list)
    for row in details:
        grouped[(row["dataset"], row["system"], row["case_id"])].append(
            bool(row["normalized_correct"])
        )
    return {key: all(values) for key, values in grouped.items()}


def build_head_to_head_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    correctness = document_correctness(details)
    rows = []
    for dataset in DATASETS:
        case_ids = sorted(
            {
                row["case_id"]
                for row in details
                if row["dataset"] == dataset
            }
        )
        counts = Counter()
        for case_id in case_ids:
            moi = correctness[(dataset, "moi", case_id)]
            landingai = correctness[(dataset, "landingai", case_id)]
            if moi and landingai:
                counts["both_correct"] += 1
            elif moi:
                counts["moi_only"] += 1
            elif landingai:
                counts["landingai_only"] += 1
            else:
                counts["neither"] += 1
        rows.append(
            {
                "dataset": dataset,
                "case_count": len(case_ids),
                "both_correct": counts["both_correct"],
                "moi_only": counts["moi_only"],
                "landingai_only": counts["landingai_only"],
                "neither": counts["neither"],
            }
        )
    return rows


def build_error_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    error_types = (
        "correct",
        "wrong_value",
        "missing_field",
        "false_positive",
        "array_missing_item",
        "array_extra_item",
        "array_missing_and_extra",
        "system_failure",
    )
    rows = []
    for dataset in DATASETS:
        for system in SYSTEMS:
            current = [
                row
                for row in details
                if row["dataset"] == dataset and row["system"] == system
            ]
            counts = Counter(row["error_type"] for row in current)
            result: dict[str, Any] = {
                "dataset": dataset,
                "system": system,
                "field_decision_count": len(current),
            }
            for error_type in error_types:
                result[error_type] = counts[error_type]
            rows.append(result)
    return rows


def build_report(
    comparison: list[dict[str, str]],
    field_metrics: list[dict[str, str]],
    field_index: dict[tuple[str, str, str], dict[str, str]],
    empty_rows: list[dict[str, Any]],
    head_rows: list[dict[str, Any]],
    error_rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    lines = [
        "# MOI vs LandingAI 信息提取多维评测报告",
        "",
        "本报告只使用最终有效运行结果，不比较或引用此前的错误运行。主指标为三个数据集等权的"
        "标准化字段级 Micro F1。VRDU 中3个由 MOI 所配置模型供应商"
        "内容安全审查拦截的 case 已从双方共同评分集合中排除，因此 VRDU 使用同一组97个 case；"
        "`null`、空字符串和纯空白字符串统一视为空字段。",
        "",
        "评分范围为 SROIE 100份、VRDU 97份、Kleister-NDA 100份，每个产品共297份文档。",
        "",
        "## 1. 总体结论",
        "",
        markdown_table(
            ["产品", "三数据集平均 F1", "平均文档全对率", "完成数", "总体成功率"],
            [
                [
                    system.upper() if system == "moi" else "LandingAI",
                    percent(summary["overall"][system]["dataset_mean_normalized_micro_f1"]),
                    percent(
                        summary["overall"][system][
                            "dataset_mean_normalized_document_exact_match"
                        ]
                    ),
                    f'{summary["overall"][system]["total_completed"]}/'
                    f'{summary["overall"][system]["total_cases"]}',
                    percent(summary["overall"][system]["overall_success_rate"]),
                ]
                for system in SYSTEMS
            ],
        ),
        "",
        "## 2. 数据集级结果",
        "",
        markdown_table(
            [
                "数据集",
                "产品",
                "评分数",
                "P",
                "R",
                "Micro F1",
                "Macro F1",
                "文档全对率",
                "Strict F1",
                "成功率",
                "Schema 合规",
            ],
            [
                [
                    row["dataset"],
                    row["system"],
                    row["case_count"],
                    percent(row["normalized_micro_precision"]),
                    percent(row["normalized_micro_recall"]),
                    percent(row["normalized_micro_f1"]),
                    percent(row["normalized_macro_f1"]),
                    percent(row["normalized_document_exact_match"]),
                    percent(row["strict_micro_f1"]),
                    percent(row["success_rate"]),
                    percent(row["schema_compliance_rate"]),
                ]
                for row in comparison
            ],
        ),
        "",
        "## 3. 字段级 F1",
        "",
        markdown_table(
            ["数据集", "字段", "MOI F1", "LandingAI F1", "差值（MOI-LandingAI）"],
            [
                [
                    dataset,
                    field,
                    percent(field_index[(dataset, "moi", field)]["normalized_f1"]),
                    percent(
                        field_index[(dataset, "landingai", field)]["normalized_f1"]
                    ),
                    f'{(float(field_index[(dataset, "moi", field)]["normalized_f1"]) - float(field_index[(dataset, "landingai", field)]["normalized_f1"])) * 100:+.2f}pp',
                ]
                for dataset in DATASETS
                for field in sorted(
                    {
                        row["field"]
                        for row in field_metrics
                        if row["dataset"] == dataset
                    }
                )
            ],
        ),
        "",
        "## 4. 空字段与非空字段",
        "",
        "空字段误提率衡量 Gold 为空时产品仍返回值的比例；非空漏提率衡量 Gold 有值但产品返回空的比例。",
        "",
        markdown_table(
            [
                "数据集",
                "产品",
                "Gold 空字段数",
                "空字段正确率",
                "空字段误提率",
                "Gold 非空字段数",
                "非空正确率",
                "非空漏提率",
                "非空错值率",
            ],
            [
                [
                    row["dataset"],
                    row["system"],
                    row["gold_empty_count"],
                    (
                        "-"
                        if row["gold_empty_count"] == 0
                        else percent(row["empty_correct_rate"])
                    ),
                    (
                        "-"
                        if row["gold_empty_count"] == 0
                        else percent(row["hallucination_rate"])
                    ),
                    row["gold_nonempty_count"],
                    percent(row["nonempty_correct_rate"]),
                    percent(row["missing_rate"]),
                    percent(row["wrong_value_rate"]),
                ]
                for row in empty_rows
            ],
        ),
        "",
        "## 5. 文档级正面对比",
        "",
        markdown_table(
            [
                "数据集",
                "评分数",
                "双方全对",
                "仅 MOI 全对",
                "仅 LandingAI 全对",
                "双方均未全对",
            ],
            [
                [
                    row["dataset"],
                    row["case_count"],
                    row["both_correct"],
                    row["moi_only"],
                    row["landingai_only"],
                    row["neither"],
                ]
                for row in head_rows
            ],
        ),
        "",
        "## 6. 错误类型",
        "",
        markdown_table(
            [
                "数据集",
                "产品",
                "正确",
                "错值",
                "漏字段",
                "空字段误提",
                "数组混合错误",
                "系统失败字段",
            ],
            [
                [
                    row["dataset"],
                    row["system"],
                    row["correct"],
                    row["wrong_value"],
                    row["missing_field"],
                    row["false_positive"],
                    row["array_missing_and_extra"]
                    + row["array_missing_item"]
                    + row["array_extra_item"],
                    row["system_failure"],
                ]
                for row in error_rows
            ],
        ),
        "",
        "## 7. 耗时与成本",
        "",
        markdown_table(
            ["数据集", "产品", "平均耗时", "P95", "总 Credits", "平均 Credits/Case"],
            [
                [
                    row["dataset"],
                    row["system"],
                    seconds(row["duration_mean_ms"]),
                    seconds(row["duration_p95_ms"]),
                    number(row["total_credits"], 1),
                    (
                        "-"
                        if row["total_credits"] == ""
                        else number(
                            float(row["total_credits"]) / int(row["completed_count"]),
                            2,
                        )
                    ),
                ]
                for row in comparison
            ],
        ),
        "",
        "耗时口径并非完全一致：MOI 使用每个任务从开始到完成的墙钟时间；LandingAI 使用 Parse 与 Extract "
        "响应中报告的服务耗时之和。因此耗时只用于观察当前运行表现，不作为严格同硬件性能结论。MOI 当前没有可比的 credits 数据。",
        "",
        "## 8. 综合评测分析",
        "",
        "- LandingAI 的三数据集平均 F1 为69.77%，比 MOI 的64.57%高5.20个百分点；"
        "平均文档全对率高6.29个百分点，整体开箱准确率领先。",
        "- SROIE 是差距最大的场景，LandingAI F1 高10.66个百分点，并在 company、date、"
        "address、total 四个字段上全部领先；MOI 的主要短板是多行地址。",
        "- VRDU 的总体差距只有2.22个百分点。MOI 的 Precision 高4.25个百分点、文档全对率"
        "高4.12个百分点、空字段误提率低28.48个百分点；LandingAI 的 Recall 高9.37个百分点，"
        "表现为 MOI 更保守、LandingAI 更积极填值。",
        "- VRDU 字段表现存在明显互补：MOI 在 file_date 和 signer_title 上领先，LandingAI 在"
        "registrant_name 和 registration_num 上明显领先。",
        "- Kleister 对双方都很难，F1 均低于50%，主要瓶颈是 party 多实体数组和 jurisdiction。"
        "MOI 文档全对率为5%，LandingAI为2%，但 LandingAI 字段级 F1 仍高2.71个百分点。",
        "- VRDU 的3个供应商内容安全失败作为范围排除项记录，不进入双方准确率和成功率统计。",
        "- MOI Kleister 的 `party` 序列化为单字段对象数组。评测将其视为字符串数组的等价表示，语义评分和 Schema 合规统计均不因此判错。",
        "- Strict 与标准化分数差距较大，说明日期格式、标点、空白、地址换行和数组表示会产生明显落库清洗成本。",
        "",
        "## 9. 产品选择建议",
        "",
        "- 标准收据和快速 API 接入场景：当前更推荐 LandingAI，其 SROIE 准确率和文档全对率"
        "有明确优势。按本次兼容口径，双方三个数据集的 Schema 合规率均为100%。",
        "- 监管表单或错误填值代价较高的场景：MOI 在 VRDU 上具有竞争力。其 Precision、空字段"
        "判断和文档全对率更好，适合宁可返回空值、也不希望写入错误值的策略。",
        "- 强调召回、允许后续人工审核的表单场景：LandingAI 更有优势，其 VRDU 非空字段漏提率"
        "仅0.68%，MOI为11.64%。",
        "- NDA/合同场景：双方都不应直接用于无人审核入库，应采用自动提取后人工复核。"
        "LandingAI 在 effective_date 和 party 上稍好，MOI 在 jurisdiction 和文档全对率上稍好。",
        "- 本次评测没有测试私有部署、工作流编排、模型替换、提示词调优、权限治理或系统集成，"
        "这些能力不能作为本报告验证出的产品优势。",
        "",
        "## 10. 评测局限",
        "",
        "- 每个产品只运行一次，没有通过重复运行评估随机波动和结果稳定性。",
        "- 数据来自三个公开英文数据集，不能直接代表中文文档或公司真实业务文档。",
        "- 没有对争议标注和近似匹配结果进行人工复核，结论依赖冻结的自动评分规则。",
        "- 双方使用各自产品链路，但模型、运行环境和计费方式不同，本次不是同模型或同硬件对照实验。",
        "- 耗时统计口径不同，不能据此得出严格的性能领先结论。",
        "- LandingAI 有 credits 数据，MOI 缺少统一的算力和模型调用成本，因此不能得出完整 TCO 结论。",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-dir", type=Path, default=DEFAULT_EVALUATION_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    comparison = read_csv(args.evaluation_dir / "comparison.csv")
    field_metrics = read_csv(args.evaluation_dir / "field_metrics.csv")
    summary = json.loads((args.evaluation_dir / "summary.json").read_text(encoding="utf-8"))
    details = [
        json.loads(line)
        for line in (args.evaluation_dir / "details.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]

    empty_rows = build_empty_value_rows(details)
    head_rows = build_head_to_head_rows(details)
    error_rows = build_error_rows(details)

    field_index = {
        (row["dataset"], row["system"], row["field"]): row for row in field_metrics
    }
    write_csv(args.evaluation_dir / "empty_value_metrics.csv", empty_rows)
    write_csv(args.evaluation_dir / "head_to_head.csv", head_rows)
    write_csv(args.evaluation_dir / "error_summary.csv", error_rows)
    report = build_report(
        comparison,
        field_metrics,
        field_index,
        empty_rows,
        head_rows,
        error_rows,
        summary,
    )
    (args.evaluation_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"Wrote multidimensional report to {(args.evaluation_dir / 'report.md').resolve()}")


if __name__ == "__main__":
    main()
