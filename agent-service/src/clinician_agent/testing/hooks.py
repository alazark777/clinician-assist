"""Out-of-band test hooks (never model-visible or public HTTP inputs)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_EXHAUST_EFFECT = "exhaust_budget_after_baseline"


def should_exhaust_model_budget_after_baseline() -> bool:
    """Return whether the active test hook requests post-baseline budget exhaustion."""
    path = os.environ.get("AGENT_TEST_FAULT_FILE")
    if not path:
        return False
    fault_path = Path(path)
    if not fault_path.is_file():
        return False
    try:
        payload = json.loads(fault_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unable to read agent test fault file: %s", exc)
        return False
    faults = payload.get("harness_faults")
    if not isinstance(faults, list):
        return False
    for fault in faults:
        if not isinstance(fault, dict):
            continue
        if fault.get("target") == "model" and fault.get("effect") == _EXHAUST_EFFECT:
            return True
    return False
