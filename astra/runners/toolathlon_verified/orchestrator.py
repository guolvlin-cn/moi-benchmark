from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import traceback
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

from .artifact_contract import (
    ARTIFACT_SCHEMA_VERSION,
    missing_observation,
    observed_observation,
)
from .adapter_common import AdapterOutcome, strip_provider_credentials
from .astra_adapter import (
    AstraRuntime,
    run_astra,
    write_astra_runtime_mcp_binding,
)
from .bundle import write_public_bundle
from .contract import (
    ContractError,
    JsonlEventWriter,
    ModelFreeze,
    RunSpec,
    assert_no_secret_values,
    canonical_json_sha256,
    read_json_object,
    sha256_file,
    utc_now,
    write_json_atomic,
    write_sha256_manifest,
)
from .hermes_adapter import HermesRuntime, run_hermes
from .mcp_client import capture_tool_manifest
from .model_proxy import (
    ModelProxyConfig,
    ModelProxyServer,
    wait_for_model_requests_to_settle,
    load_distinct_provider_credentials,
    provider_credential_fingerprint,
    provider_key_environment,
    provider_user_id,
)
from .permissions import PermissionPolicy
from .product_identity import PRIVATE_IDENTITY_FILENAME, private_identity_projection
from .resources import ResourceSampler
from .trajectory import normalize_product_events


def _load_run_configuration(path: Path) -> tuple[dict[str, Any], RunSpec]:
    raw = read_json_object(path)
    run = raw.get("run")
    if not isinstance(run, dict):
        raise ContractError("orchestrator config has no run object")
    return raw, RunSpec.from_dict(run)


def _validate_runtime_tier(path: Path, spec: RunSpec) -> dict[str, Any]:
    manifest = read_json_object(path)
    task = manifest.get("tasks", {}).get(spec.task_id)
    if not isinstance(task, dict):
        raise ContractError(f"task runtime tier is missing: {spec.task_id}")
    if task.get("deadline_seconds") != spec.deadline_s:
        raise ContractError("run deadline does not match task-runtime-tiers.json")
    return task


def _verify_checksum_manifest(path: Path, expected_sha256: str) -> None:
    if sha256_file(path) != expected_sha256:
        raise ContractError("section 3.3 checksum manifest digest mismatch")
    root = path.parent.resolve()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise ContractError("invalid section 3.3 checksum line") from exc
        candidate = (root / name).resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise ContractError("section 3.3 checksum target is invalid")
        if sha256_file(candidate) != digest:
            raise ContractError(f"section 3.3 component digest mismatch: {name}")


def _validate_frozen_inputs(
    raw: dict[str, Any], spec: RunSpec, section_freeze_path: Path
) -> tuple[dict[str, Any], Path, Path]:
    manifest_path = Path(str(raw["section_3_3_manifest"])).resolve()
    expected_manifest_sha256 = str(raw["section_3_3_manifest_sha256"])
    _verify_checksum_manifest(manifest_path, expected_manifest_sha256)
    section_freeze = read_json_object(section_freeze_path)
    if section_freeze.get("schema_version") != "toolathlon.section-3.3.freeze.v1":
        raise ContractError("unexpected section 3.3 freeze schema")
    if section_freeze.get("decision_status") != "frozen":
        raise ContractError("section 3.3 decisions are not frozen")
    if section_freeze.get("runtime_qualification") != "go":
        raise ContractError("section 3.3 runtime qualification is NO-GO")
    components = section_freeze.get("components")
    if not isinstance(components, dict):
        raise ContractError("section 3.3 component index is missing")

    adapter_freeze_path = Path(str(raw["adapter_freeze"])).resolve()
    system_freeze_path = Path(str(raw["system_freeze"])).resolve()
    permission_freeze_path = Path(str(raw["permission_policy_freeze"])).resolve()
    expected = {
        "adapter.freeze.json": adapter_freeze_path,
        f"{spec.system_id}.freeze.json": system_freeze_path,
        "model.freeze.json": spec.model_freeze_path,
        "permission-policy.freeze.json": permission_freeze_path,
        "task-runtime-tiers.json": Path(str(raw["task_runtime_tiers"])).resolve(),
    }
    for name, path in expected.items():
        component = components.get(name)
        if not isinstance(component, dict) or component.get("sha256") != sha256_file(path):
            raise ContractError(f"section 3.3 does not bind {name}")

    adapter_freeze = read_json_object(adapter_freeze_path)
    files = adapter_freeze.get("implementation", {}).get("files")
    if not isinstance(files, list):
        raise ContractError("adapter freeze has no file manifest")
    repository_root = Path(__file__).resolve().parents[3]
    for item in files:
        if not isinstance(item, dict):
            raise ContractError("invalid adapter file record")
        candidate = (repository_root / str(item.get("path", ""))).resolve()
        if repository_root not in candidate.parents or not candidate.is_file():
            raise ContractError("adapter frozen file path is unavailable")
        if sha256_file(candidate) != item.get("sha256"):
            raise ContractError(f"adapter source changed after freeze: {item.get('path')}")
    return section_freeze, adapter_freeze_path, system_freeze_path


