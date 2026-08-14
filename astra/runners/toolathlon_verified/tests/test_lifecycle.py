from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from astra.runners.toolathlon_verified.lifecycle import (
    LifecycleError,
    SingleTaskLifecycle,
    is_runtime_mutable_credential_record,
    load_task_reset_contract,
)


class LifecycleTests(unittest.TestCase):
    def test_formal_task_contract_accepts_shared_application_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "tasks/finalpool/set-conf-cr-ddl"
            (task / "preprocess").mkdir(parents=True)
            config = b'{"task":"set-conf-cr-ddl"}\n'
            (task / "task_config.json").write_bytes(config)
            (task / "preprocess/main.py").write_text("pass\n", encoding="utf-8")
            requirements = root / "task-requirements.json"
            requirements.write_text(
                json.dumps(
                    {
                        "tasks": {
                            "set-conf-cr-ddl": {
                                "task_config_sha256": hashlib.sha256(config).hexdigest(),
                                "mcp_servers": ["emails", "google_calendar"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            contract = load_task_reset_contract(
                task_id="set-conf-cr-ddl",
                task_source=task,
                requirements_path=requirements,
            )

            self.assertEqual(
                contract["required_mcp_servers"], ["emails", "google_calendar"]
            )
            self.assertTrue(contract["task_preprocess_present"])
            self.assertTrue(
                is_runtime_mutable_credential_record(
                    {
                        "category": "mcp_oauth",
                        "path": "configs/.mcp-auth/version/example_tokens.json",
                        "content_policy": "runtime_refreshable_oauth_token",
                        "runtime_mutable": True,
                    }
                )
            )
            self.assertFalse(
                is_runtime_mutable_credential_record(
                    {
                        "category": "mcp_oauth",
                        "path": "configs/gcp-oauth.keys.json",
                        "content_policy": "runtime_refreshable_oauth_token",
                        "runtime_mutable": True,
                    }
                )
            )

            configs = root / "configs"
            configs.mkdir()
            for name in ("gcp-oauth.keys.json", "google_credentials.json"):
                (configs / name).write_text("test-only\n", encoding="utf-8")
            freeze = root / "freeze"
            freeze.mkdir()
            (freeze / "credential-manifest.json").write_text(
                json.dumps(
                    {
                        "toolathlon_application_credentials": {
                            "files": [
                                {"path": "configs/gcp-oauth.keys.json"},
                                {"path": "configs/google_credentials.json"},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            lifecycle = object.__new__(SingleTaskLifecycle)
            lifecycle.lifecycle = type(
                "Events", (), {"append": lambda self, *args, **kwargs: None}
            )()
            lifecycle.task_reset_contract = {
                "required_mcp_servers": ["emails", "google_calendar"]
            }
            lifecycle.freeze = freeze
            lifecycle.source = root
            lifecycle.container_name = "test-container"
            commands: list[tuple[str, ...]] = []
            lifecycle._docker = lambda *args, **kwargs: commands.append(args)

            lifecycle._install_container_credential_layout()

            copied_targets = {
                command[-1]
                for command in commands
                if command[:3] == ("exec", "test-container", "cp")
            }
            self.assertEqual(
                copied_targets,
                {
                    "/root/.gmail-mcp/gcp-oauth.keys.json",
                    "/root/.gmail-mcp/credentials.json",
                    "/root/.calendar-mcp/gcp-oauth.keys.json",
                    "/root/.calendar-mcp/credentials.json",
                },
            )

    def test_task_config_drift_is_rejected_before_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "tasks/finalpool/example"
            task.mkdir(parents=True)
            (task / "task_config.json").write_text("{}\n", encoding="utf-8")
            requirements = root / "task-requirements.json"
            requirements.write_text(
                json.dumps(
                    {
                        "tasks": {
                            "example": {
                                "task_config_sha256": "0" * 64,
                                "mcp_servers": [],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(LifecycleError, "does not match the freeze"):
                load_task_reset_contract(
                    task_id="example",
                    task_source=task,
                    requirements_path=requirements,
                )


if __name__ == "__main__":
    unittest.main()
