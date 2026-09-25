"""Baseline selection unit tests."""

from datetime import date

from clinician_agent.mcp.models import InventoryRecord, RecordType
from clinician_agent.retrieval.baseline import select_baseline_ids


def test_select_latest_lab_key_ties():
    inventory = [
        InventoryRecord(
            record_id="lab-a",
            record_type=RecordType.LAB,
            recorded_at=date(2024, 1, 3),
            event_date=date(2024, 1, 1),
            version=1,
            fact_keys=["HbA1c"],
        ),
        InventoryRecord(
            record_id="lab-b",
            record_type=RecordType.LAB,
            recorded_at=date(2024, 1, 2),
            event_date=date(2024, 1, 1),
            version=1,
            fact_keys=["HbA1c"],
        ),
    ]
    selected = select_baseline_ids(inventory)
    assert "lab-a" in selected
    assert "lab-b" in selected
