"""Authentication models."""

from pydantic import BaseModel, ConfigDict, Field

from clinician_agent.schemas import PatientSummary, StrictModel


class DemoUserConfig(StrictModel):
    """One demo user entry from local secrets."""

    username: str
    passphrase: str
    caller_id: str
    patients: list[PatientSummary] = Field(min_length=1)


class DemoSessionsFile(StrictModel):
    """Parsed demo session configuration."""

    users: list[DemoUserConfig] = Field(min_length=1)


class CallerContext(BaseModel):
    """Resolved caller permissions for one request."""

    model_config = ConfigDict(frozen=True)

    caller_id: str
    allowed_patients: tuple[PatientSummary, ...]

    def can_access_patient(self, patient_id: str) -> bool:
        """Return whether the caller may access a patient."""
        return any(item.patient_id == patient_id for item in self.allowed_patients)
