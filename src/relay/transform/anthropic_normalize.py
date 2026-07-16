from __future__ import annotations

import json
import re
from typing import Any

FIREWORKS_REQUEST_EXTENSIONS = frozenset({"raw_output", "inference_geo"})
FIREWORKS_RESPONSE_EXTRA_KEYS = frozenset({"raw_output", "object"})
_MSG_ID_RE = re.compile(r"^msg_[a-zA-Z0-9]+$")


def prepare_fireworks_request_body(
    body: dict[str, Any],
    *,
    strip_extensions: bool = True,
) -> dict[str, Any]:
    cleaned = dict(body)
    if strip_extensions:
        for key in FIREWORKS_REQUEST_EXTENSIONS:
            cleaned.pop(key, None)
    return cleaned


def normalize_anthropic_response(
    payload: dict[str, Any],
    *,
    client_model: str | None,
    rewrite_model: bool,
) -> dict[str, Any]:
    if payload.get("type") == "error":
        return payload

    out = dict(payload)
    for key in FIREWORKS_RESPONSE_EXTRA_KEYS:
        out.pop(key, None)

    if rewrite_model and client_model:
        out["model"] = client_model

    out.setdefault("type", "message")
    out.setdefault("role", "assistant")
    if "id" in out and isinstance(out["id"], str):
        out["id"] = _anthropic_style_id(out["id"])
    out.setdefault("content", [])
    if "usage" in out and isinstance(out["usage"], dict):
        out["usage"] = _normalize_usage(out["usage"])

    return out


def rewrite_sse_chunk(
    chunk: bytes,
    *,
    client_model: str | None,
    rewrite_model: bool,
) -> bytes:
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        return chunk

    lines = text.split("\n")
    changed = False
    out_lines: list[str] = []

    for line in lines:
        if line.startswith("data:"):
            raw = line[5:].lstrip()
            if raw and raw != "[DONE]":
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    out_lines.append(line)
                    continue
                if isinstance(data, dict):
                    new_data = _normalize_sse_event(
                        data,
                        client_model=client_model,
                        rewrite_model=rewrite_model,
                    )
                    if new_data is not data:
                        changed = True
                        out_lines.append(
                            "data: " + json.dumps(new_data, separators=(",", ":"))
                        )
                        continue
        out_lines.append(line)

    if not changed:
        return chunk
    return "\n".join(out_lines).encode("utf-8")


def _normalize_sse_event(
    event: dict[str, Any],
    *,
    client_model: str | None,
    rewrite_model: bool,
) -> dict[str, Any]:
    etype = event.get("type")
    if etype == "message_start" and isinstance(event.get("message"), dict):
        message = normalize_anthropic_response(
            event["message"],
            client_model=client_model,
            rewrite_model=rewrite_model,
        )
        return {**event, "message": message}

    if etype == "message_delta" and isinstance(event.get("usage"), dict):
        return {**event, "usage": _normalize_usage(event["usage"])}

    if rewrite_model and client_model and "model" in event:
        return {**event, "model": client_model}

    return event


def _normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        if key in usage:
            out[key] = usage[key]
    out.setdefault("input_tokens", usage.get("input_tokens", 0))
    out.setdefault("output_tokens", usage.get("output_tokens", 0))
    return out


def _anthropic_style_id(message_id: str) -> str:
    if _MSG_ID_RE.match(message_id) or message_id.startswith("msg_"):
        return message_id
    safe = re.sub(r"[^a-zA-Z0-9]", "", message_id) or "relay"
    return f"msg_{safe[:64]}"
