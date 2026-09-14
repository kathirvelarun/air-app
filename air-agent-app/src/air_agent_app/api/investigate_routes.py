"""Section 8 HTTP route: parallel evidence collection and aggregation."""

from typing import Annotated

from fastapi import APIRouter, Depends

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.api.dependencies import get_evidence_investigator
from air_agent_app.investigation.evidence_investigator import EvidenceInvestigator
from air_agent_app.models.investigate import InvestigateRequest, InvestigateResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["investigate"])


@router.post("/investigate", response_model=InvestigateResponse)
async def investigate(
    request: InvestigateRequest,
    investigator: Annotated[EvidenceInvestigator, Depends(get_evidence_investigator)],
) -> InvestigateResponse:
    """Run the requested evidence agents in parallel and return aggregated evidence.

    Callers are expected to call this after ``/api/v1/planning`` returns
    `PLAN_READY`, passing `parallel_agents` as `agents`. One agent failing is
    recorded in `missing_agents`, never a 500 for the whole request. The
    response is exactly Section 8.2's `AggregatedEvidence` schema
    (`investigation_id`, `evidence`, `missing_agents`, `duplicate_count`,
    `timeline`) - no derived summary on top of it, and no `rca` field.
    Root-cause assessment is a separate call: pass this exact response body
    to `POST /api/v1/rca` (Section 9's LLM Investigation Agent) - see
    docs/section_08_investigate_service.md and docs/section_09_rca_agent.md.
    """
    response = await investigator.investigate(request)
    logger.info(
        "Investigate HTTP request completed investigation_id=%s evidence_count=%s",
        request.investigation_id,
        len(response.evidence),
    )
    return response
