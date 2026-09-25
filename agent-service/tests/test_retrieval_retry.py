"""Retrieval retry and supplemental read behavior."""

from datetime import date

import pytest

from clinician_agent.errors import AppError
from clinician_agent.coordinator import ProfileCoordinator
from clinician_agent.model.port import ModelResult, ModelUsage
from clinician_agent.mcp.models import (
    ClinicalRecord,
    FactRecord,
    InventoryRecord,
    RecordContent,
    RecordType,
)
from clinician_agent.schemas import ProfileRequest
from clinician_agent.util import canonical_input_hash
from fakes import FakeRecordsGateway, sample_records


async def _run_with_gateway(client, gateway, *, request_id: str, run_id: str):
    coordinator: ProfileCoordinator = client.app.state.coordinator  # type: ignore[attr-defined]
    db = client.app.state.db  # type: ignore[attr-defined]
    body = ProfileRequest(
        patient_id="P001",
        visit_context="coordinator test",
        as_of=date(2026, 9, 24),
        request_id=request_id,
    )
    await db.claim_run(
        run_id=run_id,
        caller_id="caller-a",
        request_id=body.request_id,
        input_hash=canonical_input_hash(body),
        body=body,
        trace_id=f"trace-{run_id}",
    )
    return await coordinator.generate(
        run_id=run_id,
        caller_id="caller-a",
        body=body,
        trace_id=f"trace-{run_id}",
        gateway=gateway,
    )


@pytest.mark.asyncio
async def test_baseline_read_retries_transient_unavailability(client):
    inventory, records = sample_records()
    gateway = FakeRecordsGateway("P001", inventory, records)
    gateway.fail_next_read = True
    result = await _run_with_gateway(
        client, gateway, request_id="retry-read-1", run_id="run-retry"
    )
    assert result.profile.facts
    assert gateway.read_calls >= 2


@pytest.mark.asyncio
async def test_inventory_list_retries_once(client):
    inventory, records = sample_records()
    gateway = FakeRecordsGateway("P001", inventory, records)
    gateway.fail_next_list = True
    result = await _run_with_gateway(
        client, gateway, request_id="retry-list-1", run_id="run-list-retry"
    )
    assert gateway.tool_attempts >= 2
    assert result.profile.facts


@pytest.mark.asyncio
async def test_supplemental_prior_hba1c_read(client):
    inventory = [
        InventoryRecord(
            record_id="lab-old",
            record_type=RecordType.LAB,
            recorded_at=date(2026, 1, 15),
            event_date=date(2026, 1, 15),
            version=1,
            fact_keys=["HbA1c"],
        ),
        InventoryRecord(
            record_id="lab-new",
            record_type=RecordType.LAB,
            recorded_at=date(2026, 9, 15),
            event_date=date(2026, 9, 15),
            version=1,
            fact_keys=["HbA1c"],
        ),
    ]
    records = {
        "lab-old": ClinicalRecord(
            record_id="lab-old",
            record_type=RecordType.LAB,
            recorded_at=date(2026, 1, 15),
            event_date=date(2026, 1, 15),
            version=1,
            content=RecordContent(
                facts=[
                    FactRecord(
                        section="lab",
                        key="HbA1c",
                        value="8.1%",
                        date=date(2026, 1, 15),
                        qualifier="documented",
                    )
                ],
                text="Synthetic record: HbA1c: 8.1%. Status: documented.",
            ),
        ),
        "lab-new": ClinicalRecord(
            record_id="lab-new",
            record_type=RecordType.LAB,
            recorded_at=date(2026, 9, 15),
            event_date=date(2026, 9, 15),
            version=1,
            content=RecordContent(
                facts=[
                    FactRecord(
                        section="lab",
                        key="HbA1c",
                        value="7.8%",
                        date=date(2026, 9, 15),
                        qualifier="documented",
                    )
                ],
                text="Synthetic record: HbA1c: 7.8%. Status: documented.",
            ),
        ),
    }
    gateway = FakeRecordsGateway("P001", inventory, records)
    result = await _run_with_gateway(
        client, gateway, request_id="supplemental-lab-1", run_id="run-supplemental"
    )
    hba_values = {fact.value for fact in result.profile.facts if fact.key == "HbA1c"}
    assert hba_values == {"8.1%", "7.8%"}
    assert "no_prior_hba1c" not in {gap.code for gap in result.profile.gaps}


