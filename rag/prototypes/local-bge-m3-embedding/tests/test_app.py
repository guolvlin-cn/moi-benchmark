import unittest
from dataclasses import replace

from fastapi.testclient import TestClient

import app as service_app
from engine import EmbeddingEngine


class FakeModel:
    def encode(self, texts, **kwargs):
        return {"dense_vecs": [[0.25, 0.5, 0.75] for _ in texts]}


class APIEndpointTests(unittest.TestCase):
    def setUp(self):
        self.original_settings = service_app.settings
        self.original_engine = service_app.engine
        service_app.settings = replace(service_app.settings, dimension=3, api_key=None)
        service_app.engine = EmbeddingEngine(
            service_app.settings,
            model_factory=lambda: FakeModel(),
        )
        self.client = TestClient(service_app.app)

    def tearDown(self):
        service_app.settings = self.original_settings
        service_app.engine = self.original_engine

    def test_embeddings_response_matches_go_client_contract(self):
        response = self.client.post(
            "/v1/embeddings",
            json={
                "model": "BAAI/bge-m3",
                "input": ["local smoke", "第二条"],
                "encoding_format": "float",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["data"][1]["index"], 1)
        self.assertEqual(payload["data"][0]["embedding"], [0.25, 0.5, 0.75])
        self.assertEqual(payload["model"], "BAAI/bge-m3")

    def test_invalid_encoding_format_is_rejected(self):
        response = self.client.post(
            "/embeddings",
            json={"input": "local smoke", "encoding_format": "base64"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "invalid_request_error")


if __name__ == "__main__":
    unittest.main()
