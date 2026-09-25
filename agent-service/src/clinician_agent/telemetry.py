"""OpenTelemetry and safe structured logging."""

from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, Status, StatusCode

from clinician_agent.settings import Settings
from clinician_agent.util import safe_log_fields

_tracer: trace.Tracer | None = None
_configured = False


class JsonLogFormatter(logging.Formatter):
    """Emit scrubbed JSON logs to stdout."""

    def __init__(self, service: str, environment: str) -> None:
        """Bind service metadata."""
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        """Format one log record."""
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "severity": record.levelname,
            "service": self._service,
            "environment": self._environment,
            "event": record.getMessage(),
        }
        extra = getattr(record, "structured", None)
        if isinstance(extra, dict):
            payload.update(extra)
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            payload["trace_id"] = format(ctx.trace_id, "032x")
            payload["span_id"] = format(ctx.span_id, "016x")
        return json.dumps(payload, separators=(",", ":"))


def configure_telemetry(settings: Settings) -> None:
    """Initialize tracing and JSON logging once at startup."""
    global _tracer, _configured
    if _configured:
        return
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)
    if settings.otel_exporter_otlp_endpoint:
        try:
            exporter = OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception:  # noqa: BLE001 - degrade safely
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(settings.otel_service_name)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter(settings.otel_service_name, settings.app_env))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _configured = True


def get_tracer() -> trace.Tracer:
    """Return the configured tracer."""
    if _tracer is None:
        return trace.get_tracer("clinician-agent-api")
    return _tracer


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    """Start a named span with safe attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def log_event(event: str, **fields: Any) -> None:
    """Write a structured operational log line."""
    logger = logging.getLogger("clinician_agent")
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __file__,
        0,
        event,
        (),
        None,
    )
    record.structured = safe_log_fields(**fields)  # type: ignore[attr-defined]
    logger.handle(record)


def set_span_error(span: Span, code: str) -> None:
    """Mark the span failed with a stable code."""
    span.set_status(Status(StatusCode.ERROR, code))
    span.set_attribute("error.code", code)
