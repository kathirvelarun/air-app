"""End-to-end orchestration HTTP route: Planning -> Evidence Collection -> RCA, one call."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.agent.orchestration_application import OrchestrationApplication
from air_agent_app.api.dependencies import get_orchestration_application
from air_agent_app.models.orchestration import OrchestrationRequest, OrchestrationResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["orchestration"])

# COMPLETED and INCONCLUSIVE are both normal outcomes (200). Everything
# else is a terminal stop before the pipeline could produce an RCA result.
_FAILURE_STATUS_CODES: dict[str, int] = {
    "PLANNER_FAILED": 502,
    "EVIDENCE_REQUEST_INVALID": 422,
    "RCA_FAILED": 502,
}


@router.post(
    "/incidents/investigate",
    response_model=OrchestrationResponse,
    responses={
        422: {"description": "Plan and request together cannot build a valid evidence request"},
        502: {"description": "Planning or RCA model failed"},
        503: {"description": "Server model configuration unavailable"},
    },
)
async def investigate_incident(
    request: OrchestrationRequest,
    response: Response,
    application: Annotated[OrchestrationApplication, Depends(get_orchestration_application)],
) -> OrchestrationResponse:
    """Run Planning, Evidence Collection, and RCA for one incident in a single call.

    `status` on the response is the definitive outcome:

    - `COMPLETED` / `INCONCLUSIVE`: RCA ran; `INCONCLUSIVE` is a normal
      result, not an error, when the evidence cannot support a defensible
      root cause.
    - `PLANNER_FAILED`: Section 1 did not produce a ready plan; `evidence`
      and `rca` are both absent.
    - `EVIDENCE_REQUEST_INVALID`: the plan selected no agent this service
      recognizes, or a selected agent needs a field the request did not
      supply (e.g. `DeploymentAgent` needs `repository`); `evidence` and
      `rca` are both absent.
    - `NO_EVIDENCE_COLLECTED`: every selected evidence agent failed; `rca`
      is absent (never a guessed `INCONCLUSIVE` standing in for missing
      evidence -- the model never saw this request at all).
    - `RCA_FAILED`: the RCA model failed after bounded retries; `evidence`
      is present, `rca` is absent.
    """
    result = await application.investigate(request)
    response.status_code = _FAILURE_STATUS_CODES.get(result.status, 200)
    logger.info(
        "Orchestration HTTP request completed investigation_id=%s status=%s",
        result.investigation_id,
        result.status,
    )
    return result
