"""Public response contract for the two-path planning workflow."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from air_agent_app.models.planner_output import PlannerOutput


class PlanningResponse(BaseModel):
    """Return either an executable plan or an explicit planning failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    investigation_id: UUID
    incident_id: UUID
    status: Literal["PLAN_READY", "PLANNER_FAILED"]
    terminal_reason: Literal["MODEL_FAILURE", "NO_AGENTS_SELECTED"] | None
    plan: PlannerOutput | None
    evidence_ready: bool
