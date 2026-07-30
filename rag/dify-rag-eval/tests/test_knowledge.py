import json
import tempfile
import unittest
from pathlib import Path

from dify_rag_eval.knowledge import (
    EmbeddingModel,
    _multipart_body,
    chunk_text,
    choose_embedding_model,
    ingest_directory,
    validate_chunk_options,
)


class FakeKnowledgeClient:
    def __init__(self):
        self.uploads = []
        self.documents = []

    def available_embedding_models(self):
        return [
            EmbeddingModel(
                "langgenius/siliconflow/siliconflow",
                "BAAI/bge-large-en-v1.5",
            )
        ]

    def list_knowledge_bases(self, keyword=None):
        return []

    def create_knowledge_base(self, name, embedding, *, top_k, search_method):
        return {"id": "dataset-1", "name": name}

    def list_documents(self, dataset_id):
        return self.documents

    def upload_document(self, dataset_id, path):
        self.uploads.append(path.name)
        document = {
            "id": f"document-{len(self.uploads)}",
            "name": path.name,
            "indexing_status": "completed",
            "error": None,
        }
        self.documents.append(document)
        return {"document": document, "batch": f"batch-{len(self.uploads)}"}

    def retrieve(self, dataset_id, query, *, top_k, search_method):
        return {"records": [{"segment": {"content": "probe hit"}, "score": 0.9}]}


class KnowledgePipelineTests(unittest.TestCase):
    def test_chunking_is_deterministic_and_overlaps(self):
        chunks = chunk_text("abcdefghij", chunk_size=6, chunk_overlap=2)
        self.assertEqual(chunks, [(0, 6, "abcdef"), (4, 10, "efghij"), (8, 10, "ij")])
        self.assertEqual(chunks, chunk_text("abcdefghij", 6, 2))

    def test_chunk_options_reject_bad_values(self):
        with self.assertRaises(ValueError):
            validate_chunk_options(0, 0)
        with self.assertRaises(ValueError):
            validate_chunk_options(10, 10)
        with self.assertRaises(ValueError):
            validate_chunk_options(10, -1)

    def test_prefers_english_embedding_for_english_corpus(self):
        selected = choose_embedding_model(
            [
                EmbeddingModel("provider", "Qwen/Qwen3-Embedding-0.6B"),
                EmbeddingModel("provider", "BAAI/bge-large-en-v1.5"),
            ]
        )
        self.assertEqual(selected.model, "BAAI/bge-large-en-v1.5")

    def test_multipart_contains_file_and_json_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide.md"
            path.write_text("hello", encoding="utf-8")
            body, content_type = _multipart_body(
                path, {"process_rule": {"mode": "automatic"}}
            )
        self.assertIn(b'name="file"; filename="guide.md"', body)
        self.assertIn(b'name="data"', body)
        self.assertIn(b'"automatic"', body)
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))

    def test_ingest_is_resumable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "a.md").write_text("a", encoding="utf-8")
            (source / "b.md").write_text("b", encoding="utf-8")
            client = FakeKnowledgeClient()
            kwargs = {
                "source": source,
                "knowledge_name": "test-kb",
                "output": output,
                "embedding_model": None,
                "embedding_provider": None,
                "top_k": 5,
                "search_method": "semantic_search",
                "upload_interval_seconds": 0,
                "wait": True,
                "probe": "hello",
            }
            first = ingest_directory(client, **kwargs)
            second = ingest_directory(client, **kwargs)
            state = json.loads(
                (output / "ingest-state.json").read_text(encoding="utf-8")
            )
        self.assertEqual(client.uploads, ["a.md", "b.md"])
        self.assertEqual(first["summary"]["retrieval_records"], 1)
        self.assertEqual(second["summary"]["uploaded_this_run"], 0)
        self.assertEqual(state["dataset_id"], "dataset-1")

    def test_local_chunks_manifest_preserves_traceability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "guide.md").write_text("abcdefghij", encoding="utf-8")
            client = FakeKnowledgeClient()
            state = ingest_directory(
                client,
                source=source,
                knowledge_name="chunk-kb",
                output=output,
                embedding_model=None,
                embedding_provider=None,
                top_k=5,
                search_method="semantic_search",
                upload_interval_seconds=0,
                wait=False,
                probe=None,
                local_chunks=True,
                chunk_size=6,
                chunk_overlap=2,
            )
            manifest = json.loads((output / "chunk-manifest.json").read_text())
            self.assertEqual([item["source_file"] for item in manifest["chunks"]], ["guide.md"] * 3)
            self.assertEqual([(x["start_offset"], x["end_offset"]) for x in manifest["chunks"]], [(0, 6), (4, 10), (8, 10)])
            self.assertEqual(len(client.uploads), 3)
            self.assertEqual(state["summary"]["documents"], 3)


if __name__ == "__main__":
    unittest.main()
