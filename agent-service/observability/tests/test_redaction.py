"""Tests for source-side redaction helpers."""

from clinician_observability.redaction import scrub_mapping, scrub_text, strip_url_query


def test_scrub_mapping_drops_sensitive_keys() -> None:
    payload = {
        "patient_id": "P001",
        "tool_arguments": {"record_ids": ["R1"]},
        "status": "ok",
    }
    cleaned = scrub_mapping(payload)
    assert "patient_id" not in cleaned
    assert "tool_arguments" not in cleaned
    assert cleaned["status"] == "ok"


def test_strip_url_query_removes_identifiers() -> None:
    url = "http://127.0.0.1:8001/mcp?patient=P001&token=secret"
    assert strip_url_query(url) == "http://127.0.0.1:8001/mcp"


def test_scrub_text_masks_patient_and_bearer_tokens() -> None:
    line = "scope P001 Bearer secret-token-abc"
    scrubbed = scrub_text(line)
    assert "P001" not in scrubbed
    assert "secret-token-abc" not in scrubbed
