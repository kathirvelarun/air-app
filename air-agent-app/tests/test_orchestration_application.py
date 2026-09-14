"""OrchestrationApplication: the full Planning -> Evidence Collection -> RCA pipeline.

Every terminal `OrchestrationStatus` gets its own test, built from the same
real offline stack (`OfflinePlanModel`, the four offline evidence tools,
`OfflineInvestigationModel`) used elsewhere in this suite -- never a mocked
service, so these tests exercise the same wiring a live request would.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from langchain_core.prompt_values import ChatPromptValue

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
from air_agent_app.models.deployment_evidence import DeploymentQuery
from air_agent_app.models.incident import IncidentInput
from air_agent_app.models.orchestration import OrchestrationRequest
from air_agent_app.models.planner_output import PlannerOutput
from air_agent_app.tools.mock.fixtures.offline_deployment_tool import OfflineDeploymentTool
from air_agent_app.tools.mock.fixtures.offline_investigation_model import OfflineInvestigationModel
from air_agent_app.tools.mock.fixtures.offline_log_tool import OfflineLogTool
from air_agent_app.tools.mock.fixtures.offline_metric_tool import OfflineMetricTool
from air_agent_app.tools.mock.fixtures.offline_plan_model import OfflinePlanModel, PlanningScenario
from air_agent_app.tools.mock.fixtures.offline_trace_tool import OfflineTraceTool

START = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


class BrokenDeploymentTool:
    """Simulates a GitHub outage so every evidence agent can be made to fail at once."""

    async def fetch_deployments(self, query: DeploymentQuery) -> list[str]:
        """Always fail, regardless of the query."""
        raise ConnectionError("simulated GitHub outage")


def make_investigator() -> EvidenceInvestigator:
    """Build an EvidenceInvestigator wired to the real offline tools."""
    return EvidenceInvestigator(
        logs_agent=LogsAgent(OfflineLogTool()),
        metrics_agent=MetricsAgent(OfflineMetricTool()),
        traces_agent=TracesAgent(OfflineTraceTool()),
        deployment_agent=DeploymentAgent(OfflineDeploymentTool()),
    )


def make_all_broken_investigator() -> EvidenceInvestigator:
    """Build an EvidenceInvestigator where every agent's tool fails."""

    class BrokenLogTool:
        """Always fails, for the logs leg of the all-agents-down scenario."""

        async def fetch_logs(self, query: object) -> list[str]:
            """Always fail, regardless of the query."""
            raise ConnectionError("simulated ELF outage")

    class BrokenMetricTool:
        """Always fails, for the metrics leg of the all-agents-down scenario."""

        async def fetch_metrics(self, query: object) -> list[str]:
            """Always fail, regardless of the query."""
            raise ConnectionError("simulated Prometheus outage")

    class BrokenTraceTool:
        """Always fails, for the traces leg of the all-agents-down scenario."""

        async def fetch_traces(self, query: object) -> list[str]:
            """Always fail, regardless of the query."""
            raise ConnectionError("simulated Jaeger outage")

    return EvidenceInvestigator(
        logs_agent=LogsAgent(BrokenLogTool()),
        metrics_agent=MetricsAgent(BrokenMetricTool()),
        traces_agent=TracesAgent(BrokenTraceTool()),
        deployment_agent=DeploymentAgent(BrokenDeploymentTool()),
    )


def make_planning_application(scenario: PlanningScenario = "ready") -> PlanningApplication:
    """Build a PlanningApplication driven by the offline plan fixture."""
    model = OfflinePlanModel(scenario)
    return PlanningApplication(InvestigationService(PlannerService(model.generate)))


class DeploymentOnlyPlanModel:
    """Forces the plan to select only DeploymentAgent, for the missing-repository case."""

    def generate(self, prompt: ChatPromptValue) -> PlannerOutput:
        """Return the ready offline fixture with its agent selection overridden."""
        plan = OfflinePlanModel("ready").generate(prompt)
        return plan.model_copy(update={"parallel_agents": ["DeploymentAgent"]})


