"""TracesAgent's tool boundary: tracing-platform specifics stay behind this interface."""

from typing import Protocol

from air_agent_app.models.trace_evidence import TraceQuery


class TraceTool(Protocol):
    """Anything that can answer a vendor-agnostic TraceQuery with raw span lines."""

    async def fetch_traces(self, query: TraceQuery) -> list[str]:
        """Return raw, unparsed span lines for the requested window."""
        ...
