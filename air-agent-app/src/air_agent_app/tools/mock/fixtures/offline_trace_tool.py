"""Explicit offline TraceTool; never selected as a fallback for a live failure."""

from air_agent_app.models.trace_evidence import TraceQuery
from air_agent_app.tools.mock.fixtures.trace_dump import generate_trace_dump


class OfflineTraceTool:
    """Return a fixed, realistic trace dump instead of querying a real tracing backend.

    This is the only ``TraceTool`` implementation until a real adapter
    (Jaeger, Tempo, OpenTelemetry Collector) exists (see AGENTS.md): none is
    available to this lesson. It deliberately ignores namespace/cluster/pod
    and operation filters; it always returns the same simulated dump,
    anchored to the query's own start time so timestamps line up.
    """

    async def fetch_traces(self, query: TraceQuery) -> list[str]:
        """Ignore query filters deliberately; return the same dump every time."""
        return generate_trace_dump(
            service_name=query.service_name,
            environment=query.environment,
            start=query.start_time,
        )
