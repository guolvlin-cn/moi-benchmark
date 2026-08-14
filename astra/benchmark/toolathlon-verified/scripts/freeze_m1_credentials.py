#!/usr/bin/env python3
"""Freeze Toolathlon credential fingerprints without persisting secret values."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any, Iterable


EXPECTED_COMMIT = "2aed2468858f15818acafa178518390cc4b0f5cb"
PLACEHOLDERS = frozenset({"", "xx", "xxx", "changeme", "replace-me", "your_token"})
RUNTIME_SECRET_ENVS = (
    "TOOLATHLON_DEEPSEEK_ASTRA_API_KEY",
    "TOOLATHLON_DEEPSEEK_HERMES_API_KEY",
    "ASTRA_ADMIN_ACCESS_TOKEN",
)
REQUIRED_TOOLATHLON_FIELDS = (
    "serper_api_key",
    "google_cloud_console_api_key",
    "gcp_project_id",
    "gcp_service_account_path",
    "google_client_id",
    "google_client_secret",
    "google_refresh_token",
    "github_token",
    "huggingface_token",
    "wandb_api_key",
    "notion_integration_key",
    "notion_integration_key_eval",
    "source_notion_page_url",
    "eval_notion_page_url",
    "snowflake_account",
    "snowflake_user",
    "snowflake_private_key_path",
    "canvas_api_token",
    "canvas_domain",
    "woocommerce_api_key",
    "woocommerce_api_secret",
    "woocommerce_site_url",
    "kubeconfig_path",
    "emails_config_file",
)
DIRECT_CREDENTIAL_PATHS = (
    "configs/global_configs.py",
    "configs/token_key_session.py",
    "configs/gcp-oauth.keys.json",
    "configs/gcp-service_account.keys.json",
    "configs/google_credentials.json",
    "configs/snowflake_rsa_key.p8",
    "configs/snowflake_rsa_key.pub",
    "deployment/canvas/configs/canvas_admin_tokens.txt",
    "deployment/canvas/configs/canvas_admin_users.json",
    "deployment/canvas/configs/canvas_tokens.txt",
    "deployment/canvas/configs/canvas_users.json",
    "deployment/poste/configs/created_accounts.json",
    "deployment/woocommerce/configs/multisite-api-keys.json",
    "deployment/woocommerce/configs/wc-api-credentials.json",
    "deployment/k8s/configs/cluster-inst-alpha1-config.yaml",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def git_head(source: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def path_record(source: Path, path: Path, *, category: str) -> dict[str, Any]:
    relative = path.relative_to(source).as_posix()
    mode = stat.S_IMODE(path.stat().st_mode)
    runtime_mutable = (
        category == "mcp_oauth"
        and relative.startswith("configs/.mcp-auth/")
        and path.name.endswith("_tokens.json")
    )
    return {
        "category": category,
        "path": relative,
        "mode": oct(mode),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "content_policy": (
            "runtime_refreshable_oauth_token"
            if runtime_mutable
            else "immutable_fingerprint"
        ),
        "runtime_mutable": runtime_mutable,
        "runtime_copy_mode": "0o600",
    }


def credential_paths(source: Path) -> list[tuple[Path, str]]:
    records: dict[Path, str] = {}
    for relative in DIRECT_CREDENTIAL_PATHS:
        path = source / relative
        if path.is_file():
            records[path] = "global_or_local_application"
    auth_root = source / "configs" / ".mcp-auth"
    if auth_root.is_dir():
        for path in sorted(auth_root.rglob("*")):
            if path.is_file():
                records[path] = "mcp_oauth"
    task_root = source / "tasks" / "finalpool"
    for path in sorted(task_root.glob("*/token_key_session.py")):
        records[path] = "task_scoped_override"
    for pattern in ("*/*email*config*.json", "*/email_config.json", "*/emails_config.json"):
        for path in sorted(task_root.glob(pattern)):
            if path.is_file():
                records[path] = "task_scoped_email"
    return sorted(records.items(), key=lambda item: item[0].as_posix())


def ast_placeholder_count(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.strip().lower() in PLACEHOLDERS:
                count += 1
    return count


def inspect_token_mapping(source: Path) -> dict[str, Any]:
    python = source / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path("/usr/bin/python3")
    helper = r'''
import hashlib, json, os, sys
from pathlib import Path
source = Path(sys.argv[1]).resolve()
os.chdir(source)
sys.path.insert(0, str(source))
from configs.token_key_session import all_token_key_session
required = json.loads(sys.argv[2])
placeholders = {"", "xx", "xxx", "changeme", "replace-me", "your_token"}
out = {}
for name in required:
    value = all_token_key_session.get(name)
    text = "" if value is None else str(value)
    out[name] = {
        "present": value is not None and bool(text.strip()),
        "placeholder": text.strip().lower() in placeholders,
        "value_type": type(value).__name__,
        "value_length": len(text),
        "value_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
    }
print(json.dumps(out, sort_keys=True))
'''
    result = subprocess.run(
        [
            str(python),
            "-c",
            helper,
            str(source),
            json.dumps(REQUIRED_TOOLATHLON_FIELDS),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {
            "state": "NO_GO",
            "reason": "credential mapping could not be loaded",
            "required_field_count": len(REQUIRED_TOOLATHLON_FIELDS),
        }
    try:
        fields = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "state": "NO_GO",
            "reason": "credential mapping inspector returned invalid JSON",
            "required_field_count": len(REQUIRED_TOOLATHLON_FIELDS),
        }
    invalid = [
        name
        for name, item in fields.items()
        if not item.get("present") or item.get("placeholder")
    ]
    return {
        "state": "GO" if not invalid else "NO_GO",
        "required_field_count": len(fields),
        "invalid_fields": sorted(invalid),
        "fields": fields,
    }


def runtime_environment_records() -> dict[str, Any]:
    records: dict[str, Any] = {}
    raw_values: dict[str, str] = {}
    for name in RUNTIME_SECRET_ENVS:
        value = os.environ.get(name, "")
        if value:
            raw_values[name] = value
        records[name] = {
            "present": bool(value),
            "value_length": len(value),
            "value_sha256": sha256_bytes(value.encode("utf-8")) if value else None,
        }
    astra = raw_values.get("TOOLATHLON_DEEPSEEK_ASTRA_API_KEY")
    hermes = raw_values.get("TOOLATHLON_DEEPSEEK_HERMES_API_KEY")
    return {
        "state": "GO" if len(raw_values) == len(RUNTIME_SECRET_ENVS) and astra != hermes else "PENDING",
        "deepseek_keys_distinct": bool(astra and hermes and astra != hermes),
        "variables": records,
    }


def assert_no_secret_values(serialized: str, values: Iterable[str]) -> None:
    for value in values:
        if value and value in serialized:
            raise SystemExit("refusing to write manifest containing a runtime secret value")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-at", required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    commit = git_head(source)
    if commit != EXPECTED_COMMIT:
        raise SystemExit(f"unexpected Toolathlon commit: {commit}")

    located = credential_paths(source)
    records = [path_record(source, path, category=category) for path, category in located]
    token_mapping = inspect_token_mapping(source)
    runtime = runtime_environment_records()
    auth_files = [item for item in records if item["category"] == "mcp_oauth"]
    mutable_auth_files = [item for item in auth_files if item["runtime_mutable"]]
    task_files = [item for item in records if item["category"].startswith("task_scoped")]
    source_placeholders = sum(
        ast_placeholder_count(path)
        for path, _category in located
        if path.suffix == ".py" and "_example" not in path.name
    )

    toolathlon_state = "GO"
    reasons: list[str] = []
    for required in ("configs/global_configs.py", "configs/token_key_session.py"):
        if not (source / required).is_file():
            toolathlon_state = "NO_GO"
            reasons.append(f"missing {required}")
    if not auth_files:
        toolathlon_state = "NO_GO"
        reasons.append("missing configs/.mcp-auth runtime files")
    if token_mapping.get("state") != "GO":
        toolathlon_state = "NO_GO"
        reasons.append("required Toolathlon credential fields are incomplete")

    overall_state = (
        "GO" if toolathlon_state == "GO" and runtime["state"] == "GO" else "PARTIAL_GO"
    )
    manifest = {
        "schema_version": "toolathlon.credentials.freeze.v2",
        "source_commit": commit,
        "frozen_at": args.frozen_at,
        "state": overall_state,
        "secret_values_recorded": False,
        "fingerprint_algorithm": "sha256",
        "runtime_secret_delivery": "trusted orchestrator to per-system Model Proxy only",
        "runtime_copy_policy": (
            "credential material enters only the task container with mode 0600 and is excluded "
            "from result artifacts; allowlisted OAuth token files may rotate in place and each "
            "attempt records before/after hashes"
        ),
        "toolathlon_application_credentials": {
            "state": toolathlon_state,
            "reasons": reasons,
            "source_file_count": len(records),
            "task_scoped_file_count": len(task_files),
            "mcp_oauth_file_count": len(auth_files),
            "runtime_mutable_oauth_file_count": len(mutable_auth_files),
            "literal_placeholder_occurrences": source_placeholders,
            "mapping": token_mapping,
            "files": records,
            "root_sha256": canonical_sha256(records),
        },
        "runtime_product_and_model_credentials": runtime,
    }
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert_no_secret_values(
        serialized,
        (os.environ.get(name, "") for name in RUNTIME_SECRET_ENVS),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    os.chmod(temporary, 0o644)
    os.replace(temporary, output)
    print(
        json.dumps(
            {
                "state": overall_state,
                "toolathlon_credentials": toolathlon_state,
                "runtime_credentials": runtime["state"],
                "credential_files": len(records),
                "task_scoped_files": len(task_files),
                "mcp_auth_files": len(auth_files),
                "output_sha256": sha256_file(output),
            },
            sort_keys=True,
        )
    )
    return 0 if toolathlon_state == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
