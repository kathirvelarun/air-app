"""Thin launchers delegate outcomes and failure exit codes to the CLI."""

import json
import runpy
import sys
from unittest.mock import Mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from air_agent_app.agent.cli.planner import run_planner_cli
from air_agent_app.agent.config import ModelSettings
from air_agent_app.agent.investigation_service import InvestigationService
from air_agent_app.investigation.planner_service import PlannerService
from air_agent_app.tools.llm.model_factory import create_llm_service
from air_agent_app.tools.mock.fixtures.offline_plan_model import OfflinePlanModel
from air_agent_app.tools.mock.fixtures.payment_alert import PAYMENT_ALERT


@pytest.mark.parametrize(
    ("scenario", "exit_code", "status"),
    [("ready", 0, "PLAN_READY"), ("no-agents", 1, "PLANNER_FAILED")],
)
def test_planner_exit_codes(
    scenario: str,
    exit_code: int,
    status: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI returns success for accepted plans and failure when no agents exist."""
    monkeypatch.setattr(sys, "argv", ["planner", "--scenario", scenario])
    assert run_planner_cli() == exit_code
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "offline_fixture"
    assert output["workflow_status"] == status


@pytest.mark.parametrize("module", ["air_agent_app.commands.planner"])
def test_thin_launchers(
    module: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both the canonical and compatibility entry points call the same CLI."""
    monkeypatch.setattr(sys, "argv", ["planner"])
    with pytest.raises(SystemExit) as caught:
        runpy.run_module(module, run_name="__main__")
    assert caught.value.code == 0
    assert json.loads(capsys.readouterr().out)["workflow_status"] == "PLAN_READY"


def test_contract_launcher(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first lesson remains available through a thin compatibility launcher."""
    monkeypatch.setattr(sys, "argv", ["validate_plan_contract"])
    runpy.run_module("air_agent_app.commands.validate_plan_contract", run_name="__main__")
    assert "Plan contract" in capsys.readouterr().out


def test_missing_live_key_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Never silently use fixtures when live mode lacks credentials."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["planner", "--live"])
    assert run_planner_cli() == 1
    assert "ConfigurationError" in capsys.readouterr().err


def test_factory_disables_sdk_retries_and_composes_structured_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the actual live factory offline and prevent nested retry multipliers."""

    def respond(prompt: object) -> dict[str, object]:
        """Return a controlled include_raw response from the factory's runnable."""
        return {
            "raw": AIMessage(content=""),
            "parsed": OfflinePlanModel().generate(prompt),
            "parsing_error": None,
        }

    constructor = Mock()
    constructor.return_value.with_structured_output.return_value = RunnableLambda(respond)
    monkeypatch.setattr("air_agent_app.tools.llm.model_factory.ChatOpenAI", constructor)
    model = create_llm_service(ModelSettings(model_name="test-model", api_key="test-only"))
    result = InvestigationService(PlannerService(model.generate)).investigate(
        uuid4(), PAYMENT_ALERT
    )
    assert result["status"] == "PLAN_READY"
    assert constructor.call_args.kwargs["max_retries"] == 0
    assert constructor.call_args.kwargs["timeout"] == 30
    assert (
        constructor.return_value.with_structured_output.call_args.kwargs["method"]
        == "function_calling"
    )
    assert constructor.return_value.with_structured_output.call_args.kwargs["include_raw"] is True
