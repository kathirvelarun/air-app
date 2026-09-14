"""Section 8: aggregate evidence from all agents into one schema-based response.

InvestigateRequest is a superset of every evidence agent's own request model,
so one HTTP call can fan out to all of them; each agent still only ever sees
its own narrower request (built in investigation/evidence_investigator.py).

InvestigateResponse matches the guide's own Section 8.2 AggregatedEvidence
shape exactly: investigation_id, evidence, missing_agents, duplicate_count,
timeline. Nothing beyond that. Two things that lived here before were
removed rather than kept as convenient extras:

- A ``key_findings`` digest (agent/title/summary/confidence, dropping the
  raw ``findings`` dict). Removed: it was a second, redundant view of the
  same ``evidence`` list, and "schema-based" means one deliberate structure
  per concern, not a derived summary sitting next to the data it summarizes.
- RCA (Section 9). An earlier version included a deterministic, rule-based
  RootCauseAssessment as a placeholder; removed because it wasn't real
  reasoning and would only have to be redesigned once real RCA arrives. The
  plan is a genuine LLM-based RCA agent (mirroring how Section 1's Planner
  integrates one), added back as its own step once built -- not before.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from air_agent_app.models.evidence import Evidence, EvidenceType
from air_agent_app.models.request_fields import ShortText, TimeWindowRequest

# The four implemented evidence agents. Kept as a Literal (not a bare str)
# so an unknown agent name is a clean 422 at the request boundary, not a
# ValueError raised deep inside EvidenceInvestigator.
AgentName = Literal["LogsAgent", "MetricsAgent", "TracesAgent", "DeploymentAgent"]
DEFAULT_AGENTS: tuple[AgentName, ...] = (
    "LogsAgent",
    "MetricsAgent",
    "TracesAgent",
    "DeploymentAgent",
)

NonEmptyAgentList = Annotated[list[AgentName], Field(min_length=1)]


class InvestigateRequest(TimeWindowRequest):
    """What to investigate and which agents to run; owned by the caller."""

    investigation_id: UUID
    service_name: ShortText
    environment: ShortText
    agents: NonEmptyAgentList = Field(default_factory=lambda: list(DEFAULT_AGENTS))
    repository: ShortText | None = None
    branch: ShortText | None = None
    deployment_environment: ShortText | None = None
    namespace: ShortText | None = None
    cluster: ShortText | None = None
    pod: ShortText | None = None
    required_evidence: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)
    required_operations: list[str] = Field(default_factory=list)
    hypothesis_context: list[str] = Field(default_factory=list)
    slow_span_threshold_ms: float = Field(default=1000.0, gt=0, le=60_000)
    step_seconds: int = Field(default=60, ge=15, le=300)
    max_results: int = Field(default=5000, ge=1, le=50000)

    @model_validator(mode="after")
    def validate_repository_for_deployment_agent(self) -> "InvestigateRequest":
        """DeploymentAgent structurally needs a repository; fail fast if it's missing."""
        if "DeploymentAgent" in self.agents and self.repository is None:
            raise ValueError("repository is required when DeploymentAgent is among agents")
        return self


class TimelineEvent(BaseModel):
    """One evidence result, ordered for the aggregated timeline (Section 8.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: AwareDatetime
    agent_name: str
    evidence_type: EvidenceType
    title: str


class InvestigateResponse(BaseModel):
    """Section 8.2's AggregatedEvidence shape: the whole response, nothing more.

    ``duplicate_count`` is always ``0`` today: every agent currently returns
    exactly one Evidence per run, so no two evidence items can collide. The
    field is real, not decorative -- Section 8.1 requires the Aggregator to
    "deduplicate or link duplicate observations" -- it just has nothing to
    count yet. Wire real dedup logic here if an agent ever returns more than
    one Evidence, or once RecentIncidentAgent can overlap with the others.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    investigation_id: UUID
    evidence: list[Evidence]
    missing_agents: list[str] = Field(default_factory=list)
    duplicate_count: int = Field(default=0, ge=0)
    timeline: list[TimelineEvent] = Field(default_factory=list)
