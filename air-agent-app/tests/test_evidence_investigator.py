"""EvidenceInvestigator: parallel dispatch, aggregation, and timeline.

No RCA coverage here: root-cause assessment is not implemented (it needs an
LLM-based RCA agent, Section 9), so this only tests evidence collection and
aggregation (Section 8). There is also no derived digest on top of the
evidence list -- the response is exactly Section 8.2's schema, so tests
assert on `response.evidence` directly rather than a summary view of it.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from air_agent_app.investigation.deployment_agent import DeploymentAgent
from air_agent_app.investigation.evidence_investigator import EvidenceInvestigator
from air_agent_app.investigation.logs_agent import LogsAgent
from air_agent_app.investigation.metrics_agent import MetricsAgent
from air_agent_app.investigation.traces_agent import TracesAgent
from air_agent_app.models.investigate import InvestigateRequest
from air_agent_app.models.log_evidence import LogQuery
from air_agent_app.tools.logs.log_tool import LogTool
from air_agent_app.tools.mock.fixtures.offline_deployment_tool import OfflineDeploymentTool
from air_agent_app.tools.mock.fixtures.offline_log_tool import OfflineLogTool
from air_agent_app.tools.mock.fixtures.offline_metric_tool import OfflineMetricTool
from air_agent_app.tools.mock.fixtures.offline_trace_tool import OfflineTraceTool

START = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


class BrokenLogTool:
    """Simulates a log-platform outage for failure-isolation tests."""

    async def fetch_logs(self, query: LogQuery) -> list[str]:
        """Always fail, regardless of the query."""
        raise ConnectionError("simulated ELF outage")


def make_investigator(*, log_tool: LogTool | None = None) -> EvidenceInvestigator:
    """Build an EvidenceInvestigator wired to the real offline tools by default."""
    return EvidenceInvestigator(
        logs_agent=LogsAgent(log_tool or OfflineLogTool()),
        metrics_agent=MetricsAgent(OfflineMetricTool()),
        traces_agent=TracesAgent(OfflineTraceTool()),
        deployment_agent=DeploymentAgent(OfflineDeploymentTool()),
    )


def make_request(**overrides: object) -> InvestigateRequest:
    """Build a valid InvestigateRequest, overriding only what a test needs."""
    fields: dict[str, object] = {
        "investigation_id": uuid4(),
        "service_name": "payment-service",
        "environment": "production",
        "repository": "org/air-services",
        "start_time": START,
        "end_time": START + timedelta(hours=2),
    }
    fields.update(overrides)
    return InvestigateRequest.model_validate(fields)


def test_request_requires_repository_when_deployment_agent_included() -> None:
    """DeploymentAgent cannot run without a repository to query."""
    with pytest.raises(ValueError, match="repository is required"):
        make_request(repository=None, agents=["DeploymentAgent"])


def test_request_rejects_unknown_agent_name() -> None:
    """Agent names are a closed set; a typo is a validation error, not a runtime failure."""
    with pytest.raises(ValueError):
        make_request(agents=["NotARealAgent"])


@pytest.mark.anyio
async def test_all_four_agents_run_and_are_aggregated() -> None:
    """The full scenario: all four agents return evidence, none missing."""
    response = await make_investigator().investigate(make_request())

    assert response.missing_agents == []
    assert {item.agent_name for item in response.evidence} == {
        "LogsAgent",
        "MetricsAgent",
        "TracesAgent",
        "DeploymentAgent",
    }
    assert len(response.evidence) == 4
    # Everything here is a "found something" tier (>= 0.9) for this scenario.
    assert all(item.confidence >= 0.9 for item in response.evidence)
    assert response.duplicate_count == 0


@pytest.mark.anyio
async def test_timeline_orders_by_specific_finding_time_not_shared_window_start() -> None:
    """Deployment (14:00:00) precedes the errors (14:14:28), not tied at the window start."""
    response = await make_investigator().investigate(make_request())

    timestamps = {item.agent_name: item.timestamp for item in response.timeline}
    assert timestamps["DeploymentAgent"] < timestamps["LogsAgent"]
    assert timestamps["DeploymentAgent"] < timestamps["TracesAgent"]
    # The deployment genuinely precedes the errors by ~14 minutes in the mock data.
    assert (timestamps["LogsAgent"] - timestamps["DeploymentAgent"]) == timedelta(
        minutes=14, seconds=28
    )


@pytest.mark.anyio
async def test_agent_subset_only_runs_the_requested_agents() -> None:
    """Requesting fewer agents means fewer agents actually run."""
    response = await make_investigator().investigate(
        make_request(agents=["LogsAgent", "MetricsAgent"], repository=None)
    )

    assert {item.agent_name for item in response.evidence} == {"LogsAgent", "MetricsAgent"}
    assert response.missing_agents == []


@pytest.mark.anyio
async def test_service_without_a_modeled_signal_is_all_healthy() -> None:
    """A service uninvolved in the scenario returns healthy evidence, not fabricated issues."""
    response = await make_investigator().investigate(make_request(service_name="unrelated-service"))

    assert response.missing_agents == []
    assert all(item.confidence < 0.9 for item in response.evidence)


@pytest.mark.anyio
async def test_one_agent_failing_does_not_fail_the_investigation() -> None:
    """LogsAgent outage is isolated: the rest of the investigation still completes."""
    investigator = make_investigator(log_tool=BrokenLogTool())
    response = await investigator.investigate(make_request())

    assert response.missing_agents == ["LogsAgent"]
    assert "LogsAgent" not in {item.agent_name for item in response.evidence}
    # The remaining three still ran and were aggregated normally.
    assert {item.agent_name for item in response.evidence} == {
        "MetricsAgent",
        "TracesAgent",
        "DeploymentAgent",
    }
