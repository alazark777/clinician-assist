"""MCP tool handlers for scoped record inventory and reads."""

from __future__ import annotations

import logging
import time
from typing import Any

from mcp_types import ToolAnnotations

from clinician_records.auth import AuthenticationError, patient_scope_from_context
from clinician_records.models import ListRecordsInput, ReadRecordsInput, ToolEnvelope
from clinician_records.repository import RecordRepository
from clinician_records.telemetry import get_tracer

logger = logging.getLogger(__name__)

READ_ONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True, destructiveHint=False)


class RecordsToolService:
    """Registers typed list/read handlers bound to a scoped repository."""

    def __init__(self, repository: RecordRepository) -> None:
        """Store the repository used for authorized reads."""
        self._repository = repository
        self._tracer = get_tracer()

    async def list_records(self, args: ListRecordsInput) -> ToolEnvelope:
        """List inventory metadata for the verified patient scope."""
        started = time.perf_counter()
        try:
            scope = patient_scope_from_context()
        except AuthenticationError as exc:
            logger.info("list_records denied: %s", exc)
            raise

        with self._tracer.start_as_current_span("records.list") as span:
            span.set_attribute("tool.name", "list_records")
            envelope = self._repository.list_records(scope.patient_id, args)
            span.set_attribute("tool.status", envelope.status)
            if envelope.error is not None:
                span.set_attribute("tool.error_code", envelope.error.code)
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "records list completed",
                extra={
                    "tool": "list_records",
                    "status": envelope.status,
                    "error_code": envelope.error.code if envelope.error else None,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return envelope

    async def read_records(self, args: ReadRecordsInput) -> ToolEnvelope:
        """Read exact record payloads for the verified patient scope."""
        started = time.perf_counter()
        try:
            scope = patient_scope_from_context()
        except AuthenticationError as exc:
            logger.info("read_records denied: %s", exc)
            raise

        with self._tracer.start_as_current_span("records.read") as span:
            span.set_attribute("tool.name", "read_records")
            envelope = self._repository.read_records(scope.patient_id, args)
            span.set_attribute("tool.status", envelope.status)
            if envelope.error is not None:
                span.set_attribute("tool.error_code", envelope.error.code)
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "records read completed",
                extra={
                    "tool": "read_records",
                    "status": envelope.status,
                    "error_code": envelope.error.code if envelope.error else None,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return envelope

    async def get_record_counts(self) -> dict[str, Any]:
        """Optional extension tool for evaluator proofs."""
        scope = patient_scope_from_context()
        counts = self._repository.record_counts(scope.patient_id)
        return {"patient_id": scope.patient_id, "counts": counts}
