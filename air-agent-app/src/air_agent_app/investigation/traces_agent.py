"""TracesAgent - deterministic distributed-tracing evidence collection.

Not part of the guide's four defined evidence agents (Sections 4-7); this is
a locally designed fifth specialist built to the same shape as LogsAgent and
MetricsAgent: TraceEvidenceRequest -> TracesQueryBuilder -> TraceTool -> raw
span lines -> normalize -> deterministic per-operation pattern extraction ->
EvidenceBuilder -> Evidence[]. See docs/extension_01_traces_agent.md. As with
LogsAgent, pattern counts are computed in Python, never asked of an LLM.
"""

from datetime import UTC, datetime
from typing import Any

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.investigation.evidence_agent import BaseEvidenceAgent
from air_agent_app.investigation.raw_line_parsing import parse_key_value_line
from air_agent_app.models.evidence import Evidence
from air_agent_app.models.trace_evidence import NormalizedSpan, TraceEvidenceRequest, TraceQuery
from air_agent_app.tools.traces.trace_tool import TraceTool

logger = get_logger(__name__)

_REQUIRED_FIELDS = ("trace_id", "span_id", "service", "env", "operation", "duration_ms", "status")


def _build_query(request: TraceEvidenceRequest) -> TraceQuery:
    """Keep only the fields a tracing-platform query needs, dropping planning context."""
    return TraceQuery(
        service_name=request.service_name,
        environment=request.environment,
        start_time=request.start_time,
        end_time=request.end_time,
        operation_names=list(request.required_operations),
        namespace=request.namespace,
        cluster=request.cluster,
        pod=request.pod,
        max_results=request.max_results,
    )


def _parse_span_line(line: str) -> NormalizedSpan | None:
    """Parse one ``TIMESTAMP key=value ...`` span line.

    Returns ``None`` for any line missing a required field or an unparsable
    timestamp/duration, rather than raising, so a handful of unexpected
    lines cannot fail the whole agent.
    """
    parsed = parse_key_value_line(line)
    if parsed is None:
        return None
    timestamp, fields = parsed
    if any(key not in fields for key in _REQUIRED_FIELDS):
        return None
    try:
        duration_ms = float(fields["duration_ms"])
    except ValueError:
        return None
    parent_span_id = fields.get("parent_span_id")
    return NormalizedSpan(
        trace_id=fields["trace_id"],
        span_id=fields["span_id"],
        parent_span_id=None if parent_span_id in (None, "-") else parent_span_id,
        service=fields["service"],
        environment=fields["env"],
        operation=fields["operation"],
        timestamp=timestamp,
        duration_ms=duration_ms,
        status=fields["status"],
        error_type=fields.get("error"),
    )


def _extract_patterns(spans: list[NormalizedSpan], slow_threshold_ms: float) -> dict[str, Any]:
    """Compute per-operation counts, durations, and error concentration.

    Deterministic by construction: every value here is a count, an average,
    a max, or a min/max timestamp, never an LLM's estimate of the same.
    """
    errors = [span for span in spans if span.status == "ERROR"]
    slow = [span for span in spans if span.duration_ms > slow_threshold_ms]
    totals: dict[str, dict[str, float]] = {}
    for span in spans:
        stats = totals.setdefault(
            span.operation,
            {"count": 0, "total_duration_ms": 0.0, "max_duration_ms": 0.0, "error_count": 0},
        )
        stats["count"] += 1
        stats["total_duration_ms"] += span.duration_ms
        stats["max_duration_ms"] = max(stats["max_duration_ms"], span.duration_ms)
        if span.status == "ERROR":
            stats["error_count"] += 1
    operations = {
        name: {
            "count": int(stats["count"]),
            "avg_duration_ms": stats["total_duration_ms"] / stats["count"],
            "max_duration_ms": stats["max_duration_ms"],
            "error_count": int(stats["error_count"]),
        }
        for name, stats in totals.items()
    }
    primary_error_operation = (
        max(operations.items(), key=lambda item: item[1]["error_count"])[0] if errors else None
    )
    slowest_operation = (
        max(operations.items(), key=lambda item: item[1]["avg_duration_ms"])[0]
        if operations
        else None
    )
    error_timestamps = sorted(span.timestamp for span in errors)
    return {
        "total_spans": len(spans),
        "error_span_count": len(errors),
        "slow_span_count": len(slow),
        "operations": operations,
        "primary_error_operation": primary_error_operation,
        "slowest_operation": slowest_operation,
        "first_error_at": error_timestamps[0].isoformat() if error_timestamps else None,
        "last_error_at": error_timestamps[-1].isoformat() if error_timestamps else None,
    }


