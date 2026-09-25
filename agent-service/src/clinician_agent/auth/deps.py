"""FastAPI auth dependencies."""

from __future__ import annotations

from fastapi import Cookie, Header, Request

from clinician_agent.auth.models import CallerContext
from clinician_agent.auth.sessions import SESSION_COOKIE, SessionStore
from clinician_agent.errors import forbidden, unprocessable
from clinician_agent.settings import Settings


def require_local_profile(settings: Settings) -> None:
    """Ensure demo routes are only enabled locally."""
    if settings.app_env != "local":
        raise forbidden("demo_disabled", "Demo authentication is disabled")


def validate_origin(settings: Settings, origin: str | None) -> None:
    """Validate CSRF Origin header for state-changing requests."""
    if origin != settings.web_origin:
        raise forbidden("invalid_origin", "Origin not permitted")


async def get_caller(
    request: Request,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> CallerContext:
    """Resolve the authenticated caller from the session cookie."""
    store: SessionStore = request.app.state.session_store
    caller = store.resolve(session_id)
    if caller is None:
        raise forbidden("unauthenticated", "Authentication required")
    return caller


async def get_optional_caller(
    request: Request,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> CallerContext | None:
    """Resolve caller when a session exists."""
    store: SessionStore = request.app.state.session_store
    return store.resolve(session_id)


def require_patient_access(caller: CallerContext, patient_id: str) -> None:
    """Ensure the caller may access a patient."""
    if not caller.can_access_patient(patient_id):
        raise forbidden("patient_forbidden", "Patient access denied")
