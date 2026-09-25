"""Patient-scoped MCP bearer tokens."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

logger = logging.getLogger(__name__)

TOKEN_TTL = timedelta(minutes=5)
JWT_ALGORITHM = "RS256"


def generate_rsa_signing_key_pem() -> str:
    """Create a development RSA private key PEM for MCP token signing."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


class McpTokenIssuer:
    """Sign short-lived audience-bound JWTs for MCP servers."""

    def __init__(self, *, key_path: Path, issuer: str) -> None:
        """Load signing material."""
        self._issuer = issuer
        self._private_key = key_path.read_text(encoding="utf-8")

    def issue(self, *, patient_id: str, audience: str) -> str:
        """Create a patient-scoped token."""
        now = datetime.now(tz=UTC)
        payload = {
            "iss": self._issuer,
            "aud": audience,
            "sub": patient_id,
            "iat": int(now.timestamp()),
            "exp": int((now + TOKEN_TTL).timestamp()),
            "patient_id": patient_id,
        }
        return jwt.encode(payload, self._private_key, algorithm=JWT_ALGORITHM)
