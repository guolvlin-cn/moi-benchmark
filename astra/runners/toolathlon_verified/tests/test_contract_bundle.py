from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astra.runners.toolathlon_verified.bundle import build_public_bundle
from astra.runners.toolathlon_verified.contract import ContractError, ModelFreeze, RunSpec
from astra.runners.toolathlon_verified.permissions import PermissionPolicy


class ContractBundleTests(unittest.TestCase):
    def test_public_bundle_excludes_private_fields_and_preserves_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            bundle = root / "trusted.json"
            bundle.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "task_dir": "daily/demo-task",
                        "task_str": "Do the task exactly.",
                        "system_prompts": {"agent": "Frozen agent prompt", "user": "private"},
                        "needed_mcp_servers": ["filesystem"],
                        "needed_local_tools": ["claim_done"],
                        "stop": {"user_phrases": [], "tool_names": ["local-claim_done"]},
                        "eval_config": {"api_key": "must-not-escape"},
                        "ground_truth": "must-not-escape",
                        "local_token_key_session": "must-not-escape",
                    }
                ),
                encoding="utf-8",
            )
            public = build_public_bundle(
                bundle,
                expected_task_id="demo-task",
                workspace=workspace,
            )
            serialized = json.dumps(public)
            self.assertEqual(public["prompt"]["system"], "Frozen agent prompt")
            self.assertEqual(public["prompt"]["task"], "Do the task exactly.")
            self.assertNotIn("must-not-escape", serialized)
            self.assertNotIn("eval_config", serialized)

    def test_bundle_task_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            bundle = root / "trusted.json"
            bundle.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "task_dir": "x/a",
                        "task_str": "task",
                        "system_prompts": {"agent": "system"},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ContractError):
                build_public_bundle(bundle, expected_task_id="b", workspace=workspace)

            model = root / "model.json"
            requirements = root / "requirements.json"
            permission = root / "permission.json"
            for path in (model, requirements, permission):
                path.write_text("{}\n", encoding="utf-8")
            output = root / "output"
            output.mkdir()
            for name in (
                "lifecycle-events.jsonl",
                "resource-usage.jsonl",
                "preprocess.log",
                "permission-policy.json",
            ):
                (output / name).write_text("prepared\n", encoding="utf-8")
            (output / "task-state").mkdir()
            spec = RunSpec.from_dict(
                {
                    "system_id": "astra",
                    "experiment_id": "exp-1",
                    "run_id": "run-1",
                    "task_id": "task-1",
                    "bundle_file": str(bundle),
                    "gateway_url": "http://127.0.0.1:19001/sse",
                    "workspace": str(workspace),
                    "output_dir": str(output),
                    "deadline_s": 1800,
                    "max_model_requests": 100,
                    "model_freeze": str(model),
                    "task_requirements_manifest": str(requirements),
                    "permission_policy": str(permission),
                }
            )
            self.assertEqual(spec.output_dir, output.resolve())

    def test_model_freeze_requires_approved_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_text(
                json.dumps(
                    {
                        "endpoint": {
                            "provider": "deepseek",
                            "base_url": "https://api.deepseek.com",
                        },
                        "model": {
                            "request_id": "deepseek-v4-flash",
                            "documented_version": "DeepSeek-V4-Flash-0731",
                        },
                        "generation": {
                            "temperature": {"value": 0},
                            "thinking": {
                                "value": "enabled",
                                "wire_behavior": "sent",
                            },
                            "reasoning_effort": {
                                "value": "max",
                                "wire_behavior": "sent",
                            },
                        },
                        "request_budget": {"max_product_model_requests": 100},
                    }
                ),
                encoding="utf-8",
            )
            freeze = ModelFreeze.load(path)
            self.assertEqual(freeze.temperature, 0)
            self.assertEqual(freeze.thinking, "enabled")
            self.assertEqual(freeze.reasoning_effort, "max")

    def test_permission_policy_denies_unresolved_shell_and_allows_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            path = root / "permission.json"
            gateway = "http://127.0.0.1:12345/sse"
            path.write_text(
                json.dumps(
                    {
                        "policy_id": "task-scoped-v1",
                        "task_scope": {"gateway_url": gateway, "workspace": str(workspace)},
                        "products": {
                            "astra": {"permission_mode": "auto"},
                            "hermes": {"approval_mode": "smart"},
                        },
                        "unresolved_approval_action": "deny",
                    }
                ),
                encoding="utf-8",
            )
            policy = PermissionPolicy.load(
                path,
                expected_gateway_url=gateway,
                expected_workspace=workspace,
            )
            self.assertEqual(
                policy.decide_hermes_approval({"tool_name": "mcp__toolathlon__x"}).choice,
                "once",
            )
            self.assertEqual(
                policy.decide_hermes_approval(
                    {"tool_name": "terminal", "command": "touch allowed"}
                ).choice,
                "deny",
            )


if __name__ == "__main__":
    unittest.main()
