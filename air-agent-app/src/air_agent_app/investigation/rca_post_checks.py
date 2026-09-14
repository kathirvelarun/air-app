"""Section 9 post-LLM checks: validate the output contract, not input evidence quality.

Per `reference/AIR-Investigation.pdf` section 13: there is no separate
EvidenceValidator in this flow. These two checks run after the LLM
response and protect callers from an untrustworthy *output* (invented
source references, an unapproved production change) -- they never
second-guess the evidence the LLM was given.
"""

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.models.exceptions import UnknownSourceReferenceError
from air_agent_app.models.rca_result import InvestigationResult

logger = get_logger(__name__)

# Any of these appearing in a suggested action's text means it changes
# production state and must require a human to approve it, regardless of
# what the model itself set `requires_human_approval` to.
_PRODUCTION_CHANGE_TERMS = (
    "rollback",
    "roll back",
    "redeploy",
    "restart",
    "scale",
    "change config",
    "configuration change",
    "disable",
    "enable",
    "route traffic",
)


def validate_source_refs(
    result: InvestigationResult,
    source_reference_map: dict[str, dict[str, str]],
) -> None:
    """Reject an InvestigationResult that cites a source reference not in the evidence.

    Every ``source_refs`` list across key findings, the RCA, and suggested
    actions is checked against ``source_reference_map`` (the exact set the
    model was told it may cite). Anything else means the model invented an
    evidence ID or reference, which the system prompt explicitly forbids.
    """
    allowed = set(source_reference_map)
    used: set[str] = set(result.source_refs_used)
    for finding in result.key_findings:
        used.update(finding.source_refs)
    if result.rca is not None:
        used.update(result.rca.source_refs)
    if result.suggestion_plan is not None:
        for action in result.suggestion_plan.immediate_actions:
            used.update(action.source_refs)

    unknown = used - allowed
    if unknown:
        logger.warning(
            "RCA response cited unknown source references investigation_id=%s count=%s",
            result.investigation_id,
            len(unknown),
        )
        raise UnknownSourceReferenceError(
            f"LLM returned unknown source references: {sorted(unknown)}"
        )


def enforce_human_approval(result: InvestigationResult) -> InvestigationResult:
    """Force ``requires_human_approval = True`` on any production-changing suggestion.

    Models are given this same rule (system prompt rule 12), but this
    application-level check makes it non-optional: the model's own flag is
    never trusted alone for actions with production impact. Every model
    here is frozen, so a changed suggestion means a new object, never a
    mutation in place.
    """
    if result.suggestion_plan is None:
        return result

    updated_actions = [
        action.model_copy(update={"requires_human_approval": True})
        if not action.requires_human_approval and _is_production_change(action.action)
        else action
        for action in result.suggestion_plan.immediate_actions
    ]
    if updated_actions == result.suggestion_plan.immediate_actions:
        return result

    updated_plan = result.suggestion_plan.model_copy(update={"immediate_actions": updated_actions})
    return result.model_copy(update={"suggestion_plan": updated_plan})


def _is_production_change(action_text: str) -> bool:
    """Check for a production-change term without depending on the model's own labeling."""
    lowered = action_text.lower()
    return any(term in lowered for term in _PRODUCTION_CHANGE_TERMS)
