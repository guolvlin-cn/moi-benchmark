#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from astra.runners.toolathlon_verified.artifact_contract import (
    read_jsonl,
    validate_run_artifacts,
)
from astra.runners.toolathlon_verified.contract import (
    ContractError,
    read_json_object,
    sha256_file,
    utc_now,
    write_json_atomic,
)


SYSTEMS = ("astra", "hermes")
TASK_ID = "find-alita-paper"


def observation_value(value: Any, label: str) -> Any:
    if not isinstance(value, dict) or set(value) != {
        "value",
        "source",
        "reliability",
        "missing_reason",
    }:
        raise ContractError(f"{label} is not an observation")
    return value["value"]


def candidate_runs(root: Path, system: str) -> list[dict[str, Any]]:
    task_root = root / system / TASK_ID
    if not task_root.is_dir():
        raise ContractError(f"missing task result directory: {task_root}")
    candidates: list[dict[str, Any]] = []
    for directory in sorted(path for path in task_root.iterdir() if path.is_dir()):
        validation = validate_run_artifacts(directory)
        run = read_json_object(directory / "run.json")
        resolved = read_json_object(directory / "resolved-config.json")
        if run.get("system_id") != system or run.get("task_id") != TASK_ID:
            raise ContractError(f"run identity mismatch: {directory}")
        candidates.append(
            {
                "directory": directory,
                "validation": validation,
                "run": run,
                "resolved": resolved,
            }
        )
    if not 1 <= len(candidates) <= 2:
        raise ContractError(f"{system} must have one original and at most one replacement")
    return candidates


