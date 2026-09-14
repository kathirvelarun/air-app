"""Section 9's bounded retry policy for one RCA investigation attempt.

Per `reference/AIR-Investigation.pdf` section 16: a transport timeout, an
invalid structured output, or an invented source reference are all
execution problems worth one bounded retry of the *same* accepted evidence
payload. A model returning ``INCONCLUSIVE`` is not one of these -- that is
a valid semantic outcome (Section 9's "Unknown is a valid result" rule) and
is never retried.
"""

from collections.abc import Callable

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.models.exceptions import (
    InvalidInvestigationResultError,
    RcaExecutionError,
    RcaModelCallError,
    UnknownSourceReferenceError,
)
from air_agent_app.models.rca_result import InvestigationResult

logger = get_logger(__name__)

MAX_RCA_ATTEMPTS = 2

_RETRYABLE_ERRORS = (
    InvalidInvestigationResultError,
    RcaModelCallError,
    UnknownSourceReferenceError,
)


def run_with_retry(attempt: Callable[[], InvestigationResult]) -> InvestigationResult:
    """Run ``attempt`` up to ``MAX_RCA_ATTEMPTS`` times, then raise a single execution error."""
    last_error: Exception | None = None
    for attempt_number in range(1, MAX_RCA_ATTEMPTS + 1):
        try:
            return attempt()
        except _RETRYABLE_ERRORS as error:
            last_error = error
            logger.warning(
                "RCA attempt failed attempt=%s/%s error_type=%s",
                attempt_number,
                MAX_RCA_ATTEMPTS,
                type(error).__name__,
            )
    raise RcaExecutionError(
        f"RCA investigation failed after {MAX_RCA_ATTEMPTS} attempt(s)"
    ) from last_error
