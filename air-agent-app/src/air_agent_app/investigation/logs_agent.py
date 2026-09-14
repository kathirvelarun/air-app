"""Section 4: LogsAgent - deterministic ELF evidence collection.

Flow: LogEvidenceRequest -> LogsQueryBuilder -> LogTool -> raw log lines ->
LogNormalizer -> LogPatternExtractor -> EvidenceBuilder -> Evidence[]. Pattern
counts are computed in Python, never asked of an LLM: software can count
occurrences exactly, and an LLM given the raw dump is exactly the context-rot
failure mode in reference/Context_Engineering_Context_Rot.ipynb.
"""

from datetime import UTC, datetime
from typing import Any

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.investigation.evidence_agent import BaseEvidenceAgent
from air_agent_app.models.evidence import Evidence
from air_agent_app.models.log_evidence import LogEvidenceRequest, LogQuery, NormalizedLogEvent
from air_agent_app.tools.logs.log_tool import LogTool

logger = get_logger(__name__)

_MIN_LINE_TOKENS = 3


def _build_query(request: LogEvidenceRequest) -> LogQuery:
    """Keep only the fields a log-platform query needs, dropping planning context."""
    return LogQuery(
        service_name=request.service_name,
        environment=request.environment,
        start_time=request.start_time,
        end_time=request.end_time,
        namespace=request.namespace,
        cluster=request.cluster,
        pod=request.pod,
        max_results=request.max_results,
    )


def _parse_line(line: str) -> NormalizedLogEvent | None:
    """Parse one ``TIMESTAMP LEVEL SERVICE key=value ...`` log line.

    Returns ``None`` for any line that does not match this shape, rather
    than raising, so a handful of unexpected lines cannot fail the whole
    agent (a single tool response is not "malformed" just because one line
    in it is unexpected).
    """
    tokens = line.split()
    if len(tokens) < _MIN_LINE_TOKENS:
        return None
    raw_timestamp, level, service, *pairs = tokens
    fields = dict(pair.split("=", 1) for pair in pairs if "=" in pair)
    environment = fields.get("env")
    if environment is None:
        return None
    try:
        timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    http_status = fields.get("status")
    return NormalizedLogEvent(
        timestamp=timestamp,
        service=service,
        environment=environment,
        level=level,
        message=" ".join(pairs),
        exception_type=fields.get("error"),
        pod=fields.get("pod"),
        http_status=int(http_status) if http_status and http_status.isdigit() else None,
    )


def _extract_patterns(events: list[NormalizedLogEvent]) -> dict[str, Any]:
    """Compute exception counts, affected pods, status counts, and error span.

    Deterministic by construction: every value here is a count, a sorted
    set, or a min/max timestamp, never an LLM's estimate of the same.
    """
    errors = [event for event in events if event.level == "ERROR"]
    warnings = [event for event in events if event.level == "WARNING"]
    exception_counts: dict[str, int] = {}
    for event in errors:
        key = event.exception_type or "unknown"
        exception_counts[key] = exception_counts.get(key, 0) + 1
    affected_classes = sorted({event.class_name for event in errors if event.class_name})
    affected_pods = sorted({event.pod for event in errors if event.pod})
    http_statuses: dict[str, int] = {}
    for event in events:
        if event.http_status is not None:
            key = str(event.http_status)
            http_statuses[key] = http_statuses.get(key, 0) + 1
    error_timestamps = sorted(event.timestamp for event in errors)
    return {
        "total_events": len(events),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "exceptions": exception_counts,
        "affected_classes": affected_classes,
        "affected_pods": affected_pods,
        "http_statuses": http_statuses,
        "first_error_at": error_timestamps[0].isoformat() if error_timestamps else None,
        "last_error_at": error_timestamps[-1].isoformat() if error_timestamps else None,
    }


def _build_evidence(findings: dict[str, Any], request: LogEvidenceRequest) -> list[Evidence]:
    """Turn findings into exactly one Evidence result, per the guide's example shape.

    Three deterministic tiers, matching Section 4.6's retry-behavior table:
    zero results and zero errors are both successful evidence, just with
    different confidence, never a failure.
    """
    total_events = findings["total_events"]
    error_count = findings["error_count"]
    if total_events == 0:
        title = "No log data returned for the requested window"
        summary = (
            f"The log source returned no events for {request.service_name} "
            f"in {request.environment} for the requested time window."
        )
        confidence = 0.4
    elif error_count == 0:
        title = "No error events observed"
        summary = (
            f"Observed {total_events} log events for {request.service_name} "
            f"in {request.environment} with no ERROR-level events in the requested window."
        )
        confidence = 0.85
    else:
        top_exception, top_count = max(findings["exceptions"].items(), key=lambda item: item[1])
        title = f"{error_count} log error event(s) observed"
        summary = (
            f"Observed {error_count} error events out of {total_events} log events for "
            f"{request.service_name} in {request.environment}; the most common is "
            f"'{top_exception}' ({top_count} occurrences)."
        )
        confidence = 0.9
    return [
        Evidence(
            investigation_id=request.investigation_id,
            agent_name="LogsAgent",
            evidence_type="LOG",
            source_system="ELF",
            title=title,
            summary=summary,
            confidence=confidence,
            findings=findings,
            observed_from=request.start_time,
            observed_to=request.end_time,
            collected_at=datetime.now(UTC),
        )
    ]


class LogsAgent(BaseEvidenceAgent[LogEvidenceRequest, list[str], list[NormalizedLogEvent]]):
    """ELF evidence specialist. States facts only; never a root cause or a fix."""

    def __init__(self, tool: LogTool) -> None:
        """Inject the log-platform tool adapter; never construct one internally."""
        self._tool = tool

    async def collect(self, request: LogEvidenceRequest) -> list[str]:
        """Build a vendor-agnostic query and fetch raw log lines through it."""
        logger.info(
            "LogsAgent collection started investigation_id=%s tool=%s",
            request.investigation_id,
            type(self._tool).__name__,
        )
        return await self._tool.fetch_logs(_build_query(request))

    def normalize(self, raw: list[str]) -> list[NormalizedLogEvent]:
        """Parse raw lines, silently dropping any that do not match the known shape."""
        events: list[NormalizedLogEvent] = []
        skipped = 0
        for line in raw:
            event = _parse_line(line)
            if event is None:
                skipped += 1
                continue
            events.append(event)
        if skipped:
            logger.debug("LogsAgent skipped unparsable lines count=%s", skipped)
        return events

    def summarize(
        self,
        normalized: list[NormalizedLogEvent],
        request: LogEvidenceRequest,
    ) -> list[Evidence]:
        """Extract deterministic patterns and build the single Evidence result."""
        findings = _extract_patterns(normalized)
        evidence = _build_evidence(findings, request)
        logger.info(
            "LogsAgent collection completed investigation_id=%s error_count=%s total_events=%s",
            request.investigation_id,
            findings["error_count"],
            findings["total_events"],
        )
        return evidence
