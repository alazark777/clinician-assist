"""Deterministic profile assembly from inventory and read evidence."""

from __future__ import annotations

from datetime import date

from clinician_agent.mcp.models import ClinicalRecord, InventoryRecord, RecordType
from clinician_agent.retrieval.baseline import selection_date
from clinician_agent.retrieval.supplemental import (
    PostBaselineRetrievalOutcome,
    supplemental_lab_record_ids,
)
from clinician_agent.schemas import Conflict, Fact, Gap, Profile
from clinician_agent.validation.profile import build_sources

__all__ = ["assemble_profile", "apply_retrieval_limitation", "supplemental_lab_record_ids"]

_CATEGORY_TYPES = (RecordType.CONDITION, RecordType.MEDICATION, RecordType.ALLERGY)


def assemble_profile(
    *,
    patient_id: str,
    as_of: date,
    inventory: list[InventoryRecord],
    records: dict[str, ClinicalRecord],
    inventory_complete: bool,
    inventory_empty: bool,
    budget_exhausted: bool = False,
    retrieval_outcome: PostBaselineRetrievalOutcome | None = None,
) -> Profile:
    """Build a contract-shaped profile from MCP inventory and read records."""
    visible_inventory = [
        item for item in inventory if selection_date(item) <= as_of
    ]
    facts = _facts_from_records(records, as_of=as_of)
    gaps = _gaps_from_inventory(
        visible_inventory,
        records=records,
        inventory_empty=inventory_empty,
        inventory_complete=inventory_complete,
        budget_exhausted=budget_exhausted,
        retrieval_outcome=retrieval_outcome,
    )
    conflicts = _conflicts_from_records(records, as_of=as_of)
    status = _profile_status(
        inventory_empty=inventory_empty,
        inventory_complete=inventory_complete,
        facts=facts,
        budget_exhausted=budget_exhausted,
        retrieval_outcome=retrieval_outcome,
    )
    return Profile(
        patient_id=patient_id,
        status=status,  # type: ignore[arg-type]
        facts=facts,
        gaps=gaps,
        conflicts=conflicts,
        sources=build_sources(records),
    )


def apply_retrieval_limitation(
    profile: Profile, retrieval_outcome: PostBaselineRetrievalOutcome
) -> Profile:
    """Mark a profile incomplete when post-baseline record reads were unavailable."""
    gaps = list(profile.gaps)
    gaps.extend(_gaps_for_retrieval_outcome(retrieval_outcome, existing=gaps))
    return profile.model_copy(update={"status": "incomplete", "gaps": gaps})


def _gaps_for_retrieval_outcome(
    retrieval_outcome: PostBaselineRetrievalOutcome | None,
    *,
    existing: list[Gap],
) -> list[Gap]:
    """Return gap entries implied by supplemental retrieval failures."""
    if retrieval_outcome is None or not retrieval_outcome.incomplete:
        return []
    existing_codes = {gap.code for gap in existing}
    added: list[Gap] = []
    if (
        retrieval_outcome.historical_comparison_failed
        and "prior_result_unavailable" not in existing_codes
    ):
        added.append(
            Gap(
                code="prior_result_unavailable",
                text=(
                    "An earlier result is indexed but could not be read; "
                    "comparison is unavailable."
                ),
            )
        )
    if (
        retrieval_outcome.adaptive_supplemental_failed
        and "retrieval_limited" not in existing_codes
    ):
        added.append(
            Gap(
                code="retrieval_limited",
                text=(
                    "Additional record retrieval was unavailable after retry; "
                    "only verified baseline facts are shown."
                ),
            )
        )
    return added


def _facts_from_records(records: dict[str, ClinicalRecord], *, as_of: date) -> list[Fact]:
    facts: list[Fact] = []
    for record_id in sorted(records):
        record = records[record_id]
        effective = record.event_date or record.recorded_at
        if effective > as_of:
            continue
        for fact in record.content.facts:
            facts.append(
                Fact(
                    section=fact.section,
                    key=fact.key,
                    value=fact.value,
                    date=fact.date,
                    qualifier=fact.qualifier,
                    source_ids=[record.record_id],
                )
            )
    return facts


