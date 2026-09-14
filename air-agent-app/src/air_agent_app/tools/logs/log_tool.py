"""LogsAgent's tool boundary: log-platform specifics stay behind this interface."""

from typing import Protocol

from air_agent_app.models.log_evidence import LogQuery


class LogTool(Protocol):
    """Anything that can answer a vendor-agnostic LogQuery with raw log lines."""

    async def fetch_logs(self, query: LogQuery) -> list[str]:
        """Return raw, unparsed log lines for the requested window."""
        ...
