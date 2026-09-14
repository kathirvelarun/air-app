"""HTTP planning contract, dependency injection and safe failure responses."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from air_agent_app.agent.investigation_service import InvestigationService
from air_agent_app.agent.planning_application import PlanningApplication
from air_agent_app.api.app import create_app
from air_agent_app.api.dependencies import get_planning_application
from air_agent_app.investigation.planner_service import PlannerService
from air_agent_app.models.exceptions import ModelCallError
from air_agent_app.tools.mock.fixtures.offline_plan_model import OfflinePlanModel, PlanningScenario
from air_agent_app.tools.mock.fixtures.payment_alert import PAYMENT_ALERT


@pytest.mark.parametrize(
    ("scenario", "status", "ready"),
    [
        ("ready", "PLAN_READY", True),
        ("no_agents", "PLANNER_FAILED", False),
    ],
)
def test_api_planning_outcomes(scenario: PlanningScenario, status: str, ready: bool) -> None:
    """Return typed business outcomes using the real bounded planning graph."""
    app = create_app()
    application = PlanningApplication(
        InvestigationService(PlannerService(OfflinePlanModel(scenario).generate))
    )

    def override_application() -> PlanningApplication:
        """Inject the test application without introducing HTTP query parameters."""
        return application

    app.dependency_overrides[get_planning_application] = override_application
    with TestClient(app) as client:
        response = client.post("/api/v1/planning", json=PAYMENT_ALERT)
    assert response.status_code == (200 if ready else 502)
    data = response.json()
    assert data["status"] == status
    assert data["evidence_ready"] is ready
    assert data["incident_id"] == PAYMENT_ALERT["incident_id"]
    if ready:
        assert "parallel_agents" in data["plan"]
    else:
        assert data["plan"] is None
        assert data["terminal_reason"] == "NO_AGENTS_SELECTED"
    assert "evidence" not in data


@pytest.mark.parametrize(
    "update",
    [
        {"incident_id": "bad"},
        {"detected_at": "2026-09-13T14:00:00"},
        {"severity": "URGENT"},
        {"title": ""},
        {"unexpected": "PRIVATE_VALUE"},
    ],
)
def test_invalid_incident_does_not_call_planner(update: dict[str, object]) -> None:
    """Invalid incidents return 422 without echoing private inputs or invoking a model."""
    app = create_app()
    application = Mock()

    def override_application() -> PlanningApplication:
        """Inject the test application without introducing HTTP query parameters."""
        return application

    app.dependency_overrides[get_planning_application] = override_application
    with TestClient(app) as client:
        response = client.post("/api/v1/planning", json=PAYMENT_ALERT | update)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    application.plan.assert_not_called()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ModelCallError("PRIVATE_PROVIDER_ERROR"), 502),
        (RuntimeError("PRIVATE_IMPLEMENTATION_ERROR"), 500),
    ],
)
def test_api_failure_is_safe(error: Exception, code: int, caplog: pytest.LogCaptureFixture) -> None:
    """Provider failures and unexpected errors have distinct safe HTTP responses."""
    app = create_app()
    application = PlanningApplication(InvestigationService(PlannerService(Mock(side_effect=error))))

    def override_application() -> PlanningApplication:
        """Inject the test application without introducing HTTP query parameters."""
        return application

    app.dependency_overrides[get_planning_application] = override_application
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/planning", json=PAYMENT_ALERT)
    assert response.status_code == code
    assert "PRIVATE_" not in response.text and "PRIVATE_" not in caplog.text
    if code == 502:
        assert response.json()["status"] == "PLANNER_FAILED"
        assert response.json()["evidence_ready"] is False
        assert response.json()["plan"] is None


def test_live_dependency_uses_server_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default HTTP path composes the live factory, with provider IO mocked in this test."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("AIR_MODEL_NAME", "test-model")
    factory = Mock(return_value=OfflinePlanModel())
    monkeypatch.setattr("air_agent_app.api.dependencies.create_llm_service", factory)
    with TestClient(create_app()) as client:
        first = client.post("/api/v1/planning", json=PAYMENT_ALERT).json()
        second = client.post("/api/v1/planning", json=PAYMENT_ALERT).json()
    assert first["status"] == second["status"] == "PLAN_READY"
    assert first["investigation_id"] != second["investigation_id"]
    assert factory.call_count == 2


def test_missing_server_settings_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing live credentials never silently enable an offline API mode."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/planning", json=PAYMENT_ALERT)
    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "Planner configuration unavailable. Configure OPENAI_API_KEY "
            "and AIR_MODEL_NAME in the API server environment."
        )
    }


def test_openapi_documents_incident_and_response_without_model_call() -> None:
    """Interactive API documentation is available without model configuration or requests."""
    with TestClient(create_app()) as client:
        response = client.get("/openapi.json")
        assert client.get("/docs").status_code == 200
    operation = response.json()["paths"]["/api/v1/planning"]["post"]
    assert operation["requestBody"]
    assert set(operation["responses"]) >= {"200", "422", "502", "503"}
