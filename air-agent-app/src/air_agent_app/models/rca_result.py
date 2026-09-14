"""Section 9: the LLM Investigation Agent's structured output contract.

Schema follows `reference/AIR-Investigation.pdf` ("LLM Integration - Direct
Evidence Collection Handoff", v2.0) section 7 exactly: KeyFinding,
RootCauseAnalysis, Suggestion, SuggestionPlan, InvestigationResult. One
deliberate deviation from the PDF's pseudocode: ``investigation_id`` is
still part of this schema (so the type matches the PDF and downstream
consumers get one self-describing object), but the service
(`investigation/rca_service.py`) always overwrites whatever the LLM
returns for it with the trusted value from the evidence payload before
returning a result. Never trust a model to echo a UUID back correctly.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Priority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Risk = Literal["LOW", "MEDIUM", "HIGH"]
InvestigationStatus = Literal["COMPLETED", "INCONCLUSIVE"]


class KeyFinding(BaseModel):
    """One evidence-backed observation, never a root cause by itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1)
    finding: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class RootCauseAnalysis(BaseModel):
    """The most defensible explanation the evidence supports, or none at all.

    ``uncertainty`` is not decorative: rule 7 of the system prompt requires
    stating explicitly when multiple explanations remain plausible, rather
    than silently picking one.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    root_cause: str = Field(min_length=1)
    contributing_factors: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: str | None = None


class Suggestion(BaseModel):
    """One recommended action, always traceable back to the evidence that motivated it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    suggestion_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority: Priority
    risk: Risk
    requires_human_approval: bool
    source_refs: list[str] = Field(default_factory=list)


class SuggestionPlan(BaseModel):
    """A safe remediation plan: what to do, how to verify it, how to undo it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    immediate_actions: list[Suggestion] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    follow_up_actions: list[str] = Field(default_factory=list)


class InvestigationResult(BaseModel):
    """The LLM Investigation Agent's complete, schema-based response.

    ``INCONCLUSIVE`` is a first-class, expected outcome (Section 9's "Unknown
    is a valid result" rule): when the evidence cannot support a defensible
    root cause, ``rca`` and ``suggestion_plan`` stay ``None`` rather than a
    fabricated cause being forced into the schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    investigation_id: UUID
    investigation_status: InvestigationStatus
    key_findings: list[KeyFinding] = Field(default_factory=list)
    rca: RootCauseAnalysis | None = None
    suggestion_plan: SuggestionPlan | None = None
    overall_confidence: float = Field(ge=0.0, le=1.0)
    source_refs_used: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