def _adapter_failure(exc: BaseException, duration: float) -> AdapterOutcome:
    return AdapterOutcome(
        terminal_status="crashed",
        product_exit_code=None,
        termination_reason="adapter_error",
        output="",
        error=f"{type(exc).__name__}: {exc}",
        duration_seconds=duration,
        product_pid=None,
        escalated_to_sigkill=False,
        native_events=[],
        metadata={"adapter_exception_type": type(exc).__name__},
    )


def _render_evaluator_command(
    command: list[str],
    *,
    spec: RunSpec,
    public_bundle: Path,
    evaluator_dir: Path,
    agent_exit_code: int,
) -> list[str]:
    values = {
        "trusted_bundle": str(spec.bundle_file),
        "public_bundle": str(public_bundle),
        "workspace": str(spec.workspace),
        "output_dir": str(spec.output_dir),
        "evaluator_dir": str(evaluator_dir),
        "task_id": spec.task_id,
        "run_id": spec.run_id,
        "system_id": spec.system_id,
        "agent_exit_code": str(agent_exit_code),
    }
    rendered: list[str] = []
    for item in command:
        if not isinstance(item, str) or "\x00" in item or "\n" in item:
            raise ContractError("invalid evaluator command argument")
        rendered.append(item.format_map(values))
    if not rendered:
        raise ContractError("evaluator command is empty")
    return rendered


def _run_evaluator(
    config: dict[str, Any] | None,
    *,
    spec: RunSpec,
    public_bundle_path: Path,
    evaluator_timeout_seconds: int,
    agent_exit_code: int,
) -> dict[str, Any]:
    evaluator_dir = spec.output_dir / "evaluator"
    evaluator_dir.mkdir(parents=True, exist_ok=True)
    log_path = evaluator_dir / "eval.log"
    result_path = evaluator_dir / "eval_res.json"
    started = time.monotonic()
    if not isinstance(config, dict):
        result = {
            "pass": None,
            "status": "unavailable",
            "error": "evaluator command not configured",
        }
        write_json_atomic(result_path, result, mode=0o644)
        log_path.write_text("evaluator unavailable: command not configured\n", encoding="utf-8")
        return {
            "verify_status": "unavailable",
            "reward": None,
            "exit_code": None,
            "error": result["error"],
            "duration_seconds": time.monotonic() - started,
        }

    command = config.get("command")
    if not isinstance(command, list):
        raise ContractError("evaluator.command must be an argv list")
    argv = _render_evaluator_command(
        command,
        spec=spec,
        public_bundle=public_bundle_path,
        evaluator_dir=evaluator_dir,
        agent_exit_code=agent_exit_code,
    )
    env = dict(os.environ)
    strip_provider_credentials(env)
    env.update(
        {
            "TOOLATHLON_TRUSTED_BUNDLE": str(spec.bundle_file),
            "TOOLATHLON_PUBLIC_BUNDLE": str(public_bundle_path),
            "TOOLATHLON_RUN_ID": spec.run_id,
            "TOOLATHLON_SYSTEM_ID": spec.system_id,
        }
    )
    try:
        completed = subprocess.run(
            argv,
            cwd=spec.workspace,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=evaluator_timeout_seconds,
            check=False,
        )
        log_path.write_bytes(completed.stdout)
        configured_result = config.get("result_file")
        candidate = (
            Path(str(configured_result).format(evaluator_dir=str(evaluator_dir)))
            if configured_result
            else result_path
        )
        if candidate.is_file() and candidate.resolve() != result_path.resolve():
            result_path.write_bytes(candidate.read_bytes())
        result = read_json_object(result_path) if result_path.is_file() else {}
        passed = result.get("pass")
        if passed is True:
            verify_status = "pass"
        elif passed is False:
            verify_status = "no_pass"
        else:
            verify_status = "unavailable"
        error = None
        if completed.returncode not in {0, 1}:
            error = f"evaluator exited with code {completed.returncode}"
            verify_status = "unavailable"
        elif passed is True and completed.returncode != 0:
            error = f"evaluator reported pass but exited with code {completed.returncode}"
            verify_status = "unavailable"
        elif passed is not False and completed.returncode != 0:
            error = f"evaluator exited with code {completed.returncode} without no-pass result"
            verify_status = "unavailable"
        elif verify_status == "unavailable":
            error = str(result.get("error") or "evaluator result has no boolean pass")
        return {
            "verify_status": verify_status,
            "reward": result.get("reward"),
            "exit_code": completed.returncode,
            "error": error,
            "duration_seconds": time.monotonic() - started,
        }
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b""
        log_path.write_bytes(output)
        result = {
            "pass": None,
            "status": "unavailable",
            "error": "evaluator infrastructure timeout",
        }
        write_json_atomic(result_path, result, mode=0o644)
        return {
            "verify_status": "unavailable",
            "reward": None,
            "exit_code": None,
            "error": result["error"],
            "duration_seconds": time.monotonic() - started,
        }


