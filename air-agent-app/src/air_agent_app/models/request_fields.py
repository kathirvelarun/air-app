"""Field definitions and validation shared by every evidence-agent request.

Extracted after LogEvidenceRequest, MetricEvidenceRequest, TraceEvidenceRequest,
and DeploymentEvidenceRequest all independently defined the same ShortText
alias and the same end-after-start validator.
"""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class TimeWindowRequest(BaseModel):
    """A request scoped to a [start_time, end_time) query window."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    start_time: AwareDatetime
    end_time: AwareDatetime

    @model_validator(mode="after")
    def validate_time_order(self) -> "TimeWindowRequest":
        """Reject an end time at or before the start of the query window."""
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self
