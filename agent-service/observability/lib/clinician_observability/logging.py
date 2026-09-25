"""Structured JSON logging with trace correlation and source-side redaction."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from clinician_observability.constants import DEFAULT_LOG_EVENT_ALLOWLIST
from clinician_observability.redaction import scrub_mapping, scrub_text

try:
    from opentelemetry import trace
except ImportError:  # pragma: no cover - optional during minimal imports
    trace = None  # type: ignore[assignment]


class JsonLogFormatter(logging.Formatter):
    """Emit one JSON object per log line with contract fields when present."""

    def __init__(
        self,
        *,
        service_name: str,
        app_env: str,
        event_allowlist: frozenset[str] | None = None,
    ) -> None:
        super().__init__()
        self._service_name = service_name
        self._app_env = app_env
        self._event_allowlist = event_allowlist or DEFAULT_LOG_EVENT_ALLOWLIST

    def format(self, record: logging.LogRecord) -> str:
        """Build a scrubbed JSON log record."""
        event = getattr(record, "event", None)
        if event is not None and event not in self._event_allowlist:
            event = "operational.event"

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "service": self._service_name,
            "environment": self._app_env,
            "event": event or "log.message",
            "message": scrub_text(record.getMessage()),
        }

        for field in (
            "run_id",
            "tool_name",
            "server_name",
            "status",
            "error_code",
            "duration_ms",
            "retry_count",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if trace is not None:
            span = trace.get_current_span()
            ctx = span.get_span_context() if span is not None else None
            if ctx is not None and ctx.is_valid:
                payload["trace_id"] = format(ctx.trace_id, "032x")
                payload["span_id"] = format(ctx.span_id, "016x")

        extra = getattr(record, "structured", None)
        if isinstance(extra, dict):
            payload.update(scrub_mapping(extra))

        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(
    *,
    service_name: str,
    app_env: str,
    level: int = logging.INFO,
    event_allowlist: frozenset[str] | None = None,
) -> None:
    """Attach JSON logging to the root logger (stdout only)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonLogFormatter(
            service_name=service_name,
            app_env=app_env,
            event_allowlist=event_allowlist,
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
