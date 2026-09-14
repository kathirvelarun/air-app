"""HTTP contract for POST /api/v1/incidents/investigate: the single end-to-end call."""

from fastapi.testclient import TestClient

from air_agent_app.agent.investigation_service import InvestigationService
from air_agent_app.agent.orchestration_application import OrchestrationApplication
from air_agent_app.agent.planning_application import PlanningApplication
from air_agent_app.api.app import create_app
from air_agent_app.api.dependencies import get_orchestration_application
from air_agent_app.investigation.deployment_agent import DeploymentAgent
from air_agent_app.investigation.evidence_investigator import EvidenceInvestigator
from air_agent_app.investigation.logs_agent import LogsAgent
from air_agent_app.investigation.metrics_agent import MetricsAgent
from air_agent_app.investigation.planner_service import PlannerService
from air_agent_app.investigation.rca_service import RcaService
from air_agent_app.investigation.traces_agent import TracesAgent
from air_agent_app.tools.mock.fixtures.offline_deployment_tool import OfflineDeploymentTool
from air_agent_app.tools.mock.fixtures.offline_investigation_model import OfflineInvestigationModel
from air_agent_app.tools.mock.fixtures.offline_log_tool import OfflineLogTool
from air_agent_app.tools.mock.fixtures.offline_metric_tool import OfflineMetricTool
from air_agent_app.tools.mock.fixtures.offline_plan_model import OfflinePlanModel, PlanningScenario
from air_agent_app.tools.mock.fixtures.offline_trace_tool import OfflineTraceTool

REQUEST = {
    "incident": {
        "incident_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
        "title": "Payment errors spiking",
        "description": "payment-service error rate elevated",
        "severity": "HIGH",
        "detected_at": "2026-08-29T14:20:00Z",
        "service_name": "payment-service",
        "environment": "production",
    },
    "repository": "org/air-services",
    "start_time": "2026-08-29T14:00:00Z",
    "end_time": "2026-08-29T16:00:00Z",
}


def _offline_orchestration_application(
    scenario: PlanningScenario = "ready",
) -> OrchestrationApplication:
    """Build an OrchestrationApplication wired to every offline fixture."""
    planning_application = PlanningApplication(
        InvestigationService(PlannerService(OfflinePlanModel(scenario).generate))
    )
    investigator = EvidenceInvestigator(
        logs_agent=LogsAgent(OfflineLogTool()),
        metrics_agent=MetricsAgent(OfflineMetricTool()),
        traces_agent=TracesAgent(OfflineTraceTool()),
        deployment_agent=DeploymentAgent(OfflineDeploymentTool()),
    )
    return OrchestrationApplication(
        planning_application, investigator, RcaService(OfflineInvestigationModel())
    )


def test_orchestration_completes_the_full_pipeline_in_one_call() -> None:
    """A single POST runs Planning, Evidence Collection, and RCA and returns 200."""
    app = create_app()
    app.dependency_overrides[get_orchestration_application] = _offline_orchestration_application
    with TestClient(app) as client:
        response = client.post("/api/v1/incidents/investigate", json=REQUEST)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["planning"]["status"] == "PLAN_READY"
    assert data["evidence"] is not None
    assert data["rca"]["investigation_status"] == "COMPLETED"
    assert set(data.keys()) == {
        "investigation_id",
        "incident_id",
        "status",
        "terminal_reason",
        "planning",
        "evidence",
        "rca",
    }


def test_orchestration_planner_failure_maps_to_502() -> None:
    """PLANNER_FAILED is reported as 502, matching /api/v1/planning's own mapping."""
    app = create_app()
    app.dependency_overrides[get_orchestration_application] = lambda: (
        _offline_orchestration_application("no_agents")
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/incidents/investigate", json=REQUEST)
    assert response.status_code == 502
    data = response.json()
    assert data["status"] == "PLANNER_FAILED"
    assert data["evidence"] is None
    assert data["rca"] is None


def test_orchestration_rejects_malformed_request_body() -> None:
    """A body missing the evidence-window fields is a 422, not a 500."""
    app = create_app()
    app.dependency_overrides[get_orchestration_application] = _offline_orchestration_application
    payload = {"incident": REQUEST["incident"]}
    with TestClient(app) as client:
        response = client.post("/api/v1/incidents/investigate", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
