from __future__ import annotations

import hashlib
import json
import os
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contract import ContractError, sha256_file, utc_now, write_json_atomic


PRIVATE_IDENTITY_FILENAME = "product-identity.private.json"
PRIVATE_IDENTITY_SCHEMA = "toolathlon.astra-product-identity.private.v1"


class ProductIdentityError(ContractError):
    pass


@dataclass(frozen=True)
class AstraProductIdentity:
    identity_id: str
    attempt_ordinal: int
    username: str
    email: str
    server_user_id: str
    access_token: str = field(repr=False)
    password: str = field(repr=False)


def attempt_label(attempt_ordinal: int) -> str:
    if attempt_ordinal not in {1, 2}:
        raise ProductIdentityError("product identity attempt must be 1 or 2")
    return f"a{attempt_ordinal}"


def _request_json(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    access_token: str | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict[str, Any]]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers: dict[str, str] = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if access_token is not None:
        headers["Authorization"] = f"Bearer {access_token}"
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            value = json.loads(raw) if raw else {}
            if not isinstance(value, dict):
                raise ProductIdentityError("Astra identity API returned a non-object response")
            return int(response.status), value
    except urllib.error.HTTPError as exc:
        # Never include a response body: it is outside the benchmark's redaction contract.
        raise ProductIdentityError(
            f"Astra identity API {method} failed with HTTP {exc.code}"
        ) from None
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise ProductIdentityError(
            f"Astra identity API {method} transport failed ({type(exc).__name__})"
        ) from None
    except json.JSONDecodeError:
        raise ProductIdentityError("Astra identity API returned invalid JSON") from None


def _private_record(
    *,
    identity_id: str,
    experiment_id: str,
    task_id: str,
    run_id: str,
    attempt_ordinal: int,
    username: str,
    password: str,
    email: str,
    registration_status: str,
    server_user_id: str | None = None,
    auth_me_verified: bool = False,
    failure_type: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PRIVATE_IDENTITY_SCHEMA,
        "identity_id": identity_id,
        "experiment_id": experiment_id,
        "task_id": task_id,
        "run_id": run_id,
        "attempt_ordinal": attempt_ordinal,
        "attempt_label": attempt_label(attempt_ordinal),
        "strategy": "astra_registered_user_per_attempt",
        "username": username,
        "password": password,
        "email": email,
        "registration_status": registration_status,
        "server_user_id": server_user_id,
        "auth_me_verified": auth_me_verified,
        "failure_type": failure_type,
        "created_at": utc_now(),
        "handling": {
            "file_mode": "0o600",
            "publish": False,
            "contains_plaintext_product_password": True,
            "contains_access_or_refresh_token": False,
        },
    }


def provision_astra_identity(
    *,
    api_url: str,
    output_dir: Path,
    experiment_id: str,
    task_id: str,
    run_id: str,
    attempt_ordinal: int,
) -> AstraProductIdentity:
    label = attempt_label(attempt_ordinal)
    random_suffix = secrets.token_hex(6)
    stable = hashlib.sha256(
        f"{experiment_id}\0{task_id}\0{run_id}\0{label}".encode("utf-8")
    ).hexdigest()[:16]
    identity_id = f"astra-{stable}-{label}-{random_suffix}"
    username = f"tva_{stable}_{label}_{random_suffix}"
    email = f"{username}@toolathlon.invalid"
    password = secrets.token_urlsafe(32)
    private_path = output_dir / PRIVATE_IDENTITY_FILENAME
    pending = _private_record(
        identity_id=identity_id,
        experiment_id=experiment_id,
        task_id=task_id,
        run_id=run_id,
        attempt_ordinal=attempt_ordinal,
        username=username,
        password=password,
        email=email,
        registration_status="pending",
    )
    write_json_atomic(private_path, pending, mode=0o600)

    try:
        status, registered = _request_json(
            "POST",
            f"{api_url.rstrip('/')}/auth/register",
            body={
                "username": username,
                "email": email,
                "password": password,
                "display_name": None,
            },
        )
        if status != 201:
            raise ProductIdentityError(
                f"Astra identity registration returned unexpected HTTP {status}"
            )
        access_token = registered.get("access_token")
        server_user_id = registered.get("user_id")
        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(server_user_id, str)
            or not server_user_id
            or registered.get("username") != username
            or registered.get("email") != email
        ):
            raise ProductIdentityError("Astra identity registration response mismatch")
        me_status, me = _request_json(
            "GET",
            f"{api_url.rstrip('/')}/auth/me",
            access_token=access_token,
        )
        if (
            me_status != 200
            or me.get("user_id") != server_user_id
            or me.get("username") != username
            or me.get("email") != email
        ):
            raise ProductIdentityError("Astra /auth/me identity mismatch")
    except BaseException as exc:
        failed = dict(pending)
        failed["registration_status"] = "failed"
        failed["failure_type"] = type(exc).__name__
        write_json_atomic(private_path, failed, mode=0o600)
        raise

    complete = _private_record(
        identity_id=identity_id,
        experiment_id=experiment_id,
        task_id=task_id,
        run_id=run_id,
        attempt_ordinal=attempt_ordinal,
        username=username,
        password=password,
        email=email,
        registration_status="verified",
        server_user_id=server_user_id,
        auth_me_verified=True,
    )
    write_json_atomic(private_path, complete, mode=0o600)
    return AstraProductIdentity(
        identity_id=identity_id,
        attempt_ordinal=attempt_ordinal,
        username=username,
        email=email,
        server_user_id=server_user_id,
        access_token=access_token,
        password=password,
    )


def private_identity_projection(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductIdentityError("cannot read Astra private identity record") from exc
    if not isinstance(record, dict) or record.get("schema_version") != PRIVATE_IDENTITY_SCHEMA:
        raise ProductIdentityError("invalid Astra private identity record")
    if path.stat().st_mode & 0o077:
        raise ProductIdentityError("Astra private identity record is not mode 0600")
    username = record.get("username")
    password = record.get("password")
    if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
        raise ProductIdentityError("Astra private identity record has no credentials")
    server_user_id = record.get("server_user_id")
    return {
        "strategy": "astra_registered_user_per_attempt",
        "identity_id": record.get("identity_id"),
        "attempt_ordinal": record.get("attempt_ordinal"),
        "attempt_label": record.get("attempt_label"),
        "registration_status": record.get("registration_status"),
        "auth_me_verified": record.get("auth_me_verified") is True,
        "username_sha256": hashlib.sha256(username.encode("utf-8")).hexdigest(),
        "server_user_id_sha256": (
            hashlib.sha256(server_user_id.encode("utf-8")).hexdigest()
            if isinstance(server_user_id, str) and server_user_id
            else None
        ),
        "private_record": PRIVATE_IDENTITY_FILENAME,
        "private_record_sha256": sha256_file(path),
        "private_record_mode": oct(path.stat().st_mode & 0o777),
        "plaintext_password_persisted": True,
        "access_or_refresh_token_persisted": False,
        "true_server_user_identity": True,
        "provider_user_id_is_product_identity": False,
    }
