"""Validated monitoring alert contract."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class AlertInput(BaseModel):
    """Normalized monitoring event; source plus eventId is its delivery identity."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    event_id: str = Field(alias="eventId", min_length=1, max_length=160)
    source: Literal["ELF", "UI", "Grafana"]
    service: str = Field(min_length=1, max_length=120)
    environment: Literal["demo", "development", "staging", "production"]
    rule: str = Field(min_length=1, max_length=160)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    summary: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=4000)
    observed_at: AwareDatetime = Field(alias="observedAt")
    owner: str = Field(default="SRE on-call", min_length=1, max_length=120)
    repository: str = Field(default="org/air-services", min_length=1, max_length=200)
    required_metrics: list[str] = Field(
        alias="requiredMetrics", default_factory=list, max_length=30
    )
    simulated: Literal[True] = True
