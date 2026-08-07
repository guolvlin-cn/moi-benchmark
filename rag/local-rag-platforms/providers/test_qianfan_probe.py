import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("qianfan_probe", HERE / "qianfan_probe.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class QianfanProbeTest(unittest.TestCase):
    def test_embedding_dimension(self):
        payload = {"data": [{"embedding": [0.0, 1.0]}]}
        self.assertEqual(MODULE.validate_embedding(payload, 2), 2)

    def test_embedding_dimension_mismatch_fails(self):
        with self.assertRaises(MODULE.ProbeError):
            MODULE.validate_embedding({"data": [{"embedding": [0.0]}]}, 2)

    def test_embedding_rejects_non_finite_values(self):
        with self.assertRaises(MODULE.ProbeError):
            MODULE.validate_embedding({"data": [{"embedding": [float("nan")]}]}, 1)

    def test_chat_requires_content(self):
        self.assertTrue(MODULE.validate_chat({"choices": [{"message": {"content": "OK"}}]}))
        with self.assertRaises(MODULE.ProbeError):
            MODULE.validate_chat({"choices": []})

    def test_models_require_both_capabilities(self):
        payload = {"data": [
            {"id": "chat", "type": "chat"},
            {"id": "embed", "type": "embeddings"},
            {"id": "rerank", "type": "reranker"},
        ]}
        self.assertEqual(MODULE.validate_models(payload, "chat", "embed", "rerank")["embed"], "embeddings")
        with self.assertRaises(MODULE.ProbeError):
            MODULE.validate_models(payload, "missing", "embed", "rerank")

    def test_rerank_requires_results(self):
        self.assertEqual(MODULE.validate_rerank({"results": [{"index": 0}]}), 1)
        with self.assertRaises(MODULE.ProbeError):
            MODULE.validate_rerank({"results": []})


if __name__ == "__main__":
    unittest.main()
