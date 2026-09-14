"""Section 5.2-5.3: MetricsAgent's request contract and normalized series."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from air_agent_app.models.request_fields import ShortText, TimeWindowRequest


class MetricEvidenceRequest(TimeWindowRequest):
    """What MetricsAgent is asked to check; owned by the caller, not the agent."""

    investigation_id: UUID
    service_name: ShortText
    environment: ShortText
    required_metrics: list[str] = Field(default_factory=list)
    namespace: ShortText | None = None
    cluster: ShortText | None = None
    pod: ShortText | None = None
    step_seconds: int = Field(default=60, ge=15, le=300)


class MetricQuery(BaseModel):
    """The vendor-agnostic query MetricsQueryBuilder derives from a request.

    Spans both the baseline and the incident window in one range, so the
    tool adapter makes one call per metric; MetricsAgent splits the returned
    samples at ``start_time`` itself. ``window_start`` is always exactly one
    incident-length span before ``window_end``'s incident half begins (see
    ``_build_query`` in ``investigation/metrics_agent.py``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_name: str
    environment: str
    window_start: AwareDatetime
    window_end: AwareDatetime
    metric_names: list[str]
    namespace: str | None = None
    cluster: str | None = None
    pod: str | None = None
    step_seconds: int = Field(ge=15, le=300)


class MetricSample(BaseModel):
    """One (timestamp, value) point in a time series."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: AwareDatetime
    value: float


class NormalizedMetricSeries(BaseModel):
    """One metric's samples, with the service/environment context attached."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_name: str
    service: str
    environment: str
    unit: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    samples: list[MetricSample]