@pytest.mark.asyncio
async def test_supplemental_read_outage_keeps_baseline_evidence(client):
    inventory, baseline_records = sample_records()
    inventory = [item for item in inventory if item.record_id != "lab-1"]
    baseline_records.pop("lab-1", None)
    inventory.extend(
        [
            InventoryRecord(
                record_id="lab-old",
                record_type=RecordType.LAB,
                recorded_at=date(2026, 1, 15),
                event_date=date(2026, 1, 15),
                version=1,
                fact_keys=["HbA1c"],
            ),
            InventoryRecord(
                record_id="lab-new",
                record_type=RecordType.LAB,
                recorded_at=date(2026, 9, 15),
                event_date=date(2026, 9, 15),
                version=1,
                fact_keys=["HbA1c"],
            ),
        ]
    )
    baseline_records["lab-new"] = ClinicalRecord(
        record_id="lab-new",
        record_type=RecordType.LAB,
        recorded_at=date(2026, 9, 15),
        event_date=date(2026, 9, 15),
        version=1,
        content=RecordContent(
            facts=[
                FactRecord(
                    section="lab",
                    key="HbA1c",
                    value="7.8%",
                    date=date(2026, 9, 15),
                    qualifier="documented",
                )
            ],
            text="Synthetic record: HbA1c: 7.8%. Status: documented.",
        ),
    )
    gateway = FakeRecordsGateway("P001", inventory, baseline_records)
    gateway.permanently_unavailable_record_ids.add("lab-old")
    result = await _run_with_gateway(
        client,
        gateway,
        request_id="supplemental-outage-1",
        run_id="run-supplemental-outage",
    )
    gap_codes = {gap.code for gap in result.profile.gaps}
    hba_values = {fact.value for fact in result.profile.facts if fact.key == "HbA1c"}
    condition_facts = [fact for fact in result.profile.facts if fact.section == "condition"]
    assert condition_facts
    assert hba_values == {"7.8%"}
    assert result.profile.status == "incomplete"
    assert "prior_result_unavailable" in gap_codes
    assert "retrieval_limited" not in gap_codes
    assert gateway.read_calls >= 3


class _AdaptiveReadRequestModel:
    """Requests one adaptive supplemental read before delegating to the stub."""

    def __init__(self, inner):
        self._inner = inner
        self._issued_request = False

    async def generate_profile(self, **kwargs):
        if not self._issued_request:
            self._issued_request = True
            return ModelResult(
                profile=None,
                requested_record_ids=["note-old"],
                complete=False,
                usage=ModelUsage(input_tokens=0, output_tokens=0),
            )
        return await self._inner.generate_profile(**kwargs)


@pytest.mark.asyncio
async def test_adaptive_supplemental_outage_emits_retrieval_limited(client):
    inventory, baseline_records = sample_records()
    inventory.extend(
        [
            InventoryRecord(
                record_id="note-old",
                record_type=RecordType.VISIT_NOTE,
                recorded_at=date(2026, 3, 1),
                event_date=date(2026, 3, 1),
                version=1,
                fact_keys=["visit_summary"],
            ),
            InventoryRecord(
                record_id="note-new",
                record_type=RecordType.VISIT_NOTE,
                recorded_at=date(2026, 9, 1),
                event_date=date(2026, 9, 1),
                version=1,
                fact_keys=["visit_summary"],
            ),
        ]
    )
    baseline_records["note-new"] = ClinicalRecord(
        record_id="note-new",
        record_type=RecordType.VISIT_NOTE,
        recorded_at=date(2026, 9, 1),
        event_date=date(2026, 9, 1),
        version=1,
        content=RecordContent(
            facts=[
                FactRecord(
                    section="condition",
                    key="Type 2 diabetes",
                    value="Latest visit note.",
                    date=date(2026, 9, 1),
                    qualifier="documented",
                )
            ],
            text="Latest visit note.",
        ),
    )
    baseline_records["note-old"] = ClinicalRecord(
        record_id="note-old",
        record_type=RecordType.VISIT_NOTE,
        recorded_at=date(2026, 3, 1),
        event_date=date(2026, 3, 1),
        version=1,
        content=RecordContent(
            facts=[
                FactRecord(
                    section="condition",
                    key="Type 2 diabetes",
                    value="Earlier note mentions stable control.",
                    date=date(2026, 3, 1),
                    qualifier="documented",
                )
            ],
            text="Earlier visit note.",
        ),
    )
    gateway = FakeRecordsGateway("P001", inventory, baseline_records)
    gateway.permanently_unavailable_record_ids.add("note-old")
    coordinator: ProfileCoordinator = client.app.state.coordinator  # type: ignore[attr-defined]
    coordinator._model = _AdaptiveReadRequestModel(coordinator._model)  # type: ignore[attr-defined]
    result = await _run_with_gateway(
        client,
        gateway,
        request_id="adaptive-outage-1",
        run_id="run-adaptive-outage",
    )
    gap_codes = {gap.code for gap in result.profile.gaps}
    assert result.profile.status == "incomplete"
    assert "retrieval_limited" in gap_codes
    assert "prior_result_unavailable" not in gap_codes
    assert result.profile.facts


@pytest.mark.asyncio
async def test_baseline_read_outage_still_returns_503(client):
    inventory, records = sample_records()
    gateway = FakeRecordsGateway("P001", inventory, records)
    gateway.permanently_unavailable_record_ids.update(records.keys())
    with pytest.raises(AppError) as exc_info:
        await _run_with_gateway(
            client,
            gateway,
            request_id="baseline-outage-1",
            run_id="run-baseline-outage",
        )
    assert exc_info.value.status_code == 503
