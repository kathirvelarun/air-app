"""Minimal runtime state for one planner model invocation."""

from typing import Literal, NotRequired, TypedDict
from uuid import UUID

from air_agent_app.models.incident import IncidentInput
from air_agent_app.models.planner_context import PlannerContext
from air_agent_app.models.planner_output import PlannerOutput


class PlannerState(TypedDict):
    """Carry only values required by the single-attempt planning graph."""

    investigation_id: UUID
    incident: IncidentInput
    status: Literal["PLANNING", "PLAN_READY", "PLANNER_FAILED"]
    terminal_reason: Literal["MODEL_FAILURE", "NO_AGENTS_SELECTED"] | None
    context: NotRequired[PlannerContext]
    planner_output: PlannerOutput | None
