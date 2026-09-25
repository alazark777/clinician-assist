"""Run polling routes."""

from fastapi import APIRouter, Depends, Request

from clinician_agent.auth.deps import get_caller, require_patient_access
from clinician_agent.auth.models import CallerContext
from clinician_agent.db import Database
from clinician_agent.errors import not_found
from clinician_agent.schemas import RunResponse

router = APIRouter(prefix="/v1", tags=["runs"])


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    request: Request,
    caller: CallerContext = Depends(get_caller),
) -> RunResponse:
    """Poll run lifecycle state."""
    db: Database = request.app.state.db
    row = await db.get_run(run_id)
    if row is None or row.caller_id != caller.caller_id:
        raise not_found()
    require_patient_access(caller, row.patient_id)
    return RunResponse(
        run_id=row.run_id,
        run_status=row.run_status,
        profile_id=row.profile_id,
        error_code=row.error_code,
    )
