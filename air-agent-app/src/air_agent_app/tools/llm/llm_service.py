"""LangChain model boundary: structured responses and safe domain errors."""

from collections.abc import Mapping
from time import perf_counter

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from langchain_core.prompt_values import ChatPromptValue
from langchain_core.runnables import Runnable
from openai import OpenAIError
from pydantic import ValidationError

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.investigation.plan_validation import validate_plan
from air_agent_app.models.exceptions import InvalidPlanError, ModelCallError
from air_agent_app.models.planner_output import PlannerOutput

logger = get_logger(__name__)


class LLMService:
    """Execute one logical model call. No transport retries in this lesson."""

    def __init__(self, structured_model: Runnable, model_name: str = "unknown") -> None:
        """Inject the structured model boundary and a label used only for logging."""
        self._structured_model = structured_model
        self._model_name = model_name

    def generate(self, prompt: ChatPromptValue) -> PlannerOutput:
        """Preserve failures without including provider responses in messages."""
        started_at = perf_counter()
        logger.info("LLM call started model=%s", self._model_name)
        try:
            output = self._structured_model.invoke(prompt)
        except (ValidationError, OutputParserException) as error:
            self._log_failure(started_at, error)
            raise InvalidPlanError("Model returned an invalid plan") from error
        except OpenAIError as error:
            self._log_failure(started_at, error)
            raise ModelCallError("Planner model request failed") from error

        raw_message, parsed, parsing_error = self._unpack_structured_output(output)
        structured_output_is_valid = (
            isinstance(raw_message, AIMessage)
            and isinstance(parsed, PlannerOutput)
            and parsing_error is None
        )
        logger.info(
            "LLM call completed model=%s duration_ms=%.2f structured_output=%s",
            self._model_name,
            (perf_counter() - started_at) * 1_000,
            "accepted" if structured_output_is_valid else "rejected",
        )
        if not isinstance(output, Mapping):
            raise InvalidPlanError("Model returned no structured planner response")
        if parsing_error is not None:
            raise InvalidPlanError("Model returned an invalid plan") from (
                parsing_error if isinstance(parsing_error, Exception) else None
            )
        if not structured_output_is_valid:
            raise InvalidPlanError("Model returned no structured planner output")
        # Revalidate even model instances; mutable list values can change.
        return validate_plan(parsed.model_dump())

    @staticmethod
    def _unpack_structured_output(output: object) -> tuple[object, object, object]:
        """Return ``(raw_message, parsed_plan, parsing_error)`` from a model response.

        All three are ``None`` when ``output`` is not the mapping shape LangChain's
        ``include_raw=True`` structured output normally returns (an unexpected
        provider response), so callers can treat that case the same as a rejected
        parse instead of raising an unrelated ``AttributeError``.
        """
        if not isinstance(output, Mapping):
            return None, None, None
        return output.get("raw"), output.get("parsed"), output.get("parsing_error")

    def _log_failure(self, started_at: float, error: Exception) -> None:
        """Record failure timing and type without provider or prompt content."""
        logger.warning(
            "LLM call failed model=%s duration_ms=%.2f error_type=%s",
            self._model_name,
            (perf_counter() - started_at) * 1_000,
            type(error).__name__,
        )
