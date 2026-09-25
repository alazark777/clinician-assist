"""Unit tests for repository list/read semantics."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from clinician_records.models import ListRecordsInput, ReadRecordsInput, RecordType
from clinician_records.repository import RecordRepository


def test_list_returns_fact_keys(patient_data_dir: Path) -> None:
    """Inventory entries expose sorted unique fact keys."""
    repo = RecordRepository(patient_data_dir)
    envelope = repo.list_records("P001", ListRecordsInput())
    assert envelope.status == "ok"
    assert envelope.data is not None
    assert envelope.data.records
    assert envelope.data.records[0].fact_keys


def test_list_empty_patient(tmp_path: Path) -> None:
    """Confirmed empty inventories use the empty status."""
    payload = {
        "schema_version": "1.0",
        "dataset_version": "test-v1",
        "patient_id": "PTEST",
        "records": [],
    }
    (tmp_path / "PTEST.json").write_text(json.dumps(payload), encoding="utf-8")
    repo = RecordRepository(tmp_path)
    envelope = repo.list_records("PTEST", ListRecordsInput())
    assert envelope.status == "empty"
    assert envelope.data is not None
    assert envelope.data.records == []
    assert envelope.data.inventory_complete is True


def test_read_denies_unknown_id(patient_data_dir: Path) -> None:
    """Missing opaque IDs fail the whole batch as denied."""
    repo = RecordRepository(patient_data_dir)
    envelope = repo.read_records("P001", ReadRecordsInput(record_ids=["missing-id"]))
    assert envelope.status == "denied"
    assert envelope.error is not None
    assert envelope.error.code == "record_not_accessible"
    assert envelope.data is None


def test_read_exact_set(patient_data_dir: Path) -> None:
    """Successful reads return exactly the requested ID set."""
    repo = RecordRepository(patient_data_dir)
    inventory = repo.list_records("P001", ListRecordsInput())
    assert inventory.data is not None
    first_id = inventory.data.records[0].record_id
    envelope = repo.read_records("P001", ReadRecordsInput(record_ids=[first_id]))
    assert envelope.status == "ok"
    assert envelope.data is not None
    assert [record.record_id for record in envelope.data.records] == [first_id]


def test_list_before_filter(patient_data_dir: Path) -> None:
    """The before filter uses event_date with recorded_at fallback."""
    repo = RecordRepository(patient_data_dir)
    envelope = repo.list_records("P001", ListRecordsInput(before=date(2020, 1, 1)))
    assert envelope.status == "empty"


def test_inventory_limit_marks_incomplete(tmp_path: Path) -> None:
    """More than 100 inventory rows mark inventory_complete false."""
    records = []
    for index in range(101):
        records.append(
            {
                "record_id": f"PTEST-R{index}",
                "record_type": "vital",
                "recorded_at": "2026-01-01",
                "event_date": "2026-01-01",
                "version": 1,
                "content": {
                    "facts": [
                        {
                            "section": "vital",
                            "key": "weight",
                            "value": "70 kg",
                            "date": "2026-01-01",
                            "qualifier": "documented",
                        }
                    ],
                    "text": f"Synthetic vital {index}",
                },
            }
        )
    payload = {
        "schema_version": "1.0",
        "dataset_version": "test-v1",
        "patient_id": "PTEST",
        "records": records,
    }
    (tmp_path / "PTEST.json").write_text(json.dumps(payload), encoding="utf-8")
    repo = RecordRepository(tmp_path)
    envelope = repo.list_records("PTEST", ListRecordsInput(record_types=[RecordType.VITAL]))
    assert envelope.status == "ok"
    assert envelope.data is not None
    assert len(envelope.data.records) == 100
    assert envelope.data.inventory_complete is False


def test_read_unavailable_fault(patient_data_dir: Path) -> None:
    """Injected record faults surface as retryable unavailable."""
    repo = RecordRepository(patient_data_dir)
    inventory = repo.list_records("P001", ListRecordsInput())
    assert inventory.data is not None
    record_id = inventory.data.records[0].record_id
    repo.mark_record_unavailable(record_id)
    envelope = repo.read_records("P001", ReadRecordsInput(record_ids=[record_id]))
    assert envelope.status == "unavailable"
    assert envelope.error is not None
    assert envelope.error.code == "record_unavailable"
    assert envelope.error.retryable is True
