"""Patient catalog routes."""

from fastapi import APIRouter, Depends

from clinician_agent.auth.deps import get_caller
from clinician_agent.auth.models import CallerContext
from clinician_agent.schemas import PatientSummary

router = APIRouter(prefix="/v1", tags=["patients"])


@router.get("/patients", response_model=list[PatientSummary])
async def list_patients(caller: CallerContext = Depends(get_caller)) -> list[PatientSummary]:
    """Return authorized patient catalog entries."""
    return list(caller.allowed_patients)
