from __future__ import annotations

import json
import queue
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from astra.runners.toolathlon_verified.mcp_client import (
    ClassicSseMcpClient,
    build_observed_tool_manifest,
)


class _Gateway:
    def __init__(self) -> None:
        self.messages: "queue.Queue[dict]" = queue.Queue()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                return

            def do_GET(self):  # noqa: N802
                if self.path != "/sse":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(b"event: endpoint\ndata: /messages\n\n")
                self.wfile.flush()
                while True:
                    message = owner.messages.get()
                    if message is None:
                        break
                    payload = json.dumps(message, separators=(",", ":")).encode()
                    self.wfile.write(b"event: message\ndata: " + payload + b"\n\n")
                    self.wfile.flush()

            def do_POST(self):  # noqa: N802
                length = int(self.headers["Content-Length"])
                value = json.loads(self.rfile.read(length))
                method = value.get("method")
                if "id" in value:
                    if method == "initialize":
                        result = {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {"listChanged": False}},
                            "serverInfo": {"name": "mock", "version": "1"},
                        }
                    elif method == "tools/list":
                        result = {
                            "tools": [
                                {
                                    "name": "server-tool-name",
                                    "description": "test",
                                    "inputSchema": {"type": "object", "properties": {}},
                                }
                            ]
                        }
                    else:
                        result = {}
                    owner.messages.put({"jsonrpc": "2.0", "id": value["id"], "result": result})
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/sse"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.messages.put(None)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class McpClientTests(unittest.TestCase):
    def test_list_tools_and_record_product_native_name_difference(self) -> None:
        with _Gateway() as gateway:
            with ClassicSseMcpClient(gateway.url, timeout_s=5) as client:
                initialized, tools = client.list_tools()
            manifest = build_observed_tool_manifest(
                task_id="demo",
                gateway_url=gateway.url,
                initialize_result=initialized,
                tools=tools,
            )
            row = manifest["tools"][0]
            self.assertEqual(row["astra_model_visible_tool_name"], "mcp__toolathlon__server-tool-name")
            self.assertEqual(row["hermes_model_visible_tool_name"], "mcp__toolathlon__server_tool_name")
            self.assertFalse(row["names_equal"])
            self.assertEqual(manifest["run_qualification"], "go")


if __name__ == "__main__":
    unittest.main()
