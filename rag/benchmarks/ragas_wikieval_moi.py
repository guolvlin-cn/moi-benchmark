#!/usr/bin/env python3
"""Offline WikiEval -> local-matrixflow-rag adapter and deterministic scorer.

Ragas is intentionally optional here: the primary score is based on the frozen
source/evidence fields and the runner's actual ranked chunks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets/downloads/public/wiki-eval/train-00000-of-00001-097798a99d58791d.parquet"
PROTOCOL = "wikieval-to-moi-v1"
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was",
    "what", "when", "where", "which", "who", "why", "will", "with", "would",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_text(value: Any) -> str:
    return " ".join(re.findall(r"\w+", str(value or "").casefold(), flags=re.UNICODE))


def clean_question(value: Any) -> str:
    return re.sub(r"^\s*question\s*:\s*", "", str(value or ""), flags=re.I).strip()


def clean_answer(value: Any) -> str:
    return re.sub(r"^\s*answer\s*:\s*", "", str(value or ""), flags=re.I).strip()


def first_non_empty_context(row: dict[str, Any], field: str = "context_v1") -> str:
    value = row.get(field) or []
    if isinstance(value, str):
        value = [value]
    for item in value:
        if item is not None and str(item).strip():
            return str(item).strip()
    return ""


def extract_answer_keywords(reference: str) -> list[str]:
    """Return human-readable lexical anchors, never the whole reference sentence."""
    words = re.findall(r"[\w]+(?:[-'][\w]+)?", clean_answer(reference), flags=re.UNICODE)
    result: list[str] = []
    seen: set[str] = set()
    for word in words:
        key = word.casefold()
        if len(key) < 2 and not key.isdigit():
            continue
        if key in STOPWORDS or key in seen:
            continue
        seen.add(key)
        result.append(word)
    return result


def slugify_source(source: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", source.casefold()).strip("-")
    return slug[:70] or "source"


def stable_document_name(source: str, used: set[str]) -> str:
    base = f"{slugify_source(source)}-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:10]}.md"
    if base not in used:
        used.add(base)
        return base
    index = 2
    while f"{base[:-3]}-{index}.md" in used:
        index += 1
    name = f"{base[:-3]}-{index}.md"
    used.add(name)
    return name


def _read_parquet(path: Path) -> tuple[list[dict[str, Any]], int]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("prepare requires pyarrow (the repository parquet reader)") from exc
    table = pq.read_table(path)
    return table.slice(0, 50).to_pylist(), table.num_rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(dataset: Path, run_dir: Path) -> dict[str, Any]:
    rows, total_rows = _read_parquet(dataset)
    if len(rows) < 50:
        raise ValueError(f"WikiEval dataset has {len(rows)} rows; expected at least 50")
    artifact_dir = run_dir / "artifacts"
    document_dir = artifact_dir / "documents"
    document_dir.mkdir(parents=True, exist_ok=True)
    questions: list[dict[str, Any]] = []
    source_to_document: dict[str, str] = {}
    used_names: set[str] = set()
    for index, row in enumerate(rows[:50]):
        source = str(row.get("source") or f"source-{index + 1}").strip()
        if source not in source_to_document:
            filename = stable_document_name(source, used_names)
            source_to_document[source] = filename
            context = next((first_non_empty_context(candidate) for candidate in rows[:50]
                            if str(candidate.get("source") or "").strip() == source
                            and first_non_empty_context(candidate)), "")
            document_dir.joinpath(filename).write_text(f"# {source}\n\n{context}\n", encoding="utf-8")
        reference = clean_answer(row.get("grounded_answer", ""))
        question = clean_question(row.get("question", ""))
        questions.append({
            "id": f"wikieval-{index + 1:03d}",
            "question": question,
            "retrieval_keywords": [question],
            "relevant_documents": [source_to_document[source]],
            "relevant_evidence": [reference],
            "expected_answer_keywords": extract_answer_keywords(str(row.get("grounded_answer", ""))),
            "metadata": {
                "source": source,
                "reference": reference,
                "context_v1": row.get("context_v1") or [],
                "context_v2": row.get("context_v2") or [],
                "dataset_sha256": sha256_file(dataset),
                "protocol": PROTOCOL,
                "wiki_eval_field_mapping": {"reference": "grounded_answer"},
            },
        })
    questions_path = artifact_dir / "questions.jsonl"
    questions_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in questions), encoding="utf-8")
    document_hashes = {p.name: sha256_file(p) for p in sorted(document_dir.glob("*.md"))}
    question_hash = sha256_file(questions_path)
    labels_path = dataset.parent / "ragas-wiki-labelling.json"
    manifest = {
        "protocol": PROTOCOL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "url": "https://huggingface.co/datasets/vibrantlabsai/wiki-eval",
            "repo": "vibrantlabsai/wiki-eval",
            "revision_or_local_filename": dataset.name,
            "dataset_sha256": sha256_file(dataset),
            "labels_sha256": sha256_file(labels_path) if labels_path.is_file() else None,
        },
        "dataset": {"rows_in_file": total_rows, "rows_selected": len(questions), "unique_sources": len(source_to_document)},
        "artifacts": {"questions_sha256": question_hash, "documents_sha256": document_hashes},
        "license_notes": "Preserve the upstream WikiEval/Hugging Face dataset license and attribution; no network download is performed by this script.",
        "field_mapping": {"QuestionCase.relevant_evidence": "grounded_answer without Answer: prefix", "reference": "grounded_answer"},
    }
    _write_json(artifact_dir / "dataset_manifest.json", manifest)
    return manifest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * percentile / 100
    lower, upper = math.floor(index), math.ceil(index)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def _chunks(result: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = result.get("chunks") or []
    return sorted(chunks, key=lambda item: item.get("rank", 10**9))


def _source_match(chunk: dict[str, Any], relevant: set[str]) -> bool:
    return bool({str(chunk.get(k, "")) for k in ("file_id", "file_name", "source_uri")} & relevant)


def calculate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(results)
    successful = [r for r in results if str(r.get("status", "")).casefold() in {"ok", "success", "completed"}]
    latencies = [float(r["retrieval_latency_ms"]) for r in results if r.get("retrieval_latency_ms") is not None]
    aggregate: dict[str, Any] = {
        "attempts": count,
        "success_rate": len(successful) / count if count else None,
        "source_recall_at_1": None, "source_recall_at_3": None, "source_recall_at_5": None, "source_recall_at_10": None,
        "mrr": 0.0 if count else None, "evidence_substring_recall": 0.0 if count else None,
        "answer_non_empty_rate": 0.0 if count else None, "reference_keyword_recall": 0.0 if count else None,
        "reference_substring_rate": 0.0 if count else None, "reference_normalized_overlap": 0.0 if count else None,
        "latency_ms_p50": _percentile(latencies, 50), "latency_ms_p95": _percentile(latencies, 95),
    }
    source_hits = {k: 0 for k in (1, 3, 5, 10)}
    mrr = evidence = non_empty = keyword_recall = strict = overlap = 0.0
    for result in results:
        case = result.get("case") or {}
        relevant = {str(v) for v in case.get("relevant_documents", [])}
        chunks = _chunks(result)
        first_rank = next((i + 1 for i, chunk in enumerate(chunks) if _source_match(chunk, relevant)), None)
        for k in source_hits:
            source_hits[k] += int(first_rank is not None and first_rank <= k)
        mrr += 1 / first_rank if first_rank else 0
        evidence_values = [str(v) for v in case.get("relevant_evidence", []) if str(v).strip()]
        joined_content = "\n".join(str(c.get("content", "")) for c in chunks)
        evidence += int(bool(evidence_values) and any(normalized_text(v) in normalized_text(joined_content) for v in evidence_values))
        answer = str(result.get("answer") or "")
        non_empty += int(bool(answer.strip()))
        keywords = [str(v) for v in case.get("expected_answer_keywords", []) if str(v).strip()]
        answer_norm = normalized_text(answer)
        keyword_recall += (sum(int(normalized_text(k) in answer_norm.split()) for k in keywords) / len(keywords)) if keywords else 0
        reference = str((case.get("metadata") or {}).get("reference") or (case.get("relevant_evidence") or [""])[0])
        reference_norm = normalized_text(reference)
        strict += int(bool(reference_norm) and reference_norm in answer_norm)
        ref_tokens, answer_tokens = set(reference_norm.split()), set(answer_norm.split())
        overlap += len(ref_tokens & answer_tokens) / len(ref_tokens) if ref_tokens else 0
    if count:
        for k, value in source_hits.items():
            aggregate[f"source_recall_at_{k}"] = value / count
        aggregate.update({"mrr": mrr / count, "evidence_substring_recall": evidence / count,
                          "answer_non_empty_rate": non_empty / count, "reference_keyword_recall": keyword_recall / count,
                          "reference_substring_rate": strict / count, "reference_normalized_overlap": overlap / count})
    return aggregate


def score(run_dir: Path, results_path: Path | None = None) -> dict[str, Any]:
    path = results_path or run_dir / "results.jsonl"
    metrics = calculate_metrics(_read_jsonl(path))
    metrics["protocol"] = PROTOCOL
    _write_json(run_dir / "artifacts" / "metrics.json", metrics)
    return metrics


def to_ragas_evaluation_dataset(results: Iterable[dict[str, Any]]) -> Any:
    """Convert runner rows to Ragas' dataset when Ragas is installed.

    This adapter is deliberately opt-in and does not evaluate or invoke an LLM.
    Ragas has changed dataset import paths across releases, so the import is
    isolated here and callers receive a clear install/version error.
    """
    try:
        from ragas import EvaluationDataset, SingleTurnSample
    except ImportError as exc:
        raise RuntimeError("optional Ragas conversion requires the ragas package") from exc
    samples = []
    for result in results:
        case = result.get("case") or {}
        samples.append(SingleTurnSample(
            user_input=case.get("question", ""),
            retrieved_contexts=[str(chunk.get("content", "")) for chunk in _chunks(result)],
            response=result.get("answer", "") or "",
            reference=(case.get("metadata") or {}).get("reference", ""),
        ))
    return EvaluationDataset(samples=samples)


def report(run_dir: Path, output: Path | None = None) -> Path:
    manifest = json.loads((run_dir / "artifacts/dataset_manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "artifacts/metrics.json").read_text(encoding="utf-8"))
    lines = ["# WikiEval → MOI benchmark report", "", f"- Protocol: `{manifest['protocol']}`", f"- Dataset: `{manifest['source']['repo']}` / `{manifest['source']['revision_or_local_filename']}`", f"- Dataset SHA256: `{manifest['source']['dataset_sha256']}`", f"- Selected rows / unique sources: {manifest['dataset']['rows_selected']} / {manifest['dataset']['unique_sources']}", "", "## Metrics", "", "| Metric | Value |", "|---|---:|"]
    for key, value in metrics.items():
        if key != "protocol":
            lines.append(f"| `{key}` | {value} |")
    ragas_summary_path = run_dir / "artifacts/ragas/summary.json"
    ragas_config_path = run_dir / "artifacts/ragas/config.json"
    if ragas_summary_path.exists():
        ragas_summary = json.loads(ragas_summary_path.read_text(encoding="utf-8"))
        lines += ["", "## Ragas diagnostic metrics", "", "| Metric | Scored rows | Mean | P50 |", "|---|---:|---:|---:|"]
        for key, value in (ragas_summary.get("metrics") or {}).items():
            lines.append(f"| `{key}` | {value.get('scored_rows')} | {value.get('mean')} | {value.get('p50')} |")
        lines.append(f"- Ragas rows evaluated: {ragas_summary.get('rows')}.")
        if ragas_config_path.exists():
            ragas_config = json.loads(ragas_config_path.read_text(encoding="utf-8"))
            lines.append(f"- Judge model: `{ragas_config.get('llm_model')}`; embedding model: `{ragas_config.get('embedding_model')}`; Ragas: `{ragas_config.get('ragas_version')}`.")
    lines += ["", "## Scope and limitations", "", "- WikiEval official row fields are adapted from `source`, `question`, `grounded_answer`, `context_v1`, and `context_v2`; `grounded_answer` is retained as the reference mapping for this local snapshot.", "- The deterministic MOI score is primary: availability, ranked source recall, MRR, evidence substring recall, and latency. Reference/answer checks are diagnostics.", "- Ragas EvaluationDataset and Ragas/LLM-judge metrics are diagnostic only; they are not the primary score.", "- Dataset acquisition is completed before the run; no network resource is downloaded during scoring/reporting. Results without ranked chunks or latency are reported only on the available denominator.", "", "## Artifact paths", "", f"- `{run_dir / 'artifacts' / 'dataset_manifest.json'}`", f"- `{run_dir / 'artifacts' / 'questions.jsonl'}`", f"- `{run_dir / 'artifacts' / 'documents'}`", f"- `{run_dir / 'artifacts' / 'metrics.json'}`"]
    if ragas_summary_path.exists():
        lines += [f"- `{ragas_summary_path}`", f"- `{run_dir / 'artifacts/ragas/scores.jsonl'}`"]
    path = output or run_dir / "artifacts/report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p_prepare.add_argument("--run", type=Path, required=True)
    p_score = sub.add_parser("score")
    p_score.add_argument("--run", type=Path, required=True)
    p_score.add_argument("--results", type=Path)
    p_report = sub.add_parser("report")
    p_report.add_argument("--run", type=Path, required=True)
    p_report.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.dataset, args.run)
    elif args.command == "score":
        score(args.run, args.results)
    else:
        print(report(args.run, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
