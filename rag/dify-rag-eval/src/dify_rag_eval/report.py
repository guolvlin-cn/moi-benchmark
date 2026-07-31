from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def render_markdown(summary: dict[str, Any]) -> str:
    metrics = summary.get("metrics") or {}
    latency = summary.get("latency_seconds") or {}
    lines = [
        "# Dify RAG Evaluation Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Attempts: {summary.get('attempts', 0)}",
        f"- Distinct questions: {summary.get('distinct_questions', 0)}",
        f"- Mean latency: {_format(latency.get('mean'))} s",
        f"- P50 latency: {_format(latency.get('p50'))} s",
        f"- P95 latency: {_format(latency.get('p95'))} s",
        "",
        "| Metric | Macro mean |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {_format(value)} |" for name, value in metrics.items())
    lines.extend(
        [
            "",
            "> `N/A` means the dataset did not contain the labels needed for that "
            "metric. Failed product requests remain in `request_success`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(path: str | Path, summary: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_markdown(summary), encoding="utf-8")


def _format(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.4f}"
