#!/usr/bin/env python3
"""Synthetic sentinel check for source-side redaction helpers."""

from __future__ import annotations

import json
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib"
REDACTION_PATH = LIB / "clinician_observability" / "redaction.py"


def _load_redaction_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("clinician_redaction", REDACTION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load redaction module from {REDACTION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_redaction = _load_redaction_module()
assert_redaction_sentinels_absent = _redaction.assert_redaction_sentinels_absent
scrub_mapping = _redaction.scrub_mapping
scrub_text = _redaction.scrub_text
strip_url_query = _redaction.strip_url_query

SENTINELS = (
    "P001",
    "Bearer secret-token-abc",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig",
    "HbA1c=9.2",
    "patient prompt injection",
)


def main() -> int:
    """Run redaction checks and print JSON evidence."""
    raw = {
        "patient_id": "P001",
        "prompt": "patient prompt injection",
        "http.url": "http://127.0.0.1:8001/mcp?patient=P001&token=abc",
        "nested": {"tool_result": "HbA1c=9.2"},
    }
    cleaned = scrub_mapping(raw)
    blob = json.dumps(cleaned)
    leaks = assert_redaction_sentinels_absent(blob, SENTINELS)
    scrubbed_line = scrub_text(" ".join(SENTINELS))
    leaks.extend(assert_redaction_sentinels_absent(scrubbed_line, ("P001", "Bearer secret-token-abc")))
    url = strip_url_query(str(raw["http.url"]))
    result = {
        "status": "pass" if not leaks else "fail",
        "leaked_sentinels": leaks,
        "sample_url": url,
        "keys_removed": sorted(set(raw) - set(cleaned)),
    }
    print(json.dumps(result, indent=2))
    return 0 if not leaks else 1


if __name__ == "__main__":
    raise SystemExit(main())
