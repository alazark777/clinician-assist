"""Integration tests using the official MCP client transport."""

from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from httpx2 import AsyncClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from clinician_records.server import create_server
from clinician_records.settings import Settings
from conftest import ORIGIN, mint_token


@asynccontextmanager
async def _with_mcp_session(
    settings: Settings,
    headers: dict[str, str],
):
    """Run a coroutine against a live in-process Streamable HTTP server."""
    server = create_server(settings)
    app = server.streamable_http_app(
        streamable_http_path=settings.streamable_http_path,
        transport_security=settings.transport_security(),
        host=settings.host,
        stateless_http=True,
    )
    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((settings.host, 0))
        port = sock.getsockname()[1]
    config = uvicorn.Config(app, host=settings.host, port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)
    serve_task = asyncio.create_task(uvicorn_server.serve())
    try:
        while not uvicorn_server.started:
            await asyncio.sleep(0.05)
        url = f"http://{settings.host}:{port}{settings.streamable_http_path}"
        async with AsyncClient(
            base_url=f"http://{settings.host}:{port}",
            headers=headers,
        ) as http_client:
            async with streamable_http_client(url, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
    finally:
        uvicorn_server.should_exit = True
        await serve_task


async def _discover_and_list(settings: Settings, headers: dict[str, str]) -> None:
    async with _with_mcp_session(settings, headers) as session:
        tools = await session.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {"list_records", "read_records", "get_record_counts"}
        result = await session.call_tool("list_records", {})
        assert not result.is_error
        payload = result.structured_content
        assert payload is not None
        assert payload["status"] in {"ok", "empty"}
        assert payload["patient_id"] == "P001"


def test_discover_and_list_records(settings: Settings, auth_headers: dict[str, str]) -> None:
    """The SDK discovers tools and returns a successful inventory envelope."""
    asyncio.run(_discover_and_list(settings, auth_headers))


async def _read_round_trip(settings: Settings, headers: dict[str, str]) -> None:
    async with _with_mcp_session(settings, headers) as session:
        listed = await session.call_tool("list_records", {})
        record_id = listed.structured_content["data"]["records"][0]["record_id"]
        read = await session.call_tool("read_records", {"record_ids": [record_id]})
        assert not read.is_error
        payload = read.structured_content
        assert payload["status"] == "ok"
        assert payload["data"]["records"][0]["record_id"] == record_id


def test_read_records_round_trip(settings: Settings, auth_headers: dict[str, str]) -> None:
    """Reads return exact records for discovered IDs."""
    asyncio.run(_read_round_trip(settings, auth_headers))


async def _invalid_token(settings: Settings, private_pem: str) -> None:
    token = mint_token(private_pem, patient_id="P001", audience="wrong-audience")
    headers = {"Authorization": f"Bearer {token}", "Origin": ORIGIN}
    server = create_server(settings)
    app = server.streamable_http_app(
        streamable_http_path=settings.streamable_http_path,
        transport_security=settings.transport_security(),
        host=settings.host,
        stateless_http=True,
    )
    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((settings.host, 0))
        port = sock.getsockname()[1]
    config = uvicorn.Config(app, host=settings.host, port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)
    serve_task = asyncio.create_task(uvicorn_server.serve())
    try:
        while not uvicorn_server.started:
            await asyncio.sleep(0.05)
        url = f"http://{settings.host}:{port}{settings.streamable_http_path}"
        async with AsyncClient(base_url=f"http://{settings.host}:{port}", headers=headers) as client:
            response = await client.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
            assert response.status_code in {401, 403}
    finally:
        uvicorn_server.should_exit = True
        await serve_task


def test_invalid_token_rejected(settings: Settings, rsa_keypair: tuple[str, str]) -> None:
    """Wrong-audience tokens fail before tool execution."""
    private_pem, _ = rsa_keypair
    asyncio.run(_invalid_token(settings, private_pem))


async def _interleaved(settings: Settings, private_pem: str) -> None:
    async def patient_call(patient_id: str) -> str:
        token = mint_token(private_pem, patient_id=patient_id)
        headers = {"Authorization": f"Bearer {token}", "Origin": ORIGIN}
        async with _with_mcp_session(settings, headers) as session:
            result = await session.call_tool("list_records", {})
            assert result.structured_content is not None
            return result.structured_content["patient_id"]

    p001, p002 = await asyncio.gather(patient_call("P001"), patient_call("P002"))
    assert {p001, p002} == {"P001", "P002"}


def test_interleaved_patients(settings: Settings, rsa_keypair: tuple[str, str]) -> None:
    """Concurrent requests preserve per-token patient scope."""
    private_pem, _ = rsa_keypair
    asyncio.run(_interleaved(settings, private_pem))


async def _invalid_args(settings: Settings, headers: dict[str, str]) -> None:
    async with _with_mcp_session(settings, headers) as session:
        result = await session.call_tool("list_records", {"record_types": ["lab", "lab"]})
        assert result.is_error


def test_invalid_tool_arguments_rejected(settings: Settings, auth_headers: dict[str, str]) -> None:
    """Invalid list arguments fail validation."""
    asyncio.run(_invalid_args(settings, auth_headers))
