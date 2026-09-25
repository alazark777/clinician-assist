"""OpenTelemetry bootstrap with bounded export and safe degradation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from clinician_observability.config import TelemetrySettings
from clinician_observability.constants import DEFAULT_LOG_EVENT_ALLOWLIST
from clinician_observability.logging import configure_logging
from clinician_observability.metrics import OperationalMetrics

_LOGGER = logging.getLogger(__name__)
_RUNTIME: TelemetryRuntime | None = None


@dataclass(slots=True)
class TelemetryRuntime:
    """Handles configured providers and metric helpers."""

    settings: TelemetrySettings
    tracer_provider: TracerProvider | None
    meter_provider: MeterProvider | None
    metrics: OperationalMetrics | None

    @property
    def export_degraded(self) -> bool:
        """True when export was requested but providers were not fully configured."""
        return self.settings.export_enabled and self.tracer_provider is None


def configure_telemetry(
    *,
    default_service_name: str = "clinician-agent-api",
    default_otlp_endpoint: str | None = "http://127.0.0.1:4318",
) -> TelemetryRuntime:
    """Initialize logging and OpenTelemetry once at process startup."""
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME

    settings = TelemetrySettings.from_environ(
        default_service_name=default_service_name,
        default_otlp_endpoint=default_otlp_endpoint,
    )
    allowlist = settings.log_event_allowlist or DEFAULT_LOG_EVENT_ALLOWLIST
    configure_logging(
        service_name=settings.service_name,
        app_env=settings.app_env,
        event_allowlist=allowlist,
    )

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "deployment.environment": settings.app_env,
        }
    )

    tracer_provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None
    operational: OperationalMetrics | None = None

    if settings.export_enabled and settings.otlp_endpoint:
        try:
            span_exporter = OTLPSpanExporter(
                endpoint=f"{settings.otlp_endpoint.rstrip('/')}/v1/traces",
                timeout=int(settings.export_timeout_seconds),
            )
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    span_exporter,
                    max_queue_size=settings.max_export_queue_size,
                    export_timeout_millis=int(settings.export_timeout_seconds * 1000),
                )
            )
            trace.set_tracer_provider(tracer_provider)

            metric_exporter = OTLPMetricExporter(
                endpoint=f"{settings.otlp_endpoint.rstrip('/')}/v1/metrics",
                timeout=int(settings.export_timeout_seconds),
            )
            reader = PeriodicExportingMetricReader(
                metric_exporter,
                export_interval_millis=15000,
            )
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
            operational = OperationalMetrics.from_meter_provider()
            _LOGGER.info(
                "telemetry.startup",
                extra={
                    "event": "telemetry.startup",
                    "structured": {"export": "enabled"},
                },
            )
        except Exception as exc:  # noqa: BLE001 - degrade safely
            _LOGGER.warning(
                "Telemetry export disabled after setup failure",
                extra={
                    "event": "exporter.degraded",
                    "structured": {"error_type": type(exc).__name__},
                },
            )
            tracer_provider = None
            meter_provider = None
    else:
        _LOGGER.info(
            "telemetry.startup",
            extra={
                "event": "telemetry.startup",
                "structured": {"export": "disabled"},
            },
        )

    _RUNTIME = TelemetryRuntime(
        settings=settings,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        metrics=operational,
    )
    return _RUNTIME


def get_runtime() -> TelemetryRuntime | None:
    """Return the configured runtime, if startup completed."""
    return _RUNTIME


def shutdown_telemetry() -> None:
    """Flush providers during process shutdown."""
    global _RUNTIME
    if _RUNTIME is None:
        return
    if _RUNTIME.tracer_provider is not None:
        _RUNTIME.tracer_provider.shutdown()
    if _RUNTIME.meter_provider is not None:
        _RUNTIME.meter_provider.shutdown()
    _LOGGER.info("telemetry.shutdown", extra={"event": "telemetry.shutdown"})
    _RUNTIME = None
