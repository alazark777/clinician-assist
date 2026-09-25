"""Strict public and internal data contracts."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]


class StrictModel(BaseModel):
    """Base model that rejects unknown input."""

    model_config = ConfigDict(extra="forbid")


class DemoLogin(StrictModel):
    """Local synthetic login credentials."""

    username: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    passphrase: Annotated[str, StringConstraints(min_length=1, max_length=512)]


class PatientSummary(StrictModel):
    """Authorized catalog entry without clinical data."""

    patient_id: Identifier
    label: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class ProfileRequest(StrictModel):
    """Profile generation input."""

    patient_id: Identifier
    visit_context: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    as_of: date
    request_id: Identifier


class Fact(StrictModel):
    """Source-grounded clinical fact."""

    section: Literal["condition", "medication", "allergy", "lab", "vital"]
    key: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    value: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    date: date | None
    qualifier: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    source_ids: list[Identifier] = Field(min_length=1)


class Gap(StrictModel):
    """Explicit missing or unavailable evidence."""

    code: Identifier
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class Conflict(StrictModel):
    """Conflicting source-linked assertions."""

    code: Identifier
    source_ids: list[Identifier] = Field(min_length=2)
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class Source(StrictModel):
    """Immutable source snapshot displayed with a profile."""

    record_id: Identifier
    version: int = Field(ge=1)
    excerpt: Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class Profile(StrictModel):
    """Validated profile derived only from read records."""

    patient_id: Identifier
    status: Literal["complete", "incomplete"]
    facts: list[Fact]
    gaps: list[Gap]
    conflicts: list[Conflict]
    sources: list[Source]

    @model_validator(mode="after")
    def validate_provenance(self) -> "Profile":
        """Ensure every fact and conflict references a returned source."""
        available = {source.record_id for source in self.sources}
        referenced = {
            source_id
            for item in [*self.facts, *self.conflicts]
            for source_id in item.source_ids
        }
        if not referenced <= available:
            raise ValueError("profile references unavailable sources")
        return self


class Usage(StrictModel):
    """Bounded execution usage."""

    model_calls: int = Field(ge=0, le=6)
    tool_attempts: int = Field(ge=0)
    additional_record_ids: int = Field(ge=0, le=10)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ProfileResponse(StrictModel):
    """Persisted runtime profile envelope."""

    profile_id: Identifier
    run_id: Identifier
    trace_id: Identifier
    profile_version: int = Field(ge=1)
    review_status: Literal["draft", "accepted", "needs_correction"]
    review_revision: int = Field(ge=0)
    profile: Profile
    usage: Usage


class RunStatus(StrEnum):
    """Durable run lifecycle."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class RunResponse(StrictModel):
    """Safe polling response."""

    run_id: Identifier
    run_status: RunStatus
    profile_id: Identifier | None
    error_code: Identifier | None


class RunningResponse(StrictModel):
    """Response for an already active idempotent run."""

    run_id: Identifier
    run_status: Literal["running"]
    profile_id: None = None


class FeedbackDecision(StrEnum):
    """Permitted review decisions."""

    ACCEPT = "accept"
    NEEDS_CORRECTION = "needs_correction"


class FeedbackRequest(StrictModel):
    """Version-bound feedback command."""

    profile_version: int = Field(ge=1)
    review_revision: int = Field(ge=0)
    decision: FeedbackDecision
    comment: Annotated[str, StringConstraints(max_length=4000)] | None = None


class FeedbackResponse(StrictModel):
    """Updated review state."""

    profile_id: Identifier
    profile_version: int
    review_status: Literal["accepted", "needs_correction"]
    review_revision: int


class ErrorBody(StrictModel):
    """Stable API error."""

    code: Identifier
    message: str


class HealthResponse(StrictModel):
    """Non-sensitive health state."""

    status: Literal["ok", "degraded", "unavailable"]
    dependencies: dict[str, Literal["ok", "degraded", "unavailable"]]
