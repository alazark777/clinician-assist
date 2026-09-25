"""W3C trace propagation tests."""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from clinician_observability.propagation import inject_trace_headers, parent_context_from_headers


def test_inject_and_extract_traceparent() -> None:
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("test")
    headers: dict[str, str] = {}
    with tracer.start_as_current_span("profile.generate") as parent:
        inject_trace_headers(headers)
        expected_trace = format(parent.get_span_context().trace_id, "032x")
    assert "traceparent" in headers
    ctx = parent_context_from_headers(headers)
    child = tracer.start_span("mcp.call", context=ctx)
    assert format(child.get_span_context().trace_id, "032x") == expected_trace
    child.end()
