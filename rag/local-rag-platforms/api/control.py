#!/usr/bin/env python3
"""One control plane for the HTTP interfaces of all local RAG competitors.

The platform-specific request shapes remain in the target adapters, while
callers use one small interface: describe, request once, or benchmark.  The
transport and metric implementation is shared with ``dify_rag_eval`` so the
old API benchmark and this controller produce the same artifact schema.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


PLATFORM_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLATFORM_ROOT.parent
if str(PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(PLATFORM_ROOT))
EVALUATOR_SRC = PLATFORM_ROOT / "dify-rag-eval" / "src"
if str(EVALUATOR_SRC) not in sys.path:
    sys.path.insert(0, str(EVALUATOR_SRC))

from env import load_central_env  # noqa: E402
from dify_rag_eval.api_benchmark import (  # noqa: E402
    BenchmarkConfigError,
    ScenarioConfig,
    TargetConfig,
    describe_targets,
    load_benchmark_targets,
    build_builtin_targets,
    measure_request,
    run_benchmark,
    write_markdown_report,
)


SUPPORTED_PLATFORMS = ("moi", "dify", "fastgpt", "maxkb", "ragflow")
SUPPORTED_SCENARIOS = ("events", "empty_workflow")


class ControllerConfigError(ValueError):
    """Raised when the controller cannot resolve a runnable target."""


def load_controller_environment(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load the single repository-root dotenv file, then explicit values."""

    return load_central_env(environ)


def _ragflow_target(environ: Mapping[str, str]) -> TargetConfig:
    question = environ.get("RAG_BENCHMARK_QUESTION", "benchmark query")
    base_url = (
        environ.get("RAGFLOW_BENCHMARK_BASE_URL")
        or environ.get("RAGFLOW_BASE_URL")
        or "http://127.0.0.1:9380"
    )
    api_key_env = environ.get("RAGFLOW_BENCHMARK_API_KEY_ENV", "RAGFLOW_API_KEY")
    chat_id_env = environ.get("RAGFLOW_BENCHMARK_CHAT_ID_ENV", "RAGFLOW_CHAT_ID")
    chat_id = "${" + chat_id_env + "}"
    path = environ.get(
        "RAGFLOW_BENCHMARK_PATH",
        f"/api/v1/openai/{chat_id}/chat/completions",
    )
    common_body = {
        "model": environ.get("RAGFLOW_MODEL", "ragflow"),
        "messages": [{"role": "user", "content": question}],
        "detail": True,
        "extra_body": {"reference": True},
    }
    return TargetConfig(
        name="ragflow",
        base_url=base_url,
        api_key_env=api_key_env,
        auth_header="Authorization",
        auth_scheme="bearer",
        event=ScenarioConfig(
            name="events",
            path=path,
            protocol="sse",
            body={**common_body, "stream": True},
            note="RAGFlow OpenAI-compatible chat SSE with reference metadata.",
        ),
        empty_workflow=ScenarioConfig(
            name="empty_workflow",
            path=path,
            protocol="json",
            body={**common_body, "stream": False},
            note="Non-stream native chat; use a no-op chat configuration for a true empty-workflow comparison.",
        ),
        required_env=(chat_id_env,),
        metadata={
            "family": "RAGFlow",
            "event_contract": "OpenAI-compatible SSE",
            "health_path": "/api/v1/system/healthz",
        },
    )


def build_competitor_targets(
    environ: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, TargetConfig]:
    """Build all five target adapters and apply optional JSON overrides."""

    env = load_controller_environment(environ)
    if config_path is None:
        targets = build_builtin_targets(env)
    else:
        targets = load_benchmark_targets(config_path, env)
    targets.setdefault("ragflow", _ragflow_target(env))
    return targets


