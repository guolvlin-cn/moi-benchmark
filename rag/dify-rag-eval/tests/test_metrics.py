import math
import unittest

from dify_rag_eval.metrics import (
    keyword_recall,
    retrieval_metrics,
    token_f1,
)


class MetricsTests(unittest.TestCase):
    def test_chinese_token_f1(self):
        self.assertGreater(token_f1("Dify 是开源平台", "Dify 是一个开源平台"), 0.7)

    def test_keyword_recall(self):
        self.assertEqual(keyword_recall("一个开源 LLM 应用平台", ["开源", "LLM"]), 1.0)
        self.assertTrue(math.isnan(keyword_recall("answer", [])))

    def test_retrieval_by_document_name(self):
        metrics = retrieval_metrics(
            [{"document_name": "Guide", "content": "x"}],
            {"gold_document_names": ["guide.md"]},
            5,
        )
        self.assertEqual(metrics["retrieval_hit_at_k"], 1.0)
        self.assertEqual(metrics["retrieval_recall_at_k"], 1.0)
        self.assertEqual(metrics["retrieval_precision_at_k"], 1.0)
        self.assertEqual(metrics["mrr"], 1.0)


if __name__ == "__main__":
    unittest.main()
