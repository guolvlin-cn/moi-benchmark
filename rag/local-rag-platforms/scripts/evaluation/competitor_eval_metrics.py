#!/usr/bin/env python3
"""Deterministic aggregation for local competitor-evaluation runs.

This module is deliberately small and standard-library only.  It reads a
frozen package manifest plus the run's initial/terminal ledgers; it never
downloads data, calls a model, or edits ``TODO.md``.  Missing trace, Gold, or
judge input is represented explicitly instead of being guessed from answer
text.

The public seams are :func:`aggregate_run`, :func:`todo_markdown`, and the
``aggregate``/``todo-markdown`` CLI subcommands.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


TOP_K = (1, 3, 5, 10)
UNSUPPORTED_NEEDS_JUDGE = "UNSUPPORTED_NEEDS_JUDGE"
UNSUPPORTED_TRACE_UNAVAILABLE = "UNSUPPORTED_TRACE_UNAVAILABLE"
UNSUPPORTED_GOLD_UNAVAILABLE = "UNSUPPORTED_GOLD_UNAVAILABLE"
INCOMPLETE_PLANNED_DENOMINATOR = "INCOMPLETE_PLANNED_DENOMINATOR"

VALID_STATUSES = frozenset({"SUCCESS", "EMPTY"})
FAILED_STATUSES = frozenset(
    {
        "FAILED",
        "FAILURE",
        "ERROR",
        "BLOCKED",
        "TIMEOUT",
        "TIMED_OUT",
        "INTERRUPTED",
        "INVALID",
        "CANCELLED",
        "CANCELED",
        "ABORTED",
        "SKIPPED",
        "REJECTED",
    }
)
UNSUPPORTED_STATUSES = frozenset({"UNSUPPORTED", "NOT_SUPPORTED"})
PENDING_STATUSES = frozenset({"PLANNED", "NOT_STARTED", "PENDING", "RUNNING", "IN_PROGRESS"})
EXCLUDED_DATASETS = frozenset({"omnidocbench", "lenovo", "lenovo-bench"})

_DATASET_ALIASES = {
    "wiki": "wikieval",
    "wiki-eval": "wikieval",
    "wikieval": "wikieval",
    "multi-hop": "multihop-rag",
    "multihop": "multihop-rag",
    "multihoprag": "multihop-rag",
    "multihop-rag": "multihop-rag",
    "enterprise": "enterprise-rag-bench",
    "enterprise-rag": "enterprise-rag-bench",
    "enterpriserag": "enterprise-rag-bench",
    "enterpriserag-bench": "enterprise-rag-bench",
    "enterprise-rag-bench": "enterprise-rag-bench",
    "fab": "fab-bench",
    "fabbench": "fab-bench",
    "fab-bench": "fab-bench",
    "mm-doc-ir": "mmdocir",
    "mm_doc_ir": "mmdocir",
    "mmdocir": "mmdocir",
    "mm-doc-rag": "mmdocrag",
    "mm_doc_rag": "mmdocrag",
    "mmdocrag": "mmdocrag",
    "doc-bench": "docbench",
    "doc_bench": "docbench",
    "docbench": "docbench",
    "omnidocbench": "omnidocbench",
    "omni-doc-bench": "omnidocbench",
    "lenovo": "lenovo-bench",
    "lenovo-bench": "lenovo-bench",
}

_ID_KEYS = frozenset(
    {
        "id",
        "document_id",
        "doc_id",
        "file_id",
        "source_id",
        "chunk_id",
        "page_id",
        "layout_id",
        "quote_id",
        "evidence_id",
        "collection_id",
        "source",
        "source_name",
        "sourcename",
        "file_name",
        "filename",
        "name",
        "title",
    }
)
_ANSWER_KEYS = (
    "answer",
    "generated_answer",
    "prediction",
    "response",
    "output",
    "content",
    "text",
)
_HIT_KEYS = (
    "hits",
    "retrieval_hits",
    "retrieved",
    "retrieved_evidence",
    "evidence_hits",
    "search_results",
    "documents",
    "results",
    "records",
    "items",
    "list",
    "retriever_resources",
    "contexts",
    "chunks",
)
_STAGE_ALIASES = {
    "retrieve": "retrieval",
    "retrieval": "retrieval",
    "search": "retrieval",
    "direct_retrieval": "retrieval",
    "retriever": "retrieval",
    "qa": "qa",
    "answer": "qa",
    "generation": "qa",
    "generate": "qa",
    "native_qa": "qa",
    "controlled_qa": "qa",
}


class MetricsError(RuntimeError):
    """Raised for malformed local input or an unusable manifest."""


@dataclass
class PackageData:
    root: Path
    manifest_path: Path | None
    manifest: dict[str, Any]
    condition_manifest: dict[str, Any]
    dataset_id: str
    dataset_name: str
    revision: str
    split: str
    protocol_tag: str
    condition: str
    questions: list[dict[str, Any]]
    corpus: list[dict[str, Any]]
    gold: dict[str, dict[str, Any]]


@dataclass
class StageState:
    name: str
    units: list[tuple[str, int]]
    rows: dict[tuple[str, int], dict[str, Any]]
    questions: dict[str, dict[str, Any]]
    planned_n: int
    terminal_n: int
    valid_n: int
    failed_n: int
    unsupported_n: int
    pending_n: int
    status_counts: dict[str, int]

    @property
    def denominator(self) -> dict[str, int]:
        # Keep this compact and stable: callers use this object as the
        # denominator contract for every metric below it.
        return {
            "planned_n": self.planned_n,
            "terminal_n": self.terminal_n,
            "valid_n": self.valid_n,
            "failed_n": self.failed_n,
            "unsupported_n": self.unsupported_n,
            "pending_n": self.pending_n,
        }


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _boolish(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1", "ready", "complete", "completed"}:
            return True
        if normalized in {"false", "no", "0", "unknown", "missing"}:
            return False
    if value is None:
        return default
    return bool(value)


def _first(mapping: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    if mapping is None:
        return default
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


def _json_load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError as exc:
        raise MetricsError(f"FILE_MISSING: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MetricsError(f"JSON_INVALID: {path}: {exc}") from exc


def _jsonl_load(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError as exc:
        raise MetricsError(f"FILE_MISSING: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MetricsError(f"JSONL_INVALID: {path}:{line_number}: {exc}") from exc
        if isinstance(value, Mapping):
            rows.append(dict(value))
    return rows


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _resolve_ref(base: Path, value: Any, *, alternatives: Sequence[Path] = ()) -> Path | None:
    if not isinstance(value, (str, Path)):
        return None
    raw = Path(str(value)).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    candidates = [base / raw, *(root / raw for root in alternatives)]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve() if candidates else None


def _records_from_spec(base: Path, value: Any, label: str, *, alternatives: Sequence[Path] = ()) -> tuple[list[dict[str, Any]], Path | None]:
    source: Path | None = None
    if isinstance(value, Mapping):
        if isinstance(value.get("items"), list):
            value = value["items"]
        elif isinstance(value.get("records"), list):
            value = value["records"]
        elif value.get("path") is not None:
            value = value["path"]
    if isinstance(value, (str, Path)):
        source = _resolve_ref(base, value, alternatives=alternatives)
        if source is None or not source.exists():
            raise MetricsError(f"PACKAGE_{label.upper()}_MISSING: {value}")
        if source.is_dir():
            candidates = sorted(source.glob("*.jsonl")) + sorted(source.glob("*.json"))
            if len(candidates) != 1:
                raise MetricsError(f"PACKAGE_{label.upper()}_PATH_NOT_FILE: {source}")
            source = candidates[0]
        value = _jsonl_load(source) if source.suffix.lower() == ".jsonl" else _json_load(source)
    if isinstance(value, Mapping):
        for key in ("items", "records", label, "data"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
    if not isinstance(value, list):
        raise MetricsError(f"PACKAGE_{label.upper()}_MUST_BE_LIST")
    return [dict(row) for row in value if isinstance(row, Mapping)], source


def _manifest_path(path: str | Path, *, names: Sequence[str]) -> tuple[Path, Path | None]:
    supplied = Path(path).expanduser().resolve()
    if supplied.is_file():
        return supplied.parent, supplied
    if not supplied.is_dir():
        raise MetricsError(f"PATH_NOT_FOUND: {supplied}")
    for name in names:
        candidate = supplied / name
        if candidate.is_file():
            return supplied, candidate
    return supplied, None


def canonical_dataset_id(value: Any) -> str:
    text = str(value or "unknown").strip().casefold().replace("_", "-").replace(" ", "-")
    if text in _DATASET_ALIASES:
        return _DATASET_ALIASES[text]
    compact = re.sub(r"[^a-z0-9-]+", "", text)
    return _DATASET_ALIASES.get(compact, compact or "unknown")


def _condition_from_run(run_manifest: Mapping[str, Any]) -> str:
    return str(_first(run_manifest, "condition", "track", "evaluation_condition", default="") or "").strip()


def _condition_selection(manifest: Mapping[str, Any], run_condition: str) -> tuple[str, dict[str, Any]]:
    conditions = manifest.get("conditions")
    if not isinstance(conditions, Mapping):
        return run_condition or str(manifest.get("condition", "") or ""), dict(manifest)
    candidates = {str(key).casefold(): (str(key), value) for key, value in conditions.items()}
    if run_condition and run_condition.casefold() in candidates and isinstance(candidates[run_condition.casefold()][1], Mapping):
        key, value = candidates[run_condition.casefold()]
        return key, dict(value)
    if len(candidates) == 1:
        key, value = next(iter(candidates.values()))
        return key, dict(value) if isinstance(value, Mapping) else dict(manifest)
    for alias in ("native", "native-pdf", "page", "c15", "default"):
        if alias in candidates and isinstance(candidates[alias][1], Mapping):
            key, value = candidates[alias]
            return key, dict(value)
    return run_condition or "", dict(manifest)


def _question_id(row: Mapping[str, Any]) -> str:
    return str(_first(row, "question_id", "id", "qid", "query_id", default=""))


def _merge_question_gold(question: dict[str, Any], gold: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = dict(question)
    if not gold:
        return merged
    for key, value in gold.items():
        if key not in merged or merged[key] in (None, "", [], {}):
            merged[key] = value
    return merged


def _load_package(package: str | Path, run_manifest: Mapping[str, Any]) -> PackageData:
    root, manifest_path = _manifest_path(
        package,
        names=("package.json", "manifest.json", "dataset-fragment.json", "competitor-eval-ready.json", "package-manifest.json"),
    )
    raw_manifest: Any = {} if manifest_path is None else _json_load(manifest_path)
    if not isinstance(raw_manifest, Mapping):
        raise MetricsError("PACKAGE_MANIFEST_MUST_BE_OBJECT")
    nested_manifest = raw_manifest.get("package")
    if not isinstance(nested_manifest, Mapping):
        nested_manifest = raw_manifest.get("manifest")
    manifest = dict(nested_manifest) if isinstance(nested_manifest, Mapping) else dict(raw_manifest)
    run_condition = _condition_from_run(run_manifest)
    condition, selected = _condition_selection(manifest, run_condition)
    base = manifest_path.parent if manifest_path is not None else root
    # A selected document-fragment condition stores paths relative to the
    # fragment root.  Also try the condition directory for compact manifests.
    condition_root = base / condition if condition else base
    alternatives = (condition_root, base)
    selected_paths = _mapping(selected.get("paths")) or {}

    question_spec = _first(selected, "questions", "questions_path", default=None)
    if question_spec is None:
        question_spec = _first(selected_paths, "questions", "questions_path", default=None)
    if question_spec is None:
        question_spec = _first(manifest, "questions", "questions_path", default=None)
    if question_spec is None:
        for name in ("questions.jsonl", "questions.json"):
            candidate = condition_root / name
            if candidate.exists():
                question_spec = candidate
                break
    questions, _ = _records_from_spec(base, question_spec, "questions", alternatives=alternatives) if question_spec is not None else ([], None)

    gold_spec = _first(selected, "gold", "gold_path", default=None)
    if gold_spec is None:
        gold_spec = _first(selected_paths, "gold", "gold_path", default=None)
    if gold_spec is None:
        gold_spec = _first(manifest, "gold", "gold_path", default=None)
    if gold_spec is None:
        for name in ("gold.jsonl", "gold.json"):
            candidate = condition_root / name
            if candidate.exists():
                gold_spec = candidate
                break
    gold_rows, _ = _records_from_spec(base, gold_spec, "gold", alternatives=alternatives) if gold_spec is not None else ([], None)
    gold = {_question_id(row): row for row in gold_rows if _question_id(row)}
    questions = [_merge_question_gold(row, gold.get(_question_id(row))) for row in questions]

    corpus_spec = _first(selected, "corpus", "corpus_path", default=None)
    if corpus_spec is None:
        corpus_spec = _first(selected_paths, "corpus", "corpus_path", default=None)
    if corpus_spec is None:
        corpus_spec = _first(manifest, "corpus", "corpus_path", default=None)
    if corpus_spec is None:
        for name in ("corpus.jsonl", "corpus.json"):
            candidate = condition_root / name
            if candidate.exists():
                corpus_spec = candidate
                break
    corpus, _ = _records_from_spec(base, corpus_spec, "corpus", alternatives=alternatives) if corpus_spec is not None else ([], None)

    dataset_value = _first(
        manifest,
        "dataset_id",
        "dataset",
        "dataset_name",
        default=_first(run_manifest, "dataset_id", "dataset", "dataset_name", default="unknown"),
    )
    if isinstance(dataset_value, Mapping):
        dataset_name = str(_first(dataset_value, "name", "id", "dataset_id", default="unknown"))
    else:
        dataset_name = str(dataset_value)
    dataset_id = canonical_dataset_id(dataset_name)
    revision = str(
        _first(
            manifest,
            "revision",
            "dataset_revision",
            "gold_version",
            default=_first(run_manifest, "revision", "dataset_revision", "gold_version", default="UNKNOWN"),
        )
    )
    split = str(_first(manifest, "split", default=_first(run_manifest, "split", default="UNKNOWN")))
    protocol = str(
        _first(
            selected,
            "protocol_tag",
            "protocol",
            default=_first(
                manifest,
                "protocol_tag",
                "protocol",
                default=_first(run_manifest, "protocol_tag", "protocol", default="ADAPTED_PROTOCOL"),
            ),
        )
    )
    if not questions:
        # A package may expose only a count and put all Gold on the run ledger.
        # Keep the absence visible; placeholders are added from ledger rows in
        # aggregate_run and never manufacture Gold values.
        questions = []
    return PackageData(
        root=root,
        manifest_path=manifest_path,
        manifest=manifest,
        condition_manifest=selected,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        revision=revision,
        split=split,
        protocol_tag=protocol,
        condition=condition,
        questions=questions,
        corpus=corpus,
        gold=gold,
    )


def _load_run_manifest(run: str | Path) -> tuple[Path, dict[str, Any], Path | None]:
    root, manifest_path = _manifest_path(
        run,
        names=("run-manifest.json", "start-record.json", "run.json", "manifest.json", "package.json"),
    )
    if manifest_path is None:
        return root, {}, None
    raw = _json_load(manifest_path)
    return root, dict(raw) if isinstance(raw, Mapping) else {}, manifest_path


def _read_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    return _jsonl_load(path) if path.is_file() else []


def _ledger_paths(root: Path) -> list[Path]:
    preferred = (
        "terminal-ledger.jsonl",
        "attempts.jsonl",
        "results.jsonl",
        "run-results.jsonl",
        "ledger.jsonl",
        "retrieval-ledger.jsonl",
        "qa-ledger.jsonl",
        "retrieval-results.jsonl",
        "qa-results.jsonl",
    )
    paths: list[Path] = []
    for name in preferred:
        candidate = root / name
        if candidate.is_file():
            paths.append(candidate)
    for pattern in (
        "**/terminal-ledger.jsonl",
        "**/attempts.jsonl",
        "**/results.jsonl",
        "**/run-results.jsonl",
        "**/retrieval-ledger.jsonl",
        "**/qa-ledger.jsonl",
        "**/retrieval-results.jsonl",
        "**/qa-results.jsonl",
    ):
        for candidate in sorted(root.glob(pattern)):
            if candidate.is_file() and candidate not in paths and "http" not in candidate.parts:
                paths.append(candidate)
    return paths


def _load_ledgers(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    initial: list[dict[str, Any]] = []
    initial_candidates = sorted(root.glob("**/initial-ledger.jsonl"))
    for path in initial_candidates:
        if path.is_file():
            initial.extend(_jsonl_load(path))
    terminal: list[dict[str, Any]] = []
    for path in _ledger_paths(root):
        terminal.extend(_jsonl_load(path))
    return initial, terminal


def _normal_stage(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    return _STAGE_ALIASES.get(text, text)


def _status(value: Any) -> str:
    normalized = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    # Historical competitor runners used a compact ``results.jsonl`` schema
    # with ``status: ok``.  Normalize only unambiguous terminal spellings so
    # that the denominator contract stays shared by all runner generations.
    return {
        "OK": "SUCCESS",
        "SUCCESSFUL": "SUCCESS",
        "SUCCEEDED": "SUCCESS",
        "COMPLETED": "SUCCESS",
        "COMPLETE": "SUCCESS",
        "EMPTY_RESULT": "EMPTY",
        "NO_RESULTS": "EMPTY",
        "NOT_FOUND": "EMPTY",
        "FAIL": "FAILED",
    }.get(normalized, normalized)


def _attempt_type_is_primary(row: Mapping[str, Any]) -> bool:
    attempt_type = str(_first(row, "attempt_type", "type", default="initial") or "initial").casefold()
    if attempt_type in {"retry", "diagnostic", "replacement", "recovery"}:
        return False
    if row.get("retry_of") not in (None, "") or row.get("replacement_of") not in (None, ""):
        return False
    if row.get("is_retry") is True:
        return False
    return row.get("planned_denominator", True) is not False


def _row_question_id(row: Mapping[str, Any]) -> str:
    direct = _first(row, "question_id", "qid", "query_id", default=None)
    if direct not in (None, ""):
        return str(direct)
    for key in ("case", "question", "query", "request"):
        nested = _mapping(row.get(key))
        nested_id = _first(nested, "question_id", "id", "qid", "query_id", default=None)
        if nested_id not in (None, ""):
            return str(nested_id)
    direct_id = row.get("id")
    return str(direct_id) if direct_id not in (None, "") else ""


def _repeat_id(row: Mapping[str, Any]) -> int:
    value = _first(row, "repeat_id", "repeat", "run_repeat", default=1)
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _row_has_stage_data(row: Mapping[str, Any], stage: str) -> bool:
    normal = _normal_stage(_first(row, "stage", "phase", "track", default=""))
    if normal == stage:
        return True
    if normal:
        return False
    if _status(row.get("status")) in FAILED_STATUSES | UNSUPPORTED_STATUSES:
        # A legacy whole-run result may record only a terminal error and no
        # stage payload.  Count that unit as failed/unsupported for both
        # applicable ledgers instead of silently turning it into pending.
        return True
    if stage == "retrieval":
        return any(
            key in row
            for key in (
                "hits",
                "retrieval",
                "retrieval_hits",
                "retrieved",
                "retrieval_contract",
                "retrieval_result",
                "retrieval_payload",
                "retrieved_evidence",
                "evidence_hits",
                "retrieval_trace",
                "search_results",
                "chunks",
                "contexts",
                "retriever_resources",
                "documents",
                "results",
            )
        )
    return any(key in row for key in ("answer", "generated_answer", "prediction", "qa", "answer_metrics", "qa_contract"))


def _dedupe_stage_rows(rows: Iterable[Mapping[str, Any]], stage: str) -> dict[tuple[str, int], dict[str, Any]]:
    selected: dict[tuple[str, int], dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if not _attempt_type_is_primary(row) or not _row_has_stage_data(row, stage):
            continue
        question_id = _row_question_id(row)
        if not question_id:
            continue
        key = (question_id, _repeat_id(row))
        # Terminal-ledger writers are append-only.  If a generic source has
        # duplicate keys, keep the first terminal observation deterministically.
        if key not in selected or _status(selected[key].get("status")) in PENDING_STATUSES:
            selected[key] = row
    return selected


def _run_repeats(run_manifest: Mapping[str, Any], initial: Sequence[Mapping[str, Any]], questions_n: int) -> int:
    planned_block = _mapping(run_manifest.get("planned")) or {}
    planned = _first(planned_block, "repeats", default=None)
    if planned is None:
        planned = _first(_mapping(run_manifest.get("denominator_contract")), "repeats", default=None)
    values = [_repeat_id(row) for row in initial if _row_question_id(row)]
    if planned is None and values:
        planned = max(values)
    if planned is None and questions_n:
        initial_attempts = _first(planned_block, "initial_attempts", "attempts", default=None)
        try:
            if initial_attempts is not None and int(initial_attempts) >= questions_n and int(initial_attempts) % questions_n == 0:
                planned = int(initial_attempts) // questions_n
        except (TypeError, ValueError):
            pass
    try:
        repeats = int(planned or 1)
    except (TypeError, ValueError):
        repeats = 1
    return max(1, repeats)


def _manifest_question_count(package: PackageData, run_manifest: Mapping[str, Any]) -> int:
    if package.questions:
        return len(package.questions)
    counts = _mapping(package.manifest.get("counts")) or _mapping(package.condition_manifest.get("counts"))
    count = _first(counts, "questions", "question_rows", "question_count", "questions_count", "num_questions", default=None)
    if count is None:
        count = _first(package.manifest, "question_count", "questions_count", "num_questions", default=None)
    if count is None:
        count = _first(_mapping(run_manifest.get("planned")), "questions", "question_count", default=0)
    try:
        return max(0, int(count or 0))
    except (TypeError, ValueError):
        return 0


def _question_type(row: Mapping[str, Any]) -> str:
    metadata = _mapping(row.get("metadata")) or {}
    case = _mapping(row.get("case")) or {}
    case_metadata = _mapping(case.get("metadata")) or {}
    return str(
        _first(
            row,
            "question_type",
            default=_first(
                metadata,
                "question_type",
                "test_type",
                "original_type",
                default=_first(
                    case,
                    "question_type",
                    default=_first(case_metadata, "question_type", "test_type", "original_type", default=_first(row, "type", default="unknown")),
                ),
            ),
        )
        or "unknown"
    )


def _question_map(package: PackageData, terminal_rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {_question_id(row): dict(row) for row in package.questions if _question_id(row)}
    for row in terminal_rows:
        qid = _row_question_id(row)
        if not qid or qid in result:
            continue
        # This fallback only copies explicitly observed fields.  It is useful
        # for generic/legacy ledgers while keeping missing Gold visibly
        # missing.  Some older competitor runners nested the case under
        # ``case`` and called retrieved chunks ``chunks``.
        case = _mapping(row.get("case")) or {}
        case_metadata = _mapping(case.get("metadata")) or {}
        metadata = dict(_mapping(row.get("metadata")) or case_metadata)
        for keyword_key in ("retrieval_keywords", "expected_answer_keywords", "reference_keywords", "gold_keywords"):
            if keyword_key not in metadata:
                keyword_value = _first(row, keyword_key, default=_first(case, keyword_key, default=None))
                if keyword_value is not None:
                    metadata[keyword_key] = keyword_value
        result[qid] = {
            "question_id": qid,
            "question_type": _question_type(row),
            "question": _first(row, "question", default=_first(case, "question", default="")),
            "reference_answer": _first(
                row,
                "reference_answer",
                "gold_answer",
                "expected_answer",
                "ground_truth_answer",
                default=_first(case, "reference_answer", "gold_answer", "expected_answer", "ground_truth_answer", default=""),
            ),
            "gold_doc_ids": _first(
                row,
                "gold_doc_ids",
                "relevant_documents",
                "expected_doc_ids",
                default=_first(case, "gold_doc_ids", "relevant_documents", "expected_doc_ids", default=[]),
            ),
            "gold_evidence": _first(
                row,
                "gold_evidence",
                "evidence",
                "relevant_evidence",
                default=_first(case, "gold_evidence", "evidence", "relevant_evidence", default=[]),
            ),
            "metadata": metadata,
        }
    return result


def _build_stage(
    stage: str,
    package: PackageData,
    run_manifest: Mapping[str, Any],
    initial: Sequence[Mapping[str, Any]],
    terminal_rows: Sequence[Mapping[str, Any]],
    questions: Mapping[str, dict[str, Any]],
) -> StageState:
    questions_n = _manifest_question_count(package, run_manifest)
    repeats = _run_repeats(run_manifest, initial, questions_n)
    if package.questions:
        question_ids = [_question_id(row) for row in package.questions if _question_id(row)]
    else:
        question_ids = [qid for qid in questions if qid]
    if not question_ids and questions_n:
        question_ids = [f"__planned_{index + 1:05d}" for index in range(questions_n)]
    if questions_n and len(question_ids) < questions_n:
        existing = set(question_ids)
        for index in range(questions_n - len(question_ids)):
            candidate = f"__planned_{index + 1:05d}"
            while candidate in existing:
                candidate = f"_{candidate}"
            question_ids.append(candidate)
            existing.add(candidate)
    units = [(qid, repeat) for qid in question_ids for repeat in range(1, repeats + 1)]
    planned_n = questions_n * repeats if questions_n else len(units)
    selected = _dedupe_stage_rows(terminal_rows, stage)
    # The package (or its frozen count) defines the denominator.  Ignore
    # stray diagnostic/retry question IDs in a run directory rather than
    # allowing them to inflate terminal_n, latency samples, or slices.
    unit_keys = set(units)
    if unit_keys:
        selected = {key: row for key, row in selected.items() if key in unit_keys}
    counts: Counter[str] = Counter(_status(row.get("status")) for row in selected.values())
    terminal_n = sum(counts.get(value, 0) for value in counts if value not in PENDING_STATUSES)
    valid_n = sum(counts.get(value, 0) for value in VALID_STATUSES)
    failed_n = sum(counts.get(value, 0) for value in FAILED_STATUSES)
    unsupported_n = sum(counts.get(value, 0) for value in UNSUPPORTED_STATUSES)
    pending_n = max(0, planned_n - terminal_n)
    return StageState(
        name=stage,
        units=units,
        rows=selected,
        questions=dict(questions),
        planned_n=planned_n,
        terminal_n=terminal_n,
        valid_n=valid_n,
        failed_n=failed_n,
        unsupported_n=unsupported_n,
        pending_n=pending_n,
        status_counts=dict(sorted(counts.items())),
    )


def _metric_record(
    state: StageState,
    value: float | None,
    numerator: float | int | None,
    denominator: int | float | None,
    *,
    eligible_n: int = 0,
    missing_n: int = 0,
    reason: str | None = None,
    unit: str = "rate",
    aggregation: str = "planned-initial-denominator",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "value": None if value is None else _number(value),
        "numerator": None if numerator is None else _number(numerator),
        "denominator": None if denominator is None else _number(denominator),
        "planned_n": state.planned_n,
        "terminal_n": state.terminal_n,
        "valid_n": state.valid_n,
        "failed_n": state.failed_n,
        "unsupported_n": state.unsupported_n,
        "pending_n": state.pending_n,
        "eligible_n": int(eligible_n),
        "missing_n": int(missing_n),
        "unit": unit,
        "aggregation": aggregation,
    }
    if reason:
        record["reason"] = reason
    return record


def _number(value: float | int) -> int | float:
    if isinstance(value, int):
        return value
    rounded = round(float(value), 6)
    return int(rounded) if rounded.is_integer() else rounded


def _rate_from_values(
    state: StageState,
    values: Sequence[float],
    *,
    reason_if_empty: str = UNSUPPORTED_TRACE_UNAVAILABLE,
    eligible_n: int | None = None,
    missing_n: int | None = None,
    force_unsupported: str | None = None,
) -> dict[str, Any]:
    numerator = sum(float(value) for value in values)
    eligible = len(values) if eligible_n is None else eligible_n
    missing = max(0, state.planned_n - eligible) if missing_n is None else missing_n
    if state.planned_n <= 0:
        return _metric_record(state, None, numerator, None, eligible_n=eligible, missing_n=missing, reason="NO_PLANNED_ATTEMPTS")
    if force_unsupported:
        return _metric_record(state, None, numerator, state.planned_n, eligible_n=eligible, missing_n=missing, reason=force_unsupported)
    if state.terminal_n == 0:
        return _metric_record(state, None, numerator, state.planned_n, eligible_n=eligible, missing_n=missing, reason="NO_TERMINAL_OBSERVATIONS")
    if not values:
        return _metric_record(state, None, numerator, state.planned_n, eligible_n=eligible, missing_n=missing, reason=reason_if_empty)
    if state.pending_n:
        return _metric_record(state, None, numerator, state.planned_n, eligible_n=eligible, missing_n=missing, reason=INCOMPLETE_PLANNED_DENOMINATOR)
    return _metric_record(state, numerator / state.planned_n, numerator, state.planned_n, eligible_n=eligible, missing_n=missing)


def _unsupported_record(state: StageState, reason: str = UNSUPPORTED_NEEDS_JUDGE) -> dict[str, Any]:
    return _metric_record(state, None, 0, state.planned_n or None, reason=reason)


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    # Match the existing local scorer's punctuation-insensitive normalization.
    return re.sub(r"\W+", "", text, flags=re.UNICODE)


def _tokens(value: Any) -> list[str]:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.findall(r"[\w\u4e00-\u9fff]+", text, flags=re.UNICODE)


def _token_f1(prediction: Any, reference: Any) -> float | None:
    expected = _tokens(reference)
    predicted = _tokens(prediction)
    if not expected:
        return None
    if not predicted:
        return 0.0
    expected_counts = Counter(expected)
    predicted_counts = Counter(predicted)
    overlap = sum((expected_counts & predicted_counts).values())
    if not overlap:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


def _answer_from_row(row: Mapping[str, Any]) -> str | None:
    for key in _ANSWER_KEYS:
        value = row.get(key)
        if isinstance(value, str):
            return value
    for key in (
        "answer",
        "generated_answer",
        "prediction",
        "qa",
        "native",
        "generation",
        "response_payload",
        "raw_response",
        "result",
        "response",
        "output",
    ):
        nested = _mapping(row.get(key))
        if nested:
            found = _answer_from_row(nested)
            if found is not None:
                return found
    return None


def _gold_answer(question: Mapping[str, Any], row: Mapping[str, Any] | None = None) -> str | None:
    metadata = _mapping(question.get("metadata")) or {}
    for source in (question, metadata):
        value = _first(source, "reference_answer", "gold_answer", "expected_answer", "answer", "ground_truth_answer", default=None)
        if value is not None and str(value) != "":
            return str(value)
    # A run row may carry an explicit copied Gold field, but its ordinary
    # ``answer`` field is the prediction and must never become self-Gold.
    if row:
        value = _first(row, "reference_answer", "gold_answer", "expected_answer", "ground_truth_answer", default=None)
        if value is not None and str(value) != "":
            return str(value)
    return None


def _gold_keywords(question: Mapping[str, Any]) -> list[str]:
    metadata = _mapping(question.get("metadata")) or {}
    values: list[str] = []
    for source in (question, metadata):
        for key in ("retrieval_keywords", "expected_answer_keywords", "reference_keywords", "gold_keywords"):
            if source.get(key) is not None:
                values.extend(str(item) for item in _as_list(source[key]) if str(item).strip())
    return list(dict.fromkeys(values))


def _as_ids(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, Mapping):
        for key in ("id", "document_id", "doc_id", "file_id", "source_id", "quote_id", "evidence_id", "path", "name"):
            if value.get(key) not in (None, ""):
                result.append(str(value[key]))
                break
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            result.extend(_as_ids(item))
    elif value not in (None, ""):
        result.append(str(value))
    return list(dict.fromkeys(result))


def _evidence_ids(value: Mapping[str, Any]) -> list[str]:
    """Collect all explicit evidence identifiers, not just the first one."""

    result: list[str] = []
    for key in (
        "id",
        "quote_id",
        "evidence_id",
        "document_id",
        "doc_id",
        "file_id",
        "source_id",
        "chunk_id",
        "path",
        "name",
    ):
        if value.get(key) not in (None, ""):
            result.extend(_as_ids(value[key]))
    return list(dict.fromkeys(result))


def _id_variants(value: Any) -> set[str]:
    if value in (None, ""):
        return set()
    text = str(value).strip().casefold()
    if not text:
        return set()
    variants = {text}
    variants.add(Path(text).name)
    if text.endswith((".md", ".txt", ".pdf", ".json", ".jsonl")):
        variants.add(Path(text).stem)
    if ":" in text:
        variants.add(text.rsplit(":", 1)[-1])
    return {item for item in variants if item}


def _metadata_identifier_aliases(package: PackageData) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for row in package.corpus:
        ids = _as_ids(row)
        metadata = _mapping(row.get("metadata")) or {}
        for key in _ID_KEYS:
            if row.get(key) not in (None, ""):
                ids.extend(_as_ids(row[key]))
            if metadata.get(key) not in (None, ""):
                ids.extend(_as_ids(metadata[key]))
        if not ids:
            continue
        canonical = str(_first(row, "doc_id", "document_id", "id", default=ids[0]))
        variants = set().union(*(_id_variants(item) for item in ids))
        aliases.setdefault(canonical.casefold(), set()).update(variants)
        # Match either the frozen canonical ID or a runner's filename/source
        # alias against the same corpus row.
        for variant in variants:
            aliases.setdefault(variant, set()).update(variants)
    return aliases


def _gold_doc_ids(question: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("gold_doc_ids", "gold_document_ids", "relevant_document_ids", "relevant_documents", "document_ids", "expected_doc_ids", "valid_doc_ids"):
        if question.get(key) is not None:
            values.extend(_as_ids(question[key]))
    metadata = _mapping(question.get("metadata")) or {}
    for key in ("gold_doc_ids", "expected_doc_ids", "valid_doc_ids"):
        if metadata.get(key) is not None:
            values.extend(_as_ids(metadata[key]))
    if not values:
        for evidence in _gold_evidence(question):
            if isinstance(evidence, Mapping) and str(evidence.get("status", "resolved")).casefold() not in {"missing", "missing_candidate"}:
                values.extend(_evidence_ids(evidence))
    return list(dict.fromkeys(values))


def _gold_evidence(question: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = question.get("gold_evidence")
    if values is None:
        values = question.get("evidence")
    if values is None:
        values = []
        for modality in ("text", "image"):
            for item in _as_list(question.get(f"{modality}_evidence")):
                if isinstance(item, Mapping):
                    enriched = dict(item)
                    enriched.setdefault("modality", modality)
                    values.append(enriched)
    result: list[dict[str, Any]] = []
    for item in _as_list(values):
        if isinstance(item, Mapping):
            value = dict(item)
            if str(value.get("status", "resolved")).casefold() in {"missing", "missing_candidate"} and not _as_ids(value):
                continue
            result.append(value)
    return result


def _iter_nested_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_nested_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_nested_mappings(child)


def _extract_hits(row: Mapping[str, Any]) -> tuple[list[Any] | None, bool]:
    """Return (hits, trace_available), without treating answer text as hits."""

    candidates: list[Any] = []
    for key in (
        "hits",
        "retrieval_hits",
        "diagnostic_hits",
        "retrieved",
        "retrieved_evidence",
        "evidence_hits",
        "retrieval",
        "retrieval_trace",
        "search_results",
        "documents",
        "contexts",
        "chunks",
        "results",
        "retriever_resources",
    ):
        if key in row:
            value = row[key]
            if isinstance(value, Mapping):
                for nested_key in _HIT_KEYS:
                    if isinstance(value.get(nested_key), list):
                        return list(value[nested_key]), True
            if isinstance(value, list):
                return list(value), True
    for key in ("retrieval", "retrieval_result", "retrieval_payload", "payload"):
        nested = _mapping(row.get(key))
        if not nested:
            continue
        for hit_key in (*_HIT_KEYS, "chunks"):
            value = nested.get(hit_key)
            if isinstance(value, list):
                return list(value), True
        if any(key in nested for key in ("records", "retriever_resources", "list")):
            return [], True
    if "hit_count" in row or "retrieval_trace_available" in row:
        return None, bool(row.get("retrieval_trace_available"))
    return None, False


def _hit_ids(hit: Any) -> set[str]:
    values: list[str] = []
    for mapping in _iter_nested_mappings(hit):
        for key, value in mapping.items():
            if str(key).casefold() in _ID_KEYS:
                values.extend(_as_ids(value))
    if isinstance(hit, str):
        values.append(hit)
    return set().union(*(_id_variants(value) for value in values)) if values else set()


def _hit_modalities(hit: Any) -> set[str]:
    values: list[str] = []
    for mapping in _iter_nested_mappings(hit):
        for key in ("modality", "quote_modality", "evidence_modality", "evidence_type", "content_type", "type", "media", "media_type"):
            if mapping.get(key) not in (None, ""):
                values.extend(str(item).casefold() for item in _as_list(mapping[key]))
    normalized: set[str] = set()
    for value in values:
        if "image" in value or value in {"figure", "chart", "table-image", "visual"}:
            normalized.add("image")
        elif "text" in value or value in {"ocr", "markdown", "plain"}:
            normalized.add("text")
    return normalized


def _ordered_hits(hits: Sequence[Any]) -> list[Any]:
    """Honor explicit runner ranks while preserving input order otherwise."""

    decorated: list[tuple[float | None, int, Any]] = []
    has_rank = False
    for index, hit in enumerate(hits):
        rank_value: float | None = None
        for mapping in _iter_nested_mappings(hit):
            raw = _first(mapping, "rank", "position", "rank_index", "order", default=None)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(float(raw)):
                rank_value = float(raw)
                has_rank = True
                break
        decorated.append((rank_value, index, hit))
    if not has_rank:
        return list(hits)
    return [item for _, _, item in sorted(decorated, key=lambda value: (value[0] is None, value[0] if value[0] is not None else value[1], value[1]))]


def _locator_values(value: Any) -> list[tuple[str | None, str | None, tuple[float, ...] | None]]:
    result: list[tuple[str | None, str | None, tuple[float, ...] | None]] = []
    for mapping in _iter_nested_mappings(value):
        file_value = _first(mapping, "file_id", "file", "doc_name", "document_id", "doc_id", "source_id", default=None)
        page_value = _first(mapping, "page", "page_number", "page_id", default=None)
        bbox_value = _first(mapping, "bbox", "bounding_box", "box", default=None)
        bbox: tuple[float, ...] | None = None
        if isinstance(bbox_value, (list, tuple)) and len(bbox_value) == 4:
            try:
                bbox = tuple(float(item) for item in bbox_value)
            except (TypeError, ValueError):
                bbox = None
        if file_value is not None or page_value is not None or bbox is not None:
            result.append(
                (
                    next(iter(_id_variants(file_value)), None) if file_value is not None else None,
                    str(page_value) if page_value is not None else None,
                    bbox,
                )
            )
    # De-duplicate while preserving traversal order.
    output: list[tuple[str | None, str | None, tuple[float, ...] | None]] = []
    for item in result:
        if item not in output:
            output.append(item)
    return output


def _gold_locator_items(question: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for evidence in _gold_evidence(question):
        locators = _locator_values(evidence.get("locator", evidence))
        if locators:
            result.append(
                {
                    "evidence": evidence,
                    "locators": locators,
                    "ids": set().union(*(_id_variants(item) for item in _evidence_ids(evidence))),
                }
            )
    return result


def _match_id_sets(gold_ids: Iterable[str], hit_ids: set[str], aliases: Mapping[str, set[str]] | None = None) -> bool:
    hit = set(hit_ids)
    for gold in gold_ids:
        variants = _id_variants(gold)
        if aliases:
            variants.update(aliases.get(str(gold).casefold(), set()))
        if variants & hit:
            return True
    return False


def _retrieval_items(question: Mapping[str, Any], dataset_id: str) -> tuple[list[str], str]:
    # Platform ledgers usually expose document/page/quote IDs, not evidence
    # sentences.  MultiHop therefore uses Gold document IDs as its explicit
    # evidence unit unless a future ledger provides typed evidence IDs.
    docs = _gold_doc_ids(question)
    if docs:
        return docs, "document"
    return [], "unknown"


def _row_matches_gold_ids(
    hit: Any,
    gold_ids: Sequence[str],
    aliases: Mapping[str, set[str]] | None = None,
) -> bool:
    return _match_id_sets(gold_ids, _hit_ids(hit), aliases)


def _rank_values(
    question: Mapping[str, Any],
    hits: Sequence[Any],
    aliases: Mapping[str, set[str]],
    k: int,
) -> tuple[float, float, bool]:
    gold_ids, _ = _retrieval_items(question, "")
    if not gold_ids:
        return 0.0, 0.0, False
    matched: set[int] = set()
    first_rank: int | None = None
    for rank, hit in enumerate(_ordered_hits(hits)[:k], start=1):
        for index, gold_id in enumerate(gold_ids):
            if index in matched:
                continue
            if _row_matches_gold_ids(hit, [gold_id], aliases):
                matched.add(index)
                if first_rank is None:
                    first_rank = rank
    recall = len(matched) / len(gold_ids)
    mrr = 1.0 / first_rank if first_rank is not None else 0.0
    return recall, mrr, True


def _page_rank_values(question: Mapping[str, Any], hits: Sequence[Any], aliases: Mapping[str, set[str]], k: int) -> tuple[float, float, bool]:
    gold_items = _gold_locator_items(question)
    if not gold_items:
        return 0.0, 0.0, False
    ordered_hits = _ordered_hits(hits)
    hit_locators = [_locator_values(hit) for hit in ordered_hits[:k]]
    matched: set[int] = set()
    first_rank: int | None = None
    for rank, locators in enumerate(hit_locators, start=1):
        hit_ids = _hit_ids(ordered_hits[rank - 1])
        for index, item in enumerate(gold_items):
            if index in matched:
                continue
            direct = bool(item["ids"] & hit_ids)
            locator_match = any(
                (gold_file is None or hit_file is None or _id_variants(gold_file) & _id_variants(hit_file))
                and (gold_page is None or hit_page == gold_page)
                for gold_file, gold_page, _ in item["locators"]
                for hit_file, hit_page, _ in locators
            )
            if direct or locator_match:
                matched.add(index)
                if first_rank is None:
                    first_rank = rank
    return len(matched) / len(gold_items), (1.0 / first_rank if first_rank else 0.0), True


def _layout_available(question: Mapping[str, Any], hits: Sequence[Any]) -> bool:
    gold = [item for item in _gold_locator_items(question) if any(locator[2] is not None for locator in item["locators"])]
    hit_has_bbox = any(any(locator[2] is not None for locator in _locator_values(hit)) for hit in hits)
    return bool(gold) and (hit_has_bbox or not hits)


def _layout_rank_values(question: Mapping[str, Any], hits: Sequence[Any], k: int) -> tuple[float, bool]:
    gold_items = [item for item in _gold_locator_items(question) if any(locator[2] is not None for locator in item["locators"])]
    if not gold_items:
        return 0.0, False
    overlap_total = 0.0
    for item in gold_items:
        best_overlap = 0.0
        for hit in _ordered_hits(hits)[:k]:
            for gold_file, gold_page, gold_bbox in item["locators"]:
                if gold_bbox is None:
                    continue
                for hit_file, hit_page, hit_bbox in _locator_values(hit):
                    if hit_bbox is None:
                        continue
                    if gold_file and hit_file and not (_id_variants(gold_file) & _id_variants(hit_file)):
                        continue
                    if gold_page and hit_page and gold_page != hit_page:
                        continue
                    best_overlap = max(best_overlap, _bbox_gold_area_recall(gold_bbox, hit_bbox))
        overlap_total += best_overlap
    return overlap_total / len(gold_items), True


def _bbox_gold_area_recall(gold_bbox: tuple[float, ...], hit_bbox: tuple[float, ...]) -> float:
    """Return intersection area normalized by the Gold bbox area."""

    if len(gold_bbox) != 4 or len(hit_bbox) != 4:
        return 0.0
    gold_left, gold_top, gold_right, gold_bottom = gold_bbox
    hit_left, hit_top, hit_right, hit_bottom = hit_bbox
    gold_width = max(0.0, gold_right - gold_left)
    gold_height = max(0.0, gold_bottom - gold_top)
    gold_area = gold_width * gold_height
    if gold_area <= 0:
        return 0.0
    intersection_width = max(0.0, min(gold_right, hit_right) - max(gold_left, hit_left))
    intersection_height = max(0.0, min(gold_bottom, hit_bottom) - max(gold_top, hit_top))
    return min(1.0, (intersection_width * intersection_height) / gold_area)


def _typed_gold(question: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]] | None:
    evidence = _gold_evidence(question)
    if not evidence:
        return None
    output: dict[str, list[dict[str, Any]]] = {"text": [], "image": []}
    for item in evidence:
        modalities = _hit_modalities(item)
        if len(modalities) != 1:
            return None
        modality = next(iter(modalities))
        ids = _evidence_ids(item)
        if not ids:
            return None
        item_copy = dict(item)
        item_copy["_ids"] = ids
        output[modality].append(item_copy)
    if not output["text"] and not output["image"]:
        return None
    return output


def _typed_recall(question: Mapping[str, Any], hits: Sequence[Any], modality: str, k: int, aliases: Mapping[str, set[str]]) -> tuple[float, bool]:
    typed = _typed_gold(question)
    if typed is None or not typed.get(modality):
        return 0.0, False
    if hits and not any(_hit_modalities(hit) for hit in hits):
        return 0.0, False
    matched = 0
    ordered_hits = _ordered_hits(hits)
    for gold in typed[modality]:
        if any(
            modality in _hit_modalities(hit) and _row_matches_gold_ids(hit, gold["_ids"], aliases)
            for hit in ordered_hits[:k]
        ):
            matched += 1
    return matched / len(typed[modality]), True


def _latency_value(row: Mapping[str, Any], stage: str) -> float | None:
    if stage == "retrieval":
        keys = ("retrieval_latency_ms", "search_latency_ms", "retrieval_ms", "latency_ms", "duration_ms", "latency", "duration")
    elif stage == "e2e":
        keys = ("e2e_latency_ms", "end_to_end_latency_ms", "total_latency_ms", "latency_ms", "duration_ms", "latency", "duration")
    else:
        keys = ("generation_latency_ms", "qa_latency_ms", "generation_ms", "latency_ms", "duration_ms", "latency", "duration")
    for key in keys:
        value = row.get(key)
        if value is None:
            for nested_key in ("timings", "latencies", "metrics"):
                nested = _mapping(row.get(nested_key))
                if nested:
                    value = nested.get(key)
                    if value is not None:
                        break
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and float(value) >= 0:
            return float(value)
    latency_maps = [
        nested
        for key in ("latency", "timing", "timings", "latencies")
        if (nested := _mapping(row.get(key))) is not None
    ]
    mapping_keys = {
        "retrieval": ("retrieval", "retrieval_ms", "retrieval_latency_ms", "search"),
        "qa": ("qa", "generation", "generation_ms", "generation_latency_ms", "answer"),
        "e2e": ("e2e", "total", "total_ms", "e2e_ms", "end_to_end"),
    }.get(stage, ())
    for latency_map in latency_maps:
        for key in (*mapping_keys, "latency_ms", "duration_ms", "ms"):
            value = latency_map.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and float(value) >= 0:
                return float(value)
    if stage == "e2e":
        retrieval = row.get("retrieval_latency_ms")
        generation = row.get("generation_latency_ms")
        if (
            isinstance(retrieval, (int, float))
            and not isinstance(retrieval, bool)
            and isinstance(generation, (int, float))
            and not isinstance(generation, bool)
            and math.isfinite(float(retrieval))
            and math.isfinite(float(generation))
            and float(retrieval) >= 0
            and float(generation) >= 0
        ):
            return float(retrieval) + float(generation)
    return None


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, int(math.ceil(fraction * len(ordered))) - 1))
    return ordered[index]


def _latency_record(state: StageState, values: Sequence[float], fraction: float) -> dict[str, Any]:
    value = _percentile(values, fraction)
    if value is None:
        reason = "NO_LATENCY_OBSERVATIONS" if state.terminal_n else "NO_TERMINAL_OBSERVATIONS"
    else:
        reason = None
    return _metric_record(
        state,
        value,
        value,
        len(values) if values else None,
        eligible_n=len(values),
        missing_n=max(0, state.planned_n - len(values)),
        reason=reason,
        unit="milliseconds",
        aggregation="observed-terminal-latencies; nearest-rank-percentile",
    )


def _qa_metrics(state: StageState, dataset_id: str, aliases: Mapping[str, set[str]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if dataset_id == "fab-bench":
        # FAB's released native score is a six-dimensional judge.  Lexical
        # answer matching is not promoted to correctness for this subjective
        # benchmark; deterministic coverage is reported separately.
        for name in ("completeness", "technical_depth", "factuality", "relevance", "context_utilization", "support_quality", "overall", "correctness", "semantic_correctness"):
            metrics[name] = _unsupported_record(state)
    else:
        values_by_metric: dict[str, list[float]] = {"answer_non_empty": [], "contains_gold": [], "normalized_em": [], "token_f1": []}
        missing_gold = 0
        for key in state.units:
            row = state.rows.get(key)
            question = state.questions.get(key[0], {})
            if row is None:
                continue
            status = _status(row.get("status"))
            if status not in VALID_STATUSES:
                continue
            answer = _answer_from_row(row)
            if answer is None and status == "EMPTY":
                # EMPTY is a terminal, valid response.  A few ledgers omit
                # the redundant empty answer field, so preserve its zero in
                # lexical QA denominators without treating a missing SUCCESS
                # answer as an empty answer.
                answer = ""
            if answer is None:
                # A successful row without an answer field is not an empty
                # answer; it is an unavailable QA observation.
                continue
            values_by_metric["answer_non_empty"].append(float(bool(answer.strip())))
            gold = _gold_answer(question, row)
            if gold is None:
                missing_gold += 1
                continue
            normalized_answer = _normalize(answer)
            normalized_gold = _normalize(gold)
            values_by_metric["contains_gold"].append(float(bool(normalized_gold and normalized_gold in normalized_answer)))
            values_by_metric["normalized_em"].append(float(bool(normalized_gold and normalized_gold == normalized_answer)))
            token_value = _token_f1(answer, gold)
            if token_value is not None:
                values_by_metric["token_f1"].append(token_value)
        for name, values in values_by_metric.items():
            if name != "answer_non_empty" and missing_gold:
                metrics[name] = _metric_record(
                    state,
                    None,
                    sum(values),
                    state.planned_n or None,
                    eligible_n=len(values),
                    missing_n=missing_gold,
                    reason=UNSUPPORTED_GOLD_UNAVAILABLE,
                )
            else:
                metrics[name] = _rate_from_values(state, values, eligible_n=len(values), missing_n=max(0, state.planned_n - len(values)))
        keyword_values: list[float] = []
        keyword_missing = 0
        for key in state.units:
            row = state.rows.get(key)
            question = state.questions.get(key[0], {})
            if row is None or _status(row.get("status")) not in VALID_STATUSES:
                continue
            answer = _answer_from_row(row)
            keywords = _gold_keywords(question)
            if answer is None or not keywords:
                keyword_missing += 1
                continue
            normalized = _normalize(answer)
            keyword_values.append(sum(bool(_normalize(keyword) and _normalize(keyword) in normalized) for keyword in keywords) / len(keywords))
        metrics["reference_keyword_recall"] = _rate_from_values(
            state,
            keyword_values,
            eligible_n=len(keyword_values),
            missing_n=keyword_missing + max(0, state.planned_n - state.valid_n),
            reason_if_empty="UNSUPPORTED_KEYWORDS_UNAVAILABLE",
        )
        metrics["em"] = metrics["normalized_em"]
        metrics["exact_match"] = metrics["normalized_em"]
        metrics["answer_non_empty_rate"] = metrics["answer_non_empty"]
        metrics["answer_contains_gold_rate"] = metrics["contains_gold"]
        if dataset_id == "docbench":
            # This is deliberately labelled as a proxy: DocBench correctness
            # itself is judge-defined, while strict normalized EM is local and
            # deterministic.
            metrics["deterministic_correctness_proxy"] = metrics["normalized_em"]
            metrics["correctness_proxy"] = metrics["deterministic_correctness_proxy"]

    # These metrics require a frozen RAGAS/LLM judge or semantic scorer.  A
    # lexical overlap score is intentionally not substituted for them.
    for name in (
        "faithfulness",
        "answer_relevance",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "context_relevance",
        "ragas_faithfulness",
        "ragas_answer_relevance",
        "ragas_answer_relevancy",
        "ragas_context_precision",
        "ragas_context_recall",
        "ragas_context_relevance",
        "semantic_correctness",
        "semantic_similarity",
        "answer_similarity",
        "answer_correctness",
        "judge_answer_correctness",
        "judge_answer_relevance",
        "judge_faithfulness",
        "judge_completeness",
        "judge_overall_quality",
        "correctness",
        "completeness",
        "dataset_aggregate",
        "strict_unanswerable_success",
        "tdas",
    ):
        metrics.setdefault(name, _unsupported_record(state))
    qa_latency_values = [
        value
        for row in state.rows.values()
        if _status(row.get("status")) not in PENDING_STATUSES and (value := _latency_value(row, "qa")) is not None
    ]
    e2e_latency_values = [
        value
        for row in state.rows.values()
        if _status(row.get("status")) not in PENDING_STATUSES and (value := _latency_value(row, "e2e")) is not None
    ]
    metrics["latency_ms_p50"] = _latency_record(state, qa_latency_values, 0.50)
    metrics["latency_ms_p95"] = _latency_record(state, qa_latency_values, 0.95)
    metrics["generation_latency_ms_p50"] = metrics["latency_ms_p50"]
    metrics["generation_latency_ms_p95"] = metrics["latency_ms_p95"]
    metrics["e2e_latency_ms_p50"] = _latency_record(state, e2e_latency_values, 0.50)
    metrics["e2e_latency_ms_p95"] = _latency_record(state, e2e_latency_values, 0.95)
    metrics["generation_p50"] = metrics["latency_ms_p50"]
    metrics["generation_p95"] = metrics["latency_ms_p95"]
    metrics["e2e_p50"] = metrics["e2e_latency_ms_p50"]
    metrics["e2e_p95"] = metrics["e2e_latency_ms_p95"]
    return metrics


def _retrieval_metrics(state: StageState, package: PackageData, aliases: Mapping[str, set[str]]) -> dict[str, Any]:
    dataset_id = package.dataset_id
    metrics: dict[str, Any] = {}
    for k in TOP_K:
        values: list[float] = []
        hit_values: list[float] = []
        eligible = 0
        for key in state.units:
            row = state.rows.get(key)
            question = state.questions.get(key[0], {})
            if row is None:
                continue
            status = _status(row.get("status"))
            hits, trace = _extract_hits(row)
            if status in VALID_STATUSES and trace and hits is not None:
                recall, _, available = _rank_values(question, hits, aliases, k)
                if available:
                    values.append(recall)
                    hit_values.append(float(recall > 0.0))
                    eligible += 1
        record = _rate_from_values(state, values, eligible_n=eligible, missing_n=max(0, state.planned_n - eligible))
        hit_record = _rate_from_values(state, hit_values, eligible_n=eligible, missing_n=max(0, state.planned_n - eligible))
        metrics[f"recall_at_{k}"] = record
        metrics[f"r@{k}"] = record
        metrics[f"R@{k}"] = record
        metrics[f"source_recall_at_{k}"] = record
        metrics[f"source_recall@{k}"] = record
        metrics[f"source_r@{k}"] = record
        metrics[f"hit_at_{k}"] = hit_record
        metrics[f"hit@{k}"] = hit_record

    mrr_values: list[float] = []
    mrr_eligible = 0
    for key in state.units:
        row = state.rows.get(key)
        question = state.questions.get(key[0], {})
        if row is None:
            continue
        if _status(row.get("status")) not in VALID_STATUSES:
            continue
        hits, trace = _extract_hits(row)
        if not trace or hits is None:
            continue
        _, mrr, available = _rank_values(question, hits, aliases, 10)
        if available:
            mrr_values.append(mrr)
            mrr_eligible += 1
    metrics["mrr"] = _rate_from_values(state, mrr_values, eligible_n=mrr_eligible, missing_n=max(0, state.planned_n - mrr_eligible))

    if dataset_id in {"multihop-rag", "enterprise-rag-bench"}:
        for k in TOP_K:
            evidence_values: list[float] = []
            complete_values: list[float] = []
            eligible = 0
            for key in state.units:
                row = state.rows.get(key)
                question = state.questions.get(key[0], {})
                if row is None or _status(row.get("status")) not in VALID_STATUSES:
                    continue
                hits, trace = _extract_hits(row)
                if not trace or hits is None:
                    continue
                value, _, available = _rank_values(question, hits, aliases, k)
                if available:
                    evidence_values.append(value)
                    complete_values.append(float(value == 1.0))
                    eligible += 1
            metrics[f"evidence_recall_at_{k}"] = _rate_from_values(state, evidence_values, eligible_n=eligible, missing_n=max(0, state.planned_n - eligible))
            metrics[f"all_evidence_success_at_{k}"] = _rate_from_values(state, complete_values, eligible_n=eligible, missing_n=max(0, state.planned_n - eligible))
            metrics[f"complete_evidence_set_recall_at_{k}"] = metrics[f"all_evidence_success_at_{k}"]
            metrics[f"evidence_recall@{k}"] = metrics[f"evidence_recall_at_{k}"]
            metrics[f"all_evidence_success@{k}"] = metrics[f"all_evidence_success_at_{k}"]
            metrics[f"complete_evidence_set_recall@{k}"] = metrics[f"complete_evidence_set_recall_at_{k}"]
            if dataset_id == "enterprise-rag-bench":
                metrics[f"document_recall_at_{k}"] = metrics[f"recall_at_{k}"]
                metrics[f"document_recall@{k}"] = metrics[f"recall_at_{k}"]
                metrics[f"doc_recall_at_{k}"] = metrics[f"recall_at_{k}"]
                metrics[f"all_required_doc_success_at_{k}"] = metrics[f"all_evidence_success_at_{k}"]
                metrics[f"completeness_proxy_at_{k}"] = metrics[f"complete_evidence_set_recall_at_{k}"]
                metrics[f"completeness_proxy@{k}"] = metrics[f"complete_evidence_set_recall_at_{k}"]

    if dataset_id == "mmdocir":
        for k in TOP_K:
            page_values: list[float] = []
            page_mrr_values: list[float] = []
            page_eligible = 0
            layout_values: list[float] = []
            layout_eligible = 0
            for key in state.units:
                row = state.rows.get(key)
                question = state.questions.get(key[0], {})
                if row is None or _status(row.get("status")) not in VALID_STATUSES:
                    continue
                hits, trace = _extract_hits(row)
                if not trace or hits is None:
                    continue
                page_recall, page_mrr, page_available = _page_rank_values(question, hits, aliases, k)
                if page_available:
                    page_values.append(page_recall)
                    page_mrr_values.append(page_mrr)
                    page_eligible += 1
                if _layout_available(question, hits):
                    layout_recall, layout_available = _layout_rank_values(question, hits, k)
                    if layout_available:
                        layout_values.append(layout_recall)
                        layout_eligible += 1
            metrics[f"page_recall_at_{k}"] = _rate_from_values(state, page_values, eligible_n=page_eligible, missing_n=max(0, state.planned_n - page_eligible))
            metrics[f"page_r@{k}"] = metrics[f"page_recall_at_{k}"]
            metrics[f"page_recall@{k}"] = metrics[f"page_recall_at_{k}"]
            if k in {1, 5, 10}:
                metrics[f"layout_recall_at_{k}"] = _rate_from_values(state, layout_values, eligible_n=layout_eligible, missing_n=max(0, state.planned_n - layout_eligible), reason_if_empty="UNSUPPORTED_LAYOUT_LOCATORS_UNAVAILABLE")
                metrics[f"layout_recall@{k}"] = metrics[f"layout_recall_at_{k}"]
        # The first-relevant page rank is a separate metric, not the average of
        # page recall values.
        page_mrr_values: list[float] = []
        page_eligible = 0
        for key in state.units:
            row = state.rows.get(key)
            question = state.questions.get(key[0], {})
            if row is None or _status(row.get("status")) not in VALID_STATUSES:
                continue
            hits, trace = _extract_hits(row)
            if not trace or hits is None:
                continue
            _, value, available = _page_rank_values(question, hits, aliases, 10)
            if available:
                page_mrr_values.append(value)
                page_eligible += 1
        metrics["page_mrr"] = _rate_from_values(state, page_mrr_values, eligible_n=page_eligible, missing_n=max(0, state.planned_n - page_eligible), reason_if_empty="UNSUPPORTED_PAGE_LOCATORS_UNAVAILABLE")

    if dataset_id == "mmdocrag":
        for modality in ("text", "image"):
            for k in TOP_K:
                values: list[float] = []
                eligible = 0
                for key in state.units:
                    row = state.rows.get(key)
                    question = state.questions.get(key[0], {})
                    if row is None or _status(row.get("status")) not in VALID_STATUSES:
                        continue
                    hits, trace = _extract_hits(row)
                    if not trace or hits is None:
                        continue
                    value, available = _typed_recall(question, hits, modality, k, aliases)
                    if available:
                        values.append(value)
                        eligible += 1
                reason = "UNSUPPORTED_TYPED_EVIDENCE_UNAVAILABLE"
                metrics[f"{modality}_evidence_recall_at_{k}"] = _rate_from_values(state, values, eligible_n=eligible, missing_n=max(0, state.planned_n - eligible), reason_if_empty=reason)
                metrics[f"{modality}_quote_recall_at_{k}"] = metrics[f"{modality}_evidence_recall_at_{k}"]
                metrics[f"{modality}_evidence_recall@{k}"] = metrics[f"{modality}_evidence_recall_at_{k}"]
                metrics[f"{modality}_quote_recall@{k}"] = metrics[f"{modality}_quote_recall_at_{k}"]
        for k in TOP_K:
            values: list[float] = []
            eligible = 0
            for key in state.units:
                row = state.rows.get(key)
                question = state.questions.get(key[0], {})
                if row is None or _status(row.get("status")) not in VALID_STATUSES:
                    continue
                hits, trace = _extract_hits(row)
                typed = _typed_gold(question)
                if not trace or hits is None or typed is None:
                    continue
                total = sum(len(items) for items in typed.values())
                if not total:
                    continue
                per_modality = []
                available = True
                for modality in ("text", "image"):
                    value, ok = _typed_recall(question, hits, modality, k, aliases)
                    if typed[modality]:
                        if not ok:
                            available = False
                            break
                        per_modality.append(value * len(typed[modality]))
                if available:
                    values.append(sum(per_modality) / total)
                    eligible += 1
            metrics[f"overall_evidence_recall_at_{k}"] = _rate_from_values(state, values, eligible_n=eligible, missing_n=max(0, state.planned_n - eligible), reason_if_empty="UNSUPPORTED_TYPED_EVIDENCE_UNAVAILABLE")
            metrics[f"overall_evidence_recall@{k}"] = metrics[f"overall_evidence_recall_at_{k}"]

    latency_values = [
        value
        for row in state.rows.values()
        if _status(row.get("status")) not in PENDING_STATUSES and (value := _latency_value(row, "retrieval")) is not None
    ]
    metrics["latency_ms_p50"] = _latency_record(state, latency_values, 0.50)
    metrics["latency_ms_p95"] = _latency_record(state, latency_values, 0.95)
    metrics["retrieval_latency_ms_p50"] = metrics["latency_ms_p50"]
    metrics["retrieval_latency_ms_p95"] = metrics["latency_ms_p95"]
    metrics["retrieval_p50"] = metrics["latency_ms_p50"]
    metrics["retrieval_p95"] = metrics["latency_ms_p95"]
    return metrics


def _slice_state(state: StageState, label: str) -> StageState:
    units = [unit for unit in state.units if _question_type(state.questions.get(unit[0], {})) == label]
    unit_keys = set(units)
    rows = {key: row for key, row in state.rows.items() if key in unit_keys}
    counts: Counter[str] = Counter(_status(row.get("status")) for row in rows.values())
    terminal_n = sum(counts.get(value, 0) for value in counts if value not in PENDING_STATUSES)
    valid_n = sum(counts.get(value, 0) for value in VALID_STATUSES)
    failed_n = sum(counts.get(value, 0) for value in FAILED_STATUSES)
    unsupported_n = sum(counts.get(value, 0) for value in UNSUPPORTED_STATUSES)
    return StageState(
        name=state.name,
        units=units,
        rows=rows,
        questions=state.questions,
        planned_n=len(units),
        terminal_n=terminal_n,
        valid_n=valid_n,
        failed_n=failed_n,
        unsupported_n=unsupported_n,
        pending_n=max(0, len(units) - terminal_n),
        status_counts=dict(sorted(counts.items())),
    )


def _stage_result(stage: str, state: StageState, package: PackageData, aliases: Mapping[str, set[str]]) -> dict[str, Any]:
    metrics = _retrieval_metrics(state, package, aliases) if stage == "retrieval" else _qa_metrics(state, package.dataset_id, aliases)
    result: dict[str, Any] = {
        "stage": stage,
        "denominator": state.denominator,
        "status_counts": state.status_counts,
        "metrics": metrics,
        "slices": {},
    }
    labels = sorted(
        {
            _question_type(state.questions[question_id])
            for question_id, _ in state.units
            if question_id in state.questions
        }
    )
    for label in labels:
        subset = _slice_state(state, label)
        subset_metrics = _retrieval_metrics(subset, package, aliases) if stage == "retrieval" else _qa_metrics(subset, package.dataset_id, aliases)
        result["slices"][label] = {
            "denominator": subset.denominator,
            "status_counts": subset.status_counts,
            "metrics": subset_metrics,
        }
    if package.dataset_id == "docbench" and stage == "qa":
        # DocBench's native correctness requires a judge.  Keep that metric
        # null above, and expose strict lexical Gold matches only as an
        # explicitly named diagnostic proxy.
        result["metrics"]["deterministic_correctness_proxy"] = result["metrics"].get("normalized_em", _unsupported_record(state, UNSUPPORTED_GOLD_UNAVAILABLE))
        result["metrics"]["correctness_proxy"] = result["metrics"]["deterministic_correctness_proxy"]
        result["correctness_proxy_by_question_type"] = {
            label: {
                metric_name: result["slices"][label]["metrics"].get(metric_name)
                for metric_name in (
                    "normalized_em",
                    "contains_gold",
                    "token_f1",
                    "answer_non_empty",
                    "deterministic_correctness_proxy",
                )
            }
            for label in labels
        }
        result["type_correctness_proxy"] = result["correctness_proxy_by_question_type"]
    # A short values view is convenient for report/table adapters and does not
    # replace the auditable metric records above.
    result["values"] = {name: record.get("value") for name, record in metrics.items() if isinstance(record, Mapping) and "value" in record}
    return result


def _nested_find(mapping: Any, keys: Sequence[str]) -> Any:
    wanted = {key.casefold() for key in keys}
    for value in _iter_nested_mappings(mapping):
        for key, child in value.items():
            if str(key).casefold() in wanted:
                return child
    return None


def _coverage_metric(numerator: Any, denominator: Any, reason: str = "UNSUPPORTED_COVERAGE_UNAVAILABLE") -> dict[str, Any]:
    try:
        numerator_value = float(numerator)
        denominator_value = float(denominator)
    except (TypeError, ValueError):
        return {"value": None, "numerator": None, "denominator": None, "unit": "rate", "reason": reason}
    if denominator_value <= 0:
        return {"value": None, "numerator": _number(numerator_value), "denominator": _number(denominator_value), "unit": "rate", "reason": reason}
    return {"value": _number(numerator_value / denominator_value), "numerator": _number(numerator_value), "denominator": _number(denominator_value), "unit": "rate"}


def _coverage(package: PackageData) -> dict[str, Any]:
    if package.dataset_id != "fab-bench":
        return {}
    sources = _nested_find(package.manifest, ("source_status_counts",))
    if not isinstance(sources, Mapping):
        sources = _nested_find(package.condition_manifest, ("source_status_counts",))
    source_acquired = 0
    source_total = 0
    if isinstance(sources, Mapping):
        source_acquired = int(sources.get("source_acquired", sources.get("source", 0)) or 0)
        declared_total = _first(sources, "source_total", "sources_total", "total", default=None)
        if isinstance(declared_total, (int, float)):
            source_total = int(declared_total)
        else:
            source_total = sum(int(value or 0) for value in sources.values() if isinstance(value, (int, float)))
    image = _nested_find(package.manifest, ("gold_image_coverage",))
    if not isinstance(image, Mapping):
        image = _nested_find(package.condition_manifest, ("gold_image_coverage",))
    if not isinstance(image, Mapping):
        image = {}
    result = {
        "source_document_coverage": _coverage_metric(source_acquired, source_total),
        "gold_image_evidence": _coverage_metric(image.get("available", image.get("gold_image_evidence_available")), image.get("required", image.get("gold_image_evidence"))),
        "source_complete": _boolish(
            _first(
                package.manifest,
                "source_complete",
                default=_first(package.condition_manifest, "source_complete", default=False),
            )
        ),
        "denominator_policy": "current_local_frozen",
    }
    return result


def _readiness(run_root: Path, package: PackageData) -> dict[str, Any]:
    resource_paths = sorted(run_root.glob("**/resource-map.json"))
    if not resource_paths:
        return {"status": None, "reason": "UNSUPPORTED_READINESS_LEDGER_UNAVAILABLE", "planned_n": len(package.corpus)}
    payload = _json_load(resource_paths[0])
    resources = payload.get("resources", {}) if isinstance(payload, Mapping) else {}
    statuses: Counter[str] = Counter()
    document_count = 0
    for resource in resources.values() if isinstance(resources, Mapping) else []:
        if not isinstance(resource, Mapping):
            continue
        documents = resource.get("documents", {})
        if isinstance(documents, Mapping):
            for document in documents.values():
                if isinstance(document, Mapping):
                    document_count += 1
                    statuses[str(document.get("status", "unknown")).casefold()] += 1
        else:
            statuses[str(resource.get("status", "unknown")).casefold()] += 1
    ready = sum(statuses.get(value, 0) for value in ("ready", "indexed", "completed", "available"))
    return {
        "status": "READY" if document_count and ready == document_count else "PARTIAL",
        "planned_n": len(package.corpus),
        "observed_n": document_count,
        "ready_n": ready,
        "ready_rate": _coverage_metric(ready, document_count or len(package.corpus)),
        "status_counts": dict(sorted(statuses.items())),
    }


def aggregate_run(run: str | Path, package: str | Path) -> dict[str, Any]:
    """Aggregate one local run against one local frozen package manifest."""

    run_root, run_manifest, run_manifest_path = _load_run_manifest(run)
    package_data = _load_package(package, run_manifest)
    base_result: dict[str, Any] = {
        "schema": "competitor-eval-metrics-v1",
        "status": "COMPLETE",
        "run": {
            "root": str(run_root),
            "manifest_path": str(run_manifest_path) if run_manifest_path else None,
            "run_id": _first(run_manifest, "run_id", "id", default=run_root.name),
        },
        "package": {"root": str(package_data.root), "manifest_path": str(package_data.manifest_path) if package_data.manifest_path else None},
        "dataset": {
            "dataset_id": package_data.dataset_id,
            "dataset_name": package_data.dataset_name,
            "revision": package_data.revision,
            "split": package_data.split,
            "protocol_tag": package_data.protocol_tag,
            "condition": package_data.condition,
        },
        "denominator_policy": "current_local_frozen",
        "excluded_datasets": sorted(EXCLUDED_DATASETS),
    }
    if package_data.dataset_id in EXCLUDED_DATASETS:
        base_result.update({"status": "EXCLUDED", "reason": "EXCLUDED_DATASET", "metrics": {}, "coverage": {}})
        return base_result

    initial, terminal_rows = _load_ledgers(run_root)
    # Initial rows carry the complete planned question set even when a run
    # stops before producing terminal observations.  They are used only to
    # preserve the frozen denominator/question slices; metrics still consume
    # terminal rows below.
    questions = _question_map(package_data, [*terminal_rows, *initial])
    aliases = _metadata_identifier_aliases(package_data)
    retrieval_state = _build_stage("retrieval", package_data, run_manifest, initial, terminal_rows, questions)
    qa_state = _build_stage("qa", package_data, run_manifest, initial, terminal_rows, questions)
    base_result["retrieval"] = _stage_result("retrieval", retrieval_state, package_data, aliases)
    base_result["qa"] = _stage_result("qa", qa_state, package_data, aliases)
    base_result["readiness"] = _readiness(run_root, package_data)
    base_result["coverage"] = _coverage(package_data)
    base_result["ledger"] = {
        "initial_n": len(initial),
        "terminal_n": len(terminal_rows),
        "terminal_paths": [str(path) for path in _ledger_paths(run_root)],
    }
    if retrieval_state.pending_n or qa_state.pending_n:
        base_result["status"] = "PARTIAL"
    base_result["metrics"] = {
        "retrieval": base_result["retrieval"]["values"],
        "qa": base_result["qa"]["values"],
    }
    return base_result


def aggregate(run: str | Path, package: str | Path) -> dict[str, Any]:
    """Compatibility alias for callers that mirror the CLI subcommand name."""

    return aggregate_run(run, package)


def _markdown_value(result: Mapping[str, Any], stage: str, name: str) -> str:
    record = _mapping(_mapping(result.get(stage)).get("metrics", {}).get(name)) if isinstance(result.get(stage), Mapping) else None
    value = record.get("value") if record else None
    return "—" if value is None else str(value)


def _markdown_cell(value: Any, limit: int = 160) -> str:
    text = str(value if value is not None else "")
    text = text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def todo_markdown(result_or_run: Mapping[str, Any] | str | Path, package: str | Path | None = None) -> str:
    """Return a bounded replacement-safe Markdown result block.

    The function only returns text.  It never opens or edits ``TODO.md``.
    """

    result = aggregate_run(result_or_run, package) if package is not None else dict(result_or_run)  # type: ignore[arg-type]
    dataset = _mapping(result.get("dataset")) or {}
    retrieval = _mapping(result.get("retrieval")) or {}
    qa = _mapping(result.get("qa")) or {}
    retrieval_denominator = _mapping(retrieval.get("denominator")) or {}
    qa_denominator = _mapping(qa.get("denominator")) or {}
    lines = [
        "<!-- COMPETITOR_EVAL_METRICS_START -->",
        "| Dataset | Condition | Planned R/QA | R@1 | R@3 | R@5 | R@10 | MRR | EM | Token F1 | Contains gold | Nonempty | R p50/p95 ms | QA p50/p95 ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| "
        + " | ".join(
            (
                _markdown_cell(dataset.get("dataset_name", dataset.get("dataset_id", "unknown"))),
                _markdown_cell(dataset.get("condition", "")),
                f"{retrieval_denominator.get('planned_n', '—')}/{qa_denominator.get('planned_n', '—')}",
                _markdown_value(result, "retrieval", "recall_at_1"),
                _markdown_value(result, "retrieval", "recall_at_3"),
                _markdown_value(result, "retrieval", "recall_at_5"),
                _markdown_value(result, "retrieval", "recall_at_10"),
                _markdown_value(result, "retrieval", "mrr"),
                _markdown_value(result, "qa", "normalized_em"),
                _markdown_value(result, "qa", "token_f1"),
                _markdown_value(result, "qa", "contains_gold"),
                _markdown_value(result, "qa", "answer_non_empty"),
                f"{_markdown_value(result, 'retrieval', 'latency_ms_p50')}/{_markdown_value(result, 'retrieval', 'latency_ms_p95')}",
                f"{_markdown_value(result, 'qa', 'latency_ms_p50')}/{_markdown_value(result, 'qa', 'latency_ms_p95')}",
            )
        )
        + " |",
        "",
        f"Denominator policy: `current_local_frozen`; retrieval valid/failed/pending = `{retrieval_denominator.get('valid_n', '—')}/{retrieval_denominator.get('failed_n', '—')}/{retrieval_denominator.get('pending_n', '—')}`, QA = `{qa_denominator.get('valid_n', '—')}/{qa_denominator.get('failed_n', '—')}/{qa_denominator.get('pending_n', '—')}`.",
        "Judge/semantic metrics remain `null` with `UNSUPPORTED_NEEDS_JUDGE`; this block contains deterministic ledger metrics only.",
        "<!-- COMPETITOR_EVAL_METRICS_END -->",
    ]
    return "\n".join(lines) + "\n"


def _write_text(path: str | Path, text: str) -> None:
    target = Path(path).expanduser().resolve()
    if target.name.casefold() == "todo.md":
        raise MetricsError("TODO_WRITE_FORBIDDEN")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    aggregate_parser = subparsers.add_parser("aggregate", help="aggregate a local run directory")
    aggregate_parser.add_argument("--run", required=True, type=Path)
    aggregate_parser.add_argument("--package", required=True, type=Path)
    aggregate_parser.add_argument("--output", required=True, type=Path)
    markdown_parser = subparsers.add_parser("todo-markdown", help="emit a bounded TODO result block")
    markdown_parser.add_argument("--run", required=True, type=Path)
    markdown_parser.add_argument("--package", required=True, type=Path)
    markdown_parser.add_argument("--output", type=Path, help="write the block here; stdout when omitted")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "aggregate":
            result = aggregate_run(args.run, args.package)
            _write_text(args.output, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            return 0
        block = todo_markdown(args.run, args.package)
        if args.output:
            _write_text(args.output, block)
        else:
            sys.stdout.write(block)
        return 0
    except MetricsError as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
