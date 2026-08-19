#!/usr/bin/env python3
"""Merge MaxKB Lenovo formal recoveries and run the frozen Lenovo judge.

The MaxKB public OpenAI response omits retrieval details.  MaxKB's authenticated
chat-record detail endpoint retains the exact context injected into generation,
so this scorer uses that context for claim/answerability judging.  The chat
record does not preserve PDF page lineage; page-level evidence metrics are
therefore explicitly nulled instead of being inferred from answer text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lenovo_bench_fastgpt_eval import score_rows  # noqa: E402
from score_dify_lenovo_bench import (  # noqa: E402
    QianfanJudge,
    citations_from_answer,
    parse_env,
    read_jsonl,
    safe_name,
    source_name,
    write_json,
    write_jsonl,
)


DEFAULT_ROOT = ROOT / "runs/maxkb-lenovo-bench-20260813"
DEFAULT_PACKAGE = DEFAULT_ROOT / "lenovo-bench-chunked-text-v1/package"
DEFAULT_OUTPUT = DEFAULT_ROOT / "maxkb-local-lenovo-bench-merged-judge-v1"
DEFAULT_RUNS = (
    DEFAULT_ROOT / "maxkb-local-lenovo-bench-chunked-text-v1",
    DEFAULT_ROOT / "maxkb-local-lenovo-bench-qianfan-retry-v1",
    DEFAULT_ROOT / "maxkb-local-lenovo-bench-qianfan-retry2-v1",
)
DEFAULT_MANIFEST = ROOT / "datasets/lenovo-bench/moi-corpus-100q-v1/corpus_manifest.jsonl"
DEFAULT_ADMIN_TOKEN = ROOT / ".local-services/maxkb_local/secrets/admin.token"


def response_body(path: Path) -> dict[str, Any]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    body = (artifact.get("response") or {}).get("body")
    return body if isinstance(body, dict) else {}


def successful_qa_artifact(run_root: Path, question_id: str) -> Path | None:
    pattern = f"*-maxkb-openai-qa-{safe_name(question_id)}_repeat-1.json"
    for path in reversed(sorted((run_root / "http").glob(pattern))):
        body = response_body(path)
        choices = body.get("choices") or []
        if choices and isinstance(choices[0], dict) and choices[0].get("chat_id"):
            return path
    return None


def application_id(run_root: Path) -> str:
    payload = json.loads((run_root / "resource-map.json").read_text(encoding="utf-8"))
    resource = (payload.get("resources") or {}).get("__global__") or {}
    value = resource.get("app_id") or resource.get("application_id")
    if not value:
        raise RuntimeError(f"MAXKB_APPLICATION_ID_MISSING:{run_root}")
    return str(value)


class MaxKBAdmin:
    def __init__(self, token_path: Path, base_url: str):
        self.token = token_path.read_text(encoding="utf-8").strip()
        if not self.token:
            raise RuntimeError("MAXKB_ADMIN_TOKEN_MISSING")
        self.base_url = base_url.rstrip("/")

    def get(self, path: str) -> dict[str, Any]:
        request = Request(
            self.base_url + path,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            method="GET",
        )
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if int(payload.get("code", 0) or 0) != 200:
            raise RuntimeError(f"MAXKB_ADMIN_ERROR:{payload.get('message', payload)}")
        return payload

    def chat_detail(self, application: str, chat_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        prefix = f"/workspace/default/application/{application}/chat/{chat_id}/chat_record"
        listing = self.get(prefix + "?order_asc=true")
        records = listing.get("data") or []
        if not records:
            raise RuntimeError(f"MAXKB_CHAT_RECORD_MISSING:{chat_id}")
        record_id = str(records[-1].get("id") or "")
        if not record_id:
            raise RuntimeError(f"MAXKB_CHAT_RECORD_ID_MISSING:{chat_id}")
        detail = self.get(prefix + f"/{record_id}")
        return listing, detail


def step(detail: dict[str, Any], step_type: str) -> dict[str, Any]:
    execution = (detail.get("data") or {}).get("execution_details") or []
    return next(
        (
            item
            for item in execution
            if isinstance(item, dict) and (item.get("step_type") == step_type or item.get("type") == step_type)
        ),
        {},
    )


def exact_generation_context(detail: dict[str, Any]) -> str:
    chat = step(detail, "chat_step")
    messages = chat.get("message_list") or []
    user_text = "\n".join(
        str(message.get("content") or "")
        for message in messages
        if isinstance(message, dict) and message.get("role") == "user"
    )
    match = re.search(r"<data>(.*?)</data>", user_text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    paragraphs = (detail.get("data") or {}).get("paragraph_list") or []
    return "\n\n".join(str(item.get("content") or "") for item in paragraphs if isinstance(item, dict)).strip()


def paragraph_chunks(detail: dict[str, Any], title_to_source: dict[str, str]) -> list[dict[str, Any]]:
    paragraphs = (detail.get("data") or {}).get("paragraph_list") or []
    chunks: list[dict[str, Any]] = []
    for rank, paragraph in enumerate(paragraphs, start=1):
        if not isinstance(paragraph, dict):
            continue
        title = source_name(paragraph.get("document_name") or paragraph.get("title"))
        chunks.append(
            {
                "rank": rank,
                "source_file": title_to_source.get(title, title),
                "pdf_page": 0,
                "content": str(paragraph.get("content") or ""),
                "score": paragraph.get("comprehensive_score", paragraph.get("similarity")),
                "document_name": title,
            }
        )
    return chunks


def build_rows(
    run_roots: list[Path],
    package: Path,
    output: Path,
    admin: MaxKBAdmin,
) -> list[dict[str, Any]]:
    questions = {str(row["question_id"]): row for row in read_jsonl(package / "questions.jsonl")}
    if len(questions) != 60:
        raise RuntimeError(f"MAXKB_FORMAL_QUESTION_COUNT:{len(questions)}")
    corpus = read_jsonl(package / "corpus.jsonl")
    title_to_source = {
        source_name(row.get("title") or row.get("path")): source_name((row.get("metadata") or {}).get("source_file"))
        for row in corpus
    }
    successes: dict[str, tuple[dict[str, Any], Path, Path]] = {}
    for run_root in run_roots:
        qa_rows = [row for row in read_jsonl(run_root / "terminal-ledger.jsonl") if row.get("stage") == "qa"]
        for qa in qa_rows:
            question_id = str(qa.get("question_id") or "")
            if question_id not in questions or question_id in successes or qa.get("status") != "SUCCESS":
                continue
            artifact = successful_qa_artifact(run_root, question_id)
            if artifact is not None and str(qa.get("answer") or "").strip():
                successes[question_id] = (qa, artifact, run_root)
    missing = sorted(set(questions) - set(successes))
    if missing:
        raise RuntimeError(f"MAXKB_MERGED_QA_INCOMPLETE:{missing}")

    detail_root = output / "chat-records"
    rows: list[dict[str, Any]] = []
    for ordinal, question_id in enumerate(questions, start=1):
        qa, artifact, run_root = successes[question_id]
        body = response_body(artifact)
        choice = (body.get("choices") or [])[0]
        chat_id = str(choice.get("chat_id") or "")
        app_id = application_id(run_root)
        listing_path = detail_root / f"{question_id}-list.json"
        detail_path = detail_root / f"{question_id}-detail.json"
        if listing_path.is_file() and detail_path.is_file():
            listing = json.loads(listing_path.read_text(encoding="utf-8"))
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
        else:
            listing, detail = admin.chat_detail(app_id, chat_id)
            write_json(listing_path, listing)
            write_json(detail_path, detail)
        search = step(detail, "search_step")
        chat = step(detail, "chat_step")
        context = exact_generation_context(detail)
        if not context:
            raise RuntimeError(f"MAXKB_GENERATION_CONTEXT_MISSING:{question_id}")
        recorded_answer = str((detail.get("data") or {}).get("answer_text") or "").strip()
        ledger_answer = str(qa.get("answer") or "").strip()
        if recorded_answer != ledger_answer:
            raise RuntimeError(f"MAXKB_CHAT_RECORD_ANSWER_MISMATCH:{question_id}")
        row = {
            "ordinal": ordinal,
            "question_id": question_id,
            "case": questions[question_id],
            "answer": ledger_answer,
            "status": "success",
            "chunks": paragraph_chunks(detail, title_to_source),
            "judge_contexts": [context],
            "citations": citations_from_answer(str(qa.get("answer") or "")),
            "retrieval_latency_ms": float(search.get("run_time", 0.0) or 0.0) * 1000,
            "generation_latency_ms": float(chat.get("run_time", 0.0) or 0.0) * 1000,
            "source_run": run_root.name,
            "source_artifact": str(artifact.relative_to(ROOT)),
            "chat_id": chat_id,
            "chat_record_detail": str(detail_path.relative_to(output)),
            "context_contract": "maxkb_chat_record_exact_generation_context",
        }
        rows.append(row)
        print(f"prepared {ordinal:02d}/60 {question_id} context_chars={len(context)}", flush=True)
    return rows


def null_page_metrics(metrics: dict[str, Any]) -> None:
    for cutoff in (1, 3, 5, 10):
        for prefix in (
            "evidence_any_recall_at_",
            "evidence_fraction_recall_at_",
            "complete_evidence_set_recall_at_",
            "context_precision_at_",
            "evidence_mrr_at_",
        ):
            metrics[prefix + str(cutoff)] = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-root", type=Path, action="append", default=[])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--admin-token", type=Path, default=DEFAULT_ADMIN_TOKEN)
    parser.add_argument("--base-url", default="http://127.0.0.1:8090/admin/api")
    parser.add_argument("--judge-provider", choices=("maas", "qianfan"), default="maas")
    parser.add_argument("--judge-model", default="deepseek-v4-flash")
    parser.add_argument("--judge-workers", type=int, default=4)
    parser.add_argument("--skip-judge", action="store_true")
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    run_roots = [path.expanduser().resolve() for path in (args.run_root or list(DEFAULT_RUNS))]
    admin = MaxKBAdmin(args.admin_token.expanduser().resolve(), args.base_url)
    rows = build_rows(run_roots, args.package.expanduser().resolve(), output, admin)

    judge_ledger_path = output / f"lenovo-judge-ledger.{args.judge_provider}.jsonl"
    judged_by_id = {str(row.get("question_id")): row for row in read_jsonl(judge_ledger_path)}
    if not args.skip_judge:
        if args.judge_provider == "maas":
            configured = parse_env(ROOT / ".env")
            env = {
                "QIANFAN_API_KEY": configured.get("MAAS_API_KEY", ""),
                "QIANFAN_BASE_URL": configured.get("MAAS_BASE_URL", "https://api.modelarts-maas.com/v1"),
                "QIANFAN_LLM_MODEL": configured.get("MAAS_LLM_MODEL", args.judge_model),
            }
        else:
            env = parse_env(ROOT / ".env")
            env.update({key: value for key, value in os.environ.items() if key.startswith("QIANFAN_") and value})
        judge_root = output / f"judge-{args.judge_provider}"
        judge = QianfanJudge(judge_root, env, args.judge_model)
        pending: list[dict[str, Any]] = []
        for row in rows:
            question_id = row["question_id"]
            prior = judged_by_id.get(question_id)
            if isinstance(prior, dict) and (prior.get("judge") or {}).get("status") == "success":
                row["judge"] = prior["judge"]
                print(f"judge resumed {question_id}", flush=True)
                continue
            pending.append(row)

        def judge_one(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            result = judge.judge(row["case"], row["answer"], row["judge_contexts"], row["question_id"])
            return row, result

        completed = sum((item.get("judge") or {}).get("status") == "success" for item in rows)
        with ThreadPoolExecutor(max_workers=max(1, args.judge_workers)) as executor:
            futures = [executor.submit(judge_one, row) for row in pending]
            for future in as_completed(futures):
                row, result = future.result()
                question_id = row["question_id"]
                row["judge"] = result
                judged_by_id[question_id] = {
                    "question_id": question_id,
                    "judge": result,
                    "judge_provider": args.judge_provider,
                    "judge_model": args.judge_model,
                    "context_contract": row["context_contract"],
                    "chat_record_detail": row["chat_record_detail"],
                }
                write_jsonl(judge_ledger_path, [judged_by_id[key] for key in sorted(judged_by_id)])
                completed += int(result.get("status") == "success")
                print(f"judge {completed:02d}/60 {question_id} status={result.get('status')}", flush=True)
                error = str(result.get("error") or "")
                if result.get("status") != "success" and (
                    "HTTP_401:" in error or "HTTP_403:" in error or "account_overdue" in error
                ):
                    raise RuntimeError(f"JUDGE_PROVIDER_AUTH_OR_BILLING:{error}")

    manifest = read_jsonl(args.manifest.expanduser().resolve())
    metrics = score_rows(rows, manifest)
    null_page_metrics(metrics)
    metrics.update(
        {
            "schema": "lenovo-bench-maxkb-merged-posthoc-metrics-v1",
            "dataset": "lenovo-bench",
            "split": "formal",
            "system": "maxkb_local",
            "condition": "controlled-parsed-text-chunked",
            "planned_questions": 60,
            "merged_successful_questions": len(rows),
            "initial_successful_questions": 47,
            "recovered_questions": 13,
            "judge_provider": args.judge_provider,
            "judge_model": args.judge_model,
            "judge_context_contract": "maxkb_chat_record_exact_generation_context",
            "retrieval_trace_contract": "authenticated_chat_record_search_step",
            "page_lineage_available": False,
            "page_metric_note": "MaxKB chat records preserve exact generation context and source documents but not PDF page lineage; page evidence metrics are N/A.",
        }
    )
    serializable_rows = [{key: value for key, value in row.items() if key != "judge_contexts"} for row in rows]
    write_jsonl(output / "lenovo-scored-rows.jsonl", serializable_rows)
    write_json(output / "lenovo-metrics.json", metrics)
    summary = {
        "status": "success" if metrics.get("judge_valid_n") == 60 else "partial",
        "output": str(output),
        "headline_formal": metrics,
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
