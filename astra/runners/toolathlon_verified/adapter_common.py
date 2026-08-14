from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contract import ContractError, write_json_atomic


PROVIDER_CREDENTIAL_ENV_NAMES = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "CEREBRAS_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "HF_TOKEN",
        "MISTRAL_API_KEY",
        "NOUS_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "TOGETHER_API_KEY",
        "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY",
        "TOOLATHLON_DEEPSEEK_HERMES_API_KEY",
        "XAI_API_KEY",
    }
)


def strip_provider_credentials(environment: dict[str, str]) -> None:
    """Remove inherited provider credentials before starting a product."""

    for name in PROVIDER_CREDENTIAL_ENV_NAMES:
        environment.pop(name, None)


@dataclass(frozen=True)
class AdapterOutcome:
    terminal_status: str
    product_exit_code: int | None
    termination_reason: str
    output: str
    error: str | None
    duration_seconds: float
    product_pid: int | None
    escalated_to_sigkill: bool
    native_events: list[dict[str, Any]]
    metadata: dict[str, Any]
    sensitive_values: tuple[str, ...] = field(default_factory=tuple, repr=False)


class EphemeralState:
    """A run-private product home, preferably on tmpfs, removed on exit."""

    def __init__(self, *, prefix: str, preferred_root: Path | None = None) -> None:
        candidates = [preferred_root] if preferred_root is not None else []
        candidates.extend([Path("/dev/shm"), Path(tempfile.gettempdir())])
        root: Path | None = None
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                if candidate.is_dir() and os.access(candidate, os.W_OK | os.X_OK):
                    root = candidate
                    break
            except OSError:
                continue
        if root is None:
            raise ContractError("no writable root for ephemeral product state")
        self.path = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
        os.chmod(self.path, 0o700)
        self.on_tmpfs = self._is_tmpfs(self.path)

    @staticmethod
    def _is_tmpfs(path: Path) -> bool:
        try:
            best_mount = ""
            best_type = ""
            for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
                fields = line.split()
                if len(fields) < 3:
                    continue
                mount = fields[1].replace("\\040", " ")
                if str(path).startswith(mount.rstrip("/") + "/") and len(mount) > len(best_mount):
                    best_mount = mount
                    best_type = fields[2]
            return best_type in {"tmpfs", "ramfs"}
        except OSError:
            return False

    def close(self) -> None:
        shutil.rmtree(self.path, ignore_errors=False)

    def __enter__(self) -> "EphemeralState":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def write_astra_credentials(directory: Path, access_token: str) -> Path:
    if not access_token:
        raise ContractError("Astra access token is empty")
    directory.mkdir(parents=True, exist_ok=False)
    os.chmod(directory, 0o700)
    path = directory / "credentials.json"
    write_json_atomic(
        path,
        {
            "current_profile": "default",
            "profiles": {"default": {"access_token": access_token}},
        },
        mode=0o600,
    )
    return path


def read_product_json_output(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    candidates = [text, *reversed(text.splitlines())]
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None
