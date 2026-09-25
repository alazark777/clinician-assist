"""Environment-backed configuration for the records MCP server."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp.server.transport_security import TransportSecuritySettings


class Settings(BaseModel):
    """Validated settings loaded from known environment variables."""

    model_config = ConfigDict(frozen=True)

    patient_data_dir: Path = Path("data/patients")
    mcp_verification_key_path: Path = Path("secrets/mcp-verification-key.pem")
    mcp_token_issuer: str = "clinician-agent-api"
    mcp_token_audience: str = "clinician-records-mcp"
    mcp_allowed_origins: tuple[str, ...] = ("http://127.0.0.1:8000",)
    mcp_resource_server_url: str = "http://127.0.0.1:8001/mcp"
    mcp_auth_issuer_url: str = "http://127.0.0.1:8000"
    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=1, le=65535)
    streamable_http_path: str = "/mcp"
    app_env: str = "local"
    otel_service_name: str = "clinician-records-mcp"
    otel_exporter_otlp_endpoint: str | None = "http://127.0.0.1:4318"
    enable_extension_tools: bool = False
    mcp_request_state_key: str | None = None
    log_level: str = "INFO"

    @field_validator("mcp_allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> tuple[str, ...]:
        """Parse a comma-separated origin list."""
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            if not parts:
                raise ValueError("MCP_ALLOWED_ORIGINS must include at least one origin")
            return tuple(parts)
        if isinstance(value, (list, tuple)):
            return tuple(str(item) for item in value)
        return value  # type: ignore[return-value]

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings from whitelisted environment variables."""
        mapping = {
            "patient_data_dir": "PATIENT_DATA_DIR",
            "mcp_verification_key_path": "MCP_VERIFICATION_KEY",
            "mcp_token_issuer": "MCP_TOKEN_ISSUER",
            "mcp_token_audience": "MCP_TOKEN_AUDIENCE",
            "mcp_allowed_origins": "MCP_ALLOWED_ORIGINS",
            "mcp_resource_server_url": "MCP_RESOURCE_SERVER_URL",
            "mcp_auth_issuer_url": "MCP_AUTH_ISSUER_URL",
            "host": "MCP_HOST",
            "port": "MCP_PORT",
            "app_env": "APP_ENV",
            "otel_service_name": "OTEL_SERVICE_NAME",
            "otel_exporter_otlp_endpoint": "OTEL_EXPORTER_OTLP_ENDPOINT",
            "log_level": "LOG_LEVEL",
            "mcp_request_state_key": "MCP_REQUEST_STATE_KEY",
        }
        values: dict[str, object] = {}
        for field_name, env_name in mapping.items():
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        if os.environ.get("ENABLE_EXTENSION_TOOLS", "").lower() in {"1", "true", "yes"}:
            values["enable_extension_tools"] = True
        return cls.model_validate(values)

    def transport_security(self) -> TransportSecuritySettings:
        """Build DNS rebinding protection settings for Streamable HTTP."""
        allowed_hosts = [
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
        ]
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            allowed_hosts.append(f"{self.host}:*")
        origin_patterns = list(self.mcp_allowed_origins)
        for origin in self.mcp_allowed_origins:
            if origin.endswith(":8000"):
                origin_patterns.append(origin.replace(":8000", ":*"))
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=sorted(set(origin_patterns)),
        )
