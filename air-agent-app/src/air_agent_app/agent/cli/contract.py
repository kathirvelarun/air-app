"""Render the Section 1 planner contract fixture and demonstrate a rejection."""

from air_agent_app.agent.logging_config import configure_logging, get_logger
from air_agent_app.investigation.plan_validation import validate_plan
from air_agent_app.models.exceptions import InvalidPlanError
from air_agent_app.models.planner_output import PlannerOutput

logger = get_logger(__name__)


def run_contract_validation() -> None:
    """Print the Section 1 contract fixture and demonstrate input rejection."""
    configure_logging()
    logger.info("Starting planner contract validation")
    # A hand-written teaching example, not output from an AI model.
    plan = PlannerOutput(
        status="READY",
        confidence=0.85,
        investigation_type="Application",
        priority="High",
        parallel_agents=["LogsAgent", "MetricsAgent", "DeploymentAgent"],
        required_evidence=[
            "Application exceptions during the incident",
            "HTTP error rate and latency",
            "Recent deployment changes",
        ],
        hypotheses=["Possible deployment regression"],
        reasoning="Inspect errors, runtime health, and deployment timing.",
    )
    print("Plan contract (hand-written):")
    print(plan.model_dump_json(indent=2, by_alias=True))

    # model_dump() converts the validated Python object into a dictionary.
    invalid_data = plan.model_dump()
    invalid_data["confidence"] = 1.5

    print("\nTrying confidence=1.5:")
    try:
        validate_plan(invalid_data)
    except InvalidPlanError:
        logger.info("Expected validation failure: confidence exceeds its allowed range")
