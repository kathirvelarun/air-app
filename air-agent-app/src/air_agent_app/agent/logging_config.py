"""Logging configuration, called once by the application entry point."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Write operational logs to stderr; leave stdout for program output.

    Existing host logging configuration is respected by basicConfig.
    Invalid levels raise ValueError rather than silently disabling logs.
    """
    numeric_level = logging.getLevelNamesMapping().get(level.upper())
    if numeric_level is None:
        raise ValueError("Unknown logging level")
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module logger without adding handlers or changing host configuration.

    Call with __name__. Log operational counts, outcomes and error types only;
    never pass credentials, prompts, raw evidence or provider exception text.
    """
    return logging.getLogger(name)
