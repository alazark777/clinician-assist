"""Extension proofs: get_record_counts and second-server ping discovery."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_SRC = REPO_ROOT / "agent-service" / "src"
RECORDS_SRC = REPO_ROOT / "records-mcp" / "src"
HARNESS_DIR = Path(__file__).resolve().parent

for path in (AGENT_SRC, RECORDS_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


async def prove_get_record_counts(*, mcp_url: str, signing_key: Path) -> dict[str, Any]:
    """Call optional get_record_counts; must not be on clinical allowlist."""
    from clinician_agent.auth.jwt_tokens import McpTokenIssuer
    from clinician_agent.mcp.client import McpCallContext, build_records_client
    from clinician_agent.mcp.registry import load_registry

    registry_path = HARNESS_DIR / "config" / "mcp_servers_eval.json"
    registry = load_registry(registry_path)
    clinical_tools = registry.servers[0].allowed_tools
    issuer = McpTokenIssuer(key_path=signing_key, issuer="clinician-agent-api")
    token = issuer.issue(patient_id="P001", audience="clinician-records-mcp")
    client = build_records_client(
        registry,
        context=McpCallContext(
            patient_id="P001",
            bearer_token=token,
            expected_patient_id="P001",
        ),
    )
    import httpx2
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {token}", "Origin": "http://127.0.0.1:8000"}
    discovered: set[str] = set()
    counts_payload: dict[str, Any] | None = None
    error: str | None = None
    async with httpx2.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                discovered = {tool.name for tool in tools.tools}
                if "get_record_counts" not in discovered:
                    error = "get_record_counts not discovered on instrumented MCP"
                elif "get_record_counts" in clinical_tools:
                    error = "get_record_counts incorrectly on clinical allowlist"
                else:
                    result = await session.call_tool("get_record_counts", {})
                    structured = result.structured_content
                    if isinstance(structured, dict):
                        counts_payload = structured
                    elif result.content:
                        counts_payload = json.loads(result.content[0].text)  # type: ignore[index]
    return {
        "proof": "get_record_counts",
        "pass": error is None and counts_payload is not None,
        "clinical_allowlist": clinical_tools,
        "discovered_tools": sorted(discovered),
        "counts": counts_payload,
        "error": error,
    }


async def prove_ping_server(*, ping_url: str, signing_key: Path) -> dict[str, Any]:
    """Discover and call ping on the test-only second MCP server."""
    from clinician_agent.auth.jwt_tokens import McpTokenIssuer
    from clinician_agent.mcp.registry import load_registry

    registry = load_registry(HARNESS_DIR / "config" / "mcp_servers_extensions.json")
    ping_server = next(item for item in registry.servers if item.id == "eval_ping")
    issuer = McpTokenIssuer(key_path=signing_key, issuer="clinician-agent-api")
    token = issuer.issue(patient_id="P001", audience=ping_server.token_audience)

    import httpx2
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {token}", "Origin": "http://127.0.0.1:8000"}
    discovered: set[str] = set()
    pong: dict[str, Any] | None = None
    error: str | None = None
    async with httpx2.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(ping_url, http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                discovered = {tool.name for tool in tools.tools}
                if "ping" not in discovered:
                    error = "ping tool not discovered"
                elif "ping" not in ping_server.allowed_tools:
                    error = "ping missing from registry allowlist entry"
                else:
                    result = await session.call_tool("ping", {})
                    structured = result.structured_content
                    if isinstance(structured, dict):
                        pong = structured
    records_allowlist = next(item for item in registry.servers if item.id == "records").allowed_tools
    return {
        "proof": "ping_server",
        "pass": error is None and pong is not None and "ping" not in records_allowlist,
        "records_clinical_allowlist": records_allowlist,
        "ping_allowlist": ping_server.allowed_tools,
        "discovered_tools": sorted(discovered),
        "pong": pong,
        "error": error,
    }


def prove_registry_load_without_coordinator_change() -> dict[str, Any]:
    """Ensure extended registry validates without touching coordinator/UI code."""
    from clinician_agent.mcp.registry import load_registry

    path = HARNESS_DIR / "config" / "mcp_servers_extensions.json"
    registry = load_registry(path)
    ids = [server.id for server in registry.servers]
    return {
        "proof": "registry_adapter",
        "pass": ids == ["records", "eval_ping"],
        "server_ids": ids,
    }
