"""Low-cardinality operational metrics."""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, Meter

from clinician_observability.constants import (
    METRIC_BUDGET_EXHAUSTED,
    METRIC_MODEL_TOKENS,
    METRIC_REQUEST_DURATION,
    METRIC_TOOL_ATTEMPTS,
    METRIC_TOOL_TIMEOUTS,
)


class OperationalMetrics:
    """Aggregate counters and histograms without patient or run labels."""

    def __init__(self, meter: Meter) -> None:
        self.request_duration: Histogram = meter.create_histogram(
            METRIC_REQUEST_DURATION,
            unit="ms",
            description="End-to-end handler duration",
        )
        self.tool_attempts: Counter = meter.create_counter(
            METRIC_TOOL_ATTEMPTS,
            description="MCP tool invocation attempts",
        )
        self.tool_timeouts: Counter = meter.create_counter(
            METRIC_TOOL_TIMEOUTS,
            description="MCP tool timeouts",
        )
        self.model_tokens: Counter = meter.create_counter(
            METRIC_MODEL_TOKENS,
            description="Model token usage when reported by provider",
        )
        self.budget_exhausted: Counter = meter.create_counter(
            METRIC_BUDGET_EXHAUSTED,
            description="Profile generation stopped by budget limits",
        )

    @classmethod
    def from_meter_provider(cls) -> OperationalMetrics:
        """Build metrics using the global meter provider."""
        meter = metrics.get_meter("clinician.observability")
        return cls(meter)
