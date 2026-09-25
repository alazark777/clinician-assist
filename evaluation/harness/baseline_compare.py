"""Compare deterministic baseline reads vs adaptive tool trace."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_SRC = REPO_ROOT / "agent-service" / "src"
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from clinician_agent.mcp.models import InventoryRecord, RecordType  # noqa: E402
from clinician_agent.retrieval.baseline import select_baseline_ids  # noqa: E402


def baseline_ids_from_trace(tool_calls: list[dict[str, Any]]) -> set[str]:
    """Collect record IDs returned on successful reads."""
    read: set[str] = set()
    for call in tool_calls:
        if call.get("tool") != "records__read_records" or call.get("status") != "ok":
            continue
        read.update(call.get("returned_record_ids") or [])
    return read


def compare_baseline_adaptive(
    *,
    patient_fixture: Path,
    as_of: date,
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Report fixed baseline set vs actual reads (adaptive delta)."""
    import json

    patient = json.loads(patient_fixture.read_text(encoding="utf-8"))
    inventory: list[InventoryRecord] = []
    for record in patient["records"]:
        effective = record.get("event_date") or record["recorded_at"]
        eff_date = date.fromisoformat(effective) if isinstance(effective, str) else effective
        if eff_date > as_of:
            continue
        fact_keys = sorted({fact["key"] for fact in record["content"]["facts"]})
        inventory.append(
            InventoryRecord(
                record_id=record["record_id"],
                record_type=RecordType(record["record_type"]),
                recorded_at=date.fromisoformat(record["recorded_at"]),
                event_date=date.fromisoformat(record["event_date"]) if record.get("event_date") else None,
                version=int(record["version"]),
                fact_keys=fact_keys,
            )
        )
    expected_baseline = set(select_baseline_ids(inventory))
    actual_reads = baseline_ids_from_trace(tool_calls)
    additional = actual_reads - expected_baseline
    missing_baseline = expected_baseline - actual_reads
    return {
        "expected_baseline_ids": sorted(expected_baseline),
        "actual_read_ids": sorted(actual_reads),
        "additional_adaptive_reads": sorted(additional),
        "missing_baseline_reads": sorted(missing_baseline),
        "baseline_only": not additional,
    }
