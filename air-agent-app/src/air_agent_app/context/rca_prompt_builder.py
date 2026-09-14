"""Turn the accepted evidence-collection payload into LangChain messages.

Used only by ``RcaLLMService`` (`tools/llm/rca_llm_service.py`): the live
model boundary needs a rendered prompt, but the RCA service itself
(`investigation/rca_service.py`) and its offline test double work directly
with typed ``InvestigateResponse``/source-reference objects, never a
rendered prompt string -- see that module's docstring for why.
"""

import json

from langchain_core.prompt_values import ChatPromptValue
from langchain_core.prompts import ChatPromptTemplate

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.context.prompts.rca import PROMPT_VERSION, SYSTEM_PROMPT
from air_agent_app.models.investigate import InvestigateResponse

logger = get_logger(__name__)

_USER_TEMPLATE = """Analyze the following accepted Evidence Collection request for AIR.

Generate a structured InvestigationResult containing:
- Key Findings
- Root Cause Analysis
- Suggestion Plan
- Overall confidence
- Source references used

Use only the evidence supplied below.
Do not invent evidence or source references.
If a defensible RCA cannot be established, return INCONCLUSIVE.

EVIDENCE_COLLECTION_REQUEST:
{evidence_json}

SOURCE_REFERENCES:
{source_reference_map_json}
"""


class RcaPromptBuilder:
    """Keep trusted instructions separate from the serialized evidence payload."""

    def __init__(self) -> None:
        """Compile the versioned system prompt once per builder."""
        self._template = ChatPromptTemplate.from_messages(
            [
                ("system", f"RCA prompt version {PROMPT_VERSION}\n{SYSTEM_PROMPT}"),
                ("human", _USER_TEMPLATE),
            ]
        )

    def build(
        self,
        evidence: InvestigateResponse,
        source_reference_map: dict[str, dict[str, str]],
    ) -> ChatPromptValue:
        """Insert both payloads as JSON values so evidence content is never template syntax."""
        logger.debug(
            "RCA prompt built investigation_id=%s prompt_version=%s evidence_count=%s",
            evidence.investigation_id,
            PROMPT_VERSION,
            len(evidence.evidence),
        )
        return self._template.invoke(
            {
                "evidence_json": evidence.model_dump_json(),
                "source_reference_map_json": json.dumps(source_reference_map),
            }
        )
