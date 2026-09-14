"""Validate untrusted planner output at the application boundary."""

from collections.abc import Mapping

from pydantic import ValidationError

from air_agent_app.models.exceptions import InvalidPlanError
from air_agent_app.models.planner_output import PlannerOutput


def validate_plan(data: Mapping[str, object]) -> PlannerOutput:
    """Return validated output or raise a domain error with its cause preserved.

    The caller owns logging so failures are logged once. Never put incident
    payloads or Pydantic's input-bearing error text into operational logs.
    Unexpected programming errors propagate rather than becoming fake plans.
    """
    try:
        return PlannerOutput.model_validate(dict(data))
    except ValidationError as error:
        raise InvalidPlanError("Planner output failed schema validation") from error
