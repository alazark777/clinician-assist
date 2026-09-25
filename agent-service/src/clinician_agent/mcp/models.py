"""MCP tool envelope models aligned with records service."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from clinician_agent.schemas import StrictModel

MAX_READ_IDS = 20


class RecordType(StrEnum):
    """Supported record types."""

    CONDITION = "condition"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    LAB = "lab"
    VITAL = "vital"
    VISIT_NOTE = "visit_note"


class FactRecord(StrictModel):
    """Structured fact inside a record."""

    section: Literal["condition", "medication", "allergy", "lab", "vital"]
    key: Annotated[str, Field(min_length=1)]
    value: Annotated[str, Field(min_length=1)]
    date: date | None
    qualifier: Annotated[str, Field(min_length=1)]


class RecordContent(StrictModel):
    """Record body."""

    facts: list[FactRecord]
    text: Annotated[str, Field(min_length=1)]


class ClinicalRecord(StrictModel):
    """Versioned clinical record."""

    record_id: Annotated[str, Field(min_length=1, max_length=128)]
    record_type: RecordType
    recorded_at: date
    event_date: date | None
    version: Annotated[int, Field(ge=1)]
    content: RecordContent


class InventoryRecord(StrictModel):
    """Inventory metadata entry."""

    record_id: str
    record_type: RecordType
    recorded_at: date
    event_date: date | None
    version: int
    fact_keys: list[str]


class InventoryData(StrictModel):
    """Inventory payload."""

    records: list[InventoryRecord]
    inventory_complete: bool


class ReadData(StrictModel):
    """Read payload."""

    records: list[ClinicalRecord]


class ToolError(StrictModel):
    """Tool execution error."""

    code: Annotated[str, Field(min_length=1)]
    retryable: bool


class ToolEnvelope(StrictModel):
    """Common MCP tool envelope."""

    schema_version: Literal["1.0"]
    status: Literal["ok", "empty", "unavailable", "denied"]
    patient_id: Annotated[str, Field(min_length=1)]
    dataset_version: Annotated[str, Field(min_length=1)]
    data: InventoryData | ReadData | None
    error: ToolError | None

    @model_validator(mode="after")
    def validate_status_shape(self) -> "ToolEnvelope":
        """Enforce envelope invariants."""
        if self.status in {"ok", "empty"} and (self.data is None or self.error is not None):
            raise ValueError("successful results require data")
        if self.status in {"unavailable", "denied"} and (
            self.data is not None or self.error is None
        ):
            raise ValueError("failed results require error")
        if self.status == "empty":
            if not isinstance(self.data, InventoryData):
                raise ValueError("empty reserved for inventory")
            if self.data.records or not self.data.inventory_complete:
                raise ValueError("empty inventory must be complete")
        if self.status == "ok":
            records = self.data.records if self.data is not None else []
            if not records:
                raise ValueError("ok requires records")
        return self


class ListRecordsArgs(StrictModel):
    """Validated list_records input."""

    record_types: list[RecordType] | None = None
    before: date | None = None


class ReadRecordsArgs(StrictModel):
    """Validated read_records input."""

    record_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=128)]],
        Field(min_length=1, max_length=MAX_READ_IDS),
    ]
