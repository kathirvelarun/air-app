"""Explicit offline LogTool; never selected as a fallback for a live failure."""

from air_agent_app.models.log_evidence import LogQuery
from air_agent_app.tools.mock.fixtures.log_dump import generate_application_log_dump


class OfflineLogTool:
    """Return a fixed, realistic log dump instead of querying a real ELF cluster.

    This is the only ``LogTool`` implementation until a real log-platform
    adapter exists (see AGENTS.md): no ELF cluster is available to this
    lesson. It deliberately ignores namespace/cluster/pod filters; it always
    returns the same simulated dump, anchored to the query's own start time
    so timestamps line up with whatever window was requested.
    """

    async def fetch_logs(self, query: LogQuery) -> list[str]:
        """Ignore query filters deliberately; return the same dump every time."""
        return generate_application_log_dump(
            service_name=query.service_name,
            environment=query.environment,
            start=query.start_time,
        )
