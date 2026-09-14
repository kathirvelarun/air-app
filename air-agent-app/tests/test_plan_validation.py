"""Contract compatibility and failure behavior at the validation boundary."""

import pytest
from pydantic import ValidationError

from air_agent_app.investigation.plan_validation import validate_plan
from air_agent_app.models.exceptions import InvalidPlanError


def test_json_alias_round_trip() -> None:
    """Json alias round trip."""
    data = {
        "status": "READY",
        "confidence": 0.85,
        "parallelAgents": ["LogsAgent"],
        "reasoning": "Inspect exceptions",
    }
    plan = validate_plan(data)
    assert plan.parallel_agents == ["LogsAgent"]
    assert validate_plan(plan.model_dump(by_alias=True)) == plan
    assert "parallelAgents" in plan.model_dump(by_alias=True)
    assert "parallel_agents" not in plan.model_dump(by_alias=True)


@pytest.mark.parametrize(
    "update",
    [
        {"confidence": 1.5},
        {"confidence": float("nan")},
        {"status": "UNKNOWN"},
        {"reasoning": "  "},
        {"unexpected": "value"},
    ],
)
def test_invalid_plan_preserves_cause_without_exposing_input(update: dict) -> None:
    """Invalid plan preserves cause without exposing input."""
    data = {"status": "READY", "confidence": 0.85, "reasoning": "private incident text"}
    with pytest.raises(InvalidPlanError) as caught:
        validate_plan(data | update)
    assert isinstance(caught.value.__cause__, ValidationError)
    assert "private incident text" not in str(caught.value)


def test_python_names_and_independent_defaults() -> None:
    """Python names and independent defaults."""
    data = {"status": "READY", "confidence": 0.2, "reasoning": "Need service"}
    first = validate_plan(data | {"missing_context": ["service"]})
    second = validate_plan(data)
    assert first.missing_context == ["service"]
    assert second.missing_context == []
