"""LogsAgent: deterministic dump generation, normalization, and evidence shape."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from air_agent_app.investigation.logs_agent import (
    LogsAgent,
    _build_evidence,
    _extract_patterns,
    _parse_line,
)
from air_agent_app.models.log_evidence import LogEvidenceRequest, NormalizedLogEvent
from air_agent_app.tools.mock.fixtures.log_dump import generate_application_log_dump
from air_agent_app.tools.mock.fixtures.offline_log_tool import OfflineLogTool

START = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


def make_request(**overrides: object) -> LogEvidenceRequest:
    """Build a valid LogEvidenceRequest, overriding only what a test needs."""
    fields: dict[str, object] = {
        "investigation_id": uuid4(),
        "service_name": "payment-service",
        "environment": "production",
        "start_time": START,
        "end_time": START + timedelta(hours=2),
    }
    fields.update(overrides)
    return LogEvidenceRequest.model_validate(fields)


def test_dump_is_deterministic_with_five_sparse_errors() -> None:
    """Same inputs produce the same 1500 lines with exactly 5 buried errors."""
    first = generate_application_log_dump(start=START)
    second = generate_application_log_dump(start=START)
    assert first == second
    assert len(first) == 1500
    error_lines = [line for line in first if " ERROR " in line]
    assert len(error_lines) == 5
    assert all("upstream_connect_timeout" in line for line in error_lines)


def test_request_rejects_end_before_start() -> None:
    """The query window must be non-empty and forward in time."""
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        make_request(end_time=START - timedelta(minutes=1))


def test_parse_line_extracts_known_fields() -> None:
    """A well-formed error line becomes a fully populated NormalizedLogEvent."""
    line = (
        "2026-08-29T14:14:28Z ERROR payment-service env=production pod=payment-service-1 "
        "req_id=1217 status=504 error=upstream_connect_timeout upstream=payment-processor "
        "configured_connect_timeout_ms=30 connect_elapsed_ms=30"
    )
    event = _parse_line(line)
    assert event is not None
    assert event.level == "ERROR"
    assert event.service == "payment-service"
    assert event.environment == "production"
    assert event.pod == "payment-service-1"
    assert event.http_status == 504
    assert event.exception_type == "upstream_connect_timeout"


@pytest.mark.parametrize(
    "line",
    ["", "not a log line", "2026-08-29T14:14:28Z ERROR payment-service req_id=1"],
)
def test_parse_line_rejects_unknown_shapes(line: str) -> None:
    """Lines missing the minimum shape or the environment field are dropped, not raised."""
    assert _parse_line(line) is None


def test_extract_patterns_counts_errors_pods_and_statuses() -> None:
    """Pattern extraction is a pure count/group operation over normalized events."""
    events = [
        NormalizedLogEvent(
            timestamp=START,
            service="payment-service",
            environment="production",
            level="INFO",
            message="status=200",
            http_status=200,
        ),
        NormalizedLogEvent(
            timestamp=START + timedelta(seconds=4),
            service="payment-service",
            environment="production",
            level="ERROR",
            message="status=504",
            exception_type="upstream_connect_timeout",
            pod="payment-service-1",
            http_status=504,
        ),
        NormalizedLogEvent(
            timestamp=START + timedelta(seconds=8),
            service="payment-service",
            environment="production",
            level="ERROR",
            message="status=504",
            exception_type="upstream_connect_timeout",
            pod="payment-service-2",
            http_status=504,
        ),
    ]
    findings = _extract_patterns(events)
    assert findings["total_events"] == 3
    assert findings["error_count"] == 2
    assert findings["exceptions"] == {"upstream_connect_timeout": 2}
    assert findings["affected_pods"] == ["payment-service-1", "payment-service-2"]
    assert findings["http_statuses"] == {"200": 1, "504": 2}
    assert findings["first_error_at"] < findings["last_error_at"]


@pytest.mark.parametrize(
    ("total_events", "error_count", "expected_confidence"),
    [(0, 0, 0.4), (10, 0, 0.85), (10, 2, 0.9)],
)
def test_build_evidence_confidence_tiers(
    total_events: int, error_count: int, expected_confidence: float
) -> None:
    """Zero results and zero errors are both successful evidence, at different confidence."""
    findings = {
        "total_events": total_events,
        "error_count": error_count,
        "exceptions": {"upstream_connect_timeout": error_count} if error_count else {},
    }
    evidence = _build_evidence(findings, make_request())
    assert len(evidence) == 1
    assert evidence[0].confidence == expected_confidence


@pytest.mark.anyio
async def test_logs_agent_finds_the_buried_timeout_via_offline_tool() -> None:
    """End-to-end: the same scenario as the context-rot notebook, now deterministic."""
    request = make_request()
    agent = LogsAgent(OfflineLogTool())
    evidence = await agent.execute(request)
    assert len(evidence) == 1
    result = evidence[0]
    assert result.investigation_id == request.investigation_id
    assert result.agent_name == "LogsAgent"
    assert result.evidence_type == "LOG"
    assert result.findings["error_count"] == 5
    assert result.findings["total_events"] == 1500
    assert result.findings["exceptions"] == {"upstream_connect_timeout": 5}
    assert result.observed_from == request.start_time
    assert result.observed_to == request.end_time
