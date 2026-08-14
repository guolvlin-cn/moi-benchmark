from __future__ import annotations

import json
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from astra.runners.toolathlon_verified.artifact_contract import (
    ARTIFACT_SCHEMA_VERSION,
    REQUIRED_LIFECYCLE_EVENTS,
    missing_observation,
    validate_observation,
    validate_run_artifacts,
)
from astra.runners.toolathlon_verified.contract import (
    ContractError,
    canonical_json_sha256,
    sha256_file,
    write_sha256_manifest,
)
from astra.runners.toolathlon_verified.trajectory import normalize_product_events


class ArtifactContractTests(unittest.TestCase):
    def _write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def _write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )

    @staticmethod
    def _rehash(root: Path) -> None:
        files = [
            path
            for path in root.rglob("*")
            if path.is_file() and path.name != "artifacts.sha256"
        ]
        write_sha256_manifest(root / "artifacts.sha256", files, root=root)

    @staticmethod
    def _event(event: str, sequence: int = 1) -> dict:
        return {
            "run_id": "run-1",
            "system_id": "astra",
            "timestamp": "2026-08-06T00:00:00+00:00",
            "monotonic_ns": sequence,
            "sequence": sequence,
            "event": event,
        }

    def _fixture(self, root: Path) -> None:
        identity = {
            "experiment_id": "exp-1",
            "run_id": "run-1",
            "system_id": "astra",
            "task_id": "find-alita-paper",
            "pair_id": "exp-1:find-alita-paper",
        }
        freeze = {
            name: "a" * 64
            for name in (
                "m0_manifest_sha256",
                "sections_3_1_3_2_manifest_sha256",
                "section_3_3_sha256",
                "section_3_3_manifest_sha256",
                "adapter_freeze_sha256",
                "system_freeze_sha256",
                "model_sha256",
                "runtime_tiers_sha256",
                "runtime_config_sha256",
                "permission_policy_sha256",
                "task_requirements_sha256",
                "execution_protocol_sha256",
                "vm_freeze_sha256",
                "credential_manifest_sha256",
                "app_state_live_sha256",
            )
        }
        username = "tva_fixture_a1"
        password = "fixture-password"
        private_path = root / "product-identity.private.json"
        self._write_json(
            private_path,
            {
                **identity,
                "schema_version": "toolathlon.astra-product-identity.private.v1",
                "identity_id": "astra-fixture-a1",
                "attempt_ordinal": 1,
                "attempt_label": "a1",
                "strategy": "astra_registered_user_per_attempt",
                "username": username,
                "password": password,
                "email": "fixture@toolathlon.invalid",
                "registration_status": "verified",
                "server_user_id": "server-user-1",
                "auth_me_verified": True,
            },
        )
        os.chmod(private_path, 0o600)
        product_identity = {
            "strategy": "astra_registered_user_per_attempt",
            "identity_id": "astra-fixture-a1",
            "attempt_ordinal": 1,
            "attempt_label": "a1",
            "registration_status": "verified",
            "auth_me_verified": True,
            "username_sha256": hashlib.sha256(username.encode()).hexdigest(),
            "server_user_id_sha256": hashlib.sha256(b"server-user-1").hexdigest(),
            "private_record": "product-identity.private.json",
            "private_record_sha256": sha256_file(private_path),
            "private_record_mode": "0o600",
            "plaintext_password_persisted": True,
            "access_or_refresh_token_persisted": False,
            "true_server_user_identity": True,
            "provider_user_id_is_product_identity": False,
        }
        replacement = missing_observation("orchestrator_scheduling_record", "original_run")
        raw_tool = {
            "name": "local-claim_done",
            "description": "",
            "inputSchema": {"type": "object"},
        }
        astra_tool_name = "mcp__toolathlon__local-claim_done"
        task_tool_names = [astra_tool_name]
        tool_set_sha256 = canonical_json_sha256([raw_tool])
        self._write_json(
            root / "tool-schema-observed.json",
            {
                "schema_version": 1,
                "task_id": "find-alita-paper",
                "gateway": {"url": "http://127.0.0.1:19001/sse"},
                "tool_count": 1,
                "tool_set_sha256": tool_set_sha256,
                "collisions": [],
                "run_qualification": "go",
                "tools": [
                    {
                        "astra_model_visible_tool_name": astra_tool_name,
                        "hermes_model_visible_tool_name": "mcp__toolathlon__local_claim_done",
                        "raw": raw_tool,
                    }
                ],
            },
        )
        self._write_json(
            root / "astra-runtime-mcp-binding.json",
            {
                "schema_version": "toolathlon.astra-runtime-mcp-binding.v1",
                "endpoint": "/chat/stream",
                "runtime_profile": "request_scoped_runtime_mcp",
                "binding": {
                    "id": "toolathlon",
                    "transport": "sse",
                    "url": "http://127.0.0.1:19001/sse",
                    "headers_present": False,
                    "auth_token_present": False,
                },
                "interaction_mode": "auto",
                "expected_mcp_tool_names": task_tool_names,
                "expected_mcp_tool_names_sha256": canonical_json_sha256(
                    task_tool_names
                ),
            },
        )
        self._write_json(
            root / "run.json",
            {
                **identity,
                "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                "artifact_gate": {"status": "passed"},
                "replacement_for_run_id": replacement,
                "run_validity": "valid",
                "adapter": {
                    "product_identity": product_identity,
                    "setup_provider_requests_before_agent": 0,
                    "post_terminal_model_drain": {
                        "settled": True,
                        "provider_requests_forwarded": 1,
                        "provider_requests_completed": 1,
                    },
                },
            },
        )
        self._write_json(
            root / "resolved-config.json",
            {
                **identity,
                "freeze": freeze,
                "adapter": {
                    "tool_set_sha256": tool_set_sha256,
                    "tool_exposure": {
                        "scope": "current_task_attempt_only",
                        "mechanism": "astra_native_request_scoped_runtime_mcp",
                        "gateway_url": "http://127.0.0.1:19001/sse",
                        "mcp_tool_count": 1,
                        "mcp_tool_names_sha256": canonical_json_sha256(
                            task_tool_names
                        ),
                        "all_observed_task_mcp_tools_required": True,
                        "other_task_mcp_tools_allowed": False,
                        "product_builtin_tools_retained": True,
                        "provider_request_tool_names_recorded": True,
                        "binding_artifact": "astra-runtime-mcp-binding.json",
                        "binding_sha256": sha256_file(
                            root / "astra-runtime-mcp-binding.json"
                        ),
                        "astra_endpoint": "/chat/stream",
                        "runtime_profile": "request_scoped_runtime_mcp",
                        "session_strategy": "native_chat_stream_auto_create",
                    },
                    "product_identity": {
                        "attempt_ordinal": 1,
                        "attempt_label": "a1",
                        "strategy": "astra_registered_user_per_attempt",
                        "provider_user_id_is_product_identity": False,
                    }
                },
            },
        )
        self._write_json(
            root / "failure-evidence.json",
            {
                "run_id": "run-1",
                "system_id": "astra",
                "raw_error_code": missing_observation("run_outcome", "no_failure"),
                "evidence_paths": [],
            },
        )
        self._write_json(root / "evaluator/eval_res.json", {"pass": False})
        (root / "evaluator/eval.log").write_text("evaluated\n", encoding="utf-8")
        lifecycle = [
            self._event(name, index)
            for index, name in enumerate(sorted(REQUIRED_LIFECYCLE_EVENTS), start=1)
        ]
        self._write_jsonl(root / "lifecycle-events.jsonl", lifecycle)
        self._write_jsonl(
            root / "adapter-events.jsonl",
            [
                self._event("agent.execution_start", 1),
                self._event("run.finalized", 2),
            ],
        )
        self._write_jsonl(root / "trajectory.jsonl", [])
        self._write_jsonl(root / "tool-calls.jsonl", [])
        missing_provider = missing_observation(
            "provider_response", "provider_not_reported"
        )
        retry_missing = missing_observation(
            "product_event", "product_retry_relation_not_exposed"
        )
        request_tool_names = ["bash", astra_tool_name]
        self._write_jsonl(
            root / "model-usage.jsonl",
            [
                {
                    **self._event("model_request.started", 2),
                    "product_attempt": 1,
                    "model_request_id": "run-1:model:1",
                    "retry_of": retry_missing,
                    "thinking": "enabled",
                    "thinking_wire_behavior": "sent",
                    "reasoning_effort": "max",
                    "reasoning_effort_wire_behavior": "sent",
                    "generation_parameter_source": "benchmark_override",
                    "request_tool_count": len(request_tool_names),
                    "request_tool_names": request_tool_names,
                    "request_tool_names_sha256": canonical_json_sha256(
                        request_tool_names
                    ),
                },
                {
                    **self._event("model_request.completed", 3),
                    "product_attempt": 1,
                    "model_request_id": "run-1:model:1",
                    "retry_of": retry_missing,
                    "finish_reason": missing_provider,
                    "token_usage": {
                        field: dict(missing_provider)
                        for field in (
                            "input_tokens",
                            "output_tokens",
                            "cache_read_tokens",
                            "cache_write_tokens",
                            "total_tokens",
                        )
                    },
                },
            ],
        )
        self._write_jsonl(root / "resource-usage.jsonl", [self._event("sample")])
        files = [
            path
            for path in root.rglob("*")
            if path.is_file() and path.name != "artifacts.sha256"
        ]
        write_sha256_manifest(root / "artifacts.sha256", files, root=root)

    def test_complete_artifact_set_and_hash_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            result = validate_run_artifacts(root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["required_artifacts"], 14)

    def test_null_metric_without_missing_reason_is_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_observation(
                {
                    "value": None,
                    "source": "provider_response",
                    "reliability": "missing",
                    "missing_reason": None,
                },
                "usage.input_tokens",
            )

    def test_astra_transport_normalization_is_complete_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            rows = [
                {
                    "type": "tool_transport_started",
                    "tool": "mcp__toolathlon__local-claim_done",
                    "call_id": "transport-1",
                    "arguments": {},
                },
                {
                    "type": "tool_transport_failed",
                    "tool": "mcp__toolathlon__local-claim_done",
                    "call_id": "transport-1",
                    "success": False,
                    "error": "expected product tool failure",
                },
                {"type": "usage", "tool_call_count": 1},
            ]
            summary = normalize_product_events(
                rows,
                run_id="run-1",
                system_id="astra",
                trajectory_path=root / "trajectory.jsonl",
                tool_calls_path=root / "tool-calls.jsonl",
                observed_tool_manifest={
                    "tools": [
                        {
                            "canonical_tool_name": "local-claim-done",
                            "gateway_tool_name": "local-claim-done",
                            "astra_model_visible_tool_name": (
                                "mcp__toolathlon__local-claim-done"
                            ),
                        }
                    ]
                },
            )
            self.assertEqual(summary["tool_terminal_events"], 1)
            self.assertEqual(summary["tool_failed_events"], 1)
            run = json.loads((root / "run.json").read_text(encoding="utf-8"))
            run["terminal_status"] = "completed"
            run["trajectory"] = summary
            self._write_json(root / "run.json", run)
            self._rehash(root)
            self.assertEqual(validate_run_artifacts(root)["status"], "passed")

            self._write_jsonl(root / "tool-calls.jsonl", [])
            run["trajectory"].update(
                {
                    "tool_started_events": 0,
                    "tool_terminal_events": 0,
                    "tool_failed_events": 0,
                    "started_only_tool_calls": 0,
                }
            )
            self._write_json(root / "run.json", run)
            self._rehash(root)
            with self.assertRaisesRegex(
                ContractError, "native tool transport start has no unique normalized start"
            ):
                validate_run_artifacts(root)


if __name__ == "__main__":
    unittest.main()
