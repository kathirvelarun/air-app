"""Three demo scenarios, three distinct root-cause classes.

Scenario 1 (``payment-service``) is covered by the existing agent/service
test suites; this file covers the two added for the demo -- ``web-ui`` (a
code/contract issue) and ``ledger-service`` (infrastructure capacity
exhaustion) -- and asserts each has a genuinely different evidence
signature from scenario 1, not just a renamed copy of it.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from air_agent_app.investigation.deployment_agent import DeploymentAgent
from air_agent_app.investigation.evidence_investigator import EvidenceInvestigator
from air_agent_app.investigation.logs_agent import LogsAgent
from air_agent_app.investigation.metrics_agent import MetricsAgent
from air_agent_app.investigation.rca_service import RcaService
from air_agent_app.investigation.traces_agent import TracesAgent
from air_agent_app.models.investigate import InvestigateRequest
from air_agent_app.tools.mock.fixtures.offline_deployment_tool import OfflineDeploymentTool
from air_agent_app.tools.mock.fixtures.offline_investigation_model import OfflineInvestigationModel
from air_agent_app.tools.mock.fixtures.offline_log_tool import OfflineLogTool
from air_agent_app.tools.mock.fixtures.offline_metric_tool import OfflineMetricTool
from air_agent_app.tools.mock.fixtures.offline_trace_tool import OfflineTraceTool

START = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


def make_investigator() -> EvidenceInvestigator:
    """Build an EvidenceInvestigator wired to the real offline tools."""
    return EvidenceInvestigator(
        logs_agent=LogsAgent(OfflineLogTool()),
        metrics_agent=MetricsAgent(OfflineMetricTool()),
        traces_agent=TracesAgent(OfflineTraceTool()),
        deployment_agent=DeploymentAgent(OfflineDeploymentTool()),
    )


def make_request(service_name: str, **overrides: object) -> InvestigateRequest:
    """Build a valid InvestigateRequest for one demo scenario's service."""
    fields: dict[str, object] = {
        "investigation_id": uuid4(),
        "service_name": service_name,
        "environment": "production",
        "repository": "org/air-services",
        "start_time": START,
        "end_time": START + timedelta(hours=2),
    }
    fields.update(overrides)
    return InvestigateRequest.model_validate(fields)


@pytest.mark.anyio
async def test_web_ui_scenario_is_a_fast_contract_failure_not_a_timeout() -> None:
    """web-ui: parsing errors, healthy latency, no slow spans -- unlike payment-service."""
    evidence = await make_investigator().investigate(make_request("web-ui"))
    by_agent = {item.agent_name: item for item in evidence.evidence}

    logs = by_agent["LogsAgent"].findings
    assert logs["exceptions"] == {"response_parse_error": 5}

    metrics = by_agent["MetricsAgent"].findings
    assert metrics["http_5xx_rate"]["health"] == "UNHEALTHY"
    assert metrics["p95_latency_ms"]["health"] == "HEALTHY"

    traces = by_agent["TracesAgent"].findings
    assert traces["error_span_count"] == 5
    assert traces["slow_span_count"] == 0
    assert traces["primary_error_operation"] == "render_checkout_page"

    deployment = by_agent["DeploymentAgent"].findings
    assert deployment["deployment_detected"] is True
    assert deployment["latest_deployment"]["version"] == "3.2.0"
    assert deployment["changed_files"] == ["src/adapters/order-api-client.ts"]


@pytest.mark.anyio
async def test_ledger_service_scenario_has_no_deployment_and_no_slow_spans() -> None:
    """ledger-service: disk exhaustion, no deployment implicated, fast (not slow) failures."""
    evidence = await make_investigator().investigate(
        make_request(
            "ledger-service",
            required_metrics=[
                "cpu_pct",
                "memory_pct",
                "http_5xx_rate",
                "p95_latency_ms",
                "disk_usage_pct",
            ],
        )
    )
    by_agent = {item.agent_name: item for item in evidence.evidence}

    logs = by_agent["LogsAgent"].findings
    assert logs["exceptions"] == {"disk_write_failed": 5}

    metrics = by_agent["MetricsAgent"].findings
    assert metrics["disk_usage_pct"]["health"] == "UNHEALTHY"
    assert metrics["disk_usage_pct"]["current_avg"] >= 0.95  # near the 99.8% the scenario describes
    assert metrics["disk_usage_pct"]["max"] <= 1.0  # never a physically impossible >100% sample
    assert metrics["p95_latency_ms"]["health"] == "HEALTHY"

    traces = by_agent["TracesAgent"].findings
    assert traces["error_span_count"] == 10  # both outer and inner span error
    assert traces["slow_span_count"] == 0

    deployment = by_agent["DeploymentAgent"].findings
    assert deployment["deployment_detected"] is False
    assert by_agent["DeploymentAgent"].confidence < 0.5


@pytest.mark.anyio
async def test_rca_reaches_completed_for_both_new_scenarios() -> None:
    """Both scenarios have enough notable evidence for RCA to run and complete."""
    rca_service = RcaService(OfflineInvestigationModel())
    for service_name, required_metrics in (
        ("web-ui", []),
        ("ledger-service", ["disk_usage_pct", "http_5xx_rate"]),
    ):
        evidence = await make_investigator().investigate(
            make_request(service_name, required_metrics=required_metrics)
        )
        result = rca_service.investigate(evidence)
        assert result.investigation_status == "COMPLETED"
        assert result.rca is not None


def test_unrelated_service_is_unaffected_by_the_new_scenarios() -> None:
    """Adding two new named scenarios must not change any other service's behavior."""
    from air_agent_app.tools.mock.fixtures.log_dump import generate_application_log_dump

    lines = generate_application_log_dump(service_name="some-other-service")
    assert all(" INFO " in line for line in lines)
