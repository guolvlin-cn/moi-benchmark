"""Central local environment loader for all competitor-facing tools.

The repository root ``.env`` is the only credential entry point.  Explicit
process variables still win, which keeps CI and one-off dry-runs possible
without writing secrets to disk.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, MutableMapping


REPO_ROOT = Path(__file__).resolve().parents[1]
CENTRAL_ENV_FILE = REPO_ROOT / ".env"


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse simple dotenv assignments without printing or validating values."""

    values: dict[str, str] = {}
    env_path = Path(path)
    if not env_path.is_file():
        return values
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_central_env(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load root ``.env`` and let explicit process values override it."""

    values = parse_env_file(CENTRAL_ENV_FILE)
    values.update(dict(os.environ if environ is None else environ))
    return values


def inject_central_env(
    environ: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    """Populate a process mapping from root ``.env`` without overwriting it."""

    target = os.environ if environ is None else environ
    for key, value in parse_env_file(CENTRAL_ENV_FILE).items():
        target.setdefault(key, value)
    return target


__all__ = [
    "CENTRAL_ENV_FILE",
    "REPO_ROOT",
    "inject_central_env",
    "load_central_env",
    "parse_env_file",
]
