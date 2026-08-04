#!/usr/bin/env python3
"""Freeze a ZAI sampling temperature into the pinned Hermes source tree."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


EXPECTED_ZAI_SOURCE_SHA256 = (
    "cc5fa60f47bec6f0b1e3bc28d34e6182758efa400344ecb4342e53bdb61c10f4"
)
C0_TEMPERATURE = "0.0"
ZAI_PROVIDER_PATH = Path("plugins/model-providers/zai/__init__.py")
INSERT_AFTER = '    default_aux_model="glm-4.5-flash",\n'


def normalize_temperature(raw: str) -> str:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("temperature must be a decimal number") from exc
    if not value.is_finite() or value < 0 or value > 1:
        raise ValueError("temperature must be in [0, 1]")
    if value.as_tuple().exponent < -2:
        raise ValueError("temperature must have at most two decimal places")
    normalized = format(value.normalize(), "f")
    if "." not in normalized:
        normalized += ".0"
    return normalized


def apply_temperature(
    repo_root: Path,
    audit_dir: Path,
    raw_temperature: str,
) -> dict[str, object]:
    temperature = normalize_temperature(raw_temperature)
    if temperature != C0_TEMPERATURE:
        raise ValueError(
            f"Hermes C0 image temperature is frozen at {C0_TEMPERATURE}"
        )
    source_path = repo_root / ZAI_PROVIDER_PATH
    original = source_path.read_bytes()
    original_sha256 = hashlib.sha256(original).hexdigest()
    if original_sha256 != EXPECTED_ZAI_SOURCE_SHA256:
        raise RuntimeError(
            "pinned ZAI provider source digest does not match the expected "
            "Hermes revision"
        )

    text = original.decode("utf-8")
    if text.count(INSERT_AFTER) != 1:
        raise RuntimeError("could not locate the unique ZAI profile insertion point")
    replacement = (
        INSERT_AFTER
        + f"    fixed_temperature={temperature},\n"
    )
    patched = text.replace(INSERT_AFTER, replacement, 1)
    source_path.write_text(patched, encoding="utf-8")

    patch = "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{ZAI_PROVIDER_PATH}",
            tofile=f"b/{ZAI_PROVIDER_PATH}",
        )
    )
    patch_sha256 = hashlib.sha256(patch.encode()).hexdigest()
    patched_source_sha256 = hashlib.sha256(
        patched.encode()
    ).hexdigest()
    audit = {
        "schema_version": 1,
        "provider": "zai",
        "model": "glm-5.2",
        "temperature": float(temperature),
        "temperature_literal": temperature,
        "application": "provider_profile.fixed_temperature",
        "scope": "primary_zai_chat_completions",
        "base_source_sha256": original_sha256,
        "patched_source_sha256": patched_source_sha256,
        "patch_sha256": patch_sha256,
    }

    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "hermes-temperature").write_text(
        temperature + "\n",
        encoding="utf-8",
    )
    (audit_dir / "hermes-temperature.patch").write_text(
        patch,
        encoding="utf-8",
    )
    (audit_dir / "hermes-temperature.patch.sha256").write_text(
        patch_sha256 + "\n",
        encoding="utf-8",
    )
    (audit_dir / "hermes-temperature.json").write_text(
        json.dumps(audit, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser("normalize")
    normalize.add_argument("temperature")

    apply = subparsers.add_parser("apply")
    apply.add_argument("--repo-root", type=Path, required=True)
    apply.add_argument("--audit-dir", type=Path, required=True)
    apply.add_argument("--temperature", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "normalize":
        print(normalize_temperature(args.temperature))
        return 0
    audit = apply_temperature(
        args.repo_root,
        args.audit_dir,
        args.temperature,
    )
    print(json.dumps(audit, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
