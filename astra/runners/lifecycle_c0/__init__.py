"""Product-neutral C0 lifecycle controller primitives."""

from .core import (
    C0Controller,
    C0ControllerConfig,
    C0Outcome,
    collect_process_cleanup_report,
    ExternalTriggerManifest,
    JsonlLedger,
    LifecycleConfigurationError,
    LifecycleControllerError,
    get_terminal_bench_trigger,
    get_terminal_bench_trigger_for_instruction,
    lifecycle_predicate_probe_source_path,
    lifecycle_predicate_probe_source_sha256,
    parse_process_cleanup_report,
    process_probe_cleanup_command,
    process_probe_run_command,
    process_probe_source_path,
)

__all__ = [
    "C0Controller",
    "C0ControllerConfig",
    "C0Outcome",
    "collect_process_cleanup_report",
    "ExternalTriggerManifest",
    "JsonlLedger",
    "LifecycleConfigurationError",
    "LifecycleControllerError",
    "get_terminal_bench_trigger",
    "get_terminal_bench_trigger_for_instruction",
    "lifecycle_predicate_probe_source_path",
    "lifecycle_predicate_probe_source_sha256",
    "parse_process_cleanup_report",
    "process_probe_cleanup_command",
    "process_probe_run_command",
    "process_probe_source_path",
]
