#!/usr/bin/env python3
"""Build the first unified MOI RAG benchmark slice.

The source packages intentionally keep their original identifiers and gold
annotations in the generated records.  The output adds stable MOI identifiers
and rewrites gold document references into the 500-document unified corpus.

This script is deterministic.  It is designed to be rerun after the source
packages change, with the same source paths and selection policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Set, Tuple


ROOT = Path(__file__).resolve().parents[1]
READY_ROOT = ROOT / ".local-services" / "competitor-eval-ready" / "v1"
PARSED_ROOT = ROOT / "outputs" / "parsed-documents" / "moi-ready-v1" / "datasets"
DEFAULT_OUTPUT = ROOT / "datasets" / "moi-rag-bench-v0.1"
SELECTION_SEED = "moi-rag-bench-v0.1:20260816"


SOURCE_CONFIG: Dict[str, Dict[str, Any]] = {
    "docbench": {
        "slug": "docbench",
        "label": "DocBench controlled parsed text",
        "package_root": READY_ROOT / "docbench" / "controlled-parsed-text",
        "doc_cap": 180,
        "qa_cap": 450,
        "qa_targets": {
            "text-only": 168,
            "meta-data": 108,
            "multimodal-t": 90,
            "multimodal-f": 36,
            "unanswerable": 45,
            "una-web": 3,
        },
        "result_basis": [
            {
                "path": "runs/stage1/docbench-fastgpt/20260813-fastgpt-docbench-controlled-full-v2/summary.json",
                "description": "FastGPT full controlled-parsed-text run; 1102 planned QA, 1076 SUCCESS and 26 EMPTY, no failed attempts.",
            }
        ],
    },
    "enterprise": {
        "slug": "enterprise",
        "label": "EnterpriseRAG-Bench adapted slice",
        "package_root": READY_ROOT / "enterprise-rag-bench",
        "doc_cap": 150,
        "qa_cap": 150,
        "selection_mode": "compact",
        "qa_targets": {
            "basic": 49,
            "semantic": 39,
            "intra_document_reasoning": 12,
            "project_related": 11,
            "constrained": 9,
            "conflicting_info": 6,
            "miscellaneous": 6,
            "high_level": 3,
            "completeness": 1,
            "info_not_found": 14,
        },
        "result_basis": [
            {
                "path": "runs/stage1/enterpriserag-bench-fastgpt/20260813-fastgpt-enterpriserag-adapted500-v3-rpm-safe/enterprise-evaluation-metrics.json",
                "description": "FastGPT complete adapted 500-QA run; 500 terminal successful QA, retrieval doc recall@10 89.61% on linked questions.",
            }
        ],
    },
    "multihop": {
        "slug": "multihop",
        "label": "MultiHop-RAG official corpus",
        "package_root": READY_ROOT / "multihop-rag",
        "doc_cap": 120,
        "qa_cap": 250,
        "qa_targets": {
            "comparison_query": 84,
            "inference_query": 80,
            "temporal_query": 57,
            "null_query": 29,
        },
        "result_basis": [
            {
                "path": "runs/stage1/multihop-rag-fastgpt/20260813-fastgpt-multihop-rag-full-v1/summary.json",
                "description": "FastGPT full MultiHop-RAG run; 2556 planned QA, 2536 SUCCESS and 20 EMPTY, no failed attempts.",
            },
            {
                "path": "runs/stage1/multihop-rag-fastgpt/20260813-fastgpt-multihop-rag-full-v1/fastgpt-multihop-metrics.json",
                "description": "Per-question retrieval and answer metrics for the same full run.",
            },
        ],
    },
    "mmdocir": {
        "slug": "mmdocir",
        "label": "MMDocIR page condition",
        "package_root": READY_ROOT / "mmdocir" / "page",
        "doc_cap": 50,
        "qa_cap": 150,
        "qa_targets": {"retrieval": 150},
        "result_basis": [
            {
                "path": "runs/stage1/mmdocir-qa/20260813-230700-mmdocir-qwen35-recovery-full-1658/qa-summary.json",
                "description": "Local MOI full 1658-QA run; all 1658 terminal attempts successful. This is an evidence/QA run, not a directly comparable competitor score.",
            }
        ],
    },
}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def stable_hash(*parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def global_doc_id(dataset: str, source_id: str) -> str:
    return f"moi500d_doc_{SOURCE_CONFIG[dataset]['slug']}_{stable_hash(dataset, source_id)[:12]}"


def global_question_id(dataset: str, source_id: str) -> str:
    return f"moi500d_qa_{SOURCE_CONFIG[dataset]['slug']}_{stable_hash(dataset, source_id)[:12]}"


def normalized_name(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\\", "/").rsplit("/", 1)[-1].lower()
    # Remove a final extension, but keep dotted corpus identifiers such as
    # 2020.acl-main.408 intact.
    text = re.sub(r"\.(pdf|md|txt|json|html?)$", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def compact_json(value: Any, depth: int = 0) -> Any:
    """Keep useful source metadata without copying parser/run internals."""

    if depth > 2:
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        compacted = [compact_json(item, depth + 1) for item in value[:25]]
        return [item for item in compacted if item is not None]
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key in sorted(value):
            # These fields are large, machine-specific, or contain run paths
            # that do not belong in a portable benchmark artifact.
            if key in {
                "parsed_manifest_row",
                "attempts",
                "layout_mapping",
                "image_path",
                "source_path",
                "parsed_manifest_path",
                "sha256_path",
            }:
                continue
            compacted = compact_json(value[key], depth + 1)
            if compacted is not None:
                result[str(key)] = compacted
        return result
    return str(value)


def compact_metadata(value: Any) -> Dict[str, Any]:
    result = compact_json(value or {})
    return result if isinstance(result, dict) else {}


def repo_reference(raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    raw_text = str(raw)
    candidate = Path(raw_text)
    if candidate.is_absolute():
        try:
            return str(candidate.relative_to(ROOT))
        except ValueError:
            # Avoid embedding the developer's home-directory path in a
            # portable artifact while retaining where the source came from.
            return f"external_snapshot_reference:{candidate.name}"
    return raw_text


def question_type(dataset: str, row: Mapping[str, Any]) -> str:
    value = row.get("question_type")
    if value:
        return str(value)
    metadata = row.get("metadata") or {}
    value = metadata.get("question_type") or metadata.get("original_type")
    if value:
        return str(value)
    if dataset == "mmdocir":
        return "retrieval"
    return "unknown"


def source_question_id(row: Mapping[str, Any]) -> str:
    value = row.get("question_id") or row.get("id")
    if not value:
        raise ValueError(f"Question has no question_id/id: {row}")
    return str(value)


def source_document_id(dataset: str, row: Mapping[str, Any]) -> str:
    if dataset == "mmdocir":
        value = row.get("scope_id") or (row.get("metadata") or {}).get("scope_id")
    else:
        value = row.get("doc_id") or row.get("scope_id")
    if not value:
        raise ValueError(f"Document has no source id for {dataset}: {row}")
    return str(value)


def gold_document_refs(dataset: str, question: Mapping[str, Any], gold: Mapping[str, Any]) -> Set[str]:
    if dataset == "mmdocir":
        # MMDocIR gold_doc_ids are page ids.  The unified benchmark is
        # document-grained, so link the QA to its source document scope.
        values = question.get("scope_doc_ids") or gold.get("scope_doc_ids") or []
    else:
        values = (
            question.get("gold_doc_ids")
            or gold.get("gold_doc_ids")
            or gold.get("expected_doc_ids")
            or question.get("expected_doc_ids")
            or []
        )
    if isinstance(values, str):
        values = [values]
    return {str(value) for value in values if value}


def evidence_class(value: Any) -> str:
    text = str(value or "").lower()
    if "multimodal" in text:
        return "multimodal"
    if "meta-data" in text or "metadata" in text:
        return "metadata"
    if "table" in text:
        return "table"
    if "figure" in text:
        return "figure"
    if "chart" in text:
        return "chart"
    if "layout" in text:
        return "layout"
    if "pure-text" in text or "text-only" in text or "generalized-text" in text:
        return "text"
    return "other"


def load_source(dataset: str) -> Dict[str, Any]:
    config = SOURCE_CONFIG[dataset]
    root = config["package_root"]
    corpus = read_jsonl(root / "corpus.jsonl")
    questions = read_jsonl(root / "questions.jsonl")
    gold_rows = read_jsonl(root / "gold.jsonl")
    gold_by_id = {source_question_id(row): row for row in gold_rows}
    if len(gold_by_id) != len(gold_rows):
        raise ValueError(f"Duplicate gold question ids in {dataset}")
    return {"corpus": corpus, "questions": questions, "gold_by_id": gold_by_id}


def build_doc_records(dataset: str, source: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    corpus = source["corpus"]
    records: Dict[str, Dict[str, Any]] = {}

    if dataset == "mmdocir":
        pages_by_scope: MutableMapping[str, List[Dict[str, Any]]] = defaultdict(list)
        for page in corpus:
            pages_by_scope[source_document_id(dataset, page)].append(page)
        for doc_id, pages in pages_by_scope.items():
            pages.sort(key=lambda row: ((row.get("metadata") or {}).get("page_number", 0), str(row.get("doc_id"))))
            first = pages[0]
            first_meta = first.get("metadata") or {}
            content = "\n\n".join(str(page.get("content") or "").strip() for page in pages).strip()
            source_meta = compact_metadata(first_meta)
            source_meta["page_count"] = len(pages)
            records[doc_id] = {
                "source_document_id": doc_id,
                "title": first_meta.get("doc_name") or first.get("title") or doc_id,
                "content": content,
                "media_type": first.get("media_type") or "application/pdf",
                "source_sha256": first.get("sha256"),
                "source_reference": repo_reference(first_meta.get("source_binary_path") or first.get("binary_path")),
                "source_metadata": source_meta,
                "dedup_names": {
                    normalized_name(first_meta.get("doc_name")),
                    normalized_name(first_meta.get("source_binary_path")),
                },
            }
        return records

    if dataset == "enterprise":
        parsed_path = PARSED_ROOT / "enterpriserag-bench" / "moi-documents.jsonl"
        blocks_by_file: MutableMapping[str, List[Dict[str, Any]]] = defaultdict(list)
        for block in read_jsonl(parsed_path):
            metadata = block.get("metadata") or {}
            file_name = metadata.get("benchmark_source_file") or metadata.get("file_name")
            if file_name:
                blocks_by_file[str(file_name)].append(block)
        for row in corpus:
            doc_id = source_document_id(dataset, row)
            text_path = row.get("text_path")
            file_name = Path(str(text_path)).name if text_path else f"{doc_id}.md"
            blocks = blocks_by_file.get(file_name, [])
            blocks.sort(key=lambda block: (block.get("document_index", 0), str(block.get("block_uuid"))))
            content = "\n\n".join(str(block.get("content") or "").strip() for block in blocks).strip()
            if not content and text_path and Path(str(text_path)).exists():
                content = Path(str(text_path)).read_text(encoding="utf-8")
            metadata = compact_metadata(row.get("metadata"))
            metadata["parsed_block_count"] = len(blocks)
            records[doc_id] = {
                "source_document_id": doc_id,
                "title": row.get("title") or file_name,
                "content": content,
                "media_type": row.get("media_type") or "text/markdown",
                "source_sha256": row.get("sha256"),
                "source_reference": repo_reference(text_path),
                "source_metadata": metadata,
                "dedup_names": {normalized_name(doc_id), normalized_name(file_name)},
            }
        return records

    if dataset == "multihop":
        plain_root = PARSED_ROOT / "multihop-rag" / "documents"
        for row in corpus:
            doc_id = source_document_id(dataset, row)
            metadata = row.get("metadata") or {}
            official_index = metadata.get("official_index")
            content_path: Path | None = None
            if official_index is not None:
                content_path = plain_root / f"article-{int(official_index):04d}" / "payload" / "plain-text.txt"
            if content_path is None or not content_path.exists():
                candidate = row.get("text_path")
                if candidate and Path(str(candidate)).exists():
                    content_path = Path(str(candidate))
            content = content_path.read_text(encoding="utf-8") if content_path and content_path.exists() else ""
            source_meta = compact_metadata(metadata)
            if content_path:
                source_meta["parsed_content_path"] = repo_reference(content_path)
            records[doc_id] = {
                "source_document_id": doc_id,
                "title": row.get("title") or metadata.get("title") or doc_id,
                "content": content,
                "media_type": row.get("media_type") or "text/markdown",
                "source_sha256": row.get("sha256"),
                "source_reference": repo_reference(content_path or row.get("text_path")),
                "source_metadata": source_meta,
                "dedup_names": {normalized_name(doc_id), normalized_name(metadata.get("title"))},
            }
        return records

    # DocBench controlled-parsed-text already exposes one complete document
    # row per source document.
    for row in corpus:
        doc_id = source_document_id(dataset, row)
        metadata = compact_metadata(row.get("metadata"))
        records[doc_id] = {
            "source_document_id": doc_id,
            "title": row.get("title") or doc_id,
            "content": str(row.get("content") or ""),
            "media_type": row.get("media_type") or "application/pdf",
            "source_sha256": row.get("sha256"),
            "source_reference": repo_reference(row.get("binary_path") or row.get("text_path")),
            "source_metadata": metadata,
            "dedup_names": {
                normalized_name(doc_id.split(":")[-1]),
                normalized_name(row.get("title")),
            },
        }
    return records


def candidate_rows(
    dataset: str,
    source: Mapping[str, Any],
    doc_records: Mapping[str, Mapping[str, Any]],
    blocked_doc_names: Set[str],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for question in source["questions"]:
        qid = source_question_id(question)
        gold = source["gold_by_id"].get(qid, {})
        refs = gold_document_refs(dataset, question, gold)
        refs = {ref for ref in refs if ref in doc_records}
        if dataset == "mmdocir":
            # Drop MMDocIR source documents that are already represented by
            # DocBench, even if a source question happens not to have a page
            # gold row in the local package.
            refs = {ref for ref in refs if not (set(doc_records[ref].get("dedup_names", set())) & blocked_doc_names)}
            if not refs:
                continue
        if dataset != "mmdocir" and not refs and question_type(dataset, question) not in {"null_query", "high_level", "info_not_found"}:
            continue
        metadata = question.get("metadata") or {}
        raw_domain = metadata.get("domain") or metadata.get("category")
        if not raw_domain:
            if dataset == "enterprise":
                source_types = metadata.get("source_types") or ["enterprise"]
                raw_domain = "source:" + "/".join(str(item) for item in source_types)
            else:
                raw_domain = dataset
        raw_evidence = metadata.get("evidence_type")
        if not raw_evidence:
            if dataset in {"docbench", "multihop"}:
                raw_evidence = question_type(dataset, question)
            else:
                raw_evidence = "text"
        candidates.append(
            {
                "question": question,
                "gold": gold,
                "question_id": qid,
                "question_type": question_type(dataset, question),
                "refs": refs,
                "domain": str(raw_domain),
                "evidence_class": evidence_class(raw_evidence),
            }
        )
    return candidates


def select_by_type(
    dataset: str,
    candidates: Sequence[Mapping[str, Any]],
    targets: Mapping[str, int],
    doc_cap: int,
    selection_mode: str = "broad",
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    ordered_types = list(targets)
    by_type: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_type[str(candidate["question_type"])].append(candidate)
    for qtype in by_type:
        by_type[qtype].sort(key=lambda item: stable_hash(SELECTION_SEED, dataset, item["question_id"]))

    positions = Counter()
    remaining = {qtype: int(targets[qtype]) for qtype in ordered_types}
    selected: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()
    used_docs: Set[str] = set()

    while sum(remaining.values()) > 0:
        progressed = False
        for qtype in ordered_types:
            if remaining[qtype] <= 0:
                continue
            pool = by_type.get(qtype, [])
            chosen: Mapping[str, Any] | None = None
            chosen_position = None
            for index, candidate in enumerate(pool):
                qid = str(candidate["question_id"])
                if qid in selected_ids:
                    continue
                refs = set(candidate["refs"])
                if len(used_docs | refs) > doc_cap:
                    continue
                # Most sources use a broad spread. EnterpriseRAG has
                # multi-document gold sets, so its compact mode prefers
                # candidates that add the fewest new documents while still
                # meeting every type quota.
                if chosen is None:
                    chosen = candidate
                    chosen_position = index
                else:
                    old_new = len(set(chosen["refs"]) - used_docs)
                    new = len(refs - used_docs)
                    if selection_mode == "compact":
                        old_key = (old_new, len(set(chosen["refs"])), int(chosen_position))
                        new_key = (new, len(refs), index)
                        better = new_key < old_key
                    else:
                        better = new > old_new or (new == old_new and index < int(chosen_position))
                    if better:
                        chosen = candidate
                        chosen_position = index
            if chosen is None:
                available = len(pool) - positions[qtype]
                raise RuntimeError(
                    f"Cannot meet {dataset} target {qtype}={targets[qtype]}; "
                    f"selected={targets[qtype] - remaining[qtype]}, available={available}, docs={len(used_docs)}/{doc_cap}"
                )
            qid = str(chosen["question_id"])
            selected.append(dict(chosen))
            selected_ids.add(qid)
            used_docs.update(chosen["refs"])
            remaining[qtype] -= 1
            positions[qtype] += 1
            progressed = True
        if not progressed:
            raise RuntimeError(f"No progress selecting {dataset}")
    return selected, used_docs


MMDOCIR_DOMAIN_Q_TARGETS = {
    "Academic paper": 31,
    "Research report / Introduction": 29,
    "News": 21,
    "Guidebook": 17,
    "Financial report": 16,
    "Tutorial/Workshop": 16,
    "Brochure": 12,
    "Administration/Industry file": 8,
}

MMDOCIR_DOMAIN_DOC_TARGETS = {
    "Academic paper": 11,
    "Research report / Introduction": 10,
    "News": 1,
    "Guidebook": 8,
    "Financial report": 5,
    "Tutorial/Workshop": 7,
    "Brochure": 5,
    "Administration/Industry file": 3,
}


def select_mmdocir(
    candidates: Sequence[Mapping[str, Any]],
    doc_cap: int,
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Select MMDocIR QA while spreading them over 50 source documents."""

    by_domain_doc: Dict[str, Dict[str, List[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for candidate in candidates:
        refs = list(candidate["refs"])
        if len(refs) != 1:
            continue
        by_domain_doc[str(candidate["domain"])][refs[0]].append(candidate)

    selected_docs: Set[str] = set()
    all_domains = list(MMDOCIR_DOMAIN_DOC_TARGETS)
    for domain in all_domains:
        docs = by_domain_doc.get(domain, {})
        ranked = sorted(
            docs,
            key=lambda doc_id: (-len(docs[doc_id]), stable_hash(SELECTION_SEED, "mmdocir-doc", doc_id)),
        )
        target = min(MMDOCIR_DOMAIN_DOC_TARGETS[domain], len(ranked))
        selected_docs.update(ranked[:target])

    if len(selected_docs) < doc_cap:
        remaining_docs: List[Tuple[str, str, int]] = []
        for domain, docs in by_domain_doc.items():
            for doc_id, rows in docs.items():
                if doc_id not in selected_docs:
                    remaining_docs.append((domain, doc_id, len(rows)))
        remaining_docs.sort(key=lambda item: (-item[2], stable_hash(SELECTION_SEED, "mmdocir-fill-doc", item[1])))
        selected_docs.update(doc_id for _, doc_id, _ in remaining_docs[: doc_cap - len(selected_docs)])
    if len(selected_docs) > doc_cap:
        raise RuntimeError(f"MMDocIR doc pool exceeds cap: {len(selected_docs)} > {doc_cap}")

    by_domain: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        refs = set(candidate["refs"])
        if len(refs) == 1 and next(iter(refs)) in selected_docs:
            by_domain[str(candidate["domain"])].append(candidate)
    for domain in by_domain:
        by_domain[domain].sort(key=lambda item: stable_hash(SELECTION_SEED, "mmdocir-q", item["question_id"]))

    selected: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()
    selected_by_domain: Counter = Counter()
    selected_by_doc: Counter = Counter()
    evidence_seen_by_domain: MutableMapping[str, Set[str]] = defaultdict(set)

    # Reserve one QA for every selected document first.  This prevents the
    # 150 QA from collapsing onto a handful of high-density documents while
    # the remaining 50 documents become unlinked distractors.
    for doc_id in sorted(selected_docs, key=lambda value: stable_hash(SELECTION_SEED, "mmdocir-reserve", value)):
        pool_for_doc = []
        for domain, docs in by_domain_doc.items():
            pool_for_doc.extend(docs.get(doc_id, []))
        if not pool_for_doc:
            raise RuntimeError(f"MMDocIR selected document has no QA candidate: {doc_id}")
        pool_for_doc = sorted(
            pool_for_doc,
            key=lambda item: (
                0 if item["evidence_class"] not in evidence_seen_by_domain[str(item["domain"])] else 1,
                stable_hash(SELECTION_SEED, "mmdocir-reserve-q", item["question_id"]),
            ),
        )
        chosen = pool_for_doc[0]
        selected.append(dict(chosen))
        selected_ids.add(str(chosen["question_id"]))
        domain = str(chosen["domain"])
        selected_by_domain[domain] += 1
        selected_by_doc[doc_id] += 1
        evidence_seen_by_domain[domain].add(str(chosen["evidence_class"]))

    for domain, target in MMDOCIR_DOMAIN_Q_TARGETS.items():
        pool = by_domain.get(domain, [])
        by_doc: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
        for candidate in pool:
            by_doc[next(iter(candidate["refs"]))].append(candidate)
        while selected_by_domain[domain] < target:
            choices: List[Tuple[Tuple[Any, ...], Mapping[str, Any], str]] = []
            for doc_id, pool_for_doc in by_doc.items():
                remaining = [item for item in pool_for_doc if item["question_id"] not in selected_ids]
                for item in remaining:
                    key = (
                        selected_by_doc[doc_id],
                        0 if item["evidence_class"] not in evidence_seen_by_domain[domain] else 1,
                        stable_hash(SELECTION_SEED, "mmdocir-fill-q", item["question_id"]),
                    )
                    choices.append((key, item, doc_id))
            chosen: Mapping[str, Any] | None = None
            chosen_doc_id: str | None = None
            if choices:
                _, chosen, chosen_doc_id = min(choices, key=lambda item: item[0])
            if chosen is None:
                raise RuntimeError(
                    f"Cannot meet MMDocIR domain target {domain}={target}; "
                    f"available={len(pool)} selected={sum(1 for item in selected if item['domain'] == domain)}"
                )
            selected.append(dict(chosen))
            selected_ids.add(str(chosen["question_id"]))
            selected_by_domain[domain] += 1
            selected_by_doc[str(chosen_doc_id)] += 1
            evidence_seen_by_domain[domain].add(str(chosen["evidence_class"]))

    if len(selected) != sum(MMDOCIR_DOMAIN_Q_TARGETS.values()):
        raise RuntimeError(f"MMDocIR selected {len(selected)} QA instead of 150")
    return selected, selected_docs


def grouped_fill(
    dataset: str,
    doc_records: Mapping[str, Mapping[str, Any]],
    required: Set[str],
    preselected: Set[str],
    cap: int,
) -> List[str]:
    selected = set(required) | set(preselected)
    if len(selected) > cap:
        raise RuntimeError(f"{dataset} requires {len(selected)} documents but cap is {cap}")
    available = [doc_id for doc_id in doc_records if doc_id not in selected]

    groups: Dict[str, List[str]] = defaultdict(list)
    for doc_id in available:
        metadata = doc_records[doc_id].get("source_metadata") or {}
        group = str(metadata.get("domain") or metadata.get("category") or metadata.get("source_type") or "other")
        groups[group].append(doc_id)
    for group in groups:
        groups[group].sort(key=lambda doc_id: stable_hash(SELECTION_SEED, dataset, "fill", doc_id))

    group_order = sorted(groups, key=lambda group: stable_hash(SELECTION_SEED, dataset, "group", group))
    positions = Counter()
    while len(selected) < cap:
        progressed = False
        for group in group_order:
            index = positions[group]
            if index >= len(groups[group]):
                continue
            selected.add(groups[group][index])
            positions[group] += 1
            progressed = True
            if len(selected) >= cap:
                break
        if not progressed:
            raise RuntimeError(f"Not enough documents to fill {dataset}: {len(selected)}/{cap}")
    return sorted(selected, key=lambda doc_id: stable_hash(SELECTION_SEED, dataset, "output", doc_id))


def answerable_value(dataset: str, question: Mapping[str, Any]) -> bool:
    if "answerable" in question:
        return bool(question["answerable"])
    if "expected_answerable" in question:
        return bool(question["expected_answerable"])
    return True


def reference_answer(question: Mapping[str, Any], gold: Mapping[str, Any]) -> Any:
    return question.get("reference_answer") or gold.get("reference_answer") or gold.get("gold_answer")


def normalized_source_q(dataset: str, candidate: Mapping[str, Any], doc_map: Mapping[Tuple[str, str], str]) -> Dict[str, Any]:
    question = candidate["question"]
    gold = candidate["gold"]
    source_qid = str(candidate["question_id"])
    refs = sorted(str(value) for value in candidate["refs"])
    global_qid = global_question_id(dataset, source_qid)
    global_refs = [doc_map[(dataset, ref)] for ref in refs]
    metadata = compact_metadata(question.get("metadata"))
    metadata["selection_bucket"] = str(candidate["question_type"])
    metadata["selection_domain"] = str(candidate["domain"])
    metadata["selection_evidence_class"] = str(candidate["evidence_class"])
    metadata["selection_seed"] = SELECTION_SEED
    return {
        "question_id": global_qid,
        "source_dataset": dataset,
        "source_question_id": source_qid,
        "question": question.get("question") or "",
        "question_type": str(candidate["question_type"]),
        "answerable": answerable_value(dataset, question),
        "gold_doc_ids": global_refs,
        "source_gold_doc_ids": refs,
        "source_scope_doc_ids": sorted(str(value) for value in (question.get("scope_doc_ids") or []))[:1000],
        "reference_answer": reference_answer(question, gold),
        "metadata": metadata,
    }


def normalized_gold(dataset: str, candidate: Mapping[str, Any], doc_map: Mapping[Tuple[str, str], str]) -> Dict[str, Any]:
    question = candidate["question"]
    gold = candidate["gold"]
    source_qid = str(candidate["question_id"])
    refs = sorted(str(value) for value in candidate["refs"])
    global_qid = global_question_id(dataset, source_qid)
    source_evidence = question.get("gold_evidence") or gold.get("gold_evidence") or question.get("relevant_evidence") or []
    return {
        "question_id": global_qid,
        "source_dataset": dataset,
        "source_question_id": source_qid,
        "gold_doc_ids": [doc_map[(dataset, ref)] for ref in refs],
        "source_gold_doc_ids": refs,
        "gold_evidence": compact_json(source_evidence),
        "reference_answer": reference_answer(question, gold),
        "source_gold": compact_metadata(gold),
    }


def build_benchmark(output: Path) -> Dict[str, Any]:
    loaded: Dict[str, Dict[str, Any]] = {}
    doc_records_by_dataset: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for dataset in SOURCE_CONFIG:
        loaded[dataset] = load_source(dataset)
        doc_records_by_dataset[dataset] = build_doc_records(dataset, loaded[dataset])

    docbench_names: Set[str] = set()
    for record in doc_records_by_dataset["docbench"].values():
        docbench_names.update(name for name in record.get("dedup_names", set()) if name)

    selected_candidates: Dict[str, List[Dict[str, Any]]] = {}
    preselected_docs: Dict[str, Set[str]] = defaultdict(set)
    selection_stats: Dict[str, Any] = {}
    for dataset, config in SOURCE_CONFIG.items():
        candidates = candidate_rows(dataset, loaded[dataset], doc_records_by_dataset[dataset], docbench_names)
        if dataset == "mmdocir":
            selected, preselected = select_mmdocir(candidates, config["doc_cap"])
            preselected_docs[dataset].update(preselected)
        else:
            selected, _ = select_by_type(
                dataset,
                candidates,
                config["qa_targets"],
                config["doc_cap"],
                config.get("selection_mode", "broad"),
            )
        selected_candidates[dataset] = selected
        selection_stats[dataset] = {
            "candidate_questions": len(candidates),
            "selected_questions": len(selected),
            "selected_question_types": dict(sorted(Counter(item["question_type"] for item in selected).items())),
            "selected_domains": dict(sorted(Counter(item["domain"] for item in selected).items())),
            "selected_evidence_classes": dict(sorted(Counter(item["evidence_class"] for item in selected).items())),
        }

    doc_ids_by_dataset: Dict[str, List[str]] = {}
    for dataset, config in SOURCE_CONFIG.items():
        required = set()
        for candidate in selected_candidates[dataset]:
            required.update(candidate["refs"])
        doc_ids_by_dataset[dataset] = grouped_fill(
            dataset,
            doc_records_by_dataset[dataset],
            required,
            preselected_docs[dataset],
            config["doc_cap"],
        )
        selection_stats[dataset]["required_documents"] = len(required)
        selection_stats[dataset]["selected_documents"] = len(doc_ids_by_dataset[dataset])
        selection_stats[dataset]["distractor_documents"] = len(set(doc_ids_by_dataset[dataset]) - required)

    doc_map: Dict[Tuple[str, str], str] = {}
    documents: List[Dict[str, Any]] = []
    for dataset in SOURCE_CONFIG:
        required = set()
        for candidate in selected_candidates[dataset]:
            required.update(candidate["refs"])
        for source_id in doc_ids_by_dataset[dataset]:
            record = doc_records_by_dataset[dataset][source_id]
            gid = global_doc_id(dataset, source_id)
            doc_map[(dataset, source_id)] = gid
            content = str(record.get("content") or "")
            documents.append(
                {
                    "doc_id": gid,
                    "source_dataset": dataset,
                    "source_document_id": source_id,
                    "title": record.get("title") or source_id,
                    "content": content,
                    "content_chars": len(content),
                    "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "media_type": record.get("media_type"),
                    "source_sha256": record.get("source_sha256"),
                    "source_reference": record.get("source_reference"),
                    "source_metadata": record.get("source_metadata") or {},
                    "distractor": source_id not in required,
                }
            )

    questions: List[Dict[str, Any]] = []
    gold: List[Dict[str, Any]] = []
    selection_audit: List[Dict[str, Any]] = []
    linked_counts: Counter = Counter()
    for dataset in SOURCE_CONFIG:
        for candidate in selected_candidates[dataset]:
            normalized_q = normalized_source_q(dataset, candidate, doc_map)
            normalized_g = normalized_gold(dataset, candidate, doc_map)
            questions.append(normalized_q)
            gold.append(normalized_g)
            for ref in candidate["refs"]:
                linked_counts[(dataset, ref)] += 1
            selection_audit.append(
                {
                    "kind": "question",
                    "global_id": normalized_q["question_id"],
                    "source_dataset": dataset,
                    "source_id": candidate["question_id"],
                    "selection_bucket": candidate["question_type"],
                    "domain": candidate["domain"],
                    "evidence_class": candidate["evidence_class"],
                    "gold_source_document_ids": sorted(candidate["refs"]),
                }
            )

    for document in documents:
        key = (document["source_dataset"], document["source_document_id"])
        selection_audit.append(
            {
                "kind": "document",
                "global_id": document["doc_id"],
                "source_dataset": document["source_dataset"],
                "source_id": document["source_document_id"],
                "selection_bucket": "distractor" if document["distractor"] else "gold-linked",
                "linked_question_count": linked_counts[key],
                "dedup_key": normalized_name(document["title"]),
            }
        )

    documents.sort(key=lambda row: row["doc_id"])
    questions.sort(key=lambda row: row["question_id"])
    gold.sort(key=lambda row: row["question_id"])
    selection_audit.sort(key=lambda row: (row["kind"], row["global_id"]))

    if len(documents) != 500 or len(questions) != 1000 or len(gold) != 1000:
        raise RuntimeError(f"Unexpected final counts: docs={len(documents)} questions={len(questions)} gold={len(gold)}")

    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "documents.jsonl", documents)
    write_jsonl(output / "questions.jsonl", questions)
    write_jsonl(output / "gold.jsonl", gold)
    write_jsonl(output / "selection.jsonl", selection_audit)

    result_evidence = {
        dataset: config["result_basis"] for dataset, config in SOURCE_CONFIG.items()
    }
    manifest = {
        "schema": "moi-rag-bench-unified-v0.1",
        "version": "0.1.0",
        "generated_at": "2026-08-16",
        "selection_seed": SELECTION_SEED,
        "grain": {
            "document": "one source document; MMDocIR pages are reconstructed into one document",
            "question": "one source QA; source question and gold ids are retained",
        },
        "counts": {
            "documents": len(documents),
            "questions": len(questions),
            "gold": len(gold),
            "distractor_documents": sum(1 for row in documents if row["distractor"]),
        },
        "allocation": {
            dataset: {
                "documents": len(doc_ids_by_dataset[dataset]),
                "questions": len(selected_candidates[dataset]),
                "label": SOURCE_CONFIG[dataset]["label"],
                "question_targets": SOURCE_CONFIG[dataset]["qa_targets"],
            }
            for dataset in SOURCE_CONFIG
        },
        "selection_stats": selection_stats,
        "deduplication": {
            "key": "normalized document id/title/source filename",
            "docbench_blocked_name_count": len(docbench_names),
            "mmdocir_overlap_questions_removed": sum(
                1
                for row in loaded["mmdocir"]["questions"]
                if any(
                    set(doc_records_by_dataset["mmdocir"].get(ref, {}).get("dedup_names", set())) & docbench_names
                    for ref in gold_document_refs("mmdocir", row, loaded["mmdocir"]["gold_by_id"].get(source_question_id(row), {}))
                )
            ),
            "mmdocir_nonoverlap_source_documents_with_questions": len(
                {
                    ref
                    for candidate in candidate_rows("mmdocir", loaded["mmdocir"], doc_records_by_dataset["mmdocir"], docbench_names)
                    for ref in candidate["refs"]
                }
            ),
        },
        "historical_run_basis": result_evidence,
        "known_limitations": [
            "This is a unified selection slice, not a new comparable score: the source packages use different protocols and document grains.",
            "EnterpriseRAG-Bench is the local adapted 500-question slice, not the declared 511,962-row source corpus.",
            "MMDocIR evidence is based on the page condition and is linked at document level after page reconstruction.",
            "The initial slice preserves source QA semantics, including MultiHop null questions and Enterprise info_not_found questions.",
        ],
        "artifacts": {
            "documents": "documents.jsonl",
            "questions": "questions.jsonl",
            "gold": "gold.jsonl",
            "selection_audit": "selection.jsonl",
            "builder": "../../tools/build_moi_unique_bench_v0_1.py",
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def check_output(output: Path) -> None:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    documents = read_jsonl(output / "documents.jsonl")
    questions = read_jsonl(output / "questions.jsonl")
    gold = read_jsonl(output / "gold.jsonl")
    if (len(documents), len(questions), len(gold)) != (500, 1000, 1000):
        raise RuntimeError(f"Count check failed: {len(documents)}, {len(questions)}, {len(gold)}")
    doc_ids = [row["doc_id"] for row in documents]
    question_ids = [row["question_id"] for row in questions]
    gold_ids = [row["question_id"] for row in gold]
    if len(set(doc_ids)) != 500 or len(set(question_ids)) != 1000 or len(set(gold_ids)) != 1000:
        raise RuntimeError("ID uniqueness check failed")
    if set(question_ids) != set(gold_ids):
        raise RuntimeError("Question/gold id integrity check failed")
    doc_id_set = set(doc_ids)
    missing_gold_links = [
        row["question_id"]
        for row in questions
        if any(doc_id not in doc_id_set for doc_id in row.get("gold_doc_ids", []))
    ]
    if missing_gold_links:
        raise RuntimeError(f"Gold links point outside corpus: {missing_gold_links[:5]}")
    empty_content = [row["doc_id"] for row in documents if not str(row.get("content") or "").strip()]
    if empty_content:
        raise RuntimeError(f"Documents without reconstructed content: {empty_content[:5]}")
    allocation = manifest.get("allocation", {})
    if sum(item.get("documents", 0) for item in allocation.values()) != 500:
        raise RuntimeError("Manifest document allocation does not sum to 500")
    if sum(item.get("questions", 0) for item in allocation.values()) != 1000:
        raise RuntimeError("Manifest question allocation does not sum to 1000")
    print(json.dumps({"status": "OK", "documents": 500, "questions": 1000, "gold": 1000}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.check_only:
        check_output(output)
        return
    manifest = build_benchmark(output)
    print(
        json.dumps(
            {
                "status": "BUILT",
                "output": str(output.relative_to(ROOT)),
                "counts": manifest["counts"],
                "allocation": manifest["allocation"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
