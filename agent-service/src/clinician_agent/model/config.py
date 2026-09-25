"""Strongly typed model provider resolution for the factory."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from clinician_agent.model.backend import ModelBackend
from clinician_agent.settings import Settings

GOOGLE_OPENAI_COMPAT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class OpenAICompatibleClientConfig(BaseModel):
    """Resolved credentials and endpoint for AsyncOpenAI-compatible APIs."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["google", "openai", "custom"]
    model_id: str
    api_key: str = Field(repr=False)
    base_url: str | None
    call_timeout_seconds: float


def resolve_openai_compatible_client_config(settings: Settings) -> OpenAICompatibleClientConfig:
    """Map settings to a single OpenAI-compatible client configuration."""
    backend = ModelBackend(settings.model_backend)
    _require_real_model_id(settings.model_id, backend=backend)

    if backend is ModelBackend.GOOGLE:
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required for google backend")
        return OpenAICompatibleClientConfig(
            provider="google",
            model_id=settings.model_id,
            api_key=settings.google_api_key,
            base_url=GOOGLE_OPENAI_COMPAT_BASE_URL,
            call_timeout_seconds=settings.model_call_timeout_seconds,
        )

    if backend is ModelBackend.OPENAI:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for openai backend")
        return OpenAICompatibleClientConfig(
            provider="openai",
            model_id=settings.model_id,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            call_timeout_seconds=settings.model_call_timeout_seconds,
        )

    if backend is ModelBackend.CUSTOM:
        if not settings.model_api_key:
            raise ValueError("MODEL_API_KEY is required for custom backend")
        if not settings.model_base_url:
            raise ValueError("MODEL_BASE_URL is required for custom backend")
        return OpenAICompatibleClientConfig(
            provider="custom",
            model_id=settings.model_id,
            api_key=settings.model_api_key,
            base_url=settings.model_base_url,
            call_timeout_seconds=settings.model_call_timeout_seconds,
        )

    raise ValueError(f"Unsupported model backend for OpenAI-compatible client: {backend}")


def _require_real_model_id(model_id: str, *, backend: ModelBackend) -> None:
    """Ensure non-stub backends use an explicit model identifier."""
    if backend is ModelBackend.STUB:
        return
    if not model_id or model_id == "offline-stub":
        raise ValueError(f"MODEL_ID is required for {backend.value} backend")
