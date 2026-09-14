"""Section 6.2-6.3: DeploymentAgent's request contract and normalized event."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from air_agent_app.models.request_fields import ShortText, TimeWindowRequest


class DeploymentEvidenceRequest(TimeWindowRequest):
    """What DeploymentAgent is asked to check; owned by the caller, not the agent."""

    investigation_id: UUID
    service_name: ShortText
    environment: ShortText
    repository: ShortText
    branch: ShortText | None = None
    deployment_environment: ShortText | None = None
    required_evidence: list[str] = Field(default_factory=list)


class DeploymentQuery(BaseModel):
    """The vendor-agnostic query DeploymentAgent derives from a request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str
    service_name: str
    environment: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    branch: str | None = None
    deployment_environment: str | None = None


class NormalizedDeploymentEvent(BaseModel):
    """One parsed GitHub event: a deployment, or a commit included in one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str
    timestamp: AwareDatetime
    repository: str
    environment: str | None = None
    version: str | None = None
    commit_sha: str | None = None
    branch: str | None = None
    actor: str | None = None
    workflow_name: str | None = None
    workflow_run_id: str | None = None
    status: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    rollback: bool = False
    reference_url: str | None = None
