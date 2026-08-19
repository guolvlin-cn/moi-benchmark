#!/usr/bin/env python3
"""Stage-1 MOI Native RAG benchmark for MMDocIR, DocBench and MMDocRAG.

The script keeps the benchmark's paper-native fields alongside the MOI-native
retrieval/answer trace.  Transient TaaS embedding gateway failures are retried
by the Go client with a bounded policy.  DocBench Judge requests use bounded
per-question retries, then optionally fail over to the configured Qianfan chat
provider; a final failure is recorded for that question and the run continues.

Default scope follows the execution plan:

* MMDocIR: all 1,658 evaluation questions;
* DocBench: the S1-G1 smoke (20 PDFs / 50 questions);
* MMDocRAG: deterministic stratified 200-question sample from evaluation_20.

Use ``--full-docbench`` for the 229-PDF / 1,102-question run.  The three
complete parsed corpora are ingested by default, even when a smoke QA split is
selected.  Each corpus gets its own MatrixOne database/table so that one
benchmark cannot retrieve another benchmark's documents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PARSED_ROOT = ROOT / "outputs" / "parsed-documents" / "moi-ready-v1" / "datasets"
DATA_ROOT = ROOT / "datasets" / "downloads" / "document-rag"
RAG_ROOT = ROOT / "prototypes" / "local-matrixflow-rag"
RAG_LAUNCHER = RAG_ROOT / "local_matrixflow_rag.py"
DEFAULT_ENV = ROOT / ".env"
DEFAULT_RUN_ROOT = ROOT / "runs" / "stage1" / "moi-rag-native"
DOCBENCH_EVAL_PROMPT = (
    DATA_ROOT / "docbench" / "code" / "DocBench" / "evaluation_prompt.txt"
)
MMDOCRAG_JUDGE_PROMPT = (
    DATA_ROOT / "mmdocrag" / "code" / "MMDocRAG" / "prompt_bank" / "evaluation_answer.txt"
)


class APIError(RuntimeError):
    """An external embedding/generation/Judge API failed."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dotenv(path: Path, environ: dict[str, str]) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        environ.setdefault(key, value)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL {path}:{line_number}: {exc}") from exc
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def allocate_run(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:-3]
    for sequence in range(100):
        name = stamp if sequence == 0 else f"{stamp}-{sequence:02d}"
        candidate = root / name
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"could not allocate a run directory under {root}")


