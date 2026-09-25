"""Model provider configuration and factory resolution tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from clinician_agent.model.config import (
    GOOGLE_OPENAI_COMPAT_BASE_URL,
    resolve_openai_compatible_client_config,
)
from clinician_agent.model.factory import build_model
from clinician_agent.model.openai_compatible_adapter import OpenAICompatibleModelAdapter
from clinician_agent.model.stub import OfflineStubModel
from clinician_agent.settings import Settings


def test_resolve_google_uses_google_key_and_default_base_url():
    settings = Settings(
        model_backend="google",
        model_id="gemini-2.5-flash-lite",
        google_api_key="gemini-key",
    )
    config = resolve_openai_compatible_client_config(settings)
    assert config.provider == "google"
    assert config.api_key == "gemini-key"
    assert config.base_url == GOOGLE_OPENAI_COMPAT_BASE_URL
    assert config.model_id == "gemini-2.5-flash-lite"


def test_resolve_openai_uses_openai_key_and_optional_base_url():
    settings = Settings(
        model_backend="openai",
        model_id="gpt-4o-mini",
        openai_api_key="sk-openai",
        openai_base_url="https://proxy.example/v1",
    )
    config = resolve_openai_compatible_client_config(settings)
    assert config.provider == "openai"
    assert config.api_key == "sk-openai"
    assert config.base_url == "https://proxy.example/v1"


def test_resolve_openai_native_base_url_when_unset():
    settings = Settings(
        model_backend="openai",
        model_id="gpt-4o-mini",
        openai_api_key="sk-openai",
    )
    config = resolve_openai_compatible_client_config(settings)
    assert config.base_url is None


def test_resolve_custom_requires_api_key_and_base_url():
    settings = Settings(
        model_backend="custom",
        model_id="local-model",
        model_api_key="custom-key",
        model_base_url="https://compat.example/v1",
    )
    config = resolve_openai_compatible_client_config(settings)
    assert config.provider == "custom"
    assert config.api_key == "custom-key"
    assert config.base_url == "https://compat.example/v1"


def test_google_does_not_accept_openai_api_key_only():
    settings = Settings(
        model_backend="google",
        model_id="gemini-2.5-flash-lite",
        openai_api_key="sk-should-not-use",
    )
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        resolve_openai_compatible_client_config(settings)


def test_openai_requires_openai_api_key():
    settings = Settings(
        model_backend="openai",
        model_id="gpt-4o-mini",
        google_api_key="gemini-only",
    )
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        resolve_openai_compatible_client_config(settings)


def test_custom_missing_base_url():
    settings = Settings(
        model_backend="custom",
        model_id="x",
        model_api_key="k",
    )
    with pytest.raises(ValueError, match="MODEL_BASE_URL"):
        resolve_openai_compatible_client_config(settings)


def test_custom_missing_api_key():
    settings = Settings(
        model_backend="custom",
        model_id="x",
        model_base_url="https://example/v1",
    )
    with pytest.raises(ValueError, match="MODEL_API_KEY"):
        resolve_openai_compatible_client_config(settings)


def test_real_backend_requires_model_id():
    settings = Settings(model_backend="openai", model_id="offline-stub", openai_api_key="k")
    with pytest.raises(ValueError, match="MODEL_ID"):
        resolve_openai_compatible_client_config(settings)


def test_build_model_stub():
    model = build_model(Settings(model_backend="stub"))
    assert isinstance(model, OfflineStubModel)


@patch("clinician_agent.model.factory.OpenAICompatibleModelAdapter")
def test_build_model_openai_passes_resolved_client(mock_adapter: MagicMock):
    mock_adapter.return_value = MagicMock()
    settings = Settings(
        model_backend="openai",
        model_id="gpt-4o-mini",
        openai_api_key="sk-test",
    )
    build_model(settings)
    mock_adapter.assert_called_once_with(
        api_key="sk-test",
        model_id="gpt-4o-mini",
        base_url=None,
        call_timeout_seconds=settings.model_call_timeout_seconds,
    )


def test_settings_repr_hides_api_keys():
    settings = Settings(
        model_backend="openai",
        model_id="gpt-4o-mini",
        openai_api_key="super-secret",
    )
    text = repr(settings)
    assert "super-secret" not in text


def test_safe_log_fields_redacts_api_keys():
    from clinician_agent.util import safe_log_fields

    payload = safe_log_fields(openai_api_key="secret-value", patient_id="P001")
    assert payload["openai_api_key"] == "[REDACTED]"
    assert payload["patient_id"] == "P001"
