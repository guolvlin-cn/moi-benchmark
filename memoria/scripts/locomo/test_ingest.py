from datetime import datetime, timezone
import json
from pathlib import Path

import ingest


class CharacterTokenizer:
    def count(self, text: str) -> int:
        return len(text) + 2


def sample_fixture() -> dict:
    return {
        "sample_id": "conv-test",
        "conversation": {
            "speaker_a": "Alice",
            "speaker_b": "Bob",
            "session_1_date_time": "1:56 pm on 8 May, 2023",
            "session_1": [
                {"speaker": "Alice", "dia_id": "D1:1", "text": "Hello."},
                {
                    "speaker": "Bob",
                    "dia_id": "D1:2",
                    "text": "Look at this.",
                    "blip_caption": "a blue bicycle",
                    "img_url": ["https://example.test/bicycle.jpg"],
                },
            ],
            "session_2_date_time": "4:04 pm on 20 May, 2023",
            "session_2": [
                {"speaker": "Bob", "dia_id": "D2:1", "text": "Welcome back."}
            ],
            "session_3_date_time": "9:00 am on 30 May, 2023",
        },
        "qa": [{"question": "Ignored?", "answer": "Yes", "category": 4}],
        "observation": {"session_1_observation": {"Alice": [["Leak", "D1:1"]]}},
        "session_summary": {"session_1_summary": "Leak"},
        "event_summary": {"events_session_1": {"Alice": ["Leak"]}},
    }


def test_parse_and_relative_shift_preserve_delta() -> None:
    source = ingest.parse_locomo_date("1:56 pm on 8 May, 2023")
    source_anchor = ingest.parse_locomo_date("4:04 pm on 20 May, 2023")
    run_anchor = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
    result = ingest.mapped_time(source, source_anchor, run_anchor)
    assert run_anchor - result == source_anchor - source


def test_builds_one_memory_per_turn_and_ignores_annotations() -> None:
    run_anchor = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
    memories = ingest.build_turn_memories(
        sample_fixture(),
        tokenizer=CharacterTokenizer(),
        run_anchor_utc=run_anchor,
        user_prefix="locomo-",
        max_tokens=1_000,
        max_bytes=1_000,
    )
    assert len(memories) == 3
    assert {memory.user_id for memory in memories} == {"locomo-conv-test"}
    assert {memory.session_id for memory in memories} == {
        "locomo-conv-test-session-001",
        "locomo-conv-test-session-002",
    }
    assert [memory.dia_id for memory in memories] == ["D1:1", "D1:2", "D2:1"]
    assert all("Ignored?" not in memory.content for memory in memories)
    assert all("Leak" not in memory.content for memory in memories)
    assert "[Image caption: a blue bicycle]" in memories[1].content
    assert memories[2].observed_at == ingest.utc_iso(run_anchor)


def test_payload_preserves_evidence_and_partitions_dedup_by_turn(tmp_path) -> None:
    writer = ingest.JsonlWriter(tmp_path / "checkpoint.jsonl")
    errors = ingest.JsonlWriter(tmp_path / "errors.jsonl")
    try:
        importer = ingest.MemoriaImporter(
            api_url="http://127.0.0.1:8100",
            master_key="test",
            tokenizer_path=tmp_path / "unused.model",
            run_anchor_utc=datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc),
            dataset_sha256="dataset-sha",
            checkpoint=writer,
            errors=errors,
            user_prefix="locomo-",
            memory_type="semantic",
            max_tokens=1_000,
            max_bytes=1_000,
            timeout=1,
            max_retries=0,
            dry_run=True,
        )
        memory = ingest.build_turn_memories(
            sample_fixture(),
            tokenizer=CharacterTokenizer(),
            run_anchor_utc=importer.run_anchor_utc,
            user_prefix="locomo-",
            max_tokens=1_000,
            max_bytes=1_000,
        )[1]
        payload = importer.payload(memory)
    finally:
        writer.close()
        errors.close()
    assert payload["subject_id"] == "D1:2"
    assert payload["session_id"] == "locomo-conv-test-session-001"
    assert payload["extra_metadata"]["dia_id"] == "D1:2"
    assert payload["extra_metadata"]["dedup_partition_adapter"] == "dia_id"
    assert payload["extra_metadata"]["img_url"] == [
        "https://example.test/bicycle.jpg"
    ]


