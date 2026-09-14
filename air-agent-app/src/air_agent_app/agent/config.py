"""Explicit runtime configuration; no network calls at import time."""

import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.models.exceptions import ConfigurationError

logger = get_logger(__name__)


class ModelSettings(BaseModel):
    """Required provider choices and a bounded per-request timeout."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    model_name: str = Field(min_length=1)
    api_key: SecretStr = Field(min_length=1)
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    @classmethod
    def from_environment(cls) -> "ModelSettings":
        """Read credentials only for explicitly requested live execution."""
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ConfigurationError("OPENAI_API_KEY is required for live mode")
        try:
            settings = cls(
                model_name=os.environ.get("AIR_MODEL_NAME", ""),
                api_key=SecretStr(key),
                timeout_seconds=os.environ.get("AIR_MODEL_TIMEOUT_SECONDS", "30"),
            )
        except ValidationError as error:
            raise ConfigurationError("Invalid or missing AIR model configuration") from error
        logger.debug(
            "Model settings loaded model=%s timeout_seconds=%s",
            settings.model_name,
            settings.timeout_seconds,
        )
        return settings
