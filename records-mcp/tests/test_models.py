"""Validation tests for strict tool models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from clinician_records.models import ListRecordsInput, ReadRecordsInput, ToolEnvelope


def test_list_rejects_unknown_fields() -> None:
    """Unknown inventory fields fail closed."""
    with pytest.raises(ValidationError):
        ListRecordsInput.model_validate({"record_types": ["lab"], "unexpected": True})


def test_read_rejects_duplicate_ids() -> None:
    """Duplicate read IDs are rejected."""
    with pytest.raises(ValidationError):
        ReadRecordsInput.model_validate({"record_ids": ["a", "a"]})


def test_envelope_empty_invariants() -> None:
    """Empty inventory envelopes require complete empty data."""
    envelope = ToolEnvelope.model_validate(
        {
            "status": "empty",
            "patient_id": "P001",
            "dataset_version": "synthetic-v1",
            "data": {"records": [], "inventory_complete": True},
            "error": None,
        }
    )
    assert envelope.status == "empty"