def _failure_category(outcome: AdapterOutcome, evaluator: dict[str, Any]) -> str:
    if outcome.termination_reason == "agent_deadline":
        return "agent_deadline"
    if outcome.termination_reason == "max_model_requests":
        return "model_request_budget"
    if outcome.termination_reason == "adapter_error":
        return "adapter_error"
    if outcome.terminal_status in {"failed", "crashed", "interrupted"}:
        return "product_error"
    if evaluator["verify_status"] == "unavailable":
        return "evaluator_error"
    if evaluator["verify_status"] == "no_pass":
        return "completed_but_no_pass"
    return "none"


def _redact_if_needed(paths: list[Path], secrets: list[str]) -> list[str]:
    redacted: list[str] = []
    needles = [(item.encode("utf-8"), b"[REDACTED]") for item in secrets if item]
    for path in paths:
        if not path.is_file():
            continue
        payload = path.read_bytes()
        rewritten = payload
        for needle, replacement in needles:
            rewritten = rewritten.replace(needle, replacement)
        if rewritten != payload:
            path.write_bytes(rewritten)
            redacted.append(path.name)
    return redacted


def _write_official_trajectory(
    spec: RunSpec,
    *,
    outcome: AdapterOutcome,
    trajectory_summary: dict[str, Any],
) -> Path:
    trusted = read_json_object(spec.bundle_file)
    host_paths = trusted.get("host_paths")
    if not isinstance(host_paths, dict):
        raise ContractError("trusted bundle has no host_paths for evaluator trajectory")
    log_path = Path(str(host_paths.get("log_file", ""))).resolve()
    if spec.output_dir.resolve() not in log_path.parents:
        raise ContractError("evaluator trajectory must be inside the run output directory")
    status = "success" if outcome.terminal_status == "completed" else "failed"
    write_json_atomic(
        log_path,
        {
            "config": {},
            "request_id": spec.run_id,
            "initial_run_time": utc_now(),
            "completion_time": utc_now(),
            "tool_calls": {"tools": [], "tool_choice": None},
            "status": status,
            "messages": ([{"role": "assistant", "content": outcome.output}] if outcome.output else []),
            "key_stats": trajectory_summary,
            "agent_cost": {},
            "user_cost": {},
            "resumed": False,
            "session_id": spec.run_id,
            "history_file": None,
        },
        mode=0o644,
    )
    return log_path


def _failure_evidence(
    spec: RunSpec,
    *,
    primary_failure: str,
    outcome: AdapterOutcome,
    evaluator: dict[str, Any],
) -> dict[str, Any]:
    evidence_paths: list[str] = []
    if outcome.error:
        evidence_paths.append("adapter.stderr.log")
    if evaluator.get("error") or evaluator.get("verify_status") != "pass":
        evidence_paths.extend(["evaluator/eval.log", "evaluator/eval_res.json"])
    if primary_failure == "none":
        raw_error_code = missing_observation("run_outcome", "no_failure")
    elif outcome.product_exit_code is not None:
        raw_error_code = observed_observation(
            outcome.product_exit_code, "product_process.exit_code"
        )
    elif evaluator.get("exit_code") is not None:
        raw_error_code = observed_observation(
            evaluator["exit_code"], "evaluator_process.exit_code"
        )
    else:
        raw_error_code = missing_observation("run_outcome", "source_not_reported")
    return {
        "schema_version": "toolathlon.failure-evidence.v1",
        "run_id": spec.run_id,
        "system_id": spec.system_id,
        "task_id": spec.task_id,
        "primary_failure_category": primary_failure,
        "raw_error_code": raw_error_code,
        "evidence_paths": sorted(set(evidence_paths)),
        "product_error": (
            observed_observation(outcome.error, "product_adapter")
            if outcome.error
            else missing_observation("product_adapter", "no_product_error")
        ),
        "evaluator_error": (
            observed_observation(evaluator["error"], "evaluator")
            if evaluator.get("error")
            else missing_observation("evaluator", "no_evaluator_error")
        ),
    }


