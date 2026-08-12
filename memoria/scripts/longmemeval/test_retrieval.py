import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


retrieve = load("longmemeval_retrieve", "retrieve.py")
evaluate = load("longmemeval_evaluate_retrieval", "evaluate_retrieval.py")


def test_select_questions_preserves_dataset_order():
    questions = [{"question_id": "a"}, {"question_id": "b"}, {"question_id": "c"}]
    assert [q["question_id"] for q in retrieve.select_questions(questions, ["c", "a"], 0, None)] == ["a", "c"]


def test_score_record_deduplicates_chunks_by_session():
    record = {
        "answer_session_ids": ["gold-a", "gold-b"],
        "normalized_results": [
            {"original_session_id": "gold-a"},
            {"original_session_id": "gold-a"},
            {"original_session_id": "noise"},
            {"original_session_id": "gold-b"},
        ],
    }
    metrics = evaluate.score_record(record)
    assert metrics["recall@1"] == 0.5
    assert metrics["recall@5"] == 1.0
    assert metrics["hit@1"] == 1.0
    assert metrics["complete_recall@5"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["unique_sessions@5"] == 3.0
    assert metrics["duplicate_chunk_rate@5"] == 0.25


def test_normalize_item_uses_original_session_id():
    item = {
        "memory_id": "m1",
        "user_id": "u1",
        "session_id": "physical-session",
        "extra_metadata": {
            "original_session_id": "original-session",
            "question_id": "q1",
            "ingest_key": "k1",
        },
    }
    normalized = retrieve.normalize_item(item, 1, "q1", False)
    assert normalized["original_session_id"] == "original-session"
    assert normalized["question_id"] == "q1"
    assert normalized["rank"] == 1


def test_normalize_item_legacy_v023_infers_unavailable_provenance():
    item = {
        "memory_id": "m1",
        "user_id": "longmemeval-q1",
        "session_id": "answer-session",
    }
    normalized = retrieve.normalize_item(item, 1, "q1", True)
    assert normalized["original_session_id"] == "answer-session"
    assert normalized["question_id"] == "q1"
    assert normalized["ingest_key"] is None
