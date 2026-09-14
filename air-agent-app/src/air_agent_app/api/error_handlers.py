"""Map HTTP-boundary failures to safe responses without exposing incident payloads."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.models.exceptions import ConfigurationError, RcaExecutionError

logger = get_logger(__name__)


async def rca_execution_error_handler(request: Request, error: RcaExecutionError) -> JSONResponse:
    """Report a failed RCA investigation without leaking model/provider details.

    This is an execution failure (transport, malformed output, or invented
    source references surviving bounded retry), never the semantic
    `INCONCLUSIVE` outcome -- that is a normal `200` response, not an error.
    """
    logger.error("RCA investigation failed error_type=%s", type(error).__name__)
    return JSONResponse(
        status_code=502,
        content={"detail": "RCA investigation failed after bounded retries"},
    )


async def configuration_error_handler(request: Request, error: ConfigurationError) -> JSONResponse:
    """Report unavailable server settings without returning keys or provider details."""
    logger.error("Planning API unavailable error_type=%s", type(error).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Planner configuration unavailable. Configure OPENAI_API_KEY "
                "and AIR_MODEL_NAME in the API server environment."
            )
        },
    )


async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    """Reject invalid requests without echoing submitted values or raw validation context.

    Shared across every route (registered once in ``create_app``), so the
    message stays generic rather than naming one endpoint's request shape.
    """
    logger.warning("API request rejected path=%s reason=invalid_request", request.url.path)
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})


async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    """Log the failure type and hide implementation details from the HTTP response."""
    logger.error("API request failed path=%s error_type=%s", request.url.path, type(error).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
