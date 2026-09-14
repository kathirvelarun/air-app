"""FastAPI application factory; start with Uvicorn's --factory option."""

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from air_agent_app.agent.logging_config import configure_logging, get_logger
from air_agent_app.api.error_handlers import (
    configuration_error_handler,
    rca_execution_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from air_agent_app.api.evidence_routes import router as evidence_router
from air_agent_app.api.investigate_routes import router as investigate_router
from air_agent_app.api.orchestration_routes import router as orchestration_router
from air_agent_app.api.planning_routes import router as planning_router
from air_agent_app.api.rca_routes import router as rca_router
from air_agent_app.models.exceptions import ConfigurationError, RcaExecutionError

logger = get_logger(__name__)

# air-ui-app's Vite dev server (see air-ui-app/src/airApi.ts, which calls
# this API at http://127.0.0.1:8000 directly, not through a dev proxy).
# Browsers treat "localhost" and "127.0.0.1" as different origins, so both
# host forms are listed.
_DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def _allowed_origins() -> list[str]:
    """Read allowed browser origins from the environment, or use the local UI dev default.

    ``AIR_UI_ORIGINS`` is a comma-separated list, for deployments where the
    UI is served from somewhere other than the local Vite dev server.
    """
    raw = os.environ.get("AIR_UI_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or list(_DEFAULT_ALLOWED_ORIGINS)


def create_app() -> FastAPI:
    """Register routes and safe error handlers without making a model request."""
    configure_logging()
    app = FastAPI(title="AIR Planning API", version="0.1.0")
    origins = _allowed_origins()
    logger.debug("CORS allowed origins=%s", ",".join(origins))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(planning_router)
    app.include_router(evidence_router)
    app.include_router(investigate_router)
    app.include_router(rca_router)
    app.include_router(orchestration_router)
    app.add_exception_handler(ConfigurationError, configuration_error_handler)
    app.add_exception_handler(RcaExecutionError, rca_execution_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    return app
