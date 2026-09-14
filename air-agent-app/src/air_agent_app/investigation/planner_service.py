"""Planning behavior lives here, outside LangGraph nodes."""

from collections.abc import Callable

from langchain_core.prompt_values import ChatPromptValue

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.context.prompt_builder import PromptBuilder
from air_agent_app.models.planner_context import PlannerContext
from air_agent_app.models.planner_output import PlannerOutput

logger = get_logger(__name__)


class PlannerService:
    """Compose prompt preparation and one structured model invocation."""

    def __init__(
        self,
        generate: Callable[[ChatPromptValue], PlannerOutput],
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        """Inject the model boundary so offline tests exercise the same workflow."""
        self._generate = generate
        self._prompt_builder = prompt_builder or PromptBuilder()

    def plan(self, context: PlannerContext) -> PlannerOutput:
        """Build the prompt and request one plan from the injected model boundary."""
        logger.debug("Planner generation started investigation_id=%s", context.investigation_id)
        return self._generate(self._prompt_builder.build(context))
