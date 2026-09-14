"""Public response contract shared by every single-agent evidence endpoint."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from air_agent_app.models.evidence import Evidence


class EvidenceResponse(BaseModel):
    """One evidence agent's run, returned over HTTP.

    Shared across agents deliberately: LogsAgent and MetricsAgent both
    return exactly this shape, so there is no per-agent response model to
    keep in sync.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    investigation_id: UUID
    evidence: list[Evidence]
