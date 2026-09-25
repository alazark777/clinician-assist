"""Strict data and tool contract models for the records service."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"
MAX_READ_IDS = 20
MAX_INVENTORY_RECORDS = 100
MAX_RESULT_BYTES = 100 * 1024


class StrictModel(BaseModel):
    """Base model that rejects unexpected fields."""

    model_config = ConfigDict(extra="forbid")


class RecordType(StrEnum):
    """Supported synthetic record types."""

    CONDITION = "condition"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    LAB = "lab"
    VITAL = "vital"
    VISIT_NOTE = "visit_note"


class Fact(StrictModel):
    """One structured factual tuple from a synthetic record."""

    section: Literal["condition", "medication", "allergy", "lab", "vital"]
    key: Annotated[str, Field(min_length=1)]
    value: Annotated[str, Field(min_length=1)]
    date: date | None
    qualifier: Annotated[str, Field(min_length=1)]


class RecordContent(StrictModel):
    """Untrusted source text and structured facts."""

    facts: list[Fact]
    text: Annotated[str, Field(min_length=1)]


class Record(StrictModel):
    """A versioned synthetic clinical record."""

    record_id: Annotated[str, Field(min_length=1, max_length=128)]
    record_type: RecordType
    recorded_at: date
    event_date: date | None
    version: Annotated[int, Field(ge=1)]
    content: RecordContent


class PatientFile(StrictModel):
    """Validated patient fixture file."""

    schema_version: Literal["1.0"]
    dataset_version: Annotated[str, Field(min_length=1)]
    patient_id: Annotated[str, Field(min_length=1)]
    records: list[Record]

    @model_validator(mode="after")
    def unique_record_ids(self) -> "PatientFile":
        """Reject duplicate opaque IDs within a patient file."""
        ids = [record.record_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("record_id values must be unique")
        return self


class ListRecordsInput(StrictModel):
    """Model-visible inventory arguments."""

    record_types: list[RecordType] | None = None
    before: date | None = None

    @model_validator(mode="after")
    def unique_record_types(self) -> "ListRecordsInput":
        """Reject duplicate record type filters."""
        if self.record_types and len(self.record_types) != len(set(self.record_types)):
            raise ValueError("record_types must be unique")
        return self


class ReadRecordsInput(StrictModel):
    """Model-visible exact read arguments."""

    record_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=128)]],
        Field(min_length=1, max_length=MAX_READ_IDS),
    ]

    @model_validator(mode="after")
    def unique_ids(self) -> "ReadRecordsInput":
        """Reject duplicate IDs so exact-set semantics stay unambiguous."""
        if len(self.record_ids) != len(set(self.record_ids)):
            raise ValueError("record_ids must be unique")
        return self


class InventoryRecord(StrictModel):
    """Record metadata safe for inventory selection."""

    record_id: str
    record_type: RecordType
    recorded_at: date
    event_date: date | None
    version: int
    fact_keys: list[str]


class InventoryData(StrictModel):
    """Inventory result data."""

    records: list[InventoryRecord]
    inventory_complete: bool


class ReadData(StrictModel):
    """Atomic exact-read result data."""

    records: list[Record]


class ToolError(StrictModel):
    """Stable tool execution error."""

    code: Annotated[str, Field(min_length=1)]
    retryable: bool


class ToolEnvelope(StrictModel):
    """Common strict result envelope."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    status: Literal["ok", "empty", "unavailable", "denied"]
    patient_id: Annotated[str, Field(min_length=1)]
    dataset_version: Annotated[str, Field(min_length=1)]
    data: InventoryData | ReadData | None
    error: ToolError | None

    @model_validator(mode="after")
    def validate_status_shape(self) -> "ToolEnvelope":
        """Enforce success and failure envelope invariants."""
        if self.status in {"ok", "empty"} and (self.data is None or self.error is not None):
            raise ValueError("successful results require data and no error")
        if self.status in {"unavailable", "denied"} and (
            self.data is not None or self.error is None
        ):
            raise ValueError("failed results require error and no data")
        if self.status == "empty":
            if not isinstance(self.data, InventoryData):
                raise ValueError("empty is reserved for inventory")
            if self.data.records or not self.data.inventory_complete:
                raise ValueError("empty inventory must be complete")
        if self.status == "ok":
            records = self.data.records if self.data is not None else []
            if not records:
                raise ValueError("ok results require records")
        return self
