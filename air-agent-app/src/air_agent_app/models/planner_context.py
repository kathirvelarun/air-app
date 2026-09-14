"""The bounded, normalized information supplied to the model."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from air_agent_app.models.incident import IncidentInput


class PlannerContext(BaseModel):
    """Separate caller facts from application-derived planning information."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investigation_id: UUID
    incident: IncidentInput
    window_start: datetime
    window_end: datetime
    window_basis: str
    available_agents: tuple[str, ...]
    missing_context: tuple[str, ...]
