"""MetricsAgent: deterministic series generation, baseline comparison, and health."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from air_agent_app.investigation.metrics_agent import (
    MetricsAgent,
    _build_evidence,
    _classify_health,
    _extract_findings,
    _percent_change,
    _window_stats,
)
from air_agent_app.models.metric_evidence import (
    MetricEvidenceRequest,
    MetricSample,
    NormalizedMetricSeries,
)
from air_agent_app.tools.mock.fixtures.metric_series import generate_metric_samples
from air_agent_app.tools.mock.fixtures.offline_metric_tool import OfflineMetricTool

START = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


def make_request(**overrides: object) -> MetricEvidenceRequest:
    """Build a valid MetricEvidenceRequest, overriding only what a test needs."""
    fields: dict[str, object] = {
        "investigation_id": uuid4(),
        "service_name": "payment-service",
        "environment": "production",
        "start_time": START,
        "end_time": START + timedelta(hours=2),
    }
    fields.update(overrides)
    return MetricEvidenceRequest.model_validate(fields)


def test_request_rejects_end_before_start() -> None:
    """The incident window must be non-empty and forward in time."""
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        make_request(end_time=START - timedelta(minutes=1))


def test_generated_series_shifts_at_the_window_midpoint() -> None:
    """Samples before the midpoint target the baseline average; at/after target current."""
    window_end = START + timedelta(hours=2)
    samples = generate_metric_samples("http_5xx_rate", "payment-service", START, window_end)
    midpoint = START + (window_end - START) / 2
    before = [s.value for s in samples if s.timestamp < midpoint]
    after = [s.value for s in samples if s.timestamp >= midpoint]
    assert sum(before) / len(before) < 0.05
    assert sum(after) / len(after) > 0.1


def test_unknown_service_and_metric_get_a_sane_default() -> None:
    """An unrecognized (service, metric) pair never lands on a nonsensical value."""
    end = START + timedelta(hours=1)
    samples = generate_metric_samples("http_5xx_rate", "unknown-service", START, end)
    assert all(0 <= s.value <= 0.1 for s in samples)


def test_window_stats_handles_empty_and_populated_samples() -> None:
    """Empty windows report zero samples instead of raising."""
    assert _window_stats([])["sample_count"] == 0
    samples = [MetricSample(timestamp=START, value=1.0), MetricSample(timestamp=START, value=3.0)]
    stats = _window_stats(samples)
    assert stats == {
        "sample_count": 2,
        "min": 1.0,
        "max": 3.0,
        "avg": 2.0,
        "first": 1.0,
        "last": 3.0,
    }


@pytest.mark.parametrize(
    ("baseline", "current", "expected"),
    [(0.28, 0.31, pytest.approx(10.714, rel=1e-3)), (0.0, 0.0, None), (0.0, 1.0, float("inf"))],
)
def test_percent_change(baseline: float, current: float, expected: object) -> None:
    """Percent change handles the zero-baseline edge cases explicitly."""
    assert _percent_change(baseline, current) == expected


def test_classify_health_absolute_threshold_overrides_small_relative_change() -> None:
    """A metric already critical in absolute terms is unhealthy even with modest relative drift.

    This is the cache-service decoy case: memory was already elevated
    throughout the baseline window, so the relative change alone understates
    the severity.
    """
    assert _classify_health("memory_pct", 0.91, 5.0) == "UNHEALTHY"
    assert _classify_health("memory_pct", 0.40, 5.0) == "HEALTHY"
    assert _classify_health("http_5xx_rate", 0.01, None) == "UNKNOWN"


def test_extract_findings_splits_at_the_boundary() -> None:
    """Findings are computed per metric from samples split at the given boundary."""
    boundary = START + timedelta(hours=1)
    series = [
        NormalizedMetricSeries(
            metric_name="cpu_pct",
            service="payment-service",
            environment="production",
            samples=[
                MetricSample(timestamp=START, value=0.2),
                MetricSample(timestamp=boundary, value=0.9),
            ],
        )
    ]
    findings = _extract_findings(series, boundary)
    assert findings["cpu_pct"]["baseline_avg"] == 0.2
    assert findings["cpu_pct"]["current_avg"] == 0.9
    assert findings["cpu_pct"]["health"] == "UNHEALTHY"


def test_build_evidence_confidence_tiers() -> None:
    """Zero samples, all-healthy, and any-unhealthy each get a distinct confidence."""
    request = make_request()
    zero = _build_evidence({"cpu_pct": {"sample_count": 0, "health": "UNKNOWN"}}, request)
    healthy = _build_evidence({"cpu_pct": {"sample_count": 10, "health": "HEALTHY"}}, request)
    unhealthy = _build_evidence({"cpu_pct": {"sample_count": 10, "health": "UNHEALTHY"}}, request)
    assert zero[0].confidence == 0.4
    assert healthy[0].confidence == 0.85
    assert unhealthy[0].confidence == 0.99


@pytest.mark.anyio
async def test_metrics_agent_finds_the_real_signal_via_offline_tool() -> None:
    """End-to-end: payment-service's HTTP 5xx and latency spike are flagged, CPU/memory are not."""
    request = make_request()
    agent = MetricsAgent(OfflineMetricTool())
    evidence = await agent.execute(request)
    assert len(evidence) == 1
    findings = evidence[0].findings
    assert findings["http_5xx_rate"]["health"] == "UNHEALTHY"
    assert findings["p95_latency_ms"]["health"] == "UNHEALTHY"
    assert findings["cpu_pct"]["health"] == "HEALTHY"
    assert findings["memory_pct"]["health"] == "HEALTHY"


@pytest.mark.anyio
async def test_metrics_agent_flags_the_decoy_as_its_own_unrelated_anomaly() -> None:
    """cache-service's memory climb is real evidence, correctly scoped to cache-service."""
    request = make_request(service_name="cache-service")
    agent = MetricsAgent(OfflineMetricTool())
    evidence = await agent.execute(request)
    findings = evidence[0].findings
    assert findings["memory_pct"]["health"] == "UNHEALTHY"
    assert findings["http_5xx_rate"]["health"] == "HEALTHY"
    assert findings["p95_latency_ms"]["health"] == "HEALTHY"
