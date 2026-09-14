"""DeploymentAgent's tool boundary: GitHub/CI specifics stay behind this interface."""

from typing import Protocol

from air_agent_app.models.deployment_evidence import DeploymentQuery


class DeploymentTool(Protocol):
    """Anything that can answer a vendor-agnostic DeploymentQuery with raw event lines."""

    async def fetch_deployments(self, query: DeploymentQuery) -> list[str]:
        """Return raw, unparsed deployment/commit event lines for the requested window."""
        ...
