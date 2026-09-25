"""Structured model step envelope (provider-only, not persisted)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from clinician_agent.schemas import Identifier, Profile, StrictModel


class ModelStepResponse(StrictModel):
    """One coordinator model step from the provider."""

    profile: Profile | None = None
    requested_record_ids: list[Identifier] = Field(default_factory=list, max_length=10)
    complete: bool = False


def model_step_json_schema() -> dict[str, Any]:
    """JSON Schema for OpenAI-compatible structured output."""
    return ModelStepResponse.model_json_schema(mode="validation")
