"""Planning HTTP routes; business decisions stay in the application service."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.agent.planning_application import PlanningApplication
from air_agent_app.api.dependencies import get_planning_application
from air_agent_app.models.incident import IncidentInput
from air_agent_app.models.planning_response import PlanningResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["planning"])


@router.post(
    "/planning",
    response_model=PlanningResponse,
    response_model_by_alias=False,
    responses={
        502: {"model": PlanningResponse, "description": "Planner model failed"},
        503: {"description": "Server model configuration unavailable"},
    },
)
def create_plan(
    incident: IncidentInput,
    response: Response,
    application: Annotated[PlanningApplication, Depends(get_planning_application)],
) -> PlanningResponse:
    """Plan the supplied incident in a worker thread; do not dispatch evidence tools."""
    result = application.plan(incident)
    if result.status == "PLANNER_FAILED":
        response.status_code = 502
    logger.info(
        "Planning HTTP request completed investigation_id=%s status=%s",
        result.investigation_id,
        result.status,
    )
    return result
