"""Detect real-model configuration for Stage C (evaluator-owned)."""

from __future__ import annotations

import os
from typing import Any

# Documented for reports; the agent runtime applies this URL for ``google`` backend.
GOOGLE_OPENAI_COMPAT_BASE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/openai/"
)

REAL_MODEL_BACKENDS = frozenset({"google", "openai", "custom"})


def _valid_model_id() -> bool:
    model_id = os.environ.get("MODEL_ID")
    return bool(model_id and model_id != "offline-stub")


def _explicit_backend() -> str | None:
    return os.environ.get("MODEL_BACKEND")


def _credentials_satisfied(backend: str) -> bool:
    if backend == "google":
        return bool(os.environ.get("GOOGLE_API_KEY"))
    if backend == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if backend == "custom":
        return bool(os.environ.get("MODEL_API_KEY") and os.environ.get("MODEL_BASE_URL"))
    return False


def real_model_configured() -> bool:
    """Return True when dev real-model repetitions may run.

    Requires explicit ``MODEL_BACKEND`` in ``google``, ``openai``, or ``custom``,
    a non-stub ``MODEL_ID``, and provider-specific credentials. Never infers
    backend from keys alone (e.g. ``OPENAI_API_KEY`` without ``MODEL_BACKEND``).
    """
    backend = _explicit_backend()
    if backend is None or backend == "stub":
        return False
    if backend not in REAL_MODEL_BACKENDS:
        return False
    if not _valid_model_id():
        return False
    return _credentials_satisfied(backend)


def real_model_skip_reason() -> str:
    """Human-readable skip reason when ``real_model_configured()`` is False."""
    backend = _explicit_backend()
    if backend is None:
        return (
            "MODEL_BACKEND not set (required: google, openai, or custom with "
            "matching credentials and non-stub MODEL_ID)"
        )
    if backend == "stub":
        return "MODEL_BACKEND=stub; real-model suite not run"
    if backend not in REAL_MODEL_BACKENDS:
        return f"MODEL_BACKEND={backend!r} is not a real-model backend"
    if not _valid_model_id():
        return "MODEL_ID missing or offline-stub"
    if backend == "google" and not os.environ.get("GOOGLE_API_KEY"):
        return "GOOGLE_API_KEY required for MODEL_BACKEND=google"
    if backend == "openai" and not os.environ.get("OPENAI_API_KEY"):
        return "OPENAI_API_KEY required for MODEL_BACKEND=openai"
    if backend == "custom":
        missing: list[str] = []
        if not os.environ.get("MODEL_API_KEY"):
            missing.append("MODEL_API_KEY")
        if not os.environ.get("MODEL_BASE_URL"):
            missing.append("MODEL_BASE_URL")
        if missing:
            return f"{', '.join(missing)} required for MODEL_BACKEND=custom"
    return "real-model configuration incomplete"


def credential_presence() -> dict[str, bool]:
    """Report which credential env vars are set (never values)."""
    return {
        "google_api_key": bool(os.environ.get("GOOGLE_API_KEY")),
        "openai_api_key": bool(os.environ.get("OPENAI_API_KEY")),
        "model_api_key": bool(os.environ.get("MODEL_API_KEY")),
        "model_base_url": bool(os.environ.get("MODEL_BASE_URL")),
        "openai_base_url": bool(os.environ.get("OPENAI_BASE_URL")),
    }


def real_model_report_metadata(*, status: str) -> dict[str, Any]:
    """Safe ``real_model`` block fields for Stage C reports."""
    backend = _explicit_backend()
    meta: dict[str, Any] = {
        "status": status,
        "model_backend": backend,
        "model_id": os.environ.get("MODEL_ID"),
        "credentials_present": credential_presence(),
    }
    if backend == "google":
        meta["google_base_url"] = GOOGLE_OPENAI_COMPAT_BASE_URL
    openai_base = os.environ.get("OPENAI_BASE_URL")
    if openai_base:
        meta["openai_base_url"] = openai_base
    return meta


def apply_agent_model_env(agent_env: dict[str, str]) -> None:
    """Forward provider credentials into agent subprocess env (in place).

    Uses ``EVAL_MODEL_BACKEND`` when set (real-model restart). Otherwise forces
    ``stub`` so shell ``MODEL_BACKEND`` does not affect the default stub suite.
    """
    backend = os.environ.get("EVAL_MODEL_BACKEND", "stub")
    agent_env["MODEL_BACKEND"] = backend
    model_id = os.environ.get("MODEL_ID")
    if model_id:
        agent_env["MODEL_ID"] = model_id

    if backend == "google":
        key = os.environ.get("GOOGLE_API_KEY")
        if key:
            agent_env["GOOGLE_API_KEY"] = key
    elif backend == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            agent_env["OPENAI_API_KEY"] = key
        base = os.environ.get("OPENAI_BASE_URL")
        if base:
            agent_env["OPENAI_BASE_URL"] = base
    elif backend == "custom":
        key = os.environ.get("MODEL_API_KEY")
        base = os.environ.get("MODEL_BASE_URL")
        if key:
            agent_env["MODEL_API_KEY"] = key
        if base:
            agent_env["MODEL_BASE_URL"] = base


def openai_compatible_configured() -> bool:
    """Deprecated alias; use ``real_model_configured``."""
    return real_model_configured()
