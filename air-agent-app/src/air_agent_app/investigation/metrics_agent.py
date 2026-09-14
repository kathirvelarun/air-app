"""Section 5: MetricsAgent - deterministic runtime-health evidence collection.

Flow: MetricEvidenceRequest -> MetricsQueryBuilder -> MetricTool -> raw
samples -> MetricNormalizer -> MetricAnalyzer -> MetricHealthEvaluator ->
MetricEvidenceBuilder -> Evidence[]. A metric's absolute value is often
ambiguous (Section 5.5); every finding here is a baseline-vs-incident-window
comparison, never a bare snapshot.
"""

from datetime import UTC, datetime
from typing import Any

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.investigation.evidence_agent import BaseEvidenceAgent
from air_agent_app.models.evidence import Evidence
from air_agent_app.models.metric_evidence import (
    MetricEvidenceRequest,
    MetricQuery,
    MetricSample,
    NormalizedMetricSeries,
)
from air_agent_app.tools.metrics.metric_tool import MetricTool

logger = get_logger(__name__)

DEFAULT_METRICS = ("cpu_pct", "memory_pct", "http_5xx_rate", "p95_latency_ms")

# A metric more than this far from its baseline average, in either
# direction, is flagged UNHEALTHY. Not specified by the guide; chosen so
# the Section 5.5 example table classifies correctly (CPU +10.7% and Memory
# +3.3% stay HEALTHY; HTTP 5xx +1450% and P95 latency +1067% are UNHEALTHY).
_UNHEALTHY_PERCENT_CHANGE_THRESHOLD = 50.0

# A metric at or above this absolute level is UNHEALTHY regardless of its
# relative change from baseline. Without this, a metric that was already
# elevated throughout the baseline window (e.g. memory climbing steadily for
# hours before the requested window even starts) reads as a small relative
# change and is missed by the threshold above alone -- exactly the
# cache-service memory trend in the notebook's decoy.
_ABSOLUTE_CRITICAL_THRESHOLDS: dict[str, float] = {
    "cpu_pct": 0.85,
    "memory_pct": 0.85,
    "http_5xx_rate": 0.05,
    "p95_latency_ms": 1000.0,
    # Disk-exhaustion demo scenario (ledger-service): a filesystem this full
    # is critical regardless of how gradually it got there.
    "disk_usage_pct": 0.90,
}

RawMetrics = tuple[MetricQuery, dict[str, list[MetricSample]]]


def _build_query(request: MetricEvidenceRequest) -> MetricQuery:
    """Derive a baseline window: same length as the incident window, immediately before it."""
    incident_span = request.end_time - request.start_time
    return MetricQuery(
        service_name=request.service_name,
        environment=request.environment,
        window_start=request.start_time - incident_span,
        window_end=request.end_time,
        metric_names=list(request.required_metrics) or list(DEFAULT_METRICS),
        namespace=request.namespace,
        cluster=request.cluster,
        pod=request.pod,
        step_seconds=request.step_seconds,
    )


def _window_stats(samples: list[MetricSample]) -> dict[str, float | int | None]:
    """Compute count, min, max, average, first, and last value for one window."""
    if not samples:
        return {
            "sample_count": 0,
            "min": None,
            "max": None,
            "avg": None,
            "first": None,
            "last": None,
        }
    values = [sample.value for sample in samples]
    return {
        "sample_count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "first": values[0],
        "last": values[-1],
    }


def _percent_change(baseline_avg: float | None, current_avg: float | None) -> float | None:
    """Return the signed percent change from baseline to current, or None if incomparable."""
    if baseline_avg is None or current_avg is None:
        return None
    if baseline_avg == 0:
        return None if current_avg == 0 else float("inf")
    return ((current_avg - baseline_avg) / baseline_avg) * 100


def _classify_health(
    metric_name: str,
    current_avg: float | None,
    percent_change: float | None,
) -> str:
    """Flag a critical absolute level or a large relative deviation as UNHEALTHY.

    Checked in this order because an absolute breach is unambiguous evidence
    on its own, even when ``percent_change`` is small, None, or unavailable.
    """
    absolute_limit = _ABSOLUTE_CRITICAL_THRESHOLDS.get(metric_name)
    if absolute_limit is not None and current_avg is not None and current_avg >= absolute_limit:
        return "UNHEALTHY"
    if percent_change is None:
        return "UNKNOWN"
    return "UNHEALTHY" if abs(percent_change) > _UNHEALTHY_PERCENT_CHANGE_THRESHOLD else "HEALTHY"


