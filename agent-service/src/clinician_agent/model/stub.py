"""Offline deterministic model stub."""

from __future__ import annotations

from datetime import date

from clinician_agent.mcp.models import ClinicalRecord, InventoryRecord
from clinician_agent.model.port import ModelPort, ModelResult, ModelUsage
from clinician_agent.profile_assembly import assemble_profile
from clinician_agent.schemas import Profile


class OfflineStubModel:
    """Build profiles directly from MCP evidence without external calls."""

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
        """Map structured record facts into a profile envelope."""
        _ = (visit_context, call_index)
        profile: Profile = assemble_profile(
            patient_id=patient_id,
            as_of=date.fromisoformat(as_of),
            inventory=inventory,
            records=records,
            inventory_complete=inventory_complete,
            inventory_empty=inventory_empty,
            budget_exhausted=budget_exhausted,
        )
        return ModelResult(
            profile=profile,
            requested_record_ids=[],
            complete=True,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
        )
