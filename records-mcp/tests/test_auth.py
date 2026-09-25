"""JWT verification tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from clinician_records.auth import JwtTokenVerifier
from clinician_records.settings import Settings


@pytest.mark.asyncio
async def test_verifier_accepts_valid_token(
    settings: Settings,
    rsa_keypair: tuple[str, str],
) -> None:
    """Valid scoped tokens verify successfully."""
    private_pem, _ = rsa_keypair
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": settings.mcp_token_issuer,
            "aud": settings.mcp_token_audience,
            "patient_id": "P001",
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        private_pem,
        algorithm="RS256",
    )
    verifier = JwtTokenVerifier(settings)
    access = await verifier.verify_token(token)
    assert access is not None
    assert access.claims is not None
    assert access.claims["patient_id"] == "P001"


@pytest.mark.asyncio
async def test_verifier_rejects_expired_token(settings: Settings, rsa_keypair: tuple[str, str]) -> None:
    """Expired tokens are rejected."""
    private_pem, _ = rsa_keypair
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": settings.mcp_token_issuer,
            "aud": settings.mcp_token_audience,
            "patient_id": "P001",
            "exp": int((now - timedelta(minutes=1)).timestamp()),
        },
        private_pem,
        algorithm="RS256",
    )
    verifier = JwtTokenVerifier(settings)
    assert await verifier.verify_token(token) is None
