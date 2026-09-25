"""Source-side scrubbing for logs, span attributes, and baggage."""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SENSITIVE_ATTRIBUTE_KEYS = frozenset(
    {
        "patient_id",
        "authorization",
        "prompt",
        "completion",
        "record_content",
        "tool_arguments",
        "tool_result",
        "mcp.arguments",
        "mcp.result",
        "http.request.header.authorization",
        "http.response.header.authorization",
        "user.id",
        "enduser.id",
        "exception.message",
        "exception.stacktrace",
    }
)

_PATIENT_ID_PATTERN = re.compile(r"\bP\d{3}[A-Z]?\b")
_BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
)
_SENTINEL_MARK = "[REDACTED]"


def strip_url_query(value: str) -> str:
    """Remove query strings and fragments from URLs before export or logging."""
    parts = urlsplit(value)
    if not parts.scheme:
        return value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def scrub_text(value: str) -> str:
    """Replace known sensitive patterns in free text."""
    redacted = _BEARER_PATTERN.sub(f"Bearer {_SENTINEL_MARK}", value)
    redacted = _JWT_PATTERN.sub(_SENTINEL_MARK, redacted)
    redacted = _PATIENT_ID_PATTERN.sub(_SENTINEL_MARK, redacted)
    return redacted


def scrub_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of payload with sensitive keys removed and strings scrubbed."""
    cleaned: dict[str, Any] = {}
    for key, raw in payload.items():
        if key in SENSITIVE_ATTRIBUTE_KEYS:
            continue
        if key in {"http.url", "url.full"} and isinstance(raw, str):
            cleaned[key] = strip_url_query(scrub_text(raw))
            continue
        if isinstance(raw, str):
            cleaned[key] = scrub_text(raw)
        elif isinstance(raw, Mapping):
            cleaned[key] = scrub_mapping(raw)
        else:
            cleaned[key] = raw
    return cleaned


def apply_span_attribute_allowlist(
    attributes: MutableMapping[str, Any],
    *,
    extra_allowed: frozenset[str] | None = None,
) -> None:
    """Drop sensitive span attributes in place."""
    allowed = extra_allowed or frozenset()
    for key in list(attributes.keys()):
        if key in SENSITIVE_ATTRIBUTE_KEYS and key not in allowed:
            del attributes[key]
        elif isinstance(attributes.get(key), str):
            attributes[key] = scrub_text(str(attributes[key]))


def assert_redaction_sentinels_absent(payload: str, sentinels: tuple[str, ...]) -> list[str]:
    """Return sentinel strings still present after scrubbing (for tests)."""
    missing: list[str] = []
    for sentinel in sentinels:
        if sentinel in payload:
            missing.append(sentinel)
    return missing
