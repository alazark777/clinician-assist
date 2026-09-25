"""Restart marks interrupted runs."""

from datetime import date

import httpx
import pytest

from clinician_agent.main import create_app
from clinician_agent.schemas import ProfileRequest
from clinician_agent.settings import Settings
from fakes import write_demo_sessions, write_signing_key


@pytest.mark.asyncio
async def test_restart_marks_interrupted(tmp_path):
    demo = tmp_path / "secrets" / "demo-sessions.json"
    key = tmp_path / "secrets" / "key.pem"
    db_path = tmp_path / "agent.sqlite3"
    write_demo_sessions(demo)
    write_signing_key(key)
    settings = Settings.from_env().model_copy(
        update={
            "demo_sessions_path": demo,
            "mcp_signing_key_path": key,
            "agent_db_path": db_path,
            "otel_exporter_otlp_endpoint": None,
        }
    )
    app = create_app(settings)
    await app.state.db.connect()
    await app.state.db.claim_run(
        run_id="run-stale",
        caller_id="caller-a",
        request_id="req-stale",
        input_hash="hash",
        body=ProfileRequest(
            patient_id="P001",
            visit_context="x",
            as_of=date(2024, 6, 1),
            request_id="req-stale",
        ),
        trace_id="trace",
    )
    await app.state.db.close()
    app2 = create_app(settings)
    await app2.state.db.connect()
    count = await app2.state.db.mark_interrupted_runs()
    row = await app2.state.db.get_run("run-stale")
    await app2.state.db.close()
    assert count == 1
    assert row is not None
    assert row.run_status.value == "interrupted"