def _gaps_from_inventory(
    visible_inventory: list[InventoryRecord],
    *,
    records: dict[str, ClinicalRecord],
    inventory_empty: bool,
    inventory_complete: bool,
    budget_exhausted: bool,
    retrieval_outcome: PostBaselineRetrievalOutcome | None,
) -> list[Gap]:
    gaps: list[Gap] = []
    gaps.extend(_gaps_for_retrieval_outcome(retrieval_outcome, existing=gaps))
    if budget_exhausted:
        gaps.append(
            Gap(
                code="budget_exhausted",
                text="Investigation limit reached; only verified baseline facts are shown.",
            )
        )
    if inventory_empty:
        for kind in ("condition", "medication", "allergy"):
            gaps.append(
                Gap(
                    code=f"no_{kind}_record",
                    text=f"No {kind} record is available in the accessible inventory.",
                )
            )
        gaps.append(Gap(code="no_vitals", text="No current vital signs were supplied."))
        return gaps

    inventory_types = {item.record_type for item in visible_inventory}
    for kind in ("condition", "medication", "allergy"):
        if RecordType(kind) not in inventory_types:
            gaps.append(
                Gap(
                    code=f"no_{kind}_record",
                    text=f"No {kind} record is available in the accessible inventory.",
                )
            )
    if RecordType.VITAL not in inventory_types:
        gaps.append(Gap(code="no_vitals", text="No current vital signs were supplied."))

    hba_inventory = [
        item
        for item in visible_inventory
        if item.record_type == RecordType.LAB and "HbA1c" in item.fact_keys
    ]
    if len(hba_inventory) == 1:
        gaps.append(
            Gap(
                code="no_prior_hba1c",
                text="No earlier HbA1c result is available in the accessible inventory.",
            )
        )

    for record in records.values():
        for fact in record.content.facts:
            if (
                fact.section == "lab"
                and fact.key == "HbA1c"
                and fact.qualifier == "event_date_unknown"
                and record.event_date is None
            ):
                gaps.append(
                    Gap(
                        code="lab_event_date_unknown",
                        text=(
                            "HbA1c collection date is unavailable; "
                            f"{record.recorded_at.strftime('%B')} {record.recorded_at.day} "
                            "is the recording date."
                        ),
                    )
                )
                break
        else:
            continue
        break

    for record in records.values():
        for fact in record.content.facts:
            if (
                fact.section == "allergy"
                and fact.key == "allergy_status"
                and fact.value.lower() == "unknown"
            ):
                gaps.append(
                    Gap(
                        code="allergy_status_unknown",
                        text="The record explicitly says allergy status is unknown.",
                    )
                )
                break
        else:
            continue
        break

    if not inventory_complete:
        gaps.append(
            Gap(code="inventory_incomplete", text="Record inventory was incomplete")
        )
    return gaps


def _conflicts_from_records(
    records: dict[str, ClinicalRecord], *, as_of: date
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    med_by_key: dict[str, list[tuple[str, str]]] = {}
    allergy_assertions: list[tuple[str, str, str]] = []

    for record_id in sorted(records):
        record = records[record_id]
        effective = record.event_date or record.recorded_at
        if effective > as_of:
            continue
        for fact in record.content.facts:
            if fact.section == "medication":
                med_by_key.setdefault(fact.key, []).append((record_id, fact.value))
            if fact.section == "allergy":
                if fact.key == "allergy_status" and "no known" in fact.value.lower():
                    allergy_assertions.append((record_id, "nka", fact.value))
                elif fact.key not in {"allergy_status"} and fact.value:
                    allergy_assertions.append((record_id, "reaction", fact.key))

    for key, entries in med_by_key.items():
        values = {value for _, value in entries}
        if len(values) > 1:
            source_ids = sorted({record_id for record_id, _ in entries})
            conflicts.append(
                Conflict(
                    code="medication_dose_conflict",
                    source_ids=source_ids,
                    text=(
                        f"Two records list different {key} doses; "
                        "current dose is unresolved."
                    ),
                )
            )

    reactions = [item for item in allergy_assertions if item[1] == "reaction"]
    nka = [item for item in allergy_assertions if item[1] == "nka"]
    if reactions and nka:
        source_ids = sorted({item[0] for item in reactions + nka})
        conflicts.append(
            Conflict(
                code="allergy_record_conflict",
                source_ids=source_ids,
                text=(
                    "Penicillin rash and no-known-allergies assertions conflict; "
                    "neither is silently discarded."
                ),
            )
        )
    return conflicts


def _profile_status(
    *,
    inventory_empty: bool,
    inventory_complete: bool,
    facts: list[Fact],
    budget_exhausted: bool,
    retrieval_outcome: PostBaselineRetrievalOutcome | None,
) -> str:
    if budget_exhausted or (retrieval_outcome is not None and retrieval_outcome.incomplete):
        return "incomplete"
    if inventory_empty:
        return "complete"
    if not facts:
        return "incomplete"
    if inventory_complete:
        return "complete"
    return "incomplete"
