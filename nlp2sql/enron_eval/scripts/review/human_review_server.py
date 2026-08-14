#!/usr/bin/env python3
"""Serve a local, side-by-side human review UI for failed NL2SQL attempts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = Path(__file__).with_name("human_review.html")
CASES_PATH = PROJECT_ROOT / "benchmark/cases/cases_enron_50.yaml"
DETAILED_SPECS_PATH = (
    PROJECT_ROOT / "benchmark/questions/spec/questions_enron_50_detailed_spec.txt"
)
CONVENTIONS_PATH = PROJECT_ROOT / "benchmark/questions/spec/evaluation_conventions.md"
ANNOTATIONS_PATH = (
    PROJECT_ROOT
    / "../enron_eval_SOP/reviews/qwen37/chat2db_wren/annotations.json"
)
EVALUATIONS = {
    "chat2db": PROJECT_ROOT
    / "../enron_eval_SOP/reference_results/qwen37/chat2db/evaluation.json",
    "wren": PROJECT_ROOT
    / "../enron_eval_SOP/reference_results/qwen37/wren/evaluation.json",
}
PREDICTIONS = {
    "chat2db": PROJECT_ROOT
    / "../enron_eval_SOP/reference_results/qwen37/chat2db/predictions.jsonl",
    "wren": PROJECT_ROOT
    / "../enron_eval_SOP/reference_results/qwen37/wren/predictions.jsonl",
}
CASE_PREFIX = re.compile(r"^(e\d{2}|m\d{2}|h\d{2})")
VALID_VERDICTS = {"full", "partial", "incorrect", "pending"}
VALID_ERROR_TYPES = {
    "",
    "ambiguous_question_or_golden",
    "case_or_collation",
    "extra_or_missing_columns",
    "wrong_table_or_column",
    "where_filter",
    "join_logic",
    "aggregation_or_grouping",
    "order_or_limit",
    "date_handling",
    "sql_dialect",
    "no_sql",
    "other",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def short_id(value: str) -> str:
    match = CASE_PREFIX.match(value)
    return match.group(1) if match else value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detailed_specs() -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in DETAILED_SPECS_PATH.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        case_id, text = raw.split("\t", 1)
        result[short_id(case_id.strip())] = text.strip()
    return result


def source_runs() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for product, evaluation_path in EVALUATIONS.items():
        report = read_json(evaluation_path)
        result[product] = {
            "run_id": report.get("run_id"),
            "evaluation": str(evaluation_path.resolve()),
            "evaluation_sha256": sha256(evaluation_path),
            "predictions": str(PREDICTIONS[product].resolve()),
            "predictions_sha256": sha256(PREDICTIONS[product]),
        }
    return result


def compact_record(product: str, record: dict[str, Any]) -> dict[str, Any]:
    if product == "moi" or product.startswith("moi_"):
        candidates = [
            {
                "sql": item.get("sql") or "",
                "columns": item.get("columns") or [],
                "row_count": item.get("row_count"),
                "sample": item.get("sample") or [],
                "reason": item.get("reason") or "",
                "exact_match": bool(item.get("passed")),
                "combined": bool(item.get("combined_candidate")),
            }
            for item in (record.get("candidate_results") or record.get("candidates") or [])
        ]
        if not candidates and record.get("generated_sql"):
            candidates = [{
                "sql": record.get("generated_sql") or "",
                "columns": [],
                "row_count": None,
                "sample": [],
                "reason": record.get("reason") or "",
                "exact_match": False,
                "combined": False,
            }]
    else:
        candidates = [{
            "sql": record.get("pred_sql") or "",
            "columns": record.get("pred_columns") or [],
            "row_count": record.get("pred_row_count"),
            "sample": record.get("pred_sample") or [],
            "reason": record.get("reason") or "",
            "exact_match": bool(record.get("execution_correct")),
            "combined": False,
        }]

    return {
        "repeat_index": record.get("repeat_index"),
        "auto_correct": bool(record.get("execution_correct")),
        "sql_success": bool(record.get("sql_success")),
        "generation_status": record.get("generation_status"),
        "reason": record.get("reason") or "",
        "candidates": candidates,
        "latency_ms": record.get("latency_ms"),
        "total_tokens": record.get("total_tokens"),
    }


def build_review_data() -> dict[str, Any]:
    cases_doc = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    cases = {short_id(item["case_id"]): item for item in cases_doc["cases"]}
    specs = detailed_specs()
    groups: list[dict[str, Any]] = []
    product_metrics: dict[str, Any] = {}

    for product, path in EVALUATIONS.items():
        report = read_json(path)
        source_by_key = {
            (short_id(item["question_id"]), int(item["repeat_index"])): item
            for item in read_jsonl(PREDICTIONS[product])
        }
        product_metrics[product] = report.get("metrics") or {}
        records_by_case: dict[str, list[dict[str, Any]]] = {}
        for record in report.get("records") or []:
            records_by_case.setdefault(short_id(record["case_id"]), []).append(record)

        for case_key, records in records_by_case.items():
            if all(record.get("execution_correct") for record in records):
                continue
            case = cases[case_key]
            reference = records[0]
            groups.append(
                {
                    "key": f"{product}:{case_key}",
                    "product": product,
                    "case_key": case_key,
                    "case_id": case["case_id"],
                    "difficulty": case["difficulty"],
                    "question": case["question"],
                    "detailed_spec": specs.get(case_key, ""),
                    "gold_sql": case["gold_sql"],
                    "gold_columns": reference.get("gold_columns") or [],
                    "gold_row_count": reference.get("gold_row_count"),
                    "gold_sample": reference.get("gold_sample") or [],
                    "attempts": [],
                }
            )
            for item in sorted(records, key=lambda value: value["repeat_index"]):
                attempt = compact_record(product, item)
                source = source_by_key.get((case_key, int(item["repeat_index"])), {})
                attempt["final_answer"] = source.get("raw_answer") or ""
                groups[-1]["attempts"].append(attempt)

    order = {"easy": 0, "medium": 1, "hard": 2}
    groups.sort(key=lambda item: (item["product"], order[item["difficulty"]], item["case_key"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "automatic_failures_only",
        "review_title": "Chat2DB 与 Wren（二次重跑）人工审核",
        "source_runs": source_runs(),
        "evaluation_conventions": CONVENTIONS_PATH.read_text(encoding="utf-8"),
        "products": product_metrics,
        "groups": groups,
        "annotations": load_annotations().get("annotations", {}),
    }


def load_annotations() -> dict[str, Any]:
    if not ANNOTATIONS_PATH.exists():
        return {"schema_version": 1, "annotations": {}}
    return read_json(ANNOTATIONS_PATH)


def save_annotations(payload: dict[str, Any]) -> dict[str, Any]:
    annotations = payload.get("annotations")
    if not isinstance(annotations, dict):
        raise ValueError("annotations 必须是对象")
    for key, item in annotations.items():
        if not isinstance(key, str) or not isinstance(item, dict):
            raise ValueError("标注格式错误")
        if item.get("verdict", "pending") not in VALID_VERDICTS:
            raise ValueError(f"不支持的审核结论：{item.get('verdict')}")
        if item.get("error_type", "") not in VALID_ERROR_TYPES:
            raise ValueError(f"不支持的错误类型：{item.get('error_type')}")

    document = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "review_scope": "automatic_failures_only",
        "source_runs": source_runs(),
        "scoring": {"full": 1, "partial": 0.5, "incorrect": 0},
        "annotations": annotations,
    }
    ANNOTATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=ANNOTATIONS_PATH.parent, delete=False
    ) as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(ANNOTATIONS_PATH)
    return document


class ReviewHandler(BaseHTTPRequestHandler):
    def send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/review-data":
            self.send_json(build_review_data())
            return
        if path in {"/", "/index.html"}:
            body = HTML_PATH.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/annotations":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self.send_json(save_annotations(payload))
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, message: str, *args: Any) -> None:
        print(f"[review] {self.address_string()} {message % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 Enron NL2SQL 人工审核页面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--product", default="")
    parser.add_argument("--evaluation", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--annotations", type=Path)
    return parser.parse_args()


def main() -> int:
    global EVALUATIONS, PREDICTIONS, ANNOTATIONS_PATH
    args = parse_args()
    if args.evaluation or args.predictions:
        if not args.evaluation or not args.predictions or not args.product:
            raise ValueError("自定义审核必须同时提供 --product、--evaluation 和 --predictions")
        EVALUATIONS = {args.product: args.evaluation.resolve()}
        PREDICTIONS = {args.product: args.predictions.resolve()}
    if args.annotations:
        ANNOTATIONS_PATH = args.annotations.resolve()
    server = ThreadingHTTPServer((args.host, args.port), ReviewHandler)
    print(f"人工审核页面：http://{args.host}:{args.port}")
    print(f"标注文件：{ANNOTATIONS_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
