"""Section 4.2-4.3: LogsAgent's request contract and normalized log record."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from air_agent_app.models.request_fields import ShortText, TimeWindowRequest


class LogEvidenceRequest(TimeWindowRequest):
    """What LogsAgent is asked to check; owned by the caller, not the agent."""

    investigation_id: UUID
    service_name: ShortText
    environment: ShortText
    required_evidence: list[str] = Field(default_factory=list)
    hypothesis_context: list[str] = Field(default_factory=list)
    namespace: ShortText | None = None
    cluster: ShortText | None = None
    pod: ShortText | None = None
    max_results: int = Field(default=5000, ge=1, le=50000)


class LogQuery(BaseModel):
    """The vendor-agnostic query LogsQueryBuilder derives from a request.

    Deliberately narrower than ``LogEvidenceRequest``: a tool adapter should
    see only what it needs to fetch data, not planning context such as
    ``hypothesis_context`` or ``required_evidence``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_name: str
    environment: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    namespace: str | None = None
    cluster: str | None = None
    pod: str | None = None
    max_results: int = Field(ge=1, le=50000)


class NormalizedLogEvent(BaseModel):
    """One parsed log line; the unit LogPatternExtractor counts and groups."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: AwareDatetime
    service: str
    environment: str
    level: str
    message: str
    exception_type: str | None = None
    exception_message: str | None = None
    class_name: str | None = None
    method_name: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    host: str | None = None
    pod: str | None = None
    namespace: str | None = None
    http_status: int | None = None
