"""Read-only patient record repository with scoped opaque ID resolution."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from clinician_records.models import (
    MAX_INVENTORY_RECORDS,
    MAX_RESULT_BYTES,
    InventoryData,
    InventoryRecord,
    ListRecordsInput,
    ReadData,
    ReadRecordsInput,
    Record,
    RecordType,
    ToolEnvelope,
    ToolError,
    PatientFile,
)

logger = logging.getLogger(__name__)

_PATIENT_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,31}$")


class PatientDataError(Exception):
    """Base error for patient fixture access."""


class PatientUnavailable(PatientDataError):
    """Patient fixture could not be loaded temporarily."""


class RecordRepository:
    """Loads synthetic patient fixtures and serves scoped list/read operations."""

    def __init__(self, patient_data_dir: Path) -> None:
        """Bind the repository to a patient data directory."""
        self._patient_data_dir = patient_data_dir
        self._cache: dict[str, PatientFile] = {}
        self._unavailable_record_ids: set[str] = set()

    def mark_record_unavailable(self, record_id: str) -> None:
        """Test hook to simulate transient record read failures."""
        self._unavailable_record_ids.add(record_id)

    def clear_faults(self) -> None:
        """Clear injected read faults."""
        self._unavailable_record_ids.clear()

    def _patient_path(self, patient_id: str) -> Path:
        """Resolve the authorized patient fixture path without using record IDs."""
        if not _PATIENT_ID_PATTERN.fullmatch(patient_id):
            raise PatientUnavailable("invalid patient identifier")
        candidate = self._patient_data_dir / f"{patient_id}.json"
        resolved = candidate.resolve()
        root = self._patient_data_dir.resolve()
        if not str(resolved).startswith(str(root)):
            raise PatientUnavailable("patient path escape blocked")
        return candidate

    def _load_patient(self, patient_id: str) -> PatientFile:
        """Load and validate a patient fixture."""
        if patient_id in self._cache:
            return self._cache[patient_id]
        path = self._patient_path(patient_id)
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            patient = PatientFile.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Patient fixture unavailable for authorized scope")
            raise PatientUnavailable("patient fixture unavailable") from exc
        if patient.patient_id != patient_id:
            raise PatientUnavailable("patient identifier mismatch")
        self._cache[patient_id] = patient
        return patient

    @staticmethod
    def _effective_date(record: Record) -> date:
        """Return the selection date for inventory filtering."""
        return record.event_date or record.recorded_at

    @staticmethod
    def _fact_keys(record: Record) -> list[str]:
        """Return sorted unique fact keys for inventory metadata."""
        keys = {fact.key for fact in record.content.facts}
        return sorted(keys)

    @staticmethod
    def _envelope_bytes(envelope: ToolEnvelope) -> int:
        """Measure serialized envelope size."""
        return len(envelope.model_dump_json().encode("utf-8"))

    def _base_envelope(
        self,
        *,
        patient_id: str,
        dataset_version: str,
        status: str,
        data: InventoryData | ReadData | None,
        error: ToolError | None,
    ) -> ToolEnvelope:
        """Construct a validated tool envelope."""
        return ToolEnvelope.model_validate(
            {
                "status": status,
                "patient_id": patient_id,
                "dataset_version": dataset_version,
                "data": data,
                "error": error,
            }
        )

    def list_records(self, patient_id: str, args: ListRecordsInput) -> ToolEnvelope:
        """Return scoped inventory metadata for an authorized patient."""
        try:
            patient = self._load_patient(patient_id)
        except PatientUnavailable:
            return self._base_envelope(
                patient_id=patient_id,
                dataset_version="unknown",
                status="unavailable",
                data=None,
                error=ToolError(code="record_unavailable", retryable=True),
            )

        filtered: list[Record] = []
        type_filter = set(args.record_types) if args.record_types else None
        for record in patient.records:
            if type_filter is not None and record.record_type not in type_filter:
                continue
            if args.before is not None and self._effective_date(record) > args.before:
                continue
            filtered.append(record)

        filtered.sort(key=lambda item: (item.recorded_at, item.record_id))

        if not filtered:
            return self._base_envelope(
                patient_id=patient.patient_id,
                dataset_version=patient.dataset_version,
                status="empty",
                data=InventoryData(records=[], inventory_complete=True),
                error=None,
            )

        inventory: list[InventoryRecord] = []
        inventory_complete = len(filtered) <= MAX_INVENTORY_RECORDS
        candidates = filtered if inventory_complete else filtered[:MAX_INVENTORY_RECORDS]

        for record in candidates:
            inventory.append(
                InventoryRecord(
                    record_id=record.record_id,
                    record_type=record.record_type,
                    recorded_at=record.recorded_at,
                    event_date=record.event_date,
                    version=record.version,
                    fact_keys=self._fact_keys(record),
                )
            )

        envelope = self._base_envelope(
            patient_id=patient.patient_id,
            dataset_version=patient.dataset_version,
            status="ok",
            data=InventoryData(records=inventory, inventory_complete=inventory_complete),
            error=None,
        )
        if self._envelope_bytes(envelope) > MAX_RESULT_BYTES:
            trimmed: list[InventoryRecord] = []
            for item in inventory:
                trial = InventoryData(records=trimmed + [item], inventory_complete=False)
                trial_envelope = self._base_envelope(
                    patient_id=patient.patient_id,
                    dataset_version=patient.dataset_version,
                    status="ok",
                    data=trial,
                    error=None,
                )
                if self._envelope_bytes(trial_envelope) > MAX_RESULT_BYTES:
                    break
                trimmed.append(item)
            if not trimmed:
                return self._base_envelope(
                    patient_id=patient.patient_id,
                    dataset_version=patient.dataset_version,
                    status="unavailable",
                    data=None,
                    error=ToolError(code="result_too_large", retryable=False),
                )
            return self._base_envelope(
                patient_id=patient.patient_id,
                dataset_version=patient.dataset_version,
                status="ok",
                data=InventoryData(records=trimmed, inventory_complete=False),
                error=None,
            )
        return envelope

    def read_records(self, patient_id: str, args: ReadRecordsInput) -> ToolEnvelope:
        """Return exact records for the authorized opaque ID set."""
        try:
            patient = self._load_patient(patient_id)
        except PatientUnavailable:
            return self._base_envelope(
                patient_id=patient_id,
                dataset_version="unknown",
                status="unavailable",
                data=None,
                error=ToolError(code="record_unavailable", retryable=True),
            )

        index = {record.record_id: record for record in patient.records}
        for record_id in args.record_ids:
            if record_id not in index:
                return self._base_envelope(
                    patient_id=patient.patient_id,
                    dataset_version=patient.dataset_version,
                    status="denied",
                    data=None,
                    error=ToolError(code="record_not_accessible", retryable=False),
                )
            if record_id in self._unavailable_record_ids:
                return self._base_envelope(
                    patient_id=patient.patient_id,
                    dataset_version=patient.dataset_version,
                    status="unavailable",
                    data=None,
                    error=ToolError(code="record_unavailable", retryable=True),
                )

        records = [index[record_id] for record_id in args.record_ids]
        envelope = self._base_envelope(
            patient_id=patient.patient_id,
            dataset_version=patient.dataset_version,
            status="ok",
            data=ReadData(records=records),
            error=None,
        )
        if self._envelope_bytes(envelope) > MAX_RESULT_BYTES:
            return self._base_envelope(
                patient_id=patient.patient_id,
                dataset_version=patient.dataset_version,
                status="unavailable",
                data=None,
                error=ToolError(code="result_too_large", retryable=False),
            )
        return envelope

    def record_counts(self, patient_id: str) -> dict[str, int]:
        """Return per-type counts for extension tooling."""
        patient = self._load_patient(patient_id)
        counts: dict[str, int] = {record_type.value: 0 for record_type in RecordType}
        for record in patient.records:
            counts[record.record_type.value] += 1
        return counts
