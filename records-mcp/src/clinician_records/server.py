"""MCPServer wiring for Streamable HTTP transport."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.request_state import RequestStateSecurity

from contextlib import asynccontextmanager

from clinician_records.auth import JwtTokenVerifier
from clinician_records.models import ListRecordsInput, ReadRecordsInput, RecordType, ToolEnvelope
from clinician_records.repository import RecordRepository
from clinician_records.settings import Settings
from clinician_records.tools import READ_ONLY_ANNOTATIONS, RecordsToolService

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "record_tools.json"


def _load_tool_schemas() -> dict[str, dict[str, object]]:
    """Load published tool schemas for registration metadata."""
    payload = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return {tool["name"]: tool for tool in payload["tools"]}


def create_server(settings: Settings) -> MCPServer[RecordRepository]:
    """Construct the MCP server with auth, tools, and repository lifespan."""
    repository = RecordRepository(settings.patient_data_dir)
    tool_service = RecordsToolService(repository)
    schemas = _load_tool_schemas()
    token_verifier = JwtTokenVerifier(settings)

    @asynccontextmanager
    async def lifespan(server: MCPServer[RecordRepository]):
        """Expose the repository through MCP lifespan context."""
        yield repository

    if settings.mcp_request_state_key:
        request_state_security = RequestStateSecurity(
            keys=[settings.mcp_request_state_key],
            audience=settings.mcp_token_audience,
        )
    else:
        request_state_security = RequestStateSecurity.ephemeral()

    server = MCPServer[RecordRepository](
        name=settings.mcp_token_audience,
        version="0.1.0",
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=settings.mcp_auth_issuer_url,
            resource_server_url=settings.mcp_resource_server_url,
            validate_token_resource=False,
        ),
        request_state_security=request_state_security,
        lifespan=lifespan,
    )

    list_schema = schemas["list_records"]
    read_schema = schemas["read_records"]

    @server.tool(
        name="list_records",
        description=str(list_schema["description"]),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def list_records(
        record_types: list[RecordType] | None = None,
        before: date | None = None,
    ) -> ToolEnvelope:
        """List scoped inventory metadata."""
        parsed = ListRecordsInput(record_types=record_types, before=before)
        return await tool_service.list_records(parsed)

    @server.tool(
        name="read_records",
        description=str(read_schema["description"]),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def read_records(record_ids: list[str]) -> ToolEnvelope:
        """Read exact scoped records."""
        parsed = ReadRecordsInput(record_ids=record_ids)
        return await tool_service.read_records(parsed)

    if settings.enable_extension_tools:

        @server.tool(
            name="get_record_counts",
            description="Test-only extension: return per-type record counts for the scoped patient.",
            annotations=READ_ONLY_ANNOTATIONS,
            structured_output=True,
        )
        async def get_record_counts() -> dict[str, Any]:
            """Return record counts for extension proofs."""
            return await tool_service.get_record_counts()

    logger.info("Records MCP server initialized")
    return server
