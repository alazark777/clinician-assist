"""Profile generation and feedback routes."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from clinician_agent.auth.deps import get_caller, require_patient_access
from clinician_agent.auth.models import CallerContext
from clinician_agent.coordinator import ProfileCoordinator
from clinician_agent.db import Database
from clinician_agent.errors import AppError, conflict, forbidden, not_found, service_unavailable
from clinician_agent.runtime import RunScheduler
from clinician_agent.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    ProfileRequest,
    ProfileResponse,
    RunStatus,
    RunningResponse,
)
from clinician_agent.util import canonical_input_hash, new_id, trace_id as new_trace_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["profiles"])


@router.post("/profiles")
async def create_profile(
    request: Request,
    body: ProfileRequest,
    caller: CallerContext = Depends(get_caller),
) -> Response:
    """Start or replay profile generation."""
    require_patient_access(caller, body.patient_id)
    db: Database = request.app.state.db
    scheduler: RunScheduler = request.app.state.scheduler
    coordinator: ProfileCoordinator = request.app.state.coordinator

    input_hash = canonical_input_hash(body)
    existing = await db.get_run_by_request(caller.caller_id, body.request_id)
    if existing is not None:
        return await _replay_existing(db, existing, input_hash=input_hash, caller=caller)

    active = await db.count_active_runs()
    if not scheduler.can_start(active):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "overloaded", "message": "Too many active runs"},
        )

    run_id = new_id("run")
    trace = new_trace_id()
    try:
        row, outcome = await db.claim_run(
            run_id=run_id,
            caller_id=caller.caller_id,
            request_id=body.request_id,
            input_hash=input_hash,
            body=body,
            trace_id=trace,
        )
    except Exception as exc:  # noqa: BLE001
        raise service_unavailable("persistence_failed", "Unable to persist run") from exc

    if outcome == "existing" and row is not None:
        return await _replay_existing(db, row, input_hash=input_hash, caller=caller)

    assert row is not None
    cancel_event = asyncio.Event()
    try:
        result = await coordinator.generate(
            run_id=row.run_id,
            caller_id=caller.caller_id,
            body=body,
            trace_id=row.trace_id,
            cancel_event=cancel_event,
            gateway=request.app.state.test_gateway,
        )
    except AppError as exc:
        await db.fail_run(run_id=row.run_id, error_code=exc.code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": str(exc)},
        )

    profile_row = await db.get_profile(result.profile_id)
    assert profile_row is not None
    payload = db.to_profile_response(profile_row, trace_id=row.trace_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content=payload.model_dump(mode="json"))


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    request: Request,
    caller: CallerContext = Depends(get_caller),
) -> ProfileResponse:
    """Return a saved profile when authorized."""
    db: Database = request.app.state.db
    row = await db.get_profile(profile_id)
    if row is None or row.caller_id != caller.caller_id:
        raise not_found()
    require_patient_access(caller, row.patient_id)
    run = await db.get_run(row.run_id)
    trace = run.trace_id if run else new_trace_id()
    return db.to_profile_response(row, trace_id=trace)


@router.post("/profiles/{profile_id}/feedback", response_model=FeedbackResponse)
async def post_feedback(
    profile_id: str,
    body: FeedbackRequest,
    request: Request,
    caller: CallerContext = Depends(get_caller),
) -> FeedbackResponse:
    """Apply version-bound review feedback."""
    db: Database = request.app.state.db
    row = await db.get_profile(profile_id)
    if row is None or row.caller_id != caller.caller_id:
        raise not_found()
    require_patient_access(caller, row.patient_id)
    try:
        updated = await db.apply_feedback(
            profile_id=profile_id,
            expected_profile_version=body.profile_version,
            expected_review_revision=body.review_revision,
            decision=body.decision,
            actor=caller.caller_id,
            comment=body.comment,
        )
    except ValueError as exc:
        raise conflict("version_conflict", str(exc)) from exc
    review_status = updated.review_status
    if review_status not in {"accepted", "needs_correction"}:
        raise conflict("review_state_invalid", "Unexpected review status")
    return FeedbackResponse(
        profile_id=updated.profile_id,
        profile_version=updated.profile_version,
        review_status=review_status,  # type: ignore[arg-type]
        review_revision=updated.review_revision,
    )


async def _replay_existing(db: Database, existing, *, input_hash: str, caller: CallerContext) -> Response:
    """Handle idempotent replay for an existing run."""
    if existing.input_hash != input_hash:
        raise conflict("input_conflict", "request_id reused with different input")
    require_patient_access(caller, existing.patient_id)
    if existing.run_status == RunStatus.COMPLETED and existing.profile_id:
        row = await db.get_profile(existing.profile_id)
        assert row is not None
        payload = db.to_profile_response(row, trace_id=existing.trace_id)
        return JSONResponse(status_code=status.HTTP_200_OK, content=payload.model_dump(mode="json"))
    if existing.run_status == RunStatus.FAILED:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "run_id": existing.run_id,
                "run_status": existing.run_status.value,
                "profile_id": existing.profile_id,
                "error_code": existing.error_code,
            },
        )
    if existing.run_status == RunStatus.INTERRUPTED:
        raise conflict("run_interrupted", "Run interrupted; start a new request_id")
    running = RunningResponse(run_id=existing.run_id)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=running.model_dump(mode="json"),
        headers={"Location": f"/v1/runs/{existing.run_id}"},
    )
