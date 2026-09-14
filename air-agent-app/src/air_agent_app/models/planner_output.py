"""Section 1: the Planner's decision, separate from workflow state."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContextRequest(BaseModel):
    """Proposed local contract; the guide does not specify these fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class PlannerOutput(BaseModel):
    """An investigation strategy. Hypotheses are leads, not proven causes.

    Pydantic validates data shape. The graph separately requires at least one
    selected agent before marking the plan ready.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    planner_version: str = Field(default="1.0", alias="plannerVersion", min_length=1)
    status: Literal["READY"]
    confidence: float = Field(ge=0.0, le=1.0)

    investigation_type: str | None = Field(default=None, alias="investigationType")
    priority: str | None = None

    # Python uses snake_case; aliases preserve the guide's JSON contract.
    # Each instance receives its own lists.
    parallel_agents: list[str] = Field(default_factory=list, alias="parallelAgents")
    required_evidence: list[str] = Field(default_factory=list, alias="requiredEvidence")
    hypotheses: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list, alias="missingContext")
    context_requests: list[ContextRequest] = Field(default_factory=list, alias="contextRequests")

    reasoning: str = Field(min_length=1)
