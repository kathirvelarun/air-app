"""Operational logging, handler ownership and private-payload protection."""

import json
import logging
import subprocess
import sys

import pytest

from air_agent_app.agent.logging_config import configure_logging, get_logger


def test_logger_reuses_named_instance_without_handlers() -> None:
    """Repeated imports reuse a logger and do not attach duplicate output handlers."""
    logger = get_logger("air_agent_app.tests.logging")
    before = tuple(logger.handlers)
    assert get_logger(logger.name) is logger
    assert tuple(logger.handlers) == before


def test_configuration_respects_host_and_validates_level() -> None:
    """Existing host handlers survive setup, while invalid levels always fail."""
    before = tuple(logging.getLogger().handlers)
    configure_logging("debug")
    assert tuple(logging.getLogger().handlers) == before
    with pytest.raises(ValueError, match="Unknown logging level"):
        configure_logging("invalid")


def test_cli_keeps_json_stdout_separate_from_logs() -> None:
    """A fresh process proves default logs use stderr and stdout remains valid JSON."""
    result = subprocess.run(
        [sys.executable, "-m", "air_agent_app.commands.planner", "--scenario", "ready"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["workflow_status"] == "PLAN_READY"
    assert "Planning started" in result.stderr
