"""Validated service configuration."""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from clinician_agent.model.backend import ModelBackend


class Settings(BaseModel):
    """Environment-backed settings with safe local defaults."""

    model_config = ConfigDict(frozen=True)

    app_env: str = "local"
    model_backend: str = "stub"
    model_id: str = "offline-stub"
    google_api_key: str | None = Field(default=None, repr=False)
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str | None = None
    model_api_key: str | None = Field(default=None, repr=False)
    model_base_url: str | None = None
    model_call_timeout_seconds: float = Field(default=25.0, gt=0, le=120)
    mcp_registry_path: Path = Path("config/mcp_servers.json")
    mcp_signing_key_path: Path = Path("secrets/mcp-signing-key.pem")
    mcp_token_issuer: str = "clinician-agent-api"
    mcp_request_origin: str = "http://127.0.0.1:8000"
    demo_sessions_path: Path = Path("secrets/demo-sessions.json")
    agent_db_path: Path = Path("var/agent/clinician-agent.sqlite3")
    web_origin: str = "http://127.0.0.1:5173"
    otel_service_name: str = "clinician-agent-api"
    otel_exporter_otlp_endpoint: str | None = "http://127.0.0.1:4318"
    max_active_runs: int = Field(default=4, ge=1, le=32)
    total_deadline_seconds: float = Field(default=60.0, gt=0, le=300)

    @field_validator("model_backend")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        """Allow only explicit model provider backends."""
        allowed = {member.value for member in ModelBackend}
        if value not in allowed:
            raise ValueError(f"MODEL_BACKEND must be one of: {', '.join(sorted(allowed))}")
        return value

    @field_validator("web_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        """Require an exact origin without wildcard or path."""
        if value != "http://127.0.0.1:5173":
            raise ValueError("local API permits only http://127.0.0.1:5173")
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        """Load known settings without accepting arbitrary environment keys."""
        values: dict[str, object] = {}
        for field_name in cls.model_fields:
            env_name = field_name.upper()
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        return cls.model_validate(values)
