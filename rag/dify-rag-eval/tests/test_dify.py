import unittest

from dify_rag_eval.dify import get_path, normalize_contexts


class DifyParsingTests(unittest.TestCase):
    def test_get_path(self):
        self.assertEqual(get_path({"data": {"outputs": {"answer": "ok"}}}, "data.outputs.answer"), "ok")
        self.assertIsNone(get_path({}, "data.outputs.answer"))

    def test_normalize_workflow_contexts(self):
        contexts = normalize_contexts(
            [{"text": "chunk", "metadata": {"document_name": "guide", "score": 0.9}}]
        )
        self.assertEqual(contexts[0]["content"], "chunk")
        self.assertEqual(contexts[0]["document_name"], "guide")


if __name__ == "__main__":
    unittest.main()