class UnknownAgentPlanModel:
    """Forces the plan to select an agent name evidence collection does not recognize."""

    def generate(self, prompt: ChatPromptValue) -> PlannerOutput:
        """Return the ready offline fixture with an unrecognized agent name only."""
        plan = OfflinePlanModel("ready").generate(prompt)
        return plan.model_copy(update={"parallel_agents": ["RecentIncidentAgent"]})


def make_request(**overrides: object) -> OrchestrationRequest:
    """Build a valid OrchestrationRequest, overriding only what a test needs."""
    fields: dict[str, object] = {
        "incident": IncidentInput(
            incident_id=uuid4(),
            title="Payment errors spiking",
            description="payment-service error rate elevated",
            severity="HIGH",
            detected_at=START,
            service_name="payment-service",
            environment="production",
        ),
        "repository": "org/air-services",
        "start_time": START,
        "end_time": START + timedelta(hours=2),
    }
    fields.update(overrides)
    return OrchestrationRequest.model_validate(fields)


@pytest.mark.anyio
async def test_full_pipeline_reaches_completed() -> None:
    """The full payment-service scenario runs all three stages to a COMPLETED RCA."""
    app = OrchestrationApplication(
        make_planning_application("ready"),
        make_investigator(),
        RcaService(OfflineInvestigationModel()),
    )
    result = await app.investigate(make_request())

    assert result.status == "COMPLETED"
    assert result.planning.status == "PLAN_READY"
    assert result.evidence is not None
    assert result.rca is not None
    assert result.rca.investigation_status == "COMPLETED"
    assert result.investigation_id == result.planning.investigation_id


@pytest.mark.anyio
async def test_planner_failure_stops_before_evidence_collection() -> None:
    """No agents selected means the pipeline stops at Planning; nothing downstream runs."""
    app = OrchestrationApplication(
        make_planning_application("no_agents"),
        make_investigator(),
        RcaService(OfflineInvestigationModel()),
    )
    result = await app.investigate(make_request())

    assert result.status == "PLANNER_FAILED"
    assert result.terminal_reason == "NO_AGENTS_SELECTED"
    assert result.evidence is None
    assert result.rca is None


@pytest.mark.anyio
async def test_all_evidence_agents_failing_skips_rca() -> None:
    """Zero evidence collected means RCA never runs -- not a guessed INCONCLUSIVE."""
    app = OrchestrationApplication(
        make_planning_application("ready"),
        make_all_broken_investigator(),
        RcaService(OfflineInvestigationModel()),
    )
    result = await app.investigate(make_request())

    assert result.status == "NO_EVIDENCE_COLLECTED"
    assert result.terminal_reason == "ALL_AGENTS_FAILED"
    assert result.evidence is not None
    assert result.evidence.evidence == []
    assert result.rca is None


@pytest.mark.anyio
async def test_deployment_agent_without_repository_is_invalid_not_a_crash() -> None:
    """A plan needing a field the request never supplied fails cleanly, not with an exception."""
    planning_application = PlanningApplication(
        InvestigationService(PlannerService(DeploymentOnlyPlanModel().generate))
    )
    app = OrchestrationApplication(
        planning_application, make_investigator(), RcaService(OfflineInvestigationModel())
    )
    result = await app.investigate(make_request(repository=None))

    assert result.status == "EVIDENCE_REQUEST_INVALID"
    assert result.terminal_reason == "DEPLOYMENT_AGENT_NEEDS_REPOSITORY"
    assert result.evidence is None
    assert result.rca is None


