"""Validated incident input. Missing operational context stays explicit."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class IncidentInput(BaseModel):
    """Facts supplied by the caller; timestamps must include a timezone."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    incident_id: UUID
    title: ShortText
    description: str = Field(min_length=1, max_length=8000)
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    detected_at: AwareDatetime
    service_name: ShortText | None = None
    environment: ShortText | None = None
    started_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_time_order(self) -> "IncidentInput":
        """Reject a claimed start after detection instead of silently correcting it."""
        if self.started_at is not None and self.started_at > self.detected_at:
            raise ValueError("started_at must not be after detected_at")
        return self
