"""Bounded profile generation coordinator."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from clinician_agent.auth.jwt_tokens import McpTokenIssuer
from clinician_agent.db import Database
from clinician_agent.errors import AppError
from clinician_agent.mcp.client import McpCallContext, RecordsGateway, build_records_client
from clinician_agent.mcp.models import ClinicalRecord, InventoryData, InventoryRecord, ReadData, ToolEnvelope
from clinician_agent.mcp.registry import McpRegistry
from clinician_agent.model.port import ModelPort
from clinician_agent.profile_assembly import apply_retrieval_limitation, assemble_profile
from clinician_agent.retrieval.supplemental import (
    PostBaselineRetrievalOutcome,
    SupplementalReadPlan,
    adaptive_supplemental_plans,
    historical_comparison_lab_plans,
)
from clinician_agent.retrieval.baseline import chunk_ids, select_baseline_ids
from clinician_agent.retrieval.budget import RunBudget
from clinician_agent.schemas import Profile, ProfileRequest, Usage
from clinician_agent.settings import Settings
from clinician_agent.telemetry import log_event, span
from clinician_agent.testing.hooks import should_exhaust_model_budget_after_baseline
from clinician_agent.util import new_id
from clinician_agent.validation.profile import (
    ProfileValidationError,
    build_sources,
    validate_profile_against_records,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoordinatorResult:
    """Terminal coordinator output."""

    profile_id: str
    profile: Profile
    usage: Usage


class ProfileCoordinator:
    """Orchestrate retrieval, model calls, and persistence."""

    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        registry: McpRegistry,
        token_issuer: McpTokenIssuer,
        model: ModelPort,
        records_client_factory=build_records_client,
    ) -> None:
        """Wire dependencies."""
        self._settings = settings
        self._db = db
        self._registry = registry
        self._token_issuer = token_issuer
        self._model = model
        self._records_client_factory = records_client_factory

    async def generate(
        self,
        *,
        run_id: str,
        caller_id: str,
        body: ProfileRequest,
        trace_id: str,
        cancel_event: asyncio.Event | None = None,
        gateway: RecordsGateway | None = None,
    ) -> CoordinatorResult:
        """Execute one profile generation run."""
        with span("profile.generate", run_id=run_id):
            budget = RunBudget(deadline_seconds=self._settings.total_deadline_seconds)
            token = self._token_issuer.issue(
                patient_id=body.patient_id,
                audience=self._records_server().token_audience,
            )
            if gateway is None:
                gateway = self._records_client_factory(
                    self._registry,
                    context=McpCallContext(
                        patient_id=body.patient_id,
                        bearer_token=token,
                        expected_patient_id=body.patient_id,
                        request_origin=self._settings.mcp_request_origin,
                    ),
                )
            records = await self._baseline_retrieval(
                gateway,
                as_of=body.as_of,
                budget=budget,
                cancel_event=cancel_event,
            )
            inventory_complete = bool(records["inventory_complete"])
            inventory_empty = bool(records["inventory_empty"])
            retrieval_outcome = records.get("retrieval_outcome")
            if not isinstance(retrieval_outcome, PostBaselineRetrievalOutcome):
                retrieval_outcome = PostBaselineRetrievalOutcome()
            inventory: list[InventoryRecord] = records["inventory"]  # type: ignore[assignment]
            baseline_ids = set(records["baseline_ids"])  # type: ignore[arg-type]
            budget.baseline_ids = baseline_ids
            read_map: dict[str, ClinicalRecord] = records["records"]  # type: ignore[assignment]

            budget_exhausted = False
            if should_exhaust_model_budget_after_baseline():
                budget_exhausted = True
                for _ in range(budget.max_model_calls):
                    budget.record_model_call()

            if records["inventory_failed"]:
                raise AppError("inventory_failed", "Unable to inventory records", 503)

            if not read_map and inventory_empty:
                profile = assemble_profile(
                    patient_id=body.patient_id,
                    as_of=body.as_of,
                    inventory=inventory,
                    records=read_map,
                    inventory_complete=inventory_complete,
                    inventory_empty=True,
                    budget_exhausted=budget_exhausted,
                    retrieval_outcome=retrieval_outcome,
                )
            elif not read_map:
                raise AppError("no_evidence", "No usable evidence retrieved", 503)
            elif budget_exhausted:
                profile = assemble_profile(
                    patient_id=body.patient_id,
                    as_of=body.as_of,
                    inventory=inventory,
                    records=read_map,
                    inventory_complete=inventory_complete,
                    inventory_empty=False,
                    budget_exhausted=True,
                    retrieval_outcome=retrieval_outcome,
                )
            else:
                profile, adaptive_outcome = await self._model_phase(
                    body=body,
                    read_map=read_map,
                    inventory=inventory,
                    inventory_complete=inventory_complete,
                    inventory_empty=inventory_empty,
                    budget=budget,
                    cancel_event=cancel_event,
                    gateway=gateway,
                    baseline_ids=baseline_ids,
                )
                retrieval_outcome.merge(adaptive_outcome)
                if retrieval_outcome.incomplete:
                    profile = apply_retrieval_limitation(profile, retrieval_outcome)

            sources = build_sources(read_map)
            profile = profile.model_copy(update={"sources": sources})
            with span("profile.validate"):
                try:
                    validate_profile_against_records(profile, records=read_map, as_of=body.as_of)
                except ProfileValidationError as exc:
                    raise AppError("profile_invalid", str(exc), 422) from exc

            usage = Usage(
                model_calls=budget.model_calls,
                tool_attempts=getattr(gateway, "tool_attempts", 0),
                additional_record_ids=budget.additional_record_ids,
                input_tokens=None,
                output_tokens=None,
            )
            with span("profile.persist", run_id=run_id):
                profile_id = new_id("prof")
                await self._db.save_source_snapshots(
                    run_id=run_id,
                    records=[record.model_dump(mode="json") for record in read_map.values()],
                )
                await self._db.save_profile(
                    profile_id=profile_id,
                    run_id=run_id,
                    caller_id=caller_id,
                    patient_id=body.patient_id,
                    profile=profile,
                    sources=sources,
                    usage=usage,
                )
                await self._db.complete_run(run_id=run_id, profile_id=profile_id, usage=usage)
            log_event("profile.completed", run_id=run_id, trace_id=trace_id, status=profile.status)
            return CoordinatorResult(profile_id=profile_id, profile=profile, usage=usage)

    async def _baseline_retrieval(
        self,
        gateway: RecordsGateway,
        *,
        as_of: date,
        budget: RunBudget,
        cancel_event: asyncio.Event | None,
    ) -> dict[str, object]:
        """Inventory and read the deterministic baseline set."""
        if cancel_event and cancel_event.is_set():
            raise AppError("cancelled", "Run cancelled", 499)
        list_envelope = await self._list_with_retry(gateway, before=as_of)
        if list_envelope.status == "unavailable":
            return {
                "inventory_complete": False,
                "inventory_empty": False,
                "inventory_failed": True,
                "inventory": [],
                "baseline_ids": [],
                "records": {},
                "retrieval_outcome": PostBaselineRetrievalOutcome(),
            }
        (
            inventory_complete,
            inventory_empty,
            baseline_ids,
            read_map,
            inventory,
            retrieval_outcome,
        ) = await self._handle_inventory(
            gateway,
            list_envelope,
            as_of=as_of,
            budget=budget,
            cancel_event=cancel_event,
        )
        return {
            "inventory_complete": inventory_complete,
            "inventory_empty": inventory_empty,
            "inventory_failed": False,
            "inventory": inventory,
            "baseline_ids": baseline_ids,
            "records": read_map,
            "retrieval_outcome": retrieval_outcome,
        }

    async def _list_with_retry(
        self, gateway: RecordsGateway, *, before: date
    ) -> ToolEnvelope:
        """Call inventory with retry semantics when supported."""
        list_with_retry = getattr(gateway, "list_with_retry", None)
        if callable(list_with_retry):
            return await list_with_retry(before=before)
        return await gateway.list_records(before=before)

    async def _read_with_retry(self, gateway: RecordsGateway, *, record_ids: list[str]) -> ToolEnvelope:
        """Call read with retry semantics when supported."""
        read_with_retry = getattr(gateway, "read_with_retry", None)
        if callable(read_with_retry):
            return await read_with_retry(record_ids=record_ids)
        return await gateway.read_records(record_ids=record_ids)

    async def _handle_inventory(
        self,
        gateway: RecordsGateway,
        envelope: ToolEnvelope,
        *,
        as_of: date,
        budget: RunBudget,
        cancel_event: asyncio.Event | None,
    ) -> tuple[
        bool,
        bool,
        list[str],
        dict[str, ClinicalRecord],
        list[InventoryRecord],
        PostBaselineRetrievalOutcome,
    ]:
        """Process inventory and baseline reads."""
        if envelope.status == "empty":
            return True, True, [], {}, [], PostBaselineRetrievalOutcome()
        if envelope.status != "ok" or not isinstance(envelope.data, InventoryData):
            raise AppError("inventory_failed", "Unable to inventory records", 503)
        inventory = envelope.data.records
        baseline_ids = select_baseline_ids(inventory)
        read_map: dict[str, ClinicalRecord] = {}
        baseline_set = set(baseline_ids)
        retrieval_outcome = PostBaselineRetrievalOutcome()
        for batch in chunk_ids(baseline_ids):
            if budget.expired():
                break
            if cancel_event and cancel_event.is_set():
                raise AppError("cancelled", "Run cancelled", 499)
            read_envelope = await self._read_with_retry(gateway, record_ids=batch)
            if read_envelope.status != "ok" or not isinstance(read_envelope.data, ReadData):
                raise AppError("baseline_read_failed", "Baseline read failed", 503)
            for record in read_envelope.data.records:
                read_map[record.record_id] = record

        supplemental_plans = historical_comparison_lab_plans(
            inventory, baseline_ids=baseline_set, as_of=as_of
        )
        if supplemental_plans:
            phase_outcome = await self._read_post_baseline_records(
                gateway,
                plans=supplemental_plans,
                read_map=read_map,
                budget=budget,
                cancel_event=cancel_event,
            )
            retrieval_outcome.merge(phase_outcome)

        return (
            envelope.data.inventory_complete,
            False,
            baseline_ids,
            read_map,
            inventory,
            retrieval_outcome,
        )

    async def _read_post_baseline_records(
        self,
        gateway: RecordsGateway,
        *,
        plans: list[SupplementalReadPlan],
        read_map: dict[str, ClinicalRecord],
        budget: RunBudget,
        cancel_event: asyncio.Event | None,
    ) -> PostBaselineRetrievalOutcome:
        """Read additional record IDs after baseline evidence exists."""
        outcome = PostBaselineRetrievalOutcome()
        record_ids = [plan.record_id for plan in plans]
        if not record_ids or not read_map:
            return outcome
        if not budget.can_read_additional(record_ids):
            return outcome
        plan_by_id = {plan.record_id: plan for plan in plans}
        for batch in chunk_ids(record_ids):
            if budget.expired():
                break
            if cancel_event and cancel_event.is_set():
                raise AppError("cancelled", "Run cancelled", 499)
            if not budget.can_read_additional(batch):
                break
            read_envelope = await self._read_with_retry(gateway, record_ids=batch)
            if read_envelope.status != "ok" or not isinstance(read_envelope.data, ReadData):
                batch_plans = [plan_by_id[record_id] for record_id in batch if record_id in plan_by_id]
                outcome.merge(PostBaselineRetrievalOutcome.from_failed_plans(batch_plans))
                log_event(
                    "retrieval.post_baseline_unavailable",
                    record_count=len(batch),
                    purposes=sorted({plan.purpose.value for plan in batch_plans}),
                )
                break
            budget.record_additional_reads(batch)
            for record in read_envelope.data.records:
                read_map[record.record_id] = record
        return outcome

    async def _model_phase(
        self,
        *,
        body: ProfileRequest,
        read_map: dict[str, ClinicalRecord],
        inventory: list[InventoryRecord],
        inventory_complete: bool,
        inventory_empty: bool,
        budget: RunBudget,
        cancel_event: asyncio.Event | None,
        gateway: RecordsGateway,
        baseline_ids: set[str],
    ) -> tuple[Profile, PostBaselineRetrievalOutcome]:
        """Run bounded model generation."""
        profile: Profile | None = None
        adaptive_outcome = PostBaselineRetrievalOutcome()
        inventory_ids = {item.record_id for item in inventory}
        while budget.can_model_call():
            if cancel_event and cancel_event.is_set():
                raise AppError("cancelled", "Run cancelled", 499)
            with span("model.call", index=budget.model_calls):
                result = await self._model.generate_profile(
                    patient_id=body.patient_id,
                    visit_context=body.visit_context,
                    as_of=body.as_of.isoformat(),
                    records=read_map,
                    inventory=inventory,
                    inventory_complete=inventory_complete,
                    inventory_empty=inventory_empty,
                    call_index=budget.model_calls,
                    budget_exhausted=False,
                )
            budget.record_model_call()
            requested = [
                record_id
                for record_id in result.requested_record_ids
                if record_id in inventory_ids
                and record_id not in baseline_ids
                and record_id not in read_map
            ]
            if requested:
                phase_outcome = await self._read_post_baseline_records(
                    gateway,
                    plans=adaptive_supplemental_plans(requested),
                    read_map=read_map,
                    budget=budget,
                    cancel_event=cancel_event,
                )
                adaptive_outcome.merge(phase_outcome)
            if result.profile is not None:
                profile = result.profile
            if result.complete:
                break
        if profile is None:
            raise AppError("model_failed", "Model did not return a profile", 503)
        return profile, adaptive_outcome

    def _records_server(self):
        """Return the records server config."""
        for server in self._registry.servers:
            if server.id == "records" and server.enabled:
                return server
        raise AppError("records_server_missing", "Records MCP server unavailable", 503)
