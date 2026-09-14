"""RcaService: the LLM Investigation Agent over a real evidence-collection payload.

Uses the real offline evidence pipeline (all four agents) to produce a
genuine `InvestigateResponse`, then feeds it straight into `RcaService` --
proving the "Direct Evidence Collection Handoff" architecture actually
holds: Section 8's output is valid Section 9 input with no transformation
in between.
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
from air_agent_app.models.exceptions import RcaExecutionError, UnknownSourceReferenceError
from air_agent_app.models.investigate import InvestigateRequest, InvestigateResponse
from air_agent_app.models.rca_result import InvestigationResult
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


async def collect_evidence(**overrides: object) -> InvestigateResponse:
    """Run the real evidence-collection pipeline to produce a genuine handoff payload."""
    fields: dict[str, object] = {
        "investigation_id": uuid4(),
        "service_name": "payment-service",
        "environment": "production",
        "repository": "org/air-services",
        "start_time": START,
        "end_time": START + timedelta(hours=2),
    }
    fields.update(overrides)
    request = InvestigateRequest.model_validate(fields)
    return await make_investigator().investigate(request)


class BrokenSourceRefClient:
    """Always cites a source reference absent from the supplied evidence."""

    def generate(
        self, evidence: InvestigateResponse, source_reference_map: dict
    ) -> InvestigationResult:
        """Return a result that fails validate_source_refs no matter what evidence it gets."""
        return InvestigationResult(
            investigation_id=evidence.investigation_id,
            investigation_status="COMPLETED",
            overall_confidence=0.9,
            source_refs_used=["FakeAgent/FAKE"],
        )


@pytest.mark.anyio
async def test_direct_handoff_from_evidence_collection_produces_a_completed_result() -> None:
    """The full payment-service scenario: real evidence in, a grounded RCA out."""
    evidence = await collect_evidence()
    result = RcaService(OfflineInvestigationModel()).investigate(evidence)

    assert result.investigation_id == evidence.investigation_id
    assert result.investigation_status == "COMPLETED"
    assert result.rca is not None
    assert len(result.key_findings) == len(evidence.evidence)
    allowed_refs = {f"{item.agent_name}/{item.evidence_type}" for item in evidence.evidence}
    assert set(result.source_refs_used) <= allowed_refs


@pytest.mark.anyio
async def test_all_healthy_evidence_returns_inconclusive_not_a_fabricated_rca() -> None:
    """No notable evidence means INCONCLUSIVE, never a guessed root cause."""
    evidence = await collect_evidence(service_name="unrelated-service")
    result = RcaService(OfflineInvestigationModel()).investigate(evidence)

    assert result.investigation_status == "INCONCLUSIVE"
    assert result.rca is None
    assert result.suggestion_plan is None


@pytest.mark.anyio
async def test_persistent_invented_source_refs_raise_after_bounded_retry() -> None:
    """A client that always cites unknown references fails closed, not silently accepted."""
    evidence = await collect_evidence()
    with pytest.raises(RcaExecutionError) as excinfo:
        RcaService(BrokenSourceRefClient()).investigate(evidence)
    assert isinstance(excinfo.value.__cause__, UnknownSourceReferenceError)


@pytest.mark.anyio
async def test_investigation_id_is_always_the_evidence_investigation_id() -> None:
    """The service trusts its own evidence payload for the ID, never the model's echo."""

    class WrongIdClient:
        """Simulates a model echoing back the wrong investigation_id."""

        def generate(
            self, evidence: InvestigateResponse, source_reference_map: dict
        ) -> InvestigationResult:
            """Return a result carrying a fabricated, unrelated investigation_id."""
            return InvestigationResult(
                investigation_id=uuid4(),
                investigation_status="INCONCLUSIVE",
                overall_confidence=0.4,
            )

    evidence = await collect_evidence()
    result = RcaService(WrongIdClient()).investigate(evidence)
    assert result.investigation_id == evidence.investigation_id
