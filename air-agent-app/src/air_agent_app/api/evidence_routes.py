"""Evidence-collection HTTP routes; agent behavior stays in the agents themselves."""

from typing import Annotated

from fastapi import APIRouter, Depends

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.api.dependencies import (
    get_deployment_agent,
    get_logs_agent,
    get_metrics_agent,
    get_traces_agent,
)
from air_agent_app.investigation.deployment_agent import DeploymentAgent
from air_agent_app.investigation.logs_agent import LogsAgent
from air_agent_app.investigation.metrics_agent import MetricsAgent
from air_agent_app.investigation.traces_agent import TracesAgent
from air_agent_app.models.deployment_evidence import DeploymentEvidenceRequest
from air_agent_app.models.evidence_response import EvidenceResponse
from air_agent_app.models.log_evidence import LogEvidenceRequest
from air_agent_app.models.metric_evidence import MetricEvidenceRequest
from air_agent_app.models.trace_evidence import TraceEvidenceRequest

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


@router.post("/logs", response_model=EvidenceResponse)
async def collect_log_evidence(
    request: LogEvidenceRequest,
    agent: Annotated[LogsAgent, Depends(get_logs_agent)],
) -> EvidenceResponse:
    """Run LogsAgent once for an already-accepted plan; never a root cause.

    Callers are expected to call this only after ``/api/v1/planning`` returns
    `PLAN_READY` with "LogsAgent" among `parallel_agents`; this endpoint does
    not itself check plan status, since no investigation state is persisted
    server-side yet (see docs/section_03_evidence_collection_plan.md).
    """
    evidence = await agent.execute(request)
    logger.info(
        "Log evidence HTTP request completed investigation_id=%s evidence_count=%s",
        request.investigation_id,
        len(evidence),
    )
    return EvidenceResponse(investigation_id=request.investigation_id, evidence=evidence)


@router.post("/traces", response_model=EvidenceResponse)
async def collect_trace_evidence(
    request: TraceEvidenceRequest,
    agent: Annotated[TracesAgent, Depends(get_traces_agent)],
) -> EvidenceResponse:
    """Run TracesAgent once for an already-accepted plan; never a root cause.

    Same contract as ``/logs``/``/metrics``. TracesAgent is not one of the
    guide's four defined evidence agents; see
    docs/extension_01_traces_agent.md.
    """
    evidence = await agent.execute(request)
    logger.info(
        "Trace evidence HTTP request completed investigation_id=%s evidence_count=%s",
        request.investigation_id,
        len(evidence),
    )
    return EvidenceResponse(investigation_id=request.investigation_id, evidence=evidence)


@router.post("/deployments", response_model=EvidenceResponse)
async def collect_deployment_evidence(
    request: DeploymentEvidenceRequest,
    agent: Annotated[DeploymentAgent, Depends(get_deployment_agent)],
) -> EvidenceResponse:
    """Run DeploymentAgent once for an already-accepted plan; never a root cause.

    Same contract as ``/logs``/``/metrics``/``/traces``. DeploymentAgent is
    one of the guide's four defined evidence agents (Section 6); see
    docs/section_06_deployment_agent.md.
    """
    evidence = await agent.execute(request)
    logger.info(
        "Deployment evidence HTTP request completed investigation_id=%s evidence_count=%s",
        request.investigation_id,
        len(evidence),
    )
    return EvidenceResponse(investigation_id=request.investigation_id, evidence=evidence)


@router.post("/metrics", response_model=EvidenceResponse)
async def collect_metric_evidence(
    request: MetricEvidenceRequest,
    agent: Annotated[MetricsAgent, Depends(get_metrics_agent)],
) -> EvidenceResponse:
    """Run MetricsAgent once for an already-accepted plan; never a root cause.

    Same contract as ``/logs``: callers call this after `PLAN_READY` with
    "MetricsAgent" among `parallel_agents`, and no investigation state is
    checked or persisted server-side.
    """
    evidence = await agent.execute(request)
    logger.info(
        "Metric evidence HTTP request completed investigation_id=%s evidence_count=%s",
        request.investigation_id,
        len(evidence),
    )
    return EvidenceResponse(investigation_id=request.investigation_id, evidence=evidence)
