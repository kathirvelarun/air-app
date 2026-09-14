"""Post-LLM checks: output-contract validation, not an EvidenceValidator."""

from uuid import uuid4

import pytest

from air_agent_app.investigation.rca_post_checks import enforce_human_approval, validate_source_refs
from air_agent_app.models.exceptions import UnknownSourceReferenceError
from air_agent_app.models.rca_result import InvestigationResult, Suggestion, SuggestionPlan

SOURCE_REFERENCE_MAP = {
    "LogsAgent/LOG": {"agent_name": "LogsAgent", "evidence_type": "LOG", "source_system": "ELF"},
}


def make_result(**overrides: object) -> InvestigationResult:
    """Build a minimal valid InvestigationResult, overriding only what a test needs."""
    fields: dict[str, object] = {
        "investigation_id": uuid4(),
        "investigation_status": "COMPLETED",
        "key_findings": [],
        "rca": None,
        "suggestion_plan": None,
        "overall_confidence": 0.9,
        "source_refs_used": [],
        "missing_information": [],
    }
    fields.update(overrides)
    return InvestigationResult.model_validate(fields)


def test_validate_source_refs_accepts_only_known_references() -> None:
    """A reference present in the supplied evidence passes silently."""
    result = make_result(source_refs_used=["LogsAgent/LOG"])
    validate_source_refs(result, SOURCE_REFERENCE_MAP)


def test_validate_source_refs_rejects_an_invented_reference() -> None:
    """A reference absent from the supplied evidence is rejected, not silently trusted."""
    result = make_result(source_refs_used=["LogsAgent/LOG", "FakeAgent/FAKE"])
    with pytest.raises(UnknownSourceReferenceError, match="FakeAgent/FAKE"):
        validate_source_refs(result, SOURCE_REFERENCE_MAP)


def test_validate_source_refs_checks_suggestion_source_refs_too() -> None:
    """An invented reference inside a suggestion's own source_refs is caught too."""
    result = make_result(
        suggestion_plan=SuggestionPlan(
            immediate_actions=[
                Suggestion(
                    suggestion_id="SG-001",
                    action="Investigate further",
                    rationale="r",
                    priority="HIGH",
                    risk="LOW",
                    requires_human_approval=False,
                    source_refs=["log-001"],
                )
            ]
        )
    )
    with pytest.raises(UnknownSourceReferenceError, match="log-001"):
        validate_source_refs(result, SOURCE_REFERENCE_MAP)


def test_enforce_human_approval_flips_only_production_changing_actions() -> None:
    """A rollback is forced to require approval; a read-only diagnostic step is untouched."""
    result = make_result(
        suggestion_plan=SuggestionPlan(
            immediate_actions=[
                Suggestion(
                    suggestion_id="SG-001",
                    action="Roll back the deployment to the previous release",
                    rationale="r",
                    priority="HIGH",
                    risk="MEDIUM",
                    requires_human_approval=False,
                    source_refs=[],
                ),
                Suggestion(
                    suggestion_id="SG-002",
                    action="Check upstream connectivity from production pods",
                    rationale="r",
                    priority="CRITICAL",
                    risk="LOW",
                    requires_human_approval=False,
                    source_refs=[],
                ),
            ]
        )
    )
    updated = enforce_human_approval(result)
    actions = {
        action.suggestion_id: action.requires_human_approval
        for action in updated.suggestion_plan.immediate_actions
    }
    assert actions == {"SG-001": True, "SG-002": False}


def test_enforce_human_approval_never_mutates_the_original_result() -> None:
    """Every model here is frozen: a changed suggestion means a new object, not a mutation."""
    result = make_result(
        suggestion_plan=SuggestionPlan(
            immediate_actions=[
                Suggestion(
                    suggestion_id="SG-001",
                    action="Redeploy the previous known-good release",
                    rationale="r",
                    priority="HIGH",
                    risk="MEDIUM",
                    requires_human_approval=False,
                    source_refs=[],
                )
            ]
        )
    )
    enforce_human_approval(result)
    assert result.suggestion_plan.immediate_actions[0].requires_human_approval is False


def test_enforce_human_approval_is_a_no_op_without_a_suggestion_plan() -> None:
    """No suggestion plan means nothing to enforce; the same object comes back."""
    result = make_result(suggestion_plan=None)
    assert enforce_human_approval(result) is result
