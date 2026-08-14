import json
from pathlib import Path

import evaluate_top200 as evaluation
from mem0_prompts import get_answer_generation_prompt, preprocess_answer


def dataset_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "datasets/downloads/public-benchmarks/locomo/locomo10.json"
    )


def test_vendored_mem0_prompt_hashes_are_pinned() -> None:
    assert evaluation.validate_prompt_hashes() == evaluation.EXPECTED_PROMPT_HASHES


def test_dataset_questions_and_original_time_index() -> None:
    questions, dates, references = evaluation.load_dataset_questions(dataset_path())
    assert len(questions) == 1_540
    assert questions[0]["question_id"] == "conv0_q0"
    assert dates[0]["D1:1"] == "2023-05-08T13:56:00"
    assert references[0] == "9:55 am on 22 October, 2023"


def test_reader_prompt_uses_top200_then_chronological_order() -> None:
    results = [
        {"memory": "newer", "created_at": "2023-02-01T00:00:00"},
        {"memory": "older", "created_at": "2023-01-01T00:00:00"},
    ]
    prompt = get_answer_generation_prompt("question", results, "February 2023")
    assert prompt.index("older") < prompt.index("newer")
    assert "(Sunday, January 01, 2023) older" in prompt
    assert "These conversations took place around February 2023." in prompt


def test_reader_answer_and_category3_gold_preprocessing() -> None:
    assert evaluation.extract_answer("thinking ANSWER: first ANSWER: final") == "final"
    assert evaluation.extract_answer("plain") == "plain"
    assert preprocess_answer(3, "primary; explanatory tail") == "primary"
    assert preprocess_answer(4, "primary; explanatory tail") == "primary; explanatory tail"


def test_judge_validation_accepts_only_binary_labels() -> None:
    parsed, label = evaluation.validate_judgment(
        json.dumps({"reasoning": "same fact", "label": "correct"})
    )
    assert parsed["reasoning"] == "same fact"
    assert label == "CORRECT"


def test_strict_metrics_keep_missing_judgment_in_denominator() -> None:
    selected = [
        {"question_id": "q1", "category_name": "single-hop"},
        {"question_id": "q2", "category_name": "single-hop"},
    ]
    retrievals = {
        "q1": {"gold_evidence": ["D1:1"], "results": [{"dia_id": "D1:1"}]},
        "q2": {"gold_evidence": ["D2:1"], "results": [{"dia_id": "D9:9"}]},
    }
    answers = {"q1": {"usage": {}, "latency_ms": 1.0}}
    judgments = {
        "q1": {"label": "CORRECT", "usage": {}, "latency_ms": 1.0}
    }
    metrics = evaluation.build_metrics(selected, retrievals, answers, judgments)
    assert metrics["overall"] == {
        "total": 2,
        "correct": 1,
        "wrong_or_missing": 1,
        "accuracy": 0.5,
    }
    assert metrics["complete"] is False
