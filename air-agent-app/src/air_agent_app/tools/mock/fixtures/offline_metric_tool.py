"""Explicit offline MetricTool; never selected as a fallback for a live failure."""

from air_agent_app.models.metric_evidence import MetricQuery, MetricSample
from air_agent_app.tools.mock.fixtures.metric_series import generate_metric_samples


class OfflineMetricTool:
    """Return fixed, realistic time series instead of querying a real metrics platform.

    This is the only ``MetricTool`` implementation until a real adapter
    (Prometheus, Datadog, Dynatrace) exists (see AGENTS.md): none is
    available to this lesson. It deliberately ignores namespace/cluster/pod
    filters; each requested metric gets a deterministic series anchored to
    the query's own window.
    """

    async def fetch_metrics(self, query: MetricQuery) -> dict[str, list[MetricSample]]:
        """Ignore query filters deliberately; return the same series every time."""
        return {
            metric_name: generate_metric_samples(
                metric_name=metric_name,
                service_name=query.service_name,
                window_start=query.window_start,
                window_end=query.window_end,
                step_seconds=query.step_seconds,
            )
            for metric_name in query.metric_names
        }
