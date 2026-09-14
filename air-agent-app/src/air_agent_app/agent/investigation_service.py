"""Validate an incident and execute the single-attempt planning graph."""

import logging
from collections.abc import Mapping
from uuid import UUID

from pydantic import ValidationError

from air_agent_app.agent.graph.planner_graph import build_planner_graph
from air_agent_app.agent.graph.planner_state import PlannerState
from air_agent_app.agent.logging_config import get_logger
from air_agent_app.context.context_builder import ContextBuilder
from air_agent_app.investigation.planner_service import PlannerService
from air_agent_app.models.exceptions import InvalidIncidentError
from air_agent_app.models.incident import IncidentInput

logger = get_logger(__name__)


class InvestigationService:
    """Return a ready plan or a failed outcome; never dispatch evidence here."""

    def __init__(
        self,
        planner: PlannerService,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        """Compile the graph once while keeping per-request state outside the service."""
        self._graph = build_planner_graph(planner, context_builder or ContextBuilder())

    def investigate(
        self,
        investigation_id: UUID,
        data: Mapping[str, object],
    ) -> PlannerState:
        """Validate incident input and invoke one bounded planning execution."""
        try:
            # Re-validate even though the parameter is typed as UUID: Python does
            # not enforce type hints at runtime, and callers at process boundaries
            # (CLI, HTTP) may pass an unvalidated string.
            run_id = UUID(str(investigation_id))
            incident = IncidentInput.model_validate(dict(data))
        except (ValidationError, ValueError) as error:
            logger.warning("Incident input validation failed")
            raise InvalidIncidentError("Incident input failed validation") from error

        logger.info("Planning started investigation_id=%s", run_id)
        initial: PlannerState = {
            "investigation_id": run_id,
            "incident": incident,
            "status": "PLANNING",
            "terminal_reason": None,
            "planner_output": None,
        }
        try:
            result: PlannerState = self._graph.invoke(initial, config={"recursion_limit": 10})
        except Exception as error:
            logger.error(
                "Planning interrupted investigation_id=%s error_type=%s",
                run_id,
                type(error).__name__,
            )
            raise
        logger.log(
            logging.ERROR if result["status"] == "PLANNER_FAILED" else logging.INFO,
            "Planning finished investigation_id=%s status=%s reason=%s",
            run_id,
            result["status"],
            result["terminal_reason"],
        )
        return result
