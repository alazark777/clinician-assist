"""Shared-file MCP tool trace collection (cross-process)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

QUALIFIED_PREFIX = "records__"
DEFAULT_TRACE_PATH = Path(__file__).resolve().parents[1] / "var" / "evaluation" / "tool_trace.jsonl"


def trace_path() -> Path:
    raw = os.environ.get("EVAL_TRACE_FILE")
    return Path(raw) if raw else DEFAULT_TRACE_PATH


class TraceStore:
    """Append-only JSONL trace shared between MCP and harness."""

    def clear(self) -> None:
        """Drop accumulated calls."""
        path = trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def append(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        patient_id: str,
        status: str,
        returned_record_ids: list[str],
    ) -> None:
        """Record one MCP tool invocation."""
        qualified = tool if tool.startswith("records__") else f"{QUALIFIED_PREFIX}{tool}"
        entry = {
            "tool": qualified,
            "arguments": arguments,
            "patient_id": patient_id,
            "status": status,
            "returned_record_ids": sorted(set(returned_record_ids)),
        }
        path = trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def snapshot(self, *, patient_id: str | None = None) -> list[dict[str, Any]]:
        """Return trace entries, optionally filtered by patient."""
        path = trace_path()
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if patient_id is None or row.get("patient_id") == patient_id:
                rows.append(row)
        return rows

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")


TRACE_STORE = TraceStore()
