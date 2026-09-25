"""Model provider identity values."""

from enum import StrEnum


class ModelBackend(StrEnum):
    """Provider identity for chat completion routing."""

    STUB = "stub"
    GOOGLE = "google"
    OPENAI = "openai"
    CUSTOM = "custom"
