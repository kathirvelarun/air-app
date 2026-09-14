"""Offline RCA fixture: derives a fixture from the real supplied evidence.

Unlike ``OfflinePlanModel`` (which ignores its input entirely and returns a
fixed canned plan), this fixture must not: ``InvestigationResult.source_refs_used``
and every finding's ``source_refs`` are re-checked against the evidence
actually supplied (`investigation/rca_post_checks.py::validate_source_refs`),
so a hardcoded reference list would break for any request that omits an
agent. Deriving the fixture from the real evidence keeps every offline
scenario (all four agents, a subset, or an all-healthy service) valid
without special-casing.
"""

from air_agent_app.investigation.rca_source_refs import evidence_ref
from air_agent_app.models.investigate import InvestigateResponse
from air_agent_app.models.rca_result import (
    InvestigationResult,
    KeyFinding,
    RootCauseAnalysis,
    Suggestion,
    SuggestionPlan,
)

# Matches the "found something" confidence tier every evidence agent already
# uses (see AGENTS.md / each agent's own _build_evidence): ~0.9-0.99 means an
# agent found a real signal, ~0.85 means healthy/negative evidence, ~0.4
# means no data. Reusing that tier means this fixture never needs its own
# agent-specific parsing.
_NOTABLE_CONFIDENCE_THRESHOLD = 0.9


class OfflineInvestigationModel:
    """Ground every finding, RCA, and suggestion in the evidence actually supplied."""

    def generate(
        self,
        evidence: InvestigateResponse,
        source_reference_map: dict[str, dict[str, str]],
    ) -> InvestigationResult:
        """Return INCONCLUSIVE with no notable evidence, else a grounded COMPLETED result."""
        notable = [
            item for item in evidence.evidence if item.confidence >= _NOTABLE_CONFIDENCE_THRESHOLD
        ]
        if not notable:
            return InvestigationResult(
                investigation_id=evidence.investigation_id,
                investigation_status="INCONCLUSIVE",
                key_findings=[],
                rca=None,
                suggestion_plan=None,
                overall_confidence=0.4,
                source_refs_used=[],
                missing_information=["OFFLINE FIXTURE: no evidence met the notability threshold."],
            )

        refs = [evidence_ref(item) for item in notable]
        key_findings = [
            KeyFinding(
                finding_id=f"KF-{index:03d}",
                finding=f"OFFLINE FIXTURE: {item.summary}",
                source_refs=[evidence_ref(item)],
                confidence=item.confidence,
            )
            for index, item in enumerate(notable, start=1)
        ]
        rca = RootCauseAnalysis(
            root_cause=f"OFFLINE FIXTURE: {notable[0].summary}",
            contributing_factors=[item.title for item in notable[1:]],
            source_refs=refs,
            confidence=min(item.confidence for item in notable),
            uncertainty="OFFLINE FIXTURE: heuristic placeholder, not real model reasoning.",
        )
        suggestion = Suggestion(
            suggestion_id="SG-001",
            action=f"OFFLINE FIXTURE: investigate {notable[0].agent_name} findings further",
            rationale=notable[0].summary,
            priority="HIGH",
            risk="LOW",
            requires_human_approval=False,
            source_refs=refs,
        )
        plan = SuggestionPlan(
            immediate_actions=[suggestion],
            verification_steps=["OFFLINE FIXTURE: confirm the cited evidence recovers."],
            rollback_plan=[],
            follow_up_actions=[],
        )
        return InvestigationResult(
            investigation_id=evidence.investigation_id,
            investigation_status="COMPLETED",
            key_findings=key_findings,
            rca=rca,
            suggestion_plan=plan,
            overall_confidence=min(item.confidence for item in notable),
            source_refs_used=refs,
            missing_information=[],
        )
