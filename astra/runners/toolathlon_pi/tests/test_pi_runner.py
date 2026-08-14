from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from astra.runners.toolathlon_pi.lifecycle import PiSingleTaskLifecycle
from astra.runners.toolathlon_pi.orchestrator import _add_pi_tool_names, _pi_name
from astra.runners.toolathlon_pi.pi_adapter import (
    PiRuntime,
    _PiStdoutFilter,
    _extract_error,
    _extract_output,
    _normalize_events,
    run_pi,
)
from astra.runners.toolathlon_verified.contract import ContractError
from astra.runners.toolathlon_verified.lifecycle import SingleTaskLifecycle, TASK_IMAGE
from astra.runners.toolathlon_verified.process_control import ProcessResult
from astra.runners.toolathlon_verified.trajectory import (
    normalize_product_events,
    read_json_rows,
)


class PiRunnerTests(unittest.TestCase):
    def test_pi_evaluator_runs_regardless_of_agent_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            permission = root / "permission.json"
            permission.write_text(
                json.dumps({"products": {"astra": {}}}), encoding="utf-8"
            )
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "run": {
                            "permission_policy": str(permission),
                            "system_id": "astra",
                        },
                        "evaluator": {"command": ["container-eval"]},
                    }
                ),
                encoding="utf-8",
            )
            credential_manifest = root / "credential-manifest.runtime.json"
            credential_manifest.write_text("{}\n", encoding="utf-8")
            lifecycle = object.__new__(PiSingleTaskLifecycle)
            lifecycle.credential_manifest_path = credential_manifest

            with patch.dict(
                os.environ,
                {"TOOLATHLON_PI_CREDENTIAL_MANIFEST": str(credential_manifest)},
            ):
                with patch.object(
                    SingleTaskLifecycle, "_write_slot_config", return_value=config_path
                ):
                    lifecycle._write_slot_config(12345)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIn(
                "--evaluate_regardless_of_agent_status",
                config["evaluator"]["command"],
            )
            self.assertEqual(config["run"]["system_id"], "pi")
            self.assertEqual(
                config["credential_manifest"], str(credential_manifest)
            )
            self.assertEqual(
                config["credential_manifest_scope"], "batch_runtime_rebaseline"
            )

    def test_stdout_filter_drops_only_message_updates(self) -> None:
        event_filter = _PiStdoutFilter()
        self.assertIsNone(
            event_filter(b'{"type":"message_update","message":{}}\n')
        )
        retained = b'{"type":"message_end","message":{"type":"message_update"}}\n'
        self.assertEqual(event_filter(retained), retained)
        self.assertEqual(event_filter.dropped_message_updates, 1)

    def test_json_rows_are_read_incrementally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(
                '{"type":"agent_start"}\ninvalid\n{"type":"agent_end"}\n',
                encoding="utf-8",
            )
            rows = read_json_rows(path)
            self.assertNotIsInstance(rows, list)
            self.assertEqual(
                [row["type"] for row in rows], ["agent_start", "agent_end"]
            )

    def test_pi_tool_name_matches_extension_rule(self) -> None:
        self.assertEqual(
            _pi_name("server-tool.name"), "mcp__toolathlon__server-tool_name"
        )

    def test_manifest_adds_pi_names_and_rejects_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "tools.json"
            manifest = {
                "tools": [
                    {"gateway_tool_name": "a-b"},
                    {"gateway_tool_name": "a.b"},
                ]
            }
            names = _add_pi_tool_names(manifest, destination)
            self.assertEqual(
                names, ["mcp__toolathlon__a-b", "mcp__toolathlon__a_b"]
            )
            with self.assertRaises(ContractError):
                _add_pi_tool_names(
                    {
                        "tools": [
                            {"gateway_tool_name": "a.b"},
                            {"gateway_tool_name": "a/b"},
                        ]
                    },
                    destination,
                )

    def test_pi_events_are_normalized_for_shared_trajectory(self) -> None:
        rows = _normalize_events(
            [
                {
                    "type": "tool_execution_start",
                    "toolCallId": "call-1",
                    "toolName": "mcp__toolathlon__x",
                    "args": {"x": 1},
                },
                {
                    "type": "tool_execution_end",
                    "toolCallId": "call-1",
                    "toolName": "mcp__toolathlon__x",
                    "isError": True,
                },
            ]
        )
        self.assertEqual(rows[0]["tool_call_id"], "call-1")
        self.assertEqual(rows[0]["tool_name"], "mcp__toolathlon__x")
        self.assertFalse(rows[1]["success"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = normalize_product_events(
                rows,
                run_id="run",
                system_id="pi",
                trajectory_path=root / "trajectory.jsonl",
                tool_calls_path=root / "tool-calls.jsonl",
            )
            self.assertEqual(summary["tool_started_events"], 1)
            self.assertEqual(summary["tool_terminal_events"], 1)
            self.assertEqual(summary["tool_failed_events"], 1)

    def test_extracts_last_assistant_text(self) -> None:
        output = _extract_output(
            [
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "done"}],
                    },
                }
            ]
        )
        self.assertEqual(output, "done")

    def test_extracts_pi_assistant_error(self) -> None:
        error = _extract_error(
            [
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "stopReason": "error",
                        "errorMessage": "404 proxy_path_not_allowed",
                    },
                }
            ]
        )
        self.assertEqual(error, "404 proxy_path_not_allowed")

    def test_runtime_requires_exact_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "pi"
            executable.write_text("#!/bin/sh\necho 0.73.1\n", encoding="utf-8")
            executable.chmod(0o755)
            with patch.dict(
                os.environ,
                {"TOOLATHLON_PI_EXECUTABLE": str(executable)},
                clear=False,
            ):
                runtime = PiRuntime.load_from_environment()
                self.assertEqual(runtime.executable, executable)
            executable.write_text("#!/bin/sh\necho 0.74.0\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"TOOLATHLON_PI_EXECUTABLE": str(executable)},
                clear=False,
            ):
                with self.assertRaises(ContractError):
                    PiRuntime.load_from_environment()

    def test_adapter_runs_json_mode_to_agent_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "pi"
            executable.write_text(
                "#!/bin/sh\n"
                "if [ \"${1:-}\" = --version ]; then echo 0.73.1; exit 0; fi\n"
                "cp \"$PI_CODING_AGENT_DIR/models.json\" \"$PI_TEST_MODELS\"\n"
                "printf '%s\\n' "
                "'{\"type\":\"agent_start\"}' "
                "'{\"type\":\"message_end\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"done\"}]}}' "
                "'{\"type\":\"agent_end\"}'\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            extension = root / "extension.ts"
            extension.write_text("export default function () {}\n", encoding="utf-8")
            workspace = root / "workspace"
            output = root / "output"
            workspace.mkdir()
            output.mkdir()
            captured_models = root / "models.json"
            captured_argv: list[str] = []

            def fake_monitored_process(argv: object, **kwargs: object) -> ProcessResult:
                captured_argv.extend(argv)  # type: ignore[arg-type]
                stdout_filter = kwargs["stdout_line_filter"]
                self.assertIsNone(  # type: ignore[operator]
                    stdout_filter(b'{"type":"message_update"}\n')
                )
                mount_specs = [
                    captured_argv[index + 1]
                    for index, value in enumerate(captured_argv[:-1])
                    if value == "--mount"
                ]
                state_mount = next(
                    value for value in mount_specs if "dst=/run/pi-state" in value
                )
                state_source = Path(
                    state_mount.split("src=", 1)[1].split(",dst=", 1)[0]
                )
                extension_mount = next(
                    value
                    for value in mount_specs
                    if "dst=/opt/toolathlon_mcp.ts" in value
                )
                extension_source = Path(
                    extension_mount.split("src=", 1)[1].split(",dst=", 1)[0]
                )
                self.assertEqual(extension_source.parent, state_source)
                self.assertEqual(extension_source.stat().st_mode & 0o777, 0o444)
                self.assertEqual(extension_source.read_bytes(), extension.read_bytes())
                captured_models.write_text(
                    (state_source / "agent/models.json").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                self.assertNotIn("PI_CODING_AGENT_DIR", kwargs["env"])  # type: ignore[operator]
                Path(kwargs["stdout_path"]).write_text(  # type: ignore[arg-type]
                    '{"type":"agent_start"}\n'
                    '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"done"}]}}\n'
                    '{"type":"agent_end"}\n',
                    encoding="utf-8",
                )
                return ProcessResult(0, 0.1, "product_exit", 1234, False)

            with patch(
                "astra.runners.toolathlon_pi.pi_adapter.run_monitored_process",
                side_effect=fake_monitored_process,
            ), patch(
                "astra.runners.toolathlon_pi.pi_adapter._remove_pi_container",
                return_value="already_absent",
            ) as cleanup:
                outcome = run_pi(
                    runtime=PiRuntime(executable=executable, extension=extension),
                    public_bundle={
                        "prompt": {"system": "system instruction", "task": "task"}
                    },
                    gateway_url="http://127.0.0.1:1234/sse",
                    workspace=workspace,
                    output_dir=output,
                    proxy_url="http://127.0.0.1:4321/v1",
                    deadline_seconds=30,
                    budget_exceeded=lambda: False,
                    model_request_snapshot=lambda: {
                        "provider_requests_forwarded": 0
                    },
                    task_mcp_tool_names=[],
                )
            cleanup.assert_called_once()
            self.assertEqual(outcome.terminal_status, "completed")
            self.assertEqual(outcome.output, "done")
            self.assertEqual(
                outcome.metadata["native_event_filter"]["dropped_event_count"], 1
            )
            self.assertTrue(outcome.metadata["command"]["no_context_files"])
            self.assertEqual(
                outcome.metadata["command"]["workspace_namespace"],
                {
                    "mode": "docker_sidecar_allowlist",
                    "image": TASK_IMAGE,
                    "container_id": None,
                    "root_filesystem_read_only": True,
                    "linux_capabilities": [],
                    "no_new_privileges": True,
                    "docker_socket_exposed": False,
                    "host_home_exposed": False,
                    "host_tmp_exposed": False,
                    "workspace_host_source": str(workspace),
                    "workspace_mount_mode": "read_write",
                    "runtime_mount_mode": "read_only",
                    "product_cwd": "/workspace/dumps/workspace",
                    "network_mode": "host_for_loopback_gateway_and_proxy",
                    "cleanup_status": "already_absent",
                    "product_pid_source": "not_observed",
                },
            )
            self.assertEqual(captured_argv[:2], ["/usr/bin/docker", "run"])
            self.assertIn("--read-only", captured_argv)
            self.assertIn("--cap-drop", captured_argv)
            self.assertIn("no-new-privileges", captured_argv)
            self.assertIn("--mount", captured_argv)
            mount_specs = [
                captured_argv[index + 1]
                for index, value in enumerate(captured_argv[:-1])
                if value == "--mount"
            ]
            self.assertEqual(len(mount_specs), 4)
            self.assertIn(
                f"type=bind,src={workspace},dst=/workspace/dumps/workspace",
                mount_specs,
            )
            self.assertTrue(
                any("dst=/opt/pi,readonly" in value for value in mount_specs)
            )
            self.assertTrue(
                any(
                    "dst=/opt/toolathlon_mcp.ts,readonly" in value
                    for value in mount_specs
                )
            )
            self.assertFalse(any("docker.sock" in value for value in mount_specs))
            sandbox_preflight = next(
                value
                for value in captured_argv
                if "Pi sandbox exposed forbidden host path" in value
            )
            self.assertIn("/home/vagrant/moi-benchmark", sandbox_preflight)
            self.assertIn("/tmp/toolathlon_src", sandbox_preflight)
            self.assertIn("/var/run/docker.sock", sandbox_preflight)
            prompt_index = captured_argv.index("--append-system-prompt") + 1
            self.assertEqual(captured_argv[prompt_index], "system instruction")
            models = json.loads(captured_models.read_text(encoding="utf-8"))
            self.assertEqual(
                models["providers"]["toolathlon-proxy"]["baseUrl"],
                "http://127.0.0.1:4321/v1",
            )
            self.assertFalse(
                models["providers"]["toolathlon-proxy"]["models"][0]["compat"][
                    "supportsDeveloperRole"
                ]
            )

            def fake_failed_process(_argv: object, **kwargs: object) -> ProcessResult:
                Path(kwargs["stdout_path"]).write_text(  # type: ignore[arg-type]
                    '{"type":"message_end","message":{"role":"assistant","content":[],"stopReason":"error","errorMessage":"provider failed"}}\n'
                    '{"type":"agent_end"}\n',
                    encoding="utf-8",
                )
                return ProcessResult(0, 0.1, "product_exit", 1234, False)

            with patch(
                "astra.runners.toolathlon_pi.pi_adapter.run_monitored_process",
                side_effect=fake_failed_process,
            ), patch(
                "astra.runners.toolathlon_pi.pi_adapter._remove_pi_container",
                return_value="already_absent",
            ):
                failed = run_pi(
                    runtime=PiRuntime(executable=executable, extension=extension),
                    public_bundle={
                        "prompt": {"system": "system instruction", "task": "task"}
                    },
                    gateway_url="http://127.0.0.1:1234/sse",
                    workspace=workspace,
                    output_dir=output,
                    proxy_url="http://127.0.0.1:4321/v1",
                    deadline_seconds=30,
                    budget_exceeded=lambda: False,
                    model_request_snapshot=lambda: {
                        "provider_requests_forwarded": 0
                    },
                    task_mcp_tool_names=[],
                )
            self.assertEqual(failed.terminal_status, "crashed")
            self.assertEqual(failed.error, "provider failed")


if __name__ == "__main__":
    unittest.main()
