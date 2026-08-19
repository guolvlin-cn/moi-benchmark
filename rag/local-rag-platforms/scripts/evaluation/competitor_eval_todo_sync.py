#!/usr/bin/env python3
"""Render auditable Markdown fragments from a local competitor campaign.

The campaign checkpoint is the source of unit selection.  A row is emitted
only when the checkpoint says that the unit completed, its result is SUCCESS,
the selected runner summary is SUCCESS, and both retrieval and QA have a full
terminal denominator.  The renderer is intentionally read-only with respect
to ``TODO.md``: the CLI prints by default and ``--output`` writes only the
explicitly named non-TODO file.

This module is standard-library-only so it can be used from the repository
root or directly as ``python3 local-rag-platforms/scripts/evaluation/competitor_eval_todo_sync.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


START_MARKER = "<!-- COMPETITOR_EVAL_TODO_SYNC_START -->"
END_MARKER = "<!-- COMPETITOR_EVAL_TODO_SYNC_END -->"

_SUCCESS_STATUSES = frozenset({"SUCCESS", "OK", "COMPLETE", "COMPLETED"})
_VALID_TERMINAL_STATUSES = frozenset({"SUCCESS", "OK", "COMPLETE", "COMPLETED", "EMPTY"})
_UNSUPPORTED_STATUSES = frozenset({"UNSUPPORTED", "NOT_SUPPORTED"})
_PENDING_STATUSES = frozenset({"PLANNED", "NOT_STARTED", "PENDING", "RUNNING", "IN_PROGRESS"})
_FAILED_STATUSES = frozenset(
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
_METRIC_FILENAMES = (
    "metrics.json",
    "aggregate-metrics.json",
    "aggregate.json",
    "retrieval-metrics.json",
    "qa-metrics.json",
)
_DATASET_LABELS = {
    "wikieval": "WikiEval",
    "mmdocir": "MMDocIR",
    "mmdocrag": "MMDocRAG",
    "docbench": "DocBench",
    "multihop-rag": "MultiHop-RAG",
    "enterprise-rag-bench": "EnterpriseRAG-Bench",
    "fab-bench": "FAB-Bench",
}


class SyncError(RuntimeError):
    """Raised when the checkpoint or an explicitly requested output is invalid."""


@dataclass(frozen=True)
class StageSnapshot:
    """The denominator and reportable values for one runner stage."""

    name: str
    metrics: Mapping[str, Any]
    planned: int | None
    valid: int | None
    failed: int | None
    unsupported: int | None
    terminal: int | None
    observed_rows: int
    status: str | None

    @property
    def full(self) -> bool:
        """Whether the stage has a complete initial denominator."""

        if self.planned is None or self.planned <= 0:
            return False
        if self.terminal is None or self.terminal < self.planned:
            return False
        if self.observed_rows < self.planned:
            return False
        if self.status and _normal(self.status) not in (_SUCCESS_STATUSES | _UNSUPPORTED_STATUSES):
            return False
        return True


@dataclass(frozen=True)
class UnitReport:
    ordinal: int
    dataset: str
    condition: str
    platform: str
    status: str
    run_id: str
    summary_path: Path
    metrics_paths: tuple[Path, ...]
    terminal_path: Path
    start_record_path: Path | None
    retrieval: StageSnapshot
    qa: StageSnapshot
    public_retrieval_contract: str
    provider_model: str
    tags: tuple[str, ...]
    diagnostic_retrieval: str


def _normal(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def _stage(value: Any) -> str | None:
    return _STAGE_ALIASES.get(str(value or "").strip().casefold().replace("-", "_"))


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError as exc:
        raise SyncError(f"FILE_MISSING:{path}") from exc
    except json.JSONDecodeError as exc:
        raise SyncError(f"JSON_INVALID:{path}") from exc


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError as exc:
        raise SyncError(f"FILE_MISSING:{path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SyncError(f"JSONL_INVALID:{path}:{line_number}") from exc
        if isinstance(value, Mapping):
            rows.append(dict(value))
    return rows


def _first(mapping: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    if mapping is None:
        return default
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _metric_value(value: Any) -> Any:
    """Unwrap metric-record values without treating a missing value as zero."""

    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")
    return value


def _metric_number(mapping: Mapping[str, Any], *keys: str) -> float | int | None:
    value: Any = None
    found = False
    for key in keys:
        if key in mapping:
            value = _metric_value(mapping[key])
            found = True
            break
    if not found or value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else None


def _nested_mapping(mapping: Mapping[str, Any], *keys: str) -> Mapping[str, Any] | None:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return _mapping(value)


def _resolve_reference(value: Any, checkpoint_path: Path, checkpoint: Mapping[str, Any]) -> Path | None:
    if value in (None, ""):
        return None
    candidate = Path(str(value)).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    roots: list[Path] = [checkpoint_path.parent]
    repo_root = checkpoint.get("repo_root")
    if repo_root not in (None, ""):
        roots.insert(0, Path(str(repo_root)).expanduser())
    roots.append(Path.cwd())
    for root in roots:
        resolved = (root / candidate).resolve()
        if resolved.exists():
            return resolved
    return (roots[0] / candidate).resolve()


def _run_ids(unit: Mapping[str, Any]) -> list[str]:
    result = _mapping(unit.get("result")) or {}
    values = [result.get("run_id"), unit.get("run_id"), unit.get("base_run_id")]
    result_ids: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result_ids:
            result_ids.append(text)
    return result_ids


def _candidate_run_roots(checkpoint_path: Path, checkpoint: Mapping[str, Any], unit: Mapping[str, Any]) -> list[Path]:
    """Resolve attempt-aware runner roots, preferring result.run_id."""

    ids = _run_ids(unit)
    output_roots: list[Path] = []
    explicit_roots: list[Path] = []
    for field in ("runner_output_root", "output_root"):
        resolved = _resolve_reference(unit.get(field), checkpoint_path, checkpoint)
        if resolved is not None and resolved not in output_roots:
            output_roots.append(resolved)
    for field in ("artifact_root", "runner_artifact_root", "run_root"):
        resolved = _resolve_reference(unit.get(field), checkpoint_path, checkpoint)
        if resolved is not None and resolved not in explicit_roots:
            explicit_roots.append(resolved)

    candidates: list[Path] = []

    def add(path: Path) -> None:
        if path not in candidates:
            candidates.append(path)

    for output_root in output_roots:
        for run_id in ids:
            add(output_root / run_id)
    for root in explicit_roots:
        if root.name in ids:
            add(root)
    for root in explicit_roots:
        for run_id in ids:
            add(root / run_id)
    for root in explicit_roots:
        add(root)
    for output_root in output_roots:
        if output_root.is_dir():
            for child in sorted(output_root.iterdir()):
                if child.is_dir() and (not ids or any(child.name.startswith(run_id) for run_id in ids)):
                    add(child)
    return candidates


def _summary_matches(summary: Mapping[str, Any], unit: Mapping[str, Any]) -> bool:
    summary_run_id = str(summary.get("run_id") or "").strip()
    result = _mapping(unit.get("result")) or {}
    result_run_id = str(result.get("run_id") or "").strip()
    if result_run_id and summary_run_id:
        return summary_run_id == result_run_id
    expected = _run_ids(unit)
    return not summary_run_id or not expected or summary_run_id in expected


def _find_summary(checkpoint_path: Path, checkpoint: Mapping[str, Any], unit: Mapping[str, Any]) -> tuple[Path, Path] | None:
    for root in _candidate_run_roots(checkpoint_path, checkpoint, unit):
        summary_path = root if root.name == "summary.json" else root / "summary.json"
        if not summary_path.is_file():
            continue
        summary = _mapping(_load_json(summary_path))
        if summary is not None and _summary_matches(summary, unit):
            return summary_path, summary_path.parent
    return None


def _find_terminal_ledger(run_root: Path) -> Path | None:
    direct = run_root / "terminal-ledger.jsonl"
    if direct.is_file():
        return direct
    candidates = sorted(run_root.glob("**/terminal-ledger.jsonl")) if run_root.is_dir() else []
    return candidates[0] if candidates else None


def _metric_paths(run_root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for filename in _METRIC_FILENAMES:
        direct = run_root / filename
        if direct.is_file() and direct not in paths:
            paths.append(direct)
    return tuple(paths)


def _stage_payload(payload: Mapping[str, Any], stage: str) -> Mapping[str, Any] | None:
    direct = payload.get(stage)
    if isinstance(direct, Mapping):
        metrics = direct.get("metrics")
        if isinstance(metrics, Mapping):
            return metrics
        values = direct.get("values")
        if isinstance(values, Mapping):
            return values
        return direct
    nested = payload.get("metrics")
    if isinstance(nested, Mapping):
        direct = nested.get(stage)
        if isinstance(direct, Mapping):
            metrics = direct.get("metrics")
            if isinstance(metrics, Mapping):
                return metrics
            values = direct.get("values")
            if isinstance(values, Mapping):
                return values
            return direct
    declared_stage = _stage(payload.get("stage"))
    if declared_stage == stage:
        return payload
    return None


def _load_stage_metrics(summary: Mapping[str, Any], metric_paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {"retrieval": {}, "qa": {}}
    for stage in merged:
        summary_stage = _stage_payload(summary, stage)
        if summary_stage is not None:
            merged[stage].update(summary_stage)
    for path in metric_paths:
        payload = _mapping(_load_json(path))
        if payload is None:
            continue
        for stage in merged:
            stage_metrics = _stage_payload(payload, stage)
            if stage_metrics is not None:
                merged[stage].update(stage_metrics)
    return merged


def _row_key(row: Mapping[str, Any], index: int) -> tuple[str, str]:
    question_id = str(row.get("question_id") or row.get("attempt_id") or f"row-{index}")
    repeat_id = str(row.get("repeat_id") or "1")
    return question_id, repeat_id


def _stage_rows(rows: Iterable[Mapping[str, Any]], stage: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        if _stage(row.get("stage")) != stage:
            continue
        key = _row_key(row, index)
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(row))
    return selected


def _fallback_counts(rows: Sequence[Mapping[str, Any]]) -> tuple[int, int, int, int, int]:
    valid = failed = unsupported = terminal = 0
    for row in rows:
        status = _normal(row.get("status"))
        if status in _VALID_TERMINAL_STATUSES:
            valid += 1
            terminal += 1
        elif status in _UNSUPPORTED_STATUSES:
            unsupported += 1
            terminal += 1
        elif status in _PENDING_STATUSES:
            continue
        else:
            failed += 1
            terminal += 1
    return len(rows), valid, failed, unsupported, terminal


def _stage_snapshot(
    name: str,
    metrics: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    summary_stage: Mapping[str, Any] | None,
    planned_fallback: int | None,
) -> StageSnapshot:
    fallback_planned, fallback_valid, fallback_failed, fallback_unsupported, fallback_terminal = _fallback_counts(rows)
    planned = _integer(_metric_number(metrics, "planned_n", "planned", "initial_n"))
    if planned is None:
        planned = planned_fallback or (fallback_planned or None)
    valid = _integer(_metric_number(metrics, "valid_n", "eligible_n"))
    failed = _integer(_metric_number(metrics, "failed_n", "error_n"))
    unsupported = _integer(_metric_number(metrics, "unsupported_n", "not_supported_n"))
    terminal = _integer(_metric_number(metrics, "terminal_n", "observed_n"))
    valid = fallback_valid if valid is None else valid
    failed = fallback_failed if failed is None else failed
    unsupported = fallback_unsupported if unsupported is None else unsupported
    terminal = fallback_terminal if terminal is None else terminal
    status_values = []
    if summary_stage is not None and summary_stage.get("status") is not None:
        status_values.append(str(summary_stage.get("status")))
    if metrics.get("status") is not None:
        status_values.append(str(metrics.get("status")))
    status = next(
        (value for value in status_values if _normal(value) not in _SUCCESS_STATUSES),
        status_values[0] if status_values else None,
    )
    return StageSnapshot(name, metrics, planned, valid, failed, unsupported, terminal, len(rows), status)


def _metric_first(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping:
            return _metric_value(mapping[key])
    return None


def _recall(metrics: Mapping[str, Any], k: int) -> Any:
    return _metric_first(
        metrics,
        (
            f"recall_at_{k}",
            f"evidence_recall_at_{k}",
            f"source_recall_at_{k}",
            f"page_recall_at_{k}",
            f"text_evidence_recall_at_{k}",
            f"image_evidence_recall_at_{k}",
            f"recall@{k}",
            f"R@{k}",
        ),
    )


def _mrr(metrics: Mapping[str, Any]) -> Any:
    return _metric_first(metrics, ("mrr", "page_mrr", "source_mrr", "evidence_mrr"))


def _latency(metrics: Mapping[str, Any], percentile: int, stage: str) -> Any:
    suffix = str(percentile)
    keys = [f"latency_ms_p{suffix}"]
    if stage == "qa":
        keys.extend((f"generation_latency_ms_p{suffix}", f"generation_p{suffix}", f"qa_latency_ms_p{suffix}"))
    else:
        keys.extend((f"retrieval_latency_ms_p{suffix}", f"retrieval_p{suffix}", f"search_latency_ms_p{suffix}"))
    keys.append(f"p{suffix}")
    return _metric_first(metrics, keys)


def _qa_metric(metrics: Mapping[str, Any], keys: Iterable[str]) -> Any:
    return _metric_first(metrics, keys)


def _status_contract(metrics: Mapping[str, Any]) -> str:
    value = metrics.get("public_retrieval_contract")
    return str(value) if value not in (None, "") else "public_direct_retrieval"


def _is_diagnostic_retrieval(platform: str, contract: str, rows: Sequence[Mapping[str, Any]]) -> bool:
    if "DIAGNOSTIC_ADMIN" in _normal(contract) or "ADMIN_DIAGNOSTIC" in _normal(contract):
        return True
    if _normal(platform).startswith("MAXKB"):
        return any("diagnostic_hits" in row or "diagnostic" in row for row in rows)
    return False


def _diagnostic_text(metrics: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], diagnostic: bool) -> str:
    if not diagnostic:
        return "—"
    diagnostic_rows = [row for row in rows if "diagnostic_hits" in row or "diagnostic" in row]
    hit_count = 0
    for row in diagnostic_rows:
        hits = row.get("diagnostic_hits")
        if isinstance(hits, Sequence) and not isinstance(hits, (str, bytes)):
            hit_count += len(hits)
        elif hits not in (None, ""):
            hit_count += 1
    diagnostic_recall = _metric_first(metrics, ("diagnostic_recall_at_1", "diagnostic_recall", "admin_recall_at_1"))
    diagnostic_mrr = _metric_first(metrics, ("diagnostic_mrr", "admin_mrr"))
    score_text = ""
    if diagnostic_recall is not None or diagnostic_mrr is not None:
        score_text = f"; diagnostic Recall/MRR={_format(diagnostic_recall)}/{_format(diagnostic_mrr)}"
    p50 = _latency(metrics, 50, "retrieval")
    p95 = _latency(metrics, 95, "retrieval")
    return f"admin diagnostic only; diagnostic rows={len(diagnostic_rows)}; hits={hit_count}; p50/p95={_format(p50)}/{_format(p95)}{score_text}"


def _clean_model(value: Any) -> str | None:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None
    text = str(value).strip()
    if not text or any(marker in text.casefold() for marker in ("api_key", "secret", "password", "token=")):
        return None
    return text


def _model_from_sources(sources: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> str | None:
    for source in sources:
        for key in keys:
            value = _clean_model(source.get(key))
            if value:
                return value
    return None


def _provider_model(
    summary: Mapping[str, Any],
    metrics: Mapping[str, Any],
    start_record: Mapping[str, Any] | None,
    checkpoint: Mapping[str, Any],
) -> str:
    sources: list[Mapping[str, Any]] = []
    for root in (start_record, summary, metrics):
        if not isinstance(root, Mapping):
            continue
        for child_key in ("provider", "pipeline", "models", "model", "provider_selection"):
            child = root.get(child_key)
            if isinstance(child, Mapping):
                sources.append(child)
        sources.append(root)
    llm = _model_from_sources(sources, ("llm", "text_model", "chat_model", "completion_model", "generator", "model"))
    embedding = _model_from_sources(sources, ("embedding", "embedding_model", "index_model", "vector_model"))
    image = _model_from_sources(sources, ("image_llm", "multimodal_model", "vision_model", "image_model"))
    if not llm and not embedding and not image:
        policy = _mapping(checkpoint.get("policy")) or {}
        provider = _clean_model(policy.get("provider")) or "UNKNOWN"
        return f"Provider={provider}; LLM=UNKNOWN; Embedding=UNKNOWN"
    parts = [f"LLM={llm or 'UNKNOWN'}", f"Embedding={embedding or 'UNKNOWN'}"]
    if image:
        parts.append(f"VLM={image}")
    return "; ".join(parts)


def _needs_judge(qa_metrics: Mapping[str, Any], qa_rows: Sequence[Mapping[str, Any]], start_record: Mapping[str, Any] | None) -> bool:
    tdas_present = False
    if "tdas" in qa_metrics:
        tdas = _metric_value(qa_metrics.get("tdas"))
        if isinstance(tdas, Mapping):
            tdas_present = _normal(tdas.get("status")) in _SUCCESS_STATUSES and tdas.get("value") is not None
        else:
            tdas_present = tdas is not None
    for key in ("tdas_score", "judge_overall_quality", "judge_answer_correctness", "answer_correctness"):
        if _metric_first(qa_metrics, (key,)) is not None:
            tdas_present = True
    reasons = [str(qa_metrics.get("tdas_reason") or "")]
    for value in qa_metrics.values():
        if isinstance(value, Mapping):
            reasons.append(str(value.get("reason") or ""))
    reasons.extend(
        str((_mapping(row.get("tdas")) or {}).get("reason") or "")
        for row in qa_rows
        if row.get("tdas") is not None
    )
    if any("JUDGE" in reason.upper() or "TDAS" in reason.upper() for reason in reasons):
        return True
    if start_record:
        pipeline = _mapping(start_record.get("pipeline")) or {}
        judge = str(pipeline.get("judge") or "").strip().casefold()
        if judge in {"", "n/a", "na", "unknown"}:
            return True
    return not tdas_present


def _summary_stage(summary: Mapping[str, Any], stage: str) -> Mapping[str, Any] | None:
    value = summary.get(stage)
    return _mapping(value)


def _is_completed_unit(unit: Mapping[str, Any]) -> bool:
    result = _mapping(unit.get("result")) or {}
    status = _normal(unit.get("status"))
    result_status = _normal(result.get("status"))
    return status == "COMPLETED" and result_status == "SUCCESS" and _integer(result.get("returncode", 0)) in {0, None}


def _read_unit_report(checkpoint_path: Path, checkpoint: Mapping[str, Any], unit: Mapping[str, Any]) -> UnitReport | None:
    if not _is_completed_unit(unit):
        return None
    found = _find_summary(checkpoint_path, checkpoint, unit)
    if found is None:
        return None
    summary_path, run_root = found
    summary = _mapping(_load_json(summary_path))
    if summary is None or _normal(summary.get("status")) != "SUCCESS":
        return None
    terminal_path = _find_terminal_ledger(run_root)
    if terminal_path is None:
        return None
    rows = _load_jsonl(terminal_path)
    metric_paths = _metric_paths(run_root)
    stage_metrics = _load_stage_metrics(summary, metric_paths)
    retrieval_rows = _stage_rows(rows, "retrieval")
    qa_rows = _stage_rows(rows, "qa")
    start_record_path = run_root / "start-record.json"
    start_record = _mapping(_load_json(start_record_path)) if start_record_path.is_file() else None
    planned_fallback = _integer(_nested_mapping(start_record or {}, "planned", "initial_attempts")) if start_record else None
    retrieval = _stage_snapshot("retrieval", stage_metrics["retrieval"], retrieval_rows, _summary_stage(summary, "retrieval"), planned_fallback)
    qa = _stage_snapshot("qa", stage_metrics["qa"], qa_rows, _summary_stage(summary, "qa"), planned_fallback)
    if not retrieval.full or not qa.full:
        return None

    platform = str(unit.get("platform") or unit.get("system") or summary.get("system_id") or "unknown")
    contract = _status_contract(stage_metrics["retrieval"])
    diagnostic = _is_diagnostic_retrieval(platform, contract, retrieval_rows)
    tags: list[str] = []
    if diagnostic:
        tags.append("MAXKB_DIAGNOSTIC_ONLY")
    if _needs_judge(stage_metrics["qa"], qa_rows, start_record):
        tags.append("NEEDS_JUDGE")
    result = _mapping(unit.get("result")) or {}
    run_id = str(result.get("run_id") or summary.get("run_id") or unit.get("run_id") or run_root.name)
    return UnitReport(
        ordinal=_integer(unit.get("ordinal")) or 0,
        dataset=str(unit.get("dataset") or summary.get("dataset") or "unknown"),
        condition=str(unit.get("condition") or summary.get("condition") or "native"),
        platform=platform,
        status="SUCCESS",
        run_id=run_id,
        summary_path=summary_path,
        metrics_paths=metric_paths,
        terminal_path=terminal_path,
        start_record_path=start_record_path if start_record_path.is_file() else None,
        retrieval=retrieval,
        qa=qa,
        public_retrieval_contract=contract if not diagnostic else f"UNSUPPORTED:{contract.split(':', 1)[1] if ':' in contract else 'diagnostic_admin_contract'}",
        provider_model=_provider_model(summary, stage_metrics["qa"], start_record, checkpoint),
        tags=tuple(tags),
        diagnostic_retrieval=_diagnostic_text(stage_metrics["retrieval"], retrieval_rows, diagnostic),
    )


def _format(value: Any) -> str:
    value = _metric_value(value)
    if value is None:
        return "—"
    return str(value)


def _quad(stage: StageSnapshot) -> str:
    return "/".join(_format(value) for value in (stage.planned, stage.valid, stage.failed, stage.unsupported))


def _cell(value: Any, limit: int = 2000) -> str:
    text = str(value if value is not None else "")
    text = text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _dataset_label(value: str) -> str:
    normalized = value.strip().casefold().replace("_", "-")
    return _DATASET_LABELS.get(normalized, value)


def _artifact_text(report: UnitReport) -> str:
    values = [f"summary: `{report.summary_path}`"]
    if report.metrics_paths:
        values.append("metrics: " + ", ".join(f"`{path}`" for path in report.metrics_paths))
    else:
        values.append("metrics: inline summary")
    values.append(f"terminal: `{report.terminal_path}`")
    if report.start_record_path is not None:
        values.append(f"provider: `{report.start_record_path}`")
    return "<br>".join(values)


def _row(report: UnitReport) -> str:
    public_recall = "UNSUPPORTED" if "MAXKB_DIAGNOSTIC_ONLY" in report.tags else None
    recall_values = [public_recall or _recall(report.retrieval.metrics, k) for k in (1, 3, 5, 10)]
    public_mrr = public_recall or _mrr(report.retrieval.metrics)
    em = _qa_metric(report.qa.metrics, ("normalized_em", "em", "exact_match", "answer_exact_match"))
    f1 = _qa_metric(report.qa.metrics, ("token_f1", "f1"))
    non_empty = _qa_metric(report.qa.metrics, ("answer_non_empty_rate", "answer_non_empty", "non_empty_rate"))
    retrieval_latency = f"{_format(_latency(report.retrieval.metrics, 50, 'retrieval'))}/{_format(_latency(report.retrieval.metrics, 95, 'retrieval'))}"
    qa_latency = f"{_format(_latency(report.qa.metrics, 50, 'qa'))}/{_format(_latency(report.qa.metrics, 95, 'qa'))}"
    cells = [
        _dataset_label(report.dataset),
        report.condition,
        report.platform,
        report.status,
        _quad(report.retrieval),
        _quad(report.qa),
        *(_format(value) for value in recall_values),
        _format(public_mrr),
        _format(em),
        _format(f1),
        _format(non_empty),
        retrieval_latency,
        qa_latency,
        report.public_retrieval_contract,
        report.provider_model,
        "; ".join(report.tags) if report.tags else "—",
        report.diagnostic_retrieval,
        _artifact_text(report),
    ]
    return "| " + " | ".join(_cell(value) for value in cells) + " |"


def collect_completed_units(checkpoint: str | Path) -> list[UnitReport]:
    """Return only completed, SUCCESS, full-denominator campaign units."""

    checkpoint_path = Path(checkpoint).expanduser().resolve()
    payload = _mapping(_load_json(checkpoint_path))
    if payload is None:
        raise SyncError(f"CHECKPOINT_NOT_OBJECT:{checkpoint_path}")
    units_value = payload.get("units", [])
    if isinstance(units_value, Mapping):
        units_value = list(units_value.values())
    if not isinstance(units_value, list):
        raise SyncError(f"CHECKPOINT_UNITS_NOT_LIST:{checkpoint_path}")
    reports: list[UnitReport] = []
    for value in units_value:
        if not isinstance(value, Mapping):
            continue
        report = _read_unit_report(checkpoint_path, payload, value)
        if report is not None:
            reports.append(report)
    reports.sort(key=lambda report: (report.ordinal, report.dataset.casefold(), report.condition.casefold(), report.platform.casefold(), report.run_id))
    return reports


def render_markdown(checkpoint: str | Path) -> str:
    """Render a reviewable Markdown experiment-table fragment."""

    checkpoint_path = Path(checkpoint).expanduser().resolve()
    payload = _mapping(_load_json(checkpoint_path))
    if payload is None:
        raise SyncError(f"CHECKPOINT_NOT_OBJECT:{checkpoint_path}")
    units_value = payload.get("units", [])
    total_units = len(units_value) if isinstance(units_value, list) else len(units_value) if isinstance(units_value, Mapping) else 0
    reports = collect_completed_units(checkpoint_path)
    campaign_id = str(payload.get("campaign_id") or checkpoint_path.parent.name)
    lines = [
        START_MARKER,
        "### Local competitor evaluation experiment fragment",
        "",
        f"Campaign: `{_cell(campaign_id)}`; checkpoint: `{_cell(checkpoint_path)}`; eligible full units: `{len(reports)}/{total_units}`.",
        "Selection rule: only checkpoint units with `status=completed`, result `status=SUCCESS`, summary `status=SUCCESS`, a terminal ledger, and full retrieval/QA denominators are included.",
        "Public retrieval metrics are never inferred from answer text. MaxKB admin `hit_test` observations are shown only in the separate diagnostic column.",
        "",
        "| Dataset | Condition | Platform | Status | R P/V/F/U | QA P/V/F/U | R@1 | R@3 | R@5 | R@10 | MRR | QA EM | QA F1 | QA non-empty | R p50/p95 ms | QA p50/p95 ms | Public retrieval contract | Provider/model | Tags | MaxKB diagnostic retrieval (admin only) | Artifacts |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|",
    ]
    if reports:
        lines.extend(_row(report) for report in reports)
    else:
        lines.append("| — | — | — | No eligible completed SUCCESS full units | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |")
    lines.extend(
        [
            "",
            "`R P/V/F/U` and `QA P/V/F/U` are planned/valid/failed/unsupported; failures and unsupported observations remain visible in the planned denominator.",
            "`NEEDS_JUDGE` means the frozen judge/TDAS result is absent or explicitly unsupported; lexical EM/F1 are not a substitute for a judge-defined score.",
            END_MARKER,
        ]
    )
    return "\n".join(lines) + "\n"


def _write_output(path: Path, text: str, checkpoint: Path) -> None:
    target = path.expanduser().resolve()
    if target.name.casefold() == "todo.md":
        raise SyncError("TODO_WRITE_FORBIDDEN")
    if target == checkpoint.expanduser().resolve():
        raise SyncError("CHECKPOINT_OVERWRITE_FORBIDDEN")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path, help="campaign checkpoint JSON")
    parser.add_argument("--output", type=Path, help="write to this non-TODO Markdown file; stdout by default")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checkpoint = args.checkpoint.expanduser().resolve()
        text = render_markdown(checkpoint)
        if args.output is None:
            sys.stdout.write(text)
        else:
            _write_output(args.output, text, checkpoint)
        return 0
    except (OSError, SyncError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
