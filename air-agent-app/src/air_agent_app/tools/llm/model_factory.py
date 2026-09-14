"""Construct the provider integration separately from planning behavior."""

from langchain_openai import ChatOpenAI

from air_agent_app.agent.config import ModelSettings
from air_agent_app.agent.logging_config import get_logger
from air_agent_app.models.planner_output import PlannerOutput
from air_agent_app.tools.llm.llm_service import LLMService

logger = get_logger(__name__)


def create_llm_service(settings: ModelSettings) -> LLMService:
    """Use tool-call structured output with Pydantic validation.

    The current schema has optional/default fields, so this uses function
    calling rather than claiming compatibility with provider strict JSON schema.
    SDK retries are disabled; this lesson makes a single planning attempt.
    """
    logger.debug(
        "Configuring live LLM service model=%s timeout_seconds=%s",
        settings.model_name,
        settings.timeout_seconds,
    )
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        max_retries=0,
    )
    structured_model = model.with_structured_output(
        PlannerOutput,
        method="function_calling",
        strict=False,
        include_raw=True,
    )
    return LLMService(structured_model, model_name=settings.model_name)
