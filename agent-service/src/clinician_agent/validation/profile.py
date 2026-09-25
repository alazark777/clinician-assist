"""Profile validation against read evidence."""

from __future__ import annotations

from datetime import date

from clinician_agent.mcp.models import ClinicalRecord
from clinician_agent.schemas import Conflict, Fact, Gap, Profile, Source


class ProfileValidationError(ValueError):
    """Raised when profile validation fails."""


def build_sources(records: dict[str, ClinicalRecord]) -> list[Source]:
    """Build source snapshots from read records."""
    from clinician_agent.util import excerpt_text

    sources: list[Source] = []
    for record_id in sorted(records):
        record = records[record_id]
        sources.append(
            Source(
                record_id=record.record_id,
                version=record.version,
                excerpt=excerpt_text(record.content.text),
            )
        )
    return sources


def validate_profile_against_records(
    profile: Profile,
    *,
    records: dict[str, ClinicalRecord],
    as_of: date,
) -> None:
    """Validate provenance, scope, and temporal rules."""
    available = set(records)
    for fact in profile.facts:
        for source_id in fact.source_ids:
            if source_id not in available:
                raise ProfileValidationError(f"unknown source {source_id}")
            record = records[source_id]
            effective = record.event_date or record.recorded_at
            if effective > as_of:
                raise ProfileValidationError("future event in fact")
        _validate_numeric_fact(fact)

    for conflict in profile.conflicts:
        if len(conflict.source_ids) < 2:
            raise ProfileValidationError("conflict requires two sources")
        for source_id in conflict.source_ids:
            if source_id not in available:
                raise ProfileValidationError(f"conflict source missing {source_id}")


def _validate_numeric_fact(fact: Fact) -> None:
    """Basic numeric/date consistency checks."""
    if fact.section in {"lab", "vital"}:
        cleaned = fact.value.replace("%", "").strip()
        try:
            float(cleaned.split()[0])
        except ValueError as exc:
            raise ProfileValidationError(f"non-numeric value for {fact.key}") from exc