def _build_evidence(findings: dict[str, Any], request: TraceEvidenceRequest) -> list[Evidence]:
    """Turn findings into exactly one Evidence result, mirroring LogsAgent's shape.

    Three deterministic tiers: zero spans and zero errors/slow spans are
    both successful evidence, never a failure.
    """
    total_spans = findings["total_spans"]
    error_count = findings["error_span_count"]
    slow_count = findings["slow_span_count"]
    if total_spans == 0:
        title = "No trace data returned for the requested window"
        summary = (
            f"The tracing source returned no spans for {request.service_name} "
            f"in {request.environment} for the requested time window."
        )
        confidence = 0.4
    elif error_count == 0 and slow_count == 0:
        title = "All traces healthy"
        summary = (
            f"Observed {total_spans} spans for {request.service_name} in "
            f"{request.environment} with no errors or spans over "
            f"{request.slow_span_threshold_ms:.0f}ms."
        )
        confidence = 0.85
    else:
        title = f"{error_count} error span(s) observed"
        summary = (
            f"Observed {error_count} error spans and {slow_count} spans over "
            f"{request.slow_span_threshold_ms:.0f}ms for {request.service_name} in "
            f"{request.environment}; concentrated in '{findings['primary_error_operation']}'."
        )
        confidence = 0.9
    return [
        Evidence(
            investigation_id=request.investigation_id,
            agent_name="TracesAgent",
            evidence_type="TRACE",
            source_system="Jaeger",
            title=title,
            summary=summary,
            confidence=confidence,
            findings=findings,
            observed_from=request.start_time,
            observed_to=request.end_time,
            collected_at=datetime.now(UTC),
        )
    ]


class TracesAgent(BaseEvidenceAgent[TraceEvidenceRequest, list[str], list[NormalizedSpan]]):
    """Distributed-tracing evidence specialist. States facts only, never a root cause."""

    def __init__(self, tool: TraceTool) -> None:
        """Inject the tracing-platform tool adapter; never construct one internally."""
        self._tool = tool

    async def collect(self, request: TraceEvidenceRequest) -> list[str]:
        """Build a vendor-agnostic query and fetch raw span lines through it."""
        logger.info(
            "TracesAgent collection started investigation_id=%s tool=%s",
            request.investigation_id,
            type(self._tool).__name__,
        )
        return await self._tool.fetch_traces(_build_query(request))

    def normalize(self, raw: list[str]) -> list[NormalizedSpan]:
        """Parse raw lines, silently dropping any that do not match the known shape."""
        spans: list[NormalizedSpan] = []
        skipped = 0
        for line in raw:
            span = _parse_span_line(line)
            if span is None:
                skipped += 1
                continue
            spans.append(span)
        if skipped:
            logger.debug("TracesAgent skipped unparsable lines count=%s", skipped)
        return spans

    def summarize(
        self,
        normalized: list[NormalizedSpan],
        request: TraceEvidenceRequest,
    ) -> list[Evidence]:
        """Extract deterministic per-operation patterns and build the Evidence result."""
        findings = _extract_patterns(normalized, request.slow_span_threshold_ms)
        evidence = _build_evidence(findings, request)
        logger.info(
            "TracesAgent collection completed investigation_id=%s error_span_count=%s "
            "total_spans=%s",
            request.investigation_id,
            findings["error_span_count"],
            findings["total_spans"],
        )
        return evidence
