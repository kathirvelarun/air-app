"""TracesAgent's request contract and normalized span record.

Not part of the guide's four defined evidence agents (Sections 4-7 cover
Logs, Metrics, Deployment, RecentIncident only). TracesAgent is a locally
designed fifth specialist, built to the same request -> query -> tool ->
normalize -> deterministic-analysis -> Evidence shape, for distributed
tracing platforms (e.g. Jaeger, OpenTelemetry). See
docs/extension_01_traces_agent.md.
"""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from air_agent_app.models.request_fields import ShortText, TimeWindowRequest


class TraceEvidenceRequest(TimeWindowRequest):
    """What TracesAgent is asked to check; owned by the caller, not the agent."""

    investigation_id: UUID
    service_name: ShortText
    environment: ShortText
    required_operations: list[str] = Field(default_factory=list)
    namespace: ShortText | None = None
    cluster: ShortText | None = None
    pod: ShortText | None = None
    slow_span_threshold_ms: float = Field(default=1000.0, gt=0, le=60_000)
    max_results: int = Field(default=5000, ge=1, le=50000)


class TraceQuery(BaseModel):
    """The vendor-agnostic query TracesQueryBuilder derives from a request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_name: str
    environment: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    operation_names: list[str] = Field(default_factory=list)
    namespace: str | None = None
    cluster: str | None = None
    pod: str | None = None
    max_results: int = Field(ge=1, le=50000)


class NormalizedSpan(BaseModel):
    """One parsed span; the unit TracePatternExtractor counts and groups."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str
    span_id: str
    parent_span_id: str | None
    service: str
    environment: str
    operation: str
    timestamp: AwareDatetime
    duration_ms: float
    status: str
    error_type: str | None = None
