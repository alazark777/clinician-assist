"""Evaluator-owned MCP fault injection state (out-of-band, not model-visible)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

QUALIFIED_PREFIX = "records__"


@dataclass
class FaultState:
    """Mutable fault plan for one case execution."""

    faults: list[dict[str, Any]] = field(default_factory=list)
    list_attempts: int = 0
    read_attempts: int = 0

    def reset(self, faults: list[dict[str, Any]]) -> None:
        """Load harness faults for the next case."""
        self.faults = list(faults)
        self.list_attempts = 0
        self.read_attempts = 0

    def sync_faults(self, faults: list[dict[str, Any]]) -> None:
        """Replace fault definitions without resetting attempt counters."""
        self.faults = list(faults)

    def _attempts_match(self, spec: object, current: int) -> bool:
        if spec == "all":
            return True
        if isinstance(spec, list):
            return current in spec
        return False

    def list_effect(self) -> str | None:
        """Return injected list status if a fault applies."""
        self.list_attempts += 1
        for fault in self.faults:
            tool = fault.get("tool")
            if tool not in {None, f"{QUALIFIED_PREFIX}list_records", "list_records"}:
                continue
            if fault.get("record_ids"):
                continue
            if self._attempts_match(fault.get("attempts", "all"), self.list_attempts):
                effect = fault.get("effect")
                if isinstance(effect, str):
                    logger.info("Injecting list_records fault effect=%s attempt=%s", effect, self.list_attempts)
                    return effect
        return None

    def read_effect(self, record_ids: list[str]) -> str | None:
        """Return injected read status if a fault applies."""
        self.read_attempts += 1
        requested = set(record_ids)
        for fault in self.faults:
            tool = fault.get("tool")
            if tool not in {None, f"{QUALIFIED_PREFIX}read_records", "read_records"}:
                continue
            fault_ids = set(fault.get("record_ids") or [])
            if fault_ids and not (fault_ids & requested):
                continue
            if self._attempts_match(fault.get("attempts", "all"), self.read_attempts):
                effect = fault.get("effect")
                if isinstance(effect, str):
                    logger.info(
                        "Injecting read_records fault effect=%s attempt=%s ids=%s",
                        effect,
                        self.read_attempts,
                        sorted(requested),
                    )
                    return effect
        return None


def load_fault_file(path: Path) -> list[dict[str, Any]]:
    """Read a harness fault JSON document."""
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        faults = payload.get("harness_faults")
        return faults if isinstance(faults, list) else []
    return []


def write_fault_file(path: Path, faults: list[dict[str, Any]]) -> None:
    """Persist faults for the instrumented MCP process."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"harness_faults": faults}, indent=2), encoding="utf-8")
