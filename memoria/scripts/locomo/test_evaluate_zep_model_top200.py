import json
from pathlib import Path

import evaluate_top200 as common
import evaluate_zep_model_top200 as evaluation


def dataset_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "datasets/downloads/public-benchmarks/locomo/locomo10.json"
    )


def test_protocol_uses_pinned_mem0_prompts() -> None:
    assert common.validate_prompt_hashes() == common.EXPECTED_PROMPT_HASHES
    assert evaluation.DEFAULT_MODEL == "gpt-5.4"
    assert evaluation.REASONING_EFFORT == "medium"


def test_reader_input_is_identical_to_mem0_protocol() -> None:
    questions, _dates, references = common.load_dataset_questions(dataset_path())
    retrieval = {
        "results": [
            {"dia_id": "D1:2", "memory_id": "m2", "content": "newer turn"},
            {"dia_id": "D1:1", "memory_id": "m1", "content": "older turn"},
        ]
    }
    source_dates = {
        "D1:1": "2023-01-01T00:00:00",
        "D1:2": "2023-02-01T00:00:00",
    }
    prompt, chronological_ids = common.build_reader_input(
        questions[0], retrieval, source_dates, references[0]
    )
    assert chronological_ids == ["m1", "m2"]
    assert prompt.index("older turn") < prompt.index("newer turn")
    assert questions[0]["question"] in prompt
    assert "ANSWER:" in prompt


def test_mem0_judge_json_is_required() -> None:
    parsed, label = common.validate_judgment(
        json.dumps({"reasoning": "same fact", "label": "correct"})
    )
    assert parsed["reasoning"] == "same fact"
    assert label == "CORRECT"
