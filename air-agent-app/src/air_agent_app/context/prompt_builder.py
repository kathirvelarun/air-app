"""Turn typed context into LangChain system and human messages."""

from langchain_core.prompt_values import ChatPromptValue
from langchain_core.prompts import ChatPromptTemplate

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.context.prompts.planner import PROMPT_VERSION, SYSTEM_PROMPT
from air_agent_app.models.planner_context import PlannerContext

logger = get_logger(__name__)


class PromptBuilder:
    """Keep trusted instructions separate from serialized incident data."""

    def __init__(self) -> None:
        """Compile versioned trusted instructions once per builder."""
        self._template = ChatPromptTemplate.from_messages(
            [
                ("system", f"Planner prompt version {PROMPT_VERSION}\n{SYSTEM_PROMPT}"),
                ("human", "Incident context (JSON data):\n{context_json}"),
            ]
        )

    def build(self, context: PlannerContext) -> ChatPromptValue:
        """Insert JSON as a value so incident braces are never template syntax."""
        logger.debug(
            "Prompt built investigation_id=%s prompt_version=%s",
            context.investigation_id,
            PROMPT_VERSION,
        )
        return self._template.invoke({"context_json": context.model_dump_json()})
