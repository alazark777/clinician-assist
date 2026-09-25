"""Mocked OpenAI-compatible model adapter tests."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import AuthenticationError, RateLimitError

from clinician_agent.errors import AppError
from clinician_agent.model.factory import build_model
from clinician_agent.model.openai_compatible_adapter import OpenAICompatibleModelAdapter
from clinician_agent.model.provider_errors import normalize_model_provider_error
from clinician_agent.schemas import Profile
from clinician_agent.settings import Settings
from fakes import sample_records


def _minimal_step_json(*, complete: bool = True) -> str:
    profile = {
        "patient_id": "P001",
        "status": "complete",
        "facts": [
            {
                "section": "condition",
                "key": "Type 2 diabetes",
                "value": "documented",
                "date": "2026-09-01",
                "qualifier": "from record",
                "source_ids": ["cond-1"],
            }
        ],
        "gaps": [],
        "conflicts": [],
        "sources": [
            {
                "record_id": "cond-1",
                "version": 1,
                "excerpt": "Type 2 diabetes documented.",
            }
        ],
    }
    payload = {
        "profile": profile if complete else None,
        "requested_record_ids": [] if complete else ["note-old"],
        "complete": complete,
    }
    return json.dumps(payload)


def _chat_response(content: str, *, prompt_tokens: int = 11, completion_tokens: int = 22) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


@pytest.mark.asyncio
async def test_openai_adapter_parses_structured_step():
    inventory, records = sample_records()
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_chat_response(_minimal_step_json()))
    adapter = OpenAICompatibleModelAdapter(api_key="test-key", model_id="gpt-test", client=client)

    result = await adapter.generate_profile(
        patient_id="P001",
        visit_context="Annual visit",
        as_of="2026-09-15",
        records=records,
        inventory=inventory,
        inventory_complete=True,
        inventory_empty=False,
        call_index=0,
    )

    assert result.complete is True
    assert isinstance(result.profile, Profile)
    assert result.profile.patient_id == "P001"
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 22
    client.chat.completions.create.assert_awaited_once()
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "gpt-test"
    assert kwargs["response_format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_openai_adapter_adaptive_step_requests_records():
    inventory, records = sample_records()
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            _chat_response(_minimal_step_json(complete=False)),
            _chat_response(_minimal_step_json(complete=True)),
        ]
    )
    adapter = OpenAICompatibleModelAdapter(api_key="test-key", model_id="gpt-test", client=client)

    first = await adapter.generate_profile(
        patient_id="P001",
        visit_context="Annual visit",
        as_of="2026-09-15",
        records=records,
        inventory=inventory,
        inventory_complete=True,
        inventory_empty=False,
        call_index=0,
    )
    second = await adapter.generate_profile(
        patient_id="P001",
        visit_context="Annual visit",
        as_of="2026-09-15",
        records=records,
        inventory=inventory,
        inventory_complete=True,
        inventory_empty=False,
        call_index=1,
    )

    assert first.complete is False
    assert first.requested_record_ids == ["note-old"]
    assert first.profile is None
    assert second.complete is True
    assert second.profile is not None


@pytest.mark.asyncio
async def test_openai_adapter_maps_auth_error():
    response = MagicMock(status_code=401)
    exc = AuthenticationError("invalid key", response=response, body=None)
    mapped = normalize_model_provider_error(exc)
    assert isinstance(mapped, AppError)
    assert mapped.code == "model_auth_failed"
    assert mapped.status_code == 503


@pytest.mark.asyncio
async def test_openai_adapter_maps_rate_limit():
    response = MagicMock(status_code=429)
    exc = RateLimitError("slow down", response=response, body=None)
    mapped = normalize_model_provider_error(exc)
    assert mapped.code == "model_rate_limited"
    assert mapped.status_code == 503


@pytest.mark.asyncio
async def test_openai_adapter_invalid_json_raises():
    inventory, records = sample_records()
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_chat_response("not-json"))
    adapter = OpenAICompatibleModelAdapter(api_key="test-key", model_id="gpt-test", client=client)

    with pytest.raises(AppError) as raised:
        await adapter.generate_profile(
            patient_id="P001",
            visit_context="Annual visit",
            as_of="2026-09-15",
            records=records,
            inventory=inventory,
            inventory_complete=True,
            inventory_empty=False,
            call_index=0,
        )
    assert raised.value.code == "model_output_invalid"
    assert raised.value.status_code == 502


def test_build_model_openai_requires_credentials():
    settings = Settings(
        model_backend="openai",
        model_id="gpt-4o-mini",
        openai_api_key=None,
    )
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_model(settings)


def test_build_model_google_requires_google_credentials():
    settings = Settings(
        model_backend="google",
        model_id="gemini-2.5-flash-lite",
        google_api_key=None,
    )
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        build_model(settings)


def test_build_model_openai_requires_model_id():
    settings = Settings(
        model_backend="openai",
        model_id="offline-stub",
        openai_api_key="test-key",
    )
    with pytest.raises(ValueError, match="MODEL_ID"):
        build_model(settings)
