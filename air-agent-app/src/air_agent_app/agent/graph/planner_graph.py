"""Single-attempt planning graph with accepted and failed terminal paths."""

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from air_agent_app.agent.graph.planner_state import PlannerState
from air_agent_app.context.context_builder import ContextBuilder
from air_agent_app.investigation.planner_service import PlannerService
from air_agent_app.models.exceptions import InvalidPlanError, ModelCallError


def build_planner_graph(
    planner_service: PlannerService,
    context_builder: ContextBuilder,
) -> CompiledStateGraph:
    """Compile one planning attempt followed by an accepted or failed outcome."""

    def build_context(state: PlannerState) -> dict[str, object]:
        """Build bounded context from the validated incident without external IO."""
        context = context_builder.build(state["investigation_id"], state["incident"])
        return {"context": context}

    def generate_plan(state: PlannerState) -> dict[str, object]:
        """Call the planner model once and convert known model errors into state."""
        try:
            return {"planner_output": planner_service.plan(state["context"])}
        except (InvalidPlanError, ModelCallError):
            return {"planner_output": None, "terminal_reason": "MODEL_FAILURE"}

    def route_plan(state: PlannerState) -> Literal["accepted", "failed"]:
        """Accept plans with agents; send empty or failed model results to failure."""
        if state["terminal_reason"] == "MODEL_FAILURE":
            return "failed"
        plan = state["planner_output"]
        if plan is None or not plan.parallel_agents:
            return "failed"
        return "accepted"

    def accept_plan(state: PlannerState) -> dict[str, object]:
        """Mark a generated plan with at least one agent as ready for dispatch."""
        return {"status": "PLAN_READY", "terminal_reason": None}

    def planner_failed(state: PlannerState) -> dict[str, object]:
        """Record whether model generation failed or returned no agents."""
        reason = state["terminal_reason"] or "NO_AGENTS_SELECTED"
        return {"status": "PLANNER_FAILED", "terminal_reason": reason}

    graph = StateGraph(PlannerState)
    graph.add_node("build_context", build_context)
    graph.add_node("generate_plan", generate_plan)
    graph.add_node("accept_plan", accept_plan)
    graph.add_node("planner_failed", planner_failed)
    graph.add_edge(START, "build_context")
    graph.add_edge("build_context", "generate_plan")
    graph.add_conditional_edges(
        "generate_plan",
        route_plan,
        {"accepted": "accept_plan", "failed": "planner_failed"},
    )
    graph.add_edge("accept_plan", END)
    graph.add_edge("planner_failed", END)
    return graph.compile()
