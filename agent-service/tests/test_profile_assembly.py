"""Behavioral tests for deterministic profile assembly."""

from datetime import date

from clinician_agent.mcp.models import (
    ClinicalRecord,
    FactRecord,
    InventoryRecord,
    RecordContent,
    RecordType,
)
from clinician_agent.profile_assembly import assemble_profile, supplemental_lab_record_ids


def _inventory(*items: InventoryRecord) -> list[InventoryRecord]:
    return list(items)


def _record(
    record_id: str,
    record_type: RecordType,
    *,
    key: str,
    value: str,
    fact_date: date | None,
    event_date: date | None,
    recorded_at: date,
    qualifier: str = "documented",
) -> ClinicalRecord:
    section = record_type.value if record_type != RecordType.VISIT_NOTE else "condition"
    return ClinicalRecord(
        record_id=record_id,
        record_type=record_type,
        recorded_at=recorded_at,
        event_date=event_date,
        version=1,
        content=RecordContent(
            facts=[
                FactRecord(
                    section=section,  # type: ignore[arg-type]
                    key=key,
                    value=value,
                    date=fact_date,
                    qualifier=qualifier,
                )
            ],
            text=f"Synthetic record: {key}: {value}. Status: {qualifier}.",
        ),
    )


def test_standard_inventory_gaps_include_vitals_and_single_hba1c():
    inventory = _inventory(
        InventoryRecord(
            record_id="r1",
            record_type=RecordType.CONDITION,
            recorded_at=date(2026, 6, 10),
            event_date=date(2026, 6, 10),
            version=1,
            fact_keys=["condition"],
        ),
        InventoryRecord(
            record_id="r2",
            record_type=RecordType.LAB,
            recorded_at=date(2026, 9, 15),
            event_date=date(2026, 9, 15),
            version=1,
            fact_keys=["HbA1c"],
        ),
    )
    records = {
        "r1": _record(
            "r1",
            RecordType.CONDITION,
            key="condition",
            value="Type 2 diabetes",
            fact_date=date(2026, 6, 10),
            event_date=date(2026, 6, 10),
            recorded_at=date(2026, 6, 10),
        ),
        "r2": _record(
            "r2",
            RecordType.LAB,
            key="HbA1c",
            value="7.8%",
            fact_date=date(2026, 9, 15),
            event_date=date(2026, 9, 15),
            recorded_at=date(2026, 9, 15),
        ),
    }
    profile = assemble_profile(
        patient_id="P001",
        as_of=date(2026, 9, 24),
        inventory=inventory,
        records=records,
        inventory_complete=True,
        inventory_empty=False,
    )
    codes = {gap.code for gap in profile.gaps}
    assert codes == {"no_medication_record", "no_allergy_record", "no_vitals", "no_prior_hba1c"}
    assert profile.status == "complete"


def test_empty_inventory_is_complete_with_category_gaps():
    profile = assemble_profile(
        patient_id="P008",
        as_of=date(2026, 9, 24),
        inventory=[],
        records={},
        inventory_complete=True,
        inventory_empty=True,
    )
    assert profile.status == "complete"
    assert {gap.code for gap in profile.gaps} == {
        "no_condition_record",
        "no_medication_record",
        "no_allergy_record",
        "no_vitals",
    }


def test_medication_dose_conflict_and_supplemental_lab_ids():
    inventory = _inventory(
        InventoryRecord(
            record_id="m1",
            record_type=RecordType.MEDICATION,
            recorded_at=date(2026, 6, 10),
            event_date=date(2026, 6, 10),
            version=1,
            fact_keys=["metformin"],
        ),
        InventoryRecord(
            record_id="m2",
            record_type=RecordType.MEDICATION,
            recorded_at=date(2026, 6, 10),
            event_date=date(2026, 6, 10),
            version=1,
            fact_keys=["metformin"],
        ),
        InventoryRecord(
            record_id="lab-old",
            record_type=RecordType.LAB,
            recorded_at=date(2026, 1, 15),
            event_date=date(2026, 1, 15),
            version=1,
            fact_keys=["HbA1c"],
        ),
        InventoryRecord(
            record_id="lab-new",
            record_type=RecordType.LAB,
            recorded_at=date(2026, 9, 15),
            event_date=date(2026, 9, 15),
            version=1,
            fact_keys=["HbA1c"],
        ),
    )
    extra = supplemental_lab_record_ids(
        inventory, baseline_ids={"lab-new"}, as_of=date(2026, 9, 24)
    )
    assert extra == ["lab-old"]
    records = {
        "m1": _record(
            "m1",
            RecordType.MEDICATION,
            key="metformin",
            value="500 mg twice daily",
            fact_date=date(2026, 6, 10),
            event_date=date(2026, 6, 10),
            recorded_at=date(2026, 6, 10),
            qualifier="last_documented_current_use_unconfirmed",
        ),
        "m2": _record(
            "m2",
            RecordType.MEDICATION,
            key="metformin",
            value="1000 mg twice daily",
            fact_date=date(2026, 6, 10),
            event_date=date(2026, 6, 10),
            recorded_at=date(2026, 6, 10),
            qualifier="last_documented_current_use_unconfirmed",
        ),
    }
    profile = assemble_profile(
        patient_id="P004",
        as_of=date(2026, 9, 24),
        inventory=inventory,
        records=records,
        inventory_complete=True,
        inventory_empty=False,
    )
    assert profile.conflicts[0].code == "medication_dose_conflict"
    assert set(profile.conflicts[0].source_ids) == {"m1", "m2"}


def test_event_date_unknown_preserves_qualifier_and_adds_gap():
    record = _record(
        "lab-1",
        RecordType.LAB,
        key="HbA1c",
        value="7.6%",
        fact_date=None,
        event_date=None,
        recorded_at=date(2026, 9, 15),
        qualifier="event_date_unknown",
    )
    profile = assemble_profile(
        patient_id="P006",
        as_of=date(2026, 9, 24),
        inventory=[
            InventoryRecord(
                record_id="lab-1",
                record_type=RecordType.LAB,
                recorded_at=date(2026, 9, 15),
                event_date=None,
                version=1,
                fact_keys=["HbA1c"],
            )
        ],
        records={"lab-1": record},
        inventory_complete=True,
        inventory_empty=False,
    )
    assert profile.facts[0].qualifier == "event_date_unknown"
    assert profile.facts[0].date is None
    assert any(gap.code == "lab_event_date_unknown" for gap in profile.gaps)
