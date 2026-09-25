"""Telemetry bootstrap and degradation tests."""

import os

import pytest

from clinician_observability.setup import configure_telemetry, shutdown_telemetry


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    import clinician_observability.setup as setup_module

    monkeypatch.setattr(setup_module, "_RUNTIME", None)
    yield
    shutdown_telemetry()
    monkeypatch.setattr(setup_module, "_RUNTIME", None)


def test_configure_telemetry_disabled_without_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    runtime = configure_telemetry()
    assert runtime.settings.export_enabled is False
    assert runtime.tracer_provider is None


def test_configure_telemetry_survives_unreachable_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    runtime = configure_telemetry()
    assert runtime.settings.export_enabled is True
    # Exporter setup should succeed; export failures must not raise at startup.
    assert runtime.tracer_provider is not None or runtime.export_degraded
