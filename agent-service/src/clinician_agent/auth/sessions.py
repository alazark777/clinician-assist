"""Opaque demo session management."""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from clinician_agent.auth.models import CallerContext, DemoSessionsFile
from clinician_agent.schemas import DemoLogin, PatientSummary

logger = logging.getLogger(__name__)

SESSION_COOKIE = "clinician_session"
SESSION_TTL = timedelta(hours=8)


@dataclass
class SessionStore:
    """In-memory session index backed by SQLite demo_sessions table hooks."""

    demo_config_path: Path
    _sessions: dict[str, tuple[str, datetime, tuple[PatientSummary, ...]]]

    @classmethod
    def create(cls, demo_config_path: Path) -> "SessionStore":
        """Create an empty session store."""
        return cls(demo_config_path=demo_config_path, _sessions={})

    def _load_config(self) -> DemoSessionsFile:
        """Load demo users from secrets."""
        raw = json.loads(self.demo_config_path.read_text(encoding="utf-8"))
        return DemoSessionsFile.model_validate(raw)

    def login(self, body: DemoLogin) -> tuple[str, CallerContext]:
        """Validate credentials and issue an opaque session identifier."""
        config = self._load_config()
        for user in config.users:
            if user.username == body.username and user.passphrase == body.passphrase:
                session_id = secrets.token_urlsafe(32)
                expires = datetime.now(tz=UTC) + SESSION_TTL
                patients = tuple(user.patients)
                self._sessions[session_id] = (user.caller_id, expires, patients)
                return session_id, CallerContext(caller_id=user.caller_id, allowed_patients=patients)
        raise ValueError("invalid_credentials")

    def logout(self, session_id: str | None) -> None:
        """Remove a session."""
        if session_id:
            self._sessions.pop(session_id, None)

    def resolve(self, session_id: str | None) -> CallerContext | None:
        """Resolve an opaque session to caller permissions."""
        if not session_id:
            return None
        entry = self._sessions.get(session_id)
        if entry is None:
            return None
        caller_id, expires, patients = entry
        if datetime.now(tz=UTC) >= expires:
            self._sessions.pop(session_id, None)
            return None
        return CallerContext(caller_id=caller_id, allowed_patients=patients)
