from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from . import EVENT_SCHEMA_VERSION


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class ContractError(ValueError):
    """The run input violates the frozen Adapter contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def write_json_atomic(path: Path, value: Any, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"expected a JSON object in {path}")
    return value


def validate_id(label: str, value: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ContractError(f"{label} is not a safe identifier")
    return value


def validate_loopback_url(label: str, value: str, *, require_sse: bool = False) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS:
        raise ContractError(f"{label} must be an http loopback URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ContractError(f"{label} must not contain credentials or a fragment")
    if require_sse and not parsed.path.rstrip("/").endswith("/sse"):
        raise ContractError(f"{label} must identify the Gateway /sse endpoint")
    return value


def ensure_descendant(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    root = parent.resolve()
    if resolved != root and root not in resolved.parents:
        raise ContractError(f"{label} must be within {root}")
    return resolved


@dataclass(frozen=True)
class ModelFreeze:
    provider: str
    provider_base_url: str
    request_model_id: str
    documented_model_version: str
    temperature: float
    thinking: str
    thinking_wire_behavior: str
    reasoning_effort: str
    reasoning_effort_wire_behavior: str
    max_model_requests: int

    @classmethod
    def load(cls, path: Path) -> "ModelFreeze":
        raw = read_json_object(path)
        try:
            endpoint = raw["endpoint"]
            model = raw["model"]
            generation = raw["generation"]
            budget = raw["request_budget"]
            result = cls(
                provider=str(endpoint["provider"]),
                provider_base_url=str(endpoint["base_url"]),
                request_model_id=str(model["request_id"]),
                documented_model_version=str(model["documented_version"]),
                temperature=float(generation["temperature"]["value"]),
                thinking=str(generation["thinking"]["value"]),
                thinking_wire_behavior=str(
                    generation["thinking"]["wire_behavior"]
                ),
                reasoning_effort=str(generation["reasoning_effort"]["value"]),
                reasoning_effort_wire_behavior=str(
                    generation["reasoning_effort"]["wire_behavior"]
                ),
                max_model_requests=int(budget["max_product_model_requests"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"invalid model freeze {path}") from exc
        if (
            result.provider != "deepseek"
            or result.provider_base_url.rstrip("/") != "https://api.deepseek.com"
            or result.request_model_id != "deepseek-v4-flash"
            or result.documented_model_version != "DeepSeek-V4-Flash-0731"
            or result.temperature != 0.0
            or result.thinking != "enabled"
            or result.thinking_wire_behavior != "sent"
            or result.reasoning_effort != "max"
            or result.reasoning_effort_wire_behavior != "sent"
            or result.max_model_requests != 100
        ):
            raise ContractError("model freeze does not match the approved 3.3 policy")
        return result


@dataclass(frozen=True)
class RunSpec:
    system_id: str
    experiment_id: str
    run_id: str
    task_id: str
    bundle_file: Path
    gateway_url: str
    workspace: Path
    output_dir: Path
    deadline_s: int
    max_model_requests: int
    model_freeze_path: Path
    task_requirements_manifest_path: Path
    permission_policy_path: Path

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RunSpec":
        try:
            result = cls(
                system_id=str(raw["system_id"]),
                experiment_id=validate_id("experiment_id", str(raw["experiment_id"])),
                run_id=validate_id("run_id", str(raw["run_id"])),
                task_id=validate_id("task_id", str(raw["task_id"])),
                bundle_file=Path(str(raw["bundle_file"])).resolve(),
                gateway_url=validate_loopback_url(
                    "gateway_url", str(raw["gateway_url"]), require_sse=True
                ),
                workspace=Path(str(raw["workspace"])).resolve(),
                output_dir=Path(str(raw["output_dir"])).resolve(),
                deadline_s=int(raw["deadline_s"]),
                max_model_requests=int(raw["max_model_requests"]),
                model_freeze_path=Path(str(raw["model_freeze"])).resolve(),
                task_requirements_manifest_path=Path(
                    str(raw["task_requirements_manifest"])
                ).resolve(),
                permission_policy_path=Path(
                    str(raw["permission_policy"])
                ).resolve(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("invalid run specification") from exc
        if result.system_id not in {"astra", "hermes"}:
            raise ContractError("system_id must be astra or hermes")
        if result.deadline_s not in {1800, 2700, 3600, 5400}:
            raise ContractError("deadline_s must be a frozen runtime tier value")
        if result.max_model_requests != 100:
            raise ContractError("max_model_requests must equal the frozen value 100")
        for label, path in (
            ("bundle_file", result.bundle_file),
            ("model_freeze", result.model_freeze_path),
            ("task_requirements_manifest", result.task_requirements_manifest_path),
            ("permission_policy", result.permission_policy_path),
        ):
            if not path.is_file():
                raise ContractError(f"{label} is not a regular file: {path}")
        if not result.workspace.is_dir():
            raise ContractError(f"workspace is not a directory: {result.workspace}")
        if result.output_dir.exists():
            existing = {
                path.name for path in result.output_dir.iterdir()
            }
            if not existing.issubset(
                {
                    "lifecycle-events.jsonl",
                    "resource-usage.jsonl",
                    "task-state",
                    "preprocess.log",
                    "permission-policy.json",
                }
            ):
                raise ContractError(
                    "output_dir contains files outside the prepared lifecycle boundary"
                )
        return result


class JsonlEventWriter:
    """Append-only, fsync-backed event evidence with a per-run sequence."""

    def __init__(self, path: Path, *, run_id: str, system_id: str) -> None:
        self.path = path
        self.run_id = validate_id("run_id", run_id)
        self.system_id = system_id
        self._sequence = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size:
            raise ContractError(f"event stream already exists: {path}")

    def append(self, event: str, **fields: Any) -> dict[str, Any]:
        self._sequence += 1
        record = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "run_id": self.run_id,
            "system_id": self.system_id,
            "sequence": self._sequence,
            "timestamp": utc_now(),
            "monotonic_ns": time.monotonic_ns(),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record

    @property
    def sequence(self) -> int:
        return self._sequence


def write_sha256_manifest(path: Path, files: Iterable[Path], *, root: Path) -> None:
    root = root.resolve()
    records: list[tuple[str, str]] = []
    for file_path in sorted((item.resolve() for item in files), key=str):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(root).as_posix()
        records.append((sha256_file(file_path), relative))
    payload = "".join(f"{digest}  {relative}\n" for digest, relative in records)
    path.write_text(payload, encoding="utf-8")


def assert_no_secret_values(paths: Iterable[Path], secret_values: Iterable[str]) -> None:
    needles = [item.encode("utf-8") for item in secret_values if item]
    if not needles:
        return
    for path in paths:
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if any(needle in payload for needle in needles):
            raise ContractError(f"secret value leaked into run artifact: {path}")
