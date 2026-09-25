"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from clinician_agent.auth.jwt_tokens import McpTokenIssuer
from clinician_agent.auth.models import DemoSessionsFile, DemoUserConfig
from clinician_agent.auth.sessions import SessionStore
from clinician_agent.coordinator import ProfileCoordinator
from clinician_agent.db import Database
from clinician_agent.errors import AppError, error_body
from clinician_agent.mcp.registry import load_registry
from clinician_agent.model.factory import build_model
from clinician_agent.routes import demo, health, patients, profiles, runs
from clinician_agent.runtime import RunScheduler
from clinician_agent.schemas import PatientSummary
from clinician_agent.settings import Settings
from clinician_agent.telemetry import configure_telemetry, log_event

logger = logging.getLogger(__name__)

_AGENT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Load agent-service/.env into os.environ when keys are not already set."""
    env_path = _AGENT_ROOT / ".env"
    if not env_path.is_file():
        return
    from_file: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key:
            from_file[key] = value
    for key, value in from_file.items():
        if key not in os.environ:
            os.environ[key] = value


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hooks."""
    settings: Settings = app.state.settings
    configure_telemetry(settings)
    db: Database = app.state.db
    await db.connect()
    interrupted = await db.mark_interrupted_runs()
    if interrupted:
        log_event("runs.interrupted_on_startup", count=interrupted)
    yield
    await db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory used by tests and uvicorn."""
    resolved = settings or Settings.from_env()
    _ensure_local_secrets(resolved)
    registry_path = resolved.mcp_registry_path
    if not registry_path.is_absolute():
        registry_path = Path(__file__).resolve().parents[2] / registry_path

    app = FastAPI(title="Clinician Agent API", lifespan=lifespan)
    app.state.settings = resolved
    app.state.db = Database(_resolve_path(resolved.agent_db_path))
    app.state.session_store = SessionStore.create(_resolve_path(resolved.demo_sessions_path))
    app.state.registry = load_registry(registry_path)
    app.state.token_issuer = McpTokenIssuer(
        key_path=_resolve_path(resolved.mcp_signing_key_path),
        issuer=resolved.mcp_token_issuer,
    )
    app.state.model = build_model(resolved)
    app.state.coordinator = ProfileCoordinator(
        settings=resolved,
        db=app.state.db,
        registry=app.state.registry,
        token_issuer=app.state.token_issuer,
        model=app.state.model,
    )
    app.state.scheduler = RunScheduler(max_active=resolved.max_active_runs)
    app.state.test_gateway = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(demo.router)
    app.include_router(patients.router)
    app.include_router(profiles.router)
    app.include_router(runs.router)
    app.include_router(health.router)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        """Map domain errors."""
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, str(exc)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        """Return contracted validation failures."""
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", "Invalid request"),
        )

    return app


def _resolve_path(path: Path) -> Path:
    """Resolve service-relative paths."""
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path


def _ensure_local_secrets(settings: Settings) -> None:
    """Bootstrap ignored local secrets for synthetic demo profile."""
    if settings.app_env != "local":
        return
    demo_path = _resolve_path(settings.demo_sessions_path)
    key_path = _resolve_path(settings.mcp_signing_key_path)
    if not demo_path.exists():
        demo_path.parent.mkdir(parents=True, exist_ok=True)
        demo_path.write_text(
            DemoSessionsFile(
                users=[
                    DemoUserConfig(
                        username="reviewer",
                        passphrase="local-demo",
                        caller_id="local-reviewer",
                        patients=[PatientSummary(patient_id="P001", label="Demo Patient")],
                    )
                ]
            ).model_dump_json(),
            encoding="utf-8",
        )
    if not key_path.exists():
        logger.warning(
            "MCP signing key missing at %s; generate paired RSA material with "
            "scripts/generate_dev_signing_key.sh and records-mcp/scripts/generate_dev_keys.sh, "
            "then set MCP_SIGNING_KEY_PATH to the private key that matches the MCP verification key.",
            key_path,
        )


_load_dotenv()
app = create_app()