def run(
    config_path: Path,
    *,
    before_evaluator: Callable[[AdapterOutcome], None] | None = None,
    lifecycle_writer: JsonlEventWriter | None = None,
    resource_sampler: ResourceSampler | None = None,
    on_product_pid: Callable[[int], None] | None = None,
    write_artifact_manifest: bool = True,
) -> int:
    run_started_at = utc_now()
    raw, spec = _load_run_configuration(config_path)
    model_freeze = ModelFreeze.load(spec.model_freeze_path)
    tier_manifest_path = Path(str(raw["task_runtime_tiers"])).resolve()
    tier = _validate_runtime_tier(tier_manifest_path, spec)
    section_freeze_path = Path(str(raw["section_3_3_freeze"])).resolve()
    section_freeze, adapter_freeze_path, system_freeze_path = _validate_frozen_inputs(
        raw, spec, section_freeze_path
    )
    infrastructure_timeouts = section_freeze.get("infrastructure_timeouts")
    if not isinstance(infrastructure_timeouts, dict):
        raise ContractError("section 3.3 freeze has no infrastructure timeouts")
    evaluator_timeout = int(infrastructure_timeouts["evaluator_seconds"])

    if "provider_api_key_env" in raw:
        raise ContractError(
            "provider_api_key_env is no longer configurable; use the frozen per-system variables"
        )
    provider_keys = load_distinct_provider_credentials()
    provider_key_env = provider_key_environment(spec.system_id)
    provider_key = provider_keys[spec.system_id]
    provider_fingerprints = {
        system_id: provider_credential_fingerprint(value)
        for system_id, value in sorted(provider_keys.items())
    }
    model_user_id = provider_user_id(spec.system_id, spec.run_id)
    replacement_for_run_id = raw.get("replacement_for_run_id")
    if replacement_for_run_id is not None and not isinstance(
        replacement_for_run_id, str
    ):
        raise ContractError("replacement_for_run_id must be a string when present")
    attempt_ordinal = 2 if replacement_for_run_id else 1
    spec.output_dir.mkdir(parents=True, exist_ok=True)
    event_writer = JsonlEventWriter(
        spec.output_dir / "adapter-events.jsonl",
        run_id=spec.run_id,
        system_id=spec.system_id,
    )
    event_writer.append("run.preparing", task_id=spec.task_id)
    public_bundle_path = spec.output_dir / "task-bundle.public.json"
    public_bundle = write_public_bundle(
        spec.bundle_file,
        public_bundle_path,
        expected_task_id=spec.task_id,
        workspace=spec.workspace,
    )
    permission = PermissionPolicy.load(
        spec.permission_policy_path,
        expected_gateway_url=spec.gateway_url,
        expected_workspace=spec.workspace,
    )

    if lifecycle_writer is not None:
        lifecycle_writer.append("tools_list.start")
    observed_tool_path = spec.output_dir / "tool-schema-observed.json"
    observed_tools = capture_tool_manifest(
        task_id=spec.task_id,
        gateway_url=spec.gateway_url,
        destination=observed_tool_path,
        timeout_s=float(infrastructure_timeouts["gateway_readiness_seconds"]),
    )
    if observed_tools["run_qualification"] != "go":
        raise ContractError("model-visible MCP tool names collide after product sanitization")
    if observed_tools.get("task_id") != spec.task_id:
        raise ContractError("runtime tools/list manifest task_id mismatch")
    observed_rows = observed_tools.get("tools")
    if not isinstance(observed_rows, list):
        raise ContractError("runtime tools/list manifest has no tools array")
    product_tool_name_field = f"{spec.system_id}_model_visible_tool_name"
    product_task_mcp_tools: list[str] = []
    for index, row in enumerate(observed_rows, start=1):
        if not isinstance(row, dict):
            raise ContractError(f"runtime tools/list row {index} is not an object")
        name = row.get(product_tool_name_field)
        if not isinstance(name, str) or not name.startswith("mcp__toolathlon__"):
            raise ContractError(
                f"runtime tools/list row {index} has no valid {spec.system_id} MCP name"
            )
        product_task_mcp_tools.append(name)
    product_task_mcp_tools.sort()
    if len(product_task_mcp_tools) != len(set(product_task_mcp_tools)):
        raise ContractError("runtime product-visible MCP tool names are not unique")
    if observed_tools.get("tool_count") != len(product_task_mcp_tools):
        raise ContractError("runtime tools/list tool_count does not match product names")

    astra_runtime_mcp_binding: dict[str, Any] | None = None
    if spec.system_id == "astra":
        astra_runtime_mcp_binding = write_astra_runtime_mcp_binding(
            spec.output_dir,
            observed_tools,
            gateway_url=spec.gateway_url,
        )
        if astra_runtime_mcp_binding["tool_names"] != product_task_mcp_tools:
            raise ContractError("Astra runtime MCP binding differs from tools/list")
        tool_exposure_mechanism = "astra_native_request_scoped_runtime_mcp"
    else:
        tool_exposure_mechanism = "hermes_fresh_single_task_gateway"
    tool_exposure = {
        "scope": "current_task_attempt_only",
        "mechanism": tool_exposure_mechanism,
        "gateway_server_name": "toolathlon",
        "gateway_url": spec.gateway_url,
        "mcp_tool_count": len(product_task_mcp_tools),
        "mcp_tool_names_sha256": canonical_json_sha256(product_task_mcp_tools),
        "all_observed_task_mcp_tools_required": True,
        "other_task_mcp_tools_allowed": False,
        "product_builtin_tools_retained": True,
        "provider_request_tool_names_recorded": True,
    }
    if astra_runtime_mcp_binding is not None:
        tool_exposure.update(
            {
                "binding_artifact": astra_runtime_mcp_binding["path"].name,
                "binding_sha256": astra_runtime_mcp_binding["binding_sha256"],
                "astra_endpoint": "/chat/stream",
                "runtime_profile": "request_scoped_runtime_mcp",
                "session_strategy": "native_chat_stream_auto_create",
            }
        )
    if lifecycle_writer is not None:
        lifecycle_writer.append(
            "tools_list.end",
            status="passed",
            tool_set_sha256=observed_tools["tool_set_sha256"],
        )

    runtime_config_path = Path(str(raw["runtime_config"])).resolve()
    if not runtime_config_path.is_file():
        raise ContractError("runtime_config is not a file")
    credential_manifest_path = Path(
        str(
            raw.get(
                "credential_manifest",
                section_freeze_path.parent / "credential-manifest.json",
            )
        )
    ).resolve()
    if not credential_manifest_path.is_file() or credential_manifest_path.is_symlink():
        raise ContractError("credential_manifest is not a regular file")

    resolved_config = {
        "schema_version": 1,
        "started_at": run_started_at,
        "experiment_id": spec.experiment_id,
        "run_id": spec.run_id,
        "task_id": spec.task_id,
        "system_id": spec.system_id,
        "pair_id": f"{spec.experiment_id}:{spec.task_id}",
        "replacement_for_run_id": (
            observed_observation(
                replacement_for_run_id, "orchestrator_scheduling_record"
            )
            if replacement_for_run_id
            else missing_observation(
                "orchestrator_scheduling_record", "original_run"
            )
        ),
        "freeze": {
            "m0_manifest_sha256": sha256_file(
                section_freeze_path.parent / "m0.sha256"
            ),
            "sections_3_1_3_2_manifest_sha256": sha256_file(
                section_freeze_path.parent / "sections-3.1-3.2.sha256"
            ),
            "section_3_3_sha256": sha256_file(section_freeze_path),
            "section_3_3_manifest_sha256": sha256_file(
                Path(str(raw["section_3_3_manifest"])).resolve()
            ),
            "adapter_freeze_sha256": sha256_file(adapter_freeze_path),
            "system_freeze_sha256": sha256_file(system_freeze_path),
            "model_sha256": sha256_file(spec.model_freeze_path),
            "runtime_tiers_sha256": sha256_file(tier_manifest_path),
            "runtime_config_sha256": sha256_file(runtime_config_path),
            "permission_policy_sha256": sha256_file(spec.permission_policy_path),
            "task_requirements_sha256": sha256_file(
                spec.task_requirements_manifest_path
            ),
            "execution_protocol_sha256": sha256_file(
                section_freeze_path.parent / "execution-protocol.freeze.json"
            ),
            "vm_freeze_sha256": sha256_file(
                section_freeze_path.parent / "vm.freeze.json"
            ),
            "credential_manifest_sha256": sha256_file(
                credential_manifest_path
            ),
            "app_state_live_sha256": sha256_file(
                section_freeze_path.parent / "m1-app-state-live.json"
            ),
            "task_image_reference": (
                "docker.io/lockon0927/toolathlon-task-image@"
                "sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f"
            ),
        },
        "prompt": public_bundle["prompt"],
        "budget": {
            "tier": tier["tier"],
            "agent_deadline_seconds": spec.deadline_s,
            "max_product_model_requests": spec.max_model_requests,
            "tool_call_limit": {"bounded": False},
        },
        "model": {
            "provider": model_freeze.provider,
            "provider_base_url": model_freeze.provider_base_url,
            "request_id": model_freeze.request_model_id,
            "documented_version": model_freeze.documented_model_version,
            "temperature": model_freeze.temperature,
            "temperature_effective": False,
            "thinking": model_freeze.thinking,
            "thinking_wire_behavior": model_freeze.thinking_wire_behavior,
            "reasoning_effort": model_freeze.reasoning_effort,
            "reasoning_effort_wire_behavior": (
                model_freeze.reasoning_effort_wire_behavior
            ),
            "generation_parameter_source": "benchmark_override",
            "provider_user_id": model_user_id,
            "credential": {
                "selected_environment": provider_key_env,
                "selected_fingerprint": provider_fingerprints[spec.system_id],
                "pair_fingerprints": provider_fingerprints,
                "distinct_values_verified": True,
                "values_logged": False,
            },
        },
        "adapter": {
            "retry_count": 0,
            "fresh_state": True,
            "resume": False,
            "gateway_url": spec.gateway_url,
            "tool_set_sha256": observed_tools["tool_set_sha256"],
            "tool_exposure": tool_exposure,
            "product_identity": {
                "attempt_ordinal": attempt_ordinal,
                "attempt_label": f"a{attempt_ordinal}",
                "strategy": (
                    "astra_registered_user_per_attempt"
                    if spec.system_id == "astra"
                    else "hermes_ephemeral_runtime_session"
                ),
                "provider_user_id_is_product_identity": False,
            },
        },
        "infrastructure_timeouts": infrastructure_timeouts,
    }
    if "credential_manifest" in raw:
        resolved_config["freeze"]["credential_manifest_scope"] = raw.get(
            "credential_manifest_scope", "runtime_override"
        )
    resolved_path = spec.output_dir / "resolved-config.json"
    write_json_atomic(resolved_path, resolved_config, mode=0o644)

    product_pid: list[int | None] = [None]
    sampler = resource_sampler or ResourceSampler(
        spec.output_dir / "resource-usage.jsonl",
        run_id=spec.run_id,
        system_id=spec.system_id,
        product_pid=lambda: product_pid[0],
    )
    model_events = spec.output_dir / "model-usage.jsonl"
    model_state = spec.output_dir / "model-proxy-state.json"
    proxy_config = ModelProxyConfig(
        upstream_base_url=model_freeze.provider_base_url,
        upstream_api_key=provider_key,
        effective_model=model_freeze.request_model_id,
        temperature=model_freeze.temperature,
        thinking=model_freeze.thinking,
        reasoning_effort=model_freeze.reasoning_effort,
        max_requests=spec.max_model_requests,
        run_id=spec.run_id,
        system_id=spec.system_id,
        events_path=model_events,
        state_path=model_state,
    )
    outcome: AdapterOutcome
    adapter_started = time.monotonic()
    event_writer.append("product.startup_start")
    if lifecycle_writer is not None:
        lifecycle_writer.append("adapter.start")
    agent_started: list[bool] = [False]

    def mark_agent_started() -> None:
        if not agent_started[0]:
            agent_started[0] = True
            event_writer.append(
                "agent.execution_start", deadline_seconds=spec.deadline_s
            )

    sampler_context = nullcontext(sampler) if resource_sampler is not None else sampler
    with sampler_context, ModelProxyServer(proxy_config) as proxy:
        try:
            if spec.system_id == "astra":
                outcome = run_astra(
                    runtime=AstraRuntime.load(runtime_config_path),
                    public_bundle=public_bundle,
                    gateway_url=spec.gateway_url,
                    workspace=spec.workspace,
                    output_dir=spec.output_dir,
                    proxy_url=proxy.url,
                    deadline_seconds=spec.deadline_s,
                    budget_exceeded=proxy.budget.exceeded.is_set,
                    model_request_snapshot=proxy.budget.snapshot,
                    experiment_id=spec.experiment_id,
                    task_id=spec.task_id,
                    run_id=spec.run_id,
                    attempt_ordinal=attempt_ordinal,
                    runtime_mcp_binding_path=astra_runtime_mcp_binding["path"],
                    task_mcp_tool_names=astra_runtime_mcp_binding["tool_names"],
                    on_product_pid=lambda pid: (
                        product_pid.__setitem__(0, pid),
                        on_product_pid(pid) if on_product_pid is not None else None,
                    ),
                    on_agent_start=mark_agent_started,
                )
            else:
                outcome = run_hermes(
                    runtime=HermesRuntime.load(runtime_config_path),
                    public_bundle=public_bundle,
                    gateway_url=spec.gateway_url,
                    workspace=spec.workspace,
                    output_dir=spec.output_dir,
                    proxy_url=proxy.url,
                    permission_policy=permission,
                    deadline_seconds=spec.deadline_s,
                    budget_exceeded=proxy.budget.exceeded.is_set,
                    model_request_snapshot=proxy.budget.snapshot,
                    on_product_pid=lambda pid: (
                        product_pid.__setitem__(0, pid),
                        on_product_pid(pid) if on_product_pid is not None else None,
                    ),
                    on_agent_start=mark_agent_started,
                )
            if spec.system_id == "astra":
                outcome.metadata["post_terminal_model_drain"] = (
                    wait_for_model_requests_to_settle(
                        proxy.budget.snapshot,
                        context="Astra post-terminal",
                    )
                )
        except BaseException as exc:
            outcome = _adapter_failure(exc, time.monotonic() - adapter_started)
            (spec.output_dir / "adapter.stderr.log").write_text(
                "".join(traceback.format_exception(exc)), encoding="utf-8"
            )
    private_identity_path = spec.output_dir / PRIVATE_IDENTITY_FILENAME
    if spec.system_id == "astra" and private_identity_path.is_file():
        outcome.metadata["product_identity"] = private_identity_projection(
            private_identity_path
        )
    if agent_started[0]:
        event_writer.append(
            "agent.execution_end",
            terminal_status=outcome.terminal_status,
            termination_reason=outcome.termination_reason,
        )
    else:
        event_writer.append(
            "agent.execution_not_started",
            terminal_status=outcome.terminal_status,
            termination_reason=outcome.termination_reason,
        )

    trajectory_summary = normalize_product_events(
        outcome.native_events,
        run_id=spec.run_id,
        system_id=spec.system_id,
        trajectory_path=spec.output_dir / "trajectory.jsonl",
        tool_calls_path=spec.output_dir / "tool-calls.jsonl",
        observed_tool_manifest=observed_tools,
    )
    if not (spec.output_dir / "adapter.stdout.log").exists():
        (spec.output_dir / "adapter.stdout.log").write_text(outcome.output, encoding="utf-8")
    if not (spec.output_dir / "adapter.stderr.log").exists():
        (spec.output_dir / "adapter.stderr.log").write_text(
            (outcome.error or "") + ("\n" if outcome.error else ""), encoding="utf-8"
        )

    _write_official_trajectory(
        spec,
        outcome=outcome,
        trajectory_summary=trajectory_summary,
    )
    if lifecycle_writer is not None:
        lifecycle_writer.append(
            "adapter.end",
            status=outcome.terminal_status,
            termination_reason=outcome.termination_reason,
        )

    if before_evaluator is not None:
        before_evaluator(outcome)

    event_writer.append("evaluator.start")
    if lifecycle_writer is not None:
        lifecycle_writer.append("evaluator.start")
    evaluator = _run_evaluator(
        raw.get("evaluator") if isinstance(raw.get("evaluator"), dict) else None,
        spec=spec,
        public_bundle_path=public_bundle_path,
        evaluator_timeout_seconds=evaluator_timeout,
        agent_exit_code=0 if outcome.terminal_status == "completed" else 1,
    )
    event_writer.append("evaluator.end", verify_status=evaluator["verify_status"])
    if lifecycle_writer is not None:
        lifecycle_writer.append(
            "evaluator.end", verify_status=evaluator["verify_status"]
        )

    secrets = [
        *provider_keys.values(),
        os.environ.get("ASTRA_ADMIN_ACCESS_TOKEN", ""),
        *outcome.sensitive_values,
    ]
    primary_failure = _failure_category(outcome, evaluator)
    run_validity = (
        "infra_invalid"
        if primary_failure in {"adapter_error", "environment_error", "evaluator_error"}
        else "valid"
    )
    run_record = {
        "schema_version": 1,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "experiment_id": spec.experiment_id,
        "run_id": spec.run_id,
        "system_id": spec.system_id,
        "task_id": spec.task_id,
        "pair_id": f"{spec.experiment_id}:{spec.task_id}",
        "replacement_for_run_id": (
            observed_observation(
                replacement_for_run_id, "orchestrator_scheduling_record"
            )
            if replacement_for_run_id
            else missing_observation(
                "orchestrator_scheduling_record", "original_run"
            )
        ),
        "started_at": run_started_at,
        "finished_at": utc_now(),
        "terminal_status": outcome.terminal_status,
        "product_exit_code": (
            observed_observation(outcome.product_exit_code, "product_process")
            if outcome.product_exit_code is not None
            else missing_observation("product_process", "process_not_started")
        ),
        "termination_reason": outcome.termination_reason,
        "claim_done_seen": trajectory_summary["claim_done_seen"],
        "timeout": outcome.terminal_status == "timeout",
        "timeout_scope": "agent" if outcome.terminal_status == "timeout" else "none",
        "deadline_s": spec.deadline_s,
        "agent_duration_seconds": outcome.duration_seconds,
        "product_pid": (
            observed_observation(outcome.product_pid, "adapter_process_monitor")
            if outcome.product_pid is not None
            else missing_observation("adapter_process_monitor", "process_not_started")
        ),
        "escalated_to_sigkill": outcome.escalated_to_sigkill,
        "verify_status": evaluator["verify_status"],
        "reward": (
            observed_observation(evaluator["reward"], "evaluator_result")
            if evaluator["reward"] is not None
            else missing_observation("evaluator_result", "evaluator_not_reported")
        ),
        "evaluator_exit_code": (
            observed_observation(evaluator["exit_code"], "evaluator_process")
            if evaluator["exit_code"] is not None
            else missing_observation("evaluator_process", "process_not_started")
        ),
        "evaluator_error": (
            observed_observation(evaluator["error"], "evaluator")
            if evaluator["error"] is not None
            else missing_observation("evaluator", "no_evaluator_error")
        ),
        "evaluator_duration_seconds": evaluator["duration_seconds"],
        "run_validity": run_validity,
        "invalid_scope": (
            observed_observation("run", "orchestrator_classification")
            if run_validity == "infra_invalid"
            else missing_observation("orchestrator_classification", "run_is_valid")
        ),
        "primary_failure_category": primary_failure,
        "adapter": outcome.metadata,
        "trajectory": trajectory_summary,
        "model_budget": read_json_object(model_state)["budget"],
        "artifact_gate": {"status": "pending_cleanup_and_validation"},
        "secret_redaction": {"redacted": False, "files": []},
    }
    write_json_atomic(
        spec.output_dir / "failure-evidence.json",
        _failure_evidence(
            spec,
            primary_failure=primary_failure,
            outcome=outcome,
            evaluator=evaluator,
        ),
        mode=0o644,
    )
    write_json_atomic(spec.output_dir / "run.json", run_record, mode=0o644)
    event_writer.append("run.finalized", run_validity=run_validity)
    artifact_candidates = [
        path
        for path in spec.output_dir.rglob("*")
        if path.is_file()
        and path.name not in {"artifacts.sha256", PRIVATE_IDENTITY_FILENAME}
    ]
    redacted_files = _redact_if_needed(artifact_candidates, secrets)
    assert_no_secret_values(artifact_candidates, secrets)
    if redacted_files:
        run_record = read_json_object(spec.output_dir / "run.json")
        run_record["secret_redaction"] = {
            "redacted": True,
            "files": redacted_files,
        }
        write_json_atomic(spec.output_dir / "run.json", run_record, mode=0o644)
    if write_artifact_manifest:
        artifact_candidates = [
            path
            for path in spec.output_dir.rglob("*")
            if path.is_file() and path.name != "artifacts.sha256"
        ]
        write_sha256_manifest(
            spec.output_dir / "artifacts.sha256",
            artifact_candidates,
            root=spec.output_dir,
        )
    return 0 if run_validity == "valid" else 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one frozen Toolathlon product slot")
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return run(args.config.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
