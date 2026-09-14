"""Construct the RCA provider integration separately from investigation behavior."""

from langchain_openai import ChatOpenAI

from air_agent_app.agent.config import ModelSettings
from air_agent_app.agent.logging_config import get_logger
from air_agent_app.models.rca_result import InvestigationResult
from air_agent_app.tools.llm.rca_llm_service import RcaLLMService

logger = get_logger(__name__)


def create_rca_llm_service(settings: ModelSettings) -> RcaLLMService:
    """Use tool-call structured output with Pydantic validation.

    Mirrors ``tools/llm/model_factory.py::create_llm_service``: function
    calling (not strict provider JSON schema) because ``InvestigationResult``
    has optional/default fields, and SDK retries are disabled since bounded
    retry is handled explicitly by ``investigation/rca_retry.py``.
    """
    logger.debug(
        "Configuring live RCA LLM service model=%s timeout_seconds=%s",
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
        InvestigationResult,
        method="function_calling",
        strict=False,
        include_raw=True,
    )
    return RcaLLMService(structured_model, model_name=settings.model_name)
