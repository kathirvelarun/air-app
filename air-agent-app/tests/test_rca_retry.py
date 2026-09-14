"""Bounded RCA retry: retryable execution errors get one retry, then a single raise."""

from uuid import uuid4

import pytest

from air_agent_app.investigation.rca_retry import MAX_RCA_ATTEMPTS, run_with_retry
from air_agent_app.models.exceptions import (
    InvalidInvestigationResultError,
    RcaExecutionError,
    RcaModelCallError,
    UnknownSourceReferenceError,
)
from air_agent_app.models.rca_result import InvestigationResult


def make_result() -> InvestigationResult:
    """Build a minimal valid InvestigationResult for a successful attempt."""
    return InvestigationResult(
        investigation_id=uuid4(),
        investigation_status="INCONCLUSIVE",
        overall_confidence=0.4,
    )


def test_run_with_retry_returns_the_first_successful_attempt() -> None:
    """No retry needed when the first attempt already succeeds."""
    calls = {"count": 0}

    def attempt() -> InvestigationResult:
        """Succeed immediately and record that it ran."""
        calls["count"] += 1
        return make_result()

    result = run_with_retry(attempt)
    assert result.investigation_status == "INCONCLUSIVE"
    assert calls["count"] == 1


@pytest.mark.parametrize(
    "error",
    [
        InvalidInvestigationResultError("bad output"),
        RcaModelCallError("transport failure"),
        UnknownSourceReferenceError("invented ref"),
    ],
)
def test_run_with_retry_recovers_after_one_retryable_failure(error: Exception) -> None:
    """Each documented retryable error succeeds on the second attempt."""
    calls = {"count": 0}

    def attempt() -> InvestigationResult:
        """Fail once with the given retryable error, then succeed."""
        calls["count"] += 1
        if calls["count"] == 1:
            raise error
        return make_result()

    result = run_with_retry(attempt)
    assert result.investigation_status == "INCONCLUSIVE"
    assert calls["count"] == 2


def test_run_with_retry_raises_rca_execution_error_after_exhausting_attempts() -> None:
    """Persistent failure surfaces as one execution error, not the last raw exception."""
    calls = {"count": 0}

    def attempt() -> InvestigationResult:
        """Always fail with the same retryable error."""
        calls["count"] += 1
        raise UnknownSourceReferenceError("always invented")

    with pytest.raises(RcaExecutionError) as excinfo:
        run_with_retry(attempt)
    assert calls["count"] == MAX_RCA_ATTEMPTS
    assert isinstance(excinfo.value.__cause__, UnknownSourceReferenceError)


def test_run_with_retry_does_not_catch_unrelated_exceptions() -> None:
    """A programming error is not swallowed as a retryable RCA failure."""

    def attempt() -> InvestigationResult:
        """Raise an exception type outside the documented retryable set."""
        raise KeyError("not an RCA execution error")

    with pytest.raises(KeyError):
        run_with_retry(attempt)
