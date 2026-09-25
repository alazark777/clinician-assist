"""Interleaved two-patient isolation."""

import pytest

from fakes import FakeRecordsGateway, sample_records


@pytest.mark.asyncio
async def test_interleaved_patient_gateways(client, authed_client):
    inventory_a, records_a = sample_records()
    inventory_b, records_b = sample_records()
    for record in records_b.values():
        record.model_copy(update={"record_id": record.record_id + "-b"})  # noqa: B007
    records_b = {
        "cond-1-b": records_a["cond-1"].model_copy(update={"record_id": "cond-1-b"}),
        "med-1-b": records_a["med-1"].model_copy(update={"record_id": "med-1-b"}),
        "lab-1-b": records_a["lab-1"].model_copy(update={"record_id": "lab-1-b"}),
    }
    inventory_b = [
        item.model_copy(update={"record_id": item.record_id + "-b"}) for item in inventory_a
    ]
    gateway_a = FakeRecordsGateway("P001", inventory_a, records_a)
    gateway_b = FakeRecordsGateway("P002", inventory_b, records_b)

    client.app.state.test_gateway = gateway_a  # type: ignore[attr-defined]
    first = await authed_client.post(
        "/v1/profiles",
        json={
            "patient_id": "P001",
            "visit_context": "A",
            "as_of": "2024-06-01",
            "request_id": "req-a",
        },
    )
    client.app.state.test_gateway = gateway_b  # type: ignore[attr-defined]
    second = await authed_client.post(
        "/v1/profiles",
        json={
            "patient_id": "P002",
            "visit_context": "B",
            "as_of": "2024-06-01",
            "request_id": "req-b",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["profile"]["patient_id"] == "P001"
    assert second.json()["profile"]["patient_id"] == "P002"