@pytest.mark.anyio
async def test_unrecognized_agent_name_is_dropped_not_fatal_when_others_remain() -> None:
    """An unrecognized agent alongside valid ones does not sink the whole investigation."""

    class MixedPlanModel:
        """Selects one unrecognized name and one real agent together."""

        def generate(self, prompt: ChatPromptValue) -> PlannerOutput:
            """Return the ready fixture with a mixed valid/invalid agent selection."""
            plan = OfflinePlanModel("ready").generate(prompt)
            return plan.model_copy(update={"parallel_agents": ["RecentIncidentAgent", "LogsAgent"]})

    planning_application = PlanningApplication(
        InvestigationService(PlannerService(MixedPlanModel().generate))
    )
    app = OrchestrationApplication(
        planning_application, make_investigator(), RcaService(OfflineInvestigationModel())
    )
    result = await app.investigate(make_request())

    assert result.status in ("COMPLETED", "INCONCLUSIVE")
    assert result.evidence is not None
    assert {item.agent_name for item in result.evidence.evidence} == {"LogsAgent"}


@pytest.mark.anyio
async def test_unrecognized_agent_only_is_evidence_request_invalid() -> None:
    """No known agent at all in the plan is a clean invalid outcome, not an empty call."""
    planning_application = PlanningApplication(
        InvestigationService(PlannerService(UnknownAgentPlanModel().generate))
    )
    app = OrchestrationApplication(
        planning_application, make_investigator(), RcaService(OfflineInvestigationModel())
    )
    result = await app.investigate(make_request())

    assert result.status == "EVIDENCE_REQUEST_INVALID"
    assert result.terminal_reason == "NO_KNOWN_AGENTS_IN_PLAN"


@pytest.mark.anyio
async def test_rca_failure_is_reported_with_evidence_still_present() -> None:
    """An RCA model failure surfaces as RCA_FAILED; the evidence collected is still visible."""

    class AlwaysFailingRcaClient:
        """Simulates an RCA model that always returns unusable output."""

        def generate(self, evidence: object, source_reference_map: object) -> object:
            """Always raise, forcing bounded retry to exhaust and escalate."""
            from air_agent_app.models.exceptions import InvalidInvestigationResultError

            raise InvalidInvestigationResultError("simulated malformed output")

    app = OrchestrationApplication(
        make_planning_application("ready"),
        make_investigator(),
        RcaService(AlwaysFailingRcaClient()),
    )
    result = await app.investigate(make_request())

    assert result.status == "RCA_FAILED"
    assert result.terminal_reason == "RCA_EXECUTION_FAILED"
    assert result.evidence is not None
    assert result.rca is None


@pytest.mark.anyio
async def test_required_metrics_passthrough_reaches_the_evidence_request() -> None:
    """A caller-supplied required_metrics reaches MetricsAgent, not just the Planner's own list.

    The Planner produces no per-agent metric breakdown today (see
    `docs/extension_03_end_to_end_orchestration_agent.md` section 6), so a
    scenario needing a metric outside `MetricsAgent.DEFAULT_METRICS` (like
    `disk_usage_pct`) has no other way to reach evidence collection through
    this single endpoint.
    """
    app = OrchestrationApplication(
        make_planning_application("ready"),
        make_investigator(),
        RcaService(OfflineInvestigationModel()),
    )
    request = make_request(
        incident=IncidentInput(
            incident_id=uuid4(),
            title="Ledger writes failing",
            description="ledger-service write-ahead log appends are failing",
            severity="CRITICAL",
            detected_at=START,
            service_name="ledger-service",
            environment="production",
        ),
        required_metrics=[
            "cpu_pct",
            "memory_pct",
            "http_5xx_rate",
            "p95_latency_ms",
            "disk_usage_pct",
        ],
    )
    result = await app.investigate(request)

    assert result.evidence is not None
    metrics_evidence = next(
        item for item in result.evidence.evidence if item.agent_name == "MetricsAgent"
    )
    assert "disk_usage_pct" in metrics_evidence.findings
    assert metrics_evidence.findings["disk_usage_pct"]["health"] == "UNHEALTHY"
