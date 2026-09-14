"""Section 8: fan out to evidence agents in parallel, then aggregate.

Flow: InvestigateRequest -> (per-agent request) -> agents in parallel ->
Evidence[] -> timeline (Section 8.1-8.2). The response is exactly
AggregatedEvidence's shape: no derived digest on top of it, no RCA. See
docs/section_08_investigate_service.md for why (a digest and a heuristic
RCA both lived here before and were removed on purpose).

This uses plain asyncio.gather rather than a LangGraph subgraph: there is no
conditional routing between agents, so a graph would add a state schema and
node-wiring layer without doing anything gather doesn't already do. A
LangGraph "Evidence Collection Subgraph" (matching Section 3.1's diagram) is
the natural next step if branching logic is ever needed here.
"""

import asyncio
from datetime import datetime
from typing import Any

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.investigation.deployment_agent import DeploymentAgent
from air_agent_app.investigation.logs_agent import LogsAgent
from air_agent_app.investigation.metrics_agent import MetricsAgent
from air_agent_app.investigation.traces_agent import TracesAgent
from air_agent_app.models.deployment_evidence import DeploymentEvidenceRequest
from air_agent_app.models.evidence import Evidence
from air_agent_app.models.investigate import (
    InvestigateRequest,
    InvestigateResponse,
    TimelineEvent,
)
from air_agent_app.models.log_evidence import LogEvidenceRequest
from air_agent_app.models.metric_evidence import MetricEvidenceRequest
from air_agent_app.models.trace_evidence import TraceEvidenceRequest

logger = get_logger(__name__)


def _build_agent_request(agent_name: str, request: InvestigateRequest) -> Any:
    """Narrow the shared InvestigateRequest down to one agent's own request type."""
    common = {
        "investigation_id": request.investigation_id,
        "service_name": request.service_name,
        "environment": request.environment,
        "start_time": request.start_time,
        "end_time": request.end_time,
    }
    if agent_name == "LogsAgent":
        return LogEvidenceRequest(
            **common,
            required_evidence=request.required_evidence,
            hypothesis_context=request.hypothesis_context,
            namespace=request.namespace,
            cluster=request.cluster,
            pod=request.pod,
            max_results=request.max_results,
        )
    if agent_name == "MetricsAgent":
        return MetricEvidenceRequest(
            **common,
            required_metrics=request.required_metrics,
            namespace=request.namespace,
            cluster=request.cluster,
            pod=request.pod,
            step_seconds=request.step_seconds,
        )
    if agent_name == "TracesAgent":
        return TraceEvidenceRequest(
            **common,
            required_operations=request.required_operations,
            namespace=request.namespace,
            cluster=request.cluster,
            pod=request.pod,
            slow_span_threshold_ms=request.slow_span_threshold_ms,
            max_results=request.max_results,
        )
    if agent_name == "DeploymentAgent":
        # request.repository is guaranteed non-None here: InvestigateRequest's
        # own validator rejects "DeploymentAgent" in agents without one.
        return DeploymentEvidenceRequest(
            **common,
            repository=request.repository,
            branch=request.branch,
            deployment_environment=request.deployment_environment,
            required_evidence=request.required_evidence,
        )
    raise ValueError(f"Unknown agent: {agent_name}")


def _evidence_timestamp(item: Evidence) -> datetime:
    """Prefer a specific finding time over the shared query-window boundary.

    Every agent's ``findings`` stores window-level stats, but Logs, Traces,
    and Deployment also record when their specific finding actually
    happened. Using that when present makes the aggregated timeline reflect
    real chronology instead of every evidence item sharing the same
    query-window start (MetricsAgent has no single-event timestamp to offer,
    since its findings are baseline-vs-window averages, not one occurrence).
    """
    raw: object = None
    if item.evidence_type == "DEPLOYMENT":
        latest = item.findings.get("latest_deployment")
        if isinstance(latest, dict):
            raw = latest.get("timestamp")
    elif item.evidence_type in ("LOG", "TRACE"):
        raw = item.findings.get("first_error_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return item.observed_from or item.collected_at


def _build_timeline(evidence: list[Evidence]) -> list[TimelineEvent]:
    """Order evidence by the most specific timestamp each finding can offer."""
    ordered = sorted(evidence, key=_evidence_timestamp)
    return [
        TimelineEvent(
            timestamp=_evidence_timestamp(item),
            agent_name=item.agent_name,
            evidence_type=item.evidence_type,
            title=item.title,
        )
        for item in ordered
    ]


class EvidenceInvestigator:
    """Compose the four evidence agents into one parallel investigate() call."""

    def __init__(
        self,
        logs_agent: LogsAgent,
        metrics_agent: MetricsAgent,
        traces_agent: TracesAgent,
        deployment_agent: DeploymentAgent,
    ) -> None:
        """Inject each agent; never construct one internally."""
        self._agents: dict[str, Any] = {
            "LogsAgent": logs_agent,
            "MetricsAgent": metrics_agent,
            "TracesAgent": traces_agent,
            "DeploymentAgent": deployment_agent,
        }

    async def investigate(self, request: InvestigateRequest) -> InvestigateResponse:
        """Run the requested agents in parallel and aggregate their results.

        One agent's failure is recorded as a missing agent, never raised: no
        single evidence agent should be able to fail the whole investigation
        (Section 10's failure-isolation rule). Agent *names* are validated
        by ``InvestigateRequest.agents`` itself (a Literal type), so every
        name here is guaranteed to be a key in ``self._agents``.
        """
        requested = list(dict.fromkeys(request.agents))
        logger.info(
            "Investigation started investigation_id=%s agents=%s",
            request.investigation_id,
            ",".join(requested),
        )
        results = await asyncio.gather(
            *(self._run_one(name, request) for name in requested),
            return_exceptions=True,
        )

        evidence: list[Evidence] = []
        missing_agents: list[str] = []
        for name, result in zip(requested, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "Evidence agent failed investigation_id=%s agent=%s error_type=%s",
                    request.investigation_id,
                    name,
                    type(result).__name__,
                )
                missing_agents.append(name)
                continue
            evidence.extend(result)

        response = InvestigateResponse(
            investigation_id=request.investigation_id,
            evidence=evidence,
            missing_agents=missing_agents,
            duplicate_count=0,
            timeline=_build_timeline(evidence),
        )
        logger.info(
            "Investigation completed investigation_id=%s evidence_count=%s missing_agents=%s",
            request.investigation_id,
            len(evidence),
            ",".join(missing_agents) or "none",
        )
        return response

    async def _run_one(self, agent_name: str, request: InvestigateRequest) -> list[Evidence]:
        """Build one agent's own request and execute it."""
        agent = self._agents[agent_name]
        agent_request = _build_agent_request(agent_name, request)
        return await agent.execute(agent_request)
