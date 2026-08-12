#!/usr/bin/env python3
"""Import LongMemEval-S sessions into a self-hosted Memoria instance.

The importer deliberately uses the single-memory endpoint. Memoria's current
batch endpoint does not preserve per-item ``observed_at`` values.
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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests
import sentencepiece as spm


DATE_FORMAT = "%Y/%m/%d (%a) %H:%M"
TIME_MAPPING_VERSION = "relative_shift_v1"
DEFAULT_MAX_TOKENS = 7_000
DEFAULT_MAX_BYTES = 30 * 1024
TOKENIZER_SPECIAL_TOKENS = 2
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class ImportFailure(RuntimeError):
    """An import request failed permanently."""


@dataclass(frozen=True)
class Chunk:
    content: str
    token_count: int
    byte_count: int


@dataclass(frozen=True)
class QuestionResult:
    question_id: str
    sessions: int
    chunks: int
    imported: int
    skipped: int
    failed: int


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_benchmark_date(value: str) -> datetime:
    parsed = datetime.strptime(value, DATE_FORMAT)
    expected_weekday = re.search(r"\(([^)]+)\)", value)
    if expected_weekday and parsed.strftime("%a") != expected_weekday.group(1):
        raise ValueError(f"weekday mismatch in benchmark date: {value}")
    return parsed


def mapped_time(
    source_time: datetime, source_anchor: datetime, run_anchor_utc: datetime
) -> datetime:
    """Shift a naive benchmark timestamp onto the frozen UTC run timeline."""
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


class BgeM3Tokenizer:
    def __init__(self, model_path: Path) -> None:
        self.processor = spm.SentencePieceProcessor(model_file=str(model_path))

    def count(self, text: str) -> int:
        return len(self.processor.encode(text, out_type=int)) + TOKENIZER_SPECIAL_TOKENS


class SessionChunker:
    def __init__(
        self,
        tokenizer: BgeM3Tokenizer,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.tokenizer = tokenizer
        self.max_tokens = max_tokens
        self.max_bytes = max_bytes

    def measure(self, text: str) -> tuple[int, int]:
        return self.tokenizer.count(text), len(text.encode("utf-8"))

    def fits(self, text: str) -> bool:
        tokens, byte_count = self.measure(text)
        return tokens <= self.max_tokens and byte_count <= self.max_bytes

    def _hard_split(self, text: str, prefix: str) -> list[str]:
        parts: list[str] = []
        remaining = text
        while remaining:
            low, high = 1, len(remaining)
            best = 0
            while low <= high:
                mid = (low + high) // 2
                candidate = prefix + remaining[:mid]
                if self.fits(candidate):
                    best = mid
                    low = mid + 1
                else:
                    high = mid - 1
            if best == 0:
                raise ValueError("chunk prefix alone exceeds configured limits")
            split_at = best
            if best < len(remaining):
                whitespace = max(
                    remaining.rfind(" ", 0, best),
                    remaining.rfind("\n", 0, best),
                )
                if whitespace >= max(1, best // 2):
                    split_at = whitespace + 1
            parts.append(remaining[:split_at])
            remaining = remaining[split_at:]
        return parts

    def _split_text(self, text: str, prefix: str) -> list[str]:
        if self.fits(prefix + text):
            return [text]

        paragraph_parts = [
            part for part in re.split(r"(?<=\n)\s*\n+", text) if part
        ]
        if len(paragraph_parts) > 1:
            output: list[str] = []
            for part in paragraph_parts:
                output.extend(self._split_text(part, prefix))
            return output

        sentence_parts = [
            part
            for part in re.split(r"(?<=[.!?。！？])(?=\s+|$)", text)
            if part
        ]
        if len(sentence_parts) > 1:
            output = []
            for part in sentence_parts:
                output.extend(self._split_text(part, prefix))
            return output

        return self._hard_split(text, prefix)

    def split_session(
        self, session_id: str, source_date: str, messages: Sequence[dict[str, Any]]
    ) -> list[Chunk]:
        header = f"Session date: {source_date}\nSession ID: {session_id}"
        units: list[str] = []
        for message in messages:
            role = str(message.get("role", "unknown")).strip().lower() or "unknown"
            content = str(message.get("content", ""))
            role_prefix = f"[{role}]\n"
            for part in self._split_text(content, header + "\n\n" + role_prefix):
                units.append(role_prefix + part)

        if not units:
            units = ["[unknown]\n"]

        chunks: list[str] = []
        current = header
        for unit in units:
            candidate = current + "\n\n" + unit
            if self.fits(candidate):
                current = candidate
                continue
            if current != header:
                chunks.append(current)
            current = header + "\n\n" + unit
            if not self.fits(current):
                raise ValueError(f"failed to split oversized unit in session {session_id}")
        if current != header or not chunks:
            chunks.append(current)

        measured: list[Chunk] = []
        for content in chunks:
            token_count, byte_count = self.measure(content)
            if token_count > self.max_tokens or byte_count > self.max_bytes:
                raise AssertionError(f"chunk limit violated for {session_id}")
            measured.append(Chunk(content, token_count, byte_count))
        return measured


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


class MemoriaImporter:
    def __init__(
        self,
        *,
        api_url: str,
        master_key: str,
        tokenizer_path: Path,
        run_anchor_utc: datetime,
        checkpoint: JsonlWriter,
        errors: JsonlWriter,
        max_tokens: int,
        max_bytes: int,
        user_prefix: str,
        memory_type: str,
        subject_per_session: bool,
        timeout: float,
        max_retries: int,
        dry_run: bool,
        legacy_v023: bool,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.master_key = master_key
        self.tokenizer_path = tokenizer_path
        self.run_anchor_utc = run_anchor_utc
        self.checkpoint = checkpoint
        self.errors = errors
        self.max_tokens = max_tokens
        self.max_bytes = max_bytes
        self.user_prefix = user_prefix
        self.memory_type = memory_type
        self.subject_per_session = subject_per_session
        self.timeout = timeout
        self.max_retries = max_retries
        self.dry_run = dry_run
        self.legacy_v023 = legacy_v023
        self.local = threading.local()

    def session(self) -> requests.Session:
        session = getattr(self.local, "http_session", None)
        if session is None:
            session = requests.Session()
            self.local.http_session = session
        return session

    def chunker(self) -> SessionChunker:
        chunker = getattr(self.local, "chunker", None)
        if chunker is None:
            chunker = SessionChunker(
                BgeM3Tokenizer(self.tokenizer_path), self.max_tokens, self.max_bytes
            )
            self.local.chunker = chunker
        return chunker

    def headers(self, user_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.master_key}",
            "X-Impersonate-User": user_id,
            "Content-Type": "application/json",
        }

    def list_memories(
        self, user_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 500}
        if session_id:
            params["session_id"] = session_id
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(min(2 ** (attempt - 1), 16))
            try:
                response = self.session().get(
                    f"{self.api_url}/v1/memories",
                    headers=self.headers(user_id),
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            if response.status_code == 200:
                body = response.json()
                return list(body.get("items", []))
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"
            if response.status_code not in TRANSIENT_STATUS:
                break
        raise ImportFailure(f"list failed for {user_id}: {last_error}")

    @staticmethod
    def ingest_key(question_id: str, session_id: str, chunk_index: int, content: str) -> str:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        raw = (
            f"{TIME_MAPPING_VERSION}|{question_id}|{session_id}|"
            f"{chunk_index}|{content_hash}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def legacy_key(session_id: str, content: str) -> str:
        return hashlib.sha256(
            f"legacy-v0.2.3|{session_id}|{content}".encode("utf-8")
        ).hexdigest()

    def key_map(self, memories: Iterable[dict[str, Any]]) -> dict[str, str]:
        output: dict[str, str] = {}
        for memory in memories:
            if self.legacy_v023:
                session_id = str(memory.get("session_id") or "")
                content = str(memory.get("content") or "")
                if session_id and content:
                    output[self.legacy_key(session_id, content)] = str(
                        memory.get("memory_id", "")
                    )
                continue
            metadata = memory.get("extra_metadata") or {}
            key = metadata.get("ingest_key")
            if key:
                output[str(key)] = str(memory.get("memory_id", ""))
        return output

    def reconcile(
        self,
        user_id: str,
        session_id: str,
        lookup_key: str,
        content: str,
    ) -> dict[str, Any] | None:
        try:
            memories = self.list_memories(user_id, session_id)
        except Exception:
            return None
        for memory in memories:
            if self.legacy_v023:
                if self.legacy_key(
                    str(memory.get("session_id") or ""),
                    str(memory.get("content") or ""),
                ) == lookup_key:
                    return memory
                continue
            metadata = memory.get("extra_metadata") or {}
            if metadata.get("ingest_key") == lookup_key:
                return memory
        return None

    def store_one(
        self,
        user_id: str,
        session_id: str,
        lookup_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            if attempt:
                existing = self.reconcile(
                    user_id, session_id, lookup_key, str(payload["content"])
                )
                if existing is not None:
                    return existing
                time.sleep(min(2 ** (attempt - 1), 16))
            try:
                response = self.session().post(
                    f"{self.api_url}/v1/memories",
                    headers=self.headers(user_id),
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            if response.status_code == 201:
                return response.json()
            last_error = f"HTTP {response.status_code}: {response.text[:1000]}"
            if response.status_code not in TRANSIENT_STATUS:
                break
        raise ImportFailure(last_error)

    def import_question(self, question: dict[str, Any]) -> QuestionResult:
        question_id = str(question["question_id"])
        user_id = f"{self.user_prefix}{question_id}"
        session_ids = question["haystack_session_ids"]
        session_dates = question["haystack_dates"]
        sessions = question["haystack_sessions"]
        if not (len(session_ids) == len(session_dates) == len(sessions)):
            raise ValueError(f"parallel array length mismatch for {question_id}")

        question_time = parse_benchmark_date(question["question_date"])
        parsed_dates = [parse_benchmark_date(value) for value in session_dates]
        source_anchor = max([question_time, *parsed_dates])
        mapped_question_at = mapped_time(
            question_time, source_anchor, self.run_anchor_utc
        )

        existing_by_key: dict[str, str] = {}
        if not self.dry_run:
            existing_by_key = self.key_map(self.list_memories(user_id))

        imported = 0
        skipped = 0
        failed = 0
        total_chunks = 0
        for session_order, (session_id, source_date, source_time, messages) in enumerate(
            zip(session_ids, session_dates, parsed_dates, sessions, strict=True)
        ):
            chunks = self.chunker().split_session(session_id, source_date, messages)
            observed_at = mapped_time(source_time, source_anchor, self.run_anchor_utc)
            for chunk_index, chunk in enumerate(chunks):
                total_chunks += 1
                ingest_key = self.ingest_key(
                    question_id, session_id, chunk_index, chunk.content
                )
                lookup_key = (
                    self.legacy_key(session_id, chunk.content)
                    if self.legacy_v023
                    else ingest_key
                )
                if lookup_key in existing_by_key:
                    skipped += 1
                    continue

                metadata = {
                    "dataset": "LongMemEval-S",
                    "question_id": question_id,
                    "question_type": question.get("question_type"),
                    "source_session_date": source_date,
                    "source_question_date": question["question_date"],
                    "source_anchor": source_anchor.strftime(DATE_FORMAT),
                    "mapped_question_at": utc_iso(mapped_question_at),
                    "run_anchor_utc": utc_iso(self.run_anchor_utc),
                    "time_mapping": TIME_MAPPING_VERSION,
                    "original_session_id": session_id,
                    "session_order": session_order,
                    "chunk_index": chunk_index,
                    "chunk_count": len(chunks),
                    "embedding_token_count": chunk.token_count,
                    "content_byte_count": chunk.byte_count,
                    "ingest_key": ingest_key,
                }
                if self.subject_per_session:
                    metadata["dedup_partition_adapter"] = "session_id"
                payload = {
                    "content": chunk.content,
                    "memory_type": self.memory_type,
                    "session_id": session_id,
                    "observed_at": utc_iso(observed_at),
                    "source": "longmemeval-s",
                    "extra_metadata": metadata,
                }
                if self.subject_per_session:
                    payload["subject_id"] = session_id
                if self.legacy_v023:
                    # Memoria v0.2.3 accepts observed_at/session_id but does not
                    # persist extra_metadata or subject_id on direct-store writes.
                    payload.pop("extra_metadata", None)
                    payload.pop("subject_id", None)

                if self.dry_run:
                    imported += 1
                    continue

                try:
                    response = self.store_one(user_id, session_id, lookup_key, payload)
                except Exception as exc:
                    failed += 1
                    self.errors.write(
                        {
                            "at": utc_iso(datetime.now(timezone.utc)),
                            "question_id": question_id,
                            "user_id": user_id,
                            "session_id": session_id,
                            "session_order": session_order,
                            "chunk_index": chunk_index,
                            "ingest_key": ingest_key,
                            "error": str(exc),
                        }
                    )
                    continue

                imported += 1
                existing_by_key[ingest_key] = str(response.get("memory_id", ""))
                self.checkpoint.write(
                    {
                        "at": utc_iso(datetime.now(timezone.utc)),
                        "question_id": question_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "session_order": session_order,
                        "chunk_index": chunk_index,
                        "chunk_count": len(chunks),
                        "ingest_key": ingest_key,
                        "memory_id": response.get("memory_id"),
                        "observed_at": response.get("observed_at"),
                    }
                )

        return QuestionResult(
            question_id=question_id,
            sessions=len(sessions),
            chunks=total_chunks,
            imported=imported,
            skipped=skipped,
            failed=failed,
        )


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_or_create_manifest(
    *,
    path: Path,
    dataset_path: Path,
    dataset_sha256: str,
    tokenizer_path: Path,
    tokenizer_sha256: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "dataset_sha256": dataset_sha256,
            "time_mapping": TIME_MAPPING_VERSION,
            "max_tokens": args.max_tokens,
            "max_bytes": args.max_bytes,
            "user_prefix": args.user_prefix,
            "memoria_commit": args.memoria_commit,
            "memoria_patch_sha256": args.memoria_patch_sha256,
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise ValueError(
                    f"run manifest mismatch for {key}: {manifest.get(key)!r} != {value!r}"
                )
        return manifest

    run_anchor = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    manifest = {
        "created_at": utc_iso(datetime.now(timezone.utc)),
        "run_anchor_utc": utc_iso(run_anchor),
        "dataset": "LongMemEval-S",
        "dataset_path": str(dataset_path.resolve()),
        "dataset_sha256": dataset_sha256,
        "api_url": args.api_url,
        "embedding_model": "bge-m3",
        "embedding_dimension": 1024,
        "tokenizer_path": str(tokenizer_path.resolve()),
        "tokenizer_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "tokenizer_sha256": tokenizer_sha256,
        "max_tokens": args.max_tokens,
        "max_bytes": args.max_bytes,
        "time_mapping": TIME_MAPPING_VERSION,
        "time_mapping_formula": (
            "observed_at = run_anchor_utc - "
            "(max(question_date, haystack_dates) - session_date)"
        ),
        "user_prefix": args.user_prefix,
        "memory_type": args.memory_type,
        "write_endpoint": "/v1/memories",
        "batch_endpoint_used": False,
        "internal_llm": False,
        "memoria_compatibility": (
            "legacy-v0.2.3-no-extra-metadata"
            if args.legacy_v023
            else "current"
        ),
        "memoria_commit": args.memoria_commit,
        "memoria_patch_sha256": args.memoria_patch_sha256,
    }
    atomic_json(path, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[3]
    default_dataset = (
        project_root
        / "memoria/datasets/downloads/public-benchmarks/longmemeval/longmemeval_s_cleaned.json"
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
        default=(
            default_runtime
            / "tokenizer/bge-m3-5617a9f/sentencepiece.bpe.model"
        ),
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--user-prefix", default="longmemeval-")
    parser.add_argument("--memory-type", default="semantic")
    parser.add_argument(
        "--subject-per-session",
        action="store_true",
        help=(
            "Set subject_id=session_id for writes so Memoria near-duplicate "
            "supersession does not collapse distinct benchmark sessions."
        ),
    )
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--legacy-v023",
        action="store_true",
        help="Use idempotence compatible with Memoria v0.2.3 metadata behavior.",
    )
    parser.add_argument("--memoria-commit")
    parser.add_argument("--memoria-patch-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if not args.dataset.is_file():
        raise FileNotFoundError(args.dataset)
    if not args.tokenizer_model.is_file():
        raise FileNotFoundError(args.tokenizer_model)

    env = read_env(args.runtime_env)
    master_key = env.get("MEMORIA_MASTER_KEY", "")
    if not master_key and not args.dry_run:
        raise ValueError("MEMORIA_MASTER_KEY is missing from runtime env")

    args.run_dir.mkdir(parents=True, exist_ok=True)
    dataset_sha256 = sha256_file(args.dataset)
    tokenizer_sha256 = sha256_file(args.tokenizer_model)
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

    with args.dataset.open("r", encoding="utf-8") as handle:
        questions = json.load(handle)
    if args.question_id:
        selected = set(args.question_id)
        questions = [q for q in questions if q["question_id"] in selected]
        missing = selected - {q["question_id"] for q in questions}
        if missing:
            raise ValueError(f"unknown question ids: {sorted(missing)}")
    else:
        questions = questions[args.start_index :]
        if args.limit is not None:
            questions = questions[: args.limit]

    checkpoint = JsonlWriter(args.run_dir / "logs/checkpoint.jsonl")
    errors = JsonlWriter(args.run_dir / "logs/errors.jsonl")
    importer = MemoriaImporter(
        api_url=args.api_url,
        master_key=master_key,
        tokenizer_path=args.tokenizer_model,
        run_anchor_utc=run_anchor,
        checkpoint=checkpoint,
        errors=errors,
        max_tokens=args.max_tokens,
        max_bytes=args.max_bytes,
        user_prefix=args.user_prefix,
        memory_type=args.memory_type,
        subject_per_session=args.subject_per_session,
        timeout=args.timeout,
        max_retries=args.max_retries,
        dry_run=args.dry_run,
        legacy_v023=args.legacy_v023,
    )

    started = time.monotonic()
    results: list[QuestionResult] = []
    unexpected: list[dict[str, str]] = []
    completed = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_map = {
                pool.submit(importer.import_question, question): question["question_id"]
                for question in questions
            }
            for future in concurrent.futures.as_completed(future_map):
                question_id = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    unexpected.append({"question_id": question_id, "error": str(exc)})
                    errors.write(
                        {
                            "at": utc_iso(datetime.now(timezone.utc)),
                            "question_id": question_id,
                            "error": str(exc),
                            "scope": "question",
                        }
                    )
                else:
                    results.append(result)
                completed += 1
                imported = sum(item.imported for item in results)
                skipped = sum(item.skipped for item in results)
                failed = sum(item.failed for item in results) + len(unexpected)
                elapsed = time.monotonic() - started
                print(
                    f"[{completed}/{len(questions)}] question={question_id} "
                    f"imported={imported} skipped={skipped} failed={failed} "
                    f"elapsed={elapsed:.1f}s",
                    flush=True,
                )
    finally:
        checkpoint.close()
        errors.close()

    summary = {
        "finished_at": utc_iso(datetime.now(timezone.utc)),
        "dry_run": args.dry_run,
        "selected_questions": len(questions),
        "completed_questions": len(results),
        "question_failures": unexpected,
        "sessions": sum(item.sessions for item in results),
        "chunks": sum(item.chunks for item in results),
        "imported": sum(item.imported for item in results),
        "skipped_existing": sum(item.skipped for item in results),
        "failed_chunks": sum(item.failed for item in results),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "results": [item.__dict__ for item in sorted(results, key=lambda x: x.question_id)],
    }
    atomic_json(args.run_dir / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    return 1 if unexpected or summary["failed_chunks"] else 0


if __name__ == "__main__":
    sys.exit(main())
