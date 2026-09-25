"""CLI entrypoint for the records MCP server."""

from __future__ import annotations

import argparse
import logging

from clinician_records.server import create_server
from clinician_records.settings import Settings
from clinician_records.telemetry import configure_observability

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    """Parse command-line overrides for local debugging."""
    parser = argparse.ArgumentParser(description="Clinician records MCP server")
    parser.add_argument("--host", default=None, help="Bind host (default from MCP_HOST or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default from MCP_PORT or 8001)")
    return parser.parse_args()


def main() -> None:
    """Run the Streamable HTTP MCP server."""
    args = _parse_args()
    settings = Settings.from_env()
    overrides: dict[str, object] = {}
    if args.host is not None:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if overrides:
        settings = settings.model_copy(update=overrides)

    configure_observability(settings)
    server = create_server(settings)
    logger.info(
        "Starting Streamable HTTP MCP server",
        extra={"tool": "streamable-http", "status": "starting"},
    )
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
