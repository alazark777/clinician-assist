"""Environment-backed telemetry settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelemetrySettings:
    """Process-local telemetry configuration."""

    service_name: str
    otlp_endpoint: str | None
    app_env: str
    export_enabled: bool
    max_export_queue_size: int = 256
    export_timeout_seconds: float = 5.0
    log_event_allowlist: frozenset[str] | None = None

    @classmethod
    def from_environ(
        cls,
        *,
        default_service_name: str,
        default_otlp_endpoint: str | None = "http://127.0.0.1:4318",
    ) -> TelemetrySettings:
        """Load settings from standard environment variables."""
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", default_otlp_endpoint)
        disabled = os.environ.get("OTEL_SDK_DISABLED", "").lower() in {"1", "true", "yes"}
        allowlist_raw = os.environ.get("OTEL_LOG_EVENT_ALLOWLIST", "")
        allowlist = (
            frozenset(item.strip() for item in allowlist_raw.split(",") if item.strip())
            if allowlist_raw
            else None
        )
        queue_raw = os.environ.get("OTEL_BSP_MAX_QUEUE_SIZE", "256")
        timeout_raw = os.environ.get("OTEL_EXPORTER_OTLP_TIMEOUT", "5")
        return cls(
            service_name=os.environ.get("OTEL_SERVICE_NAME", default_service_name),
            otlp_endpoint=None if disabled else endpoint,
            app_env=os.environ.get("APP_ENV", "local"),
            export_enabled=not disabled and bool(endpoint),
            max_export_queue_size=int(queue_raw),
            export_timeout_seconds=float(timeout_raw),
            log_event_allowlist=allowlist,
        )
