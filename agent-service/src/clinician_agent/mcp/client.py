"""Registry-driven MCP client with allowlist enforcement."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from clinician_agent.errors import AppError
from clinician_agent.mcp.models import (
    InventoryData,
    ListRecordsArgs,
    ReadData,
    ReadRecordsArgs,
    ToolEnvelope,
)
from clinician_agent.mcp.registry import McpServerConfig, McpRegistry
from clinician_agent.telemetry import log_event, span

logger = logging.getLogger(__name__)

QUALIFIED_PREFIX = "records__"


class RecordsGateway(Protocol):
    """Test seam for MCP record access."""

    async def list_records(
        self, *, before: date, record_types: list[str] | None = None
    ) -> ToolEnvelope:
        """Inventory scoped records."""

    async def list_with_retry(
        self, *, before: date, record_types: list[str] | None = None
    ) -> ToolEnvelope:
        """Inventory with one transient retry."""

    async def read_records(self, *, record_ids: list[str]) -> ToolEnvelope:
        """Read exact record IDs."""

    async def read_with_retry(self, *, record_ids: list[str]) -> ToolEnvelope:
        """Read with one transient retry."""


@dataclass
class McpCallContext:
    """Request-scoped MCP credentials."""

    patient_id: str
    bearer_token: str
    expected_patient_id: str
    request_origin: str = "http://127.0.0.1:8000"


@dataclass
class RecordsMcpClient(RecordsGateway):
    """Official SDK client bound to one registry server."""

    server: McpServerConfig
    context: McpCallContext
    tool_attempts: int = field(default=0, init=False)

    async def list_records(
        self, *, before: date, record_types: list[str] | None = None
    ) -> ToolEnvelope:
        """Call list_records through the allowlisted MCP server."""
        args = ListRecordsArgs(before=before, record_types=record_types)  # type: ignore[arg-type]
        payload = args.model_dump(mode="json", exclude_none=True)
        return await self._call_tool("list_records", payload, span_name="records.list")

    async def list_with_retry(
        self, *, before: date, record_types: list[str] | None = None
    ) -> ToolEnvelope:
        """Retry one transient unavailable inventory call."""
        envelope = await self.list_records(before=before, record_types=record_types)
        if (
            envelope.status == "unavailable"
            and envelope.error is not None
            and envelope.error.retryable
            and self.server.max_transient_read_retries > 0
        ):
            log_event("mcp.list.retry", retry_count=1, tool="list_records")
            return await self.list_records(before=before, record_types=record_types)
        return envelope

    async def read_records(self, *, record_ids: list[str]) -> ToolEnvelope:
        """Call read_records with exact-set validation."""
        args = ReadRecordsArgs(record_ids=record_ids)
        payload = args.model_dump(mode="json")
        envelope = await self._call_tool("read_records", payload, span_name="records.read")
        if envelope.status == "ok" and isinstance(envelope.data, ReadData):
            returned = {record.record_id for record in envelope.data.records}
            if returned != set(record_ids):
                raise AppError(
                    "mcp_read_set_mismatch",
                    "read_records returned unexpected ID set",
                    502,
                )
        return envelope

    async def read_with_retry(self, *, record_ids: list[str]) -> ToolEnvelope:
        """Retry one transient unavailable batch."""
        envelope = await self.read_records(record_ids=record_ids)
        if (
            envelope.status == "unavailable"
            and envelope.error is not None
            and envelope.error.retryable
            and self.server.max_transient_read_retries > 0
        ):
            log_event("mcp.read.retry", retry_count=1, tool="read_records")
            return await self.read_records(record_ids=record_ids)
        return envelope

    async def _call_tool(
        self, tool_name: str, arguments: dict[str, Any], *, span_name: str
    ) -> ToolEnvelope:
        """Execute one allowlisted tool."""
        if tool_name not in self.server.allowed_tools:
            raise AppError("tool_not_allowed", f"Tool {tool_name} is not allowlisted", 502)
        self.tool_attempts += 1
        headers = {
            "Authorization": f"Bearer {self.context.bearer_token}",
            "Origin": self.context.request_origin,
        }
        with span("mcp.call", tool=tool_name, server=self.server.id):
            with span(span_name, tool=tool_name, server=self.server.id):
                async with httpx2.AsyncClient(headers=headers) as http_client:
                    async with streamable_http_client(
                        str(self.server.url),
                        http_client=http_client,
                    ) as (read_stream, write_stream):
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()
                            discovered = await session.list_tools()
                            discovered_names = {tool.name for tool in discovered.tools}
                            if tool_name not in discovered_names:
                                raise AppError(
                                    "tool_missing",
                                    f"Discovered MCP server lacks {tool_name}",
                                    502,
                                )
                            result = await session.call_tool(
                                tool_name,
                                arguments,
                                read_timeout_seconds=self.server.timeout_seconds,
                            )
        if result.is_error:
            raise AppError("mcp_tool_error", "MCP tool returned is_error", 502)
        structured = _extract_structured(result.structured_content, result.content)
        try:
            envelope = ToolEnvelope.model_validate(structured)
        except Exception as exc:  # noqa: BLE001
            raise AppError("mcp_schema_invalid", "MCP tool envelope invalid", 502) from exc
        if envelope.patient_id != self.context.expected_patient_id:
            raise AppError("mcp_patient_mismatch", "MCP patient scope mismatch", 502)
        return envelope


def build_records_client(
    registry: McpRegistry, *, context: McpCallContext
) -> RecordsMcpClient:
    """Construct the primary records MCP client."""
    enabled = [server for server in registry.servers if server.enabled and server.id == "records"]
    if not enabled:
        raise AppError("records_server_missing", "Records MCP server not configured", 503)
    return RecordsMcpClient(server=enabled[0], context=context)


def _extract_structured(structured: Any, content: Any) -> dict[str, Any]:
    """Normalize SDK tool results to a dict envelope."""
    if isinstance(structured, dict):
        return structured
    if content:
        for block in content:
            text = getattr(block, "text", None)
            if text:
                return json.loads(text)
    raise ValueError("tool result missing structured content")
