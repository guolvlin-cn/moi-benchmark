from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


VERIFIER_INFRA_EXCEPTION_TYPES = frozenset(
    {
        "VerifierInfrastructureError",
        "VerifierTimeoutError",
        "RewardFileNotFoundError",
        "RewardFileEmptyError",
        "VerifierOutputParseError",
        "DownloadVerifierDirError",
        "AddTestsDirError",
    }
)


class VerifierEvidenceError(RuntimeError):
    pass


def validate_binary_reward(value: Any) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) not in {0.0, 1.0}
    ):
        raise VerifierEvidenceError(
            "verifier reward must be the finite number 0 or 1"
        )
    return float(value)


def validate_ctrf_report(path: Path) -> dict[str, Any]:
    """Require evidence that pytest actually collected and ran tests."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VerifierEvidenceError("verifier did not produce ctrf.json") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifierEvidenceError("verifier produced unreadable ctrf.json") from exc

    results = payload.get("results") if isinstance(payload, dict) else None
    summary = results.get("summary") if isinstance(results, dict) else None
    tests = results.get("tests") if isinstance(results, dict) else None
    test_count = summary.get("tests") if isinstance(summary, dict) else None
    if (
        type(test_count) is not int
        or test_count <= 0
        or not isinstance(tests, list)
        or len(tests) != test_count
    ):
        raise VerifierEvidenceError(
            "ctrf.json does not prove that any tests were executed"
        )
    if any(not isinstance(test, dict) for test in tests):
        raise VerifierEvidenceError("ctrf.json contains an invalid test record")
    if not any(test.get("status") in {"passed", "failed"} for test in tests):
        raise VerifierEvidenceError(
            "ctrf.json does not prove that any test completed"
        )
    return {"test_count": test_count}
