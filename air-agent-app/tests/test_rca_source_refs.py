"""Deterministic source-reference derivation, never LLM-invented IDs."""

from datetime import UTC, datetime
from uuid import uuid4

from air_agent_app.investigation.rca_source_refs import build_source_reference_map, evidence_ref
from air_agent_app.models.evidence import Evidence
from air_agent_app.models.investigate import InvestigateResponse

NOW = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


def make_evidence(agent_name: str, evidence_type: str) -> Evidence:
    """Build a minimal valid Evidence item for one agent/type combination."""
    return Evidence(
        investigation_id=uuid4(),
        agent_name=agent_name,
        evidence_type=evidence_type,
        source_system="ELF",
        title="title",
        summary="summary",
        confidence=0.9,
        findings={},
        collected_at=NOW,
    )


def test_evidence_ref_is_agent_name_slash_evidence_type() -> None:
    """The reference format matches the guide's own worked examples exactly."""
    item = make_evidence("LogsAgent", "LOG")
    assert evidence_ref(item) == "LogsAgent/LOG"


def test_build_source_reference_map_covers_every_evidence_item() -> None:
    """Every evidence item gets exactly one reference, carrying its own metadata."""
    investigation_id = uuid4()
    response = InvestigateResponse(
        investigation_id=investigation_id,
        evidence=[
            make_evidence("LogsAgent", "LOG"),
            make_evidence("MetricsAgent", "METRIC"),
        ],
    )
    reference_map = build_source_reference_map(response)
    assert set(reference_map) == {"LogsAgent/LOG", "MetricsAgent/METRIC"}
    assert reference_map["LogsAgent/LOG"] == {
        "agent_name": "LogsAgent",
        "evidence_type": "LOG",
        "source_system": "ELF",
    }


def test_build_source_reference_map_is_empty_for_no_evidence() -> None:
    """No evidence means no reference the model is allowed to cite."""
    response = InvestigateResponse(investigation_id=uuid4(), evidence=[])
    assert build_source_reference_map(response) == {}
