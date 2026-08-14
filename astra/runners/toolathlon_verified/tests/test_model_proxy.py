from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from astra.runners.toolathlon_verified.model_proxy import (
    ModelProxyConfig,
    ModelProxyServer,
    RequestBudget,
    load_distinct_provider_credentials,
    provider_credential_fingerprint,
    provider_user_id,
)
from astra.runners.toolathlon_verified.contract import ContractError


class _Upstream:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.authorizations: list[str] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers["Content-Length"])
                owner.requests.append(json.loads(self.rfile.read(length)))
                owner.authorizations.append(self.headers.get("Authorization", ""))
                payload = json.dumps(
                    {
                        "id": "response",
                        "choices": [
                            {"message": {"content": "ok"}, "finish_reason": "stop"}
                        ],
                        "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("x-request-id", "provider-header-id")
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class ModelProxyTests(unittest.TestCase):
    def test_proxy_enforces_frozen_wire_parameters_and_hides_provider_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory, _Upstream() as upstream:
            root = Path(directory)
            key = "provider-key-never-forwarded-from-product"
            config = ModelProxyConfig(
                upstream_base_url=upstream.url,
                upstream_api_key=key,
                effective_model="deepseek-v4-flash",
                temperature=0,
                thinking="enabled",
                reasoning_effort="max",
                max_requests=100,
                run_id="run-1",
                system_id="astra",
                events_path=root / "events.jsonl",
                state_path=root / "state.json",
            )
            with ModelProxyServer(config) as proxy:
                payload = json.dumps(
                    {
                        "model": "different-model",
                        "messages": [{"role": "user", "content": "hello"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "mcp__toolathlon__local-claim_done",
                                    "parameters": {"type": "object"},
                                },
                            }
                        ],
                        "temperature": 1,
                        "top_p": 0.2,
                        "reasoning_effort": "low",
                        "thinking": {"type": "disabled"},
                        "user_id": "product-controlled-id",
                        "extra_body": {
                            "user_id": "product-controlled-nested-id",
                            "preserved": "yes",
                        },
                    }
                ).encode()
                request = urllib.request.Request(
                    proxy.url + "/chat/completions",
                    data=payload,
                    headers={
                        "Authorization": "Bearer untrusted-product-key",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    response.read()
            forwarded = upstream.requests[0]
            self.assertEqual(forwarded["model"], "deepseek-v4-flash")
            self.assertEqual(forwarded["temperature"], 0)
            self.assertNotIn("top_p", forwarded)
            self.assertEqual(forwarded["reasoning_effort"], "max")
            self.assertEqual(forwarded["thinking"], {"type": "enabled"})
            self.assertEqual(forwarded["user_id"], provider_user_id("astra", "run-1"))
            self.assertEqual(forwarded["extra_body"], {"preserved": "yes"})
            self.assertEqual(upstream.authorizations, [f"Bearer {key}"])
            self.assertNotIn(key, (root / "events.jsonl").read_text())
            events = [
                json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()
            ]
            completed = next(
                event for event in events if event["event"] == "model_request.completed"
            )
            started = next(
                event for event in events if event["event"] == "model_request.started"
            )
            self.assertEqual(started["request_tool_count"], 1)
            self.assertEqual(started["thinking"], "enabled")
            self.assertEqual(started["thinking_wire_behavior"], "sent")
            self.assertEqual(started["reasoning_effort"], "max")
            self.assertEqual(started["reasoning_effort_wire_behavior"], "sent")
            self.assertEqual(
                started["generation_parameter_source"], "benchmark_override"
            )
            self.assertEqual(
                started["request_tool_names"],
                ["mcp__toolathlon__local-claim_done"],
            )
            self.assertEqual(completed["model_request_id"], "run-1:model:1")
            self.assertEqual(completed["provider_response_id"]["value"], "response")
            self.assertEqual(
                completed["provider_header_request_id"]["value"],
                "provider-header-id",
            )
            self.assertEqual(completed["finish_reasons"], ["stop"])
            self.assertEqual(
                completed["token_usage"]["input_tokens"]["value"], 2
            )
            self.assertEqual(
                completed["token_usage"]["output_tokens"]["value"], 1
            )
            self.assertEqual(
                completed["token_usage"]["cache_write_tokens"],
                {
                    "value": None,
                    "source": "provider_response",
                    "reliability": "missing",
                    "missing_reason": "provider_not_reported",
                },
            )
            self.assertEqual(
                completed["retry_of"]["missing_reason"],
                "product_retry_relation_not_exposed",
            )
            ready = next(event for event in events if event["event"] == "proxy.ready")
            self.assertEqual(
                ready["provider_credential_fingerprint"],
                provider_credential_fingerprint(key),
            )
            self.assertEqual(ready["provider_user_id"], provider_user_id("astra", "run-1"))

    def test_request_budget_allows_exactly_the_frozen_number(self) -> None:
        credentials = load_distinct_provider_credentials(
            {
                "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY": "astra-key-0000000",
                "TOOLATHLON_DEEPSEEK_HERMES_API_KEY": "hermes-key-000000",
            }
        )
        self.assertEqual(
            credentials,
            {"astra": "astra-key-0000000", "hermes": "hermes-key-000000"},
        )
        with self.assertRaises(ContractError):
            load_distinct_provider_credentials(
                {
                    "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY": "shared-key-000000",
                    "TOOLATHLON_DEEPSEEK_HERMES_API_KEY": "shared-key-000000",
                }
            )
        with self.assertRaises(ContractError):
            load_distinct_provider_credentials(
                {
                    "DEEPSEEK_API_KEY": "legacy-shared-key",
                    "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY": "astra-key-0000000",
                    "TOOLATHLON_DEEPSEEK_HERMES_API_KEY": "hermes-key-000000",
                }
            )
        budget = RequestBudget(2)
        first = budget.reserve()
        second = budget.reserve()
        self.assertTrue(first[0])
        self.assertTrue(second[0])
        self.assertFalse(budget.exceeded.is_set())
        budget.finish(provider_request=first[2], success=True)
        self.assertFalse(budget.exceeded.is_set())
        budget.finish(provider_request=second[2], success=True)
        self.assertTrue(budget.exceeded.is_set())
        self.assertFalse(budget.reserve()[0])
        self.assertTrue(budget.exceeded.is_set())
        self.assertEqual(budget.snapshot()["provider_requests_forwarded"], 2)


if __name__ == "__main__":
    unittest.main()
