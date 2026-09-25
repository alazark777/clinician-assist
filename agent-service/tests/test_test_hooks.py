"""Out-of-band test hook behavior."""

import json
from datetime import date

import pytest

from clinician_agent.coordinator import ProfileCoordinator
from clinician_agent.schemas import ProfileRequest
from clinician_agent.testing.hooks import should_exhaust_model_budget_after_baseline
from clinician_agent.util import canonical_input_hash
from fakes import FakeRecordsGateway, sample_records


def test_should_exhaust_model_budget_from_fault_file(tmp_path, monkeypatch):
    fault_file = tmp_path / "faults.json"
    fault_file.write_text(
        json.dumps(
            {
                "harness_faults": [
                    {"target": "model", "effect": "exhaust_budget_after_baseline"}
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_TEST_FAULT_FILE", str(fault_file))
    assert should_exhaust_model_budget_after_baseline() is True


@pytest.mark.asyncio
async def test_budget_exhaustion_hook_after_baseline(client, tmp_path, monkeypatch):
    fault_file = tmp_path / "faults.json"
    fault_file.write_text(
        json.dumps(
            {
                "harness_faults": [
                    {"target": "model", "effect": "exhaust_budget_after_baseline"}
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_TEST_FAULT_FILE", str(fault_file))
    inventory, records = sample_records()
    gateway = FakeRecordsGateway("P001", inventory, records)
    coordinator: ProfileCoordinator = client.app.state.coordinator  # type: ignore[attr-defined]
    db = client.app.state.db  # type: ignore[attr-defined]
    body = ProfileRequest(
        patient_id="P001",
        visit_context="budget hook",
        as_of=date(2026, 9, 24),
        request_id="budget-hook-1",
    )
    await db.claim_run(
        run_id="run-budget-hook",
        caller_id="caller-a",
        request_id=body.request_id,
        input_hash=canonical_input_hash(body),
        body=body,
        trace_id="trace-budget",
    )
    result = await coordinator.generate(
        run_id="run-budget-hook",
        caller_id="caller-a",
        body=body,
        trace_id="trace-budget",
        gateway=gateway,
    )
    assert result.profile.status == "incomplete"
    assert any(gap.code == "budget_exhausted" for gap in result.profile.gaps)
