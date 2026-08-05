import unittest
from dataclasses import replace

from engine import (
    EmbeddingEngine,
    EmbeddingInputError,
    EmbeddingOutputError,
    Settings,
    normalize_inputs,
    vectors_to_rows,
)


class FakeModel:
    def __init__(self, dimension):
        self.dimension = dimension
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        return {
            "dense_vecs": [
                [float(index + 1)] * self.dimension for index, _ in enumerate(texts)
            ]
        }


class EngineTests(unittest.TestCase):
    def test_normalize_inputs_accepts_single_and_batch(self):
        self.assertEqual(normalize_inputs("hello", max_batch=2, max_batch_bytes=100), ["hello"])
        self.assertEqual(
            normalize_inputs(["hello", "世界"], max_batch=2, max_batch_bytes=100),
            ["hello", "世界"],
        )

    def test_normalize_inputs_rejects_invalid_payload(self):
        with self.assertRaises(EmbeddingInputError):
            normalize_inputs([], max_batch=2, max_batch_bytes=100)
        with self.assertRaises(EmbeddingInputError):
            normalize_inputs([""], max_batch=2, max_batch_bytes=100)
        with self.assertRaises(EmbeddingInputError):
            normalize_inputs(["12345"], max_batch=2, max_batch_bytes=4)

    def test_vectors_to_rows_converts_flat_single_vector(self):
        self.assertEqual(
            vectors_to_rows([1, 2, 3], expected_count=1, expected_dimension=3),
            [[1.0, 2.0, 3.0]],
        )

    def test_vectors_to_rows_rejects_wrong_shape(self):
        with self.assertRaises(EmbeddingOutputError):
            vectors_to_rows([[1, 2]], expected_count=1, expected_dimension=3)
        with self.assertRaises(EmbeddingOutputError):
            vectors_to_rows([[1, float("nan"), 3]], expected_count=1, expected_dimension=3)

    def test_engine_loads_once_and_forwards_official_dense_options(self):
        settings = replace(Settings(), dimension=3, batch_size=4, max_length=128)
        fake = FakeModel(3)
        factory_calls = []

        def factory():
            factory_calls.append(True)
            return fake

        engine = EmbeddingEngine(settings, model_factory=factory)
        self.assertEqual(engine.embed(["one", "two"]), [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]])
        self.assertEqual(engine.embed("three"), [[1.0, 1.0, 1.0]])
        self.assertEqual(len(factory_calls), 1)
        self.assertEqual(fake.calls[0][1]["batch_size"], 4)
        self.assertEqual(fake.calls[0][1]["max_length"], 128)
        self.assertFalse(fake.calls[0][1]["return_sparse"])
        self.assertFalse(fake.calls[0][1]["return_colbert_vecs"])


if __name__ == "__main__":
    unittest.main()
