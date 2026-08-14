from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from astra.runners.toolathlon_verified.astra_adapter import (
    ASTRA_RUNTIME_MCP_BINDING_FILENAME,
    AstraRuntime,
    run_astra,
)
from astra.runners.toolathlon_verified.astra_runtime_mcp_client import (
    _request_body,
    _validate_loopback_api_url,
)
from astra.runners.toolathlon_verified.contract import ContractError, sha256_file
from astra.runners.toolathlon_verified.hermes_adapter import (
    HermesRuntime,
    _wait_for_model_requests_to_settle,
    run_hermes,
)
from astra.runners.toolathlon_verified.permissions import PermissionPolicy
from astra.runners.toolathlon_verified.process_control import ProcessResult
from astra.runners.toolathlon_verified.product_identity import PRIVATE_IDENTITY_FILENAME


PUBLIC_BUNDLE = {
    "prompt": {"system": "same system prompt", "task": "same task prompt"},
}


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class AdapterTests(unittest.TestCase):
    def test_astra_adapter_uses_native_request_scoped_runtime_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output = root / "output"
            state_root = root / "state"
            workspace.mkdir()
            output.mkdir()
            state_root.mkdir()
            executable = root / "fake-astra"
            _write_executable(
                executable,
                """#!/usr/bin/env python3
import json, os, sys
if any(os.environ.get(name) for name in ('OPENAI_API_KEY', 'TOOLATHLON_DEEPSEEK_ASTRA_API_KEY', 'TOOLATHLON_DEEPSEEK_HERMES_API_KEY', 'ASTRA_ACCESS_TOKEN', 'ASTRA_ADMIN_ACCESS_TOKEN')):
    raise SystemExit(13)
if 'admin' in sys.argv and 'update' in sys.argv and '--api-key' in sys.argv:
    raise SystemExit(14)
if '--help' in sys.argv:
    print('Run a one-shot chat request')
    raise SystemExit(0)
prompt = sys.stdin.read()
print(json.dumps({"type":"tool_started","tool_name":"mcp__toolathlon__local-claim_done","tool_call_id":"c1","arguments":{}}), file=sys.stderr)
print(json.dumps({"type":"tool_completed","tool_name":"mcp__toolathlon__local-claim_done","tool_call_id":"c1"}), file=sys.stderr)
print(json.dumps({"output":"done:" + prompt}))
""",
            )
            runtime_path = root / "runtime.json"
            executable_hash = sha256_file(executable)
            runtime_path.write_text(
                json.dumps(
                    {
                        "source_commit": "844473c68649d8ea43e10b616dc4fbf98e2321e8",
                        "source_tree": "bfd88d2fe30ad7a04b2611a42c70d5dc993280bf",
                        "executable": str(executable),
                        "executable_sha256": executable_hash,
                        "server_executable": str(executable),
                        "server_executable_sha256": executable_hash,
                        "api_url": "http://127.0.0.1:17001",
                        "server_mode": "shared_frozen_loopback",
                        "configure_model": True,
                    }
                ),
                encoding="utf-8",
            )
            registered: dict[str, str] = {}
            task_mcp_tools = ["mcp__toolathlon__local-claim_done"]
            runtime_binding = output / ASTRA_RUNTIME_MCP_BINDING_FILENAME
            runtime_binding.write_text(
                json.dumps(
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
                        "expected_mcp_tool_names": task_mcp_tools,
                        "expected_mcp_tool_names_sha256": (
                            "5da8c8e46483c6f1690954b56d7aeecf049101c554b81e66cea9958b8c46f2de"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            request_body = _request_body(
                SimpleNamespace(
                    gateway_url="http://127.0.0.1:19001/sse",
                    model="deepseek-v4-flash",
                ),
                "same system prompt",
                "same task prompt",
            )
            self.assertEqual(_validate_loopback_api_url("http://localhost:17001/"), "http://localhost:17001")
            self.assertEqual(request_body["message"], "same task prompt")
            self.assertEqual(request_body["runtime_system_prompt"], "same system prompt")
            self.assertEqual(request_body["runtime_profile"], "request_scoped_runtime_mcp")
            self.assertEqual(
                request_body["runtime_mcp_bindings"],
                [
                    {
                        "id": "toolathlon",
                        "transport": "sse",
                        "url": "http://127.0.0.1:19001/sse",
                    }
                ],
            )
            self.assertEqual(request_body["interaction_mode"], "auto")
            self.assertFalse(request_body["interactive_client"])
            self.assertNotIn("session_id", request_body)

            def identity_api(method: str, _url: str, **kwargs: object):
                if method == "POST":
                    body = kwargs["body"]
                    assert isinstance(body, dict)
                    registered.update(username=str(body["username"]), email=str(body["email"]))
                    return 201, {
                        "user_id": "server-user-1",
                        "username": registered["username"],
                        "email": registered["email"],
                        "access_token": "attempt-access-token",
                        "refresh_token": "must-not-persist",
                    }
                return 200, {
                    "user_id": "server-user-1",
                    "username": registered["username"],
                    "email": registered["email"],
                }

            captured_process: dict[str, object] = {}

            def fake_monitored_process(argv: object, **kwargs: object) -> ProcessResult:
                environment = kwargs["env"]
                assert isinstance(environment, dict)
                self.assertEqual(
                    environment.get("ASTRA_ACCESS_TOKEN"), "attempt-access-token"
                )
                for name in (
                    "OPENAI_API_KEY",
                    "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY",
                    "TOOLATHLON_DEEPSEEK_HERMES_API_KEY",
                    "ASTRA_ADMIN_ACCESS_TOKEN",
                ):
                    self.assertNotIn(name, environment)
                request_input = json.loads(kwargs["stdin_payload"])
                captured_process.update(argv=list(argv), request_input=request_input)
                stdout_path = kwargs["stdout_path"]
                stderr_path = kwargs["stderr_path"]
                assert isinstance(stdout_path, Path)
                assert isinstance(stderr_path, Path)
                stdout_path.write_text(
                    json.dumps(
                        {
                            "success": True,
                            "error": None,
                            "response": "done:same task prompt",
                            "session_id": "server-created-session-1",
                        }
                    ),
                    encoding="utf-8",
                )
                events = [
                    {
                        "type": "run_started",
                        "session_id": "server-created-session-1",
                    },
                    {
                        "type": "tool_call_start",
                        "tool": "mcp__toolathlon__local-claim_done",
                        "call_id": "c1",
                        "arguments": {},
                    },
                    {"type": "tool_call_end", "call_id": "c1", "result": "ok"},
                    {"type": "text_done", "full_text": "done:same task prompt"},
                    {
                        "type": "turn_complete",
                        "assistant_text": "done:same task prompt",
                    },
                    {"type": "done"},
                ]
                stderr_path.write_text(
                    "".join(json.dumps(row) + "\n" for row in events),
                    encoding="utf-8",
                )
                on_start = kwargs.get("on_start")
                if callable(on_start):
                    on_start(1234)
                on_agent_start = kwargs.get("on_agent_start")
                if callable(on_agent_start):
                    on_agent_start()
                return ProcessResult(0, 0.1, "product_exit", 1234, False)

            with patch(
                "astra.runners.toolathlon_verified.product_identity._request_json",
                side_effect=identity_api,
            ), patch(
                "astra.runners.toolathlon_verified.astra_adapter.run_monitored_process",
                side_effect=fake_monitored_process,
            ), patch.dict(
                os.environ,
                {
                    "ASTRA_ACCESS_TOKEN": "test-token",
                    "ASTRA_ADMIN_ACCESS_TOKEN": "test-admin-token",
                    "OPENAI_API_KEY": "must-strip",
                    "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY": "astra-must-strip",
                    "TOOLATHLON_DEEPSEEK_HERMES_API_KEY": "hermes-must-strip",
                },
                clear=False,
            ):
                outcome = run_astra(
                    runtime=AstraRuntime.load(runtime_path),
                    public_bundle=PUBLIC_BUNDLE,
                    gateway_url="http://127.0.0.1:19001/sse",
                    workspace=workspace,
                    output_dir=output,
                    proxy_url="http://127.0.0.1:19002/v1",
                    deadline_seconds=10,
                    budget_exceeded=lambda: False,
                    model_request_snapshot=lambda: {
                        "provider_requests_forwarded": 0
                    },
                    experiment_id="exp-1",
                    task_id="find-alita-paper",
                    run_id="run-a1",
                    attempt_ordinal=1,
                    runtime_mcp_binding_path=runtime_binding,
                    task_mcp_tool_names=task_mcp_tools,
                    ephemeral_root=state_root,
                )
            self.assertEqual(outcome.terminal_status, "completed")
            self.assertEqual(outcome.output, "done:same task prompt")
            self.assertEqual(len(outcome.native_events), 6)
            self.assertEqual(
                outcome.metadata["server_session"],
                {
                    "strategy": "native_chat_stream_auto_create",
                    "requested_session_id": None,
                    "observed_session_id": "server-created-session-1",
                },
            )
            self.assertEqual(
                captured_process["request_input"],
                {"system": "same system prompt", "task": "same task prompt"},
            )
            process_argv = captured_process["argv"]
            self.assertIn("--gateway-url", process_argv)
            self.assertIn("http://127.0.0.1:19001/sse", process_argv)
            self.assertNotIn("--session-id", process_argv)
            argv = outcome.metadata["command"]["argv_without_prompt"]
            self.assertIn("<astra-api-client>", argv)
            self.assertEqual(
                outcome.metadata["command"]["task_tool_exposure"]["mcp_tool_count"],
                1,
            )
            self.assertFalse(
                outcome.metadata["command"]["task_tool_exposure"][
                    "other_task_mcp_tools_allowed"
                ]
            )
            self.assertEqual(
                outcome.metadata["model_registration"]["action"],
                "update_without_probe",
            )
            self.assertEqual(outcome.metadata["setup_provider_requests_before_agent"], 0)
            private_path = output / PRIVATE_IDENTITY_FILENAME
            private = json.loads(private_path.read_text())
            self.assertEqual(private["registration_status"], "verified")
            self.assertEqual(private["username"], registered["username"])
            self.assertTrue(private["password"])
            self.assertNotIn("access_token", private)
            self.assertNotIn("refresh_token", private)
            self.assertEqual(stat.S_IMODE(private_path.stat().st_mode), 0o600)
            self.assertTrue(outcome.metadata["product_identity"]["auth_me_verified"])
            self.assertEqual(list(state_root.iterdir()), [])

            blocked_output = root / "blocked-output"
            blocked_output.mkdir()
            blocked_binding = blocked_output / ASTRA_RUNTIME_MCP_BINDING_FILENAME
            blocked_binding.write_bytes(runtime_binding.read_bytes())
            with patch(
                "astra.runners.toolathlon_verified.product_identity._request_json",
                side_effect=identity_api,
            ), patch.dict(
                os.environ,
                {"ASTRA_ADMIN_ACCESS_TOKEN": "test-admin-token"},
                clear=False,
            ), self.assertRaises(ContractError):
                run_astra(
                    runtime=AstraRuntime.load(runtime_path),
                    public_bundle=PUBLIC_BUNDLE,
                    gateway_url="http://127.0.0.1:19001/sse",
                    workspace=workspace,
                    output_dir=blocked_output,
                    proxy_url="http://127.0.0.1:19002/v1",
                    deadline_seconds=10,
                    budget_exceeded=lambda: False,
                    model_request_snapshot=lambda: {
                        "provider_requests_forwarded": 1
                    },
                    experiment_id="exp-1",
                    task_id="find-alita-paper",
                    run_id="run-a2",
                    attempt_ordinal=2,
                    runtime_mcp_binding_path=blocked_binding,
                    task_mcp_tool_names=task_mcp_tools,
                    ephemeral_root=state_root,
                )

    def test_hermes_adapter_drives_gateway_runs_api_without_yolo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            workspace = root / "workspace"
            output = root / "output"
            state_root = root / "state"
            for path in (source, workspace, output, state_root):
                path.mkdir()
            server = root / "fake_hermes.py"
            server.write_text(
                """import json, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
if any(os.environ.get(name) for name in ('OPENAI_API_KEY', 'TOOLATHLON_DEEPSEEK_ASTRA_API_KEY', 'TOOLATHLON_DEEPSEEK_HERMES_API_KEY')):
    raise SystemExit(13)
port = int(os.environ['API_SERVER_PORT'])
time.sleep(1.2)
class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def send_json(self, status, value):
        data=json.dumps(value).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == '/health': self.send_json(200, {'status':'ok'}); return
        if self.path.endswith('/events'):
            data=b'data: {"event":"run.completed","run_id":"run_mock","output":"done"}\\n\\n'
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        if self.path == '/v1/runs/run_mock': self.send_json(200, {'status':'completed','output':'done','usage':{}}); return
        self.send_json(404,{})
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0')); self.rfile.read(n)
        if self.path == '/v1/runs': self.send_json(202, {'run_id':'run_mock','status':'started'}); return
        self.send_json(200, {'status':'ok'})
ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
""",
                encoding="utf-8",
            )
            runtime_path = root / "runtime.json"
            environment_manifest = root / "hermes-environment.json"
            environment_manifest.write_text("{}\n", encoding="utf-8")
            runtime_path.write_text(
                json.dumps(
                    {
                        "source_commit": "f4df260f26c93f15694698869f3ea8e965eea301",
                        "source_tree": "40f0136a9995a9a1712a3ab28c231a2812748cdf",
                        "source_dir": str(source),
                        "command": [sys.executable, str(server)],
                        "executable_sha256": sha256_file(Path(sys.executable)),
                        "environment_manifest": str(environment_manifest),
                        "environment_manifest_sha256": sha256_file(environment_manifest),
                        "gateway_startup_timeout_seconds": 10,
                    }
                ),
                encoding="utf-8",
            )
            policy_path = root / "permission.json"
            gateway_url = "http://127.0.0.1:19001/sse"
            policy_path.write_text(
                json.dumps(
                    {
                        "policy_id": "task-scoped-v1",
                        "task_scope": {"gateway_url": gateway_url, "workspace": str(workspace)},
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
                policy_path,
                expected_gateway_url=gateway_url,
                expected_workspace=workspace,
            )
            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "must-strip",
                    "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY": "astra-must-strip",
                    "TOOLATHLON_DEEPSEEK_HERMES_API_KEY": "hermes-must-strip",
                },
                clear=False,
            ):
                outcome = run_hermes(
                    runtime=HermesRuntime.load(runtime_path),
                    public_bundle=PUBLIC_BUNDLE,
                    gateway_url=gateway_url,
                    workspace=workspace,
                    output_dir=output,
                    proxy_url="http://127.0.0.1:19002/v1",
                    permission_policy=policy,
                    # Gateway startup is an infrastructure phase and must not
                    # consume this one-second Agent execution window.
                    deadline_seconds=1,
                    budget_exceeded=lambda: False,
                    model_request_snapshot=lambda: {
                        "provider_requests_forwarded": 0,
                        "provider_requests_completed": 0,
                    },
                    ephemeral_root=state_root,
                )
            self.assertEqual(outcome.terminal_status, "completed")
            self.assertEqual(outcome.output, "done")
            self.assertFalse(outcome.metadata["permission"]["yolo"])
            identity = outcome.metadata["product_identity"]
            self.assertTrue(identity["fresh_hermes_home"])
            self.assertTrue(identity["fresh_gateway_process"])
            self.assertEqual(identity["memory_provider"], "")
            self.assertFalse(identity["true_server_user_identity"])
            self.assertEqual(outcome.metadata["setup_provider_requests_before_agent"], 0)
            self.assertTrue(outcome.metadata["post_terminal_model_drain"]["settled"])
            evidence = (output / "hermes-policy-guard.jsonl").read_text()
            self.assertIn("policy_guard.loaded", evidence)
            self.assertNotIn("toolathlon-run-proxy", evidence)
            self.assertEqual(list(state_root.iterdir()), [])

            snapshots = iter(
                [
                    {
                        "provider_requests_forwarded": 1,
                        "provider_requests_completed": 0,
                    },
                    {
                        "provider_requests_forwarded": 1,
                        "provider_requests_completed": 1,
                    },
                ]
            )
            drained = _wait_for_model_requests_to_settle(
                lambda: next(snapshots),
                timeout_seconds=1,
                quiet_seconds=0,
                poll_seconds=0,
            )
            self.assertTrue(drained["settled"])
            self.assertEqual(drained["provider_requests_completed"], 1)


if __name__ == "__main__":
    unittest.main()
