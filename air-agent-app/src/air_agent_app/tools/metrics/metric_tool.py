"""MetricsAgent's tool boundary: metrics-platform specifics stay behind this interface."""

from typing import Protocol

from air_agent_app.models.metric_evidence import MetricQuery, MetricSample


class MetricTool(Protocol):
    """Anything that can answer a vendor-agnostic MetricQuery with raw samples."""

    async def fetch_metrics(self, query: MetricQuery) -> dict[str, list[MetricSample]]:
        """Return raw samples per requested metric name for the query window."""
        ...
