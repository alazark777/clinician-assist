"""Shared helpers."""

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from clinician_agent.schemas import ProfileRequest, StrictModel


def new_id(prefix: str) -> str:
    """Create an opaque identifier with a stable prefix."""
    return f"{prefix}_{secrets.token_hex(12)}"


def trace_id() -> str:
    """Create a W3C-compatible trace identifier."""
    return uuid.uuid4().hex


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(tz=UTC)


def canonical_input_hash(body: ProfileRequest) -> str:
    """Hash canonical profile input for idempotency."""
    payload = body.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonical_model_json(model: StrictModel) -> str:
    """Serialize a strict model deterministically."""
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def excerpt_text(text: str, limit: int = 240) -> str:
    """Return a bounded excerpt from untrusted source text."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


_SECRET_FIELD_HINTS = ("api_key", "token", "secret", "password", "authorization", "credential")


def safe_log_fields(**fields: Any) -> dict[str, Any]:
    """Drop None values and redact likely secret fields from structured logs."""
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue
        lowered = key.lower()
        if any(hint in lowered for hint in _SECRET_FIELD_HINTS):
            safe[key] = "[REDACTED]"
            continue
        safe[key] = value
    return safe
