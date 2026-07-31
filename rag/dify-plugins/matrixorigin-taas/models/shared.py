from __future__ import annotations

import base64
import binascii
from typing import Any

import httpx
from dify_plugin.entities.model.text_embedding import MultiModalContent, MultiModalContentType
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)


DEFAULT_BASE_URL = "https://api-taas.moi.matrixorigin.cn/v1"


def base_url(credentials: dict) -> str:
    return str(credentials.get("base_url") or DEFAULT_BASE_URL).rstrip("/")


def headers(credentials: dict) -> dict[str, str]:
    api_key = str(credentials.get("api_key") or "").strip()
    if not api_key:
        raise InvokeAuthorizationError("TaaS API key is required")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def post_json(credentials: dict, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = httpx.post(
            f"{base_url(credentials)}{path}",
            headers=headers(credentials),
            json=payload,
            timeout=120,
        )
    except httpx.RequestError as exc:
        raise InvokeConnectionError(str(exc)) from exc

    if response.status_code >= 400:
        try:
            body = response.json()
            error = body.get("error") or body.get("detail") or body.get("message") or body
            if isinstance(error, dict):
                message = str(error.get("message") or error)
            else:
                message = str(error)
        except ValueError:
            message = response.text[:1000]

        if response.status_code in (401, 403):
            raise InvokeAuthorizationError(message)
        if response.status_code == 429:
            raise InvokeRateLimitError(message)
        if response.status_code >= 500:
            raise InvokeServerUnavailableError(message)
        raise InvokeBadRequestError(message)

    try:
        return response.json()
    except ValueError as exc:
        raise InvokeServerUnavailableError(
            f"TaaS returned invalid JSON: {response.text[:1000]}"
        ) from exc


def image_data_url(value: str) -> str:
    value = value.strip()
    if value.startswith(("data:", "http://", "https://")):
        return value

    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvokeBadRequestError(
            "Image content must be a URL, data URL, or base64-encoded image"
        ) from exc

    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif raw.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        mime = "image/webp"
    elif raw.startswith(b"BM"):
        mime = "image/bmp"
    else:
        raise InvokeBadRequestError("Unsupported image format")
    return f"data:{mime};base64,{value}"


def multimodal_content(value: MultiModalContent) -> dict[str, Any]:
    if value.content_type == MultiModalContentType.TEXT:
        return {
            "content": [
                {
                    "type": "text",
                    "text": value.content,
                }
            ]
        }
    if value.content_type == MultiModalContentType.IMAGE:
        return {
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url(value.content)},
                }
            ]
        }
    raise InvokeBadRequestError(f"Unsupported multimodal content type: {value.content_type}")
