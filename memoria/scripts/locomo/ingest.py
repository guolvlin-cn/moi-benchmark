#!/usr/bin/env python3
"""Import LoCoMo conversations into Memoria as one memory per dialogue turn.

This is the LoCoMo Controlled Track importer. It maps one ``sample_id`` to one
isolated Memoria user, preserves LoCoMo sessions through ``session_id``, and
stores every dialogue turn as an individual memory. It does not ingest QA,
generated observations, generated session summaries, or gold event summaries.

The importer deliberately uses ``POST /v1/memories`` rather than
``POST /v1/observe`` so that source timestamps and turn-level evidence IDs are
preserved without invoking Memoria's LLM extraction pipeline.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests
import sentencepiece as spm


DATE_FORMAT = "%I:%M %p on %d %B, %Y"
TIME_MAPPING_VERSION = "relative_shift_per_sample_v1"
INGEST_MAPPING_VERSION = "turn_memory_v1"
DEFAULT_MAX_TOKENS = 7_000
DEFAULT_MAX_BYTES = 30 * 1024
TOKENIZER_SPECIAL_TOKENS = 2
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
OFFICIAL_DATASET_SHA256 = (
    "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
)
SESSION_KEY_RE = re.compile(r"session_(\d+)")
SAMPLE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ImportFailure(RuntimeError):
    """A Memoria request failed permanently."""


@dataclass(frozen=True)
class TurnMemory:
    sample_id: str
    user_id: str
    session_id: str
    original_session_id: str
    session_num: int
    session_order: int
    source_date_time: str
    observed_at: str
    dia_id: str
    turn_order: int
    speaker: str
    content: str
    token_count: int
    byte_count: int
    ingest_key: str
    blip_caption: str | None
    img_url: Any


@dataclass(frozen=True)
class SampleResult:
    sample_id: str
    user_id: str
    sessions: int
    expected_memories: int
    imported: int
    skipped_existing: int
    failed: int
    accepted_memories: int
    missing_ingest_keys: tuple[str, ...]
    extra_ingest_keys: tuple[str, ...]


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_locomo_date(value: str) -> datetime:
    """Parse LoCoMo's English session timestamp as a timezone-naive value."""
    return datetime.strptime(value.strip().upper(), DATE_FORMAT)


def mapped_time(
    source_time: datetime, source_anchor: datetime, run_anchor_utc: datetime
) -> datetime:
    """Shift one sample's timeline while preserving all source time deltas."""
    return run_anchor_utc - (source_anchor - source_time)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self.lock:
            self.handle.write(line + "\n")
            self.handle.flush()
            os.fsync(self.handle.fileno())

    def close(self) -> None:
        with self.lock:
            self.handle.close()


class BgeM3Tokenizer:
    def __init__(self, model_path: Path) -> None:
        self.processor = spm.SentencePieceProcessor(model_file=str(model_path))

    def count(self, text: str) -> int:
        return len(self.processor.encode(text, out_type=int)) + TOKENIZER_SPECIAL_TOKENS


def session_entries(conversation: dict[str, Any]) -> list[tuple[int, str, list[dict[str, Any]]]]:
    """Return non-empty sessions in numeric order and reject malformed pairs."""
    entries: list[tuple[int, str, list[dict[str, Any]]]] = []
    for key, value in conversation.items():
        match = SESSION_KEY_RE.fullmatch(key)
        if not match:
            continue
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        if not value:
            continue
        session_num = int(match.group(1))
        date_key = f"{key}_date_time"
        source_date = conversation.get(date_key)
        if not isinstance(source_date, str) or not source_date.strip():
            raise ValueError(f"missing {date_key}")
        parse_locomo_date(source_date)
        entries.append((session_num, source_date, value))
    entries.sort(key=lambda item: item[0])
    if not entries:
        raise ValueError("conversation has no non-empty sessions")
    if len({item[0] for item in entries}) != len(entries):
        raise ValueError("duplicate session numbers")
    return entries


def render_turn(
    *,
    source_date: str,
    original_session_id: str,
    dia_id: str,
    speaker: str,
    text: str,
    blip_caption: str | None,
) -> str:
    lines = [
        f"Original date: {source_date}",
        f"Session ID: {original_session_id}",
        f"[{dia_id}] {speaker}: {text}",
    ]
    if blip_caption:
        lines.append(f"[Image caption: {blip_caption}]")
    return "\n".join(lines)


