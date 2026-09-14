"""Runtime state for the end-to-end Planning -> Evidence Collection -> RCA graph."""

from typing import NotRequired, TypedDict
from uuid import UUID

from air_agent_app.models.investigate import InvestigateResponse
from air_agent_app.models.orchestration import OrchestrationRequest, OrchestrationStatus
from air_agent_app.models.planning_response import PlanningResponse
from air_agent_app.models.rca_result import InvestigationResult


class OrchestrationState(TypedDict):
    """Carry only values required across the three composed stages.

    `status`/`terminal_reason` are set by whichever node ends the pipeline
    (successfully or not) -- their presence is itself the routing signal:
    each conditional edge checks ``"status" in state`` to decide whether to
    continue to the next stage or stop.
    """

    request: OrchestrationRequest
    investigation_id: NotRequired[UUID]
    planning: NotRequired[PlanningResponse]
    evidence: NotRequired[InvestigateResponse]
    rca: NotRequired[InvestigationResult]
    status: NotRequired[OrchestrationStatus]
    terminal_reason: NotRequired[str]
