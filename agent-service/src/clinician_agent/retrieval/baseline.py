"""Deterministic baseline record selection."""

from __future__ import annotations

from datetime import date

from clinician_agent.mcp.models import InventoryRecord, RecordType

LAB_KEYS = ("HbA1c", "glucose")
BASELINE_TYPES = {
    RecordType.CONDITION,
    RecordType.MEDICATION,
    RecordType.ALLERGY,
    RecordType.VISIT_NOTE,
}


def selection_date(record: InventoryRecord) -> date:
    """Return the effective selection date for a record."""
    return record.event_date or record.recorded_at


def select_baseline_ids(inventory: list[InventoryRecord]) -> list[str]:
    """Select mandatory baseline record IDs in stable order."""
    by_type: dict[RecordType, list[InventoryRecord]] = {}
    for item in inventory:
        by_type.setdefault(item.record_type, []).append(item)

    selected: list[str] = []

    for record_type in (
        RecordType.CONDITION,
        RecordType.MEDICATION,
        RecordType.ALLERGY,
    ):
        selected.extend(record.record_id for record in sorted(by_type.get(record_type, []), key=_sort_key))

    visit_notes = by_type.get(RecordType.VISIT_NOTE, [])
    if visit_notes:
        latest = _select_latest_group(visit_notes)
        selected.extend(record.record_id for record in latest)

    lab_records = by_type.get(RecordType.LAB, [])
    for key in LAB_KEYS:
        candidates = [record for record in lab_records if key in record.fact_keys]
        if candidates:
            latest = _select_latest_group(candidates)
            selected.extend(record.record_id for record in latest)

    vital_records = by_type.get(RecordType.VITAL, [])
    vital_keys = sorted({key for record in vital_records for key in record.fact_keys})
    for key in vital_keys:
        candidates = [record for record in vital_records if key in record.fact_keys]
        latest = _select_latest_group(candidates)
        selected.extend(record.record_id for record in latest)

    deduped: list[str] = []
    seen: set[str] = set()
    for record_id in selected:
        if record_id not in seen:
            deduped.append(record_id)
            seen.add(record_id)
    return deduped


def chunk_ids(record_ids: list[str], size: int = 20) -> list[list[str]]:
    """Batch IDs for MCP reads."""
    return [record_ids[index : index + size] for index in range(0, len(record_ids), size)]


def _sort_key(record: InventoryRecord) -> tuple[date, date, str]:
    """Stable ordering for exhaustive category reads."""
    return (selection_date(record), record.recorded_at, record.record_id)


def _select_latest_group(records: list[InventoryRecord]) -> list[InventoryRecord]:
    """Select all records tied on the latest selection date."""
    if not records:
        return []
    dated = [(selection_date(record), record) for record in records]
    max_date = max(item[0] for item in dated)
    tied = [record for effective, record in dated if effective == max_date]
    return sorted(tied, key=_sort_key)
