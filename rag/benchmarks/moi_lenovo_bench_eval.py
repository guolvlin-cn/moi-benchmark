#!/usr/bin/env python3
"""Prepare and score the frozen Lenovo-Bench formal split for MOI RAG."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks import moi_rag_benchmark as legacy

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "lenovo-bench"
GOLD = DATASET / "moi-corpus-100q-v1"
CORPUS = DATASET / "corpus"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evidence_items(question: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for group in question.get("evidence_sets", []) for item in group.get("items", [])]


def prepare(parse_root: Path, output: Path, exclude_results: Path | None = None) -> None:
    manifest = read_jsonl(GOLD / "corpus_manifest.jsonl")
    questions = read_jsonl(GOLD / "questions.formal.jsonl")
    if len(manifest) != 46 or len(questions) != 60:
        raise RuntimeError(f"frozen dataset mismatch: documents={len(manifest)} questions={len(questions)}")
    by_name = {row["source_file"]: row for row in manifest}
    for name, row in by_name.items():
        actual = file_sha256(CORPUS / name)
        if actual != row["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch for {name}: {actual}")

    parsed: list[dict[str, Any]] = []
    parser_inputs: list[dict[str, Any]] = []
    for name, manifest_row in by_name.items():
        stem = Path(name).stem
        candidates = sorted(parse_root.glob(f"parse-*/{stem}/**/documents.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise FileNotFoundError(f"no parsed documents for {name} under {parse_root}")
        source = candidates[0]
        count = 0
        for document in read_jsonl(source):
            metadata = document.setdefault("metadata", {})
            metadata["file_name"] = name
            metadata["source_file_name"] = name
            metadata["benchmark_doc_id"] = manifest_row["doc_id"]
            metadata["source_sha256"] = manifest_row["sha256"]
            metadata["source_uri"] = f"lenovo-bench://{manifest_row['sha256']}/{name}"
            parsed.append(document)
            count += 1
        parser_inputs.append({"source_file": name, "doc_id": manifest_row["doc_id"], "sha256": manifest_row["sha256"], "documents": count, "documents_jsonl": str(source)})
    write_jsonl(output / "moi-documents.jsonl", parsed)

    cases = []
    for question in questions:
        items = evidence_items(question)
        relevant_documents = list(dict.fromkeys(item["source_file"] for item in items))
        cases.append({
            "id": question["question_id"],
            "question": question["question"],
            "retrieval_keywords": [question["question"]],
            "file_ids": [],
            "relevant_documents": relevant_documents,
            "relevant_evidence": [item["evidence_text"] for item in items],
            "expected_answer_keywords": [],
            "expected_answerable": question["answerability"] == "answerable",
            "metadata": question,
        })
    write_jsonl(output / "questions.formal.moi.jsonl", cases)
    write_jsonl(output / "questions.formal.text.moi.jsonl", [row for row in cases if row["metadata"]["primary_type"] != "image_layout"])
    write_jsonl(output / "questions.formal.visual.moi.jsonl", [row for row in cases if row["metadata"]["primary_type"] == "image_layout"])
    if exclude_results is not None:
        completed = {str((row.get("case") or {}).get("id")) for row in read_jsonl(exclude_results) if row.get("status") == "ok"}
        write_jsonl(output / "questions.formal.remaining.moi.jsonl", [row for row in cases if row["id"] not in completed])
        write_jsonl(output / "questions.formal.remaining-text.moi.jsonl", [row for row in cases if row["id"] not in completed and row["metadata"]["primary_type"] != "image_layout"])
    write_json(output / "prepare-manifest.json", {
        "protocol": "Lenovo-Bench native mode; formal split; evidence sets OR and items within one set AND",
        "documents": len(manifest), "parsed_records": len(parsed), "questions": len(cases),
        "corpus_combined_sha256": hashlib.sha256("".join(row["sha256"] for row in manifest).encode()).hexdigest(),
        "parser_inputs": parser_inputs,
    })
    print(f"prepared documents={len(manifest)} records={len(parsed)} questions={len(cases)} output={output}", flush=True)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))]


def location_matches(chunk: dict[str, Any], item: dict[str, Any]) -> bool:
    return Path(str(chunk.get("file_name", ""))).name.lower() == item["source_file"].lower() and int(chunk.get("page_number") or 0) == int(item["pdf_page"])


def retrieval_metrics(row: dict[str, Any], gold: dict[str, Any], k: int) -> dict[str, Any]:
    chunks = (row.get("chunks") or [])[:k]
    groups = gold.get("evidence_sets", [])
    items = evidence_items(gold)
    matched = sum(any(location_matches(chunk, item) for chunk in chunks) for item in items)
    complete = any(all(any(location_matches(chunk, item) for chunk in chunks) for item in group.get("items", [])) for group in groups) if groups else None
    docs = {item["source_file"].lower() for item in items}
    found = {Path(str(chunk.get("file_name", ""))).name.lower() for chunk in chunks}
    return {
        f"evidence_item_recall_at_{k}": matched / len(items) if items else None,
        f"complete_evidence_set_at_{k}": complete,
        f"document_recall_at_{k}": len(docs & found) / len(docs) if docs else None,
    }


def parse_judge(raw: str) -> dict[str, Any] | None:
    return legacy.extract_json_object(raw)


def score(results_paths: list[Path], output: Path, workers: int) -> None:
    results_by_id: dict[str, dict[str, Any]] = {}
    for results_path in results_paths:
        for row in read_jsonl(results_path):
            results_by_id[str((row.get("case") or {}).get("id"))] = row
    results = list(results_by_id.values())
    gold_by_id = {row["question_id"]: row for row in read_jsonl(GOLD / "questions.formal.jsonl")}
    environment = os.environ.copy()
    legacy.load_dotenv(ROOT / ".env", environment)
    existing = {row["id"]: row for row in read_jsonl(output / "judgements.jsonl")} if (output / "judgements.jsonl").is_file() else {}

    def judge_one(row: dict[str, Any]) -> dict[str, Any]:
        case = row.get("case") or {}
        qid = str(case.get("id"))
        gold = gold_by_id[qid]
        claims = gold.get("claims", [])
        prompt = {
            "task": "Evaluate the candidate answer only against the gold atomic claims. Return JSON only.",
            "question": gold["question"], "answerability": gold["answerability"],
            "reference_answer_for_interpretation_only": gold["reference_answer"],
            "claims": claims, "candidate_answer": row.get("answer", ""),
            "rules": [
                "For each claim_id return 1 only if the candidate clearly states the complete claim with all numbers, units, versions and conditions; otherwise 0.",
                "answerability_correct is 1 for answerable questions only if the answer attempts an evidence-based answer, and for unanswerable questions only if it explicitly abstains without inventing the missing fact.",
                "unsupported_claim is 1 if the candidate asserts a material fact not supported by the reference answer/claims; otherwise 0.",
            ],
            "schema": {"claim_scores": {"claim_id": 0}, "answerability_correct": 0, "unsupported_claim": 0, "reason": "short"},
        }
        try:
            raw = legacy.openai_chat(environment, "https://api.modelarts-maas.com/v1", environment.get("MAAS_LLM_MODEL", "qwen3-30b-a3b"), [
                {"role": "system", "content": "You are a strict RAG benchmark judge. Output one JSON object and no markdown."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ], timeout=300, api_key_env="MAAS_API_KEY")
            parsed = parse_judge(raw)
            if not parsed:
                raise ValueError(f"invalid JSON: {raw[:300]}")
            scores = parsed.get("claim_scores") or {}
            normalized = {claim["claim_id"]: 1 if int(scores.get(claim["claim_id"], 0)) == 1 else 0 for claim in claims}
            return {"id": qid, "status": "ok", "claim_scores": normalized, "answerability_correct": 1 if int(parsed.get("answerability_correct", 0)) == 1 else 0, "unsupported_claim": 1 if int(parsed.get("unsupported_claim", 0)) == 1 else 0, "reason": parsed.get("reason"), "raw": raw}
        except Exception as exc:
            return {"id": qid, "status": "failed", "error": str(exc)}

    pending = [row for row in results if row.get("status") == "ok" and existing.get(str((row.get("case") or {}).get("id")), {}).get("status") != "ok"]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(judge_one, row) for row in pending]
        for index, future in enumerate(as_completed(futures), 1):
            record = future.result(); append_jsonl(output / "judgements.jsonl", record); existing[record["id"]] = record
            print(f"judge {index}/{len(pending)} id={record['id']} status={record['status']}", flush=True)

    ledgers = []
    for row in results:
        case = row.get("case") or {}; qid = str(case.get("id")); gold = gold_by_id[qid]
        computed: dict[str, Any] = {"query_available": row.get("status") == "ok"}
        if row.get("status") == "ok":
            for k in (1, 3, 5, 10): computed.update(retrieval_metrics(row, gold, k))
        judge = existing.get(qid)
        if judge and judge.get("status") == "ok":
            values = list((judge.get("claim_scores") or {}).values())
            computed.update({"claim_recall": sum(values) / len(values) if values else None, "all_critical_claims": all(values) if values else None, "answerability_correct": bool(judge["answerability_correct"]), "unsupported_claim": bool(judge["unsupported_claim"])})
        answer = str(row.get("answer") or "")
        if gold["answerability"] == "answerable":
            items = evidence_items(gold)
            required = gold.get("citation_requirements", [])
            field_hits = {
                "source_file": all(item["source_file"].lower() in answer.lower() for item in items),
                "sha256": all(item["sha256"].lower() in answer.lower() for item in items),
                "pdf_page": all(re.search(rf"(?:page|页|p\.?)[^0-9]{{0,4}}{int(item['pdf_page'])}\b", answer, re.I) is not None for item in items),
                "section": all(str(item["section"]).lower() in answer.lower() for item in items),
                "row_or_cell": all(not item.get("row_or_cell") or str(item["row_or_cell"]).lower() in answer.lower() for item in items),
                "bbox_norm": all(not item.get("bbox_norm") or str(item["bbox_norm"]) in answer for item in items),
            }
            computed["citation_field_hits"] = field_hits
            computed["strict_citation_complete"] = all(field_hits.get(field, False) for field in required)
        ledgers.append({"id": qid, "primary_type": gold["primary_type"], "answerability": gold["answerability"], "result": row, "judge": judge, "computed": computed})
    write_jsonl(output / "qa-ledger.jsonl", ledgers)

    successful = [x for x in ledgers if x["computed"]["query_available"]]
    judged = [x for x in successful if x.get("judge") and x["judge"].get("status") == "ok"]
    def mean(field: str, rows: list[dict[str, Any]]) -> float | None:
        vals = [x["computed"].get(field) for x in rows if x["computed"].get(field) is not None]
        return sum(float(v) for v in vals) / len(vals) if vals else None
    latencies = [float(x["result"].get("retrieval_latency_ms") or 0) for x in successful]
    metrics: dict[str, Any] = {
        "questions": len(ledgers), "query_success": len(successful), "query_availability": len(successful) / len(ledgers),
        "judged": len(judged), "judge_failed": len(successful) - len(judged),
        "claim_recall": mean("claim_recall", judged), "all_critical_claims_rate": mean("all_critical_claims", judged),
        "answerability_accuracy": mean("answerability_correct", judged), "unsupported_claim_rate": mean("unsupported_claim", judged),
        "strict_citation_complete_rate": mean("strict_citation_complete", judged),
        "retrieval_latency_ms": {"mean": sum(latencies)/len(latencies) if latencies else None, "p50": percentile(latencies, .5), "p95": percentile(latencies, .95)},
        "by_type": {},
    }
    for k in (1, 3, 5, 10):
        metrics[f"document_recall_at_{k}"] = mean(f"document_recall_at_{k}", successful)
        metrics[f"evidence_item_recall_at_{k}"] = mean(f"evidence_item_recall_at_{k}", successful)
        metrics[f"complete_evidence_set_at_{k}"] = mean(f"complete_evidence_set_at_{k}", successful)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in ledgers: by_type[item["primary_type"]].append(item)
    for kind, items in by_type.items():
        subset = [x for x in items if x in judged]
        metrics["by_type"][kind] = {"n": len(items), "claim_recall": mean("claim_recall", subset), "answerability_accuracy": mean("answerability_correct", subset), "complete_evidence_set_at_10": mean("complete_evidence_set_at_10", items)}
    write_json(output / "metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("--parse-root", type=Path, required=True); prep.add_argument("--output", type=Path, required=True); prep.add_argument("--exclude-results", type=Path)
    scoring = sub.add_parser("score"); scoring.add_argument("--results", type=Path, nargs="+", required=True); scoring.add_argument("--output", type=Path, required=True); scoring.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.command == "prepare": prepare(args.parse_root.resolve(), args.output.resolve(), args.exclude_results.resolve() if args.exclude_results else None)
    else: score([path.resolve() for path in args.results], args.output.resolve(), args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
