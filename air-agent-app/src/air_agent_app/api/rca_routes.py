"""Section 9 HTTP route: the LLM Investigation Agent over an accepted evidence payload."""

from typing import Annotated

from fastapi import APIRouter, Depends

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.api.dependencies import get_rca_service
from air_agent_app.investigation.rca_service import RcaService
from air_agent_app.models.investigate import InvestigateResponse
from air_agent_app.models.rca_result import InvestigationResult

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["rca"])


@router.post(
    "/rca",
    response_model=InvestigationResult,
    responses={
        502: {"description": "RCA model failed after bounded retries"},
        503: {"description": "Server model configuration unavailable"},
    },
)
def create_rca(
    evidence: InvestigateResponse,
    service: Annotated[RcaService, Depends(get_rca_service)],
) -> InvestigationResult:
    """Run the LLM Investigation Agent over one accepted `/api/v1/investigate` response.

    The request body is exactly what `POST /api/v1/investigate` returns --
    the "Direct Evidence Collection Handoff" architecture from
    `reference/AIR-Investigation.pdf`: no separate EvidenceValidator stage
    runs first. `investigation_status = "INCONCLUSIVE"` is a normal, valid
    outcome (never an error) when the evidence cannot support a defensible
    root cause. Model/transport/output-contract failures surviving bounded
    retry raise `RcaExecutionError`, mapped to `502` by the app's error
    handler -- see docs/section_09_rca_agent.md.
    """
    result = service.investigate(evidence)
    logger.info(
        "RCA HTTP request completed investigation_id=%s status=%s",
        evidence.investigation_id,
        result.investigation_status,
    )
    return result
