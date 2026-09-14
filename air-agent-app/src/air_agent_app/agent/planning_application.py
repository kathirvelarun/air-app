"""Turn validated incident submissions into the public planning response."""

from uuid import uuid4

from air_agent_app.agent.investigation_service import InvestigationService
from air_agent_app.models.incident import IncidentInput
from air_agent_app.models.planning_response import PlanningResponse


class PlanningApplication:
    """Reuse bounded planning without HTTP dependencies or automatic evidence collection."""

    def __init__(self, investigation_service: InvestigationService) -> None:
        """Inject the existing planner orchestration for live execution or offline tests."""
        self._investigation_service = investigation_service

    def plan(self, incident: IncidentInput) -> PlanningResponse:
        """Create a fresh run and expose an accepted plan only through its terminal status."""
        result = self._investigation_service.investigate(uuid4(), incident.model_dump())
        return PlanningResponse(
            investigation_id=result["investigation_id"],
            incident_id=incident.incident_id,
            status=result["status"],
            terminal_reason=result["terminal_reason"],
            plan=None if result["status"] == "PLANNER_FAILED" else result["planner_output"],
            evidence_ready=result["status"] == "PLAN_READY",
        )
