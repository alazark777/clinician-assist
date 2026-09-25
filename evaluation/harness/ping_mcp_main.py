"""Test-only second MCP server exposing an innocuous ping tool."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORDS_SRC = REPO_ROOT / "records-mcp" / "src"
if str(RECORDS_SRC) not in sys.path:
    sys.path.insert(0, str(RECORDS_SRC))

from clinician_records.auth import JwtTokenVerifier  # noqa: E402
from clinician_records.settings import Settings  # noqa: E402
from clinician_records.telemetry import configure_observability  # noqa: E402
from clinician_records.tools import READ_ONLY_ANNOTATIONS  # noqa: E402
from mcp.server.auth.settings import AuthSettings  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.request_state import RequestStateSecurity  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("MCP_PING_PORT", "8012"))
    settings = Settings.from_env().model_copy(
        update={
            "port": port,
            "mcp_token_audience": "clinician-eval-ping-mcp",
            "mcp_resource_server_url": f"http://127.0.0.1:{port}/mcp",
        }
    )
    configure_observability(settings)
    token_verifier = JwtTokenVerifier(settings)
    request_state_security = (
        RequestStateSecurity(keys=[settings.mcp_request_state_key], audience=settings.mcp_token_audience)
        if settings.mcp_request_state_key
        else RequestStateSecurity.ephemeral()
    )
    server = MCPServer(
        name="clinician-eval-ping-mcp",
        version="0.0.1-eval",
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=settings.mcp_auth_issuer_url,
            resource_server_url=settings.mcp_resource_server_url,
            validate_token_resource=False,
        ),
        request_state_security=request_state_security,
    )

    @server.tool(
        name="ping",
        description="Test-only liveness probe for extension proofs.",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def ping() -> dict[str, Any]:
        return {"status": "ok", "message": "pong"}

    logger.info("Eval ping MCP listening on %s:%s", settings.host, settings.port)
    server.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        streamable_http_path=settings.streamable_http_path,
        transport_security=settings.transport_security(),
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