def select_effective(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    original = [
        item
        for item in candidates
        if observation_value(
            item["run"]["replacement_for_run_id"], "replacement_for_run_id"
        )
        is None
    ]
    if len(original) != 1:
        raise ContractError("each system must have exactly one original run")
    if len(candidates) == 1:
        return original[0]
    replacement = next(item for item in candidates if item is not original[0])
    replacement_for = observation_value(
        replacement["run"]["replacement_for_run_id"], "replacement_for_run_id"
    )
    if replacement_for != original[0]["run"]["run_id"]:
        raise ContractError("replacement_for_run_id does not identify the original")
    if original[0]["run"].get("run_validity") != "infra_invalid":
        raise ContractError("a replacement exists for a non-infrastructure result")
    return replacement


def validate_attempt_identities(
    system: str, candidates: list[dict[str, Any]]
) -> None:
    identity_ids: set[str] = set()
    scope_fingerprints: set[str] = set()
    for item in candidates:
        run = item["run"]
        replacement = observation_value(
            run["replacement_for_run_id"], "replacement_for_run_id"
        )
        expected_ordinal = 2 if replacement is not None else 1
        identity = run.get("adapter", {}).get("product_identity")
        if not isinstance(identity, dict):
            raise ContractError(f"{system} run has no product identity evidence")
        if system == "astra":
            if identity.get("attempt_ordinal") != expected_ordinal:
                raise ContractError("Astra attempt identity ordinal mismatch")
            identity_id = identity.get("identity_id")
            fingerprint = identity.get("server_user_id_sha256") or identity.get(
                "username_sha256"
            )
            if not isinstance(identity_id, str) or not identity_id:
                raise ContractError("Astra identity ID is missing")
            if not isinstance(fingerprint, str) or not fingerprint:
                raise ContractError("Astra attempt user fingerprint is missing")
        else:
            identity_id = f"hermes-a{expected_ordinal}"
            fingerprint = identity.get("attempt_session_id_sha256")
            if not isinstance(fingerprint, str) or not fingerprint:
                raise ContractError("Hermes session fingerprint is missing")
        if identity_id in identity_ids or fingerprint in scope_fingerprints:
            raise ContractError(f"{system} reused an attempt identity")
        identity_ids.add(identity_id)
        scope_fingerprints.add(fingerprint)


def validate_live_e2e(system: str, item: dict[str, Any]) -> None:
    run = item["run"]
    if run.get("run_validity") != "valid":
        raise ContractError(f"{system} effective run is not valid")
    if run.get("terminal_status") != "completed":
        raise ContractError(f"{system} Agent did not complete")
    if run.get("verify_status") not in {"pass", "no_pass"}:
        raise ContractError(f"{system} evaluator result is unavailable")
    budget = run.get("model_budget")
    if not isinstance(budget, dict):
        raise ContractError(f"{system} model budget evidence is missing")
    forwarded = budget.get("provider_requests_forwarded")
    completed = budget.get("provider_requests_completed")
    failed = budget.get("provider_requests_failed")
    if not isinstance(forwarded, int) or forwarded < 1:
        raise ContractError(f"{system} made no Agent model request")
    if (
        not isinstance(completed, int)
        or not isinstance(failed, int)
        or completed != forwarded
        or failed < 0
        or failed > completed
    ):
        raise ContractError(f"{system} has incomplete model request evidence")
    if completed - failed < 1:
        raise ContractError(f"{system} has no successful Agent model request")
    if run.get("adapter", {}).get("setup_provider_requests_before_agent") != 0:
        raise ContractError(f"{system} made a setup model request")
    adapter_rows = read_jsonl(item["directory"] / "adapter-events.jsonl", allow_empty=False)
    model_rows = read_jsonl(item["directory"] / "model-usage.jsonl", allow_empty=False)
    starts = [row for row in adapter_rows if row.get("event") == "agent.execution_start"]
    if len(starts) != 1:
        raise ContractError(f"{system} has no unique Agent start event")
    agent_start = starts[0]["monotonic_ns"]
    if any(
        row.get("event") == "model_request.started"
        and row.get("monotonic_ns", -1) < agent_start
        for row in model_rows
    ):
        raise ContractError(f"{system} forwarded a model request before Agent start")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the minimal Astra/Hermes E2E pair")
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    root = args.output_root.resolve()
    selected: dict[str, dict[str, Any]] = {}
    all_candidates: dict[str, list[dict[str, Any]]] = {}
    for system in SYSTEMS:
        candidates = candidate_runs(root, system)
        validate_attempt_identities(system, candidates)
        all_candidates[system] = candidates
        selected[system] = select_effective(candidates)

    astra = selected["astra"]
    hermes = selected["hermes"]
    for field in ("experiment_id", "task_id", "pair_id"):
        if astra["run"].get(field) != hermes["run"].get(field):
            raise ContractError(f"paired run mismatch: {field}")
    validate_live_e2e("astra", astra)
    validate_live_e2e("hermes", hermes)

    common_freeze_fields = (
        "m0_manifest_sha256",
        "sections_3_1_3_2_manifest_sha256",
        "section_3_3_sha256",
        "section_3_3_manifest_sha256",
        "adapter_freeze_sha256",
        "model_sha256",
        "runtime_tiers_sha256",
        "task_requirements_sha256",
        "execution_protocol_sha256",
        "vm_freeze_sha256",
        "credential_manifest_sha256",
        "app_state_live_sha256",
        "task_image_reference",
    )
    astra_freeze = astra["resolved"]["freeze"]
    hermes_freeze = hermes["resolved"]["freeze"]
    for field in common_freeze_fields:
        if astra_freeze.get(field) != hermes_freeze.get(field):
            raise ContractError(f"paired freeze mismatch: {field}")
    for field in (
        "provider",
        "provider_base_url",
        "request_id",
        "documented_version",
        "temperature",
        "temperature_effective",
        "thinking",
        "thinking_wire_behavior",
        "reasoning_effort",
        "reasoning_effort_wire_behavior",
        "generation_parameter_source",
    ):
        if astra["resolved"]["model"].get(field) != hermes["resolved"]["model"].get(field):
            raise ContractError(f"paired model mismatch: {field}")
    fingerprints = astra["resolved"]["model"]["credential"]["pair_fingerprints"]
    if fingerprints != hermes["resolved"]["model"]["credential"]["pair_fingerprints"]:
        raise ContractError("paired provider credential fingerprints differ")
    if fingerprints.get("astra") == fingerprints.get("hermes"):
        raise ContractError("paired provider credential fingerprints are not distinct")
    astra_tools = read_json_object(astra["directory"] / "tool-schema-observed.json")
    hermes_tools = read_json_object(hermes["directory"] / "tool-schema-observed.json")
    if astra_tools.get("tool_set_sha256") != hermes_tools.get("tool_set_sha256"):
        raise ContractError("paired runtime tools/list Schema differs")

    report = {
        "schema_version": "toolathlon.m1-minimal-e2e-qualification.v1",
        "created_at": utc_now(),
        "status": "GO",
        "task_id": TASK_ID,
        "pair_id": astra["run"]["pair_id"],
        "waived": [
            "independent_108_task_tools_schema_prescan",
            "independent_gold_evaluator_replay",
        ],
        "systems": {
            system: {
                "effective_run_id": selected[system]["run"]["run_id"],
                "effective_run_directory": str(selected[system]["directory"]),
                "original_run_id": all_candidates[system][0]["run"]["run_id"],
                "candidate_count": len(all_candidates[system]),
                "verify_status": selected[system]["run"]["verify_status"],
                "run_validity": selected[system]["run"]["run_validity"],
                "artifacts_sha256": sha256_file(
                    selected[system]["directory"] / "artifacts.sha256"
                ),
            }
            for system in SYSTEMS
        },
        "formal_reuse": {
            "counted_in_first_14_task_batch": True,
            "rerun_required": False,
        },
    }
    report_path = root / "m1-live-qualification.json"
    write_json_atomic(report_path, report, mode=0o644)
    digest_path = root / "m1-live-qualification.sha256"
    digest_path.write_text(
        f"{sha256_file(report_path)}  {report_path.name}\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "GO", "report": str(report_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
