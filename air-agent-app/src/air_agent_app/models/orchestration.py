"""End-to-end orchestration: one request, all three stages, one nested response.

`OrchestrationRequest` deliberately carries more than `IncidentInput` alone:
Planning only needs the incident's own facts, but Evidence Collection needs
a query time window and (for `DeploymentAgent`) a repository -- neither of
which `IncidentInput` carries, and neither of which this module invents a
default for. Reusing `TimeWindowRequest` here is the same choice already
made for every evidence-agent request.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from air_agent_app.models.incident import IncidentInput
from air_agent_app.models.investigate import InvestigateResponse
from air_agent_app.models.planning_response import PlanningResponse
from air_agent_app.models.rca_result import InvestigationResult
from air_agent_app.models.request_fields import ShortText, TimeWindowRequest


class OrchestrationRequest(TimeWindowRequest):
    """Everything needed to run Planning, Evidence Collection, and RCA for one incident.

    ``required_metrics``/``required_operations`` exist here for the same
    reason ``InvestigateRequest`` has them: the Planner does not produce
    per-agent breakdowns like these today (it only produces a generic
    ``required_evidence`` list), so a caller who knows a scenario needs a
    metric outside ``MetricsAgent.DEFAULT_METRICS`` (e.g. ``disk_usage_pct``,
    not one of the four default metrics) has to say so explicitly here --
    the orchestrator cannot infer it from the incident alone. See
    `docs/extension_03_end_to_end_orchestration_agent.md` section 6.
    """

    incident: IncidentInput
    repository: ShortText | None = None
    branch: ShortText | None = None
    deployment_environment: ShortText | None = None
    namespace: ShortText | None = None
    cluster: ShortText | None = None
    pod: ShortText | None = None
    required_metrics: list[str] = Field(default_factory=list)
    required_operations: list[str] = Field(default_factory=list)


OrchestrationStatus = Literal[
    "COMPLETED",
    "INCONCLUSIVE",
    "PLANNER_FAILED",
    "EVIDENCE_REQUEST_INVALID",
    "NO_EVIDENCE_COLLECTED",
    "RCA_FAILED",
]


class OrchestrationResponse(BaseModel):
    """The full pipeline outcome: every stage's own response, nested, plus one final status.

    `planning` is always present -- the graph always runs that stage first.
    `evidence`/`rca` are `None` whenever the pipeline stopped before that
    stage ran; `status` tells the caller exactly why (see
    `docs/extension_03_end_to_end_orchestration_agent.md` for the full
    meaning of each value).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    investigation_id: UUID
    incident_id: UUID
    status: OrchestrationStatus
    terminal_reason: str | None = None
    planning: PlanningResponse
    evidence: InvestigateResponse | None = None
    rca: InvestigationResult | None = None
