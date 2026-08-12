import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


MODULE_PATH = Path(__file__).with_name("evaluate_mem0_protocol.py")
SPEC = importlib.util.spec_from_file_location("evaluate_mem0_protocol", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class Mem0ProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dataset = json.loads(module.DEFAULT_DATASET.read_text(encoding="utf-8"))
        snapshot = module.load_jsonl(module.DEFAULT_SNAPSHOT)
        cls.row = module.validate_and_select(dataset, snapshot, None, 1, 20)[0]

    def test_prompt_uses_ranked_top20_then_original_chronology(self):
        prompt, ranked, chronological = module.build_reader_prompt(self.row)
        self.assertEqual(len(ranked), 20)
        self.assertEqual(len(chronological), 20)
        expected = sorted(
            self.row["results"][:20], key=module.source_session_date
        )
        self.assertEqual(
            chronological, [str(row["memory_id"]) for row in expected]
        )
        self.assertIn("Memories (sorted newest-first, grouped by date):", prompt)
        self.assertIn("Today's Date:", prompt)
        self.assertNotIn("2026-08-04T", prompt)

    def test_reader_cleanup_matches_mem0_flow(self):
        raw = "<mem_thinking>private reasoning</mem_thinking>\nANSWER: final answer"
        self.assertEqual(module.extract_answer(raw), "final answer")

    def test_judge_cleanup(self):
        self.assertTrue(
            module.parse_judge("<judge_thinking>reasoning</judge_thinking>\nyes")
        )
        self.assertFalse(module.parse_judge("<judge_thinking>x</judge_thinking>\nno"))

    def test_pinned_prompt_hashes(self):
        self.assertEqual(module.prompt_hashes(), module.EXPECTED_PROMPT_HASHES)

    def test_responses_api_uses_medium_reasoning_and_records_usage(self):
        response = SimpleNamespace(
            id="resp_test",
            model="gpt-54",
            status="completed",
            output_text="ANSWER: test answer",
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=25,
                total_tokens=125,
                output_tokens_details=SimpleNamespace(reasoning_tokens=10),
            ),
        )
        client = MagicMock()
        client.responses.create.return_value = response

        actual, raw, _, attempts = module.call_model(
            client, "gpt-5.4", "test prompt", 1, "responses", "medium"
        )

        self.assertIs(actual, response)
        self.assertEqual(raw, "ANSWER: test answer")
        self.assertEqual(attempts, 1)
        client.responses.create.assert_called_once_with(
            model="gpt-5.4",
            input="test prompt",
            reasoning={"effort": "medium"},
            max_output_tokens=module.MAX_COMPLETION_TOKENS,
        )
        self.assertEqual(module.usage(response)["reasoning_tokens"], 10)


if __name__ == "__main__":
    unittest.main()