def emit(run_dir: Path, message: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
    print(line, flush=True)
    append_jsonl(run_dir / "events.jsonl", {"time": now_iso(), "message": message})


def update_state(run_dir: Path, **updates: Any) -> None:
    path = run_dir / "state.json"
    state: dict[str, Any] = {}
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    state.update(updates)
    state["updated_at"] = now_iso()
    write_json(path, state)


def api_error_text(text: str) -> bool:
    lowered = text.lower()
    return "api_error" in lowered or "http " in lowered or "api key" in lowered


def run_child(
    run_dir: Path,
    name: str,
    command: list[str],
    env: dict[str, str],
    cwd: Path = RAG_ROOT,
) -> tuple[int, str, Path]:
    """Run a child while teeing its output to the terminal and a log file."""
    log_path = run_dir / "logs" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    emit(run_dir, f"START {name}: {' '.join(command)}")
    chunks: list[str] = []
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            chunks.append(line)
            log.write(raw_line)
            log.flush()
            # Go emits one line per embedding batch and one per query. Keep
            # those lines visible so a long run never looks stalled.
            print(f"[{name}] {line}", flush=True)
        return_code = process.wait()
    output = "\n".join(chunks)
    if return_code != 0:
        if api_error_text(output):
            raise APIError(f"{name} stopped after an API error; see {log_path}")
        raise RuntimeError(f"{name} failed with exit code {return_code}; see {log_path}")
    emit(run_dir, f"DONE {name}")
    return return_code, output, log_path


def emitted_run_dir(output: str) -> Path:
    for line in output.splitlines():
        if line.startswith("run_dir="):
            return Path(line.split("=", 1)[1].strip()).resolve()
    raise RuntimeError("MOI CLI did not emit run_dir")


def parsed_document_path(dataset: str) -> Path:
    path = PARSED_ROOT / dataset / "moi-documents.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"parsed corpus missing: {path}")
    return path


def build_file_map(dataset: str) -> dict[str, dict[str, Any]]:
    """Map benchmark names and stems to the file IDs in the MOI-ready corpus."""
    mapping: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    with parsed_document_path(dataset).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            metadata = row.get("metadata") or {}
            benchmark_id = str(metadata.get("benchmark_document_id") or "").strip()
            file_name = str(metadata.get("file_name") or "").strip()
            file_id = str(metadata.get("file_id") or "").strip()
            if not benchmark_id or not file_id:
                continue
            if file_id in seen:
                continue
            record = {
                "file_id": file_id,
                "file_name": file_name or f"{benchmark_id}.pdf",
                "benchmark_document_id": benchmark_id,
                "source_path": metadata.get("source_path"),
            }
            seen.add(file_id)
            keys = {
                benchmark_id,
                Path(benchmark_id).stem,
                file_name,
                Path(file_name).stem,
            }
            for key in keys:
                if key:
                    mapping.setdefault(key, record)
    if not mapping:
        raise RuntimeError(f"no file_id metadata found in {parsed_document_path(dataset)}")
    return mapping


def lookup_file(mapping: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    raw = str(name).strip()
    candidates = [raw, Path(raw).name, Path(raw).stem]
    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]
    raise KeyError(f"cannot map benchmark document {name!r} to parsed file_id")


def answer_keywords(answer: Any) -> list[str]:
    if isinstance(answer, list):
        values = answer
    else:
        text = str(answer or "")
        # MMDocIR stores list answers as a Python-list string.
        try:
            parsed = json.loads(text)
            values = parsed if isinstance(parsed, list) else [text]
        except (TypeError, json.JSONDecodeError):
            values = [text]
    output: list[str] = []
    for value in values:
        value = str(value).strip().strip("[]'\"")
        if value and value not in output:
            output.append(value)
    return output


def make_case(
    case_id: str,
    question: str,
    file_record: dict[str, Any],
    evidence: Iterable[str],
    expected_answer: Any,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    evidence_values = [str(item).strip() for item in evidence if str(item).strip()]
    return {
        "id": case_id,
        "question": question,
        "retrieval_keywords": [question],
        "file_ids": [file_record["file_id"]],
        "relevant_documents": [file_record["file_name"]],
        "relevant_evidence": evidence_values,
        "expected_answer_keywords": answer_keywords(expected_answer),
        "expected_answerable": True,
        "metadata": metadata,
    }


def prepare_mmdocir(run_dir: Path) -> tuple[Path, dict[str, Any]]:
    dataset = "mmdocir"
    mapping = build_file_map(dataset)
    annotations = read_jsonl(DATA_ROOT / dataset / "data" / "MMDocIR_annotations.jsonl")
    cases: list[dict[str, Any]] = []
    domains: defaultdict[str, int] = defaultdict(int)
    for doc_index, annotation in enumerate(annotations):
        record = lookup_file(mapping, annotation["doc_name"])
        for question_index, item in enumerate(annotation.get("questions", [])):
            question = str(item.get("Q") or "").strip()
            if not question:
                continue
            pages = [int(page) for page in item.get("page_id", [])]
            layout_mapping = item.get("layout_mapping") or []
            case = make_case(
                f"mmdocir-{doc_index:03d}-{question_index:04d}",
                question,
                record,
                answer_keywords(item.get("A")),
                item.get("A"),
                {
                    "dataset": dataset,
                    "benchmark_document_id": record["benchmark_document_id"],
                    "domain": annotation.get("domain"),
                    "reference_answer": item.get("A"),
                    "gold_page_ids": pages,
                    "gold_layout_mapping": layout_mapping,
                    "question_type": item.get("type"),
                    "page_provenance": "unavailable_in_mineru_markdown_blocks",
                },
            )
            cases.append(case)
            domains[str(annotation.get("domain"))] += 1
    path = run_dir / "datasets" / dataset / "questions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    manifest = {
        "dataset": dataset,
        "questions": len(cases),
        "documents": len({case["metadata"]["benchmark_document_id"] for case in cases}),
        "split": "evaluation_full",
        "domains": dict(domains),
        "protocol": "MMDocIR official question/doc scope; page/layout scorer adapted because MOI parsed blocks lack page boundaries",
        "questions_path": str(path),
    }
    write_json(run_dir / "datasets" / dataset / "manifest.json", manifest)
    return path, manifest


def iter_docbench_rows() -> Iterable[tuple[str, Path, dict[str, Any]]]:
    root = DATA_ROOT / "docbench" / "data"
    for folder in sorted(root.iterdir(), key=lambda item: int(item.name) if item.name.isdigit() else item.name):
        if not folder.is_dir() or not folder.name.isdigit():
            continue
        pdfs = sorted(folder.glob("*.pdf"))
        qa_path = folder / f"{folder.name}_qa.jsonl"
        if not pdfs or not qa_path.is_file():
            continue
        rows = read_jsonl(qa_path)
        for row in rows:
            yield folder.name, pdfs[0], row


def prepare_docbench(
    run_dir: Path, max_pdfs: int, max_questions: int
) -> tuple[Path, dict[str, Any]]:
    dataset = "docbench"
    mapping = build_file_map(dataset)
    grouped: defaultdict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for folder, pdf, row in iter_docbench_rows():
        grouped[folder].append((pdf, row))
    selected_folders = sorted(grouped, key=lambda value: int(value))
    if max_pdfs > 0:
        selected_folders = selected_folders[:max_pdfs]
    cases: list[dict[str, Any]] = []
    # Round-robin keeps the smoke denominator spread across the requested
    # document count instead of consuming all questions from the first few
    # folders (most folders contain several QA pairs).
    positions = {folder: 0 for folder in selected_folders}
    while selected_folders and (max_questions <= 0 or len(cases) < max_questions):
        progressed = False
        for folder in selected_folders:
            position = positions[folder]
            if position >= len(grouped[folder]):
                continue
            progressed = True
            positions[folder] = position + 1
            pdf, row = grouped[folder][position]
            record = lookup_file(mapping, pdf.name)
            case = make_case(
                f"docbench-{folder}-{position:04d}",
                row["question"],
                record,
                [row.get("evidence", "")],
                row.get("answer", ""),
                {
                    "dataset": dataset,
                    "benchmark_document_id": record["benchmark_document_id"],
                    "pdf_path": str(pdf.resolve()),
                    "reference_answer": row.get("answer", ""),
                    "reference_evidence": row.get("evidence", ""),
                    "question_type": row.get("type"),
                    "official_judge": "DocBench evaluation_prompt.txt; Judge provider/model recorded at runtime",
                },
            )
            cases.append(case)
            if max_questions > 0 and len(cases) >= max_questions:
                break
        if not progressed:
            break
    path = run_dir / "datasets" / dataset / "questions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    manifest = {
        "dataset": dataset,
        "questions": len(cases),
        "documents": len(selected_folders),
        "split": "smoke" if max_pdfs == 20 and max_questions == 50 else "evaluation_full",
        "protocol": "DocBench question/evidence schema; MOI native retrieve-then-generate",
        "questions_path": str(path),
    }
    write_json(run_dir / "datasets" / dataset / "manifest.json", manifest)
    return path, manifest


