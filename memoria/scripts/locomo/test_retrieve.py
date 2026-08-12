import json
from pathlib import Path

import retrieve


def dataset_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "datasets/downloads/public-benchmarks/locomo/locomo10.json"
    )


def test_official_dataset_question_and_evidence_counts() -> None:
    questions, audit = retrieve.load_questions(dataset_path())
    assert len(questions) == 1_540
    assert sum(bool(question["gold_evidence"]) for question in questions) == 1_536
    assert audit["questions_without_evidence"] == 4
    assert {question["category"] for question in questions} == {1, 2, 3, 4}


def test_evidence_normalization_splits_and_validates_references() -> None:
    valid = {"D8:6", "D9:17", "D11:26", "D30:5"}
    evidence, issues = retrieve.normalize_evidence(
        ["D8:6; D9:17", "D:11:26", "D30:05", "D99:1", "D"], valid
    )
    assert evidence == ["D8:6", "D9:17", "D11:26", "D30:5"]
    assert any(row["invalid"] == ["D99:1"] for row in issues)
    assert any(row["raw"] == "D" and not row["parsed"] for row in issues)


def test_smoke_selection_uses_all_samples_and_categories() -> None:
    questions, _audit = retrieve.load_questions(dataset_path())
    selected = retrieve.smoke_questions(questions)
    assert len(selected) == 10
    assert len({question["sample_id"] for question in selected}) == 10
    assert {question["category"] for question in selected} == {1, 2, 3, 4}
    assert all(question["gold_evidence"] for question in selected)


def test_score_record_reports_hit_recall_complete_and_mrr() -> None:
    record = {
        "gold_evidence": ["D1:1", "D2:2"],
        "validation_ok": True,
        "results": [
            {"dia_id": "D9:9"},
            {"dia_id": "D1:1"},
            *({"dia_id": f"DX:{index}"} for index in range(3, 20)),
            {"dia_id": "D2:2"},
        ],
    }
    scores = retrieve.score_record(record)
    assert scores["hit@10"] == 1.0
    assert scores["recall@10"] == 0.5
    assert scores["complete_recall@10"] == 0.0
    assert scores["complete_recall@20"] == 1.0
    assert scores["mrr"] == 0.5


def test_strict_metrics_count_failed_retrieval_as_zero() -> None:
    selected = [
        {
            "question_id": "q1",
            "category_name": "single-hop",
            "gold_evidence": ["D1:1"],
        },
        {
            "question_id": "q2",
            "category_name": "single-hop",
            "gold_evidence": ["D2:1"],
        },
    ]
    records = {
        "q1": {
            "question_id": "q1",
            "status": "success",
            "validation_ok": True,
            "gold_evidence": ["D1:1"],
            "results": [{"dia_id": "D1:1"}],
            "client_total_ms": 10,
            "first_pass_success": True,
            "explain": {"path": "hybrid"},
        }
    }
    metrics = retrieve.build_metrics(selected, records)
    overall = metrics["evidence_metrics"]["overall_strict"]
    assert overall["count"] == 2
    assert overall["hit@10"] == 0.5
    assert overall["hit@10_count"] == 1
    assert metrics["complete"] is False


def test_normalize_result_keeps_reader_and_provenance_fields() -> None:
    item = {
        "memory_id": "m1",
        "user_id": "locomo-qwen-v4-conv-26",
        "session_id": "session-1",
        "subject_id": "D1:1",
        "content": "turn text",
        "observed_at": "2026-01-01T00:00:00Z",
        "retrieval_score": 0.9,
        "extra_metadata": {
            "sample_id": "conv-26",
            "dia_id": "D1:1",
            "speaker": "Alice",
            "ingest_key": "key",
        },
    }
    result = retrieve.normalize_result(item, 1)
    assert result["rank"] == 1
    assert result["dia_id"] == "D1:1"
    assert result["content"] == "turn text"
    assert result["ingest_key"] == "key"


def test_existing_full_ingest_summary_matches_dataset() -> None:
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "runs/locomo-qwen-text-embedding-v4-1024-turn-v1"
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["accepted_memories"] == 5_882
    assert summary["missing_ingest_keys"] == 0
    assert summary["extra_ingest_keys"] == 0
