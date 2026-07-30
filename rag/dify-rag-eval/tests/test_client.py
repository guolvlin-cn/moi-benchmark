import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dify_rag_eval.config import Config, WorkflowConfig
from dify_rag_eval.dify import DifyClient


class MockDifyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get("User-Agent") != "Dify-RAG-Eval/0.1":
            self.send_error(400, "missing evaluator user agent")
            return
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        if self.path == "/v1/chat-messages":
            response = {
                "answer": f"answer: {payload['query']}",
                "message_id": "message-1",
                "metadata": {
                    "usage": {"total_tokens": 10},
                    "retriever_resources": [
                        {
                            "position": 1,
                            "document_name": "Guide",
                            "content": "grounded chunk",
                        }
                    ],
                },
            }
        elif self.path == "/v1/workflows/run":
            response = {
                "workflow_run_id": "run-1",
                "data": {
                    "outputs": {
                        "answer": f"answer: {payload['inputs']['question']}",
                        "contexts": [{"text": "workflow chunk"}],
                    },
                    "total_tokens": 12,
                },
            }
        else:
            self.send_error(404)
            return
        encoded = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        pass


class DifyClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockDifyHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def test_chat_contract(self):
        client = DifyClient(Config(base_url=self.base_url), "test-key")
        response = client.query("hello", case_id="q1", repeat=1, case_inputs={})
        self.assertEqual(response.answer, "answer: hello")
        self.assertEqual(response.contexts[0]["document_name"], "Guide")
        self.assertEqual(response.usage["total_tokens"], 10)

    def test_workflow_contract(self):
        config = Config(
            base_url=self.base_url,
            app_type="workflow",
            workflow=WorkflowConfig(
                query_input="question",
                answer_path="data.outputs.answer",
                contexts_path="data.outputs.contexts",
            ),
        )
        response = DifyClient(config, "test-key").query(
            "hello", case_id="q1", repeat=1, case_inputs={}
        )
        self.assertEqual(response.answer, "answer: hello")
        self.assertEqual(response.contexts[0]["content"], "workflow chunk")
        self.assertEqual(response.ids["workflow_run_id"], "run-1")


if __name__ == "__main__":
    unittest.main()