def _extract_findings(
    series_list: list[NormalizedMetricSeries],
    boundary: datetime,
) -> dict[str, Any]:
    """Split each series at the incident boundary and compute per-metric findings."""
    findings: dict[str, Any] = {}
    for series in series_list:
        baseline_samples = [sample for sample in series.samples if sample.timestamp < boundary]
        current_samples = [sample for sample in series.samples if sample.timestamp >= boundary]
        baseline_stats = _window_stats(baseline_samples)
        current_stats = _window_stats(current_samples)
        change = _percent_change(baseline_stats["avg"], current_stats["avg"])
        delta = (
            current_stats["avg"] - baseline_stats["avg"]
            if baseline_stats["avg"] is not None and current_stats["avg"] is not None
            else None
        )
        findings[series.metric_name] = {
            "baseline_avg": baseline_stats["avg"],
            "current_avg": current_stats["avg"],
            "min": current_stats["min"],
            "max": current_stats["max"],
            "delta": delta,
            "percent_change": change,
            "sample_count": current_stats["sample_count"],
            "health": _classify_health(series.metric_name, current_stats["avg"], change),
        }
    return findings


def _build_evidence(findings: dict[str, Any], request: MetricEvidenceRequest) -> list[Evidence]:
    """Turn per-metric findings into exactly one Evidence result.

    Three deterministic tiers, mirroring LogsAgent: zero samples and all-
    healthy are both successful evidence, never a failure, just lower or
    higher confidence than a genuine deviation.
    """
    total_samples = sum(entry["sample_count"] for entry in findings.values())
    unhealthy = sorted(name for name, entry in findings.items() if entry["health"] == "UNHEALTHY")
    if total_samples == 0:
        title = "No metric data returned for the requested window"
        summary = (
            f"The metrics source returned no samples for {request.service_name} "
            f"in {request.environment} for the requested time window."
        )
        confidence = 0.4
    elif not unhealthy:
        title = "All requested metrics are healthy"
        summary = (
            f"All {len(findings)} requested metrics for {request.service_name} "
            f"in {request.environment} stayed within normal range of their baseline."
        )
        confidence = 0.85
    else:
        title = f"{len(unhealthy)} metric(s) show unhealthy deviation from baseline"
        summary = (
            f"{', '.join(unhealthy)} deviated from baseline for {request.service_name} "
            f"in {request.environment}; other requested metrics stayed normal."
        )
        confidence = 0.99
    return [
        Evidence(
            investigation_id=request.investigation_id,
            agent_name="MetricsAgent",
            evidence_type="METRIC",
            source_system="Prometheus",
            title=title,
            summary=summary,
            confidence=confidence,
            findings=findings,
            observed_from=request.start_time,
            observed_to=request.end_time,
            collected_at=datetime.now(UTC),
        )
    ]


class MetricsAgent(
    BaseEvidenceAgent[MetricEvidenceRequest, RawMetrics, list[NormalizedMetricSeries]]
):
    """Runtime-health evidence specialist. States facts only; never a root cause or a fix."""

    def __init__(self, tool: MetricTool) -> None:
        """Inject the metrics-platform tool adapter; never construct one internally."""
        self._tool = tool

    async def collect(self, request: MetricEvidenceRequest) -> RawMetrics:
        """Build a vendor-agnostic query and fetch raw samples through it."""
        query = _build_query(request)
        logger.info(
            "MetricsAgent collection started investigation_id=%s tool=%s metrics=%s",
            request.investigation_id,
            type(self._tool).__name__,
            ",".join(query.metric_names),
        )
        series = await self._tool.fetch_metrics(query)
        return query, series

    def normalize(self, raw: RawMetrics) -> list[NormalizedMetricSeries]:
        """Attach service/environment context to each metric's raw samples."""
        query, series_by_metric = raw
        return [
            NormalizedMetricSeries(
                metric_name=metric_name,
                service=query.service_name,
                environment=query.environment,
                samples=samples,
            )
            for metric_name, samples in series_by_metric.items()
        ]

    def summarize(
        self,
        normalized: list[NormalizedMetricSeries],
        request: MetricEvidenceRequest,
    ) -> list[Evidence]:
        """Compute baseline-vs-incident findings per metric and build the Evidence result."""
        findings = _extract_findings(normalized, boundary=request.start_time)
        evidence = _build_evidence(findings, request)
        logger.info(
            "MetricsAgent collection completed investigation_id=%s unhealthy=%s",
            request.investigation_id,
            sum(1 for entry in findings.values() if entry["health"] == "UNHEALTHY"),
        )
        return evidence
