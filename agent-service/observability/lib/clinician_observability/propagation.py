"""W3C trace context helpers for API to MCP requests."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_PROPAGATOR = TraceContextTextMapPropagator()


class _HeaderCarrier(MutableMapping[str, str]):
    def __init__(self, headers: MutableMapping[str, str]) -> None:
        self._headers = headers

    def __getitem__(self, key: str) -> str:
        return self._headers[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._headers[key] = value

    def __delitem__(self, key: str) -> None:
        del self._headers[key]

    def __iter__(self):
        return iter(self._headers)

    def __len__(self) -> int:
        return len(self._headers)


def inject_trace_headers(headers: MutableMapping[str, str]) -> None:
    """Inject traceparent/tracestate into outbound MCP HTTP headers."""
    inject(_HeaderCarrier(headers))


def parent_context_from_headers(headers: Mapping[str, Any]) -> otel_context.Context:
    """Extract W3C trace context from inbound HTTP headers."""
    normalized = {k.lower(): v for k, v in headers.items() if isinstance(v, str)}
    return extract(normalized)


def start_client_span(
    tracer: Tracer,
    name: str,
    headers: Mapping[str, Any],
    *,
    attributes: Mapping[str, str | int | float | bool] | None = None,
):
    """Start an outbound client span linked to incoming trace context."""
    parent = parent_context_from_headers(headers)
    span = tracer.start_span(name, context=parent, kind=SpanKind.CLIENT)
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    return span
