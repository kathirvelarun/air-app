"""End-to-end investigation graph: Planning -> Evidence Collection -> RCA.

Maps `reference/AIR-Investigation.pdf`'s "Updated LangGraph Flow" diagram
one stage further back to include Planning -- see
`docs/extension_03_end_to_end_orchestration_agent.md`. Every node here
calls an *existing*, already-verified service unchanged
(`PlanningApplication`, `EvidenceInvestigator`, `RcaService`): this graph
is pure orchestration, no new business logic, matching Section 10's "thin
LangGraph nodes" rule already followed by `planner_graph.py`.

Both conditional routers share one shape: a node stops the pipeline by
setting ``status`` in the state it returns, and does nothing else
different when continuing. So every router just checks
``"status" in state`` -- no per-stage routing logic to keep in sync.
"""

import asyncio
from typing import cast, get_args

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from air_agent_app.agent.graph.orchestration_state import OrchestrationState
from air_agent_app.agent.logging_config import get_logger
from air_agent_app.agent.planning_application import PlanningApplication
from air_agent_app.investigation.evidence_investigator import EvidenceInvestigator
from air_agent_app.investigation.rca_service import RcaService
from air_agent_app.models.exceptions import RcaExecutionError
from air_agent_app.models.investigate import AgentName, InvestigateRequest

logger = get_logger(__name__)

_KNOWN_AGENT_NAMES: frozenset[str] = frozenset(get_args(AgentName))

# The graph's topology never changes across requests; log its shape once
# per process instead of once per request, so operators can see it without
# every investigation flooding logs with an identical diagram.
_diagram_logged = False


