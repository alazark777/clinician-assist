"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from clinician_agent.main import create_app
from clinician_agent.settings import Settings
from clinician_agent.telemetry import configure_telemetry
from fakes import FakeRecordsGateway, sample_records, write_demo_sessions, write_signing_key


@pytest.fixture
def tmp_paths(tmp_path: Path) -> dict[str, Path]:
    """Create temp config paths."""
    demo = tmp_path / "secrets" / "demo-sessions.json"
    key = tmp_path / "secrets" / "mcp-signing-key.pem"
    db = tmp_path / "var" / "agent" / "test.sqlite3"
    write_demo_sessions(demo)
    write_signing_key(key)
    return {"demo": demo, "key": key, "db": db}


@pytest_asyncio.fixture
async def client(tmp_paths: dict[str, Path]):
    """Async HTTP client with fake MCP gateway."""
    settings = Settings.from_env().model_copy(
        update={
            "demo_sessions_path": tmp_paths["demo"],
            "mcp_signing_key_path": tmp_paths["key"],
            "agent_db_path": tmp_paths["db"],
            "model_backend": "stub",
            "otel_exporter_otlp_endpoint": None,
        }
    )
    app = create_app(settings)
    inventory, records = sample_records()
    app.state.test_gateway = FakeRecordsGateway("P001", inventory, records)
    configure_telemetry(settings)
    await app.state.db.connect()
    await app.state.db.mark_interrupted_runs()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        http_client.app = app  # type: ignore[attr-defined]
        yield http_client
    await app.state.db.close()


@pytest_asyncio.fixture
async def authed_client(client: AsyncClient) -> AsyncClient:
    """Client with demo session cookie."""
    response = await client.post(
        "/v1/demo/session",
        json={"username": "reviewer", "passphrase": "local-demo"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert response.status_code == 204
    return client
