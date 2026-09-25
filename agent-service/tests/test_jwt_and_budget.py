"""JWT issuance and budget unit checks."""

from datetime import date

import jwt
import pytest

from clinician_agent.auth.jwt_tokens import JWT_ALGORITHM, McpTokenIssuer
from clinician_agent.retrieval.budget import RunBudget
from fakes import write_signing_key


def test_mcp_token_audience_and_patient(tmp_path):
    key_path = tmp_path / "key.pem"
    public_key = write_signing_key(key_path)
    issuer = McpTokenIssuer(key_path=key_path, issuer="clinician-agent-api")
    token = issuer.issue(patient_id="P001", audience="clinician-records-mcp")
    payload = jwt.decode(
        token,
        public_key,
        algorithms=[JWT_ALGORITHM],
        audience="clinician-records-mcp",
        issuer="clinician-agent-api",
    )
    assert payload["patient_id"] == "P001"


def test_run_budget_caps():
    budget = RunBudget(deadline_seconds=60.0, max_model_calls=6, max_additional_record_ids=10)
    budget.baseline_ids = {"base-1"}
    assert budget.can_model_call()
    for _ in range(6):
        budget.record_model_call()
    assert not budget.can_model_call()
    assert budget.can_read_additional(["extra-1", "extra-2"])
    budget.record_additional_reads(["extra-1", "extra-2"])
    assert not budget.can_read_additional([f"extra-{index}" for index in range(9)])


@pytest.mark.asyncio
async def test_active_run_limit_returns_429(authed_client, client):
    db = client.app.state.db  # type: ignore[attr-defined]
    for index in range(4):
        await db.claim_run(
            run_id=f"run-{index}",
            caller_id="caller-a",
            request_id=f"req-active-{index}",
            input_hash=f"hash-{index}",
            body=__import__("clinician_agent.schemas", fromlist=["ProfileRequest"]).ProfileRequest(
                patient_id="P001",
                visit_context="x",
                as_of=date(2024, 6, 1),
                request_id=f"req-active-{index}",
            ),
            trace_id=f"trace-{index}",
        )
    response = await authed_client.post(
        "/v1/profiles",
        json={
            "patient_id": "P001",
            "visit_context": "blocked",
            "as_of": "2024-06-01",
            "request_id": "req-blocked",
        },
    )
    assert response.status_code == 429
