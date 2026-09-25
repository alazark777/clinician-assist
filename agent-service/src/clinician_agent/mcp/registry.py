"""MCP server registry loading and validation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

logger = logging.getLogger(__name__)


class McpServerConfig(BaseModel):
    """One allowlisted MCP server."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    enabled: bool
    url: HttpUrl
    transport: str
    protocol_version: str
    token_audience: str
    allowed_tools: list[str] = Field(min_length=1)
    approved_schema_file: str
    timeout_seconds: float = Field(gt=0, le=30)
    max_transient_read_retries: int = Field(ge=0, le=3)
    max_result_bytes: int = Field(gt=0)


class McpRegistry(BaseModel):
    """Registry document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    servers: list[McpServerConfig]


def load_registry(path: Path) -> McpRegistry:
    """Load and validate the MCP registry."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return McpRegistry.model_validate(payload)


def load_approved_tool_schemas(config_dir: Path, filename: str) -> dict[str, Any]:
    """Load approved tool schema baseline."""
    return json.loads((config_dir / filename).read_text(encoding="utf-8"))
