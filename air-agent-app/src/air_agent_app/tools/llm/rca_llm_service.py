"""LangChain model boundary for the Section 9 LLM Investigation Agent.

Deliberately not structured like ``tools/llm/llm_service.py``'s
``LLMService``: that one takes an already-rendered ``ChatPromptValue`` so
its test double (``OfflinePlanModel``) can freely ignore prompt content --
``PlannerOutput`` has no field that must trace back to specific input data.
``InvestigationResult`` is different: ``source_refs_used`` and every
finding's ``source_refs`` must only ever cite evidence actually supplied
(enforced by ``investigation/rca_post_checks.py``), so a test double needs
real access to *which* evidence and source references it may cite. This
class alone renders the prompt from typed evidence; the RCA client
boundary itself (``RcaLLMClient`` in `investigation/rca_service.py`) stays
typed, and only this live implementation ever converts that into text.
"""

from collections.abc import Mapping
from time import perf_counter

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from openai import OpenAIError
from pydantic import ValidationError

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.context.rca_prompt_builder import RcaPromptBuilder
from air_agent_app.models.exceptions import InvalidInvestigationResultError, RcaModelCallError
from air_agent_app.models.investigate import InvestigateResponse
from air_agent_app.models.rca_result import InvestigationResult

logger = get_logger(__name__)


class RcaLLMService:
    """Execute one logical RCA model call. No transport retries in this class."""

    def __init__(self, structured_model: Runnable, model_name: str = "unknown") -> None:
        """Inject the structured model boundary and a label used only for logging."""
        self._structured_model = structured_model
        self._model_name = model_name
        self._prompt_builder = RcaPromptBuilder()

    def generate(
        self,
        evidence: InvestigateResponse,
        source_reference_map: dict[str, dict[str, str]],
    ) -> InvestigationResult:
        """Render the prompt from typed evidence and request one structured investigation."""
        prompt = self._prompt_builder.build(evidence, source_reference_map)
        started_at = perf_counter()
        logger.info(
            "RCA LLM call started model=%s investigation_id=%s",
            self._model_name,
            evidence.investigation_id,
        )
        try:
            output = self._structured_model.invoke(prompt)
        except (ValidationError, OutputParserException) as error:
            self._log_failure(started_at, error)
            raise InvalidInvestigationResultError(
                "Model returned an invalid investigation result"
            ) from error
        except OpenAIError as error:
            self._log_failure(started_at, error)
            raise RcaModelCallError("RCA model request failed") from error

        raw_message, parsed, parsing_error = self._unpack_structured_output(output)
        structured_output_is_valid = (
            isinstance(raw_message, AIMessage)
            and isinstance(parsed, InvestigationResult)
            and parsing_error is None
        )
        logger.info(
            "RCA LLM call completed model=%s duration_ms=%.2f structured_output=%s",
            self._model_name,
            (perf_counter() - started_at) * 1_000,
            "accepted" if structured_output_is_valid else "rejected",
        )
        if not isinstance(output, Mapping):
            raise InvalidInvestigationResultError("Model returned no structured RCA response")
        if parsing_error is not None:
            raise InvalidInvestigationResultError(
                "Model returned an invalid investigation result"
            ) from (parsing_error if isinstance(parsing_error, Exception) else None)
        if not structured_output_is_valid:
            raise InvalidInvestigationResultError("Model returned no structured RCA output")
        # Revalidate even model instances; mutable list values can change.
        return InvestigationResult.model_validate(parsed.model_dump())

    @staticmethod
    def _unpack_structured_output(output: object) -> tuple[object, object, object]:
        """Return ``(raw_message, parsed_result, parsing_error)`` from a model response.

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
            "RCA LLM call failed model=%s duration_ms=%.2f error_type=%s",
            self._model_name,
            (perf_counter() - started_at) * 1_000,
            type(error).__name__,
        )
