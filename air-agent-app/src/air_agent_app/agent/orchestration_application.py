"""Turn a validated end-to-end submission into one orchestrated investigation."""

from air_agent_app.agent.graph.orchestration_graph import build_orchestration_graph
from air_agent_app.agent.graph.orchestration_state import OrchestrationState
from air_agent_app.agent.logging_config import get_logger
from air_agent_app.agent.planning_application import PlanningApplication
from air_agent_app.investigation.evidence_investigator import EvidenceInvestigator
from air_agent_app.investigation.rca_service import RcaService
from air_agent_app.models.orchestration import OrchestrationRequest, OrchestrationResponse

logger = get_logger(__name__)


class OrchestrationApplication:
    """Compose Planning, Evidence Collection, and RCA into one investigation.

    Thin by design: the graph (`build_orchestration_graph`) owns node
    logic, this class only compiles it once and reshapes the final graph
    state into the public `OrchestrationResponse`.
    """

    def __init__(
        self,
        planning_application: PlanningApplication,
        evidence_investigator: EvidenceInvestigator,
        rca_service: RcaService,
    ) -> None:
        """Compile the orchestration graph once per application instance."""
        self._graph = build_orchestration_graph(
            planning_application, evidence_investigator, rca_service
        )

    async def investigate(self, request: OrchestrationRequest) -> OrchestrationResponse:
        """Run the full Planning -> Evidence Collection -> RCA pipeline for one incident."""
        logger.info("Orchestration started incident_id=%s", request.incident.incident_id)
        initial: OrchestrationState = {"request": request}
        result = await self._graph.ainvoke(initial, config={"recursion_limit": 10})

        planning = result["planning"]
        status = result.get("status")
        if status is None:
            # run_rca always sets status on every path it can return from;
            # every other terminal path sets it too. Reaching here means a
            # graph wiring bug, not a runtime condition callers should handle.
            raise RuntimeError("Orchestration graph finished without a terminal status")

        response = OrchestrationResponse(
            investigation_id=planning.investigation_id,
            incident_id=request.incident.incident_id,
            status=status,
            terminal_reason=result.get("terminal_reason"),
            planning=planning,
            evidence=result.get("evidence"),
            rca=result.get("rca"),
        )
        logger.info(
            "Orchestration completed investigation_id=%s status=%s",
            response.investigation_id,
            response.status,
        )
        return response
