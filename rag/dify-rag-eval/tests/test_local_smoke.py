import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dify_rag_eval.local_smoke import SmokeContext, redact, run_local_smoke


class MaxKBProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/openapi.json"):
            payload = {"version": "2.10.4-test", "paths": {"/api/application": {}}}
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        self.send_error(404)

    def log_message(self, format, *args):
        pass


class LocalSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MaxKBProbeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def test_redact_masks_nested_credentials_and_bearer_values(self):
        value = redact({"Authorization": "Bearer secret-value", "nested": {"api_key": "sk-real-secret"}})
        self.assertEqual(value["Authorization"], "<redacted>")
        self.assertEqual(value["nested"]["api_key"], "<redacted>")

    def test_maxkb_probe_records_discovery_and_redacts_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            result = run_local_smoke(
                SmokeContext(
                    system_id="maxkb_local",
                    base_url=self.base_url,
                    output=output,
                    api_key="sk-test-secret",
                )
            )

            self.assertEqual(result["service_status"], "ready")
            self.assertEqual(result["ingest_status"], "unsupported")
            self.assertEqual(result["retrieval_status"], "unsupported")
            self.assertEqual(result["native_status"], "unsupported")
            self.assertEqual(result["blocked_reason"], "MISSING_MAXKB_OPENAI_ENDPOINT")
            self.assertTrue(result["artifacts"])
            raw = "\n".join(path.read_text(encoding="utf-8") for path in output.glob("*.json"))
            self.assertNotIn("sk-test-secret", raw)
            self.assertTrue((output / "smoke-result.json").exists() or any("smoke-result" in item for item in result["artifacts"]))


if __name__ == "__main__":
    unittest.main()
