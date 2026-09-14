"""HTTP contract for POST /api/v1/rca: the Direct Evidence Collection Handoff.

Exercises the real chain: call /api/v1/investigate first (offline evidence
tools, no live LLM needed), then feed that exact response body into
/api/v1/rca with the live LLM dependency overridden by the offline
investigation fixture -- proving the two endpoints are compatible end to
end, not just individually correct.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from air_agent_app.api.app import create_app
from air_agent_app.api.dependencies import get_rca_service
from air_agent_app.investigation.rca_service import RcaService
from air_agent_app.models.exceptions import RcaExecutionError
from air_agent_app.models.investigate import InvestigateResponse
from air_agent_app.models.rca_result import InvestigationResult
from air_agent_app.tools.mock.fixtures.offline_investigation_model import OfflineInvestigationModel

INVESTIGATE_REQUEST = {
    "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
    "service_name": "payment-service",
    "environment": "production",
    "repository": "org/air-services",
    "start_time": "2026-08-29T14:00:00Z",
    "end_time": "2026-08-29T16:00:00Z",
}


def _override_rca_service(app: FastAPI, service: RcaService) -> None:
    """Inject a test RcaService without a live OPENAI_API_KEY."""

    def override() -> RcaService:
        """Return the fixed test service instance."""
        return service

    app.dependency_overrides[get_rca_service] = override


def test_rca_accepts_the_exact_investigate_response_body() -> None:
    """The evidence-collection response needs zero transformation to become RCA input."""
    app = create_app()
    _override_rca_service(app, RcaService(OfflineInvestigationModel()))
    with TestClient(app) as client:
        evidence_response = client.post("/api/v1/investigate", json=INVESTIGATE_REQUEST)
        assert evidence_response.status_code == 200

        rca_response = client.post("/api/v1/rca", json=evidence_response.json())
    assert rca_response.status_code == 200
    data = rca_response.json()
    assert data["investigation_id"] == INVESTIGATE_REQUEST["investigation_id"]
    assert data["investigation_status"] == "COMPLETED"
    assert len(data["key_findings"]) == 4
    assert data["rca"] is not None
    assert set(data.keys()) == {
        "investigation_id",
        "investigation_status",
        "key_findings",
        "rca",
        "suggestion_plan",
        "overall_confidence",
        "source_refs_used",
        "missing_information",
    }


def test_rca_returns_inconclusive_for_an_all_healthy_service() -> None:
    """A service with no notable evidence gets a 200 INCONCLUSIVE, not an error."""
    app = create_app()
    _override_rca_service(app, RcaService(OfflineInvestigationModel()))
    payload = {**INVESTIGATE_REQUEST, "service_name": "unrelated-service"}
    with TestClient(app) as client:
        evidence_response = client.post("/api/v1/investigate", json=payload)
        rca_response = client.post("/api/v1/rca", json=evidence_response.json())
    assert rca_response.status_code == 200
    data = rca_response.json()
    assert data["investigation_status"] == "INCONCLUSIVE"
    assert data["rca"] is None


def test_rca_rejects_a_malformed_evidence_payload() -> None:
    """A body that isn't a valid InvestigateResponse is a 422, not a model call.

    The RCA service dependency is overridden here purely so this test does
    not also require a live OPENAI_API_KEY -- request validation must fail
    before the model dependency is ever exercised either way.
    """
    app = create_app()
    _override_rca_service(app, RcaService(OfflineInvestigationModel()))
    with TestClient(app) as client:
        response = client.post("/api/v1/rca", json={"not": "a valid payload"})
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_rca_execution_failure_maps_to_502() -> None:
    """A persistent execution failure surfaces as 502, never a raw stack trace."""

    class AlwaysFailingService(RcaService):
        """Simulate bounded retries already exhausted upstream."""

        def __init__(self) -> None:
            """Skip the real client entirely; this double never calls it."""

        def investigate(self, evidence: InvestigateResponse) -> InvestigationResult:
            """Always raise, as the real service would after exhausting retries."""
            raise RcaExecutionError("simulated exhausted retries")

    app = create_app()
    _override_rca_service(app, AlwaysFailingService())
    with TestClient(app) as client:
        evidence_response = client.post("/api/v1/investigate", json=INVESTIGATE_REQUEST)
        rca_response = client.post("/api/v1/rca", json=evidence_response.json())
    assert rca_response.status_code == 502
    assert rca_response.json() == {"detail": "RCA investigation failed after bounded retries"}
