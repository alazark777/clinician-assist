"""Evaluator-owned records MCP with out-of-band faults and tool tracing.

Run with records-mcp on PYTHONPATH. Does not modify runtime application code.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORDS_SRC = REPO_ROOT / "records-mcp" / "src"
if str(RECORDS_SRC) not in sys.path:
    sys.path.insert(0, str(RECORDS_SRC))

HARNESS_ROOT = Path(__file__).resolve().parent
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from clinician_records.auth import AuthenticationError, patient_scope_from_context  # noqa: E402
from clinician_records.models import (  # noqa: E402
    InventoryData,
    ListRecordsInput,
    ReadData,
    ReadRecordsInput,
    RecordType,
    ToolEnvelope,
    ToolError,
)
from clinician_records.repository import RecordRepository  # noqa: E402
from clinician_records.server import create_server  # noqa: E402
from clinician_records.settings import Settings  # noqa: E402
from clinician_records.telemetry import configure_observability  # noqa: E402
from clinician_records.tools import READ_ONLY_ANNOTATIONS, RecordsToolService  # noqa: E402

from faults import FaultState, load_fault_file  # noqa: E402
from trace_store import TRACE_STORE  # noqa: E402

logger = logging.getLogger(__name__)

FAULT_FILE = Path(os.environ.get("EVAL_FAULT_FILE", REPO_ROOT / "evaluation/var/evaluation/active_faults.json"))
FAULT_STATE = FaultState()
_FAULT_DIGEST: str | None = None


def _reload_faults() -> None:
    """Reload fault plan when the evaluator updates the active case file."""
    global _FAULT_DIGEST
    faults = load_fault_file(FAULT_FILE)
    digest = json.dumps(faults, sort_keys=True)
    if digest != _FAULT_DIGEST:
        FAULT_STATE.reset(faults)
        _FAULT_DIGEST = digest
    else:
        FAULT_STATE.sync_faults(faults)


class InstrumentedToolService(RecordsToolService):
    """Records tools with evaluator fault injection and tracing."""

    async def list_records(self, args: ListRecordsInput) -> ToolEnvelope:
        _reload_faults()
        try:
            scope = patient_scope_from_context()
        except AuthenticationError:
            raise
        effect = FAULT_STATE.list_effect()
        if effect == "unavailable":
            envelope = ToolEnvelope.model_validate(
                {
                    "status": "unavailable",
                    "patient_id": scope.patient_id,
                    "dataset_version": "eval",
                    "data": None,
                    "error": {"code": "record_unavailable", "retryable": True},
                }
            )
        elif effect == "denied":
            envelope = ToolEnvelope.model_validate(
                {
                    "status": "denied",
                    "patient_id": scope.patient_id,
                    "dataset_version": "eval",
                    "data": None,
                    "error": {"code": "record_not_accessible", "retryable": False},
                }
            )
        else:
            envelope = await super().list_records(args)
        TRACE_STORE.append(
            tool="list_records",
            arguments=args.model_dump(mode="json", exclude_none=True),
            patient_id=scope.patient_id,
            status=envelope.status,
            returned_record_ids=[],
        )
        return envelope

    async def read_records(self, args: ReadRecordsInput) -> ToolEnvelope:
        _reload_faults()
        try:
            scope = patient_scope_from_context()
        except AuthenticationError:
            raise
        effect = FAULT_STATE.read_effect(list(args.record_ids))
        if effect == "unavailable":
            envelope = ToolEnvelope.model_validate(
                {
                    "status": "unavailable",
                    "patient_id": scope.patient_id,
                    "dataset_version": "eval",
                    "data": None,
                    "error": {"code": "record_unavailable", "retryable": True},
                }
            )
        elif effect == "denied":
            envelope = ToolEnvelope.model_validate(
                {
                    "status": "denied",
                    "patient_id": scope.patient_id,
                    "dataset_version": "eval",
                    "data": None,
                    "error": {"code": "record_not_accessible", "retryable": False},
                }
            )
        else:
            repo_fault_ids = os.environ.get("EVAL_REPO_FAULT_IDS", "")
            repository: RecordRepository = self._repository  # type: ignore[attr-defined]
            for rid in [part.strip() for part in repo_fault_ids.split(",") if part.strip()]:
                if rid in args.record_ids:
                    repository.mark_record_unavailable(rid)
            envelope = await super().read_records(args)
        returned: list[str] = []
        if envelope.status == "ok" and isinstance(envelope.data, ReadData):
            returned = [record.record_id for record in envelope.data.records]
        TRACE_STORE.append(
            tool="read_records",
            arguments=args.model_dump(mode="json"),
            patient_id=scope.patient_id,
            status=envelope.status,
            returned_record_ids=returned,
        )
        return envelope


def create_instrumented_server(settings: Settings):
    """Build MCP server wired to instrumented tool handlers."""
    repository = RecordRepository(settings.patient_data_dir)
    tool_service = InstrumentedToolService(repository)
    schemas_path = REPO_ROOT / "records-mcp" / "schemas" / "record_tools.json"
    schemas = {tool["name"]: tool for tool in json.loads(schemas_path.read_text(encoding="utf-8"))["tools"]}

    from contextlib import asynccontextmanager

    from clinician_records.auth import JwtTokenVerifier
    from mcp.server.auth.settings import AuthSettings
    from mcp.server.mcpserver import MCPServer
    from mcp.server.request_state import RequestStateSecurity

    token_verifier = JwtTokenVerifier(settings)

    @asynccontextmanager
    async def lifespan(server: MCPServer[RecordRepository]):
        yield repository

    if settings.mcp_request_state_key:
        request_state_security = RequestStateSecurity(
            keys=[settings.mcp_request_state_key],
            audience=settings.mcp_token_audience,
        )
    else:
        request_state_security = RequestStateSecurity.ephemeral()

    server = MCPServer[RecordRepository](
        name=settings.mcp_token_audience,
        version="0.1.0-eval",
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=settings.mcp_auth_issuer_url,
            resource_server_url=settings.mcp_resource_server_url,
            validate_token_resource=False,
        ),
        request_state_security=request_state_security,
        lifespan=lifespan,
    )

    list_schema = schemas["list_records"]
    read_schema = schemas["read_records"]

    @server.tool(
        name="list_records",
        description=str(list_schema["description"]),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def list_records(
        record_types: list[RecordType] | None = None,
        before: date | None = None,
    ) -> ToolEnvelope:
        parsed = ListRecordsInput(record_types=record_types, before=before)
        return await tool_service.list_records(parsed)

    @server.tool(
        name="read_records",
        description=str(read_schema["description"]),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    async def read_records(record_ids: list[str]) -> ToolEnvelope:
        parsed = ReadRecordsInput(record_ids=record_ids)
        return await tool_service.read_records(parsed)

    if settings.enable_extension_tools:

        @server.tool(
            name="get_record_counts",
            description="Test-only extension: return per-type record counts for the scoped patient.",
            annotations=READ_ONLY_ANNOTATIONS,
            structured_output=True,
        )
        async def get_record_counts() -> dict[str, Any]:
            return await tool_service.get_record_counts()

    return server


def main() -> None:
    """Start instrumented MCP for Stage C."""
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    port = int(os.environ.get("MCP_PORT", "8010"))
    settings = settings.model_copy(
        update={
            "port": port,
            "mcp_resource_server_url": f"http://127.0.0.1:{port}/mcp",
            "patient_data_dir": Path(
                os.environ.get(
                    "PATIENT_DATA_DIR",
                    str(REPO_ROOT / "records-mcp" / "data" / "patients"),
                )
            ),
            "enable_extension_tools": os.environ.get("ENABLE_EXTENSION_TOOLS", "").lower()
            in {"1", "true", "yes"},
        }
    )
    configure_observability(settings)
    server = create_instrumented_server(settings)
    logger.info("Instrumented eval MCP listening on %s:%s", settings.host, settings.port)
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
