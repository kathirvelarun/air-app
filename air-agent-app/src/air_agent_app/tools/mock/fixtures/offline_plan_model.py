"""Controlled candidate sequences for offline workflow demonstrations."""

from typing import Literal

from langchain_core.prompt_values import ChatPromptValue

from air_agent_app.models.planner_output import PlannerOutput

PlanningScenario = Literal["ready", "no_agents"]


class OfflinePlanModel:
    """Emit labeled fixtures, not AI reasoning over the input incident."""

    def __init__(self, scenario: PlanningScenario = "ready") -> None:
        """Store the deterministic branch used by offline tests and commands."""
        self._scenario = scenario

    def generate(self, prompt: ChatPromptValue) -> PlannerOutput:
        """Return a fresh candidate; deliberately ignore the incident prompt."""
        plan = PlannerOutput(
            status="READY",
            confidence=0.85,
            investigation_type="Application",
            priority="High",
            parallel_agents=["LogsAgent", "MetricsAgent"],
            required_evidence=["Application exceptions", "HTTP error rate"],
            hypotheses=["Possible application error"],
            reasoning="OFFLINE FIXTURE: inspect runtime metrics and application logs.",
        )
        if self._scenario == "no_agents":
            plan.parallel_agents = []
        return plan
