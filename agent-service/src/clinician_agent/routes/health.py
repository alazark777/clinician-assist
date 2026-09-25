"""Health endpoints."""

from fastapi import APIRouter, Request

from clinician_agent.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(status="ok", dependencies={"process": "ok"})


@router.get("/health/ready", response_model=HealthResponse)
async def ready(request: Request) -> HealthResponse:
    """Readiness with dependency checks."""
    db = request.app.state.db
    dependencies: dict[str, str] = {}
    try:
        await db.count_active_runs()
        dependencies["database"] = "ok"
    except Exception:  # noqa: BLE001
        dependencies["database"] = "unavailable"
    status = "ok" if dependencies.get("database") == "ok" else "degraded"
    return HealthResponse(status=status, dependencies=dependencies)  # type: ignore[arg-type]
