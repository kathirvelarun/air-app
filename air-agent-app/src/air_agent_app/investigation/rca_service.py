"""Section 9: the LLM Investigation Agent, composed from typed evidence to a checked result.

Named ``RcaService`` (not ``InvestigationService``) to avoid colliding with
``agent/investigation_service.py``'s ``InvestigationService``, which
executes the unrelated Section 1 planning graph.

The injected model boundary (``RcaLLMClient``) takes typed
``InvestigateResponse``/source-reference objects directly, not a rendered
prompt -- see ``tools/llm/rca_llm_service.py``'s docstring for why this
differs from ``PlannerService``.
"""

from typing import Protocol

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.investigation.rca_post_checks import enforce_human_approval, validate_source_refs
from air_agent_app.investigation.rca_retry import run_with_retry
from air_agent_app.investigation.rca_source_refs import build_source_reference_map
from air_agent_app.models.investigate import InvestigateResponse
from air_agent_app.models.rca_result import InvestigationResult

logger = get_logger(__name__)


class RcaLLMClient(Protocol):
    """The model boundary: accepted evidence and its allowed references in, a result out."""

    def generate(
        self,
        evidence: InvestigateResponse,
        source_reference_map: dict[str, dict[str, str]],
    ) -> InvestigationResult:
        """Produce one InvestigationResult from the supplied evidence; no side effects."""
        ...


class RcaService:
    """Run the LLM Investigation Agent over one accepted evidence-collection payload."""

    def __init__(self, llm_client: RcaLLMClient) -> None:
        """Inject the model boundary so offline tests exercise the same workflow."""
        self._llm_client = llm_client

    def investigate(self, evidence: InvestigateResponse) -> InvestigationResult:
        """Build source references, call the model with bounded retry, then apply post-checks.

        No separate EvidenceValidator runs beforehand (`reference/AIR-Investigation.pdf`'s
        architecture update): ``evidence`` having already passed
        ``InvestigateResponse`` validation is what makes it "accepted" for
        this call. What runs here are output-side checks only -- source
        references and the human-approval policy -- never a re-judgment of
        evidence quality.
        """
        logger.info("RCA investigation started investigation_id=%s", evidence.investigation_id)
        source_reference_map = build_source_reference_map(evidence)

        def attempt() -> InvestigationResult:
            """Call the model once and apply both post-checks before returning."""
            result = self._llm_client.generate(evidence, source_reference_map)
            validate_source_refs(result, source_reference_map)
            result = result.model_copy(update={"investigation_id": evidence.investigation_id})
            return enforce_human_approval(result)

        result = run_with_retry(attempt)
        logger.info(
            "RCA investigation completed investigation_id=%s status=%s overall_confidence=%.2f",
            evidence.investigation_id,
            result.investigation_status,
            result.overall_confidence,
        )
        return result
