"""TracesAgent: deterministic dump generation, normalization, and evidence shape."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from air_agent_app.investigation.traces_agent import (
    TracesAgent,
    _build_evidence,
    _extract_patterns,
    _parse_span_line,
)
from air_agent_app.models.trace_evidence import TraceEvidenceRequest
from air_agent_app.tools.mock.fixtures.offline_trace_tool import OfflineTraceTool
from air_agent_app.tools.mock.fixtures.trace_dump import generate_trace_dump

START = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


def make_request(**overrides: object) -> TraceEvidenceRequest:
    """Build a valid TraceEvidenceRequest, overriding only what a test needs."""
    fields: dict[str, object] = {
        "investigation_id": uuid4(),
        "service_name": "payment-service",
        "environment": "production",
        "start_time": START,
        "end_time": START + timedelta(hours=2),
    }
    fields.update(overrides)
    return TraceEvidenceRequest.model_validate(fields)


def test_dump_is_deterministic_with_ten_sparse_error_spans() -> None:
    """Same inputs produce the same 3000 spans with exactly 10 buried error spans."""
    first = generate_trace_dump(start=START)
    second = generate_trace_dump(start=START)
    assert first == second
    assert len(first) == 3000
    error_lines = [line for line in first if "status=ERROR" in line]
    assert len(error_lines) == 10


def test_request_rejects_end_before_start() -> None:
    """The query window must be non-empty and forward in time."""
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        make_request(end_time=START - timedelta(minutes=1))


def test_parse_span_line_extracts_known_fields() -> None:
    """A well-formed error span line becomes a fully populated NormalizedSpan."""
    line = (
        "2026-08-29T14:14:28Z trace_id=tr-1217 span_id=tr-1217-inner "
        "parent_span_id=tr-1217-outer service=payment-service env=production "
        "operation=call_payment_processor duration_ms=30012 status=ERROR "
        "error=upstream_connect_timeout"
    )
    span = _parse_span_line(line)
    assert span is not None
    assert span.trace_id == "tr-1217"
    assert span.parent_span_id == "tr-1217-outer"
    assert span.operation == "call_payment_processor"
    assert span.duration_ms == 30012.0
    assert span.status == "ERROR"
    assert span.error_type == "upstream_connect_timeout"


def test_parse_span_line_reads_root_span_parent_as_none() -> None:
    """A root span's ``parent_span_id=-`` becomes None, not the literal string."""
    line = (
        "2026-08-29T14:14:28Z trace_id=tr-1217 span_id=tr-1217-outer parent_span_id=- "
        "service=payment-service env=production operation=handle_payment "
        "duration_ms=130 status=OK"
    )
    span = _parse_span_line(line)
    assert span is not None
    assert span.parent_span_id is None


@pytest.mark.parametrize("line", ["", "not a span line", "2026-08-29T14:14:28Z trace_id=tr-1"])
def test_parse_span_line_rejects_unknown_shapes(line: str) -> None:
    """Lines missing required fields are dropped, not raised."""
    assert _parse_span_line(line) is None


def test_extract_patterns_identifies_bottleneck_operation() -> None:
    """Pattern extraction groups by operation and finds the error/slow concentration."""
    spans = [
        _parse_span_line(
            "2026-08-29T14:14:28Z trace_id=t1 span_id=t1-outer parent_span_id=- "
            "service=payment-service env=production operation=handle_payment "
            "duration_ms=30245 status=ERROR error=upstream_timeout"
        ),
        _parse_span_line(
            "2026-08-29T14:14:28Z trace_id=t1 span_id=t1-inner parent_span_id=t1-outer "
            "service=payment-service env=production operation=call_payment_processor "
            "duration_ms=30012 status=ERROR error=upstream_connect_timeout"
        ),
        _parse_span_line(
            "2026-08-29T14:14:32Z trace_id=t2 span_id=t2-outer parent_span_id=- "
            "service=payment-service env=production operation=handle_payment "
            "duration_ms=120 status=OK"
        ),
    ]
    findings = _extract_patterns(spans, slow_threshold_ms=1000.0)
    assert findings["total_spans"] == 3
    assert findings["error_span_count"] == 2
    assert findings["slow_span_count"] == 2
    assert findings["primary_error_operation"] == "handle_payment"
    # call_payment_processor's only sample is its 30012ms error, so its
    # average is higher than handle_payment's average of one error and one
    # healthy (120ms) sample -- this is a property of the averaging, not a
    # claim that call_payment_processor is "the" bottleneck operation.
    assert findings["slowest_operation"] == "call_payment_processor"
    assert findings["operations"]["call_payment_processor"]["error_count"] == 1


@pytest.mark.parametrize(
    ("total_spans", "error_count", "slow_count", "expected_confidence"),
    [(0, 0, 0, 0.4), (10, 0, 0, 0.85), (10, 2, 2, 0.9)],
)
def test_build_evidence_confidence_tiers(
    total_spans: int, error_count: int, slow_count: int, expected_confidence: float
) -> None:
    """Zero spans and zero errors/slow spans are successful evidence too, at lower confidence."""
    findings = {
        "total_spans": total_spans,
        "error_span_count": error_count,
        "slow_span_count": slow_count,
        "primary_error_operation": "handle_payment" if error_count else None,
    }
    evidence = _build_evidence(findings, make_request())
    assert len(evidence) == 1
    assert evidence[0].confidence == expected_confidence


@pytest.mark.anyio
async def test_traces_agent_finds_the_buried_timeout_via_offline_tool() -> None:
    """End-to-end: the same scenario as LogsAgent, now visible as a slow, erroring span chain."""
    request = make_request()
    agent = TracesAgent(OfflineTraceTool())
    evidence = await agent.execute(request)
    assert len(evidence) == 1
    result = evidence[0]
    assert result.investigation_id == request.investigation_id
    assert result.agent_name == "TracesAgent"
    assert result.evidence_type == "TRACE"
    assert result.findings["error_span_count"] == 10
    bottleneck_operations = {"handle_payment", "call_payment_processor"}
    assert result.findings["primary_error_operation"] in bottleneck_operations
    assert result.observed_from == request.start_time
    assert result.observed_to == request.end_time
