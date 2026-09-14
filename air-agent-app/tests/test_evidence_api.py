"""HTTP contract for the log, metric, trace, and deployment evidence endpoints."""

from fastapi.testclient import TestClient

from air_agent_app.api.app import create_app

VALID_REQUEST = {
    "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
    "service_name": "payment-service",
    "environment": "production",
    "start_time": "2026-08-29T14:00:00Z",
    "end_time": "2026-08-29T16:00:00Z",
    "required_evidence": ["Application exceptions"],
}

VALID_METRIC_REQUEST = {
    "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
    "service_name": "payment-service",
    "environment": "production",
    "start_time": "2026-08-29T14:00:00Z",
    "end_time": "2026-08-29T16:00:00Z",
    "required_metrics": ["cpu_pct", "memory_pct", "http_5xx_rate", "p95_latency_ms"],
}

VALID_TRACE_REQUEST = {
    "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
    "service_name": "payment-service",
    "environment": "production",
    "start_time": "2026-08-29T14:00:00Z",
    "end_time": "2026-08-29T16:00:00Z",
}

VALID_DEPLOYMENT_REQUEST = {
    "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
    "service_name": "payment-service",
    "environment": "production",
    "repository": "org/air-services",
    "start_time": "2026-08-29T14:00:00Z",
    "end_time": "2026-08-29T16:00:00Z",
}


def test_log_evidence_finds_the_buried_timeout() -> None:
    """The same offline scenario as the unit tests, exercised over HTTP."""
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/logs", json=VALID_REQUEST)
    assert response.status_code == 200
    data = response.json()
    assert data["investigation_id"] == VALID_REQUEST["investigation_id"]
    evidence = data["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["agent_name"] == "LogsAgent"
    assert evidence[0]["evidence_type"] == "LOG"
    assert evidence[0]["findings"]["error_count"] == 5


def test_log_evidence_rejects_end_before_start() -> None:
    """Time-order validation runs before the agent is ever invoked."""
    payload = {
        **VALID_REQUEST,
        "start_time": "2026-08-29T16:00:00Z",
        "end_time": "2026-08-29T14:00:00Z",
    }
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/logs", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_log_evidence_rejects_missing_required_field() -> None:
    """Unknown or missing fields are rejected without echoing the payload."""
    payload = {key: value for key, value in VALID_REQUEST.items() if key != "service_name"}
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/logs", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_metric_evidence_finds_the_real_signal() -> None:
    """The same offline scenario as the unit tests, exercised over HTTP."""
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/metrics", json=VALID_METRIC_REQUEST)
    assert response.status_code == 200
    data = response.json()
    assert data["investigation_id"] == VALID_METRIC_REQUEST["investigation_id"]
    evidence = data["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["agent_name"] == "MetricsAgent"
    assert evidence[0]["evidence_type"] == "METRIC"
    assert evidence[0]["findings"]["http_5xx_rate"]["health"] == "UNHEALTHY"
    assert evidence[0]["findings"]["cpu_pct"]["health"] == "HEALTHY"


def test_metric_evidence_rejects_end_before_start() -> None:
    """Time-order validation runs before the agent is ever invoked."""
    payload = {
        **VALID_METRIC_REQUEST,
        "start_time": "2026-08-29T16:00:00Z",
        "end_time": "2026-08-29T14:00:00Z",
    }
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/metrics", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_trace_evidence_finds_the_buried_timeout() -> None:
    """The same offline scenario as the unit tests, exercised over HTTP."""
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/traces", json=VALID_TRACE_REQUEST)
    assert response.status_code == 200
    data = response.json()
    assert data["investigation_id"] == VALID_TRACE_REQUEST["investigation_id"]
    evidence = data["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["agent_name"] == "TracesAgent"
    assert evidence[0]["evidence_type"] == "TRACE"
    assert evidence[0]["findings"]["error_span_count"] == 10


def test_trace_evidence_rejects_end_before_start() -> None:
    """Time-order validation runs before the agent is ever invoked."""
    payload = {
        **VALID_TRACE_REQUEST,
        "start_time": "2026-08-29T16:00:00Z",
        "end_time": "2026-08-29T14:00:00Z",
    }
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/traces", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_deployment_evidence_finds_the_notebooks_deployment() -> None:
    """The same offline scenario as the unit tests, exercised over HTTP."""
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/deployments", json=VALID_DEPLOYMENT_REQUEST)
    assert response.status_code == 200
    data = response.json()
    assert data["investigation_id"] == VALID_DEPLOYMENT_REQUEST["investigation_id"]
    evidence = data["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["agent_name"] == "DeploymentAgent"
    assert evidence[0]["evidence_type"] == "DEPLOYMENT"
    assert evidence[0]["findings"]["latest_deployment"]["version"] == "2.4.1"
    assert evidence[0]["findings"]["minutes_before_incident"] == 120.0


def test_deployment_evidence_rejects_end_before_start() -> None:
    """Time-order validation runs before the agent is ever invoked."""
    payload = {
        **VALID_DEPLOYMENT_REQUEST,
        "start_time": "2026-08-29T16:00:00Z",
        "end_time": "2026-08-29T14:00:00Z",
    }
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/evidence/deployments", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
