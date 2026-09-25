"""Fixtures for live records MCP integration tests."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KIT_ROOT = Path(__file__).resolve().parents[2]
RECORDS_MCP_ROOT = KIT_ROOT / "records-mcp"
PATIENT_DATA_DIR = RECORDS_MCP_ROOT / "data" / "patients"


def _free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def write_rsa_keypair(private_path: Path, public_path: Path) -> None:
    """Write a matching RSA private/public pair for agent signing and records verification."""
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.write_text(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8"),
        encoding="utf-8",
    )
    public_path.write_text(
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8"),
        encoding="utf-8",
    )


def write_registry(path: Path, *, mcp_url: str) -> None:
    """Write a registry document aimed at a live records MCP endpoint."""
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "servers": [
                    {
                        "id": "records",
                        "enabled": True,
                        "url": mcp_url,
                        "transport": "streamable_http",
                        "protocol_version": "2026-07-28",
                        "token_audience": "clinician-records-mcp",
                        "allowed_tools": ["list_records", "read_records"],
                        "approved_schema_file": "record_tools.json",
                        "timeout_seconds": 5,
                        "max_transient_read_retries": 1,
                        "max_result_bytes": 102400,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@contextmanager
def live_records_mcp_process(
    *,
    verification_key_path: Path,
    patient_data_dir: Path,
    host: str = "127.0.0.1",
) -> Iterator[str]:
    """Start records MCP as a subprocess and yield its Streamable HTTP URL."""
    if not RECORDS_MCP_ROOT.is_dir():
        raise RuntimeError(f"records MCP component not found at {RECORDS_MCP_ROOT}")
    if not patient_data_dir.is_dir():
        raise RuntimeError(f"patient fixtures not found at {patient_data_dir}")

    port = _free_port(host)
    env = os.environ.copy()
    env.update(
        {
            "PATIENT_DATA_DIR": str(patient_data_dir),
            "MCP_VERIFICATION_KEY": str(verification_key_path),
            "MCP_TOKEN_ISSUER": "clinician-agent-api",
            "MCP_TOKEN_AUDIENCE": "clinician-records-mcp",
            "MCP_ALLOWED_ORIGINS": "http://127.0.0.1:8000",
            "APP_ENV": "local",
        }
    )
    env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

    process = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "-m",
            "clinician_records",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=RECORDS_MCP_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    url = f"http://{host}:{port}/mcp"
    try:
        deadline = time.time() + 30.0
        while time.time() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr else ""
                raise RuntimeError(f"records MCP exited early: {stderr}")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex((host, port)) == 0:
                    break
            time.sleep(0.1)
        else:
            raise RuntimeError("records MCP did not become reachable in time")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture(scope="module")
def live_records_mcp(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Path | str]]:
    """Module-scoped live records MCP with ephemeral RSA keys."""
    if not PATIENT_DATA_DIR.is_dir():
        pytest.skip("records MCP patient fixtures unavailable")
    base = tmp_path_factory.mktemp("live-records")
    private_key = base / "mcp-signing-key.pem"
    public_key = base / "mcp-verification-key.pem"
    write_rsa_keypair(private_key, public_key)
    with live_records_mcp_process(
        verification_key_path=public_key,
        patient_data_dir=PATIENT_DATA_DIR,
    ) as mcp_url:
        registry_path = base / "mcp_servers.json"
        write_registry(registry_path, mcp_url=mcp_url)
        yield {
            "mcp_url": mcp_url,
            "signing_key_path": private_key,
            "registry_path": registry_path,
        }
