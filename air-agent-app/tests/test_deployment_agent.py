"""DeploymentAgent: deterministic dump generation, normalization, and evidence shape."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from air_agent_app.investigation.deployment_agent import (
    DeploymentAgent,
    _build_evidence,
    _extract_findings,
    _parse_deployment_line,
)
from air_agent_app.models.deployment_evidence import DeploymentEvidenceRequest
from air_agent_app.tools.mock.fixtures.deployment_dump import generate_deployment_events
from air_agent_app.tools.mock.fixtures.offline_deployment_tool import OfflineDeploymentTool

START = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


def make_request(**overrides: object) -> DeploymentEvidenceRequest:
    """Build a valid DeploymentEvidenceRequest, overriding only what a test needs."""
    fields: dict[str, object] = {
        "investigation_id": uuid4(),
        "service_name": "payment-service",
        "environment": "production",
        "repository": "org/air-services",
        "start_time": START,
        "end_time": START + timedelta(hours=2),
    }
    fields.update(overrides)
    return DeploymentEvidenceRequest.model_validate(fields)


def test_request_rejects_end_before_start() -> None:
    """The query window must be non-empty and forward in time."""
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        make_request(end_time=START - timedelta(minutes=1))


def test_dump_returns_deployment_and_commit_within_window() -> None:
    """payment-service's deployment lands inside a 2-hour window ending at window_end."""
    window_end = START + timedelta(hours=2)
    lines = generate_deployment_events(
        "org/air-services", "payment-service", "production", START, window_end
    )
    assert len(lines) == 2
    assert any("event_type=deployment" in line and "version=2.4.1" in line for line in lines)
    assert any("event_type=commit" in line for line in lines)


def test_dump_returns_nothing_outside_the_window() -> None:
    """cache-service's deployment (6h lead time) falls outside a 2-hour window."""
    window_end = START + timedelta(hours=2)
    lines = generate_deployment_events(
        "org/air-services", "cache-service", "production", START, window_end
    )
    assert lines == []


def test_dump_returns_nothing_for_unknown_service_or_environment() -> None:
    """No modeled deployment means no fabricated events."""
    window_end = START + timedelta(hours=2)
    assert (
        generate_deployment_events(
            "org/air-services", "auth-service", "production", START, window_end
        )
        == []
    )
    assert (
        generate_deployment_events(
            "org/air-services", "payment-service", "staging", START, window_end
        )
        == []
    )


def test_parse_deployment_line_extracts_known_fields() -> None:
    """A well-formed deployment line becomes a fully populated NormalizedDeploymentEvent."""
    line = (
        "2026-08-29T14:00:00Z event_type=deployment repository=org/air-services "
        "environment=production version=2.4.1 commit_sha=a1b2c3d branch=main "
        "actor=deploy-bot workflow_name=deploy workflow_run_id=98765 status=success "
        "rollback=false changed_files=config/payment-service.yaml"
    )
    event = _parse_deployment_line(line)
    assert event is not None
    assert event.event_type == "deployment"
    assert event.version == "2.4.1"
    assert event.rollback is False
    assert event.changed_files == ["config/payment-service.yaml"]


@pytest.mark.parametrize(
    "line", ["", "not a deployment line", "2026-08-29T14:00:00Z event_type=deployment"]
)
def test_parse_deployment_line_rejects_unknown_shapes(line: str) -> None:
    """Lines missing required fields are dropped, not raised."""
    assert _parse_deployment_line(line) is None


def test_extract_findings_computes_minutes_before_incident() -> None:
    """Lead time is measured against the request's own end_time."""
    request = make_request()
    events = [
        _parse_deployment_line(
            "2026-08-29T14:00:00Z event_type=deployment repository=org/air-services "
            "environment=production version=2.4.1 commit_sha=a1b2c3d branch=main "
            "actor=deploy-bot rollback=false"
        ),
        _parse_deployment_line(
            "2026-08-29T13:55:00Z event_type=commit repository=org/air-services "
            "environment=production commit_sha=a1b2c3d branch=main actor=deploy-bot"
        ),
    ]
    findings = _extract_findings(events, request)
    assert findings["deployment_detected"] is True
    assert findings["minutes_before_incident"] == 120.0
    assert findings["commit_count"] == 1
    assert findings["rollback_detected"] is False


@pytest.mark.parametrize(
    ("total_events", "deployment_detected", "expected_confidence"),
    [(0, False, 0.4), (3, False, 0.85), (2, True, 0.99)],
)
def test_build_evidence_confidence_tiers(
    total_events: int, deployment_detected: bool, expected_confidence: float
) -> None:
    """Zero events and events-without-a-deployment are both successful evidence."""
    findings = {
        "total_events": total_events,
        "deployment_detected": deployment_detected,
        "latest_deployment": (
            {"version": "2.4.1", "commit_sha": "a1b2c3d", "branch": "main", "timestamp": "x"}
            if deployment_detected
            else None
        ),
        "minutes_before_incident": 120.0 if deployment_detected else None,
        "rollback_detected": False,
    }
    evidence = _build_evidence(findings, make_request())
    assert len(evidence) == 1
    assert evidence[0].confidence == expected_confidence


@pytest.mark.anyio
async def test_deployment_agent_finds_the_notebooks_deployment_via_offline_tool() -> None:
    """End-to-end: the exact v2.4.1/2h-ago deployment from the notebook's own STEPS list."""
    request = make_request()
    agent = DeploymentAgent(OfflineDeploymentTool())
    evidence = await agent.execute(request)
    assert len(evidence) == 1
    result = evidence[0]
    assert result.investigation_id == request.investigation_id
    assert result.agent_name == "DeploymentAgent"
    assert result.evidence_type == "DEPLOYMENT"
    assert result.findings["latest_deployment"]["version"] == "2.4.1"
    assert result.findings["minutes_before_incident"] == 120.0
    assert result.findings["rollback_detected"] is False