def stratification_key(row: dict[str, Any]) -> str:
    modalities = "+".join(sorted(str(value) for value in row.get("evidence_modality_type", [])))
    return f"{modalities}|{row.get('question_type', '')}"


def stratified_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or limit >= len(rows):
        return rows
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[stratification_key(row)].append(row)
    selected: list[dict[str, Any]] = []
    keys = sorted(groups)
    while len(selected) < limit and keys:
        changed = False
        for key in keys:
            if groups[key]:
                selected.append(groups[key].pop(0))
                changed = True
                if len(selected) >= limit:
                    break
        if not changed:
            break
    return selected


def prepare_mmdocrag(run_dir: Path, limit: int) -> tuple[Path, dict[str, Any]]:
    dataset = "mmdocrag"
    mapping = build_file_map(dataset)
    source = DATA_ROOT / dataset / "data" / "evaluation_20.jsonl"
    rows = read_jsonl(source)
    selected = stratified_rows(rows, limit)
    cases: list[dict[str, Any]] = []
    strata: defaultdict[str, int] = defaultdict(int)
    for row in selected:
        record = lookup_file(mapping, row["doc_name"])
        text_quotes = row.get("text_quotes") or []
        evidence = [str(quote.get("text", "")) for quote in text_quotes]
        metadata = {
            "dataset": dataset,
            "benchmark_document_id": record["benchmark_document_id"],
            "domain": row.get("domain"),
            "question_type": row.get("question_type"),
            "evidence_modality_type": row.get("evidence_modality_type", []),
            "gold_quotes": row.get("gold_quotes", []),
            "gold_text_quotes": [
                {"quote_id": q.get("quote_id"), "page_id": q.get("page_id"), "text": q.get("text", "")}
                for q in text_quotes
            ],
            "gold_image_quotes": [
                {
                    "quote_id": q.get("quote_id"),
                    "page_id": q.get("page_id"),
                    "img_description": q.get("img_description", ""),
                }
                for q in (row.get("img_quotes") or [])
            ],
            "answer_short": row.get("answer_short", ""),
            "answer_interleaved": row.get("answer_interleaved", ""),
            "image_trace_available": False,
            "protocol": "MMDocRAG evaluation_20; text-only MOI native adapter because SearchRAGChunks does not submit image inputs",
        }
        case = make_case(
            f"mmdocrag-{int(row.get('q_id', len(cases))):04d}",
            row["question"],
            record,
            evidence,
            row.get("answer_short", ""),
            metadata,
        )
        cases.append(case)
        strata[stratification_key(row)] += 1
    path = run_dir / "datasets" / dataset / "questions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    manifest = {
        "dataset": dataset,
        "questions": len(cases),
        "documents": len({case["metadata"]["benchmark_document_id"] for case in cases}),
        "split": "evaluation_20_stratified_200",
        "strata": dict(strata),
        "protocol": "MMDocRAG official 20-quote fields; MOI native text-only adapted answer path",
        "questions_path": str(path),
    }
    write_json(run_dir / "datasets" / dataset / "manifest.json", manifest)
    return path, manifest


def load_config_template() -> dict[str, Any]:
    config_path = RAG_ROOT / "config.local.json"
    if not config_path.is_file():
        config_path = RAG_ROOT / "config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return config


def make_config(
    run_dir: Path,
    dataset: str,
    generation: bool,
    embedding_batch_size: int = 256,
    environment: Optional[dict[str, str]] = None,
) -> Path:
    config = load_config_template()
    config["matrixone"]["database"] = f"moi_stage1_{dataset}"
    config["matrixone"]["vector_table"] = "embedding_results"
    config.setdefault("workspace_id", f"moi-stage1-{dataset}")
    config["embedding_batch_size"] = embedding_batch_size
    config.setdefault("embedding", {}).setdefault("retry_max_attempts", 4)
    config["embedding"].setdefault("retry_backoff_seconds", 5)
    config.setdefault("generation", {})["enabled"] = generation
    config["generation"].setdefault("provider", "taas")
    config["generation"].setdefault("retry_max_attempts", 3)
    config["generation"].setdefault("retry_backoff_seconds", 5)
    fallback_defaults = {
        "enabled": True,
        "provider": "qianfan",
        "base_url": "https://qianfan.baidubce.com/v2",
        "model": "deepseek-v4-flash",
        "api_key_env": "QIANFAN_API_KEY",
        "timeout_seconds": 180,
        "retry_max_attempts": 2,
        "retry_backoff_seconds": 5,
    }
    fallback = config["generation"].get("fallback")
    if not isinstance(fallback, dict):
        fallback = fallback_defaults
        config["generation"]["fallback"] = fallback
    else:
        for key, value in fallback_defaults.items():
            fallback.setdefault(key, value)
    if environment is not None:
        fallback["base_url"] = environment.get("QIANFAN_BASE_URL", fallback["base_url"])
        fallback["model"] = environment.get(
            "QIANFAN_LLM_MODEL",
            environment.get("QIANFAN_CHAT_MODEL", fallback["model"]),
        )
    config_dir = run_dir / "configs"
    path = config_dir / f"{dataset}.json"
    write_json(path, config)
    return path