def select_platforms(
    targets: Mapping[str, TargetConfig],
    raw: str | Sequence[str] = "all",
) -> dict[str, TargetConfig]:
    """Resolve ``all`` or a comma-separated/list selection deterministically."""

    if isinstance(raw, str):
        names = list(targets) if raw.strip().lower() == "all" else [
            item.strip() for item in raw.split(",") if item.strip()
        ]
    else:
        names = list(raw)
    unknown = [name for name in names if name not in targets]
    if unknown:
        raise ControllerConfigError(
            f"unknown competitor(s): {', '.join(unknown)}; available: {', '.join(targets)}"
        )
    return {name: targets[name] for name in names}


@dataclass(frozen=True)
class BenchmarkOptions:
    """Stable benchmark controls shared by every competitor adapter."""

    scenarios: tuple[str, ...] = ("events", "empty_workflow")
    connection_levels: tuple[int, ...] = (1, 4, 8)
    duration_s: float = 10.0
    warmup_s: float = 2.0
    timeout_s: float = 60.0
    max_requests: int | None = None


class CompetitorController:
    """Deep module hiding target selection, auth, transport and metrics."""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self.environ = load_controller_environment(environ)
        self.config_path = Path(config_path) if config_path is not None else None
        self._targets = build_competitor_targets(self.environ, self.config_path)

    @property
    def targets(self) -> Mapping[str, TargetConfig]:
        """Credential-safe target definitions; secrets are resolved only at request time."""

        return self._targets

    def list_platforms(self) -> tuple[str, ...]:
        return tuple(self._targets)

    def describe(self, platforms: str | Sequence[str] = "all") -> dict[str, Any]:
        selected = select_platforms(self._targets, platforms)
        return {
            "schema": "moi-competitor-control-v1",
            "repo_root": str(REPO_ROOT),
            "platforms": list(selected),
            "targets": describe_targets(selected, self.environ),
        }

    def request_once(
        self,
        platform: str,
        *,
        scenario: str = "events",
        timeout_s: float = 60.0,
    ) -> dict[str, Any]:
        if scenario not in SUPPORTED_SCENARIOS:
            raise ControllerConfigError(
                f"unknown scenario {scenario!r}; choose from {', '.join(SUPPORTED_SCENARIOS)}"
            )
        target = select_platforms(self._targets, [platform])[platform]
        missing = target.missing_requirements(self.environ)
        scenario_config = target.scenario(scenario)
        if missing:
            return {
                "target": platform,
                "scenario": scenario,
                "status": "skipped",
                "reason": f"missing configuration: {', '.join(missing)}",
            }
        if not scenario_config.supported:
            return {
                "target": platform,
                "scenario": scenario,
                "status": "unsupported",
                "reason": scenario_config.note or "scenario is not configured",
            }
        sample = measure_request(
            target,
            scenario_config,
            self.environ,
            timeout_s,
        )
        return {
            "target": platform,
            "scenario": scenario,
            "status": "success" if sample.get("success") else "error",
            **sample,
        }

    def benchmark(
        self,
        platforms: str | Sequence[str] = "all",
        *,
        options: BenchmarkOptions | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        settings = options or BenchmarkOptions()
        selected = select_platforms(self._targets, platforms)
        return run_benchmark(
            selected,
            scenarios=settings.scenarios,
            connection_levels=settings.connection_levels,
            duration_s=settings.duration_s,
            warmup_s=settings.warmup_s,
            timeout_s=settings.timeout_s,
            max_requests=settings.max_requests,
            environ=self.environ,
        )

    @staticmethod
    def write_artifacts(
        report: Mapping[str, Any],
        samples: Sequence[Mapping[str, Any]],
        output: str | Path,
    ) -> Path:
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / "summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with (output_path / "samples.jsonl").open("w", encoding="utf-8") as handle:
            for sample in samples:
                handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
        (output_path / "resolved-targets.json").write_text(
            json.dumps(report.get("targets", {}), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_markdown_report(report, output_path / "report.md")
        return output_path.resolve()


def _parse_connections(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(int(item.strip()) for item in raw.split(",") if item.strip())
    except ValueError as exc:
        raise ControllerConfigError("--connections must be comma-separated integers") from exc
    if not values or any(value <= 0 for value in values):
        raise ControllerConfigError("--connections must contain positive integers")
    return values


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, help="optional JSON target override config")
    parser.add_argument("--platforms", default="all", help="comma-separated names or all")
    parser.add_argument("--question", help="override RAG_BENCHMARK_QUESTION")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list supported platforms and safe endpoint metadata")
    _add_common_options(list_parser)

    dry_parser = subparsers.add_parser("dry-run", help="resolve targets without sending requests")
    _add_common_options(dry_parser)
    dry_parser.add_argument("--scenario", choices=("events", "empty_workflow", "both"), default="both")
    dry_parser.add_argument("--connections", default="1,4,8")
    dry_parser.add_argument("--duration", type=float, default=10.0)
    dry_parser.add_argument("--warmup", type=float, default=2.0)
    dry_parser.add_argument("--timeout", type=float, default=60.0)
    dry_parser.add_argument("--max-requests", type=int)
    dry_parser.add_argument("--output", type=Path, default=Path("runs/api-benchmark-unified"))

    request_parser = subparsers.add_parser("request", help="send one controlled request to one platform")
    request_parser.add_argument("--config", type=Path)
    request_parser.add_argument("--platform", required=True, choices=SUPPORTED_PLATFORMS)
    request_parser.add_argument("--scenario", choices=SUPPORTED_SCENARIOS, default="events")
    request_parser.add_argument("--question")
    request_parser.add_argument("--timeout", type=float, default=60.0)

    benchmark_parser = subparsers.add_parser("benchmark", help="run one unified benchmark over selected platforms")
    _add_common_options(benchmark_parser)
    benchmark_parser.add_argument("--scenario", choices=("events", "empty_workflow", "both"), default="both")
    benchmark_parser.add_argument("--connections", default="1,4,8")
    benchmark_parser.add_argument("--duration", type=float, default=10.0)
    benchmark_parser.add_argument("--warmup", type=float, default=2.0)
    benchmark_parser.add_argument("--timeout", type=float, default=60.0)
    benchmark_parser.add_argument("--max-requests", type=int)
    benchmark_parser.add_argument("--output", type=Path, default=Path("runs/api-benchmark-unified"))
    return parser


def _controller_from_args(args: argparse.Namespace) -> CompetitorController:
    environ = dict(os.environ)
    if args.question:
        environ["RAG_BENCHMARK_QUESTION"] = args.question
    return CompetitorController(environ=environ, config_path=args.config)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        controller = _controller_from_args(args)
        if args.command == "list":
            print(json.dumps(controller.describe(args.platforms), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "dry-run":
            preview = controller.describe(args.platforms)
            preview["mode"] = "dry-run"
            preview["parameters"] = {
                "scenarios": (
                    ["events", "empty_workflow"]
                    if args.scenario == "both"
                    else [args.scenario]
                ),
                "connection_levels": list(_parse_connections(args.connections)),
                "duration_s": args.duration,
                "warmup_s": args.warmup,
                "timeout_s": args.timeout,
                "max_requests": args.max_requests,
            }
            print(json.dumps(preview, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "request":
            result = controller.request_once(args.platform, scenario=args.scenario, timeout_s=args.timeout)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if result.get("status") in {"success", "skipped", "unsupported"} else 1

        scenarios = ("events", "empty_workflow") if args.scenario == "both" else (args.scenario,)
        report, samples = controller.benchmark(
            args.platforms,
            options=BenchmarkOptions(
                scenarios=scenarios,
                connection_levels=_parse_connections(args.connections),
                duration_s=args.duration,
                warmup_s=args.warmup,
                timeout_s=args.timeout,
                max_requests=args.max_requests,
            ),
        )
        output = controller.write_artifacts(report, samples, args.output)
        print(json.dumps({"status": "ok", "output": str(output), "platforms": report["targets"]}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (BenchmarkConfigError, ControllerConfigError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BenchmarkOptions",
    "CompetitorController",
    "ControllerConfigError",
    "REPO_ROOT",
    "SUPPORTED_PLATFORMS",
    "SUPPORTED_SCENARIOS",
    "build_competitor_targets",
    "load_controller_environment",
    "main",
    "select_platforms",
]
