"""Demo session routes."""

from fastapi import APIRouter, Header, Request, Response, status

from clinician_agent.auth.deps import require_local_profile, validate_origin
from clinician_agent.auth.sessions import SESSION_COOKIE, SessionStore
from clinician_agent.errors import forbidden, unprocessable
from clinician_agent.schemas import DemoLogin
from clinician_agent.settings import Settings

router = APIRouter(prefix="/v1/demo", tags=["demo"])


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
async def create_demo_session(
    request: Request,
    body: DemoLogin,
    response: Response,
    origin: str | None = Header(default=None),
) -> None:
    """Create a local demo session cookie."""
    settings: Settings = request.app.state.settings
    require_local_profile(settings)
    validate_origin(settings, origin)
    store: SessionStore = request.app.state.session_store
    try:
        session_id, _ = store.login(body)
    except ValueError as exc:
        raise forbidden("invalid_credentials", "Invalid username or passphrase") from exc
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_demo_session(
    request: Request,
    response: Response,
    origin: str | None = Header(default=None),
) -> None:
    """Clear the demo session cookie."""
    settings: Settings = request.app.state.settings
    require_local_profile(settings)
    validate_origin(settings, origin)
    store: SessionStore = request.app.state.session_store
    session_id = request.cookies.get(SESSION_COOKIE)
    store.logout(session_id)
    response.delete_cookie(SESSION_COOKIE, path="/")
