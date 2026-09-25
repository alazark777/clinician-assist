"""Model adapter port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from clinician_agent.mcp.models import ClinicalRecord, InventoryRecord
from clinician_agent.schemas import Profile


@dataclass(frozen=True)
class ModelUsage:
    """Token usage from a provider."""

    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True)
class ModelResult:
    """One model step result."""

    profile: Profile | None
    requested_record_ids: list[str]
    complete: bool
    usage: ModelUsage


class ModelPort(Protocol):
    """Replaceable model backend."""

    async def generate_profile(
        self,
        *,
        patient_id: str,
        visit_context: str,
        as_of: str,
        records: dict[str, ClinicalRecord],
        inventory: list[InventoryRecord],
        inventory_complete: bool,
        inventory_empty: bool,
        call_index: int,
        budget_exhausted: bool = False,
    ) -> ModelResult:
        """Produce or refine a profile from verified evidence."""
