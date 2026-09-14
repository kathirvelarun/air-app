"""HTTP contract for the aggregated investigate endpoint."""

from fastapi.testclient import TestClient

from air_agent_app.api.app import create_app

VALID_REQUEST = {
    "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
    "service_name": "payment-service",
    "environment": "production",
    "repository": "org/air-services",
    "start_time": "2026-08-29T14:00:00Z",
    "end_time": "2026-08-29T16:00:00Z",
}


def test_investigate_returns_evidence_only() -> None:
    """The full payment-service scenario, exercised over HTTP.

    The response is exactly Section 8.2's `AggregatedEvidence` schema: no
    derived `key_findings` digest and no `rca` key. Root-cause assessment
    is not implemented yet (it needs an LLM-based RCA agent, Section 9).
    """
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/investigate", json=VALID_REQUEST)
    assert response.status_code == 200
    data = response.json()
    assert data["investigation_id"] == VALID_REQUEST["investigation_id"]
    assert len(data["evidence"]) == 4
    assert data["missing_agents"] == []
    assert len(data["timeline"]) == 4
    assert data["duplicate_count"] == 0
    assert set(data.keys()) == {
        "investigation_id",
        "evidence",
        "missing_agents",
        "duplicate_count",
        "timeline",
    }
    assert "key_findings" not in data
    assert "rca" not in data


def test_investigate_can_run_a_subset_of_agents() -> None:
    """Requesting fewer agents runs fewer agents, with no DeploymentAgent/repository needed."""
    payload = {**VALID_REQUEST, "repository": None, "agents": ["LogsAgent", "MetricsAgent"]}
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/investigate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert {item["agent_name"] for item in data["evidence"]} == {"LogsAgent", "MetricsAgent"}


def test_investigate_rejects_deployment_agent_without_repository() -> None:
    """DeploymentAgent structurally needs a repository; missing it is a 422, not a 500."""
    payload = {**VALID_REQUEST, "repository": None}
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/investigate", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_investigate_rejects_unknown_agent_name() -> None:
    """An unrecognized agent name is a clean validation error, not a runtime failure."""
    payload = {**VALID_REQUEST, "agents": ["NotARealAgent"]}
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/investigate", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_investigate_rejects_end_before_start() -> None:
    """Time-order validation runs before any agent is ever invoked."""
    payload = {
        **VALID_REQUEST,
        "start_time": "2026-08-29T16:00:00Z",
        "end_time": "2026-08-29T14:00:00Z",
    }
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/investigate", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
