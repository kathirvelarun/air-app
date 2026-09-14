"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only; trio is not a project dependency."""
    return "asyncio"