def test_ingest_key_is_stable_and_content_sensitive() -> None:
    common = {
        "sample_id": "conv-test",
        "session_id": "locomo-conv-test-session-001",
        "dia_id": "D1:1",
    }
    key_a = ingest.make_ingest_key(content="alpha", **common)
    assert key_a == ingest.make_ingest_key(content="alpha", **common)
    assert key_a != ingest.make_ingest_key(content="beta", **common)


def test_rejects_dia_id_from_wrong_session() -> None:
    broken = sample_fixture()
    broken["conversation"]["session_1"][0]["dia_id"] = "D2:99"
    try:
        ingest.build_turn_memories(
            broken,
            tokenizer=CharacterTokenizer(),
            run_anchor_utc=datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc),
            user_prefix="locomo-",
            max_tokens=1_000,
            max_bytes=1_000,
        )
    except ValueError as exc:
        assert "does not match session_1" in str(exc)
    else:
        raise AssertionError("mismatched dia_id must fail")


def test_official_dataset_maps_to_expected_users_sessions_and_memories() -> None:
    dataset_path = (
        Path(__file__).resolve().parents[2]
        / "datasets/downloads/public-benchmarks/locomo/locomo10.json"
    )
    samples = json.loads(dataset_path.read_text(encoding="utf-8"))
    run_anchor = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
    all_memories = [
        memory
        for sample in samples
        for memory in ingest.build_turn_memories(
            sample,
            tokenizer=CharacterTokenizer(),
            run_anchor_utc=run_anchor,
            user_prefix="locomo-",
            max_tokens=100_000,
            max_bytes=100_000,
        )
    ]
    assert len(samples) == 10
    assert len({memory.user_id for memory in all_memories}) == 10
    assert len({(memory.user_id, memory.session_id) for memory in all_memories}) == 272
    assert len(all_memories) == 5_882


def test_list_memories_follows_cursor_pagination(tmp_path) -> None:
    class Response:
        status_code = 200
        text = ""

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class Session:
        def __init__(self):
            self.params = []

        def request(self, _method, _url, **kwargs):
            params = kwargs["params"]
            self.params.append(dict(params))
            if "cursor" not in params:
                return Response(
                    {"items": [{"memory_id": "first"}], "next_cursor": "a" * 32}
                )
            return Response({"items": [{"memory_id": "second"}], "next_cursor": None})

    checkpoint = ingest.JsonlWriter(tmp_path / "checkpoint.jsonl")
    errors = ingest.JsonlWriter(tmp_path / "errors.jsonl")
    try:
        importer = ingest.MemoriaImporter(
            api_url="http://127.0.0.1:8100",
            master_key="test",
            tokenizer_path=tmp_path / "unused.model",
            run_anchor_utc=datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc),
            dataset_sha256="dataset-sha",
            checkpoint=checkpoint,
            errors=errors,
            user_prefix="locomo-",
            memory_type="semantic",
            max_tokens=1_000,
            max_bytes=1_000,
            timeout=1,
            max_retries=0,
            dry_run=False,
        )
        fake_session = Session()
        importer.local.http_session = fake_session
        memories = importer.list_memories("locomo-conv-test")
    finally:
        checkpoint.close()
        errors.close()
    assert [item["memory_id"] for item in memories] == ["first", "second"]
    assert fake_session.params == [
        {"limit": 500},
        {"limit": 500, "cursor": "a" * 32},
    ]
