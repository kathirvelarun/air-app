"""Explicit offline DeploymentTool; never selected as a fallback for a live failure."""

from air_agent_app.models.deployment_evidence import DeploymentQuery
from air_agent_app.tools.mock.fixtures.deployment_dump import generate_deployment_events


class OfflineDeploymentTool:
    """Return a fixed, realistic deployment history instead of querying GitHub.

    This is the only ``DeploymentTool`` implementation until a real GitHub
    adapter exists (see AGENTS.md): none is available to this lesson. It
    deliberately ignores ``branch``/``deployment_environment`` filters; only
    ``service_name`` and ``environment`` determine what comes back.
    """

    async def fetch_deployments(self, query: DeploymentQuery) -> list[str]:
        """Ignore query filters deliberately; return the same events every time."""
        return generate_deployment_events(
            repository=query.repository,
            service_name=query.service_name,
            environment=query.environment,
            window_start=query.start_time,
            window_end=query.end_time,
        )
