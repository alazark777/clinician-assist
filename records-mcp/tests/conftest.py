"""Shared fixtures for records MCP tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from clinician_records.settings import Settings

ISSUER = "clinician-agent-api"
AUDIENCE = "clinician-records-mcp"
ORIGIN = "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[str, str]:
    """Generate an ephemeral RSA key pair for JWT tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


@pytest.fixture
def verification_key_path(tmp_path: Path, rsa_keypair: tuple[str, str]) -> Path:
    """Write the public verification key to a temporary path."""
    _, public_pem = rsa_keypair
    path = tmp_path / "mcp-verification-key.pem"
    path.write_text(public_pem, encoding="utf-8")
    return path


def mint_token(
    private_pem: str,
    *,
    patient_id: str,
    audience: str = AUDIENCE,
    issuer: str = ISSUER,
    expires_in: timedelta = timedelta(minutes=5),
) -> str:
    """Mint a development JWT for MCP requests."""
    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer,
        "aud": audience,
        "patient_id": patient_id,
        "client_id": "clinician-agent-api",
        "sub": "demo-session",
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")


@pytest.fixture
def patient_data_dir() -> Path:
    """Return the bundled synthetic patient fixtures."""
    return Path(__file__).resolve().parents[1] / "data" / "patients"


@pytest.fixture
def settings(verification_key_path: Path, patient_data_dir: Path) -> Settings:
    """Build test settings pointing at bundled fixtures."""
    return Settings(
        patient_data_dir=patient_data_dir,
        mcp_verification_key_path=verification_key_path,
        mcp_token_issuer=ISSUER,
        mcp_token_audience=AUDIENCE,
        mcp_allowed_origins=(ORIGIN,),
        host="127.0.0.1",
        port=8765,
        otel_exporter_otlp_endpoint=None,
        enable_extension_tools=True,
        mcp_request_state_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )


@pytest.fixture
def auth_headers(rsa_keypair: tuple[str, str]) -> dict[str, str]:
    """Return default authorized request headers for P001."""
    private_pem, _ = rsa_keypair
    token = mint_token(private_pem, patient_id="P001")
    return {
        "Authorization": f"Bearer {token}",
        "Origin": ORIGIN,
    }