def make_ingest_key(
    *, sample_id: str, session_id: str, dia_id: str, content: str
) -> str:
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    raw = "|".join(
        [
            INGEST_MAPPING_VERSION,
            TIME_MAPPING_VERSION,
            sample_id,
            session_id,
            dia_id,
            content_hash,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_turn_memories(
    sample: dict[str, Any],
    *,
    tokenizer: Any,
    run_anchor_utc: datetime,
    user_prefix: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[TurnMemory]:
    sample_id = str(sample.get("sample_id", "")).strip()
    if not SAMPLE_ID_RE.fullmatch(sample_id):
        raise ValueError(f"invalid sample_id: {sample_id!r}")
    conversation = sample.get("conversation")
    if not isinstance(conversation, dict):
        raise ValueError(f"conversation must be an object for {sample_id}")
    entries = session_entries(conversation)
    parsed_dates = [parse_locomo_date(source_date) for _, source_date, _ in entries]
    source_anchor = max(parsed_dates)
    user_id = f"{user_prefix}{sample_id}"
    seen_dia_ids: set[str] = set()
    memories: list[TurnMemory] = []

    for session_order, ((session_num, source_date, turns), source_time) in enumerate(
        zip(entries, parsed_dates, strict=True)
    ):
        original_session_id = f"session_{session_num}"
        session_id = f"{user_id}-session-{session_num:03d}"
        observed_at = utc_iso(mapped_time(source_time, source_anchor, run_anchor_utc))
        for turn_order, turn in enumerate(turns):
            if not isinstance(turn, dict):
                raise ValueError(f"{sample_id}/{original_session_id} turn must be an object")
            dia_id = str(turn.get("dia_id", "")).strip()
            speaker = str(turn.get("speaker", "")).strip()
            text = str(turn.get("text", "")).strip()
            if not dia_id or not speaker or not text:
                raise ValueError(
                    f"missing dia_id/speaker/text in {sample_id}/{original_session_id}"
                )
            if dia_id in seen_dia_ids:
                raise ValueError(f"duplicate dia_id in {sample_id}: {dia_id}")
            seen_dia_ids.add(dia_id)
            expected_prefix = f"D{session_num}:"
            if not dia_id.startswith(expected_prefix):
                raise ValueError(
                    f"dia_id {dia_id!r} does not match {original_session_id}"
                )

            caption_value = turn.get("blip_caption")
            blip_caption = (
                str(caption_value).strip() if caption_value is not None else None
            )
            if blip_caption == "":
                blip_caption = None
            content = render_turn(
                source_date=source_date,
                original_session_id=original_session_id,
                dia_id=dia_id,
                speaker=speaker,
                text=text,
                blip_caption=blip_caption,
            )
            token_count = tokenizer.count(content)
            byte_count = len(content.encode("utf-8"))
            if token_count > max_tokens or byte_count > max_bytes:
                raise ValueError(
                    f"turn exceeds limits: {sample_id}/{dia_id} "
                    f"tokens={token_count} bytes={byte_count}"
                )
            ingest_key = make_ingest_key(
                sample_id=sample_id,
                session_id=session_id,
                dia_id=dia_id,
                content=content,
            )
            memories.append(
                TurnMemory(
                    sample_id=sample_id,
                    user_id=user_id,
                    session_id=session_id,
                    original_session_id=original_session_id,
                    session_num=session_num,
                    session_order=session_order,
                    source_date_time=source_date,
                    observed_at=observed_at,
                    dia_id=dia_id,
                    turn_order=turn_order,
                    speaker=speaker,
                    content=content,
                    token_count=token_count,
                    byte_count=byte_count,
                    ingest_key=ingest_key,
                    blip_caption=blip_caption,
                    img_url=turn.get("img_url"),
                )
            )
    return memories


def validate_dataset(samples: Sequence[dict[str, Any]]) -> None:
    if not samples:
        raise ValueError("dataset is empty")
    sample_ids = [str(sample.get("sample_id", "")) for sample in samples]
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("duplicate sample_id values")


class MemoriaImporter:
    def __init__(
        self,
        *,
        api_url: str,
        master_key: str,
        tokenizer_path: Path,
        run_anchor_utc: datetime,
        dataset_sha256: str,
        checkpoint: JsonlWriter,
        errors: JsonlWriter,
        user_prefix: str,
        memory_type: str,
        max_tokens: int,
        max_bytes: int,
        timeout: float,
        max_retries: int,
        dry_run: bool,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.master_key = master_key
        self.tokenizer_path = tokenizer_path
        self.run_anchor_utc = run_anchor_utc
        self.dataset_sha256 = dataset_sha256
        self.checkpoint = checkpoint
        self.errors = errors
        self.user_prefix = user_prefix
        self.memory_type = memory_type
        self.max_tokens = max_tokens
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.max_retries = max_retries
        self.dry_run = dry_run
        self.local = threading.local()

    def http_session(self) -> requests.Session:
        session = getattr(self.local, "http_session", None)
        if session is None:
            session = requests.Session()
            self.local.http_session = session
        return session

    def tokenizer(self) -> BgeM3Tokenizer:
        tokenizer = getattr(self.local, "tokenizer", None)
        if tokenizer is None:
            tokenizer = BgeM3Tokenizer(self.tokenizer_path)
            self.local.tokenizer = tokenizer
        return tokenizer

    def headers(self, user_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.master_key}",
            "X-Impersonate-User": user_id,
            "Content-Type": "application/json",
        }

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        user_id: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        expected_status: int,
    ) -> dict[str, Any]:
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(min(2 ** (attempt - 1), 16))
            try:
                response = self.http_session().request(
                    method,
                    url,
                    headers=self.headers(user_id),
                    params=params,
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            if response.status_code == expected_status:
                return dict(response.json())
            last_error = f"HTTP {response.status_code}: {response.text[:1000]}"
            if response.status_code not in TRANSIENT_STATUS:
                break
        raise ImportFailure(last_error)

    def list_memories(
        self, user_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List every active memory, following Memoria's memory-id cursor."""
        memories: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            params: dict[str, Any] = {"limit": 500}
            if session_id:
                params["session_id"] = session_id
            if cursor:
                params["cursor"] = cursor
            body = self._request_json(
                "GET",
                f"{self.api_url}/v1/memories",
                user_id=user_id,
                params=params,
                expected_status=200,
            )
            items = body.get("items", [])
            if not isinstance(items, list):
                raise ImportFailure("list response items is not a list")
            memories.extend(item for item in items if isinstance(item, dict))
            next_cursor = body.get("next_cursor")
            if not next_cursor:
                break
            cursor = str(next_cursor)
            if cursor in seen_cursors:
                raise ImportFailure(f"cursor loop while listing {user_id}: {cursor}")
            seen_cursors.add(cursor)
        return memories

    @staticmethod
    def key_map(memories: Iterable[dict[str, Any]]) -> dict[str, str]:
        output: dict[str, str] = {}
        for memory in memories:
            metadata = memory.get("extra_metadata") or {}
            if not isinstance(metadata, dict):
                continue
            key = metadata.get("ingest_key")
            if key:
                output[str(key)] = str(memory.get("memory_id", ""))
        return output

    def reconcile(self, memory: TurnMemory) -> dict[str, Any] | None:
        try:
            candidates = self.list_memories(memory.user_id, memory.session_id)
        except Exception:
            return None
        for candidate in candidates:
            metadata = candidate.get("extra_metadata") or {}
            if isinstance(metadata, dict) and metadata.get("ingest_key") == memory.ingest_key:
                return candidate
        return None

    def payload(self, memory: TurnMemory) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "dataset": "LoCoMo",
            "dataset_sha256": self.dataset_sha256,
            "sample_id": memory.sample_id,
            "original_session_id": memory.original_session_id,
            "session_num": memory.session_num,
            "session_order": memory.session_order,
            "dia_id": memory.dia_id,
            "turn_order": memory.turn_order,
            "speaker": memory.speaker,
            "source_date_time": memory.source_date_time,
            "run_anchor_utc": utc_iso(self.run_anchor_utc),
            "time_mapping": TIME_MAPPING_VERSION,
            "ingest_mapping": INGEST_MAPPING_VERSION,
            "embedding_token_count": memory.token_count,
            "content_byte_count": memory.byte_count,
            "ingest_key": memory.ingest_key,
            "dedup_partition_adapter": "dia_id",
        }
        if memory.blip_caption:
            metadata["blip_caption"] = memory.blip_caption
        if memory.img_url is not None:
            metadata["img_url"] = memory.img_url
        return {
            "content": memory.content,
            "memory_type": self.memory_type,
            "session_id": memory.session_id,
            "subject_id": memory.dia_id,
            "observed_at": memory.observed_at,
            "source": "locomo-controlled-turn",
            "extra_metadata": metadata,
        }

    def store_one(self, memory: TurnMemory) -> dict[str, Any]:
        payload = self.payload(memory)
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            if attempt:
                existing = self.reconcile(memory)
                if existing is not None:
                    return existing
                time.sleep(min(2 ** (attempt - 1), 16))
            try:
                response = self.http_session().post(
                    f"{self.api_url}/v1/memories",
                    headers=self.headers(memory.user_id),
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            if response.status_code == 201:
                return dict(response.json())
            last_error = f"HTTP {response.status_code}: {response.text[:1000]}"
            if response.status_code not in TRANSIENT_STATUS:
                break
        raise ImportFailure(last_error)

    def import_sample(self, sample: dict[str, Any]) -> SampleResult:
        memories = build_turn_memories(
            sample,
            tokenizer=self.tokenizer(),
            run_anchor_utc=self.run_anchor_utc,
            user_prefix=self.user_prefix,
            max_tokens=self.max_tokens,
            max_bytes=self.max_bytes,
        )
        sample_id = memories[0].sample_id
        user_id = memories[0].user_id
        expected_keys = {memory.ingest_key for memory in memories}
        existing_by_key: dict[str, str] = {}
        if not self.dry_run:
            existing_by_key = self.key_map(self.list_memories(user_id))

        imported = 0
        skipped = 0
        failed = 0
        for memory in memories:
            if memory.ingest_key in existing_by_key:
                skipped += 1
                continue
            if self.dry_run:
                imported += 1
                continue
            try:
                response = self.store_one(memory)
            except Exception as exc:
                failed += 1
                self.errors.write(
                    {
                        "at": utc_iso(datetime.now(timezone.utc)),
                        "scope": "turn",
                        "sample_id": sample_id,
                        "user_id": user_id,
                        "session_id": memory.session_id,
                        "dia_id": memory.dia_id,
                        "ingest_key": memory.ingest_key,
                        "error": str(exc),
                    }
                )
                continue
            imported += 1
            existing_by_key[memory.ingest_key] = str(response.get("memory_id", ""))
            self.checkpoint.write(
                {
                    "at": utc_iso(datetime.now(timezone.utc)),
                    "sample_id": sample_id,
                    "user_id": user_id,
                    "session_id": memory.session_id,
                    "original_session_id": memory.original_session_id,
                    "dia_id": memory.dia_id,
                    "turn_order": memory.turn_order,
                    "ingest_key": memory.ingest_key,
                    "memory_id": response.get("memory_id"),
                    "observed_at": response.get("observed_at"),
                }
            )

        if self.dry_run:
            accepted_keys = expected_keys
            actual_keys = expected_keys
        else:
            actual_keys = set(self.key_map(self.list_memories(user_id)))
            accepted_keys = expected_keys & actual_keys
        return SampleResult(
            sample_id=sample_id,
            user_id=user_id,
            sessions=len({memory.session_id for memory in memories}),
            expected_memories=len(memories),
            imported=imported,
            skipped_existing=skipped,
            failed=failed,
            accepted_memories=len(accepted_keys),
            missing_ingest_keys=tuple(sorted(expected_keys - actual_keys)),
            extra_ingest_keys=tuple(sorted(actual_keys - expected_keys)),
        )


def load_or_create_manifest(
    *,
    path: Path,
    dataset_path: Path,
    dataset_sha256: str,
    tokenizer_path: Path,
    tokenizer_sha256: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    expected = {
        "dataset_sha256": dataset_sha256,
        "tokenizer_sha256": tokenizer_sha256,
        "embedding_model": args.embedding_model,
        "embedding_dimension": args.embedding_dimension,
        "time_mapping": TIME_MAPPING_VERSION,
        "ingest_mapping": INGEST_MAPPING_VERSION,
        "max_tokens": args.max_tokens,
        "max_bytes": args.max_bytes,
        "user_prefix": args.user_prefix,
        "memory_type": args.memory_type,
        "memoria_commit": args.memoria_commit,
        "memoria_patch_sha256": args.memoria_patch_sha256,
    }
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise ValueError(
                    f"run manifest mismatch for {key}: "
                    f"{manifest.get(key)!r} != {value!r}"
                )
        return manifest

    run_anchor = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    manifest = {
        "created_at": utc_iso(datetime.now(timezone.utc)),
        "run_anchor_utc": utc_iso(run_anchor),
        "dataset": "LoCoMo",
        "dataset_path": str(dataset_path.resolve()),
        "dataset_sha256": dataset_sha256,
        "dataset_scope": "all 10 samples; conversations only; QA not ingested",
        "api_url": args.api_url,
        "embedding_model": args.embedding_model,
        "embedding_dimension": args.embedding_dimension,
        "tokenizer_path": str(tokenizer_path.resolve()),
        "tokenizer_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "tokenizer_sha256": tokenizer_sha256,
        "tokenizer_role": (
            "conservative client-side input limit validation only; "
            "the embedding service performs authoritative tokenization"
        ),
        "max_tokens": args.max_tokens,
        "max_bytes": args.max_bytes,
        "time_mapping": TIME_MAPPING_VERSION,
        "time_mapping_formula": (
            "observed_at = run_anchor_utc - "
            "(max(sample_session_dates) - session_date)"
        ),
        "ingest_mapping": INGEST_MAPPING_VERSION,
        "isolation": "one sample_id per X-Impersonate-User",
        "memory_granularity": "one LoCoMo dialogue turn per memory",
        "session_mapping": "one LoCoMo session_n per Memoria session_id",
        "dedup_partition": "subject_id=dia_id",
        "image_handling": "append blip_caption to content; preserve img_url as metadata",
        "excluded_fields": ["qa", "observation", "session_summary", "event_summary"],
        "user_prefix": args.user_prefix,
        "memory_type": args.memory_type,
        "write_endpoint": "/v1/memories",
        "batch_endpoint_used": False,
        "internal_llm": False,
        "memoria_commit": args.memoria_commit,
        "memoria_patch_sha256": args.memoria_patch_sha256,
    }
    atomic_json(path, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[3]
    default_dataset = (
        project_root
        / "memoria/datasets/downloads/public-benchmarks/locomo/locomo10.json"
    )
    default_runtime = Path(
        "/Users/wangyaqi/Documents/cursor_project/agent评估/memoria_runtime"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=default_dataset)
    parser.add_argument("--runtime-env", type=Path, default=default_runtime / ".env")
    parser.add_argument(
        "--tokenizer-model",
        type=Path,
        default=default_runtime / "tokenizer/bge-m3-5617a9f/sentencepiece.bpe.model",
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--user-prefix", default="locomo-")
    parser.add_argument("--memory-type", default="semantic")
    parser.add_argument("--embedding-model", default="bge-m3")
    parser.add_argument("--embedding-dimension", type=int, default=1024)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-dataset-drift", action="store_true")
    parser.add_argument("--memoria-commit")
    parser.add_argument("--memoria-patch-sha256")
    return parser.parse_args()


def select_samples(
    samples: Sequence[dict[str, Any]], args: argparse.Namespace
) -> list[dict[str, Any]]:
    if args.sample_id:
        selected_ids = set(args.sample_id)
        selected = [sample for sample in samples if sample["sample_id"] in selected_ids]
        missing = selected_ids - {sample["sample_id"] for sample in selected}
        if missing:
            raise ValueError(f"unknown sample ids: {sorted(missing)}")
        return selected
    selected = list(samples[args.start_index :])
    if args.limit is not None:
        selected = selected[: args.limit]
    return selected


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if args.max_tokens < 1 or args.max_bytes < 1:
        raise ValueError("max token and byte limits must be positive")
    if args.embedding_dimension < 1:
        raise ValueError("embedding dimension must be positive")
    if not args.dataset.is_file():
        raise FileNotFoundError(args.dataset)
    if not args.tokenizer_model.is_file():
        raise FileNotFoundError(args.tokenizer_model)

    dataset_sha256 = sha256_file(args.dataset)
    if dataset_sha256 != OFFICIAL_DATASET_SHA256 and not args.allow_dataset_drift:
        raise ValueError(
            "LoCoMo dataset SHA-256 drifted: "
            f"{dataset_sha256} != {OFFICIAL_DATASET_SHA256}; "
            "pass --allow-dataset-drift only for an explicitly labelled run"
        )
    tokenizer_sha256 = sha256_file(args.tokenizer_model)
    with args.dataset.open("r", encoding="utf-8") as handle:
        samples = json.load(handle)
    if not isinstance(samples, list):
        raise ValueError("LoCoMo dataset root must be a list")
    validate_dataset(samples)
    selected = select_samples(samples, args)
    if not selected:
        raise ValueError("no samples selected")

    env: dict[str, str] = {}
    if args.runtime_env.is_file():
        env = read_env(args.runtime_env)
    master_key = env.get("MEMORIA_MASTER_KEY", "")
    if not master_key and not args.dry_run:
        raise ValueError("MEMORIA_MASTER_KEY is missing from runtime env")

    args.run_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_or_create_manifest(
        path=args.run_dir / "manifest.json",
        dataset_path=args.dataset,
        dataset_sha256=dataset_sha256,
        tokenizer_path=args.tokenizer_model,
        tokenizer_sha256=tokenizer_sha256,
        args=args,
    )
    run_anchor = datetime.fromisoformat(
        manifest["run_anchor_utc"].replace("Z", "+00:00")
    )

    checkpoint = JsonlWriter(args.run_dir / "logs/checkpoint.jsonl")
    errors = JsonlWriter(args.run_dir / "logs/errors.jsonl")
    importer = MemoriaImporter(
        api_url=args.api_url,
        master_key=master_key,
        tokenizer_path=args.tokenizer_model,
        run_anchor_utc=run_anchor,
        dataset_sha256=dataset_sha256,
        checkpoint=checkpoint,
        errors=errors,
        user_prefix=args.user_prefix,
        memory_type=args.memory_type,
        max_tokens=args.max_tokens,
        max_bytes=args.max_bytes,
        timeout=args.timeout,
        max_retries=args.max_retries,
        dry_run=args.dry_run,
    )

    started = time.monotonic()
    results: list[SampleResult] = []
    unexpected: list[dict[str, str]] = []
    completed = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_map = {
                pool.submit(importer.import_sample, sample): str(sample["sample_id"])
                for sample in selected
            }
            for future in concurrent.futures.as_completed(future_map):
                sample_id = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    unexpected.append({"sample_id": sample_id, "error": str(exc)})
                    errors.write(
                        {
                            "at": utc_iso(datetime.now(timezone.utc)),
                            "scope": "sample",
                            "sample_id": sample_id,
                            "error": str(exc),
                        }
                    )
                else:
                    results.append(result)
                completed += 1
                imported = sum(item.imported for item in results)
                skipped = sum(item.skipped_existing for item in results)
                failed = sum(item.failed for item in results) + len(unexpected)
                print(
                    f"[{completed}/{len(selected)}] sample={sample_id} "
                    f"imported={imported} skipped={skipped} failed={failed} "
                    f"elapsed={time.monotonic() - started:.1f}s",
                    flush=True,
                )
    finally:
        checkpoint.close()
        errors.close()

    results.sort(key=lambda item: item.sample_id)
    summary = {
        "finished_at": utc_iso(datetime.now(timezone.utc)),
        "dry_run": args.dry_run,
        "selected_samples": len(selected),
        "completed_samples": len(results),
        "sample_failures": unexpected,
        "sessions": sum(item.sessions for item in results),
        "expected_memories": sum(item.expected_memories for item in results),
        "imported": sum(item.imported for item in results),
        "skipped_existing": sum(item.skipped_existing for item in results),
        "failed_memories": sum(item.failed for item in results),
        "accepted_memories": sum(item.accepted_memories for item in results),
        "missing_ingest_keys": sum(len(item.missing_ingest_keys) for item in results),
        "extra_ingest_keys": sum(len(item.extra_ingest_keys) for item in results),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "results": [asdict(item) for item in results],
    }
    atomic_json(args.run_dir / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    failed = bool(
        unexpected
        or summary["failed_memories"]
        or summary["missing_ingest_keys"]
        or summary["extra_ingest_keys"]
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
