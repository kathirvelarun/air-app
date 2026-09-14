"""CLI input/output and composition for live and explicit offline planning."""

import argparse
import json
import sys
from pathlib import Path
from typing import cast
from uuid import uuid4

from pydantic import ValidationError

from air_agent_app.agent.config import ModelSettings
from air_agent_app.agent.investigation_service import InvestigationService
from air_agent_app.agent.logging_config import configure_logging, get_logger
from air_agent_app.investigation.planner_service import PlannerService
from air_agent_app.models.exceptions import ConfigurationError, InvalidIncidentError
from air_agent_app.tools.llm.model_factory import create_llm_service
from air_agent_app.tools.mock.fixtures.offline_plan_model import OfflinePlanModel, PlanningScenario
from air_agent_app.tools.mock.fixtures.payment_alert import PAYMENT_ALERT

logger = get_logger(__name__)


def run_planner_cli() -> int:
    """Parse inputs, compose the application, and render explicit terminal outcomes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Use the configured OpenAI model")
    parser.add_argument("--incident", type=Path, help="Read an incident JSON object")
    parser.add_argument("--scenario", choices=("ready", "no-agents"), default="ready")
    args = parser.parse_args()
    if args.live and args.scenario != "ready":
        parser.error("--scenario is for offline fixtures only")
    configure_logging()
    logger.debug(
        "Planner CLI invoked mode=%s scenario=%s",
        "live" if args.live else "offline",
        args.scenario,
    )
    try:
        data = json.loads(args.incident.read_text()) if args.incident else PAYMENT_ALERT
        if not isinstance(data, dict):
            raise InvalidIncidentError("Incident JSON must be an object")
        model = (
            create_llm_service(ModelSettings.from_environment())
            if args.live
            else OfflinePlanModel(cast(PlanningScenario, args.scenario.replace("-", "_")))
        )
        result = InvestigationService(PlannerService(model.generate)).investigate(uuid4(), data)
    except (
        ConfigurationError,
        InvalidIncidentError,
        OSError,
        json.JSONDecodeError,
        ValidationError,
    ) as error:
        print(f"Planner failed: {type(error).__name__}", file=sys.stderr)
        return 1
    plan = result["planner_output"] if result["status"] == "PLAN_READY" else None
    print(
        json.dumps(
            {
                "mode": "live" if args.live else "offline_fixture",
                "workflow_status": result["status"],
                "terminal_reason": result["terminal_reason"],
                "plan": plan.model_dump(by_alias=True) if plan else None,
            },
            indent=2,
        )
    )
    return 0 if result["status"] == "PLAN_READY" else 1