def percentile(values: list[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def normalized(text: Any) -> str:
    return "".join(str(text or "").lower().split())


def ndcg_at_k(result: dict[str, Any], k: int) -> float:
    expected = {str(item).lower() for item in result.get("case", {}).get("relevant_documents", [])}
    if not expected:
        return 1.0
    chunks = result.get("chunks") or []
    hits = [1 if str(chunk.get("file_name", "")).lower() in expected else 0 for chunk in chunks[:k]]
    dcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(hits))
    ideal = sum(1 / math.log2(index + 2) for index in range(min(k, len(expected))))
    return dcg / ideal if ideal else 0.0


def retrieve_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in results if row.get("status") == "ok"]
    latencies = [float(row.get("retrieval_latency_ms", 0)) for row in results]
    metrics: dict[str, Any] = {
        "attempts": len(results),
        "successful_attempts": len(successful),
        "initial_availability": len(successful) / len(results) if results else None,
        "error_count": len(results) - len(successful),
        "retrieval_latency_ms": {
            "mean": sum(latencies) / len(latencies) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
    }
    for k in (1, 3, 5, 10):
        key = str(k)
        values = [float(row.get("metrics", {}).get("source_recall_at_k", {}).get(key, 0)) for row in successful]
        metrics[f"source_recall_at_{k}"] = sum(values) / len(values) if values else None
        ndcgs = [ndcg_at_k(row, k) for row in successful]
        metrics[f"nDCG_at_{k}"] = sum(ndcgs) / len(ndcgs) if ndcgs else None
    for name in ("source_recall", "evidence_recall", "reciprocal_rank", "answer_keyword_recall"):
        values: list[float] = []
        for row in successful:
            value = row.get("metrics", {}).get(name)
            if value is not None:
                values.append(float(value))
        metrics[name] = sum(values) / len(values) if values else None
    return metrics


def rouge_l(reference: str, prediction: str) -> float:
    ref = re.findall(r"\w+|[^\w\s]", reference.lower())
    pred = re.findall(r"\w+|[^\w\s]", prediction.lower())
    if not ref or not pred:
        return 0.0
    previous = [0] * (len(pred) + 1)
    for token in ref:
        current = [0]
        for index, other in enumerate(pred, 1):
            current.append(previous[index - 1] + 1 if token == other else max(previous[index], current[-1]))
        previous = current
    lcs = previous[-1]
    precision = lcs / len(pred)
    recall = lcs / len(ref)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def bleu_1(reference: str, prediction: str) -> float:
    ref = re.findall(r"\w+", reference.lower())
    pred = re.findall(r"\w+", prediction.lower())
    if not pred:
        return 0.0
    ref_counts: defaultdict[str, int] = defaultdict(int)
    for token in ref:
        ref_counts[token] += 1
    pred_counts: defaultdict[str, int] = defaultdict(int)
    for token in pred:
        pred_counts[token] += 1
    overlap = sum(min(count, ref_counts[token]) for token, count in pred_counts.items())
    precision = overlap / len(pred)
    brevity = min(1.0, math.exp(1 - len(ref) / len(pred))) if ref else 0.0
    return precision * brevity


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0).replace("'", '"'))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def openai_chat(
    env: dict[str, str],
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout: int = 180,
    api_key_env: str = "TAAS_API_KEY",
    extra_headers: Optional[dict[str, str]] = None,
) -> str:
    """Small dependency-free OpenAI-compatible chat client for Judges."""
    import urllib.error
    import urllib.request

    key = env.get(api_key_env, "").strip()
    if not key:
        raise APIError(f"API_ERROR: {api_key_env} is not set")
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        # Keep the benchmark's TaaS Judge calls on the same direct route as
        # the Go embedding client. The host environment has a local proxy,
        # but the TaaS gateway must not see that shared proxy egress. Other
        # OpenAI-compatible providers retain urllib's normal proxy behavior.
        target_host = (urlparse(base_url).hostname or "").lower()
        if target_host == "token.moi.matrixorigin.cn":
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            response_context = opener.open(request, timeout=timeout)
        else:
            response_context = urllib.request.urlopen(request, timeout=timeout)
        with response_context as response:
            raw = response.read(16 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        body = exc.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
        raise APIError(f"API_ERROR: Judge HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise APIError(f"API_ERROR: Judge request failed: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise APIError(f"API_ERROR: invalid Judge response: {raw[:500]!r}") from exc


def judge_error_retryable(error: BaseException) -> bool:
    """Return whether a Judge failure is safe to retry for this question."""
    text = str(error).lower()
    transient_statuses = ("408", "425", "429", "500", "502", "503", "504")
    if "judge http" in text:
        return any(f"http {status}" in text for status in transient_statuses)
    return any(
        marker in text
        for marker in (
            "timed out",
            "timeout",
            "urlopen error",
            "connection reset",
            "connection refused",
            "temporarily unavailable",
            "request failed",
        )
    )


def numeric_setting(value: Any, default: float, *, integer: bool = False) -> Any:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < 0:
        parsed = default
    return int(parsed) if integer else parsed


def qianfan_judge_config(
    env: dict[str, str], config: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Resolve the local Qianfan V2 chat settings without exposing the key."""
    generation = config.get("generation") or {}
    fallback = generation.get("fallback") or {}
    if fallback.get("enabled", True) is False:
        return None
    key_env = str(fallback.get("api_key_env") or "QIANFAN_API_KEY")
    if not str(env.get(key_env, "")).strip():
        return None
    base_url = str(
        env.get("QIANFAN_BASE_URL")
        or os.environ.get("QIANFAN_BASE_URL")
        or fallback.get("base_url")
        or "https://qianfan.baidubce.com/v2"
    )
    model = str(
        env.get("QIANFAN_LLM_MODEL")
        or os.environ.get("QIANFAN_LLM_MODEL")
        or env.get("QIANFAN_CHAT_MODEL")
        or os.environ.get("QIANFAN_CHAT_MODEL")
        or fallback.get("model")
        or "deepseek-v4-flash"
    )
    headers: dict[str, str] = {}
    appid = str(env.get("QIANFAN_APPID", "")).strip()
    if appid:
        headers["appid"] = appid
    return {
        "provider": "qianfan",
        "base_url": base_url,
        "model": model,
        "api_key_env": key_env,
        "timeout": int(numeric_setting(fallback.get("timeout_seconds"), 180, integer=True)),
        "retry_max_attempts": int(
            numeric_setting(fallback.get("retry_max_attempts"), 2, integer=True)
        ),
        "retry_backoff_seconds": float(
            numeric_setting(fallback.get("retry_backoff_seconds"), 5)
        ),
        "headers": headers,
    }


def judge_call_with_retry(
    run_dir: Path,
    index: int,
    total: int,
    case_id: str,
    env: dict[str, str],
    provider: dict[str, Any],
    messages: list[dict[str, Any]],
) -> tuple[Optional[str], int, Optional[APIError]]:
    attempts = max(1, int(provider.get("retry_max_attempts", 1)))
    backoff = max(0.0, float(provider.get("retry_backoff_seconds", 0)))
    last_error: Optional[APIError] = None
    for attempt in range(1, attempts + 1):
        try:
            raw = openai_chat(
                env,
                str(provider["base_url"]),
                str(provider["model"]),
                messages,
                timeout=int(provider.get("timeout", 180)),
                api_key_env=str(provider.get("api_key_env", "TAAS_API_KEY")),
                extra_headers=provider.get("headers") or None,
            )
            return raw, attempt, None
        except APIError as exc:
            last_error = exc
            retryable = judge_error_retryable(exc)
            if attempt >= attempts or not retryable:
                break
            delay = backoff * (2 ** (attempt - 1))
            emit(
                run_dir,
                f"DOCBENCH judge retry {index}/{total} id={case_id} "
                f"provider={provider.get('provider')} attempt={attempt + 1}/{attempts} "
                f"wait={delay:g}s error={str(exc)[:240]}",
            )
            if delay:
                time.sleep(delay)
    return None, attempts if last_error is not None else 0, last_error


def run_docbench_judge(
    run_dir: Path, results: list[dict[str, Any]], env: dict[str, str], config: dict[str, Any]
) -> dict[str, Any]:
    output = run_dir / "datasets" / "docbench" / "judgements.jsonl"
    existing = {row.get("id"): row for row in read_jsonl(output)} if output.is_file() else {}
    prompt = DOCBENCH_EVAL_PROMPT.read_text(encoding="utf-8")
    generation = config.get("generation") or {}
    primary = {
        "provider": str(generation.get("provider") or "taas"),
        "base_url": str(generation.get("base_url") or env.get("TAAS_BASE_URL") or "https://token.moi.matrixorigin.cn/v1"),
        "model": str(os.environ.get("TAAS_JUDGE_MODEL") or generation.get("model") or "qwen3.6-flash"),
        "api_key_env": str(generation.get("api_key_env") or "TAAS_API_KEY"),
        "timeout": int(numeric_setting(generation.get("timeout_seconds"), 180, integer=True)),
        "retry_max_attempts": int(numeric_setting(generation.get("retry_max_attempts"), 3, integer=True)),
        "retry_backoff_seconds": float(numeric_setting(generation.get("retry_backoff_seconds"), 5)),
        "headers": {},
    }
    fallback = qianfan_judge_config(env, config)
    scored: list[dict[str, Any]] = []
    candidates = [row for row in results if row.get("status") == "ok"]
    for index, result in enumerate(candidates, 1):
        case = result.get("case") or {}
        if case.get("id") in existing:
            scored.append(existing[case["id"]])
            continue
        metadata = case.get("metadata") or {}
        rendered = prompt.replace("{{question}}", str(case.get("question", "")))
        rendered = rendered.replace("{{sys_ans}}", str(result.get("answer", "")))
        rendered = rendered.replace("{{ref_ans}}", str(metadata.get("reference_answer", "")))
        rendered = rendered.replace("{{ref_text}}", str(metadata.get("reference_evidence", "")))
        messages = [
            {"role": "system", "content": "You are a helpful evaluator."},
            {"role": "user", "content": rendered},
        ]
        raw, primary_attempts, primary_error = judge_call_with_retry(
            run_dir, index, len(candidates), str(case.get("id")), env, primary, messages
        )
        provider_used = primary
        fallback_attempts = 0
        fallback_error: Optional[APIError] = None
        if raw is None and fallback is not None:
            emit(
                run_dir,
                f"DOCBENCH judge failover {index}/{len(candidates)} id={case.get('id')} "
                f"from={primary.get('provider')} to={fallback.get('provider')}",
            )
            raw, fallback_attempts, fallback_error = judge_call_with_retry(
                run_dir, index, len(candidates), str(case.get("id")), env, fallback, messages
            )
            provider_used = fallback
        total_attempts = primary_attempts + fallback_attempts
        if raw is None:
            error = fallback_error or primary_error or APIError("unknown Judge failure")
            row = {
                "id": case.get("id"),
                "status": "fail",
                "judge_model": provider_used.get("model"),
                "provider": provider_used.get("provider"),
                "score": None,
                "attempts": total_attempts,
                "error_type": "retry_exhausted" if judge_error_retryable(error) else "non_retryable_api_error",
                "error": str(error),
                "primary_error": str(primary_error) if primary_error else None,
                "fallback_error": str(fallback_error) if fallback_error else None,
                "question": case.get("question"),
            }
            append_jsonl(output, row)
            scored.append(row)
            emit(
                run_dir,
                f"DOCBENCH judge {index}/{len(candidates)} id={case.get('id')} "
                f"status=fail attempts={total_attempts} error={str(error)[:240]}",
            )
            continue
        match = re.search(r"(?:correctness\s*[:：]\s*)?([01])\b", raw, flags=re.I)
        score = int(match.group(1)) if match else None
        row = {
            "id": case.get("id"),
            "status": "ok",
            "judge_model": provider_used.get("model"),
            "provider": provider_used.get("provider"),
            "score": score,
            "attempts": total_attempts,
            "raw": raw,
            "question": case.get("question"),
        }
        append_jsonl(output, row)
        scored.append(row)
        emit(run_dir, f"DOCBENCH judge {index}/{len(candidates)} id={case.get('id')} score={score}")
    values = [row["score"] for row in scored if isinstance(row.get("score"), int)]
    providers: defaultdict[str, int] = defaultdict(int)
    for row in scored:
        providers[str(row.get("provider") or "unknown")] += 1
    return {
        "judge_model": primary["model"],
        "scored": len(scored),
        "failed": sum(1 for row in scored if row.get("status") == "fail"),
        "valid_scores": len(values),
        "correctness": sum(values) / len(values) if values else None,
        "providers": dict(providers),
        "raw_path": str(output),
    }


def run_mmdocrag_judge(
    run_dir: Path, results: list[dict[str, Any]], env: dict[str, str], config: dict[str, Any]
) -> dict[str, Any]:
    output = run_dir / "datasets" / "mmdocrag" / "judgements.jsonl"
    existing = {row.get("id"): row for row in read_jsonl(output)} if output.is_file() else {}
    system_prompt = MMDOCRAG_JUDGE_PROMPT.read_text(encoding="utf-8")
    base_url = str(config.get("generation", {}).get("base_url") or env.get("TAAS_BASE_URL") or "https://token.moi.matrixorigin.cn/v1")
    model = str(os.environ.get("TAAS_JUDGE_MODEL") or config.get("generation", {}).get("model") or "qwen3.6-flash")
    scored: list[dict[str, Any]] = []
    candidates = [row for row in results if row.get("status") == "ok"]
    for index, result in enumerate(candidates, 1):
        case = result.get("case") or {}
        case_id = case.get("id")
        if case_id in existing:
            scored.append(existing[case_id])
            continue
        metadata = case.get("metadata") or {}
        user = (
            f"The question is: {case.get('question', '')}\n"
            f"The short answer is: {metadata.get('answer_short', '')}\n"
            f"The perfect answer is: {metadata.get('answer_interleaved', '')}\n"
            f"The interleaved answer is: {result.get('answer', '')}\n"
            "The MOI run is text-only; no image input was supplied to the Judge."
        )
        raw = openai_chat(env, base_url, model, [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}])
        parsed = extract_json_object(raw) or {}
        normalized_scores: dict[str, Any] = {}
        for key in ("Fluency", "Citation Quality", "Text-Image Coherence", "Reasoning Logic", "Factuality"):
            value = parsed.get(key)
            if value is None:
                for candidate_key, candidate_value in parsed.items():
                    if key.lower().replace(" ", "") == str(candidate_key).lower().replace(" ", ""):
                        value = candidate_value
                        break
            try:
                normalized_scores[key] = int(value)
            except (TypeError, ValueError):
                normalized_scores[key] = None
        values = [v for v in normalized_scores.values() if isinstance(v, int)]
        row = {
            "id": case_id,
            "judge_model": model,
            "scores": normalized_scores,
            "average": sum(values) / len(values) if values else None,
            "raw": raw,
            "text_only_adapter": True,
        }
        append_jsonl(output, row)
        scored.append(row)
        emit(run_dir, f"MMDOCRAG judge {index}/{len(candidates)} id={case_id} avg={row['average']}")
    averages = [float(row["average"]) for row in scored if row.get("average") is not None]
    dimensions: dict[str, Optional[float]] = {}
    for key in ("Fluency", "Citation Quality", "Text-Image Coherence", "Reasoning Logic", "Factuality"):
        values = [row.get("scores", {}).get(key) for row in scored]
        values = [float(value) for value in values if isinstance(value, int)]
        dimensions[key] = sum(values) / len(values) if values else None
    return {
        "judge_model": model,
        "scored": len(scored),
        "average": sum(averages) / len(averages) if averages else None,
        "dimensions": dimensions,
        "text_only_adapter": True,
        "raw_path": str(output),
    }


def mmdocrag_answer_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in results if row.get("status") == "ok"]
    bleu_values: list[float] = []
    rouge_values: list[float] = []
    text_precision: list[float] = []
    text_recall: list[float] = []
    text_f1: list[float] = []
    for row in rows:
        metadata = (row.get("case") or {}).get("metadata") or {}
        prediction = str(row.get("answer") or "")
        reference = str(metadata.get("answer_interleaved") or "")
        bleu_values.append(bleu_1(reference, prediction))
        rouge_values.append(rouge_l(reference, prediction))
        gold = metadata.get("gold_text_quotes") or []
        expected = [normalized(item.get("text")) for item in gold if item.get("text")]
        retrieved = [normalized(chunk.get("content")) for chunk in row.get("chunks") or []]
        hit = sum(1 for quote in expected if any(quote and quote in chunk for chunk in retrieved))
        predicted = sum(1 for chunk in retrieved if any(quote and quote in chunk for quote in expected))
        precision = predicted / len(retrieved) if retrieved else 0.0
        recall = hit / len(expected) if expected else None
        f1 = 2 * precision * recall / (precision + recall) if recall is not None and precision + recall else 0.0
        text_precision.append(precision)
        if recall is not None:
            text_recall.append(recall)
        text_f1.append(f1)
    return {
        "quote_selection": {
            "text_precision_adapted": sum(text_precision) / len(text_precision) if text_precision else None,
            "text_recall_adapted": sum(text_recall) / len(text_recall) if text_recall else None,
            "text_f1_adapted": sum(text_f1) / len(text_f1) if text_f1 else None,
            "image_precision": None,
            "image_recall": None,
            "image_f1": None,
            "overall": None,
            "na_reason": "MOI SearchRAGChunks returned text chunks; image quote locator/input is unavailable",
        },
        "bleu_1_adapted": sum(bleu_values) / len(bleu_values) if bleu_values else None,
        "rouge_l": sum(rouge_values) / len(rouge_values) if rouge_values else None,
    }


def read_results(run_dir: Path, dataset: str) -> list[dict[str, Any]]:
    path = run_dir / "datasets" / dataset / "query-run" / "results.jsonl"
    if not path.is_file():
        # query-run is a root; the CLI creates a timestamped child.
        candidates = sorted((run_dir / "datasets" / dataset / "query-run").glob("*/results.jsonl"))
        if not candidates:
            raise FileNotFoundError(f"MOI query results not found for {dataset}")
        path = candidates[-1]
    return read_jsonl(path)


def query_run_dir(run_dir: Path, dataset: str) -> Path:
    root = run_dir / "datasets" / dataset / "query-run"
    candidates = sorted(root.glob("*/results.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"MOI query results not found for {dataset}")
    return candidates[-1].parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--datasets", nargs="+", choices=["mmdocir", "docbench", "mmdocrag"], default=["mmdocir", "docbench", "mmdocrag"])
    parser.add_argument("--docbench-pdfs", type=int, default=20)
    parser.add_argument("--docbench-qa", type=int, default=50)
    parser.add_argument("--full-docbench", action="store_true")
    parser.add_argument("--mmdocrag-qa", type=int, default=200)
    parser.add_argument("--max-hits", type=int, default=10)
    parser.add_argument("--embedding-batch-size", type=int, default=256)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="ingest all selected parsed corpora and stop before QA retrieval/judging",
    )
    parser.add_argument("--skip-judge", action="store_true")
    args = parser.parse_args()

    if args.ingest_only and args.skip_ingest:
        parser.error("--ingest-only cannot be combined with --skip-ingest")

    run_dir = allocate_run(args.run_root.resolve())
    environment = os.environ.copy()
    load_dotenv(args.env_file.resolve(), environment)
    load_dotenv(RAG_ROOT / ".env", environment)
    # Provider-specific local secrets live outside the checked-in .env files.
    # Load them into the child-process environment so Qianfan can be used for
    # generation/Judge failover without ever printing the secret.
    load_dotenv(RAG_ROOT / ".local-services" / "providers" / "qianfan.env", environment)
    # Keep the project-level provider secrets available as a fallback when the
    # RAG prototype has only its TaaS key in its local .env.  setdefault keeps
    # the explicitly selected run environment authoritative.
    load_dotenv(ROOT.parent / ".env", environment)
    manifest: dict[str, Any] = {
        "schema_version": "moi-stage1-rag-native-v1",
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "started_at": now_iso(),
        "status": "running",
        "env_file": str(args.env_file.resolve()),
        "datasets": {},
        "api_error_stop": True,
    }
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "state.json", {"status": "running", "stage": "prepare", "started_at": manifest["started_at"]})
    emit(run_dir, f"RUN {run_dir}")

    try:
        if args.full_docbench:
            args.docbench_pdfs = 0
            args.docbench_qa = 0
        preparation = {}
        if "mmdocir" in args.datasets:
            emit(run_dir, "PREPARE mmdocir questions")
            preparation["mmdocir"] = prepare_mmdocir(run_dir)
        if "docbench" in args.datasets:
            emit(run_dir, "PREPARE docbench questions")
            preparation["docbench"] = prepare_docbench(run_dir, args.docbench_pdfs, args.docbench_qa)
        if "mmdocrag" in args.datasets:
            emit(run_dir, "PREPARE mmdocrag questions")
            preparation["mmdocrag"] = prepare_mmdocrag(run_dir, args.mmdocrag_qa)
        for dataset, (_, dataset_manifest) in preparation.items():
            manifest["datasets"][dataset] = {"preparation": dataset_manifest}
        write_json(run_dir / "manifest.json", manifest)
        update_state(run_dir, status="running", stage="ingest", datasets=manifest["datasets"])

        for dataset in args.datasets:
            parsed = parsed_document_path(dataset)
            config_path = make_config(
                run_dir,
                dataset,
                dataset in {"docbench", "mmdocrag"},
                args.embedding_batch_size,
                environment,
            )
            dataset_manifest = manifest["datasets"].setdefault(dataset, {})
            dataset_manifest["config"] = str(config_path)
            dataset_manifest["parsed_documents"] = str(parsed)
            if not args.skip_ingest:
                emit(run_dir, f"INGEST {dataset}: full parsed corpus -> MatrixOne")
                _, ingest_output, _ = run_child(
                    run_dir,
                    f"ingest-{dataset}",
                    [sys.executable, str(RAG_LAUNCHER), "ingest", "--config", str(config_path), "--documents", str(parsed), "--run", str(run_dir / "datasets" / dataset / "index-run"), "--force"],
                    environment,
                )
                ingest_run = emitted_run_dir(ingest_output)
                dataset_manifest["ingest_run"] = str(ingest_run)
                dataset_manifest["ingest_status"] = "succeeded"
                write_json(run_dir / "manifest.json", manifest)

            if args.ingest_only:
                continue

            question_path = preparation[dataset][0]
            update_state(run_dir, status="running", stage=f"query:{dataset}", datasets=manifest["datasets"])
            emit(run_dir, f"QUERY {dataset}: {preparation[dataset][1]['questions']} questions x {args.repeats} repeat(s)")
            _, query_output, _ = run_child(
                run_dir,
                f"query-{dataset}",
                [sys.executable, str(RAG_LAUNCHER), "run", "--config", str(config_path), "--dataset", str(question_path), "--run", str(run_dir / "datasets" / dataset / "query-run"), "--max-hits", str(args.max_hits), "--repeats", str(args.repeats)],
                environment,
            )
            query_child = emitted_run_dir(query_output)
            dataset_manifest["query_run"] = str(query_child)
            results = read_jsonl(query_child / "results.jsonl")
            dataset_manifest["moi_retrieval_metrics"] = retrieve_metrics(results)
            if dataset == "docbench" and not args.skip_judge:
                dataset_manifest["official_metrics"] = run_docbench_judge(run_dir, results, environment, json.loads(config_path.read_text(encoding="utf-8")))
            elif dataset == "mmdocrag":
                dataset_manifest["official_metrics_adapted"] = mmdocrag_answer_metrics(results)
                if not args.skip_judge:
                    dataset_manifest["llm_judge"] = run_mmdocrag_judge(run_dir, results, environment, json.loads(config_path.read_text(encoding="utf-8")))
            elif dataset == "mmdocir":
                dataset_manifest["official_metrics"] = {
                    "page_recall_at_1": None,
                    "page_recall_at_3": None,
                    "page_recall_at_5": None,
                    "layout_recall_at_1": None,
                    "layout_recall_at_5": None,
                    "layout_recall_at_10": None,
                    "na_reason": "TRACE_UNAVAILABLE: MinerU Markdown blocks do not expose the original PDF page boundaries/layout IDs; MOI native block/evidence metrics are recorded above",
                }
            write_json(run_dir / "manifest.json", manifest)
            emit(run_dir, f"METRICS {dataset}: {json.dumps(dataset_manifest.get('moi_retrieval_metrics'), ensure_ascii=False)}")

        if args.ingest_only:
            manifest["status"] = "succeeded"
            manifest["finished_at"] = now_iso()
            update_state(run_dir, status="succeeded", stage="ingest_complete", datasets=manifest["datasets"])
            write_json(run_dir / "manifest.json", manifest)
            emit(run_dir, "INGESTION COMPLETE")
            return 0

        manifest["status"] = "succeeded"
        manifest["finished_at"] = now_iso()
        update_state(run_dir, status="succeeded", stage="complete", datasets=manifest["datasets"])
        write_json(run_dir / "manifest.json", manifest)
        emit(run_dir, "RUN COMPLETE")
        return 0
    except KeyboardInterrupt as exc:
        manifest["status"] = "interrupted"
        manifest["finished_at"] = now_iso()
        update_state(run_dir, status="interrupted", stage="interrupted", error="user interrupt", datasets=manifest["datasets"])
        write_json(run_dir / "manifest.json", manifest)
        emit(run_dir, "INTERRUPTED by user; no formal metrics were recorded")
        print(f"\n评估已中断，断点目录：{run_dir}", file=sys.stderr, flush=True)
        return 130
    except APIError as exc:
        manifest["status"] = "paused_api_error"
        manifest["api_error"] = str(exc)
        manifest["finished_at"] = now_iso()
        update_state(run_dir, status="paused_api_error", stage="api_error", error=str(exc), datasets=manifest["datasets"])
        write_json(run_dir / "manifest.json", manifest)
        emit(run_dir, f"PAUSED API_ERROR: {exc}")
        print(f"\n评估因 API 错误暂停：{exc}\n已保存断点：{run_dir}", file=sys.stderr, flush=True)
        return 2
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["finished_at"] = now_iso()
        update_state(run_dir, status="failed", stage="failed", error=str(exc), datasets=manifest["datasets"])
        write_json(run_dir / "manifest.json", manifest)
        emit(run_dir, f"FAILED: {exc}")
        print(f"评估失败：{exc}\n运行目录：{run_dir}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
