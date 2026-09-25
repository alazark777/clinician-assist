"""Post-baseline supplemental read planning and failure taxonomy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from clinician_agent.mcp.models import InventoryRecord, RecordType
from clinician_agent.retrieval.baseline import LAB_KEYS, _select_latest_group, _sort_key, selection_date


class SupplementalReadPurpose(StrEnum):
    """Why a post-baseline record read was scheduled."""

    HISTORICAL_COMPARISON = "historical_comparison"
    ADAPTIVE = "adaptive"


@dataclass(frozen=True)
class SupplementalReadPlan:
    """One bounded post-baseline read with retrieval purpose metadata."""

    record_id: str
    purpose: SupplementalReadPurpose
    comparable_fact_key: str | None = None


@dataclass
class PostBaselineRetrievalOutcome:
    """Gap-driving failures after baseline evidence exists."""

    historical_comparison_failed: bool = False
    adaptive_supplemental_failed: bool = False

    @property
    def incomplete(self) -> bool:
        """Return whether any supplemental read remained unavailable."""
        return self.historical_comparison_failed or self.adaptive_supplemental_failed

    def merge(self, other: PostBaselineRetrievalOutcome) -> None:
        """Combine outcomes from multiple read phases."""
        self.historical_comparison_failed = (
            self.historical_comparison_failed or other.historical_comparison_failed
        )
        self.adaptive_supplemental_failed = (
            self.adaptive_supplemental_failed or other.adaptive_supplemental_failed
        )

    @classmethod
    def from_failed_plans(cls, plans: list[SupplementalReadPlan]) -> PostBaselineRetrievalOutcome:
        """Derive outcome from plans tied to an unavailable read batch."""
        outcome = cls()
        for plan in plans:
            if plan.purpose == SupplementalReadPurpose.HISTORICAL_COMPARISON:
                outcome.historical_comparison_failed = True
            elif plan.purpose == SupplementalReadPurpose.ADAPTIVE:
                outcome.adaptive_supplemental_failed = True
        return outcome


def historical_comparison_lab_plans(
    inventory: list[InventoryRecord],
    *,
    baseline_ids: set[str],
    as_of: date,
) -> list[SupplementalReadPlan]:
    """Plan indexed earlier comparable lab reads for historical comparison."""
    lab_records = [
        item
        for item in inventory
        if item.record_type == RecordType.LAB and selection_date(item) <= as_of
    ]
    plans: list[SupplementalReadPlan] = []
    for key in LAB_KEYS:
        candidates = [record for record in lab_records if key in record.fact_keys]
        if len(candidates) <= 1:
            continue
        latest = _select_latest_group(candidates)
        latest_ids = {record.record_id for record in latest}
        for record in sorted(candidates, key=_sort_key):
            if record.record_id in latest_ids or record.record_id in baseline_ids:
                continue
            plans.append(
                SupplementalReadPlan(
                    record_id=record.record_id,
                    purpose=SupplementalReadPurpose.HISTORICAL_COMPARISON,
                    comparable_fact_key=key,
                )
            )
    return _dedupe_plans(plans)


def adaptive_supplemental_plans(record_ids: list[str]) -> list[SupplementalReadPlan]:
    """Tag coordinator- or model-requested supplemental reads as adaptive."""
    seen: set[str] = set()
    plans: list[SupplementalReadPlan] = []
    for record_id in record_ids:
        if record_id in seen:
            continue
        seen.add(record_id)
        plans.append(
            SupplementalReadPlan(
                record_id=record_id,
                purpose=SupplementalReadPurpose.ADAPTIVE,
            )
        )
    return plans


def supplemental_lab_record_ids(
    inventory: list[InventoryRecord],
    *,
    baseline_ids: set[str],
    as_of: date,
) -> list[str]:
    """Return historical-comparison lab record IDs (stable order)."""
    return [
        plan.record_id
        for plan in historical_comparison_lab_plans(
            inventory, baseline_ids=baseline_ids, as_of=as_of
        )
    ]


def _dedupe_plans(plans: list[SupplementalReadPlan]) -> list[SupplementalReadPlan]:
    deduped: list[SupplementalReadPlan] = []
    seen: set[str] = set()
    for plan in plans:
        if plan.record_id not in seen:
            deduped.append(plan)
            seen.add(plan.record_id)
    return deduped
