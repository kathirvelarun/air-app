"""Section 9: deterministic source references, never LLM-invented ones.

The evidence payload has no per-item ID (`Evidence` carries no `id` field),
so the LLM must not invent one like "log-001". Instead every evidence item
gets a stable reference derived from its own identity: `{agent_name}/{evidence_type}`.
This is supplied to the model explicitly (`source_references` in the user
prompt) and re-checked against the model's response afterward
(`investigation/rca_post_checks.py`).
"""

from air_agent_app.models.evidence import Evidence
from air_agent_app.models.investigate import InvestigateResponse


def evidence_ref(item: Evidence) -> str:
    """Build the one deterministic reference for one evidence item.

    If evidence agents ever add a native ``evidence_id``, prefer that field
    and keep this derived reference as metadata only -- not before.
    """
    return f"{item.agent_name}/{item.evidence_type}"


def build_source_reference_map(response: InvestigateResponse) -> dict[str, dict[str, str]]:
    """Map every allowed reference to the metadata the LLM may cite it by."""
    return {
        evidence_ref(item): {
            "agent_name": item.agent_name,
            "evidence_type": item.evidence_type,
            "source_system": item.source_system,
        }
        for item in response.evidence
    }