def build_orchestration_graph(
    planning_application: PlanningApplication,
    evidence_investigator: EvidenceInvestigator,
    rca_service: RcaService,
) -> CompiledStateGraph:
    """Compile the three-stage investigation graph and log its shape once per process."""

    async def run_planning(state: OrchestrationState) -> dict[str, object]:
        """Run Section 1's planner in a worker thread; it is a blocking LLM call."""
        incident = state["request"].incident
        logger.info("PLANNING started incident_id=%s", incident.incident_id)
        planning = await asyncio.to_thread(planning_application.plan, incident)
        result: dict[str, object] = {
            "investigation_id": planning.investigation_id,
            "planning": planning,
        }
        if planning.status == "PLANNER_FAILED":
            logger.error(
                "PLANNING failed investigation_id=%s reason=%s",
                planning.investigation_id,
                planning.terminal_reason,
            )
            result["status"] = "PLANNER_FAILED"
            result["terminal_reason"] = planning.terminal_reason or "MODEL_FAILURE"
        else:
            logger.info(
                "PLANNING completed investigation_id=%s status=PLAN_READY",
                planning.investigation_id,
            )
        return result

    async def collect_evidence(state: OrchestrationState) -> dict[str, object]:
        """Build the evidence request from the plan, then run evidence collection.

        Two things can make this stage unable to proceed, both recorded as
        `EVIDENCE_REQUEST_INVALID` rather than raised: the plan selected no
        agent evidence collection recognizes (the planner's
        `parallel_agents` is free text, never validated against
        `AgentName`), or the request lacks a field a selected agent
        structurally requires (`DeploymentAgent` needs `repository`).
        Unrecognized agent names alone are *not* fatal -- they are dropped
        and logged, and the rest of the plan still runs (Section 10's
        failure-isolation rule, applied one level up).
        """
        request = state["request"]
        investigation_id = state["investigation_id"]
        plan = state["planning"].plan
        assert plan is not None  # route_after_planning only admits PLAN_READY here

        known = [name for name in plan.parallel_agents if name in _KNOWN_AGENT_NAMES]
        dropped = [name for name in plan.parallel_agents if name not in _KNOWN_AGENT_NAMES]
        if dropped:
            logger.warning(
                "EVIDENCE_COLLECTION dropping unrecognized agents investigation_id=%s dropped=%s",
                investigation_id,
                ",".join(dropped),
            )
        if not known:
            logger.error(
                "EVIDENCE_COLLECTION invalid investigation_id=%s reason=no_known_agents_in_plan",
                investigation_id,
            )
            return {
                "status": "EVIDENCE_REQUEST_INVALID",
                "terminal_reason": "NO_KNOWN_AGENTS_IN_PLAN",
            }
        if request.incident.service_name is None or request.incident.environment is None:
            logger.error(
                "EVIDENCE_COLLECTION invalid investigation_id=%s reason=missing_service_context",
                investigation_id,
            )
            return {
                "status": "EVIDENCE_REQUEST_INVALID",
                "terminal_reason": "MISSING_SERVICE_CONTEXT",
            }

        try:
            evidence_request = InvestigateRequest(
                investigation_id=investigation_id,
                service_name=request.incident.service_name,
                environment=request.incident.environment,
                agents=cast(list[AgentName], known),
                repository=request.repository,
                branch=request.branch,
                deployment_environment=request.deployment_environment,
                namespace=request.namespace,
                cluster=request.cluster,
                pod=request.pod,
                required_evidence=plan.required_evidence,
                required_metrics=request.required_metrics,
                required_operations=request.required_operations,
                hypothesis_context=plan.hypotheses,
                start_time=request.start_time,
                end_time=request.end_time,
            )
        except ValidationError:
            logger.error(
                "EVIDENCE_COLLECTION invalid investigation_id=%s reason=%s",
                investigation_id,
                "deployment_agent_needs_repository",
            )
            return {
                "status": "EVIDENCE_REQUEST_INVALID",
                "terminal_reason": "DEPLOYMENT_AGENT_NEEDS_REPOSITORY",
            }

        logger.info(
            "EVIDENCE_COLLECTION started investigation_id=%s agents=%s",
            investigation_id,
            ",".join(known),
        )
        evidence = await evidence_investigator.investigate(evidence_request)
        if not evidence.evidence:
            logger.error(
                "EVIDENCE_COLLECTION produced no evidence investigation_id=%s missing_agents=%s",
                investigation_id,
                ",".join(evidence.missing_agents),
            )
            return {
                "evidence": evidence,
                "status": "NO_EVIDENCE_COLLECTED",
                "terminal_reason": "ALL_AGENTS_FAILED",
            }
        logger.info(
            "EVIDENCE_COLLECTION completed investigation_id=%s evidence_count=%s missing_agents=%s",
            investigation_id,
            len(evidence.evidence),
            ",".join(evidence.missing_agents) or "none",
        )
        return {"evidence": evidence}

    async def run_rca(state: OrchestrationState) -> dict[str, object]:
        """Run Section 9's RCA agent in a worker thread; it is a blocking LLM call.

        Only reached with at least one evidence item present (see
        `route_after_evidence`) -- `INCONCLUSIVE` from here is the model's
        own judgment on real evidence, never a stand-in for missing evidence.
        """
        evidence = state["evidence"]
        investigation_id = state["investigation_id"]
        logger.info(
            "RCA started investigation_id=%s evidence_count=%s",
            investigation_id,
            len(evidence.evidence),
        )
        try:
            rca = await asyncio.to_thread(rca_service.investigate, evidence)
        except RcaExecutionError:
            logger.error("RCA failed investigation_id=%s", investigation_id)
            return {"status": "RCA_FAILED", "terminal_reason": "RCA_EXECUTION_FAILED"}
        logger.info(
            "RCA completed investigation_id=%s status=%s overall_confidence=%.2f",
            investigation_id,
            rca.investigation_status,
            rca.overall_confidence,
        )
        return {"rca": rca, "status": rca.investigation_status}

    def route_after_planning(state: OrchestrationState) -> str:
        """Continue to evidence collection only if planning did not already stop the pipeline."""
        return END if "status" in state else "collect_evidence"

    def route_after_evidence(state: OrchestrationState) -> str:
        """Continue to RCA only if evidence collection did not already stop the pipeline."""
        return END if "status" in state else "run_rca"

    graph = StateGraph(OrchestrationState)
    graph.add_node("run_planning", run_planning)
    graph.add_node("collect_evidence", collect_evidence)
    graph.add_node("run_rca", run_rca)
    graph.add_edge(START, "run_planning")
    graph.add_conditional_edges(
        "run_planning", route_after_planning, {"collect_evidence": "collect_evidence", END: END}
    )
    graph.add_conditional_edges(
        "collect_evidence", route_after_evidence, {"run_rca": "run_rca", END: END}
    )
    graph.add_edge("run_rca", END)
    compiled = graph.compile()

    global _diagram_logged
    if not _diagram_logged:
        logger.info("Orchestration graph compiled:\n%s", compiled.get_graph().draw_mermaid())
        _diagram_logged = True
    return compiled
