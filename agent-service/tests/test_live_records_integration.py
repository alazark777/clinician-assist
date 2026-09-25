"""Live records MCP integration (no FakeRecordsGateway)."""

from __future__ import annotations

from datetime import date

import pytest

from clinician_agent.auth.jwt_tokens import McpTokenIssuer
from clinician_agent.coordinator import ProfileCoordinator
from clinician_agent.db import Database
from clinician_agent.mcp.client import McpCallContext, build_records_client
from clinician_agent.mcp.registry import load_registry
from clinician_agent.model.factory import build_model
from clinician_agent.schemas import ProfileRequest
from clinician_agent.settings import Settings
from clinician_agent.util import canonical_input_hash
from live_records_fixtures import live_records_mcp


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_live_mcp_discovery_list_and_read(live_records_mcp: dict[str, object]) -> None:
    """Agent MCP client discovers tools and reads bundled patient records."""
    registry = load_registry(live_records_mcp["registry_path"])  # type: ignore[arg-type]
    issuer = McpTokenIssuer(
        key_path=live_records_mcp["signing_key_path"],  # type: ignore[arg-type]
        issuer="clinician-agent-api",
    )
    token = issuer.issue(patient_id="P001", audience="clinician-records-mcp")
    client = build_records_client(
        registry,
        context=McpCallContext(
            patient_id="P001",
            bearer_token=token,
            expected_patient_id="P001",
            request_origin="http://127.0.0.1:8000",
        ),
    )
    inventory = await client.list_records(before=date(2027, 1, 1))
    assert inventory.status in {"ok", "empty"}
    assert inventory.patient_id == "P001"
    if inventory.status != "ok" or inventory.data is None:
        pytest.skip("P001 inventory empty in bundled fixtures")
    record_id = inventory.data.records[0].record_id
    read = await client.read_records(record_ids=[record_id])
    assert read.status == "ok"
    assert read.data is not None
    assert read.data.records[0].record_id == record_id


@pytest.mark.asyncio
async def test_live_mcp_profile_generation(live_records_mcp: dict[str, object], tmp_path) -> None:
    """Coordinator generates a profile using the real records MCP gateway."""
    settings = Settings.from_env().model_copy(
        update={
            "mcp_registry_path": live_records_mcp["registry_path"],  # type: ignore[arg-type]
            "mcp_signing_key_path": live_records_mcp["signing_key_path"],  # type: ignore[arg-type]
            "agent_db_path": tmp_path / "live.sqlite3",
            "model_backend": "stub",
            "otel_exporter_otlp_endpoint": None,
        }
    )
    registry = load_registry(settings.mcp_registry_path)
    db = Database(settings.agent_db_path)
    await db.connect()
    coordinator = ProfileCoordinator(
        settings=settings,
        db=db,
        registry=registry,
        token_issuer=McpTokenIssuer(
            key_path=settings.mcp_signing_key_path,
            issuer=settings.mcp_token_issuer,
        ),
        model=build_model(settings),
    )
    body = ProfileRequest(
        patient_id="P001",
        visit_context="Live MCP integration",
        as_of=date(2027, 1, 1),
        request_id="req-live-1",
    )
    await db.claim_run(
        run_id="run-live-1",
        caller_id="integration",
        request_id=body.request_id,
        input_hash=canonical_input_hash(body),
        body=body,
        trace_id="trace-live-1",
    )
    try:
        result = await coordinator.generate(
            run_id="run-live-1",
            caller_id="integration",
            body=body,
            trace_id="trace-live-1",
            gateway=None,
        )
    finally:
        await db.close()

    assert result.profile.patient_id == "P001"
    assert result.profile.status in {"complete", "incomplete"}
    assert result.usage.tool_attempts >= 1
