"""MCP envelope validation."""

import pytest
from pydantic import ValidationError

from clinician_agent.mcp.models import InventoryData, ToolEnvelope, ToolError


def test_read_denied_requires_null_data():
    envelope = ToolEnvelope(
        schema_version="1.0",
        status="denied",
        patient_id="P001",
        dataset_version="v1",
        data=None,
        error=ToolError(code="record_not_accessible", retryable=False),
    )
    assert envelope.error is not None


def test_empty_inventory_invariants():
    ToolEnvelope(
        schema_version="1.0",
        status="empty",
        patient_id="P001",
        dataset_version="v1",
        data=InventoryData(records=[], inventory_complete=True),
        error=None,
    )


def test_ok_requires_records():
    with pytest.raises(ValidationError):
        ToolEnvelope(
            schema_version="1.0",
            status="ok",
            patient_id="P001",
            dataset_version="v1",
            data=InventoryData(records=[], inventory_complete=True),
            error=None,
        )
