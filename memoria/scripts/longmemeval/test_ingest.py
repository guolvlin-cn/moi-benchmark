from datetime import datetime, timezone

from ingest import SessionChunker, mapped_time, parse_benchmark_date


class CharacterTokenizer:
    def count(self, text: str) -> int:
        return len(text) + 2


def test_relative_shift_preserves_delta() -> None:
    source = parse_benchmark_date("2023/05/20 (Sat) 02:21")
    source_anchor = parse_benchmark_date("2023/05/30 (Tue) 23:40")
    run_anchor = datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc)
    result = mapped_time(source, source_anchor, run_anchor)
    assert run_anchor - result == source_anchor - source


def test_chunker_preserves_limits_and_headers() -> None:
    chunker = SessionChunker(CharacterTokenizer(), max_tokens=180, max_bytes=180)
    messages = [
        {"role": "user", "content": "First paragraph. " * 20},
        {"role": "assistant", "content": "Second paragraph. " * 20},
    ]
    chunks = chunker.split_session(
        "session-1", "2023/05/20 (Sat) 02:21", messages
    )
    assert len(chunks) > 1
    assert all(chunk.token_count <= 180 for chunk in chunks)
    assert all(chunk.byte_count <= 180 for chunk in chunks)
    assert all("Session date: 2023/05/20 (Sat) 02:21" in chunk.content for chunk in chunks)


def test_invalid_weekday_is_rejected() -> None:
    try:
        parse_benchmark_date("2023/05/20 (Sun) 02:21")
    except ValueError as exc:
        assert "weekday mismatch" in str(exc)
    else:
        raise AssertionError("invalid weekday must fail")
