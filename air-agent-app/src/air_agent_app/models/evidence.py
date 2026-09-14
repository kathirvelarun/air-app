"""Section 3.1: the shared contract every evidence agent returns.

Evidence agents state observable facts. They never assert a root cause and
never recommend remediation; that boundary is enforced by convention here
and by each agent's own instructions, not by this schema alone.
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# LOG/METRIC/DEPLOYMENT/HISTORICAL_INCIDENT are the guide's own four evidence
# types (Sections 4-7). TRACE is a local extension for TracesAgent, a fifth
# specialist not defined in the guide -- see docs/extension_01_traces_agent.md.
EvidenceType = Literal["LOG", "METRIC", "DEPLOYMENT", "HISTORICAL_INCIDENT", "TRACE"]


class EvidenceReference(BaseModel):
    """A pointer back to the raw data behind a finding, for auditability.

    The guide requires evidence to carry references but does not specify
    their shape; this is a local design choice, not a literal guide contract.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    source_type: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    description: str | None = None


class Evidence(BaseModel):
    """One observation from one evidence agent, ready for aggregation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    investigation_id: UUID
    agent_name: str = Field(min_length=1)
    evidence_type: EvidenceType
    source_system: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    findings: dict[str, Any]
    references: list[EvidenceReference] = Field(default_factory=list)
    observed_from: AwareDatetime | None = None
    observed_to: AwareDatetime | None = None
    collected_at: AwareDatetime
