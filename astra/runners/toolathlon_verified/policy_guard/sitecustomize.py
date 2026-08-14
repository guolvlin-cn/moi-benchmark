"""Pin non-interactive Hermes benchmark policy before product imports."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


_PIN_NAMES = (
    "HERMES_HOME",
    "HERMES_YOLO_MODE",
    "HERMES_ACCEPT_HOOKS",
    "HERMES_EXEC_ASK",
    "API_SERVER_ENABLED",
    "API_SERVER_HOST",
    "API_SERVER_PORT",
    "API_SERVER_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "TERMINAL_CWD",
    "TERMINAL_ENV",
)
_PINS = {name: os.environ[name] for name in _PIN_NAMES if os.environ.get(name)}
_ORIGINAL_SETITEM = os._Environ.__setitem__
_ORIGINAL_DELITEM = os._Environ.__delitem__
_ORIGINAL_PUTENV = os.putenv
_ORIGINAL_UNSETENV = os.unsetenv


def _text(key: Any) -> str:
    if isinstance(key, bytes):
        return key.decode(sys.getfilesystemencoding(), "surrogateescape")
    return str(key)


def _value(key: Any, value: str) -> str | bytes:
    return os.fsencode(value) if isinstance(key, bytes) else value


def _setitem(environment: os._Environ[Any], key: Any, value: Any) -> None:
    pinned = _PINS.get(_text(key))
    _ORIGINAL_SETITEM(environment, key, _value(key, pinned) if pinned is not None else value)


def _delitem(environment: os._Environ[Any], key: Any) -> None:
    pinned = _PINS.get(_text(key))
    if pinned is not None:
        _ORIGINAL_SETITEM(environment, key, _value(key, pinned))
    else:
        _ORIGINAL_DELITEM(environment, key)


def _putenv(key: Any, value: Any) -> None:
    pinned = _PINS.get(_text(key))
    _ORIGINAL_PUTENV(key, _value(key, pinned) if pinned is not None else value)


def _unsetenv(key: Any) -> None:
    pinned = _PINS.get(_text(key))
    if pinned is not None:
        _ORIGINAL_PUTENV(key, _value(key, pinned))
    else:
        _ORIGINAL_UNSETENV(key)


def _fail(message: str) -> None:
    os.write(2, f"Toolathlon Hermes policy guard: {message}\n".encode())
    os._exit(126)


source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
if source_hash != os.environ.get("TOOLATHLON_POLICY_GUARD_SHA256", ""):
    _fail("source digest mismatch")

os._Environ.__setitem__ = _setitem
os._Environ.__delitem__ = _delitem
os.putenv = _putenv
os.unsetenv = _unsetenv
for name, value in _PINS.items():
    _ORIGINAL_SETITEM(os.environ, name, value)

evidence_path = os.environ.get("TOOLATHLON_POLICY_GUARD_EVIDENCE", "")
if not evidence_path:
    _fail("evidence path missing")
try:
    evidence = Path(evidence_path)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with evidence.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "event": "policy_guard.loaded",
                    "pid": os.getpid(),
                    "source_sha256": source_hash,
                    "pinned_names": sorted(_PINS),
                    "timestamp": time.time(),
                },
                sort_keys=True,
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())
except OSError as exc:
    _fail(f"evidence write failed: {type(exc).__name__}")
