"""Model adapter factory."""

from clinician_agent.model.backend import ModelBackend
from clinician_agent.model.config import resolve_openai_compatible_client_config
from clinician_agent.model.openai_compatible_adapter import OpenAICompatibleModelAdapter
from clinician_agent.model.port import ModelPort
from clinician_agent.model.stub import OfflineStubModel
from clinician_agent.settings import Settings


def build_model(settings: Settings) -> ModelPort:
    """Select the configured model adapter."""
    backend = ModelBackend(settings.model_backend)
    if backend is ModelBackend.STUB:
        return OfflineStubModel()

    client_config = resolve_openai_compatible_client_config(settings)
    return OpenAICompatibleModelAdapter(
        api_key=client_config.api_key,
        model_id=client_config.model_id,
        base_url=client_config.base_url,
        call_timeout_seconds=client_config.call_timeout_seconds,
    )
