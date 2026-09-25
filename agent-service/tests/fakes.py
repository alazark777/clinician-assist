"""Test doubles shared across suites."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from clinician_agent.mcp.models import (
    ClinicalRecord,
    FactRecord,
    InventoryData,
    InventoryRecord,
    ReadData,
    RecordContent,
    RecordType,
    ToolEnvelope,
    ToolError,
)


class FakeRecordsGateway:
    """In-memory MCP gateway for tests."""

    def __init__(self, patient_id: str, inventory: list[InventoryRecord], records: dict[str, ClinicalRecord]):
        self.patient_id = patient_id
        self.inventory = inventory
        self.records = records
        self.tool_attempts = 0
        self.fail_next_read = False
        self.fail_next_list = False
        self.permanently_unavailable_record_ids: set[str] = set()
        self.read_calls = 0

    async def list_records(self, *, before: date, record_types: list[str] | None = None) -> ToolEnvelope:
        self.tool_attempts += 1
        if self.fail_next_list:
            self.fail_next_list = False
            return ToolEnvelope(
                schema_version="1.0",
                status="unavailable",
                patient_id=self.patient_id,
                dataset_version="test-1",
                data=None,
                error=ToolError(code="inventory_unavailable", retryable=True),
            )
        filtered = [
            item
            for item in self.inventory
            if (item.event_date or item.recorded_at) <= before
            and (not record_types or item.record_type.value in record_types)
        ]
        if not filtered:
            return ToolEnvelope(
                schema_version="1.0",
                status="empty",
                patient_id=self.patient_id,
                dataset_version="test-1",
                data=InventoryData(records=[], inventory_complete=True),
                error=None,
            )
        return ToolEnvelope(
            schema_version="1.0",
            status="ok",
            patient_id=self.patient_id,
            dataset_version="test-1",
            data=InventoryData(records=filtered, inventory_complete=True),
            error=None,
        )

    async def list_with_retry(
        self, *, before: date, record_types: list[str] | None = None
    ) -> ToolEnvelope:
        """Inventory with one transient retry."""
        envelope = await self.list_records(before=before, record_types=record_types)
        if (
            envelope.status == "unavailable"
            and envelope.error is not None
            and envelope.error.retryable
        ):
            return await self.list_records(before=before, record_types=record_types)
        return envelope

    async def read_records(self, *, record_ids: list[str]) -> ToolEnvelope:
        self.tool_attempts += 1
        self.read_calls += 1
        if any(record_id in self.permanently_unavailable_record_ids for record_id in record_ids):
            return ToolEnvelope(
                schema_version="1.0",
                status="unavailable",
                patient_id=self.patient_id,
                dataset_version="test-1",
                data=None,
                error=ToolError(code="record_unavailable", retryable=True),
            )
        if self.fail_next_read:
            self.fail_next_read = False
            return ToolEnvelope(
                schema_version="1.0",
                status="unavailable",
                patient_id=self.patient_id,
                dataset_version="test-1",
                data=None,
                error=ToolError(code="record_unavailable", retryable=True),
            )
        missing = [record_id for record_id in record_ids if record_id not in self.records]
        if missing:
            return ToolEnvelope(
                schema_version="1.0",
                status="denied",
                patient_id=self.patient_id,
                dataset_version="test-1",
                data=None,
                error=ToolError(code="record_not_accessible", retryable=False),
            )
        payload = [self.records[record_id] for record_id in record_ids]
        return ToolEnvelope(
            schema_version="1.0",
            status="ok",
            patient_id=self.patient_id,
            dataset_version="test-1",
            data=ReadData(records=payload),
            error=None,
        )

    async def read_with_retry(self, *, record_ids: list[str]) -> ToolEnvelope:
        """Read with one transient retry."""
        envelope = await self.read_records(record_ids=record_ids)
        if (
            envelope.status == "unavailable"
            and envelope.error is not None
            and envelope.error.retryable
        ):
            return await self.read_records(record_ids=record_ids)
        return envelope


def write_demo_sessions(path: Path) -> None:
    """Write demo session secrets."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "reviewer",
                        "passphrase": "local-demo",
                        "caller_id": "caller-a",
                        "patients": [
                            {"patient_id": "P001", "label": "Patient One"},
                            {"patient_id": "P002", "label": "Patient Two"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def write_signing_key(path: Path) -> str:
    """Write an RS256 signing key and return the matching public PEM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_text(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8"),
        encoding="utf-8",
    )
    return (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )


def sample_records() -> tuple[list[InventoryRecord], dict[str, ClinicalRecord]]:
    """Synthetic in-memory patient records."""
    inventory = [
        InventoryRecord(
            record_id="cond-1",
            record_type=RecordType.CONDITION,
            recorded_at=date(2024, 1, 2),
            event_date=date(2024, 1, 1),
            version=1,
            fact_keys=["Type 2 diabetes"],
        ),
        InventoryRecord(
            record_id="med-1",
            record_type=RecordType.MEDICATION,
            recorded_at=date(2024, 2, 1),
            event_date=date(2024, 2, 1),
            version=1,
            fact_keys=["metformin"],
        ),
        InventoryRecord(
            record_id="lab-1",
            record_type=RecordType.LAB,
            recorded_at=date(2024, 3, 1),
            event_date=date(2024, 3, 1),
            version=1,
            fact_keys=["HbA1c"],
        ),
    ]
    records = {
        "cond-1": ClinicalRecord(
            record_id="cond-1",
            record_type=RecordType.CONDITION,
            recorded_at=date(2024, 1, 2),
            event_date=date(2024, 1, 1),
            version=1,
            content=RecordContent(
                facts=[
                    FactRecord(
                        section="condition",
                        key="Type 2 diabetes",
                        value="Type 2 diabetes",
                        date=date(2024, 1, 1),
                        qualifier="problem-list",
                    )
                ],
                text="Problem list documents type 2 diabetes.",
            ),
        ),
        "med-1": ClinicalRecord(
            record_id="med-1",
            record_type=RecordType.MEDICATION,
            recorded_at=date(2024, 2, 1),
            event_date=date(2024, 2, 1),
            version=1,
            content=RecordContent(
                facts=[
                    FactRecord(
                        section="medication",
                        key="metformin",
                        value="500 mg BID",
                        date=date(2024, 2, 1),
                        qualifier="active",
                    )
                ],
                text="Continue metformin 500 mg twice daily.",
            ),
        ),
        "lab-1": ClinicalRecord(
            record_id="lab-1",
            record_type=RecordType.LAB,
            recorded_at=date(2024, 3, 1),
            event_date=date(2024, 3, 1),
            version=1,
            content=RecordContent(
                facts=[
                    FactRecord(
                        section="lab",
                        key="HbA1c",
                        value="7.4%",
                        date=date(2024, 3, 1),
                        qualifier="lab-result",
                    )
                ],
                text="HbA1c 7.4 percent.",
            ),
        ),
    }
    return inventory, records
