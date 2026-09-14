"""Compose request-local live planning dependencies without import-time provider IO."""

from air_agent_app.agent.config import ModelSettings
from air_agent_app.agent.investigation_service import InvestigationService
from air_agent_app.agent.orchestration_application import OrchestrationApplication
from air_agent_app.agent.planning_application import PlanningApplication
from air_agent_app.investigation.deployment_agent import DeploymentAgent
from air_agent_app.investigation.evidence_investigator import EvidenceInvestigator
from air_agent_app.investigation.logs_agent import LogsAgent
from air_agent_app.investigation.metrics_agent import MetricsAgent
from air_agent_app.investigation.planner_service import PlannerService
from air_agent_app.investigation.rca_service import RcaService
from air_agent_app.investigation.traces_agent import TracesAgent
from air_agent_app.tools.llm.model_factory import create_llm_service
from air_agent_app.tools.llm.rca_model_factory import create_rca_llm_service
from air_agent_app.tools.mock.fixtures.offline_deployment_tool import OfflineDeploymentTool
from air_agent_app.tools.mock.fixtures.offline_log_tool import OfflineLogTool
from air_agent_app.tools.mock.fixtures.offline_metric_tool import OfflineMetricTool
from air_agent_app.tools.mock.fixtures.offline_trace_tool import OfflineTraceTool


def get_planning_application() -> PlanningApplication:
    """Use server-owned OpenAI settings; clients cannot choose credentials or mock mode."""
    model = create_llm_service(ModelSettings.from_environment())
    return PlanningApplication(InvestigationService(PlannerService(model.generate)))


def get_logs_agent() -> LogsAgent:
    """Wire the offline log tool; no live log-platform adapter exists yet.

    Unlike planning, there is no live/offline switch here to choose between:
    this is the only ``LogTool`` implementation until a real ELF adapter is
    built (see AGENTS.md), and every request is logged with the tool name
    that served it so this is never ambiguous in production logs.
    """
    return LogsAgent(OfflineLogTool())


def get_metrics_agent() -> MetricsAgent:
    """Wire the offline metric tool; no live metrics-platform adapter exists yet.

    Same rationale as ``get_logs_agent``: this is the only ``MetricTool``
    implementation until a real Prometheus/Datadog/Dynatrace adapter is
    built (see AGENTS.md).
    """
    return MetricsAgent(OfflineMetricTool())


def get_traces_agent() -> TracesAgent:
    """Wire the offline trace tool; no live tracing-platform adapter exists yet.

    Same rationale as ``get_logs_agent``: this is the only ``TraceTool``
    implementation until a real Jaeger/Tempo/OpenTelemetry adapter is built
    (see AGENTS.md).
    """
    return TracesAgent(OfflineTraceTool())


def get_deployment_agent() -> DeploymentAgent:
    """Wire the offline deployment tool; no live GitHub adapter exists yet.

    Same rationale as ``get_logs_agent``: this is the only
    ``DeploymentTool`` implementation until a real GitHub adapter is built
    (see AGENTS.md).
    """
    return DeploymentAgent(OfflineDeploymentTool())


def get_evidence_investigator() -> EvidenceInvestigator:
    """Compose all four evidence agents behind one parallel investigate() call."""
    return EvidenceInvestigator(
        logs_agent=get_logs_agent(),
        metrics_agent=get_metrics_agent(),
        traces_agent=get_traces_agent(),
        deployment_agent=get_deployment_agent(),
    )


def get_rca_service() -> RcaService:
    """Use server-owned OpenAI settings; same live-only rationale as planning.

    Unlike the evidence agents, there is no offline fixture wired here:
    `OfflineInvestigationModel` exists for tests and any future CLI, not as
    a client-selectable mode of this endpoint.
    """
    llm = create_rca_llm_service(ModelSettings.from_environment())
    return RcaService(llm)


def get_orchestration_application() -> OrchestrationApplication:
    """Compose the full pipeline from the same live-config dependencies each stage already uses."""
    return OrchestrationApplication(
        planning_application=get_planning_application(),
        evidence_investigator=get_evidence_investigator(),
        rca_service=get_rca_service(),
    )
