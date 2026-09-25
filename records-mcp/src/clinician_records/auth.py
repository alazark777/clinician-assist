"""JWT verification and request-scoped patient authorization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier

from clinician_records.settings import Settings

logger = logging.getLogger(__name__)

PATIENT_ID_CLAIM = "patient_id"
ALLOWED_ALGORITHMS = ("RS256",)


class AuthenticationError(Exception):
    """Raised when bearer authentication cannot be established."""


@dataclass(frozen=True)
class VerifiedPatientScope:
    """Patient scope derived from a verified token."""

    patient_id: str


class JwtTokenVerifier(TokenVerifier):
    """Verify development JWTs using configured issuer, audience, and key material."""

    def __init__(self, settings: Settings) -> None:
        """Load verification key and validation policy."""
        self._issuer = settings.mcp_token_issuer
        self._audience = settings.mcp_token_audience
        key_path = settings.mcp_verification_key_path
        try:
            self._public_key = key_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Unable to read MCP verification key at {key_path}") from exc

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate a bearer JWT and map it to MCP access metadata."""
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=list(ALLOWED_ALGORITHMS),
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iss", "aud"]},
            )
        except InvalidTokenError:
            logger.info("Bearer token rejected during verification")
            return None

        patient_id = claims.get(PATIENT_ID_CLAIM)
        if not isinstance(patient_id, str) or not patient_id:
            logger.info("Bearer token missing patient scope claim")
            return None

        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id", "clinician-agent-api")),
            scopes=[],
            expires_at=int(claims["exp"]) if "exp" in claims else None,
            resource=self._audience,
            subject=str(claims.get("sub")) if claims.get("sub") is not None else None,
            claims=dict(claims),
        )


def patient_scope_from_context() -> VerifiedPatientScope:
    """Resolve authorized patient scope from verified request context."""
    access = get_access_token()
    if access is None or not access.claims:
        raise AuthenticationError("missing authenticated access token")
    patient_id = access.claims.get(PATIENT_ID_CLAIM)
    if not isinstance(patient_id, str) or not patient_id:
        raise AuthenticationError("token missing patient scope")
    return VerifiedPatientScope(patient_id=patient_id)


def load_verification_key(path: Path) -> str:
    """Read PEM verification material for tests and tooling."""
    return path.read_text(encoding="utf-8")
