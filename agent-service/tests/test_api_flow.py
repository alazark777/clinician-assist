"""HTTP flow tests with fake MCP gateway."""

import pytest


@pytest.mark.asyncio
async def test_demo_login_and_patients(authed_client):
    response = await authed_client.get("/v1/patients")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["patient_id"] == "P001"


@pytest.mark.asyncio
async def test_profile_generation_stub(authed_client):
    response = await authed_client.post(
        "/v1/profiles",
        json={
            "patient_id": "P001",
            "visit_context": "Diabetes follow-up",
            "as_of": "2024-06-01",
            "request_id": "req-1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["patient_id"] == "P001"
    assert body["profile"]["status"] in {"complete", "incomplete"}
    assert body["review_status"] == "draft"
    assert body["usage"]["model_calls"] >= 1


@pytest.mark.asyncio
async def test_idempotent_replay_completed(authed_client):
    payload = {
        "patient_id": "P001",
        "visit_context": "Diabetes follow-up",
        "as_of": "2024-06-01",
        "request_id": "req-replay",
    }
    first = await authed_client.post("/v1/profiles", json=payload)
    second = await authed_client.post("/v1/profiles", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["profile_id"] == second.json()["profile_id"]


@pytest.mark.asyncio
async def test_request_id_input_conflict(authed_client):
    base = {
        "patient_id": "P001",
        "visit_context": "Diabetes follow-up",
        "as_of": "2024-06-01",
        "request_id": "req-conflict",
    }
    await authed_client.post("/v1/profiles", json=base)
    changed = {**base, "visit_context": "Changed context"}
    response = await authed_client.post("/v1/profiles", json=changed)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_forbidden_patient(authed_client):
    response = await authed_client.post(
        "/v1/profiles",
        json={
            "patient_id": "P999",
            "visit_context": "x",
            "as_of": "2024-06-01",
            "request_id": "req-forbidden",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_feedback_version_binding(authed_client):
    created = await authed_client.post(
        "/v1/profiles",
        json={
            "patient_id": "P001",
            "visit_context": "Diabetes follow-up",
            "as_of": "2024-06-01",
            "request_id": "req-feedback",
        },
    )
    profile = created.json()
    ok = await authed_client.post(
        f"/v1/profiles/{profile['profile_id']}/feedback",
        json={
            "profile_version": profile["profile_version"],
            "review_revision": profile["review_revision"],
            "decision": "accept",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["review_status"] == "accepted"
    stale = await authed_client.post(
        f"/v1/profiles/{profile['profile_id']}/feedback",
        json={
            "profile_version": profile["profile_version"],
            "review_revision": profile["review_revision"],
            "decision": "accept",
        },
    )
    assert stale.status_code == 409
