"""Simulate deterministic metric time series for the demo services.

Continues reference/Context_Engineering_Context_Rot.ipynb: ``payment-service``
gets the real signal (HTTP 5xx and p95 latency spike after a connection
timeout regression, matching the guide's own Section 5.6 example numbers
exactly). ``cache-service`` gets the notebook's decoy (a genuine but
unrelated memory climb toward 91%, mirroring its ``apm_report()``) - a real
anomaly, just not the cause of the payment-service incident.

Two more demo scenarios, each a different root-cause class from
``payment-service``'s config regression:

- ``web-ui``: only ``http_5xx_rate`` deviates (parse failures surfacing as
  500s); ``p95_latency_ms`` stays healthy, since nothing is actually slow -
  the downstream call itself succeeds.
- ``ledger-service``: ``disk_usage_pct`` climbs to the exact 99.8% figure
  the incident describes, and ``http_5xx_rate`` deviates too (write
  failures surfacing as errors); latency stays healthy since ENOSPC fails
  fast, not slow.

Any other service gets stable, unremarkable values. MetricsAgent has no
way to tell these apart on its own; that arbitration is the Evidence
Aggregator's job, not built yet (see
docs/section_03_evidence_collection_plan.md).
"""

from datetime import datetime, timedelta

from air_agent_app.models.metric_evidence import MetricSample

# (service_name, metric_name) -> (baseline_avg, incident_avg). Values are the
# same units the guide's Section 5.5/5.6 tables use: fractions for rates
# (0.28 = 28%), milliseconds for latency.
_METRIC_PROFILES: dict[tuple[str, str], tuple[float, float]] = {
    ("payment-service", "cpu_pct"): (0.28, 0.31),
    ("payment-service", "memory_pct"): (0.60, 0.62),
    ("payment-service", "http_5xx_rate"): (0.012, 0.186),
    ("payment-service", "p95_latency_ms"): (240.0, 2800.0),
    ("cache-service", "cpu_pct"): (0.31, 0.34),
    ("cache-service", "memory_pct"): (0.62, 0.91),
    ("cache-service", "http_5xx_rate"): (0.01, 0.01),
    ("cache-service", "p95_latency_ms"): (180.0, 190.0),
    ("web-ui", "cpu_pct"): (0.25, 0.27),
    ("web-ui", "memory_pct"): (0.40, 0.41),
    ("web-ui", "http_5xx_rate"): (0.010, 0.140),
    ("web-ui", "p95_latency_ms"): (150.0, 165.0),
    ("ledger-service", "cpu_pct"): (0.30, 0.33),
    ("ledger-service", "memory_pct"): (0.55, 0.58),
    ("ledger-service", "http_5xx_rate"): (0.010, 0.090),
    ("ledger-service", "p95_latency_ms"): (180.0, 195.0),
    ("ledger-service", "disk_usage_pct"): (0.62, 0.998),
}

# Per-metric-name fallback for any service not listed above, so an unknown
# service never lands on a value that's meaningless for that metric's scale
# (e.g. a flat 0.5 would read as a 50% error rate for http_5xx_rate).
_DEFAULT_METRIC_PROFILES: dict[str, tuple[float, float]] = {
    "cpu_pct": (0.30, 0.30),
    "memory_pct": (0.55, 0.55),
    "http_5xx_rate": (0.01, 0.01),
    "p95_latency_ms": (200.0, 200.0),
    "disk_usage_pct": (0.55, 0.55),
}
_FALLBACK_PROFILE = (0.5, 0.5)


def generate_metric_samples(
    metric_name: str,
    service_name: str,
    window_start: datetime,
    window_end: datetime,
    step_seconds: int = 60,
) -> list[MetricSample]:
    """Return deterministic samples spanning ``[window_start, window_end]``.

    The window's midpoint is treated as the incident boundary: samples
    before it oscillate around the baseline average, samples at or after it
    oscillate around the incident-window average. This lines up with how
    ``_build_query`` in ``investigation/metrics_agent.py`` constructs the
    window (baseline span immediately preceding the incident span, of equal
    length), so this function does not need the boundary passed in
    separately. Unknown (service, metric) combinations get a flat, healthy
    default so an unrecognized request never fails.
    """
    baseline_avg, incident_avg = _METRIC_PROFILES.get(
        (service_name, metric_name),
        _DEFAULT_METRIC_PROFILES.get(metric_name, _FALLBACK_PROFILE),
    )
    # Fraction-style metrics (cpu/memory/error-rate/disk, all expressed as
    # 0.0-1.0) can never physically exceed 100%; latency-style metrics have
    # no such ceiling. Both profile values being <= 1.0 is how this
    # generator tells the two apart, since no metric name is threaded in.
    is_fraction_metric = baseline_avg <= 1.0 and incident_avg <= 1.0
    boundary = window_start + (window_end - window_start) / 2
    samples: list[MetricSample] = []
    timestamp = window_start
    index = 0
    while timestamp <= window_end:
        target = incident_avg if timestamp >= boundary else baseline_avg
        # A deterministic +/-5% oscillation that averages to ~0 over any full
        # 7-sample cycle, so long windows converge close to `target` without
        # every sample being identical.
        jitter = target * 0.05 * (((index % 7) - 3) / 3)
        value = target + jitter
        if is_fraction_metric:
            value = min(max(value, 0.0), 1.0)
        samples.append(MetricSample(timestamp=timestamp, value=round(value, 6)))
        timestamp += timedelta(seconds=step_seconds)
        index += 1
    return samples
