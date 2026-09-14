"""Deterministic context preparation; no model or database calls."""

from datetime import UTC, timedelta
from uuid import UUID

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.models.exceptions import ConfigurationError
from air_agent_app.models.incident import IncidentInput
from air_agent_app.models.planner_context import PlannerContext

logger = get_logger(__name__)


class ContextBuilder:
    """Select a reproducible window and explicitly identify missing facts.

    The agent list describes planned specialists, not evidence executors that
    have already been implemented. Callers can restrict it for their deployment.
    """

    def __init__(
        self,
        available_agents: tuple[str, ...] = (
            "LogsAgent",
            "MetricsAgent",
            "DeploymentAgent",
            "RecentIncidentAgent",
        ),
    ) -> None:
        """Accept only a nonempty set of nonblank, uniquely named agents."""
        if not available_agents or any(not name.strip() for name in available_agents):
            raise ConfigurationError("At least one nonblank agent name is required")
        self._available_agents = tuple(dict.fromkeys(available_agents))

    def build(self, investigation_id: UUID, incident: IncidentInput) -> PlannerContext:
        """Use incident start, or an explicitly labeled 30-minute lookback."""
        end = incident.detected_at.astimezone(UTC)
        start = (
            incident.started_at.astimezone(UTC)
            if incident.started_at is not None
            else end - timedelta(minutes=30)
        )
        missing = tuple(
            name for name in ("service_name", "environment") if getattr(incident, name) is None
        )
        logger.debug(
            "Planner context built missing_fields=%s available_agents=%s",
            len(missing),
            len(self._available_agents),
        )
        return PlannerContext(
            investigation_id=investigation_id,
            incident=incident,
            window_start=start,
            window_end=end,
            window_basis="incident_start" if incident.started_at else "30_minute_lookback",
            available_agents=self._available_agents,
            missing_context=missing,
        )
