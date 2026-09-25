"""Stable span and metric names aligned with the implementation contract."""

from enum import StrEnum


class SpanName(StrEnum):
    """Contracted span identifiers for backend instrumentation."""

    PROFILE_GENERATE = "profile.generate"
    MODEL_CALL = "model.call"
    MCP_CALL = "mcp.call"
    RECORDS_LIST = "records.list"
    RECORDS_READ = "records.read"
    PROFILE_VALIDATE = "profile.validate"
    PROFILE_PERSIST = "profile.persist"


# Low-cardinality metric names (no patient_id or run_id labels).
METRIC_REQUEST_DURATION = "clinician.request.duration"
METRIC_TOOL_ATTEMPTS = "clinician.tool.attempts"
METRIC_TOOL_TIMEOUTS = "clinician.tool.timeouts"
METRIC_MODEL_TOKENS = "clinician.model.tokens"
METRIC_BUDGET_EXHAUSTED = "clinician.budget.exhausted"

DEFAULT_LOG_EVENT_ALLOWLIST = frozenset(
    {
        "telemetry.startup",
        "telemetry.shutdown",
        "profile.generate.start",
        "profile.generate.end",
        "model.call.start",
        "model.call.end",
        "mcp.call.start",
        "mcp.call.end",
        "records.list.start",
        "records.list.end",
        "records.read.start",
        "records.read.end",
        "profile.validate.start",
        "profile.validate.end",
        "profile.persist.start",
        "profile.persist.end",
        "exporter.degraded",
        "collector.unreachable",
    }
)
